//! Real `ClinicService` (Task 10b): stored, versioned clinic plans and the active map.
//!
//! **One writer at a time (ruling R17).** Task 10b serialises every clinic write (create,
//! update, activate, delete) behind one `tokio::sync::Mutex` held by the service, and re-checks
//! the references (open tasks, stock items, schedule stops, docks) *inside* that lock, right
//! before the store write, so a task created between the check and the write cannot be
//! orphaned. The compare-and-set on the version (`ClinicRepository::update`) stays as the
//! guard against other server processes.

use std::collections::HashSet;
use std::sync::Arc;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use domain::ports::{
    ClinicRecord, ClinicRepository, InventoryRepository, ScheduleRepository, TaskRepository,
};
use domain::{
    Actor, ClinicChange, ClinicId, Clock, DomainError, ErrorProblem, Page, PlaceId, TaskFilter,
};
use locations::{ActiveMap, ActivePlan, ClinicPlan, PlanOverlay};
use realtime::{AppEvent, Hub, RobotDown};
use security::ClientIdentity;

use super::ClinicService;
use super::routing::RoutingCache;
use crate::dto::{ClinicSummary, VersionedOverlay, VersionedPlan};
use crate::error::ApiError;

/// Id of the seed plan stored at first start (`ClinicId::seed`).
pub const SEED_CLINIC_ID: &str = "seed";

/// What `RealClinicService` needs.
pub struct ClinicDeps {
    /// Stored plans.
    pub repo: Arc<dyn ClinicRepository>,
    /// The plan in force, shared with the map, route and stats services.
    pub active: Arc<ActiveMap>,
    /// Open tasks (referential check, activation check).
    pub tasks: Arc<dyn TaskRepository>,
    /// Stock items and their places (referential check).
    pub inventory: Arc<dyn InventoryRepository>,
    /// Schedules and their stops (referential check).
    pub schedules: Arc<dyn ScheduleRepository>,
    /// Places robots start from: the configured dock. Task 5b adds the demo robots' homes
    /// (`DemoRobot::home`) when the server runs with `--demo`.
    pub docks: Vec<PlaceId>,
    /// The dispatcher's graph, rebuilt when the active plan changes.
    pub routing: Arc<RoutingCache>,
    /// `map.updated` to the apps, `map.update` to the robots.
    pub hub: Arc<Hub>,
    /// Journal (`clinic_changed`).
    pub journal: Journal,
    /// Clock.
    pub clock: Arc<dyn Clock>,
}

/// The real clinic service.
pub struct RealClinicService {
    deps: ClinicDeps,
    /// Serialises clinic writes (ruling R17).
    writes: tokio::sync::Mutex<()>,
}

impl RealClinicService {
    /// A service.
    #[must_use]
    pub fn new(deps: ClinicDeps) -> RealClinicService {
        RealClinicService {
            deps,
            writes: tokio::sync::Mutex::new(()),
        }
    }

    /// First start and restart: when no plan is stored, stores `seed` as clinic
    /// [`SEED_CLINIC_ID`] (version 1, active, journaled `created`); otherwise loads the stored
    /// active plan, validates it again and puts it in the active map (a stored plan that no
    /// longer validates is reported in the journal and the seed stays in force). Awaited by
    /// `Wiring::finish` before the server serves anything (ruling R16).
    ///
    /// # Errors
    /// Store failures.
    pub async fn bootstrap(&self, seed: &ClinicPlan) -> Result<(), ApiError> {
        let _writing = self.writes.lock().await;
        if let Some(record) = self.deps.repo.active().await? {
            match parse_active(&record) {
                Ok(active) => self.deps.active.replace(active),
                Err(error) => {
                    tracing::error!(clinic = %record.id, problem = error.message(), "stored active clinic plan is invalid; the seed stays in force");
                }
            }
            return Ok(());
        }
        if !self.deps.repo.list().await?.is_empty() {
            return Ok(());
        }
        let map = seed.validate()?;
        let id = ClinicId::seed();
        let record = ClinicRecord {
            id: id.clone(),
            name: seed.name.clone(),
            version: 1,
            active: true,
            updated_at: self.deps.clock.now(),
            plan_json: plan_json(seed)?,
            overlay_json: String::new(),
        };
        self.deps.repo.insert(&record).await?;
        let active = ActivePlan {
            clinic_id: id.clone(),
            version: 1,
            plan: Arc::new(seed.clone()),
            map: Arc::new(map),
        };
        self.deps.active.replace(active.clone());
        self.announce_as(
            Actor::System("server"),
            &id,
            1,
            ClinicChange::Created,
            Some(&active),
        )
        .await
    }

