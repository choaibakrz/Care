//! Assignment: builds the fleet from live state and role cards, asks the dispatcher, sends
//! `task.assign`, moves the task to `assigned`. No robot fits: the task stays `requested`
//! with `needs_human` set to the explanation.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use audit::{Category, Journal, RecordBody, Severity};
use domain::ports::{RobotRepository, TaskRepository};
use domain::{Actor, Clock, Page, PlaceId, RobotId, RobotStatus, Task, TaskFilter, TaskState};
use locations::{LivePositions, Point2};
use optimization::{
    DispatchOracle, DispatchRequest, FleetMember, RoleCard, ShelfLeases, TourPlanner,
};
use realtime::{AlertKind, AppEvent, Hub, RobotDown};
use serde::Serialize;
use utoipa::ToSchema;

use crate::error::ApiError;

/// What `AssignmentService` needs.
pub struct AssignmentDeps {
    /// Dispatcher (native, or the Python oracle).
    pub oracle: Arc<dyn DispatchOracle>,
    /// Role cards by name.
    pub role_cards: BTreeMap<String, RoleCard>,
    /// Robots.
    pub robots: Arc<dyn RobotRepository>,
    /// Tasks.
    pub tasks: Arc<dyn TaskRepository>,
    /// Live positions (where each robot is).
    pub live: Arc<LivePositions>,
    /// Hub.
    pub hub: Arc<Hub>,
    /// Restock rounds.
    pub tours: TourPlanner,
    /// Shelf leases.
    pub leases: Arc<ShelfLeases>,
    /// Journal.
    pub journal: Journal,
    /// Clock.
    pub clock: Arc<dyn Clock>,
    /// HACKATHON: simulated robots may take real requests (env `SIM_TAKES_REAL_TASKS`, default
    /// on), so the pitch's simulated fleet answers patient and console tasks. Restore after the
    /// pitch: `false` keeps real deliveries for real robots only.
    pub simulated_take_real_tasks: bool,
}

/// Result of an assignment.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum AssignOutcome {
    /// Sent to a robot.
    Sent {
        /// Robot.
        robot: RobotId,
    },
    /// No robot fits; a human must.
    HandedToHuman {
        /// Dispatcher explanation.
        explanation: String,
    },
}

/// The assignment service.
pub struct AssignmentService {
    deps: AssignmentDeps,
    lock: tokio::sync::Mutex<()>,
}

impl AssignmentService {
    /// A service.
    #[must_use]
    pub fn new(deps: AssignmentDeps) -> AssignmentService {
        AssignmentService {
            deps,
            lock: tokio::sync::Mutex::new(()),
        }
    }

