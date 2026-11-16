//! The hub: one broadcast channel to the apps and one queue pair per connected robot.
//!
//! For each robot, `register_robot` creates two ends:
//! - [`RobotSession`], the service side (`send` down, `recv` up), run by
//!   `RobotService::run_session`;
//! - [`RobotLink`], the socket side (`next_down`, `push_up`), pumped by the WebSocket handler.
//!
//! The emergency stop uses a separate priority queue that `next_down` always drains first.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

use domain::{Clock, RobotId, SystemClock};
use tokio::sync::{broadcast, mpsc};

use crate::error::RealtimeError;
use crate::protocol::{AppEvent, Envelope, RobotDown, RobotUp};

/// Capacity of the application broadcast; a slower subscriber gets `resync`.
pub const APP_QUEUE_CAPACITY: usize = 256;
/// Capacity of each robot queue.
pub const ROBOT_QUEUE_CAPACITY: usize = 64;
/// Capacity of each robot's priority queue (emergency stops only).
pub const PRIORITY_QUEUE_CAPACITY: usize = 8;

/// Senders kept by the hub for one connected robot.
#[derive(Debug, Clone)]
struct RobotChannels {
    down: mpsc::Sender<Envelope<RobotDown>>,
    priority: mpsc::Sender<Envelope<RobotDown>>,
}

/// The real-time hub. Never blocks on a slow subscriber.
pub struct Hub {
    apps: broadcast::Sender<AppEvent>,
    robots: Mutex<HashMap<RobotId, RobotChannels>>,
    clock: Arc<dyn Clock>,
}

impl Hub {
    /// A hub on the system clock.
    #[must_use]
    pub fn new() -> Hub {
        Hub::with_clock(Arc::new(SystemClock))
    }

    /// A hub on the given clock (envelope timestamps).
    #[must_use]
    pub fn with_clock(clock: Arc<dyn Clock>) -> Hub {
        let (apps, _unused) = broadcast::channel(APP_QUEUE_CAPACITY);
        Hub {
            apps,
            robots: Mutex::new(HashMap::new()),
            clock,
        }
    }

    /// Subscribes an application to every event published from now on.
    #[must_use]
    pub fn subscribe_apps(&self) -> broadcast::Receiver<AppEvent> {
        self.apps.subscribe()
    }

    /// How many application subscriptions are open (`GET /monitor/summary` `app_clients`:
    /// each `/ws` client holds one).
    #[must_use]
    pub fn app_subscribers(&self) -> usize {
        self.apps.receiver_count()
    }

    /// Publishes an event to every application; no subscriber is not an error.
    pub fn publish(&self, event: AppEvent) {
        // `Err` only means nobody is subscribed right now, which is not an error.
        let _no_subscriber_is_fine = self.apps.send(event);
    }

    /// Registers a robot connection.
    ///
    /// # Errors
    /// `RobotAlreadyConnected` when the robot already has a session.
    pub fn register_robot(&self, robot: RobotId) -> Result<RobotSession, RealtimeError> {
        let mut robots = self.robot_map();
        if robots.contains_key(&robot) {
            return Err(RealtimeError::RobotAlreadyConnected { robot });
        }
        let (down_tx, down_rx) = mpsc::channel(ROBOT_QUEUE_CAPACITY);
        let (priority_tx, priority_rx) = mpsc::channel(PRIORITY_QUEUE_CAPACITY);
        let (up_tx, up_rx) = mpsc::channel(ROBOT_QUEUE_CAPACITY);
        robots.insert(
            robot.clone(),
            RobotChannels {
                down: down_tx.clone(),
                priority: priority_tx,
            },
        );
        drop(robots);
        Ok(RobotSession {
            robot: robot.clone(),
            down: down_tx,
            up: up_rx,
            link: Some(RobotLink {
                robot,
                down: down_rx,
                priority: priority_rx,
                up: up_tx,
            }),
            clock: self.clock.clone(),
        })
    }

    /// Removes a robot's queues (on disconnect).
    pub fn unregister_robot(&self, robot: &RobotId) {
        self.robot_map().remove(robot);
    }

    /// Queues a message to a connected robot.
    ///
    /// # Errors
    /// `RobotNotConnected`; `QueueFull`; `Closed`.
    pub fn send_to_robot(&self, robot: &RobotId, down: RobotDown) -> Result<(), RealtimeError> {
        let sender = self.channels(robot)?.down;
        try_send(&sender, robot, Envelope::new(down, self.clock.now()))
    }

    /// Queues a message on the priority queue (emergency stop only), read before anything else.
    ///
    /// # Errors
    /// `RobotNotConnected`; `QueueFull`; `Closed`.
    pub fn send_priority(&self, robot: &RobotId, down: RobotDown) -> Result<(), RealtimeError> {
        let sender = self.channels(robot)?.priority;
        try_send(&sender, robot, Envelope::new(down, self.clock.now()))
    }

