//! Command line (clap) and configuration (environment, `.env`).

use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::num::NonZeroU32;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::time::Duration;

use audit::JournalConfig;
use clap::{Args, Parser, Subcommand};
use domain::{ClinicId, PlaceId};
use python_bindings::{BrainEngineConfig, DEFAULT_QUEUE_CAPACITY, PatientAidConfig, PythonConfig};
use security::{
    MonitorConfig, NetworkEntry, RateLimitConfig, RequestLimits, RouteLimits, SecurityConfig,
};

use crate::emergency_mirror::EmergencyMirrorConfig;

/// `clinic-server [--mock | --demo [--demo-seed N]] [--print-openapi] [journal verify …]`
#[derive(Debug, Clone, Parser)]
#[command(name = "clinic-server", version, about = "Clinic helper robot server")]
pub struct Cli {
    /// Serve canned, clearly invented data instead of the database.
    #[arg(long, conflicts_with = "demo")]
    pub mock: bool,
    /// Run the live server with simulated robots on the active plan (Task 5b); everything
    /// simulated is labelled "SIMULATED" and `GET /health` reports `mode: "demo"`.
    #[arg(long)]
    pub demo: bool,
    /// Seed of the demo's random choices (default: the console's demo seed).
    #[arg(long, requires = "demo")]
    pub demo_seed: Option<u64>,
    /// Print the OpenAPI document to stdout and exit.
    #[arg(long)]
    pub print_openapi: bool,
    /// Offline subcommands.
    #[command(subcommand)]
    pub command: Option<Command>,
}

/// Subcommands.
#[derive(Debug, Clone, Subcommand)]
pub enum Command {
    /// Journal tools.
    Journal {
        /// Journal subcommand.
        #[command(subcommand)]
        command: JournalCommand,
    },
}

/// Journal subcommands.
#[derive(Debug, Clone, Subcommand)]
pub enum JournalCommand {
    /// Verify chain, seals and anchors; exit non-zero on tampering.
    Verify(VerifyArgs),
}

/// `journal verify` arguments.
#[derive(Debug, Clone, Args)]
pub struct VerifyArgs {
    /// Journal directory.
    #[arg(long, env = "JOURNAL_DIR", default_value = "journal")]
    pub dir: PathBuf,
    /// Public key file (`<signing key>.pub`).
    #[arg(long)]
    pub public_key: PathBuf,
    /// Anchor files to compare (repeatable).
    #[arg(long = "anchor")]
    pub anchors: Vec<PathBuf>,
}

/// Server configuration, read from the environment (see `.env.example`).
#[derive(Debug, Clone)]
pub struct Config {
    /// Listen address (`CLINIC_BIND`; HACKATHON default `0.0.0.0:8080`, every interface; the
    /// normal default is `127.0.0.1:8080`, this computer only; a
    /// deployment sets it, for example `0.0.0.0:8080`, so tablets reach the server over the
    /// clinic network).
    pub bind: SocketAddr,
    /// `DATABASE_URL`.
    pub database_url: String,
    /// Journal settings (`JOURNAL_DIR`, `JOURNAL_KEY`, `JOURNAL_ANCHORS`, …).
    ///
    /// `LOG_DIR` (default `logs`) fills `journal.log_dir`, the only log directory: the tracing
    /// file appender writes there and seals cover the rotated files found there.
    pub journal: JournalConfig,
    /// Seed directory (`SEED_DIR`, default `seed`).
    pub seed_dir: PathBuf,
    /// Clinic map file (default `seed/clinic_map.json`).
    pub map_path: PathBuf,
    /// Role cards file (default `seed/role_cards.json`).
    pub role_cards_path: PathBuf,
    /// Demo fleet file used by `--demo` (default `seed/demo_fleet.json`).
    pub demo_fleet_path: PathBuf,
    /// Dock used by the tour planner (`DOCK_PLACE`).
    pub dock_place: PlaceId,
    /// Login token lifetime (`TOKEN_TTL_S`, default 12 h).
    pub token_ttl: Duration,
    /// Security stack settings (CORS, limits, rate, networks, origins).
    pub security: SecurityConfig,
    /// Emergency service status stream; `None` disables the mirror.
    pub emergency: Option<EmergencyMirrorConfig>,
    /// How to reach the `clinic-brain` process (`BRAIN_URL`, `BRAIN_TOKEN`, and the nested
    /// timeouts of ruling R22; Task A6).
    pub brain: BrainClientConfig,
    /// Pseudonymous accounts (Task A7): the clinic id in the key derivation's salt and the
    /// pepper key file.
    pub accounts: AccountsConfig,
    /// Monitoring and blocking thresholds (Task A8, `monitoring-security.md`): the rate of
    /// `security.rate` (`RATE_PER_SECOND`, `RATE_BURST`), `AUTO_BLOCK_AFTER_S` (5),
    /// `AUTO_BLOCK_FOR_S` (600), `LOGIN_FAILURES_MAX` (10), `LOGIN_FAILURES_WINDOW_S` (60),
    /// `MONITOR_WINDOW_S` (300), `RATE_ALERT_INTERVAL_S` (60) and
    /// `EMERGENCY_SERVICE_ADDRESSES` (never limited or blocked).
    pub monitor: MonitorConfig,
    /// `SERVICE_STATS_MIN_COUNT` (default 0, off): in `GET /stats/service`, places with fewer
    /// requests in the window are folded into `other` (k-anonymity on small wards; 3 is the
    /// documented value).
    pub stats_min_place_count: u32,
}

/// Default HTTPS port (`HTTPS_PORT`; 0 disables the HTTPS listener).
pub const DEFAULT_HTTPS_PORT: u16 = 8443;

/// The optional HTTPS listener: phone browsers only give the microphone to https pages.
///
/// HACKATHON: self-signed certificate. Without `TLS_CERT`/`TLS_KEY` the server generates one
/// at first start under `TLS_DIR` (default `data/tls`) and reuses it. Kept out of [`Config`]
/// (read on its own by `main`) so the configuration's other users are unchanged.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TlsConfig {
    /// `HTTPS_PORT` (default 8443); `None` when set to 0 (no HTTPS listener).
    pub https_port: Option<u16>,
    /// `TLS_CERT` and `TLS_KEY` (PEM files), both or neither.
    pub pem_files: Option<(PathBuf, PathBuf)>,
    /// `TLS_DIR`: where the generated self-signed certificate is kept.
    pub generated_dir: PathBuf,
}

