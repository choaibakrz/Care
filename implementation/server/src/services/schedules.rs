//! Real `ScheduleService`.

use std::sync::Arc;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use chrono::{DateTime, Utc};
use domain::ports::{ScheduleRecord, ScheduleRepository};
use domain::{Clock, ScheduleId};
use scheduler::{Schedule, SchedulerService};
use security::ClientIdentity;

use super::ScheduleService;
use crate::dto::{SchedulePatch, ScheduleView};
use crate::error::ApiError;

/// The real schedule service.
pub struct RealScheduleService {
    repo: Arc<dyn ScheduleRepository>,
    scheduler: Arc<SchedulerService>,
    journal: Journal,
    clock: Arc<dyn Clock>,
}

impl RealScheduleService {
    /// A service.
    #[must_use]
    pub fn new(
        repo: Arc<dyn ScheduleRepository>,
        scheduler: Arc<SchedulerService>,
        journal: Journal,
        clock: Arc<dyn Clock>,
    ) -> RealScheduleService {
        RealScheduleService {
            repo,
            scheduler,
            journal,
            clock,
        }
    }
}

#[async_trait]
impl ScheduleService for RealScheduleService {
    async fn list(&self) -> Result<Vec<ScheduleView>, ApiError> {
        let now = self.clock.now();
        self.repo
            .list()
            .await?
            .into_iter()
            .map(|record| view(record, now))
            .collect()
    }
    async fn update(
        &self,
        actor: &ClientIdentity,
        id: &ScheduleId,
        patch: SchedulePatch,
    ) -> Result<ScheduleView, ApiError> {
        let mut record = self
            .repo
            .get(id)
            .await?
            .ok_or_else(|| ApiError::not_found("Schedule", id.as_str()))?;
        if let Some(enabled) = patch.enabled {
            record.enabled = enabled;
        }
        if let Some(time) = &patch.time {
            let (hours, minutes) = parse_time(time)
                .ok_or_else(|| ApiError::invalid_input("time", "is not a valid HH:MM time"))?;
            record.cron = format!("{minutes} {hours} * * *");
        }
        if let Some(robot) = patch.robot_id {
            record.robot = Some(robot);
        }
        // Validates the cron, time zone and places.
        Schedule::from_record(record.clone())?;
        self.repo.upsert(&record).await?;
        self.journal
            .append(
                Severity::Critical,
                Category::Audit,
                actor.verified.subject_id.clone(),
                RecordBody::ScheduleChanged {
                    schedule: record.id.clone(),
                    enabled: record.enabled,
                },
                Some(self.clock.now()),
            )
            .await?;
        // The scheduler reads the repository on each tick: nothing to tell it.
        let _ = &self.scheduler;
        view(record, self.clock.now())
    }
}

/// `HH:MM` as (hours, minutes).
fn parse_time(time: &str) -> Option<(u8, u8)> {
    let (hours, minutes) = time.split_once(':')?;
    let hours: u8 = hours.parse().ok()?;
    let minutes: u8 = minutes.parse().ok()?;
    (hours < 24 && minutes < 60 && time.len() == 5).then_some((hours, minutes))
}

/// The view of a stored schedule: `time` from its daily cron `MM HH * * *`.
fn view(record: ScheduleRecord, now: DateTime<Utc>) -> Result<ScheduleView, ApiError> {
    let schedule = Schedule::from_record(record.clone())?;
    let mut fields = record.cron.split_whitespace();
    let time = match (
        fields.next().and_then(|m| m.parse::<u8>().ok()),
        fields.next().and_then(|h| h.parse::<u8>().ok()),
    ) {
        (Some(minutes), Some(hours)) => format!("{hours:02}:{minutes:02}"),
        _ => record.cron.clone(),
    };
    Ok(ScheduleView {
        id: record.id,
        label: record.name,
        enabled: record.enabled,
        time,
        robot_id: record.robot,
        last_run: record.last_run,
        last_result: record.last_result,
        last_counts: record.last_counts,
        timezone: record.timezone,
        next_run: schedule.next_run(now),
    })
}
