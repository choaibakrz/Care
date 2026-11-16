//! Real `TaskService`; also the scheduler's `TaskCreator`.
//!
//! The requester's owner label and the state history are kept in memory next to the stored
//! task (the task table has no column for them). After a restart a task's history is
//! rebuilt from its timestamps.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, PoisonError};

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use chrono::{DateTime, Utc};
use domain::ports::{StockLedger, TaskRepository};
use domain::{
    Actor, ApplyOutcome, Clock, DomainError, FailureReason, Page, Permission, PlaceId, Reservation,
    RobotId, Role, ScheduleId, Task, TaskFilter, TaskId, TaskKind, TaskParts, TaskState,
};
use locations::ClinicMap;
use realtime::{AlertKind, AppEvent, Hub, RobotDown, TaskHistoryEntry, requester_label};
use scheduler::{SchedulerError, TaskCreator};
use security::ClientIdentity;
use uuid::Uuid;

use super::assignment::{AssignOutcome, AssignmentService};
use super::{InventoryService, TaskService};
use crate::dto::{NewTask, TaskPage, TaskView};
use crate::error::ApiError;

/// What `RealTaskService` needs.
pub struct TaskDeps {
    /// Tasks.
    pub repo: Arc<dyn TaskRepository>,
    /// Stock reservations.
    pub ledger: Arc<dyn StockLedger>,
    /// Delivery hook.
    pub inventory: Arc<dyn InventoryService>,
    /// Dispatch.
    pub assignment: Arc<AssignmentService>,
    /// Map (place validation).
    pub map: Arc<ClinicMap>,
    /// Journal.
    pub journal: Journal,
    /// Hub (`task.updated`).
    pub hub: Arc<Hub>,
    /// Clock.
    pub clock: Arc<dyn Clock>,
}

/// What the store does not keep: labels, history, reservations.
#[derive(Default)]
struct Memo {
    labels: HashMap<TaskId, String>,
    history: HashMap<TaskId, Vec<TaskHistoryEntry>>,
    reservations: HashMap<TaskId, Reservation>,
}

/// The real task service.
pub struct RealTaskService {
    deps: TaskDeps,
    memo: Mutex<Memo>,
}

/// The label of an actor in a history line.
fn actor_label(actor: &Actor, owner: Option<&str>) -> String {
    match (actor, owner) {
        (Actor::User(_) | Actor::Device(_), Some(owner)) => owner.to_owned(),
        _ => requester_label(actor, None),
    }
}

impl RealTaskService {
    /// A service.
    #[must_use]
    pub fn new(deps: TaskDeps) -> RealTaskService {
        RealTaskService {
            deps,
            memo: Mutex::new(Memo::default()),
        }
    }

    /// A reconnecting robot says it is still running `task` (its word is the truth on
    /// reconnect): a task the server put back in the queue meanwhile is given back to it,
    /// without sending `task.assign` again. Anything else is left alone.
    ///
    /// # Errors
    /// Store or journal failures.
    async fn resume_task(&self, robot: &RobotId, task: &TaskId) -> Result<(), ApiError> {
        let Some(mut stored) = self.deps.repo.get(task).await? else {
            return Ok(());
        };
        if stored.state() != TaskState::Requested {
            return Ok(());
        }
        let now = self.deps.clock.now();
        stored.assign_to(robot.clone(), now)?;
        self.deps.repo.update(&stored).await?;
        self.remember(task, now, "server".to_owned(), TaskState::Assigned);
        self.journal_state(
            Actor::System("server"),
            task,
            TaskState::Requested,
            TaskState::Assigned,
            None,
        )
        .await?;
        self.publish(&self.view(&stored));
        Ok(())
    }

    fn memo(&self) -> std::sync::MutexGuard<'_, Memo> {
        self.memo.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Appends a history line.
    fn remember(&self, task: &TaskId, at: DateTime<Utc>, actor: String, state: TaskState) {
        self.memo()
            .history
            .entry(task.clone())
            .or_default()
            .push(TaskHistoryEntry {
                at,
                actor,
                label: state.to_string(),
            });
    }

