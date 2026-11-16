//! Real `RobotService`, and `EstopPath`: the emergency stop's separate code path.
//!
//! `EstopPath::trigger` writes the stop to the robot's priority queue before anything else,
//! then records it (to the journal, or to the emergency fallback file when the journal is
//! down). It does not touch the dispatcher, the task service or the database.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock, PoisonError};
use std::time::Duration;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use chrono::{DateTime, Utc};
use domain::incident::{IncidentCode, RobotFaultCode};
use domain::ports::RobotRepository;
use domain::{
    Actor, Clock, CommandName, ItemId, OwnerLabel, Permission, RobotFix, RobotId, RobotRecord,
    RobotStatus, Role, SubjectRef, TaskId,
};
use locations::{LivePositions, PlaceKind, Point2, PositionFix, RobotInfo};
use realtime::{
    AlertKind, AppEvent, CommandNotice, Deduper, Envelope, Hub, Liveness, MoodInputs,
    RealtimeError, RobotDown, RobotMood, RobotPose, RobotSession, RobotUp, ZoneView,
};
use security::ClientIdentity;
use tokio::task::JoinHandle;
use uuid::Uuid;

use super::incidents::IncidentBoard;
use super::{InventoryService, RobotService, TaskService, ZoneService};
use crate::dto::{CommandReceipt, FleetHomeView, RevertReceipt, RobotView, TeleportRequest};
use crate::error::ApiError;
use crate::sim::fleet::SimFleet;

/// How many commands [`CommandLog`] remembers for a revert (the oldest are forgotten; the
/// journal keeps them all).
pub const COMMAND_LOG_CAPACITY: usize = 1024;

/// Where a logged command stands in its revert (Task A7).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RevertMark {
    /// An admin's revert reserved it under the log's lock and is sending the inverse: a
    /// second revert is 409 `already_reverted` and sends nothing. Released (back to no mark)
    /// if the inverse cannot be sent.
    Pending,
    /// Reverted by the inverse command with this id.
    Done(Uuid),
}

/// One command as the revert needs it (Task A7).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoggedCommand {
    /// Its id.
    pub id: Uuid,
    /// The robot.
    pub robot: RobotId,
    /// The command.
    pub name: CommandName,
    /// Whether an admin sent it (an admin's own command is not revertible).
    pub by_admin: bool,
    /// `None` until a revert reserves it, then [`RevertMark::Pending`], then
    /// [`RevertMark::Done`] once the inverse was sent.
    pub reverted_by: Option<RevertMark>,
}

/// The recent robot commands in memory (Task A7), so the admin can revert a non-admin's
/// command: bounded to [`COMMAND_LOG_CAPACITY`]; lost on restart (a command older than the
/// server's start is answered 404 and must be undone by sending the opposite command).
///
/// It also holds the **emergency-stop latch** (ruling R24): a robot that received `estop`
/// stays latched until an admin's explicit `resume` was sent; meanwhile a non-admin `resume`
/// is 409 `estop_latched` and no revert targets the robot. Every check-and-mark happens
/// under the one lock, so two concurrent reverts of a command send one inverse.
#[derive(Debug)]
pub struct CommandLog {
    entries: Mutex<std::collections::VecDeque<LoggedCommand>>,
    latched: Mutex<std::collections::HashSet<RobotId>>,
}

impl CommandLog {
    /// An empty log.
    #[must_use]
    pub fn new() -> CommandLog {
        CommandLog {
            entries: Mutex::new(std::collections::VecDeque::with_capacity(
                COMMAND_LOG_CAPACITY,
            )),
            latched: Mutex::new(std::collections::HashSet::new()),
        }
    }

