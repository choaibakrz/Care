//! Application state and the service wiring.
//!
//! Every service is a trait object (`Arc<dyn Trait>`), so `--mock` swaps the whole set for
//! `MockServices` and tests can swap any single service. This file is the only place that
//! knows which concrete type implements which trait.

use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Duration;

use audit::{AuditIndex, Journal};
use domain::Clock;
use domain::ports::{
    AccountRepository, ClinicRepository, DeviceRepository, InventoryRepository, RobotRepository,
    ScheduleRepository, StockLedger, SystemModeStore, TaskRepository, ZoneRepository,
};
use locations::{
    ActiveMap, Attribution, ClinicMap, ClinicPlan, LivePositions, LocationError, PositionTtl,
    Positioner, PositionerConfig,
};
use optimization::{
    DispatchOracle, DispatchPolicy, Dispatcher, GraphHandle, NativeOracle, RoleCard, RoutePreview,
    RoutingGraph, ShelfLeases, TourPlanner,
};
use realtime::{AppEvent, Hub, Liveness, ZoneDelivery};
use scheduler::{SchedulerService, TaskCreator};
use security::{MonitorHooks, OriginCheck, Pepper, TokenVerifier, TrafficMonitor};
use storage::{
    Database, SqliteAccountRepository, SqliteAuditIndex, SqliteClinicRepository,
    SqliteDeviceRepository, SqliteInventoryRepository, SqliteLedger, SqliteRobotRepository,
    SqliteScheduleRepository, SqliteSystemModeStore, SqliteTaskRepository, SqliteTokenStore,
    SqliteZoneRepository,
};
use tokio::task::JoinHandle;

use crate::config::Config;
use crate::dto::EnrolmentCodeView;
use crate::dto::ServerMode;
use crate::emergency_mirror::EmergencyMirror;
use crate::error::{ApiError, StartupError};
use crate::services::assignment::{AssignmentDeps, AssignmentService};
use crate::services::audit::{JournalAuditQuery, VerifyPaths, spawn_seal_forwarder};
use crate::services::auth::{AuthDeps, RealAuthService, TokenStoreVerifier};
use crate::services::brain::{BRAIN_PROBE_INTERVAL, BrainClient, BrainDeps, HttpBrainService};
use crate::services::clinics::{ClinicDeps, RealClinicService};
use crate::services::demo::{self, DemoClinic, DemoFleet};
use crate::services::devices::{DeviceAdminDeps, RealDeviceAdminService};
use crate::services::fleet_home::FleetHome;
use crate::services::incidents::{IncidentBoard, IncidentBoardDeps};
use crate::services::inventory::RealInventoryService;
use crate::services::location::{LiveLocationService, PositionBroadcaster, to_wire_positions};
use crate::services::map::RealMapService;
use crate::services::mock::{MockServices, MockSettings};
use crate::services::monitor::{MonitorDeps, RealMonitorService};
use crate::services::robots::{EstopPath, RealRobotService, RobotDeps};
use crate::services::routing::{RealRouteService, RouteDeps, RoutingCache};
use crate::services::schedules::RealScheduleService;
use crate::services::service_stats::{RealServiceStats, ServiceStatsDeps};
use crate::services::stats::{HEAT_SAMPLE_INTERVAL, HeatMap};
use crate::services::system_mode::{RealSystemModeService, SystemModeDeps};
use crate::services::tasks::{RealTaskService, TaskDeps};
use crate::services::zones::{RealZoneService, ZoneDeps};
use crate::services::{
    AuditQueryService, AuthService, BrainService, ClinicService, DeviceAdminService,
    IncidentService, InventoryService, JournalStatus, LocationService, MapService, MonitorService,
    RobotService, RouteService, ScheduleService, ServiceStatsService, StatsService,
    SystemModeService, TaskService, ZoneService,
};
use crate::sim::{self, SimPlanner};

/// How long a robot may stay silent before it is marked offline (contract: 5 s).
pub const ROBOT_LIVENESS_TIMEOUT: Duration = Duration::from_secs(5);
/// How often changed positions are published to the apps (Task 11: 200 ms).
pub const POSITION_BROADCAST_INTERVAL: Duration = Duration::from_millis(200);
/// Each connected robot's `robot.updated` is sent at least this often (the admin console
/// greys a robot silent for 5 s).
pub const ROBOT_UPDATED_HEARTBEAT: Duration = Duration::from_secs(1);
/// How often the mock reports tablet battery changes (`device.updated` at most this often
/// per tablet) and sweeps the traffic monitor (Task A8).
pub const DEVICE_REPORT_INTERVAL: Duration = Duration::from_secs(10);

