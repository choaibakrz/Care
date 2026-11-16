//! `MockServices`: every service trait with canned, clearly invented data (`--mock`).
//! Jobs 4 and 5 build against it before the real server exists.
//!
//! The data is the admin console's own demo clinic, so the console shows the same clinic
//! against `--mock` as in its in-browser demo: the plan is `seed/clinic_map.json` and the
//! fleet, stock, zones and schedule come from `seed/demo_fleet.json` (both embedded at build
//! time, both `"marque": "inventé"`). Tasks, audit rows and the incident are invented here.
//!
//! What the mock does and does not do:
//! - mutations (task create and cancel, stock adjust, zone put and delete, schedule put,
//!   robot commands, clinic plans) change **in-memory** state only; nothing is stored or
//!   journaled, and everything is lost when the server stops;
//! - the four demo robots are simulated in-process (`crate::sim`, started by
//!   `Wiring::mock`): each is a real hub session that this service handles like a WebSocket
//!   robot, so they move along simple rounds of their floor, take tasks and obey commands;
//!   `robot-r2` is the `fake_robot` slot, offline until the `fake_robot` binary connects
//!   (token `mock-robot`, or `mock-robot-<id>` for any robot id), so a command to it is
//!   refused (409 `robot_offline`) as on the real server until then;
//! - mutations publish their console events on the hub (`task.updated`, `robot.updated`,
//!   `inventory.updated`, `zone.updated`/`zone.deleted`, `schedule.updated`, `alert`), so a
//!   second console sees them live;
//! - a new task goes to a free connected robot (the `fake_robot` first, then a demo robot of
//!   the destination's floor; ruling R21: never a demo robot of another floor) as
//!   `task.assign`; tasks wait in `requested` while no robot fits (the seed's four invented
//!   tasks are never sent to a robot);
//! - whether a robot is connected is read from the hub; a command or an emergency stop to a
//!   robot with no session is 409 `robot_offline`, and the shown state changes only after
//!   the command was queued;
//! - a robot that goes away (or says `hello` without a running task) fails its started task
//!   (`robot_lost`) and releases a task only sent to it; a robot that reconnected before its
//!   old session closed stays connected.
//! - places, items and plans are not validated the way the live server validates them
//!   (no grid, no reachability; `ClinicPlan::validate` comes with Task 10b).
//! - the brain (`POST /brain/*`, Task A6) answers clearly labelled canned drafts
//!   ("MOCK TRANSLATION …"), keeps no text and adds one audit row per call
//!   (see [`brain`]).
//! - Task A8, for real in memory: emergency mode (`mode`: the switch, robots cleared from
//!   the corridors, no dispatch while it is on), the tablet registry (`tablets`: the
//!   console's demo tablets, batteries, free and hand out, `device.updated`), monitoring and
//!   blocks (`monitor`: the shared `security::TrafficMonitor`, fed by
//!   `MockStack::apply_monitored`; `security.alert` to admin sockets), service statistics
//!   from the mock's tasks, `map.updated` on every plan change, and task routes that never
//!   invent a floor (404 `no_route` without a start).
//!
//! Login (Task A7): `{account_key}`, the key derived from user `admin`, `nurse`, `doctor`,
//! `therapist` or `reception` with the password [`MOCK_PASSWORD`] and account clinic id
//! [`MOCK_ACCOUNT_CLINIC_ID`] (`docs/accounts.md`). **Mock compatibility until frontend task
//! F9:** the A3 body `{username, password}` (also `u-admin`, `u-nurse`, ...) is still
//! accepted here; the mock derives the key itself. Enrolment codes and enrolment work in
//! memory ([`accounts`]). The token is `mock-<role>` (`mock-account-<id>` for an enrolled
//! account); `mock-robot` is a robot token (`robot-r2`) and `mock-robot-<id>` the robot
//! token of robot `<id>` (accepted by this mock verifier only; the live server's verifier
//! never knows them).

use std::collections::{HashSet, VecDeque};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

use async_trait::async_trait;
use chrono::{DateTime, Duration as ChronoDuration, TimeZone as _, Utc};
use domain::{
    AccountKey, AccountTag, Actor, ApplyOutcome, ClinicId, Clock, CommandName, DeviceId,
    DomainError, FailureReason, ItemId, OwnerLabel, Page, PlaceId, ReconcileOutcome, RobotId,
    RobotStatus, Role, RoundResult, ScheduleId, SeenItem, ShelfCount, StockAdjustReason,
    StockLevel, SystemClock, SystemModeState, Task, TaskFilter, TaskId, TaskKind, TaskState,
    ZoneId, ZoneKind, ZoneVersions,
};
use locations::{
    ClinicMap, ClinicPlan, LiveSnapshot, MapVersion, MapView, Method, Point2, PositionEstimate,
    RobotLive, TabletLive,
};
use realtime::{
    AlertKind, AppErrorCode, AppEvent, DeliveryState, Hub, Incident, IncidentCode, IncidentId,
    IncidentSeverity, RealtimeError, RobotDown, RobotPose, RobotSession, RobotUp,
    SIMULATED_REQUEST_LABEL, TaskHistoryEntry, WireZone, ZoneDeliveryEntry,
};
use security::{
    ClientIdentity, ClientNetwork, MonitorConfig, SecurityError, TokenVerifier, TrafficMonitor,
    VerifiedIdentity,
};
use uuid::Uuid;

pub mod accounts;
pub mod brain;
mod follow;
mod mode;
mod monitor;
mod tablets;

pub use mode::HELD_LABEL;
pub use tablets::MOCK_TABLET_TOKEN_PREFIX;

pub use accounts::{MOCK_ACCOUNT_CLINIC_ID, MOCK_ACCOUNT_TOKEN_PREFIX, MOCK_PEPPER};

use super::demo::DemoFleet;
use super::{
    AuditQueryService, AuthService, ClinicService, DeviceAdminService, IncidentService,
    InventoryService, JournalStatus, LocationService, MapService, MonitorService, RobotService,
    RouteService, ScheduleService, ServiceStatsService, StatsService, SystemModeService,
    TaskService, ZoneService,
};
use crate::dto::{
    AccountView, AssignTabletRequest, AuditEntry, AuditPageView, AuditQueryParams, AuditResult,
    BlockView, ClientView, ClinicSummary, CommandReceipt, EnrolRequest, EnrolledView,
    EnrolmentCodeRequest, EnrolmentCodeView, HeatView, KeyDerivationParams, LoginResponse, MeView,
    MonitorSummaryView, NewBlockRequest, NewTask, RevertReceipt, RobotView, RouteView, ScanBody,
    SchedulePatch, ScheduleView, ServiceStatsView, SetModeRequest, TabletView, TaskPage, TaskView,
    TrafficView, VersionedOverlay, VersionedPlan, ZoneInput, ZoneView,
};
use crate::error::ApiError;
use crate::services::auth::derivation_params;
use crate::services::robots::LoggedCommand;
use crate::sim::{SimRobotConfig, Unreachable};

/// The password of every mock user (printed in the startup log and in `docs/dev-setup.md`).
pub const MOCK_PASSWORD: &str = "mock";
/// Prefix of every mock token: `mock-<role>`.
pub const MOCK_TOKEN_PREFIX: &str = "mock-";
/// The robot of the `mock-robot` token, the `fake_robot` slot (offline until the
/// `fake_robot` binary connects).
pub const MOCK_ROBOT_ID: &str = "robot-r2";
/// Prefix of the mock robot token of any robot: `mock-robot-<id>`.
pub const MOCK_ROBOT_TOKEN_PREFIX: &str = "mock-robot-";
/// How often the in-process robots of `--mock` report their state (smooth motion on the map;
/// the `fake_robot` binary reports every second).
pub const MOCK_SIM_STATE_INTERVAL: std::time::Duration = std::time::Duration::from_millis(200);
/// How long a mock login token is said to last.
pub const MOCK_TOKEN_TTL_H: i64 = 12;

/// The console's demo clinic plan.
const SEED_PLAN: &str = include_str!("../../seed/clinic_map.json");
/// The console's demo fleet, stock, zones and schedule.
const SEED_FLEET: &str = include_str!("../../seed/demo_fleet.json");
/// Suffix of every mock robot name.
const MOCK_SUFFIX: &str = " (mock)";
/// The note on a mock command receipt sent to a simulated robot's session.
const MOCK_SENT_NOTE: &str = "mock server: sent to the simulated robot";
/// How many robot event ids are remembered to drop replays.
const SEEN_EVENTS: usize = 512;
/// Default and largest audit page.
const AUDIT_DEFAULT_LIMIT: u32 = 100;
/// Largest audit page.
const AUDIT_MAX_LIMIT: u32 = 500;

/// Canned data, labelled invented. Accepts the mock token `mock-<role>` for every role.
pub struct MockServices {
    clock: Arc<dyn Clock>,
    hub: Arc<Hub>,
    started: DateTime<Utc>,
    data: Mutex<MockData>,
    /// Counters, rate limit and blocks (Task A8), shared with the transport stack.
    traffic: Arc<TrafficMonitor>,
    /// `SERVICE_STATS_MIN_COUNT`: places with fewer requests are folded into `other`.
    stats_min_place_count: u32,
}

/// The settings of the mock that come from the configuration (Task A8).
pub struct MockSettings {
    /// The traffic monitor the transport stack feeds (`build_mock_app` reads it from the
    /// state).
    pub traffic: Arc<TrafficMonitor>,
    /// `SERVICE_STATS_MIN_COUNT` (0: no folding).
    pub stats_min_place_count: u32,
}

impl std::fmt::Debug for MockServices {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MockServices")
            .field("started", &self.started)
            .finish_non_exhaustive()
    }
}

impl Default for MockServices {
    fn default() -> Self {
        MockServices::new()
    }
}

/// The in-memory state the mutations change.
struct MockData {
    plans: Vec<MockPlan>,
    robots: Vec<MockRobot>,
    tasks: Vec<TaskView>,
    next_task: u32,
    items: Vec<StockLevel>,
    zones: Vec<ZoneView>,
    schedules: Vec<ScheduleView>,
    audit: Vec<AuditEntry>,
    incidents: Vec<Incident>,
    /// Robot event ids already applied (replays are duplicates).
    seen_events: VecDeque<Uuid>,
    /// Version of the zone set sent to robots (`zones.update`).
    zone_set_version: u64,
    /// The invented tasks of the seed: never sent to a robot (they tell a story).
    seed_tasks: Vec<TaskId>,
    /// The demo accounts and those enrolled since start (Task A7).
    accounts: Vec<accounts::MockAccount>,
    /// Enrolment codes issued since start (their HMAC only).
    codes: Vec<accounts::MockCode>,
    /// Recent robot commands, for the admin's revert.
    commands: VecDeque<LoggedCommand>,
    /// Robots latched in emergency stop (ruling R24): only an admin's `resume` re-arms them.
    estop_latched: std::collections::HashSet<RobotId>,
    /// Emergency mode (Task A8), memory only in the mock.
    mode: SystemModeState,
    /// The robots the server paused on entering emergency mode (resumed on exit).
    paused_by_emergency: HashSet<RobotId>,
    /// The tablet registry (Task A8).
    tablets: Vec<tablets::MockTablet>,
    /// The running `follow` tasks (Step C1).
    follows: Vec<follow::Follow>,
}

/// One stored plan.
struct MockPlan {
    id: ClinicId,
    version: u64,
    active: bool,
    /// The effective plan: `base` with `overlay` applied.
    plan: ClinicPlan,
    base: ClinicPlan,
    overlay: locations::PlanOverlay,
    updated_at: DateTime<Utc>,
}

impl MockPlan {
    /// A stored plan from a base and its modifications; the effective plan is validated.
    fn new(
        id: ClinicId,
        version: u64,
        active: bool,
        base: ClinicPlan,
        overlay: locations::PlanOverlay,
        updated_at: DateTime<Utc>,
    ) -> Result<MockPlan, ApiError> {
        let mut stored = MockPlan {
            id,
            version,
            active,
            plan: base.clone(),
            base,
            overlay,
            updated_at,
        };
        stored.set(stored.base.clone(), stored.overlay.clone())?;
        Ok(stored)
    }

