//! Clinic server binary: startup only.
//!
//! Order matters and is part of the design:
//! 1. configuration,
//! 2. the sealed journal (nothing may happen that cannot be recorded),
//! 3. tracing, with the journal and flight-recorder layers,
//! 4. database and services (or the mock services with `--mock`, or the live services plus
//!    simulated robots with `--demo`),
//! 5. the security stack and the router,
//! 6. serving with the peer address (`ConnectInfo<SocketAddr>`),
//! 7. graceful shutdown ending with a final journal seal.
//!
//! `--mock` takes its own short path ([`run_mock`]): configuration, tracing to stderr, the
//! mock services and the mock transport stack. It opens no journal, no database and no log
//! file, and runs no clinic bootstrap.

mod tls;

use std::io::{IsTerminal as _, Write as _};
use std::net::SocketAddr;
use std::process::ExitCode;
use std::sync::Arc;
use std::time::Duration;

use audit::{Category, Ed25519FileSigner, Journal, JournalLayer, RecordBody, SealReason, Severity};
use axum::Router;
use clap::Parser as _;
use clinic_server::config::{Cli, Command, Config, JournalCommand, TlsConfig, VerifyArgs};
use clinic_server::error::StartupError;
use clinic_server::openapi::ApiDoc;
use clinic_server::services::demo::{DEFAULT_DEMO_SEED, DemoFleet};
use clinic_server::services::mock::{MOCK_ACCOUNT_CLINIC_ID, MOCK_PASSWORD, MOCK_TOKEN_PREFIX};
use clinic_server::state::{RealDeps, SeedData, Wiring, load_pepper};
use clinic_server::{build_app, build_mock_app};
use domain::{Actor, Clock, SystemClock};
use realtime::Hub;
use security::{MockStack, SecurityStack};
use storage::Database;
use tokio::net::TcpListener;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::layer::SubscriberExt as _;
use tracing_subscriber::util::SubscriberInitExt as _;
use tracing_subscriber::{EnvFilter, Layer as _};
use utoipa::OpenApi as _;

#[tokio::main]
async fn main() -> ExitCode {
    let cli = Cli::parse();
    match run(cli).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            // Tracing may not be running yet, so the error goes to stderr directly.
            let _ignored = writeln!(std::io::stderr().lock(), "clinic-server: {error}");
            ExitCode::FAILURE
        }
    }
}

async fn run(cli: Cli) -> Result<(), StartupError> {
    // Offline commands first: they touch no journal, database or network.
    if cli.print_openapi {
        return print_openapi();
    }
    if let Some(Command::Journal {
        command: JournalCommand::Verify(args),
    }) = &cli.command
    {
        return verify_journal(args);
    }

    // 1. Configuration.
    let config = Config::load(&cli)?;
    if cli.mock {
        return run_mock(&config).await;
    }
    let clock: Arc<dyn Clock> = Arc::new(SystemClock);

    // 2. Journal first: every later step may write to it.
    let signer =
        Ed25519FileSigner::open_for_journal(&config.journal.key_path, &config.journal.dir)?;
    let (journal, writer) =
        Journal::start(config.journal.clone(), clock.clone(), Box::new(signer))?;

    // 3. Tracing, copying WARN and above into the journal and DEBUG into the flight recorder.
    let _log_guard = init_tracing(&config, &journal)?;
    journal
        .append(
            Severity::Notice,
            Category::System,
            Actor::System("server"),
            RecordBody::SystemEvent {
                target: "startup".to_owned(),
                message: format!("server starting (mock: {}, demo: {})", cli.mock, cli.demo),
            },
            None,
        )
        .await?;

    // 4. Services: the mock set, or the database-backed set.
    let hub = Arc::new(Hub::new());
    // The account pepper (Task A7): created on first start, refused when readable by others,
    // never logged. Without it no account can log in.
    create_database_dir(&config.database_url)?;
    let db = Database::connect(&config.database_url).await?;
    db.migrate().await?;
    let pepper = Arc::new(load_pepper(&config.accounts.pepper_path, &db).await?);
    let wiring = if cli.demo {
        let fleet = DemoFleet::load(&config.demo_fleet_path)?;
        Wiring::demo(
            RealDeps {
                config: &config,
                db,
                journal: journal.clone(),
                clock: clock.clone(),
                hub,
                pepper,
            },
            SeedData::load(&config)?,
            fleet,
            cli.demo_seed.unwrap_or(DEFAULT_DEMO_SEED),
        )
        .await?
    } else {
        live_wiring(RealDeps {
            config: &config,
            db,
            journal: journal.clone(),
            clock: clock.clone(),
            hub,
            pepper,
        })
        .await?
    };

    // 5. Security stack and router.
    let security = SecurityStack::new(config.security.clone(), wiring.state.verifier.clone())?;
    announce_live(&config, &security, wiring.first_admin_code.as_ref());
    let app = build_app(wiring.state, &security);

    // 6. Serve, keeping the peer address for the known-network check.
    let listener = TcpListener::bind(config.bind)
        .await
        .map_err(|source| StartupError::Bind {
            addr: config.bind,
            source,
        })?;
    tracing::info!(addr = %config.bind, demo = cli.demo, "clinic server listening");
    let https = start_https(&config, &app).await?;
    let served = serve(listener, app, https).await;

    // 7. Shutdown, also when serving failed: stop background work, then seal what was written
    //    before reporting the serve error, so the last records are never left unsealed.
    match &served {
        Ok(()) => tracing::info!("shutting down"),
        Err(error) => tracing::error!(%error, "server stopped with an error; sealing the journal"),
    }
    for task in wiring.background {
        task.abort();
    }
    let sealed = journal.seal_now(SealReason::Shutdown).await;
    served.map_err(StartupError::Serve)?;
    sealed?;
    journal.close().await?;
    writer.await.map_err(|error| StartupError::Task {
        what: "journal writer",
        detail: error.to_string(),
    })?;
    Ok(())
}

