//! Demo mode (Task 5b): `clinic-server --demo`, a port of the console's in-browser demo
//! (`admin/src/mock/sim.ts`, `sim-motion.ts`, `sim-tasks.ts`, `sim-admin.ts`).
//!
//! The live server runs as usual (database, journal, dispatcher, stock); simulated robots
//! connect to its hub **as robots** (C2 messages through `Hub::register_robot`), so the real
//! robot service, dispatcher, task and stock services handle them exactly like real robots.
//! The demo adds what people would do: staff requests appear by themselves (every 9 to 21 s,
//! from `seed/demo_fleet.json` destinations and requesters), shelves are counted on rounds.
//! The robots drive the routes of the route preview (Task 13b) at walking speed, avoid each
//! other, close their microphone in deaf zones, never enter restricted zones, go home when
//! idle and charge when low.
//!
//! **Everything says "SIMULATED"**: every demo robot is registered `simulated: true` with a
//! name ending in " (SIMULATED)", every generated task is created with
//! `TaskService::create_as_system(Actor::System("demo"), …)` (ruling R15), whose
//! `requested_by` is `realtime::SIMULATED_REQUEST_LABEL` ("SIMULATED request"), and
//! `GET /health` reports `mode: "demo"`.
//! Nothing here is tested against a real robot.

use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::ports::{
    ClinicRepository, InventoryRepository, RobotRecord, RobotRepository, RoundResult,
    ScheduleRecord, ScheduleRepository, StockLevel, ZoneRecord, ZoneRepository,
};
use domain::{
    Actor, ClinicId, Clock, DomainError, ItemId, PlaceId, RobotId, ScheduleId, TaskKind, ZoneId,
    ZoneKind,
};
use locations::{ActiveMap, ActivePlan, ClinicPlan};
use realtime::{Hub, RobotPose};
use serde::Deserialize;
use tokio::task::JoinHandle;

use super::{RobotService, TaskService};
use crate::dto::NewTask;
use crate::error::StartupError;
use crate::sim::{self, SimPlanner, SimRobotConfig, Unreachable};

/// Suffix of every simulated robot's name.
pub const SIMULATED_SUFFIX: &str = " (SIMULATED)";
/// Seed of the demo's random choices when none is given (the console's `20261114`).
pub const DEFAULT_DEMO_SEED: u64 = 20_261_114;
/// How often simulated robots move and report (`robot.state`), seconds.
pub const DEMO_TICK_S: f64 = 0.2;
/// Simulated walking speed, metres per second.
pub const DEMO_SPEED_M_S: f64 = 0.9;

/// `seed/demo_fleet.json`, written by `scripts/export_console_clinic.mjs` from the console's
/// `seed.ts`. Invented data (`marque`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DemoFleet {
    /// Always `"inventé"`.
    pub marque: String,
    /// Simulated robots.
    pub robots: Vec<DemoRobot>,
    /// Stock items.
    pub items: Vec<DemoItem>,
    /// Zones.
    pub zones: Vec<DemoZone>,
    /// Schedules.
    pub schedules: Vec<DemoSchedule>,
    /// For each shelf place, the places a fetched item from there can be asked for.
    pub destinations: std::collections::BTreeMap<String, Vec<PlaceId>>,
    /// Requester roles, drawn at random for generated requests (repeats weight the draw).
    pub requesters: Vec<String>,
}

/// One simulated robot.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DemoRobot {
    /// Id.
    pub id: RobotId,
    /// Display name (gets [`SIMULATED_SUFFIX`]).
    pub name: String,
    /// Role shown in the console.
    pub role: String,
    /// Dock place it starts from and returns to.
    pub home: PlaceId,
    /// Battery at start, percent.
    pub battery: f32,
    /// Heading at start, radians (0 east, positive toward south).
    pub heading: f64,
}

/// One stock item.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DemoItem {
    /// Id.
    pub id: ItemId,
    /// Label.
    pub label: String,
    /// Shelf place.
    pub place: PlaceId,
    /// Count at start.
    pub count: u32,
    /// Low threshold.
    pub low_at: u32,
}

/// One zone.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DemoZone {
    /// Id.
    pub id: ZoneId,
    /// Name.
    pub name: String,
    /// Floor.
    pub floor: i32,
    /// Kind.
    pub kind: ZoneKind,
    /// Polygon `[x, y]`.
    pub polygon: Vec<[f64; 2]>,
}

/// One schedule.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DemoSchedule {
    /// Id.
    pub id: ScheduleId,
    /// Label.
    pub label: String,
    /// Enabled.
    pub enabled: bool,
    /// Local time `HH:MM`.
    pub time: String,
    /// Robot doing the round.
    pub robot_id: Option<RobotId>,
}

