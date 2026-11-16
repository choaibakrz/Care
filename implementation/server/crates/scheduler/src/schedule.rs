//! Schedules and their runs.

use std::time::Duration;

use chrono::{DateTime, Utc};
use chrono_tz::Tz;
use domain::{PlaceId, RoundResult, ScheduleId, ScheduleRecord, TaskId};

use crate::cron::CronExpr;
use crate::error::SchedulerError;

/// How late a missed run may still fire (30 min).
pub const DEFAULT_GRACE: Duration = Duration::from_mins(30);

/// What a schedule does.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ScheduledJob {
    /// Create a restock round over these places.
    RestockRound {
        /// Shelves to visit.
        places: Vec<PlaceId>,
    },
}

/// A validated schedule.
#[derive(Debug, Clone, PartialEq)]
pub struct Schedule {
    /// Id.
    pub id: ScheduleId,
    /// Name.
    pub name: String,
    /// When.
    pub cron: CronExpr,
    /// Time zone (default `Europe/Zurich`).
    pub timezone: Tz,
    /// What.
    pub job: ScheduledJob,
    /// Whether it runs.
    pub enabled: bool,
    /// Last fired scheduled time.
    pub last_run: Option<DateTime<Utc>>,
    /// Grace for missed runs.
    pub grace: Duration,
}

impl Schedule {
    /// Validates a stored record.
    ///
    /// # Errors
    /// `InvalidCron`, `FieldCount`, `UnknownTimezone`, `InvalidSchedule` (no places).
    pub fn from_record(record: ScheduleRecord) -> Result<Schedule, SchedulerError> {
        let cron = CronExpr::parse(&record.cron)?;
        let timezone: Tz =
            record
                .timezone
                .parse()
                .map_err(|_| SchedulerError::UnknownTimezone {
                    tz: record.timezone.clone(),
                })?;
        if record.places.is_empty() {
            return Err(SchedulerError::InvalidSchedule {
                schedule: record.id,
                reason: "a restock round needs at least one place",
            });
        }
        Ok(Schedule {
            id: record.id,
            name: record.name,
            cron,
            timezone,
            job: ScheduledJob::RestockRound {
                places: record.places,
            },
            enabled: record.enabled,
            last_run: record.last_run,
            grace: Duration::from_secs(record.grace_s),
        })
    }

    /// The record to store.
    #[must_use]
    pub fn to_record(&self) -> ScheduleRecord {
        let ScheduledJob::RestockRound { places } = &self.job;
        // The robot and the last round's result are not part of `Schedule`; the stored row
        // keeps them (callers that update a row start from the stored record).
        ScheduleRecord {
            id: self.id.clone(),
            name: self.name.clone(),
            cron: self.cron.as_str().to_owned(),
            timezone: self.timezone.name().to_owned(),
            places: places.clone(),
            enabled: self.enabled,
            last_run: self.last_run,
            grace_s: self.grace.as_secs(),
            robot: None,
            last_result: RoundResult::default(),
            last_counts: Vec::new(),
        }
    }

    /// The next run after `after`.
    #[must_use]
    pub fn next_run(&self, after: DateTime<Utc>) -> Option<DateTime<Utc>> {
        self.cron.next_after(after, self.timezone)
    }
}

/// What happened to one due run.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RunOutcome {
    /// The task was created.
    Created(TaskId),
    /// Older than the grace: skipped and reported as `ScheduleMissed`.
    Missed,
}

/// One due run handled by `run_once`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FiredJob {
    /// Schedule.
    pub schedule: ScheduleId,
    /// Scheduled time.
    pub scheduled_for: DateTime<Utc>,
    /// Outcome.
    pub outcome: RunOutcome,
}
