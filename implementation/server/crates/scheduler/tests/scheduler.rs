//! Task 17: the scheduler with a `FakeClock`, an in-memory schedule repository (whose
//! `claim_run` is atomic, like the SQL statement) and a recording task creator.
//!
//! Zurich is UTC+1 in winter (CET) and UTC+2 in summer (CEST). 2026-10-25 and 2027-03-28 are
//! the daylight-saving changes.

use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use chrono::{DateTime, TimeZone, Utc};
use domain::ports::ScheduleRepository;
use domain::{
    Clock, DomainError, FakeClock, PlaceId, RoundResult, ScheduleId, ScheduleRecord, TaskId,
};
use scheduler::{CronExpr, FiredJob, RunOutcome, SchedulerError, SchedulerService, TaskCreator};

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn utc(y: i32, mo: u32, d: u32, h: u32, mi: u32, s: u32) -> Result<DateTime<Utc>, BoxError> {
    Ok(Utc
        .with_ymd_and_hms(y, mo, d, h, mi, s)
        .single()
        .ok_or("bad test date")?)
}

#[derive(Default)]
struct MemoryRepo {
    rows: Mutex<BTreeMap<ScheduleId, ScheduleRecord>>,
}

fn store_failure() -> DomainError {
    DomainError::StoreUnavailable { what: "schedule" }
}

#[async_trait]
impl ScheduleRepository for MemoryRepo {
    async fn list(&self) -> Result<Vec<ScheduleRecord>, DomainError> {
        let rows = self.rows.lock().map_err(|_| store_failure())?;
        Ok(rows.values().cloned().collect())
    }
    async fn get(&self, id: &ScheduleId) -> Result<Option<ScheduleRecord>, DomainError> {
        let rows = self.rows.lock().map_err(|_| store_failure())?;
        Ok(rows.get(id).cloned())
    }
    async fn upsert(&self, schedule: &ScheduleRecord) -> Result<(), DomainError> {
        let mut rows = self.rows.lock().map_err(|_| store_failure())?;
        rows.insert(schedule.id.clone(), schedule.clone());
        Ok(())
    }
    async fn claim_run(
        &self,
        id: &ScheduleId,
        scheduled: DateTime<Utc>,
    ) -> Result<bool, DomainError> {
        let mut rows = self.rows.lock().map_err(|_| store_failure())?;
        let Some(row) = rows.get_mut(id) else {
            return Ok(false);
        };
        if row.last_run.is_some_and(|last| last >= scheduled) {
            return Ok(false);
        }
        row.last_run = Some(scheduled);
        Ok(true)
    }
}

#[derive(Default)]
struct RecordingCreator {
    created: Mutex<Vec<Vec<PlaceId>>>,
    missed: Mutex<Vec<(ScheduleId, DateTime<Utc>)>>,
}

impl RecordingCreator {
    fn created(&self) -> usize {
        self.created.lock().map_or(usize::MAX, |c| c.len())
    }
    fn missed(&self) -> Vec<(ScheduleId, DateTime<Utc>)> {
        self.missed.lock().map(|m| m.clone()).unwrap_or_default()
    }
}

#[async_trait]
impl TaskCreator for RecordingCreator {
    async fn create_restock_round(&self, places: &[PlaceId]) -> Result<TaskId, SchedulerError> {
        let mut created = self
            .created
            .lock()
            .map_err(|_| SchedulerError::Repository(store_failure()))?;
        created.push(places.to_vec());
        let id = format!("t-round-{}", created.len());
        id.parse().map_err(SchedulerError::Repository)
    }
    async fn report_missed(&self, schedule: &ScheduleId, scheduled_for: DateTime<Utc>) {
        if let Ok(mut missed) = self.missed.lock() {
            missed.push((schedule.clone(), scheduled_for));
        }
    }
}

struct Setup {
    service: SchedulerService,
    repo: Arc<MemoryRepo>,
    creator: Arc<RecordingCreator>,
    clock: Arc<FakeClock>,
}

