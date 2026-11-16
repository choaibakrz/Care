//! Task 14: robot sessions over real WebSockets on a free port: authentication and close
//! codes, de-duplication, liveness, reassignment, the emergency stop path, slow subscribers.

mod support;

use std::time::Duration;

use axum::http::StatusCode;
use domain::{Clock as _, Role};
use realtime::{AlertKind, AlertLevel, AppEvent};
use serde_json::{Value, json};
use storage::TokenSubject;
use support::{
    LiveServer, RealApp, Res, TestResult, WsClient, get, hello, map, post_json, task_event,
};
use tokio::sync::broadcast;

const WAIT: Duration = Duration::from_secs(3);

fn fetch_blanket() -> Value {
    json!({ "kind": "fetch", "item": "blanket", "from_place": map::STOREROOM, "to_place": map::ROOM_101 })
}

fn estop() -> Value {
    json!({ "name": "estop" })
}

/// Creates a fetch task and waits for the robot to receive its `task.assign`.
async fn assign_one(app: &RealApp, robot: &mut WsClient, nurse: &str) -> Res<String> {
    app.set_stock("blanket", 3).await?;
    let reply = app
        .call(post_json("/tasks", Some(nurse), &fetch_blanket())?)
        .await?;
    assert!(
        reply.status.is_success(),
        "{}: {}",
        reply.status,
        reply.body
    );
    let task = reply
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no task id")?
        .to_owned();
    let assign = robot.next_of_type("task.assign", WAIT).await?;
    assert_eq!(assign.get("task_id"), Some(&json!(task)));
    Ok(task)
}

async fn task_body(app: &RealApp, token: &str, task: &str) -> Res<Value> {
    Ok(app
        .call(get(&format!("/tasks/{task}"), Some(token))?)
        .await?
        .body)
}