impl TlsConfig {
    /// Reads the environment and `.env`, like [`Config::load`].
    ///
    /// # Errors
    /// `ConfigError::Invalid` for a bad port, `ConfigError::Missing` when only one of
    /// `TLS_CERT` and `TLS_KEY` is set.
    pub fn load() -> Result<TlsConfig, ConfigError> {
        let dotenv = read_dotenv(Path::new(".env"))?;
        TlsConfig::from_lookup(&|var| std::env::var(var).ok().or_else(|| dotenv.get(var).cloned()))
    }

    /// [`TlsConfig::load`] on a given variable lookup (tests pass a map).
    ///
    /// # Errors
    /// As [`TlsConfig::load`].
    pub fn from_lookup(lookup: &dyn Fn(&str) -> Option<String>) -> Result<TlsConfig, ConfigError> {
        tls_config(&Env { lookup })
    }
}

fn tls_config(env: &Env<'_>) -> Result<TlsConfig, ConfigError> {
    let port: u16 = env.parsed("HTTPS_PORT", DEFAULT_HTTPS_PORT)?;
    let pem_files = match (env.get("TLS_CERT"), env.get("TLS_KEY")) {
        (Some(cert), Some(key)) => Some((PathBuf::from(cert), PathBuf::from(key))),
        (None, None) => None,
        (Some(_), None) => return Err(ConfigError::Missing { var: "TLS_KEY" }),
        (None, Some(_)) => return Err(ConfigError::Missing { var: "TLS_CERT" }),
    };
    Ok(TlsConfig {
        https_port: (port != 0).then_some(port),
        pem_files,
        generated_dir: env.path("TLS_DIR", "data/tls"),
    })
}

/// Default account clinic id (`ACCOUNT_CLINIC_ID`); also the id the `--mock` demo accounts
/// were derived with.
pub const DEFAULT_ACCOUNT_CLINIC_ID: &str = "demo-clinic";

/// Pseudonymous accounts (Task A7, `docs/accounts.md`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AccountsConfig {
    /// `ACCOUNT_CLINIC_ID` (default `demo-clinic`): the clinic id in the salt
    /// `clinic:<id>:<lowercase username>`. Fixed for the life of an installation: changing
    /// it changes every account key, so every account would have to enrol again. Not a plan
    /// id (plans can be switched; this cannot).
    pub clinic_id: ClinicId,
    /// `ACCOUNT_PEPPER` (default `keys/account.pepper`): the pepper key file, created on
    /// first start in live mode, refused when readable by other users; never logged. Back it
    /// up with the journal key: without it no account can log in.
    pub pepper_path: PathBuf,
}

/// Paths of the brain routes, which get their own body and time limits (rulings R22, R23).
pub const BRAIN_ROUTE_PREFIX: &str = "/brain/";
/// Largest body of a `/brain/*` request (ruling R23): 1 MiB, above the worst case of 20
/// sources of 8 000 characters (see `brain_process::BRAIN_PROCESS_MAX_BODY_BYTES`); every
/// other route keeps `MAX_BODY_BYTES` (64 KiB).
pub const BRAIN_MAX_BODY_BYTES: usize = 1024 * 1024;
/// Default request timeout of the `/brain/*` routes (`BRAIN_ROUTE_TIMEOUT_S`, ruling R22);
/// every other route keeps `REQUEST_TIMEOUT_S` (10 s).
pub const DEFAULT_BRAIN_ROUTE_TIMEOUT: Duration = Duration::from_secs(30);
/// Default time the main server waits for one brain answer (`BRAIN_TIMEOUT_S`), below the
/// route timeout, so the client gets `brain_timeout`, not a bare 408.
pub const DEFAULT_BRAIN_TIMEOUT: Duration = Duration::from_secs(25);
/// Default time one call may take inside the brain, queue wait included
/// (`BRAIN_CALL_TIMEOUT_S`), below the client timeout by more than the brain's margin.
pub const DEFAULT_BRAIN_CALL_TIMEOUT: Duration = Duration::from_secs(20);

/// The brain's timeouts, nested outer > inner (ruling R22):
///
/// `/brain/*` route (30 s) > main-server client `BRAIN_TIMEOUT_S` (25 s) > brain call
/// `BRAIN_CALL_TIMEOUT_S` (20 s, queue wait plus execution) + the brain's HTTP margin
/// (`brain_process::TIMEOUT_MARGIN`, 2 s) > the cascade's Apertus cut-off
/// (`python_bindings::brain::APERTUS_CUTOFF`, 15 s, after which the rules step answers and the
/// draft is marked degraded).
///
/// So each layer answers with its own explicit error before the layer around it gives up.
/// Both programs read the three variables and refuse to start when the nesting is broken.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BrainTimeouts {
    route: Duration,
    client: Duration,
    call: Duration,
}

impl BrainTimeouts {
    /// Checks the nesting.
    ///
    /// # Errors
    /// `ConfigError::Invalid` naming the variable: a zero timeout; `BRAIN_TIMEOUT_S` not below
    /// `BRAIN_ROUTE_TIMEOUT_S`; `BRAIN_CALL_TIMEOUT_S` plus the margin not below
    /// `BRAIN_TIMEOUT_S`; `BRAIN_CALL_TIMEOUT_S` not above the Apertus cut-off.
    pub fn new(
        route: Duration,
        client: Duration,
        call: Duration,
    ) -> Result<BrainTimeouts, ConfigError> {
        let invalid = |var, reason: String| Err(ConfigError::Invalid { var, reason });
        for (var, value) in [
            ("BRAIN_ROUTE_TIMEOUT_S", route),
            ("BRAIN_TIMEOUT_S", client),
            ("BRAIN_CALL_TIMEOUT_S", call),
        ] {
            if value.is_zero() {
                return invalid(var, "it must be above zero".to_owned());
            }
        }
        let margin = crate::brain_process::TIMEOUT_MARGIN;
        let cutoff = python_bindings::brain::APERTUS_CUTOFF;
        if client >= route {
            return invalid(
                "BRAIN_TIMEOUT_S",
                format!(
                    "{} s is not below the /brain route timeout (BRAIN_ROUTE_TIMEOUT_S, {} s)",
                    client.as_secs(),
                    route.as_secs()
                ),
            );
        }
        if call.saturating_add(margin) >= client {
            return invalid(
                "BRAIN_CALL_TIMEOUT_S",
                format!(
                    "{} s plus the brain's {} s margin is not below BRAIN_TIMEOUT_S ({} s)",
                    call.as_secs(),
                    margin.as_secs(),
                    client.as_secs()
                ),
            );
        }
        if call <= cutoff {
            return invalid(
                "BRAIN_CALL_TIMEOUT_S",
                format!(
                    "{} s is not above the {} s Apertus cut-off, so the rules fallback would have no time to answer",
                    call.as_secs(),
                    cutoff.as_secs()
                ),
            );
        }
        Ok(BrainTimeouts {
            route,
            client,
            call,
        })
    }

