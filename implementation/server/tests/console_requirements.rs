//! Task A8: what the updated admin console needs from the server
//! (`implementation/admin/requirements/`): emergency mode, the tablet registry, monitoring
//! and blocking, service statistics, and the map items.
//!
//! The JSON examples of the requirement files are the console's test fixtures: each one is
//! copied here and compared key for key (and code for code) with what the server sends. The
//! tests against `--mock` run (the mock implements all of it in memory); the live-server
//! tests are ignored with their fill ids (E1, T7b, T8b, T11e).

mod support;

use std::collections::BTreeSet;
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4};
use std::time::Duration;

use axum::http::{Method, StatusCode};
use clinic_server::dto::{AssignTabletRequest, NewBlockRequest, SetModeRequest};
use clinic_server::error::EMERGENCY_MODE_MESSAGE;
use clinic_server::services::mock::HELD_LABEL;
use domain::{SystemMode, TaskState};
use realtime::{AlertLevel, AppEvent, TabletKind};
use serde_json::{Value, json};
use support::{
    LiveServer, MockApp, RealApp, Res, TestResult, WsClient, app_socket_with_token, call,
    call_from, get, post_json, put_json, request,
};
use tokio::sync::broadcast;

const ADMIN: Option<&str> = Some("mock-admin");
const NURSE: Option<&str> = Some("mock-nurse");

// ---------------------------------------------------------------------------------------
// The examples of the requirement files, verbatim.

const MODE_EMERGENCY: &str = r#"{"mode": "emergency", "since": "2026-11-15T09:12:00Z", "by": "Admin A", "reason": "Fire alarm, wing B"}"#;
const MODE_NORMAL: &str =
    r#"{"mode": "normal", "since": "2026-11-15T09:40:00Z", "by": "Admin A", "reason": null}"#;
const MODE_PUT: &str = r#"{"mode": "emergency", "reason": "Switched on from the admin console."}"#;
const MODE_UPDATED: &str = r#"{"type": "mode.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T09:12:00Z", "mode": {"mode": "emergency", "since": "2026-11-15T09:12:00Z", "by": "Admin A", "reason": "Fire alarm, wing B"}}"#;
const TABLET: &str = r#"{"device_id": "tab-bed-12", "kind": "bedside", "label": "Bed 12", "speciality": null, "battery_pct": 64, "online": true, "assigned": true, "place": "room-12", "floor": 2, "x": 20.9, "y": 4.1, "uncertainty_m": null, "last_seen": "2026-11-15T09:12:00Z"}"#;
const ASSIGN_STAFF: &str =
    r#"{"kind": "staff", "label": "Dr. C", "speciality": "Neurology", "place": null}"#;
const ASSIGN_BEDSIDE: &str =
    r#"{"kind": "bedside", "label": "Bed 12", "speciality": null, "place": "room-12"}"#;
const DEVICE_UPDATED: &str = r#"{"type": "device.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T09:12:00Z", "device": {"device_id": "tab-spare-1", "kind": "staff", "label": "", "speciality": null, "battery_pct": 100, "online": true, "assigned": false, "place": "nurse-station", "floor": 2, "x": 4.6, "y": 9.5, "uncertainty_m": null, "last_seen": "2026-11-15T09:12:00Z"}}"#;
const SUMMARY: &str = r#"{"started_at": "2026-11-15T06:00:00Z", "uptime_s": 10800, "version": "0.4.0", "robots_connected": 3, "robots_total": 4, "app_clients": 6, "journal_ok": true, "database_ok": true, "requests_per_s": 12.4, "rejected_per_s": 0.3, "p95_ms": 28, "blocked_clients": 1}"#;
const TRAFFIC: &str = r#"{"step_s": 1, "p95_ms": 31, "points": [{"at": "2026-11-15T09:00:00Z", "accepted": 11, "rejected": 0}, {"at": "2026-11-15T09:00:01Z", "accepted": 12, "rejected": 45}], "rejected_by": {"rate_limited": 45, "unauthorized": 2, "forbidden": 0, "blocked": 0, "emergency_mode": 0, "invalid": 0}}"#;
const CLIENTS: &str = r#"[{"ip": "203.0.113.42", "label": null, "requests_per_s": 84.2, "requests": 2410, "rejected": 2300, "login_failures": 0, "status": "blocked", "reason": "Over 20 requests/s for 5 s"},
 {"ip": "10.0.3.12", "label": "Robot R2", "requests_per_s": 1.2, "requests": 360, "rejected": 0, "login_failures": 0, "status": "ok", "reason": null}]"#;
const BLOCKS: &str = r#"[{"id": "blk-3", "target": "203.0.113.0/24", "reason": "Flooding the login page", "source": "manual", "created_at": "2026-11-15T09:02:00Z", "expires_at": null, "by": "Admin A", "hits": 120}]"#;
const BLOCK_POST: &str =
    r#"{"target": "203.0.113.0/24", "reason": "Flooding the login page", "expires_in_s": 3600}"#;
const SERVICE: &str = r#"{"hours": 24, "requests": 28, "delivered": 19, "failed": 5, "median_wait_s": 43, "p90_wait_s": 68, "by_item": [{"label": "Water bottle", "count": 4}], "by_place": [{"place": "room-13", "count": 6}], "bedside_online": 3, "bedside_total": 4}"#;
const SECURITY_ALERT: &str = r#"{"type": "security.alert", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T09:01:05Z", "alert": {"at": "2026-11-15T09:01:05Z", "kind": "auto_blocked", "ip": "203.0.113.42", "message": "203.0.113.42 blocked automatically for 10 min: over 20 requests/s for 5 s."}}"#;
const MAP_UPDATED: &str = r#"{"type": "map.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T08:00:00Z", "active": true, "clinic_id": "seed", "version": 2}"#;

// ---------------------------------------------------------------------------------------
// Helpers

fn doc(text: &str) -> Res<Value> {
    Ok(serde_json::from_str(text)?)
}

fn keys(value: &Value) -> BTreeSet<String> {
    value
        .as_object()
        .map(|object| object.keys().cloned().collect())
        .unwrap_or_default()
}

/// The same keys as `expected`, recursively through objects and the first item of arrays.
fn assert_same_shape(actual: &Value, expected: &Value, path: &str) {
    match (actual, expected) {
        (Value::Object(_), Value::Object(want)) => {
            assert_eq!(keys(actual), keys(expected), "keys of {path}: {actual}");
            for (key, value) in want {
                if let Some(got) = actual.get(key)
                    && !got.is_null()
                {
                    assert_same_shape(got, value, &format!("{path}.{key}"));
                }
            }
        }
        (Value::Array(got), Value::Array(want)) => {
            if let (Some(first), Some(model)) = (got.first(), want.first()) {
                assert_same_shape(first, model, &format!("{path}[0]"));
            }
        }
        _ => {}
    }
}

/// An address on no known network, as a client of the clinic network would be.
fn peer(a: u8, b: u8, c: u8, d: u8) -> SocketAddr {
    SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::new(a, b, c, d), 40_000))
}

fn encoded(event: AppEvent) -> Res<Value> {
    let envelope = realtime::Envelope::new(event, chrono::Utc::now());
    Ok(serde_json::from_str(&realtime::encode(&envelope)?)?)
}

/// The next published event matching `wanted` within 2 s.
async fn next_event(
    events: &mut broadcast::Receiver<AppEvent>,
    wanted: impl Fn(&AppEvent) -> bool,
) -> Res<AppEvent> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        match tokio::time::timeout(left, events.recv()).await? {
            Ok(event) if wanted(&event) => return Ok(event),
            Ok(_) | Err(broadcast::error::RecvError::Lagged(_)) => {}
            Err(error) => return Err(error.into()),
        }
    }
}