    /// Every user of `place`: open tasks (`tasks/<id>`), stock items (`inventory/<id>`),
    /// schedule stops (`schedules/<id>`) and docks (`docks/<place>`), each with a problem
    /// text ("open task goes to this place").
    ///
    /// # Errors
    /// Store failures.
    pub async fn users_of(&self, place: &PlaceId) -> Result<Vec<ErrorProblem>, ApiError> {
        Ok(self
            .references(true)
            .await?
            .into_iter()
            .filter(|(used, _)| used == place)
            .map(|(_, user)| user)
            .collect())
    }

    /// Every (place, user) pair of the stores.
    async fn references(&self, with_tasks: bool) -> Result<Vec<(PlaceId, ErrorProblem)>, ApiError> {
        let mut refs = Vec::new();
        let user = |path: String, problem: &str| ErrorProblem {
            path,
            problem: problem.to_owned(),
        };
        if with_tasks {
            let filter = TaskFilter {
                active_only: true,
                ..TaskFilter::default()
            };
            for task in self
                .deps
                .tasks
                .list(&filter, &Page::new(Page::MAX_LIMIT, 0)?)
                .await?
            {
                for place in task.from().into_iter().chain([task.to()]) {
                    refs.push((
                        place.clone(),
                        user(
                            format!("tasks/{}", task.id()),
                            "open task goes to this place",
                        ),
                    ));
                }
            }
        }
        for level in self.deps.inventory.list().await? {
            refs.push((
                level.place.clone(),
                user(
                    format!("inventory/{}", level.item),
                    "stock item is kept at this place",
                ),
            ));
        }
        for schedule in self.deps.schedules.list().await? {
            for place in &schedule.places {
                refs.push((
                    place.clone(),
                    user(
                        format!("schedules/{}", schedule.id),
                        "schedule stops at this place",
                    ),
                ));
            }
        }
        for dock in &self.deps.docks {
            refs.push((dock.clone(), user(format!("docks/{dock}"), "robot dock")));
        }
        Ok(refs)
    }

    /// Refuses (409 `place_in_use`) when a reference points at a place outside `kept`.
    async fn check_places_kept(
        &self,
        kept: &HashSet<PlaceId>,
        with_tasks: bool,
    ) -> Result<(), ApiError> {
        let users: Vec<ErrorProblem> = self
            .references(with_tasks)
            .await?
            .into_iter()
            .filter(|(place, _)| !kept.contains(place))
            .map(|(place, user)| ErrorProblem {
                path: user.path,
                problem: format!("{} ('{place}' is not in the plan)", user.problem),
            })
            .collect();
        if users.is_empty() {
            return Ok(());
        }
        Err(ApiError::conflict_with_users(
            "place_in_use",
            "The plan lacks places that are still in use; keep them or move their users first."
                .to_owned(),
            users,
        ))
    }

    /// Journals the change and announces it (`map.updated`; `map.update` to robots when
    /// `active` is the new plan in force).
    ///
    /// # Errors
    /// `journal_unavailable` when the journal refuses the record.
    pub async fn announce(
        &self,
        actor: &ClientIdentity,
        clinic: &ClinicId,
        version: u64,
        change: ClinicChange,
        active: Option<&ActivePlan>,
    ) -> Result<(), ApiError> {
        self.announce_as(
            actor.verified.subject_id.clone(),
            clinic,
            version,
            change,
            active,
        )
        .await
    }

    async fn announce_as(
        &self,
        actor: Actor,
        clinic: &ClinicId,
        version: u64,
        change: ClinicChange,
        active: Option<&ActivePlan>,
    ) -> Result<(), ApiError> {
        self.deps
            .journal
            .append(
                Severity::Notice,
                Category::Audit,
                actor,
                RecordBody::ClinicChanged {
                    clinic: clinic.clone(),
                    version,
                    change,
                },
                None,
            )
            .await
            .map_err(|_| ApiError::journal_unavailable())?;
        self.deps.hub.publish(AppEvent::MapUpdated {
            clinic_id: clinic.clone(),
            version,
            active: active.is_some(),
        });
        if let Some(active) = active {
            let _delivered = self.deps.hub.broadcast_to_robots(RobotDown::MapUpdate {
                version: active.tag(),
            });
        }
        Ok(())
    }

    /// Puts `record`'s plan in force and tells the routing graph.
    fn put_in_force(&self, record: &ClinicRecord) -> Result<ActivePlan, ApiError> {
        let active = parse_active(record)?;
        self.deps.active.replace(active.clone());
        // Task 13b: `self.deps.routing.rebuild().await` goes here once the graph exists.
        Ok(active)
    }

