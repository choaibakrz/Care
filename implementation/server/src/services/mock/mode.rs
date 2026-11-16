//! Emergency mode in the mock (Task A8: what fill E1 does on the live server, for real in
//! memory): the switch, the robots cleared from the corridors, no dispatch while it is on,
//! and on exit only the robots the server paused are resumed.
//!
//! The 503 filter itself is the router's (`crate::emergency_mode`), the same for both
//! wirings. The mock keeps the mode and the set of robots it paused in memory only (a
//! restart is back to normal with no robot to resume); the live server stores both
//! (`SystemModeStore`, ruling R26).

use domain::{CommandName, RobotId, RobotStatus, SystemMode, SystemModeState, TaskState};
use realtime::{AlertKind, AppEvent, RobotDown, TaskView};
use security::ClientIdentity;

use super::{MockServices, history_label};
use crate::dto::SetModeRequest;
use crate::error::ApiError;

/// The history line of a task put back in the queue on entry.
pub const HELD_LABEL: &str = "held: emergency mode";

/// What the server does to one robot on entry.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Clearing {
    /// Idle or driving home: `dock`.
    Dock,
    /// A task and nothing in its hands: `task.cancel`, then `dock`.
    CancelThenDock,
    /// Carrying an item (it refuses `dock`): `pause` where it is, remembered.
    Pause,
}

impl MockServices {
    /// `GET /system/mode`.
    pub(super) fn mock_mode(&self) -> SystemModeState {
        self.data().mode.clone()
    }

    /// Whether emergency mode is on.
    pub(super) fn mock_is_emergency(&self) -> bool {
        self.data().mode.is_emergency()
    }

