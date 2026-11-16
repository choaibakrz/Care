//! [`TrafficMonitor`]: counters, rate limit, automatic and manual blocks.

use std::collections::{BTreeMap, HashMap, VecDeque};
use std::net::IpAddr;
use std::sync::{Arc, Mutex, MutexGuard, OnceLock, PoisonError, Weak};
use std::time::Duration;

use chrono::{DateTime, TimeDelta, Utc};
use domain::{BlockSource, ClientStatus, Clock, RejectReason, SecurityAlert, SecurityAlertKind};
use ipnet::IpNet;
use serde::Serialize;
use tokio::sync::watch;
use utoipa::ToSchema;

use super::blocks::{BlockError, BlockView, NewBlockRequest};
use super::config::{MonitorConfig, ProtectedAddresses, overlaps};
use crate::known_networks::NetworkEntry;

/// Most client addresses tracked at once; the least recently seen is forgotten first.
pub const MAX_TRACKED_CLIENTS: usize = 4096;
/// Answer times kept per second for the p95 (the first ones of the second).
const MAX_LATENCY_SAMPLES: usize = 2048;
/// "Now" for rates and the p95: the last 10 seconds.
const RECENT_SECONDS: i64 = 10;
/// One request costs this many milli-tokens of the bucket.
const TOKEN: u64 = 1000;

/// What the monitor reports outside: alerts for the admin sockets and audit rows.
pub trait MonitorHooks: Send + Sync {
    /// One alert or audit row. Called without the monitor's lock held.
    fn notify(&self, notice: MonitorNotice);
    /// Whether the robot `robot` has a session now (its address is then protected).
    fn robot_connected(&self, robot: &str) -> bool;
}

/// Whether a rule was added or removed (audit `client_blocked` / `client_unblocked`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockAction {
    /// `client_blocked`.
    Blocked,
    /// `client_unblocked`.
    Unblocked,
}

/// An audit row about a rule: target, reason, source, by.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BlockJournal {
    /// Added or removed.
    pub action: BlockAction,
    /// The rule (as it was when removed).
    pub rule: BlockView,
    /// Who removed it (`None`: it expired, or it is an addition, whose author is `rule.by`).
    pub removed_by: Option<String>,
}

/// What the monitor tells [`MonitorHooks`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MonitorNotice {
    /// Send to the admin sockets.
    Alert(SecurityAlert),
    /// Write to the audit journal.
    Journal(BlockJournal),
}

/// The gate's decision for one request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Admission {
    /// Serve it.
    Allowed,
    /// 403 `blocked` (the rule's id, for the logs).
    Blocked {
        /// Rule id.
        rule: String,
    },
    /// 429 `rate_limited`.
    Limited {
        /// Seconds until a request is accepted again (at least 1).
        retry_after_s: u64,
    },
}

/// One answered request, as the counting layer saw it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Outcome {
    /// HTTP status.
    pub status: u16,
    /// The reason a layer marked on a refusal (`RejectMarker`), if any.
    pub marker: Option<RejectReason>,
    /// Time to answer.
    pub latency: Duration,
    /// A refused `POST /auth/login` (401).
    pub login_failure: bool,
    /// A request with a bearer token answered 401 on any other route (Fix R26: refused tokens
    /// count like failed logins).
    pub token_failure: bool,
}

impl Outcome {
    /// Why it was refused, or `None` when it was accepted. The marker wins; otherwise 401 is
    /// `unauthorized`, 403 `forbidden`, 429 `rate_limited`, any other 4xx `invalid`. A 5xx
    /// is not a refusal (it belongs in the logs and `journal_ok`).
    #[must_use]
    pub fn reason(&self) -> Option<RejectReason> {
        self.marker.or(match self.status {
            401 => Some(RejectReason::Unauthorized),
            403 => Some(RejectReason::Forbidden),
            429 => Some(RejectReason::RateLimited),
            400..=499 => Some(RejectReason::Invalid),
            _ => None,
        })
    }
}

/// The numbers of `GET /monitor/summary` the monitor knows.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TrafficTotals {
    /// Requests per second over the last 10 s.
    pub requests_per_s: f64,
    /// Refused requests per second over the last 10 s.
    pub rejected_per_s: f64,
    /// Answer time p95 of the last 10 s; `None` without a request.
    pub p95_ms: Option<u64>,
    /// Active block rules.
    pub blocked_clients: u64,
}

/// One second of `GET /monitor/traffic`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct TrafficPoint {
    /// The second.
    pub at: DateTime<Utc>,
    /// Requests served.
    pub accepted: u64,
    /// Requests refused (any reason).
    pub rejected: u64,
}

/// Refusals of the window by reason.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, ToSchema)]
pub struct RejectedBy {
    /// 401.
    pub unauthorized: u64,
    /// 403 other than a block.
    pub forbidden: u64,
    /// 429.
    pub rate_limited: u64,
    /// Refused by a block rule.
    pub blocked: u64,
    /// 503 `emergency_mode`.
    pub emergency_mode: u64,
    /// Other 4xx.
    pub invalid: u64,
}

impl RejectedBy {
    fn add(&mut self, counts: &[u64; 6]) {
        let [
            unauthorized,
            forbidden,
            rate_limited,
            blocked,
            emergency_mode,
            invalid,
        ] = counts;
        self.unauthorized += unauthorized;
        self.forbidden += forbidden;
        self.rate_limited += rate_limited;
        self.blocked += blocked;
        self.emergency_mode += emergency_mode;
        self.invalid += invalid;
    }
}

/// `GET /monitor/traffic`: one point per second, oldest first.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct TrafficView {
    /// Seconds between points (always 1).
    pub step_s: u32,
    /// Answer time p95 of the window; `null` without a request.
    pub p95_ms: Option<u64>,
    /// The seconds of the window, oldest first.
    pub points: Vec<TrafficPoint>,
    /// Refusals of the window by reason.
    pub rejected_by: RejectedBy,
}

/// One client address of `GET /monitor/clients`. Never a user name.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct ClientView {
    /// The address.
    pub ip: String,
    /// What the server knows the address is (a known network, `Robot <id>`), or `null`.
    pub label: Option<String>,
    /// Requests per second over the last 10 s.
    pub requests_per_s: f64,
    /// Requests of the last 5 minutes.
    pub requests: u64,
    /// Refused requests of the last 5 minutes.
    pub rejected: u64,
    /// Failed logins of the last 5 minutes.
    pub login_failures: u64,
    /// `ok`, `limited` or `blocked`.
    pub status: ClientStatus,
    /// Why it is limited or blocked; `null` when `ok`.
    pub reason: Option<String>,
}

/// Per-address monitoring, rate limit and blocks. In memory only.
pub struct TrafficMonitor {
    config: MonitorConfig,
    protected: ProtectedAddresses,
    networks: Vec<NetworkEntry>,
    clock: Arc<dyn Clock>,
    inner: Mutex<Inner>,
    hooks: OnceLock<Weak<dyn MonitorHooks>>,
    blocks_changed: watch::Sender<u64>,
}

impl std::fmt::Debug for TrafficMonitor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TrafficMonitor")
            .field("config", &self.config)
            .finish_non_exhaustive()
    }
}