    /// The `/brain/*` request timeout.
    #[must_use]
    pub fn route(self) -> Duration {
        self.route
    }

    /// How long the main server waits for the brain.
    #[must_use]
    pub fn client(self) -> Duration {
        self.client
    }

    /// How long one call may take inside the brain, queue wait included.
    #[must_use]
    pub fn call(self) -> Duration {
        self.call
    }

    /// Reads `BRAIN_ROUTE_TIMEOUT_S`, `BRAIN_TIMEOUT_S`, `BRAIN_CALL_TIMEOUT_S` and checks
    /// them.
    fn from_env(env: &Env<'_>) -> Result<BrainTimeouts, ConfigError> {
        let secs = |var: &'static str, default: Duration| -> Result<Duration, ConfigError> {
            Ok(Duration::from_secs(env.parsed(var, default.as_secs())?))
        };
        BrainTimeouts::new(
            secs("BRAIN_ROUTE_TIMEOUT_S", DEFAULT_BRAIN_ROUTE_TIMEOUT)?,
            secs("BRAIN_TIMEOUT_S", DEFAULT_BRAIN_TIMEOUT)?,
            secs("BRAIN_CALL_TIMEOUT_S", DEFAULT_BRAIN_CALL_TIMEOUT)?,
        )
    }
}

impl Default for BrainTimeouts {
    /// 30 s, 25 s, 20 s.
    fn default() -> Self {
        BrainTimeouts {
            route: DEFAULT_BRAIN_ROUTE_TIMEOUT,
            client: DEFAULT_BRAIN_TIMEOUT,
            call: DEFAULT_BRAIN_CALL_TIMEOUT,
        }
    }
}

/// The body and time limits of the `/brain/*` routes for the security stack (1 MiB, the
/// route timeout).
#[must_use]
pub fn brain_route_limits(timeouts: BrainTimeouts) -> RouteLimits {
    RouteLimits {
        prefix: BRAIN_ROUTE_PREFIX.to_owned(),
        max_body_bytes: BRAIN_MAX_BODY_BYTES,
        timeout: timeouts.route(),
    }
}

/// Default address of the `clinic-brain` process: this computer only.
pub const DEFAULT_BRAIN_ADDR: SocketAddr = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 8091);
/// Shortest accepted `BRAIN_TOKEN`, in characters.
pub const MIN_BRAIN_TOKEN_CHARS: usize = 24;

/// The address of the brain process. Invariant: a loopback address (the brain refuses any
/// other caller, and the main server never sends texts off this computer).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BrainAddr(SocketAddr);

impl BrainAddr {
    /// The socket address.
    #[must_use]
    pub fn socket(self) -> SocketAddr {
        self.0
    }
}

impl FromStr for BrainAddr {
    type Err = String;

    /// Reads `http://127.0.0.1:8091`, `http://localhost:8091`, `http://[::1]:8091` or the bare
    /// `127.0.0.1:8091`; a trailing `/` is ignored.
    ///
    /// # Errors
    /// Not `http`, not `host:port`, or not a loopback address.
    fn from_str(text: &str) -> Result<Self, Self::Err> {
        let rest = text.trim().trim_end_matches('/');
        let rest = rest.strip_prefix("http://").unwrap_or(rest);
        if rest.contains("://") {
            return Err(
                "use http:// on this computer (the brain listens on loopback only)".to_owned(),
            );
        }
        let rest = rest.replacen("localhost:", "127.0.0.1:", 1);
        let addr: SocketAddr = rest
            .parse()
            .map_err(|_| "expected http://127.0.0.1:<port>".to_owned())?;
        if addr.ip().is_loopback() {
            Ok(BrainAddr(addr))
        } else {
            Err(
                "the brain must be on this computer (a loopback address such as 127.0.0.1)"
                    .to_owned(),
            )
        }
    }
}

/// The shared secret between the main server and the brain (`BRAIN_TOKEN`). `Debug` never
/// prints it. Invariant: at least [`MIN_BRAIN_TOKEN_CHARS`] visible ASCII characters.
#[derive(Clone, PartialEq, Eq)]
pub struct BrainToken(String);

impl BrainToken {
    /// Validates a token.
    ///
    /// # Errors
    /// Too short, or a character outside visible ASCII.
    pub fn new(token: String) -> Result<BrainToken, String> {
        if token.chars().count() < MIN_BRAIN_TOKEN_CHARS {
            Err(format!(
                "it is shorter than {MIN_BRAIN_TOKEN_CHARS} characters; generate a long random one"
            ))
        } else if !token.chars().all(|c| c.is_ascii_graphic()) {
            Err("use visible ASCII characters only".to_owned())
        } else {
            Ok(BrainToken(token))
        }
    }

    /// The token, for the `Authorization` header.
    #[must_use]
    pub fn expose(&self) -> &str {
        &self.0
    }

    /// Compares with a presented token without stopping at the first different byte.
    #[must_use]
    pub fn matches(&self, presented: &str) -> bool {
        let expected = self.0.as_bytes();
        let presented = presented.as_bytes();
        expected.len() == presented.len()
            && expected
                .iter()
                .zip(presented)
                .fold(0_u8, |acc, (a, b)| acc | (a ^ b))
                == 0
    }
}

impl std::fmt::Debug for BrainToken {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("BrainToken(***)")
    }
}

/// How the main server reaches the brain.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrainClientConfig {
    /// `BRAIN_URL` (default `http://127.0.0.1:8091`).
    pub addr: BrainAddr,
    /// `BRAIN_TOKEN`; `None` when unset: the brain is then reported `down` ("`BRAIN_TOKEN` is
    /// not set") and every brain call is 503 `brain_unavailable`.
    pub token: Option<BrainToken>,
    /// The nested timeouts (ruling R22); the client waits `timeouts.client()`.
    pub timeouts: BrainTimeouts,
}

impl BrainClientConfig {
    /// A client configuration for a brain at `addr` waiting `client_timeout` (tests start a
    /// brain on a free port and use short timeouts; the nesting is not checked here, only by
    /// [`Config::load`]).
    ///
    /// # Errors
    /// `addr` is not a loopback address.
    pub fn local(
        addr: SocketAddr,
        token: Option<BrainToken>,
        client_timeout: Duration,
    ) -> Result<BrainClientConfig, String> {
        Ok(BrainClientConfig {
            addr: addr.to_string().parse()?,
            token,
            timeouts: BrainTimeouts {
                client: client_timeout,
                ..BrainTimeouts::default()
            },
        })
    }
}

