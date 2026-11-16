//! The simulated robot's behaviour, independent of how it is connected.
//!
//! [`SimDriver::run`] speaks contract C2 over any [`RobotTransport`]: `hello`, then
//! `robot.state` every `state_interval` (and at once after every change), and the answers to
//! what the server sends:
//! - `task.assign`: `task.event` `assigned` at once, `en_route` 2 s later, `delivered` once the
//!   robot reached the destination and at least 2 s after `en_route`; a robot already busy
//!   answers `failed` (`handed_to_human`). A destination (or origin) it cannot reach on its
//!   floor, or not on the plan, follows [`Unreachable`] (ruling R21): the in-process robots of
//!   `--mock` answer `failed` (`path_blocked`) at once and never show `holding`; the
//!   `fake_robot` binary keeps the 2 s timeline (`en_route`, `delivered`) without moving and
//!   logs that the destination is not on its floor;
//! - `task.cancel`: drops the task and goes back to its round;
//! - `zones.update`: `zone.ack` with every zone version;
//! - `command`: `pause` and `estop` stop it (`paused`, `estop`), `resume` moves it again, `dock`
//!   sends it home, `shutdown` answers `failed` (`robot_lost`) for a running task and ends the
//!   session.
//!
//! Between tasks the robot loops along its round (places of its floor, joined by
//! [`SimPlanner::route`]). Everything here is simulated: no motor, no sensor.

use std::collections::{BTreeMap, VecDeque};
use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use domain::{
    CommandName, FailureReason, ItemId, PlaceId, RobotId, RobotStatus, TaskId, TaskState, ZoneKind,
};
use locations::{MapPoint, Point2, Polygon, Zone};
use realtime::{RobotDown, RobotPose, RobotUp, WireZone};

use super::SimError;
use super::fleet::{SimFleet, SimStatus};
use super::route::SimPlanner;

/// Time between `task.event`s of one task (the brief: 2 s gaps).
pub const TASK_EVENT_GAP: Duration = Duration::from_secs(2);
/// Default speed of a simulated robot, metres per second.
pub const DEFAULT_SPEED_MPS: f64 = 0.7;
/// Default time between two `robot.state` messages.
pub const DEFAULT_STATE_INTERVAL: Duration = Duration::from_secs(1);
/// Default simulation step.
pub const DEFAULT_STEP: Duration = Duration::from_millis(200);
/// Battery used per second of motion, percent.
const BATTERY_DRAIN_PER_S: f32 = 0.02;
/// The battery never shows less than this (simulated: no robot ever runs flat).
const BATTERY_FLOOR: f32 = 20.0;
/// Distance under which a waypoint counts as reached, metres.
const ARRIVED_M: f64 = 0.01;
/// Fleet robots: battery used per second of motion, percent.
const FLEET_DRAIN_PER_S: f32 = 0.05;
/// Fleet robots: lowest battery shown.
const FLEET_BATTERY_FLOOR: f32 = 5.0;
/// Fleet robots: below this they go home to charge, percent.
const LOW_BATTERY: f32 = 20.0;
/// Fleet robots: charge gained per second while charging, percent.
const CHARGE_PER_S: f32 = 2.0;
/// Fleet robots: distance to the home place that counts as "at home", metres.
const AT_HOME_M: f64 = 0.6;

/// How a simulated robot reaches the server: a WebSocket (`fake_robot`) or the hub's
/// in-process link (`--mock`).
#[async_trait]
pub trait RobotTransport: Send {
    /// Sends one message to the server.
    ///
    /// # Errors
    /// When the connection is gone.
    async fn send(&mut self, up: RobotUp) -> Result<(), SimError>;
    /// The next message from the server; `None` when the server closed the connection
    /// normally. Cancel-safe: nothing is lost when the future is dropped.
    ///
    /// # Errors
    /// When the connection failed or the server closed it with an error code.
    async fn recv(&mut self) -> Result<Option<RobotDown>, SimError>;
}

/// Why a simulated robot's session ended without an error.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionEnd {
    /// The server closed the connection.
    Closed,
    /// The server sent `shutdown`.
    Shutdown,
}

/// What a simulated robot does with a task it cannot reach (ruling R21).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Unreachable {
    /// Answer `failed` with `path_blocked` at once (the in-process robots of `--mock`).
    FailPathBlocked,
    /// Keep the 2 s timeline without moving and log it (the `fake_robot` binary, gate M0).
    TimedDelivery,
}

/// What a simulated robot is and how it behaves.
#[derive(Debug, Clone)]
pub struct SimRobotConfig {
    robot_id: RobotId,
    role_card: String,
    start: RobotPose,
    battery_pct: f32,
    round: Vec<PlaceId>,
    home: Option<PlaceId>,
    speed_mps: f64,
    state_interval: Duration,
    step: Duration,
    unreachable: Unreachable,
    /// The live server's fleet: wander, route around restricted zones, go home.
    fleet: Option<Arc<SimFleet>>,
    /// Seed of the wandering choices.
    seed: u64,
    /// `simulated` in `hello` (default true; an external stand-in robot may say false).
    simulated: bool,
}

impl SimRobotConfig {
    /// A robot starting at `start` that loops along `round` (places of its floor; places of
    /// other floors or not on the plan are skipped with a warning).
    #[must_use]
    pub fn new(robot_id: RobotId, start: RobotPose, round: Vec<PlaceId>) -> SimRobotConfig {
        SimRobotConfig {
            robot_id,
            role_card: "fetch".to_owned(),
            start,
            battery_pct: 90.0,
            round,
            home: None,
            speed_mps: DEFAULT_SPEED_MPS,
            state_interval: DEFAULT_STATE_INTERVAL,
            step: DEFAULT_STEP,
            unreachable: Unreachable::TimedDelivery,
            fleet: None,
            seed: 0,
            simulated: true,
        }
    }

