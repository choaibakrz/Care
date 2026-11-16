//! Task A3: the API contract as the admin console reads it (`implementation/admin/src/lib/
//! adapt.ts`, `http.ts`, `live.ts`). One check per contract row: key sets, enum spellings,
//! request bodies, and the `/ws` first-message authentication.
//!
//! The type-level tests (schemas, serde) and the tests against the `--mock` wiring run
//! (Task 4). Only the robot heartbeat test waits for `fake_robot` and robot sessions (Task 5).

mod support;

use std::collections::BTreeSet;
use std::process::Stdio;
use std::time::Duration;

use axum::http::{Method, StatusCode};
use clinic_server::dto::{
    AdjustRequest, AuditEntry, AuditPageView, AuditResult, CommandReceipt, LoginRequest,
    LoginResponse, MapView, RobotView, SchedulePatch, ScheduleView, TaskHistoryEntry, TaskPage,
    TaskView, ZoneInput, ZoneView,
};
use clinic_server::openapi::ApiDoc;
use domain::{
    CommandName, RobotStatus, RoundResult, ShelfCount, StockAdjustReason, StockLevel, TaskKind,
    TaskState, ZoneKind,
};
use locations::{
    PlaceViewKind, PlanFloor, PlanPlace, PlanProp, PlanRoom, PlanWall, PropKind, RoomKind,
};
use realtime::{
    APP_AUTH_CLOSE_CODE, AlertKind, AlertLevel, AppEvent, AppUp, DeliveryState, RobotPose,
    ZoneDeliveryEntry,
};
use serde_json::{Value, json};
use support::{
    ADMIN_ORIGIN, LiveServer, MockApp, Res, TestResult, WsClient, app_socket_with_token, call, get,
    post_json, put_json, request,
};
use tokio::process::{Child, Command};
use utoipa::{OpenApi as _, PartialSchema};

const ADMIN: Option<&str> = Some("mock-admin");

// ---------------------------------------------------------------------------------------
// Helpers

fn set(keys: &[&str]) -> BTreeSet<String> {
    keys.iter().map(|k| (*k).to_owned()).collect()
}

fn keys(value: &Value) -> BTreeSet<String> {
    value
        .as_object()
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default()
}

/// The property names of a type's OpenAPI schema.
fn schema_keys<T: PartialSchema>() -> Res<BTreeSet<String>> {
    let schema = serde_json::to_value(T::schema())?;
    let properties = schema
        .get("properties")
        .ok_or_else(|| format!("schema has no properties: {schema}"))?;
    Ok(keys(properties))
}

/// The `enum` values of a string enum's OpenAPI schema.
fn schema_enum<T: PartialSchema>() -> Res<BTreeSet<String>> {
    let schema = serde_json::to_value(T::schema())?;
    let values = schema
        .get("enum")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("schema is not a string enum: {schema}"))?;
    Ok(values
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect())
}

/// Asserts the console's keys are all there and nothing else but the documented extras.
fn assert_keys(actual: &BTreeSet<String>, console: &[&str], extras: &[&str]) {
    let mut expected = set(console);
    expected.extend(set(extras));
    assert_eq!(actual, &expected);
}

/// Asserts every console key is present in a JSON object from the server.
fn assert_has_keys(value: &Value, console: &[&str]) {
    let present = keys(value);
    let missing: Vec<&&str> = console.iter().filter(|k| !present.contains(**k)).collect();
    assert!(missing.is_empty(), "missing {missing:?} in {value}");
}

/// A field of a JSON object, `null` when absent.
fn field<'a>(value: &'a Value, key: &str) -> &'a Value {
    value.get(key).unwrap_or(&Value::Null)
}

fn first(value: &Value) -> Res<&Value> {
    value
        .as_array()
        .and_then(|list| list.first())
        .ok_or_else(|| format!("expected a non-empty array, got {value}").into())
}

