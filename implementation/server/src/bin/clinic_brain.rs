//! `clinic-brain`: the brain process of the clinic server (Task A6).
//!
//! Serves translate, simplify, summarise and report to the main server only, on loopback,
//! with the shared `BRAIN_TOKEN` (see `clinic_server::brain_process` and
//! `docs/brain.md`). Built without the `python` feature (the default), it starts anyway and
//! answers every call with 503 `brain_unavailable`, so the main server reports `brain: down`
//! and keeps working.
//!
//! ```text
//! BRAIN_TOKEN=<24+ characters> cargo run --bin clinic-brain                    # no Python
//! BRAIN_TOKEN=<24+ characters> cargo run --bin clinic-brain --features python  # real models
//! ```
//!
//! Logs go to stderr, at `info` (no request or response body is ever logged).

use std::io::Write as _;
use std::process::ExitCode;

use clinic_server::brain_process::serve_brain;
use clinic_server::config::BrainProcessConfig;
use clinic_server::error::StartupError;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> ExitCode {
    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            let _ignored = writeln!(std::io::stderr().lock(), "clinic-brain: {error}");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), StartupError> {
    let config = BrainProcessConfig::load()?;
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .with_writer(std::io::stderr)
        .try_init()
        .map_err(|error| StartupError::Tracing {
            detail: error.to_string(),
        })?;
    serve_brain(config).await
}
