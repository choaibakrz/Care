//! Tasks and their state machine: the six states of `clinique/taches.py`, plus `cancelled`
//! (an intentional difference, see `docs/task-states.md`).

use std::fmt;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::actor::Actor;
use crate::error::DomainError;
use crate::ids::{ItemId, PlaceId, RobotId, TaskId, UserId};

/// Task state (`demandée`, `attribuée`, `en route`, `livrée`, `échouée`, `reprise`), plus
/// `cancelled`, which the Python states do not have.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    /// Created, waiting for a robot (or a human).
    Requested,
    /// Sent to a robot.
    Assigned,
    /// The robot is carrying it.
    EnRoute,
    /// Done.
    Delivered,
    /// Failed; `FailureReason` says why.
    Failed,
    /// Resumed after a failure or a handover.
    Resumed,
    /// Cancelled by an admin or the requester. Terminal; reachable only from `requested` and
    /// `assigned` (a task en route cannot be cancelled).
    Cancelled,
}

impl TaskState {
    /// Whether the state machine allows `self -> next`.
    #[must_use]
    pub fn can_go_to(self, next: TaskState) -> bool {
        use TaskState::{Assigned, Cancelled, Delivered, EnRoute, Failed, Requested, Resumed};
        // The only place that decides what is allowed. See docs/task-states.md.
        matches!(
            (self, next),
            (Requested, Assigned | Failed | Cancelled)
                | (Assigned, EnRoute | Failed | Cancelled)
                | (EnRoute, Delivered | Failed)
                | (Failed, Resumed)
                | (Resumed, Assigned | EnRoute | Delivered | Failed)
        )
    }

    /// Whether the task is finished for now (`delivered`, `failed` or `cancelled`).
    ///
    /// Warning: `failed` is terminal here but `failed -> resumed` is allowed, so a task for which
    /// this returns true can still change. For "can never change again" checks (for example a
    /// dispatcher deciding which tasks to skip), use [`TaskState::is_closed`].
    #[must_use]
    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            TaskState::Delivered | TaskState::Failed | TaskState::Cancelled
        )
    }
}

impl TaskState {
    /// Whether the task can never change again: only `delivered` and `cancelled`. Unlike
    /// [`TaskState::is_terminal`], this is false for `failed`, which can be resumed.
    #[must_use]
    pub fn is_closed(self) -> bool {
        matches!(self, TaskState::Delivered | TaskState::Cancelled)
    }
}

impl fmt::Display for TaskState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            TaskState::Requested => "requested",
            TaskState::Assigned => "assigned",
            TaskState::EnRoute => "en_route",
            TaskState::Delivered => "delivered",
            TaskState::Failed => "failed",
            TaskState::Resumed => "resumed",
            TaskState::Cancelled => "cancelled",
        })
    }
}

/// What a task asks for.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TaskKind {
    /// Bring an item from a place to a place.
    Fetch,
    /// Visit shelves to count and restock (night round).
    RestockRound,
    /// Go to a place.
    GoTo,
    /// Accompany a conversation as an interpreter (`BACKEND_A_FAIRE.md`, decision 1). The admin
    /// console does not know this kind yet and shows it as `fetch`.
    InterpreterSession,
    /// Follow a staff tablet from room to room (Step C1; `target_device` names the tablet).
    Follow,
}

/// Why a task failed or was handed to a human. A closed list: no free text from devices.
///
/// A cancellation is not a failure: it is the state `TaskState::Cancelled`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum FailureReason {
    /// The item was not where expected.
    ItemMissing,
    /// The path is blocked.
    PathBlocked,
    /// The robot reported a fault.
    RobotFault,
    /// The robot went silent while carrying the task.
    RobotLost,
    /// No robot could do it; a human must.
    HandedToHuman,
    /// The deadline passed.
    DeadlinePassed,
}