    /// Replaces base and overlay if the effective plan validates (nothing changes otherwise).
    fn set(&mut self, base: ClinicPlan, overlay: locations::PlanOverlay) -> Result<(), ApiError> {
        for unknown in overlay.unknown_removals(&base) {
            tracing::warn!(removal = %unknown, "overlay removes an id the base plan lacks; ignored");
        }
        let effective = overlay.apply(&base);
        effective.validate()?;
        self.plan = effective;
        self.base = base;
        self.overlay = overlay;
        Ok(())
    }

    fn versioned_of(&self, plan: &ClinicPlan) -> VersionedPlan {
        VersionedPlan {
            id: self.id.clone(),
            version: self.version,
            active: self.active,
            plan: plan.clone(),
        }
    }

    fn summary(&self) -> ClinicSummary {
        ClinicSummary {
            id: self.id.clone(),
            name: self.plan.name.clone(),
            version: self.version,
            active: self.active,
            updated_at: self.updated_at,
        }
    }

    fn versioned(&self) -> VersionedPlan {
        VersionedPlan {
            id: self.id.clone(),
            version: self.version,
            active: self.active,
            plan: self.plan.clone(),
        }
    }
}

/// One robot: its view. Whether it is connected is always read from the hub
/// (`Hub::is_connected`), never stored.
struct MockRobot {
    view: RobotView,
    /// The dock of a demo robot (the in-process robots start and dock there).
    home: Option<PlaceId>,
    /// When its last `robot.updated` was published (the heartbeat skips fresh robots).
    last_event: Option<tokio::time::Instant>,
}

/// A mock user: the names it logs in with, its role, its owner label, and its account key
/// (Task A7): the published derivation of `names[0]` / [`MOCK_PASSWORD`] with account clinic
/// id [`MOCK_ACCOUNT_CLINIC_ID`] (checked by a unit test). The mock knows the account by
/// `HMAC(MOCK_PEPPER, key)` only.
struct MockUser {
    names: [&'static str; 2],
    role: Role,
    label: &'static str,
    key: &'static str,
}

/// The mock users (password [`MOCK_PASSWORD`]).
const MOCK_USERS: &[MockUser] = &[
    MockUser {
        names: ["admin", "u-admin"],
        role: Role::Admin,
        label: "Admin (mock)",
        key: "0840a2acb742ff183c54960bd29738c2081adb0ea76d396e6cfbc2c00e0f1736",
    },
    MockUser {
        names: ["nurse", "u-nurse"],
        role: Role::Nurse,
        label: "Ward 2 nurse (mock)",
        key: "73003a80fdfedb1362422d0c0bbba519954e1ec4f02426ee3dfcbf77442ea97d",
    },
    MockUser {
        names: ["doctor", "u-doctor"],
        role: Role::Doctor,
        label: "Ward 2 doctor (mock)",
        key: "676621256f1dc60c8ef0ee3efe7fd4f09b112147dc3059c02c37f186fe20af2f",
    },
    MockUser {
        names: ["therapist", "u-therapist"],
        role: Role::Therapist,
        label: "Therapy desk (mock)",
        key: "2d2dbd84494abde4b4e7c5d635ac8072e721a7d9bf9221d41d700edfb90803f0",
    },
    MockUser {
        names: ["reception", "u-reception"],
        role: Role::Reception,
        label: "Reception desk (mock)",
        key: "9c10ee3f95743d19b0a8b2dcc113e931c26a72410122663755e1cc0b00d28c23",
    },
];

impl MockServices {
    /// The mock set on the system clock.
    #[must_use]
    pub fn new() -> MockServices {
        MockServices::with_clock(Arc::new(SystemClock))
    }

    /// The mock set on a given clock (tests pass a fake clock).
    ///
    /// The embedded seed files are checked by a unit test; should they ever not parse, the
    /// mock starts with no plan and no fleet and logs why, rather than refusing to start.
    #[must_use]
    pub fn with_clock(clock: Arc<dyn Clock>) -> MockServices {
        let hub = Arc::new(Hub::with_clock(clock.clone()));
        MockServices::with_hub(clock, hub)
    }

    /// The mock set publishing its events on `hub` (what `--mock` and the tests serve).
    #[must_use]
    pub fn with_hub(clock: Arc<dyn Clock>, hub: Arc<Hub>) -> MockServices {
        let traffic = Arc::new(TrafficMonitor::new(
            MonitorConfig::default(),
            Vec::new(),
            clock.clone(),
        ));
        MockServices::with_settings(
            clock,
            hub,
            MockSettings {
                traffic,
                stats_min_place_count: 0,
            },
        )
    }

    /// The mock set with the configured monitor and statistics settings (what `--mock`
    /// serves). Call [`MockServices::attach_monitor_hooks`] once it is in an `Arc`.
    #[must_use]
    pub fn with_settings(
        clock: Arc<dyn Clock>,
        hub: Arc<Hub>,
        settings: MockSettings,
    ) -> MockServices {
        let started = clock.now();
        let data = match MockData::from_seeds(started) {
            Ok(data) => data,
            Err(reason) => {
                tracing::error!(%reason, "mock seed data could not be read; serving empty data");
                MockData::empty()
            }
        };
        MockServices {
            clock,
            hub,
            started,
            data: Mutex::new(data),
            traffic: settings.traffic,
            stats_min_place_count: settings.stats_min_place_count,
        }
    }

    /// Makes this mock the traffic monitor's hooks (alerts to admin sockets, audit rows,
    /// robot sessions). Held weakly by the monitor.
    pub fn attach_monitor_hooks(self: &Arc<Self>) {
        let hooks: Arc<dyn security::MonitorHooks> = self.clone();
        if !self.traffic.set_hooks(Arc::downgrade(&hooks)) {
            tracing::warn!("mock: the traffic monitor already had hooks");
        }
    }

    /// The traffic monitor (shared with the transport stack).
    #[must_use]
    pub fn traffic(&self) -> Arc<TrafficMonitor> {
        self.traffic.clone()
    }

