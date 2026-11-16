//! Simulated robots (Task 5): one implementation for the `fake_robot` binary and for the
//! robots that move in `--mock`.
//!
//! - [`route::SimPlanner`]: waypoints through doors and along corridors (simplistic: no
//!   furniture, zones, other robots or lifts; real routing is Task 13b).
//! - [`driver::SimDriver`]: the robot's behaviour over contract C2 (round, tasks, commands,
//!   zone acks).
//! - [`transport`]: a WebSocket (`fake_robot`) or the hub's in-process link (`--mock`).
//! - [`spawn_in_process`]: the in-process robots of `--mock`, each a real hub session handled
//!   by the robot service like a WebSocket robot.
//!
//! Everything here is simulated and says so (`simulated: true` in `hello`).

pub mod driver;
pub mod fleet;
pub mod route;
pub mod transport;

use std::sync::Arc;
use std::time::Duration;

use domain::{Clock, RobotId};
use locations::ClinicPlan;
use realtime::{Hub, ProtocolError, RealtimeError};
use tokio::task::JoinHandle;

pub use driver::{RobotTransport, SessionEnd, SimDriver, SimRobotConfig, Unreachable};
pub use route::SimPlanner;
pub use transport::{HubTransport, WsTransport};

use crate::services::RobotService;

/// The console's demo clinic, embedded (`seed/clinic_map.json`, `"marque": "inventé"`).
const SEED_PLAN: &str = include_str!("../../seed/clinic_map.json");
/// How long an in-process robot stays off after `shutdown` before it reconnects.
pub const RESTART_DELAY: Duration = Duration::from_secs(10);

/// Why a simulated robot stopped.
#[derive(Debug, thiserror::Error)]
pub enum SimError {
    /// The connection could not be opened.
    #[error("Cannot connect to {url}: {reason}. Is the server running, and is the token right?")]
    Connect {
        /// URL.
        url: String,
        /// Why.
        reason: String,
    },
    /// The server closed the connection with an error code.
    #[error("The server closed the connection ({code}: {reason}).")]
    Closed {
        /// Close code.
        code: u16,
        /// Close text.
        reason: String,
    },
    /// The connection failed while open.
    #[error("The connection to the server failed ({reason}); start the robot again.")]
    Transport {
        /// Why.
        reason: String,
    },
    /// The hub link closed.
    #[error("The in-process robot link closed: {0}")]
    Hub(RealtimeError),
    /// A message could not be encoded.
    #[error("A robot message could not be encoded: {0}")]
    Protocol(#[from] ProtocolError),
    /// The plan could not be read.
    #[error(
        "The clinic plan could not be read ({reason}); check the file against docs/map-format.md."
    )]
    Plan {
        /// Why.
        reason: String,
    },
}

/// The embedded seed plan.
///
/// # Errors
/// `SimError::Plan` if the embedded file does not parse (a unit test checks it does).
pub fn seed_plan() -> Result<ClinicPlan, SimError> {
    serde_json::from_str(SEED_PLAN).map_err(|error| SimError::Plan {
        reason: format!("seed/clinic_map.json: {error}"),
    })
}

/// Starts in-process simulated robots: each is registered on the hub now (so it is
/// connected before the first request), its session is run by `robots` like a WebSocket
/// robot's, and its driver plays it over the hub link. After `shutdown` a robot reconnects
/// [`RESTART_DELAY`] later, back at its start pose. A robot whose registration fails (already
/// connected) is skipped with a warning.
#[must_use]
pub fn spawn_in_process(
    hub: &Arc<Hub>,
    robots: &Arc<dyn RobotService>,
    clock: &Arc<dyn Clock>,
    planner: &Arc<SimPlanner>,
    configs: Vec<SimRobotConfig>,
) -> Vec<JoinHandle<()>> {
    configs
        .into_iter()
        .filter_map(|config| {
            let id = config.robot_id().clone();
            match hub.register_robot(id.clone()) {
                Ok(session) => Some(tokio::spawn(supervise(
                    InProcess {
                        hub: hub.clone(),
                        robots: robots.clone(),
                        clock: clock.clone(),
                        planner: planner.clone(),
                        config,
                    },
                    session,
                ))),
                Err(error) => {
                    tracing::warn!(robot = %id, %error, "simulated robot not started");
                    None
                }
            }
        })
        .collect()
}

/// What an in-process robot needs.
struct InProcess {
    hub: Arc<Hub>,
    robots: Arc<dyn RobotService>,
    clock: Arc<dyn Clock>,
    planner: Arc<SimPlanner>,
    config: SimRobotConfig,
}

/// Runs one in-process robot, session after session.
async fn supervise(robot: InProcess, first: realtime::RobotSession) {
    let id: RobotId = robot.config.robot_id().clone();
    let mut next = Some(first);
    loop {
        let mut session = match next.take() {
            Some(session) => session,
            None => match robot.hub.register_robot(id.clone()) {
                Ok(session) => session,
                Err(error) => {
                    tracing::warn!(robot = %id, %error, "simulated robot cannot reconnect yet");
                    tokio::time::sleep(RESTART_DELAY).await;
                    continue;
                }
            },
        };
        let Some(link) = session.take_link() else {
            tracing::error!(robot = %id, "simulated robot session has no link; stopping it");
            robot.hub.unregister_robot(&id);
            return;
        };
        let service = robot.robots.clone();
        let service = tokio::spawn(async move { service.run_session(session).await });
        let mut transport = HubTransport::new(link, id.clone(), robot.clock.clone());
        let ended = SimDriver::new(robot.config.clone(), robot.planner.clone())
            .run(&mut transport)
            .await;
        robot.hub.unregister_robot(&id);
        drop(transport);
        service.abort();
        robot.robots.on_disconnect(&id).await;
        match ended {
            Ok(SessionEnd::Shutdown) => {
                tracing::info!(robot = %id, "simulated robot shut down; it reconnects in {} s", RESTART_DELAY.as_secs());
            }
            Ok(SessionEnd::Closed) => tracing::info!(robot = %id, "simulated robot link closed"),
            Err(error) => tracing::warn!(robot = %id, %error, "simulated robot stopped"),
        }
        tokio::time::sleep(RESTART_DELAY).await;
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn embedded_seed_plan_parses() -> Result<(), Box<dyn std::error::Error>> {
        let plan = super::seed_plan()?;
        assert_eq!(plan.floors.len(), 2);
        Ok(())
    }
}
