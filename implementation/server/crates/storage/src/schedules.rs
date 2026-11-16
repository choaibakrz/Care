//! `schedules`, with the single-statement run claim.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use domain::ports::ScheduleRepository;
use domain::{DomainError, ScheduleId, ScheduleRecord};

use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;
use crate::sql::{corrupt, db, enum_text, parse_enum, parse_id, parse_opt_ts, ts};

const COLUMNS: &str = "SELECT id, name, cron, timezone, places_json, enabled, last_run, grace_s, \
     robot, last_result, last_counts_json FROM schedules";

fn schedule_of(row: &SqliteRow) -> Result<ScheduleRecord, DomainError> {
    let id: String = row.try_get("id").map_err(db)?;
    let places: String = row.try_get("places_json").map_err(db)?;
    let enabled: i64 = row.try_get("enabled").map_err(db)?;
    let last_run: Option<String> = row.try_get("last_run").map_err(db)?;
    let grace: i64 = row.try_get("grace_s").map_err(db)?;
    let robot: Option<String> = row.try_get("robot").map_err(db)?;
    let result: String = row.try_get("last_result").map_err(db)?;
    let counts: String = row.try_get("last_counts_json").map_err(db)?;
    Ok(ScheduleRecord {
        id: parse_id("schedules", &id)?,
        name: row.try_get("name").map_err(db)?,
        cron: row.try_get("cron").map_err(db)?,
        timezone: row.try_get("timezone").map_err(db)?,
        places: serde_json::from_str(&places).map_err(|_| corrupt("schedules", "places"))?,
        enabled: enabled != 0,
        last_run: parse_opt_ts("schedules", last_run)?,
        grace_s: u64::try_from(grace).map_err(|_| corrupt("schedules", "grace_s"))?,
        robot: robot.map(|r| parse_id("schedules", &r)).transpose()?,
        last_result: parse_enum("schedules", &result)?,
        last_counts: serde_json::from_str(&counts)
            .map_err(|_| corrupt("schedules", "last_counts"))?,
    })
}

/// Schedules in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteScheduleRepository {
    db: Database,
}

impl SqliteScheduleRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteScheduleRepository {
        SqliteScheduleRepository { db }
    }
}

#[async_trait]
impl ScheduleRepository for SqliteScheduleRepository {
    async fn list(&self) -> Result<Vec<ScheduleRecord>, DomainError> {
        let rows = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} ORDER BY id")))
            .fetch_all(self.db.pool())
            .await
            .map_err(db)?;
        rows.iter().map(schedule_of).collect()
    }
    async fn get(&self, id: &ScheduleId) -> Result<Option<ScheduleRecord>, DomainError> {
        let row = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} WHERE id = ?")))
            .bind(id.as_str())
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        row.as_ref().map(schedule_of).transpose()
    }
    async fn upsert(&self, schedule: &ScheduleRecord) -> Result<(), DomainError> {
        let places =
            serde_json::to_string(&schedule.places).map_err(|_| corrupt("schedules", "places"))?;
        let counts = serde_json::to_string(&schedule.last_counts)
            .map_err(|_| corrupt("schedules", "last_counts"))?;
        let grace = i64::try_from(schedule.grace_s).map_err(|_| corrupt("schedules", "grace_s"))?;
        sqlx::query(
            "INSERT OR REPLACE INTO schedules (id, name, cron, timezone, places_json, enabled, \
             last_run, grace_s, robot, last_result, last_counts_json) \
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(schedule.id.as_str())
        .bind(&schedule.name)
        .bind(&schedule.cron)
        .bind(&schedule.timezone)
        .bind(places)
        .bind(i64::from(schedule.enabled))
        .bind(schedule.last_run.map(ts))
        .bind(grace)
        .bind(schedule.robot.as_ref().map(|r| r.as_str().to_owned()))
        .bind(enum_text(&schedule.last_result)?)
        .bind(counts)
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        Ok(())
    }
    async fn claim_run(
        &self,
        id: &ScheduleId,
        scheduled: DateTime<Utc>,
    ) -> Result<bool, DomainError> {
        let at = ts(scheduled);
        let claimed: Option<String> = sqlx::query_scalar(
            "UPDATE schedules SET last_run = ? WHERE id = ? AND (last_run IS NULL OR last_run < ?) \
             RETURNING id",
        )
        .bind(&at)
        .bind(id.as_str())
        .bind(&at)
        .fetch_optional(self.db.pool())
        .await
        .map_err(db)?;
        Ok(claimed.is_some())
    }
}
