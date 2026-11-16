//! Task 15: the `SQLite` stock ledger under concurrency (Review Focus 2), and reservations
//! following the task life cycle.

mod support;

use std::sync::Arc;
use std::time::Duration;

use axum::http::StatusCode;
use domain::ports::InventoryRepository as _;
use domain::{ItemId, StockError, StockLedger as _, StockLevel, TaskId, TaskState};
use serde_json::{Value, json};
use storage::{Database, SqliteInventoryRepository, SqliteLedger};
use support::{RealApp, Res, TestResult, api, map, post_json};
use uuid::Uuid;

fn fetch() -> Value {
    json!({ "kind": "fetch", "item": "blanket", "from_place": map::STOREROOM, "to_place": map::ROOM_101 })
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn two_tasks_one_unit_exactly_one_wins() -> TestResult {
    let blanket: ItemId = "blanket".parse()?;
    for round in 0..50_u32 {
        let db = Database::in_memory().await?;
        db.migrate().await?;
        SqliteInventoryRepository::new(db.clone())
            .upsert(&StockLevel {
                item: blanket.clone(),
                label: "blanket".to_owned(),
                place: "storeroom".parse()?,
                count: 1,
                low_threshold: 1,
                last_robot_count: None,
                last_robot_count_at: None,
                updated_at: chrono::Utc::now(),
            })
            .await?;
        let ledger = Arc::new(SqliteLedger::new(db));
        let a: TaskId = format!("t-{round}-a").parse()?;
        let b: TaskId = format!("t-{round}-b").parse()?;
        let (la, lb) = (ledger.clone(), ledger.clone());
        let (ia, ib) = (blanket.clone(), blanket.clone());
        let first = tokio::spawn(async move { la.reserve(&a, &ia, 1).await });
        let second = tokio::spawn(async move { lb.reserve(&b, &ib, 1).await });
        let (first, second) = (first.await?, second.await?);
        let wins = usize::from(first.is_ok()) + usize::from(second.is_ok());
        assert_eq!(wins, 1, "round {round}: {first:?} / {second:?}");
        let loser = first.err().or(second.err()).ok_or("no loser")?;
        assert!(matches!(loser, StockError::OutOfStock { .. }), "{loser:?}");
    }
    Ok(())
}

async fn create(app: &RealApp, token: &str) -> Res<support::Reply> {
    app.call(post_json("/tasks", Some(token), &fetch())?).await
}

fn id_of(reply: &support::Reply) -> Res<String> {
    Ok(reply
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("no task id in {}", reply.body))?
        .to_owned())
}

#[tokio::test]
async fn delivered_task_commits_reservation() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    app.set_stock("blanket", 1).await?;
    let nurse = app.nurse_token().await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    let first = create(&app, &nurse).await?;
    assert!(first.status.is_success(), "{}", first.body);
    let task = id_of(&first)?;
    robot
        .next_of_type("task.assign", Duration::from_secs(3))
        .await?;
    let second = create(&app, &nurse).await?;
    assert_eq!(
        second.status,
        StatusCode::CONFLICT,
        "the reserved unit was taken twice"
    );
    let robot_id = "robot-r2".parse()?;
    let task_id: TaskId = task.parse()?;
    for state in [TaskState::EnRoute, TaskState::Delivered] {
        api(app
            .state
            .tasks
            .apply_robot_event(&robot_id, Uuid::new_v4(), &task_id, state, None)
            .await)?;
    }
    assert_eq!(app.stock("blanket").await?, 0);
    let third = create(&app, &nurse).await?;
    assert_eq!(third.status, StatusCode::CONFLICT);
    Ok(())
}

#[tokio::test]
async fn cancelled_task_releases_reservation() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 1).await?;
    let nurse = app.nurse_token().await?;
    let first = create(&app, &nurse).await?;
    assert!(first.status.is_success(), "{}", first.body);
    let task = id_of(&first)?;
    assert_eq!(create(&app, &nurse).await?.status, StatusCode::CONFLICT);
    let cancelled = app
        .call(post_json(
            &format!("/tasks/{task}/cancel"),
            Some(&nurse),
            &json!({}),
        )?)
        .await?;
    assert!(cancelled.status.is_success(), "{}", cancelled.body);
    let again = create(&app, &nurse).await?;
    assert!(again.status.is_success(), "{}", again.body);
    assert_eq!(app.stock("blanket").await?, 1);
    Ok(())
}
