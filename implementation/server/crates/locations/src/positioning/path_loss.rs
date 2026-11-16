//! Log-distance path loss: `d = 10^((P_1m − RSSI) / (10·n))`.

/// Path-loss model, calibrated per site.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PathLossModel {
    /// Exponent `n`, 2 to 4 (default 2.7).
    pub exponent_n: f64,
    /// RSSI noise (default 4 dB).
    pub sigma_db: f64,
}

impl Default for PathLossModel {
    fn default() -> Self {
        PathLossModel {
            exponent_n: 2.7,
            sigma_db: 4.0,
        }
    }
}

impl PathLossModel {
    /// Distance in metres for a reading.
    #[must_use]
    pub fn distance_m(&self, dbm: f64, tx_power_dbm_1m: f64) -> f64 {
        10_f64.powf((tx_power_dbm_1m - dbm) / (10.0 * self.exponent_n))
    }

    /// Likelihood of reading `dbm` at `distance_m` (log-normal).
    #[must_use]
    pub fn likelihood(&self, dbm: f64, tx_power_dbm_1m: f64, distance_m: f64) -> f64 {
        let expected = self.expected_dbm(tx_power_dbm_1m, distance_m);
        let sigma = self.sigma_db.max(0.1);
        let z = (dbm - expected) / sigma;
        (-0.5 * z * z).exp() / (sigma * (std::f64::consts::TAU).sqrt())
    }

    /// Expected RSSI at `distance_m` (clamped to at least 0.1 m).
    #[must_use]
    pub fn expected_dbm(&self, tx_power_dbm_1m: f64, distance_m: f64) -> f64 {
        tx_power_dbm_1m - 10.0 * self.exponent_n * distance_m.max(0.1).log10()
    }
}
