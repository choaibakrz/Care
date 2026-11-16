//! The 3D model of the clinic, live positions of robots and tablets, the privacy filter,
//! incident attribution, and indoor positioning without beacons.
//!
//! Coordinates: metres, x grows east, y grows south (top-down screen view, as the admin
//! console draws it), z up, per-floor `elevation_m`; a heading is 0 = east, positive toward
//! south. See `docs/map-format.md`. The 2D maths does not depend on the orientation.

pub mod attribution;
pub mod error;
pub mod geometry;
pub mod grid;
pub mod live;
pub mod loader;
pub mod model;
pub mod plan;
pub mod positioning;
pub mod privacy;
pub mod snapshot;
pub mod validate;
pub mod view;

pub use attribution::Attribution;
pub use domain::{SubjectRef, ZoneKind};
pub use error::LocationError;
pub use geometry::{Point2, Polygon, Wall};
pub use grid::{Disc, GridCell, PlanningGrid};
pub use live::{LivePositions, PositionFix, PositionTtl, RobotInfo};
pub use loader::{load_plan, parse_plan};
pub use model::{
    ClinicMap, Floor, MapVersion, Obstacle, ObstacleKind, Place, PlaceKind, PlaceLink, Zone,
};
pub use plan::{
    ActiveMap, ActivePlan, ClinicPlan, MapPoint, OverlayRemove, OverlayUpsert, PlaceViewKind,
    PlanConnection, PlanErrors, PlanFloor, PlanOverlay, PlanPlace, PlanProblem, PlanProp, PlanRoom,
    PlanWall, PropKind, RoomKind,
};
pub use positioning::{
    Method, PositionEstimate, Positioner, PositionerConfig, PositioningError, ScanReport,
};
pub use snapshot::{LiveSnapshot, RobotLive, TabletLive};
pub use view::MapView;

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