/// Everything a handler can reach. Cheap to clone (all `Arc`s).
#[derive(Clone)]
pub struct AppState {
    /// Login and identity.
    pub auth: Arc<dyn AuthService>,
    /// Task queue.
    pub tasks: Arc<dyn TaskService>,
    /// Stock.
    pub inventory: Arc<dyn InventoryService>,
    /// The 3D clinic map.
    pub map: Arc<dyn MapService>,
    /// Live positions and tablet rooms.
    pub locations: Arc<dyn LocationService>,
    /// Deaf and restricted zones.
    pub zones: Arc<dyn ZoneService>,
    /// Robots, commands, the emergency stop, robot sessions.
    pub robots: Arc<dyn RobotService>,
    /// Night restock schedules.
    pub schedules: Arc<dyn ScheduleService>,
    /// Audit queries and integrity reports.
    pub audit: Arc<dyn AuditQueryService>,
    /// Incidents on the 3D map.
    pub incidents: Arc<dyn IncidentService>,
    /// Stored clinic plans and the active one (Task A4).
    pub clinics: Arc<dyn ClinicService>,
    /// Route previews of tasks (Task A4).
    pub routes: Arc<dyn RouteService>,
    /// Fleet statistics: the heat map (Task A4).
    pub stats: Arc<dyn StatsService>,
    /// The server-side brain: translate, simplify, summarise, report (Task A6).
    pub brain: Arc<dyn BrainService>,
    /// The client to `clinic-brain` for the patient app's translate, simplify and listen
    /// routes (`crate::patient::translate`).
    pub brain_client: Arc<BrainClient>,
    /// Emergency mode (Task A8): the switch, read by the router's filter on every request.
    pub system: Arc<dyn SystemModeService>,
    /// The tablet registry (Task A8).
    pub devices: Arc<dyn DeviceAdminService>,
    /// Monitoring and address blocks (Task A8).
    pub monitor: Arc<dyn MonitorService>,
    /// Service statistics (Task A8).
    pub service_stats: Arc<dyn ServiceStatsService>,
    /// Per-address counters, rate limit and blocks (Task A8), shared with the transport
    /// stack; the `/ws` loop closes a socket whose address gets blocked.
    pub traffic: Arc<TrafficMonitor>,
    /// How the server was started (`GET /health`).
    pub mode: ServerMode,
    /// Whether actions can be recorded right now (degraded mode).
    pub journal: Arc<dyn JournalStatus>,
    /// Token verification used by the security stack's identity layer and by the `/ws`
    /// first-message authentication.
    pub verifier: Arc<dyn TokenVerifier>,
    /// Real-time hub (apps and robots).
    pub hub: Arc<Hub>,
    /// `Origin` check for WebSocket upgrades.
    pub ws_origins: Arc<OriginCheck>,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
}

impl AppState {
    /// The first message a new `/ws` client receives after it authenticated: active tasks,
    /// live positions and the system mode (Task A8; left out if it cannot be read).
    ///
    /// # Errors
    /// Fails when the task list or the live positions cannot be read.
    pub async fn snapshot_event(&self) -> Result<AppEvent, ApiError> {
        let tasks = self.tasks.active().await?;
        let live = self.locations.live().await?;
        let mode = match self.system.mode().await {
            Ok(mode) => Some(mode),
            Err(error) => {
                tracing::warn!(
                    code = error.code(),
                    "snapshot without the system mode: it could not be read"
                );
                None
            }
        };
        Ok(AppEvent::Snapshot {
            tasks,
            positions: to_wire_positions(&live),
            mode,
        })
    }
}

/// A wired application: the state plus the background tasks to stop on shutdown.
pub struct Wiring {
    /// The application state handed to the router.
    pub state: AppState,
    /// Scheduler, position broadcaster, liveness watch, seal forwarder, emergency mirror.
    pub background: Vec<JoinHandle<()>>,
    /// The assignment service of the real wiring (`None` with `--mock`); tests hold its
    /// dispatch lock.
    pub assignment: Option<Arc<AssignmentService>>,
    /// The dispatcher's routing graph of the real wiring (`None` with `--mock`); tests read it
    /// to see a zone change reach dispatch.
    pub routing: Option<Arc<RoutingCache>>,
    /// Startup work [`Wiring::finish`] awaits (real wiring only).
    pending: Option<PendingStart>,
    /// Set by [`Wiring::finish`] on a first start with no account (step R1): the one-time
    /// admin enrolment code `main` prints once in the startup log. `None` otherwise.
    pub first_admin_code: Option<EnrolmentCodeView>,
}

/// What [`Wiring::finish`] awaits before the server serves anything (ruling R16).
struct PendingStart {
    clinics: Arc<RealClinicService>,
    routing: Arc<RoutingCache>,
    seed: ClinicPlan,
    auth: Arc<RealAuthService>,
    system: Arc<RealSystemModeService>,
}

/// The account pepper for the live server (security review of step R1): an existing file is
/// loaded; a missing one is created only on a fresh installation (no account and no
/// enrolment code in `db`, which must be migrated). Otherwise the start is refused: a new
/// pepper would lock every account out.
///
/// # Errors
/// `StartupError::Security` (`pepper_unusable`: restore the file from the backup) or a
/// database error.
pub async fn load_pepper(path: &std::path::Path, db: &Database) -> Result<Pepper, StartupError> {
    let fresh = !storage::has_account_data(db).await?;
    Ok(Pepper::open(path, fresh)?)
}