    /// Every `interval` (10 s): `device.updated` for the tablets whose battery or online
    /// state changed (so at most every 10 s per tablet), and the monitor's sweep (expired
    /// blocks, old counters). Until aborted.
    #[must_use]
    pub fn spawn_device_ticker(
        self: Arc<Self>,
        interval: std::time::Duration,
    ) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(interval);
            ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                ticker.tick().await;
                for device in self.tablets_due() {
                    self.publish(AppEvent::DeviceUpdated { device });
                }
                self.traffic.sweep();
            }
        })
    }

    /// Publishes `robot.updated` for every connected mock robot each `interval` (1 s), until
    /// aborted, like the real heartbeat. A robot whose `robot.updated` went out less than
    /// `interval` ago (it reported its state) is skipped.
    #[must_use]
    pub fn spawn_heartbeat(
        self: Arc<Self>,
        hub: Arc<realtime::Hub>,
        interval: std::time::Duration,
    ) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(interval);
            ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                ticker.tick().await;
                self.follow_tick();
                for robot in self.heartbeat_due(interval) {
                    hub.publish(AppEvent::RobotUpdated { robot });
                }
            }
        })
    }

    /// The data, also after a panic while it was held (it stays consistent: every change
    /// is a single assignment).
    fn data(&self) -> MutexGuard<'_, MockData> {
        self.data.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Every robot's view, `last_seen` now for the connected ones.
    fn robot_views(&self) -> Vec<RobotView> {
        let now = self.clock.now();
        self.data()
            .robots
            .iter()
            .map(|robot| robot_view(robot, self.hub.is_connected(&robot.view.id), now))
            .collect()
    }

    /// The connected robots whose last `robot.updated` is older than `interval`; each is
    /// marked as published now.
    fn heartbeat_due(&self, interval: std::time::Duration) -> Vec<RobotView> {
        let now = self.clock.now();
        let tick = tokio::time::Instant::now();
        let mut data = self.data();
        data.robots
            .iter_mut()
            .filter(|robot| self.hub.is_connected(&robot.view.id))
            .filter(|robot| {
                robot
                    .last_event
                    .is_none_or(|at| tick.saturating_duration_since(at) >= interval)
            })
            .map(|robot| {
                robot.last_event = Some(tick);
                robot_view(robot, true, now)
            })
            .collect()
    }

    /// The in-process simulated robots of `--mock`: one per demo robot (not the `fake_robot`
    /// slot), starting at its dock and looping along the places of its floor (docks left
    /// out, sorted west to east; every second robot of a floor goes the other way). Also
    /// returns the active plan they move on.
    #[must_use]
    pub fn simulated_fleet(&self) -> Option<(ClinicPlan, Vec<SimRobotConfig>)> {
        let data = self.data();
        let plan = data.active_plan()?.plan.clone();
        let mut floors_seen: Vec<i32> = Vec::new();
        let configs = data
            .robots
            .iter()
            .filter_map(|robot| {
                let home = robot.home.clone()?;
                let floor = robot.view.pos.floor;
                let mut stops: Vec<&locations::PlanPlace> = plan
                    .places
                    .iter()
                    .filter(|place| place.floor == floor)
                    .filter(|place| place.kind != locations::PlaceViewKind::Dock)
                    .collect();
                stops.sort_by(|a, b| a.x.total_cmp(&b.x));
                let before = floors_seen.iter().filter(|seen| **seen == floor).count();
                floors_seen.push(floor);
                if before % 2 == 1 {
                    stops.reverse();
                }
                let round: Vec<PlaceId> = std::iter::once(home.clone())
                    .chain(stops.into_iter().map(|place| place.id.clone()))
                    .collect();
                Some(
                    SimRobotConfig::new(robot.view.id.clone(), robot.view.pos, round)
                        .with_role_card(robot.view.role.to_lowercase())
                        .with_battery(robot.view.battery.unwrap_or(90.0))
                        .with_home(home)
                        .with_state_interval(MOCK_SIM_STATE_INTERVAL)
                        .with_unreachable(Unreachable::FailPathBlocked),
                )
            })
            .collect();
        Some((plan, configs))
    }

    /// Publishes an event to every console.
    fn publish(&self, event: AppEvent) {
        self.hub.publish(event);
    }

    /// Publishes `robot.updated` for one robot (and remembers when, for the heartbeat).
    fn publish_robot(&self, id: &RobotId) {
        let now = self.clock.now();
        let view = {
            let mut data = self.data();
            data.robots
                .iter_mut()
                .find(|robot| &robot.view.id == id)
                .map(|robot| {
                    robot.last_event = Some(tokio::time::Instant::now());
                    robot_view(robot, self.hub.is_connected(id), now)
                })
        };
        if let Some(robot) = view {
            self.publish(AppEvent::RobotUpdated { robot });
        }
    }

    /// Sends the new zone list to every connected robot.
    fn send_zones_to_robots(&self) {
        for robot in self.hub.broadcast_to_robots(self.zones_down()) {
            tracing::warn!(%robot, "mock: zones.update not delivered");
        }
    }

    /// The zone list as robots receive it (`zones.update`).
    fn zones_down(&self) -> RobotDown {
        let data = self.data();
        RobotDown::ZonesUpdate {
            zones: data
                .zones
                .iter()
                .map(|zone| WireZone {
                    id: zone.id.clone(),
                    kind: zone.kind,
                    floor: zone.floor,
                    polygon: zone.polygon.clone(),
                    version: zone.version,
                })
                .collect(),
            version: data.zone_set_version,
        }
    }

    /// Sends the waiting tasks (`requested`, oldest first) to free connected robots: a robot
    /// that is not one of the in-process demo robots (the `fake_robot`) first, then a robot on
    /// the destination's floor. Returns whether every waiting task found a robot.
    fn dispatch_waiting(&self) -> bool {
        let mut data = self.data();
        // Task A8: no task is handed out while emergency mode is on.
        if data.mode.is_emergency() {
            return false;
        }
        let reserved: Vec<TaskId> = data
            .robots
            .iter()
            .filter_map(|robot| robot.view.task_id.clone())
            .collect();
        let mut waiting: Vec<TaskView> = data
            .tasks
            .iter()
            .filter(|task| task.state == TaskState::Requested && task.robot_id.is_none())
            .filter(|task| task.kind != TaskKind::Follow)
            .filter(|task| !reserved.contains(&task.id) && !data.seed_tasks.contains(&task.id))
            .cloned()
            .collect();
        waiting.sort_by_key(|task| task.created_at);
        let mut all_placed = true;
        for task in waiting {
            let floor = data.place(&task.to_place).map(|(floor, _, _)| floor);
            let chosen = data
                .robots
                .iter()
                .filter(|robot| robot.view.task_id.is_none())
                .filter(|robot| self.hub.is_connected(&robot.view.id))
                .filter(|robot| {
                    !matches!(
                        robot.view.state,
                        RobotStatus::Paused | RobotStatus::Estop | RobotStatus::Fault
                    )
                })
                // Ruling R21: a demo robot only takes a task whose destination is on its floor.
                .filter(|robot| {
                    robot.home.is_none() || floor.is_some_and(|floor| robot.view.pos.floor == floor)
                })
                .min_by_key(|robot| {
                    (
                        robot.home.is_some(),
                        floor.is_none_or(|floor| robot.view.pos.floor != floor),
                    )
                })
                .map(|robot| robot.view.id.clone());
            let Some(robot) = chosen else {
                all_placed = false;
                continue;
            };
            let assign = RobotDown::TaskAssign {
                task_id: task.id.clone(),
                kind: task.kind,
                item: task.item.clone(),
                from_place: task.from_place.clone(),
                to_place: task.to_place.clone(),
                deadline: None,
            };
            match self.hub.send_to_robot(&robot, assign) {
                Ok(()) => {
                    if let Ok(entry) = data.robot_mut(&robot) {
                        entry.view.task_id = Some(task.id.clone());
                    }
                }
                Err(error) => {
                    tracing::warn!(%robot, task = %task.id, %error, "mock dispatch: task not sent");
                    all_placed = false;
                }
            }
        }
        all_placed
    }

    /// The open tasks a robot held when it went away (or said hello without them): a task it
    /// had started (`assigned`, `en_route`, `resumed`) becomes `failed` (`robot_lost`), a task
    /// only sent to it (`requested`) goes back to the queue. The seed's invented tasks are left
    /// alone. Publishes `task.updated` for each and dispatches the queue again. Returns the
    /// failed tasks. `session_gone`: the robot disconnected, so a `requested` task sent to it
    /// is released too; on a `hello` it is kept (the new session received it and answers).
    fn fail_open_tasks(&self, robot: &RobotId, session_gone: bool) -> Vec<TaskId> {
        let now = self.clock.now();
        let failed: Vec<TaskView> = {
            let mut data = self.data();
            let seed = data.seed_tasks.clone();
            let reserved = data
                .robot_mut(robot)
                .ok()
                .and_then(|entry| entry.view.task_id.clone());
            let started = reserved.as_ref().is_some_and(|id| {
                data.tasks
                    .iter()
                    .any(|task| &task.id == id && task.state != TaskState::Requested)
            });
            if (session_gone || started)
                && let Ok(entry) = data.robot_mut(robot)
            {
                entry.view.task_id = None;
            }
            data.tasks
                .iter_mut()
                .filter(|task| !seed.contains(&task.id))
                .filter(|task| {
                    task.robot_id.as_ref() == Some(robot) || reserved.as_ref() == Some(&task.id)
                })
                .filter(|task| {
                    task.state != TaskState::Requested && task.state.can_go_to(TaskState::Failed)
                })
                .map(|task| {
                    task.state = TaskState::Failed;
                    task.reason = Some(wire_name(&FailureReason::RobotLost));
                    task.updated_at = now;
                    task.history.push(history(now, "server", TaskState::Failed));
                    task.clone()
                })
                .collect()
        };
        let ids = failed.iter().map(|task| task.id.clone()).collect();
        for task in failed {
            self.publish(AppEvent::TaskUpdated { task });
        }
        self.dispatch_waiting();
        ids
    }

    /// A robot session opened: the robot is connected (added to the list if unknown).
    fn robot_connected(&self, id: &RobotId) {
        {
            let mut data = self.data();
            if data.robot_mut(id).is_err() {
                let pos = data.robots.first().map_or(
                    RobotPose {
                        x: 1.0,
                        y: 1.0,
                        heading: 0.0,
                        floor: 0,
                    },
                    |robot| robot.view.pos,
                );
                data.robots.push(MockRobot {
                    view: RobotView {
                        id: id.clone(),
                        name: format!("{id} · fake_robot{MOCK_SUFFIX}"),
                        role: "Test".to_owned(),
                        simulated: true,
                        pos,
                        battery: None,
                        state: RobotStatus::Idle,
                        holding: None,
                        mic_open: false,
                        task_id: None,
                        last_seen: None,
                        connected: true,
                        in_deaf_zone: false,
                        going_home: false,
                        mood: realtime::RobotMood::Happy,
                    },
                    home: None,
                    last_event: None,
                });
            }
        }
        self.publish_robot(id);
        self.dispatch_waiting();
    }

    /// A `robot.state` arrived: the view follows it.
    fn robot_state(&self, id: &RobotId, state: RobotUp) {
        let RobotUp::State {
            pos,
            battery_pct,
            status,
            holding,
            mic_open,
        } = state
        else {
            return;
        };
        let now = self.clock.now();
        {
            let mut data = self.data();
            let Ok(robot) = data.robot_mut(id) else {
                return;
            };
            robot.view.pos = pos;
            robot.view.battery = Some(battery_pct);
            robot.view.state = status;
            robot.view.holding = holding;
            robot.view.mic_open = mic_open;
            robot.view.last_seen = Some(now);
        }
        self.publish_robot(id);
    }

    /// Applies a robot's `task.event`: replays are duplicates, an illegal step is refused,
    /// a delivery takes one item out of the reserve; publishes `task.updated`,
    /// `robot.updated` (and `inventory.updated`).
    fn apply_event(
        &self,
        robot: &RobotId,
        event_id: Uuid,
        task: &TaskId,
        state: TaskState,
        reason: Option<FailureReason>,
    ) -> Result<ApplyOutcome, ApiError> {
        let now = self.clock.now();
        let mut data = self.data();
        if data.seen_events.contains(&event_id) {
            return Ok(ApplyOutcome::Duplicate);
        }
        data.seen_events.push_back(event_id);
        if data.seen_events.len() > SEEN_EVENTS {
            data.seen_events.pop_front();
        }
        let held = data
            .robots
            .iter()
            .any(|entry| &entry.view.id == robot && entry.view.task_id.as_ref() == Some(task));
        let view = data.task_mut(task)?;
        // Step C1: a follow task goes on after each arrival; only a failure ends it here.
        if view.kind == TaskKind::Follow && state != TaskState::Failed {
            return Ok(ApplyOutcome::Applied);
        }
        // Task A8: a task the server took back (emergency mode) is not taken again by an event
        // the robot sent before it got the `task.cancel`.
        if view.state == TaskState::Requested && view.robot_id.is_none() && !held {
            tracing::debug!(%robot, %task, "mock: event for a task back in the queue ignored");
            return Ok(ApplyOutcome::Duplicate);
        }
        if view.state == state {
            return Ok(ApplyOutcome::Applied);
        }
        if !view.state.can_go_to(state) {
            let from = view.state;
            if state.is_terminal()
                && let Ok(entry) = data.robot_mut(robot)
                && entry.view.task_id.as_ref() == Some(task)
            {
                entry.view.task_id = None;
            }
            return Err(DomainError::IllegalTransition {
                task: task.clone(),
                from,
                to: state,
            }
            .into());
        }
        view.state = state;
        view.robot_id = Some(robot.clone());
        view.updated_at = now;
        view.reason = reason.as_ref().map(wire_name);
        view.history
            .push(history(now, &format!("robot:{robot}"), state));
        let updated = view.clone();
        if let Ok(entry) = data.robot_mut(robot) {
            entry.view.task_id = (!state.is_terminal()).then(|| task.clone());
        }
        // A delivery takes one item out of the reserve, as the live server does.
        let stock = if state == TaskState::Delivered {
            updated.item.as_ref().and_then(|item| {
                data.items
                    .iter_mut()
                    .find(|level| &level.item == item && level.count > 0)
                    .map(|level| {
                        level.count -= 1;
                        level.updated_at = now;
                        level.clone()
                    })
            })
        } else {
            None
        };
        drop(data);
        self.publish(AppEvent::TaskUpdated { task: updated });
        self.publish_robot(robot);
        if let Some(item) = stock {
            self.publish(AppEvent::InventoryUpdated { item });
        }
        if state.is_terminal() {
            self.dispatch_waiting();
        }
        Ok(ApplyOutcome::Applied)
    }
}

/// A robot's view: `connected` and `last_seen` now while it has a hub session.
fn robot_view(robot: &MockRobot, connected: bool, now: DateTime<Utc>) -> RobotView {
    let mood = realtime::RobotMood::derive(
        robot.view.state,
        realtime::MoodInputs {
            connected,
            in_deaf_zone: robot.view.in_deaf_zone,
            has_task: robot.view.task_id.is_some(),
            ..realtime::MoodInputs::default()
        },
    );
    RobotView {
        connected,
        mood,
        last_seen: if connected {
            Some(now)
        } else {
            robot.view.last_seen
        },
        ..robot.view.clone()
    }
}

/// The wire name of a serde enum value (`en_route`, `robot_lost`, …).
fn wire_name<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_default()
}

impl MockData {
    /// Nothing at all (the fallback when the embedded seeds do not parse).
    fn empty() -> MockData {
        MockData {
            plans: Vec::new(),
            robots: Vec::new(),
            tasks: Vec::new(),
            next_task: 1,
            items: Vec::new(),
            zones: Vec::new(),
            schedules: Vec::new(),
            audit: Vec::new(),
            incidents: Vec::new(),
            seen_events: VecDeque::new(),
            zone_set_version: 1,
            seed_tasks: Vec::new(),
            accounts: Vec::new(),
            codes: Vec::new(),
            commands: VecDeque::new(),
            estop_latched: std::collections::HashSet::new(),
            mode: SystemModeState::initial(),
            paused_by_emergency: HashSet::new(),
            tablets: Vec::new(),
            follows: Vec::new(),
        }
    }

    /// The console's demo clinic and fleet, plus invented tasks, audit rows and an incident.
    fn from_seeds(now: DateTime<Utc>) -> Result<MockData, String> {
        let plan: ClinicPlan = serde_json::from_str(SEED_PLAN)
            .map_err(|error| format!("seed/clinic_map.json: {error}"))?;
        let fleet: DemoFleet = serde_json::from_str(SEED_FLEET)
            .map_err(|error| format!("seed/demo_fleet.json: {error}"))?;
        for (file, marque) in [
            ("seed/clinic_map.json", plan.marque.as_deref()),
            ("seed/demo_fleet.json", Some(fleet.marque.as_str())),
        ] {
            if marque != Some("inventé") {
                return Err(format!("{file} is not marked \"marque\": \"inventé\""));
            }
        }
        let robots = mock_robots(&plan, &fleet, now).map_err(|error| error.to_string())?;
        let tasks = mock_tasks(now).map_err(|error| error.to_string())?;
        let seed_tasks: Vec<TaskId> = tasks.iter().map(|task| task.id.clone()).collect();
        let robot_ids: Vec<(RobotId, bool)> = robots
            .iter()
            .map(|robot| (robot.view.id.clone(), robot.home.is_some()))
            .collect();
        let data = MockData {
            next_task: u32::try_from(tasks.len())
                .unwrap_or(u32::MAX)
                .saturating_add(1),
            tasks,
            items: fleet
                .items
                .iter()
                .map(|item| StockLevel {
                    item: item.id.clone(),
                    label: item.label.clone(),
                    place: item.place.clone(),
                    count: item.count,
                    low_threshold: item.low_at,
                    last_robot_count: None,
                    last_robot_count_at: None,
                    updated_at: now,
                })
                .collect(),
            zones: fleet
                .zones
                .iter()
                .map(|zone| ZoneView {
                    id: zone.id.clone(),
                    name: zone.name.clone(),
                    floor: zone.floor,
                    kind: zone.kind,
                    polygon: zone.polygon.clone(),
                    deliveries: deliveries(&robot_ids, 1),
                    enforced_by_gardien: zone.kind == ZoneKind::Deaf,
                    version: 1,
                })
                .collect(),
            schedules: mock_schedules(&fleet).map_err(|error| error.to_string())?,
            audit: mock_audit(now),
            incidents: mock_incidents(now).map_err(|error| error.to_string())?,
            seen_events: VecDeque::new(),
            zone_set_version: 1,
            seed_tasks,
            accounts: accounts::demo_accounts(MOCK_USERS, now)
                .map_err(|error| error.to_string())?,
            codes: Vec::new(),
            commands: VecDeque::new(),
            estop_latched: std::collections::HashSet::new(),
            mode: SystemModeState::initial(),
            paused_by_emergency: HashSet::new(),
            tablets: tablets::seed_tablets(now).map_err(|error| error.to_string())?,
            follows: Vec::new(),
            robots,
            plans: vec![
                MockPlan::new(
                    ClinicId::seed(),
                    1,
                    true,
                    plan,
                    locations::PlanOverlay::default(),
                    now,
                )
                .map_err(|error| error.message().to_owned())?,
            ],
        };
        Ok(data)
    }

