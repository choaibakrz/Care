//! Task 5, gate M0: the mock server on a free port, an application WebSocket client, and the
//! `fake_robot` binary (`--server` is the server's base `ws://host:port` URL; the robot token
//! comes from `ROBOT_TOKEN`, `mock-robot` with the mock services). The last tests check the
//! in-process simulated robots of `--mock` and that mock mutations reach a second console.

mod support;

use std::process::Stdio;
use std::time::Duration;

use serde_json::{Value, json};
use support::{LiveServer, MockApp, Res, TestResult, WsClient, call, post_json, put_json};
use tokio::process::{Child, Command};

const ADMIN: Option<&str> = Some("mock-admin");

fn spawn_fake_robot(server: &LiveServer) -> Res<Child> {
    Ok(Command::new(env!("CARGO_BIN_EXE_fake_robot"))
        .args([
            "--server",
            &server.ws_url(""),
            "--id",
            "robot-r2",
            "--simulated",
        ])
        .env("ROBOT_TOKEN", "mock-robot")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .kill_on_drop(true)
        .spawn()?)
}

async fn app_socket(_app: &MockApp, server: &LiveServer) -> Res<WsClient> {
    support::app_socket_with_token(server, "mock-admin").await
}

#[tokio::test]
async fn fake_robot_position_reaches_app_websocket_within_3s() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    let _robot = spawn_fake_robot(&server)?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = watcher.next_of_type("robot.updated", left).await?;
        if event.pointer("/robot/id") == Some(&json!("robot-r2")) {
            break;
        }
    }
    Ok(())
}

#[tokio::test]
async fn task_created_over_rest_reaches_fake_robot_and_delivers() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    let _robot = spawn_fake_robot(&server)?;
    tokio::time::sleep(Duration::from_millis(500)).await;
    let task = json!({ "kind": "fetch", "item": "blanket", "from_place": "storeroom", "to_place": "room-101" });
    let created = call(&app.app, post_json("/tasks", ADMIN, &task)?).await?;
    assert!(
        created.status.is_success(),
        "{}: {}",
        created.status,
        created.body
    );
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no task id")?
        .to_owned();
    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = watcher.next_of_type("task.updated", left).await?;
        if event.pointer("/task/id") == Some(&json!(id))
            && event.pointer("/task/state") == Some(&json!("delivered"))
        {
            break;
        }
    }
    Ok(())
}

/// The next `robot.updated` of one robot within `within`.
async fn next_update_of(watcher: &mut WsClient, robot: &str, within: Duration) -> Res<Value> {
    let deadline = tokio::time::Instant::now() + within;
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = watcher.next_of_type("robot.updated", left).await?;
        if event.pointer("/robot/id") == Some(&json!(robot)) {
            return Ok(event);
        }
    }
}

/// The second `robot.updated` of `robot` in `state` within 3 s (the robot's own report).
async fn settled_in(watcher: &mut WsClient, robot: &str, state: &str) -> Res<Value> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    let mut seen = 0;
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = next_update_of(watcher, robot, left).await?;
        if event.pointer("/robot/state") == Some(&json!(state)) {
            seen += 1;
            if seen == 2 {
                return Ok(event);
            }
        }
    }
}

/// The next `task.updated` of task `id` within `within`.
async fn next_task_update(watcher: &mut WsClient, id: &str, within: Duration) -> Res<Value> {
    let deadline = tokio::time::Instant::now() + within;
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = watcher.next_of_type("task.updated", left).await?;
        if event.pointer("/task/id") == Some(&json!(id)) {
            return Ok(event);
        }
    }
}

fn task_id(reply: &support::Reply) -> Res<String> {
    Ok(reply
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no task id")?
        .to_owned())
}

fn pos(event: &Value) -> Res<(f64, f64)> {
    let x = event
        .pointer("/robot/pos/x")
        .and_then(Value::as_f64)
        .ok_or("no pos.x")?;
    let y = event
        .pointer("/robot/pos/y")
        .and_then(Value::as_f64)
        .ok_or("no pos.y")?;
    Ok((x, y))
}

#[tokio::test]
async fn mock_demo_robots_move_and_report_every_second() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    for robot in ["r1", "r2", "r3", "r4"] {
        let first = next_update_of(&mut watcher, robot, Duration::from_secs(2)).await?;
        let mut moved = false;
        for _ in 0..10 {
            let later = next_update_of(&mut watcher, robot, Duration::from_secs(1)).await?;
            if pos(&later)? != pos(&first)? {
                moved = true;
                break;
            }
        }
        assert!(moved, "robot {robot} did not move");
    }
    Ok(())
}

