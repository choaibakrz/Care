//! Which zone version each robot has acknowledged (Task 16).

use std::collections::HashMap;
use std::sync::Mutex;

use domain::{RobotId, ZoneId, ZoneVersions};
use serde::Serialize;
use utoipa::ToSchema;

/// Delivery state of one zone to one robot (wire spellings as the admin console reads them).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum DeliveryState {
    /// The robot acknowledged the current version.
    Received,
    /// Not acknowledged yet: sent and waiting, or the robot is offline and receives the list
    /// on reconnect (`robot_online: false` tells the two apart).
    Pending,
    /// The robot is connected but the current list could not be queued to it
    /// (see [`ZoneDelivery::record_send_failed`]).
    Failed,
}

/// One line of `GET /zones` `deliveries`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct ZoneDeliveryEntry {
    /// Robot.
    pub robot_id: domain::RobotId,
    /// State.
    pub status: DeliveryState,
    /// Last version it acknowledged (extra field).
    pub acked_version: Option<u32>,
    /// Whether the robot is connected now (extra field).
    pub robot_online: bool,
}

/// Acknowledged versions per robot, and failed sends.
#[derive(Debug, Default)]
pub struct ZoneDelivery {
    acked: Mutex<HashMap<RobotId, ZoneVersions>>,
    failed: Mutex<HashMap<RobotId, u64>>,
}

impl ZoneDelivery {
    /// Empty.
    #[must_use]
    pub fn new() -> ZoneDelivery {
        ZoneDelivery::default()
    }

    /// Records a `zone.ack`.
    pub fn record_ack(&self, robot: &RobotId, versions: &ZoneVersions) {
        self.acked
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .insert(robot.clone(), versions.clone());
        self.failed
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .remove(robot);
    }

    /// Records that the zone list at global `version` could not be queued to `robot`.
    pub fn record_send_failed(&self, robot: &RobotId, version: u64) {
        self.failed
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .insert(robot.clone(), version);
    }

    /// Delivery lines for one zone at `version`, given each robot and whether it is online.
    #[must_use]
    pub fn entries_for(
        &self,
        zone: &ZoneId,
        version: u32,
        robots: &[(RobotId, bool)],
    ) -> Vec<ZoneDeliveryEntry> {
        let acked = self
            .acked
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let failed = self
            .failed
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        robots
            .iter()
            .map(|(robot, online)| {
                let acked_version = acked
                    .get(robot)
                    .and_then(|versions| versions.get(zone))
                    .copied();
                // The failed record holds the global list version; any failure not yet cleared by
                // an ack means the current list did not reach this robot.
                let status = if acked_version.is_some_and(|acked| acked >= version) {
                    DeliveryState::Received
                } else if *online && failed.contains_key(robot) {
                    DeliveryState::Failed
                } else {
                    DeliveryState::Pending
                };
                ZoneDeliveryEntry {
                    robot_id: robot.clone(),
                    status,
                    acked_version,
                    robot_online: *online,
                }
            })
            .collect()
    }
}