    fn entries(&self) -> std::sync::MutexGuard<'_, std::collections::VecDeque<LoggedCommand>> {
        self.entries.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn latched(&self) -> std::sync::MutexGuard<'_, std::collections::HashSet<RobotId>> {
        self.latched.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Remembers a sent command (estops included, so a later estop supersedes an earlier
    /// command), forgetting the oldest beyond the capacity.
    pub fn record(&self, command: LoggedCommand) {
        let mut entries = self.entries();
        entries.push_back(command);
        while entries.len() > COMMAND_LOG_CAPACITY {
            entries.pop_front();
        }
    }

    /// Checks that `id` is a revertible command of `robot` and **reserves** it (marks it
    /// [`RevertMark::Pending`]) under the lock, then returns it; the caller sends the inverse,
    /// then [`CommandLog::mark_reverted`], or [`CommandLog::release`] when the send failed.
    /// In this order: 404 unknown or another robot's; 409 `already_reverted` (done, or
    /// pending: another revert is sending, [`ApiError::revert_in_progress`]); 409
    /// `not_revertible` (estop, shutdown, an admin's command); 409 `estop_latched` when
    /// `robot` is latched; 409 `superseded` when a later command of `robot` is in the log
    /// (only the robot's latest command is revertible).
    ///
    /// # Errors
    /// As above.
    pub fn reserve_revert(&self, robot: &RobotId, id: Uuid) -> Result<LoggedCommand, ApiError> {
        let latched = self.is_latched(robot);
        let mut entries = self.entries();
        let not_found = || ApiError::not_found("Command", &id.to_string());
        let position = entries
            .iter()
            .position(|command| command.id == id && &command.robot == robot)
            .ok_or_else(not_found)?;
        let later = entries
            .iter()
            .skip(position.saturating_add(1))
            .rfind(|command| &command.robot == robot)
            .map(|command| command.id);
        let command = entries.get_mut(position).ok_or_else(not_found)?;
        match command.reverted_by {
            Some(RevertMark::Done(by)) => return Err(ApiError::already_reverted(&by.to_string())),
            Some(RevertMark::Pending) => return Err(ApiError::revert_in_progress()),
            None => {}
        }
        if command.by_admin {
            return Err(ApiError::not_revertible(
                "an administrator sent it; send the opposite command instead",
            ));
        }
        if command.name.inverse().is_none() {
            return Err(ApiError::not_revertible(match command.name {
                CommandName::Shutdown => "the robot was shut down; restart it on site",
                _ => "an emergency stop is released on the robot itself",
            }));
        }
        if latched {
            return Err(ApiError::estop_latched(robot.as_str()));
        }
        if let Some(later) = later {
            return Err(ApiError::superseded(robot.as_str(), &later.to_string()));
        }
        command.reverted_by = Some(RevertMark::Pending);
        Ok(command.clone())
    }

    /// Gives a reservation back (the inverse was not sent): `Pending` -> no mark.
    pub fn release(&self, id: Uuid) {
        if let Some(command) = self.entries().iter_mut().find(|command| command.id == id)
            && command.reverted_by == Some(RevertMark::Pending)
        {
            command.reverted_by = None;
        }
    }

    /// Marks `id` reverted by `by` (after the inverse was sent): `Pending` -> `Done(by)`.
    pub fn mark_reverted(&self, id: Uuid, by: Uuid) {
        if let Some(command) = self.entries().iter_mut().find(|command| command.id == id) {
            command.reverted_by = Some(RevertMark::Done(by));
        }
    }

    /// Latches `robot` in emergency stop (after `EstopPath::trigger` delivered the stop).
    pub fn latch_estop(&self, robot: &RobotId) {
        self.latched().insert(robot.clone());
    }

    /// Whether `robot` is latched in emergency stop.
    #[must_use]
    pub fn is_latched(&self, robot: &RobotId) -> bool {
        self.latched().contains(robot)
    }

    /// Re-arms `robot` (after an admin's `resume` was sent).
    pub fn rearm(&self, robot: &RobotId) {
        self.latched().remove(robot);
    }
}

impl Default for CommandLog {
    fn default() -> Self {
        CommandLog::new()
    }
}

/// How often liveness is checked.
pub const LIVENESS_CHECK_INTERVAL: Duration = Duration::from_secs(1);

/// The wire name of a command (`pause`, `resume`, ...).
fn wire_name(name: CommandName) -> &'static str {
    match name {
        CommandName::Pause => "pause",
        CommandName::Resume => "resume",
        CommandName::Dock => "dock",
        CommandName::Estop => "estop",
        CommandName::Shutdown => "shutdown",
    }
}

/// The emergency stop path.
pub struct EstopPath {
    hub: Arc<Hub>,
    journal: Journal,
    clock: Arc<dyn Clock>,
}

impl EstopPath {
    /// A path over the hub.
    #[must_use]
    pub fn new(hub: Arc<Hub>, journal: Journal, clock: Arc<dyn Clock>) -> EstopPath {
        EstopPath {
            hub,
            journal,
            clock,
        }
    }