    /// Sends the same message to every connected robot; returns the robots it did not reach.
    #[must_use]
    #[allow(
        clippy::needless_pass_by_value,
        reason = "public signature; callers hand over the message"
    )]
    pub fn broadcast_to_robots(&self, down: RobotDown) -> Vec<RobotId> {
        self.connected_robots()
            .into_iter()
            .filter(|robot| self.send_to_robot(robot, down.clone()).is_err())
            .collect()
    }

    /// Robots with a live connection.
    #[must_use]
    pub fn connected_robots(&self) -> Vec<RobotId> {
        self.robot_map().keys().cloned().collect()
    }

    /// Whether a robot has a live connection.
    #[must_use]
    pub fn is_connected(&self, robot: &RobotId) -> bool {
        self.robot_map().contains_key(robot)
    }
}

impl Hub {
    /// The robot map. A poisoned lock (a panic while holding it, which the lint wall makes
    /// unlikely) still yields the map: it only holds senders, which stay consistent.
    fn robot_map(&self) -> MutexGuard<'_, HashMap<RobotId, RobotChannels>> {
        self.robots.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// A clone of a connected robot's senders (the lock is released before sending).
    fn channels(&self, robot: &RobotId) -> Result<RobotChannels, RealtimeError> {
        self.robot_map()
            .get(robot)
            .cloned()
            .ok_or_else(|| RealtimeError::RobotNotConnected {
                robot: robot.clone(),
            })
    }
}

impl Default for Hub {
    fn default() -> Self {
        Hub::new()
    }
}

/// Service side of one robot connection.
pub struct RobotSession {
    robot: RobotId,
    down: mpsc::Sender<Envelope<RobotDown>>,
    up: mpsc::Receiver<Envelope<RobotUp>>,
    link: Option<RobotLink>,
    clock: Arc<dyn Clock>,
}

impl RobotSession {
    /// The robot.
    #[must_use]
    pub fn robot(&self) -> &RobotId {
        &self.robot
    }

    /// Queues a message to this robot.
    ///
    /// # Errors
    /// `QueueFull`; `Closed`.
    pub fn send(&self, down: RobotDown) -> Result<(), RealtimeError> {
        try_send(
            &self.down,
            &self.robot,
            Envelope::new(down, self.clock.now()),
        )
    }

    /// The next message from the robot; `None` when the socket closed.
    pub async fn recv(&mut self) -> Option<Envelope<RobotUp>> {
        self.up.recv().await
    }

    /// Hands the socket side to the WebSocket pump. Returns `None` after the first call.
    pub fn take_link(&mut self) -> Option<RobotLink> {
        self.link.take()
    }
}

/// Socket side of one robot connection.
pub struct RobotLink {
    robot: RobotId,
    down: mpsc::Receiver<Envelope<RobotDown>>,
    priority: mpsc::Receiver<Envelope<RobotDown>>,
    up: mpsc::Sender<Envelope<RobotUp>>,
}

impl RobotLink {
    /// The next message to write to the socket: the priority queue first; `None` when closed.
    pub async fn next_down(&mut self) -> Option<Envelope<RobotDown>> {
        tokio::select! {
            biased;
            Some(urgent) = self.priority.recv() => Some(urgent),
            next = self.down.recv() => next,
        }
    }

    /// Passes a decoded robot message to the service side.
    ///
    /// # Errors
    /// `QueueFull` when the service is not keeping up; `Closed` when it stopped.
    pub fn push_up(&self, envelope: Envelope<RobotUp>) -> Result<(), RealtimeError> {
        self.up.try_send(envelope).map_err(|error| match error {
            mpsc::error::TrySendError::Full(_) => RealtimeError::QueueFull {
                robot: self.robot.clone(),
            },
            mpsc::error::TrySendError::Closed(_) => RealtimeError::Closed {
                robot: self.robot.clone(),
            },
        })
    }
}

/// Queues one message without waiting: a full queue or a closed connection is an error, so a
/// robot that stops reading never blocks the hub or the caller.
fn try_send(
    sender: &mpsc::Sender<Envelope<RobotDown>>,
    robot: &RobotId,
    envelope: Envelope<RobotDown>,
) -> Result<(), RealtimeError> {
    sender.try_send(envelope).map_err(|error| match error {
        mpsc::error::TrySendError::Full(_) => RealtimeError::QueueFull {
            robot: robot.clone(),
        },
        mpsc::error::TrySendError::Closed(_) => RealtimeError::Closed {
            robot: robot.clone(),
        },
    })
}