#[derive(Default)]
struct Inner {
    seconds: VecDeque<Second>,
    clients: HashMap<IpAddr, Client>,
    rules: Vec<Rule>,
    next_rule: u64,
    /// The address of each robot's current `/ws/robot/{id}` session (set when the session
    /// starts, cleared when it ends): only these are protected as robot addresses.
    robots: HashMap<IpAddr, BTreeMap<String, u64>>,
    /// The id of the last robot session started (R27: a session ends only itself).
    next_session: u64,
}

struct Rule {
    view: BlockView,
    net: IpNet,
}

struct Second {
    at: i64,
    accepted: u64,
    rejected: [u64; 6],
    latencies: Vec<u32>,
}

struct ClientSecond {
    at: i64,
    requests: u64,
    rejected: u64,
}

struct Client {
    seconds: VecDeque<ClientSecond>,
    login_failures: VecDeque<DateTime<Utc>>,
    /// Requests whose bearer token was refused (401), kept as long as login failures.
    token_failures: VecDeque<DateTime<Utc>>,
    /// Milli-tokens left in the bucket.
    tokens: u64,
    refilled_at: DateTime<Utc>,
    excess_start: Option<i64>,
    excess_last: Option<i64>,
    limited_at: Option<DateTime<Utc>>,
    rate_alert_at: Option<DateTime<Utc>>,
    last_seen: DateTime<Utc>,
}

impl TrafficMonitor {
    /// A monitor with no counter and no rule. `networks` label the addresses of the known
    /// networks (`GET /monitor/clients`); the mock has none.
    #[must_use]
    pub fn new(
        config: MonitorConfig,
        networks: Vec<NetworkEntry>,
        clock: Arc<dyn Clock>,
    ) -> TrafficMonitor {
        let (blocks_changed, _) = watch::channel(0);
        TrafficMonitor {
            protected: ProtectedAddresses::new(config.emergency_service.clone()),
            config,
            networks,
            clock,
            inner: Mutex::new(Inner::default()),
            hooks: OnceLock::new(),
            blocks_changed,
        }
    }

    /// Where alerts and audit rows go, and how robot sessions are known. Set once (the
    /// owner is built after the monitor, so it is held weakly); later calls are ignored and
    /// answer `false`.
    pub fn set_hooks(&self, hooks: Weak<dyn MonitorHooks>) -> bool {
        self.hooks.set(hooks).is_ok()
    }

    /// The thresholds in force.
    #[must_use]
    pub fn config(&self) -> &MonitorConfig {
        &self.config
    }

    /// Changes each time a block rule is added: open WebSockets re-check their address
    /// ([`TrafficMonitor::is_blocked`]) and close when it is blocked.
    #[must_use]
    pub fn subscribe_blocks(&self) -> watch::Receiver<u64> {
        self.blocks_changed.subscribe()
    }

    fn inner(&self) -> MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn hooks(&self) -> Option<Arc<dyn MonitorHooks>> {
        self.hooks.get().and_then(Weak::upgrade)
    }

    fn dispatch(&self, notices: Vec<MonitorNotice>) {
        if notices.is_empty() {
            return;
        }
        let hooks = self.hooks();
        for notice in notices {
            if let MonitorNotice::Alert(alert) = &notice {
                tracing::warn!(kind = ?alert.kind, ip = %alert.ip, "{}", alert.message);
            }
            if let Some(hooks) = &hooks {
                hooks.notify(notice);
            }
        }
    }

    /// Whether `ip` may never be limited or blocked: loopback (or no peer address), a
    /// connected robot's address, the emergency service.
    fn is_protected(&self, inner: &Inner, ip: IpAddr) -> bool {
        if ProtectedAddresses::is_local(ip) || self.protected.is_emergency_service(ip) {
            return true;
        }
        inner
            .robots
            .get(&ip)
            .is_some_and(|robots| robots.keys().any(|robot| self.robot_connected(robot)))
    }

    fn robot_connected(&self, robot: &str) -> bool {
        self.hooks()
            .is_some_and(|hooks| hooks.robot_connected(robot))
    }

    /// A robot's `/ws/robot/{id}` session started from `ip`: that address is protected (never
    /// limited or blocked) until the session ends. Several robots may share an address. A
    /// robot token on any other route marks nothing. Returns the session's id, which
    /// [`TrafficMonitor::robot_session_ended`] needs.
    pub fn robot_session_started(&self, ip: IpAddr, robot: &str) -> u64 {
        let ip = ip.to_canonical();
        let mut inner = self.inner();
        inner.next_session = inner.next_session.wrapping_add(1);
        let session = inner.next_session;
        inner
            .robots
            .entry(ip)
            .or_default()
            .insert(robot.to_owned(), session);
        session
    }

    /// Session `session` of `robot` from `ip` ended. A newer session of the same robot (a
    /// reconnect that started before the old one closed) keeps the protection (R27); the
    /// address stops being a robot's when its last session ended.
    pub fn robot_session_ended(&self, ip: IpAddr, robot: &str, session: u64) {
        let ip = ip.to_canonical();
        let mut inner = self.inner();
        let empty = inner.robots.get_mut(&ip).is_some_and(|robots| {
            if robots.get(robot) == Some(&session) {
                robots.remove(robot);
            }
            robots.is_empty()
        });
        if empty {
            inner.robots.remove(&ip);
        }
    }