impl DemoFleet {
    /// Reads `seed/demo_fleet.json`.
    ///
    /// # Errors
    /// `StartupError::Io` when unreadable; `StartupError::Demo` when not valid or `marque` is
    /// not `"inventé"`.
    pub fn load(path: &Path) -> Result<DemoFleet, StartupError> {
        let text = std::fs::read_to_string(path).map_err(|source| StartupError::Io {
            action: "read the demo fleet",
            source,
        })?;
        let fleet: DemoFleet = serde_json::from_str(&text).map_err(|error| StartupError::Demo {
            reason: format!("{}: {error}", path.display()),
        })?;
        if fleet.marque != "inventé" {
            return Err(StartupError::Demo {
                reason: format!("{}: `marque` is not \"inventé\"", path.display()),
            });
        }
        Ok(fleet)
    }
}

/// The running demo; dropping it does not stop it, [`DemoHandle::stop`] does.
pub struct DemoHandle {
    tasks: Vec<JoinHandle<()>>,
}

impl DemoHandle {
    /// Stops every simulated robot and the request generator.
    pub fn stop(self) {
        for task in self.tasks {
            task.abort();
        }
    }

    /// The background tasks, for `Wiring::background` (aborted on shutdown).
    #[must_use]
    pub fn into_tasks(self) -> Vec<JoinHandle<()>> {
        self.tasks
    }
}

/// The demo clinic.
pub struct DemoClinic;

impl DemoClinic {
    /// Starts the simulation on the active plan: one task per robot of `fleet` (connected
    /// through `hub` as that robot, sending `hello` with `simulated: true`, then `robot.state`
    /// every [`DEMO_TICK_S`] and `task.event`s as it works), and one request generator that
    /// creates tasks with `tasks.create_as_system(Actor::System("demo"), …)`. Random choices come from
    /// `seed` (`SplitMix64`), so a run is reproducible with a fake `clock`.
    ///
    /// `robots` runs each simulated robot's hub session, as it runs a WebSocket robot's.
    ///
    /// The robots, items, zones and schedules of `fleet` must already be in the database
    /// (`Wiring::demo` stores them before calling this).
    #[allow(
        clippy::needless_pass_by_value,
        reason = "owned arguments keep the call sites simple"
    )]
    #[must_use]
    pub fn start(
        plan: Arc<ActiveMap>,
        fleet: DemoFleet,
        hub: Arc<Hub>,
        clock: Arc<dyn Clock>,
        seed: u64,
        tasks: Arc<dyn TaskService>,
        robots: Arc<dyn RobotService>,
    ) -> DemoHandle {
        let current = plan.current();
        let planner = Arc::new(SimPlanner::new(&current.plan));
        let configs: Vec<SimRobotConfig> = fleet
            .robots
            .iter()
            .filter_map(|robot| {
                let Some((floor, [x, y])) = planner.place(&robot.home) else {
                    tracing::warn!(robot = %robot.id, "demo robot home is not on the plan");
                    return None;
                };
                let start = RobotPose {
                    x,
                    y,
                    heading: robot.heading,
                    floor,
                };
                let mut stops: Vec<&locations::PlanPlace> = current
                    .plan
                    .places
                    .iter()
                    .filter(|place| place.floor == floor)
                    .filter(|place| place.kind != locations::PlaceViewKind::Dock)
                    .collect();
                stops.sort_by(|a, b| a.x.total_cmp(&b.x));
                let round: Vec<PlaceId> = std::iter::once(robot.home.clone())
                    .chain(stops.into_iter().map(|place| place.id.clone()))
                    .collect();
                Some(
                    SimRobotConfig::new(robot.id.clone(), start, round)
                        .with_role_card("demo")
                        .with_battery(robot.battery)
                        .with_home(robot.home.clone())
                        .with_unreachable(Unreachable::FailPathBlocked),
                )
            })
            .collect();
        let mut handles = sim::spawn_in_process(&hub, &robots, &clock, &planner, configs);
        handles.push(tokio::spawn(generate_requests(fleet, seed, tasks)));
        DemoHandle { tasks: handles }
    }
}

/// `SplitMix64`: small, seeded, reproducible.
struct SplitMix64(u64);

impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// One of `items`, or `None` when empty.
    fn pick<'a, T>(&mut self, items: &'a [T]) -> Option<&'a T> {
        let len = u64::try_from(items.len()).ok().filter(|len| *len > 0)?;
        let index = usize::try_from(self.next() % len).ok()?;
        items.get(index)
    }
}

/// First request after this; then every 9 to 21 s.
const FIRST_REQUEST: Duration = Duration::from_secs(2);

/// Creates a simulated staff request now and then: an item of a shelf, fetched to one of the
/// shelf's destinations, as `Actor::System("demo")` (ruling R15).
async fn generate_requests(fleet: DemoFleet, seed: u64, tasks: Arc<dyn TaskService>) {
    let mut random = SplitMix64(seed);
    let shelves: Vec<(&PlaceId, &Vec<PlaceId>)> = fleet
        .destinations
        .iter()
        .filter_map(|(shelf, destinations)| {
            let shelf = fleet
                .items
                .iter()
                .find(|item| item.place.as_str() == shelf)?;
            Some((&shelf.place, destinations))
        })
        .collect();
    let mut wait = FIRST_REQUEST;
    loop {
        tokio::time::sleep(wait).await;
        wait = Duration::from_secs(9 + random.next() % 13);
        let Some((shelf, destinations)) = random.pick(&shelves) else {
            continue;
        };
        let items: Vec<&DemoItem> = fleet
            .items
            .iter()
            .filter(|item| &item.place == *shelf)
            .collect();
        let (Some(item), Some(to)) = (random.pick(&items), random.pick(destinations)) else {
            continue;
        };
        let request = NewTask {
            kind: TaskKind::Fetch,
            item: Some(item.id.clone()),
            from_place: Some((*shelf).clone()),
            to_place: Some(to.clone()),
            deadline: None,
            robot_id: None,
            target_device: None,
        };
        if let Err(error) = tasks.create_as_system(Actor::System("demo"), request).await {
            tracing::info!(code = error.code(), "simulated request not created");
        }
    }
}

