//! Shared helpers for the integration tests of the clinic server.
//!
//! - [`MockApp`]: the `--mock` wiring behind the mock transport stack (`security::MockStack`:
//!   CORS, limits, mock bearer identity), exactly as `clinic-server --mock` serves it, called
//!   with `tower::ServiceExt::oneshot` (no network).
//! - [`RealApp`]: the real wiring on an in-memory database, a journal in a temporary
//!   directory, the small invented map of [`map`], and a [`FakeClock`].
//! - [`LiveServer`]: any router served on `127.0.0.1:0` (a free port), with the peer address.
//! - [`WsClient`]: a WebSocket test client that reads JSON messages with a timeout.
//! - [`LogCapture`]: captures `tracing` output for the privacy tests.
//!
//! Every helper returns `Res<T>`; nothing here unwraps or panics.
#![allow(dead_code)]

pub mod map;

use std::collections::BTreeMap;
use std::io;
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4};
use std::num::NonZeroU32;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use audit::{Ed25519FileSigner, Journal, JournalConfig};
use axum::Router;
use axum::body::Body;
use axum::extract::ConnectInfo;
use axum::http::{HeaderMap, HeaderValue, Method, Request, StatusCode, header};
use chrono::{DateTime, TimeZone, Utc};
use clinic_server::config::{AccountsConfig, BrainClientConfig, Config, DEFAULT_ACCOUNT_CLINIC_ID};
use clinic_server::dto::ServerMode;
use clinic_server::services::assignment::AssignmentService;
use clinic_server::services::demo::DemoFleet;
use clinic_server::services::routing::RoutingCache;
use clinic_server::state::{AppState, RealDeps, RepositoryOverrides, SeedData, Wiring};
use clinic_server::{build_app, build_mock_app};
use domain::ports::{AccountRepository, InventoryRepository, RobotRepository};
use domain::{
    AccountId, AccountKey, AccountRecord, Clock, FakeClock, OwnerLabel, PlaceId, RobotRecord, Role,
    StockLevel,
};
use futures_util::{SinkExt as _, StreamExt as _};
use locations::positioning::{FingerprintIndex, PathLossModel};
use locations::{ClinicPlan, PositionerConfig};
use optimization::RoleCard;
use realtime::Hub;
use security::{
    MockStack, NetworkEntry, Pepper, RateLimitConfig, RequestLimits, SecurityConfig, SecurityStack,
    account_id, derive_account_key,
};
use serde_json::{Value, json};
use storage::{
    Database, SqliteAccountRepository, SqliteInventoryRepository, SqliteRobotRepository,
    SqliteTokenStore, TokenSubject,
};
use tokio::net::TcpStream;
use tokio::task::JoinHandle;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::client::IntoClientRequest as _;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};
use tower::ServiceExt as _;

/// Error type of every helper and test.
pub type BoxError = Box<dyn std::error::Error + Send + Sync>;
/// Result of every helper.
pub type Res<T> = Result<T, BoxError>;
/// Result of every test.
pub type TestResult = Res<()>;

/// The admin panel origin allowed by CORS and on WebSocket upgrades.
pub const ADMIN_ORIGIN: &str = "http://localhost:5173";
/// The peer address used by `oneshot` calls (on the known test network).
pub const PEER: SocketAddr = SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 40_000));
/// A peer address on no known network.
pub const FOREIGN_PEER: SocketAddr =
    SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::new(203, 0, 113, 7), 40_000));
/// The password every test account derives its key from (Task A7: the server never sees
/// it; the tests derive the key as a client would).
pub const TEST_PASSWORD: &str = "4821-invented-test-password";
/// The pepper of every [`RealApp`] (invented; [`RealApp::relaunch_with_pepper`] swaps it).
pub const TEST_PEPPER: [u8; 32] = [0x5a; 32];
/// Role card used by test robots (allows every place of the fixture map).
pub const PORTER_CARD: &str = "porteur";
/// Role card that allows floor 1 only, without room 104.
pub const FLOOR_1_CARD: &str = "etage-1";

/// 2026-11-14 08:00:00 UTC, the start of every fake clock.
///
/// # Errors
/// Never in practice; the date is valid.
pub fn start_time() -> Res<DateTime<Utc>> {
    Utc.with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
        .single()
        .ok_or_else(|| "invalid test start time".into())
}

/// A fake clock stopped at [`start_time`].
///
/// # Errors
/// Never in practice.
pub fn fake_clock() -> Res<Arc<FakeClock>> {
    Ok(Arc::new(FakeClock::new(start_time()?)))
}