    /// What [`TrafficMonitor::admit`] would answer now, without taking a token, counting a
    /// hit or an excess (the gate's look before it waits for the identity).
    #[must_use]
    pub fn peek(&self, ip: IpAddr) -> Admission {
        let ip = ip.to_canonical();
        let now = self.clock.now();
        let mut notices = Vec::new();
        let admission = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            if self.is_protected(&inner, ip) {
                Admission::Allowed
            } else if let Some(rule) = inner.rules.iter().find(|rule| rule.net.contains(&ip)) {
                Admission::Blocked {
                    rule: rule.view.id.clone(),
                }
            } else {
                let rate = u64::from(self.config.rate.per_second.get());
                let capacity = u64::from(self.config.rate.burst.get()).saturating_mul(TOKEN);
                let tokens = inner.clients.get(&ip).map_or(capacity, |client| {
                    let elapsed_ms =
                        u64::try_from((now - client.refilled_at).num_milliseconds()).unwrap_or(0);
                    client
                        .tokens
                        .saturating_add(elapsed_ms.saturating_mul(rate))
                        .min(capacity)
                });
                if tokens >= TOKEN {
                    Admission::Allowed
                } else {
                    let per_second = rate.saturating_mul(TOKEN).max(1);
                    Admission::Limited {
                        retry_after_s: (TOKEN - tokens).div_ceil(per_second).max(1),
                    }
                }
            }
        };
        self.dispatch(notices);
        admission
    }

    /// Whether `ip` has had at least `login_failures` refused tokens within `login_window`
    /// (and is not protected): its requests are then refused before the token verifier.
    #[must_use]
    pub fn token_guessing(&self, ip: IpAddr) -> bool {
        let ip = ip.to_canonical();
        let now = self.clock.now();
        let inner = self.inner();
        if self.is_protected(&inner, ip) {
            return false;
        }
        let window = TimeDelta::from_std(self.config.login_window).unwrap_or(TimeDelta::MAX);
        let recent = inner.clients.get(&ip).map_or(0, |client| {
            client
                .token_failures
                .iter()
                .filter(|at| now - **at < window)
                .count()
        });
        recent >= usize::try_from(self.config.login_failures).unwrap_or(usize::MAX)
    }

    /// The gate's decision for one request from `ip` (fills the token bucket, counts a
    /// persistent excess, applies the rules). `exempt`: an authenticated admin's robot
    /// command, mode switch, monitoring or block request, or a robot reconnecting to its own
    /// socket: never refused.
    pub fn admit(&self, ip: IpAddr, exempt: bool) -> Admission {
        let ip = ip.to_canonical();
        let now = self.clock.now();
        let mut notices = Vec::new();
        let admission = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            if exempt || self.is_protected(&inner, ip) {
                Admission::Allowed
            } else if let Some(rule) = inner.rules.iter_mut().find(|rule| rule.net.contains(&ip)) {
                rule.view.hits = rule.view.hits.saturating_add(1);
                Admission::Blocked {
                    rule: rule.view.id.clone(),
                }
            } else {
                self.take_token(&mut inner, ip, now, &mut notices)
            }
        };
        self.dispatch(notices);
        admission
    }

    /// Takes one token of `ip`'s bucket; on excess, counts the run of limited seconds and
    /// blocks the address after `excess_seconds` of them in a row.
    fn take_token(
        &self,
        inner: &mut Inner,
        ip: IpAddr,
        now: DateTime<Utc>,
        notices: &mut Vec<MonitorNotice>,
    ) -> Admission {
        let rate = u64::from(self.config.rate.per_second.get());
        let capacity = u64::from(self.config.rate.burst.get()).saturating_mul(TOKEN);
        let client = inner.client(ip, now, capacity);
        let elapsed_ms = u64::try_from((now - client.refilled_at).num_milliseconds()).unwrap_or(0);
        client.tokens = client
            .tokens
            .saturating_add(elapsed_ms.saturating_mul(rate))
            .min(capacity);
        client.refilled_at = now;
        if client.tokens >= TOKEN {
            client.tokens -= TOKEN;
            return Admission::Allowed;
        }
        let per_second = rate.saturating_mul(TOKEN).max(1);
        let retry_after_s = (TOKEN - client.tokens).div_ceil(per_second).max(1);
        client.limited_at = Some(now);
        let second = now.timestamp();
        let start = match (client.excess_start, client.excess_last) {
            (Some(start), Some(last)) if second - last <= 1 => start,
            _ => second,
        };
        client.excess_start = Some(start);
        client.excess_last = Some(second);
        if second - start + 1 >= i64::from(self.config.excess_seconds) {
            client.excess_start = None;
            client.excess_last = None;
            let why = format!(
                "Over {} requests/s for {} s",
                self.config.rate.per_second, self.config.excess_seconds
            );
            let view =
                self.add_auto_rule(inner, ip, why, now, notices, SecurityAlertKind::AutoBlocked);
            return Admission::Blocked { rule: view.id };
        }
        let alert_due = client.rate_alert_at.is_none_or(|at| {
            (now - at).to_std().unwrap_or(Duration::ZERO) >= self.config.rate_alert_every
        });
        if alert_due {
            client.rate_alert_at = Some(now);
            notices.push(MonitorNotice::Alert(SecurityAlert {
                at: now,
                kind: SecurityAlertKind::RateLimited,
                ip: ip.to_string(),
                message: format!(
                    "{ip} is over {} requests/s: its extra requests are refused (429).",
                    self.config.rate.per_second
                ),
            }));
        }
        Admission::Limited { retry_after_s }
    }

    /// Blocks `ip` for `auto_block_for` (an automatic rule) and reports it.
    #[allow(
        clippy::needless_pass_by_value,
        reason = "owned argument kept for the callers"
    )]
    fn add_auto_rule(
        &self,
        inner: &mut Inner,
        ip: IpAddr,
        reason: String,
        now: DateTime<Utc>,
        notices: &mut Vec<MonitorNotice>,
        kind: SecurityAlertKind,
    ) -> BlockView {
        let expires_at = TimeDelta::from_std(self.config.auto_block_for)
            .ok()
            .and_then(|lifetime| now.checked_add_signed(lifetime));
        let view = self.push_rule(
            inner,
            IpNet::from(ip),
            ip.to_string(),
            reason.clone(),
            BlockSource::Auto,
            None,
            now,
            expires_at,
        );
        notices.push(MonitorNotice::Alert(SecurityAlert {
            at: now,
            kind,
            ip: ip.to_string(),
            message: format!(
                "{ip} blocked automatically for {}: {}.",
                human(self.config.auto_block_for),
                lowercase_first(&reason)
            ),
        }));
        notices.push(MonitorNotice::Journal(BlockJournal {
            action: BlockAction::Blocked,
            rule: view.clone(),
            removed_by: None,
        }));
        view
    }

    #[allow(clippy::too_many_arguments)]
    fn push_rule(
        &self,
        inner: &mut Inner,
        net: IpNet,
        target: String,
        reason: String,
        source: BlockSource,
        by: Option<String>,
        now: DateTime<Utc>,
        expires_at: Option<DateTime<Utc>>,
    ) -> BlockView {
        inner.next_rule = inner.next_rule.saturating_add(1);
        let view = BlockView {
            id: format!("blk-{}", inner.next_rule),
            target,
            reason,
            source,
            created_at: now,
            expires_at,
            by,
            hits: 0,
        };
        inner.rules.push(Rule {
            view: view.clone(),
            net,
        });
        self.blocks_changed
            .send_modify(|generation| *generation = generation.wrapping_add(1));
        view
    }

    /// Removes the rules whose time is over, with an `unblocked` alert and an audit row
    /// each.
    fn expire(inner: &mut Inner, now: DateTime<Utc>, notices: &mut Vec<MonitorNotice>) {
        let (expired, kept): (Vec<Rule>, Vec<Rule>) = std::mem::take(&mut inner.rules)
            .into_iter()
            .partition(|rule| rule.view.expires_at.is_some_and(|at| at <= now));
        inner.rules = kept;
        for rule in expired {
            notices.push(MonitorNotice::Alert(SecurityAlert {
                at: now,
                kind: SecurityAlertKind::Unblocked,
                ip: rule.view.target.clone(),
                message: format!(
                    "{} is no longer blocked: the rule expired.",
                    rule.view.target
                ),
            }));
            notices.push(MonitorNotice::Journal(BlockJournal {
                action: BlockAction::Unblocked,
                rule: rule.view,
                removed_by: None,
            }));
        }
    }

    /// Counts one answered request from `ip`; a failed login may block the address
    /// (`login_failures` within `login_window`).
    pub fn record(&self, ip: IpAddr, outcome: Outcome) {
        let ip = ip.to_canonical();
        let now = self.clock.now();
        let second = now.timestamp();
        let reason = outcome.reason();
        let latency = u32::try_from(outcome.latency.as_millis()).unwrap_or(u32::MAX);
        let window = self.window_seconds();
        let capacity = u64::from(self.config.rate.burst.get()).saturating_mul(TOKEN);
        let mut notices = Vec::new();
        {
            let mut inner = self.inner();
            if let Some(slot) = inner.second(second, window) {
                match reason {
                    Some(reason) => {
                        if let Some(count) = slot.rejected.get_mut(reason.index()) {
                            *count += 1;
                        }
                    }
                    None => slot.accepted += 1,
                }
                if slot.latencies.len() < MAX_LATENCY_SAMPLES {
                    slot.latencies.push(latency);
                }
            }
            let protected = self.is_protected(&inner, ip);
            let already_blocked = inner.rules.iter().any(|rule| rule.net.contains(&ip));
            if outcome.login_failure || outcome.token_failure {
                self.keep_auto_rule_alive(&mut inner, ip, now);
            }
            let login_window =
                TimeDelta::from_std(self.config.login_window).unwrap_or(TimeDelta::MAX);
            let client = inner.client(ip, now, capacity);
            client.last_seen = now;
            client.count(second, reason.is_some(), window);
            let mut burst = false;
            if outcome.login_failure {
                client.login_failures.push_back(now);
                client.prune_failures(now, window);
                let recent = client
                    .login_failures
                    .iter()
                    .filter(|at| now - **at < login_window)
                    .count();
                burst = recent >= usize::try_from(self.config.login_failures).unwrap_or(usize::MAX);
                if burst {
                    client.login_failures.clear();
                }
            }
            let mut token_burst = false;
            if outcome.token_failure {
                client.token_failures.push_back(now);
                client.prune_failures(now, window);
                let recent = client
                    .token_failures
                    .iter()
                    .filter(|at| now - **at < login_window)
                    .count();
                token_burst =
                    recent >= usize::try_from(self.config.login_failures).unwrap_or(usize::MAX);
            }
            if token_burst && !burst && !protected && !already_blocked {
                let why = format!(
                    "{} refused tokens within {}",
                    self.config.login_failures,
                    human(self.config.login_window)
                );
                self.add_auto_rule(
                    &mut inner,
                    ip,
                    why,
                    now,
                    &mut notices,
                    SecurityAlertKind::LoginBurst,
                );
            }
            if burst && !protected && !already_blocked {
                let why = format!(
                    "{} failed sign-ins within {}",
                    self.config.login_failures,
                    human(self.config.login_window)
                );
                self.add_auto_rule(
                    &mut inner,
                    ip,
                    why,
                    now,
                    &mut notices,
                    SecurityAlertKind::LoginBurst,
                );
            }
        }
        self.dispatch(notices);
    }

    /// R27: while failed logins or refused tokens continue, the automatic rule of `ip` is
    /// kept alive (its end moves on), so guessing never finds a gap.
    fn keep_auto_rule_alive(&self, inner: &mut Inner, ip: IpAddr, now: DateTime<Utc>) {
        let Some(until) = TimeDelta::from_std(self.config.auto_block_for)
            .ok()
            .and_then(|life| now.checked_add_signed(life))
        else {
            return;
        };
        let target = IpNet::from(ip);
        for rule in inner
            .rules
            .iter_mut()
            .filter(|rule| rule.view.source == BlockSource::Auto && rule.net == target)
        {
            rule.view.expires_at = Some(until);
        }
    }

    fn window_seconds(&self) -> i64 {
        i64::try_from(self.config.window.as_secs())
            .unwrap_or(i64::MAX)
            .max(1)
    }

    /// Requests and refusals per second and the p95 of the last 10 s, and the active rules.
    #[must_use]
    pub fn totals(&self) -> TrafficTotals {
        let now = self.clock.now();
        let mut notices = Vec::new();
        let totals = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            let from = now.timestamp() - RECENT_SECONDS + 1;
            let recent: Vec<&Second> = inner.seconds.iter().filter(|s| s.at >= from).collect();
            let accepted: u64 = recent.iter().map(|s| s.accepted).sum();
            let rejected: u64 = recent.iter().map(|s| s.rejected.iter().sum::<u64>()).sum();
            TrafficTotals {
                requests_per_s: per_second(accepted + rejected, RECENT_SECONDS),
                rejected_per_s: per_second(rejected, RECENT_SECONDS),
                p95_ms: p95(recent.iter().flat_map(|s| s.latencies.iter().copied())),
                blocked_clients: u64::try_from(inner.rules.len()).unwrap_or(u64::MAX),
            }
        };
        self.dispatch(notices);
        totals
    }

    /// The last `window_s` seconds (1 to the counter window, 300 by default), one point per
    /// second, oldest first; seconds without traffic are zeros.
    #[must_use]
    pub fn traffic(&self, window_s: u32) -> TrafficView {
        let now = self.clock.now();
        let span = i64::from(window_s).clamp(1, self.window_seconds());
        let last = now.timestamp();
        let first = last - span + 1;
        let inner = self.inner();
        let by_second: HashMap<i64, &Second> = inner
            .seconds
            .iter()
            .filter(|s| s.at >= first && s.at <= last)
            .map(|s| (s.at, s))
            .collect();
        let mut rejected_by = RejectedBy::default();
        let mut latencies = Vec::new();
        let points = (first..=last)
            .filter_map(|at| {
                let time = DateTime::from_timestamp(at, 0)?;
                let (accepted, rejected) = by_second.get(&at).map_or((0, 0), |second| {
                    rejected_by.add(&second.rejected);
                    latencies.extend(second.latencies.iter().copied());
                    (second.accepted, second.rejected.iter().sum())
                });
                Some(TrafficPoint {
                    at: time,
                    accepted,
                    rejected,
                })
            })
            .collect();
        TrafficView {
            step_s: 1,
            p95_ms: p95(latencies.into_iter()),
            points,
            rejected_by,
        }
    }

    /// The busiest addresses of the window, busiest first (requests per second over the
    /// last 10 s, then refusals), at most `limit`.
    #[must_use]
    pub fn clients(&self, limit: usize) -> Vec<ClientView> {
        let now = self.clock.now();
        let window = self.window_seconds();
        let mut notices = Vec::new();
        let mut views = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            inner.prune(now, window);
            let inner = &*inner;
            inner
                .clients
                .iter()
                .filter_map(|(ip, client)| self.client_view(inner, *ip, client, now))
                .collect::<Vec<_>>()
        };
        self.dispatch(notices);
        views.sort_by(|a, b| {
            b.requests_per_s
                .total_cmp(&a.requests_per_s)
                .then(b.rejected.cmp(&a.rejected))
                .then(a.ip.cmp(&b.ip))
        });
        views.truncate(limit);
        views
    }

    fn client_view(
        &self,
        inner: &Inner,
        ip: IpAddr,
        client: &Client,
        now: DateTime<Utc>,
    ) -> Option<ClientView> {
        let requests: u64 = client.seconds.iter().map(|s| s.requests).sum();
        if requests == 0 {
            return None;
        }
        let from = now.timestamp() - RECENT_SECONDS + 1;
        let recent: u64 = client
            .seconds
            .iter()
            .filter(|s| s.at >= from)
            .map(|s| s.requests)
            .sum();
        let protected = self.is_protected(inner, ip);
        let rule = inner
            .rules
            .iter()
            .find(|rule| rule.net.contains(&ip))
            .filter(|_| !protected);
        let limited = client
            .limited_at
            .is_some_and(|at| (now - at).num_seconds() < RECENT_SECONDS);
        let (status, reason) = match rule {
            Some(rule) => (ClientStatus::Blocked, Some(rule.view.reason.clone())),
            None if limited => (
                ClientStatus::Limited,
                Some(format!("Over {} requests/s", self.config.rate.per_second)),
            ),
            None => (ClientStatus::Ok, None),
        };
        Some(ClientView {
            ip: ip.to_string(),
            label: self.label(inner, ip),
            requests_per_s: per_second(recent, RECENT_SECONDS),
            requests,
            rejected: client.seconds.iter().map(|s| s.rejected).sum(),
            login_failures: u64::try_from(client.login_failures.len()).unwrap_or(u64::MAX),
            status,
            reason,
        })
    }

    /// What the server knows the address is: a robot it served, a known network, or
    /// nothing. Never a user name.
    fn label(&self, inner: &Inner, ip: IpAddr) -> Option<String> {
        if let Some(robots) = inner.robots.get(&ip).filter(|robots| !robots.is_empty()) {
            let names: Vec<&str> = robots.keys().map(String::as_str).collect();
            return Some(format!("Robot {}", names.join(", ")));
        }
        self.networks
            .iter()
            .filter(|entry| entry.cidr.contains(&ip))
            .max_by_key(|entry| entry.cidr.prefix_len())
            .map(|entry| entry.label.clone())
    }

    /// Every active rule, oldest first.
    #[must_use]
    pub fn blocks(&self) -> Vec<BlockView> {
        let now = self.clock.now();
        let mut notices = Vec::new();
        let views = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            inner.rules.iter().map(|rule| rule.view.clone()).collect()
        };
        self.dispatch(notices);
        views
    }

    /// Adds a manual rule by the admin `by` calling from `caller`. Takes effect on the next
    /// request, open WebSockets of the address included ([`TrafficMonitor::subscribe_blocks`]).
    ///
    /// # Errors
    /// `(field, error)`: an invalid field, `RangeTooBroad`, or `Protected` when the block
    /// would cover the caller, loopback, a connected robot or the emergency service.
    pub fn add_block(
        &self,
        request: &NewBlockRequest,
        by: &str,
        caller: IpAddr,
    ) -> Result<BlockView, (&'static str, BlockError)> {
        let caller = caller.to_canonical();
        let checked = request.check()?;
        let now = self.clock.now();
        let mut notices = Vec::new();
        let result = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            if let Some(what) = self.protected_by(&inner, &checked.net, caller) {
                Err((
                    "target",
                    BlockError::Protected {
                        target: checked.target.clone(),
                        what,
                    },
                ))
            } else {
                let expires_at = checked
                    .expires_in_s
                    .and_then(|seconds| TimeDelta::try_seconds(i64::try_from(seconds).ok()?))
                    .and_then(|lifetime| now.checked_add_signed(lifetime));
                let view = self.push_rule(
                    &mut inner,
                    checked.net,
                    checked.target,
                    checked.reason,
                    BlockSource::Manual,
                    Some(by.to_owned()),
                    now,
                    expires_at,
                );
                notices.push(MonitorNotice::Alert(SecurityAlert {
                    at: now,
                    kind: SecurityAlertKind::Blocked,
                    ip: view.target.clone(),
                    message: format!(
                        "{} blocked by {by}: {}.",
                        view.target,
                        view.reason.trim_end_matches('.')
                    ),
                }));
                notices.push(MonitorNotice::Journal(BlockJournal {
                    action: BlockAction::Blocked,
                    rule: view.clone(),
                    removed_by: None,
                }));
                Ok(view)
            }
        };
        self.dispatch(notices);
        result
    }

    /// Which protected address `net` would cover, in plain words.
    fn protected_by(&self, inner: &Inner, net: &IpNet, caller: IpAddr) -> Option<String> {
        if net.contains(&caller) {
            return Some(format!(
                "your own address ({caller}); an admin must not lock themselves out"
            ));
        }
        let loopback = ["127.0.0.0/8", "::1/128"]
            .iter()
            .filter_map(|text| text.parse::<IpNet>().ok())
            .any(|local| overlaps(&local, net));
        if loopback {
            return Some("loopback (this computer)".to_owned());
        }
        if let Some(robot) = inner
            .robots
            .iter()
            .filter(|(ip, _)| net.contains(*ip))
            .flat_map(|(_, robots)| robots.keys())
            .find(|robot| self.robot_connected(robot))
        {
            return Some(format!(
                "robot {robot} (robots must stay reachable for the emergency stop)"
            ));
        }
        if self.protected.overlaps_emergency_service(net) {
            return Some("the emergency service".to_owned());
        }
        None
    }

    /// Removes a rule (`DELETE /security/blocks/{id}`).
    ///
    /// # Errors
    /// `NotFound` when it expired or was already removed.
    pub fn remove_block(&self, id: &str, by: &str) -> Result<BlockView, BlockError> {
        let now = self.clock.now();
        let mut notices = Vec::new();
        let removed = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            let position = inner.rules.iter().position(|rule| rule.view.id == id);
            position.map(|index| inner.rules.remove(index).view)
        };
        if let Some(view) = &removed {
            notices.push(MonitorNotice::Alert(SecurityAlert {
                at: now,
                kind: SecurityAlertKind::Unblocked,
                ip: view.target.clone(),
                message: format!("{} is no longer blocked: removed by {by}.", view.target),
            }));
            notices.push(MonitorNotice::Journal(BlockJournal {
                action: BlockAction::Unblocked,
                rule: view.clone(),
                removed_by: Some(by.to_owned()),
            }));
        }
        self.dispatch(notices);
        removed.ok_or_else(|| BlockError::NotFound { id: id.to_owned() })
    }

    /// Whether a request from `ip` would be refused by a rule now (protected addresses
    /// never are).
    #[must_use]
    pub fn is_blocked(&self, ip: IpAddr) -> bool {
        let ip = ip.to_canonical();
        let now = self.clock.now();
        let mut notices = Vec::new();
        let blocked = {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            !self.is_protected(&inner, ip) && inner.rules.iter().any(|rule| rule.net.contains(&ip))
        };
        self.dispatch(notices);
        blocked
    }

    /// Expires rules and forgets counters older than the window (run it now and then: the
    /// mock does every 10 s).
    pub fn sweep(&self) {
        let now = self.clock.now();
        let window = self.window_seconds();
        let mut notices = Vec::new();
        {
            let mut inner = self.inner();
            Self::expire(&mut inner, now, &mut notices);
            inner.prune(now, window);
        }
        self.dispatch(notices);
    }
}

