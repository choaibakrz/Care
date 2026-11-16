//! Live positions of robots and tablets, in memory only.

use std::collections::HashMap;
use std::sync::{Arc, PoisonError, RwLock};
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::{Clock, DeviceId, OwnerLabel, PlaceId, RobotId, RobotStatus, SubjectRef, TaskSummary};

use crate::error::LocationError;
use crate::geometry::Point2;
use crate::model::ClinicMap;
use crate::positioning::PositionEstimate;
use crate::positioning::observation::{Anchor, AnchorId, AnchorKind};
use crate::positioning::room_tracker::MANUAL_OVERRIDE;
use crate::privacy::public_point;
use crate::snapshot::{LiveSnapshot, RobotLive, TabletLive};

/// A robot fix younger than this makes the robot a positioning anchor.
pub const ROBOT_ANCHOR_MAX_AGE: Duration = Duration::from_secs(1);
/// RSSI at 1 m assumed for robots and tablets used as anchors.
pub const DEFAULT_TX_POWER_DBM_1M: f64 = -59.0;

/// `now - at`, or `None` when it does not fit a `TimeDelta` comparison.
fn age_over(now: DateTime<Utc>, at: DateTime<Utc>, limit: Duration) -> bool {
    chrono::TimeDelta::from_std(limit).is_ok_and(|limit| now.signed_duration_since(at) > limit)
}

/// `true` when `at` is less than `limit` before `now` (and not in the future).
fn age_under(now: DateTime<Utc>, at: DateTime<Utc>, limit: Duration) -> bool {
    let age = now.signed_duration_since(at);
    chrono::TimeDelta::from_std(limit)
        .is_ok_and(|limit| age >= chrono::TimeDelta::zero() && age < limit)
}

/// One position measurement.
#[derive(Debug, Clone, PartialEq)]
pub struct PositionFix {
    /// Robot or tablet.
    pub subject: SubjectRef,
    /// Floor.
    pub floor: i32,
    /// Point.
    pub point: Point2,
    /// Heading.
    pub heading_rad: Option<f64>,
    /// When measured.
    pub at: DateTime<Utc>,
}

/// Expiry rules.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PositionTtl {
    /// A robot fix older than this is shown `stale` (default 5 s).
    pub robot_stale: Duration,
    /// A tablet entry older than this is removed (default 120 s).
    pub tablet_expiry: Duration,
}

impl Default for PositionTtl {
    fn default() -> Self {
        PositionTtl {
            robot_stale: Duration::from_secs(5),
            tablet_expiry: Duration::from_mins(2),
        }
    }
}

/// What a robot is doing, shown next to it.
#[derive(Debug, Clone, PartialEq)]
pub struct RobotInfo {
    /// Display name (from the robot table).
    pub name: String,
    /// Status.
    pub status: RobotStatus,
    /// Current task.
    pub task: Option<TaskSummary>,
    /// Battery.
    pub battery_pct: f32,
    /// Microphone open.
    pub mic_open: bool,
}

#[derive(Debug, Clone)]
struct RobotEntry {
    fix: PositionFix,
    info: RobotInfo,
}

#[derive(Debug, Clone)]
struct TabletEntry {
    owner: OwnerLabel,
    place: PlaceId,
    floor: i32,
    point: Point2,
    uncertainty_m: Option<f64>,
    updated_at: DateTime<Utc>,
    /// A manual pick or QR scan overrides Bluetooth until then (5 min).
    manual_until: Option<DateTime<Utc>>,
}

/// The live position store.
pub struct LivePositions {
    map: Arc<ClinicMap>,
    clock: Arc<dyn Clock>,
    ttl: PositionTtl,
    robots: RwLock<HashMap<RobotId, RobotEntry>>,
    tablets: RwLock<HashMap<DeviceId, TabletEntry>>,
}

impl LivePositions {
    /// An empty store.
    #[must_use]
    pub fn new(map: Arc<ClinicMap>, clock: Arc<dyn Clock>, ttl: PositionTtl) -> LivePositions {
        LivePositions {
            map,
            clock,
            ttl,
            robots: RwLock::new(HashMap::new()),
            tablets: RwLock::new(HashMap::new()),
        }
    }

