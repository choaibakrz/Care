//! Stand-in robot for jobs 4 and 5 (Task 5).
//!
//! `fake_robot --server ws://… --id robot-r2 --simulated`: sends `hello`, then `robot.state`
//! every second along a round between three places (default `dock-a`, `reception`,
//! `therapy-1` of the seed plan, through doors and corridors); on `task.assign` replies
//! `task.event` `assigned` → `en_route` → `delivered` with 2 s gaps (`delivered` waits until
//! it reached a destination on its floor; a destination not on its floor or not on the plan
//! keeps the 2 s timeline without moving, and a warning says so on stderr). Obeys `pause`, `resume`, `estop`, `dock`,
//! `shutdown`; acknowledges `zones.update`. Everything it does is simulated; the behaviour is
//! `clinic_server::sim`, shared with the robots of `--mock`.
//!
//! The token comes from `--token` or `ROBOT_TOKEN`; without one it uses the mock server's
//! robot token `mock-robot-<id>` (the live server refuses it).

use std::io::Write as _;
use std::process::ExitCode;
use std::sync::Arc;
use std::time::Duration;

use clap::Parser;
use clinic_server::services::mock::MOCK_ROBOT_TOKEN_PREFIX;
use clinic_server::sim::{
    SessionEnd, SimDriver, SimError, SimPlanner, SimRobotConfig, WsTransport, seed_plan,
};
use domain::{PlaceId, RobotId};
use realtime::RobotPose;

/// Command line.
#[derive(Debug, Clone, Parser)]
#[command(name = "fake_robot", about = "Simulated robot for the clinic server")]
struct FakeRobotArgs {
    /// Server WebSocket base, for example `ws://127.0.0.1:8080`.
    #[arg(long)]
    server: String,
    /// Robot id.
    #[arg(long)]
    id: String,
    /// Robot token (`TokenSubject::Robot`); default `mock-robot-<id>` (mock server only).
    #[arg(long, env = "ROBOT_TOKEN")]
    token: Option<String>,
    /// Announce itself as simulated. Without it the robot says it is real, so the console and
    /// the dispatcher treat it like a physical robot (HACKATHON stand-in for real hardware).
    #[arg(long)]
    simulated: bool,
    /// Places of its round, comma-separated, all on one floor of the plan.
    #[arg(
        long,
        value_delimiter = ',',
        default_value = "dock-a,reception,therapy-1"
    )]
    round: Vec<String>,
    /// A clinic plan file (`ClinicPlan` JSON); default: the embedded seed plan.
    #[arg(long)]
    plan: Option<std::path::PathBuf>,
    /// Milliseconds between two `robot.state` messages.
    #[arg(long, default_value_t = 1000)]
    state_interval_ms: u64,
}

/// Why the fake robot stopped before it connected.
#[derive(Debug, thiserror::Error)]
enum FakeRobotError {
    /// A command-line value is wrong.
    #[error("{0}")]
    Input(String),
    /// The simulation failed.
    #[error(transparent)]
    Sim(#[from] SimError),
}

#[tokio::main]
async fn main() -> ExitCode {
    let args = FakeRobotArgs::parse();
    // Warnings (for example a destination not on this robot's floor) go to stderr.
    if tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_target(false)
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn")),
        )
        .try_init()
        .is_err()
    {
        let _ignored = writeln!(std::io::stderr().lock(), "fake_robot: no log output");
    }
    match run(args).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            let _ignored = writeln!(std::io::stderr().lock(), "fake_robot: {error}");
            ExitCode::FAILURE
        }
    }
}

/// Connects and plays the robot until the server closes.
async fn run(args: FakeRobotArgs) -> Result<(), FakeRobotError> {
    let robot: RobotId = args
        .id
        .parse()
        .map_err(|error| FakeRobotError::Input(format!("--id: {error}")))?;
    let plan = match &args.plan {
        Some(path) => locations::load_plan(path)
            .map_err(|error| FakeRobotError::Input(format!("--plan: {error}")))?,
        None => seed_plan()?,
    };
    let planner = Arc::new(SimPlanner::new(&plan));
    let round = args
        .round
        .iter()
        .map(|place| {
            place
                .trim()
                .parse::<PlaceId>()
                .map_err(|error| FakeRobotError::Input(format!("--round: {error}")))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let first = round
        .first()
        .ok_or_else(|| FakeRobotError::Input("--round: name at least one place".to_owned()))?;
    let (floor, [x, y]) = planner.place(first).ok_or_else(|| {
        FakeRobotError::Input(format!("--round: place '{first}' is not on the plan"))
    })?;
    let config = SimRobotConfig::new(
        robot.clone(),
        RobotPose {
            x,
            y,
            heading: 0.0,
            floor,
        },
        round.clone(),
    )
    .with_role_card("test")
    .with_home(first.clone())
    .with_state_interval(Duration::from_millis(args.state_interval_ms))
    .with_simulated(args.simulated);
    let token = args
        .token
        .unwrap_or_else(|| format!("{MOCK_ROBOT_TOKEN_PREFIX}{robot}"));
    let mut transport = WsTransport::connect(&args.server, &robot, &token).await?;
    let mut out = std::io::stderr().lock();
    let _ignored = writeln!(
        out,
        "fake_robot: {robot} connected to {} ({}); round {}",
        args.server,
        if args.simulated { "simulated" } else { "announced as real" },
        args.round.join(" -> ")
    );
    drop(out);
    let ended = SimDriver::new(config, planner).run(&mut transport).await?;
    let why = match ended {
        SessionEnd::Closed => "the server closed the connection",
        SessionEnd::Shutdown => "the server sent shutdown",
    };
    let _ignored = writeln!(std::io::stderr().lock(), "fake_robot: stopped: {why}");
    Ok(())
}