    /// A robot of the live server's fleet: it wanders to random places instead of looping
    /// along its round, routes like the dispatcher (around restricted zones), goes to the
    /// fleet's home place on `dock`, in an emergency and when its battery is low, and
    /// accepts teleports.
    #[must_use]
    pub fn with_fleet(mut self, fleet: Arc<SimFleet>, seed: u64) -> SimRobotConfig {
        self.fleet = Some(fleet);
        self.seed = seed;
        self
    }

    /// What it does with a task it cannot reach (default [`Unreachable::TimedDelivery`]).
    #[must_use]
    pub fn with_unreachable(mut self, unreachable: Unreachable) -> SimRobotConfig {
        self.unreachable = unreachable;
        self
    }

    /// What `hello` says about `simulated`.
    #[must_use]
    pub fn with_simulated(mut self, simulated: bool) -> SimRobotConfig {
        self.simulated = simulated;
        self
    }

    /// The role card announced in `hello`.
    #[must_use]
    pub fn with_role_card(mut self, role_card: impl Into<String>) -> SimRobotConfig {
        self.role_card = role_card.into();
        self
    }

    /// Battery at start, clamped to 0–100 %.
    #[must_use]
    pub fn with_battery(mut self, battery_pct: f32) -> SimRobotConfig {
        self.battery_pct = if battery_pct.is_finite() {
            battery_pct.clamp(0.0, 100.0)
        } else {
            self.battery_pct
        };
        self
    }

    /// The dock `dock` sends it to.
    #[must_use]
    pub fn with_home(mut self, home: PlaceId) -> SimRobotConfig {
        self.home = Some(home);
        self
    }

    /// Time between two `robot.state` messages (at least the step).
    #[must_use]
    pub fn with_state_interval(mut self, interval: Duration) -> SimRobotConfig {
        self.state_interval = interval.max(self.step);
        self
    }

    /// The robot's id.
    #[must_use]
    pub fn robot_id(&self) -> &RobotId {
        &self.robot_id
    }
}

/// What the robot is doing.
#[derive(Debug, Clone)]
enum Activity {
    /// Looping along its round.
    Round,
    /// Working on a task.
    Task(SimTask),
    /// Going home after `dock`.
    Docking,
    /// At home after `dock`, until `resume`.
    Docked,
}

/// Why a fleet robot went home.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DockReason {
    /// The `dock` command.
    Command,
    /// Emergency mode.
    Emergency,
    /// Low battery: it charges, then wanders again.
    Battery,
}

/// Where a task stands on the robot.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TaskPhase {
    /// `assigned` sent; `en_route` follows after [`TASK_EVENT_GAP`].
    Assigned,
    /// `en_route` sent; `delivered` when arrived and after [`TASK_EVENT_GAP`].
    EnRoute,
}

/// A task the robot is running.
#[derive(Debug, Clone)]
struct SimTask {
    id: TaskId,
    item: Option<ItemId>,
    phase: TaskPhase,
    /// Time spent in the phase while not halted.
    in_phase: Duration,
    route: Vec<MapPoint>,
    /// Where the task ends (re-planned after a teleport).
    goal: Option<MapPoint>,
}

/// A stop ordered by the server.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Halt {
    Moving,
    Paused,
    Estop,
}

/// What one handled message or one step produced.
#[derive(Debug, Default)]
struct Outcome {
    /// Messages to send, in order.
    messages: Vec<RobotUp>,
    /// Whether the robot state changed (a `robot.state` is sent at once).
    changed: bool,
    /// Whether the session must end (`shutdown`).
    shutdown: bool,
}

/// One simulated robot.
#[derive(Debug)]
pub struct SimDriver {
    config: SimRobotConfig,
    planner: Arc<SimPlanner>,
    pose: RobotPose,
    battery_pct: f32,
    holding: Option<ItemId>,
    halt: Halt,
    activity: Activity,
    path: VecDeque<MapPoint>,
    round: Vec<MapPoint>,
    round_next: usize,
    /// The latest zone list the server sent; `None` until the first `zones.update`.
    zones: Option<Vec<DeafArea>>,
    /// The restricted zones of that list (fleet routing avoids them).
    restricted: Vec<Zone>,
    /// Why it is going home or at home.
    dock_reason: DockReason,
    /// Emergency mode at the previous step.
    was_emergency: bool,
    /// Random state of the wandering choices.
    random: u64,
}

/// A deaf zone the robot checks its position against.
#[derive(Debug, Clone)]
struct DeafArea {
    floor: i32,
    polygon: Polygon,
}

impl SimDriver {
    /// A robot at its start pose, ready to loop along its round.
    #[must_use]
    pub fn new(config: SimRobotConfig, planner: Arc<SimPlanner>) -> SimDriver {
        let pose = config.start;
        let round = round_points(&config, &planner);
        SimDriver {
            battery_pct: config.battery_pct,
            planner,
            pose,
            holding: None,
            halt: Halt::Moving,
            activity: Activity::Round,
            path: VecDeque::new(),
            round,
            round_next: 0,
            zones: None,
            restricted: Vec::new(),
            dock_reason: DockReason::Command,
            was_emergency: false,
            random: config
                .seed
                .wrapping_mul(0x9E37_79B9_7F4A_7C15)
                .wrapping_add(7),
            config,
        }
    }

