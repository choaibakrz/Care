//! The live server's own simulated robots ("happy" robots): when no real robot is around,
//! `clinic-server` (live mode) starts `SIM_ROBOTS` (default 2) in-process robots that wander
//! the active plan, so the console's 3D view shows the fleet moving and the routing can be
//! checked by eye.
//!
//! They are ordinary hub sessions played by [`SimDriver`](super::SimDriver), so the robot
//! service, the dispatcher and the task service treat them like real robots (`simulated:
//! true`). [`SimFleet`] is what they share with the server:
//! - routing: the route preview's planner ([`RoutePreview`], the same rule as the dispatcher:
//!   walls, furniture, lifts and restricted zones are impassable, deaf zones are crossed);
//! - the fleet's home place ([`FleetHome`]) and the system mode (emergency: go home);
//! - teleports asked by `POST /robots/{id}/teleport`;
//! - what each robot reports back (going home, charging, at home, in a deaf zone).

use std::collections::HashMap;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use domain::ports::{RobotRecord, RobotRepository};
use domain::{Clock, PlaceId, RobotId};
use locations::{ActiveMap, MapPoint, Point2, Zone};
use optimization::RoutePreview;
use realtime::{Hub, RobotPose};
use tokio::task::JoinHandle;

use super::{SimPlanner, SimRobotConfig, Unreachable};
use crate::error::StartupError;
use crate::services::fleet_home::FleetHome;
use crate::services::{RobotService, SystemModeService};

/// Default number of simulated robots of the live server (`SIM_ROBOTS`).
pub const DEFAULT_SIM_ROBOTS: usize = 2;
/// Names of the simulated robots, in start order.
const NAMES: [&str; 6] = ["Sunny", "Pip", "Bolt", "Mochi", "Ziggy", "Nova"];
/// The role card they announce (seed `role_cards.json`: every place).
const ROLE_CARD: &str = "demo";
/// How often they report `robot.state`.
const STATE_INTERVAL: Duration = Duration::from_millis(400);

/// What a simulated robot last reported to the fleet.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[allow(
    clippy::struct_excessive_bools,
    reason = "independent flags of one robot"
)]
pub struct SimStatus {
    /// Driving to the home place.
    pub going_home: bool,
    /// Charging its battery.
    pub charging: bool,
    /// Stopped at the home place.
    pub at_home: bool,
    /// Inside a deaf zone.
    pub in_deaf_zone: bool,
}

/// What the simulated robots share with the server.
pub struct SimFleet {
    active: Arc<ActiveMap>,
    preview: RoutePreview,
    home: Arc<FleetHome>,
    system: Arc<dyn SystemModeService>,
    status: Mutex<HashMap<RobotId, SimStatus>>,
    teleports: Mutex<HashMap<RobotId, RobotPose>>,
}

impl std::fmt::Debug for SimFleet {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SimFleet")
            .field("robots", &self.statuses().len())
            .finish_non_exhaustive()
    }
}

impl SimFleet {
    /// A fleet on the plan in force, with its home place and the system mode.
    #[must_use]
    pub fn new(
        active: Arc<ActiveMap>,
        home: Arc<FleetHome>,
        system: Arc<dyn SystemModeService>,
    ) -> SimFleet {
        SimFleet {
            active,
            preview: RoutePreview::new(),
            home,
            system,
            status: Mutex::new(HashMap::new()),
            teleports: Mutex::new(HashMap::new()),
        }
    }