    /// Stores `base` and `overlay` (writes lock held): validates the effective plan, checks
    /// that no place in use disappears, saves with the version check, puts it in force when
    /// active and announces it. Returns the effective plan.
    async fn save(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        base: ClinicPlan,
        overlay: PlanOverlay,
    ) -> Result<VersionedPlan, ApiError> {
        for unknown in overlay.unknown_removals(&base) {
            tracing::warn!(removal = %unknown, "overlay removes an id the base plan lacks; ignored");
        }
        let plan = overlay.apply(&base);
        plan.validate()?;
        let before = self.stored(id).await?;
        let old = parse_effective(&before)?;
        let kept: HashSet<PlaceId> = plan.place_ids().into_iter().cloned().collect();
        let removed: HashSet<PlaceId> = old
            .place_ids()
            .into_iter()
            .filter(|place| !kept.contains(*place))
            .cloned()
            .collect();
        if !removed.is_empty() {
            let users: Vec<ErrorProblem> = self
                .references(true)
                .await?
                .into_iter()
                .filter(|(place, _)| removed.contains(place))
                .map(|(_, user)| user)
                .collect();
            if !users.is_empty() {
                return Err(ApiError::conflict_with_users(
                    "place_in_use",
                    "A place you removed is still in use; move its users first.".to_owned(),
                    users,
                ));
            }
        }
        let record = self
            .deps
            .repo
            .update(
                id,
                expected_version,
                &base.name,
                &plan_json(&base)?,
                &overlay_json(&overlay)?,
                self.deps.clock.now(),
            )
            .await
            .map_err(|error| cas_error(id, error))?;
        let in_force = if record.active {
            Some(self.put_in_force(&record)?)
        } else {
            None
        };
        self.announce(
            actor,
            id,
            record.version,
            ClinicChange::Updated,
            in_force.as_ref(),
        )
        .await?;
        Ok(VersionedPlan {
            id: record.id.clone(),
            version: record.version,
            active: record.active,
            plan,
        })
    }

    async fn stored(&self, id: &ClinicId) -> Result<ClinicRecord, ApiError> {
        self.deps
            .repo
            .get(id)
            .await?
            .ok_or_else(|| ApiError::not_found("Clinic plan", id.as_str()))
    }
}

fn plan_json(plan: &ClinicPlan) -> Result<String, ApiError> {
    serde_json::to_string(plan).map_err(|_| ApiError::internal("clinic plan json"))
}

fn parse_plan(record: &ClinicRecord) -> Result<ClinicPlan, ApiError> {
    serde_json::from_str(&record.plan_json).map_err(|_| ApiError::internal("stored clinic plan"))
}

fn parse_overlay(record: &ClinicRecord) -> Result<PlanOverlay, ApiError> {
    if record.overlay_json.is_empty() {
        return Ok(PlanOverlay::default());
    }
    serde_json::from_str(&record.overlay_json)
        .map_err(|_| ApiError::internal("stored clinic overlay"))
}

fn overlay_json(overlay: &PlanOverlay) -> Result<String, ApiError> {
    if overlay.is_empty() {
        return Ok(String::new());
    }
    serde_json::to_string(overlay).map_err(|_| ApiError::internal("clinic overlay json"))
}

/// The base with the stored modifications applied (what everything but `/base` serves).
fn parse_effective(record: &ClinicRecord) -> Result<ClinicPlan, ApiError> {
    Ok(parse_overlay(record)?.apply(&parse_plan(record)?))
}

fn parse_active(record: &ClinicRecord) -> Result<ActivePlan, ApiError> {
    let plan = parse_effective(record)?;
    let map = plan.validate()?;
    Ok(ActivePlan {
        clinic_id: record.id.clone(),
        version: record.version,
        plan: Arc::new(plan),
        map: Arc::new(map),
    })
}

fn summary(record: &ClinicRecord) -> ClinicSummary {
    ClinicSummary {
        id: record.id.clone(),
        name: record.name.clone(),
        version: record.version,
        active: record.active,
        updated_at: record.updated_at,
    }
}

/// The id derived from a plan name: lowercase, other runs become `-`, at most 48 characters.
fn derive_id(name: &str) -> Result<ClinicId, ApiError> {
    let mut id = String::new();
    for ch in name.to_lowercase().chars() {
        if ch.is_ascii_alphanumeric() {
            id.push(ch);
        } else if !id.ends_with('-') {
            id.push('-');
        }
    }
    let id: String = id.trim_matches('-').chars().take(48).collect();
    let id = id.trim_end_matches('-');
    Ok(id.parse::<ClinicId>()?)
}

/// A stale `expected` becomes 412; everything else keeps its mapping.
fn cas_error(id: &ClinicId, error: DomainError) -> ApiError {
    match error {
        DomainError::VersionConflict { current, .. } => {
            ApiError::version_conflict(id.as_str(), current)
        }
        DomainError::NotFound { .. } => ApiError::not_found("Clinic plan", id.as_str()),
        other => ApiError::from(other),
    }
}