/// Waits until `robot` shows no task and `idle` (a state report the robot sent before it got
/// the server's commands may still say `busy` for a moment).
async fn wait_idle_without_task(app: &MockApp, robot: &str) -> TestResult {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    loop {
        let robots = call(&app.app, get("/robots", ADMIN)?).await?;
        let view = robots
            .body
            .as_array()
            .and_then(|list| list.iter().find(|r| r.get("id") == Some(&json!(robot))))
            .cloned()
            .ok_or("robot gone")?;
        assert_eq!(view.get("task_id"), Some(&Value::Null), "{view}");
        if view.get("state") == Some(&json!("idle")) {
            return Ok(());
        }
        if tokio::time::Instant::now() > deadline {
            return Err(format!("robot never idle at its dock: {view}").into());
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
}

/// How many audit rows have `action`.
async fn audit_rows(app: &MockApp, action: &str) -> Res<usize> {
    let audit = call(&app.app, get("/audit?limit=500", ADMIN)?).await?;
    Ok(audit
        .body
        .get("items")
        .and_then(Value::as_array)
        .map_or(0, |rows| {
            rows.iter()
                .filter(|row| row.get("action") == Some(&json!(action)))
                .count()
        }))
}

async fn set_mode(app: &MockApp, mode: &str) -> Res<support::Reply> {
    call(
        &app.app,
        put_json(
            "/system/mode",
            ADMIN,
            &json!({ "mode": mode, "reason": "drill" }),
        )?,
    )
    .await
}

// ---------------------------------------------------------------------------------------
// Emergency mode (emergency-mode.md)

#[tokio::test]
async fn system_mode_matches_the_documented_examples() -> TestResult {
    let app = MockApp::start()?;
    // Any signed-in user may read it.
    let reply = call(&app.app, get("/system/mode", NURSE)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_same_shape(&reply.body, &doc(MODE_NORMAL)?, "mode");
    assert_eq!(
        reply.body,
        json!({"mode": "normal", "since": null, "by": null, "reason": null})
    );
    let unsigned = call(&app.app, get("/system/mode", None)?).await?;
    assert_eq!(unsigned.status, StatusCode::UNAUTHORIZED);
    // The PUT body of the doc parses; the answer has the GET shape.
    let body: SetModeRequest = serde_json::from_str(MODE_PUT)?;
    assert_eq!(body.mode, SystemMode::Emergency);
    let reply = call(&app.app, put_json("/system/mode", ADMIN, &doc(MODE_PUT)?)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_same_shape(&reply.body, &doc(MODE_EMERGENCY)?, "mode");
    assert_eq!(reply.body.get("mode"), Some(&json!("emergency")));
    assert_eq!(reply.body.get("by"), Some(&json!("Admin (mock)")));
    // Idempotent: the same mode again changes nothing (same `since`).
    let again = call(&app.app, put_json("/system/mode", ADMIN, &doc(MODE_PUT)?)?).await?;
    assert_eq!(again.status, StatusCode::OK);
    assert_eq!(again.body.get("since"), reply.body.get("since"));
    Ok(())
}

#[tokio::test]
async fn put_mode_is_admin_only_and_checks_its_fields() -> TestResult {
    let app = MockApp::start()?;
    let nurse = call(
        &app.app,
        put_json("/system/mode", NURSE, &json!({ "mode": "emergency" }))?,
    )
    .await?;
    assert_eq!(nurse.status, StatusCode::FORBIDDEN);
    assert_eq!(nurse.error_code(), Some("forbidden"));
    for body in [
        json!({ "mode": "panic" }),
        json!({ "mode": "emergency", "reason": "x".repeat(201) }),
    ] {
        let reply = call(&app.app, put_json("/system/mode", ADMIN, &body)?).await?;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert_eq!(reply.error_code(), Some("invalid_field"), "{body}");
    }
    let mode = call(&app.app, get("/system/mode", ADMIN)?).await?;
    assert_eq!(mode.body.get("mode"), Some(&json!("normal")));
    Ok(())
}

#[tokio::test]
async fn emergency_serves_every_route_of_the_allow_list() -> TestResult {
    let app = MockApp::start()?;
    assert_eq!(set_mode(&app, "emergency").await?.status, StatusCode::OK);
    let allowed: [(Method, &str, Option<Value>); 19] = [
        (Method::GET, "/me", None),
        (Method::GET, "/system/mode", None),
        (Method::GET, "/robots", None),
        (Method::GET, "/map", None),
        (Method::GET, "/live", None),
        (Method::GET, "/zones", None),
        (Method::GET, "/tasks", None),
        (Method::GET, "/tasks/t-1", None),
        (Method::POST, "/tasks/t-1/cancel", Some(json!({}))),
        (Method::GET, "/incidents", None),
        (Method::POST, "/incidents/1/ack", Some(json!({}))),
        (Method::GET, "/monitor/summary", None),
        (Method::GET, "/monitor/traffic", None),
        (Method::GET, "/monitor/clients", None),
        (Method::GET, "/security/blocks", None),
        (Method::GET, "/devices", None),
        (
            Method::POST,
            "/devices/tab-spare-1/assign",
            Some(json!({"kind": "staff", "label": "Dr. Z", "speciality": null, "place": null})),
        ),
        (
            Method::POST,
            "/robots/r1/command",
            Some(json!({ "name": "pause" })),
        ),
        (Method::GET, "/health", None),
    ];
    for (method, path, body) in allowed {
        let reply = call(
            &app.app,
            request(method.clone(), path, ADMIN, body.as_ref())?,
        )
        .await?;
        assert_ne!(
            reply.status,
            StatusCode::SERVICE_UNAVAILABLE,
            "{method} {path} must stay allowed: {}",
            reply.body
        );
        assert!(
            reply.status.is_success(),
            "{method} {path}: {} {}",
            reply.status,
            reply.body
        );
    }
    let login = call(
        &app.app,
        post_json(
            "/auth/login",
            None,
            &json!({ "username": "nurse", "password": "mock" }),
        )?,
    )
    .await?;
    assert_eq!(
        login.status,
        StatusCode::OK,
        "people must still sign in: {}",
        login.body
    );
    Ok(())
}

#[tokio::test]
async fn emergency_refuses_the_rest_with_the_documented_message() -> TestResult {
    let app = MockApp::start()?;
    assert_eq!(set_mode(&app, "emergency").await?.status, StatusCode::OK);
    let refused: [(Method, &str, Option<Value>); 10] = [
        (
            Method::POST,
            "/tasks",
            Some(json!({ "kind": "fetch", "item": "blanket", "to_place": "room-12" })),
        ),
        (
            Method::POST,
            "/inventory/blanket/adjust",
            Some(json!({ "delta": 1, "reason": "restock" })),
        ),
        (
            Method::PUT,
            "/zones/z-new",
            Some(
                json!({ "name": "x", "floor": 2, "kind": "deaf", "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]] }),
            ),
        ),
        (Method::DELETE, "/zones/z-new", None),
        (
            Method::PUT,
            "/schedules/night-restock",
            Some(json!({ "enabled": false })),
        ),
        (Method::POST, "/clinics/seed/activate", Some(json!({}))),
        (
            Method::POST,
            "/brain/translate",
            Some(json!({ "text": "x", "from": "en", "to": "fr" })),
        ),
        (Method::GET, "/stats/heat?floor=2", None),
        (Method::GET, "/stats/service", None),
        (Method::GET, "/inventory", None),
    ];
    for (method, path, body) in refused {
        let reply = call(
            &app.app,
            request(method.clone(), path, ADMIN, body.as_ref())?,
        )
        .await?;
        assert_eq!(
            reply.status,
            StatusCode::SERVICE_UNAVAILABLE,
            "{method} {path}: {}",
            reply.body
        );
        assert_eq!(
            reply.error_code(),
            Some("emergency_mode"),
            "{method} {path}"
        );
        assert_eq!(reply.error_message(), EMERGENCY_MODE_MESSAGE);
    }
    assert_eq!(
        EMERGENCY_MODE_MESSAGE,
        "The clinic is in emergency mode: only emergency actions are accepted."
    );
    // Back to normal: new requests are accepted again.
    assert_eq!(set_mode(&app, "normal").await?.status, StatusCode::OK);
    let task = call(
        &app.app,
        post_json(
            "/tasks",
            ADMIN,
            &json!({ "kind": "fetch", "item": "blanket", "to_place": "room-12" }),
        )?,
    )
    .await?;
    assert!(task.status.is_success(), "{}", task.body);
    Ok(())
}

#[tokio::test]
async fn estop_and_robot_commands_stay_allowed_in_emergency() -> TestResult {
    let app = MockApp::start()?;
    assert_eq!(set_mode(&app, "emergency").await?.status, StatusCode::OK);
    for (robot, name) in [
        ("r1", "estop"),
        ("r2", "pause"),
        ("r2", "resume"),
        ("r3", "dock"),
    ] {
        let reply = call(
            &app.app,
            post_json(
                &format!("/robots/{robot}/command"),
                ADMIN,
                &json!({ "name": name }),
            )?,
        )
        .await?;
        assert_eq!(
            reply.status,
            StatusCode::OK,
            "{robot} {name}: {}",
            reply.body
        );
    }
    // A7's latch still applies: a nurse cannot lift the estop, even in emergency mode.
    let nurse = call(
        &app.app,
        post_json("/robots/r1/command", NURSE, &json!({ "name": "resume" }))?,
    )
    .await?;
    assert_eq!(nurse.error_code(), Some("estop_latched"));
    Ok(())
}

#[tokio::test]
async fn entering_emergency_holds_tasks_and_docks_robots_then_exit_dispatches_again() -> TestResult
{
    let app = MockApp::start()?;
    let mut events = app.hub.subscribe_apps();
    let created = call(
        &app.app,
        post_json(
            "/tasks",
            ADMIN,
            &json!({ "kind": "fetch", "item": "blanket", "to_place": "room-12" }),
        )?,
    )
    .await?;
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?
        .to_owned();
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    let holder = robots
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|robot| robot.get("task_id") == Some(&json!(id)))
        })
        .and_then(|robot| robot.get("id").and_then(Value::as_str))
        .ok_or("the task went to no robot")?
        .to_owned();
    let reply = set_mode(&app, "emergency").await?;
    assert_eq!(reply.status, StatusCode::OK);
    // mode.updated, then a critical alert.
    let updated = next_event(&mut events, |e| matches!(e, AppEvent::ModeUpdated { .. })).await?;
    assert_same_shape(&encoded(updated)?, &doc(MODE_UPDATED)?, "mode.updated");
    let alert = next_event(&mut events, |e| matches!(e, AppEvent::Alert { .. })).await?;
    assert!(
        matches!(
            alert,
            AppEvent::Alert {
                level: AlertLevel::Critical,
                ..
            }
        ),
        "{alert:?}"
    );
    // The task is back in the queue with the documented history line; the robot docks.
    let task = call(&app.app, get(&format!("/tasks/{id}"), ADMIN)?).await?;
    assert_eq!(
        task.body.get("state"),
        Some(&json!("requested")),
        "{}",
        task.body
    );
    assert_eq!(task.body.get("robot_id"), Some(&Value::Null));
    let last = task
        .body
        .get("history")
        .and_then(Value::as_array)
        .and_then(|history| history.last())
        .and_then(|entry| entry.get("label"))
        .cloned();
    assert_eq!(last, Some(json!(HELD_LABEL)));
    assert_eq!(HELD_LABEL, "held: emergency mode");
    // The robot drops the task and docks.
    wait_idle_without_task(&app, &holder).await?;
    // While on, nothing is handed out (the task stays requested).
    tokio::time::sleep(Duration::from_millis(300)).await;
    let task = call(&app.app, get(&format!("/tasks/{id}"), ADMIN)?).await?;
    assert_eq!(task.body.get("state"), Some(&json!("requested")));
    // Exit: info alert, the queue is handed out again.
    assert_eq!(set_mode(&app, "normal").await?.status, StatusCode::OK);
    let alert = next_event(&mut events, |e| {
        matches!(
            e,
            AppEvent::Alert {
                level: AlertLevel::Info,
                ..
            }
        )
    })
    .await?;
    assert!(matches!(alert, AppEvent::Alert { .. }));
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    let taken = robots.body.as_array().is_some_and(|list| {
        list.iter()
            .any(|robot| robot.get("task_id") == Some(&json!(id)))
    });
    assert!(taken, "the held task is dispatched again: {}", robots.body);
    // The switch is journaled.
    let switches = audit_rows(&app, "system_mode_changed").await?;
    assert_eq!(switches, 2);
    Ok(())
}

#[tokio::test]
async fn a_robot_holding_an_item_is_paused_and_only_it_is_resumed() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut robot =
        WsClient::connect_with_token(&server.ws_url("/ws/robot/robot-r2"), "mock-robot").await?;
    let now = chrono::Utc::now();
    robot
        .send_json(&support::hello("robot-r2", true, None, now))
        .await?;
    let mut state = support::robot_state(2, 3.0, 7.0, "busy", now);
    if let Some(holding) = state.get_mut("holding") {
        *holding = json!("blanket");
    }
    robot.send_json(&state).await?;
    // Wait until the server shows it holding the item.
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    loop {
        let robots = call(&app.app, get("/robots", ADMIN)?).await?;
        let holds = robots.body.as_array().is_some_and(|list| {
            list.iter().any(|r| {
                r.get("id") == Some(&json!("robot-r2"))
                    && r.get("holding") == Some(&json!("blanket"))
            })
        });
        if holds {
            break;
        }
        if tokio::time::Instant::now() > deadline {
            return Err("robot-r2 never showed its item".into());
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    assert_eq!(set_mode(&app, "emergency").await?.status, StatusCode::OK);
    let command = robot
        .next_of_type("command", Duration::from_secs(2))
        .await?;
    assert_eq!(command.get("name"), Some(&json!("pause")), "{command}");
    assert_eq!(set_mode(&app, "normal").await?.status, StatusCode::OK);
    let command = robot
        .next_of_type("command", Duration::from_secs(2))
        .await?;
    assert_eq!(command.get("name"), Some(&json!("resume")), "{command}");
    Ok(())
}

#[tokio::test]
async fn the_snapshot_carries_the_mode() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = app_socket_with_token(&server, "mock-nurse").await?;
    let snapshot = socket
        .next_of_type("snapshot", Duration::from_secs(3))
        .await?;
    let mode = snapshot.get("mode").ok_or("no mode in the snapshot")?;
    assert_same_shape(mode, &doc(MODE_NORMAL)?, "snapshot.mode");
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Tablets (tablets.md)

#[tokio::test]
async fn devices_list_every_tablet_with_the_documented_object() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/devices", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let tablets = reply.body.as_array().ok_or("not an array")?;
    assert!(tablets.len() >= 6, "{}", reply.body);
    let model = doc(TABLET)?;
    for tablet in tablets {
        assert_eq!(keys(tablet), keys(&model), "{tablet}");
        if tablet.get("kind") == Some(&json!("bedside")) {
            assert_eq!(tablet.get("speciality"), Some(&Value::Null), "{tablet}");
        }
    }
    let bed12 = tablets
        .iter()
        .find(|t| t.get("device_id") == Some(&json!("tab-bed-12")))
        .ok_or("no tab-bed-12")?;
    assert_eq!(bed12.get("label"), Some(&json!("Bed 12")));
    assert_eq!(bed12.get("place"), Some(&json!("room-12")));
    // Free and offline tablets are listed too.
    assert!(
        tablets
            .iter()
            .any(|t| t.get("assigned") == Some(&json!(false)))
    );
    assert!(
        tablets
            .iter()
            .any(|t| t.get("online") == Some(&json!(false)))
    );
    let text = reply.body.to_string();
    for forbidden in ["patient", "diagnosis", "issue"] {
        assert!(!text.contains(forbidden), "{forbidden} in {text}");
    }
    let nurse = call(&app.app, get("/devices", NURSE)?).await?;
    assert_eq!(nurse.status, StatusCode::FORBIDDEN);
    Ok(())
}

#[tokio::test]
async fn freeing_a_tablet_revokes_its_session_and_publishes_device_updated() -> TestResult {
    let app = MockApp::start()?;
    let mut events = app.hub.subscribe_apps();
    let token = Some("mock-tablet-tab-dr-a");
    assert_eq!(
        call(&app.app, get("/me", token)?).await?.status,
        StatusCode::OK
    );
    let unknown = call(
        &app.app,
        post_json("/devices/tab-nope/disconnect", ADMIN, &json!({}))?,
    )
    .await?;
    assert_eq!(unknown.status, StatusCode::NOT_FOUND);
    assert_eq!(unknown.error_code(), Some("not_found"));
    let free = call(
        &app.app,
        post_json("/devices/tab-spare-1/disconnect", ADMIN, &json!({}))?,
    )
    .await?;
    assert_eq!(free.status, StatusCode::CONFLICT);
    assert_eq!(free.error_code(), Some("already_free"));
    let reply = call(
        &app.app,
        post_json("/devices/tab-dr-a/disconnect", ADMIN, &json!({}))?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_same_shape(&reply.body, &doc(TABLET)?, "tablet");
    assert_eq!(reply.body.get("assigned"), Some(&json!(false)));
    assert_eq!(reply.body.get("label"), Some(&json!("")));
    assert_eq!(reply.body.get("speciality"), Some(&Value::Null));
    assert_eq!(
        reply.body.get("place"),
        Some(&json!("nurse-station")),
        "back on its shelf"
    );
    // Signed out at once.
    assert_eq!(
        call(&app.app, get("/me", token)?).await?.status,
        StatusCode::UNAUTHORIZED
    );
    let event = next_event(&mut events, |e| matches!(e, AppEvent::DeviceUpdated { .. })).await?;
    assert_same_shape(&encoded(event)?, &doc(DEVICE_UPDATED)?, "device.updated");
    // Journaled without the label.
    let audit = call(&app.app, get("/audit?limit=500", ADMIN)?).await?;
    let row = audit
        .body
        .get("items")
        .and_then(Value::as_array)
        .and_then(|rows| {
            rows.iter()
                .find(|row| row.get("action") == Some(&json!("device_freed")))
        })
        .cloned()
        .ok_or("no device_freed row")?;
    assert!(!row.to_string().contains("Dr. A"), "{row}");
    Ok(())
}

#[tokio::test]
async fn assigning_a_tablet_follows_the_documented_codes() -> TestResult {
    let app = MockApp::start()?;
    let staff: AssignTabletRequest = serde_json::from_str(ASSIGN_STAFF)?;
    assert_eq!(staff.kind, TabletKind::Staff);
    let bedside: AssignTabletRequest = serde_json::from_str(ASSIGN_BEDSIDE)?;
    assert_eq!(bedside.kind, TabletKind::Bedside);
    let assign = |id: &str| format!("/devices/{id}/assign");
    let unknown = call(
        &app.app,
        post_json(&assign("tab-nope"), ADMIN, &doc(ASSIGN_STAFF)?)?,
    )
    .await?;
    assert_eq!(
        (unknown.status, unknown.error_code()),
        (StatusCode::NOT_FOUND, Some("not_found"))
    );
    let in_use = call(
        &app.app,
        post_json(&assign("tab-dr-a"), ADMIN, &doc(ASSIGN_STAFF)?)?,
    )
    .await?;
    assert_eq!(
        (in_use.status, in_use.error_code()),
        (StatusCode::CONFLICT, Some("in_use"))
    );
    // An offline tablet: free tab-bed-14 (offline), then try to hand it out.
    let freed = call(
        &app.app,
        post_json("/devices/tab-bed-14/disconnect", ADMIN, &json!({}))?,
    )
    .await?;
    assert_eq!(freed.status, StatusCode::OK, "{}", freed.body);
    let offline = call(
        &app.app,
        post_json(&assign("tab-bed-14"), ADMIN, &doc(ASSIGN_BEDSIDE)?)?,
    )
    .await?;
    assert_eq!(
        (offline.status, offline.error_code()),
        (StatusCode::CONFLICT, Some("offline"))
    );
    for body in [
        json!({"kind": "staff", "label": "", "speciality": null, "place": null}),
        json!({"kind": "staff", "label": "12345", "speciality": null, "place": null}),
        json!({"kind": "staff", "label": "x".repeat(41), "speciality": null, "place": null}),
        json!({"kind": "bedside", "label": "Bed 12", "speciality": null, "place": null}),
        json!({"kind": "bedside", "label": "Bed 12", "speciality": null, "place": "supply-a"}),
        json!({"kind": "bedside", "label": "Bed 12", "speciality": "Cardiology", "place": "room-12"}),
        json!({"kind": "bedside", "label": "Anna Example", "speciality": null, "place": "room-12"}),
        json!({"kind": "bedside", "label": "Mrs Smith 12", "speciality": null, "place": "room-12"}),
    ] {
        let reply = call(&app.app, post_json(&assign("tab-spare-2"), ADMIN, &body)?).await?;
        assert_eq!(
            reply.status,
            StatusCode::UNPROCESSABLE_ENTITY,
            "{body}: {}",
            reply.body
        );
        assert_eq!(reply.error_code(), Some("invalid_field"), "{body}");
    }
    let bed = call(
        &app.app,
        post_json(&assign("tab-spare-2"), ADMIN, &doc(ASSIGN_BEDSIDE)?)?,
    )
    .await?;
    assert_eq!(bed.status, StatusCode::OK, "{}", bed.body);
    assert_same_shape(&bed.body, &doc(TABLET)?, "tablet");
    assert_eq!(bed.body.get("label"), Some(&json!("Bed 12")));
    assert_eq!(bed.body.get("place"), Some(&json!("room-12")));
    assert_eq!(bed.body.get("speciality"), Some(&Value::Null));
    let dr = call(
        &app.app,
        post_json(&assign("tab-spare-1"), ADMIN, &doc(ASSIGN_STAFF)?)?,
    )
    .await?;
    assert_eq!(dr.status, StatusCode::OK, "{}", dr.body);
    assert_eq!(dr.body.get("speciality"), Some(&json!("Neurology")));
    // The tablet's next login is bound to the assignment.
    let me = call(&app.app, get("/me", Some("mock-tablet-tab-spare-1"))?).await?;
    assert_eq!(me.status, StatusCode::OK, "{}", me.body);
    assert_eq!(me.body.get("device_id"), Some(&json!("tab-spare-1")));
    assert_eq!(me.body.get("owner_label"), Some(&json!("Dr. C")));
    Ok(())
}

#[tokio::test]
async fn live_lists_the_tablets_in_use_from_the_registry() -> TestResult {
    let app = MockApp::start()?;
    let live = call(&app.app, get("/live", ADMIN)?).await?;
    let tablets = live
        .body
        .get("tablets")
        .and_then(Value::as_array)
        .ok_or("no tablets")?;
    assert!(
        tablets
            .iter()
            .any(|t| t.get("device_id") == Some(&json!("tab-dr-a"))),
        "{}",
        live.body
    );
    assert!(
        !tablets
            .iter()
            .any(|t| t.get("device_id") == Some(&json!("tab-spare-1"))),
        "a free tablet has no owner"
    );
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Monitoring and blocking (monitoring-security.md)

#[tokio::test]
async fn monitor_summary_traffic_and_clients_match_the_examples() -> TestResult {
    let app = MockApp::start()?;
    let visitor = peer(203, 0, 113, 77);
    for _ in 0..5 {
        call_from(&app.app, visitor, get("/health", None)?).await?;
    }
    call_from(&app.app, visitor, get("/robots", None)?).await?;
    let summary = call(&app.app, get("/monitor/summary", ADMIN)?).await?;
    assert_eq!(summary.status, StatusCode::OK, "{}", summary.body);
    assert_eq!(keys(&summary.body), keys(&doc(SUMMARY)?));
    assert_eq!(
        summary.body.get("journal_ok"),
        Some(&Value::Null),
        "not checked in mock mode"
    );
    assert_eq!(summary.body.get("database_ok"), Some(&Value::Null));
    let traffic = call(&app.app, get("/monitor/traffic?window_s=300", ADMIN)?).await?;
    assert_eq!(traffic.status, StatusCode::OK);
    assert_same_shape(&traffic.body, &doc(TRAFFIC)?, "traffic");
    assert_eq!(
        traffic
            .body
            .get("points")
            .and_then(Value::as_array)
            .map(Vec::len),
        Some(300)
    );
    assert_eq!(
        traffic.body.pointer("/rejected_by/unauthorized"),
        Some(&json!(1)),
        "{}",
        traffic.body
    );
    for bad in ["0", "301"] {
        let reply = call(
            &app.app,
            get(&format!("/monitor/traffic?window_s={bad}"), ADMIN)?,
        )
        .await?;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    }
    let clients = call(&app.app, get("/monitor/clients?limit=20", ADMIN)?).await?;
    assert_eq!(clients.status, StatusCode::OK);
    assert_same_shape(&clients.body, &doc(CLIENTS)?, "clients");
    let entry = clients
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|c| c.get("ip") == Some(&json!("203.0.113.77")))
        })
        .ok_or("the visitor is not listed")?;
    assert_eq!(entry.get("requests"), Some(&json!(6)));
    assert_eq!(entry.get("rejected"), Some(&json!(1)));
    assert_eq!(entry.get("label"), Some(&Value::Null));
    assert_eq!(entry.get("status"), Some(&json!("ok")));
    // Never a user name.
    assert!(
        !clients.body.to_string().contains("(mock)"),
        "{}",
        clients.body
    );
    let nurse = call(&app.app, get("/monitor/summary", NURSE)?).await?;
    assert_eq!(nurse.status, StatusCode::FORBIDDEN);
    Ok(())
}

#[tokio::test]
async fn a_flood_gets_429_then_an_automatic_block_and_alerts() -> TestResult {
    let app = MockApp::start()?;
    let mut events = app.hub.subscribe_apps();
    let attacker = peer(203, 0, 113, 42);
    for _ in 0..40 {
        let reply = call_from(&app.app, attacker, get("/health", None)?).await?;
        assert_eq!(reply.status, StatusCode::OK);
    }
    let limited = call_from(&app.app, attacker, get("/health", None)?).await?;
    assert_eq!(limited.status, StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(limited.error_code(), Some("rate_limited"));
    assert!(limited.header("retry-after").is_some());
    let alert = next_event(&mut events, |e| matches!(e, AppEvent::SecurityAlert { .. })).await?;
    let alert = encoded(alert)?;
    assert_eq!(alert.pointer("/alert/kind"), Some(&json!("rate_limited")));
    // Over the limit in 5 seconds in a row: blocked for 10 minutes.
    let mut last = limited.status;
    for _ in 0..4 {
        app.clock.advance(Duration::from_secs(1));
        for _ in 0..25 {
            last = call_from(&app.app, attacker, get("/health", None)?)
                .await?
                .status;
        }
    }
    assert_eq!(last, StatusCode::FORBIDDEN);
    let blocked = call_from(&app.app, attacker, get("/health", None)?).await?;
    assert_eq!(blocked.error_code(), Some("blocked"));
    assert_eq!(keys(&blocked.body), keys(&json!({"error": 0})));
    let alert = next_event(&mut events, |e| {
        matches!(e, AppEvent::SecurityAlert { alert } if alert.kind == domain::SecurityAlertKind::AutoBlocked)
    })
    .await?;
    assert_same_shape(&encoded(alert)?, &doc(SECURITY_ALERT)?, "security.alert");
    let blocks = call(&app.app, get("/security/blocks", ADMIN)?).await?;
    assert_same_shape(&blocks.body, &doc(BLOCKS)?, "blocks");
    let rule = blocks
        .body
        .as_array()
        .and_then(|list| list.first())
        .ok_or("no rule")?;
    assert_eq!(rule.get("source"), Some(&json!("auto")));
    assert_eq!(rule.get("target"), Some(&json!("203.0.113.42")));
    assert_eq!(rule.get("by"), Some(&Value::Null));
    let clients = call(&app.app, get("/monitor/clients", ADMIN)?).await?;
    let entry = clients
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|c| c.get("ip") == Some(&json!("203.0.113.42")))
        })
        .ok_or("attacker not listed")?;
    assert_eq!(entry.get("status"), Some(&json!("blocked")));
    let summary = call(&app.app, get("/monitor/summary", ADMIN)?).await?;
    assert_eq!(summary.body.get("blocked_clients"), Some(&json!(1)));
    // The automatic block is journaled.
    let audit = call(&app.app, get("/audit?limit=500", ADMIN)?).await?;
    assert!(
        audit.body.to_string().contains("client_blocked"),
        "{}",
        audit.body
    );
    Ok(())
}

