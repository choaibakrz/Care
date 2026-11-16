//! Synthetic scans along a true path through the seed map: log-normal noise (σ = 4 dB) and
//! 5 dB per wall crossed, so positioning is testable without hardware.

use std::sync::Arc;

use chrono::{DateTime, Utc};
use domain::DeviceId;

use super::MIN_RSSI_DBM;
use super::observation::{Anchor, MotionDelta, Observation, ScanReport};
use super::path_loss::PathLossModel;
use super::rng::SplitMix64;
use crate::geometry::Point2;
use crate::model::ClinicMap;

/// Loss per wall crossed.
pub const WALL_LOSS_DB: f64 = 5.0;
/// Walking speed of [`SyntheticScanner::walk`], metres per second (a slow ward pace).
pub const WALK_SPEED_M_S: f64 = 0.5;
/// Heading uncertainty reported with the synthetic PDR, radians.
const PDR_HEADING_SIGMA_RAD: f64 = 0.05;

/// Generates scans. Deterministic for a given seed.
#[derive(Debug, Clone)]
pub struct SyntheticScanner {
    map: Arc<ClinicMap>,
    anchors: Vec<Anchor>,
    model: PathLossModel,
    noise_sigma_db: f64,
    wall_loss_db: f64,
    rng_state: u64,
    /// PDR drift as a fraction of the distance walked.
    pdr_drift: f64,
}

impl SyntheticScanner {
    /// A scanner over these anchors.
    #[must_use]
    pub fn new(map: Arc<ClinicMap>, anchors: Vec<Anchor>, seed: u64) -> SyntheticScanner {
        let model = PathLossModel::default();
        SyntheticScanner {
            map,
            anchors,
            noise_sigma_db: model.sigma_db,
            model,
            wall_loss_db: WALL_LOSS_DB,
            rng_state: seed,
            pdr_drift: 0.0,
        }
    }

    /// One scan taken at `truth`.
    pub fn scan_at(
        &mut self,
        device: &DeviceId,
        floor: i32,
        truth: Point2,
        at: DateTime<Utc>,
    ) -> ScanReport {
        let mut rng = SplitMix64(self.rng_state);
        let walls = self
            .map
            .floor(floor)
            .map(|level| level.walls.clone())
            .unwrap_or_default();
        let mut observations = Vec::new();
        for anchor in self.anchors.iter().filter(|anchor| anchor.floor == floor) {
            let distance = truth.distance(&anchor.point);
            let crossed = walls
                .iter()
                .filter(|wall| wall.crosses(&truth, &anchor.point))
                .count();
            #[allow(clippy::cast_precision_loss)]
            let wall_loss = crossed as f64 * self.wall_loss_db;
            let dbm = self.model.expected_dbm(anchor.tx_power_dbm_1m, distance) - wall_loss
                + self.noise_sigma_db * rng.gaussian();
            let rounded = dbm.round();
            if rounded < f64::from(MIN_RSSI_DBM) {
                continue;
            }
            #[allow(clippy::cast_possible_truncation)]
            let dbm = rounded.min(0.0) as i16;
            observations.push(Observation::Rssi {
                anchor: anchor.id.clone(),
                dbm,
            });
        }
        self.rng_state = rng.0;
        ScanReport {
            device: device.clone(),
            at,
            observations,
            motion: None,
            pressure_hpa: None,
        }
    }

    /// Sets the log-normal RSSI noise (default 4 dB).
    #[must_use]
    pub fn with_noise_sigma_db(self, sigma_db: f64) -> SyntheticScanner {
        SyntheticScanner {
            noise_sigma_db: sigma_db,
            ..self
        }
    }

    /// Adds pedestrian dead-reckoning drift to the motion reported by [`SyntheticScanner::walk`],
    /// as a fraction of the distance walked (0.03 = 3 %; default 0).
    #[must_use]
    pub fn with_pdr_drift(self, fraction: f64) -> SyntheticScanner {
        SyntheticScanner {
            pdr_drift: fraction,
            ..self
        }
    }

    /// Scans along a path, one per `step_s` seconds; each with its true point.
    pub fn walk(
        &mut self,
        device: &DeviceId,
        floor: i32,
        path: &[Point2],
        step_s: f64,
        start: DateTime<Utc>,
    ) -> Vec<(Point2, ScanReport)> {
        let Some(first) = path.first().copied() else {
            return Vec::new();
        };
        let total: f64 = path
            .iter()
            .zip(path.iter().skip(1))
            .map(|(a, b)| a.distance(b))
            .sum();
        let step_s = if step_s.is_finite() && step_s > 0.0 {
            step_s
        } else {
            1.0
        };
        let mut scans = Vec::new();
        let mut previous = first;
        let mut index: u32 = 0;
        loop {
            let elapsed = f64::from(index) * step_s;
            let walked = elapsed * WALK_SPEED_M_S;
            if walked > total + 1e-9 {
                break;
            }
            let truth = point_along(path, walked).unwrap_or(previous);
            #[allow(clippy::cast_possible_truncation)]
            let offset = chrono::TimeDelta::milliseconds((elapsed * 1000.0).round() as i64);
            let mut scan = self.scan_at(device, floor, truth, start + offset);
            if index > 0 {
                let (dx, dy) = (truth.x() - previous.x(), truth.y() - previous.y());
                let length = dx.hypot(dy);
                scan.motion = Some(MotionDelta {
                    steps: u32::from(length > 0.0),
                    heading_rad: dy.atan2(dx) + self.pdr_drift,
                    heading_sigma_rad: PDR_HEADING_SIGMA_RAD,
                    stride_m: length * (1.0 + self.pdr_drift),
                });
            }
            scans.push((truth, scan));
            previous = truth;
            index += 1;
        }
        scans
    }
}

/// The point `distance` metres along a polyline (its end when past it).
fn point_along(path: &[Point2], distance: f64) -> Option<Point2> {
    let mut left = distance;
    for (a, b) in path.iter().zip(path.iter().skip(1)) {
        let length = a.distance(b);
        if left <= length && length > 0.0 {
            let t = left / length;
            return Point2::new(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t).ok();
        }
        left -= length;
    }
    path.last().copied()
}
