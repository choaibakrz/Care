//! Time source. Everything that needs "now" takes an `Arc<dyn Clock>`, so tests control time.

use chrono::{DateTime, Utc};

/// A source of the current UTC time.
pub trait Clock: Send + Sync {
    /// The current time.
    fn now(&self) -> DateTime<Utc>;
}

/// The system clock.
#[derive(Debug, Clone, Copy, Default)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> DateTime<Utc> {
        Utc::now()
    }
}

/// A settable clock for tests (feature `testing`).
#[cfg(feature = "testing")]
#[derive(Debug)]
pub struct FakeClock {
    now: std::sync::Mutex<DateTime<Utc>>,
}

#[cfg(feature = "testing")]
impl FakeClock {
    /// A clock stopped at `at`.
    #[must_use]
    pub fn new(at: DateTime<Utc>) -> FakeClock {
        FakeClock {
            now: std::sync::Mutex::new(at),
        }
    }

    /// The stored time; a poisoned lock is recovered because a `DateTime` cannot be half-written.
    fn lock(&self) -> std::sync::MutexGuard<'_, DateTime<Utc>> {
        self.now
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    /// Sets the time.
    pub fn set(&self, at: DateTime<Utc>) {
        *self.lock() = at;
    }

    /// Moves the time forward.
    pub fn advance(&self, by: std::time::Duration) {
        let mut now = self.lock();
        // A duration too large for chrono leaves the time unchanged rather than panicking.
        if let Ok(by) = chrono::Duration::from_std(by) {
            *now = now.checked_add_signed(by).unwrap_or(*now);
        }
    }
}

#[cfg(feature = "testing")]
impl Clock for FakeClock {
    fn now(&self) -> DateTime<Utc> {
        *self.lock()
    }
}

#[cfg(all(test, feature = "testing"))]
mod tests {
    use chrono::{TimeZone, Utc};

    use super::{Clock, FakeClock};

    #[test]
    fn fake_clock_is_set_and_advanced() -> Result<(), Box<dyn std::error::Error>> {
        let start = Utc
            .with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
            .single()
            .ok_or("bad test date")?;
        let clock = FakeClock::new(start);
        assert_eq!(clock.now(), start);
        clock.advance(std::time::Duration::from_secs(90));
        assert_eq!(clock.now(), start + chrono::Duration::seconds(90));
        clock.set(start);
        assert_eq!(clock.now(), start);
        Ok(())
    }
}