#[tokio::test]
async fn paused_robot_stops_and_resume_moves_it_again() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    next_update_of(&mut watcher, "r1", Duration::from_secs(2)).await?;
    let pause = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert!(
        pause.status.is_success(),
        "{}: {}",
        pause.status,
        pause.body
    );
    // The robot's own report of the pause (the second `paused`: the first can be the
    // server's publish with the last position reported before the robot stopped).
    let paused = settled_in(&mut watcher, "r1", "paused").await?;
    tokio::time::sleep(Duration::from_millis(600)).await;
    let still = next_update_of(&mut watcher, "r1", Duration::from_secs(2)).await?;
    assert_eq!(still.pointer("/robot/state"), Some(&json!("paused")));
    assert_eq!(pos(&still)?, pos(&paused)?, "a paused robot moved");
    let resume = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "resume" }))?,
    )
    .await?;
    assert!(
        resume.status.is_success(),
        "{}: {}",
        resume.status,
        resume.body
    );
    let mut moved = false;
    for _ in 0..15 {
        let event = next_update_of(&mut watcher, "r1", Duration::from_secs(1)).await?;
        if pos(&event)? != pos(&paused)? {
            assert_ne!(event.pointer("/robot/state"), Some(&json!("paused")));
            moved = true;
            break;
        }
    }
    assert!(moved, "resume did not move r1");
    Ok(())
}

#[tokio::test]
async fn estop_shows_estop() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    watcher
        .next_of_type("snapshot", Duration::from_secs(2))
        .await?;
    let stop = call(
        &app.app,
        post_json("/robots/r3/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert!(stop.status.is_success(), "{}: {}", stop.status, stop.body);
    let stopped = settled_in(&mut watcher, "r3", "estop").await?;
    tokio::time::sleep(Duration::from_millis(600)).await;
    let still = next_update_of(&mut watcher, "r3", Duration::from_secs(2)).await?;
    assert_eq!(still.pointer("/robot/state"), Some(&json!("estop")));
    assert_eq!(pos(&still)?, pos(&stopped)?, "a stopped robot moved");
    Ok(())
}

#[tokio::test]
async fn mock_mutations_reach_a_second_console() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    let wait = Duration::from_secs(2);
    // Subscribed once the snapshot arrives: events published before that are not owed.
    watcher.next_of_type("snapshot", wait).await?;

    let adjusted = call(
        &app.app,
        post_json("/inventory/blanket/adjust", ADMIN, &json!({ "delta": 1 }))?,
    )
    .await?;
    assert!(adjusted.status.is_success(), "{}", adjusted.body);
    let event = watcher.next_of_type("inventory.updated", wait).await?;
    assert_eq!(event.pointer("/item/id"), Some(&json!("blanket")));

    let zone = json!({
        "id": "z-live", "name": "Quiet", "floor": 2, "kind": "deaf",
        "polygon": [[1.0, 1.0], [3.0, 1.0], [3.0, 3.0]]
    });
    let saved = call(&app.app, put_json("/zones/z-live", ADMIN, &zone)?).await?;
    assert!(saved.status.is_success(), "{}", saved.body);
    let event = watcher.next_of_type("zone.updated", wait).await?;
    assert_eq!(event.pointer("/zone/id"), Some(&json!("z-live")));
    let deleted = call(
        &app.app,
        support::request(axum::http::Method::DELETE, "/zones/z-live", ADMIN, None)?,
    )
    .await?;
    assert!(deleted.status.is_success(), "{}", deleted.body);
    let event = watcher.next_of_type("zone.deleted", wait).await?;
    assert_eq!(event.pointer("/zone_id"), Some(&json!("z-live")));

    let patched = call(
        &app.app,
        put_json(
            "/schedules/night-restock",
            ADMIN,
            &json!({ "enabled": false }),
        )?,
    )
    .await?;
    assert!(patched.status.is_success(), "{}", patched.body);
    let event = watcher.next_of_type("schedule.updated", wait).await?;
    assert_eq!(event.pointer("/schedule/enabled"), Some(&json!(false)));

    let cancelled = call(&app.app, post_json("/tasks/t-1/cancel", ADMIN, &json!({}))?).await?;
    assert!(cancelled.status.is_success(), "{}", cancelled.body);
    let deadline = tokio::time::Instant::now() + wait;
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = watcher.next_of_type("task.updated", left).await?;
        if event.pointer("/task/id") == Some(&json!("t-1")) {
            assert_eq!(event.pointer("/task/state"), Some(&json!("cancelled")));
            break;
        }
    }
    Ok(())
}

#[tokio::test]
async fn mock_never_sends_a_demo_robot_a_task_off_its_floor() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    watcher
        .next_of_type("snapshot", Duration::from_secs(2))
        .await?;
    // Not on the plan: no demo robot may take it (ruling R21); no fake_robot is connected.
    let task = json!({ "kind": "fetch", "item": "blanket", "from_place": "storeroom", "to_place": "room-101" });
    let created = call(&app.app, post_json("/tasks", ADMIN, &task)?).await?;
    assert!(created.status.is_success(), "{}", created.body);
    let alert = watcher
        .next_of_type("alert", Duration::from_secs(2))
        .await?;
    assert_eq!(alert.get("kind"), Some(&json!("task_needs_human")));
    let id = task_id(&created)?;
    tokio::time::sleep(Duration::from_millis(500)).await;
    let now = call(&app.app, support::get(&format!("/tasks/{id}"), ADMIN)?).await?;
    assert_eq!(
        now.body.get("state"),
        Some(&json!("requested")),
        "{}",
        now.body
    );
    assert_eq!(now.body.get("robot_id"), Some(&Value::Null));
    Ok(())
}