    /// Records a robot fix.
    ///
    /// # Errors
    /// `UnknownFloor`; `PositionOutOfMap` when outside the floor outline.
    pub fn update_robot(&self, fix: PositionFix, info: RobotInfo) -> Result<(), LocationError> {
        if fix.heading_rad.is_some_and(|heading| !heading.is_finite()) {
            return Err(LocationError::NonFinite { what: "heading" });
        }
        let SubjectRef::Robot(robot) = fix.subject.clone() else {
            return Err(LocationError::NonFinite {
                what: "robot fix (its subject is a tablet)",
            });
        };
        let floor = self
            .map
            .floor(fix.floor)
            .ok_or(LocationError::UnknownFloor { floor: fix.floor })?;
        if !floor.outline.contains(&fix.point) {
            return Err(LocationError::PositionOutOfMap {
                robot,
                floor: fix.floor,
            });
        }
        self.robots
            .write()
            .unwrap_or_else(PoisonError::into_inner)
            .insert(robot, RobotEntry { fix, info });
        Ok(())
    }

    /// Updates only the robot's status fields (no position change).
    pub fn update_robot_info(&self, robot: &RobotId, info: RobotInfo) {
        if let Some(entry) = self
            .robots
            .write()
            .unwrap_or_else(PoisonError::into_inner)
            .get_mut(robot)
        {
            entry.info = info;
        }
    }

    /// Removes a robot (it stays on the map as offline through its status instead, if known).
    pub fn remove_robot(&self, robot: &RobotId) {
        self.robots
            .write()
            .unwrap_or_else(PoisonError::into_inner)
            .remove(robot);
    }

    /// The latest fix of a robot (anchors, attribution).
    #[must_use]
    pub fn robot_fix(&self, robot: &RobotId) -> Option<PositionFix> {
        self.robots
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .get(robot)
            .map(|entry| entry.fix.clone())
    }

    /// Sets a tablet's room by hand or QR: the position is the room's anchor.
    ///
    /// # Errors
    /// `UnknownPlace` with suggestions.
    pub fn set_tablet(
        &self,
        device: DeviceId,
        owner: OwnerLabel,
        place: &PlaceId,
    ) -> Result<(), LocationError> {
        let now = self.clock.now();
        let known_floor = self
            .tablets
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .get(&device)
            .map(|entry| entry.floor);
        let suggestion_floor = known_floor
            .or_else(|| self.map.floors().first().map(|floor| floor.level))
            .unwrap_or(0);
        let found = self
            .map
            .place(place)
            .ok_or_else(|| self.map.unknown_place_error(place, suggestion_floor))?;
        let manual_until = chrono::TimeDelta::from_std(MANUAL_OVERRIDE)
            .ok()
            .map(|span| now + span);
        let entry = TabletEntry {
            owner,
            place: found.id.clone(),
            floor: found.floor,
            point: found.anchor,
            uncertainty_m: None,
            updated_at: now,
            manual_until,
        };
        self.tablets
            .write()
            .unwrap_or_else(PoisonError::into_inner)
            .insert(device, entry);
        Ok(())
    }

    /// Sets a tablet's estimate from Bluetooth positioning, unless a manual pick is active.
    ///
    /// # Errors
    /// `UnknownPlace`; `UnknownFloor`.
    pub fn set_tablet_estimate(
        &self,
        device: DeviceId,
        owner: OwnerLabel,
        estimate: &PositionEstimate,
    ) -> Result<(), LocationError> {
        let now = self.clock.now();
        let mut tablets = self.tablets.write().unwrap_or_else(PoisonError::into_inner);
        if let Some(entry) = tablets.get_mut(&device)
            && entry.manual_until.is_some_and(|until| now < until)
        {
            // A manual pick wins: the radio estimate only keeps the entry alive.
            entry.updated_at = now;
            return Ok(());
        }
        if self.map.floor(estimate.floor).is_none() {
            return Err(LocationError::UnknownFloor {
                floor: estimate.floor,
            });
        }
        let place = self.map.place(&estimate.place).ok_or_else(|| {
            self.map
                .unknown_place_error(&estimate.place, estimate.floor)
        })?;
        let point = public_point(place.anchor, estimate.point, Some(estimate.uncertainty_m));
        tablets.insert(
            device,
            TabletEntry {
                owner,
                place: place.id.clone(),
                floor: place.floor,
                point,
                uncertainty_m: Some(estimate.uncertainty_m),
                updated_at: now,
                manual_until: None,
            },
        );
        Ok(())
    }