fn clinic_exists(id: &ClinicId) -> ApiError {
    ApiError::conflict_with_users(
        "clinic_exists",
        format!("A clinic plan '{id}' already exists. Rename the plan or edit the existing one."),
        Vec::new(),
    )
}

#[async_trait]
impl ClinicService for RealClinicService {
    async fn list(&self) -> Result<Vec<ClinicSummary>, ApiError> {
        Ok(self.deps.repo.list().await?.iter().map(summary).collect())
    }
    async fn get(&self, id: &ClinicId) -> Result<VersionedPlan, ApiError> {
        let record = self.stored(id).await?;
        Ok(VersionedPlan {
            id: record.id.clone(),
            version: record.version,
            active: record.active,
            plan: parse_effective(&record)?,
        })
    }
    async fn base(&self, id: &ClinicId) -> Result<VersionedPlan, ApiError> {
        let record = self.stored(id).await?;
        Ok(VersionedPlan {
            id: record.id.clone(),
            version: record.version,
            active: record.active,
            plan: parse_plan(&record)?,
        })
    }
    async fn overlay(&self, id: &ClinicId) -> Result<VersionedOverlay, ApiError> {
        let record = self.stored(id).await?;
        Ok(VersionedOverlay {
            version: record.version,
            overlay: parse_overlay(&record)?,
        })
    }
    async fn put_overlay(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        overlay: PlanOverlay,
    ) -> Result<VersionedPlan, ApiError> {
        let _writing = self.writes.lock().await;
        let base = parse_plan(&self.stored(id).await?)?;
        self.save(actor, id, expected_version, base, overlay).await
    }
    async fn put_base(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        plan: ClinicPlan,
    ) -> Result<VersionedPlan, ApiError> {
        let _writing = self.writes.lock().await;
        let overlay = parse_overlay(&self.stored(id).await?)?;
        self.save(actor, id, expected_version, plan, overlay).await
    }
    async fn create(
        &self,
        actor: &ClientIdentity,
        plan: ClinicPlan,
    ) -> Result<ClinicSummary, ApiError> {
        let _writing = self.writes.lock().await;
        plan.validate()?;
        let id = derive_id(&plan.name)?;
        if self.deps.repo.get(&id).await?.is_some() {
            return Err(clinic_exists(&id));
        }
        let record = ClinicRecord {
            id: id.clone(),
            name: plan.name.clone(),
            version: 1,
            active: false,
            updated_at: self.deps.clock.now(),
            plan_json: plan_json(&plan)?,
            overlay_json: String::new(),
        };
        self.deps
            .repo
            .insert(&record)
            .await
            .map_err(|error| match error {
                DomainError::Conflict { .. } => clinic_exists(&id),
                other => ApiError::from(other),
            })?;
        self.announce(actor, &id, 1, ClinicChange::Created, None)
            .await?;
        Ok(summary(&record))
    }
    async fn update(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        plan: ClinicPlan,
    ) -> Result<VersionedPlan, ApiError> {
        let _writing = self.writes.lock().await;
        self.save(actor, id, expected_version, plan, PlanOverlay::default())
            .await
    }
    async fn activate(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
    ) -> Result<ClinicSummary, ApiError> {
        let _writing = self.writes.lock().await;
        let before = self.stored(id).await?;
        if before.active {
            return Ok(summary(&before));
        }
        let open: Vec<ErrorProblem> = self
            .references(true)
            .await?
            .into_iter()
            .map(|(_, user)| user)
            .filter(|user| user.path.starts_with("tasks/"))
            .collect();
        if !open.is_empty() {
            return Err(ApiError::conflict_with_users(
                "open_tasks",
                "Tasks are still open; finish or cancel them before switching plans.".to_owned(),
                open,
            ));
        }
        let plan = parse_plan(&before)?;
        plan.validate()?;
        let kept: HashSet<PlaceId> = plan.place_ids().into_iter().cloned().collect();
        self.check_places_kept(&kept, false).await?;
        let record = self
            .deps
            .repo
            .activate(id, self.deps.clock.now())
            .await
            .map_err(|error| cas_error(id, error))?;
        let in_force = self.put_in_force(&record)?;
        self.announce(
            actor,
            id,
            record.version,
            ClinicChange::Activated,
            Some(&in_force),
        )
        .await?;
        Ok(summary(&record))
    }
    async fn delete(&self, actor: &ClientIdentity, id: &ClinicId) -> Result<(), ApiError> {
        let _writing = self.writes.lock().await;
        let record = self.stored(id).await?;
        if record.active {
            return Err(ApiError::conflict_with_users(
                "clinic_active",
                format!("Clinic plan '{id}' is the active plan; activate another one first."),
                Vec::new(),
            ));
        }
        self.deps.repo.delete(id).await?;
        self.announce(actor, id, record.version, ClinicChange::Deleted, None)
            .await
    }
}
