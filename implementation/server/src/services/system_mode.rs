//! Real `SystemModeService` (Task A8, fill E1): the emergency switch, stored so a restart
//! keeps an emergency on.
//!
//! The mode in force lives in a `watch` channel: the router's emergency filter reads it on
//! every request ([`SystemModeService::is_emergency`]), the assignment service and the
//! scheduler subscribe to it ([`RealSystemModeService::subscribe`]) so no task is handed out
//! and no night round starts while it is on (E1).

use std::collections::{BTreeSet, HashSet};
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use domain::ports::{StoredSystemMode, SystemModeStore, TaskRepository};
use domain::{
    Actor, Clock, CommandName, RobotId, RobotStatus, SystemMode, SystemModeState, Task, TaskId,
    TaskParts, TaskState,
};
use realtime::{AlertKind, AppEvent, Hub, RobotDown};
use security::ClientIdentity;
use tokio::sync::watch;
use uuid::Uuid;

use super::{RobotService, SystemModeService};
use crate::dto::SetModeRequest;
use crate::error::ApiError;

/// The mark of a task put back in the queue on entry.
pub const HELD_LABEL: &str = "held: emergency mode";

/// What the real switch needs.
pub struct SystemModeDeps {
    /// Where the mode is stored (one row).
    pub store: Arc<dyn SystemModeStore>,
    /// The robots, their commands and states (clearing the corridors).
    pub robots: Arc<dyn RobotService>,
    /// The tasks put back in the queue on entry.
    pub tasks: Arc<dyn TaskRepository>,
    /// `mode.updated` and `alert`.
    pub hub: Arc<Hub>,
    /// `system_mode_changed`, refused robot commands.
    pub journal: Journal,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
}

/// The emergency switch of the live server.
pub struct RealSystemModeService {
    deps: SystemModeDeps,
    state: watch::Sender<SystemModeState>,
    /// The robots the server paused on entry (only they are resumed on exit); stored with
    /// the mode (`StoredSystemMode.paused_robots`, ruling R26) and loaded by `bootstrap`.
    paused: Mutex<HashSet<RobotId>>,
}

impl RealSystemModeService {
    /// Normal operation until [`RealSystemModeService::bootstrap`] loads the stored mode.
    #[must_use]
    pub fn new(deps: SystemModeDeps) -> RealSystemModeService {
        let (state, _) = watch::channel(SystemModeState::initial());
        RealSystemModeService {
            deps,
            state,
            paused: Mutex::new(HashSet::new()),
        }
    }

    /// Loads the stored mode (a restart keeps an emergency on). `Wiring::finish` must await
    /// it before the server serves anything (E1 adds it to the pending start).
    ///
    /// # Errors
    /// `unavailable` when the store cannot be read.
    pub async fn bootstrap(&self) -> Result<(), ApiError> {
        let stored = self
            .deps
            .store
            .load()
            .await
            .map_err(|_| ApiError::unavailable("system mode store"))?;
        self.state.send_replace(stored.state);
        if let Ok(mut paused) = self.paused.lock() {
            *paused = stored.paused_robots.into_iter().collect();
        }
        Ok(())
    }

    /// The mode in force and its changes (the assignment service and the scheduler hold
    /// back while it is `emergency`).
    #[must_use]
    pub fn subscribe(&self) -> watch::Receiver<SystemModeState> {
        self.state.subscribe()
    }

    /// Entry: docks free robots, cancels and requeues running tasks then docks, pauses
    /// robots holding an item. Returns the robots it paused.
    async fn clear_corridors(&self) -> BTreeSet<RobotId> {
        let mut paused = BTreeSet::new();
        let robots = match self.deps.robots.list().await {
            Ok(robots) => robots,
            Err(error) => {
                tracing::warn!(
                    error = error.message(),
                    "emergency mode: robots could not be listed"
                );
                return paused;
            }
        };
        for robot in robots {
            // Left alone: offline, estop, fault, and a robot already paused (a staff pause
            // stays a staff pause: never remembered, never resumed by the server; R26).
            if !robot.connected
                || matches!(
                    robot.state,
                    RobotStatus::Estop | RobotStatus::Fault | RobotStatus::Paused
                )
            {
                continue;
            }
            if robot.holding.is_some() {
                if self.server_command(&robot.id, CommandName::Pause).await {
                    paused.insert(robot.id.clone());
                }
                continue;
            }
            if let Some(task_id) = robot.task_id.clone() {
                if let Err(error) = self.deps.hub.send_to_robot(
                    &robot.id,
                    RobotDown::TaskCancel {
                        task_id: task_id.clone(),
                    },
                ) {
                    tracing::warn!(robot = %robot.id, %error, "task.cancel not delivered on emergency entry");
                }
                self.requeue(&task_id).await;
            }
            self.server_command(&robot.id, CommandName::Dock).await;
        }
        paused
    }

