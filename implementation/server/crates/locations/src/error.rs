//! Errors of the map model and of live positions.

use domain::{PlaceId, RobotId, ZoneId};

use crate::plan::PlanErrors;

/// Map validation and live-position errors. Tablet coordinates never appear in a message.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum LocationError {
    /// NaN or infinite coordinate.
    #[error(
        "The {what} has a coordinate that is not a finite number; use metres as plain numbers."
    )]
    NonFinite {
        /// What was being built.
        what: &'static str,
    },
    /// Fewer than three vertices.
    #[error("A polygon needs at least 3 vertices; this one has {have}.")]
    TooFewVertices {
        /// Vertices given.
        have: usize,
    },
    /// Zero area.
    #[error("The polygon has zero area (all vertices on one line); draw a real outline.")]
    ZeroArea,
    /// Edges cross.
    #[error("The polygon crosses itself (edges {edge_a} and {edge_b}); reorder the vertices.")]
    SelfIntersecting {
        /// First edge index.
        edge_a: usize,
        /// Second edge index.
        edge_b: usize,
    },
    /// Two consecutive equal vertices.
    #[error("Vertex {index} repeats the previous one; remove the duplicate.")]
    RepeatedPoint {
        /// Vertex index.
        index: usize,
    },
    /// The same id twice.
    #[error("The {kind} id '{id}' appears twice in the map; ids must be unique.")]
    DuplicateId {
        /// `place`, `zone` or `floor`.
        kind: &'static str,
        /// The id.
        id: String,
    },
    /// A floor level the map does not have.
    #[error("Floor {floor} is not on the map; check the floor number.")]
    UnknownFloor {
        /// Level.
        floor: i32,
    },
    /// A place the map does not have, with up to 10 suggestions from the same floor.
    #[error("Place '{place}' is not on the map. Places on floor {floor} include: {suggestions}.")]
    UnknownPlace {
        /// The place.
        place: PlaceId,
        /// Floor used for suggestions.
        floor: i32,
        /// Comma-separated list, capped at 10.
        suggestions: String,
    },
    /// A place footprint outside its floor outline.
    #[error("Place '{place}' is not inside the outline of floor {floor}; fix its footprint.")]
    PlaceOutsideFloor {
        /// Place.
        place: PlaceId,
        /// Floor.
        floor: i32,
    },
    /// An invalid link.
    #[error("The link from '{from}' to '{to}' is invalid: {reason}.")]
    BadLink {
        /// From.
        from: PlaceId,
        /// To.
        to: PlaceId,
        /// Why (unknown place, metres <= 0).
        reason: &'static str,
    },
    /// A zone outside its floor.
    #[error("Zone '{zone}' is not inside the outline of floor {floor}; redraw it on the floor.")]
    ZoneOutsideFloor {
        /// Zone.
        zone: ZoneId,
        /// Floor.
        floor: i32,
    },
    /// A robot fix outside the floor outline.
    #[error(
        "Robot {robot} reported a position outside floor {floor}; the fix was ignored. Check the robot's localisation."
    )]
    PositionOutOfMap {
        /// Robot.
        robot: RobotId,
        /// Floor.
        floor: i32,
    },
    /// A clinic plan was refused; every problem is listed (Task A4).
    #[error("{0}")]
    InvalidPlan(#[from] PlanErrors),
    /// The map file could not be read or parsed.
    #[error("The map file could not be loaded ({reason}); see docs/map-format.md.")]
    MapFile {
        /// Why.
        reason: String,
    },
}
