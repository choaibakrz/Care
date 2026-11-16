//! `clinics(id, name, version, active, plan_json, updated_at)` (migration
//! `migrations/0100_clinics.sql`): the stored clinic plans of Task A4. At most one row is
//! active (partial unique index).

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use domain::ports::ClinicRepository;
use domain::{ClinicId, ClinicRecord, DomainError};
use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;

/// Clinic plans in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteClinicRepository {
    db: Database,
}

impl SqliteClinicRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteClinicRepository {
        SqliteClinicRepository { db }
    }
}

fn unavailable(_error: &sqlx::Error) -> DomainError {
    DomainError::StoreUnavailable { what: "clinic" }
}

fn corrupt(reason: &str) -> DomainError {
    DomainError::Corrupt {
        table: "clinics",
        reason: reason.to_owned(),
    }
}

fn record_of(row: &SqliteRow) -> Result<ClinicRecord, DomainError> {
    let id: String = row.try_get("id").map_err(|e| unavailable(&e))?;
    let version: i64 = row.try_get("version").map_err(|e| unavailable(&e))?;
    let active: i64 = row.try_get("active").map_err(|e| unavailable(&e))?;
    let updated: String = row.try_get("updated_at").map_err(|e| unavailable(&e))?;
    Ok(ClinicRecord {
        id: id.parse().map_err(|_| corrupt("id"))?,
        name: row.try_get("name").map_err(|e| unavailable(&e))?,
        version: u64::try_from(version).map_err(|_| corrupt("version"))?,
        active: active == 1,
        updated_at: DateTime::parse_from_rfc3339(&updated)
            .map_err(|_| corrupt("updated_at"))?
            .with_timezone(&Utc),
        plan_json: row.try_get("plan_json").map_err(|e| unavailable(&e))?,
        overlay_json: row.try_get("overlay_json").map_err(|e| unavailable(&e))?,
    })
}

#[async_trait]
impl ClinicRepository for SqliteClinicRepository {
    async fn list(&self) -> Result<Vec<ClinicRecord>, DomainError> {
        let rows = sqlx::query("SELECT id, name, version, active, plan_json, overlay_json, updated_at FROM clinics ORDER BY updated_at, id")
        .fetch_all(self.db.pool())
        .await
        .map_err(|e| unavailable(&e))?;
        rows.iter().map(record_of).collect()
    }
    async fn get(&self, id: &ClinicId) -> Result<Option<ClinicRecord>, DomainError> {
        let row = sqlx::query(
            "SELECT id, name, version, active, plan_json, overlay_json, updated_at FROM clinics WHERE id = ?",
        )
        .bind(id.to_string())
        .fetch_optional(self.db.pool())
        .await
        .map_err(|e| unavailable(&e))?;
        row.as_ref().map(record_of).transpose()
    }
    async fn active(&self) -> Result<Option<ClinicRecord>, DomainError> {
        let row = sqlx::query(
            "SELECT id, name, version, active, plan_json, overlay_json, updated_at FROM clinics WHERE active = 1",
        )
        .fetch_optional(self.db.pool())
        .await
        .map_err(|e| unavailable(&e))?;
        row.as_ref().map(record_of).transpose()
    }
    async fn insert(&self, record: &ClinicRecord) -> Result<(), DomainError> {
        let version = i64::try_from(record.version).map_err(|_| corrupt("version"))?;
        sqlx::query("INSERT INTO clinics (id, name, version, active, plan_json, overlay_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)")
        .bind(record.id.to_string())
        .bind(&record.name)
        .bind(version)
        .bind(i64::from(record.active))
        .bind(&record.plan_json)
        .bind(&record.overlay_json)
        .bind(record.updated_at.to_rfc3339())
        .execute(self.db.pool())
        .await
        .map_err(|error| match &error {
            sqlx::Error::Database(db) if db.is_unique_violation() => DomainError::Conflict {
                what: format!("Clinic plan '{}'", record.id),
            },
            _ => unavailable(&error),
        })?;
        Ok(())
    }
    async fn update(
        &self,
        id: &ClinicId,
        expected_version: u64,
        name: &str,
        plan_json: &str,
        overlay_json: &str,
        at: DateTime<Utc>,
    ) -> Result<ClinicRecord, DomainError> {
        let expected = i64::try_from(expected_version).map_err(|_| corrupt("version"))?;
        let row = sqlx::query("UPDATE clinics SET name = ?, plan_json = ?, overlay_json = ?, updated_at = ?, version = version + 1 \
             WHERE id = ? AND version = ? RETURNING id, name, version, active, plan_json, overlay_json, updated_at")
        .bind(name)
        .bind(plan_json)
        .bind(overlay_json)
        .bind(at.to_rfc3339())
        .bind(id.to_string())
        .bind(expected)
        .fetch_optional(self.db.pool())
        .await
        .map_err(|e| unavailable(&e))?;
        if let Some(row) = row {
            return record_of(&row);
        }
        match self.get(id).await? {
            None => Err(DomainError::NotFound {
                what: format!("Clinic plan '{id}'"),
            }),
            Some(current) => Err(DomainError::VersionConflict {
                what: format!("Clinic plan '{id}'"),
                expected: expected_version,
                current: current.version,
            }),
        }
    }
    async fn activate(
        &self,
        id: &ClinicId,
        at: DateTime<Utc>,
    ) -> Result<ClinicRecord, DomainError> {
        let mut tx = self.db.pool().begin().await.map_err(|e| unavailable(&e))?;
        sqlx::query("UPDATE clinics SET active = 0 WHERE active = 1 AND id <> ?")
            .bind(id.to_string())
            .execute(&mut *tx)
            .await
            .map_err(|e| unavailable(&e))?;
        let row = sqlx::query("UPDATE clinics SET active = 1, updated_at = ? WHERE id = ? RETURNING id, name, version, active, plan_json, overlay_json, updated_at")
        .bind(at.to_rfc3339())
        .bind(id.to_string())
        .fetch_optional(&mut *tx)
        .await
        .map_err(|e| unavailable(&e))?;
        let Some(row) = row else {
            return Err(DomainError::NotFound {
                what: format!("Clinic plan '{id}'"),
            });
        };
        let record = record_of(&row)?;
        tx.commit().await.map_err(|e| unavailable(&e))?;
        Ok(record)
    }
    async fn delete(&self, id: &ClinicId) -> Result<bool, DomainError> {
        let done = sqlx::query("DELETE FROM clinics WHERE id = ? AND active = 0")
            .bind(id.to_string())
            .execute(self.db.pool())
            .await
            .map_err(|e| unavailable(&e))?;
        if done.rows_affected() == 1 {
            return Ok(true);
        }
        match self.get(id).await? {
            Some(_) => Err(DomainError::Conflict {
                what: format!("Clinic plan '{id}' is active; it"),
            }),
            None => Ok(false),
        }
    }
}
