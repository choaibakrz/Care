//! RSSI smoothing: median of the last 5 readings, then exponential smoothing.

use std::collections::{HashMap, VecDeque};

use super::observation::AnchorId;

/// Readings kept for the median.
pub const MEDIAN_WINDOW: usize = 5;

/// Smoother for one anchor.
#[derive(Debug, Clone)]
pub struct RssiSmoother {
    window: VecDeque<i16>,
    ema: Option<f64>,
    alpha: f64,
}

impl RssiSmoother {
    /// A smoother with EMA factor `alpha` in (0, 1].
    #[must_use]
    pub fn new(alpha: f64) -> RssiSmoother {
        RssiSmoother {
            window: VecDeque::with_capacity(MEDIAN_WINDOW),
            ema: None,
            alpha: if alpha > 0.0 && alpha <= 1.0 {
                alpha
            } else {
                1.0
            },
        }
    }

    /// Adds a reading; returns the smoothed value.
    pub fn push(&mut self, dbm: i16) -> f64 {
        if self.window.len() >= MEDIAN_WINDOW {
            self.window.pop_front();
        }
        self.window.push_back(dbm);
        let mut sorted: Vec<f64> = self.window.iter().map(|value| f64::from(*value)).collect();
        sorted.sort_by(f64::total_cmp);
        let middle = sorted.len() / 2;
        let median = if sorted.len().is_multiple_of(2) {
            let low = sorted
                .get(middle.saturating_sub(1))
                .copied()
                .unwrap_or_default();
            let high = sorted.get(middle).copied().unwrap_or(low);
            f64::midpoint(low, high)
        } else {
            sorted.get(middle).copied().unwrap_or_default()
        };
        let smoothed = match self.ema {
            Some(previous) => self.alpha * median + (1.0 - self.alpha) * previous,
            None => median,
        };
        self.ema = Some(smoothed);
        smoothed
    }
}

/// One smoother per anchor.
#[derive(Debug, Clone, Default)]
pub struct SmootherBank {
    by_anchor: HashMap<AnchorId, RssiSmoother>,
    alpha: f64,
}

impl SmootherBank {
    /// A bank whose smoothers use `alpha`.
    #[must_use]
    pub fn new(alpha: f64) -> SmootherBank {
        SmootherBank {
            by_anchor: HashMap::new(),
            alpha,
        }
    }

    /// Adds a reading for an anchor; returns the smoothed value.
    pub fn push(&mut self, anchor: &AnchorId, dbm: i16) -> f64 {
        let alpha = self.alpha;
        self.by_anchor
            .entry(anchor.clone())
            .or_insert_with(|| RssiSmoother::new(alpha))
            .push(dbm)
    }
}