#[tokio::test]
async fn ten_failed_logins_block_the_address() -> TestResult {
    let app = MockApp::start()?;
    let guesser = peer(198, 51, 100, 23);
    for _ in 0..10 {
        let reply = call_from(
            &app.app,
            guesser,
            post_json(
                "/auth/login",
                None,
                &json!({ "account_key": "0".repeat(64) }),
            )?,
        )
        .await?;
        assert_eq!(reply.status, StatusCode::UNAUTHORIZED);
    }
    let next = call_from(&app.app, guesser, get("/health", None)?).await?;
    assert_eq!(next.status, StatusCode::FORBIDDEN);
    assert_eq!(next.error_code(), Some("blocked"));
    let blocks = call(&app.app, get("/security/blocks", ADMIN)?).await?;
    assert!(
        blocks.body.to_string().contains("failed sign-ins"),
        "{}",
        blocks.body
    );
    Ok(())
}

#[tokio::test]
async fn manual_blocks_follow_the_documented_codes() -> TestResult {
    let app = MockApp::start()?;
    let body: NewBlockRequest = serde_json::from_str(BLOCK_POST)?;
    assert_eq!(body.expires_in_s, Some(3600));
    let created = call(
        &app.app,
        post_json("/security/blocks", ADMIN, &doc(BLOCK_POST)?)?,
    )
    .await?;
    assert_eq!(created.status, StatusCode::CREATED, "{}", created.body);
    assert_same_shape(
        &created.body,
        &doc(BLOCKS)?.get(0).cloned().ok_or("doc")?,
        "rule",
    );
    assert_eq!(created.body.get("source"), Some(&json!("manual")));
    assert_eq!(created.body.get("by"), Some(&json!("Admin (mock)")));
    assert!(
        created
            .body
            .get("expires_at")
            .is_some_and(|at| !at.is_null())
    );
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?
        .to_owned();
    // Takes effect at once, with no detail for the client.
    let refused = call_from(&app.app, peer(203, 0, 113, 9), get("/health", None)?).await?;
    assert_eq!(refused.status, StatusCode::FORBIDDEN);
    assert_eq!(refused.error_code(), Some("blocked"));
    assert!(!refused.error_message().contains("Flooding"));
    let listed = call(&app.app, get("/security/blocks", ADMIN)?).await?;
    let hits = listed
        .body
        .as_array()
        .and_then(|list| list.iter().find(|rule| rule.get("id") == Some(&json!(id))))
        .and_then(|rule| rule.get("hits"))
        .cloned();
    assert_eq!(hits, Some(json!(1)));
    // Remove: 204, then 404.
    let path = format!("/security/blocks/{id}");
    let removed = call(&app.app, request(Method::DELETE, &path, ADMIN, None)?).await?;
    assert_eq!(removed.status, StatusCode::NO_CONTENT);
    let again = call(&app.app, request(Method::DELETE, &path, ADMIN, None)?).await?;
    assert_eq!(
        (again.status, again.error_code()),
        (StatusCode::NOT_FOUND, Some("not_found"))
    );
    let back = call_from(&app.app, peer(203, 0, 113, 9), get("/health", None)?).await?;
    assert_eq!(back.status, StatusCode::OK);
    assert_eq!(audit_rows(&app, "client_blocked").await?, 1);
    assert_eq!(audit_rows(&app, "client_unblocked").await?, 1);
    Ok(())
}