    /// Sends `estop` first, records after.
    ///
    /// # Errors
    /// Offline robot: 409 `robot_offline` "Robot X is offline: the stop was not delivered. Use
    /// the physical button." (recorded as not delivered). Never fails because of the journal.
    pub async fn trigger(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
    ) -> Result<CommandReceipt, ApiError> {
        let sent = self.hub.send_priority(
            robot,
            RobotDown::Command {
                name: CommandName::Estop,
            },
        );
        let now = self.clock.now();
        let delivered = sent.is_ok();
        self.record(&actor.verified.subject_id, robot, delivered, now)
            .await;
        if let Err(error) = sent {
            self.hub.publish(AppEvent::Alert {
                level: AlertKind::EstopNotDelivered.level(),
                kind: AlertKind::EstopNotDelivered,
                message: format!(
                    "The stop for robot {robot} was not delivered ({error}). Use the physical button."
                ),
                command: None,
            });
            return Err(ApiError::conflict(
                "robot_offline",
                format!(
                    "Robot {robot} is offline: the stop was not delivered. Use the physical button."
                ),
            ));
        }
        Ok(CommandReceipt {
            accepted: true,
            reason: None,
            sent_at: now,
            command: CommandName::Estop,
            command_id: Uuid::new_v4(),
        })
    }

    /// Journals the stop, or writes the fallback file when the journal is down.
    async fn record(&self, actor: &Actor, robot: &RobotId, delivered: bool, at: DateTime<Utc>) {
        let journaled = self.journal.is_writable()
            && self
                .journal
                .append(
                    Severity::Critical,
                    Category::Robot,
                    actor.clone(),
                    RecordBody::EstopSent {
                        robot: robot.clone(),
                        delivered,
                    },
                    Some(at),
                )
                .await
                .is_ok();
        if !journaled
            && let Err(error) = self
                .journal
                .record_estop_fallback(actor, robot, delivered, at)
        {
            tracing::error!(%error, %robot, "emergency stop not recorded anywhere");
        }
    }
}

/// What `RealRobotService` needs.
pub struct RobotDeps {
    /// Robots.
    pub repo: Arc<dyn RobotRepository>,
    /// Tasks (robot events, lost robots).
    pub tasks: Arc<dyn TaskService>,
    /// Stock (`inventory.seen`).
    pub inventory: Arc<dyn InventoryService>,
    /// Zones (sync on connect, acks).
    pub zones: Arc<dyn ZoneService>,
    /// Live positions.
    pub live: Arc<LivePositions>,
    /// Liveness (5 s).
    pub liveness: Liveness,
    /// The emergency stop path.
    pub estop: EstopPath,
    /// Incidents (faults, offline, estop).
    pub incidents: Arc<IncidentBoard>,
    /// Hub.
    pub hub: Arc<Hub>,
    /// Journal.
    pub journal: Journal,
    /// Clock.
    pub clock: Arc<dyn Clock>,
}

/// What the server last heard from a robot (memory only).
#[derive(Debug, Clone)]
struct HeardState {
    name: String,
    pose: Option<RobotPose>,
    battery: Option<f32>,
    status: RobotStatus,
    holding: Option<ItemId>,
    mic_open: bool,
    task_id: Option<TaskId>,
    last_seen: Option<DateTime<Utc>>,
    fix_saved_at: Option<DateTime<Utc>>,
}

impl HeardState {
    fn new(name: String) -> HeardState {
        HeardState {
            name,
            pose: None,
            battery: None,
            status: RobotStatus::Idle,
            holding: None,
            mic_open: false,
            task_id: None,
            last_seen: None,
            fix_saved_at: None,
        }
    }
}

/// How often a robot's last fix is saved (ruling R1: robots only).
const FIX_SAVE_EVERY_S: i64 = 5;

/// The real robot service.
pub struct RealRobotService {
    deps: RobotDeps,
    dedupe: Mutex<HashMap<RobotId, Deduper>>,
    commands: CommandLog,
    heard: Mutex<HashMap<RobotId, HeardState>>,
    /// The live server's simulated fleet (teleports, home place, emergency, moods).
    sim: OnceLock<Arc<SimFleet>>,
}

impl RealRobotService {
    /// A service.
    #[must_use]
    pub fn new(deps: RobotDeps) -> RealRobotService {
        RealRobotService {
            deps,
            dedupe: Mutex::new(HashMap::new()),
            commands: CommandLog::new(),
            heard: Mutex::new(HashMap::new()),
            sim: OnceLock::new(),
        }
    }