    fn active_plan(&self) -> Option<&MockPlan> {
        self.plans.iter().find(|plan| plan.active)
    }

    /// Whether `place` is a room of the active plan (a bed's room for a bedside tablet).
    fn is_room(&self, place: &PlaceId) -> bool {
        self.active_plan().is_some_and(|plan| {
            plan.plan.places.iter().any(|candidate| {
                &candidate.id == place && candidate.kind == locations::PlaceViewKind::Room
            })
        })
    }

    /// A place of the active plan: `(floor, x, y)`.
    fn place(&self, place: &PlaceId) -> Option<(i32, f64, f64)> {
        self.active_plan()?
            .plan
            .places
            .iter()
            .find(|candidate| &candidate.id == place)
            .map(|found| (found.floor, found.x, found.y))
    }

    /// Every robot with whether it is in `connected`.
    fn robot_ids(&self, connected: &[RobotId]) -> Vec<(RobotId, bool)> {
        self.robots
            .iter()
            .map(|robot| (robot.view.id.clone(), connected.contains(&robot.view.id)))
            .collect()
    }

    fn task_mut(&mut self, id: &TaskId) -> Result<&mut TaskView, ApiError> {
        self.tasks
            .iter_mut()
            .find(|task| &task.id == id)
            .ok_or_else(|| ApiError::not_found("Task", id.as_str()))
    }

    fn robot_mut(&mut self, id: &RobotId) -> Result<&mut MockRobot, ApiError> {
        self.robots
            .iter_mut()
            .find(|robot| &robot.view.id == id)
            .ok_or_else(|| ApiError::not_found("Robot", id.as_str()))
    }
}

/// The four demo robots at their homes (connected), and the `fake_robot` slot (offline).
/// The offline slot's `last_seen` is the mock start time, so the console shows "last seen"
/// rather than nothing.
fn mock_robots(
    plan: &ClinicPlan,
    fleet: &DemoFleet,
    started: DateTime<Utc>,
) -> Result<Vec<MockRobot>, DomainError> {
    let at = |place: &PlaceId, heading: f64| -> RobotPose {
        plan.places
            .iter()
            .find(|candidate| &candidate.id == place)
            .map_or(
                RobotPose {
                    x: 1.0,
                    y: 1.0,
                    heading,
                    floor: 0,
                },
                |found| RobotPose {
                    x: found.x,
                    y: found.y,
                    heading,
                    floor: found.floor,
                },
            )
    };
    let mut robots: Vec<MockRobot> = fleet
        .robots
        .iter()
        .map(|robot| MockRobot {
            view: RobotView {
                id: robot.id.clone(),
                name: format!("{}{MOCK_SUFFIX}", robot.name),
                role: robot.role.clone(),
                simulated: true,
                pos: at(&robot.home, robot.heading),
                battery: Some(robot.battery),
                state: RobotStatus::Idle,
                holding: None,
                mic_open: false,
                task_id: None,
                last_seen: None,
                connected: true,
                in_deaf_zone: false,
                going_home: false,
                mood: realtime::RobotMood::Happy,
            },
            home: Some(robot.home.clone()),
            last_event: None,
        })
        .collect();
    let dock: PlaceId = "dock-a".parse()?;
    robots.push(MockRobot {
        view: RobotView {
            id: MOCK_ROBOT_ID.parse()?,
            name: format!("{MOCK_ROBOT_ID} · fake_robot slot{MOCK_SUFFIX}"),
            role: "Test".to_owned(),
            simulated: true,
            pos: at(&dock, 0.0),
            battery: None,
            state: RobotStatus::Idle,
            holding: None,
            mic_open: false,
            task_id: None,
            last_seen: Some(started),
            connected: false,
            in_deaf_zone: false,
            going_home: false,
            mood: realtime::RobotMood::Offline,
        },
        home: None,
        last_event: None,
    });
    Ok(robots)
}

/// Delivery of a zone list to each robot: received by the connected ones, pending for the
/// offline ones.
fn deliveries(robots: &[(RobotId, bool)], version: u32) -> Vec<ZoneDeliveryEntry> {
    robots
        .iter()
        .map(|(id, online)| ZoneDeliveryEntry {
            robot_id: id.clone(),
            status: if *online {
                DeliveryState::Received
            } else {
                DeliveryState::Pending
            },
            acked_version: online.then_some(version),
            robot_online: *online,
        })
        .collect()
}

/// One history line.
fn history(at: DateTime<Utc>, actor: &str, state: TaskState) -> TaskHistoryEntry {
    TaskHistoryEntry {
        at,
        actor: actor.to_owned(),
        label: state_label(state),
    }
}

/// One history line with a free label (Task A8: `held: emergency mode`).
fn history_label(at: DateTime<Utc>, actor: &str, label: &str) -> TaskHistoryEntry {
    TaskHistoryEntry {
        at,
        actor: actor.to_owned(),
        label: label.to_owned(),
    }
}

/// The wire name of a state (`en_route`, …).
fn state_label(state: TaskState) -> String {
    wire_name(&state)
}

/// Four invented tasks, one per interesting state.
fn mock_tasks(now: DateTime<Utc>) -> Result<Vec<TaskView>, DomainError> {
    let minutes = |m: i64| now - ChronoDuration::minutes(m);
    let nurse = "Ward 2 nurse (mock)";
    let fetch = |id: &str,
                 item: &str,
                 from: &str,
                 to: &str,
                 robot: Option<&str>,
                 states: &[(i64, &str, TaskState)]|
     -> Result<TaskView, DomainError> {
        let history: Vec<TaskHistoryEntry> = states
            .iter()
            .map(|(m, actor, state)| history(minutes(*m), actor, *state))
            .collect();
        let created_at = history.first().map_or(now, |entry| entry.at);
        let updated_at = history.last().map_or(now, |entry| entry.at);
        let state = states.last().map_or(TaskState::Requested, |entry| entry.2);
        Ok(TaskView {
            id: id.parse()?,
            kind: TaskKind::Fetch,
            item: Some(item.parse()?),
            from_place: Some(from.parse()?),
            to_place: to.parse()?,
            state,
            robot_id: robot.map(str::parse).transpose()?,
            requested_by: nurse.to_owned(),
            created_at,
            updated_at,
            reason: None,
            history,
            target_device: None,
            target_label: None,
            until: None,
        })
    };
    Ok(vec![
        fetch(
            "t-1",
            "blanket",
            "supply-a",
            "room-12",
            None,
            &[(2, nurse, TaskState::Requested)],
        )?,
        fetch(
            "t-2",
            "water-bottle",
            "supply-b",
            "room-14",
            Some("r2"),
            &[
                (6, nurse, TaskState::Requested),
                (5, "server", TaskState::Assigned),
            ],
        )?,
        fetch(
            "t-3",
            "towel",
            "linen-shelf",
            "therapy-1",
            Some("r3"),
            &[
                (12, "Therapy desk (mock)", TaskState::Requested),
                (11, "server", TaskState::Assigned),
                (9, "robot:r3", TaskState::EnRoute),
            ],
        )?,
        fetch(
            "t-4",
            "welcome-folder",
            "reception",
            "hall",
            Some("r1"),
            &[
                (40, "Reception desk (mock)", TaskState::Requested),
                (39, "server", TaskState::Assigned),
                (37, "robot:r1", TaskState::EnRoute),
                (33, "robot:r1", TaskState::Delivered),
            ],
        )?,
    ])
}

/// The fleet's schedule, with an invented last round.
fn mock_schedules(fleet: &DemoFleet) -> Result<Vec<ScheduleView>, DomainError> {
    let last_run = Utc.with_ymd_and_hms(2026, 11, 14, 1, 30, 0).single();
    let counts = vec![
        ShelfCount {
            place: "supply-a".parse()?,
            item: "blanket".parse()?,
            expected: 9,
            counted: 9,
        },
        ShelfCount {
            place: "supply-a".parse()?,
            item: "large-pillow".parse()?,
            expected: 3,
            counted: 2,
        },
    ];
    Ok(fleet
        .schedules
        .iter()
        .map(|schedule| ScheduleView {
            id: schedule.id.clone(),
            label: schedule.label.clone(),
            enabled: schedule.enabled,
            time: schedule.time.clone(),
            robot_id: schedule.robot_id.clone(),
            last_run,
            last_result: RoundResult::Partial,
            last_counts: counts.clone(),
            timezone: "Europe/Zurich".to_owned(),
            next_run: None,
        })
        .collect())
}

/// One invented audit row: `at` is a time on 2026-11-14 (the fixtures' demo day), or `None`
/// for "when the mock started"; an empty `detail` is `null`.
struct AuditSeed {
    at: Option<(u32, u32)>,
    actor: &'static str,
    action: &'static str,
    target: &'static str,
    result: AuditResult,
    detail: &'static str,
    category: &'static str,
}

/// A day of history on 2026-11-14, then the rows of this mock session.
const AUDIT_SEEDS: &[AuditSeed] = &[
    AuditSeed {
        at: Some((8, 2)),
        actor: "Admin (mock)",
        action: "login_succeeded",
        target: "",
        result: AuditResult::Ok,
        detail: "",
        category: "security",
    },
    AuditSeed {
        at: Some((8, 15)),
        actor: "Ward 2 nurse (mock)",
        action: "task_created",
        target: "t-1",
        result: AuditResult::Ok,
        detail: "blanket to room-12",
        category: "audit",
    },
    AuditSeed {
        at: Some((8, 16)),
        actor: "robot:r2",
        action: "task_state",
        target: "t-1",
        result: AuditResult::Ok,
        detail: "assigned",
        category: "robot",
    },
    AuditSeed {
        at: Some((9, 40)),
        actor: "Ward 2 nurse (mock)",
        action: "permission_denied",
        target: "r1",
        result: AuditResult::Refused,
        detail: "estop needs the admin role",
        category: "security",
    },
    AuditSeed {
        at: Some((11, 5)),
        actor: "Admin (mock)",
        action: "zone_saved",
        target: "zone-room-12",
        result: AuditResult::Ok,
        detail: "version 1",
        category: "audit",
    },
    AuditSeed {
        at: Some((14, 30)),
        actor: "Admin (mock)",
        action: "estop_sent",
        target: MOCK_ROBOT_ID,
        result: AuditResult::Failed,
        detail: "robot offline",
        category: "robot",
    },
    AuditSeed {
        at: None,
        actor: "system:server",
        action: "system_event",
        target: "startup",
        result: AuditResult::Ok,
        detail: "mock server started; nothing is journaled",
        category: "system",
    },
    AuditSeed {
        at: None,
        actor: "Admin (mock)",
        action: "stock_adjusted",
        target: "masks",
        result: AuditResult::Ok,
        detail: "+2 (restock)",
        category: "audit",
    },
];