/// Polls `GET /tasks/{id}` until `check` holds or `within` passes.
async fn wait_for_task(
    app: &RealApp,
    token: &str,
    task: &str,
    within: Duration,
    check: impl Fn(&Value) -> bool,
) -> Res<Value> {
    let deadline = tokio::time::Instant::now() + within;
    loop {
        let body = task_body(app, token, task).await?;
        if check(&body) {
            return Ok(body);
        }
        if tokio::time::Instant::now() >= deadline {
            return Err(format!("task never reached the expected state: {body}").into());
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
}

/// Real time for at least one tick of the liveness watch (it ticks every second).
const LIVENESS_TICK: Duration = Duration::from_millis(1_200);

async fn robot_status(app: &RealApp, admin: &str, robot: &str) -> Res<Option<Value>> {
    let robots = app.call(get("/robots", Some(admin))?).await?;
    Ok(robots
        .body
        .as_array()
        .and_then(|list| list.iter().find(|r| r.get("id") == Some(&json!(robot))))
        .and_then(|r| r.get("state"))
        .cloned())
}

/// Moves the fake clock (which drives liveness) past the 5 s timeout, checking both sides:
/// at 4.9 s and at exactly 5.0 s ("silent for longer than 5 s") there is no `robot_offline`
/// alert yet and the state is never `offline`; then the clock goes to 6 s.
async fn go_silent(
    app: &RealApp,
    robot: &str,
    mut events: Option<&mut broadcast::Receiver<AppEvent>>,
) -> TestResult {
    let admin = app.admin_token().await?;
    for (step_ms, label) in [(4_900, "4.9 s"), (100, "exactly 5.0 s")] {
        app.clock.advance(Duration::from_millis(step_ms));
        tokio::time::sleep(LIVENESS_TICK).await;
        let status = robot_status(app, &admin, robot).await?;
        assert_ne!(status, Some(json!("offline")), "{robot} offline at {label}");
        if let Some(events) = events.as_deref_mut() {
            while let Ok(event) = events.try_recv() {
                let early = matches!(
                    event,
                    AppEvent::Alert {
                        kind: AlertKind::RobotOffline,
                        ..
                    }
                );
                assert!(!early, "robot_offline alert at {label}");
            }
        }
    }
    app.clock.advance(Duration::from_secs(1));
    Ok(())
}

async fn connect(server: &LiveServer, path_robot: &str, token: &str) -> Res<WsClient> {
    WsClient::connect_with_token(&server.ws_url(&format!("/ws/robot/{path_robot}")), token).await
}

#[tokio::test]
async fn robot_with_wrong_token_is_closed_with_4403_and_reason() -> TestResult {
    let app = RealApp::start().await?;
    let r1_token = app.add_robot("robot-r1", false).await?;
    app.add_robot("robot-r2", false).await?;
    let server = app.serve().await?;
    let mut socket = connect(&server, "robot-r2", &r1_token).await?;
    let (code, reason) = socket.close_frame(WAIT).await?;
    assert_eq!(code, 4403);
    assert_eq!(
        reason,
        "Token belongs to robot robot-r1 but the connection asks for robot robot-r2."
    );
    Ok(())
}

#[tokio::test]
async fn unknown_robot_is_closed_with_4404() -> TestResult {
    let app = RealApp::start().await?;
    let token = app
        .tokens
        .issue(
            TokenSubject::Robot {
                robot_id: "robot-zz".parse()?,
            },
            Duration::from_hours(1),
        )
        .await?;
    let server = app.serve().await?;
    let mut socket = connect(&server, "robot-zz", token.expose()).await?;
    let (code, reason) = socket.close_frame(WAIT).await?;
    assert_eq!(code, 4404);
    assert!(reason.contains("robot-zz"), "{reason}");
    Ok(())
}

#[tokio::test]
async fn duplicate_event_id_after_reconnect_changes_nothing() -> TestResult {
    let logs = support::LogCapture::global()?;
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let nurse = app.nurse_token().await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let task = assign_one(&app, &mut robot, &nurse).await?;
    let en_route = task_event(&task, "en_route", None, app.clock.now());
    robot.send_json(&en_route).await?;
    wait_for_task(&app, &nurse, &task, WAIT, |b| {
        b.get("state") == Some(&json!("en_route"))
    })
    .await?;
    robot.close().await?;

    let token = app.add_robot("robot-r2", false).await?;
    let mut again = connect(&server, "robot-r2", &token).await?;
    let mark = logs.mark();
    again
        .send_json(&hello("robot-r2", false, Some(&task), app.clock.now()))
        .await?;
    // The same envelope (same id): en_route -> en_route would be an illegal transition, so
    // only de-duplication leaves no rejection behind.
    again.send_json(&en_route).await?;
    app.robot_barrier(&mut again, "robot-r2", 42.0).await?;
    app.assert_nothing_rejected(&logs, mark).await?;
    let body = task_body(&app, &nurse, &task).await?;
    assert_eq!(body.get("state"), Some(&json!("en_route")));
    let to_en_route = support::read_journal(&app.config.journal.dir)?
        .into_iter()
        .filter(|r| {
            matches!(&r.body, audit::RecordBody::TaskStateChanged { task: t, to: domain::TaskState::EnRoute, .. } if t.as_str() == task)
        })
        .count();
    assert_eq!(to_en_route, 1);
    Ok(())
}

#[tokio::test]
async fn robot_silent_for_5s_raises_alert_and_keeps_last_state() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let mut events = app.hub.subscribe_apps();
    let _robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    go_silent(&app, "robot-r2", Some(&mut events)).await?;
    let deadline = tokio::time::Instant::now() + WAIT;
    let mut alerted = false;
    while let Ok(Ok(event)) = tokio::time::timeout_at(deadline, events.recv()).await {
        if let AppEvent::Alert {
            kind: AlertKind::RobotOffline,
            message,
            ..
        } = event
        {
            assert!(message.contains("robot-r2"), "{message}");
            alerted = true;
            break;
        }
    }
    assert!(alerted, "no robot_offline alert within 3 s");
    // The state is the last reported one (never `offline`); `last_seen` shows the silence.
    let admin = app.admin_token().await?;
    let robots = app.call(get("/robots", Some(&admin))?).await?;
    let robot = robots
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|r| r.get("id") == Some(&json!("robot-r2")))
        })
        .cloned()
        .ok_or("robot-r2 not listed")?;
    assert_eq!(robot.get("state"), Some(&json!("idle")), "{robot}");
    let last_seen = robot
        .get("last_seen")
        .and_then(Value::as_str)
        .ok_or("no last_seen")?
        .parse::<chrono::DateTime<chrono::Utc>>()?;
    assert!(
        app.clock.now() - last_seen > chrono::TimeDelta::seconds(5),
        "{robot}"
    );
    Ok(())
}

#[tokio::test]
async fn assigned_task_returns_to_requested_when_robot_is_lost() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let nurse = app.nurse_token().await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let task = assign_one(&app, &mut robot, &nurse).await?;
    go_silent(&app, "robot-r2", None).await?;
    let body = wait_for_task(&app, &nurse, &task, WAIT, |b| {
        b.get("state") == Some(&json!("requested"))
    })
    .await?;
    assert_eq!(body.get("robot_id"), Some(&Value::Null));
    Ok(())
}

#[tokio::test]
async fn en_route_task_is_flagged_for_a_human_not_reassigned() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let nurse = app.nurse_token().await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let task = assign_one(&app, &mut robot, &nurse).await?;
    robot
        .send_json(&task_event(&task, "en_route", None, app.clock.now()))
        .await?;
    wait_for_task(&app, &nurse, &task, WAIT, |b| {
        b.get("state") == Some(&json!("en_route"))
    })
    .await?;
    let _second = app.connect_robot(&server, "robot-r3", 5.0, 4.0).await?;
    go_silent(&app, "robot-r2", None).await?;
    let body = wait_for_task(&app, &nurse, &task, WAIT, |b| {
        b.get("reason").is_some_and(|v| !v.is_null())
    })
    .await?;
    assert_ne!(body.get("state"), Some(&json!("requested")));
    assert_eq!(body.get("robot_id"), Some(&json!("robot-r2")));
    Ok(())
}