    /// Plays the robot over `transport` until the server closes the connection or sends
    /// `shutdown`.
    ///
    /// # Errors
    /// When the transport fails.
    pub async fn run<T: RobotTransport + ?Sized>(
        mut self,
        transport: &mut T,
    ) -> Result<SessionEnd, SimError> {
        transport.send(self.hello()).await?;
        transport.send(self.state()).await?;
        let step = self.config.step;
        let mut ticker = tokio::time::interval(step);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut since_state = Duration::ZERO;
        loop {
            let outcome = tokio::select! {
                down = transport.recv() => match down? {
                    Some(down) => self.handle(down),
                    None => return Ok(SessionEnd::Closed),
                },
                _ = ticker.tick() => {
                    since_state = since_state.saturating_add(step);
                    self.step(step)
                }
            };
            for message in outcome.messages {
                transport.send(message).await?;
            }
            if outcome.shutdown {
                return Ok(SessionEnd::Shutdown);
            }
            if outcome.changed || since_state >= self.config.state_interval {
                transport.send(self.state()).await?;
                since_state = Duration::ZERO;
            }
        }
    }

    /// The `hello` message.
    fn hello(&self) -> RobotUp {
        RobotUp::Hello {
            robot_id: self.config.robot_id.clone(),
            role_card: self.config.role_card.clone(),
            capabilities: vec!["fetch".to_owned(), "deliver".to_owned()],
            simulated: self.config.simulated,
            running_task: self.task().map(|task| task.id.clone()),
            ble_id: None,
        }
    }

    /// The `robot.state` message.
    fn state(&self) -> RobotUp {
        RobotUp::State {
            pos: self.pose,
            battery_pct: self.battery_pct,
            status: self.status(),
            holding: self.holding.clone(),
            mic_open: self.mic_open(),
        }
    }

    /// Whether the microphone is open: closed until the first zone list arrived (the server
    /// sends it on connect), and closed inside a deaf zone of the robot's floor. Restricted
    /// zones do not affect it. The pose is always known to a simulated robot.
    fn mic_open(&self) -> bool {
        if self.zones.is_none() {
            return false;
        }
        // A pose that is not a number is not "known": stay closed.
        Point2::new(self.pose.x, self.pose.y).is_ok() && !self.in_deaf_zone()
    }

    /// Whether the robot stands in a deaf zone of its floor (of the latest zone list).
    fn in_deaf_zone(&self) -> bool {
        let (Some(zones), Ok(point)) = (&self.zones, Point2::new(self.pose.x, self.pose.y)) else {
            return false;
        };
        zones
            .iter()
            .any(|zone| zone.floor == self.pose.floor && zone.polygon.contains(&point))
    }

    /// The status reported: the halt first, then busy with a task, else idle.
    fn status(&self) -> RobotStatus {
        match (self.halt, &self.activity) {
            (Halt::Estop, _) => RobotStatus::Estop,
            (Halt::Paused, _) => RobotStatus::Paused,
            (Halt::Moving, Activity::Task(_)) => RobotStatus::Busy,
            (Halt::Moving, _) => RobotStatus::Idle,
        }
    }

    fn task(&self) -> Option<&SimTask> {
        match &self.activity {
            Activity::Task(task) => Some(task),
            _ => None,
        }
    }

    /// Answers one server message.
    fn handle(&mut self, down: RobotDown) -> Outcome {
        match down {
            RobotDown::TaskAssign {
                task_id,
                item,
                from_place,
                to_place,
                ..
            } => self.assign(task_id, item, from_place.as_ref(), &to_place),
            RobotDown::TaskCancel { task_id } => {
                if self.task().is_some_and(|task| task.id == task_id) {
                    self.back_to_round();
                    return changed(Vec::new());
                }
                Outcome::default()
            }
            RobotDown::ZonesUpdate { zones, .. } => {
                let zone_version_by_id: BTreeMap<_, _> = zones
                    .iter()
                    .map(|zone| (zone.id.clone(), zone.version))
                    .collect();
                self.zones = Some(self.deaf_areas(&zones));
                self.restricted = restricted_zones(&zones);
                // The microphone may change: report the state at once, after the ack.
                changed(vec![RobotUp::ZoneAck { zone_version_by_id }])
            }
            RobotDown::MapUpdate { version } => {
                tracing::info!(robot = %self.config.robot_id, %version, "simulated robot: the active plan changed; it keeps its round");
                Outcome::default()
            }
            RobotDown::Command { name } => self.command(name),
        }
    }

    /// The deaf zones of a list, as polygons. A zone whose polygon is not valid (fewer than
    /// three points, crossing edges, ...) cannot contain any point: it is dropped, with one
    /// warning per list, and never closes the microphone.
    fn deaf_areas(&self, zones: &[WireZone]) -> Vec<DeafArea> {
        zones
            .iter()
            .filter(|zone| zone.kind == ZoneKind::Deaf)
            .filter_map(|zone| match Polygon::from_pairs(&zone.polygon) {
                Ok(polygon) => Some(DeafArea {
                    floor: zone.floor,
                    polygon,
                }),
                Err(error) => {
                    tracing::warn!(robot = %self.config.robot_id, zone = %zone.id, %error, "simulated robot: a deaf zone has an invalid polygon; it is ignored");
                    None
                }
            })
            .collect()
    }