    /// The wire view of a stored task.
    fn view(&self, task: &Task) -> TaskView {
        let memo = self.memo();
        let label = memo
            .labels
            .get(task.id())
            .cloned()
            .unwrap_or_else(|| requester_label(task.requested_by(), None));
        let history = memo.history.get(task.id()).cloned().unwrap_or_else(|| {
            let mut lines = vec![TaskHistoryEntry {
                at: task.created_at(),
                actor: label.clone(),
                label: TaskState::Requested.to_string(),
            }];
            if task.state() != TaskState::Requested {
                lines.push(TaskHistoryEntry {
                    at: task.updated_at(),
                    actor: "server".to_owned(),
                    label: task.state().to_string(),
                });
            }
            lines
        });
        drop(memo);
        TaskView::new(task, label, history)
    }

    async fn load(&self, id: &TaskId) -> Result<Task, ApiError> {
        self.deps
            .repo
            .get(id)
            .await?
            .ok_or_else(|| ApiError::not_found("Task", id.as_str()))
    }

    fn publish(&self, view: &TaskView) {
        self.deps
            .hub
            .publish(AppEvent::TaskUpdated { task: view.clone() });
    }

    async fn journal_state(
        &self,
        actor: Actor,
        task: &TaskId,
        from: TaskState,
        to: TaskState,
        reason: Option<FailureReason>,
    ) -> Result<(), ApiError> {
        let category = if matches!(actor, Actor::Robot(_)) {
            Category::Robot
        } else {
            Category::Audit
        };
        self.deps
            .journal
            .append(
                Severity::Info,
                category,
                actor,
                RecordBody::TaskStateChanged {
                    task: task.clone(),
                    from,
                    to,
                    reason,
                },
                None,
            )
            .await?;
        Ok(())
    }

    /// Releases the task's reservation, if it holds one (an expired one is fine).
    async fn release(&self, task: &TaskId) {
        let held = self.memo().reservations.remove(task);
        if let Some(reservation) = held
            && let Err(error) = self.deps.ledger.release(&reservation).await
        {
            tracing::debug!(%task, %error, "reservation already gone");
        }
    }

    /// Dispatches a stored task and records the outcome in the history.
    async fn dispatch(&self, task: &Task) -> Task {
        match self.deps.assignment.assign(task).await {
            Ok(AssignOutcome::Sent { robot }) => {
                self.remember(
                    task.id(),
                    self.deps.clock.now(),
                    "server".to_owned(),
                    TaskState::Assigned,
                );
                tracing::info!(task = %task.id(), %robot, "task assigned");
            }
            Ok(AssignOutcome::HandedToHuman { explanation }) => {
                tracing::info!(task = %task.id(), %explanation, "no robot fits; human needed");
            }
            Err(error) => {
                tracing::warn!(task = %task.id(), code = error.code(), "dispatch failed; task stays queued");
            }
        }
        match self.deps.repo.get(task.id()).await {
            Ok(Some(fresh)) => fresh,
            _ => task.clone(),
        }
    }

    /// The shared create path.
    async fn create_with(
        &self,
        actor: Actor,
        label: String,
        by_admin: bool,
        new: NewTask,
    ) -> Result<TaskView, ApiError> {
        if (new.robot_id.is_some() || new.target_device.is_some()) && !by_admin {
            return Err(ApiError::forbidden(Permission::RobotShutdown));
        }
        if new.kind == TaskKind::Follow && new.robot_id.is_none() {
            return Err(ApiError::invalid_input(
                "robot_id",
                "is required for a follow task",
            ));
        }
        let direct = new.robot_id.clone();
        let draft = new.into_draft()?;
        for (field, place) in [
            ("from_place", draft.from.as_ref()),
            ("to_place", Some(&draft.to)),
        ] {
            if let Some(place) = place
                && self.deps.map.place(place).is_none()
            {
                return Err(ApiError::invalid_input(
                    field,
                    &format!("'{place}' is not a place on the clinic map (see GET /map)"),
                ));
            }
        }
        let now = self.deps.clock.now();
        let id: TaskId = format!("t-{}", Uuid::new_v4().simple()).parse()?;
        let task = Task::new(id.clone(), draft, actor.clone(), now)?;
        let reservation = match (task.kind(), task.item()) {
            (TaskKind::Fetch, Some(item)) => Some(self.deps.ledger.reserve(&id, item, 1).await?),
            _ => None,
        };
        if let Err(error) = self.deps.repo.insert(&task).await {
            if let Some(reservation) = &reservation
                && let Err(release) = self.deps.ledger.release(reservation).await
            {
                tracing::warn!(task = %id, error = %release, "reservation not released");
            }
            return Err(error.into());
        }
        {
            let mut memo = self.memo();
            memo.labels.insert(id.clone(), label.clone());
            if let Some(reservation) = reservation {
                memo.reservations.insert(id.clone(), reservation);
            }
        }
        self.remember(&id, now, label, TaskState::Requested);
        self.deps
            .journal
            .append(
                Severity::Info,
                Category::Audit,
                actor,
                RecordBody::TaskCreated {
                    task: id.clone(),
                    kind: task.kind(),
                    item: task.item().cloned(),
                    to: task.to().clone(),
                },
                None,
            )
            .await?;
        self.publish(&self.view(&task));
        let task = match direct {
            Some(robot) => self.give_to(task, &robot).await?,
            None => self.dispatch(&task).await,
        };
        let view = self.view(&task);
        self.publish(&view);
        Ok(view)
    }

