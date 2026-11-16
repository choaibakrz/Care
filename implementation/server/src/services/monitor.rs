//! Real `MonitorService` (Task A8, fill T7b): the admin's view of the live server's defences.
//!
//! The counters, the rate limit and the rules are `security::TrafficMonitor` (real code,
//! shared with `--mock`); the live security stack feeds it in Task 7b. This service adds what
//! only the live wiring knows: robots, open sockets, the journal and the database.

use std::sync::Arc;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use chrono::{DateTime, Utc};
use domain::{Actor, Clock, RobotId};
use realtime::{AppEvent, Hub};
use security::{BlockAction, ClientIdentity, MonitorHooks, MonitorNotice, TrafficMonitor};

use super::{MonitorService, RobotService};
use crate::dto::{BlockView, ClientView, MonitorSummaryView, NewBlockRequest, TrafficView};
use crate::error::ApiError;

/// What the real monitoring needs.
pub struct MonitorDeps {
    /// Counters, limits and rules (shared with the security stack).
    pub traffic: Arc<TrafficMonitor>,
    /// Robots (connected and total).
    pub robots: Arc<dyn RobotService>,
    /// Open `/ws` connections.
    pub hub: Arc<Hub>,
    /// `journal_ok`; `client_blocked`, `client_unblocked`.
    pub journal: Journal,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
    /// When the server started.
    pub started_at: DateTime<Utc>,
}

/// Monitoring and blocks of the live server.
pub struct RealMonitorService {
    deps: MonitorDeps,
}

impl RealMonitorService {
    /// On the shared traffic monitor.
    #[must_use]
    pub fn new(deps: MonitorDeps) -> RealMonitorService {
        RealMonitorService { deps }
    }
}

/// The owner label of `actor` (who acted), or `unknown`.
fn by_label(actor: &ClientIdentity) -> String {
    actor
        .verified
        .owner
        .as_ref()
        .map_or_else(|| "unknown".to_owned(), ToString::to_string)
}

impl MonitorHooks for RealMonitorService {
    fn notify(&self, notice: MonitorNotice) {
        match notice {
            MonitorNotice::Alert(alert) => self.deps.hub.publish(AppEvent::SecurityAlert { alert }),
            MonitorNotice::Journal(row) => {
                let body = match row.action {
                    BlockAction::Blocked => RecordBody::ClientBlocked {
                        rule: row.rule.id.clone(),
                        target: row.rule.target.clone(),
                        reason: row.rule.reason.clone(),
                        source: row.rule.source,
                        expires_at: row.rule.expires_at,
                    },
                    BlockAction::Unblocked => RecordBody::ClientUnblocked {
                        rule: row.rule.id.clone(),
                        target: row.rule.target.clone(),
                        expired: row.removed_by.is_none(),
                    },
                };
                let journal = self.deps.journal.clone();
                // Hooks are synchronous: the record is written in the background.
                if let Ok(runtime) = tokio::runtime::Handle::try_current() {
                    runtime.spawn(async move {
                        if let Err(error) = journal
                            .append(
                                Severity::Notice,
                                Category::Security,
                                Actor::System("security"),
                                body,
                                None,
                            )
                            .await
                        {
                            tracing::warn!(%error, "block change not journaled");
                        }
                    });
                }
            }
        }
    }

    fn robot_connected(&self, robot: &str) -> bool {
        robot
            .parse::<RobotId>()
            .is_ok_and(|robot| self.deps.hub.is_connected(&robot))
    }
}

#[async_trait]
impl MonitorService for RealMonitorService {
    async fn summary(&self) -> Result<MonitorSummaryView, ApiError> {
        let now = self.deps.clock.now();
        let count = |n: usize| u32::try_from(n).unwrap_or(u32::MAX);
        // The robot list reads the database: it doubles as the cheap database check.
        let robots = self.deps.robots.list().await;
        let database_ok = robots.is_ok();
        let robots = robots.unwrap_or_default();
        let totals = self.deps.traffic.totals();
        Ok(MonitorSummaryView {
            started_at: self.deps.started_at,
            uptime_s: u64::try_from((now - self.deps.started_at).num_seconds()).unwrap_or(0),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            robots_connected: count(robots.iter().filter(|robot| robot.connected).count()),
            robots_total: count(robots.len()),
            app_clients: count(self.deps.hub.app_subscribers()),
            journal_ok: Some(self.deps.journal.is_writable()),
            database_ok: Some(database_ok),
            requests_per_s: totals.requests_per_s,
            rejected_per_s: totals.rejected_per_s,
            p95_ms: totals.p95_ms,
            blocked_clients: totals.blocked_clients,
        })
    }

    async fn traffic(&self, window_s: u32) -> Result<TrafficView, ApiError> {
        Ok(self.deps.traffic.traffic(window_s))
    }

    async fn clients(&self, limit: u32) -> Result<Vec<ClientView>, ApiError> {
        Ok(self
            .deps
            .traffic
            .clients(usize::try_from(limit).unwrap_or(usize::MAX)))
    }

    async fn blocks(&self) -> Result<Vec<BlockView>, ApiError> {
        Ok(self.deps.traffic.blocks())
    }

    async fn add_block(
        &self,
        actor: &ClientIdentity,
        request: NewBlockRequest,
    ) -> Result<BlockView, ApiError> {
        Ok(self
            .deps
            .traffic
            .add_block(&request, &by_label(actor), actor.network.ip)?)
    }

    async fn remove_block(&self, actor: &ClientIdentity, id: &str) -> Result<(), ApiError> {
        self.deps
            .traffic
            .remove_block(id, &by_label(actor))
            .map(|_| ())
            .map_err(|error| ApiError::from(("id", error)))
    }
}
