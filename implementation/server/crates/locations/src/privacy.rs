//! The privacy filter for tablets: a person is shown at the room's anchor point unless the
//! estimate is precise (uncertainty at most 3 m). Nothing else about a person leaves memory.

use crate::geometry::Point2;

/// Largest uncertainty for which the exact estimated point may be shown.
pub const EXACT_POINT_MAX_UNCERTAINTY_M: f64 = 3.0;

/// Fields that must never be logged when they refer to a tablet.
pub const TABLET_SENSITIVE_FIELDS: &[&str] = &["rssi", "point", "position", "place"];

/// The point to show for a tablet.
#[must_use]
pub fn public_point(room_anchor: Point2, estimate: Point2, uncertainty_m: Option<f64>) -> Point2 {
    match uncertainty_m {
        Some(radius) if radius <= EXACT_POINT_MAX_UNCERTAINTY_M => estimate,
        _ => room_anchor,
    }
}