    /// Attaches the simulated fleet (once; a second call is ignored).
    pub fn attach_sim(&self, fleet: Arc<SimFleet>) {
        if self.sim.set(fleet).is_err() {
            tracing::warn!("a simulated fleet is already attached");
        }
    }

    /// The zones, for `in_deaf_zone` (empty when they cannot be read).
    async fn zone_list(&self) -> Vec<ZoneView> {
        self.deps.zones.list().await.unwrap_or_default()
    }

    /// Checks liveness every second until aborted.
    #[must_use]
    pub fn spawn_liveness_watch(self: Arc<Self>) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(LIVENESS_CHECK_INTERVAL);
            ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                ticker.tick().await;
                let _lost = self.check_liveness().await;
            }
        })
    }

    /// Publishes `robot.updated` for every connected robot each `interval` (1 s), even when
    /// nothing changed, until aborted. The admin console greys a robot silent for 5 s.
    #[must_use]
    pub fn spawn_heartbeat(self: Arc<Self>, interval: Duration) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(interval);
            ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                ticker.tick().await;
                let robots = match self.list().await {
                    Ok(robots) => robots,
                    Err(error) => {
                        tracing::warn!(error = error.message(), "heartbeat: robots not listed");
                        continue;
                    }
                };
                for robot in robots.into_iter().filter(|robot| robot.connected) {
                    self.deps.hub.publish(AppEvent::RobotUpdated { robot });
                }
            }
        })
    }

    fn heard(&self) -> std::sync::MutexGuard<'_, HashMap<RobotId, HeardState>> {
        self.heard.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// The dock's position, for a robot never heard from.
    fn dock_pose(&self) -> RobotPose {
        let map = self.deps.live.map();
        map.places()
            .iter()
            .find(|place| place.kind == PlaceKind::Dock)
            .map_or(
                RobotPose {
                    x: 0.0,
                    y: 0.0,
                    heading: 0.0,
                    floor: map.floors().first().map_or(0, |floor| floor.level),
                },
                |place| RobotPose {
                    x: place.anchor.x(),
                    y: place.anchor.y(),
                    heading: 0.0,
                    floor: place.floor,
                },
            )
    }

    /// The view of one registered robot (`zones` decide `in_deaf_zone`).
    async fn view(&self, record: RobotRecord, zones: &[ZoneView]) -> RobotView {
        let heard = self.heard().get(&record.id).cloned();
        let connected = self.deps.hub.is_connected(&record.id);
        let pose = match heard.as_ref().and_then(|heard| heard.pose) {
            Some(pose) => pose,
            None => match self.deps.repo.last_fix(&record.id).await {
                Ok(Some(fix)) => RobotPose {
                    x: fix.x,
                    y: fix.y,
                    heading: fix.heading_rad.unwrap_or(0.0),
                    floor: fix.floor,
                },
                _ => self.dock_pose(),
            },
        };
        let heard = heard.unwrap_or_else(|| HeardState::new(record.name.clone()));
        let in_deaf_zone = heard.pose.is_some() && in_deaf_zone(zones, pose);
        let sim = self.sim.get();
        let status = sim.and_then(|fleet| fleet.status(&record.id));
        let going_home = status.is_some_and(|status| status.going_home);
        let mood = RobotMood::derive(
            heard.status,
            MoodInputs {
                connected,
                emergency: sim.is_some_and(|fleet| fleet.emergency()),
                charging: status.is_some_and(|status| status.charging),
                home: going_home || status.is_some_and(|status| status.at_home),
                in_deaf_zone,
                has_task: heard.task_id.is_some(),
            },
        );
        RobotView {
            id: record.id,
            name: record.name,
            role: record.role_card,
            simulated: record.simulated,
            pos: pose,
            battery: heard.battery,
            state: heard.status,
            holding: heard.holding,
            mic_open: heard.mic_open,
            task_id: heard.task_id,
            last_seen: heard.last_seen,
            connected,
            in_deaf_zone,
            going_home,
            mood,
        }
    }

    /// Publishes `robot.updated` for one robot.
    async fn publish_robot(&self, robot: &RobotId) {
        if let Ok(Some(record)) = self.deps.repo.find(robot).await {
            let zones = self.zone_list().await;
            let view = self.view(record, &zones).await;
            self.deps
                .hub
                .publish(AppEvent::RobotUpdated { robot: view });
        }
    }

    /// Journals a sent command (a failure is logged; the command is already sent).
    async fn journal(&self, actor: &Actor, body: RecordBody) {
        if let Err(error) = self
            .deps
            .journal
            .append(Severity::Notice, Category::Robot, actor.clone(), body, None)
            .await
        {
            tracing::warn!(%error, "robot command not journaled");
        }
    }

    /// Sends a command (not estop) to a connected robot; 409 `robot_offline` otherwise.
    fn send(&self, robot: &RobotId, name: CommandName) -> Result<(), ApiError> {
        match self
            .deps
            .hub
            .send_to_robot(robot, RobotDown::Command { name })
        {
            Ok(()) => Ok(()),
            Err(RealtimeError::RobotNotConnected { .. } | RealtimeError::Closed { .. }) => {
                Err(ApiError::conflict(
                    "robot_offline",
                    format!("Robot {robot} is offline: the command was not delivered."),
                ))
            }
            Err(error) => Err(ApiError::conflict(
                "robot_unreachable",
                format!("{error} Try again."),
            )),
        }
    }

    /// A `robot.state` message: live position, memory state, the saved fix (throttled).
    async fn on_state(&self, robot: &RobotId, up: RobotUp) {
        let RobotUp::State {
            pos,
            battery_pct,
            status,
            holding,
            mic_open,
        } = up
        else {
            return;
        };
        let now = self.deps.clock.now();
        let (name, save_fix, previous_status) = {
            let mut heard = self.heard();
            let entry = heard
                .entry(robot.clone())
                .or_insert_with(|| HeardState::new(robot.to_string()));
            let previous_status = entry.status;
            entry.pose = Some(pos);
            entry.battery = Some(battery_pct);
            entry.status = status;
            entry.holding = holding;
            entry.mic_open = mic_open;
            entry.last_seen = Some(now);
            let save_fix = entry
                .fix_saved_at
                .is_none_or(|at| (now - at).num_seconds() >= FIX_SAVE_EVERY_S);
            if save_fix {
                entry.fix_saved_at = Some(now);
            }
            (entry.name.clone(), save_fix, previous_status)
        };
        if let Ok(point) = Point2::new(pos.x, pos.y) {
            let fix = PositionFix {
                subject: SubjectRef::Robot(robot.clone()),
                floor: pos.floor,
                point,
                heading_rad: Some(pos.heading),
                at: now,
            };
            let info = RobotInfo {
                name,
                status,
                task: None,
                battery_pct,
                mic_open,
            };
            if let Err(error) = self.deps.live.update_robot(fix, info) {
                tracing::debug!(%robot, %error, "robot position not shown");
            }
        }
        if save_fix {
            let fix = RobotFix {
                floor: pos.floor,
                x: pos.x,
                y: pos.y,
                heading_rad: Some(pos.heading),
                at: now,
            };
            if let Err(error) = self.deps.repo.save_last_fix(robot, &fix).await {
                tracing::warn!(%robot, %error, "robot fix not saved");
            }
        }
        if status == RobotStatus::Fault && previous_status != RobotStatus::Fault {
            self.deps
                .incidents
                .raise(
                    IncidentCode::RobotFault {
                        fault: RobotFaultCode::Software,
                    },
                    Some(SubjectRef::Robot(robot.clone())),
                    now,
                )
                .await;
        }
    }

    /// One message of a robot session.
    async fn on_message(&self, robot: &RobotId, envelope: Envelope<RobotUp>) {
        match envelope.body {
            RobotUp::Hello {
                running_task,
                simulated,
                ..
            } => {
                tracing::info!(%robot, simulated, ?running_task, "robot said hello");
                if let Some(entry) = self.heard().get_mut(robot) {
                    entry.task_id.clone_from(&running_task);
                }
                // The robot's word is the truth on (re)connect: without a running task, a
                // task it held before is failed (`robot_lost`).
                let settled = match &running_task {
                    None => self.deps.tasks.on_robot_lost(robot).await.map(|_| ()),
                    Some(task) => self.deps.tasks.on_robot_resumed(robot, task).await,
                };
                if let Err(error) = settled {
                    tracing::warn!(%robot, error = error.message(), "open tasks not settled on hello");
                }
            }
            state @ RobotUp::State { .. } => self.on_state(robot, state).await,
            RobotUp::TaskEvent {
                task_id,
                state,
                reason,
            } => {
                if let Some(entry) = self.heard().get_mut(robot) {
                    entry.task_id = (!state.is_terminal()).then(|| task_id.clone());
                }
                if let Err(error) = self
                    .deps
                    .tasks
                    .apply_robot_event(robot, envelope.id, &task_id, state, reason)
                    .await
                {
                    tracing::warn!(%robot, task = %task_id, error = error.message(), "task event not applied");
                }
            }
            RobotUp::InventorySeen { place, items } => {
                if let Err(error) = self.deps.inventory.on_seen(robot, &place, &items).await {
                    tracing::warn!(%robot, error = error.message(), "shelf count not reconciled");
                }
            }
            RobotUp::ZoneAck { zone_version_by_id } => {
                if let Err(error) = self.deps.zones.record_ack(robot, &zone_version_by_id).await {
                    tracing::warn!(%robot, error = error.message(), "zone ack not recorded");
                }
            }
        }
    }
}

