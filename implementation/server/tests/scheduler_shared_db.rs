//! Task 17: two scheduler services sharing one `SQLite` database fire a run once. The claim
//! is one SQL statement (`UPDATE … WHERE last_run < $scheduled RETURNING`), so this test runs
//! on the real repository, not on an in-memory double.

mod support;

use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use chrono::{DateTime, TimeZone, Utc};
use domain::ports::ScheduleRepository as _;
use domain::{Clock, FakeClock, PlaceId, RoundResult, ScheduleId, ScheduleRecord, TaskId};
use scheduler::{SchedulerError, SchedulerService, TaskCreator};
use storage::{Database, SqliteScheduleRepository};
use support::{Res, TestResult};

fn utc(y: i32, mo: u32, d: u32, h: u32, mi: u32) -> Res<DateTime<Utc>> {
    Ok(Utc
        .with_ymd_and_hms(y, mo, d, h, mi, 0)
        .single()
        .ok_or("bad test date")?)
}

#[derive(Default)]
struct CountingCreator {
    created: Mutex<u32>,
}

impl CountingCreator {
    fn created(&self) -> u32 {
        self.created.lock().map_or(u32::MAX, |c| *c)
    }
}

#[async_trait]
impl TaskCreator for CountingCreator {
    async fn create_restock_round(&self, _places: &[PlaceId]) -> Result<TaskId, SchedulerError> {
        let mut created = self.created.lock().map_err(|_| {
            SchedulerError::Repository(domain::DomainError::StoreUnavailable { what: "test" })
        })?;
        *created += 1;
        format!("t-round-{created}")
            .parse()
            .map_err(SchedulerError::Repository)
    }
    async fn report_missed(&self, _schedule: &ScheduleId, _scheduled_for: DateTime<Utc>) {}
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn two_services_sharing_a_database_fire_once() -> TestResult {
    let db = Database::in_memory().await?;
    db.migrate().await?;
    let first_repo = Arc::new(SqliteScheduleRepository::new(db.clone()));
    let second_repo = Arc::new(SqliteScheduleRepository::new(db));
    first_repo
        .upsert(&ScheduleRecord {
            id: "night-round".parse()?,
            name: "Night restock round".to_owned(),
            cron: "0 2 * * *".to_owned(),
            timezone: "Europe/Zurich".to_owned(),
            places: vec!["storeroom".parse()?],
            enabled: true,
            last_run: Some(utc(2026, 11, 13, 1, 0)?),
            grace_s: 1800,
            robot: None,
            last_result: RoundResult::Never,
            last_counts: Vec::new(),
        })
        .await?;
    // 02:00 Zurich (CET) is 01:00 UTC.
    let clock: Arc<dyn Clock> = Arc::new(FakeClock::new(utc(2026, 11, 14, 1, 0)?));
    let (a_creator, b_creator) = (
        Arc::new(CountingCreator::default()),
        Arc::new(CountingCreator::default()),
    );
    let a = SchedulerService::new(first_repo, clock.clone(), a_creator.clone());
    let b = SchedulerService::new(second_repo, clock, b_creator.clone());
    let (fired_a, fired_b) = tokio::join!(a.run_once(), b.run_once());
    assert_eq!(fired_a?.len() + fired_b?.len(), 1);
    assert_eq!(a_creator.created() + b_creator.created(), 1);
    Ok(())
}