impl Default for BrainClientConfig {
    /// The defaults with no token: the brain is `down` until `BRAIN_TOKEN` is set.
    fn default() -> Self {
        BrainClientConfig {
            addr: BrainAddr(DEFAULT_BRAIN_ADDR),
            token: None,
            timeouts: BrainTimeouts::default(),
        }
    }
}

/// Configuration of the `clinic-brain` process (same `.env` and environment as the server).
#[derive(Debug, Clone)]
pub struct BrainProcessConfig {
    /// `BRAIN_BIND` (default `127.0.0.1:8091`); must be a loopback address.
    pub bind: SocketAddr,
    /// `BRAIN_TOKEN`, required.
    pub token: BrainToken,
    /// The nested timeouts (ruling R22), checked like the main server's; the engine's call
    /// timeout is `timeouts.call()`.
    pub timeouts: BrainTimeouts,
    /// The engine: `BRAIN_REPO_ROOT` (default `../..`, the repository root seen from
    /// `implementation/server`), `BRAIN_VENV` (default `<repo root>/.venv`),
    /// `BRAIN_CALL_TIMEOUT_S` (default 20, queue wait plus execution), `BRAIN_QUEUE`
    /// (default 8).
    pub engine: BrainEngineConfig,
}

impl BrainProcessConfig {
    /// Reads `.env` and the environment, like [`Config::load`].
    ///
    /// # Errors
    /// `ConfigError::Missing` (`BRAIN_TOKEN`) or `ConfigError::Invalid` naming the variable.
    pub fn load() -> Result<BrainProcessConfig, ConfigError> {
        let dotenv = read_dotenv(Path::new(".env"))?;
        BrainProcessConfig::from_lookup(&|var| {
            std::env::var(var).ok().or_else(|| dotenv.get(var).cloned())
        })
    }

    /// [`BrainProcessConfig::load`] on a given lookup.
    ///
    /// # Errors
    /// As [`BrainProcessConfig::load`].
    pub fn from_lookup(
        lookup: &dyn Fn(&str) -> Option<String>,
    ) -> Result<BrainProcessConfig, ConfigError> {
        let env = Env { lookup };
        let bind: SocketAddr = env.parsed("BRAIN_BIND", DEFAULT_BRAIN_ADDR)?;
        if !bind.ip().is_loopback() {
            return Err(ConfigError::Invalid {
                var: "BRAIN_BIND",
                reason: format!(
                    "{bind} is not a loopback address; the brain serves this computer only"
                ),
            });
        }
        let token = env
            .get("BRAIN_TOKEN")
            .ok_or(ConfigError::Missing { var: "BRAIN_TOKEN" })?;
        let token = BrainToken::new(token).map_err(|reason| ConfigError::Invalid {
            var: "BRAIN_TOKEN",
            reason,
        })?;
        let repo_root = env.path("BRAIN_REPO_ROOT", "../..");
        let venv = Some(env.path_in("BRAIN_VENV", &repo_root, ".venv"));
        let timeouts = BrainTimeouts::from_env(&env)?;
        Ok(BrainProcessConfig {
            bind,
            token,
            timeouts,
            engine: BrainEngineConfig {
                python: PythonConfig {
                    repo_root,
                    venv,
                    call_timeout: timeouts.call(),
                },
                queue_capacity: env.parsed("BRAIN_QUEUE", DEFAULT_QUEUE_CAPACITY)?,
                patient: patient_aid_config(&env, timeouts.call())?,
            },
        })
    }
}

/// The patient helpers of the brain (hackathon): `APERTUS_URL` (default
/// `http://127.0.0.1:8089`), `APERTUS_TIMEOUT_S` (default 15, below `BRAIN_CALL_TIMEOUT_S`),
/// `WHISPER_MODEL` (default `small`).
fn patient_aid_config(env: &Env<'_>, call: Duration) -> Result<PatientAidConfig, ConfigError> {
    let defaults = PatientAidConfig::default();
    let apertus_url = env.get("APERTUS_URL").unwrap_or(defaults.apertus_url);
    if !apertus_url.starts_with("http://") && !apertus_url.starts_with("https://") {
        return Err(ConfigError::Invalid {
            var: "APERTUS_URL",
            reason: "it does not start with http:// or https://".to_owned(),
        });
    }
    let seconds: u64 = env.parsed("APERTUS_TIMEOUT_S", defaults.apertus_timeout.as_secs())?;
    let apertus_timeout = Duration::from_secs(seconds);
    if seconds == 0 || apertus_timeout >= call {
        return Err(ConfigError::Invalid {
            var: "APERTUS_TIMEOUT_S",
            reason: format!(
                "{seconds} s must be above 0 and below BRAIN_CALL_TIMEOUT_S ({} s)",
                call.as_secs()
            ),
        });
    }
    Ok(PatientAidConfig {
        apertus_url,
        apertus_timeout,
        whisper_model: env.get("WHISPER_MODEL").unwrap_or(defaults.whisper_model),
    })
}

/// The brain settings of the main server.
fn brain_client_config(env: &Env<'_>) -> Result<BrainClientConfig, ConfigError> {
    let addr = match env.get("BRAIN_URL") {
        None => BrainAddr(DEFAULT_BRAIN_ADDR),
        Some(text) => text.parse().map_err(|reason| ConfigError::Invalid {
            var: "BRAIN_URL",
            reason,
        })?,
    };
    let token = env
        .get("BRAIN_TOKEN")
        .map(BrainToken::new)
        .transpose()
        .map_err(|reason| ConfigError::Invalid {
            var: "BRAIN_TOKEN",
            reason,
        })?;
    Ok(BrainClientConfig {
        addr,
        token,
        timeouts: BrainTimeouts::from_env(env)?,
    })
}

impl Config {
    /// Reads `.env` (if present, in the working directory) and the environment; a variable
    /// set in the environment wins over `.env`. Every variable has a default (listed in
    /// `.env.example`), so `clinic-server --mock` runs with none set.
    ///
    /// With `--mock`, the known networks file is not read (mock mode checks no network).
    ///
    /// # Errors
    /// `ConfigError::Missing` or `ConfigError::Invalid` naming the variable.
    pub fn load(cli: &Cli) -> Result<Config, ConfigError> {
        let dotenv = read_dotenv(Path::new(".env"))?;
        Config::from_lookup(cli, &|var| {
            std::env::var(var).ok().or_else(|| dotenv.get(var).cloned())
        })
    }