#[tokio::test]
async fn manual_block_refusals_follow_the_documented_codes() -> TestResult {
    let app = MockApp::start()?;
    // The documented refusals.
    let admin_away = peer(198, 51, 100, 7);
    let cases = [
        (json!({"target": "nope", "reason": "x"}), "invalid_field"),
        (
            json!({"target": "203.0.113.5", "reason": ""}),
            "invalid_field",
        ),
        (
            json!({"target": "203.0.113.5", "reason": "x".repeat(201)}),
            "invalid_field",
        ),
        (
            json!({"target": "127.0.0.1", "reason": "x"}),
            "protected_target",
        ),
        (json!({"target": "::1", "reason": "x"}), "protected_target"),
        (
            json!({"target": "198.51.100.0/24", "reason": "x"}),
            "protected_target",
        ),
        (
            json!({"target": "0.0.0.0/0", "reason": "x"}),
            "range_too_broad",
        ),
        (
            json!({"target": "10.0.0.0/8", "reason": "x"}),
            "range_too_broad",
        ),
        (
            json!({"target": "2001:db8::/32", "reason": "x"}),
            "range_too_broad",
        ),
    ];
    for (body, code) in cases {
        let reply = call_from(
            &app.app,
            admin_away,
            post_json("/security/blocks", ADMIN, &body)?,
        )
        .await?;
        assert_eq!(
            reply.status,
            StatusCode::UNPROCESSABLE_ENTITY,
            "{body}: {}",
            reply.body
        );
        assert_eq!(reply.error_code(), Some(code), "{body}: {}", reply.body);
    }
    let nurse = call(
        &app.app,
        post_json("/security/blocks", NURSE, &doc(BLOCK_POST)?)?,
    )
    .await?;
    assert_eq!(nurse.status, StatusCode::FORBIDDEN);
    let blocks = call(&app.app, get("/security/blocks", ADMIN)?).await?;
    assert_eq!(blocks.body, json!([]), "nothing was blocked");
    Ok(())
}