/// A fresh, empty directory under the system temporary directory.
///
/// # Errors
/// When the directory cannot be created.
pub fn temp_dir(name: &str) -> Res<PathBuf> {
    let dir = std::env::temp_dir()
        .join("clinic-server-tests")
        .join(format!("{name}-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

/// Journal settings inside `dir` (key and anchor in their own sub-directories).
#[must_use]
pub fn journal_config(dir: &Path) -> JournalConfig {
    JournalConfig {
        dir: dir.join("journal"),
        seal_interval: Duration::from_mins(1),
        segment_max_bytes: 64 * 1024 * 1024,
        batch_fsync: Duration::from_secs(1),
        key_path: dir.join("keys").join("journal.key"),
        anchor_paths: vec![dir.join("anchor").join("anchor.log")],
        flight_window: Duration::from_secs(30),
        flight_capacity: 10_000,
        emergency_fallback: dir.join("estop-fallback.log"),
        log_dir: dir.join("logs"),
    }
}

/// Security settings: `127.0.0.0/8` is the known network `test-lan`; generous rate limits.
///
/// # Errors
/// Never in practice.
pub fn security_config() -> Res<SecurityConfig> {
    Ok(SecurityConfig {
        cors_origins: vec![ADMIN_ORIGIN.to_owned()],
        limits: RequestLimits::default(),
        rate: RateLimitConfig {
            per_second: NonZeroU32::new(50).ok_or("zero rate")?,
            burst: NonZeroU32::new(100).ok_or("zero burst")?,
        },
        networks: vec![NetworkEntry {
            cidr: "127.0.0.0/8".parse()?,
            label: "test-lan".to_owned(),
            area: None,
        }],
        trusted_proxies: Vec::new(),
        ws_origins: vec![ADMIN_ORIGIN.to_owned()],
        ws_allow_missing_origin: true,
        public_paths: ["/health", "/docs", "/openapi.json", "/auth/login"]
            .into_iter()
            .map(str::to_owned)
            .collect(),
        // The `/brain/*` limits of the real configuration (1 MiB, 30 s).
        route_limits: vec![clinic_server::config::brain_route_limits(
            clinic_server::config::BrainTimeouts::default(),
        )],
    })
}

/// A full configuration rooted in `dir`.
///
/// # Errors
/// Never in practice.
pub fn test_config(dir: &Path) -> Res<Config> {
    Ok(Config {
        bind: SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)),
        database_url: "sqlite::memory:".to_owned(),
        journal: journal_config(dir),
        seed_dir: dir.join("seed"),
        map_path: dir.join("seed").join("clinic_map.json"),
        role_cards_path: dir.join("seed").join("role_cards.json"),
        demo_fleet_path: dir.join("seed").join("demo_fleet.json"),
        dock_place: map::DOCK.parse()?,
        token_ttl: Duration::from_hours(8),
        security: security_config()?,
        emergency: None,
        brain: BrainClientConfig::default(),
        accounts: AccountsConfig {
            clinic_id: DEFAULT_ACCOUNT_CLINIC_ID.parse()?,
            pepper_path: dir.join("keys").join("account.pepper"),
        },
        monitor: security::MonitorConfig::default(),
        stats_min_place_count: 0,
    })
}

/// The account key a client derives for `username` / `password` on the test server (account
/// clinic id `demo-clinic`). Cached: the derivation takes 600 000 rounds.
///
/// # Errors
/// Never in practice.
pub fn derived_key(username: &str, password: &str) -> Res<AccountKey> {
    static CACHE: std::sync::OnceLock<Mutex<BTreeMap<(String, String), String>>> =
        std::sync::OnceLock::new();
    let cache = CACHE.get_or_init(|| Mutex::new(BTreeMap::new()));
    let entry = (username.to_owned(), password.to_owned());
    if let Some(hex) = cache
        .lock()
        .map_err(|_| "key cache poisoned")?
        .get(&entry)
        .cloned()
    {
        return Ok(hex.parse()?);
    }
    let key = derive_account_key(username, password, &DEFAULT_ACCOUNT_CLINIC_ID.parse()?);
    cache
        .lock()
        .map_err(|_| "key cache poisoned")?
        .insert(entry, key.to_hex());
    Ok(key)
}

/// The JSON body of `POST /auth/login` for `username` / `password`, as a client sends it
/// (the derived key, never the name or the password), with an optional device.
///
/// # Errors
/// Never in practice.
pub fn login_body(username: &str, password: &str, device: Option<&str>) -> Res<Value> {
    let key = derived_key(username, password)?;
    Ok(match device {
        Some(device) => json!({ "account_key": key.to_hex(), "device_id": device }),
        None => json!({ "account_key": key.to_hex() }),
    })
}

/// Creates the journal, key, anchor and log directories of `config`.
///
/// # Errors
/// When a directory cannot be created.
pub fn create_journal_dirs(config: &JournalConfig) -> Res<()> {
    std::fs::create_dir_all(&config.dir)?;
    std::fs::create_dir_all(&config.log_dir)?;
    for path in std::iter::once(&config.key_path).chain(&config.anchor_paths) {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
    }
    Ok(())
}

/// Role cards for the fixture map: [`PORTER_CARD`] (every place) and [`FLOOR_1_CARD`].
///
/// # Errors
/// Never in practice.
pub fn role_cards() -> Res<BTreeMap<String, RoleCard>> {
    let all = [
        map::STOREROOM,
        map::DOCK,
        map::CORRIDOR_1,
        map::ROOM_101,
        map::ROOM_102,
        map::ROOM_103,
        map::ROOM_104,
        map::LIFT_1,
        map::LIFT_2,
        map::CORRIDOR_2,
        map::ROOM_201,
    ];
    let floor_1 = [
        map::STOREROOM,
        map::DOCK,
        map::CORRIDOR_1,
        map::ROOM_101,
        map::ROOM_102,
        map::ROOM_103,
    ];
    let card = |name: &str, places: &[&str]| -> Res<RoleCard> {
        Ok(RoleCard {
            name: name.to_owned(),
            permitted_places: places
                .iter()
                .map(|p| p.parse::<PlaceId>())
                .collect::<Result<_, _>>()?,
            max_speed_m_s: 1.0,
        })
    };
    Ok(BTreeMap::from([
        (PORTER_CARD.to_owned(), card(PORTER_CARD, &all)?),
        (FLOOR_1_CARD.to_owned(), card(FLOOR_1_CARD, &floor_1)?),
    ]))
}

/// Positioning seeds with no fixed anchors, no beacons and no fingerprints.
#[must_use]
pub fn positioning_config() -> PositionerConfig {
    PositionerConfig {
        model: PathLossModel::default(),
        fingerprints: FingerprintIndex::default(),
        fixed_anchors: Vec::new(),
        particles: 500,
        seed: 7,
    }
}

/// The `--mock` wiring behind the mock transport stack, as `clinic-server --mock` serves it
/// (Task 4: mock mode applies CORS and limits only; the live server keeps the full security
/// stack, tested on [`RealApp`]). Mock tokens are `mock-<role>`.
pub struct MockApp {
    /// Router with the security stack applied.
    pub app: Router,
    /// The hub the mock services publish on.
    pub hub: Arc<Hub>,
    /// The fake clock.
    pub clock: Arc<FakeClock>,
    /// Temporary directory of this instance.
    pub dir: PathBuf,
}

impl MockApp {
    /// Builds the mock application.
    ///
    /// # Errors
    /// When the mock transport stack rejects the test configuration.
    pub fn start() -> Res<MockApp> {
        MockApp::start_in_mode(ServerMode::Mock)
    }

    /// The mock services behind a state that says `mode` (Task A7: the login handler's
    /// refusal of a user name and password body outside `--mock` is tested with the mock
    /// services and `ServerMode::Live`).
    ///
    /// # Errors
    /// As [`MockApp::start`].
    pub fn start_in_mode(mode: ServerMode) -> Res<MockApp> {
        let dir = temp_dir("mock")?;
        let config = test_config(&dir)?;
        let clock = fake_clock()?;
        let dyn_clock: Arc<dyn Clock> = clock.clone();
        let hub = Arc::new(Hub::with_clock(dyn_clock.clone()));
        let mut wiring = Wiring::mock(&config, hub.clone(), dyn_clock);
        wiring.state.mode = mode;
        let transport = MockStack::new(&config.security, wiring.state.verifier.clone())?;
        let app = build_mock_app(wiring.state, &transport);
        Ok(MockApp {
            app,
            hub,
            clock,
            dir,
        })
    }
}

/// Which wiring [`RealApp::launch`] builds.
enum Launch {
    /// `Wiring::real_with_overrides`.
    Real {
        seeds: SeedData,
        overrides: RepositoryOverrides,
    },
    /// `Wiring::demo`.
    Demo {
        seeds: SeedData,
        fleet: DemoFleet,
        seed: u64,
    },
}

/// The real wiring: in-memory database, journal in a temporary directory, fixture map.
pub struct RealApp {
    /// Router with the security stack applied.
    pub app: Router,
    /// Application state (services).
    pub state: AppState,
    /// The database.
    pub db: Database,
    /// The journal.
    pub journal: Journal,
    /// Token store on the same database.
    pub tokens: SqliteTokenStore,
    /// The fake clock.
    pub clock: Arc<FakeClock>,
    /// The hub.
    pub hub: Arc<Hub>,
    /// Configuration (paths inside `dir`).
    pub config: Config,
    /// Temporary directory of this instance.
    pub dir: PathBuf,
    /// The assignment service (its dispatch lock); `None` while the live wiring has no
    /// dispatch (step R1).
    pub assignment: Option<Arc<AssignmentService>>,
    /// The one-time admin enrolment code issued at startup when no account existed (step
    /// R1), as `main` prints it.
    pub first_admin_code: Option<String>,
    /// The routing graph of the dispatcher and the tour planner.
    pub routing: Arc<RoutingCache>,
    /// The account pepper of this instance.
    pub pepper: Arc<Pepper>,
    background: Vec<JoinHandle<()>>,
    writer: Option<JoinHandle<()>>,
}

impl RealApp {
    /// Starts the real wiring on the fixture map.
    ///
    /// # Errors
    /// Any startup error.
    pub async fn start() -> Res<RealApp> {
        RealApp::start_with(map::small_plan()?, security_config()?).await
    }

    /// Starts the real wiring with a given map and security configuration.
    ///
    /// # Errors
    /// Any startup error.
    pub async fn start_with(plan: ClinicPlan, security: SecurityConfig) -> Res<RealApp> {
        RealApp::start_with_overrides(plan, security, RepositoryOverrides::default()).await
    }

    /// Starts the real wiring with some repositories replaced by test doubles.
    ///
    /// # Errors
    /// Any startup error.
    pub async fn start_with_overrides(
        plan: ClinicPlan,
        security: SecurityConfig,
        overrides: RepositoryOverrides,
    ) -> Res<RealApp> {
        let seeds = SeedData {
            plan,
            role_cards: role_cards()?,
            positioning: positioning_config(),
        };
        RealApp::launch(security, Launch::Real { seeds, overrides }).await
    }

    /// `--demo` (Task 5b) on the committed seed files: `seed/clinic_map.json` (the console's
    /// demo clinic) and `seed/demo_fleet.json`, with the fixture role cards and a fake clock.
    ///
    /// # Errors
    /// Any startup error, or a seed file that does not load.
    pub async fn start_demo(seed: u64) -> Res<RealApp> {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("seed");
        let plan = locations::load_plan(&root.join("clinic_map.json"))?;
        let fleet = DemoFleet::load(&root.join("demo_fleet.json"))?;
        let seeds = SeedData {
            plan,
            role_cards: role_cards()?,
            positioning: positioning_config(),
        };
        RealApp::launch(security_config()?, Launch::Demo { seeds, fleet, seed }).await
    }

    /// Starts the real wiring on the fixture map with the main server's brain client pointed
    /// at `brain` (Task A6: tests serve a fake `clinic-brain` on a free port).
    ///
    /// # Errors
    /// Any startup error.
    pub async fn start_with_brain(brain: BrainClientConfig) -> Res<RealApp> {
        let seeds = SeedData {
            plan: map::small_plan()?,
            role_cards: role_cards()?,
            positioning: positioning_config(),
        };
        let launch = Launch::Real {
            seeds,
            overrides: RepositoryOverrides::default(),
        };
        RealApp::launch_with(security_config()?, brain, launch).await
    }

    /// The common start: directories, database, journal, hub, then the chosen wiring.
    async fn launch(security: SecurityConfig, launch: Launch) -> Res<RealApp> {
        RealApp::launch_with(security, BrainClientConfig::default(), launch).await
    }

    /// [`RealApp::launch`] with a brain client configuration.
    async fn launch_with(
        security: SecurityConfig,
        brain: BrainClientConfig,
        launch: Launch,
    ) -> Res<RealApp> {
        RealApp::launch_on(
            security,
            brain,
            launch,
            None,
            Pepper::from_bytes(TEST_PEPPER),
        )
        .await
    }

    /// A second instance on this instance's database with another pepper: what an attacker
    /// with a copy of the database but not the pepper file would run (Task A7).
    ///
    /// # Errors
    /// Any startup error.
    pub async fn relaunch_with_pepper(&self, pepper: Pepper) -> Res<RealApp> {
        let seeds = SeedData {
            plan: map::small_plan()?,
            role_cards: role_cards()?,
            positioning: positioning_config(),
        };
        let launch = Launch::Real {
            seeds,
            overrides: RepositoryOverrides::default(),
        };
        RealApp::launch_on(
            security_config()?,
            BrainClientConfig::default(),
            launch,
            Some(self.db.clone()),
            pepper,
        )
        .await
    }

    /// The common start on a new in-memory database (or `db`) with `pepper`.
    async fn launch_on(
        security: SecurityConfig,
        brain: BrainClientConfig,
        launch: Launch,
        db: Option<Database>,
        pepper: Pepper,
    ) -> Res<RealApp> {
        let dir = temp_dir("real")?;
        let mut config = test_config(&dir)?;
        config.security = security;
        config.brain = brain;
        create_journal_dirs(&config.journal)?;
        let clock = fake_clock()?;
        let dyn_clock: Arc<dyn Clock> = clock.clone();
        let db = if let Some(db) = db {
            db
        } else {
            let db = Database::in_memory().await?;
            db.migrate().await?;
            db
        };
        let pepper = Arc::new(pepper);
        let signer = Ed25519FileSigner::load(&config.journal.key_path)?;
        let (journal, writer) =
            Journal::start(config.journal.clone(), dyn_clock.clone(), Box::new(signer))?;
        let hub = Arc::new(Hub::with_clock(dyn_clock.clone()));
        let deps = RealDeps {
            config: &config,
            db: db.clone(),
            journal: journal.clone(),
            clock: dyn_clock,
            hub: hub.clone(),
            pepper: pepper.clone(),
        };
        let wiring = match launch {
            Launch::Real { seeds, overrides } => {
                Wiring::real_with_overrides(deps, seeds, overrides)?
                    .finish()
                    .await?
            }
            Launch::Demo { seeds, fleet, seed } => Wiring::demo(deps, seeds, fleet, seed).await?,
        };
        let security = SecurityStack::new(config.security.clone(), wiring.state.verifier.clone())?;
        let app = build_app(wiring.state.clone(), &security);
        let assignment = wiring.assignment.clone();
        let first_admin_code = wiring
            .first_admin_code
            .as_ref()
            .map(|view| view.code.clone());
        let routing = wiring
            .routing
            .clone()
            .ok_or("the real wiring has no routing cache")?;
        Ok(RealApp {
            assignment,
            first_admin_code,
            routing,
            pepper,
            app,
            state: wiring.state,
            tokens: SqliteTokenStore::new(db.clone()),
            db,
            journal,
            clock,
            hub,
            config,
            dir,
            background: wiring.background,
            writer: Some(writer),
        })
    }

    /// Adds an account as enrolment would (Task A7): the key a client derives for
    /// `username` / [`TEST_PASSWORD`], its id under this instance's pepper, `role` and the
    /// pseudonym `label` (kept when the account exists). The name and the password are never
    /// given to the server.
    ///
    /// # Errors
    /// Invalid label or a store failure.
    pub async fn add_account(&self, username: &str, role: Role, label: &str) -> Res<AccountId> {
        let key = derived_key(username, TEST_PASSWORD)?;
        let id = account_id(&self.pepper, &key);
        let record = AccountRecord {
            id,
            role,
            display_label: OwnerLabel::new(label)?,
            created_at: start_time()?,
            disabled: false,
        };
        let accounts = SqliteAccountRepository::new(self.db.clone());
        // Idempotent, like the `upsert` of the A2 helper: a second token for the same
        // person reuses the account.
        if accounts.find(&id).await?.is_none() {
            accounts.insert(&record).await?;
        }
        Ok(id)
    }

    /// The account id `username` / [`TEST_PASSWORD`] has on this instance.
    ///
    /// # Errors
    /// Never in practice.
    pub fn account_of(&self, username: &str) -> Res<AccountId> {
        Ok(account_id(
            &self.pepper,
            &derived_key(username, TEST_PASSWORD)?,
        ))
    }

    /// Adds an account for `username` (pseudonym "Test <role>") and returns a token bound to
    /// `device`.
    ///
    /// # Errors
    /// Invalid ids or a store failure.
    pub async fn user_token(&self, username: &str, role: Role, device: &str) -> Res<String> {
        let id = self
            .add_account(username, role, &format!("Test {role}"))
            .await?;
        let subject = TokenSubject::User {
            user_id: id.user_id()?,
            role,
            device_id: Some(device.parse()?),
        };
        let raw = self.tokens.issue(subject, Duration::from_hours(1)).await?;
        Ok(raw.expose().to_owned())
    }

    /// Adds an account for `username` and returns a token bound to no device (a browser
    /// login).
    ///
    /// # Errors
    /// Invalid ids or a store failure.
    pub async fn browser_token(&self, username: &str, role: Role) -> Res<String> {
        let id = self
            .add_account(username, role, &format!("Test {role}"))
            .await?;
        let subject = TokenSubject::User {
            user_id: id.user_id()?,
            role,
            device_id: None,
        };
        let raw = self.tokens.issue(subject, Duration::from_hours(1)).await?;
        Ok(raw.expose().to_owned())
    }

    /// An admin token on device `tab-admin`.
    ///
    /// # Errors
    /// See [`RealApp::user_token`].
    pub async fn admin_token(&self) -> Res<String> {
        self.user_token("u-admin", Role::Admin, "tab-admin").await
    }

    /// A nurse token on device `tab-nurse`.
    ///
    /// # Errors
    /// See [`RealApp::user_token`].
    pub async fn nurse_token(&self) -> Res<String> {
        self.user_token("u-nurse", Role::Nurse, "tab-nurse").await
    }

    /// Registers a robot with [`PORTER_CARD`] and returns its token.
    ///
    /// # Errors
    /// Invalid ids or a store failure.
    pub async fn add_robot(&self, id: &str, simulated: bool) -> Res<String> {
        let robot = RobotRecord {
            id: id.parse()?,
            name: format!("Robot {id}"),
            role_card: PORTER_CARD.to_owned(),
            simulated,
            key_hash: String::new(),
        };
        SqliteRobotRepository::new(self.db.clone())
            .upsert(&robot)
            .await?;
        let raw = self
            .tokens
            .issue(
                TokenSubject::Robot { robot_id: robot.id },
                Duration::from_hours(1),
            )
            .await?;
        Ok(raw.expose().to_owned())
    }

    /// Registers robot `id` (not simulated), connects it on `/ws/robot/{id}`, and sends
    /// `hello` and one idle `robot.state` at `(x, y)` on floor 1; then waits 200 ms so the
    /// server has the fix.
    ///
    /// # Errors
    /// Registration or connection errors.
    pub async fn connect_robot(
        &self,
        server: &LiveServer,
        id: &str,
        x: f64,
        y: f64,
    ) -> Res<WsClient> {
        let token = self.add_robot(id, false).await?;
        let url = server.ws_url(&format!("/ws/robot/{id}"));
        let mut socket = WsClient::connect_with_token(&url, &token).await?;
        let now = self.clock.now();
        socket.send_json(&hello(id, false, None, now)).await?;
        socket.send_json(&robot_state(1, x, y, "idle", now)).await?;
        tokio::time::sleep(Duration::from_millis(200)).await;
        Ok(socket)
    }

    /// Opens an application WebSocket on `/ws` as an admin from the admin origin and sends
    /// the `auth` first message, as the admin console does.
    ///
    /// # Errors
    /// Connection errors.
    pub async fn app_socket(&self, server: &LiveServer) -> Res<WsClient> {
        let token = self.admin_token().await?;
        app_socket_with_token(server, &token).await
    }

    /// Sends a `robot.state` whose battery is `marker` and polls `GET /robots` until the
    /// server shows it. Messages on one socket are handled in order, so everything sent
    /// before the barrier has been processed when this returns.
    ///
    /// # Errors
    /// When the marker is not visible within 3 s.
    pub async fn robot_barrier(&self, socket: &mut WsClient, robot: &str, marker: f64) -> Res<()> {
        let mut state = robot_state(1, 5.0, 4.0, "idle", self.clock.now());
        if let Some(fields) = state.as_object_mut() {
            fields.insert("battery".to_owned(), json!(marker));
        }
        socket.send_json(&state).await?;
        let admin = self.admin_token().await?;
        let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
        loop {
            let robots = self.call(get("/robots", Some(&admin))?).await?;
            let battery = robots
                .body
                .as_array()
                .and_then(|list| list.iter().find(|r| r.get("id") == Some(&json!(robot))))
                .and_then(|r| r.get("battery"))
                .and_then(Value::as_f64);
            if battery.is_some_and(|b| (b - marker).abs() < 0.01) {
                return Ok(());
            }
            if tokio::time::Instant::now() >= deadline {
                return Err(format!("{robot}: barrier state not processed within 3 s").into());
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    }

    /// Fails when anything was rejected since `mark`: an "is not allowed" (illegal
    /// transition) line in the logs, or a rejection or illegal-transition record in the
    /// journal. A de-duplicated replay leaves no such trace; a rejected one does.
    ///
    /// # Errors
    /// The rejection found, or journal errors.
    pub async fn assert_nothing_rejected(&self, logs: &LogCapture, mark: LogMark) -> Res<()> {
        let text = logs.since(mark);
        if text.contains(REJECTION_TEXT) {
            return Err(format!("a rejection was logged: {text}").into());
        }
        self.journal.seal_now(audit::SealReason::Interval).await?;
        for record in read_journal(&self.config.journal.dir)? {
            let rejected = match &record.body {
                audit::RecordBody::SecurityRejected { .. } => true,
                audit::RecordBody::SystemEvent { message, .. } => message.contains(REJECTION_TEXT),
                _ => false,
            };
            if rejected {
                return Err(format!("a rejection was journaled: {record:?}").into());
            }
        }
        Ok(())
    }

    /// `GET /tasks/{id}` and its `state`.
    ///
    /// # Errors
    /// When the call fails or the body has no state.
    pub async fn task_state(&self, token: &str, id: &str) -> Res<String> {
        let reply = self
            .call(get(&format!("/tasks/{id}"), Some(token))?)
            .await?;
        reply
            .body
            .get("state")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| format!("no task state in {}", reply.body).into())
    }

    /// Sets the stock of an item.
    ///
    /// # Errors
    /// Invalid id or a store failure.
    pub async fn set_stock(&self, item: &str, count: u32) -> Res<()> {
        let level = StockLevel {
            item: item.parse()?,
            label: item.replace('-', " "),
            place: map::STOREROOM.parse()?,
            count,
            low_threshold: 1,
            last_robot_count: None,
            last_robot_count_at: None,
            updated_at: self.clock.now(),
        };
        SqliteInventoryRepository::new(self.db.clone())
            .upsert(&level)
            .await?;
        Ok(())
    }

    /// Current stock of an item (0 when unknown).
    ///
    /// # Errors
    /// Invalid id or a store failure.
    pub async fn stock(&self, item: &str) -> Res<u32> {
        let level = SqliteInventoryRepository::new(self.db.clone())
            .get(&item.parse()?)
            .await?;
        Ok(level.map_or(0, |l| l.count))
    }

    /// Calls the router as `oneshot` from [`PEER`].
    ///
    /// # Errors
    /// When the body cannot be read.
    pub async fn call(&self, request: Request<Body>) -> Res<Reply> {
        call(&self.app, request).await
    }

    /// Serves this application on a free port.
    ///
    /// # Errors
    /// When binding fails.
    pub async fn serve(&self) -> Res<LiveServer> {
        LiveServer::serve(self.app.clone()).await
    }

    /// Stops background tasks, seals and closes the journal.
    ///
    /// # Errors
    /// Journal errors.
    pub async fn shutdown(mut self) -> Res<()> {
        for task in self.background.drain(..) {
            task.abort();
        }
        self.journal.seal_now(audit::SealReason::Shutdown).await?;
        self.journal.close().await?;
        if let Some(writer) = self.writer.take() {
            writer.await?;
        }
        Ok(())
    }
}

impl Drop for RealApp {
    fn drop(&mut self) {
        for task in &self.background {
            task.abort();
        }
    }
}

/// A response: status, headers and the body as JSON (`Null` when empty, a string when the
/// body is not JSON).
#[derive(Debug, Clone)]
pub struct Reply {
    /// Status.
    pub status: StatusCode,
    /// Headers.
    pub headers: HeaderMap,
    /// Body.
    pub body: Value,
}

impl Reply {
    /// `error.code` of an error body.
    #[must_use]
    pub fn error_code(&self) -> Option<&str> {
        self.body.pointer("/error/code").and_then(Value::as_str)
    }

    /// `error.message` of an error body.
    #[must_use]
    pub fn error_message(&self) -> &str {
        self.body
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or_default()
    }

    /// A header as text.
    #[must_use]
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.get(name).and_then(|v| v.to_str().ok())
    }
}

/// Calls a router as `oneshot`, from [`PEER`] unless the request already has a peer.
///
/// # Errors
/// When the body cannot be read.
pub async fn call(app: &Router, mut request: Request<Body>) -> Res<Reply> {
    if request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .is_none()
    {
        request.extensions_mut().insert(ConnectInfo(PEER));
    }
    let response = app.clone().oneshot(request).await?;
    let status = response.status();
    let headers = response.headers().clone();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX).await?;
    let body = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes)
            .unwrap_or_else(|_| Value::String(String::from_utf8_lossy(&bytes).into_owned()))
    };
    Ok(Reply {
        status,
        headers,
        body,
    })
}