#[async_trait]
impl RobotService for RealRobotService {
    async fn list(&self) -> Result<Vec<RobotView>, ApiError> {
        let records = self.deps.repo.list().await?;
        let zones = self.zone_list().await;
        let mut views = Vec::with_capacity(records.len());
        for record in records {
            views.push(self.view(record, &zones).await);
        }
        Ok(views)
    }

    async fn teleport(&self, robot: &RobotId, to: TeleportRequest) -> Result<RobotView, ApiError> {
        let record = self
            .deps
            .repo
            .find(robot)
            .await?
            .ok_or_else(|| ApiError::not_found("Robot", robot.as_str()))?;
        let fleet = self
            .sim
            .get()
            .filter(|fleet| record.simulated && fleet.is_simulated(robot))
            .ok_or_else(|| {
                ApiError::conflict(
                    "not_simulated",
                    format!(
                        "Robot {robot} is not a simulated robot of this server: it cannot be teleported."
                    ),
                )
            })?;
        let point = Point2::new(to.x, to.y)
            .map_err(|_| ApiError::invalid_input("x", "x and y must be finite numbers"))?;
        let current = fleet.active().current();
        let inside = current
            .map
            .floor(to.floor)
            .is_some_and(|floor| floor.outline.contains(&point));
        if !inside {
            return Err(ApiError::invalid_input(
                "x",
                &format!(
                    "({}, {}) is outside the outline of floor {}",
                    to.x, to.y, to.floor
                ),
            ));
        }
        let zones = self.zone_list().await;
        if let Some(zone) = zones.iter().find(|zone| {
            zone.kind == domain::ZoneKind::Restricted
                && zone.floor == to.floor
                && locations::Polygon::from_pairs(&zone.polygon)
                    .is_ok_and(|polygon| polygon.contains(&point))
        }) {
            return Err(ApiError::invalid_input(
                "x",
                &format!("the point is inside the restricted zone '{}'", zone.name),
            ));
        }
        let previous = self.heard().get(robot).and_then(|heard| heard.pose);
        let pose = RobotPose {
            x: to.x,
            y: to.y,
            heading: previous.map_or(0.0, |pose| pose.heading),
            floor: to.floor,
        };
        fleet.request_teleport(robot, pose);
        {
            let mut heard = self.heard();
            let entry = heard
                .entry(robot.clone())
                .or_insert_with(|| HeardState::new(record.name.clone()));
            entry.pose = Some(pose);
            entry.mic_open = !in_deaf_zone(&zones, pose);
        }
        let view = self.view(record, &zones).await;
        self.deps.hub.publish(AppEvent::RobotUpdated {
            robot: view.clone(),
        });
        Ok(view)
    }