/// What the real wiring needs from `main`.
pub struct RealDeps<'a> {
    /// Loaded configuration.
    pub config: &'a Config,
    /// Connected and migrated database.
    pub db: Database,
    /// The started journal.
    pub journal: Journal,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
    /// Real-time hub.
    pub hub: Arc<Hub>,
    /// The account pepper (Task A7): `Pepper::load_or_create(&config.accounts.pepper_path)`
    /// in `main`, a fixed invented one in tests. Never logged.
    pub pepper: Arc<Pepper>,
}

/// Seed data the real wiring needs in memory: the seed clinic plan, the role cards and the
/// positioning configuration. [`SeedData::load`] reads them from the files named in
/// [`Config`]; tests build them inline and call [`Wiring::real_with_seeds`].
///
/// There is no separate map: the model is always `plan.validate()` (ruling R14), done by the
/// wiring.
pub struct SeedData {
    /// The seed clinic plan (`seed/clinic_map.json`): stored as clinic `seed` at first start
    /// and in force until the stored active plan is loaded (`RealClinicService::bootstrap`,
    /// awaited by [`Wiring::finish`]).
    pub plan: ClinicPlan,
    /// Role cards by name.
    pub role_cards: BTreeMap<String, RoleCard>,
    /// Positioning seeds (fixed anchors, beacons, fingerprints).
    pub positioning: PositionerConfig,
}

impl SeedData {
    /// Loads the map, role cards and positioning seeds from the configured files.
    ///
    /// # Errors
    /// `StartupError::Map`, `Optimization` or `Positioning` when a file cannot be loaded.
    pub fn load(config: &Config) -> Result<SeedData, StartupError> {
        Ok(SeedData {
            plan: locations::load_plan(&config.map_path)?,
            role_cards: RoleCard::load_all(&config.role_cards_path)?,
            positioning: PositionerConfig::from_seed_dir(&config.seed_dir)?,
        })
    }
}

/// Repositories that replace the `SQLite` ones in [`Wiring::real_with_overrides`].
#[derive(Default)]
pub struct RepositoryOverrides {
    /// Replaces the robot repository (the only port that persists a position).
    pub robots: Option<Arc<dyn RobotRepository>>,
    /// Replaces the clinic plan repository.
    pub clinics: Option<Arc<dyn ClinicRepository>>,
}

/// Every repository, as the port traits the services depend on.
struct Repositories {
    accounts: Arc<dyn AccountRepository>,
    devices: Arc<dyn DeviceRepository>,
    robots: Arc<dyn RobotRepository>,
    tasks: Arc<dyn TaskRepository>,
    inventory: Arc<dyn InventoryRepository>,
    zones: Arc<dyn ZoneRepository>,
    schedules: Arc<dyn ScheduleRepository>,
    ledger: Arc<dyn StockLedger>,
    audit_index: Arc<dyn AuditIndex>,
    clinics: Arc<dyn ClinicRepository>,
    system_mode: Arc<dyn SystemModeStore>,
    tokens: SqliteTokenStore,
}

impl Repositories {
    fn with_overrides(mut self, overrides: RepositoryOverrides) -> Self {
        if let Some(robots) = overrides.robots {
            self.robots = robots;
        }
        if let Some(clinics) = overrides.clinics {
            self.clinics = clinics;
        }
        self
    }

    fn new(db: &Database) -> Self {
        Self {
            accounts: Arc::new(SqliteAccountRepository::new(db.clone())),
            devices: Arc::new(SqliteDeviceRepository::new(db.clone())),
            robots: Arc::new(SqliteRobotRepository::new(db.clone())),
            tasks: Arc::new(SqliteTaskRepository::new(db.clone())),
            inventory: Arc::new(SqliteInventoryRepository::new(db.clone())),
            zones: Arc::new(SqliteZoneRepository::new(db.clone())),
            schedules: Arc::new(SqliteScheduleRepository::new(db.clone())),
            ledger: Arc::new(SqliteLedger::new(db.clone())),
            audit_index: Arc::new(SqliteAuditIndex::new(db.clone())),
            clinics: Arc::new(SqliteClinicRepository::new(db.clone())),
            system_mode: Arc::new(SqliteSystemModeStore::new(db.clone())),
            tokens: SqliteTokenStore::new(db.clone()),
        }
    }
}