    /// The room and floor of a tablet.
    #[must_use]
    pub fn tablet_place(&self, device: &DeviceId) -> Option<(PlaceId, i32)> {
        self.tablets
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .get(device)
            .map(|entry| (entry.place.clone(), entry.floor))
    }

    /// Everything, pruning expired tablets and marking stale robots.
    #[must_use]
    pub fn snapshot(&self) -> LiveSnapshot {
        let now = self.clock.now();
        let mut robots: Vec<RobotLive> = self
            .robots
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .iter()
            .map(|(id, entry)| RobotLive {
                id: id.clone(),
                name: entry.info.name.clone(),
                status: entry.info.status,
                task: entry.info.task.clone(),
                battery_pct: entry.info.battery_pct,
                mic_open: entry.info.mic_open,
                floor: entry.fix.floor,
                point: entry.fix.point,
                heading_rad: entry.fix.heading_rad,
                stale: age_over(now, entry.fix.at, self.ttl.robot_stale),
            })
            .collect();
        robots.sort_by(|a, b| a.id.as_str().cmp(b.id.as_str()));
        let mut guard = self.tablets.write().unwrap_or_else(PoisonError::into_inner);
        guard.retain(|_, entry| !age_over(now, entry.updated_at, self.ttl.tablet_expiry));
        let mut tablets: Vec<TabletLive> = guard
            .iter()
            .map(|(device, entry)| TabletLive {
                device_id: device.clone(),
                owner: entry.owner.clone(),
                place: entry.place.clone(),
                floor: entry.floor,
                point: entry.point,
                uncertainty_m: entry.uncertainty_m,
            })
            .collect();
        drop(guard);
        tablets.sort_by(|a, b| a.device_id.as_str().cmp(b.device_id.as_str()));
        LiveSnapshot {
            robots,
            tablets,
            map_version: self.map.version(),
            at: now,
        }
    }

    /// The map.
    #[must_use]
    pub fn map(&self) -> &Arc<ClinicMap> {
        &self.map
    }

    /// The current time of the store's clock.
    #[must_use]
    pub fn now(&self) -> DateTime<Utc> {
        self.clock.now()
    }

    /// Positioning anchors: robots whose fix is under 1 s old, and tablets with a radio
    /// estimate (`AnchorId` = robot id or device id). `exclude` (the scanning tablet) is left
    /// out.
    #[must_use]
    pub fn anchors(&self, exclude: &DeviceId) -> Vec<Anchor> {
        let now = self.clock.now();
        let mut anchors: Vec<Anchor> = self
            .robots
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .iter()
            .filter(|(_, entry)| age_under(now, entry.fix.at, ROBOT_ANCHOR_MAX_AGE))
            .map(|(id, entry)| Anchor {
                id: AnchorId(id.as_str().to_owned()),
                kind: AnchorKind::Robot(id.clone()),
                floor: entry.fix.floor,
                point: entry.fix.point,
                spread_m: 0.0,
                tx_power_dbm_1m: DEFAULT_TX_POWER_DBM_1M,
            })
            .collect();
        let tablets = self.tablets.read().unwrap_or_else(PoisonError::into_inner);
        for (device, entry) in tablets.iter() {
            if device == exclude || age_over(now, entry.updated_at, self.ttl.tablet_expiry) {
                continue;
            }
            if let Some(spread) = entry.uncertainty_m {
                anchors.push(Anchor {
                    id: AnchorId(device.as_str().to_owned()),
                    kind: AnchorKind::Tablet(device.clone()),
                    floor: entry.floor,
                    point: entry.point,
                    spread_m: spread,
                    tx_power_dbm_1m: DEFAULT_TX_POWER_DBM_1M,
                });
            }
        }
        anchors.sort_by(|a, b| a.id.cmp(&b.id));
        anchors
    }
}
