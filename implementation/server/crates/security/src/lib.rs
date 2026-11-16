//! HTTP security stack: CORS, request limits, per-IP rate limiting, known networks with an
//! identity header, token identity, and the `Origin` check for WebSocket upgrades; and the
//! account key primitives of Task A7 (`accounts`: reference derivation, pepper HMAC); and
//! the monitoring, rate limit and blocks of Task A8 (`monitor`).

pub mod accounts;
pub mod cors;
pub mod error;
pub mod identity;
pub mod known_networks;
pub mod limits;
pub mod mock;
pub mod monitor;
pub mod origin;
pub mod rate_limit;
pub mod stack;

pub use accounts::{Pepper, account_id, constant_time_eq, derive_account_key, enrolment_code_hash};
pub use cors::CorsPolicy;
pub use error::SecurityError;
pub use identity::{ClientIdentity, TokenVerifier, VerifiedIdentity};
pub use known_networks::{ClientNetwork, KnownNetworks, NetworkEntry};
pub use limits::{PathLimits, RequestLimits, RouteLimits};
pub use mock::{MOCK_NETWORK_LABEL, MockStack};
pub use monitor::{
    Admission, BlockAction, BlockError, BlockJournal, BlockView, ClientView, MonitorConfig,
    MonitorHooks, MonitorNotice, NewBlockRequest, RejectMarker, SecurityAlert, TrafficMonitor,
    TrafficTotals, TrafficView,
};
pub use origin::OriginCheck;
pub use rate_limit::{RateLimitConfig, RateLimiter};
pub use stack::{OPEN_NETWORK_LABEL, SecurityConfig, SecurityStack};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