    /// `PUT /system/mode`.
    #[allow(
        clippy::needless_pass_by_value,
        reason = "owned arguments keep the call sites simple"
    )]
    pub(super) fn mock_set_mode(
        &self,
        actor: &ClientIdentity,
        request: SetModeRequest,
    ) -> Result<SystemModeState, ApiError> {
        let reason = domain::check_mode_reason(request.reason.as_deref())
            .map_err(|why| ApiError::invalid_input("reason", &why))?;
        let now = self.clock.now();
        let by = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        let (from, state) = {
            let mut data = self.data();
            if data.mode.mode == request.mode {
                // Idempotent: two admins pressing at once is fine.
                return Ok(data.mode.clone());
            }
            let from = data.mode.mode;
            data.mode = SystemModeState {
                mode: request.mode,
                since: Some(now),
                by: Some(by.clone()),
                reason: reason.clone(),
            };
            (from, data.mode.clone())
        };
        let detail = format!(
            "{} -> {}{}",
            mode_name(from),
            mode_name(request.mode),
            reason
                .as_ref()
                .map_or_else(String::new, |reason| format!(" ({reason})"))
        );
        self.push_audit(
            actor,
            "system_mode_changed",
            "system",
            Some(detail),
            "system",
        );
        match request.mode {
            SystemMode::Emergency => self.clear_corridors(),
            SystemMode::Normal => self.restore_robots(),
        }
        self.publish(AppEvent::ModeUpdated {
            mode: state.clone(),
        });
        let (kind, message) = match request.mode {
            SystemMode::Emergency => (
                AlertKind::EmergencyModeOn,
                "Emergency mode is on: only emergency actions are accepted. Robots are going to their docks.",
            ),
            SystemMode::Normal => (
                AlertKind::EmergencyModeOff,
                "Emergency mode is off: the clinic is back to normal operation.",
            ),
        };
        self.publish(AppEvent::Alert {
            level: kind.level(),
            kind,
            message: message.to_owned(),
            command: None,
        });
        Ok(state)
    }

    /// Entry: every connected robot leaves the corridors (`emergency-mode.md`, "What happens
    /// to robots and tasks"). Robots in `estop`, `fault` or already `paused` are left alone.
    fn clear_corridors(&self) {
        let now = self.clock.now();
        let (plan, requeued) = {
            let mut data = self.data();
            let mut plan: Vec<(RobotId, Clearing, Option<domain::TaskId>)> = Vec::new();
            for robot in &data.robots {
                // Left alone: estop, fault, and a robot already paused (a staff pause stays a
                // staff pause: never remembered, never resumed by the server; R26). Charging
                // is not modelled (`RobotStatus` has no such state).
                if !self.hub.is_connected(&robot.view.id)
                    || matches!(
                        robot.view.state,
                        RobotStatus::Estop | RobotStatus::Fault | RobotStatus::Paused
                    )
                {
                    continue;
                }
                let action = if robot.view.holding.is_some() {
                    Clearing::Pause
                } else if robot.view.task_id.is_some() {
                    Clearing::CancelThenDock
                } else {
                    Clearing::Dock
                };
                plan.push((robot.view.id.clone(), action, robot.view.task_id.clone()));
            }
            let mut requeued: Vec<TaskView> = Vec::new();
            for (robot, action, task) in &plan {
                match action {
                    Clearing::Pause => {
                        data.paused_by_emergency.insert(robot.clone());
                    }
                    Clearing::CancelThenDock => {
                        if let Ok(entry) = data.robot_mut(robot) {
                            entry.view.task_id = None;
                        }
                        if let Some(task) = task
                            && let Ok(view) = data.task_mut(task)
                            && !view.state.is_terminal()
                        {
                            // A follow is not queued: emergency mode ends it.
                            view.state = if view.kind == domain::TaskKind::Follow {
                                TaskState::Cancelled
                            } else {
                                TaskState::Requested
                            };
                            view.robot_id = None;
                            view.updated_at = now;
                            view.history.push(history_label(now, "server", HELD_LABEL));
                            requeued.push(view.clone());
                        }
                    }
                    Clearing::Dock => {}
                }
            }
            (plan, requeued)
        };
        for (robot, action, task) in plan {
            match action {
                Clearing::Pause => {
                    if !self.server_command(&robot, CommandName::Pause) {
                        self.data().paused_by_emergency.remove(&robot);
                    }
                }
                Clearing::CancelThenDock => {
                    if let Some(task_id) = task
                        && let Err(error) = self
                            .hub
                            .send_to_robot(&robot, RobotDown::TaskCancel { task_id })
                    {
                        tracing::warn!(%robot, %error, "mock: task.cancel not delivered on emergency entry");
                    }
                    self.server_command(&robot, CommandName::Dock);
                }
                Clearing::Dock => {
                    self.server_command(&robot, CommandName::Dock);
                }
            }
        }
        for task in requeued {
            self.publish(AppEvent::TaskUpdated { task });
        }
    }

    /// Exit: `resume` only the robots the server paused on entry (and still not in
    /// emergency stop), then hand out the queue again.
    fn restore_robots(&self) {
        let paused: Vec<RobotId> = {
            let mut data = self.data();
            let paused = std::mem::take(&mut data.paused_by_emergency);
            paused
                .into_iter()
                .filter(|robot| !data.estop_latched.contains(robot))
                .collect()
        };
        for robot in paused {
            self.server_command(&robot, CommandName::Resume);
        }
        self.dispatch_waiting();
    }

    /// Sends a command on the server's own behalf (no permission, no `staff_command` alert).
    /// A refusal is not retried: it is shown in an `alert` (`command_refused`) and an audit
    /// row. Returns whether it was sent.
    fn server_command(&self, robot: &RobotId, name: CommandName) -> bool {
        match self.hub.send_to_robot(robot, RobotDown::Command { name }) {
            Ok(()) => {
                if let Ok(entry) = self.data().robot_mut(robot) {
                    entry.view.state = match name {
                        CommandName::Pause => RobotStatus::Paused,
                        CommandName::Resume if entry.view.task_id.is_some() => RobotStatus::Busy,
                        CommandName::Resume | CommandName::Dock => RobotStatus::Idle,
                        CommandName::Estop | CommandName::Shutdown => entry.view.state,
                    };
                }
                self.publish_robot(robot);
                true
            }
            Err(error) => {
                let command = super::wire_name(&name);
                self.publish(AppEvent::Alert {
                    level: AlertKind::CommandRefused.level(),
                    kind: AlertKind::CommandRefused,
                    message: format!(
                        "Robot {robot} did not take the {command} command of emergency mode ({error}). It was not sent again."
                    ),
                    command: None,
                });
                self.push_system_audit(
                    "robot_command_refused",
                    robot.as_str(),
                    format!("{command} (emergency mode): {error}"),
                );
                false
            }
        }
    }
}

fn mode_name(mode: SystemMode) -> &'static str {
    match mode {
        SystemMode::Normal => "normal",
        SystemMode::Emergency => "emergency",
    }
}