/// A task id and kind, as shown next to a robot on the map.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct TaskSummary {
    /// Task id.
    pub id: TaskId,
    /// Task kind.
    pub kind: TaskKind,
}

/// A task. It has an item, two places and a state; never health content.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Task {
    id: TaskId,
    kind: TaskKind,
    item: Option<ItemId>,
    from: Option<PlaceId>,
    to: PlaceId,
    deadline: Option<DateTime<Utc>>,
    state: TaskState,
    requested_by: Actor,
    assigned_robot: Option<RobotId>,
    failure: Option<FailureReason>,
    /// Set when no robot fits: the dispatcher's explanation for the human who takes over.
    needs_human: Option<String>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

/// Fields of a new task, before it has an id or a state.
#[derive(Debug, Clone, PartialEq)]
pub struct TaskDraft {
    /// Kind.
    pub kind: TaskKind,
    /// Item (required for `fetch`).
    pub item: Option<ItemId>,
    /// Origin place.
    pub from: Option<PlaceId>,
    /// Destination place.
    pub to: PlaceId,
    /// Optional deadline.
    pub deadline: Option<DateTime<Utc>>,
}

impl Task {
    /// Creates a task in state `requested`.
    ///
    /// # Errors
    /// `DomainError::MissingTaskField` when a `fetch` task has no item.
    pub fn new(
        id: TaskId,
        draft: TaskDraft,
        requested_by: Actor,
        at: DateTime<Utc>,
    ) -> Result<Task, DomainError> {
        if draft.kind == TaskKind::Fetch && draft.item.is_none() {
            return Err(DomainError::MissingTaskField {
                kind: "fetch",
                field: "item",
            });
        }
        Ok(Task {
            id,
            kind: draft.kind,
            item: draft.item,
            from: draft.from,
            to: draft.to,
            deadline: draft.deadline,
            state: TaskState::Requested,
            requested_by,
            assigned_robot: None,
            failure: None,
            needs_human: None,
            created_at: at,
            updated_at: at,
        })
    }

    /// Rebuilds a task read back from storage (no transition checks).
    ///
    /// # Errors
    /// `DomainError::Corrupt` when the stored combination is impossible (for example `assigned`
    /// without a robot).
    pub fn restore(parts: TaskParts) -> Result<Task, DomainError> {
        let corrupt = |reason: &str| DomainError::Corrupt {
            table: "tasks",
            reason: reason.to_owned(),
        };
        if parts.kind == TaskKind::Fetch && parts.item.is_none() {
            return Err(corrupt("fetch without an item"));
        }
        if parts.state == TaskState::Assigned && parts.assigned_robot.is_none() {
            return Err(corrupt("assigned without a robot"));
        }
        if parts.state == TaskState::Failed && parts.failure.is_none() {
            return Err(corrupt("failed without a reason"));
        }
        Ok(Task {
            id: parts.id,
            kind: parts.kind,
            item: parts.item,
            from: parts.from,
            to: parts.to,
            deadline: parts.deadline,
            state: parts.state,
            requested_by: parts.requested_by,
            assigned_robot: parts.assigned_robot,
            failure: parts.failure,
            needs_human: parts.needs_human,
            created_at: parts.created_at,
            updated_at: parts.updated_at,
        })
    }

    /// Moves the task to `next`, recording `reason` on failure.
    ///
    /// # Errors
    /// `DomainError::IllegalTransition` when the state machine forbids it;
    /// `DomainError::MissingFailureReason` when `next` is `failed` and `reason` is `None`.
    pub fn transition(
        &mut self,
        next: TaskState,
        reason: Option<FailureReason>,
        at: DateTime<Utc>,
    ) -> Result<(), DomainError> {
        if !self.state.can_go_to(next) {
            return Err(DomainError::IllegalTransition {
                task: self.id.clone(),
                from: self.state,
                to: next,
            });
        }
        if next == TaskState::Failed && reason.is_none() {
            return Err(DomainError::MissingFailureReason {
                task: self.id.clone(),
            });
        }
        self.state = next;
        // The reason belongs to the failed state; a resumed or later task carries none.
        self.failure = if next == TaskState::Failed {
            reason
        } else {
            None
        };
        self.updated_at = at;
        Ok(())
    }