impl Wiring {
    /// `--mock`: every service is `MockServices` (canned, clearly invented data). Touches no
    /// database, journal, clinic bootstrap or routing graph: nothing to [`Wiring::finish`].
    ///
    /// The demo robots are simulated in-process (`crate::sim::spawn_in_process`): each is a
    /// hub session registered here, before the first request, and played by the same driver
    /// as the `fake_robot` binary. Must be called inside a Tokio runtime.
    #[must_use]
    pub fn mock(config: &Config, hub: Arc<Hub>, clock: Arc<dyn Clock>) -> Wiring {
        let traffic = Arc::new(TrafficMonitor::new(
            config.monitor.clone(),
            config.security.networks.clone(),
            clock.clone(),
        ));
        let mock = Arc::new(MockServices::with_settings(
            clock.clone(),
            hub.clone(),
            MockSettings {
                traffic: traffic.clone(),
                stats_min_place_count: config.stats_min_place_count,
            },
        ));
        mock.attach_monitor_hooks();
        let heartbeat = mock
            .clone()
            .spawn_heartbeat(hub.clone(), ROBOT_UPDATED_HEARTBEAT);
        let devices = mock.clone().spawn_device_ticker(DEVICE_REPORT_INTERVAL);
        let mut background = vec![heartbeat, devices];
        if let Some((plan, fleet)) = mock.simulated_fleet() {
            let planner = Arc::new(SimPlanner::new(&plan));
            let robots: Arc<dyn RobotService> = mock.clone();
            background.extend(sim::spawn_in_process(
                &hub, &robots, &clock, &planner, fleet,
            ));
        }
        Wiring {
            state: AppState {
                auth: mock.clone(),
                tasks: mock.clone(),
                inventory: mock.clone(),
                map: mock.clone(),
                locations: mock.clone(),
                zones: mock.clone(),
                robots: mock.clone(),
                schedules: mock.clone(),
                audit: mock.clone(),
                incidents: mock.clone(),
                clinics: mock.clone(),
                routes: mock.clone(),
                stats: mock.clone(),
                brain: mock.clone(),
                brain_client: Arc::new(BrainClient::new(&config.brain)),
                system: mock.clone(),
                devices: mock.clone(),
                monitor: mock.clone(),
                service_stats: mock.clone(),
                traffic,
                mode: ServerMode::Mock,
                journal: mock.clone(),
                verifier: mock,
                hub,
                ws_origins: Arc::new(origin_check(config)),
                clock,
            },
            background,
            assignment: None,
            routing: None,
            pending: None,
            first_admin_code: None,
        }
    }

    /// Finishes startup (ruling R16): stores the seed plan or loads the stored active plan
    /// (`RealClinicService::bootstrap`), then builds the dispatcher's routing graph
    /// (`RoutingCache::rebuild`). `main` and the tests await it before serving, so no request
    /// sees a half-started server. Nothing to do for `--mock`.
    ///
    /// # Errors
    /// `StartupError::Bootstrap` when the clinic store or the zone store fails.
    pub async fn finish(mut self) -> Result<Wiring, StartupError> {
        if let Some(pending) = self.pending.take() {
            let failed = |error: ApiError| StartupError::Bootstrap {
                reason: error.message().to_owned(),
            };
            pending
                .clinics
                .bootstrap(&pending.seed)
                .await
                .map_err(failed)?;
            pending.routing.rebuild().await.map_err(failed)?;
            pending.system.bootstrap().await.map_err(failed)?;
            self.first_admin_code = pending.auth.bootstrap_admin_code().await.map_err(failed)?;
        }
        Ok(self)
    }

    /// The real server: repositories on the database, services on the repositories. Call
    /// [`Wiring::finish`] before serving.
    ///
    /// # Errors
    /// Fails when a seed file (map, role cards, positioning) cannot be loaded.
    pub fn real(deps: RealDeps<'_>) -> Result<Wiring, StartupError> {
        let seeds = SeedData::load(deps.config)?;
        Wiring::real_with_overrides(deps, seeds, RepositoryOverrides::default())
    }

    /// The real server with seed data already in memory (tests build small maps inline).
    ///
    /// # Errors
    /// None today beyond those of the services' constructors; kept fallible like
    /// [`Wiring::real`].
    pub fn real_with_seeds(deps: RealDeps<'_>, seeds: SeedData) -> Result<Wiring, StartupError> {
        Wiring::real_with_overrides(deps, seeds, RepositoryOverrides::default())
    }

    /// `--demo` (Task 5b): the real server, plus the demo fleet of `fleet` stored in the
    /// database (robots `simulated` with the role card `demo`, which permits every place of
    /// the active plan; items, zones, schedule) and a `DemoClinic`
    /// (`crate::services::demo::DemoClinic`) driving them on the active plan; `mode` is
    /// `demo`. `seed` makes the run reproducible. Returns a wiring already finished
    /// ([`Wiring::finish`] awaited inside, before the fleet is stored).
    ///
    /// # Errors
    /// As [`Wiring::real`], and store failures while seeding the fleet.
    pub async fn demo(
        deps: RealDeps<'_>,
        seeds: SeedData,
        fleet: DemoFleet,
        seed: u64,
    ) -> Result<Wiring, StartupError> {
        let db = deps.db.clone();
        let hub = deps.hub.clone();
        let clock = deps.clock.clone();
        let seed_plan = seeds.plan.clone();
        let mut wiring = Wiring::real_with_seeds(deps, seeds)?.finish().await?;
        wiring.state.mode = ServerMode::Demo;
        let repos = Repositories::new(&db);
        demo::store_fleet(
            &fleet,
            demo::FleetStores {
                robots: repos.robots.as_ref(),
                inventory: repos.inventory.as_ref(),
                zones: repos.zones.as_ref(),
                schedules: repos.schedules.as_ref(),
            },
            clock.now(),
        )
        .await?;
        if let Some(routing) = &wiring.routing {
            // The demo zones reach the dispatcher's graph.
            routing
                .rebuild()
                .await
                .map_err(|error| StartupError::Demo {
                    reason: error.message().to_owned(),
                })?;
        }
        let active = demo::active_plan(repos.clinics.as_ref(), seed_plan).await?;
        let handle = DemoClinic::start(
            active,
            fleet,
            hub,
            clock,
            seed,
            wiring.state.tasks.clone(),
            wiring.state.robots.clone(),
        );
        wiring.background.extend(handle.into_tasks());
        Ok(wiring)
    }