#[tokio::test]
async fn an_admins_robot_command_is_never_refused_by_blocks_limits_or_mode() -> TestResult {
    let app = MockApp::start()?;
    // The admin works from 203.0.113.50; another admin (loopback) blocks the whole range.
    let admin_desk = peer(203, 0, 113, 50);
    let block = call(
        &app.app,
        post_json(
            "/security/blocks",
            ADMIN,
            &json!({"target": "203.0.113.0/24", "reason": "attack"}),
        )?,
    )
    .await?;
    assert_eq!(block.status, StatusCode::CREATED, "{}", block.body);
    assert_eq!(set_mode(&app, "emergency").await?.status, StatusCode::OK);
    // Flood from the admin's own address too.
    for _ in 0..100 {
        call_from(&app.app, admin_desk, get("/robots", ADMIN)?).await?;
    }
    for (robot, name) in [("r2", "pause"), ("r2", "resume"), ("r1", "estop")] {
        let reply = call_from(
            &app.app,
            admin_desk,
            post_json(
                &format!("/robots/{robot}/command"),
                ADMIN,
                &json!({ "name": name }),
            )?,
        )
        .await?;
        assert_eq!(
            reply.status,
            StatusCode::OK,
            "{robot} {name}: {}",
            reply.body
        );
    }
    for (method, path) in [
        (Method::GET, "/system/mode"),
        (Method::GET, "/monitor/summary"),
        (Method::GET, "/security/blocks"),
    ] {
        let reply = call_from(&app.app, admin_desk, request(method, path, ADMIN, None)?).await?;
        assert_eq!(reply.status, StatusCode::OK, "{path}: {}", reply.body);
    }
    let leave = call_from(
        &app.app,
        admin_desk,
        put_json("/system/mode", ADMIN, &json!({ "mode": "normal" }))?,
    )
    .await?;
    assert_eq!(leave.status, StatusCode::OK);
    // Other routes from the blocked address are refused, and anyone else's command too.
    let other = call_from(&app.app, admin_desk, get("/robots", ADMIN)?).await?;
    assert_eq!(other.error_code(), Some("blocked"));
    let nurse = call_from(
        &app.app,
        admin_desk,
        post_json("/robots/r2/command", NURSE, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(nurse.error_code(), Some("blocked"));
    let forged = call_from(
        &app.app,
        admin_desk,
        post_json(
            "/robots/r2/command",
            Some("mock-pirate"),
            &json!({ "name": "pause" }),
        )?,
    )
    .await?;
    // R26: a forged token from a blocked address gets the block, not a 401.
    assert_eq!(forged.status, StatusCode::FORBIDDEN, "{}", forged.body);
    assert_eq!(forged.error_code(), Some("blocked"));
    Ok(())
}

#[tokio::test]
async fn invalid_tokens_on_exempt_routes_end_in_a_block_not_endless_401() -> TestResult {
    let app = MockApp::start()?;
    let guesser = peer(203, 0, 113, 99);
    let mut statuses = Vec::new();
    for n in 0..50 {
        let token = format!("guess-{n}");
        let reply = call_from(
            &app.app,
            guesser,
            post_json(
                "/robots/r1/command",
                Some(&token),
                &json!({ "name": "estop" }),
            )?,
        )
        .await?;
        statuses.push(reply.status);
    }
    assert!(
        statuses.iter().all(|status| *status != StatusCode::OK),
        "{statuses:?}"
    );
    let unauthorized = statuses
        .iter()
        .filter(|status| **status == StatusCode::UNAUTHORIZED)
        .count();
    assert!(
        unauthorized <= 10,
        "{unauthorized} answers were 401: {statuses:?}"
    );
    assert!(
        statuses
            .last()
            .is_some_and(|status| *status == StatusCode::FORBIDDEN
                || *status == StatusCode::TOO_MANY_REQUESTS),
        "{statuses:?}"
    );
    // A real admin elsewhere in the now blocked range still sends the estop.
    let blocks = call(&app.app, get("/security/blocks", ADMIN)?).await?;
    assert!(
        blocks.body.to_string().contains("203.0.113.99"),
        "{}",
        blocks.body
    );
    let range = call(
        &app.app,
        post_json(
            "/security/blocks",
            ADMIN,
            &json!({"target": "203.0.113.0/24", "reason": "token guessing"}),
        )?,
    )
    .await?;
    assert_eq!(range.status, StatusCode::CREATED, "{}", range.body);
    let admin = call_from(
        &app.app,
        peer(203, 0, 113, 50),
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert_eq!(admin.status, StatusCode::OK, "{}", admin.body);
    Ok(())
}

/// One estop with `token` from `from`.
async fn estop_from(app: &MockApp, from: SocketAddr, token: &str) -> Res<support::Reply> {
    call_from(
        &app.app,
        from,
        post_json(
            "/robots/r1/command",
            Some(token),
            &json!({ "name": "estop" }),
        )?,
    )
    .await
}

#[tokio::test]
async fn an_admin_on_a_guessing_address_still_sends_the_estop() -> TestResult {
    let app = MockApp::start()?;
    // A guesser and an admin behind the same address (a shared ward Wi-Fi gateway).
    let shared = peer(203, 0, 113, 98);
    for n in 0..15 {
        estop_from(&app, shared, &format!("guess-{n}")).await?;
    }
    let admin = estop_from(&app, shared, "mock-admin").await?;
    assert_eq!(admin.status, StatusCode::OK, "{}", admin.body);
    for n in 15..20 {
        let guess = estop_from(&app, shared, &format!("guess-{n}")).await?;
        assert!(
            guess.status == StatusCode::FORBIDDEN || guess.status == StatusCode::TOO_MANY_REQUESTS,
            "{}: {}",
            guess.status,
            guess.body
        );
    }
    Ok(())
}

#[tokio::test]
async fn continued_guessing_keeps_the_address_blocked_across_block_lifetimes() -> TestResult {
    let app = MockApp::start()?;
    let shared = peer(203, 0, 113, 97);
    for n in 0..10 {
        estop_from(&app, shared, &format!("guess-{n}")).await?;
    }
    // Two block lifetimes (2 x 10 min) of guesses every 30 s: the address never comes free.
    for n in 0..44 {
        app.clock.advance(Duration::from_secs(30));
        let guess = estop_from(&app, shared, &format!("late-{n}")).await?;
        assert_ne!(
            guess.status,
            StatusCode::UNAUTHORIZED,
            "guess {n}: {}",
            guess.body
        );
        let other = call_from(&app.app, shared, get("/health", None)?).await?;
        assert_eq!(other.error_code(), Some("blocked"), "after guess {n}");
    }
    let admin = estop_from(&app, shared, "mock-admin").await?;
    assert_eq!(admin.status, StatusCode::OK, "{}", admin.body);
    Ok(())
}

#[tokio::test]
async fn a_revoked_tablet_polling_does_not_block_a_shared_address() -> TestResult {
    let app = MockApp::start()?;
    let ward = peer(10, 0, 2, 40);
    // tab-spare-1 is free: its old token is refused on every poll.
    for _ in 0..30 {
        let reply = call_from(
            &app.app,
            ward,
            put_json(
                "/me/location",
                Some("mock-tablet-tab-spare-1"),
                &json!({ "place": "room-12" }),
            )?,
        )
        .await?;
        assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{}", reply.body);
    }
    let other = call_from(&app.app, ward, get("/health", None)?).await?;
    assert_eq!(other.status, StatusCode::OK, "{}", other.body);
    Ok(())
}

#[tokio::test]
async fn a_robot_token_marks_no_address_but_a_robot_may_reconnect_through_a_block() -> TestResult {
    let app = MockApp::start()?;
    // A robot token on an ordinary route does not make its address protected (R26).
    let robot_call = call_from(
        &app.app,
        peer(10, 0, 3, 12),
        get("/tasks", Some("mock-robot-r1"))?,
    )
    .await?;
    assert_eq!(robot_call.status, StatusCode::OK, "{}", robot_call.body);
    let block = call(
        &app.app,
        post_json(
            "/security/blocks",
            ADMIN,
            &json!({"target": "10.0.3.0/24", "reason": "x"}),
        )?,
    )
    .await?;
    assert_eq!(block.status, StatusCode::CREATED, "{}", block.body);
    let upgrade = |token: &str| -> Res<axum::http::Request<axum::body::Body>> {
        Ok(axum::http::Request::builder()
            .method(Method::GET)
            .uri("/ws/robot/r1")
            .header("authorization", format!("Bearer {token}"))
            .header("connection", "upgrade")
            .header("upgrade", "websocket")
            .header("sec-websocket-version", "13")
            .header("sec-websocket-key", "dGhlIHNhbXBsZSBub25jZQ==")
            .body(axum::body::Body::empty())?)
    };
    // The robot itself passes the block on its own socket (the oneshot call cannot really
    // upgrade, so any answer but `blocked` is a pass).
    let robot = call_from(&app.app, peer(10, 0, 3, 12), upgrade("mock-robot-r1")?).await?;
    assert_ne!(robot.error_code(), Some("blocked"), "{}", robot.body);
    // Another robot's token, or a nurse's, does not.
    for token in ["mock-robot-r2", "mock-nurse"] {
        let other = call_from(&app.app, peer(10, 0, 3, 12), upgrade(token)?).await?;
        assert_eq!(
            other.error_code(),
            Some("blocked"),
            "{token}: {}",
            other.body
        );
    }
    Ok(())
}

#[tokio::test]
async fn a_staff_paused_robot_holding_an_item_stays_paused_through_emergency() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut robot =
        WsClient::connect_with_token(&server.ws_url("/ws/robot/robot-r2"), "mock-robot").await?;
    let now = chrono::Utc::now();
    robot
        .send_json(&support::hello("robot-r2", true, None, now))
        .await?;
    let mut state = support::robot_state(2, 3.0, 7.0, "busy", now);
    if let Some(holding) = state.get_mut("holding") {
        *holding = json!("blanket");
    }
    robot.send_json(&state).await?;
    tokio::time::sleep(Duration::from_millis(300)).await;
    let paused = call(
        &app.app,
        post_json(
            "/robots/robot-r2/command",
            NURSE,
            &json!({ "name": "pause" }),
        )?,
    )
    .await?;
    assert_eq!(paused.status, StatusCode::OK, "{}", paused.body);
    let command = robot
        .next_of_type("command", Duration::from_secs(2))
        .await?;
    assert_eq!(command.get("name"), Some(&json!("pause")));
    assert_eq!(set_mode(&app, "emergency").await?.status, StatusCode::OK);
    assert!(
        robot
            .next_of_type("command", Duration::from_millis(500))
            .await
            .is_err(),
        "an already paused robot is neither re-paused nor remembered"
    );
    assert_eq!(set_mode(&app, "normal").await?.status, StatusCode::OK);
    assert!(
        robot
            .next_of_type("command", Duration::from_millis(500))
            .await
            .is_err(),
        "the server never resumes a staff pause"
    );
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    let view = robots
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|r| r.get("id") == Some(&json!("robot-r2")))
        })
        .cloned()
        .ok_or("robot-r2 gone")?;
    assert_eq!(view.get("state"), Some(&json!("paused")), "{view}");
    Ok(())
}