/// The running HTTPS listener: its shutdown handle and task.
struct Https {
    handle: axum_server::Handle<SocketAddr>,
    task: tokio::task::JoinHandle<()>,
}

/// How long open connections get to finish when the server stops.
const GRACE: Duration = Duration::from_secs(5);

/// Starts the optional HTTPS listener (`HTTPS_PORT`, default 8443, 0 disables) on the
/// `CLINIC_BIND` address with the same router, and logs the URLs phones should open.
/// HACKATHON: self-signed certificate (see `tls.rs`). A certificate problem is logged and
/// leaves the server on HTTP only.
async fn start_https(config: &Config, app: &Router) -> Result<Option<Https>, StartupError> {
    let tls_config = TlsConfig::load()?;
    let Some(port) = tls_config.https_port else {
        tracing::info!("https listener disabled (HTTPS_PORT=0)");
        return Ok(None);
    };
    let rustls = match tls::rustls_config(&tls_config).await {
        Ok(rustls) => rustls,
        Err(error) => {
            tracing::error!(%error, "https disabled: no usable certificate");
            return Ok(None);
        }
    };
    let addr = SocketAddr::new(config.bind.ip(), port);
    let handle = axum_server::Handle::new();
    let task = tls::spawn(addr, rustls, app.clone(), handle.clone());
    tracing::info!(
        "This computer: http://localhost:{http}/patient/ or https://localhost:{port}/patient/",
        http = config.bind.port()
    );
    if !config.bind.ip().is_loopback() {
        for ip in tls::lan_ipv4() {
            tracing::info!(
                "Phones: https://{ip}:{port}/patient/ - accept the certificate warning once"
            );
        }
    }
    Ok(Some(Https { handle, task }))
}

/// Serves HTTP (and HTTPS when started) until Ctrl+C; both stop together, so the caller can
/// then seal the journal.
async fn serve(listener: TcpListener, app: Router, https: Option<Https>) -> std::io::Result<()> {
    let handle = https.as_ref().map(|https| https.handle.clone());
    let signal = async move {
        shutdown_signal().await;
        if let Some(handle) = handle {
            handle.graceful_shutdown(Some(GRACE));
        }
    };
    let served = axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .with_graceful_shutdown(signal)
    .await;
    if let Some(https) = https {
        // Also when HTTP stopped with an error.
        https.handle.graceful_shutdown(Some(GRACE));
        if let Err(error) = https.task.await {
            tracing::error!(%error, "https listener task failed");
        }
    }
    served
}

/// SQLite's `mode=rwc` creates the database file but not a missing directory: create the
/// directory of a `sqlite://<path>` URL first (`data/` by default).
fn create_database_dir(url: &str) -> Result<(), StartupError> {
    let path = url
        .strip_prefix("sqlite://")
        .or_else(|| url.strip_prefix("sqlite:"))
        .map(|rest| rest.split('?').next().unwrap_or(rest))
        .filter(|path| !path.is_empty() && !path.starts_with(':'));
    let Some(parent) = path
        .and_then(|path| std::path::Path::new(path).parent())
        .filter(|parent| !parent.as_os_str().is_empty())
    else {
        return Ok(());
    };
    std::fs::create_dir_all(parent).map_err(|source| StartupError::Io {
        action: "create the database directory",
        source,
    })
}