    /// [`Config::load`] on a given variable lookup (tests pass a map).
    ///
    /// # Errors
    /// As [`Config::load`].
    pub fn from_lookup(
        cli: &Cli,
        lookup: &dyn Fn(&str) -> Option<String>,
    ) -> Result<Config, ConfigError> {
        let env = Env { lookup };
        let seed_dir = env.path("SEED_DIR", "seed");
        let journal = JournalConfig {
            dir: env.path("JOURNAL_DIR", "journal"),
            seal_interval: Duration::from_secs(env.parsed("JOURNAL_SEAL_INTERVAL_S", 60)?),
            segment_max_bytes: env.parsed("JOURNAL_SEGMENT_MAX_BYTES", 64 * 1024 * 1024)?,
            batch_fsync: Duration::from_millis(env.parsed("JOURNAL_BATCH_FSYNC_MS", 1_000)?),
            key_path: env.path("JOURNAL_KEY", "keys/journal.key"),
            anchor_paths: env
                .list("JOURNAL_ANCHORS", "anchor/anchor.log")
                .into_iter()
                .map(PathBuf::from)
                .collect(),
            flight_window: Duration::from_secs(30),
            flight_capacity: 10_000,
            emergency_fallback: env.path("JOURNAL_ESTOP_FALLBACK", "estop-fallback.log"),
            log_dir: env.path("LOG_DIR", "logs"),
        };
        let emergency = match env.get("EMERGENCY_STATUS_URL") {
            Some(status_url) => Some(EmergencyMirrorConfig {
                status_url,
                silence: Duration::from_secs(env.parsed("EMERGENCY_SILENCE_S", 10)?),
            }),
            None => None,
        };
        let brain = brain_client_config(&env)?;
        let security = security_config(&env, &seed_dir, cli.mock, brain.timeouts)?;
        let monitor = monitor_config(&env, security.rate)?;
        Ok(Config {
            // HACKATHON: loopback-only default bind disabled (phones and laptops on the LAN
            // must reach the server), restore after the pitch.
            // bind: env.parsed("CLINIC_BIND", SocketAddr::from(([127, 0, 0, 1], 8080)))?,
            bind: env.parsed("CLINIC_BIND", SocketAddr::from(([0, 0, 0, 0], 8080)))?,
            database_url: env
                .get("DATABASE_URL")
                .unwrap_or_else(|| "sqlite://data/clinic.db?mode=rwc".to_owned()),
            journal,
            map_path: env.path_in("MAP_PATH", &seed_dir, "clinic_map.json"),
            role_cards_path: env.path_in("ROLE_CARDS_PATH", &seed_dir, "role_cards.json"),
            demo_fleet_path: env.path_in("DEMO_FLEET_PATH", &seed_dir, "demo_fleet.json"),
            dock_place: env.parsed_with("DOCK_PLACE", "dock-a")?,
            token_ttl: Duration::from_secs(env.parsed("TOKEN_TTL_S", 12 * 60 * 60)?),
            security,
            emergency,
            brain,
            monitor,
            stats_min_place_count: env.parsed("SERVICE_STATS_MIN_COUNT", 0)?,
            accounts: AccountsConfig {
                clinic_id: env.parsed_with("ACCOUNT_CLINIC_ID", DEFAULT_ACCOUNT_CLINIC_ID)?,
                pepper_path: env.path("ACCOUNT_PEPPER", "keys/account.pepper"),
            },
            seed_dir,
        })
    }
}

/// The admin console's dev (`npm run dev`) and preview (`npm run preview`) origins.
pub const DEFAULT_CONSOLE_ORIGINS: &str =
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173";

/// Paths that need no token header (`/ws` authenticates with its first message).
pub const PUBLIC_PATHS: &[&str] = &[
    "/health",
    "/docs",
    crate::DOCS_SCRIPT_PATH,
    "/openapi.json",
    "/auth/login",
    "/auth/derivation",
    "/auth/enrol",
    "/ws",
];