    async fn fleet_home(&self) -> Result<FleetHomeView, ApiError> {
        let fleet = self
            .sim
            .get()
            .ok_or_else(|| ApiError::unavailable("fleet home store"))?;
        Ok(fleet.home().view(&fleet.active().current().plan))
    }

    async fn set_fleet_home(
        &self,
        place_id: Option<domain::PlaceId>,
    ) -> Result<FleetHomeView, ApiError> {
        let fleet = self
            .sim
            .get()
            .ok_or_else(|| ApiError::unavailable("fleet home store"))?;
        fleet.home().set(&fleet.active().current().plan, place_id)
    }

    fn sim_fleet(&self) -> Option<Arc<SimFleet>> {
        self.sim.get().cloned()
    }

    async fn command(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        name: CommandName,
    ) -> Result<CommandReceipt, ApiError> {
        if name == CommandName::Estop {
            return self.estop(actor, robot).await;
        }
        if !self.deps.journal.is_writable() {
            return Err(ApiError::journal_unavailable());
        }
        if self.deps.repo.find(robot).await?.is_none() {
            return Err(ApiError::not_found("Robot", robot.as_str()));
        }
        let by_admin = actor.verified.role == Role::Admin;
        // The handler checks it too; the service never sends a non-admin's shutdown (R24).
        if name == CommandName::Shutdown && !by_admin {
            return Err(ApiError::forbidden(Permission::RobotShutdown));
        }
        if name == CommandName::Resume && !by_admin && self.commands.is_latched(robot) {
            return Err(ApiError::estop_latched(robot.as_str()));
        }
        self.send(robot, name)?;
        let now = self.deps.clock.now();
        let command_id = Uuid::new_v4();
        self.commands.record(LoggedCommand {
            id: command_id,
            robot: robot.clone(),
            name,
            by_admin,
            reverted_by: None,
        });
        if name == CommandName::Resume && by_admin {
            // The admin's explicit resume re-arms a robot after an emergency stop.
            self.commands.rearm(robot);
        }
        self.journal(
            &actor.verified.subject_id,
            RecordBody::RobotCommandSent {
                robot: robot.clone(),
                command: name,
                delivered: true,
                command_id,
            },
        )
        .await;
        if !by_admin {
            let by = actor
                .verified
                .owner
                .clone()
                .or_else(|| OwnerLabel::new("unknown").ok());
            if let Some(by) = by {
                let revertible = name.inverse().is_some();
                let command = wire_name(name);
                self.deps.hub.publish(AppEvent::Alert {
                    level: AlertKind::StaffCommand.level(),
                    kind: AlertKind::StaffCommand,
                    message: format!(
                        "{by} sent {command} to robot {robot} (command {command_id}).{}",
                        if revertible {
                            " You can revert it."
                        } else {
                            " It cannot be reverted from the server."
                        }
                    ),
                    command: Some(CommandNotice {
                        command_id,
                        robot_id: robot.clone(),
                        command: name,
                        by,
                        revertible,
                    }),
                });
            }
        }
        self.publish_robot(robot).await;
        Ok(CommandReceipt {
            accepted: true,
            reason: None,
            sent_at: now,
            command: name,
            command_id,
        })
    }

