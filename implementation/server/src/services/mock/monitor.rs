//! Monitoring, blocks and service statistics in the mock (Task A8: what fills T7b and T11e
//! do on the live server, for real in memory).
//!
//! The counters, the rate limit and the rules are the shared `security::TrafficMonitor`, fed
//! by the layers `MockStack::apply_monitored` puts around the mock router; this module is its
//! admin view and its hooks (`security.alert` to admin sockets, audit rows).

use std::collections::BTreeMap;

use domain::{BlockSource, RobotId, TaskState};
use realtime::AppEvent;
use security::{BlockAction, ClientIdentity, MonitorHooks, MonitorNotice};

use super::MockServices;
use crate::dto::{
    BlockView, ClientView, ItemCount, MonitorSummaryView, NewBlockRequest, PlaceCount,
    ServiceStatsView, TrafficView,
};
use crate::error::ApiError;

/// How many items and places `GET /stats/service` lists.
const TOP: usize = 6;

impl MonitorHooks for MockServices {
    fn notify(&self, notice: MonitorNotice) {
        match notice {
            MonitorNotice::Alert(alert) => self.publish(AppEvent::SecurityAlert { alert }),
            MonitorNotice::Journal(row) => {
                let action = match row.action {
                    BlockAction::Blocked => "client_blocked",
                    BlockAction::Unblocked => "client_unblocked",
                };
                let source = match row.rule.source {
                    BlockSource::Manual => "manual",
                    BlockSource::Auto => "auto",
                };
                let by = row
                    .removed_by
                    .clone()
                    .or_else(|| row.rule.by.clone())
                    .unwrap_or_else(|| "system:server".to_owned());
                let why = match (row.action, &row.removed_by) {
                    (BlockAction::Unblocked, None) => "expired".to_owned(),
                    (BlockAction::Unblocked, Some(_)) => "removed".to_owned(),
                    (BlockAction::Blocked, _) => row.rule.reason.clone(),
                };
                self.push_labelled_audit(
                    &by,
                    action,
                    &row.rule.target,
                    format!("{source} {}: {why}", row.rule.id),
                    "security",
                );
            }
        }
    }

    fn robot_connected(&self, robot: &str) -> bool {
        robot
            .parse::<RobotId>()
            .is_ok_and(|robot| self.hub.is_connected(&robot))
    }
}

impl MockServices {
    /// `GET /monitor/summary`.
    pub(super) fn mock_summary(&self) -> MonitorSummaryView {
        let now = self.clock.now();
        let robots = self.robot_views();
        let totals = self.traffic.totals();
        let count = |n: usize| u32::try_from(n).unwrap_or(u32::MAX);
        MonitorSummaryView {
            started_at: self.started,
            uptime_s: u64::try_from((now - self.started).num_seconds()).unwrap_or(0),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            robots_connected: count(robots.iter().filter(|robot| robot.connected).count()),
            robots_total: count(robots.len()),
            app_clients: count(self.hub.app_subscribers()),
            // Mock mode: no journal, no database to check.
            journal_ok: None,
            database_ok: None,
            requests_per_s: totals.requests_per_s,
            rejected_per_s: totals.rejected_per_s,
            p95_ms: totals.p95_ms,
            blocked_clients: totals.blocked_clients,
        }
    }

    /// `GET /monitor/traffic`.
    pub(super) fn mock_traffic(&self, window_s: u32) -> TrafficView {
        self.traffic.traffic(window_s)
    }

    /// `GET /monitor/clients`.
    pub(super) fn mock_clients(&self, limit: u32) -> Vec<ClientView> {
        self.traffic
            .clients(usize::try_from(limit).unwrap_or(usize::MAX))
    }

    /// `GET /security/blocks`.
    pub(super) fn mock_blocks(&self) -> Vec<BlockView> {
        self.traffic.blocks()
    }

    /// `POST /security/blocks`.
    pub(super) fn mock_add_block(
        &self,
        actor: &ClientIdentity,
        request: &NewBlockRequest,
    ) -> Result<BlockView, ApiError> {
        let by = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        Ok(self.traffic.add_block(request, &by, actor.network.ip)?)
    }