    /// Live mode: starts `count` simulated "happy" robots (`SIM_ROBOTS`, default 2; 0 starts
    /// none) that wander the active plan (`crate::sim::fleet`). Their records are stored in
    /// `db`; their tasks join [`Wiring::background`]. Nothing happens with `--mock`.
    ///
    /// # Errors
    /// `StartupError::Demo` when a robot record cannot be stored.
    pub async fn start_sim_robots(
        &mut self,
        db: &Database,
        count: usize,
    ) -> Result<(), StartupError> {
        let Some(fleet) = self.state.robots.sim_fleet() else {
            return Ok(());
        };
        if count == 0 {
            return Ok(());
        }
        let repo = SqliteRobotRepository::new(db.clone());
        let handles = sim::fleet::start_happy_robots(
            sim::fleet::HappyRobotsDeps {
                fleet,
                hub: self.state.hub.clone(),
                robots: self.state.robots.clone(),
                clock: self.state.clock.clone(),
                repo: &repo,
            },
            count,
        )
        .await?;
        tracing::info!(count = handles.len(), "simulated robots started");
        self.background.extend(handles);
        Ok(())
    }

    /// [`Wiring::real_with_seeds`] with some repositories replaced (tests inject counting
    /// doubles to check what reaches storage).
    ///
    /// # Errors
    /// Same as [`Wiring::real_with_seeds`].
    #[allow(
        clippy::too_many_lines,
        reason = "the one place that wires every service"
    )]
    pub fn real_with_overrides(
        deps: RealDeps<'_>,
        seeds: SeedData,
        overrides: RepositoryOverrides,
    ) -> Result<Wiring, StartupError> {
        let RealDeps {
            config,
            db,
            journal,
            clock,
            hub,
            pepper,
        } = deps;
        let SeedData {
            plan,
            role_cards,
            positioning,
        } = seeds;
        let repos = Repositories::new(&db).with_overrides(overrides);

        // The model, derived from the seed plan (ruling R14), and live positions (memory only).
        let map = Arc::new(plan.validate().map_err(LocationError::from)?);
        let live = Arc::new(LivePositions::new(
            map.clone(),
            clock.clone(),
            PositionTtl::default(),
        ));
        let active = seed_active_map(&plan, &map);
        let routing = routing_cache(&map, &active, &repos);
        let shared = Shared {
            config,
            journal,
            clock,
            hub,
            map,
            live,
            active,
            routing,
            pepper,
        };

        let incidents = Arc::new(IncidentBoard::new(IncidentBoardDeps {
            journal: shared.journal.clone(),
            hub: shared.hub.clone(),
            attribution: Attribution::new(shared.live.clone()),
            clock: shared.clock.clone(),
        }));
        let inventory = inventory_service(&shared, &repos);
        let assignment = assignment_service(&shared, &repos, role_cards);
        let tasks = task_service(&shared, &repos, &inventory, &assignment);
        let zones = zone_service(&shared, &repos);
        let robots = robot_service(&shared, &repos, &tasks, &inventory, &zones, &incidents);
        let creator: Arc<dyn TaskCreator> = tasks.clone();
        let scheduler = Arc::new(SchedulerService::new(
            repos.schedules.clone(),
            shared.clock.clone(),
            creator,
        ));

        let plans = plan_services(&shared, &repos);
        let brain = brain_service(&shared, &tasks, &incidents, &robots);
        let console = console_services(&shared, &repos, &robots);
        // Blocks and unblocks are journaled and alerted by the monitor service; the traffic
        // monitor only holds a weak link, the state keeps the service alive.
        let hooks: Arc<dyn MonitorHooks> = console.monitor.clone();
        console.traffic.set_hooks(Arc::downgrade(&hooks));
        // The simulated fleet (teleports, home place, moods); its robots start with
        // `Wiring::start_sim_robots`.
        let system: Arc<dyn SystemModeService> = console.system.clone();
        robots.attach_sim(Arc::new(sim::fleet::SimFleet::new(
            shared.active.clone(),
            Arc::new(FleetHome::load(FleetHome::path_near(
                &shared.config.journal.dir,
            ))),
            system,
        )));
        let mut background = background_tasks(&shared, &scheduler, &robots, &incidents);
        background.extend(plans.background);
        background.push(brain.clone().spawn_health_probe(BRAIN_PROBE_INTERVAL));
        let auth = auth_service(&shared, &repos);
        let state = AppState {
            auth: auth.clone(),
            tasks,
            inventory,
            map: Arc::new(RealMapService::new(shared.active.clone())),
            locations: location_service(&shared, positioning),
            zones,
            robots,
            schedules: schedule_service(&shared, &repos, scheduler),
            audit: audit_query(&shared, &repos),
            incidents,
            clinics: plans.clinics.clone(),
            routes: plans.routes,
            stats: plans.heat,
            brain,
            brain_client: Arc::new(BrainClient::new(&shared.config.brain)),
            system: console.system.clone(),
            devices: console.devices,
            monitor: console.monitor,
            service_stats: console.service_stats,
            traffic: console.traffic,
            mode: ServerMode::Live,
            journal: Arc::new(shared.journal.clone()),
            verifier: Arc::new(TokenStoreVerifier::new(
                repos.tokens.clone(),
                repos.accounts.clone(),
            )),
            hub: shared.hub.clone(),
            ws_origins: Arc::new(origin_check(shared.config)),
            clock: shared.clock.clone(),
        };
        Ok(Wiring {
            state,
            background,
            assignment: Some(assignment),
            routing: Some(shared.routing.clone()),
            pending: Some(PendingStart {
                clinics: plans.clinics,
                routing: shared.routing.clone(),
                seed: plan,
                auth,
                system: console.system,
            }),
            first_admin_code: None,
        })
    }
}