#[tokio::test]
async fn admin_reasons_are_cleaned_of_control_and_bidi_characters() -> TestResult {
    let app = MockApp::start()?;
    let mode = call(
        &app.app,
        put_json(
            "/system/mode",
            ADMIN,
            &json!({ "mode": "emergency", "reason": "Fire\u{202E}alarm\u{0007} wing B" }),
        )?,
    )
    .await?;
    assert_eq!(mode.body.get("reason"), Some(&json!("Firealarm wing B")));
    let block = call(
        &app.app,
        post_json(
            "/security/blocks",
            ADMIN,
            &json!({"target": "203.0.113.7", "reason": "\u{2066}Flood\u{2069}"}),
        )?,
    )
    .await?;
    assert_eq!(
        block.body.get("reason"),
        Some(&json!("Flood")),
        "{}",
        block.body
    );
    Ok(())
}

#[tokio::test]
async fn a_blocked_address_cannot_open_a_websocket() -> TestResult {
    let app = MockApp::start()?;
    let block = call(
        &app.app,
        post_json(
            "/security/blocks",
            ADMIN,
            &json!({"target": "203.0.113.66", "reason": "x"}),
        )?,
    )
    .await?;
    assert_eq!(block.status, StatusCode::CREATED);
    let upgrade = axum::http::Request::builder()
        .method(Method::GET)
        .uri("/ws")
        .header("origin", support::ADMIN_ORIGIN)
        .header("connection", "upgrade")
        .header("upgrade", "websocket")
        .header("sec-websocket-version", "13")
        .header("sec-websocket-key", "dGhlIHNhbXBsZSBub25jZQ==")
        .body(axum::body::Body::empty())?;
    let reply = call_from(&app.app, peer(203, 0, 113, 66), upgrade).await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("blocked"));
    Ok(())
}