    /// Admin path: hands the task to one robot without the dispatcher.
    ///
    /// A robot already holding an active task is refused (409 `robot_busy`, the task is
    /// cancelled): it would answer `failed` at once. The assignment is stored before the order
    /// leaves, so the robot's immediate answer finds the task assigned to it (it used to be
    /// dropped as "not this robot's task", leaving the task `assigned` forever).
    async fn give_to(&self, mut task: Task, robot: &RobotId) -> Result<Task, ApiError> {
        let busy_with = self
            .active()
            .await?
            .into_iter()
            .find(|view| {
                view.id != *task.id()
                    && view.robot_id.as_ref() == Some(robot)
                    && matches!(view.state, TaskState::Assigned | TaskState::EnRoute)
            })
            .map(|view| view.id);
        if let Some(other) = busy_with {
            self.cancel_undelivered(&mut task).await;
            return Err(ApiError::conflict(
                "robot_busy",
                format!(
                    "Robot {robot} is busy with task {other}. Wait until it is done, or send it to its dock first."
                ),
            ));
        }
        let now = self.deps.clock.now();
        task.assign_to(robot.clone(), now)?;
        self.deps.repo.update(&task).await?;
        let sent = self.deps.hub.send_to_robot(
            robot,
            RobotDown::TaskAssign {
                task_id: task.id().clone(),
                kind: task.kind(),
                item: task.item().cloned(),
                from_place: task.from().cloned(),
                to_place: task.to().clone(),
                deadline: task.deadline(),
            },
        );
        if let Err(error) = sent {
            self.cancel_undelivered(&mut task).await;
            return Err(error.into());
        }
        self.remember(task.id(), now, "server".to_owned(), TaskState::Assigned);
        self.journal_state(
            Actor::System("server"),
            task.id(),
            TaskState::Requested,
            TaskState::Assigned,
            None,
        )
        .await?;
        Ok(task)
    }

    /// A task that never reached its robot: cancelled, its stock hold released, published.
    async fn cancel_undelivered(&self, task: &mut Task) {
        let now = self.deps.clock.now();
        if task.transition(TaskState::Cancelled, None, now).is_err() {
            return;
        }
        if let Err(error) = self.deps.repo.update(task).await {
            tracing::warn!(task = %task.id(), %error, "undelivered task not cancelled");
        }
        self.release(task.id()).await;
        self.remember(task.id(), now, "server".to_owned(), TaskState::Cancelled);
        self.publish(&self.view(task));
    }
}