/// Calls a router as `oneshot` from a given peer address.
///
/// # Errors
/// When the body cannot be read.
pub async fn call_from(app: &Router, peer: SocketAddr, mut request: Request<Body>) -> Res<Reply> {
    request.extensions_mut().insert(ConnectInfo(peer));
    call(app, request).await
}

/// Builds a request with an optional bearer token and an optional JSON body.
///
/// # Errors
/// When the request cannot be built.
pub fn request(
    method: Method,
    path: &str,
    token: Option<&str>,
    body: Option<&Value>,
) -> Res<Request<Body>> {
    let mut builder = Request::builder().method(method).uri(path);
    if let Some(token) = token {
        builder = builder.header(header::AUTHORIZATION, format!("Bearer {token}"));
    }
    let request = match body {
        Some(json) => builder
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(json.to_string()))?,
        None => builder.body(Body::empty())?,
    };
    Ok(request)
}

/// `GET path` with a token.
///
/// # Errors
/// When the request cannot be built.
pub fn get(path: &str, token: Option<&str>) -> Res<Request<Body>> {
    request(Method::GET, path, token, None)
}

/// `POST path` with a JSON body and a token.
///
/// # Errors
/// When the request cannot be built.
pub fn post_json(path: &str, token: Option<&str>, body: &Value) -> Res<Request<Body>> {
    request(Method::POST, path, token, Some(body))
}

