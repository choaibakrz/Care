//! Room decision with hysteresis: a change needs 3 s of agreement; a manual pick wins 5 min.

use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::PlaceId;

/// Fingerprint confidence above which the fingerprint decides the room.
pub const FINGERPRINT_MIN_CONFIDENCE: f64 = 0.6;
/// Agreement needed before a room or floor change.
pub const ROOM_HYSTERESIS: Duration = Duration::from_secs(3);
/// How long a manual pick overrides Bluetooth.
pub const MANUAL_OVERRIDE: Duration = Duration::from_mins(5);

/// Tracks the decided room of one tablet.
#[derive(Debug, Clone)]
pub struct RoomTracker {
    current: Option<(PlaceId, i32)>,
    candidate: Option<(PlaceId, i32, DateTime<Utc>)>,
    hysteresis: Duration,
    manual_until: Option<DateTime<Utc>>,
}

impl RoomTracker {
    /// A tracker with the given hysteresis.
    #[must_use]
    pub fn new(hysteresis: Duration) -> RoomTracker {
        RoomTracker {
            current: None,
            candidate: None,
            hysteresis,
            manual_until: None,
        }
    }

    /// Feeds a proposed room; returns the decided room.
    pub fn observe(
        &mut self,
        place: PlaceId,
        floor: i32,
        at: DateTime<Utc>,
    ) -> Option<(PlaceId, i32)> {
        if self.manual_active(at) {
            self.candidate = None;
            return self.current.clone();
        }
        self.manual_until = None;
        let proposed = (place, floor);
        match &self.current {
            None => {
                self.current = Some(proposed);
                self.candidate = None;
            }
            Some(current) if *current == proposed => self.candidate = None,
            Some(_) => {
                let since = match &self.candidate {
                    Some((candidate, candidate_floor, since))
                        if *candidate == proposed.0 && *candidate_floor == proposed.1 =>
                    {
                        *since
                    }
                    _ => at,
                };
                let needed = chrono::TimeDelta::from_std(self.hysteresis)
                    .unwrap_or(chrono::TimeDelta::zero());
                if at.signed_duration_since(since) >= needed {
                    self.current = Some(proposed);
                    self.candidate = None;
                } else {
                    self.candidate = Some((proposed.0, proposed.1, since));
                }
            }
        }
        self.current.clone()
    }

    /// A manual pick: decided immediately, overrides Bluetooth for 5 minutes.
    pub fn set_manual(&mut self, place: PlaceId, floor: i32, at: DateTime<Utc>) {
        self.current = Some((place, floor));
        self.candidate = None;
        self.manual_until = chrono::TimeDelta::from_std(MANUAL_OVERRIDE)
            .ok()
            .map(|span| at + span);
    }

    /// Whether a manual pick still overrides Bluetooth at `at`.
    #[must_use]
    pub fn manual_active(&self, at: DateTime<Utc>) -> bool {
        self.manual_until.is_some_and(|until| at < until)
    }
}