/// What most services share in the real wiring.
struct Shared<'a> {
    config: &'a Config,
    journal: Journal,
    clock: Arc<dyn Clock>,
    hub: Arc<Hub>,
    map: Arc<ClinicMap>,
    live: Arc<LivePositions>,
    active: Arc<ActiveMap>,
    routing: Arc<RoutingCache>,
    pepper: Arc<Pepper>,
}

/// The routing graph of the dispatcher: built from the seed model now, rebuilt with the
/// restricted zones by [`Wiring::finish`] and after every zone or plan change.
fn routing_cache(
    map: &ClinicMap,
    active: &Arc<ActiveMap>,
    repos: &Repositories,
) -> Arc<RoutingCache> {
    Arc::new(RoutingCache::new(
        GraphHandle::new(RoutingGraph::from_map(map)),
        active.clone(),
        repos.zones.clone(),
    ))
}

/// The plan in force at start (Task A4): the seed, until `RealClinicService::bootstrap` loads
/// the stored active plan.
///
/// BUILD-OUT: the other services still take the seed model (`Arc<ClinicMap>`); Task 10b
/// moves every map reader to `ActiveMap` so an activated plan reaches them.
fn seed_active_map(plan: &ClinicPlan, map: &Arc<ClinicMap>) -> Arc<ActiveMap> {
    Arc::new(ActiveMap::new(locations::ActivePlan {
        clinic_id: domain::ClinicId::seed(),
        version: 1,
        plan: Arc::new(plan.clone()),
        map: map.clone(),
    }))
}

/// The task queue.
fn task_service(
    shared: &Shared<'_>,
    repos: &Repositories,
    inventory: &Arc<RealInventoryService>,
    assignment: &Arc<AssignmentService>,
) -> Arc<RealTaskService> {
    Arc::new(RealTaskService::new(TaskDeps {
        repo: repos.tasks.clone(),
        ledger: repos.ledger.clone(),
        inventory: inventory.clone(),
        assignment: assignment.clone(),
        map: shared.map.clone(),
        journal: shared.journal.clone(),
        hub: shared.hub.clone(),
        clock: shared.clock.clone(),
    }))
}

/// Stock.
fn inventory_service(shared: &Shared<'_>, repos: &Repositories) -> Arc<RealInventoryService> {
    Arc::new(RealInventoryService::new(
        repos.inventory.clone(),
        repos.ledger.clone(),
        shared.journal.clone(),
        shared.hub.clone(),
    ))
}

/// Deaf and restricted zones.
fn zone_service(shared: &Shared<'_>, repos: &Repositories) -> Arc<RealZoneService> {
    Arc::new(RealZoneService::new(ZoneDeps {
        repo: repos.zones.clone(),
        map: shared.map.clone(),
        delivery: Arc::new(ZoneDelivery::new()),
        routing: shared.routing.clone(),
        hub: shared.hub.clone(),
        robots: repos.robots.clone(),
        journal: shared.journal.clone(),
        clock: shared.clock.clone(),
    }))
}

/// The services of Task A4 and their background work.
struct PlanServices {
    clinics: Arc<RealClinicService>,
    routes: Arc<RealRouteService>,
    heat: Arc<HeatMap>,
    /// The heat sampler.
    background: Vec<JoinHandle<()>>,
}