    /// `DELETE /security/blocks/{id}`.
    pub(super) fn mock_remove_block(
        &self,
        actor: &ClientIdentity,
        id: &str,
    ) -> Result<(), ApiError> {
        let by = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        self.traffic
            .remove_block(id, &by)
            .map(|_| ())
            .map_err(|error| ApiError::from(("id", error)))
    }

    /// `GET /stats/service`: counts of the mock's tasks created in the last `hours`.
    pub(super) fn mock_service_stats(&self, hours: u32) -> ServiceStatsView {
        let now = self.clock.now();
        let since = now - chrono::Duration::hours(i64::from(hours));
        let (online, total) = self.bedside_counts();
        let data = self.data();
        let tasks: Vec<_> = data
            .tasks
            .iter()
            .filter(|task| task.created_at >= since)
            .collect();
        let count = |n: usize| u32::try_from(n).unwrap_or(u32::MAX);
        let mut waits: Vec<u64> = tasks
            .iter()
            .filter(|task| task.state == TaskState::Delivered)
            .filter_map(|task| {
                let delivered = task
                    .history
                    .iter()
                    .rev()
                    .find(|entry| entry.label == "delivered")
                    .map_or(task.updated_at, |entry| entry.at);
                u64::try_from((delivered - task.created_at).num_seconds()).ok()
            })
            .collect();
        waits.sort_unstable();
        let mut items: BTreeMap<String, u32> = BTreeMap::new();
        let mut places: BTreeMap<String, u32> = BTreeMap::new();
        for task in &tasks {
            if let Some(item) = &task.item {
                let label = data
                    .items
                    .iter()
                    .find(|level| &level.item == item)
                    .map_or_else(|| item.to_string(), |level| level.label.clone());
                *items.entry(label).or_default() += 1;
            }
            *places.entry(task.to_place.to_string()).or_default() += 1;
        }
        if self.stats_min_place_count > 0 {
            let small: Vec<String> = places
                .iter()
                .filter(|(_, n)| **n < self.stats_min_place_count)
                .map(|(place, _)| place.clone())
                .collect();
            let folded: u32 = small.iter().filter_map(|place| places.remove(place)).sum();
            if folded > 0 {
                *places.entry("other".to_owned()).or_default() += folded;
            }
        }
        ServiceStatsView {
            hours,
            requests: count(tasks.len()),
            delivered: count(
                tasks
                    .iter()
                    .filter(|task| task.state == TaskState::Delivered)
                    .count(),
            ),
            failed: count(
                tasks
                    .iter()
                    .filter(|task| task.state == TaskState::Failed)
                    .count(),
            ),
            median_wait_s: percentile(&waits, 50),
            p90_wait_s: percentile(&waits, 90),
            by_item: top(items)
                .into_iter()
                .map(|(label, count)| ItemCount { label, count })
                .collect(),
            by_place: top(places)
                .into_iter()
                .map(|(place, count)| PlaceCount { place, count })
                .collect(),
            bedside_online: online,
            bedside_total: total,
        }
    }
}

/// The `percent`th percentile (nearest rank) of sorted values; `None` when empty.
fn percentile(sorted: &[u64], percent: usize) -> Option<u64> {
    let rank = (sorted.len() * percent).div_ceil(100).saturating_sub(1);
    sorted.get(rank).copied()
}

/// The [`TOP`] largest counts, largest first (ties by name).
fn top(counts: BTreeMap<String, u32>) -> Vec<(String, u32)> {
    let mut sorted: Vec<(String, u32)> = counts.into_iter().collect();
    sorted.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    sorted.truncate(TOP);
    sorted
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::{percentile, top};

    #[test]
    fn percentiles_are_nearest_rank() {
        assert_eq!(percentile(&[], 50), None);
        assert_eq!(percentile(&[7], 90), Some(7));
        let waits: Vec<u64> = (1..=10).collect();
        assert_eq!(percentile(&waits, 50), Some(5));
        assert_eq!(percentile(&waits, 90), Some(9));
    }

    #[test]
    fn top_keeps_six_largest_first() {
        let counts: BTreeMap<String, u32> =
            (1..=8_u32).map(|n| (format!("place-{n}"), n)).collect();
        let kept = top(counts);
        assert_eq!(kept.len(), 6);
        assert_eq!(kept.first().map(|(_, n)| *n), Some(8));
        assert_eq!(kept.last().map(|(_, n)| *n), Some(3));
    }
}