#[tokio::test]
async fn mock_sends_a_task_to_a_demo_robot_of_the_destination_floor() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    watcher
        .next_of_type("snapshot", Duration::from_secs(2))
        .await?;
    // Both places on the ground floor, where r1 and r3 live.
    let task = json!({ "kind": "fetch", "item": "towel", "from_place": "linen-shelf", "to_place": "therapy-1" });
    let created = call(&app.app, post_json("/tasks", ADMIN, &task)?).await?;
    assert!(created.status.is_success(), "{}", created.body);
    let id = task_id(&created)?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = next_task_update(&mut watcher, &id, left).await?;
        if event.pointer("/task/state") == Some(&json!("assigned")) {
            let robot = event.pointer("/task/robot_id").and_then(Value::as_str);
            assert!(matches!(robot, Some("r1" | "r3")), "assigned to {robot:?}");
            break;
        }
    }
    Ok(())
}

#[tokio::test]
async fn a_task_held_by_a_robot_that_disconnects_fails_robot_lost() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    let mut robot = spawn_fake_robot(&server)?;
    next_update_of(&mut watcher, "robot-r2", Duration::from_secs(3)).await?;
    let task = json!({ "kind": "fetch", "item": "blanket", "from_place": "storeroom", "to_place": "room-101" });
    let created = call(&app.app, post_json("/tasks", ADMIN, &task)?).await?;
    assert!(created.status.is_success(), "{}", created.body);
    let id = task_id(&created)?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = next_task_update(&mut watcher, &id, left).await?;
        if event.pointer("/task/state") == Some(&json!("assigned")) {
            break;
        }
    }
    robot.kill().await?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = next_task_update(&mut watcher, &id, left).await?;
        if event.pointer("/task/state") == Some(&json!("failed")) {
            assert_eq!(event.pointer("/task/reason"), Some(&json!("robot_lost")));
            break;
        }
    }
    let robots = call(&app.app, support::get("/robots", ADMIN)?).await?;
    let fake = robots
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|r| r.get("id") == Some(&json!("robot-r2")))
        })
        .ok_or("robot-r2 not listed")?;
    assert_eq!(fake.get("connected"), Some(&json!(false)));
    // The stop for an offline robot is refused, never accepted.
    let stop = call(
        &app.app,
        post_json(
            "/robots/robot-r2/command",
            ADMIN,
            &json!({ "name": "estop" }),
        )?,
    )
    .await?;
    assert_eq!(stop.status.as_u16(), 409, "{}", stop.body);
    Ok(())
}

/// Polls `robot.updated` events of `robot` until `/robot/mic_open` equals `want` (2 s).
async fn wait_mic(watcher: &mut WsClient, robot: &str, want: bool) -> Res<Value> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = next_update_of(watcher, robot, left)
            .await
            .map_err(|error| {
                format!("robot {robot}: mic_open never became {want} within 2 s ({error})")
            })?;
        if event.pointer("/robot/mic_open") == Some(&json!(want)) {
            return Ok(event);
        }
    }
}

#[tokio::test]
async fn mock_robot_mic_is_open_outside_deaf_zones_and_closed_inside_one() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket(&app, &server).await?;
    // Every demo robot hears at startup (no deaf zone in the seed).
    for robot in ["r1", "r2", "r3", "r4"] {
        wait_mic(&mut watcher, robot, true).await?;
    }
    // Stop r1 where it is, then put a deaf zone around it.
    let pause = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert!(
        pause.status.is_success(),
        "{}: {}",
        pause.status,
        pause.body
    );
    let paused = settled_in(&mut watcher, "r1", "paused").await?;
    let (x, y) = pos(&paused)?;
    let floor = paused
        .pointer("/robot/pos/floor")
        .and_then(Value::as_i64)
        .ok_or("no pos.floor")?;
    let zone = json!({
        "id": "z-quiet", "name": "Quiet", "floor": floor, "kind": "deaf",
        "polygon": [[x - 0.5, y - 0.5], [x + 0.5, y - 0.5], [x + 0.5, y + 0.5], [x - 0.5, y + 0.5]]
    });
    let saved = call(&app.app, put_json("/zones/z-quiet", ADMIN, &zone)?).await?;
    assert!(
        saved.status.is_success(),
        "{}: {}",
        saved.status,
        saved.body
    );
    wait_mic(&mut watcher, "r1", false).await?;
    let deleted = call(
        &app.app,
        support::request(axum::http::Method::DELETE, "/zones/z-quiet", ADMIN, None)?,
    )
    .await?;
    assert!(
        deleted.status.is_success(),
        "{}: {}",
        deleted.status,
        deleted.body
    );
    wait_mic(&mut watcher, "r1", true).await?;
    Ok(())
}
