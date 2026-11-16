//! Tasks given to one robot by an admin, and `follow` tasks (Step C1, mock path).
//!
//! A `follow` task re-targets the simulated robot to the room of a staff tablet: the heartbeat
//! calls [`MockServices::follow_tick`] every second, and the robot is sent to the tablet's
//! room whenever it changed. It ends on cancel, after `FOLLOW_MAX_MINUTES` (default 10), or
//! when the robot fails. The tablet is shown by its pseudonym (`target_label`) only.

use chrono::{DateTime, Duration as ChronoDuration, Utc};
use domain::{DeviceId, PlaceId, RobotId, RobotStatus, TaskId, TaskKind, TaskState};
use realtime::{AppEvent, Hub, RobotDown, TaskView};

use super::{MockData, MockServices, history};
use crate::error::ApiError;

/// Default longest follow, minutes (`FOLLOW_MAX_MINUTES`).
const FOLLOW_MAX_MINUTES: i64 = 10;

/// One running follow.
pub(super) struct Follow {
    task: TaskId,
    robot: RobotId,
    device: DeviceId,
    until: DateTime<Utc>,
    /// The room the robot was last sent to.
    target: PlaceId,
}

impl Follow {
    pub(super) fn start(
        task: &TaskView,
        robot: RobotId,
        device: DeviceId,
        until: DateTime<Utc>,
    ) -> Follow {
        Follow {
            task: task.id.clone(),
            robot,
            device,
            until,
            target: task.to_place.clone(),
        }
    }
}

/// The longest follow: `FOLLOW_MAX_MINUTES` from the environment, else 10 minutes.
pub(super) fn follow_duration() -> ChronoDuration {
    let minutes = std::env::var("FOLLOW_MAX_MINUTES")
        .ok()
        .and_then(|value| value.trim().parse::<i64>().ok())
        .filter(|minutes| *minutes > 0)
        .unwrap_or(FOLLOW_MAX_MINUTES);
    ChronoDuration::minutes(minutes)
}

impl MockData {
    /// Whether an admin may give `robot` a task now: 409 `estop_latched`, `robot_offline` or
    /// `robot_busy` otherwise.
    pub(super) fn check_assignable(&self, hub: &Hub, robot: &RobotId) -> Result<(), ApiError> {
        let entry = self
            .robots
            .iter()
            .find(|entry| &entry.view.id == robot)
            .ok_or_else(|| ApiError::not_found("Robot", robot.as_str()))?;
        if self.estop_latched.contains(robot) || entry.view.state == RobotStatus::Estop {
            return Err(ApiError::estop_latched(robot.as_str()));
        }
        if !hub.is_connected(robot) {
            return Err(ApiError::conflict(
                "robot_offline",
                format!("Robot {robot} is offline: the task was not sent."),
            ));
        }
        if entry.view.task_id.is_some()
            || matches!(
                entry.view.state,
                RobotStatus::Paused | RobotStatus::Fault | RobotStatus::Busy
            )
        {
            return Err(ApiError::conflict(
                "robot_busy",
                format!(
                    "Robot {robot} is busy, paused or faulty: the task was not sent. Pick another robot or wait."
                ),
            ));
        }
        Ok(())
    }
}

impl MockServices {
    /// Gives `task` to `robot` instead of dispatching it: the robot answers with its own
    /// `task.event`s. A follow is under way at once (each arrival is not a delivery).
    pub(super) fn hand_to_robot(
        &self,
        data: &mut MockData,
        task: &mut TaskView,
        robot: &RobotId,
        now: DateTime<Utc>,
    ) -> Result<(), ApiError> {
        let follow = task.kind == TaskKind::Follow;
        let assign = RobotDown::TaskAssign {
            task_id: task.id.clone(),
            kind: if follow { TaskKind::GoTo } else { task.kind },
            item: task.item.clone(),
            from_place: task.from_place.clone(),
            to_place: task.to_place.clone(),
            deadline: None,
        };
        if let Err(error) = self.hub.send_to_robot(robot, assign) {
            return Err(ApiError::conflict(
                "robot_unreachable",
                format!("{error} The task was not created. Try again."),
            ));
        }
        if let Ok(entry) = data.robot_mut(robot) {
            entry.view.task_id = Some(task.id.clone());
        }
        if let (true, Some(device), Some(until)) = (follow, &task.target_device, task.until) {
            for state in [TaskState::Assigned, TaskState::EnRoute] {
                task.history.push(history(now, "server", state));
            }
            task.state = TaskState::EnRoute;
            task.robot_id = Some(robot.clone());
            data.follows
                .push(Follow::start(task, robot.clone(), device.clone(), until));
        }
        Ok(())
    }

