//! Indoor positioning without beacons (Task 11b): robots as moving anchors, fixed devices,
//! optional beacons; RSSI smoothing, path-loss ranging, trilateration, a map-matched particle
//! filter, a fingerprint room classifier, and room hysteresis.
//!
//! Raw scans are processed in memory and dropped: never stored, journaled or logged.

pub mod fingerprint;
pub mod observation;
pub mod particle_filter;
pub mod path_loss;
pub mod positioner;
mod rng;
pub mod room_tracker;
pub mod simulate;
pub mod smoothing;
pub mod trilateration;
pub mod virtual_anchors;

use std::time::Duration;

pub use fingerprint::{FingerprintIndex, SurveySample};
pub use observation::{Anchor, AnchorId, AnchorKind, MotionDelta, Observation, ScanReport};
pub use particle_filter::{FilterEstimate, Particle, ParticleFilter};
pub use path_loss::PathLossModel;
pub use positioner::{Method, PositionEstimate, Positioner, PositionerConfig};
pub use room_tracker::RoomTracker;
pub use simulate::SyntheticScanner;
pub use smoothing::{RssiSmoother, SmootherBank};
pub use trilateration::{Estimate, Trilaterator, WeightedRange};
pub use virtual_anchors::{Identifiability, Line2, VirtualAnchors};

use crate::error::LocationError;

/// Positioning errors.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum PositioningError {
    /// Not enough anchors on the floor.
    #[error(
        "Only {have} anchors are in range; at least {need} are needed. The room is kept from the last estimate."
    )]
    TooFewAnchors {
        /// Anchors available.
        have: usize,
        /// Anchors needed.
        need: usize,
    },
    /// RSSI outside −110..0 dBm.
    #[error("Signal strength {dbm} dBm is outside -110 to 0 dBm; the scan was rejected.")]
    RssiOutOfRange {
        /// Value.
        dbm: i16,
    },
    /// Too many observations in one scan.
    #[error("A scan has {count} observations; at most {max} are accepted.")]
    TooManyObservations {
        /// Count.
        count: usize,
        /// Limit.
        max: usize,
    },
    /// Scan timestamp too far in the future.
    #[error(
        "The scan is dated {ahead_ms} ms in the future (more than 2 s); check the tablet clock."
    )]
    FromTheFuture {
        /// How far ahead.
        ahead_ms: i64,
    },
    /// Implausible step rate.
    #[error(
        "The scan reports {steps_per_s:.1} steps per second (at most 10); the motion was rejected."
    )]
    TooManySteps {
        /// Rate.
        steps_per_s: f64,
    },
    /// A range observation with a bad value.
    #[error("A range observation must have metres >= 0 and sigma > 0; the scan was rejected.")]
    BadRange,
    /// An observation names an anchor the server does not know.
    #[error("Anchor '{anchor}' is not known; it was ignored.")]
    UnknownAnchor {
        /// Anchor id.
        anchor: String,
    },
    /// The solver did not converge.
    #[error(
        "Trilateration did not converge after {iterations} iterations; the previous estimate is kept."
    )]
    Diverged {
        /// Iterations run.
        iterations: u32,
    },
    /// A seed file could not be loaded.
    #[error("Positioning seed data could not be loaded ({reason}).")]
    Seed {
        /// Why.
        reason: String,
    },
    /// A map error.
    #[error("Positioning failed on the map: {0}")]
    Map(#[from] LocationError),
}

/// Most observations accepted per scan.
pub const MAX_OBSERVATIONS: usize = 64;
/// Lowest accepted RSSI.
pub const MIN_RSSI_DBM: i16 = -110;
/// How far in the future a scan may be dated.
pub const MAX_FUTURE: Duration = Duration::from_secs(2);
/// Highest plausible step rate.
pub const MAX_STEPS_PER_SECOND: f64 = 10.0;
