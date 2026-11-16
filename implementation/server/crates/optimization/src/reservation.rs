//! Space-time reservations (P2).
//!
//! Scope: this plans around other robots on the server side. It does **not** replace each
//! robot's own obstacle avoidance or the gardien. Physical safety stays on the robot.

use std::sync::{Arc, Mutex, PoisonError};

use chrono::{DateTime, Utc};
use domain::{Clock, PlaceId, RobotId};

use crate::graph::Path;

/// A place or an edge between two places.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum PlaceOrEdge {
    /// A place.
    Place(PlaceId),
    /// An edge (unordered).
    Edge(PlaceId, PlaceId),
}

/// A conflict with another robot's reservation.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error("Robot {with} has reserved {at:?} between {} and {}; start later.", window.0, window.1)]
pub struct Conflict {
    /// Other robot.
    pub with: RobotId,
    /// Where.
    pub at: PlaceOrEdge,
    /// When.
    pub window: (DateTime<Utc>, DateTime<Utc>),
}

#[derive(Debug, Clone)]
struct Slot {
    robot: RobotId,
    at: PlaceOrEdge,
    window: (DateTime<Utc>, DateTime<Utc>),
}

/// The reservation table.
pub struct ReservationTable {
    clock: Arc<dyn Clock>,
    slots: Mutex<Vec<Slot>>,
}

impl ReservationTable {
    /// Empty.
    #[must_use]
    pub fn new(clock: Arc<dyn Clock>) -> ReservationTable {
        ReservationTable {
            clock,
            slots: Mutex::new(Vec::new()),
        }
    }

    /// Reserves every place and edge of `path` for the time the robot needs.
    ///
    /// # Errors
    /// `Conflict` with the first overlapping slot.
    pub fn try_reserve(
        &self,
        robot: &RobotId,
        path: &Path,
        start: DateTime<Utc>,
        speed_m_s: f64,
    ) -> Result<(), Conflict> {
        let mine = windows(path, start, speed_m_s);
        let now = self.clock.now();
        let mut slots = self.slots.lock().unwrap_or_else(PoisonError::into_inner);
        slots.retain(|slot| slot.window.1 > now);
        for (at, window) in &mine {
            if let Some(other) = first_conflict(&slots, robot, at, *window) {
                return Err(Conflict {
                    with: other.robot.clone(),
                    at: other.at.clone(),
                    window: other.window,
                });
            }
        }
        slots.extend(mine.into_iter().map(|(at, window)| Slot {
            robot: robot.clone(),
            at,
            window,
        }));
        Ok(())
    }

    /// The earliest start at or after `not_before` with no conflict.
    #[must_use]
    pub fn earliest_start(
        &self,
        robot: &RobotId,
        path: &Path,
        not_before: DateTime<Utc>,
        speed_m_s: f64,
    ) -> DateTime<Utc> {
        let slots = self.slots.lock().unwrap_or_else(PoisonError::into_inner);
        let mut start = not_before;
        // Each round moves the start past at least one conflicting slot; the bound only
        // guards against a pathological table.
        for _ in 0..10_000 {
            let mut later = start;
            for (at, window) in windows(path, start, speed_m_s) {
                if let Some(other) = first_conflict(&slots, robot, &at, window) {
                    let shifted = start + (other.window.1 - window.0);
                    later = later.max(shifted);
                }
            }
            if later == start {
                return start;
            }
            start = later;
        }
        start
    }

    /// Drops every slot of a robot.
    pub fn release(&self, robot: &RobotId) {
        let mut slots = self.slots.lock().unwrap_or_else(PoisonError::into_inner);
        slots.retain(|slot| slot.robot != *robot);
    }
}

/// A time window, start inclusive, end exclusive.
type Window = (DateTime<Utc>, DateTime<Utc>);

/// The first slot of another robot at `at` whose window overlaps `window` (half-open).
fn first_conflict<'a>(
    slots: &'a [Slot],
    robot: &RobotId,
    at: &PlaceOrEdge,
    window: Window,
) -> Option<&'a Slot> {
    slots.iter().find(|slot| {
        slot.robot != *robot
            && slot.at == *at
            && slot.window.0 < window.1
            && window.0 < slot.window.1
    })
}

/// Seconds as a chrono duration (zero when not representable).
fn seconds(secs: f64) -> chrono::Duration {
    std::time::Duration::try_from_secs_f64(secs)
        .ok()
        .and_then(|d| chrono::Duration::from_std(d).ok())
        .unwrap_or_else(chrono::Duration::zero)
}

/// The windows a robot needs along `path` from `start`: places are spread evenly along the
/// path's length; a place is held from the arrival at the previous place to the arrival at the
/// next one, an edge while it is driven.
fn windows(path: &Path, start: DateTime<Utc>, speed_m_s: f64) -> Vec<(PlaceOrEdge, Window)> {
    let speed = if speed_m_s.is_finite() && speed_m_s > 0.01 {
        speed_m_s
    } else {
        0.01
    };
    let legs = path.places.len().saturating_sub(1);
    let leg_secs = if legs == 0 {
        0.0
    } else {
        path.metres.max(0.0) / f64::from(u32::try_from(legs).unwrap_or(u32::MAX)) / speed
    };
    let mut arrivals = Vec::with_capacity(path.places.len());
    let mut elapsed = 0.0;
    for _ in &path.places {
        arrivals.push(start + seconds(elapsed));
        elapsed += leg_secs;
    }
    let mut out = Vec::new();
    for (index, place) in path.places.iter().enumerate() {
        let Some(at) = arrivals.get(index).copied() else {
            continue;
        };
        let lo = index
            .checked_sub(1)
            .and_then(|before| arrivals.get(before))
            .copied()
            .unwrap_or(at);
        let mut hi = arrivals.get(index + 1).copied().unwrap_or(at);
        if hi <= lo {
            hi = lo + chrono::Duration::seconds(1);
        }
        out.push((PlaceOrEdge::Place(place.clone()), (lo, hi)));
    }
    for (index, pair) in path.places.windows(2).enumerate() {
        let [a, b] = pair else { continue };
        let (Some(lo), Some(hi)) = (arrivals.get(index), arrivals.get(index + 1)) else {
            continue;
        };
        let edge = if a <= b {
            PlaceOrEdge::Edge(a.clone(), b.clone())
        } else {
            PlaceOrEdge::Edge(b.clone(), a.clone())
        };
        let hi = if hi <= lo {
            *lo + chrono::Duration::seconds(1)
        } else {
            *hi
        };
        out.push((edge, (*lo, hi)));
    }
    out
}