#[tokio::test]
async fn no_fitting_robot_leaves_task_requested_with_explanation() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 3).await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json("/tasks", Some(&nurse), &fetch_blanket())?)
        .await?;
    assert!(
        reply.status.is_success(),
        "{}: {}",
        reply.status,
        reply.body
    );
    assert_eq!(reply.body.get("state"), Some(&json!("requested")));
    let explanation = reply
        .body
        .get("reason")
        .and_then(Value::as_str)
        .unwrap_or_default();
    assert!(!explanation.is_empty(), "{}", reply.body);
    Ok(())
}

#[tokio::test]
async fn estop_reaches_robot_even_when_dispatcher_lock_is_held() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    let nurse = app.nurse_token().await?;
    app.set_stock("blanket", 3).await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let assignment = app
        .assignment
        .clone()
        .ok_or("the real wiring has no assignment service")?;
    let guard = assignment.dispatch_lock().await;
    let blocked = tokio::time::timeout(
        Duration::from_millis(300),
        app.call(post_json("/tasks", Some(&nurse), &fetch_blanket())?),
    )
    .await;
    assert!(
        blocked.is_err(),
        "task creation did not wait for the dispatch lock"
    );
    let reply = tokio::time::timeout(
        Duration::from_secs(1),
        app.call(post_json(
            "/robots/robot-r2/command",
            Some(&admin),
            &estop(),
        )?),
    )
    .await??;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("accepted"), Some(&json!(true)));
    let command = robot
        .next_of_type("command", Duration::from_secs(1))
        .await?;
    assert_eq!(command.get("name"), Some(&json!("estop")));
    drop(guard);
    Ok(())
}

#[tokio::test]
async fn estop_to_offline_robot_says_use_the_physical_button() -> TestResult {
    let app = RealApp::start().await?;
    app.add_robot("robot-r2", false).await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(post_json(
            "/robots/robot-r2/command",
            Some(&admin),
            &estop(),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(
        reply.error_message(),
        "Robot robot-r2 is offline: the stop was not delivered. Use the physical button."
    );
    Ok(())
}

#[tokio::test]
async fn nurse_cannot_send_estop() -> TestResult {
    let app = RealApp::start().await?;
    app.add_robot("robot-r2", false).await?;
    let nurse = app.user_token("u-nurse", Role::Nurse, "tab-nurse").await?;
    let reply = app
        .call(post_json(
            "/robots/robot-r2/command",
            Some(&nurse),
            &estop(),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("forbidden"));
    assert!(
        reply.error_message().contains("estop"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn slow_app_subscriber_gets_resync_and_does_not_block_others() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let mut slow = app.app_socket(&server).await?;
    let mut fast = app.app_socket(&server).await?;
    assert_eq!(
        slow.next_json(WAIT).await?.get("type"),
        Some(&json!("snapshot"))
    );
    assert_eq!(
        fast.next_json(WAIT).await?.get("type"),
        Some(&json!("snapshot"))
    );
    let reader = tokio::spawn(async move {
        loop {
            let message = fast.next_json(Duration::from_secs(10)).await?;
            if message.get("message") == Some(&json!("last")) {
                return Ok::<(), support::BoxError>(());
            }
        }
    });
    let padding = "x".repeat(2048);
    for _ in 0..3000 {
        app.hub.publish(AppEvent::Alert {
            level: AlertLevel::Warning,
            kind: AlertKind::StockMismatch,
            message: padding.clone(),
            command: None,
        });
        tokio::task::yield_now().await;
    }
    app.hub.publish(AppEvent::Alert {
        level: AlertLevel::Warning,
        kind: AlertKind::StockMismatch,
        message: "last".to_owned(),
        command: None,
    });
    reader.await??;
    let resync = slow.next_of_type("resync", Duration::from_secs(10)).await?;
    assert_eq!(resync.get("type"), Some(&json!("resync")));
    let after = slow.next_json(WAIT).await?;
    assert_eq!(after.get("type"), Some(&json!("snapshot")));
    Ok(())
}

#[tokio::test]
async fn reconnecting_robot_with_running_task_in_hello_is_reconciled() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let nurse = app.nurse_token().await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let task = assign_one(&app, &mut robot, &nurse).await?;
    robot.close().await?;
    // The server loses the robot and takes the task back: its state now diverges from the
    // robot's, which is still running the task.
    app.clock.advance(Duration::from_secs(6));
    wait_for_task(&app, &nurse, &task, WAIT, |b| {
        b.get("state") == Some(&json!("requested"))
    })
    .await?;

    let token = app.add_robot("robot-r2", false).await?;
    let mut again = connect(&server, "robot-r2", &token).await?;
    again
        .send_json(&hello("robot-r2", false, Some(&task), app.clock.now()))
        .await?;
    let body = wait_for_task(&app, &nurse, &task, WAIT, |b| {
        b.get("robot_id") == Some(&json!("robot-r2")) && b.get("state") != Some(&json!("requested"))
    })
    .await?;
    assert_eq!(body.get("state"), Some(&json!("assigned")));
    app.robot_barrier(&mut again, "robot-r2", 42.0).await?;
    let resent = again
        .next_of_type("task.assign", Duration::from_millis(500))
        .await;
    assert!(
        resent.is_err(),
        "the running task was assigned a second time"
    );
    Ok(())
}