    fn assign(
        &mut self,
        task_id: TaskId,
        item: Option<ItemId>,
        from_place: Option<&PlaceId>,
        to_place: &PlaceId,
    ) -> Outcome {
        if self.task().is_some() {
            return Outcome {
                messages: vec![task_event(
                    task_id,
                    TaskState::Failed,
                    Some(FailureReason::HandedToHuman),
                )],
                ..Outcome::default()
            };
        }
        let floor = self.pose.floor;
        let mut route = Vec::new();
        let mut at = [self.pose.x, self.pose.y];
        let mut reachable = true;
        for place in from_place.into_iter().chain(Some(to_place)) {
            let leg = self
                .planner
                .place(place)
                .filter(|(place_floor, _)| *place_floor == floor)
                .and_then(|(_, point)| self.find_route(floor, at, point).map(|leg| (leg, point)));
            if let Some((leg, point)) = leg {
                route.extend(leg);
                at = point;
            } else {
                reachable = false;
            }
        }
        if !reachable {
            match self.config.unreachable {
                Unreachable::FailPathBlocked => {
                    tracing::info!(robot = %self.config.robot_id, task = %task_id, %to_place, "simulated robot cannot reach the task's places on its floor; answering failed (path_blocked)");
                    return Outcome {
                        messages: vec![task_event(
                            task_id,
                            TaskState::Failed,
                            Some(FailureReason::PathBlocked),
                        )],
                        ..Outcome::default()
                    };
                }
                Unreachable::TimedDelivery => {
                    tracing::warn!(robot = %self.config.robot_id, task = %task_id, %to_place, floor, "destination is not on this robot's floor (or not on the plan): simulated delivery on the 2 s timeline without moving there");
                    route.clear();
                }
            }
        }
        self.path.clear();
        let goal = route.last().copied();
        self.activity = Activity::Task(SimTask {
            id: task_id.clone(),
            item,
            phase: TaskPhase::Assigned,
            in_phase: Duration::ZERO,
            route,
            goal,
        });
        changed(vec![task_event(task_id, TaskState::Assigned, None)])
    }

    fn command(&mut self, name: CommandName) -> Outcome {
        match name {
            CommandName::Pause => {
                if self.halt == Halt::Moving {
                    self.halt = Halt::Paused;
                }
            }
            CommandName::Estop => self.halt = Halt::Estop,
            CommandName::Resume => {
                self.halt = Halt::Moving;
                if matches!(self.activity, Activity::Docked) {
                    self.back_to_round();
                }
            }
            CommandName::Dock => {
                let mut messages = Vec::new();
                if let Some(task) = self.task() {
                    messages.push(task_event(
                        task.id.clone(),
                        TaskState::Failed,
                        Some(FailureReason::HandedToHuman),
                    ));
                }
                self.holding = None;
                let emergency = self
                    .config
                    .fleet
                    .as_ref()
                    .is_some_and(|fleet| fleet.emergency());
                self.go_home(if emergency {
                    DockReason::Emergency
                } else {
                    DockReason::Command
                });
                return changed(messages);
            }
            CommandName::Shutdown => {
                let messages = self
                    .task()
                    .map(|task| {
                        task_event(
                            task.id.clone(),
                            TaskState::Failed,
                            Some(FailureReason::RobotLost),
                        )
                    })
                    .into_iter()
                    .collect();
                return Outcome {
                    messages,
                    shutdown: true,
                    ..Outcome::default()
                };
            }
        }
        changed(Vec::new())
    }

    /// Advances the simulation by `dt`; a fleet robot also applies a teleport, follows the
    /// emergency mode and its battery, and reports its status to the fleet.
    fn step(&mut self, dt: Duration) -> Outcome {
        let Some(fleet) = self.config.fleet.clone() else {
            return self.step_moving(dt);
        };
        let mut outcome = Outcome::default();
        if let Some(pose) = fleet.take_teleport(&self.config.robot_id) {
            self.teleport(pose);
            outcome.changed = true;
        }
        if self.halt == Halt::Moving {
            outcome.changed |= self.fleet_rules(&fleet, dt);
        }
        let moved = self.step_moving(dt);
        outcome.messages.extend(moved.messages);
        outcome.changed |= moved.changed;
        fleet.report(&self.config.robot_id, self.fleet_status());
        outcome
    }

    /// Emergency mode, low battery, charging and wandering (fleet robots). Returns whether the
    /// state changed.
    fn fleet_rules(&mut self, fleet: &SimFleet, dt: Duration) -> bool {
        let emergency = fleet.emergency();
        let mut changed = false;
        if self.was_emergency
            && !emergency
            && matches!(self.activity, Activity::Docking | Activity::Docked)
            && self.dock_reason == DockReason::Emergency
        {
            self.back_to_round();
            changed = true;
        }
        self.was_emergency = emergency;
        if matches!(self.activity, Activity::Round) {
            if emergency {
                self.go_home(DockReason::Emergency);
                return true;
            }
            if self.battery_pct < LOW_BATTERY {
                self.go_home(DockReason::Battery);
                return true;
            }
            if self.path.is_empty() {
                self.wander();
            }
        }
        if matches!(self.activity, Activity::Docked)
            && (self.at_home() || self.dock_reason == DockReason::Battery)
            && self.battery_pct < 100.0
        {
            self.battery_pct = (self.battery_pct + CHARGE_PER_S * dt.as_secs_f32()).min(100.0);
            if self.battery_pct >= 100.0 && self.dock_reason == DockReason::Battery && !emergency {
                self.back_to_round();
                changed = true;
            }
        }
        changed
    }

    /// What a fleet robot reports.
    fn fleet_status(&self) -> SimStatus {
        let docked = matches!(self.activity, Activity::Docked);
        let at_home = docked && self.at_home();
        SimStatus {
            going_home: matches!(self.activity, Activity::Docking),
            charging: docked
                && self.battery_pct < 100.0
                && (at_home || self.dock_reason == DockReason::Battery),
            at_home,
            in_deaf_zone: self.in_deaf_zone(),
        }
    }