/// The first start of an installation (no account yet): the one-time admin enrolment code,
/// printed once. It is not journaled in clear (the journal has its id only).
fn announce_first_admin_code(code: &clinic_server::dto::EnrolmentCodeView) {
    // Straight to stderr, never through tracing: tracing also writes the log file, the
    // flight recorder and (WARN and above) the journal, and the code is a secret until used.
    // The journal has its id only.
    tracing::info!("first start: a one-time admin enrolment code was printed on stderr");
    let _ignored = writeln!(
        std::io::stderr().lock(),
        "{nl}FIRST START: no account exists. One-time ADMIN enrolment code: {code}{nl}  valid until {expires}, single use. In the admin console choose {q}I have an enrolment code{q},{nl}  type it with a user name, a password and a pseudonym. It is not written to any file; a{nl}  restart without an account retires it and prints a new one.{nl}",
        nl = '\n',
        q = '"',
        code = code.code,
        expires = code.expires_at.to_rfc3339(),
    );
}

/// The startup log of the live server: networks, CORS, and what is not built yet.
fn announce_live(
    config: &Config,
    security: &SecurityStack,
    first_admin_code: Option<&clinic_server::dto::EnrolmentCodeView>,
) {
    if let Some(code) = first_admin_code {
        announce_first_admin_code(code);
    }
    if config.security.networks == security::NetworkEntry::defaults() {
        tracing::info!(
            "known networks: no seed/known_networks.json, using the defaults (this computer \
             and the private LAN ranges 10/8, 172.16/12, 192.168/16, fc00::/7, fe80::/10)"
        );
    } else {
        tracing::info!(
            networks = config.security.networks.len(),
            "known networks loaded"
        );
    }
    tracing::info!(origins = ?security.cors_origins(), "CORS origins");
    tracing::info!("LIVE SERVER: every service is wired to the database and the journal");
}

/// `clinic-server --mock`: the mock services behind the mock transport stack (CORS and
/// request limits; no known-network check, no rate limit), with invented data kept in memory.
/// Nothing is journaled or stored; tracing goes to stderr only.
async fn run_mock(config: &Config) -> Result<(), StartupError> {
    init_mock_tracing()?;
    let clock: Arc<dyn Clock> = Arc::new(SystemClock);
    let hub = Arc::new(Hub::with_clock(clock.clone()));
    let wiring = Wiring::mock(config, hub, clock);
    let transport = MockStack::new(&config.security, wiring.state.verifier.clone())?;
    let app = build_mock_app(wiring.state, &transport);
    let listener = TcpListener::bind(config.bind)
        .await
        .map_err(|source| StartupError::Bind {
            addr: config.bind,
            source,
        })?;
    announce_mock(config, &transport);
    let https = start_https(config, &app).await?;
    let served = serve(listener, app, https).await;
    for task in wiring.background {
        task.abort();
    }
    tracing::info!("mock server stopped; its in-memory data is gone");
    served.map_err(StartupError::Serve)
}

/// The startup log of `--mock`: what runs, what does not, and how to log in.
fn announce_mock(config: &Config, transport: &MockStack) {
    tracing::warn!(
        "MOCK MODE: invented data (the admin console's demo clinic), kept in memory only. \
         No database, no journal: nothing is recorded."
    );
    tracing::warn!(
        origins = ?transport.cors_origins(),
        "mock mode applies CORS, request limits and the traffic monitor (per-address rate \
         limit, automatic and manual blocks; loopback, connected robots and an admin's robot \
         commands are never refused): no known-network check, no X-Client-Id check (the live \
         server keeps the full security stack)"
    );
    tracing::info!(
        "demo credentials: user 'admin' (role admin) or 'nurse' (role nurse), password \
         '{MOCK_PASSWORD}'; also 'doctor', 'therapist', 'reception'. Tokens are \
         {MOCK_TOKEN_PREFIX}<role>. The console derives the account key from them \
         (account clinic id '{MOCK_ACCOUNT_CLINIC_ID}', docs/accounts.md); a \
         {{username, password}} body is still accepted here only, until frontend task F9."
    );
    if !config.bind.ip().is_loopback() {
        tracing::warn!(
            addr = %config.bind,
            "mock mode is reachable from other computers (CLINIC_BIND is not a loopback \
             address) with no network check: use a trusted network only"
        );
    }
    tracing::info!(
        "robots r1..r4 are SIMULATED in-process: they loop between the places of their floor \
         through doors and corridors (simplistic motion: no furniture, zones, lifts or other \
         robots; real routing is Task 13b, demo motion Task 5b), take new tasks and obey \
         pause/resume/estop/dock"
    );
    tracing::info!(
        "robot-r2 is the fake_robot slot: cargo run --bin fake_robot -- --server ws://{addr} \
         --id robot-r2 --simulated (token mock-robot-<id> by default, mock server only)",
        addr = config.bind
    );
    tracing::info!(
        addr = %config.bind,
        "clinic server (mock) listening: REST on port {port}, docs at /docs, WebSocket at /ws",
        port = config.bind.port()
    );
}