/// The invented audit rows, numbered from 1.
fn mock_audit(now: DateTime<Utc>) -> Vec<AuditEntry> {
    (1_u64..)
        .zip(AUDIT_SEEDS)
        .map(|(id, seed)| AuditEntry {
            id,
            at: seed
                .at
                .and_then(|(hour, minute)| {
                    Utc.with_ymd_and_hms(2026, 11, 14, hour, minute, 0).single()
                })
                .unwrap_or(now),
            actor: seed.actor.to_owned(),
            action: seed.action.to_owned(),
            target: seed.target.to_owned(),
            result: seed.result,
            detail: (!seed.detail.is_empty()).then(|| seed.detail.to_owned()),
            category: seed.category.to_owned(),
        })
        .collect()
}

/// One open, orange (warning) incident: the bedside tablet of bed 13 has a low battery.
fn mock_incidents(now: DateTime<Utc>) -> Result<Vec<Incident>, DomainError> {
    Ok(vec![Incident {
        id: IncidentId(1),
        code: IncidentCode::TabletBatteryLow,
        severity: IncidentSeverity::Warning,
        subject: Some(domain::SubjectRef::Tablet("tab-bed-13".parse()?)),
        place: Some("room-13".parse()?),
        floor: Some(2),
        opened_at: now - ChronoDuration::minutes(20),
        last_seen_at: now - ChronoDuration::minutes(3),
        repeats: 2,
        acknowledged_by: None,
        closed_at: None,
    }])
}

/// The id `POST /clinics` derives from a plan name: lowercased, every run of other
/// characters turned into `-`, trimmed of `-`, cut to 48 characters.
fn clinic_id_from_name(name: &str) -> Result<ClinicId, ApiError> {
    let mut id = String::new();
    for c in name.to_lowercase().chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            id.push(c);
        } else if !id.ends_with('-') {
            id.push('-');
        }
    }
    let id: String = id.trim_matches('-').chars().take(48).collect();
    id.trim_end_matches('-')
        .parse()
        .map_err(|_| ApiError::invalid_input("name", "must contain at least one letter or digit"))
}

/// Checks a `HH:MM` time.
fn valid_time(time: &str) -> bool {
    let Some((hours, minutes)) = time.split_once(':') else {
        return false;
    };
    hours.len() == 2
        && minutes.len() == 2
        && hours.parse::<u8>().is_ok_and(|h| h < 24)
        && minutes.parse::<u8>().is_ok_and(|m| m < 60)
}

/// The mock identity of a robot token (`mock-robot`, `mock-robot-<id>`), if it is one. User
/// tokens are looked up among the mock accounts (`MockServices::account_identity`).
fn mock_identity(raw: &str) -> Option<VerifiedIdentity> {
    let robot = if raw == "mock-robot" {
        Some(MOCK_ROBOT_ID)
    } else {
        raw.strip_prefix(MOCK_ROBOT_TOKEN_PREFIX)
    };
    let robot = robot?.parse::<RobotId>().ok()?;
    Some(VerifiedIdentity {
        subject_id: Actor::Robot(robot),
        role: Role::Robot,
        device_id: None,
        owner: None,
    })
}

#[async_trait]
impl AuthService for MockServices {
    async fn login(
        &self,
        key: &AccountKey,
        _device: Option<DeviceId>,
        _network: &ClientNetwork,
    ) -> Result<LoginResponse, ApiError> {
        self.mock_login(key)
    }
    async fn login_with_password(
        &self,
        username: &str,
        password: &str,
        _device: Option<DeviceId>,
        _network: &ClientNetwork,
    ) -> Result<LoginResponse, ApiError> {
        // Mock compatibility until frontend task F9 (the live server refuses this body).
        self.mock_login_with_password(username, password).await
    }
    fn derivation(&self) -> KeyDerivationParams {
        derivation_params(&Self::account_clinic())
    }
    async fn enrol(
        &self,
        request: EnrolRequest,
        _network: &ClientNetwork,
    ) -> Result<EnrolledView, ApiError> {
        self.mock_enrol(request)
    }
    async fn issue_enrolment_code(
        &self,
        _actor: &ClientIdentity,
        request: EnrolmentCodeRequest,
    ) -> Result<EnrolmentCodeView, ApiError> {
        self.mock_issue_code(request)
    }
    async fn list_accounts(&self) -> Result<Vec<AccountView>, ApiError> {
        Ok(self.mock_accounts())
    }
    async fn disable_account(
        &self,
        actor: &ClientIdentity,
        tag: &AccountTag,
    ) -> Result<(), ApiError> {
        self.mock_disable(actor, tag)
    }
    async fn me(&self, identity: &ClientIdentity) -> Result<MeView, ApiError> {
        Ok(MeView {
            subject: identity.verified.subject_id.to_string(),
            role: identity.verified.role,
            device_id: identity.verified.device_id.clone(),
            owner_label: identity.verified.owner.clone(),
            network: identity.network.label.clone(),
            area: identity.network.area.clone(),
        })
    }
}

impl MockServices {
    /// Adds one audit row by the caller (its owner label).
    fn push_audit(
        &self,
        actor: &ClientIdentity,
        action: &str,
        target: &str,
        detail: Option<String>,
        category: &str,
    ) {
        let label = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        self.push_row(&label, action, target, AuditResult::Ok, detail, category);
    }

    /// Adds one audit row by `actor` (a label: an owner label or `system:server`).
    fn push_labelled_audit(
        &self,
        actor: &str,
        action: &str,
        target: &str,
        detail: String,
        category: &str,
    ) {
        self.push_row(
            actor,
            action,
            target,
            AuditResult::Ok,
            Some(detail),
            category,
        );
    }

    /// Adds one failed audit row by the server.
    fn push_system_audit(&self, action: &str, target: &str, detail: String) {
        self.push_row(
            "system:server",
            action,
            target,
            AuditResult::Failed,
            Some(detail),
            "robot",
        );
    }

    fn push_row(
        &self,
        actor: &str,
        action: &str,
        target: &str,
        result: AuditResult,
        detail: Option<String>,
        category: &str,
    ) {
        let at = self.clock.now();
        let mut data = self.data();
        let id = data.audit.iter().map(|row| row.id).max().unwrap_or(0) + 1;
        data.audit.push(AuditEntry {
            id,
            at,
            actor: actor.to_owned(),
            action: action.to_owned(),
            target: target.to_owned(),
            result,
            detail,
            category: category.to_owned(),
        });
    }
}

impl MockServices {
    /// Creates a task in state `requested` (shared by both create paths).
    fn create_task(
        &self,
        requested_by: String,
        new: NewTask,
        by_admin: bool,
    ) -> Result<TaskView, ApiError> {
        // Step C1: giving a task to one robot is the admin's.
        if (new.robot_id.is_some() || new.target_device.is_some()) && !by_admin {
            return Err(ApiError::forbidden(domain::Permission::RobotShutdown));
        }
        let follow = new.kind == TaskKind::Follow;
        if follow && (new.robot_id.is_none() || new.target_device.is_none()) {
            return Err(ApiError::invalid_input(
                "target_device",
                "and `robot_id` are required for a follow task",
            ));
        }
        if new.kind == TaskKind::Fetch && new.item.is_none() {
            return Err(DomainError::MissingTaskField {
                kind: "fetch",
                field: "item",
            }
            .into());
        }
        let now = self.clock.now();
        let mut data = self.data();
        if let Some(item) = &new.item
            && !data.items.iter().any(|level| &level.item == item)
        {
            return Err(ApiError::invalid_input(
                "item",
                "is not in the reserve (see GET /inventory)",
            ));
        }
        let target = match &new.target_device {
            Some(device) if follow => Some(data.follow_target(device)?),
            _ => None,
        };
        let to_place = match (&target, new.to_place) {
            (Some((_, room)), _) => room.clone(),
            (None, Some(place)) => place,
            (None, None) => return Err(ApiError::invalid_input("to_place", "is required")),
        };
        if let Some(robot) = &new.robot_id {
            data.check_assignable(&self.hub, robot)?;
        }
        let id: TaskId = format!("t-{}", data.next_task).parse()?;
        data.next_task = data.next_task.saturating_add(1);
        let until = follow.then(|| now + follow::follow_duration());
        let mut task = TaskView {
            id,
            kind: new.kind,
            item: new.item,
            from_place: new.from_place,
            to_place,
            state: TaskState::Requested,
            robot_id: None,
            history: vec![history(now, &requested_by, TaskState::Requested)],
            requested_by,
            created_at: now,
            updated_at: now,
            reason: None,
            target_device: new.target_device.clone().filter(|_| follow),
            target_label: target.map(|(label, _)| label),
            until,
        };
        if let Some(robot) = &new.robot_id {
            self.hand_to_robot(&mut data, &mut task, robot, now)?;
        }
        data.tasks.push(task.clone());
        drop(data);
        self.publish(AppEvent::TaskUpdated { task: task.clone() });
        if let Some(robot) = &task.robot_id.clone().or(new.robot_id) {
            self.publish_robot(robot);
            return Ok(task);
        }
        if !self.dispatch_waiting() {
            self.publish(AppEvent::Alert {
                level: AlertKind::TaskNeedsHuman.level(),
                kind: AlertKind::TaskNeedsHuman,
                message: format!(
                    "No robot is free for task {} right now; it waits in the queue (mock server).",
                    task.id
                ),
                command: None,
            });
        }
        Ok(task)
    }
}

#[async_trait]
impl TaskService for MockServices {
    async fn create(&self, actor: &ClientIdentity, new: NewTask) -> Result<TaskView, ApiError> {
        let requested_by = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        self.create_task(requested_by, new, actor.verified.role == Role::Admin)
    }
    async fn create_as_system(&self, actor: Actor, new: NewTask) -> Result<TaskView, ApiError> {
        let requested_by = match actor {
            Actor::System("demo") => SIMULATED_REQUEST_LABEL.to_owned(),
            Actor::System(_) => "server".to_owned(),
            _ => {
                return Err(ApiError::internal(
                    "task created as system by a non-system actor",
                ));
            }
        };
        self.create_task(requested_by, new, false)
    }
    async fn get(&self, id: &TaskId) -> Result<TaskView, ApiError> {
        self.data()
            .tasks
            .iter()
            .find(|task| &task.id == id)
            .cloned()
            .ok_or_else(|| ApiError::not_found("Task", id.as_str()))
    }
    async fn list(&self, filter: TaskFilter, page: Page) -> Result<TaskPage, ApiError> {
        let mut matching: Vec<TaskView> = self
            .data()
            .tasks
            .iter()
            .filter(|task| filter.state.is_none_or(|state| task.state == state))
            .filter(|task| {
                filter
                    .robot
                    .as_ref()
                    .is_none_or(|robot| task.robot_id.as_ref() == Some(robot))
            })
            .filter(|task| !filter.active_only || !task.state.is_terminal())
            .filter(|task| filter.since.is_none_or(|since| task.created_at >= since))
            .cloned()
            .collect();
        matching.sort_by_key(|task| std::cmp::Reverse(task.created_at));
        let offset = usize::try_from(page.offset()).unwrap_or(usize::MAX);
        let limit = usize::try_from(page.limit()).unwrap_or(usize::MAX);
        let more = matching.len() > offset.saturating_add(limit);
        let items = matching.into_iter().skip(offset).take(limit).collect();
        Ok(TaskPage {
            items,
            next: more.then(|| page.offset().saturating_add(page.limit())),
        })
    }
    async fn active(&self) -> Result<Vec<TaskView>, ApiError> {
        Ok(self
            .data()
            .tasks
            .iter()
            .filter(|task| !task.state.is_terminal())
            .cloned()
            .collect())
    }
    async fn cancel(&self, actor: &ClientIdentity, id: &TaskId) -> Result<TaskView, ApiError> {
        let now = self.clock.now();
        let label = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        let mut data = self.data();
        let task = data.task_mut(id)?;
        if actor.verified.role != Role::Admin && task.requested_by != label {
            return Err(ApiError::forbidden(domain::Permission::CancelTask));
        }
        let open_follow = task.kind == TaskKind::Follow && !task.state.is_terminal();
        if !open_follow && !task.state.can_go_to(TaskState::Cancelled) {
            return Err(ApiError::conflict(
                "task_not_cancellable",
                format!(
                    "Task '{id}' is {} and can no longer be cancelled.",
                    state_label(task.state)
                ),
            ));
        }
        task.state = TaskState::Cancelled;
        task.updated_at = now;
        task.history
            .push(history(now, &label, TaskState::Cancelled));
        let cancelled = task.clone();
        let robot = data
            .robots
            .iter_mut()
            .find(|robot| robot.view.task_id.as_ref() == Some(id))
            .map(|robot| {
                robot.view.task_id = None;
                robot.view.id.clone()
            });
        drop(data);
        if let Some(robot) = &robot {
            let cancel = RobotDown::TaskCancel {
                task_id: id.clone(),
            };
            if let Err(error) = self.hub.send_to_robot(robot, cancel) {
                tracing::warn!(%robot, task = %id, %error, "mock: task.cancel not delivered");
            }
            self.publish_robot(robot);
        }
        self.publish(AppEvent::TaskUpdated {
            task: cancelled.clone(),
        });
        self.dispatch_waiting();
        Ok(cancelled)
    }
    async fn apply_robot_event(
        &self,
        robot: &RobotId,
        event_id: Uuid,
        task: &TaskId,
        state: TaskState,
        reason: Option<FailureReason>,
    ) -> Result<ApplyOutcome, ApiError> {
        self.apply_event(robot, event_id, task, state, reason)
    }
    async fn on_robot_lost(&self, robot: &RobotId) -> Result<Vec<TaskId>, ApiError> {
        Ok(self.fail_open_tasks(robot, true))
    }
}