/// Where [`store_fleet`] writes.
pub struct FleetStores<'a> {
    /// Robots.
    pub robots: &'a dyn RobotRepository,
    /// Stock.
    pub inventory: &'a dyn InventoryRepository,
    /// Zones.
    pub zones: &'a dyn ZoneRepository,
    /// Schedules.
    pub schedules: &'a dyn ScheduleRepository,
}

/// Stores the demo fleet: robots (`simulated`, role card `demo`, names ending in
/// [`SIMULATED_SUFFIX`]), items, zones and schedules (`HH:MM` -> cron `MM HH * * *`).
///
/// # Errors
/// `StartupError::Demo` when a store fails or a schedule time is not `HH:MM`.
pub async fn store_fleet(
    fleet: &DemoFleet,
    stores: FleetStores<'_>,
    now: DateTime<Utc>,
) -> Result<(), StartupError> {
    let failed = |error: DomainError| StartupError::Demo {
        reason: error.to_string(),
    };
    for robot in &fleet.robots {
        let record = RobotRecord {
            id: robot.id.clone(),
            name: format!("{}{SIMULATED_SUFFIX}", robot.name),
            role_card: "demo".to_owned(),
            simulated: true,
            // In-process robots never present a key.
            key_hash: String::new(),
        };
        stores.robots.upsert(&record).await.map_err(failed)?;
    }
    for item in &fleet.items {
        let level = StockLevel {
            item: item.id.clone(),
            label: item.label.clone(),
            place: item.place.clone(),
            count: item.count,
            low_threshold: item.low_at,
            last_robot_count: None,
            last_robot_count_at: None,
            updated_at: now,
        };
        stores.inventory.upsert(&level).await.map_err(failed)?;
    }
    for zone in &fleet.zones {
        let record = ZoneRecord {
            id: zone.id.clone(),
            name: zone.name.clone(),
            kind: zone.kind,
            floor: zone.floor,
            polygon: zone.polygon.clone(),
            version: 1,
        };
        stores.zones.upsert(&record).await.map_err(failed)?;
    }
    let mut shelves: Vec<PlaceId> = fleet.items.iter().map(|item| item.place.clone()).collect();
    shelves.sort();
    shelves.dedup();
    for schedule in &fleet.schedules {
        let (hours, minutes) = schedule
            .time
            .split_once(':')
            .and_then(|(h, m)| Some((h.parse::<u8>().ok()?, m.parse::<u8>().ok()?)))
            .filter(|(h, m)| *h < 24 && *m < 60)
            .ok_or_else(|| StartupError::Demo {
                reason: format!("schedule {}: time is not HH:MM", schedule.id),
            })?;
        let record = ScheduleRecord {
            id: schedule.id.clone(),
            name: schedule.label.clone(),
            cron: format!("{minutes} {hours} * * *"),
            timezone: "Europe/Zurich".to_owned(),
            places: shelves.clone(),
            enabled: schedule.enabled,
            last_run: None,
            grace_s: 900,
            robot: schedule.robot_id.clone(),
            last_result: RoundResult::default(),
            last_counts: Vec::new(),
        };
        stores.schedules.upsert(&record).await.map_err(failed)?;
    }
    Ok(())
}

/// The stored active plan, or `fallback` (the seed plan) when none is stored or it does not
/// read back.
///
/// # Errors
/// `StartupError::Demo` when the clinic store fails or `fallback` is not valid.
pub async fn active_plan(
    clinics: &dyn ClinicRepository,
    fallback: ClinicPlan,
) -> Result<Arc<ActiveMap>, StartupError> {
    let stored = clinics.active().await.map_err(|error| StartupError::Demo {
        reason: error.to_string(),
    })?;
    let (clinic_id, version, plan) = stored
        .and_then(|record| {
            let plan = serde_json::from_str::<ClinicPlan>(&record.plan_json).ok()?;
            Some((record.id, record.version, plan))
        })
        .unwrap_or_else(|| (ClinicId::seed(), 1, fallback));
    let map = plan.validate().map_err(|error| StartupError::Demo {
        reason: format!("active plan: {error}"),
    })?;
    Ok(Arc::new(ActiveMap::new(ActivePlan {
        clinic_id,
        version,
        plan: Arc::new(plan),
        map: Arc::new(map),
    })))
}