/// A night round (`cron`, Zurich) whose last run is `last_run`, with the clock at `now`.
async fn setup(
    cron: &str,
    enabled: bool,
    last_run: DateTime<Utc>,
    now: DateTime<Utc>,
) -> Result<Setup, BoxError> {
    let repo = Arc::new(MemoryRepo::default());
    repo.upsert(&ScheduleRecord {
        id: "night-round".parse()?,
        name: "Night restock round".to_owned(),
        cron: cron.to_owned(),
        timezone: "Europe/Zurich".to_owned(),
        places: vec!["storeroom".parse()?],
        enabled,
        last_run: Some(last_run),
        grace_s: 1800,
        robot: None,
        last_result: RoundResult::Never,
        last_counts: Vec::new(),
    })
    .await?;
    let clock = Arc::new(FakeClock::new(now));
    let creator = Arc::new(RecordingCreator::default());
    let dyn_clock: Arc<dyn Clock> = clock.clone();
    let service = SchedulerService::new(repo.clone(), dyn_clock, creator.clone());
    Ok(Setup {
        service,
        repo,
        creator,
        clock,
    })
}

/// Runs one tick per minute from `from` to `to` (inclusive); returns every fired job.
async fn tick_every_minute(
    setup: &Setup,
    from: DateTime<Utc>,
    to: DateTime<Utc>,
) -> Result<Vec<FiredJob>, BoxError> {
    let mut fired = Vec::new();
    let mut at = from;
    while at <= to {
        setup.clock.set(at);
        fired.extend(setup.service.run_once().await?);
        at += chrono::Duration::minutes(1);
    }
    Ok(fired)
}

#[tokio::test]
async fn fires_at_0200_zurich_time() -> TestResult {
    let setup = setup(
        "0 2 * * *",
        true,
        utc(2026, 11, 13, 1, 0, 0)?,
        utc(2026, 11, 14, 0, 59, 30)?,
    )
    .await?;
    assert!(setup.service.run_once().await?.is_empty());
    setup.clock.set(utc(2026, 11, 14, 1, 0, 0)?);
    let fired = setup.service.run_once().await?;
    assert_eq!(fired.len(), 1);
    let job = fired.first().ok_or("no job")?;
    assert_eq!(job.scheduled_for, utc(2026, 11, 14, 1, 0, 0)?);
    assert!(matches!(job.outcome, RunOutcome::Created(_)));
    assert_eq!(setup.creator.created(), 1);
    Ok(())
}

#[tokio::test]
async fn does_not_fire_twice_on_two_ticks_in_the_same_minute() -> TestResult {
    let setup = setup(
        "0 2 * * *",
        true,
        utc(2026, 11, 13, 1, 0, 0)?,
        utc(2026, 11, 14, 1, 0, 0)?,
    )
    .await?;
    assert_eq!(setup.service.run_once().await?.len(), 1);
    setup.clock.set(utc(2026, 11, 14, 1, 0, 30)?);
    assert!(setup.service.run_once().await?.is_empty());
    assert_eq!(setup.creator.created(), 1);
    Ok(())
}

#[tokio::test]
async fn disabled_schedule_never_fires() -> TestResult {
    let setup = setup(
        "0 2 * * *",
        false,
        utc(2026, 11, 13, 1, 0, 0)?,
        utc(2026, 11, 14, 0, 58, 0)?,
    )
    .await?;
    let fired = tick_every_minute(
        &setup,
        utc(2026, 11, 14, 0, 58, 0)?,
        utc(2026, 11, 14, 1, 5, 0)?,
    )
    .await?;
    assert!(fired.is_empty());
    assert_eq!(setup.creator.created(), 0);
    assert!(setup.creator.missed().is_empty());
    Ok(())
}