    async fn revert(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        command_id: Uuid,
    ) -> Result<RevertReceipt, ApiError> {
        if !self.deps.journal.is_writable() {
            return Err(ApiError::journal_unavailable());
        }
        let logged = self.commands.reserve_revert(robot, command_id)?;
        let Some(inverse) = logged.name.inverse() else {
            self.commands.release(command_id);
            return Err(ApiError::not_revertible("it has no opposite command"));
        };
        if let Err(error) = self.send(robot, inverse) {
            self.commands.release(command_id);
            return Err(error);
        }
        let inverse_id = Uuid::new_v4();
        self.commands.record(LoggedCommand {
            id: inverse_id,
            robot: robot.clone(),
            name: inverse,
            by_admin: true,
            reverted_by: None,
        });
        self.commands.mark_reverted(command_id, inverse_id);
        self.journal(
            &actor.verified.subject_id,
            RecordBody::RobotCommandReverted {
                robot: robot.clone(),
                command_id,
                inverse,
                reverted_by_command_id: inverse_id,
            },
        )
        .await;
        self.publish_robot(robot).await;
        Ok(RevertReceipt {
            reverted_by_command_id: inverse_id,
        })
    }

    async fn estop(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
    ) -> Result<CommandReceipt, ApiError> {
        let receipt = self.deps.estop.trigger(actor, robot).await?;
        self.commands.record(LoggedCommand {
            id: receipt.command_id,
            robot: robot.clone(),
            name: CommandName::Estop,
            by_admin: actor.verified.role == Role::Admin,
            reverted_by: None,
        });
        self.commands.latch_estop(robot);
        if let Some(entry) = self.heard().get_mut(robot) {
            entry.status = RobotStatus::Estop;
        }
        self.deps
            .incidents
            .raise(
                IncidentCode::RobotEstop,
                Some(SubjectRef::Robot(robot.clone())),
                receipt.sent_at,
            )
            .await;
        self.publish_robot(robot).await;
        Ok(receipt)
    }