#[async_trait]
impl TaskService for RealTaskService {
    async fn create(&self, actor: &ClientIdentity, new: NewTask) -> Result<TaskView, ApiError> {
        let subject = actor.verified.subject_id.clone();
        let owner = actor.verified.owner.as_ref().map(ToString::to_string);
        let label = actor_label(&subject, owner.as_deref());
        let by_admin = actor.verified.role == Role::Admin;
        self.create_with(subject, label, by_admin, new).await
    }
    async fn create_as_system(&self, actor: Actor, new: NewTask) -> Result<TaskView, ApiError> {
        if !matches!(actor, Actor::System(_)) {
            return Err(ApiError::internal(
                "task created as system by a non-system actor",
            ));
        }
        let label = requester_label(&actor, None);
        self.create_with(actor, label, false, new).await
    }
    async fn get(&self, id: &TaskId) -> Result<TaskView, ApiError> {
        let task = self.load(id).await?;
        Ok(self.view(&task))
    }
    async fn list(&self, filter: TaskFilter, page: Page) -> Result<TaskPage, ApiError> {
        let tasks = self.deps.repo.list(&filter, &page).await?;
        let full = u32::try_from(tasks.len()).is_ok_and(|count| count >= page.limit());
        let items = tasks.iter().map(|task| self.view(task)).collect();
        Ok(TaskPage {
            items,
            next: full.then(|| page.offset().saturating_add(page.limit())),
        })
    }
    async fn active(&self) -> Result<Vec<TaskView>, ApiError> {
        let filter = TaskFilter {
            active_only: true,
            ..TaskFilter::default()
        };
        let page = Page::new(Page::MAX_LIMIT, 0)?;
        Ok(self.list(filter, page).await?.items)
    }
    async fn cancel(&self, actor: &ClientIdentity, id: &TaskId) -> Result<TaskView, ApiError> {
        let mut task = self.load(id).await?;
        let subject = actor.verified.subject_id.clone();
        if actor.verified.role != Role::Admin && task.requested_by() != &subject {
            return Err(ApiError::forbidden(Permission::CancelTask));
        }
        let from = task.state();
        if !matches!(from, TaskState::Requested | TaskState::Assigned) {
            return Err(ApiError::conflict(
                "task_not_cancellable",
                format!("Task '{id}' is {from} and can no longer be cancelled."),
            ));
        }
        let now = self.deps.clock.now();
        task.transition(TaskState::Cancelled, None, now)?;
        self.deps.repo.update(&task).await?;
        self.release(id).await;
        if let Some(robot) = task.assigned_robot()
            && let Err(error) = self.deps.hub.send_to_robot(
                robot,
                RobotDown::TaskCancel {
                    task_id: id.clone(),
                },
            )
        {
            tracing::warn!(%robot, task = %id, %error, "task.cancel not delivered");
        }
        let owner = actor.verified.owner.as_ref().map(ToString::to_string);
        self.remember(
            id,
            now,
            actor_label(&subject, owner.as_deref()),
            TaskState::Cancelled,
        );
        self.journal_state(subject, id, from, TaskState::Cancelled, None)
            .await?;
        let view = self.view(&task);
        self.publish(&view);
        Ok(view)
    }
    async fn apply_robot_event(
        &self,
        robot: &RobotId,
        event_id: Uuid,
        task: &TaskId,
        state: TaskState,
        reason: Option<FailureReason>,
    ) -> Result<ApplyOutcome, ApiError> {
        let mut stored = self.load(task).await?;
        if stored.assigned_robot() != Some(robot) {
            // A task taken back (cancelled, requeued) is not taken again by a late event.
            tracing::debug!(%robot, %task, "event for a task this robot does not hold ignored");
            return Ok(ApplyOutcome::Duplicate);
        }
        let from = stored.state();
        if from == state {
            return Ok(ApplyOutcome::Duplicate);
        }
        let now = self.deps.clock.now();
        stored.transition(state, reason, now)?;
        let decrement = match (state, stored.item()) {
            (TaskState::Delivered, Some(item)) if stored.kind() == TaskKind::Fetch => {
                Some((item, 1))
            }
            _ => None,
        };
        // Release the hold first, so the decrement does not count it twice.
        if state.is_terminal() {
            self.release(task).await;
        }
        let outcome = self
            .deps
            .repo
            .apply_robot_event(event_id, &stored, decrement)
            .await?;
        if outcome == ApplyOutcome::Duplicate {
            return Ok(outcome);
        }
        if state == TaskState::Delivered {
            self.deps.inventory.on_delivered(&stored).await?;
        }
        self.remember(task, now, format!("robot:{robot}"), state);
        self.journal_state(Actor::Robot(robot.clone()), task, from, state, reason)
            .await?;
        self.publish(&self.view(&stored));
        Ok(outcome)
    }
    async fn on_robot_resumed(&self, robot: &RobotId, task: &TaskId) -> Result<(), ApiError> {
        self.resume_task(robot, task).await
    }
    async fn on_robot_lost(&self, robot: &RobotId) -> Result<Vec<TaskId>, ApiError> {
        let filter = TaskFilter {
            robot: Some(robot.clone()),
            active_only: true,
            ..TaskFilter::default()
        };
        let tasks = self
            .deps
            .repo
            .list(&filter, &Page::new(Page::MAX_LIMIT, 0)?)
            .await?;
        let now = self.deps.clock.now();
        let mut touched = Vec::new();
        for task in tasks {
            match task.state() {
                TaskState::Assigned => {
                    let requeued = requeue(&task, now)?;
                    self.deps.repo.update(&requeued).await?;
                    self.remember(task.id(), now, "server".to_owned(), TaskState::Requested);
                    self.journal_state(
                        Actor::System("server"),
                        task.id(),
                        TaskState::Assigned,
                        TaskState::Requested,
                        None,
                    )
                    .await?;
                    let fresh = self.dispatch(&requeued).await;
                    self.publish(&self.view(&fresh));
                    touched.push(task.id().clone());
                }
                TaskState::EnRoute => {
                    let mut flagged = task.clone();
                    flagged.mark_needs_human(
                        format!(
                            "Robot {robot} was lost while carrying this task; a human is needed."
                        ),
                        now,
                    );
                    self.deps.repo.update(&flagged).await?;
                    self.deps.hub.publish(AppEvent::Alert {
                        level: AlertKind::TaskNeedsHuman.level(),
                        kind: AlertKind::TaskNeedsHuman,
                        message: format!(
                            "Robot {robot} was lost with task {} en route; a human must take over.",
                            task.id()
                        ),
                        command: None,
                    });
                    self.publish(&self.view(&flagged));
                    touched.push(task.id().clone());
                }
                _ => {}
            }
        }
        Ok(touched)
    }
}

