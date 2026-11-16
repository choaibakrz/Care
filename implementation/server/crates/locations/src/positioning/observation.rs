//! Anchors, observations and scan reports.

use chrono::{DateTime, Utc};
use domain::{DeviceId, RobotId};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use super::{MAX_FUTURE, MAX_OBSERVATIONS, MAX_STEPS_PER_SECOND, MIN_RSSI_DBM, PositioningError};
use crate::geometry::Point2;

/// Id of an anchor as advertised over BLE.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema)]
#[serde(transparent)]
pub struct AnchorId(pub String);

/// What an anchor is.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AnchorKind {
    /// A robot (moving; used only while its fix is under 1 s old and not stale).
    Robot(RobotId),
    /// A fixed device registered with its place.
    FixedDevice(DeviceId),
    /// An optional BLE beacon.
    Beacon,
    /// Another tablet (uncertain anchor).
    Tablet(DeviceId),
}

/// A transmitter of known (or estimated) position.
#[derive(Debug, Clone, PartialEq)]
pub struct Anchor {
    /// Id.
    pub id: AnchorId,
    /// Kind.
    pub kind: AnchorKind,
    /// Floor.
    pub floor: i32,
    /// Position.
    pub point: Point2,
    /// Position uncertainty; 0 for known positions.
    pub spread_m: f64,
    /// RSSI at 1 m.
    pub tx_power_dbm_1m: f64,
}

/// One measurement in a scan.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Observation {
    /// Received signal strength.
    Rssi {
        /// Anchor.
        anchor: AnchorId,
        /// dBm, −110 to 0.
        dbm: i16,
    },
    /// A ranging radio distance (UWB, Channel Sounding).
    Range {
        /// Anchor.
        anchor: AnchorId,
        /// Distance.
        metres: f64,
        /// Standard deviation.
        sigma_m: f64,
    },
}

/// Pedestrian dead reckoning since the previous scan.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct MotionDelta {
    /// Steps.
    pub steps: u32,
    /// Heading.
    pub heading_rad: f64,
    /// Heading uncertainty.
    pub heading_sigma_rad: f64,
    /// Stride length.
    pub stride_m: f64,
}

/// One scan from a tablet (about 1 Hz).
#[derive(Debug, Clone, PartialEq)]
pub struct ScanReport {
    /// Device (from the caller's identity, never from the body).
    pub device: DeviceId,
    /// When scanned.
    pub at: DateTime<Utc>,
    /// Observations (at most 64).
    pub observations: Vec<Observation>,
    /// Motion since the previous scan.
    pub motion: Option<MotionDelta>,
    /// Air pressure (floor hint).
    pub pressure_hpa: Option<f64>,
}

impl ScanReport {
    /// Checks the limits: RSSI −110..0, at most 64 observations, `at` at most 2 s ahead,
    /// at most 10 steps per second since `previous_at`.
    ///
    /// # Errors
    /// The matching `PositioningError`.
    pub fn validate(
        &self,
        now: DateTime<Utc>,
        previous_at: Option<DateTime<Utc>>,
    ) -> Result<(), PositioningError> {
        if self.observations.len() > MAX_OBSERVATIONS {
            return Err(PositioningError::TooManyObservations {
                count: self.observations.len(),
                max: MAX_OBSERVATIONS,
            });
        }
        for observation in &self.observations {
            match observation {
                Observation::Rssi { dbm, .. } => {
                    if !(MIN_RSSI_DBM..=0).contains(dbm) {
                        return Err(PositioningError::RssiOutOfRange { dbm: *dbm });
                    }
                }
                Observation::Range {
                    metres, sigma_m, ..
                } => {
                    let valid = metres.is_finite()
                        && *metres >= 0.0
                        && sigma_m.is_finite()
                        && *sigma_m > 0.0;
                    if !valid {
                        return Err(PositioningError::BadRange);
                    }
                }
            }
        }
        let ahead = self.at.signed_duration_since(now);
        let limit = chrono::TimeDelta::from_std(MAX_FUTURE).unwrap_or(chrono::TimeDelta::zero());
        if ahead > limit {
            return Err(PositioningError::FromTheFuture {
                ahead_ms: ahead.num_milliseconds(),
            });
        }
        if let (Some(motion), Some(previous)) = (self.motion, previous_at) {
            #[allow(clippy::cast_precision_loss)]
            let elapsed_s =
                self.at.signed_duration_since(previous).num_milliseconds() as f64 / 1000.0;
            if elapsed_s > 0.0 {
                let steps_per_s = f64::from(motion.steps) / elapsed_s;
                if steps_per_s > MAX_STEPS_PER_SECOND {
                    return Err(PositioningError::TooManySteps { steps_per_s });
                }
            }
        }
        Ok(())
    }
}
