//! Weighted least squares (Gauss-Newton from the weighted centroid of the anchors).

use super::PositioningError;
use crate::geometry::Point2;

/// One range to an anchor with its weight.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct WeightedRange {
    /// Anchor position.
    pub anchor: Point2,
    /// Measured distance.
    pub metres: f64,
    /// Weight (inverse variance).
    pub weight: f64,
}

/// A trilateration result.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Estimate {
    /// Solution.
    pub point: Point2,
    /// Root mean square range residual.
    pub residual_m: f64,
}

/// The solver.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Trilaterator {
    /// Iteration cap.
    pub max_iterations: u32,
    /// Stop when the step is shorter than this.
    pub tolerance_m: f64,
}

impl Default for Trilaterator {
    fn default() -> Self {
        Trilaterator {
            max_iterations: 50,
            tolerance_m: 0.01,
        }
    }
}

impl Trilaterator {
    /// Solves for a point.
    ///
    /// # Errors
    /// `TooFewAnchors { have, need: 3 }`; `Diverged`.
    pub fn solve(&self, ranges: &[WeightedRange]) -> Result<Estimate, PositioningError> {
        if ranges.len() < 3 {
            return Err(PositioningError::TooFewAnchors {
                have: ranges.len(),
                need: 3,
            });
        }
        let weights: Vec<f64> = ranges
            .iter()
            .map(|range| {
                if range.weight.is_finite() && range.weight > 0.0 {
                    range.weight
                } else {
                    0.0
                }
            })
            .collect();
        let total: f64 = weights.iter().sum();
        let weights = if total > 0.0 {
            weights
        } else {
            vec![1.0; ranges.len()]
        };
        let total: f64 = weights.iter().sum();
        let weighted = || ranges.iter().zip(weights.iter().copied());
        let cx = weighted().map(|(r, w)| w * r.anchor.x()).sum::<f64>() / total;
        let cy = weighted().map(|(r, w)| w * r.anchor.y()).sum::<f64>() / total;
        let mean_range = (weighted().map(|(r, w)| w * r.metres).sum::<f64>() / total).max(1.0);
        // Principal axis of the anchors; start also on both sides of it, so nearly collinear
        // anchors do not trap the solver on the wrong mirror image.
        let (mut sxx, mut syy, mut sxy) = (0.0, 0.0, 0.0);
        for (range, w) in weighted() {
            let (dx, dy) = (range.anchor.x() - cx, range.anchor.y() - cy);
            sxx += w * dx * dx;
            syy += w * dy * dy;
            sxy += w * dx * dy;
        }
        let angle = 0.5 * (2.0 * sxy).atan2(sxx - syy);
        let (nx, ny) = (-angle.sin(), angle.cos());
        let starts = [
            (cx, cy),
            (cx + nx * mean_range, cy + ny * mean_range),
            (cx - nx * mean_range, cy - ny * mean_range),
        ];
        let mut best: Option<(f64, f64, f64)> = None;
        for start in starts {
            if let Some((x, y, cost)) = self.descend(ranges, &weights, start)
                && best.is_none_or(|(_, _, lowest)| cost < lowest - 1e-12)
            {
                best = Some((x, y, cost));
            }
        }
        let (x, y, _) = best.ok_or(PositioningError::Diverged {
            iterations: self.max_iterations,
        })?;
        let point = Point2::new(x, y).map_err(|_| PositioningError::Diverged {
            iterations: self.max_iterations,
        })?;
        #[allow(clippy::cast_precision_loss)]
        let count = ranges.len() as f64;
        let residual_m = (ranges
            .iter()
            .map(|range| (range.anchor.distance(&point) - range.metres).powi(2))
            .sum::<f64>()
            / count)
            .sqrt();
        Ok(Estimate { point, residual_m })
    }

    /// Damped Gauss-Newton with step halving from `start`; `(x, y, cost)` when it converged.
    fn descend(
        &self,
        ranges: &[WeightedRange],
        weights: &[f64],
        start: (f64, f64),
    ) -> Option<(f64, f64, f64)> {
        let cost = |x: f64, y: f64| -> f64 {
            ranges
                .iter()
                .zip(weights)
                .map(|(range, w)| {
                    let d = (x - range.anchor.x()).hypot(y - range.anchor.y());
                    w * (d - range.metres).powi(2)
                })
                .sum()
        };
        let (mut x, mut y) = start;
        let mut current = cost(x, y);
        let mut converged = false;
        for _ in 0..self.max_iterations {
            let (mut a11, mut a12, mut a22, mut g1, mut g2) = (0.0, 0.0, 0.0, 0.0, 0.0);
            for (range, w) in ranges.iter().zip(weights) {
                let (dx, dy) = (x - range.anchor.x(), y - range.anchor.y());
                let d = dx.hypot(dy).max(1e-9);
                let (jx, jy) = (dx / d, dy / d);
                let residual = d - range.metres;
                a11 += w * jx * jx;
                a12 += w * jx * jy;
                a22 += w * jy * jy;
                g1 += w * jx * residual;
                g2 += w * jy * residual;
            }
            let damping = 1e-9 * (a11 + a22).max(1e-12);
            let (a11, a22) = (a11 + damping, a22 + damping);
            let det = a11 * a22 - a12 * a12;
            if !det.is_finite() || det.abs() < 1e-18 {
                break;
            }
            let sx = -(a22 * g1 - a12 * g2) / det;
            let sy = -(a11 * g2 - a12 * g1) / det;
            let mut t = 1.0;
            let mut next = cost(x + sx, y + sy);
            while next > current && t > 1e-4 {
                t /= 2.0;
                next = cost(x + t * sx, y + t * sy);
            }
            let step = t * sx.hypot(sy);
            if !step.is_finite() {
                return None;
            }
            if next <= current {
                x += t * sx;
                y += t * sy;
                current = next;
            }
            if step < self.tolerance_m {
                converged = true;
            }
            if step < 1e-12 || (converged && next >= current && step < self.tolerance_m * 1e-3) {
                break;
            }
        }
        (converged && x.is_finite() && y.is_finite()).then_some((x, y, current))
    }
}