    /// Assigns the robot and moves to `assigned`.
    ///
    /// # Errors
    /// `DomainError::IllegalTransition` unless the task is `requested` or `resumed`.
    pub fn assign_to(&mut self, robot: RobotId, at: DateTime<Utc>) -> Result<(), DomainError> {
        self.transition(TaskState::Assigned, None, at)?;
        self.assigned_robot = Some(robot);
        self.needs_human = None;
        Ok(())
    }

    /// Marks the task as needing a human, with the dispatcher's explanation.
    pub fn mark_needs_human(&mut self, explanation: String, at: DateTime<Utc>) {
        self.needs_human = Some(explanation);
        self.updated_at = at;
    }

    /// Id.
    #[must_use]
    pub fn id(&self) -> &TaskId {
        &self.id
    }
    /// Kind.
    #[must_use]
    pub fn kind(&self) -> TaskKind {
        self.kind
    }
    /// Item.
    #[must_use]
    pub fn item(&self) -> Option<&ItemId> {
        self.item.as_ref()
    }
    /// Origin place.
    #[must_use]
    pub fn from(&self) -> Option<&PlaceId> {
        self.from.as_ref()
    }
    /// Destination place.
    #[must_use]
    pub fn to(&self) -> &PlaceId {
        &self.to
    }
    /// Deadline.
    #[must_use]
    pub fn deadline(&self) -> Option<DateTime<Utc>> {
        self.deadline
    }
    /// Current state.
    #[must_use]
    pub fn state(&self) -> TaskState {
        self.state
    }
    /// Who asked.
    #[must_use]
    pub fn requested_by(&self) -> &Actor {
        &self.requested_by
    }
    /// Assigned robot.
    #[must_use]
    pub fn assigned_robot(&self) -> Option<&RobotId> {
        self.assigned_robot.as_ref()
    }
    /// Failure reason.
    #[must_use]
    pub fn failure(&self) -> Option<FailureReason> {
        self.failure
    }
    /// Explanation when a human must take over.
    #[must_use]
    pub fn needs_human(&self) -> Option<&str> {
        self.needs_human.as_deref()
    }
    /// Creation time.
    #[must_use]
    pub fn created_at(&self) -> DateTime<Utc> {
        self.created_at
    }
    /// Last change.
    #[must_use]
    pub fn updated_at(&self) -> DateTime<Utc> {
        self.updated_at
    }
    /// Id and kind.
    #[must_use]
    pub fn summary(&self) -> TaskSummary {
        TaskSummary {
            id: self.id.clone(),
            kind: self.kind,
        }
    }
}

/// Every stored field of a task, for `Task::restore`.
#[derive(Debug, Clone, PartialEq)]
pub struct TaskParts {
    /// Id.
    pub id: TaskId,
    /// Kind.
    pub kind: TaskKind,
    /// Item.
    pub item: Option<ItemId>,
    /// Origin.
    pub from: Option<PlaceId>,
    /// Destination.
    pub to: PlaceId,
    /// Deadline.
    pub deadline: Option<DateTime<Utc>>,
    /// State.
    pub state: TaskState,
    /// Requester.
    pub requested_by: Actor,
    /// Robot.
    pub assigned_robot: Option<RobotId>,
    /// Failure reason.
    pub failure: Option<FailureReason>,
    /// Human handover explanation.
    pub needs_human: Option<String>,
    /// Created.
    pub created_at: DateTime<Utc>,
    /// Updated.
    pub updated_at: DateTime<Utc>,
}