const ROBOT_KEYS: &[&str] = &[
    "id",
    "name",
    "role",
    "simulated",
    "pos",
    "battery",
    "state",
    "holding",
    "mic_open",
    "task_id",
    "last_seen",
    "in_deaf_zone",
    "going_home",
    "mood",
];
const TASK_KEYS: &[&str] = &[
    "id",
    "kind",
    "item",
    "from_place",
    "to_place",
    "state",
    "robot_id",
    "requested_by",
    "created_at",
    "updated_at",
    "reason",
    "history",
];
const ITEM_KEYS: &[&str] = &[
    "id",
    "label",
    "place",
    "count",
    "low_at",
    "last_robot_count",
    "last_robot_count_at",
    "updated_at",
];
const ZONE_KEYS: &[&str] = &[
    "id",
    "name",
    "floor",
    "kind",
    "polygon",
    "deliveries",
    "enforced_by_gardien",
];
const SCHEDULE_KEYS: &[&str] = &[
    "id",
    "label",
    "enabled",
    "time",
    "robot_id",
    "last_run",
    "last_result",
    "last_counts",
];
const AUDIT_KEYS: &[&str] = &["id", "at", "actor", "action", "target", "result", "detail"];

// ---------------------------------------------------------------------------------------
// Type-level checks (run now)

#[test]
fn login_request_and_response_have_the_console_keys() -> TestResult {
    assert_keys(
        &schema_keys::<LoginRequest>()?,
        // Task A7: the derived key replaces `{username, password}`.
        &["account_key"],
        &["device_id"],
    );
    assert_keys(
        &schema_keys::<LoginResponse>()?,
        &["token", "role", "operator", "expires_at"],
        &[],
    );
    Ok(())
}

#[test]
fn login_body_from_a_browser_needs_no_device_id() -> TestResult {
    let body: LoginRequest = serde_json::from_value(json!({ "account_key": "ab".repeat(32) }))?;
    assert!(body.device_id.is_none());
    Ok(())
}

#[test]
fn map_view_has_floors_rooms_walls_places_props() -> TestResult {
    // Task A4: `GET /map` is the active clinic plan plus its identity; the element types are
    // the plan's own (one shape for drawing and editing).
    assert_keys(
        &schema_keys::<MapView>()?,
        &["floors", "rooms", "walls", "places", "props"],
        &["clinic_id", "version", "name"],
    );
    assert_keys(
        &schema_keys::<PlanFloor>()?,
        &["id", "label", "outline"],
        &[],
    );
    assert_keys(
        &schema_keys::<PlanRoom>()?,
        &["id", "floor", "label", "kind", "polygon", "label_at"],
        &[],
    );
    // Walls carry an `id` so they can be edited; the console ignores it until task F3.
    assert_keys(&schema_keys::<PlanWall>()?, &["floor", "points"], &["id"]);
    assert_keys(
        &schema_keys::<PlanPlace>()?,
        &["id", "label", "floor", "x", "y", "kind"],
        &[],
    );
    assert_keys(
        &schema_keys::<PlanProp>()?,
        &["id", "floor", "kind", "x", "y", "width", "depth", "solid"],
        &[],
    );
    assert_eq!(
        schema_enum::<RoomKind>()?,
        set(&[
            "room", "corridor", "elevator", "care", "storage", "therapy", "pool", "lounge"
        ])
    );
    assert_eq!(
        schema_enum::<PlaceViewKind>()?,
        set(&["room", "shelf", "dock", "point"])
    );
    assert_eq!(
        schema_enum::<PropKind>()?,
        set(&[
            "bed",
            "counter",
            "desk",
            "shelf",
            "cabinet",
            "sofa",
            "armchair",
            "table",
            "plant",
            "dock",
            "pool",
            "bench",
            "crate",
            "mat",
            "bars",
            "nightstand",
            "door"
        ])
    );
    Ok(())
}

#[test]
fn robot_view_has_the_console_keys() -> TestResult {
    assert_keys(&schema_keys::<RobotView>()?, ROBOT_KEYS, &["connected"]);
    assert_keys(
        &schema_keys::<RobotPose>()?,
        &["x", "y", "heading", "floor"],
        &[],
    );
    Ok(())
}

#[test]
fn robot_state_never_serialises_as_offline() -> TestResult {
    assert_eq!(
        schema_enum::<RobotStatus>()?,
        set(&["idle", "busy", "paused", "fault", "estop"])
    );
    assert!(serde_json::from_value::<RobotStatus>(json!("offline")).is_err());
    Ok(())
}