    async fn is_known(&self, robot: &RobotId) -> Result<bool, ApiError> {
        Ok(self.deps.repo.find(robot).await?.is_some())
    }

    async fn run_session(&self, mut session: RobotSession) {
        let robot = session.robot().clone();
        let name = match self.deps.repo.find(&robot).await {
            Ok(Some(record)) => record.name,
            _ => robot.to_string(),
        };
        self.heard()
            .entry(robot.clone())
            .or_insert_with(|| HeardState::new(String::new()))
            .name = name;
        self.deps.liveness.touch(&robot);
        match self.deps.zones.zones_update().await {
            Ok(zones) => {
                if let Err(error) = session.send(zones) {
                    tracing::warn!(%robot, %error, "zones.update not sent on connect");
                }
            }
            Err(error) => tracing::warn!(%robot, error = error.message(), "no zones.update"),
        }
        self.publish_robot(&robot).await;
        while let Some(envelope) = session.recv().await {
            let duplicate = self
                .dedupe
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .entry(robot.clone())
                .or_default()
                .seen(envelope.id);
            self.deps.liveness.touch(&robot);
            if let Some(entry) = self.heard().get_mut(&robot) {
                entry.last_seen = Some(self.deps.clock.now());
            }
            if duplicate {
                tracing::debug!(%robot, id = %envelope.id, "duplicate robot message ignored");
                continue;
            }
            self.on_message(&robot, envelope).await;
        }
    }

    async fn on_disconnect(&self, robot: &RobotId) {
        // Liveness keeps timing: `check_liveness` reports the robot offline after 5 s.
        self.publish_robot(robot).await;
    }

    async fn check_liveness(&self) -> Vec<RobotId> {
        let expired = self.deps.liveness.expired();
        let now = self.deps.clock.now();
        for robot in &expired {
            self.deps.hub.publish(AppEvent::Alert {
                level: AlertKind::RobotOffline.level(),
                kind: AlertKind::RobotOffline,
                message: format!("Robot {robot} has been silent for 5 seconds: it is offline."),
                command: None,
            });
            self.deps
                .incidents
                .raise(
                    IncidentCode::RobotOffline,
                    Some(SubjectRef::Robot(robot.clone())),
                    now,
                )
                .await;
            if let Err(error) = self.deps.tasks.on_robot_lost(robot).await {
                tracing::warn!(%robot, error = error.message(), "tasks of a lost robot not settled");
            }
            self.publish_robot(robot).await;
        }
        expired
    }
}

/// Whether `pose` is inside a deaf zone of its floor.
fn in_deaf_zone(zones: &[ZoneView], pose: RobotPose) -> bool {
    let Ok(point) = Point2::new(pose.x, pose.y) else {
        return false;
    };
    zones.iter().any(|zone| {
        zone.kind == domain::ZoneKind::Deaf
            && zone.floor == pose.floor
            && locations::Polygon::from_pairs(&zone.polygon)
                .is_ok_and(|polygon| polygon.contains(&point))
    })
}

#[cfg(test)]
mod tests {
    use domain::{CommandName, RobotId};
    use uuid::Uuid;

    use super::{CommandLog, LoggedCommand};

    #[test]
    fn staff_pause_is_reverted_once() -> Result<(), Box<dyn std::error::Error>> {
        let log = CommandLog::new();
        let robot: RobotId = "r1".parse()?;
        let id = Uuid::new_v4();
        log.record(LoggedCommand {
            id,
            robot: robot.clone(),
            name: CommandName::Pause,
            by_admin: false,
            reverted_by: None,
        });
        let reserved = log
            .reserve_revert(&robot, id)
            .map_err(|e| e.message().to_owned())?;
        assert_eq!(reserved.name, CommandName::Pause);
        assert!(log.reserve_revert(&robot, id).is_err());
        let by = Uuid::new_v4();
        log.mark_reverted(id, by);
        assert!(log.reserve_revert(&robot, id).is_err());
        log.latch_estop(&robot);
        assert!(log.is_latched(&robot));
        log.rearm(&robot);
        assert!(!log.is_latched(&robot));
        Ok(())
    }
}