/// Filter for task lists.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct TaskFilter {
    /// Only this state.
    pub state: Option<TaskState>,
    /// Only tasks of this robot.
    pub robot: Option<RobotId>,
    /// Only tasks requested by this user.
    pub requested_by: Option<UserId>,
    /// Only tasks created at or after this time.
    pub since: Option<DateTime<Utc>>,
    /// Only unfinished tasks.
    pub active_only: bool,
}

/// A validated page request: `limit` 1 to 500.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Page {
    limit: u32,
    offset: u32,
}

impl Page {
    /// Largest page.
    pub const MAX_LIMIT: u32 = 500;
    /// Page used when the caller gives none.
    pub const DEFAULT_LIMIT: u32 = 50;

    /// Validates a page request.
    ///
    /// # Errors
    /// `DomainError::InvalidPage` when `limit` is 0 or above 500.
    pub fn new(limit: u32, offset: u32) -> Result<Page, DomainError> {
        if limit == 0 || limit > Page::MAX_LIMIT {
            return Err(DomainError::InvalidPage {
                limit,
                max: Page::MAX_LIMIT,
            });
        }
        Ok(Page { limit, offset })
    }
    /// Limit.
    #[must_use]
    pub fn limit(&self) -> u32 {
        self.limit
    }
    /// Offset.
    #[must_use]
    pub fn offset(&self) -> u32 {
        self.offset
    }
}

#[cfg(test)]
mod tests {
    use chrono::{TimeZone, Utc};

    use super::{Task, TaskDraft, TaskKind, TaskState};
    use crate::actor::Actor;
    use crate::error::DomainError;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    /// A `go_to` task in state `requested`.
    fn requested_task() -> Result<Task, Box<dyn std::error::Error>> {
        let at = Utc
            .with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
            .single()
            .ok_or("bad test date")?;
        let draft = TaskDraft {
            kind: TaskKind::GoTo,
            item: None,
            from: None,
            to: "room-12".parse()?,
            deadline: None,
        };
        Ok(Task::new(
            "t-1".parse()?,
            draft,
            Actor::User("u-nurse".parse()?),
            at,
        )?)
    }

    /// Walks a requested task through `path`, failing on the first refused step.
    fn task_in(path: &[TaskState]) -> Result<Task, Box<dyn std::error::Error>> {
        let mut task = requested_task()?;
        for next in path {
            let reason = (*next == TaskState::Failed).then_some(super::FailureReason::RobotFault);
            task.transition(*next, reason, task.updated_at())?;
        }
        Ok(task)
    }

    /// Asserts that `from -> to` is refused with a message naming both states.
    fn assert_refused(path: &[TaskState], to: TaskState) -> TestResult {
        let mut task = task_in(path)?;
        let from = task.state();
        let at = task.updated_at();
        let err = task
            .transition(to, None, at)
            .err()
            .ok_or("the transition was accepted")?;
        assert!(matches!(err, DomainError::IllegalTransition { .. }));
        let message = err.to_string();
        assert!(message.contains(&from.to_string()), "{message}");
        assert!(message.contains(&to.to_string()), "{message}");
        assert!(message.contains("not allowed"), "{message}");
        assert_eq!(task.state(), from);
        Ok(())
    }

    const TO_DELIVERED: &[TaskState] = &[
        TaskState::Assigned,
        TaskState::EnRoute,
        TaskState::Delivered,
    ];

    #[test]
    fn task_requested_to_assigned_ok() -> TestResult {
        let mut task = requested_task()?;
        let at = task.updated_at();
        task.transition(TaskState::Assigned, None, at)?;
        assert_eq!(task.state(), TaskState::Assigned);
        Ok(())
    }