/// The security settings. CORS and WebSocket origins are explicit lists (never `*`); the
/// known networks come from `KNOWN_NETWORKS_FILE`, except in mock mode, which checks none.
fn security_config(
    env: &Env<'_>,
    seed_dir: &Path,
    mock: bool,
    brain: BrainTimeouts,
) -> Result<SecurityConfig, ConfigError> {
    let cors_origins = env.list("CORS_ORIGINS", DEFAULT_CONSOLE_ORIGINS);
    let ws_origins = if env.get("WS_ORIGINS").is_some() {
        env.list("WS_ORIGINS", "")
    } else {
        cors_origins.clone()
    };
    let networks = if mock {
        Vec::new()
    } else {
        let file = env.path_in("KNOWN_NETWORKS_FILE", seed_dir, "known_networks.json");
        if env.get("KNOWN_NETWORKS_FILE").is_none() && !file.exists() {
            // Step R1: no file and none named: this computer and the private LAN ranges
            // (`NetworkEntry::defaults`); the startup log says so.
            NetworkEntry::defaults()
        } else {
            NetworkEntry::load_file(&file).map_err(|error| ConfigError::Invalid {
                var: "KNOWN_NETWORKS_FILE",
                reason: error.to_string(),
            })?
        }
    };
    let trusted_proxies = env
        .list("TRUSTED_PROXIES", "")
        .iter()
        .map(|cidr| {
            cidr.parse().map_err(|_| ConfigError::Invalid {
                var: "TRUSTED_PROXIES",
                reason: format!("'{cidr}' is not a CIDR block such as 10.0.0.1/32"),
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(SecurityConfig {
        cors_origins,
        limits: RequestLimits {
            max_body_bytes: env.parsed("MAX_BODY_BYTES", 64 * 1024)?,
            timeout: Duration::from_secs(env.parsed("REQUEST_TIMEOUT_S", 10)?),
            max_in_flight: env.parsed("MAX_IN_FLIGHT", 256)?,
        },
        rate: RateLimitConfig {
            // HACKATHON: 20/s, burst 40 per address raised so demo polling never trips the
            // limiter, restore after the pitch.
            // per_second: env.parsed("RATE_PER_SECOND", NonZeroU32::MIN.saturating_add(19))?,
            // burst: env.parsed("RATE_BURST", NonZeroU32::MIN.saturating_add(39))?,
            per_second: env.parsed("RATE_PER_SECOND", NonZeroU32::MIN.saturating_add(99))?,
            burst: env.parsed("RATE_BURST", NonZeroU32::MIN.saturating_add(399))?,
        },
        networks,
        trusted_proxies,
        ws_origins,
        ws_allow_missing_origin: env.parsed("WS_ALLOW_MISSING_ORIGIN", true)?,
        public_paths: PUBLIC_PATHS.iter().map(|path| (*path).to_owned()).collect(),
        route_limits: vec![brain_route_limits(brain)],
    })
}

/// The monitoring thresholds (Task A8); every number has the documented default.
fn monitor_config(env: &Env<'_>, rate: RateLimitConfig) -> Result<MonitorConfig, ConfigError> {
    let defaults = MonitorConfig::default();
    let seconds = |var: &'static str, default: Duration| -> Result<Duration, ConfigError> {
        let value: u64 = env.parsed(var, default.as_secs())?;
        if value == 0 {
            return Err(ConfigError::Invalid {
                var,
                reason: "it must be at least 1 second".to_owned(),
            });
        }
        Ok(Duration::from_secs(value))
    };
    let emergency_service = env
        .list("EMERGENCY_SERVICE_ADDRESSES", "")
        .iter()
        .map(|text| {
            text.parse::<ipnet::IpNet>()
                .or_else(|_| text.parse::<IpAddr>().map(ipnet::IpNet::from))
                .map_err(|_| ConfigError::Invalid {
                    var: "EMERGENCY_SERVICE_ADDRESSES",
                    reason: format!(
                        "'{text}' is not an address or a CIDR block such as 10.0.9.0/24"
                    ),
                })
                .map(security::monitor::canonical_net)
                .and_then(|net| {
                    // Ruling R26: never a protected range broader than a block rule may be.
                    let too_broad = match net {
                        ipnet::IpNet::V4(v4) => v4.prefix_len() < 16,
                        ipnet::IpNet::V6(v6) => v6.prefix_len() < 48,
                    };
                    if too_broad {
                        Err(ConfigError::Invalid {
                            var: "EMERGENCY_SERVICE_ADDRESSES",
                            reason: format!(
                                "'{text}' is broader than /16 (IPv4) or /48 (IPv6); list the service's own addresses"
                            ),
                        })
                    } else {
                        Ok(net)
                    }
                })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let excess_seconds: u32 = env.parsed("AUTO_BLOCK_AFTER_S", defaults.excess_seconds)?;
    let login_failures: u32 = env.parsed("LOGIN_FAILURES_MAX", defaults.login_failures)?;
    if excess_seconds == 0 || login_failures == 0 {
        return Err(ConfigError::Invalid {
            var: if excess_seconds == 0 {
                "AUTO_BLOCK_AFTER_S"
            } else {
                "LOGIN_FAILURES_MAX"
            },
            reason: "it must be at least 1".to_owned(),
        });
    }
    let login_window = seconds("LOGIN_FAILURES_WINDOW_S", defaults.login_window)?;
    let window = seconds("MONITOR_WINDOW_S", defaults.window)?;
    if login_window > window {
        return Err(ConfigError::Invalid {
            var: "LOGIN_FAILURES_WINDOW_S",
            reason: "it must not be longer than MONITOR_WINDOW_S (failures older than the counter window are forgotten)".to_owned(),
        });
    }
    Ok(MonitorConfig {
        rate,
        excess_seconds,
        auto_block_for: seconds("AUTO_BLOCK_FOR_S", defaults.auto_block_for)?,
        login_failures,
        login_window,
        window,
        rate_alert_every: seconds("RATE_ALERT_INTERVAL_S", defaults.rate_alert_every)?,
        emergency_service,
    })
}

/// Reads the `KEY=VALUE` lines of a `.env` file (see [`parse_dotenv`]). A missing file is an
/// empty map.
fn read_dotenv(path: &Path) -> Result<BTreeMap<String, String>, ConfigError> {
    match std::fs::read_to_string(path) {
        Ok(text) => Ok(parse_dotenv(&text)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(BTreeMap::new()),
        Err(error) => Err(ConfigError::Invalid {
            var: ".env",
            reason: format!("the file cannot be read ({error})"),
        }),
    }
}

/// The pairs of a `.env` text: blank lines and `#` comments are skipped, one pair of
/// surrounding quotes (double or single) is removed.
fn parse_dotenv(text: &str) -> BTreeMap<String, String> {
    text.lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .filter_map(|line| line.split_once('='))
        .map(|(key, value)| {
            let value = value.trim();
            let unquoted = ['"', '\'']
                .iter()
                .find_map(|quote| value.strip_prefix(*quote)?.strip_suffix(*quote))
                .unwrap_or(value);
            (key.trim().to_owned(), unquoted.to_owned())
        })
        .collect()
}

/// Typed access to the variables.
struct Env<'a> {
    lookup: &'a dyn Fn(&str) -> Option<String>,
}

impl Env<'_> {
    /// A set, non-empty variable.
    fn get(&self, var: &str) -> Option<String> {
        (self.lookup)(var).filter(|value| !value.trim().is_empty())
    }

    /// A path, or the default.
    fn path(&self, var: &str, default: &str) -> PathBuf {
        PathBuf::from(self.get(var).unwrap_or_else(|| default.to_owned()))
    }

    /// A path, or `file` inside `dir`.
    fn path_in(&self, var: &str, dir: &Path, file: &str) -> PathBuf {
        self.get(var).map_or_else(|| dir.join(file), PathBuf::from)
    }

    /// A comma-separated list, or the default list.
    fn list(&self, var: &str, default: &str) -> Vec<String> {
        self.get(var)
            .unwrap_or_else(|| default.to_owned())
            .split(',')
            .map(str::trim)
            .filter(|item| !item.is_empty())
            .map(str::to_owned)
            .collect()
    }

    /// A parsed value, or `default`.
    fn parsed<T>(&self, var: &'static str, default: T) -> Result<T, ConfigError>
    where
        T: FromStr,
        T::Err: std::fmt::Display,
    {
        match self.get(var) {
            None => Ok(default),
            Some(text) => parse_var(var, &text),
        }
    }

    /// A parsed value, or the parsed `default` text.
    fn parsed_with<T>(&self, var: &'static str, default: &str) -> Result<T, ConfigError>
    where
        T: FromStr,
        T::Err: std::fmt::Display,
    {
        parse_var(var, &self.get(var).unwrap_or_else(|| default.to_owned()))
    }
}

/// Parses one variable's text, naming the variable on failure.
fn parse_var<T>(var: &'static str, text: &str) -> Result<T, ConfigError>
where
    T: FromStr,
    T::Err: std::fmt::Display,
{
    text.trim()
        .parse()
        .map_err(|error: T::Err| ConfigError::Invalid {
            var,
            reason: format!("'{text}' cannot be read ({error})"),
        })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use clap::Parser as _;

    use super::{Cli, Config, ConfigError, parse_dotenv};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn load(args: &[&str], vars: &[(&str, &str)]) -> Result<Config, Box<dyn std::error::Error>> {
        let cli = Cli::try_parse_from(args)?;
        let vars: BTreeMap<String, String> = vars
            .iter()
            .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
            .collect();
        Ok(Config::from_lookup(&cli, &|var| vars.get(var).cloned())?)
    }

    #[test]
    fn mock_runs_with_no_variable_set() -> TestResult {
        let config = load(&["clinic-server", "--mock"], &[])?;
        // HACKATHON: the default bind is every interface during the testing phase.
        assert_eq!(config.bind.to_string(), "0.0.0.0:8080");
        assert_eq!(
            config.security.cors_origins,
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:4173"
            ]
        );
        assert_eq!(config.security.ws_origins, config.security.cors_origins);
        assert!(config.security.networks.is_empty());
        assert!(config.security.public_paths.iter().any(|p| p == "/ws"));
        Ok(())
    }

    #[test]
    fn monitor_thresholds_have_the_documented_defaults_and_read_the_env() -> TestResult {
        let config = load(&["clinic-server", "--mock"], &[])?;
        // HACKATHON: the server's rate default is raised (100/s, burst 400), restore after
        // the pitch: compare the whole config again.
        // assert_eq!(config.monitor, security::MonitorConfig::default());
        assert_eq!(config.monitor.rate.per_second.get(), 100);
        assert_eq!(config.monitor.rate.burst.get(), 400);
        assert_eq!(
            security::MonitorConfig {
                rate: security::MonitorConfig::default().rate,
                ..config.monitor.clone()
            },
            security::MonitorConfig::default()
        );
        assert_eq!(config.stats_min_place_count, 0);
        let config = load(
            &["clinic-server", "--mock"],
            &[
                ("RATE_PER_SECOND", "5"),
                ("AUTO_BLOCK_AFTER_S", "3"),
                ("AUTO_BLOCK_FOR_S", "60"),
                ("LOGIN_FAILURES_MAX", "4"),
                ("EMERGENCY_SERVICE_ADDRESSES", "10.0.9.0/24, 10.0.8.7"),
                ("SERVICE_STATS_MIN_COUNT", "3"),
            ],
        )?;
        assert_eq!(config.monitor.rate.per_second.get(), 5);
        assert_eq!(config.monitor.excess_seconds, 3);
        assert_eq!(config.monitor.auto_block_for.as_secs(), 60);
        assert_eq!(config.monitor.login_failures, 4);
        assert_eq!(config.monitor.emergency_service.len(), 2);
        assert_eq!(config.stats_min_place_count, 3);
        assert!(
            load(
                &["clinic-server", "--mock"],
                &[("EMERGENCY_SERVICE_ADDRESSES", "nope")]
            )
            .is_err()
        );
        assert!(load(&["clinic-server", "--mock"], &[("AUTO_BLOCK_AFTER_S", "0")]).is_err());
        let mapped = load(
            &["clinic-server", "--mock"],
            &[("EMERGENCY_SERVICE_ADDRESSES", "::ffff:10.0.9.0/120")],
        )?;
        assert_eq!(
            mapped.monitor.emergency_service,
            vec!["10.0.9.0/24".parse::<ipnet::IpNet>()?]
        );
        for broad in ["10.0.0.0/8", "2001:db8::/32", "::ffff:10.0.0.0/104"] {
            assert!(
                load(
                    &["clinic-server", "--mock"],
                    &[("EMERGENCY_SERVICE_ADDRESSES", broad)]
                )
                .is_err(),
                "{broad}"
            );
        }
        assert!(
            load(
                &["clinic-server", "--mock"],
                &[
                    ("LOGIN_FAILURES_WINDOW_S", "600"),
                    ("MONITOR_WINDOW_S", "300")
                ]
            )
            .is_err()
        );
        Ok(())
    }

    #[test]
    fn bind_and_origins_are_configurable() -> TestResult {
        let config = load(
            &["clinic-server", "--mock"],
            &[
                ("CLINIC_BIND", "127.0.0.1:9090"),
                ("CORS_ORIGINS", "http://a.example, http://b.example:81"),
            ],
        )?;
        assert_eq!(config.bind.to_string(), "127.0.0.1:9090");
        assert_eq!(
            config.security.cors_origins,
            ["http://a.example", "http://b.example:81"]
        );
        Ok(())
    }

    #[test]
    fn invalid_value_names_the_variable() -> TestResult {
        let cli = Cli::try_parse_from(["clinic-server", "--mock"])?;
        let result = Config::from_lookup(&cli, &|var| {
            (var == "CLINIC_BIND").then(|| "nowhere".to_owned())
        });
        assert!(
            matches!(
                result,
                Err(ConfigError::Invalid {
                    var: "CLINIC_BIND",
                    ..
                })
            ),
            "{result:?}"
        );
        Ok(())
    }

    #[test]
    fn brain_defaults_to_loopback_without_a_token() -> TestResult {
        let config = load(&["clinic-server", "--mock"], &[])?;
        assert_eq!(config.brain.addr.socket().to_string(), "127.0.0.1:8091");
        assert!(config.brain.token.is_none());
        Ok(())
    }

    #[test]
    fn brain_url_must_be_loopback_and_token_long_and_hidden() -> TestResult {
        let cli = Cli::try_parse_from(["clinic-server", "--mock"])?;
        let remote = Config::from_lookup(&cli, &|var| {
            (var == "BRAIN_URL").then(|| "http://10.0.0.5:8091".to_owned())
        });
        assert!(
            matches!(
                remote,
                Err(ConfigError::Invalid {
                    var: "BRAIN_URL",
                    ..
                })
            ),
            "{remote:?}"
        );
        let short = Config::from_lookup(&cli, &|var| {
            (var == "BRAIN_TOKEN").then(|| "short".to_owned())
        });
        assert!(
            matches!(
                short,
                Err(ConfigError::Invalid {
                    var: "BRAIN_TOKEN",
                    ..
                })
            ),
            "{short:?}"
        );
        let secret = "s3cret-s3cret-s3cret-s3cret";
        let config = load(
            &["clinic-server", "--mock"],
            &[
                ("BRAIN_URL", "http://localhost:9000/"),
                ("BRAIN_TOKEN", secret),
            ],
        )?;
        assert_eq!(config.brain.addr.socket().to_string(), "127.0.0.1:9000");
        assert!(!format!("{config:?}").contains(secret));
        let token = config.brain.token.ok_or("token")?;
        assert!(token.matches(secret));
        assert!(!token.matches("s3cret-s3cret-s3cret-s3creX"));
        Ok(())
    }

    #[test]
    fn brain_process_needs_a_token_and_a_loopback_bind() -> TestResult {
        let none = super::BrainProcessConfig::from_lookup(&|_| None);
        assert!(
            matches!(none, Err(ConfigError::Missing { var: "BRAIN_TOKEN" })),
            "{none:?}"
        );
        let token = "t0ken-t0ken-t0ken-t0ken-t0ken";
        let open = super::BrainProcessConfig::from_lookup(&|var| match var {
            "BRAIN_TOKEN" => Some(token.to_owned()),
            "BRAIN_BIND" => Some("0.0.0.0:8091".to_owned()),
            _ => None,
        });
        assert!(
            matches!(
                open,
                Err(ConfigError::Invalid {
                    var: "BRAIN_BIND",
                    ..
                })
            ),
            "{open:?}"
        );
        let config = super::BrainProcessConfig::from_lookup(&|var| {
            (var == "BRAIN_TOKEN").then(|| token.to_owned())
        })?;
        assert_eq!(config.bind.to_string(), "127.0.0.1:8091");
        assert!(!format!("{config:?}").contains(token));
        Ok(())
    }

    #[test]
    fn brain_timeouts_default_to_the_nested_r22_values() -> TestResult {
        let config = load(&["clinic-server", "--mock"], &[])?;
        let t = config.brain.timeouts;
        assert_eq!(
            (
                t.route().as_secs(),
                t.client().as_secs(),
                t.call().as_secs()
            ),
            (30, 25, 20)
        );
        let brain = config
            .security
            .route_limits
            .iter()
            .find(|r| r.prefix == "/brain/")
            .ok_or("no /brain/ route limits")?;
        assert_eq!(brain.max_body_bytes, 1024 * 1024);
        assert_eq!(brain.timeout.as_secs(), 30);
        assert_eq!(config.security.limits.max_body_bytes, 64 * 1024);
        assert_eq!(config.security.limits.timeout.as_secs(), 10);
        Ok(())
    }

    #[test]
    fn broken_brain_timeout_nesting_is_refused_by_both_programs() -> TestResult {
        let token = ("BRAIN_TOKEN", "t0ken-t0ken-t0ken-t0ken-t0ken");
        let cases: &[(&[(&str, &str)], &str)] = &[
            (&[("BRAIN_TIMEOUT_S", "30")], "BRAIN_TIMEOUT_S"),
            (&[("BRAIN_TIMEOUT_S", "40")], "BRAIN_TIMEOUT_S"),
            (&[("BRAIN_ROUTE_TIMEOUT_S", "25")], "BRAIN_TIMEOUT_S"),
            (&[("BRAIN_CALL_TIMEOUT_S", "23")], "BRAIN_CALL_TIMEOUT_S"),
            (&[("BRAIN_CALL_TIMEOUT_S", "15")], "BRAIN_CALL_TIMEOUT_S"),
            (&[("BRAIN_CALL_TIMEOUT_S", "0")], "BRAIN_CALL_TIMEOUT_S"),
            (&[("BRAIN_TIMEOUT_S", "0")], "BRAIN_TIMEOUT_S"),
            (&[("BRAIN_ROUTE_TIMEOUT_S", "0")], "BRAIN_ROUTE_TIMEOUT_S"),
        ];
        let cli = Cli::try_parse_from(["clinic-server", "--mock"])?;
        for (vars, expected) in cases {
            let lookup = |var: &str| {
                vars.iter()
                    .chain(std::iter::once(&token))
                    .find(|(k, _)| *k == var)
                    .map(|(_, v)| (*v).to_owned())
            };
            let server = Config::from_lookup(&cli, &lookup);
            assert!(
                matches!(&server, Err(ConfigError::Invalid { var, .. }) if var == expected),
                "server {vars:?}: {server:?}"
            );
            let brain = super::BrainProcessConfig::from_lookup(&lookup);
            assert!(
                matches!(&brain, Err(ConfigError::Invalid { var, .. }) if var == expected),
                "brain {vars:?}: {brain:?}"
            );
        }
        // A consistent set moved together is accepted.
        let config = load(
            &["clinic-server", "--mock"],
            &[
                ("BRAIN_ROUTE_TIMEOUT_S", "60"),
                ("BRAIN_TIMEOUT_S", "50"),
                ("BRAIN_CALL_TIMEOUT_S", "40"),
            ],
        )?;
        assert_eq!(config.brain.timeouts.call().as_secs(), 40);
        Ok(())
    }

    #[test]
    fn https_listener_defaults_to_8443_and_can_be_disabled() -> TestResult {
        let tls = super::TlsConfig::from_lookup(&|_| None)?;
        assert_eq!(tls.https_port, Some(8443));
        assert_eq!(tls.pem_files, None);
        let vars = [
            ("HTTPS_PORT", "0"),
            ("TLS_CERT", "c.pem"),
            ("TLS_KEY", "k.pem"),
        ];
        let tls = super::TlsConfig::from_lookup(&|var| {
            vars.iter()
                .find(|(k, _)| *k == var)
                .map(|(_, v)| (*v).to_owned())
        })?;
        assert_eq!(tls.https_port, None);
        assert!(tls.pem_files.is_some());
        Ok(())
    }

    #[test]
    fn dotenv_lines_are_parsed() {
        let vars = parse_dotenv("# comment\n\nA=1\nB = \"two words\"\nC='x'\nnot a pair\n");
        assert_eq!(vars.get("A").map(String::as_str), Some("1"));
        assert_eq!(vars.get("B").map(String::as_str), Some("two words"));
        assert_eq!(vars.get("C").map(String::as_str), Some("x"));
        assert_eq!(vars.len(), 3);
    }
}

/// Configuration errors.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ConfigError {
    /// A required variable is missing.
    #[error("Environment variable {var} is not set. Copy .env.example to .env and fill it in.")]
    Missing {
        /// Variable.
        var: &'static str,
    },
    /// A variable has an invalid value.
    #[error("Environment variable {var} is invalid: {reason}.")]
    Invalid {
        /// Variable.
        var: &'static str,
        /// Why.
        reason: String,
    },
}