    fn statuses(&self) -> std::sync::MutexGuard<'_, HashMap<RobotId, SimStatus>> {
        self.status.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn teleports(&self) -> std::sync::MutexGuard<'_, HashMap<RobotId, RobotPose>> {
        self.teleports
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
    }

    /// The plan in force.
    #[must_use]
    pub fn active(&self) -> &Arc<ActiveMap> {
        &self.active
    }

    /// The home place store.
    #[must_use]
    pub fn home(&self) -> &Arc<FleetHome> {
        &self.home
    }

    /// Whether the clinic is in emergency mode.
    #[must_use]
    pub fn emergency(&self) -> bool {
        self.system.is_emergency()
    }

    /// The home place's floor and point, when one is set and on the plan.
    #[must_use]
    pub fn home_point(&self) -> Option<(i32, MapPoint)> {
        let current = self.active.current();
        self.home
            .place(&current.plan)
            .map(|place| (place.floor, [place.x, place.y]))
    }

    /// The places of `floor`: id and point.
    #[must_use]
    pub fn places_on(&self, floor: i32) -> Vec<(PlaceId, MapPoint)> {
        self.active
            .current()
            .plan
            .places
            .iter()
            .filter(|place| place.floor == floor)
            .map(|place| (place.id.clone(), [place.x, place.y]))
            .collect()
    }

    /// The waypoints from `from` to `to` on `floor` around walls, furniture, lifts and the
    /// restricted zones among `zones` (the dispatcher's rule), `from` left out; `None` when
    /// there is no way through.
    #[must_use]
    pub fn route(
        &self,
        floor: i32,
        from: MapPoint,
        to: MapPoint,
        zones: &[Zone],
    ) -> Option<Vec<MapPoint>> {
        let start = Point2::new(from[0], from[1]).ok()?;
        let goal = Point2::new(to[0], to[1]).ok()?;
        let current = self.active.current();
        let path = self
            .preview
            .plan(&current.map, zones, start, goal, floor)
            .ok()?;
        let mut points: Vec<MapPoint> = path
            .points
            .iter()
            .map(|point| [point.x(), point.y()])
            .collect();
        if points
            .first()
            .is_some_and(|first| (first[0] - from[0]).hypot(first[1] - from[1]) < 0.05)
        {
            points.remove(0);
        }
        Some(points)
    }

    /// Whether `robot` is one of this fleet's simulated robots.
    #[must_use]
    pub fn is_simulated(&self, robot: &RobotId) -> bool {
        self.statuses().contains_key(robot)
    }

    /// What `robot` reports.
    pub fn report(&self, robot: &RobotId, status: SimStatus) {
        self.statuses().insert(robot.clone(), status);
    }

    /// What `robot` last reported.
    #[must_use]
    pub fn status(&self, robot: &RobotId) -> Option<SimStatus> {
        self.statuses().get(robot).copied()
    }

    /// Asks `robot` to jump to `pose` (applied at its next step).
    pub fn request_teleport(&self, robot: &RobotId, pose: RobotPose) {
        self.teleports().insert(robot.clone(), pose);
    }

    /// The teleport waiting for `robot`, taken.
    #[must_use]
    pub fn take_teleport(&self, robot: &RobotId) -> Option<RobotPose> {
        self.teleports().remove(robot)
    }
}

/// What [`start_happy_robots`] needs.
pub struct HappyRobotsDeps<'a> {
    /// The fleet (attached to the robot service).
    pub fleet: Arc<SimFleet>,
    /// The hub the robots connect through.
    pub hub: Arc<Hub>,
    /// The robot service that runs their sessions.
    pub robots: Arc<dyn RobotService>,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
    /// Where their records are stored.
    pub repo: &'a dyn RobotRepository,
}

/// Registers `count` simulated robots (`sim-sunny`, `sim-pip`, …, `simulated: true`) and
/// starts them on the home floor (or the floor with the most places): the first at the home
/// place, the others at other places. Returns their background tasks.
///
/// # Errors
/// `StartupError::Demo` when a robot record cannot be stored.
pub async fn start_happy_robots(
    deps: HappyRobotsDeps<'_>,
    count: usize,
) -> Result<Vec<JoinHandle<()>>, StartupError> {
    let fleet = deps.fleet;
    let current = fleet.active().current();
    let plan = &current.plan;
    let home = fleet.home_point();
    let floor = home.map(|(floor, _)| floor).or_else(|| {
        plan.floors
            .iter()
            .map(|floor| floor.id)
            .max_by_key(|level| plan.places.iter().filter(|p| p.floor == *level).count())
    });
    let Some(floor) = floor else {
        tracing::warn!("no floor on the plan: no simulated robot started");
        return Ok(Vec::new());
    };
    let mut starts: Vec<MapPoint> = home.map(|(_, point)| point).into_iter().collect();
    starts.extend(fleet.places_on(floor).into_iter().map(|(_, point)| point));
    let mut configs = Vec::new();
    for (index, name) in NAMES.iter().take(count).enumerate() {
        let id: RobotId = format!("sim-{}", name.to_lowercase()).parse().map_err(
            |error: domain::DomainError| StartupError::Demo {
                reason: error.to_string(),
            },
        )?;
        let spread = index.saturating_mul(3) % starts.len().max(1);
        let Some([x, y]) = starts.get(spread).or(starts.first()).copied() else {
            tracing::warn!(floor, "no place on the floor: no simulated robot started");
            return Ok(Vec::new());
        };
        let record = RobotRecord {
            id: id.clone(),
            name: (*name).to_owned(),
            role_card: ROLE_CARD.to_owned(),
            simulated: true,
            // In-process robots never present a key.
            key_hash: String::new(),
        };
        deps.repo
            .upsert(&record)
            .await
            .map_err(|error| StartupError::Demo {
                reason: error.to_string(),
            })?;
        fleet.report(&id, SimStatus::default());
        let battery = 90.0 - 12.0 * f32::from(u8::try_from(index).unwrap_or(0));
        configs.push(
            SimRobotConfig::new(
                id,
                RobotPose {
                    x,
                    y,
                    heading: 0.0,
                    floor,
                },
                Vec::new(),
            )
            .with_role_card(ROLE_CARD)
            .with_battery(battery)
            .with_state_interval(STATE_INTERVAL)
            .with_unreachable(Unreachable::FailPathBlocked)
            .with_fleet(fleet.clone(), u64::try_from(index).unwrap_or(0)),
        );
    }
    let planner = Arc::new(SimPlanner::new(plan));
    Ok(super::spawn_in_process(
        &deps.hub,
        &deps.robots,
        &deps.clock,
        &planner,
        configs,
    ))
}