/// 2027-03-28: Zurich jumps from 02:00 CET to 03:00 CEST, so 02:30 does not exist; the run
/// happens at the next valid minute, 03:00 CEST (01:00 UTC), once.
#[tokio::test]
async fn spring_forward_nonexistent_0230_fires_at_next_valid_minute_once() -> TestResult {
    let cron = CronExpr::parse("30 2 * * *")?;
    assert_eq!(
        cron.next_after(utc(2027, 3, 27, 1, 30, 0)?, chrono_tz::Europe::Zurich),
        Some(utc(2027, 3, 28, 1, 0, 0)?)
    );
    let setup = setup(
        "30 2 * * *",
        true,
        utc(2027, 3, 27, 1, 30, 0)?,
        utc(2027, 3, 28, 0, 50, 0)?,
    )
    .await?;
    let fired = tick_every_minute(
        &setup,
        utc(2027, 3, 28, 0, 50, 0)?,
        utc(2027, 3, 28, 2, 0, 0)?,
    )
    .await?;
    assert_eq!(fired.len(), 1, "{fired:?}");
    assert_eq!(
        fired.first().map(|j| j.scheduled_for),
        Some(utc(2027, 3, 28, 1, 0, 0)?)
    );
    Ok(())
}

/// 2026-10-25: Zurich goes from 03:00 CEST back to 02:00 CET, so 02:30 happens twice
/// (00:30 and 01:30 UTC); the run happens once.
#[tokio::test]
async fn fall_back_repeated_0230_fires_once() -> TestResult {
    let setup = setup(
        "30 2 * * *",
        true,
        utc(2026, 10, 24, 0, 30, 0)?,
        utc(2026, 10, 25, 0, 0, 0)?,
    )
    .await?;
    let fired = tick_every_minute(
        &setup,
        utc(2026, 10, 25, 0, 0, 0)?,
        utc(2026, 10, 25, 2, 30, 0)?,
    )
    .await?;
    assert_eq!(fired.len(), 1, "{fired:?}");
    assert_eq!(setup.creator.created(), 1);
    Ok(())
}

#[tokio::test]
async fn missed_run_within_grace_fires_once_on_startup() -> TestResult {
    let setup = setup(
        "0 2 * * *",
        true,
        utc(2026, 11, 13, 1, 0, 0)?,
        utc(2026, 11, 14, 1, 20, 0)?,
    )
    .await?;
    let fired = setup.service.run_once().await?;
    assert_eq!(fired.len(), 1);
    let job = fired.first().ok_or("no job")?;
    assert_eq!(job.scheduled_for, utc(2026, 11, 14, 1, 0, 0)?);
    assert!(matches!(job.outcome, RunOutcome::Created(_)));
    assert!(setup.service.run_once().await?.is_empty());
    assert_eq!(setup.creator.created(), 1);
    Ok(())
}

#[tokio::test]
async fn missed_run_beyond_grace_is_skipped_and_audited() -> TestResult {
    let setup = setup(
        "0 2 * * *",
        true,
        utc(2026, 11, 13, 1, 0, 0)?,
        utc(2026, 11, 14, 2, 0, 0)?,
    )
    .await?;
    let fired = setup.service.run_once().await?;
    assert_eq!(fired.len(), 1);
    assert_eq!(fired.first().map(|j| &j.outcome), Some(&RunOutcome::Missed));
    assert_eq!(setup.creator.created(), 0);
    assert_eq!(
        setup.creator.missed(),
        vec![("night-round".parse()?, utc(2026, 11, 14, 1, 0, 0)?)]
    );
    let row = setup
        .repo
        .get(&"night-round".parse()?)
        .await?
        .ok_or("schedule disappeared")?;
    assert_eq!(row.last_run, Some(utc(2026, 11, 14, 1, 0, 0)?));
    Ok(())
}

#[test]
fn invalid_cron_hour_error_names_the_field() -> TestResult {
    let err = CronExpr::parse("0 25 * * *")
        .err()
        .ok_or("hour 25 was accepted")?;
    assert_eq!(
        err.to_string(),
        "Field 'hour' has value 25; hours go from 0 to 23."
    );
    assert!(matches!(
        err,
        SchedulerError::InvalidCron { field: "hour", .. }
    ));
    Ok(())
}

// `two_services_sharing_a_database_fire_once` lives in `tests/scheduler_shared_db.rs` at the
// workspace root: it needs `storage::SqliteScheduleRepository` on a real database.