/// `PUT path` with a JSON body and a token.
///
/// # Errors
/// When the request cannot be built.
pub fn put_json(path: &str, token: Option<&str>, body: &Value) -> Res<Request<Body>> {
    request(Method::PUT, path, token, Some(body))
}

/// A raw `POST` with a text body labelled JSON (for malformed-body tests).
///
/// # Errors
/// When the request cannot be built.
pub fn post_raw(path: &str, token: Option<&str>, body: &str) -> Res<Request<Body>> {
    let mut builder = Request::builder()
        .method(Method::POST)
        .uri(path)
        .header(header::CONTENT_TYPE, "application/json");
    if let Some(token) = token {
        builder = builder.header(header::AUTHORIZATION, format!("Bearer {token}"));
    }
    Ok(builder.body(Body::from(body.to_owned()))?)
}

/// Adds a header to a request.
///
/// # Errors
/// When the value is not a valid header value.
pub fn with_header(
    mut request: Request<Body>,
    name: &'static str,
    value: &str,
) -> Res<Request<Body>> {
    request
        .headers_mut()
        .insert(name, HeaderValue::from_str(value)?);
    Ok(request)
}

/// A router served on `127.0.0.1:0`, with the peer address available to handlers.
pub struct LiveServer {
    /// The bound address.
    pub addr: SocketAddr,
    handle: JoinHandle<()>,
}