    /// Puts a task back in the queue (`requested`, no robot), marked `held: emergency mode`.
    async fn requeue(&self, id: &TaskId) {
        let task = match self.deps.tasks.get(id).await {
            Ok(Some(task)) if !task.state().is_terminal() => task,
            Ok(_) => return,
            Err(error) => {
                tracing::warn!(%error, task = %id, "emergency mode: task not read");
                return;
            }
        };
        let parts = TaskParts {
            id: task.id().clone(),
            kind: task.kind(),
            item: task.item().cloned(),
            from: task.from().cloned(),
            to: task.to().clone(),
            deadline: task.deadline(),
            state: TaskState::Requested,
            requested_by: task.requested_by().clone(),
            assigned_robot: None,
            failure: None,
            needs_human: Some(HELD_LABEL.to_owned()),
            created_at: task.created_at(),
            updated_at: self.deps.clock.now(),
        };
        let result = match Task::restore(parts) {
            Ok(requeued) => self.deps.tasks.update(&requeued).await,
            Err(error) => Err(error),
        };
        if let Err(error) = result {
            tracing::warn!(%error, task = %id, "emergency mode: task not requeued");
        }
    }

    /// Exit: resumes only the robots the server paused, never one in emergency stop (R24).
    async fn restore_robots(&self) {
        let paused: Vec<RobotId> = self
            .paused
            .lock()
            .map(|mut set| set.drain().collect())
            .unwrap_or_default();
        let estopped: HashSet<RobotId> = self
            .deps
            .robots
            .list()
            .await
            .unwrap_or_default()
            .into_iter()
            .filter(|robot| robot.state == RobotStatus::Estop)
            .map(|robot| robot.id)
            .collect();
        for robot in paused {
            if !estopped.contains(&robot) {
                self.server_command(&robot, CommandName::Resume).await;
            }
        }
    }

    /// Sends a server command; a refusal is journaled and alerted, never retried.
    async fn server_command(&self, robot: &RobotId, name: CommandName) -> bool {
        let Err(error) = self
            .deps
            .hub
            .send_to_robot(robot, RobotDown::Command { name })
        else {
            return true;
        };
        self.deps.hub.publish(AppEvent::Alert {
            level: AlertKind::CommandRefused.level(),
            kind: AlertKind::CommandRefused,
            message: format!(
                "Robot {robot} did not take the {name:?} command of emergency mode ({error}). It was not sent again."
            ),
            command: None,
        });
        if let Err(error) = self
            .deps
            .journal
            .append(
                Severity::Warning,
                Category::Robot,
                Actor::System("server"),
                RecordBody::RobotCommandSent {
                    robot: robot.clone(),
                    command: name,
                    delivered: false,
                    command_id: Uuid::new_v4(),
                },
                None,
            )
            .await
        {
            tracing::warn!(%error, "refused command not journaled");
        }
        false
    }
}

#[async_trait]
impl SystemModeService for RealSystemModeService {
    async fn mode(&self) -> Result<SystemModeState, ApiError> {
        Ok(self.state.borrow().clone())
    }

    async fn set_mode(
        &self,
        actor: &ClientIdentity,
        request: SetModeRequest,
    ) -> Result<SystemModeState, ApiError> {
        let reason = domain::check_mode_reason(request.reason.as_deref())
            .map_err(|why| ApiError::invalid_input("reason", &why))?;
        let current = self.state.borrow().clone();
        if current.mode == request.mode {
            // Idempotent: two admins pressing at once is fine.
            return Ok(current);
        }
        let by = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        let state = SystemModeState {
            mode: request.mode,
            since: Some(self.deps.clock.now()),
            by: Some(by),
            reason: reason.clone(),
        };
        // The filter and the dispatcher see the new mode before the robots are moved.
        self.state.send_replace(state.clone());
        let paused = match request.mode {
            SystemMode::Emergency => self.clear_corridors().await,
            SystemMode::Normal => {
                self.restore_robots().await;
                BTreeSet::new()
            }
        };
        self.deps
            .store
            .save(&StoredSystemMode {
                state: state.clone(),
                paused_robots: paused.clone(),
            })
            .await?;
        if let Ok(mut set) = self.paused.lock() {
            *set = paused.into_iter().collect();
        }
        if let Err(error) = self
            .deps
            .journal
            .append(
                Severity::Notice,
                Category::System,
                actor.verified.subject_id.clone(),
                RecordBody::SystemModeChanged {
                    from: current.mode,
                    to: request.mode,
                    reason,
                },
                None,
            )
            .await
        {
            tracing::warn!(%error, "system mode change not journaled");
        }
        self.deps.hub.publish(AppEvent::ModeUpdated {
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
        self.deps.hub.publish(AppEvent::Alert {
            level: kind.level(),
            kind,
            message: message.to_owned(),
            command: None,
        });
        Ok(state)
    }

    fn is_emergency(&self) -> bool {
        self.state.borrow().is_emergency()
    }
}
