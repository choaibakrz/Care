//! Task 12: tasks and inventory with the real services (idempotent robot events, one stock
//! decrement per delivery, one audit entry per state change).

mod support;

use std::time::Duration;

use audit::RecordBody;
use axum::http::StatusCode;
use domain::{ApplyOutcome, Clock as _, RobotId, TaskId, TaskState};
use serde_json::{Value, json};
use support::{LiveServer, RealApp, Res, TestResult, WsClient, api, map, post_json, task_event};
use uuid::Uuid;

fn fetch(item: &str, to: &str) -> Value {
    json!({ "kind": "fetch", "item": item, "from_place": map::STOREROOM, "to_place": to })
}

/// A real app with 3 blankets, robot `robot-r2` connected at the storeroom, and one fetch
/// task assigned to it.
struct Assigned {
    app: RealApp,
    _server: LiveServer,
    robot_socket: WsClient,
    nurse: String,
    task: String,
}

async fn assigned_task() -> Res<Assigned> {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 3).await?;
    let server = app.serve().await?;
    let mut robot_socket = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &fetch("blanket", map::ROOM_101),
        )?)
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
    let assign = robot_socket
        .next_of_type("task.assign", Duration::from_secs(3))
        .await?;
    assert_eq!(assign.get("task_id"), Some(&json!(task)));
    Ok(Assigned {
        app,
        _server: server,
        robot_socket,
        nurse,
        task,
    })
}

async fn apply(app: &RealApp, task: &str, event: Uuid, state: TaskState) -> Res<ApplyOutcome> {
    let robot: RobotId = "robot-r2".parse()?;
    let task: TaskId = task.parse()?;
    api(app
        .state
        .tasks
        .apply_robot_event(&robot, event, &task, state, None)
        .await)
}

/// Journal records `TaskStateChanged` for `task`, as `(from, to)` pairs.
async fn transitions(app: &RealApp, task: &str) -> Res<Vec<(TaskState, TaskState)>> {
    app.journal.seal_now(audit::SealReason::Interval).await?;
    Ok(support::read_journal(&app.config.journal.dir)?
        .into_iter()
        .filter_map(|r| match r.body {
            RecordBody::TaskStateChanged {
                task: t, from, to, ..
            } if t.as_str() == task => Some((from, to)),
            _ => None,
        })
        .collect())
}

#[tokio::test]
async fn create_fetch_for_unknown_place_returns_422_naming_the_place() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 3).await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &fetch("blanket", "room-999"),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(
        reply.error_message().contains("room-999"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn create_fetch_for_unknown_item_returns_404() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &fetch("unicorn", map::ROOM_101),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND);
    assert_eq!(reply.error_code(), Some("not_found"));
    assert!(
        reply.error_message().contains("unicorn"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn create_with_zero_stock_returns_409_out_of_stock() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 0).await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &fetch("blanket", map::ROOM_101),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT);
    assert_eq!(reply.error_code(), Some("out_of_stock"));
    Ok(())
}

/// Review Focus 1: the same event id twice gives one transition, one stock decrement and
/// one audit entry.
#[tokio::test]
async fn duplicate_robot_event_is_applied_once() -> TestResult {
    let world = assigned_task().await?;
    apply(&world.app, &world.task, Uuid::new_v4(), TaskState::EnRoute).await?;
    let delivered = Uuid::new_v4();
    let first = apply(&world.app, &world.task, delivered, TaskState::Delivered).await?;
    let second = apply(&world.app, &world.task, delivered, TaskState::Delivered).await?;
    assert_eq!(first, ApplyOutcome::Applied);
    assert_eq!(second, ApplyOutcome::Duplicate);
    assert_eq!(
        world.app.task_state(&world.nurse, &world.task).await?,
        "delivered"
    );
    assert_eq!(world.app.stock("blanket").await?, 2);
    let to_delivered = transitions(&world.app, &world.task)
        .await?
        .into_iter()
        .filter(|(_, to)| *to == TaskState::Delivered)
        .count();
    assert_eq!(to_delivered, 1);
    Ok(())
}