impl LiveServer {
    /// Serves `app` on a free port.
    ///
    /// # Errors
    /// When binding fails.
    pub async fn serve(app: Router) -> Res<LiveServer> {
        let listener = tokio::net::TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).await?;
        let addr = listener.local_addr()?;
        let handle = tokio::spawn(async move {
            let _ignored = axum::serve(
                listener,
                app.into_make_service_with_connect_info::<SocketAddr>(),
            )
            .await;
        });
        Ok(LiveServer { addr, handle })
    }

    /// `http://127.0.0.1:<port><path>`.
    #[must_use]
    pub fn http_url(&self, path: &str) -> String {
        format!("http://{}{path}", self.addr)
    }

    /// `ws://127.0.0.1:<port><path>`.
    #[must_use]
    pub fn ws_url(&self, path: &str) -> String {
        format!("ws://{}{path}", self.addr)
    }
}

impl Drop for LiveServer {
    fn drop(&mut self) {
        self.handle.abort();
    }
}

/// A WebSocket test client exchanging JSON text messages.
pub struct WsClient {
    stream: WebSocketStream<MaybeTlsStream<TcpStream>>,
}

impl WsClient {
    /// Connects with extra headers (for example `authorization`, `origin`).
    ///
    /// # Errors
    /// When the handshake fails (the error names the HTTP status when the server refused).
    pub async fn connect(url: &str, headers: &[(&'static str, &str)]) -> Res<WsClient> {
        let mut request = url.into_client_request()?;
        for (name, value) in headers {
            request
                .headers_mut()
                .insert(*name, HeaderValue::from_str(value)?);
        }
        let (stream, _response) = tokio_tungstenite::connect_async(request).await?;
        Ok(WsClient { stream })
    }

    /// Connects with a bearer token and no `Origin` (a native client).
    ///
    /// # Errors
    /// See [`WsClient::connect`].
    pub async fn connect_with_token(url: &str, token: &str) -> Res<WsClient> {
        let bearer = format!("Bearer {token}");
        WsClient::connect(url, &[("authorization", &bearer)]).await
    }

    /// Sends one JSON message.
    ///
    /// # Errors
    /// When the connection is closed.
    pub async fn send_json(&mut self, value: &Value) -> Res<()> {
        self.stream.send(Message::text(value.to_string())).await?;
        Ok(())
    }

    /// The next JSON text message within `within`; pings and pongs are skipped.
    ///
    /// # Errors
    /// On timeout, on close (the error names the close code and reason), or on non-JSON text.
    pub async fn next_json(&mut self, within: Duration) -> Res<Value> {
        let deadline = tokio::time::Instant::now() + within;
        loop {
            let next = tokio::time::timeout_at(deadline, self.stream.next())
                .await
                .map_err(|_| format!("no WebSocket message within {within:?}"))?;
            match next {
                None => return Err("the WebSocket stream ended".into()),
                Some(Err(error)) => return Err(error.into()),
                Some(Ok(Message::Text(text))) => return Ok(serde_json::from_str(text.as_str())?),
                Some(Ok(Message::Close(frame))) => {
                    let detail = frame.map_or_else(
                        || "no close frame".to_owned(),
                        |f| format!("{}: {}", u16::from(f.code), f.reason.as_str()),
                    );
                    return Err(format!("the WebSocket was closed ({detail})").into());
                }
                Some(Ok(_)) => {}
            }
        }
    }

    /// The next message whose `type` is `kind`, skipping others, within `within` overall.
    ///
    /// # Errors
    /// See [`WsClient::next_json`].
    pub async fn next_of_type(&mut self, kind: &str, within: Duration) -> Res<Value> {
        let deadline = tokio::time::Instant::now() + within;
        loop {
            let left = deadline.saturating_duration_since(tokio::time::Instant::now());
            let message = self.next_json(left).await?;
            if message.get("type").and_then(Value::as_str) == Some(kind) {
                return Ok(message);
            }
        }
    }

    /// Waits for the server to close the connection; returns the close code and reason.
    ///
    /// # Errors
    /// On timeout, or when the stream ends without a close frame.
    pub async fn close_frame(&mut self, within: Duration) -> Res<(u16, String)> {
        let deadline = tokio::time::Instant::now() + within;
        loop {
            let next = tokio::time::timeout_at(deadline, self.stream.next())
                .await
                .map_err(|_| format!("no close frame within {within:?}"))?;
            match next {
                None => return Err("the stream ended without a close frame".into()),
                Some(Err(error)) => return Err(error.into()),
                Some(Ok(Message::Close(Some(frame)))) => {
                    return Ok((u16::from(frame.code), frame.reason.as_str().to_owned()));
                }
                Some(Ok(Message::Close(None))) => {
                    return Err("closed without a close frame".into());
                }
                Some(Ok(_)) => {}
            }
        }
    }

    /// The first frame the server sends must be a close frame (pings and pongs aside);
    /// returns its code and reason.
    ///
    /// # Errors
    /// On timeout, when a text or binary frame comes first, or when the stream ends without a
    /// close frame.
    pub async fn first_frame_is_close(&mut self, within: Duration) -> Res<(u16, String)> {
        let deadline = tokio::time::Instant::now() + within;
        loop {
            let next = tokio::time::timeout_at(deadline, self.stream.next())
                .await
                .map_err(|_| format!("no close frame within {within:?}"))?;
            match next {
                None => return Err("the stream ended without a close frame".into()),
                Some(Err(error)) => return Err(error.into()),
                Some(Ok(Message::Close(Some(frame)))) => {
                    return Ok((u16::from(frame.code), frame.reason.as_str().to_owned()));
                }
                Some(Ok(Message::Close(None))) => {
                    return Err("closed without a close frame".into());
                }
                Some(Ok(Message::Ping(_) | Message::Pong(_))) => {}
                Some(Ok(other)) => {
                    return Err(format!("a data frame came before the close: {other:?}").into());
                }
            }
        }
    }

    /// Sends one binary frame.
    ///
    /// # Errors
    /// When the connection is closed.
    pub async fn send_binary(&mut self, bytes: Vec<u8>) -> Res<()> {
        self.stream.send(Message::binary(bytes)).await?;
        Ok(())
    }

    /// Closes the connection.
    ///
    /// # Errors
    /// When the close cannot be sent.
    pub async fn close(mut self) -> Res<()> {
        self.stream.close(None).await?;
        Ok(())
    }
}

/// Opens `/ws` from the admin origin and sends `{"type":"auth","token"}` first, as the
/// admin console does.
///
/// # Errors
/// Connection errors.
pub async fn app_socket_with_token(server: &LiveServer, token: &str) -> Res<WsClient> {
    let mut socket = WsClient::connect(&server.ws_url("/ws"), &[("origin", ADMIN_ORIGIN)]).await?;
    socket
        .send_json(&json!({ "type": "auth", "token": token }))
        .await?;
    Ok(socket)
}

/// A robot-to-server message: `{ "type", "id", "ts", ...payload }`.
#[must_use]
pub fn robot_message(kind: &str, payload: &Value, ts: DateTime<Utc>) -> Value {
    let mut message = json!({
        "type": kind,
        "id": uuid::Uuid::new_v4().to_string(),
        "ts": ts.to_rfc3339(),
    });
    if let (Some(target), Some(fields)) = (message.as_object_mut(), payload.as_object()) {
        for (key, value) in fields {
            target.insert(key.clone(), value.clone());
        }
    }
    message
}

/// The `hello` a robot sends first.
#[must_use]
pub fn hello(robot: &str, simulated: bool, running_task: Option<&str>, ts: DateTime<Utc>) -> Value {
    robot_message(
        "hello",
        &json!({
            "robot_id": robot,
            "role_card": PORTER_CARD,
            "capabilities": ["carry"],
            "simulated": simulated,
            "running_task": running_task,
        }),
        ts,
    )
}

/// A `robot.state` message on floor `floor` at `(x, y)`.
#[must_use]
pub fn robot_state(floor: i32, x: f64, y: f64, status: &str, ts: DateTime<Utc>) -> Value {
    robot_message(
        "robot.state",
        &json!({
            "pos": { "x": x, "y": y, "heading": 0.0, "floor": floor },
            "battery": 80.0,
            "state": status,
            "holding": null,
            "mic_open": true,
        }),
        ts,
    )
}

/// A `task.event` message.
#[must_use]
pub fn task_event(task: &str, state: &str, reason: Option<&str>, ts: DateTime<Utc>) -> Value {
    robot_message(
        "task.event",
        &json!({ "task_id": task, "state": state, "reason": reason }),
        ts,
    )
}

/// Captured `tracing` output (every level, every thread), for asserting what is never
/// logged. One global subscriber per test binary: tests take a [`LogMark`] first and read
/// only what was logged after it (other tests running in parallel may add lines too).
#[derive(Clone, Default)]
pub struct LogCapture {
    buffer: Arc<Mutex<Vec<u8>>>,
}

/// A line the request trace layer of the security stack logs for every request; the privacy
/// tests check it was captured, so "the room is not in the logs" cannot pass by capturing
/// nothing.
pub const REQUEST_TRACE_LINE: &str = "finished processing request";

/// What an illegal task transition says (`DomainError::IllegalTransition`).
pub const REJECTION_TEXT: &str = "is not allowed";

/// A position in the captured output.
#[derive(Debug, Clone, Copy)]
pub struct LogMark(usize);

static GLOBAL_LOGS: std::sync::OnceLock<LogCapture> = std::sync::OnceLock::new();

impl LogCapture {
    /// The process-wide capture, installed as the global default subscriber on first use.
    ///
    /// # Errors
    /// When another global subscriber was installed by someone else.
    pub fn global() -> Res<LogCapture> {
        let mut install_error = None;
        let capture = GLOBAL_LOGS.get_or_init(|| {
            let capture = LogCapture::default();
            let subscriber = tracing_subscriber::fmt()
                .with_max_level(tracing::Level::TRACE)
                .with_ansi(false)
                .with_writer(capture.clone())
                .finish();
            if let Err(error) = tracing::subscriber::set_global_default(subscriber) {
                install_error = Some(error.to_string());
            }
            capture
        });
        match install_error {
            Some(error) => Err(error.into()),
            None => Ok(capture.clone()),
        }
    }

    /// The current end of the captured output.
    #[must_use]
    pub fn mark(&self) -> LogMark {
        LogMark(self.buffer.lock().map(|b| b.len()).unwrap_or_default())
    }

    /// Everything logged since `mark`.
    #[must_use]
    pub fn since(&self, mark: LogMark) -> String {
        self.buffer
            .lock()
            .map(|b| String::from_utf8_lossy(b.get(mark.0..).unwrap_or_default()).into_owned())
            .unwrap_or_default()
    }
}

/// The writer handed to `tracing_subscriber` by [`LogCapture`].
pub struct LogWriter {
    buffer: Arc<Mutex<Vec<u8>>>,
}

impl io::Write for LogWriter {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if let Ok(mut buffer) = self.buffer.lock() {
            buffer.extend_from_slice(data);
        }
        Ok(data.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for LogCapture {
    type Writer = LogWriter;

    fn make_writer(&'a self) -> LogWriter {
        LogWriter {
            buffer: self.buffer.clone(),
        }
    }
}

/// Reads every journal record found in the files of `dir` (lines that parse), sorted by `seq`.
///
/// # Errors
/// When the directory cannot be read.
pub fn read_journal(dir: &Path) -> Res<Vec<audit::JournalRecord>> {
    let mut records = Vec::new();
    for entry in std::fs::read_dir(dir)? {
        let path = entry?.path();
        if !path.is_file() {
            continue;
        }
        let text = std::fs::read_to_string(&path)?;
        records.extend(
            text.lines()
                .filter_map(|line| serde_json::from_str::<audit::JournalRecord>(line).ok()),
        );
    }
    records.sort_by_key(|r| r.seq);
    Ok(records)
}

/// Turns a service result into a test result (`ApiError` does not implement `Error`).
///
/// # Errors
/// The `ApiError`, formatted with `Debug`.
pub fn api<T>(result: Result<T, clinic_server::error::ApiError>) -> Res<T> {
    result.map_err(|error| format!("{error:?}").into())
}