#[tokio::test]
async fn security_alerts_reach_admin_sockets_only() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut admin = app_socket_with_token(&server, "mock-admin").await?;
    let mut nurse = app_socket_with_token(&server, "mock-nurse").await?;
    admin
        .next_of_type("snapshot", Duration::from_secs(3))
        .await?;
    nurse
        .next_of_type("snapshot", Duration::from_secs(3))
        .await?;
    let block = call(
        &app.app,
        post_json(
            "/security/blocks",
            ADMIN,
            &json!({"target": "203.0.113.0/24", "reason": "attack"}),
        )?,
    )
    .await?;
    assert_eq!(block.status, StatusCode::CREATED);
    let alert = admin
        .next_of_type("security.alert", Duration::from_secs(2))
        .await?;
    assert_eq!(alert.pointer("/alert/kind"), Some(&json!("blocked")));
    assert!(
        nurse
            .next_of_type("security.alert", Duration::from_millis(800))
            .await
            .is_err(),
        "a nurse socket must never get security.alert"
    );
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Service statistics

#[tokio::test]
async fn service_stats_are_counts_only_with_the_documented_keys() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/stats/service?hours=24", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_same_shape(&reply.body, &doc(SERVICE)?, "service");
    // The mock's invented tasks: four requests, one delivered after 7 minutes.
    assert_eq!(reply.body.get("requests"), Some(&json!(4)));
    assert_eq!(reply.body.get("delivered"), Some(&json!(1)));
    assert_eq!(reply.body.get("failed"), Some(&json!(0)));
    assert_eq!(reply.body.get("median_wait_s"), Some(&json!(420)));
    assert_eq!(reply.body.get("bedside_total"), Some(&json!(5)));
    assert_eq!(reply.body.get("bedside_online"), Some(&json!(4)));
    let text = reply.body.to_string();
    for person in ["nurse", "(mock)", "Dr.", "Bed "] {
        assert!(!text.contains(person), "{person} in {text}");
    }
    for bad in ["0", "721"] {
        let reply = call(
            &app.app,
            get(&format!("/stats/service?hours={bad}"), ADMIN)?,
        )
        .await?;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    }
    let nurse = call(&app.app, get("/stats/service", NURSE)?).await?;
    assert_eq!(nurse.status, StatusCode::FORBIDDEN);
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Map (map-route-heat.md)