#[async_trait]
impl InventoryService for MockServices {
    async fn list(&self) -> Result<Vec<StockLevel>, ApiError> {
        Ok(self.data().items.clone())
    }
    async fn adjust(
        &self,
        _actor: &ClientIdentity,
        item: &ItemId,
        delta: i32,
        _reason: StockAdjustReason,
    ) -> Result<StockLevel, ApiError> {
        let now = self.clock.now();
        let mut data = self.data();
        let level = data
            .items
            .iter_mut()
            .find(|level| &level.item == item)
            .ok_or_else(|| ApiError::not_found("Item", item.as_str()))?;
        let count = i64::from(level.count) + i64::from(delta);
        let Ok(count) = u32::try_from(count) else {
            return Err(DomainError::InsufficientStock {
                item: item.clone(),
                requested: delta.unsigned_abs(),
                available: level.count,
            }
            .into());
        };
        level.count = count;
        level.updated_at = now;
        let level = level.clone();
        drop(data);
        self.publish(AppEvent::InventoryUpdated {
            item: level.clone(),
        });
        Ok(level)
    }
    async fn on_delivered(&self, _task: &Task) -> Result<(), ApiError> {
        Ok(())
    }
    async fn on_seen(
        &self,
        _robot: &RobotId,
        _place: &PlaceId,
        items: &[SeenItem],
    ) -> Result<Vec<ReconcileOutcome>, ApiError> {
        Ok(items
            .iter()
            .map(|seen| ReconcileOutcome::Matched {
                item: seen.item.clone(),
            })
            .collect())
    }
}

#[async_trait]
impl MapService for MockServices {
    async fn map(&self) -> Result<Arc<ClinicMap>, ApiError> {
        // The model is always derived from a plan by `ClinicPlan::validate` (ruling R14,
        // Task 10b); the mock serves the plan view only, and no route reads the model.
        Err(ApiError::unavailable("map model (mock server)"))
    }
    async fn view(&self) -> Result<(MapView, String), ApiError> {
        let data = self.data();
        let active = data
            .active_plan()
            .ok_or_else(|| ApiError::unavailable("clinic plan (mock server)"))?;
        let plan = active.plan.clone();
        let tag = format!("{}-v{}", active.id, active.version);
        Ok((
            MapView {
                clinic_id: active.id.clone(),
                version: active.version,
                name: plan.name,
                floors: plan.floors,
                rooms: plan.rooms,
                walls: plan.walls,
                places: plan.places,
                props: plan.props,
            },
            tag,
        ))
    }
}

#[async_trait]
impl ClinicService for MockServices {
    async fn list(&self) -> Result<Vec<ClinicSummary>, ApiError> {
        Ok(self.data().plans.iter().map(MockPlan::summary).collect())
    }
    async fn get(&self, id: &ClinicId) -> Result<VersionedPlan, ApiError> {
        self.data()
            .plans
            .iter()
            .find(|plan| &plan.id == id)
            .map(MockPlan::versioned)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))
    }
    async fn create(
        &self,
        _actor: &ClientIdentity,
        plan: ClinicPlan,
    ) -> Result<ClinicSummary, ApiError> {
        plan.validate()?;
        let id = clinic_id_from_name(&plan.name)?;
        let now = self.clock.now();
        let mut data = self.data();
        if data.plans.iter().any(|stored| stored.id == id) {
            return Err(ApiError::conflict(
                "clinic_exists",
                format!("A clinic plan with the id '{id}' already exists. Rename the plan."),
            ));
        }
        let stored = MockPlan::new(id, 1, false, plan, locations::PlanOverlay::default(), now)?;
        let summary = stored.summary();
        data.plans.push(stored);
        drop(data);
        self.publish_map_updated(&summary.id, summary.version, summary.active);
        Ok(summary)
    }
    async fn update(
        &self,
        _actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        plan: ClinicPlan,
    ) -> Result<VersionedPlan, ApiError> {
        plan.validate()?;
        let now = self.clock.now();
        let mut data = self.data();
        let stored = data
            .plans
            .iter_mut()
            .find(|stored| &stored.id == id)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))?;
        if stored.version != expected_version {
            return Err(ApiError::version_conflict(id.as_str(), stored.version));
        }
        stored.set(plan, locations::PlanOverlay::default())?;
        stored.version = stored.version.saturating_add(1);
        stored.updated_at = now;
        let versioned = stored.versioned();
        drop(data);
        self.publish_map_updated(&versioned.id, versioned.version, versioned.active);
        Ok(versioned)
    }
    async fn base(&self, id: &ClinicId) -> Result<VersionedPlan, ApiError> {
        let data = self.data();
        let stored = data
            .plans
            .iter()
            .find(|plan| &plan.id == id)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))?;
        Ok(stored.versioned_of(&stored.base))
    }
    async fn overlay(&self, id: &ClinicId) -> Result<VersionedOverlay, ApiError> {
        let data = self.data();
        let stored = data
            .plans
            .iter()
            .find(|plan| &plan.id == id)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))?;
        Ok(VersionedOverlay {
            version: stored.version,
            overlay: stored.overlay.clone(),
        })
    }
    async fn put_overlay(
        &self,
        _actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        overlay: locations::PlanOverlay,
    ) -> Result<VersionedPlan, ApiError> {
        self.save_parts(id, expected_version, |stored| {
            let base = stored.base.clone();
            stored.set(base, overlay)
        })
    }
    async fn put_base(
        &self,
        _actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        plan: ClinicPlan,
    ) -> Result<VersionedPlan, ApiError> {
        self.save_parts(id, expected_version, |stored| {
            let overlay = stored.overlay.clone();
            stored.set(plan, overlay)
        })
    }
    async fn activate(
        &self,
        _actor: &ClientIdentity,
        id: &ClinicId,
    ) -> Result<ClinicSummary, ApiError> {
        let mut data = self.data();
        if !data.plans.iter().any(|stored| &stored.id == id) {
            return Err(ApiError::not_found("Clinic plan", id.as_str()));
        }
        let changed = data.active_plan().is_none_or(|active| &active.id != id);
        for stored in &mut data.plans {
            stored.active = &stored.id == id;
        }
        let summary = data
            .plans
            .iter()
            .find(|stored| &stored.id == id)
            .map(MockPlan::summary)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))?;
        drop(data);
        // Activating the active plan is a no-op: nothing to announce.
        if changed {
            self.publish_map_updated(&summary.id, summary.version, summary.active);
        }
        Ok(summary)
    }
    async fn delete(&self, _actor: &ClientIdentity, id: &ClinicId) -> Result<(), ApiError> {
        let mut data = self.data();
        let stored = data
            .plans
            .iter()
            .find(|stored| &stored.id == id)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))?;
        if stored.active {
            return Err(ApiError::conflict(
                "clinic_active",
                format!("Clinic plan '{id}' is the active plan. Activate another plan first."),
            ));
        }
        let version = stored.version;
        data.plans.retain(|stored| &stored.id != id);
        drop(data);
        self.publish_map_updated(id, version, false);
        Ok(())
    }
}

impl MockServices {
    /// `map.updated` (Task A4 event, published by the mock since Task A8): when `active`, the
    /// console reloads `GET /map` once.
    /// Applies `change` to a stored plan if `expected_version` is current, bumps the version
    /// and announces it; returns the effective plan.
    fn save_parts(
        &self,
        id: &ClinicId,
        expected_version: u64,
        change: impl FnOnce(&mut MockPlan) -> Result<(), ApiError>,
    ) -> Result<VersionedPlan, ApiError> {
        let now = self.clock.now();
        let mut data = self.data();
        let stored = data
            .plans
            .iter_mut()
            .find(|stored| &stored.id == id)
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))?;
        if stored.version != expected_version {
            return Err(ApiError::version_conflict(id.as_str(), stored.version));
        }
        change(stored)?;
        stored.version = stored.version.saturating_add(1);
        stored.updated_at = now;
        let versioned = stored.versioned();
        drop(data);
        self.publish_map_updated(&versioned.id, versioned.version, versioned.active);
        Ok(versioned)
    }

    fn publish_map_updated(&self, clinic_id: &ClinicId, version: u64, active: bool) {
        self.publish(AppEvent::MapUpdated {
            clinic_id: clinic_id.clone(),
            version,
            active,
        });
    }
}

#[async_trait]
impl RouteService for MockServices {
    async fn task_route(&self, id: &TaskId) -> Result<RouteView, ApiError> {
        let data = self.data();
        let task = data
            .tasks
            .iter()
            .find(|task| &task.id == id)
            .ok_or_else(|| ApiError::not_found("Task", id.as_str()))?;
        if task.state.is_terminal() {
            return Err(ApiError::no_route(format!(
                "Task {id} is finished: no route is drawn."
            )));
        }
        // Task A8: from the robot's position when a robot has the task (through the pick-up
        // place while it does not hold the item yet), else from the start place; never a
        // route on an invented floor. Straight segments; the real planner is Task 13b.
        let robot = data.robots.iter().find(|robot| {
            task.robot_id.as_ref() == Some(&robot.view.id)
                || robot.view.task_id.as_ref() == Some(id)
        });
        let pickup = task.from_place.as_ref().and_then(|place| data.place(place));
        let goal = data.place(&task.to_place).ok_or_else(|| {
            ApiError::no_route(format!(
                "The destination of task {id} is not on the active plan: no route is drawn."
            ))
        })?;
        let mut stops: Vec<(i32, f64, f64)> = Vec::new();
        match robot {
            Some(robot) => {
                stops.push((robot.view.pos.floor, robot.view.pos.x, robot.view.pos.y));
                if robot.view.holding.is_none()
                    && let Some(pickup) = pickup
                {
                    stops.push(pickup);
                }
            }
            None => stops.extend(pickup),
        }
        if stops.is_empty() {
            return Err(ApiError::no_route(format!(
                "Task {id} has no start place and no robot yet: no route is drawn."
            )));
        }
        stops.push(goal);
        let floor = goal.0;
        if let Some((other, _, _)) = stops.iter().find(|stop| stop.0 != floor) {
            return Err(ApiError::no_route(format!(
                "The route goes from floor {other} to floor {floor}; robots do not take the lift, so no route is drawn."
            )));
        }
        let mut points: Vec<[f64; 2]> = Vec::new();
        for (_, x, y) in &stops {
            if let Some(last) = points.last().copied()
                && (last[0] - x).abs() > f64::EPSILON
                && (last[1] - y).abs() > f64::EPSILON
            {
                points.push([*x, last[1]]);
            }
            points.push([*x, *y]);
        }
        let length_m = points
            .windows(2)
            .filter_map(|pair| match pair {
                [a, b] => Some((b[0] - a[0]).hypot(b[1] - a[1])),
                _ => None,
            })
            .sum();
        Ok(RouteView {
            floor,
            points,
            length_m,
            estimate: true,
        })
    }
}

