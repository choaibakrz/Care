//! Errors of the optimisation crate.

use domain::PlaceId;

/// Planning and loading errors.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum OptimizationError {
    /// Too many stops for one tour.
    #[error("A tour can have at most {max} stops; {given} were given. Split the round.")]
    TooManyStops {
        /// Stops given.
        given: usize,
        /// Limit.
        max: usize,
    },
    /// A place not on the routing graph.
    #[error("Place '{place}' is not on the routing graph; check the map links.")]
    UnknownPlace {
        /// The place.
        place: PlaceId,
    },
    /// No robot in the fleet.
    #[error("No robot is available to plan for; connect a robot or hand the round to a human.")]
    EmptyFleet,
    /// The role cards file is invalid.
    #[error("The role cards could not be loaded ({reason}); check seed/role_cards.json.")]
    RoleCards {
        /// Why.
        reason: String,
    },
    /// An external oracle failed (Python bridge).
    #[error("The dispatch oracle failed ({detail}); the native dispatcher is the reference.")]
    Oracle {
        /// Why (no file system paths).
        detail: String,
    },
}
