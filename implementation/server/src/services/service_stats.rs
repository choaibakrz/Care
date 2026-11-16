//! Real `ServiceStatsService` (Task A8, fill T11e): `GET /stats/service`, counts only.
//!
//! Never a person: no patient, no staff name, no room-to-person link. The by-place counts
//! may fold places with few requests into `other` (k-anonymity, `SERVICE_STATS_MIN_COUNT`).

use std::collections::BTreeMap;
use std::sync::Arc;

use async_trait::async_trait;
use domain::ports::{DeviceRepository, InventoryRepository, TaskRepository};
use domain::{Clock, ItemId, Page, Task, TaskFilter, TaskState};

use super::ServiceStatsService;
use crate::dto::{ItemCount, PlaceCount, ServiceStatsView};
use crate::error::ApiError;

/// How many items and places the answer lists.
pub const SERVICE_STATS_TOP: usize = 6;

/// What the real statistics need.
pub struct ServiceStatsDeps {
    /// Tasks of the window.
    pub tasks: Arc<dyn TaskRepository>,
    /// Item labels.
    pub inventory: Arc<dyn InventoryRepository>,
    /// Bedside tablets.
    pub devices: Arc<dyn DeviceRepository>,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
    /// Places with fewer requests than this are folded into `other` (0: never).
    pub min_place_count: u32,
}

/// Service statistics of the live server.
pub struct RealServiceStats {
    deps: ServiceStatsDeps,
}

impl RealServiceStats {
    /// On the task, stock and device repositories.
    #[must_use]
    pub fn new(deps: ServiceStatsDeps) -> RealServiceStats {
        RealServiceStats { deps }
    }
}

#[async_trait]
impl ServiceStatsService for RealServiceStats {
    async fn service(&self, hours: u32) -> Result<ServiceStatsView, ApiError> {
        let now = self.deps.clock.now();
        let since = now - chrono::Duration::hours(i64::from(hours));
        let filter = TaskFilter {
            state: None,
            robot: None,
            requested_by: None,
            since: Some(since),
            active_only: false,
        };
        let mut tasks: Vec<Task> = Vec::new();
        for page in 0..MAX_PAGES {
            let page = Page::new(Page::MAX_LIMIT, page.saturating_mul(Page::MAX_LIMIT))?;
            let batch = self.deps.tasks.list(&filter, &page).await?;
            let full = batch.len() >= usize::try_from(Page::MAX_LIMIT).unwrap_or(usize::MAX);
            tasks.extend(batch);
            if !full {
                break;
            }
        }
        tasks.retain(|task| task.created_at() >= since);
        let count = |n: usize| u32::try_from(n).unwrap_or(u32::MAX);
        // The domain task keeps no history: a delivered task's last change is its delivery.
        let mut waits: Vec<u64> = tasks
            .iter()
            .filter(|task| task.state() == TaskState::Delivered)
            .filter_map(|task| {
                u64::try_from((task.updated_at() - task.created_at()).num_seconds()).ok()
            })
            .collect();
        waits.sort_unstable();
        let labels: BTreeMap<ItemId, String> = self
            .deps
            .inventory
            .list()
            .await?
            .into_iter()
            .map(|level| (level.item, level.label))
            .collect();
        let mut items: BTreeMap<String, u32> = BTreeMap::new();
        let mut places: BTreeMap<String, u32> = BTreeMap::new();
        for task in &tasks {
            if let Some(item) = task.item() {
                let label = labels
                    .get(item)
                    .cloned()
                    .unwrap_or_else(|| item.to_string());
                *items.entry(label).or_default() += 1;
            }
            *places.entry(task.to().to_string()).or_default() += 1;
        }
        let min = self.deps.min_place_count;
        if min > 0 {
            let small: Vec<String> = places
                .iter()
                .filter(|(_, n)| **n < min)
                .map(|(place, _)| place.clone())
                .collect();
            let folded: u32 = small.iter().filter_map(|place| places.remove(place)).sum();
            if folded > 0 {
                *places.entry("other".to_owned()).or_default() += folded;
            }
        }
        let in_state =
            |state: TaskState| count(tasks.iter().filter(|task| task.state() == state).count());
        // Device records carry no kind nor last-heard time here: no bedside count yet.
        let _ = &self.deps.devices;
        Ok(ServiceStatsView {
            hours,
            requests: count(tasks.len()),
            delivered: in_state(TaskState::Delivered),
            failed: in_state(TaskState::Failed),
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
            bedside_online: 0,
            bedside_total: 0,
        })
    }
}

/// Most task pages read (500 each).
const MAX_PAGES: u32 = 20;

/// The `percent`th percentile (nearest rank) of sorted values; `None` when empty.
fn percentile(sorted: &[u64], percent: usize) -> Option<u64> {
    let rank = (sorted.len() * percent).div_ceil(100).saturating_sub(1);
    sorted.get(rank).copied()
}

/// The [`SERVICE_STATS_TOP`] largest counts, largest first (ties by name).
fn top(counts: BTreeMap<String, u32>) -> Vec<(String, u32)> {
    let mut sorted: Vec<(String, u32)> = counts.into_iter().collect();
    sorted.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    sorted.truncate(SERVICE_STATS_TOP);
    sorted
}