    /// Whether the robot stands at the home place.
    fn at_home(&self) -> bool {
        self.home_point().is_some_and(|(floor, point)| {
            floor == self.pose.floor
                && (point[0] - self.pose.x).hypot(point[1] - self.pose.y) <= AT_HOME_M
        })
    }

    /// The home place: the fleet's, else the configured dock.
    fn home_point(&self) -> Option<(i32, MapPoint)> {
        match &self.config.fleet {
            Some(fleet) => fleet.home_point(),
            None => self
                .config
                .home
                .as_ref()
                .and_then(|home| self.planner.place(home)),
        }
    }

    /// A route on `floor`: the fleet's (around restricted zones), else the simple planner's.
    fn find_route(&self, floor: i32, from: MapPoint, to: MapPoint) -> Option<Vec<MapPoint>> {
        match &self.config.fleet {
            Some(fleet) => fleet.route(floor, from, to, &self.restricted),
            None => self.planner.find_route(floor, from, to),
        }
    }

    /// Heads home (drops the path); without a reachable home on its floor it stops where it
    /// is (`Docked`). The fake robot keeps its straight-line fallback.
    fn go_home(&mut self, reason: DockReason) {
        self.path.clear();
        self.dock_reason = reason;
        let floor = self.pose.floor;
        let from = [self.pose.x, self.pose.y];
        let route = self
            .home_point()
            .filter(|(home_floor, _)| *home_floor == floor)
            .and_then(|(_, point)| {
                if self.config.fleet.is_some() {
                    self.find_route(floor, from, point)
                } else {
                    Some(self.planner.route(floor, from, point))
                }
            });
        if let Some(route) = route {
            self.path.extend(route);
            self.activity = Activity::Docking;
        } else {
            self.activity = Activity::Docked;
        }
    }

    /// Picks a random place of its floor (not where it stands, not in a restricted zone) and
    /// routes there; tries a few places, else waits for the next step.
    fn wander(&mut self) {
        let Some(fleet) = self.config.fleet.clone() else {
            return;
        };
        let floor = self.pose.floor;
        let here = [self.pose.x, self.pose.y];
        let candidates: Vec<MapPoint> = fleet
            .places_on(floor)
            .into_iter()
            .map(|(_, point)| point)
            .filter(|point| (point[0] - here[0]).hypot(point[1] - here[1]) > 1.0)
            .filter(|point| !self.in_restricted(floor, *point))
            .collect();
        for _ in 0..3 {
            let Some(target) = self.pick(&candidates) else {
                return;
            };
            if let Some(route) = self.find_route(floor, here, target)
                && !route.is_empty()
            {
                self.path.extend(route);
                return;
            }
        }
    }

    /// Whether `point` of `floor` is in a restricted zone of the latest list.
    fn in_restricted(&self, floor: i32, point: MapPoint) -> bool {
        Point2::new(point[0], point[1]).is_ok_and(|point| {
            self.restricted
                .iter()
                .any(|zone| zone.floor == floor && zone.polygon.contains(&point))
        })
    }

    /// One of `items` (`SplitMix64`).
    fn pick(&mut self, items: &[MapPoint]) -> Option<MapPoint> {
        self.random = self.random.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.random;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
        let len = u64::try_from(items.len()).ok().filter(|len| *len > 0)?;
        items.get(usize::try_from(z % len).ok()?).copied()
    }

    /// Jumps to `pose`, then re-plans what it was doing from there.
    fn teleport(&mut self, pose: RobotPose) {
        self.pose = RobotPose {
            heading: self.pose.heading,
            ..pose
        };
        self.path.clear();
        let floor = self.pose.floor;
        let here = [self.pose.x, self.pose.y];
        let replanned = match &self.activity {
            Activity::Task(task) => task
                .goal
                .map(|goal| self.find_route(floor, here, goal).unwrap_or_default()),
            _ => None,
        };
        match &mut self.activity {
            Activity::Task(task) => {
                let route = replanned.unwrap_or_default();
                if task.phase == TaskPhase::EnRoute {
                    self.path = route.iter().copied().collect();
                }
                task.route = route;
            }
            Activity::Docking => {
                let reason = self.dock_reason;
                self.go_home(reason);
            }
            Activity::Round | Activity::Docked => {}
        }
    }

    /// Advances the motion and the task timeline by `dt` (nothing while halted).
    fn step_moving(&mut self, dt: Duration) -> Outcome {
        if self.halt != Halt::Moving {
            return Outcome::default();
        }
        let mut outcome = Outcome::default();
        if let Activity::Task(task) = &mut self.activity {
            task.in_phase = task.in_phase.saturating_add(dt);
            match task.phase {
                TaskPhase::Assigned if task.in_phase >= TASK_EVENT_GAP => {
                    task.phase = TaskPhase::EnRoute;
                    task.in_phase = Duration::ZERO;
                    self.path = task.route.iter().copied().collect();
                    self.holding.clone_from(&task.item);
                    outcome = changed(vec![task_event(task.id.clone(), TaskState::EnRoute, None)]);
                }
                TaskPhase::EnRoute if self.path.is_empty() && task.in_phase >= TASK_EVENT_GAP => {
                    let id = task.id.clone();
                    self.back_to_round();
                    return changed(vec![task_event(id, TaskState::Delivered, None)]);
                }
                TaskPhase::Assigned | TaskPhase::EnRoute => {}
            }
        }
        let moving = match self.activity {
            Activity::Round => {
                if self.path.is_empty()
                    && self.config.fleet.is_none()
                    && let Some(next) = self.round.get(self.round_next).copied()
                {
                    self.path.push_back(next);
                    self.round_next = (self.round_next + 1) % self.round.len().max(1);
                }
                true
            }
            Activity::Task(ref task) => task.phase == TaskPhase::EnRoute,
            Activity::Docking => {
                if self.path.is_empty() {
                    self.activity = Activity::Docked;
                    outcome.changed = true;
                }
                true
            }
            Activity::Docked => false,
        };
        if moving {
            self.advance(self.config.speed_mps * dt.as_secs_f64(), dt);
        }
        outcome
    }