#[tokio::test]
async fn delivered_decrements_stock_exactly_once_even_if_event_replayed() -> TestResult {
    let logs = support::LogCapture::global()?;
    let mut world = assigned_task().await?;
    let mark = logs.mark();
    let now = world.app.clock.now();
    world
        .robot_socket
        .send_json(&task_event(&world.task, "en_route", None, now))
        .await?;
    let delivered = task_event(&world.task, "delivered", None, now);
    world.robot_socket.send_json(&delivered).await?;
    // The same envelope again: delivered -> delivered would be an illegal transition, so
    // only de-duplication leaves no rejection behind.
    world.robot_socket.send_json(&delivered).await?;
    world
        .app
        .robot_barrier(&mut world.robot_socket, "robot-r2", 42.0)
        .await?;
    world.app.assert_nothing_rejected(&logs, mark).await?;
    assert_eq!(
        world.app.task_state(&world.nurse, &world.task).await?,
        "delivered"
    );
    assert_eq!(world.app.stock("blanket").await?, 2);
    Ok(())
}

#[tokio::test]
async fn illegal_transition_from_robot_returns_409_with_both_states_named() -> TestResult {
    let world = assigned_task().await?;
    let err = apply(
        &world.app,
        &world.task,
        Uuid::new_v4(),
        TaskState::Delivered,
    )
    .await
    .err()
    .ok_or("assigned -> delivered was accepted")?
    .to_string();
    assert!(err.contains("CONFLICT") || err.contains("409"), "{err}");
    assert!(
        err.contains("assigned") && err.contains("delivered"),
        "{err}"
    );
    assert_eq!(
        world.app.task_state(&world.nurse, &world.task).await?,
        "assigned"
    );
    Ok(())
}

#[tokio::test]
async fn cancel_after_en_route_is_rejected() -> TestResult {
    let world = assigned_task().await?;
    apply(&world.app, &world.task, Uuid::new_v4(), TaskState::EnRoute).await?;
    let reply = world
        .app
        .call(post_json(
            &format!("/tasks/{}/cancel", world.task),
            Some(&world.nurse),
            &json!({}),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT);
    assert_eq!(
        world.app.task_state(&world.nurse, &world.task).await?,
        "en_route"
    );
    Ok(())
}

#[tokio::test]
async fn adjust_below_zero_is_rejected_with_numbers() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 3).await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(post_json(
            "/inventory/blanket/adjust",
            Some(&admin),
            &json!({ "delta": -5, "reason": "correction" }),
        )?)
        .await?;
    assert!(reply.status.is_client_error(), "{}", reply.status);
    assert_eq!(
        reply.error_message(),
        "Cannot remove 5 'blanket': only 3 in stock."
    );
    assert_eq!(app.stock("blanket").await?, 3);
    Ok(())
}

#[tokio::test]
async fn nurse_cannot_adjust_inventory() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 3).await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/inventory/blanket/adjust",
            Some(&nurse),
            &json!({ "delta": 1, "reason": "restock" }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("forbidden"));
    assert_eq!(app.stock("blanket").await?, 3);
    Ok(())
}

#[tokio::test]
async fn every_state_change_writes_one_audit_entry() -> TestResult {
    let world = assigned_task().await?;
    apply(&world.app, &world.task, Uuid::new_v4(), TaskState::EnRoute).await?;
    apply(
        &world.app,
        &world.task,
        Uuid::new_v4(),
        TaskState::Delivered,
    )
    .await?;
    let seen = transitions(&world.app, &world.task).await?;
    assert_eq!(
        seen,
        vec![
            (TaskState::Requested, TaskState::Assigned),
            (TaskState::Assigned, TaskState::EnRoute),
            (TaskState::EnRoute, TaskState::Delivered),
        ]
    );
    Ok(())
}