#[tokio::test]
async fn saving_and_activating_a_plan_publish_map_updated() -> TestResult {
    let app = MockApp::start()?;
    let mut events = app.hub.subscribe_apps();
    let seed = call(&app.app, get("/clinics/seed", ADMIN)?).await?;
    // The body is the plan document itself (its version is the ETag).
    let mut plan = seed.body.clone();
    if let Some(name) = plan.get_mut("name") {
        *name = json!("Second clinic");
    }
    let created = call(&app.app, post_json("/clinics", ADMIN, &plan)?).await?;
    assert!(created.status.is_success(), "{}", created.body);
    let event = next_event(&mut events, |e| matches!(e, AppEvent::MapUpdated { .. })).await?;
    assert!(
        matches!(event, AppEvent::MapUpdated { active: false, .. }),
        "{event:?}"
    );
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?
        .to_owned();
    let activated = call(
        &app.app,
        post_json(&format!("/clinics/{id}/activate"), ADMIN, &json!({}))?,
    )
    .await?;
    assert!(activated.status.is_success(), "{}", activated.body);
    let event = next_event(&mut events, |e| matches!(e, AppEvent::MapUpdated { .. })).await?;
    assert_same_shape(&encoded(event.clone())?, &doc(MAP_UPDATED)?, "map.updated");
    assert!(
        matches!(
            event,
            AppEvent::MapUpdated {
                active: true,
                version: 1,
                ..
            }
        ),
        "{event:?}"
    );
    let map = call(&app.app, get("/map", ADMIN)?).await?;
    assert_eq!(map.body.get("clinic_id"), Some(&json!(id)));
    Ok(())
}

#[tokio::test]
async fn routes_start_at_the_robot_or_the_start_place_and_never_invent_a_floor() -> TestResult {
    let app = MockApp::start()?;
    // t-1 waits for a robot: from its start place (supply-a, floor 2) to room-12.
    let route = call(&app.app, get("/tasks/t-1/route", ADMIN)?).await?;
    assert_eq!(route.status, StatusCode::OK, "{}", route.body);
    assert_eq!(route.body.get("floor"), Some(&json!(2)));
    assert_eq!(route.body.pointer("/points/0"), Some(&json!([1.55, 2.6])));
    assert_eq!(route.body.get("estimate"), Some(&json!(true)));
    // A finished task has no route.
    let done = call(&app.app, get("/tasks/t-4/route", ADMIN)?).await?;
    assert_eq!(
        (done.status, done.error_code()),
        (StatusCode::NOT_FOUND, Some("no_route"))
    );
    // A task with no start place and no robot (every robot paused): 404 no_route, never a
    // fixed floor-2 route.
    for robot in ["r1", "r2", "r3", "r4"] {
        let reply = call(
            &app.app,
            post_json(
                &format!("/robots/{robot}/command"),
                ADMIN,
                &json!({ "name": "pause" }),
            )?,
        )
        .await?;
        assert_eq!(reply.status, StatusCode::OK, "{robot}: {}", reply.body);
    }
    let created = call(
        &app.app,
        post_json(
            "/tasks",
            ADMIN,
            &json!({ "kind": "fetch", "item": "blanket", "to_place": "hall" }),
        )?,
    )
    .await?;
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?
        .to_owned();
    let none = call(&app.app, get(&format!("/tasks/{id}/route"), ADMIN)?).await?;
    assert_eq!(
        (none.status, none.error_code()),
        (StatusCode::NOT_FOUND, Some("no_route")),
        "{}",
        none.body
    );
    Ok(())
}

#[tokio::test]
async fn a_route_with_a_robot_starts_at_the_robot() -> TestResult {
    let app = MockApp::start()?;
    let created = call(
        &app.app,
        post_json("/tasks", ADMIN, &json!({ "kind": "fetch", "item": "blanket", "from_place": "supply-a", "to_place": "room-12" }))?,
    )
    .await?;
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?
        .to_owned();
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    let robot = robots
        .body
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|robot| robot.get("task_id") == Some(&json!(id)))
        })
        .cloned()
        .ok_or("no robot took it")?;
    let route = call(&app.app, get(&format!("/tasks/{id}/route"), ADMIN)?).await?;
    assert_eq!(route.status, StatusCode::OK, "{}", route.body);
    let first = route.body.pointer("/points/0").cloned().ok_or("no point")?;
    let x = first.get(0).and_then(Value::as_f64).ok_or("x")?;
    let y = first.get(1).and_then(Value::as_f64).ok_or("y")?;
    let rx = robot
        .pointer("/pos/x")
        .and_then(Value::as_f64)
        .ok_or("rx")?;
    let ry = robot
        .pointer("/pos/y")
        .and_then(Value::as_f64)
        .ok_or("ry")?;
    // The robot moves between the two reads; it is never far.
    assert!((x - rx).hypot(y - ry) < 2.0, "{first} vs {robot}");
    Ok(())
}

// ---------------------------------------------------------------------------------------
// The live server (ignored until their fills)

#[tokio::test]
async fn live_emergency_mode_survives_a_restart_and_refuses_new_tasks() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(put_json(
            "/system/mode",
            Some(&admin),
            &json!({ "mode": "emergency", "reason": "drill" }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let refused = app
        .call(post_json(
            "/tasks",
            Some(&admin),
            &json!({ "kind": "fetch", "item": "blanket", "to_place": "room-101" }),
        )?)
        .await?;
    assert_eq!(refused.error_code(), Some("emergency_mode"));
    let again = app
        .relaunch_with_pepper(security::Pepper::from_bytes(support::TEST_PEPPER))
        .await?;
    let token = again.admin_token().await?;
    let mode = again.call(get("/system/mode", Some(&token))?).await?;
    assert_eq!(
        mode.body.get("mode"),
        Some(&json!("emergency")),
        "a restart keeps it on"
    );
    Ok(())
}

#[tokio::test]
async fn live_devices_never_carry_a_patient_name() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app.call(get("/devices", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert!(!reply.body.to_string().contains("patient_name"));
    for tablet in reply.body.as_array().ok_or("not an array")? {
        assert_eq!(keys(tablet), keys(&doc(TABLET)?));
    }
    Ok(())
}

#[tokio::test]
async fn live_monitor_reports_journal_and_database_and_journals_blocks() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let summary = app.call(get("/monitor/summary", Some(&admin))?).await?;
    assert_eq!(keys(&summary.body), keys(&doc(SUMMARY)?));
    assert_eq!(summary.body.get("journal_ok"), Some(&json!(true)));
    assert_eq!(summary.body.get("database_ok"), Some(&json!(true)));
    let created = app
        .call(post_json(
            "/security/blocks",
            Some(&admin),
            &doc(BLOCK_POST)?,
        )?)
        .await?;
    assert_eq!(created.status, StatusCode::CREATED, "{}", created.body);
    let audit = app
        .call(get("/audit?category=security", Some(&admin))?)
        .await?;
    assert!(audit.body.to_string().contains("client_blocked"));
    Ok(())
}

#[tokio::test]
async fn live_service_stats_are_counts_only() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(get("/stats/service?hours=24", Some(&admin))?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(keys(&reply.body), keys(&doc(SERVICE)?));
    assert_eq!(reply.body.get("requests"), Some(&json!(0)));
    Ok(())
}

#[test]
fn every_state_name_in_the_examples_is_a_server_value() -> TestResult {
    // The enum values of the examples parse into the server's types.
    let state: TaskState = serde_json::from_value(json!("requested"))?;
    assert_eq!(state, TaskState::Requested);
    for kind in [
        "rate_limited",
        "auto_blocked",
        "login_burst",
        "blocked",
        "unblocked",
    ] {
        let _parsed: domain::SecurityAlertKind = serde_json::from_value(json!(kind))?;
    }
    for status in ["ok", "limited", "blocked"] {
        let _parsed: domain::ClientStatus = serde_json::from_value(json!(status))?;
    }
    for source in ["manual", "auto"] {
        let _parsed: domain::BlockSource = serde_json::from_value(json!(source))?;
    }
    for kind in ["staff", "bedside"] {
        let _parsed: TabletKind = serde_json::from_value(json!(kind))?;
    }
    Ok(())
}
