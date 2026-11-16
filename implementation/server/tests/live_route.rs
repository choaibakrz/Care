//! Task 11: live positions over HTTP and WebSocket, the position broadcaster, and privacy
//! (no tablet position reaches a repository or the logs).

mod support;

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use async_trait::async_trait;
use axum::http::StatusCode;
use clinic_server::services::location::PositionBroadcaster;
use clinic_server::state::RepositoryOverrides;
use domain::ports::RobotRepository;
use domain::{Clock, DomainError, RobotFix, RobotId, RobotRecord, RobotStatus, Role, SubjectRef};
use locations::{LivePositions, Point2, PositionFix, PositionTtl, RobotInfo};
use realtime::Hub;
use serde_json::{Value, json};
use storage::TokenSubject;
use support::{LogCapture, RealApp, TestResult, WsClient, map, post_json, put_json};

/// One call to the robot repository: method, robot id, and the fix when one was passed.
type RepoCall = (&'static str, String, Option<(i32, f64, f64)>);

/// An in-memory robot repository that records every call with its arguments.
#[derive(Default)]
struct RecordingRobotRepo {
    robots: Mutex<HashMap<RobotId, RobotRecord>>,
    fixes: Mutex<HashMap<RobotId, RobotFix>>,
    calls: Mutex<Vec<RepoCall>>,
}

impl RecordingRobotRepo {
    fn calls(&self) -> Vec<RepoCall> {
        self.calls.lock().map(|c| c.clone()).unwrap_or_default()
    }
    fn record(&self, method: &'static str, id: &str, fix: Option<&RobotFix>) {
        if let Ok(mut calls) = self.calls.lock() {
            calls.push((method, id.to_owned(), fix.map(|f| (f.floor, f.x, f.y))));
        }
    }
}

fn poisoned() -> DomainError {
    DomainError::StoreUnavailable { what: "robot" }
}

#[async_trait]
impl RobotRepository for RecordingRobotRepo {
    async fn list(&self) -> Result<Vec<RobotRecord>, DomainError> {
        self.record("list", "", None);
        Ok(self
            .robots
            .lock()
            .map_err(|_| poisoned())?
            .values()
            .cloned()
            .collect())
    }
    async fn find(&self, id: &RobotId) -> Result<Option<RobotRecord>, DomainError> {
        self.record("find", id.as_str(), None);
        Ok(self.robots.lock().map_err(|_| poisoned())?.get(id).cloned())
    }
    async fn upsert(&self, robot: &RobotRecord) -> Result<(), DomainError> {
        self.record("upsert", robot.id.as_str(), None);
        self.robots
            .lock()
            .map_err(|_| poisoned())?
            .insert(robot.id.clone(), robot.clone());
        Ok(())
    }
    async fn save_last_fix(&self, robot: &RobotId, fix: &RobotFix) -> Result<(), DomainError> {
        self.record("save_last_fix", robot.as_str(), Some(fix));
        self.fixes
            .lock()
            .map_err(|_| poisoned())?
            .insert(robot.clone(), *fix);
        Ok(())
    }
    async fn last_fix(&self, robot: &RobotId) -> Result<Option<RobotFix>, DomainError> {
        self.record("last_fix", robot.as_str(), None);
        Ok(self
            .fixes
            .lock()
            .map_err(|_| poisoned())?
            .get(robot)
            .copied())
    }
}

/// Room anchors of the fixture map where the tablet goes (a tablet is shown at its room's
/// anchor, so these are the only tablet coordinates the server knows).
const TABLET_POINTS: [(f64, f64); 3] = [(5.0, 16.0), (15.0, 16.0), (20.0, 4.0)];

fn carries_tablet_data(call: &RepoCall) -> bool {
    call.1 == "tab-1"
        || call.2.is_some_and(|(_, x, y)| {
            TABLET_POINTS
                .iter()
                .any(|(tx, ty)| (x - tx).abs() < 1e-9 && (y - ty).abs() < 1e-9)
        })
}

/// Ruling R1: the runtime check, on the full wiring with a recording robot repository (the
/// only port that persists a position). A robot moves (its paths may reach the repository);
/// a tablet moves and scans: no call carries the tablet, before or after the periodic tasks.
#[tokio::test]
async fn no_tablet_position_is_ever_passed_to_a_repository() -> TestResult {
    let repo = Arc::new(RecordingRobotRepo::default());
    let app = RealApp::start_with_overrides(
        map::small_plan()?,
        support::security_config()?,
        RepositoryOverrides {
            robots: Some(repo.clone()),
            ..RepositoryOverrides::default()
        },
    )
    .await?;
    repo.upsert(&RobotRecord {
        id: "robot-r2".parse()?,
        name: "R2".to_owned(),
        role_card: support::PORTER_CARD.to_owned(),
        simulated: false,
        key_hash: String::new(),
    })
    .await?;
    let robot_token = app
        .tokens
        .issue(
            TokenSubject::Robot {
                robot_id: "robot-r2".parse()?,
            },
            Duration::from_hours(1),
        )
        .await?;
    let server = app.serve().await?;
    let mut robot =
        WsClient::connect_with_token(&server.ws_url("/ws/robot/robot-r2"), robot_token.expose())
            .await?;
    let now = app.clock.now();
    robot
        .send_json(&support::hello("robot-r2", false, None, now))
        .await?;
    for x in [5.0, 6.0, 7.0] {
        robot
            .send_json(&support::robot_state(1, x, 4.0, "idle", app.clock.now()))
            .await?;
    }
    // The robot's session has reached the repository (at least the lookup of the robot).
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    while repo.calls().len() < 2 {
        if tokio::time::Instant::now() >= deadline {
            return Err("the robot session never reached the repository".into());
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }

    let token = app.user_token("u-nurse", Role::Nurse, "tab-1").await?;
    let before = repo.calls().len();
    for room in [map::ROOM_101, map::ROOM_102, map::ROOM_103] {
        let reply = app
            .call(put_json(
                "/me/location",
                Some(&token),
                &json!({ "place": room }),
            )?)
            .await?;
        assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    }
    let scan = json!({
        "at": app.clock.now().to_rfc3339(),
        "observations": [{ "type": "range", "anchor": "robot-r2", "metres": 3.0, "sigma_m": 0.5 }],
        "motion": null,
        "pressure_hpa": null
    });
    app.call(post_json("/me/scans", Some(&token), &scan)?)
        .await?;
    let during: Vec<RepoCall> = repo.calls().into_iter().skip(before).collect();
    assert!(
        during.iter().all(|c| c.1 == "robot-r2"),
        "tablet moves reached the robot repository: {during:?}"
    );

    // Let periodic paths (liveness, any periodic save) run, then check every call.
    app.clock.advance(Duration::from_secs(2));
    tokio::time::sleep(Duration::from_millis(1_500)).await;
    let all = repo.calls();
    let leaks: Vec<&RepoCall> = all.iter().filter(|c| carries_tablet_data(c)).collect();
    assert!(
        leaks.is_empty(),
        "repository calls carried tablet data: {leaks:?}"
    );
    Ok(())
}

#[tokio::test]
async fn broadcaster_coalesces_ten_updates_into_one_delta() -> TestResult {
    let clock = support::fake_clock()?;
    let dyn_clock: Arc<dyn Clock> = clock.clone();
    let live = Arc::new(LivePositions::new(
        Arc::new(map::small_map()?),
        dyn_clock.clone(),
        PositionTtl::default(),
    ));
    let hub = Arc::new(Hub::with_clock(dyn_clock));
    let mut events = hub.subscribe_apps();
    let robot: RobotId = "robot-r2".parse()?;
    let at = support::start_time()?;
    for step in 0..10_u32 {
        let x = 5.0 + f64::from(step);
        live.update_robot(
            PositionFix {
                subject: SubjectRef::Robot(robot.clone()),
                floor: 1,
                point: Point2::new(x, 10.0)?,
                heading_rad: Some(0.0),
                at,
            },
            RobotInfo {
                name: "R2".to_owned(),
                status: RobotStatus::Busy,
                task: None,
                battery_pct: 80.0,
                mic_open: true,
            },
        )?;
    }
    let broadcaster = PositionBroadcaster::spawn(live, hub.clone(), Duration::from_millis(200));
    let mut deltas = Vec::new();
    let deadline = tokio::time::Instant::now() + Duration::from_millis(700);
    while let Ok(Ok(event)) = tokio::time::timeout_at(deadline, events.recv()).await {
        let value = serde_json::to_value(&event)?;
        if value.get("type") == Some(&json!("positions.delta")) {
            deltas.push(value);
        }
    }
    broadcaster.abort();
    let with_robot: Vec<&Value> = deltas
        .iter()
        .filter(|d| {
            d.get("robots")
                .and_then(Value::as_array)
                .is_some_and(|r| !r.is_empty())
        })
        .collect();
    assert_eq!(with_robot.len(), 1, "{deltas:?}");
    let robots = with_robot
        .first()
        .and_then(|d| d.get("robots"))
        .and_then(Value::as_array)
        .ok_or("no robots")?;
    assert_eq!(robots.len(), 1);
    let x = robots
        .first()
        .and_then(|r| r.get("x"))
        .and_then(Value::as_f64);
    assert_eq!(x, Some(14.0), "the delta must carry the latest fix");
    Ok(())
}

#[tokio::test]
async fn new_ws_client_gets_snapshot_first() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let mut client = app.app_socket(&server).await?;
    let first = client.next_json(Duration::from_secs(3)).await?;
    assert_eq!(first.get("type"), Some(&json!("snapshot")));
    assert!(first.pointer("/positions/robots").is_some(), "{first}");
    Ok(())
}

#[tokio::test]
async fn put_location_unknown_place_lists_valid_places() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let reply = app
        .call(put_json(
            "/me/location",
            Some(&token),
            &json!({ "place": "room-999" }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(reply.error_code(), Some("unknown_place"));
    let message = reply.error_message();
    assert!(
        message.starts_with("Place 'room-999' is not on the map. Places on floor"),
        "{message}"
    );
    assert!(message.contains(map::ROOM_101), "{message}");
    Ok(())
}

/// Task 11 Step 3: log output never includes a tablet's room while the tablet moves.
#[tokio::test]
async fn tablet_room_never_appears_in_logs() -> TestResult {
    let logs = LogCapture::global()?;
    let mark = logs.mark();
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    for room in [map::ROOM_101, map::ROOM_102, map::ROOM_103] {
        let reply = app
            .call(put_json(
                "/me/location",
                Some(&token),
                &json!({ "place": room }),
            )?)
            .await?;
        assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    }
    let text = logs.since(mark);
    assert!(
        text.contains(support::REQUEST_TRACE_LINE),
        "the request log line was not captured, so the capture proves nothing"
    );
    for leak in [
        map::ROOM_101,
        map::ROOM_102,
        map::ROOM_103,
        "Chambre 101",
        "Chambre 102",
        "Chambre 103",
    ] {
        assert!(!text.contains(leak), "the logs contain '{leak}'");
    }
    Ok(())
}