#[test]
fn command_body_and_receipt_match_the_console() -> TestResult {
    for name in ["pause", "resume", "dock", "estop"] {
        let parsed: CommandName = serde_json::from_value(json!(name))?;
        assert_eq!(serde_json::to_value(parsed)?, json!(name));
    }
    assert_keys(
        &schema_keys::<CommandReceipt>()?,
        &["accepted", "reason", "sent_at"],
        &["command", "command_id"],
    );
    Ok(())
}

#[test]
fn task_view_has_the_console_keys_and_states() -> TestResult {
    assert_keys(
        &schema_keys::<TaskView>()?,
        TASK_KEYS,
        &["target_device", "target_label", "until"],
    );
    assert_keys(
        &schema_keys::<TaskHistoryEntry>()?,
        &["at", "actor", "label"],
        &[],
    );
    assert_keys(&schema_keys::<TaskPage>()?, &["items", "next"], &[]);
    assert_eq!(
        schema_enum::<TaskState>()?,
        set(&[
            "requested",
            "assigned",
            "en_route",
            "delivered",
            "failed",
            "resumed",
            "cancelled"
        ])
    );
    assert_eq!(
        schema_enum::<TaskKind>()?,
        set(&[
            "fetch",
            "restock_round",
            "go_to",
            "interpreter_session",
            "follow"
        ])
    );
    Ok(())
}

#[test]
fn inventory_item_has_the_console_keys() -> TestResult {
    assert_keys(&schema_keys::<StockLevel>()?, ITEM_KEYS, &[]);
    Ok(())
}

#[test]
fn adjust_body_without_reason_defaults_to_admin_correction() -> TestResult {
    let body: AdjustRequest = serde_json::from_value(json!({ "delta": -2 }))?;
    assert_eq!(body.delta, -2);
    assert_eq!(body.reason, StockAdjustReason::AdminCorrection);
    assert_eq!(
        serde_json::to_value(StockAdjustReason::AdminCorrection)?,
        json!("admin_correction")
    );
    Ok(())
}

#[test]
fn zone_view_and_input_have_the_console_keys() -> TestResult {
    assert_keys(&schema_keys::<ZoneView>()?, ZONE_KEYS, &["version"]);
    assert_keys(
        &schema_keys::<ZoneInput>()?,
        &["id", "name", "floor", "kind", "polygon"],
        &[],
    );
    assert_keys(
        &schema_keys::<ZoneDeliveryEntry>()?,
        &["robot_id", "status"],
        &["acked_version", "robot_online"],
    );
    assert_eq!(
        schema_enum::<DeliveryState>()?,
        set(&["received", "pending", "failed"])
    );
    assert_eq!(schema_enum::<ZoneKind>()?, set(&["deaf", "restricted"]));
    Ok(())
}

#[test]
fn schedule_view_and_patch_have_the_console_keys() -> TestResult {
    assert_keys(
        &schema_keys::<ScheduleView>()?,
        SCHEDULE_KEYS,
        &["timezone", "next_run"],
    );
    assert_keys(
        &schema_keys::<SchedulePatch>()?,
        &["enabled", "time", "robot_id"],
        &[],
    );
    assert_keys(
        &schema_keys::<ShelfCount>()?,
        &["place", "item", "expected", "counted"],
        &[],
    );
    assert_eq!(
        schema_enum::<RoundResult>()?,
        set(&["success", "partial", "failed", "never"])
    );
    Ok(())
}

#[test]
fn schedule_patch_accepts_partial_bodies() -> TestResult {
    let only_enabled: SchedulePatch = serde_json::from_value(json!({ "enabled": false }))?;
    assert_eq!(only_enabled.enabled, Some(false));
    assert!(only_enabled.time.is_none() && only_enabled.robot_id.is_none());
    let console: SchedulePatch =
        serde_json::from_value(json!({ "enabled": true, "time": "02:30" }))?;
    assert_eq!(console.time.as_deref(), Some("02:30"));
    let cron = serde_json::from_value::<SchedulePatch>(json!({ "cron": "0 2 * * *" }));
    assert!(cron.is_err(), "cron is internal, not part of the API");
    Ok(())
}

#[test]
fn audit_rows_have_the_console_keys() -> TestResult {
    assert_keys(&schema_keys::<AuditEntry>()?, AUDIT_KEYS, &["category"]);
    assert_keys(&schema_keys::<AuditPageView>()?, &["items", "next"], &[]);
    assert_eq!(
        schema_enum::<AuditResult>()?,
        set(&["ok", "refused", "failed"])
    );
    Ok(())
}