/// The task back in the queue (`assigned` -> `requested` is not a state-machine step: the
/// robot never started, so the task is rebuilt as requested).
fn requeue(task: &Task, at: DateTime<Utc>) -> Result<Task, DomainError> {
    Task::restore(TaskParts {
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
        needs_human: None,
        created_at: task.created_at(),
        updated_at: at,
    })
}

#[async_trait]
impl TaskCreator for RealTaskService {
    async fn create_restock_round(&self, places: &[PlaceId]) -> Result<TaskId, SchedulerError> {
        let Some(last) = places.last() else {
            return Err(SchedulerError::Repository(DomainError::MissingTaskField {
                kind: "restock_round",
                field: "places",
            }));
        };
        let new = NewTask {
            kind: TaskKind::RestockRound,
            item: None,
            from_place: places.first().cloned(),
            to_place: Some(last.clone()),
            deadline: None,
            robot_id: None,
            target_device: None,
        };
        match self.create_as_system(Actor::System("scheduler"), new).await {
            Ok(view) => Ok(view.id),
            Err(error) => {
                tracing::warn!(
                    code = error.code(),
                    message = error.message(),
                    "restock round not created"
                );
                Err(SchedulerError::Repository(DomainError::StoreUnavailable {
                    what: "task",
                }))
            }
        }
    }
    async fn report_missed(&self, schedule: &ScheduleId, scheduled_for: DateTime<Utc>) {
        if let Err(error) = self
            .deps
            .journal
            .append(
                Severity::Warning,
                Category::System,
                Actor::System("scheduler"),
                RecordBody::ScheduleMissed {
                    schedule: schedule.clone(),
                    scheduled_for,
                },
                None,
            )
            .await
        {
            tracing::error!(%schedule, %error, "missed schedule not journaled");
        }
        self.deps.hub.publish(AppEvent::Alert {
            level: AlertKind::ScheduleMissed.level(),
            kind: AlertKind::ScheduleMissed,
            message: format!(
                "Schedule '{schedule}' did not run at {scheduled_for}: the server was not running then."
            ),
            command: None,
        });
    }
}
