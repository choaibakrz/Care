//! Shelf leases: one robot per shelf at a time, expiring by the clock.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::{Clock, PlaceId, RobotId};

/// A held lease.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Lease {
    /// Shelf.
    pub place: PlaceId,
    /// Holder.
    pub robot: RobotId,
    /// Expiry.
    pub until: DateTime<Utc>,
}

/// Lease refusal.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum LeaseError {
    /// Another robot holds the shelf.
    #[error("Shelf is held by robot {robot} until {until}; wait or choose another shelf.")]
    HeldBy {
        /// Holder.
        robot: RobotId,
        /// Expiry.
        until: DateTime<Utc>,
    },
}

/// The lease table.
pub struct ShelfLeases {
    clock: Arc<dyn Clock>,
    leases: Mutex<HashMap<PlaceId, Lease>>,
}

impl ShelfLeases {
    /// Empty.
    #[must_use]
    pub fn new(clock: Arc<dyn Clock>) -> ShelfLeases {
        ShelfLeases {
            clock,
            leases: Mutex::new(HashMap::new()),
        }
    }

    /// Takes or renews a lease.
    ///
    /// # Errors
    /// `HeldBy` when another robot holds an unexpired lease.
    pub fn acquire(
        &self,
        place: &PlaceId,
        robot: &RobotId,
        ttl: Duration,
    ) -> Result<Lease, LeaseError> {
        let now = self.clock.now();
        let mut leases = self.leases.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some(held) = leases.get(place)
            && held.robot != *robot
            && held.until > now
        {
            return Err(LeaseError::HeldBy {
                robot: held.robot.clone(),
                until: held.until,
            });
        }
        let until = chrono::Duration::from_std(ttl)
            .ok()
            .and_then(|ttl| now.checked_add_signed(ttl))
            .unwrap_or(DateTime::<Utc>::MAX_UTC);
        let lease = Lease {
            place: place.clone(),
            robot: robot.clone(),
            until,
        };
        leases.insert(place.clone(), lease.clone());
        Ok(lease)
    }

    /// Releases a lease held by `robot` (no-op otherwise).
    pub fn release(&self, place: &PlaceId, robot: &RobotId) {
        let mut leases = self.leases.lock().unwrap_or_else(PoisonError::into_inner);
        if leases.get(place).is_some_and(|held| held.robot == *robot) {
            leases.remove(place);
        }
    }
}