#[test]
fn alert_event_has_type_level_and_message() -> TestResult {
    let alert = AppEvent::Alert {
        level: AlertLevel::Critical,
        kind: AlertKind::EstopNotDelivered,
        message: "Robot robot-r2 is offline.".to_owned(),
        command: None,
    };
    let value = serde_json::to_value(&alert)?;
    assert_eq!(value.get("type"), Some(&json!("alert")));
    assert_eq!(value.get("level"), Some(&json!("critical")));
    assert_eq!(
        value.get("message"),
        Some(&json!("Robot robot-r2 is offline."))
    );
    assert_eq!(
        schema_enum::<AlertLevel>()?,
        set(&["info", "warning", "critical"])
    );
    Ok(())
}

#[test]
fn ws_auth_message_is_type_auth_with_token() -> TestResult {
    let AppUp::Auth { token } = serde_json::from_value(json!({ "type": "auth", "token": "abc" }))?;
    assert_eq!(token, "abc");
    assert!(serde_json::from_value::<AppUp>(json!({ "type": "hello" })).is_err());
    assert_eq!(APP_AUTH_CLOSE_CODE, 4401);
    Ok(())
}

#[test]
fn openapi_lists_every_console_route_with_its_method() -> TestResult {
    let doc = serde_json::to_value(ApiDoc::openapi())?;
    let paths = doc.get("paths").ok_or("no paths")?;
    let routes = [
        ("/auth/login", "post"),
        // Task A7: the console's enrolment and account screens (frontend task F9).
        ("/auth/derivation", "get"),
        ("/auth/enrol", "post"),
        ("/admin/enrolment-codes", "post"),
        ("/admin/accounts", "get"),
        ("/admin/accounts/{account_tag}", "delete"),
        ("/robots/{id}/commands/{command_id}/revert", "post"),
        ("/map", "get"),
        ("/robots", "get"),
        ("/robots/{id}/command", "post"),
        ("/tasks", "get"),
        ("/tasks/{id}", "get"),
        ("/tasks/{id}/cancel", "post"),
        ("/inventory", "get"),
        ("/inventory/{item}/adjust", "post"),
        ("/zones", "get"),
        ("/zones/{id}", "put"),
        ("/zones/{id}", "delete"),
        ("/schedules", "get"),
        ("/schedules/{id}", "put"),
        ("/audit", "get"),
        ("/ws", "get"),
    ];
    for (path, method) in routes {
        assert!(
            paths.get(path).and_then(|p| p.get(method)).is_some(),
            "{method} {path} missing from OpenAPI"
        );
    }
    assert!(
        paths.get("/auth/ws-ticket").is_none(),
        "the WebSocket ticket route was removed"
    );
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Against the `--mock` wiring (one per contract row)

#[tokio::test]
async fn login_returns_token_role_operator_expires_at() -> TestResult {
    let app = MockApp::start()?;
    // Task A7: the console sends the key derived from `admin` / `mock`.
    let body = support::login_body("admin", "mock", None)?;
    let reply = call(&app.app, post_json("/auth/login", None, &body)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(
        keys(&reply.body),
        set(&["token", "role", "operator", "expires_at"])
    );
    Ok(())
}

#[tokio::test]
async fn map_returns_floors_rooms_walls_places() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/map", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_has_keys(
        &reply.body,
        &["floors", "rooms", "walls", "places", "props"],
    );
    assert_has_keys(
        first(field(&reply.body, "floors"))?,
        &["id", "label", "outline"],
    );
    assert_has_keys(
        first(field(&reply.body, "rooms"))?,
        &["id", "floor", "label", "kind", "polygon"],
    );
    assert_has_keys(
        first(field(&reply.body, "walls"))?,
        &["id", "floor", "points"],
    );
    assert_has_keys(
        first(field(&reply.body, "places"))?,
        &["id", "label", "floor", "x", "y", "kind"],
    );
    Ok(())
}

#[tokio::test]
async fn robots_list_has_console_keys_and_known_state() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/robots", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let robot = first(&reply.body)?;
    assert_has_keys(robot, ROBOT_KEYS);
    assert_has_keys(field(robot, "pos"), &["x", "y", "heading", "floor"]);
    let state = field(robot, "state").as_str().unwrap_or_default();
    assert!(
        ["idle", "busy", "paused", "fault", "estop"].contains(&state),
        "{robot}"
    );
    Ok(())
}