#[cfg(test)]
mod tests {
    use domain::{CommandName, RobotId, RobotStatus};
    use tokio::sync::broadcast::error::TryRecvError;

    use super::{APP_QUEUE_CAPACITY, Hub, ROBOT_QUEUE_CAPACITY};
    use crate::error::RealtimeError;
    use crate::protocol::{AppEvent, Envelope, RobotDown, RobotPose, RobotUp};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn state() -> RobotUp {
        RobotUp::State {
            pos: RobotPose {
                x: 1.0,
                y: 2.0,
                heading: 0.0,
                floor: 0,
            },
            battery_pct: 50.0,
            status: RobotStatus::Idle,
            holding: None,
            mic_open: false,
        }
    }

    #[tokio::test]
    async fn second_registration_is_refused_until_unregistered() -> TestResult {
        let hub = Hub::new();
        let robot: RobotId = "robot-r1".parse()?;
        let _session = hub.register_robot(robot.clone())?;
        assert!(hub.is_connected(&robot));
        assert!(matches!(
            hub.register_robot(robot.clone()),
            Err(RealtimeError::RobotAlreadyConnected { .. })
        ));
        hub.unregister_robot(&robot);
        assert!(!hub.is_connected(&robot));
        assert!(hub.register_robot(robot).is_ok());
        Ok(())
    }

    #[tokio::test]
    async fn messages_flow_both_ways_and_estop_goes_first() -> TestResult {
        let hub = Hub::new();
        let robot: RobotId = "robot-r1".parse()?;
        let mut session = hub.register_robot(robot.clone())?;
        assert_eq!(session.robot(), &robot);
        let mut link = session.take_link().ok_or("no link")?;
        assert!(session.take_link().is_none());
        session.send(RobotDown::Command {
            name: CommandName::Pause,
        })?;
        hub.send_priority(
            &robot,
            RobotDown::Command {
                name: CommandName::Estop,
            },
        )?;
        let first = link.next_down().await.ok_or("closed")?;
        assert_eq!(
            first.body,
            RobotDown::Command {
                name: CommandName::Estop
            }
        );
        let second = link.next_down().await.ok_or("closed")?;
        assert_eq!(
            second.body,
            RobotDown::Command {
                name: CommandName::Pause
            }
        );
        link.push_up(Envelope::new(state(), chrono::Utc::now()))?;
        let up = session.recv().await.ok_or("closed")?;
        assert_eq!(up.body, state());
        Ok(())
    }

    #[tokio::test]
    async fn unknown_robot_and_full_queue_are_errors_not_waits() -> TestResult {
        let hub = Hub::new();
        let robot: RobotId = "robot-r1".parse()?;
        let pause = RobotDown::Command {
            name: CommandName::Pause,
        };
        assert!(matches!(
            hub.send_to_robot(&robot, pause.clone()),
            Err(RealtimeError::RobotNotConnected { .. })
        ));
        let _session = hub.register_robot(robot.clone())?;
        for _ in 0..ROBOT_QUEUE_CAPACITY {
            hub.send_to_robot(&robot, pause.clone())?;
        }
        assert!(matches!(
            hub.send_to_robot(&robot, pause),
            Err(RealtimeError::QueueFull { .. })
        ));
        Ok(())
    }

    #[tokio::test]
    async fn estop_passes_a_full_robot_queue_and_is_read_first() -> TestResult {
        let hub = Hub::new();
        let robot: RobotId = "robot-r1".parse()?;
        let mut session = hub.register_robot(robot.clone())?;
        let mut link = session.take_link().ok_or("no link")?;
        let pause = RobotDown::Command {
            name: CommandName::Pause,
        };
        for _ in 0..ROBOT_QUEUE_CAPACITY {
            hub.send_to_robot(&robot, pause.clone())?;
        }
        assert!(matches!(
            hub.send_to_robot(&robot, pause.clone()),
            Err(RealtimeError::QueueFull { .. })
        ));
        let stop = RobotDown::Command {
            name: CommandName::Estop,
        };
        hub.send_priority(&robot, stop.clone())?;
        let first = link.next_down().await.ok_or("closed")?;
        assert_eq!(first.body, stop);
        let second = link.next_down().await.ok_or("closed")?;
        assert_eq!(second.body, pause);
        Ok(())
    }

    #[tokio::test]
    async fn a_slow_app_lags_instead_of_blocking_the_hub() -> TestResult {
        let hub = Hub::new();
        let mut slow = hub.subscribe_apps();
        for _ in 0..=APP_QUEUE_CAPACITY {
            hub.publish(AppEvent::Resync);
        }
        assert!(matches!(slow.try_recv(), Err(TryRecvError::Lagged(_))));
        Ok(())
    }
}
