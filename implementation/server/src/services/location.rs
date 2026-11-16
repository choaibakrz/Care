//! Real `LocationService`, the position broadcaster, and the live-to-wire conversion.
//!
//! The broadcaster lives here because it joins `locations` and `realtime`, which do not
//! depend on each other.

use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use domain::{DeviceId, OwnerLabel, PlaceId};
use locations::{ClinicMap, LivePositions, LiveSnapshot, PositionEstimate, Positioner, TabletLive};
use realtime::{AppEvent, Hub, Positions, RobotPosition, TabletPosition};
use security::ClientIdentity;
use tokio::sync::Mutex;
use tokio::task::JoinHandle;

use super::LocationService;
use crate::dto::ScanBody;
use crate::error::ApiError;

/// The real location service.
pub struct LiveLocationService {
    map: Arc<ClinicMap>,
    live: Arc<LivePositions>,
    positioner: Mutex<Positioner>,
}

impl LiveLocationService {
    /// A service.
    #[must_use]
    pub fn new(
        map: Arc<ClinicMap>,
        live: Arc<LivePositions>,
        positioner: Positioner,
    ) -> LiveLocationService {
        LiveLocationService {
            map,
            live,
            positioner: Mutex::new(positioner),
        }
    }
}

/// The device and the owner label of a tablet caller.
fn device_and_owner(identity: &ClientIdentity) -> Result<(DeviceId, OwnerLabel), ApiError> {
    let device = identity
        .verified
        .device_id
        .clone()
        .ok_or_else(ApiError::device_required)?;
    let owner = match identity.verified.owner.clone() {
        Some(owner) => owner,
        None => OwnerLabel::new("Tablet")?,
    };
    Ok((device, owner))
}

#[async_trait]
impl LocationService for LiveLocationService {
    async fn live(&self) -> Result<LiveSnapshot, ApiError> {
        Ok(self.live.snapshot())
    }

    async fn set_my_location(
        &self,
        identity: &ClientIdentity,
        place: &PlaceId,
    ) -> Result<TabletLive, ApiError> {
        let (device, owner) = device_and_owner(identity)?;
        self.live.set_tablet(device.clone(), owner, place)?;
        let (place, floor) = self
            .live
            .tablet_place(&device)
            .ok_or_else(|| ApiError::internal("tablet position"))?;
        self.positioner
            .lock()
            .await
            .set_manual(&device, place, floor, self.live.now());
        self.live
            .snapshot()
            .tablets
            .into_iter()
            .find(|tablet| tablet.device_id == device)
            .ok_or_else(|| ApiError::internal("tablet position"))
    }

    async fn ingest_scan(
        &self,
        identity: &ClientIdentity,
        scan: ScanBody,
    ) -> Result<PositionEstimate, ApiError> {
        let (device, owner) = device_and_owner(identity)?;
        let estimate = self
            .positioner
            .lock()
            .await
            .ingest(scan.into_report(device.clone()))?;
        if self.map.floor(estimate.floor).is_some() {
            self.live.set_tablet_estimate(device, owner, &estimate)?;
        }
        Ok(estimate)
    }
}

/// Publishes `positions.delta` with only the subjects that changed, coalesced.
pub struct PositionBroadcaster;

impl PositionBroadcaster {
    /// Starts publishing every `interval` (200 ms).
    #[must_use]
    pub fn spawn(live: Arc<LivePositions>, hub: Arc<Hub>, interval: Duration) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(interval);
            ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            let mut previous = Positions {
                robots: Vec::new(),
                tablets: Vec::new(),
                map_version: String::new(),
                at: live.now(),
            };
            loop {
                ticker.tick().await;
                let current = to_wire_positions(&live.snapshot());
                if let Some(delta) = delta(&previous, &current) {
                    hub.publish(delta);
                }
                previous = current;
            }
        })
    }
}

/// The `positions.delta` between two snapshots, `None` when nothing changed.
fn delta(previous: &Positions, current: &Positions) -> Option<AppEvent> {
    let robots: Vec<RobotPosition> = current
        .robots
        .iter()
        .filter(|robot| !previous.robots.contains(robot))
        .cloned()
        .collect();
    let tablets: Vec<TabletPosition> = current
        .tablets
        .iter()
        .filter(|tablet| !previous.tablets.contains(tablet))
        .cloned()
        .collect();
    let removed_tablets: Vec<DeviceId> = previous
        .tablets
        .iter()
        .filter(|old| {
            !current
                .tablets
                .iter()
                .any(|tablet| tablet.device_id == old.device_id)
        })
        .map(|old| old.device_id.clone())
        .collect();
    if robots.is_empty() && tablets.is_empty() && removed_tablets.is_empty() {
        return None;
    }
    Some(AppEvent::PositionsDelta {
        robots,
        tablets,
        removed_tablets,
    })
}

/// The wire form of a snapshot (tablets keep only owner label and room).
#[must_use]
pub fn to_wire_positions(snapshot: &LiveSnapshot) -> Positions {
    Positions {
        robots: snapshot
            .robots
            .iter()
            .map(|robot| RobotPosition {
                id: robot.id.clone(),
                name: robot.name.clone(),
                status: robot.status,
                task: robot.task.clone(),
                battery_pct: robot.battery_pct,
                mic_open: robot.mic_open,
                floor: robot.floor,
                x: robot.point.x(),
                y: robot.point.y(),
                heading_rad: robot.heading_rad,
                stale: robot.stale,
            })
            .collect(),
        // Owner label and room only: nothing else about a person leaves the server.
        tablets: snapshot
            .tablets
            .iter()
            .map(|tablet| TabletPosition {
                device_id: tablet.device_id.clone(),
                owner: tablet.owner.clone(),
                place: tablet.place.clone(),
                floor: tablet.floor,
                x: tablet.point.x(),
                y: tablet.point.y(),
                uncertainty_m: tablet.uncertainty_m,
            })
            .collect(),
        map_version: snapshot.map_version.as_str().to_owned(),
        at: snapshot.at,
    }
}