#[tokio::test]
async fn command_returns_accepted_reason_sent_at() -> TestResult {
    // `r1` is a robot the mock shows as connected (Task 4 fix round 1: was `robot-r2`, which
    // is offline, and a command to an offline robot is 409).
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_has_keys(&reply.body, &["accepted", "reason", "sent_at"]);
    Ok(())
}

#[tokio::test]
async fn command_to_offline_robot_is_409_robot_offline() -> TestResult {
    let app = MockApp::start()?;
    for name in ["pause", "resume", "dock", "shutdown"] {
        let reply = call(
            &app.app,
            post_json("/robots/robot-r2/command", ADMIN, &json!({ "name": name }))?,
        )
        .await?;
        assert_eq!(reply.status, StatusCode::CONFLICT, "{name}: {}", reply.body);
        assert_eq!(reply.error_code(), Some("robot_offline"), "{name}");
        assert!(
            reply.error_message().contains("robot-r2 is offline"),
            "{name}: {}",
            reply.error_message()
        );
    }
    Ok(())
}

#[tokio::test]
async fn offline_robot_is_listed_with_last_seen() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/robots", ADMIN)?).await?;
    let robot = reply
        .body
        .as_array()
        .and_then(|robots| {
            robots
                .iter()
                .find(|r| r.get("id") == Some(&json!("robot-r2")))
        })
        .ok_or("robot-r2 is not listed")?;
    assert_eq!(robot.get("connected"), Some(&json!(false)), "{robot}");
    assert!(
        robot.get("last_seen").and_then(Value::as_str).is_some(),
        "{robot}"
    );
    Ok(())
}

#[tokio::test]
async fn estop_to_offline_robot_is_409_with_readable_message() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        post_json(
            "/robots/robot-r2/command",
            ADMIN,
            &json!({ "name": "estop" }),
        )?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(
        reply.error_message(),
        "Robot robot-r2 is offline: the stop was not delivered. Use the physical button."
    );
    Ok(())
}

#[tokio::test]
async fn tasks_are_items_and_next_with_console_keys() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/tasks", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(keys(&reply.body), set(&["items", "next"]));
    let task = first(field(&reply.body, "items"))?;
    assert_has_keys(task, TASK_KEYS);
    assert_has_keys(first(field(task, "history"))?, &["at", "actor", "label"]);
    let one = call(
        &app.app,
        get(
            &format!("/tasks/{}", field(task, "id").as_str().unwrap_or_default()),
            ADMIN,
        )?,
    )
    .await?;
    assert_eq!(one.status, StatusCode::OK, "{}", one.body);
    assert_has_keys(&one.body, TASK_KEYS);
    Ok(())
}

#[tokio::test]
async fn cancel_returns_the_task_in_state_cancelled() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, post_json("/tasks/t-1/cancel", ADMIN, &json!({}))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_has_keys(&reply.body, TASK_KEYS);
    assert_eq!(reply.body.get("state"), Some(&json!("cancelled")));
    Ok(())
}

#[tokio::test]
async fn inventory_list_has_console_keys() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/inventory", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_has_keys(first(&reply.body)?, ITEM_KEYS);
    Ok(())
}

#[tokio::test]
async fn adjust_without_reason_uses_admin_correction() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        post_json("/inventory/blanket/adjust", ADMIN, &json!({ "delta": 1 }))?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_has_keys(&reply.body, ITEM_KEYS);
    let zero = call(
        &app.app,
        post_json("/inventory/blanket/adjust", ADMIN, &json!({ "delta": 0 }))?,
    )
    .await?;
    assert_eq!(
        zero.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        zero.body
    );
    Ok(())
}

#[tokio::test]
async fn zones_list_has_console_keys() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/zones", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let zone = first(&reply.body)?;
    assert_has_keys(zone, ZONE_KEYS);
    for delivery in field(zone, "deliveries").as_array().into_iter().flatten() {
        let status = field(delivery, "status").as_str().unwrap_or_default();
        assert!(
            ["received", "pending", "failed"].contains(&status),
            "{delivery}"
        );
    }
    Ok(())
}