impl Inner {
    /// The global counters of `second` (created at the back; older than the window
    /// dropped). A clock that stepped back counts into the latest second.
    fn second(&mut self, second: i64, window: i64) -> Option<&mut Second> {
        while self
            .seconds
            .front()
            .is_some_and(|front| front.at <= second - window)
        {
            self.seconds.pop_front();
        }
        if self.seconds.back().is_none_or(|back| back.at < second) {
            self.seconds.push_back(Second {
                at: second,
                accepted: 0,
                rejected: [0; 6],
                latencies: Vec::new(),
            });
        }
        self.seconds.back_mut()
    }

    /// The counters of `ip`, created with a full bucket; the least recently seen client is
    /// forgotten when [`MAX_TRACKED_CLIENTS`] are tracked.
    fn client(&mut self, ip: IpAddr, now: DateTime<Utc>, capacity: u64) -> &mut Client {
        if !self.clients.contains_key(&ip) && self.clients.len() >= MAX_TRACKED_CLIENTS {
            let oldest = self
                .clients
                .iter()
                .min_by_key(|(_, client)| client.last_seen)
                .map(|(ip, _)| *ip);
            if let Some(oldest) = oldest {
                self.clients.remove(&oldest);
            }
        }
        self.clients.entry(ip).or_insert_with(|| Client {
            seconds: VecDeque::new(),
            login_failures: VecDeque::new(),
            token_failures: VecDeque::new(),
            tokens: capacity,
            refilled_at: now,
            excess_start: None,
            excess_last: None,
            limited_at: None,
            rate_alert_at: None,
            last_seen: now,
        })
    }