    /// Moves `distance` metres along the path.
    fn advance(&mut self, mut distance: f64, dt: Duration) {
        let mut moved = false;
        while distance > 0.0 {
            let Some(target) = self.path.front().copied() else {
                break;
            };
            let (dx, dy) = (target[0] - self.pose.x, target[1] - self.pose.y);
            let gap = dx.hypot(dy);
            if gap > ARRIVED_M {
                self.pose.heading = dy.atan2(dx);
            }
            if gap <= distance {
                self.pose.x = target[0];
                self.pose.y = target[1];
                distance -= gap;
                self.path.pop_front();
            } else {
                self.pose.x += dx / gap * distance;
                self.pose.y += dy / gap * distance;
                distance = 0.0;
            }
            moved = true;
        }
        if moved {
            let (drain, floor) = if self.config.fleet.is_some() {
                (FLEET_DRAIN_PER_S, FLEET_BATTERY_FLOOR)
            } else {
                (BATTERY_DRAIN_PER_S, BATTERY_FLOOR)
            };
            self.battery_pct = (self.battery_pct - drain * dt.as_secs_f32()).max(floor);
        }
    }

    /// Ends the task (if any) and heads for the next point of the round along a route.
    fn back_to_round(&mut self) {
        self.activity = Activity::Round;
        self.holding = None;
        self.path.clear();
        if self.config.fleet.is_some() {
            // A fleet robot picks its next place at its next step.
            return;
        }
        if let Some(next) = self.round.get(self.round_next).copied() {
            let floor = self.pose.floor;
            self.path
                .extend(self.planner.route(floor, [self.pose.x, self.pose.y], next));
            self.round_next = (self.round_next + 1) % self.round.len().max(1);
        }
    }
}

/// The restricted zones of a list, for routing; invalid polygons are dropped.
fn restricted_zones(zones: &[WireZone]) -> Vec<Zone> {
    zones
        .iter()
        .filter(|zone| zone.kind == ZoneKind::Restricted)
        .filter_map(|zone| {
            Some(Zone {
                id: zone.id.clone(),
                kind: zone.kind,
                floor: zone.floor,
                polygon: Polygon::from_pairs(&zone.polygon).ok()?,
                version: zone.version,
            })
        })
        .collect()
}

/// An outcome that changed the robot state.
fn changed(messages: Vec<RobotUp>) -> Outcome {
    Outcome {
        messages,
        changed: true,
        shutdown: false,
    }
}

fn task_event(task_id: TaskId, state: TaskState, reason: Option<FailureReason>) -> RobotUp {
    RobotUp::TaskEvent {
        task_id,
        state,
        reason,
    }
}

