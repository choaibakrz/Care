//! Real `StatsService` (Task 11d): the heat map, a port of `admin/src/lib/heat.ts`.
//!
//! **Robots only, never tablets** (privacy rule): the only input is a [`RobotLive`], taken
//! from the live robot list once per [`HEAT_SAMPLE_INTERVAL`]; there is no method that takes
//! a tablet. Counts live in memory and start from zero at every restart; nothing is stored.

use std::collections::BTreeMap;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use async_trait::async_trait;
use locations::{ActiveMap, LivePositions, Point2, RobotLive};
use tokio::task::JoinHandle;

use super::StatsService;
use crate::dto::HeatView;
use crate::error::ApiError;

/// Side of a heat cell, metres.
pub const HEAT_CELL_M: f64 = 1.0;
/// How often each robot's position is sampled.
pub const HEAT_SAMPLE_INTERVAL: Duration = Duration::from_secs(1);

/// Counts of one floor, row-major over the floor outline's bounding box in 1 m cells.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
struct FloorHeat {
    columns: u32,
    rows: u32,
    counts: Vec<u32>,
}

/// The heat map: per floor, robot samples per square metre.
pub struct HeatMap {
    active: Arc<ActiveMap>,
    floors: Mutex<BTreeMap<i32, FloorHeat>>,
}

impl HeatMap {
    /// An empty heat map on the active plan.
    #[must_use]
    pub fn new(active: Arc<ActiveMap>) -> HeatMap {
        HeatMap {
            active,
            floors: Mutex::new(BTreeMap::new()),
        }
    }

    /// Counts one robot sample in the cell under it. Stale robots, robots off every floor and
    /// positions outside the floor's bounding box are not counted.
    pub fn record(&self, robot: &RobotLive) {
        if robot.stale {
            return;
        }
        let Some(bounds) = self.bounds(robot.floor) else {
            return;
        };
        let (Some(column), Some(row)) = (
            cell_of(robot.point.x() - bounds.min_x, bounds.columns),
            cell_of(robot.point.y() - bounds.min_y, bounds.rows),
        ) else {
            return;
        };
        let mut floors = self.floors.lock().unwrap_or_else(PoisonError::into_inner);
        let heat = floors.entry(robot.floor).or_insert_with(|| bounds.empty());
        if heat.columns != bounds.columns || heat.rows != bounds.rows {
            *heat = bounds.empty();
        }
        let index = usize::try_from(row.saturating_mul(bounds.columns).saturating_add(column));
        if let Some(count) = index.ok().and_then(|index| heat.counts.get_mut(index)) {
            *count = count.saturating_add(1);
        }
    }

    /// Forgets every count (the active plan changed: the cells no longer match).
    pub fn clear(&self) {
        self.floors
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clear();
    }

    /// Samples every live robot each `every` (robots only: `LivePositions::snapshot().robots`).
    #[must_use]
    pub fn spawn_sampler(
        self: Arc<Self>,
        live: Arc<LivePositions>,
        every: Duration,
    ) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticks = tokio::time::interval(every);
            loop {
                ticks.tick().await;
                for robot in &live.snapshot().robots {
                    self.record(robot);
                }
            }
        })
    }
}

impl HeatMap {
    /// The bounding box of a floor of the active plan, in cells.
    fn bounds(&self, floor: i32) -> Option<Bounds> {
        let plan = self.active.current();
        let outline = plan.map.floor(floor)?.outline.vertices().to_vec();
        let min_x = outline.iter().map(Point2::x).fold(f64::INFINITY, f64::min);
        let min_y = outline.iter().map(Point2::y).fold(f64::INFINITY, f64::min);
        let max_x = outline
            .iter()
            .map(Point2::x)
            .fold(f64::NEG_INFINITY, f64::max);
        let max_y = outline
            .iter()
            .map(Point2::y)
            .fold(f64::NEG_INFINITY, f64::max);
        if !(min_x.is_finite() && min_y.is_finite()) {
            return None;
        }
        Some(Bounds {
            min_x,
            min_y,
            columns: cells(max_x - min_x),
            rows: cells(max_y - min_y),
        })
    }
}

/// A floor's bounding box in cells.
struct Bounds {
    min_x: f64,
    min_y: f64,
    columns: u32,
    rows: u32,
}

impl Bounds {
    /// Zero counts of this size.
    fn empty(&self) -> FloorHeat {
        let len = usize::try_from(self.columns.saturating_mul(self.rows)).unwrap_or(0);
        FloorHeat {
            columns: self.columns,
            rows: self.rows,
            counts: vec![0; len],
        }
    }
}

/// Cells needed to cover `extent` metres (at most 1000).
fn cells(extent: f64) -> u32 {
    (0..1_000_u32)
        .find(|n| f64::from(*n) * HEAT_CELL_M >= extent)
        .unwrap_or(0)
}

/// The cell holding `offset` metres from the box edge, if inside `count` cells.
fn cell_of(offset: f64, count: u32) -> Option<u32> {
    if !offset.is_finite() || offset < 0.0 {
        return None;
    }
    (0..count).find(|n| f64::from(n.saturating_add(1)) * HEAT_CELL_M > offset)
}

#[async_trait]
impl StatsService for HeatMap {
    async fn heat(&self, floor: i32) -> Result<HeatView, ApiError> {
        let bounds = self
            .bounds(floor)
            .ok_or_else(|| ApiError::invalid_input("floor", "is not a floor of the active plan"))?;
        let counts = self
            .floors
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .get(&floor)
            .filter(|heat| heat.columns == bounds.columns && heat.rows == bounds.rows)
            .map_or_else(|| bounds.empty().counts, |heat| heat.counts.clone());
        Ok(HeatView {
            floor,
            cell_m: HEAT_CELL_M,
            origin: [bounds.min_x, bounds.min_y],
            columns: bounds.columns,
            rows: bounds.rows,
            counts,
        })
    }
}