    /// Drops counters older than the window and clients with nothing left.
    fn prune(&mut self, now: DateTime<Utc>, window: i64) {
        let second = now.timestamp();
        for client in self.clients.values_mut() {
            while client
                .seconds
                .front()
                .is_some_and(|front| front.at <= second - window)
            {
                client.seconds.pop_front();
            }
            client.prune_failures(now, window);
        }
        self.clients.retain(|_, client| {
            !client.seconds.is_empty()
                || !client.login_failures.is_empty()
                || !client.token_failures.is_empty()
        });
    }
}

impl Client {
    fn count(&mut self, second: i64, rejected: bool, window: i64) {
        while self
            .seconds
            .front()
            .is_some_and(|front| front.at <= second - window)
        {
            self.seconds.pop_front();
        }
        if self.seconds.back().is_none_or(|back| back.at < second) {
            self.seconds.push_back(ClientSecond {
                at: second,
                requests: 0,
                rejected: 0,
            });
        }
        if let Some(slot) = self.seconds.back_mut() {
            slot.requests += 1;
            if rejected {
                slot.rejected += 1;
            }
        }
    }

    fn prune_failures(&mut self, now: DateTime<Utc>, window: i64) {
        let window = TimeDelta::try_seconds(window).unwrap_or(TimeDelta::MAX);
        while self
            .login_failures
            .front()
            .is_some_and(|at| now - *at >= window)
        {
            self.login_failures.pop_front();
        }
        while self
            .token_failures
            .front()
            .is_some_and(|at| now - *at >= window)
        {
            self.token_failures.pop_front();
        }
    }
}