    /// Re-targets every follower whose tablet changed room, and ends the follows that are over
    /// (called by the heartbeat, every second).
    pub(super) fn follow_tick(&self) {
        let now = self.clock.now();
        let mut moves: Vec<(RobotId, TaskId, PlaceId)> = Vec::new();
        let mut ended: Vec<(TaskId, bool)> = Vec::new();
        {
            let mut data = self.data();
            let mut follows = std::mem::take(&mut data.follows);
            follows.retain_mut(|follow| {
                let open = data
                    .tasks
                    .iter()
                    .any(|task| task.id == follow.task && !task.state.is_terminal());
                if !open {
                    return false;
                }
                if now >= follow.until {
                    ended.push((follow.task.clone(), false));
                    return false;
                }
                let state = data
                    .robots
                    .iter()
                    .find(|entry| entry.view.id == follow.robot)
                    .map(|entry| entry.view.state);
                // An emergency-stopped robot ends the follow: it must not hold a fresh target
                // when an admin re-arms it.
                if data.estop_latched.contains(&follow.robot) || state == Some(RobotStatus::Estop) {
                    ended.push((follow.task.clone(), true));
                    return false;
                }
                // Paused or offline: no command is sent; it re-targets once it moves again.
                if state == Some(RobotStatus::Paused) || !self.hub.is_connected(&follow.robot) {
                    return true;
                }
                if let Some(place) = data.tablet_place(&follow.device)
                    && place != follow.target
                {
                    follow.target = place.clone();
                    moves.push((follow.robot.clone(), follow.task.clone(), place));
                }
                true
            });
            data.follows = follows;
        }
        for (robot, task_id, place) in moves {
            self.send_follow_target(&robot, &task_id, &place);
        }
        for (task, stopped) in ended {
            self.end_follow(&task, now, stopped);
        }
    }

    /// Sends the robot to `place`: the old target is dropped, the new one is a `go_to`.
    pub(super) fn send_follow_target(&self, robot: &RobotId, task_id: &TaskId, place: &PlaceId) {
        let cancel = RobotDown::TaskCancel {
            task_id: task_id.clone(),
        };
        let assign = RobotDown::TaskAssign {
            task_id: task_id.clone(),
            kind: TaskKind::GoTo,
            item: None,
            from_place: None,
            to_place: place.clone(),
            deadline: None,
        };
        for message in [cancel, assign] {
            if let Err(error) = self.hub.send_to_robot(robot, message) {
                tracing::warn!(%robot, task = %task_id, %error, "mock follow: target not delivered");
            }
        }
    }

    /// The follow ran its time: the task is delivered, the robot is let go.
    fn end_follow(&self, task_id: &TaskId, now: DateTime<Utc>, stopped: bool) {
        let (done, robot) = {
            let mut data = self.data();
            let Ok(task) = data.task_mut(task_id) else {
                return;
            };
            let next = if stopped {
                TaskState::Failed
            } else {
                TaskState::Delivered
            };
            task.state = next;
            if stopped {
                task.reason = Some("Follow ended: the robot was emergency-stopped.".to_owned());
            }
            task.updated_at = now;
            task.history.push(history(now, "server", next));
            let done = task.clone();
            let robot = data
                .robots
                .iter_mut()
                .find(|robot| robot.view.task_id.as_ref() == Some(task_id))
                .map(|robot| {
                    robot.view.task_id = None;
                    robot.view.id.clone()
                });
            (done, robot)
        };
        if let Some(robot) = &robot {
            let cancel = RobotDown::TaskCancel {
                task_id: task_id.clone(),
            };
            if let Err(error) = self.hub.send_to_robot(robot, cancel) {
                tracing::warn!(%robot, task = %task_id, %error, "mock follow: task.cancel not delivered");
            }
            self.publish_robot(robot);
        }
        self.publish(AppEvent::TaskUpdated { task: done });
        self.dispatch_waiting();
    }
}
