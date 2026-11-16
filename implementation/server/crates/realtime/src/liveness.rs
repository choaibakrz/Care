//! Robot liveness: a robot silent for longer than the timeout (5 s) is offline.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::{Clock, RobotId};

/// Last-seen times per robot.
pub struct Liveness {
    timeout: Duration,
    clock: Arc<dyn Clock>,
    last_seen: Mutex<HashMap<RobotId, DateTime<Utc>>>,
}

impl Liveness {
    /// A tracker with the given silence timeout.
    #[must_use]
    pub fn new(timeout: Duration, clock: Arc<dyn Clock>) -> Liveness {
        Liveness {
            timeout,
            clock,
            last_seen: Mutex::new(HashMap::new()),
        }
    }

    /// Records that the robot was heard now.
    pub fn touch(&self, robot: &RobotId) {
        let now = self.clock.now();
        let mut map = self
            .last_seen
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        map.insert(robot.clone(), now);
    }

    /// Robots silent for longer than the timeout. Each is reported once, then forgotten.
    #[must_use]
    pub fn expired(&self) -> Vec<RobotId> {
        let now = self.clock.now();
        let timeout = chrono::Duration::from_std(self.timeout).unwrap_or(chrono::Duration::MAX);
        let mut map = self
            .last_seen
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let expired: Vec<RobotId> = map
            .iter()
            .filter(|(_, seen)| now.signed_duration_since(**seen) > timeout)
            .map(|(robot, _)| robot.clone())
            .collect();
        for robot in &expired {
            map.remove(robot);
        }
        expired
    }

    /// Stops tracking a robot (clean disconnect).
    pub fn forget(&self, robot: &RobotId) {
        let mut map = self
            .last_seen
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        map.remove(robot);
    }
}
