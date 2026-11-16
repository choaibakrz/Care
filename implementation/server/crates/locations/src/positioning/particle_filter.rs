//! Particle filter with map matching: a particle whose move crosses a wall is discarded;
//! particles outside the floor outline weigh zero.

use std::time::Duration;

use super::observation::{Anchor, MotionDelta, Observation};
use super::path_loss::PathLossModel;
use super::rng::SplitMix64;
use super::simulate::WALL_LOSS_DB;
use crate::geometry::Point2;
use crate::model::Floor;

/// Highest walking speed.
pub const MAX_WALK_SPEED_M_S: f64 = 1.5;
/// Default particle count.
pub const DEFAULT_PARTICLES: usize = 500;

/// One hypothesis.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Particle {
    /// Position.
    pub point: Point2,
    /// Weight.
    pub weight: f64,
}

/// A particle-filter result.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FilterEstimate {
    /// Weighted mean.
    pub point: Point2,
    /// 2σ radius.
    pub uncertainty_m: f64,
}

/// The filter for one tablet on one floor. Deterministic for a given seed.
#[derive(Debug, Clone)]
pub struct ParticleFilter {
    floor: Floor,
    particles: Vec<Particle>,
    /// State of the internal `SplitMix64` generator (no RNG dependency).
    rng_state: u64,
    motion: Option<MotionDelta>,
}

/// Floor on the standard deviation of a range observation, metres (keeps a few particles
/// alive when the radio claims centimetres).
const RANGE_SIGMA_FLOOR_M: f64 = 0.3;
/// Position noise added to every PDR move and after resampling, metres.
const JITTER_M: f64 = 0.1;
/// Relative error of a PDR stride.
const STRIDE_NOISE: f64 = 0.1;
/// Heading noise added to the reported one, radians.
const HEADING_NOISE_RAD: f64 = 0.05;

impl ParticleFilter {
    /// Spreads `particles` uniformly over the floor outline.
    #[must_use]
    pub fn new(floor: &Floor, particles: usize, seed: u64) -> ParticleFilter {
        let mut rng = SplitMix64(seed);
        let vertices = floor.outline.vertices();
        let min_x = vertices.iter().map(Point2::x).fold(f64::INFINITY, f64::min);
        let min_y = vertices.iter().map(Point2::y).fold(f64::INFINITY, f64::min);
        let max_x = vertices
            .iter()
            .map(Point2::x)
            .fold(f64::NEG_INFINITY, f64::max);
        let max_y = vertices
            .iter()
            .map(Point2::y)
            .fold(f64::NEG_INFINITY, f64::max);
        let centroid = floor.outline.centroid();
        let count = particles.max(1);
        #[allow(clippy::cast_precision_loss)]
        let weight = 1.0 / count as f64;
        let mut spread = Vec::with_capacity(count);
        for _ in 0..count {
            let mut point = centroid;
            for _ in 0..1000 {
                let x = min_x + rng.next_f64() * (max_x - min_x);
                let y = min_y + rng.next_f64() * (max_y - min_y);
                if let Ok(candidate) = Point2::new(x, y)
                    && floor.outline.contains(&candidate)
                {
                    point = candidate;
                    break;
                }
            }
            spread.push(Particle { point, weight });
        }
        ParticleFilter {
            floor: floor.clone(),
            particles: spread,
            rng_state: rng.0,
            motion: None,
        }
    }

    /// Sets the PDR motion used by the next `predict` (random walk when `None`).
    pub fn set_motion(&mut self, motion: Option<MotionDelta>) {
        self.motion = motion;
    }

