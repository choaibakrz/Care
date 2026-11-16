//! The scheduler loop.

use std::sync::Arc;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use domain::ports::ScheduleRepository;
use domain::{Clock, PlaceId, ScheduleId, TaskId};
use tokio::task::JoinHandle;

use crate::error::SchedulerError;
use crate::schedule::{FiredJob, RunOutcome, Schedule, ScheduledJob};

/// Creates the tasks a schedule asks for (implemented by the task service).
#[async_trait]
pub trait TaskCreator: Send + Sync {
    /// Creates one restock round over `places`.
    ///
    /// # Errors
    /// `TaskCreation` when the task service refuses.
    async fn create_restock_round(&self, places: &[PlaceId]) -> Result<TaskId, SchedulerError>;

    /// Reports a run skipped because it was older than the grace; the implementer writes
    /// `ScheduleMissed` to the journal (this crate does not depend on `audit`).
    async fn report_missed(&self, schedule: &ScheduleId, scheduled_for: DateTime<Utc>);
}

/// Fires due schedules, at most once per scheduled time even with two servers.
pub struct SchedulerService {
    repo: Arc<dyn ScheduleRepository>,
    clock: Arc<dyn Clock>,
    creator: Arc<dyn TaskCreator>,
}

impl SchedulerService {
    /// A scheduler.
    #[must_use]
    pub fn new(
        repo: Arc<dyn ScheduleRepository>,
        clock: Arc<dyn Clock>,
        creator: Arc<dyn TaskCreator>,
    ) -> SchedulerService {
        SchedulerService {
            repo,
            clock,
            creator,
        }
    }

    /// One tick: claims and fires every due run; older than grace becomes `Missed`.
    ///
    /// # Errors
    /// `Repository` when schedules cannot be read.
    pub async fn run_once(&self) -> Result<Vec<FiredJob>, SchedulerError> {
        /// Upper bound of due runs handled per schedule and tick (a long outage).
        const MAX_RUNS_PER_TICK: usize = 1000;
        let now = self.clock.now();
        let mut fired = Vec::new();
        for record in self.repo.list().await? {
            let schedule = match Schedule::from_record(record) {
                Ok(schedule) => schedule,
                Err(error) => {
                    tracing::warn!(%error, "skipping an invalid schedule");
                    continue;
                }
            };
            if !schedule.enabled {
                continue;
            }
            let grace = chrono::Duration::from_std(schedule.grace).unwrap_or(chrono::Duration::MAX);
            let mut cursor = schedule
                .last_run
                .unwrap_or_else(|| now.checked_sub_signed(grace).unwrap_or(now));
            for _ in 0..MAX_RUNS_PER_TICK {
                let Some(due) = schedule.next_run(cursor) else {
                    break;
                };
                if due > now {
                    break;
                }
                cursor = due;
                if !self.repo.claim_run(&schedule.id, due).await? {
                    continue;
                }
                let outcome = if now.signed_duration_since(due) > grace {
                    self.creator.report_missed(&schedule.id, due).await;
                    RunOutcome::Missed
                } else {
                    let ScheduledJob::RestockRound { places } = &schedule.job;
                    match self.creator.create_restock_round(places).await {
                        Ok(task) => RunOutcome::Created(task),
                        Err(error) => {
                            tracing::warn!(%error, schedule = %schedule.id, "scheduled run failed");
                            continue;
                        }
                    }
                };
                fired.push(FiredJob {
                    schedule: schedule.id.clone(),
                    scheduled_for: due,
                    outcome,
                });
            }
        }
        Ok(fired)
    }

    /// Ticks every second until aborted.
    #[must_use]
    pub fn spawn(self: Arc<Self>) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_secs(1));
            interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
            loop {
                interval.tick().await;
                if let Err(error) = self.run_once().await {
                    tracing::warn!(%error, "scheduler tick failed");
                }
            }
        })
    }
}