#[async_trait]
impl StatsService for MockServices {
    async fn heat(&self, floor: i32) -> Result<HeatView, ApiError> {
        let data = self.data();
        let outline = data
            .active_plan()
            .and_then(|plan| plan.plan.floors.iter().find(|f| f.id == floor))
            .map(|found| found.outline.clone())
            .ok_or_else(|| ApiError::invalid_input("floor", "is not a floor of the active plan"))?;
        let min_x = outline.iter().map(|p| p[0]).fold(f64::INFINITY, f64::min);
        let min_y = outline.iter().map(|p| p[1]).fold(f64::INFINITY, f64::min);
        let max_x = outline
            .iter()
            .map(|p| p[0])
            .fold(f64::NEG_INFINITY, f64::max);
        let max_y = outline
            .iter()
            .map(|p| p[1])
            .fold(f64::NEG_INFINITY, f64::max);
        let cells = |extent: f64| {
            (0..1_000_u32)
                .find(|n| f64::from(*n) >= extent)
                .unwrap_or(0)
        };
        let columns = cells(max_x - min_x);
        let rows = cells(max_y - min_y);
        // A warm corridor along the middle row, warmer toward the west (invented).
        let corridor = rows / 2;
        let counts = (0..rows)
            .flat_map(|row| {
                (0..columns).map(move |column| {
                    if row == corridor {
                        columns.saturating_sub(column).saturating_mul(3)
                    } else if row.abs_diff(corridor) == 1 {
                        columns.saturating_sub(column)
                    } else {
                        0
                    }
                })
            })
            .collect();
        Ok(HeatView {
            floor,
            cell_m: 1.0,
            origin: [min_x, min_y],
            columns,
            rows,
            counts,
        })
    }
}