/// Tracing for `--mock`: stderr only (no log file, no journal layers).
fn init_mock_tracing() -> Result<(), StartupError> {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer()
                .with_writer(std::io::stderr)
                .with_ansi(std::io::stderr().is_terminal())
                .with_filter(filter),
        )
        .try_init()
        .map_err(|error| StartupError::Tracing {
            detail: error.to_string(),
        })
}

/// Writes the OpenAPI document to stdout. Uses derives only, so it works on a bare checkout.
fn print_openapi() -> Result<(), StartupError> {
    let json = ApiDoc::openapi()
        .to_pretty_json()
        .map_err(StartupError::OpenApi)?;
    writeln!(std::io::stdout().lock(), "{json}").map_err(|source| StartupError::Io {
        action: "write the OpenAPI document to stdout",
        source,
    })
}

/// `clinic-server journal verify`: checks chain, seals and anchors, prints the report as JSON.
fn verify_journal(args: &VerifyArgs) -> Result<(), StartupError> {
    let key = audit::load_verifying_key(&args.public_key)?;
    let report = audit::verify(&args.dir, &key, &args.anchors)?;
    let json = serde_json::to_string_pretty(&report).map_err(StartupError::OpenApi)?;
    writeln!(std::io::stdout().lock(), "{json}").map_err(|source| StartupError::Io {
        action: "write the verification report to stdout",
        source,
    })?;
    if report.is_clean() {
        Ok(())
    } else {
        Err(StartupError::JournalNotClean {
            first_bad_record: report.first_bad_record,
        })
    }
}

/// Installs the tracing stack. The returned guard flushes the log file when dropped.
fn init_tracing(config: &Config, journal: &Journal) -> Result<WorkerGuard, StartupError> {
    // One log directory: the one the journal seals cover.
    let file = tracing_appender::rolling::daily(&config.journal.log_dir, "clinic-server.log");
    let (file_writer, guard) = tracing_appender::non_blocking(file);
    let env_filter =
        || EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer()
                .with_writer(file_writer)
                .with_ansi(false)
                .with_filter(env_filter()),
        )
        .with(
            tracing_subscriber::fmt::layer()
                .with_writer(std::io::stderr)
                .with_filter(env_filter()),
        )
        .with(journal.flight_recorder().with_filter(LevelFilter::DEBUG))
        .with(JournalLayer::new(journal.clone()).with_filter(LevelFilter::WARN))
        .try_init()
        .map_err(|error| StartupError::Tracing {
            detail: error.to_string(),
        })?;
    Ok(guard)
}

/// Resolves on Ctrl+C (and SIGTERM on Unix, Ctrl+Break on Windows).
async fn shutdown_signal() {
    let ctrl_c = async {
        if let Err(error) = tokio::signal::ctrl_c().await {
            tracing::error!(%error, "cannot listen for Ctrl+C; shutting down now");
        }
    };
    #[cfg(unix)]
    let terminate = async {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut signal) => {
                signal.recv().await;
            }
            Err(error) => {
                tracing::error!(%error, "cannot listen for SIGTERM");
                std::future::pending::<()>().await;
            }
        }
    };
    // Windows: Ctrl+Break too (what a script or a service manager can send to a console
    // process started in its own process group).
    #[cfg(windows)]
    let terminate = async {
        match tokio::signal::windows::ctrl_break() {
            Ok(mut signal) => {
                signal.recv().await;
            }
            Err(error) => {
                tracing::error!(%error, "cannot listen for Ctrl+Break");
                std::future::pending::<()>().await;
            }
        }
    };
    #[cfg(not(any(unix, windows)))]
    let terminate = std::future::pending::<()>();
    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }
}

/// The live wiring: the seed fleet and stock (upsert: a rerun changes nothing), the real
/// services, then the simulated "happy" robots.
async fn live_wiring(deps: RealDeps<'_>) -> Result<Wiring, StartupError> {
    let counts = storage::load_seed(&deps.db, &deps.config.seed_dir).await?;
    tracing::info!(robots = counts.robots, "seed fleet loaded");
    let db = deps.db.clone();
    let mut wiring = Wiring::real(deps)?.finish().await?;
    wiring.start_sim_robots(&db, sim_robot_count()).await?;
    Ok(wiring)
}

/// How many simulated "happy" robots the live server starts (`SIM_ROBOTS`, default 2; 0
/// disables them).
fn sim_robot_count() -> usize {
    std::env::var("SIM_ROBOTS")
        .ok()
        .and_then(|value| value.trim().parse::<usize>().ok())
        .unwrap_or(clinic_server::sim::fleet::DEFAULT_SIM_ROBOTS)
}