/// Clinic plans, route previews and the heat map on the active plan (Task A4).
fn plan_services(shared: &Shared<'_>, repos: &Repositories) -> PlanServices {
    let clinics = clinic_service(shared, repos);
    let heat = Arc::new(HeatMap::new(shared.active.clone()));
    let routes = Arc::new(RealRouteService::new(RouteDeps {
        tasks: repos.tasks.clone(),
        zones: repos.zones.clone(),
        active: shared.active.clone(),
        live: shared.live.clone(),
        preview: Arc::new(RoutePreview::new()),
        dock: shared.config.dock_place.clone(),
    }));
    let background = vec![
        heat.clone()
            .spawn_sampler(shared.live.clone(), HEAT_SAMPLE_INTERVAL),
    ];
    PlanServices {
        clinics,
        routes,
        heat,
        background,
    }
}

/// Stored clinic plans (Task A4).
fn clinic_service(shared: &Shared<'_>, repos: &Repositories) -> Arc<RealClinicService> {
    Arc::new(RealClinicService::new(ClinicDeps {
        repo: repos.clinics.clone(),
        active: shared.active.clone(),
        tasks: repos.tasks.clone(),
        inventory: repos.inventory.clone(),
        schedules: repos.schedules.clone(),
        docks: vec![shared.config.dock_place.clone()],
        routing: shared.routing.clone(),
        hub: shared.hub.clone(),
        journal: shared.journal.clone(),
        clock: shared.clock.clone(),
    }))
}

/// The brain client service (Task A6): calls `clinic-brain` on this computer; reports draw on
/// the task, incident and robot services so the caller's view rules apply.
fn brain_service(
    shared: &Shared<'_>,
    tasks: &Arc<RealTaskService>,
    incidents: &Arc<IncidentBoard>,
    robots: &Arc<RealRobotService>,
) -> Arc<HttpBrainService> {
    Arc::new(HttpBrainService::new(BrainDeps {
        client: Arc::new(BrainClient::new(&shared.config.brain)),
        tasks: tasks.clone(),
        incidents: incidents.clone(),
        robots: robots.clone(),
        journal: shared.journal.clone(),
        clock: shared.clock.clone(),
    }))
}

/// Night restock schedules.
fn schedule_service(
    shared: &Shared<'_>,
    repos: &Repositories,
    scheduler: Arc<SchedulerService>,
) -> Arc<RealScheduleService> {
    Arc::new(RealScheduleService::new(
        repos.schedules.clone(),
        scheduler,
        shared.journal.clone(),
        shared.clock.clone(),
    ))
}

/// Audit queries on the index and the journal.
fn audit_query(shared: &Shared<'_>, repos: &Repositories) -> Arc<JournalAuditQuery> {
    let journal = &shared.config.journal;
    Arc::new(
        JournalAuditQuery::new(repos.audit_index.clone(), shared.journal.clone())
            .with_accounts(repos.accounts.clone())
            .with_verify(VerifyPaths {
                dir: journal.dir.clone(),
                public_key: audit::signer::public_key_path(&journal.key_path),
                anchors: journal.anchor_paths.clone(),
            }),
    )
}

/// The services of Task A8 (emergency mode, tablets, monitoring, service statistics).
struct ConsoleServices {
    system: Arc<RealSystemModeService>,
    devices: Arc<RealDeviceAdminService>,
    monitor: Arc<RealMonitorService>,
    service_stats: Arc<RealServiceStats>,
    traffic: Arc<TrafficMonitor>,
}

/// What the updated console needs from the live server (Task A8; bodies E1, T8b, T7b,
/// T11e).
fn console_services(
    shared: &Shared<'_>,
    repos: &Repositories,
    robots: &Arc<RealRobotService>,
) -> ConsoleServices {
    let traffic = Arc::new(TrafficMonitor::new(
        shared.config.monitor.clone(),
        shared.config.security.networks.clone(),
        shared.clock.clone(),
    ));
    let robots: Arc<dyn RobotService> = robots.clone();
    ConsoleServices {
        system: Arc::new(RealSystemModeService::new(SystemModeDeps {
            store: repos.system_mode.clone(),
            robots: robots.clone(),
            tasks: repos.tasks.clone(),
            hub: shared.hub.clone(),
            journal: shared.journal.clone(),
            clock: shared.clock.clone(),
        })),
        devices: Arc::new(RealDeviceAdminService::new(DeviceAdminDeps {
            devices: repos.devices.clone(),
            live: shared.live.clone(),
            hub: shared.hub.clone(),
            journal: shared.journal.clone(),
            clock: shared.clock.clone(),
        })),
        monitor: Arc::new(RealMonitorService::new(MonitorDeps {
            traffic: traffic.clone(),
            robots,
            hub: shared.hub.clone(),
            journal: shared.journal.clone(),
            clock: shared.clock.clone(),
            started_at: shared.clock.now(),
        })),
        service_stats: Arc::new(RealServiceStats::new(ServiceStatsDeps {
            tasks: repos.tasks.clone(),
            inventory: repos.inventory.clone(),
            devices: repos.devices.clone(),
            clock: shared.clock.clone(),
            min_place_count: shared.config.stats_min_place_count,
        })),
        traffic,
    }
}