    /// Moves every particle; moves through walls are discarded.
    pub fn predict(&mut self, dt: Duration) {
        let seconds = dt.as_secs_f64();
        let reach = MAX_WALK_SPEED_M_S * seconds;
        let motion = self.motion.take();
        let mut rng = SplitMix64(self.rng_state);
        let mut moved = Vec::with_capacity(self.particles.len());
        for particle in &self.particles {
            let (dx, dy) = if let Some(delta) = motion {
                let length =
                    f64::from(delta.steps) * delta.stride_m * (1.0 + STRIDE_NOISE * rng.gaussian());
                let heading = delta.heading_rad
                    + (delta.heading_sigma_rad.abs() + HEADING_NOISE_RAD) * rng.gaussian();
                (
                    length * heading.cos() + JITTER_M * rng.gaussian(),
                    length * heading.sin() + JITTER_M * rng.gaussian(),
                )
            } else {
                let sigma = reach / 2.0;
                let (dx, dy) = (sigma * rng.gaussian(), sigma * rng.gaussian());
                let length = dx.hypot(dy);
                if length > reach && length > 0.0 {
                    (dx * reach / length, dy * reach / length)
                } else {
                    (dx, dy)
                }
            };
            moved.push(self.try_step(particle.point, dx, dy).map(|point| Particle {
                point,
                weight: particle.weight,
            }));
        }
        // A discarded particle is replaced by a copy of a random survivor (whose own move was
        // legal, so no particle ever crosses a wall); with no survivor everyone stays put.
        let survivors: Vec<Particle> = moved.iter().flatten().copied().collect();
        let replaced: Vec<Particle> = moved
            .into_iter()
            .zip(&self.particles)
            .map(|(next, before)| match next {
                Some(particle) => particle,
                None if survivors.is_empty() => *before,
                None => {
                    #[allow(
                        clippy::cast_possible_truncation,
                        clippy::cast_sign_loss,
                        clippy::cast_precision_loss
                    )]
                    let pick = (rng.next_f64() * survivors.len() as f64) as usize;
                    let source = survivors.get(pick).or(survivors.first()).copied();
                    // The copy comes from another position: keep the move legal from here.
                    match source {
                        Some(copy)
                            if !self
                                .floor
                                .walls
                                .iter()
                                .any(|wall| wall.crosses(&before.point, &copy.point)) =>
                        {
                            copy
                        }
                        _ => *before,
                    }
                }
            })
            .collect();
        self.particles = replaced;
        self.rng_state = rng.0;
    }

    /// Reweights with the observations, then resamples.
    pub fn update(
        &mut self,
        observations: &[Observation],
        anchors: &[Anchor],
        model: &PathLossModel,
    ) {
        let level = self.floor.level;
        let used: Vec<(&Observation, &Anchor)> = observations
            .iter()
            .filter_map(|observation| {
                let id = match observation {
                    Observation::Rssi { anchor, .. } | Observation::Range { anchor, .. } => anchor,
                };
                anchors
                    .iter()
                    .find(|anchor| &anchor.id == id && anchor.floor == level)
                    .map(|anchor| (observation, anchor))
            })
            .collect();
        if used.is_empty() {
            return;
        }
        let log_weights: Vec<f64> = self
            .particles
            .iter()
            .map(|particle| {
                if !self.floor.outline.contains(&particle.point) {
                    return f64::NEG_INFINITY;
                }
                let mut log = particle.weight.max(f64::MIN_POSITIVE).ln();
                for (observation, anchor) in &used {
                    let distance = particle.point.distance(&anchor.point);
                    log += match observation {
                        Observation::Range {
                            metres, sigma_m, ..
                        } => {
                            let variance = sigma_m * sigma_m
                                + anchor.spread_m * anchor.spread_m
                                + RANGE_SIGMA_FLOOR_M * RANGE_SIGMA_FLOOR_M;
                            -(distance - metres).powi(2) / (2.0 * variance)
                        }
                        Observation::Rssi { dbm, .. } => {
                            // Map matching: every wall in between costs WALL_LOSS_DB.
                            #[allow(clippy::cast_precision_loss)]
                            let walls = self
                                .floor
                                .walls
                                .iter()
                                .filter(|wall| wall.crosses(&particle.point, &anchor.point))
                                .count() as f64;
                            let expected = model.expected_dbm(anchor.tx_power_dbm_1m, distance)
                                - walls * WALL_LOSS_DB;
                            // The anchor's own spread, turned into dB at this distance.
                            let spread_db = 10.0 * model.exponent_n * anchor.spread_m
                                / (std::f64::consts::LN_10 * distance.max(1.0));
                            let variance = model.sigma_db.max(0.5).powi(2) + spread_db.powi(2);
                            -(f64::from(*dbm) - expected).powi(2) / (2.0 * variance)
                        }
                    };
                }
                log
            })
            .collect();
        let best = log_weights
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        if !best.is_finite() {
            return;
        }
        let weights: Vec<f64> = log_weights.iter().map(|log| (log - best).exp()).collect();
        let total: f64 = weights.iter().sum();
        if total <= 0.0 || !total.is_finite() {
            return;
        }
        self.resample(&weights, total);
    }

    /// Current estimate.
    #[must_use]
    pub fn estimate(&self) -> FilterEstimate {
        let total: f64 = self.particles.iter().map(|p| p.weight).sum();
        let total = if total > 0.0 { total } else { 1.0 };
        let mx = self
            .particles
            .iter()
            .map(|p| p.weight * p.point.x())
            .sum::<f64>()
            / total;
        let my = self
            .particles
            .iter()
            .map(|p| p.weight * p.point.y())
            .sum::<f64>()
            / total;
        let variance = self
            .particles
            .iter()
            .map(|p| p.weight * ((p.point.x() - mx).powi(2) + (p.point.y() - my).powi(2)))
            .sum::<f64>()
            / total;
        FilterEstimate {
            point: Point2::new(mx, my).unwrap_or_else(|_| self.floor.outline.centroid()),
            uncertainty_m: 2.0 * variance.max(0.0).sqrt(),
        }
    }

    /// The current particles (tests check that no move crosses a wall).
    #[must_use]
    pub fn particles(&self) -> &[Particle] {
        &self.particles
    }

    /// Level of the floor this filter runs on.
    #[must_use]
    pub fn floor_level(&self) -> i32 {
        self.floor.level
    }

    /// `from + (dx, dy)` when the move stays inside the outline and crosses no wall; `from`
    /// otherwise.
    fn step(&self, from: Point2, dx: f64, dy: f64) -> Point2 {
        self.try_step(from, dx, dy).unwrap_or(from)
    }

    /// `from + (dx, dy)` when that move is legal.
    fn try_step(&self, from: Point2, dx: f64, dy: f64) -> Option<Point2> {
        Point2::new(from.x() + dx, from.y() + dy).ok().filter(|to| {
            self.floor.outline.contains(to)
                && !self.floor.walls.iter().any(|wall| wall.crosses(&from, to))
        })
    }

    /// Systematic resampling, then a little jitter (wall-checked).
    fn resample(&mut self, weights: &[f64], total: f64) {
        let count = self.particles.len();
        if count == 0 {
            return;
        }
        let mut rng = SplitMix64(self.rng_state);
        #[allow(clippy::cast_precision_loss)]
        let spacing = total / count as f64;
        let mut target = rng.next_f64() * spacing;
        let mut cumulative = 0.0;
        let mut source = 0;
        let mut picked = Vec::with_capacity(count);
        for _ in 0..count {
            while source + 1 < count
                && cumulative + weights.get(source).copied().unwrap_or(0.0) < target
            {
                cumulative += weights.get(source).copied().unwrap_or(0.0);
                source += 1;
            }
            if let Some(particle) = self.particles.get(source) {
                picked.push(particle.point);
            }
            target += spacing;
        }
        #[allow(clippy::cast_precision_loss)]
        let weight = 1.0 / picked.len().max(1) as f64;
        let mut fresh = Vec::with_capacity(picked.len());
        for point in picked {
            let (dx, dy) = (JITTER_M * rng.gaussian(), JITTER_M * rng.gaussian());
            fresh.push(Particle {
                point: self.step(point, dx, dy),
                weight,
            });
        }
        self.particles = fresh;
        self.rng_state = rng.0;
    }
}