#[async_trait]
impl LocationService for MockServices {
    async fn live(&self) -> Result<LiveSnapshot, ApiError> {
        let now = self.clock.now();
        let views = self.robot_views();
        let data = self.data();
        let point = |x: f64, y: f64| {
            Point2::new(x, y).map_err(|_| ApiError::internal("mock live position"))
        };
        let robots = views
            .iter()
            .filter(|view| view.connected)
            .map(|view| -> Result<RobotLive, ApiError> {
                Ok(RobotLive {
                    id: view.id.clone(),
                    name: view.name.clone(),
                    status: view.state,
                    task: None,
                    battery_pct: view.battery.unwrap_or(0.0),
                    mic_open: view.mic_open,
                    floor: view.pos.floor,
                    point: point(view.pos.x, view.pos.y)?,
                    heading_rad: Some(view.pos.heading),
                    stale: false,
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let tag = data.active_plan().map_or_else(
            || "none".to_owned(),
            |plan| format!("{}-v{}", plan.id, plan.version),
        );
        drop(data);
        // The registry's assigned, online tablets (Task A8).
        let tablets = self.live_tablets()?;
        Ok(LiveSnapshot {
            robots,
            tablets,
            map_version: MapVersion::from_tag(tag),
            at: now,
        })
    }
    async fn set_my_location(
        &self,
        identity: &ClientIdentity,
        place: &PlaceId,
    ) -> Result<TabletLive, ApiError> {
        let (floor, x, y) = self
            .data()
            .place(place)
            .ok_or_else(|| ApiError::invalid_input("place", "is not a place on the clinic map"))?;
        let device_id = identity
            .verified
            .device_id
            .clone()
            .ok_or_else(ApiError::device_required)?;
        let owner = match identity.verified.owner.clone() {
            Some(owner) => owner,
            None => OwnerLabel::new("Tablet (mock)")?,
        };
        Ok(TabletLive {
            device_id,
            owner,
            place: place.clone(),
            floor,
            point: Point2::new(x, y).map_err(|_| ApiError::internal("mock place position"))?,
            uncertainty_m: None,
        })
    }
    async fn ingest_scan(
        &self,
        _identity: &ClientIdentity,
        _scan: ScanBody,
    ) -> Result<PositionEstimate, ApiError> {
        let station: PlaceId = "nurse-station".parse()?;
        let (floor, x, y) = self.data().place(&station).unwrap_or((2, 6.0, 9.0));
        Ok(PositionEstimate {
            floor,
            place: station,
            point: Point2::new(x, y).map_err(|_| ApiError::internal("mock estimate"))?,
            uncertainty_m: 2.5,
            method: Method::Trilateration,
        })
    }
}

#[async_trait]
impl ZoneService for MockServices {
    async fn list(&self) -> Result<Vec<ZoneView>, ApiError> {
        Ok(self.data().zones.clone())
    }
    async fn upsert(
        &self,
        _actor: &ClientIdentity,
        id: ZoneId,
        input: ZoneInput,
    ) -> Result<ZoneView, ApiError> {
        if input.name.trim().is_empty() {
            return Err(ApiError::invalid_input("name", "must not be empty"));
        }
        if input.polygon.len() < 3 {
            return Err(ApiError::invalid_input(
                "polygon",
                "needs at least 3 points",
            ));
        }
        if input.polygon.iter().flatten().any(|v| !v.is_finite()) {
            return Err(ApiError::invalid_input(
                "polygon",
                "must contain plain numbers (metres)",
            ));
        }
        let connected = self.hub.connected_robots();
        let mut data = self.data();
        let robots = data.robot_ids(&connected);
        let version = data
            .zones
            .iter()
            .find(|zone| zone.id == id)
            .map_or(1, |zone| zone.version.saturating_add(1));
        let view = ZoneView {
            id: id.clone(),
            name: input.name,
            floor: input.floor,
            kind: input.kind,
            polygon: input.polygon,
            deliveries: deliveries(&robots, version),
            enforced_by_gardien: input.kind == ZoneKind::Deaf,
            version,
        };
        data.zones.retain(|zone| zone.id != id);
        data.zones.push(view.clone());
        data.zone_set_version = data.zone_set_version.saturating_add(1);
        drop(data);
        self.publish(AppEvent::ZoneUpdated { zone: view.clone() });
        self.send_zones_to_robots();
        Ok(view)
    }
    async fn delete(&self, _actor: &ClientIdentity, id: &ZoneId) -> Result<(), ApiError> {
        let mut data = self.data();
        if !data.zones.iter().any(|zone| &zone.id == id) {
            return Err(ApiError::not_found("Zone", id.as_str()));
        }
        data.zones.retain(|zone| &zone.id != id);
        data.zone_set_version = data.zone_set_version.saturating_add(1);
        drop(data);
        self.publish(AppEvent::ZoneDeleted {
            zone_id: id.clone(),
        });
        self.send_zones_to_robots();
        Ok(())
    }
    async fn zones_update(&self) -> Result<RobotDown, ApiError> {
        Ok(self.zones_down())
    }
    async fn record_ack(&self, robot: &RobotId, versions: &ZoneVersions) -> Result<(), ApiError> {
        let mut data = self.data();
        for zone in &mut data.zones {
            let Some(version) = versions.get(&zone.id) else {
                continue;
            };
            for entry in zone
                .deliveries
                .iter_mut()
                .filter(|entry| &entry.robot_id == robot)
            {
                entry.status = DeliveryState::Received;
                entry.acked_version = Some(*version);
                entry.robot_online = true;
            }
        }
        Ok(())
    }
}

#[async_trait]
impl RobotService for MockServices {
    async fn list(&self) -> Result<Vec<RobotView>, ApiError> {
        Ok(self.robot_views())
    }
    async fn command(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        name: CommandName,
    ) -> Result<CommandReceipt, ApiError> {
        let now = self.clock.now();
        let by_admin = actor.verified.role == Role::Admin;
        // The handler checks it too; the service never sends a non-admin's shutdown (R24).
        if name == CommandName::Shutdown
            && !actor
                .verified
                .role
                .allows(domain::Permission::RobotShutdown)
        {
            return Err(ApiError::forbidden(domain::Permission::RobotShutdown));
        }
        {
            let mut data = self.data();
            data.robot_mut(robot)?;
            // Ruling R24: an emergency stop is never lifted by anyone but an admin.
            if name == CommandName::Resume && !by_admin && data.estop_latched.contains(robot) {
                return Err(ApiError::estop_latched(robot.as_str()));
            }
        }
        // As on the real server: an offline robot cannot take a command (409).
        let offline = || {
            ApiError::conflict(
                "robot_offline",
                format!("Robot {robot} is offline: the command was not delivered."),
            )
        };
        match self.hub.send_to_robot(robot, RobotDown::Command { name }) {
            Ok(()) => {}
            Err(RealtimeError::RobotNotConnected { .. } | RealtimeError::Closed { .. }) => {
                return Err(offline());
            }
            Err(error) => {
                return Err(ApiError::conflict(
                    "robot_unreachable",
                    format!("{error} Try again."),
                ));
            }
        }
        // Shown once sent; the simulated robot confirms it in its next `robot.state`.
        if name == CommandName::Resume && by_admin {
            // The admin's explicit resume re-arms a robot after an emergency stop.
            self.data().estop_latched.remove(robot);
        }
        if let Ok(target) = self.data().robot_mut(robot) {
            target.view.state = match name {
                CommandName::Pause => RobotStatus::Paused,
                CommandName::Resume if target.view.task_id.is_some() => RobotStatus::Busy,
                CommandName::Resume | CommandName::Dock => RobotStatus::Idle,
                CommandName::Estop | CommandName::Shutdown => target.view.state,
            };
        }
        self.publish_robot(robot);
        let command_id = self.log_command(actor, robot, name);
        Ok(CommandReceipt {
            accepted: true,
            reason: Some(MOCK_SENT_NOTE.to_owned()),
            sent_at: now,
            command: name,
            command_id,
        })
    }
    async fn revert(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        command_id: Uuid,
    ) -> Result<RevertReceipt, ApiError> {
        // Reserved under the lock: a concurrent second revert is 409 and sends nothing.
        let inverse = self.reserve_revert(robot, command_id)?;
        // Sent as the admin's own command (no alert: the admin sent it).
        let receipt = match self.command(actor, robot, inverse).await {
            Ok(receipt) => receipt,
            Err(error) => {
                self.release_revert(command_id);
                return Err(error);
            }
        };
        self.mark_reverted(actor, robot, command_id, receipt.command_id);
        Ok(RevertReceipt {
            reverted_by_command_id: receipt.command_id,
        })
    }
    async fn estop(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
    ) -> Result<CommandReceipt, ApiError> {
        let now = self.clock.now();
        self.data().robot_mut(robot)?;
        let stop = RobotDown::Command {
            name: CommandName::Estop,
        };
        // Sent first; the view says `estop` only once the stop is queued to the robot.
        match self.hub.send_priority(robot, stop) {
            Ok(()) => {}
            Err(RealtimeError::RobotNotConnected { .. } | RealtimeError::Closed { .. }) => {
                return Err(ApiError::conflict(
                    "robot_offline",
                    format!(
                        "Robot {robot} is offline: the stop was not delivered. Use the physical button."
                    ),
                ));
            }
            Err(error) => {
                self.publish(AppEvent::Alert {
                    level: AlertKind::EstopNotDelivered.level(),
                    kind: AlertKind::EstopNotDelivered,
                    message: format!(
                        "The stop for robot {robot} was not delivered ({error}). Use the physical button."
                    ),
                    command: None,
                });
                return Err(ApiError::conflict(
                    "robot_unreachable",
                    format!("{error} Use the physical button."),
                ));
            }
        }
        {
            let mut data = self.data();
            data.estop_latched.insert(robot.clone());
            if let Ok(target) = data.robot_mut(robot) {
                target.view.state = RobotStatus::Estop;
            }
        }
        self.publish_robot(robot);
        let command_id = self.log_command(actor, robot, CommandName::Estop);
        Ok(CommandReceipt {
            accepted: true,
            reason: Some(MOCK_SENT_NOTE.to_owned()),
            sent_at: now,
            command: CommandName::Estop,
            command_id,
        })
    }
    async fn is_known(&self, _robot: &RobotId) -> Result<bool, ApiError> {
        // Any robot id may connect to the mock (an unknown one is added to the list), so the
        // `fake_robot` can play any robot.
        Ok(true)
    }
    async fn run_session(&self, mut session: RobotSession) {
        let robot = session.robot().clone();
        self.robot_connected(&robot);
        match self.zones_update().await {
            Ok(zones) => {
                if let Err(error) = session.send(zones) {
                    tracing::warn!(%robot, %error, "mock: zones.update not sent on connect");
                }
            }
            Err(error) => tracing::warn!(%robot, code = error.code(), "mock: no zones.update"),
        }
        while let Some(envelope) = session.recv().await {
            match envelope.body {
                RobotUp::Hello {
                    robot_id,
                    simulated,
                    running_task,
                    ..
                } => {
                    tracing::info!(%robot, %robot_id, simulated, ?running_task, "mock: robot said hello");
                    // The robot's word is the truth on (re)connect: without a running task,
                    // a task it held before is failed (`robot_lost`).
                    if running_task.is_none() {
                        self.fail_open_tasks(&robot, false);
                    }
                }
                state @ RobotUp::State { .. } => self.robot_state(&robot, state),
                RobotUp::TaskEvent {
                    task_id,
                    state,
                    reason,
                } => {
                    if let Err(error) =
                        self.apply_event(&robot, envelope.id, &task_id, state, reason)
                    {
                        tracing::warn!(%robot, task = %task_id, code = error.code(), message = error.message(), "mock: task event not applied");
                    }
                }
                RobotUp::InventorySeen { place, items } => {
                    tracing::debug!(%robot, %place, items = items.len(), "mock: shelf seen (not reconciled)");
                }
                RobotUp::ZoneAck { zone_version_by_id } => {
                    if let Err(error) = self.record_ack(&robot, &zone_version_by_id).await {
                        tracing::warn!(%robot, code = error.code(), "mock: zone ack not recorded");
                    }
                }
            }
        }
    }
    async fn on_disconnect(&self, robot: &RobotId) {
        // A robot that reconnected between `unregister_robot` and this call has a new session:
        // leave it connected, its new `hello` settles its tasks.
        if self.hub.is_connected(robot) {
            tracing::info!(%robot, "mock: robot reconnected before its old session closed");
            return;
        }
        let now = self.clock.now();
        self.fail_open_tasks(robot, true);
        {
            let mut data = self.data();
            if let Ok(entry) = data.robot_mut(robot) {
                entry.view.last_seen = Some(now);
                entry.view.task_id = None;
            }
            for zone in &mut data.zones {
                for entry in zone
                    .deliveries
                    .iter_mut()
                    .filter(|entry| &entry.robot_id == robot)
                {
                    entry.robot_online = false;
                }
            }
        }
        self.publish_robot(robot);
        self.publish(AppEvent::Alert {
            level: AlertKind::RobotOffline.level(),
            kind: AlertKind::RobotOffline,
            message: format!("Robot {robot} disconnected (mock server)."),
            command: None,
        });
    }
    async fn check_liveness(&self) -> Vec<RobotId> {
        // Mock sessions end when their socket closes (`on_disconnect`); nothing goes stale.
        Vec::new()
    }
}

#[async_trait]
impl ScheduleService for MockServices {
    async fn list(&self) -> Result<Vec<ScheduleView>, ApiError> {
        Ok(self.data().schedules.clone())
    }
    async fn update(
        &self,
        _actor: &ClientIdentity,
        id: &ScheduleId,
        patch: SchedulePatch,
    ) -> Result<ScheduleView, ApiError> {
        if let Some(time) = &patch.time
            && !valid_time(time)
        {
            return Err(ApiError::invalid_input(
                "time",
                "must be a time HH:MM such as 02:30",
            ));
        }
        let mut data = self.data();
        if let Some(robot) = &patch.robot_id
            && !data.robots.iter().any(|known| &known.view.id == robot)
        {
            return Err(ApiError::invalid_input("robot_id", "is not a known robot"));
        }
        let schedule = data
            .schedules
            .iter_mut()
            .find(|schedule| &schedule.id == id)
            .ok_or_else(|| ApiError::not_found("Schedule", id.as_str()))?;
        if let Some(enabled) = patch.enabled {
            schedule.enabled = enabled;
        }
        if let Some(time) = patch.time {
            schedule.time = time;
        }
        if let Some(robot) = patch.robot_id {
            schedule.robot_id = Some(robot);
        }
        let schedule = schedule.clone();
        drop(data);
        self.publish(AppEvent::ScheduleUpdated {
            schedule: schedule.clone(),
        });
        Ok(schedule)
    }
}

#[async_trait]
impl AuditQueryService for MockServices {
    async fn query(&self, params: AuditQueryParams) -> Result<AuditPageView, ApiError> {
        let limit = params.limit.unwrap_or(AUDIT_DEFAULT_LIMIT);
        if limit == 0 || limit > AUDIT_MAX_LIMIT {
            return Err(ApiError::invalid_input(
                "limit",
                "must be between 1 and 500",
            ));
        }
        let limit = usize::try_from(limit).unwrap_or(usize::MAX);
        let matching: Vec<AuditEntry> = self
            .data()
            .audit
            .iter()
            .filter(|row| params.from.is_none_or(|from| row.at >= from))
            .filter(|row| params.to.is_none_or(|to| row.at < to))
            .filter(|row| {
                params
                    .actor
                    .as_ref()
                    .is_none_or(|actor| &row.actor == actor)
            })
            .filter(|row| {
                params
                    .category
                    .as_ref()
                    .is_none_or(|category| &row.category == category)
            })
            .filter(|row| params.after.is_none_or(|after| row.id > after))
            .cloned()
            .collect();
        let more = matching.len() > limit;
        let items: Vec<AuditEntry> = matching.into_iter().take(limit).collect();
        let next = if more {
            items.last().map(|row| row.id)
        } else {
            None
        };
        Ok(AuditPageView { items, next })
    }
    async fn integrity(&self) -> Result<audit::VerifyReport, ApiError> {
        let records = u64::try_from(self.data().audit.len()).unwrap_or(u64::MAX);
        Ok(audit::VerifyReport {
            records,
            seals: 0,
            first_bad_record: None,
            gaps: Vec::new(),
            bad_seals: Vec::new(),
            anchor_mismatches: Vec::new(),
            torn_tail: false,
        })
    }
}

#[async_trait]
impl IncidentService for MockServices {
    async fn list_incidents(&self, open_only: bool) -> Result<Vec<Incident>, ApiError> {
        Ok(self
            .data()
            .incidents
            .iter()
            .filter(|incident| !open_only || incident.closed_at.is_none())
            .cloned()
            .collect())
    }
    async fn acknowledge(
        &self,
        actor: &ClientIdentity,
        id: IncidentId,
    ) -> Result<Incident, ApiError> {
        let mut data = self.data();
        let incident = data
            .incidents
            .iter_mut()
            .find(|incident| incident.id == id)
            .ok_or_else(|| ApiError::not_found("Incident", &id.0.to_string()))?;
        incident.acknowledged_by.clone_from(&actor.verified.owner);
        Ok(incident.clone())
    }
    async fn close_incident(
        &self,
        _actor: &ClientIdentity,
        id: IncidentId,
    ) -> Result<Incident, ApiError> {
        let now = self.clock.now();
        let mut data = self.data();
        let incident = data
            .incidents
            .iter_mut()
            .find(|incident| incident.id == id)
            .ok_or_else(|| ApiError::not_found("Incident", &id.0.to_string()))?;
        incident.closed_at.get_or_insert(now);
        Ok(incident.clone())
    }
    async fn report_device_event(
        &self,
        _actor: &ClientIdentity,
        _code: AppErrorCode,
    ) -> Result<(), ApiError> {
        Ok(())
    }
}

#[async_trait]
impl SystemModeService for MockServices {
    async fn mode(&self) -> Result<SystemModeState, ApiError> {
        Ok(self.mock_mode())
    }
    async fn set_mode(
        &self,
        actor: &ClientIdentity,
        request: SetModeRequest,
    ) -> Result<SystemModeState, ApiError> {
        self.mock_set_mode(actor, request)
    }
    fn is_emergency(&self) -> bool {
        self.mock_is_emergency()
    }
}

#[async_trait]
impl DeviceAdminService for MockServices {
    async fn list(&self) -> Result<Vec<TabletView>, ApiError> {
        Ok(self.mock_tablets())
    }
    async fn disconnect(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
    ) -> Result<TabletView, ApiError> {
        self.mock_free_tablet(actor, id)
    }
    async fn assign(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
        request: AssignTabletRequest,
    ) -> Result<TabletView, ApiError> {
        self.mock_assign_tablet(actor, id, request)
    }
}

#[async_trait]
impl MonitorService for MockServices {
    async fn summary(&self) -> Result<MonitorSummaryView, ApiError> {
        Ok(self.mock_summary())
    }
    async fn traffic(&self, window_s: u32) -> Result<TrafficView, ApiError> {
        Ok(self.mock_traffic(window_s))
    }
    async fn clients(&self, limit: u32) -> Result<Vec<ClientView>, ApiError> {
        Ok(self.mock_clients(limit))
    }
    async fn blocks(&self) -> Result<Vec<BlockView>, ApiError> {
        Ok(self.mock_blocks())
    }
    async fn add_block(
        &self,
        actor: &ClientIdentity,
        request: NewBlockRequest,
    ) -> Result<BlockView, ApiError> {
        self.mock_add_block(actor, &request)
    }
    async fn remove_block(&self, actor: &ClientIdentity, id: &str) -> Result<(), ApiError> {
        self.mock_remove_block(actor, id)
    }
}

#[async_trait]
impl ServiceStatsService for MockServices {
    async fn service(&self, hours: u32) -> Result<ServiceStatsView, ApiError> {
        Ok(self.mock_service_stats(hours))
    }
}

#[async_trait]
impl TokenVerifier for MockServices {
    async fn verify(&self, raw: &str) -> Result<Option<VerifiedIdentity>, SecurityError> {
        // Every mock identity is built from constants; a failure here is a programming error.
        if let Some(robot) = mock_identity(raw) {
            return Ok(Some(robot));
        }
        if raw.starts_with(MOCK_TABLET_TOKEN_PREFIX) {
            // A freed tablet's token is revoked at once (Task A8).
            return Ok(self.tablet_identity(raw));
        }
        self.account_identity(raw).map_err(|error| {
            tracing::error!(%error, "mock identity could not be built");
            SecurityError::VerifierUnavailable
        })
    }
}

impl JournalStatus for MockServices {
    fn is_writable(&self) -> bool {
        // Nothing is journaled in mock mode, so nothing is ever paused for that reason.
        true
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use domain::{FakeClock, Role};
    use security::TokenVerifier as _;

    use super::{MockData, MockServices, mock_identity};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn embedded_seeds_parse() -> TestResult {
        let data = MockData::from_seeds(chrono::Utc::now())?;
        assert_eq!(data.plans.len(), 1);
        assert_eq!(data.robots.len(), 5);
        assert_eq!(data.items.len(), 10);
        assert_eq!(data.zones.len(), 3);
        assert_eq!(data.schedules.len(), 1);
        Ok(())
    }

    #[tokio::test]
    async fn mock_tokens_map_to_roles() -> TestResult {
        let mock = MockServices::new();
        let admin = mock.verify("mock-admin").await?.ok_or("no admin")?;
        assert_eq!(admin.role, Role::Admin);
        // Task A7: a mock user is its account (the 64 hex digits of its id), never a name.
        let subject = admin.subject_id.to_string();
        assert_eq!(subject.len(), "user:".len() + 64, "{subject}");
        let nurse = mock.verify("mock-nurse").await?.ok_or("no nurse")?;
        assert_eq!(nurse.role, Role::Nurse);
        let robot = mock_identity("mock-robot").ok_or("no robot")?;
        assert_eq!(robot.role, Role::Robot);
        assert!(mock.verify("mock-pirate").await?.is_none());
        assert!(mock.verify("admin").await?.is_none());
        Ok(())
    }

    #[test]
    fn mock_services_start_on_a_fake_clock() {
        let clock = Arc::new(FakeClock::new(chrono::Utc::now()));
        let mock = MockServices::with_clock(clock);
        assert_eq!(mock.robot_views().len(), 5);
    }
}