/// Login and tokens.
fn auth_service(shared: &Shared<'_>, repos: &Repositories) -> Arc<RealAuthService> {
    Arc::new(RealAuthService::new(AuthDeps {
        accounts: repos.accounts.clone(),
        devices: repos.devices.clone(),
        tokens: repos.tokens.clone(),
        journal: shared.journal.clone(),
        clock: shared.clock.clone(),
        token_ttl: shared.config.token_ttl,
        pepper: shared.pepper.clone(),
        clinic_id: shared.config.accounts.clinic_id.clone(),
    }))
}

/// Dispatch: one routing graph (the `RoutingCache` handle) for the dispatcher and the tour
/// planner, so restricted zones and plan changes reach both.
fn assignment_service(
    shared: &Shared<'_>,
    repos: &Repositories,
    role_cards: BTreeMap<String, RoleCard>,
) -> Arc<AssignmentService> {
    let graph = shared.routing.handle();
    let policy = DispatchPolicy::default();
    let oracle: Arc<dyn DispatchOracle> = Arc::new(NativeOracle::new(Dispatcher::with_handle(
        graph.clone(),
        policy.clone(),
    )));
    Arc::new(AssignmentService::new(AssignmentDeps {
        oracle,
        role_cards,
        robots: repos.robots.clone(),
        tasks: repos.tasks.clone(),
        live: shared.live.clone(),
        hub: shared.hub.clone(),
        tours: TourPlanner::with_handle(graph, policy, shared.config.dock_place.clone()),
        leases: Arc::new(ShelfLeases::new(shared.clock.clone())),
        journal: shared.journal.clone(),
        clock: shared.clock.clone(),
        // HACKATHON: simulated robots take real tasks unless SIM_TAKES_REAL_TASKS=0, restore after the pitch.
        simulated_take_real_tasks: std::env::var("SIM_TAKES_REAL_TASKS").map_or(true, |value| value.trim() != "0"),
    }))
}

/// Robots, sessions and the emergency stop path.
fn robot_service(
    shared: &Shared<'_>,
    repos: &Repositories,
    tasks: &Arc<RealTaskService>,
    inventory: &Arc<RealInventoryService>,
    zones: &Arc<RealZoneService>,
    incidents: &Arc<IncidentBoard>,
) -> Arc<RealRobotService> {
    Arc::new(RealRobotService::new(RobotDeps {
        repo: repos.robots.clone(),
        tasks: tasks.clone(),
        inventory: inventory.clone(),
        zones: zones.clone(),
        live: shared.live.clone(),
        liveness: Liveness::new(ROBOT_LIVENESS_TIMEOUT, shared.clock.clone()),
        estop: EstopPath::new(
            shared.hub.clone(),
            shared.journal.clone(),
            shared.clock.clone(),
        ),
        incidents: incidents.clone(),
        hub: shared.hub.clone(),
        journal: shared.journal.clone(),
        clock: shared.clock.clone(),
    }))
}

/// Live positions, tablet rooms and Bluetooth positioning.
fn location_service(
    shared: &Shared<'_>,
    positioning: PositionerConfig,
) -> Arc<LiveLocationService> {
    let positioner = Positioner::new(shared.map.clone(), shared.live.clone(), positioning);
    Arc::new(LiveLocationService::new(
        shared.map.clone(),
        shared.live.clone(),
        positioner,
    ))
}

/// Background work, stopped by `main` on shutdown.
fn background_tasks(
    shared: &Shared<'_>,
    scheduler: &Arc<SchedulerService>,
    robots: &Arc<RealRobotService>,
    incidents: &Arc<IncidentBoard>,
) -> Vec<JoinHandle<()>> {
    let mut background = vec![
        scheduler.clone().spawn(),
        PositionBroadcaster::spawn(
            shared.live.clone(),
            shared.hub.clone(),
            POSITION_BROADCAST_INTERVAL,
        ),
        robots.clone().spawn_liveness_watch(),
        robots.clone().spawn_heartbeat(ROBOT_UPDATED_HEARTBEAT),
        spawn_seal_forwarder(&shared.journal, shared.hub.clone()),
    ];
    if let Some(mirror) = &shared.config.emergency {
        background.push(
            Arc::new(EmergencyMirror::new(
                mirror.clone(),
                incidents.clone(),
                shared.clock.clone(),
            ))
            .spawn(),
        );
    }
    background
}

/// The WebSocket `Origin` check from the security configuration.
fn origin_check(config: &Config) -> OriginCheck {
    OriginCheck::new(config.security.ws_origins.clone())
        .allow_missing_origin(config.security.ws_allow_missing_origin)
}