/// `count / seconds`, to one decimal.
fn per_second(count: u64, seconds: i64) -> f64 {
    let count = f64::from(u32::try_from(count).unwrap_or(u32::MAX));
    let seconds = f64::from(i32::try_from(seconds).unwrap_or(1).max(1));
    (count / seconds * 10.0).round() / 10.0
}

/// The 95th percentile (nearest rank) of answer times in ms; `None` without a sample.
fn p95(samples: impl Iterator<Item = u32>) -> Option<u64> {
    let mut sorted: Vec<u32> = samples.collect();
    if sorted.is_empty() {
        return None;
    }
    sorted.sort_unstable();
    let rank = (sorted.len() * 95).div_ceil(100).saturating_sub(1);
    sorted.get(rank).map(|ms| u64::from(*ms))
}

/// `600 s` as "10 min", `45 s` as "45 s".
fn human(duration: Duration) -> String {
    let seconds = duration.as_secs();
    if seconds >= 60 && seconds.is_multiple_of(60) {
        format!("{} min", seconds / 60)
    } else {
        format!("{seconds} s")
    }
}

/// "Over 20 …" → "over 20 …" (inside a sentence).
fn lowercase_first(text: &str) -> String {
    let mut chars = text.chars();
    chars.next().map_or_else(String::new, |first| {
        first.to_lowercase().chain(chars).collect()
    })
}

#[cfg(test)]
mod tests {
    use std::net::IpAddr;
    use std::sync::{Arc, Mutex, PoisonError, Weak};
    use std::time::Duration;

    use chrono::{TimeZone as _, Utc};
    use domain::{ClientStatus, Clock, FakeClock, RejectReason, SecurityAlertKind};

    use super::{Admission, BlockAction, MonitorHooks, MonitorNotice, Outcome, TrafficMonitor};
    use crate::monitor::{BlockError, MonitorConfig, NewBlockRequest};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    /// Records the notices; robot `r2` is connected.
    #[derive(Default)]
    struct Hooks {
        notices: Mutex<Vec<MonitorNotice>>,
    }

    impl MonitorHooks for Hooks {
        fn notify(&self, notice: MonitorNotice) {
            self.notices
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .push(notice);
        }
        fn robot_connected(&self, robot: &str) -> bool {
            robot == "r2"
        }
    }

    impl Hooks {
        fn alerts(&self) -> Vec<SecurityAlertKind> {
            self.notices
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .iter()
                .filter_map(|notice| match notice {
                    MonitorNotice::Alert(alert) => Some(alert.kind),
                    MonitorNotice::Journal(_) => None,
                })
                .collect()
        }
        fn journal(&self) -> Vec<BlockAction> {
            self.notices
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .iter()
                .filter_map(|notice| match notice {
                    MonitorNotice::Journal(row) => Some(row.action),
                    MonitorNotice::Alert(_) => None,
                })
                .collect()
        }
    }

    type Setup = (TrafficMonitor, Arc<FakeClock>, Arc<Hooks>);

    fn monitor(config: MonitorConfig) -> Result<Setup, Box<dyn std::error::Error>> {
        let start = Utc
            .with_ymd_and_hms(2026, 11, 15, 9, 0, 0)
            .single()
            .ok_or("bad date")?;
        let clock = Arc::new(FakeClock::new(start));
        let dyn_clock: Arc<dyn Clock> = clock.clone();
        let monitor = TrafficMonitor::new(config, Vec::new(), dyn_clock);
        let hooks = Arc::new(Hooks::default());
        let as_dyn: Arc<dyn MonitorHooks> = hooks.clone();
        let weak: Weak<dyn MonitorHooks> = Arc::downgrade(&as_dyn);
        assert!(monitor.set_hooks(weak));
        Ok((monitor, clock, hooks))
    }

    fn ok() -> Outcome {
        Outcome {
            status: 200,
            marker: None,
            latency: Duration::from_millis(12),
            login_failure: false,
            token_failure: false,
        }
    }

    const ATTACKER: &str = "203.0.113.42";

