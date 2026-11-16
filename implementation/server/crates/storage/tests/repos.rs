//! Happy-path checks of the SQLite repositories filled in the storage build-out.

use std::collections::BTreeSet;

use chrono::{TimeZone as _, Utc};
use domain::ports::{
    InventoryRepository as _, ScheduleRepository as _, SystemModeStore as _, TaskRepository as _,
    ZoneRepository as _,
};
use domain::{
    Actor, ApplyOutcome, DomainError, Page, RoundResult, ScheduleRecord, StockLedger as _,
    StockLevel, StoredSystemMode, SystemMode, SystemModeState, Task, TaskDraft, TaskFilter,
    TaskKind, TaskState, ZoneKind, ZoneRecord,
};
use storage::{
    Database, SqliteInventoryRepository, SqliteLedger, SqliteScheduleRepository,
    SqliteSystemModeStore, SqliteTaskRepository, SqliteZoneRepository,
};

type TestResult = Result<(), Box<dyn std::error::Error>>;

async fn database() -> Result<Database, Box<dyn std::error::Error>> {
    let db = Database::in_memory().await?;
    db.migrate().await?;
    Ok(db)
}

async fn stock(db: &Database, count: u32) -> Result<(), Box<dyn std::error::Error>> {
    SqliteInventoryRepository::new(db.clone())
        .upsert(&StockLevel {
            item: "blanket".parse()?,
            label: "Blanket".to_owned(),
            place: "supply-a".parse()?,
            count,
            low_threshold: 2,
            last_robot_count: None,
            last_robot_count_at: None,
            updated_at: Utc::now(),
        })
        .await?;
    Ok(())
}

#[tokio::test]
async fn inventory_adjust_refuses_negative() -> TestResult {
    let db = database().await?;
    stock(&db, 3).await?;
    let inventory = SqliteInventoryRepository::new(db);
    let item = "blanket".parse()?;
    assert_eq!(inventory.adjust(&item, -2).await?.count, 1);
    let err = inventory.adjust(&item, -5).await.err();
    assert!(matches!(err, Some(DomainError::InsufficientStock { .. })));
    Ok(())
}

#[tokio::test]
async fn ledger_reserve_commit() -> TestResult {
    let db = database().await?;
    stock(&db, 2).await?;
    let ledger = SqliteLedger::new(db.clone());
    let task = "t-1".parse()?;
    let item = "blanket".parse()?;
    let held = ledger.reserve(&task, &item, 2).await?;
    assert!(ledger.reserve(&task, &item, 1).await.is_err());
    ledger.commit(&held).await?;
    let level = SqliteInventoryRepository::new(db).get(&item).await?;
    assert_eq!(level.map(|l| l.count), Some(0));
    Ok(())
}

#[tokio::test]
async fn task_roundtrip_and_event_idempotent() -> TestResult {
    let db = database().await?;
    stock(&db, 2).await?;
    let tasks = SqliteTaskRepository::new(db);
    let at = Utc
        .with_ymd_and_hms(2026, 11, 16, 8, 0, 0)
        .single()
        .ok_or("time")?;
    let mut task = Task::new(
        "t-1".parse()?,
        TaskDraft {
            kind: TaskKind::Fetch,
            item: Some("blanket".parse()?),
            from: None,
            to: "room-1".parse()?,
            deadline: None,
        },
        Actor::User("u-nurse".parse()?),
        at,
    )?;
    tasks.insert(&task).await?;
    assert_eq!(tasks.get(task.id()).await?, Some(task.clone()));
    task.transition(
        TaskState::Failed,
        Some(domain::FailureReason::PathBlocked),
        at,
    )?;
    let event = uuid::Uuid::new_v4();
    let item = "blanket".parse()?;
    assert_eq!(
        tasks
            .apply_robot_event(event, &task, Some((&item, 1)))
            .await?,
        ApplyOutcome::Applied
    );
    assert_eq!(
        tasks
            .apply_robot_event(event, &task, Some((&item, 1)))
            .await?,
        ApplyOutcome::Duplicate
    );
    let page = Page::new(10, 0)?;
    let listed = tasks.list(&TaskFilter::default(), &page).await?;
    assert_eq!(listed.len(), 1);
    let active = TaskFilter {
        active_only: true,
        ..TaskFilter::default()
    };
    assert!(tasks.list(&active, &page).await?.is_empty());
    Ok(())
}

#[tokio::test]
async fn zones_bump_global_version() -> TestResult {
    let zones = SqliteZoneRepository::new(database().await?);
    let zone = ZoneRecord {
        id: "z-1".parse()?,
        name: "Quiet".to_owned(),
        kind: ZoneKind::Deaf,
        floor: 0,
        polygon: vec![[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        version: 1,
    };
    assert_eq!(zones.global_version().await?, 0);
    assert_eq!(zones.upsert(&zone).await?, 1);
    assert_eq!(zones.list().await?, vec![zone.clone()]);
    assert_eq!(zones.delete(&zone.id).await?, Some(2));
    assert_eq!(zones.delete(&zone.id).await?, None);
    Ok(())
}

#[tokio::test]
async fn schedule_claim_run_once() -> TestResult {
    let schedules = SqliteScheduleRepository::new(database().await?);
    let record = ScheduleRecord {
        id: "s-1".parse()?,
        name: "Morning".to_owned(),
        cron: "0 7 * * *".to_owned(),
        timezone: "Europe/Zurich".to_owned(),
        places: vec!["supply-a".parse()?],
        enabled: true,
        last_run: None,
        grace_s: 600,
        robot: None,
        last_result: RoundResult::Never,
        last_counts: Vec::new(),
    };
    schedules.upsert(&record).await?;
    assert_eq!(schedules.get(&record.id).await?, Some(record.clone()));
    let at = Utc::now();
    assert!(schedules.claim_run(&record.id, at).await?);
    assert!(!schedules.claim_run(&record.id, at).await?);
    Ok(())
}

#[tokio::test]
async fn system_mode_roundtrip() -> TestResult {
    let store = SqliteSystemModeStore::new(database().await?);
    assert_eq!(store.load().await?.state, SystemModeState::initial());
    let stored = StoredSystemMode {
        state: SystemModeState {
            mode: SystemMode::Emergency,
            since: Some(
                Utc.with_ymd_and_hms(2026, 11, 16, 8, 0, 0)
                    .single()
                    .ok_or("time")?,
            ),
            by: Some("Admin 1".to_owned()),
            reason: None,
        },
        paused_robots: BTreeSet::from(["r1".parse()?]),
    };
    store.save(&stored).await?;
    assert_eq!(store.load().await?, stored);
    Ok(())
}