#[tokio::test]
async fn zone_put_with_mismatched_body_id_is_422() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({
        "id": "z-other", "name": "Quiet", "floor": 1, "kind": "deaf",
        "polygon": [[1.0, 13.0], [9.0, 13.0], [9.0, 19.0]]
    });
    let reply = call(&app.app, put_json("/zones/z-1", ADMIN, &body)?).await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    assert!(reply.error_message().contains("id"), "{}", reply.body);
    Ok(())
}

#[tokio::test]
async fn zone_put_then_delete_is_200_then_204() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({
        "id": "z-1", "name": "Quiet", "floor": 1, "kind": "deaf",
        "polygon": [[1.0, 13.0], [9.0, 13.0], [9.0, 19.0]]
    });
    let saved = call(&app.app, put_json("/zones/z-1", ADMIN, &body)?).await?;
    assert_eq!(saved.status, StatusCode::OK, "{}", saved.body);
    assert_has_keys(&saved.body, ZONE_KEYS);
    let deleted = call(
        &app.app,
        request(Method::DELETE, "/zones/z-1", ADMIN, None)?,
    )
    .await?;
    assert_eq!(deleted.status, StatusCode::NO_CONTENT, "{}", deleted.body);
    Ok(())
}

#[tokio::test]
async fn schedules_list_has_console_keys() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/schedules", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let schedule = first(&reply.body)?;
    assert_has_keys(schedule, SCHEDULE_KEYS);
    let time = field(schedule, "time").as_str().unwrap_or_default();
    assert!(
        time.len() == 5 && time.as_bytes().get(2) == Some(&b':'),
        "{time}"
    );
    Ok(())
}

#[tokio::test]
async fn schedule_put_partial_body_changes_only_given_fields() -> TestResult {
    let app = MockApp::start()?;
    let before = call(&app.app, get("/schedules", ADMIN)?).await?;
    let original = first(&before.body)?.clone();
    let id = field(&original, "id")
        .as_str()
        .unwrap_or_default()
        .to_owned();
    let enabled = field(&original, "enabled").as_bool().unwrap_or_default();
    let reply = call(
        &app.app,
        put_json(
            &format!("/schedules/{id}"),
            ADMIN,
            &json!({ "enabled": !enabled }),
        )?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("enabled"), Some(&json!(!enabled)));
    assert_eq!(reply.body.get("time"), original.get("time"));
    assert_eq!(reply.body.get("robot_id"), original.get("robot_id"));
    assert_eq!(reply.body.get("label"), original.get("label"));
    Ok(())
}

#[tokio::test]
async fn audit_is_items_and_next_with_console_keys() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        get(
            "/audit?from=2026-11-14T00:00:00Z&to=2026-11-15T00:00:00Z",
            ADMIN,
        )?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(keys(&reply.body), set(&["items", "next"]));
    let row = first(field(&reply.body, "items"))?;
    assert_has_keys(row, AUDIT_KEYS);
    let result = field(row, "result").as_str().unwrap_or_default();
    assert!(["ok", "refused", "failed"].contains(&result), "{row}");
    Ok(())
}

#[tokio::test]
async fn audit_filter_by_actor_taken_from_a_row() -> TestResult {
    let app = MockApp::start()?;
    let all = call(&app.app, get("/audit", ADMIN)?).await?;
    assert_eq!(all.status, StatusCode::OK, "{}", all.body);
    let actor = field(first(field(&all.body, "items"))?, "actor")
        .as_str()
        .ok_or("no actor in the first row")?
        .to_owned();
    let query: String = url_encode(&actor);
    let filtered = call(&app.app, get(&format!("/audit?actor={query}"), ADMIN)?).await?;
    assert_eq!(filtered.status, StatusCode::OK, "{}", filtered.body);
    let rows = field(&filtered.body, "items")
        .as_array()
        .ok_or("no items")?;
    assert!(!rows.is_empty(), "filtering by {actor:?} returned nothing");
    for row in rows {
        assert_eq!(field(row, "actor").as_str(), Some(actor.as_str()), "{row}");
    }
    Ok(())
}

