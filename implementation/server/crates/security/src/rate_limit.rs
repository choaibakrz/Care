//! Per-IP rate limiting with `governor` (tower-http has none). On excess: 429,
//! code `rate_limited`, `Retry-After`, and the wait in seconds in the message.

use std::net::IpAddr;
use std::num::NonZeroU32;
use std::sync::Arc;

use governor::DefaultKeyedRateLimiter;

use crate::error::SecurityError;

/// Rate settings.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RateLimitConfig {
    /// Sustained requests per second.
    pub per_second: NonZeroU32,
    /// Burst size.
    pub burst: NonZeroU32,
}

/// A keyed limiter per client IP. Cheap to clone.
#[derive(Clone)]
pub struct RateLimiter {
    inner: Arc<DefaultKeyedRateLimiter<IpAddr>>,
}

impl RateLimiter {
    /// A limiter.
    #[must_use]
    pub fn new(config: RateLimitConfig) -> RateLimiter {
        let quota = governor::Quota::per_second(config.per_second).allow_burst(config.burst);
        RateLimiter {
            inner: Arc::new(governor::RateLimiter::keyed(quota)),
        }
    }

    /// Admits or refuses one request from `ip`.
    ///
    /// # Errors
    /// `RateLimited` with the wait in whole seconds (at least 1).
    pub fn check(&self, ip: IpAddr) -> Result<(), SecurityError> {
        use governor::clock::{Clock as _, DefaultClock};
        self.inner.check_key(&ip).map_err(|not_until| {
            let wait = not_until.wait_time_from(DefaultClock::default().now());
            SecurityError::RateLimited {
                retry_after_s: wait.as_secs().max(1),
            }
        })
    }
}