/// The round as a closed polyline: each leg between two round places is a planner route.
fn round_points(config: &SimRobotConfig, planner: &SimPlanner) -> Vec<MapPoint> {
    let floor = config.start.floor;
    let stops: Vec<MapPoint> = config
        .round
        .iter()
        .filter_map(|place| match planner.place(place) {
            Some((place_floor, point)) if place_floor == floor => Some(point),
            Some(_) => {
                tracing::warn!(robot = %config.robot_id, %place, floor, "round place is on another floor; skipped");
                None
            }
            None => {
                tracing::warn!(robot = %config.robot_id, %place, "round place is not on the plan; skipped");
                None
            }
        })
        .collect();
    let Some(first) = stops.first().copied() else {
        return Vec::new();
    };
    let mut points = planner.route(floor, [config.start.x, config.start.y], first);
    if stops.len() < 2 {
        return points;
    }
    // The loop starts at the first stop: drop the approach from the start pose.
    points.clear();
    let mut at = first;
    for next in stops.iter().skip(1).chain(Some(&first)) {
        points.extend(planner.route(floor, at, *next));
        at = *next;
    }
    points
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use std::time::Duration;

    use domain::{CommandName, FailureReason, RobotStatus, TaskState, ZoneKind};
    use realtime::{RobotDown, RobotPose, RobotUp, WireZone};

    use super::{SimDriver, SimRobotConfig, TASK_EVENT_GAP, Unreachable};
    use crate::sim::route::SimPlanner;
    use crate::sim::seed_plan;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn driver() -> Result<SimDriver, Box<dyn std::error::Error>> {
        let planner = Arc::new(SimPlanner::new(&seed_plan()?));
        let (floor, [x, y]) = planner.place(&"dock-w".parse()?).ok_or("no dock-w")?;
        let config = SimRobotConfig::new(
            "r2".parse()?,
            RobotPose {
                x,
                y,
                heading: 0.0,
                floor,
            },
            vec!["dock-w".parse()?, "room-12".parse()?, "lounge".parse()?],
        )
        .with_home("dock-w".parse()?);
        Ok(SimDriver::new(config, planner))
    }

    fn states(messages: &[RobotUp]) -> Vec<TaskState> {
        messages
            .iter()
            .filter_map(|message| match message {
                RobotUp::TaskEvent { state, .. } => Some(*state),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn it_moves_along_its_round_and_stops_when_paused() -> TestResult {
        let mut robot = driver()?;
        let start = robot.pose;
        for _ in 0..10 {
            robot.step(Duration::from_millis(200));
        }
        assert!(robot.pose != start, "the robot did not move");
        robot.handle(RobotDown::Command {
            name: CommandName::Pause,
        });
        assert_eq!(robot.status(), RobotStatus::Paused);
        let paused_at = robot.pose;
        for _ in 0..10 {
            robot.step(Duration::from_millis(200));
        }
        assert_eq!(robot.pose, paused_at);
        robot.handle(RobotDown::Command {
            name: CommandName::Estop,
        });
        assert_eq!(robot.status(), RobotStatus::Estop);
        // The driver resumes whenever it is told to: who may re-arm a robot after an
        // emergency stop (an admin only, ruling R24) is gated by the server.
        robot.handle(RobotDown::Command {
            name: CommandName::Resume,
        });
        robot.step(Duration::from_millis(200));
        assert!(robot.pose != paused_at, "resume did not move the robot");
        assert_eq!(robot.status(), RobotStatus::Idle);
        Ok(())
    }

    #[test]
    fn a_task_off_the_plan_is_assigned_en_route_delivered_two_seconds_apart() -> TestResult {
        let mut robot = driver()?;
        let first = robot.handle(RobotDown::TaskAssign {
            task_id: "t-9".parse()?,
            kind: domain::TaskKind::Fetch,
            item: Some("blanket".parse()?),
            from_place: Some("storeroom".parse()?),
            to_place: "room-101".parse()?,
            deadline: None,
        });
        assert_eq!(states(&first.messages), vec![TaskState::Assigned]);
        assert_eq!(robot.status(), RobotStatus::Busy);
        let mut seen = Vec::new();
        let step = Duration::from_millis(100);
        let mut elapsed = Duration::ZERO;
        while elapsed < TASK_EVENT_GAP * 3 {
            let outcome = robot.step(step);
            elapsed += step;
            for state in states(&outcome.messages) {
                seen.push((state, elapsed));
            }
        }
        assert_eq!(
            seen,
            vec![
                (TaskState::EnRoute, TASK_EVENT_GAP),
                (TaskState::Delivered, TASK_EVENT_GAP * 2)
            ]
        );
        assert_eq!(robot.status(), RobotStatus::Idle);
        Ok(())
    }

    #[test]
    fn a_busy_robot_hands_a_second_task_back() -> TestResult {
        let mut robot = driver()?;
        let assign = |id: &str| -> Result<RobotDown, Box<dyn std::error::Error>> {
            Ok(RobotDown::TaskAssign {
                task_id: id.parse()?,
                kind: domain::TaskKind::Fetch,
                item: None,
                from_place: None,
                to_place: "room-12".parse()?,
                deadline: None,
            })
        };
        robot.handle(assign("t-1")?);
        let second = robot.handle(assign("t-2")?);
        assert_eq!(states(&second.messages), vec![TaskState::Failed]);
        Ok(())
    }

    fn assign_off_plan() -> Result<RobotDown, Box<dyn std::error::Error>> {
        Ok(RobotDown::TaskAssign {
            task_id: "t-7".parse()?,
            kind: domain::TaskKind::Fetch,
            item: Some("blanket".parse()?),
            from_place: Some("storeroom".parse()?),
            to_place: "room-101".parse()?,
            deadline: None,
        })
    }

    #[test]
    fn a_demo_robot_fails_an_unreachable_task_path_blocked_without_holding() -> TestResult {
        let mut robot = driver()?;
        robot.config = robot
            .config
            .clone()
            .with_unreachable(Unreachable::FailPathBlocked);
        let answer = robot.handle(assign_off_plan()?);
        assert!(matches!(
            answer.messages.as_slice(),
            [RobotUp::TaskEvent {
                state: TaskState::Failed,
                reason: Some(FailureReason::PathBlocked),
                ..
            }]
        ));
        assert_eq!(robot.status(), RobotStatus::Idle);
        for _ in 0..30 {
            robot.step(Duration::from_millis(200));
            assert!(robot.holding.is_none());
        }
        // A place of another floor is unreachable too (dock-w is on floor 2, therapy-1 on 0).
        let other_floor = robot.handle(RobotDown::TaskAssign {
            task_id: "t-8".parse()?,
            kind: domain::TaskKind::Fetch,
            item: None,
            from_place: None,
            to_place: "therapy-1".parse()?,
            deadline: None,
        });
        assert_eq!(states(&other_floor.messages), vec![TaskState::Failed]);
        Ok(())
    }

    #[test]
    fn the_fake_robot_keeps_the_timeline_for_an_unreachable_task() -> TestResult {
        let mut robot = driver()?;
        robot.config = robot
            .config
            .clone()
            .with_unreachable(Unreachable::TimedDelivery);
        let answer = robot.handle(assign_off_plan()?);
        assert_eq!(states(&answer.messages), vec![TaskState::Assigned]);
        Ok(())
    }

    #[test]
    fn shutdown_fails_the_running_task_robot_lost() -> TestResult {
        let mut robot = driver()?;
        robot.handle(assign_off_plan()?);
        let end = robot.handle(RobotDown::Command {
            name: CommandName::Shutdown,
        });
        assert!(end.shutdown);
        assert!(matches!(
            end.messages.as_slice(),
            [RobotUp::TaskEvent {
                state: TaskState::Failed,
                reason: Some(FailureReason::RobotLost),
                ..
            }]
        ));
        Ok(())
    }

    #[test]
    fn zones_are_acknowledged_and_shutdown_ends_the_session() -> TestResult {
        let mut robot = driver()?;
        let ack = robot.handle(RobotDown::ZonesUpdate {
            zones: Vec::new(),
            version: 3,
        });
        assert!(matches!(ack.messages.as_slice(), [RobotUp::ZoneAck { .. }]));
        let end = robot.handle(RobotDown::Command {
            name: CommandName::Shutdown,
        });
        assert!(end.shutdown);
        Ok(())
    }

    fn zone(
        id: &str,
        kind: ZoneKind,
        floor: i32,
        around: RobotPose,
    ) -> Result<WireZone, Box<dyn std::error::Error>> {
        let (x, y) = (around.x, around.y);
        Ok(WireZone {
            id: id.parse()?,
            kind,
            floor,
            polygon: vec![
                [x - 1.0, y - 1.0],
                [x + 1.0, y - 1.0],
                [x + 1.0, y + 1.0],
                [x - 1.0, y + 1.0],
            ],
            version: 1,
        })
    }

    fn mic(robot: &SimDriver) -> Option<bool> {
        match robot.state() {
            RobotUp::State { mic_open, .. } => Some(mic_open),
            _ => None,
        }
    }

    fn send_zones(robot: &mut SimDriver, zones: Vec<WireZone>, version: u64) -> super::Outcome {
        robot.handle(RobotDown::ZonesUpdate { zones, version })
    }

    #[test]
    fn mic_is_closed_until_the_first_zone_list_then_open_outside_deaf_zones() -> TestResult {
        let mut robot = driver()?;
        assert_eq!(mic(&robot), Some(false), "no zone list yet: closed");
        let outcome = send_zones(&mut robot, Vec::new(), 1);
        assert!(outcome.changed, "a new zone list reports the state at once");
        assert_eq!(mic(&robot), Some(true));
        Ok(())
    }

    #[test]
    fn mic_closes_inside_a_deaf_zone_of_its_floor() -> TestResult {
        let mut robot = driver()?;
        let deaf = zone("z-deaf", ZoneKind::Deaf, robot.pose.floor, robot.pose)?;
        send_zones(&mut robot, vec![deaf], 1);
        assert_eq!(mic(&robot), Some(false));
        Ok(())
    }

    #[test]
    fn mic_stays_open_in_a_deaf_zone_of_another_floor_or_a_restricted_zone() -> TestResult {
        let mut robot = driver()?;
        let other = zone("z-up", ZoneKind::Deaf, robot.pose.floor + 1, robot.pose)?;
        let restricted = zone("z-no", ZoneKind::Restricted, robot.pose.floor, robot.pose)?;
        send_zones(&mut robot, vec![other, restricted], 1);
        assert_eq!(mic(&robot), Some(true));
        Ok(())
    }

    #[test]
    fn mic_follows_zone_changes_and_movement_even_when_estopped() -> TestResult {
        let mut robot = driver()?;
        let deaf = zone("z-deaf", ZoneKind::Deaf, robot.pose.floor, robot.pose)?;
        send_zones(&mut robot, vec![deaf.clone()], 1);
        assert_eq!(mic(&robot), Some(false));
        robot.handle(RobotDown::Command {
            name: CommandName::Estop,
        });
        assert_eq!(
            mic(&robot),
            Some(false),
            "an estopped robot reports truthfully"
        );
        send_zones(&mut robot, Vec::new(), 2);
        assert_eq!(mic(&robot), Some(true), "zone deleted: open");
        send_zones(&mut robot, vec![deaf], 3);
        assert_eq!(mic(&robot), Some(false), "zone added: closed");
        robot.pose.x += 5.0;
        assert_eq!(mic(&robot), Some(true), "moved out of the zone: open");
        Ok(())
    }

    #[test]
    fn a_deaf_zone_with_an_invalid_polygon_never_mutes_the_robot() -> TestResult {
        let mut robot = driver()?;
        let at = robot.pose;
        let mut two_points = zone("z-two", ZoneKind::Deaf, at.floor, at)?;
        two_points.polygon = vec![[at.x - 1.0, at.y], [at.x + 1.0, at.y]];
        let mut bowtie = zone("z-bow", ZoneKind::Deaf, at.floor, at)?;
        bowtie.polygon = vec![
            [at.x - 1.0, at.y - 1.0],
            [at.x + 1.0, at.y + 1.0],
            [at.x + 1.0, at.y - 1.0],
            [at.x - 1.0, at.y + 1.0],
        ];
        let mut empty = zone("z-empty", ZoneKind::Deaf, at.floor, at)?;
        empty.polygon = Vec::new();
        let mut nan = zone("z-nan", ZoneKind::Deaf, at.floor, at)?;
        nan.polygon = vec![[f64::NAN, 0.0], [1.0, 0.0], [1.0, 1.0]];
        send_zones(&mut robot, vec![two_points, bowtie, empty, nan], 1);
        assert_eq!(mic(&robot), Some(true));
        let good = zone("z-good", ZoneKind::Deaf, at.floor, at)?;
        let mut broken = zone("z-broken", ZoneKind::Deaf, at.floor, at)?;
        broken.polygon = Vec::new();
        send_zones(&mut robot, vec![broken, good], 2);
        assert_eq!(
            mic(&robot),
            Some(false),
            "a valid zone still works beside a broken one"
        );
        Ok(())
    }

    #[test]
    fn a_robot_on_the_edge_of_a_deaf_zone_has_its_microphone_closed() -> TestResult {
        let mut robot = driver()?;
        let at = robot.pose;
        let mut edge = zone("z-edge", ZoneKind::Deaf, at.floor, at)?;
        edge.polygon = vec![
            [at.x, at.y - 1.0],
            [at.x + 2.0, at.y - 1.0],
            [at.x + 2.0, at.y + 1.0],
            [at.x, at.y + 1.0],
        ];
        send_zones(&mut robot, vec![edge], 1);
        assert_eq!(mic(&robot), Some(false), "the boundary counts as inside");
        Ok(())
    }
}