/// Percent-encodes a query value (labels may contain spaces).
fn url_encode(value: &str) -> String {
    value
        .bytes()
        .map(|b| {
            if b.is_ascii_alphanumeric() || b"-_.~:".contains(&b) {
                char::from(b).to_string()
            } else {
                format!("%{b:02X}")
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------------------
// `WS /ws`: first-message authentication and the robot heartbeat

#[tokio::test]
async fn ws_auth_first_message_accepts_valid_token() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = app_socket_with_token(&server, "mock-admin").await?;
    let first = socket.next_json(Duration::from_secs(3)).await?;
    assert_eq!(first.get("type"), Some(&json!("snapshot")), "{first}");
    Ok(())
}

#[tokio::test]
async fn ws_without_auth_message_closes_after_5s_with_4401() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = WsClient::connect(&server.ws_url("/ws"), &[("origin", ADMIN_ORIGIN)]).await?;
    let started = tokio::time::Instant::now();
    let (code, reason) = socket.first_frame_is_close(Duration::from_secs(8)).await?;
    assert!(started.elapsed() >= Duration::from_millis(4_500));
    assert_eq!(code, 4401);
    assert!(reason.contains("auth"), "{reason}");
    Ok(())
}

#[tokio::test]
async fn ws_with_refused_token_closes_with_4401() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = app_socket_with_token(&server, "not-a-token").await?;
    let (code, reason) = socket.first_frame_is_close(Duration::from_secs(3)).await?;
    assert_eq!(code, 4401);
    assert!(reason.contains("refused"), "{reason}");
    Ok(())
}

#[tokio::test]
async fn ws_token_in_query_is_ignored() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let url = server.ws_url("/ws?token=mock-admin&ticket=mock-admin");
    let mut socket = WsClient::connect(&url, &[("origin", ADMIN_ORIGIN)]).await?;
    let (code, _reason) = socket.first_frame_is_close(Duration::from_secs(8)).await?;
    assert_eq!(code, 4401, "a token in the URL must not authenticate");
    Ok(())
}

#[tokio::test]
async fn ws_robot_token_on_app_socket_closes_with_4401() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = app_socket_with_token(&server, "mock-robot").await?;
    let (code, reason) = socket.first_frame_is_close(Duration::from_secs(3)).await?;
    assert_eq!(code, 4401);
    assert_eq!(reason, clinic_server::ws::apps::close_reason::ROBOT);
    Ok(())
}

#[tokio::test]
async fn ws_binary_first_message_closes_with_4401() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = WsClient::connect(&server.ws_url("/ws"), &[("origin", ADMIN_ORIGIN)]).await?;
    socket
        .send_binary(b"{\"type\":\"auth\",\"token\":\"mock-admin\"}".to_vec())
        .await?;
    let (code, reason) = socket.first_frame_is_close(Duration::from_secs(3)).await?;
    assert_eq!(code, 4401);
    assert_eq!(reason, clinic_server::ws::apps::close_reason::NOT_AUTH);
    Ok(())
}

#[tokio::test]
async fn ws_non_auth_first_message_closes_with_4401() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut socket = WsClient::connect(&server.ws_url("/ws"), &[("origin", ADMIN_ORIGIN)]).await?;
    socket
        .send_json(&json!({ "type": "subscribe", "token": "mock-admin" }))
        .await?;
    let (code, reason) = socket.first_frame_is_close(Duration::from_secs(3)).await?;
    assert_eq!(code, 4401);
    assert_eq!(reason, clinic_server::ws::apps::close_reason::NOT_AUTH);
    Ok(())
}

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

#[tokio::test]
async fn robot_updated_sent_every_second_while_connected() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut watcher = app_socket_with_token(&server, "mock-admin").await?;
    let _robot = spawn_fake_robot(&server)?;
    // Wait for the robot to appear, then count updates over 3.5 s: at least 3.
    let deadline = tokio::time::Instant::now() + Duration::from_secs(3);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = watcher.next_of_type("robot.updated", left).await?;
        if event.pointer("/robot/id") == Some(&json!("robot-r2")) {
            assert_has_keys(field(&event, "robot"), ROBOT_KEYS);
            break;
        }
    }
    let window = tokio::time::Instant::now() + Duration::from_millis(3_500);
    let mut updates = 0_u32;
    while let Some(left) = window.checked_duration_since(tokio::time::Instant::now()) {
        let Ok(event) = watcher.next_of_type("robot.updated", left).await else {
            break;
        };
        if event.pointer("/robot/id") == Some(&json!("robot-r2")) {
            updates += 1;
        }
    }
    assert!(updates >= 3, "only {updates} robot.updated in 3.5 s");
    Ok(())
}