    #[test]
    fn delivered_to_en_route_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(TO_DELIVERED, TaskState::EnRoute)
    }

    #[test]
    fn delivered_to_requested_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(TO_DELIVERED, TaskState::Requested)
    }

    #[test]
    fn delivered_to_assigned_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(TO_DELIVERED, TaskState::Assigned)
    }

    #[test]
    fn requested_to_en_route_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(&[], TaskState::EnRoute)
    }

    #[test]
    fn requested_to_delivered_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(&[], TaskState::Delivered)
    }

    #[test]
    fn failed_to_delivered_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(&[TaskState::Failed], TaskState::Delivered)
    }

    #[test]
    fn failed_to_en_route_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(&[TaskState::Failed], TaskState::EnRoute)
    }

    #[test]
    fn requested_and_assigned_can_be_cancelled() -> TestResult {
        let mut requested = requested_task()?;
        let at = requested.updated_at();
        requested.transition(TaskState::Cancelled, None, at)?;
        assert_eq!(requested.state(), TaskState::Cancelled);
        assert!(TaskState::Cancelled.is_terminal());
        let mut assigned = task_in(&[TaskState::Assigned])?;
        let at = assigned.updated_at();
        assigned.transition(TaskState::Cancelled, None, at)?;
        assert_eq!(assigned.state(), TaskState::Cancelled);
        Ok(())
    }

    #[test]
    fn en_route_to_cancelled_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(
            &[TaskState::Assigned, TaskState::EnRoute],
            TaskState::Cancelled,
        )
    }

    #[test]
    fn cancelled_to_assigned_is_rejected_with_explicit_message() -> TestResult {
        assert_refused(&[TaskState::Cancelled], TaskState::Assigned)
    }

    #[test]
    fn failed_requires_a_reason() -> TestResult {
        let mut task = requested_task()?;
        let at = task.updated_at();
        let err = task
            .transition(TaskState::Failed, None, at)
            .err()
            .ok_or("failed without a reason was accepted")?;
        assert!(matches!(err, DomainError::MissingFailureReason { .. }));
        assert_eq!(task.state(), TaskState::Requested);
        Ok(())
    }

    #[test]
    fn fetch_task_without_item_is_refused() -> TestResult {
        let at = Utc
            .with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
            .single()
            .ok_or("bad test date")?;
        let draft = TaskDraft {
            kind: TaskKind::Fetch,
            item: None,
            from: None,
            to: "room-12".parse()?,
            deadline: None,
        };
        let err = Task::new("t-2".parse()?, draft, Actor::System("demo"), at)
            .err()
            .ok_or("a fetch without item was accepted")?;
        assert!(matches!(err, DomainError::MissingTaskField { .. }));
        Ok(())
    }

    #[test]
    fn failure_is_recorded_and_cleared_on_resume() -> TestResult {
        let mut task = requested_task()?;
        let at = task.updated_at();
        task.transition(
            TaskState::Failed,
            Some(super::FailureReason::PathBlocked),
            at,
        )?;
        assert_eq!(task.failure(), Some(super::FailureReason::PathBlocked));
        task.transition(TaskState::Resumed, None, at)?;
        assert_eq!(task.failure(), None);
        assert!(!TaskState::Resumed.is_terminal());
        assert!(TaskState::Failed.is_terminal());
        Ok(())
    }

    #[test]
    fn only_delivered_and_cancelled_are_closed() {
        for state in [
            TaskState::Requested,
            TaskState::Assigned,
            TaskState::EnRoute,
            TaskState::Failed,
            TaskState::Resumed,
        ] {
            assert!(!state.is_closed(), "{state}");
        }
        assert!(TaskState::Delivered.is_closed());
        assert!(TaskState::Cancelled.is_closed());
        // A closed state has no way out; a terminal one may (failed -> resumed).
        for state in [TaskState::Delivered, TaskState::Cancelled] {
            for next in [
                TaskState::Requested,
                TaskState::Assigned,
                TaskState::EnRoute,
                TaskState::Delivered,
                TaskState::Failed,
                TaskState::Resumed,
                TaskState::Cancelled,
            ] {
                assert!(!state.can_go_to(next), "{state} -> {next}");
            }
        }
    }
}