    /// Holds the dispatch lock that [`AssignmentService::assign`] takes while it chooses a
    /// robot. Tests hold it to prove that the emergency stop never waits for the dispatcher.
    pub async fn dispatch_lock(&self) -> tokio::sync::MutexGuard<'_, ()> {
        self.lock.lock().await
    }

    /// Assigns one task.
    ///
    /// # Errors
    /// Repository and hub errors; "no robot fits" is not an error.
    pub async fn assign(&self, task: &Task) -> Result<AssignOutcome, ApiError> {
        let _guard = self.lock.lock().await;
        let now = self.deps.clock.now();
        // Work on the stored task: the caller's copy may be stale.
        let mut task = self
            .deps
            .tasks
            .get(task.id())
            .await?
            .ok_or_else(|| ApiError::not_found("Task", task.id().as_str()))?;
        if !matches!(task.state(), TaskState::Requested | TaskState::Resumed) {
            return Err(ApiError::conflict(
                "task_not_assignable",
                format!(
                    "Task '{}' is {} and cannot be handed to a robot.",
                    task.id(),
                    task.state()
                ),
            ));
        }
        let fleet = self.fleet().await?;
        let request = DispatchRequest {
            from: task.from().cloned().unwrap_or_else(|| task.to().clone()),
            to: task.to().clone(),
            real_delivery: !self.deps.simulated_take_real_tasks
                && !matches!(task.requested_by(), Actor::System("demo")),
        };
        let decision = self.deps.oracle.choose(&request, &fleet)?;
        let chosen = match decision.chosen {
            Some(robot) => {
                let assign = RobotDown::TaskAssign {
                    task_id: task.id().clone(),
                    kind: task.kind(),
                    item: task.item().cloned(),
                    from_place: task.from().cloned(),
                    to_place: task.to().clone(),
                    deadline: task.deadline(),
                };
                match self.deps.hub.send_to_robot(&robot, assign) {
                    Ok(()) => Ok(robot),
                    Err(error) => Err(format!(
                        "{} The chosen robot {robot} could not be reached ({error}).",
                        decision.explanation
                    )),
                }
            }
            None => Err(decision.explanation),
        };
        match chosen {
            Ok(robot) => {
                let from = task.state();
                task.assign_to(robot.clone(), now)?;
                self.deps.tasks.update(&task).await?;
                self.journal_change(&task, from).await?;
                Ok(AssignOutcome::Sent { robot })
            }
            Err(explanation) => {
                task.mark_needs_human(explanation.clone(), now);
                self.deps.tasks.update(&task).await?;
                self.deps.hub.publish(AppEvent::Alert {
                    level: AlertKind::TaskNeedsHuman.level(),
                    kind: AlertKind::TaskNeedsHuman,
                    message: format!(
                        "No robot can take task {} right now: {explanation}",
                        task.id()
                    ),
                    command: None,
                });
                Ok(AssignOutcome::HandedToHuman { explanation })
            }
        }
    }

    /// Journals `TaskStateChanged` for a dispatch.
    async fn journal_change(&self, task: &Task, from: TaskState) -> Result<(), ApiError> {
        self.deps
            .journal
            .append(
                Severity::Info,
                Category::Audit,
                Actor::System("server"),
                RecordBody::TaskStateChanged {
                    task: task.id().clone(),
                    from,
                    to: task.state(),
                    reason: None,
                },
                None,
            )
            .await?;
        Ok(())
    }

    /// The fleet as the dispatcher sees it: every connected robot with a fresh fix and a
    /// known role card. A robot holding an open task counts as busy even before it says so.
    async fn fleet(&self) -> Result<Vec<FleetMember>, ApiError> {
        let records = self.deps.robots.list().await?;
        let open = self
            .deps
            .tasks
            .list(
                &TaskFilter {
                    active_only: true,
                    ..TaskFilter::default()
                },
                &Page::new(Page::MAX_LIMIT, 0)?,
            )
            .await?;
        let working: BTreeSet<RobotId> = open
            .iter()
            .filter(|task| matches!(task.state(), TaskState::Assigned | TaskState::EnRoute))
            .filter_map(|task| task.assigned_robot().cloned())
            .collect();
        let snapshot = self.deps.live.snapshot();
        let map = self.deps.live.map().clone();
        let mut fleet = Vec::new();
        for record in records {
            if !self.deps.hub.is_connected(&record.id) {
                continue;
            }
            let Some(live) = snapshot.robots.iter().find(|robot| robot.id == record.id) else {
                continue;
            };
            if live.stale {
                continue;
            }
            let Some(card) = self.deps.role_cards.get(&record.role_card) else {
                tracing::warn!(robot = %record.id, card = %record.role_card, "unknown role card; robot skipped");
                continue;
            };
            let Some(at) = nearest_place(&map, live.floor, &live.point) else {
                continue;
            };
            let status = if working.contains(&record.id) {
                RobotStatus::Busy
            } else {
                live.status
            };
            fleet.push(FleetMember {
                id: record.id,
                name: record.name,
                status,
                at,
                battery_pct: f64::from(live.battery_pct),
                card: card.clone(),
                simulated: record.simulated,
            });
        }
        Ok(fleet)
    }
}

/// The place under `point`, else the place whose anchor is closest on that floor.
fn nearest_place(map: &locations::ClinicMap, floor: i32, point: &Point2) -> Option<PlaceId> {
    if let Some(place) = map.place_at(floor, point) {
        return Some(place.id.clone());
    }
    map.places_on(floor)
        .into_iter()
        .min_by(|a, b| {
            a.anchor
                .distance(point)
                .total_cmp(&b.anchor.distance(point))
        })
        .map(|place| place.id.clone())
}
