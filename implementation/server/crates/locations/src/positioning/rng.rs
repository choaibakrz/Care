//! `SplitMix64`: a tiny deterministic generator (no RNG dependency), for the particle filter
//! and the synthetic scanner.

/// Generator state.
#[derive(Debug, Clone, Copy)]
pub(crate) struct SplitMix64(pub(crate) u64);

impl SplitMix64 {
    /// Next 64 random bits.
    pub(crate) fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }

    /// Uniform in `[0, 1)`.
    pub(crate) fn next_f64(&mut self) -> f64 {
        #[allow(clippy::cast_precision_loss)]
        let value = (self.next_u64() >> 11) as f64 / (1_u64 << 53) as f64;
        value
    }

    /// Standard normal (Box-Muller).
    pub(crate) fn gaussian(&mut self) -> f64 {
        let u1 = self.next_f64().max(f64::MIN_POSITIVE);
        let u2 = self.next_f64();
        (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
    }
}