    #[test]
    fn burst_then_429_then_auto_block_after_five_seconds() -> TestResult {
        let (monitor, clock, hooks) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = ATTACKER.parse()?;
        for _ in 0..40 {
            assert_eq!(monitor.admit(ip, false), Admission::Allowed);
        }
        assert_eq!(
            monitor.admit(ip, false),
            Admission::Limited { retry_after_s: 1 }
        );
        // One rate_limited alert, not one per refusal.
        assert!(matches!(
            monitor.admit(ip, false),
            Admission::Limited { .. }
        ));
        assert_eq!(hooks.alerts(), [SecurityAlertKind::RateLimited]);
        // Over the limit in each of the next seconds: blocked in the fifth.
        for second in 1..=4 {
            clock.advance(Duration::from_secs(1));
            let mut last = Admission::Allowed;
            for _ in 0..25 {
                last = monitor.admit(ip, false);
            }
            if second < 4 {
                assert!(matches!(last, Admission::Limited { .. }), "second {second}");
            } else {
                assert!(matches!(last, Admission::Blocked { .. }), "second {second}");
            }
        }
        assert!(monitor.is_blocked(ip));
        assert_eq!(
            hooks.alerts(),
            [
                SecurityAlertKind::RateLimited,
                SecurityAlertKind::AutoBlocked
            ]
        );
        let blocks = monitor.blocks();
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks.first().map(|b| b.target.as_str()), Some(ATTACKER));
        assert_eq!(
            blocks.first().map(|b| b.reason.as_str()),
            Some("Over 20 requests/s for 5 s")
        );
        // Ten minutes later the rule expires: unblocked, audit row.
        clock.advance(Duration::from_mins(10));
        assert!(!monitor.is_blocked(ip));
        assert_eq!(
            hooks.alerts().last().copied(),
            Some(SecurityAlertKind::Unblocked)
        );
        assert_eq!(
            hooks.journal(),
            [BlockAction::Blocked, BlockAction::Unblocked]
        );
        Ok(())
    }

    #[test]
    fn a_pause_in_the_excess_restarts_the_count() -> TestResult {
        let (monitor, clock, _) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = ATTACKER.parse()?;
        for second in 0..8 {
            // Every third second the client stays quiet: never 5 limited seconds in a row.
            if second % 3 != 2 {
                for _ in 0..60 {
                    monitor.admit(ip, false);
                }
            }
            clock.advance(Duration::from_secs(1));
        }
        assert!(!monitor.is_blocked(ip));
        Ok(())
    }

    #[test]
    fn exempt_and_protected_addresses_are_never_refused() -> TestResult {
        // The hooks say whether r2 is connected: keep them alive.
        let (monitor, _clock, _hooks) = monitor(MonitorConfig {
            emergency_service: vec!["10.9.0.0/24".parse()?],
            ..MonitorConfig::default()
        })?;
        let admin: IpAddr = "198.51.100.7".parse()?;
        let robot: IpAddr = "10.0.3.12".parse()?;
        // The robot's address is its socket's.
        assert_eq!(
            {
                let _session = monitor.robot_session_started(robot, "r2");
                monitor.admit(robot, true)
            },
            Admission::Allowed
        );
        for ip in ["127.0.0.1", "::1", "0.0.0.0", "10.9.0.5", "10.0.3.12"] {
            let ip: IpAddr = ip.parse()?;
            for _ in 0..500 {
                assert_eq!(monitor.admit(ip, false), Admission::Allowed, "{ip}");
            }
        }
        for _ in 0..500 {
            assert_eq!(monitor.admit(admin, true), Admission::Allowed);
        }
        Ok(())
    }

    #[test]
    fn ten_failed_logins_in_a_minute_block_the_address() -> TestResult {
        let (monitor, clock, hooks) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = ATTACKER.parse()?;
        let failure = Outcome {
            status: 401,
            login_failure: true,
            ..ok()
        };
        for _ in 0..9 {
            monitor.record(ip, failure);
            clock.advance(Duration::from_secs(5));
        }
        assert!(!monitor.is_blocked(ip));
        monitor.record(ip, failure);
        assert!(monitor.is_blocked(ip));
        assert_eq!(hooks.alerts(), [SecurityAlertKind::LoginBurst]);
        // Loopback is never blocked, whatever it does.
        let local: IpAddr = "127.0.0.1".parse()?;
        for _ in 0..30 {
            monitor.record(local, failure);
        }
        assert!(!monitor.is_blocked(local));
        Ok(())
    }

    #[test]
    fn manual_blocks_refuse_protected_targets() -> TestResult {
        let (monitor, _, hooks) = monitor(MonitorConfig {
            emergency_service: vec!["10.9.0.10/32".parse()?],
            ..MonitorConfig::default()
        })?;
        let caller: IpAddr = "198.51.100.7".parse()?;
        let _r2 = monitor.robot_session_started("10.0.3.12".parse()?, "r2");
        let _r9 = monitor.robot_session_started("10.0.3.13".parse()?, "r9");
        let request = |target: &str| NewBlockRequest {
            target: target.to_owned(),
            reason: "Flooding the login page".to_owned(),
            expires_in_s: Some(3600),
        };
        for (target, what) in [
            ("198.51.100.0/24", "your own address"),
            ("127.0.0.1", "loopback"),
            ("::1", "loopback"),
            ("10.0.3.0/24", "robot r2"),
            ("10.9.0.0/24", "the emergency service"),
        ] {
            match monitor.add_block(&request(target), "Admin A", caller) {
                Err(("target", BlockError::Protected { what: said, .. })) => {
                    assert!(said.starts_with(what), "{target}: {said}");
                }
                other => return Err(format!("{target}: {other:?}").into()),
            }
        }
        assert!(matches!(
            monitor.add_block(&request("0.0.0.0/0"), "Admin A", caller),
            Err(("target", BlockError::RangeTooBroad { .. }))
        ));
        // A robot that is not connected (r9) does not protect its old address.
        let rule = monitor
            .add_block(&request("10.0.3.13"), "Admin A", caller)
            .map_err(|(field, error)| format!("{field}: {error}"))?;
        assert_eq!(rule.id, "blk-1");
        assert_eq!(rule.by.as_deref(), Some("Admin A"));
        assert!(monitor.is_blocked("10.0.3.13".parse()?));
        assert!(matches!(
            monitor.admit("10.0.3.13".parse()?, false),
            Admission::Blocked { .. }
        ));
        assert_eq!(monitor.blocks().first().map(|b| b.hits), Some(1));
        monitor.remove_block("blk-1", "Admin A")?;
        assert!(matches!(
            monitor.remove_block("blk-1", "Admin A"),
            Err(BlockError::NotFound { .. })
        ));
        assert_eq!(
            hooks.alerts(),
            [SecurityAlertKind::Blocked, SecurityAlertKind::Unblocked]
        );
        Ok(())
    }

    #[test]
    fn a_new_rule_wakes_the_watchers() -> TestResult {
        let (monitor, _, _) = monitor(MonitorConfig::default())?;
        let watcher = monitor.subscribe_blocks();
        let before = *watcher.borrow();
        let request = NewBlockRequest {
            target: ATTACKER.to_owned(),
            reason: "test".to_owned(),
            expires_in_s: None,
        };
        monitor
            .add_block(&request, "Admin A", "198.51.100.7".parse()?)
            .map_err(|(_, error)| error.to_string())?;
        assert_ne!(*watcher.borrow(), before);
        Ok(())
    }

    #[test]
    fn counters_feed_traffic_clients_and_totals() -> TestResult {
        let (monitor, clock, _) = monitor(MonitorConfig::default())?;
        let busy: IpAddr = ATTACKER.parse()?;
        let quiet: IpAddr = "10.0.3.12".parse()?;
        for _ in 0..30 {
            monitor.record(busy, ok());
        }
        for status in [401, 403, 404, 429, 500] {
            monitor.record(busy, Outcome { status, ..ok() });
        }
        monitor.record(
            busy,
            Outcome {
                status: 403,
                marker: Some(RejectReason::Blocked),
                ..ok()
            },
        );
        monitor.record(
            busy,
            Outcome {
                status: 503,
                marker: Some(RejectReason::EmergencyMode),
                ..ok()
            },
        );
        clock.advance(Duration::from_secs(1));
        monitor.record(quiet, ok());
        let traffic = monitor.traffic(300);
        assert_eq!(traffic.points.len(), 300);
        assert_eq!(traffic.step_s, 1);
        let accepted: u64 = traffic.points.iter().map(|p| p.accepted).sum();
        let rejected: u64 = traffic.points.iter().map(|p| p.rejected).sum();
        assert_eq!(accepted, 32, "30 ok, the 500, the quiet one");
        assert_eq!(rejected, 6);
        let by = traffic.rejected_by;
        assert_eq!(
            [
                by.unauthorized,
                by.forbidden,
                by.rate_limited,
                by.blocked,
                by.emergency_mode,
                by.invalid
            ],
            [1, 1, 1, 1, 1, 1]
        );
        assert_eq!(traffic.p95_ms, Some(12));
        assert_eq!(monitor.traffic(5).points.len(), 5);
        let totals = monitor.totals();
        assert!((totals.requests_per_s - 3.8).abs() < 1e-9, "{totals:?}");
        assert!((totals.rejected_per_s - 0.6).abs() < 1e-9, "{totals:?}");
        let clients = monitor.clients(20);
        assert_eq!(clients.len(), 2);
        let first = clients.first().ok_or("no client")?;
        assert_eq!(first.ip, ATTACKER);
        assert_eq!(first.requests, 37);
        assert_eq!(first.rejected, 6);
        assert_eq!(first.status, ClientStatus::Ok);
        assert_eq!(first.label, None);
        assert_eq!(monitor.clients(1).len(), 1);
        // Five minutes later the counters are gone.
        clock.advance(Duration::from_secs(301));
        assert!(monitor.clients(20).is_empty());
        assert_eq!(monitor.totals().p95_ms, None);
        Ok(())
    }

    #[test]
    fn a_robot_address_is_protected_only_during_its_session() -> TestResult {
        let (monitor, _clock, _hooks) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = "10.0.3.12".parse()?;
        let caller: IpAddr = "198.51.100.7".parse()?;
        let request = NewBlockRequest {
            target: "10.0.3.0/24".to_owned(),
            reason: "x".to_owned(),
            expires_in_s: None,
        };
        let session = monitor.robot_session_started(ip, "r2");
        assert!(matches!(
            monitor.add_block(&request, "Admin A", caller),
            Err(("target", BlockError::Protected { .. }))
        ));
        for _ in 0..100 {
            assert_eq!(monitor.admit(ip, false), Admission::Allowed);
        }
        monitor.robot_session_ended(ip, "r2", session);
        let rule = monitor
            .add_block(&request, "Admin A", caller)
            .map_err(|(_, error)| error.to_string())?;
        assert_eq!(rule.target, "10.0.3.0/24");
        assert!(monitor.is_blocked(ip));
        Ok(())
    }

    #[test]
    fn refused_tokens_block_like_failed_logins_and_peek_takes_nothing() -> TestResult {
        let (monitor, _clock, hooks) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = ATTACKER.parse()?;
        for _ in 0..100 {
            assert_eq!(monitor.peek(ip), Admission::Allowed);
        }
        let refused = Outcome {
            status: 401,
            token_failure: true,
            ..ok()
        };
        for _ in 0..9 {
            monitor.record(ip, refused);
        }
        assert!(!monitor.token_guessing(ip));
        monitor.record(ip, refused);
        assert!(monitor.token_guessing(ip));
        assert!(monitor.is_blocked(ip));
        assert!(matches!(monitor.peek(ip), Admission::Blocked { .. }));
        assert_eq!(hooks.alerts(), [SecurityAlertKind::LoginBurst]);
        Ok(())
    }

    #[test]
    fn ipv4_mapped_addresses_are_the_same_client() -> TestResult {
        let (monitor, _clock, _hooks) = monitor(MonitorConfig::default())?;
        let request = NewBlockRequest {
            target: ATTACKER.to_owned(),
            reason: "x".to_owned(),
            expires_in_s: None,
        };
        monitor
            .add_block(&request, "Admin A", "198.51.100.7".parse()?)
            .map_err(|(_, error)| error.to_string())?;
        let mapped: IpAddr = "::ffff:203.0.113.42".parse()?;
        assert!(monitor.is_blocked(mapped));
        // A mapped loopback is loopback.
        let local: IpAddr = "::ffff:127.0.0.1".parse()?;
        for _ in 0..100 {
            assert_eq!(monitor.admit(local, false), Admission::Allowed);
        }
        Ok(())
    }

    #[test]
    fn a_stale_session_end_keeps_the_live_session_and_robots_share_an_address() -> TestResult {
        let (monitor, _clock, _hooks) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = "10.0.3.12".parse()?;
        let caller: IpAddr = "198.51.100.7".parse()?;
        let request = NewBlockRequest {
            target: "10.0.3.12".to_owned(),
            reason: "x".to_owned(),
            expires_in_s: None,
        };
        // r2 reconnects before its old session closed: the old end must not drop the new one.
        let old = monitor.robot_session_started(ip, "r2");
        let new = monitor.robot_session_started(ip, "r2");
        monitor.robot_session_ended(ip, "r2", old);
        assert!(matches!(
            monitor.add_block(&request, "Admin A", caller),
            Err(("target", BlockError::Protected { .. }))
        ));
        // A second robot on the same address; r2 leaving keeps the address while r9 is on it
        // (r9 counts as connected only through the hooks, which say r2: so add r2 again).
        let other = monitor.robot_session_started(ip, "r9");
        monitor.robot_session_ended(ip, "r2", new);
        let again = monitor.robot_session_started(ip, "r2");
        monitor.robot_session_ended(ip, "r9", other);
        assert!(matches!(
            monitor.add_block(&request, "Admin A", caller),
            Err(("target", BlockError::Protected { .. }))
        ));
        monitor.robot_session_ended(ip, "r2", again);
        assert!(monitor.add_block(&request, "Admin A", caller).is_ok());
        Ok(())
    }

    #[test]
    fn continued_guessing_keeps_the_automatic_block_alive() -> TestResult {
        let (monitor, clock, _hooks) = monitor(MonitorConfig::default())?;
        let ip: IpAddr = ATTACKER.parse()?;
        let refused = Outcome {
            status: 401,
            token_failure: true,
            ..ok()
        };
        for _ in 0..10 {
            monitor.record(ip, refused);
        }
        assert!(monitor.is_blocked(ip));
        // Two block lifetimes of guesses, one every 30 s: never a gap.
        for _ in 0..40 {
            clock.advance(Duration::from_secs(30));
            assert!(monitor.is_blocked(ip));
            monitor.record(ip, refused);
        }
        // Guessing stops: the rule ends 10 minutes after the last guess.
        clock.advance(Duration::from_secs(601));
        assert!(!monitor.is_blocked(ip));
        Ok(())
    }
}
