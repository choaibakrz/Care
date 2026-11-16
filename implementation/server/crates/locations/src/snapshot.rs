//! What the outside sees of live positions.

use chrono::{DateTime, Utc};
use domain::{DeviceId, OwnerLabel, PlaceId, RobotId, RobotStatus, TaskSummary};
use serde::Serialize;
use utoipa::ToSchema;

use crate::geometry::Point2;
use crate::model::MapVersion;

/// A robot on the map.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct RobotLive {
    /// Id.
    pub id: RobotId,
    /// Name.
    pub name: String,
    /// Status.
    pub status: RobotStatus,
    /// Current task.
    pub task: Option<TaskSummary>,
    /// Battery.
    pub battery_pct: f32,
    /// Microphone open.
    pub mic_open: bool,
    /// Floor.
    pub floor: i32,
    /// Position.
    pub point: Point2,
    /// Heading.
    pub heading_rad: Option<f64>,
    /// No fix within `robot_stale`.
    pub stale: bool,
}

/// A tablet on the map. **No other field exists, so privacy holds by construction.**
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct TabletLive {
    /// Device.
    pub device_id: DeviceId,
    /// Owner label.
    pub owner: OwnerLabel,
    /// Room.
    pub place: PlaceId,
    /// Floor.
    pub floor: i32,
    /// The room anchor, or the estimate when `uncertainty_m <= 3`.
    pub point: Point2,
    /// `None` when the room was chosen by hand.
    pub uncertainty_m: Option<f64>,
}

/// Every live position at one instant.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct LiveSnapshot {
    /// Robots.
    pub robots: Vec<RobotLive>,
    /// Tablets (expired ones pruned).
    pub tablets: Vec<TabletLive>,
    /// Map version.
    pub map_version: MapVersion,
    /// When taken.
    pub at: DateTime<Utc>,
}
