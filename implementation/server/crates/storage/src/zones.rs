//! `zones(id, kind, floor, polygon_json, version)` and the global zone-set version.

use async_trait::async_trait;
use domain::ports::ZoneRepository;
use domain::{DomainError, ZoneId, ZoneRecord};

use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;
use crate::sql::{corrupt, db, enum_text, parse_enum, parse_id, to_u32};

fn zone_of(row: &SqliteRow) -> Result<ZoneRecord, DomainError> {
    let id: String = row.try_get("id").map_err(db)?;
    let kind: String = row.try_get("kind").map_err(db)?;
    let polygon: String = row.try_get("polygon_json").map_err(db)?;
    let version: i64 = row.try_get("version").map_err(db)?;
    Ok(ZoneRecord {
        id: parse_id("zones", &id)?,
        name: row.try_get("name").map_err(db)?,
        kind: parse_enum("zones", &kind)?,
        floor: row.try_get("floor").map_err(db)?,
        polygon: serde_json::from_str(&polygon).map_err(|_| corrupt("zones", "polygon"))?,
        version: to_u32("zones", version)?,
    })
}

/// Bumps the global version inside the caller's transaction and returns it.
async fn bump(conn: &mut sqlx::SqliteConnection) -> Result<u64, DomainError> {
    let version: i64 = sqlx::query_scalar(
        "INSERT INTO zone_set (id, version) VALUES (1, 1) \
         ON CONFLICT(id) DO UPDATE SET version = version + 1 RETURNING version",
    )
    .fetch_one(conn)
    .await
    .map_err(db)?;
    u64::try_from(version).map_err(|_| corrupt("zone_set", "version"))
}

/// Zones in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteZoneRepository {
    db: Database,
}

impl SqliteZoneRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteZoneRepository {
        SqliteZoneRepository { db }
    }
}

#[async_trait]
impl ZoneRepository for SqliteZoneRepository {
    async fn list(&self) -> Result<Vec<ZoneRecord>, DomainError> {
        let rows = sqlx::query(
            "SELECT id, name, kind, floor, polygon_json, version FROM zones ORDER BY id",
        )
        .fetch_all(self.db.pool())
        .await
        .map_err(db)?;
        rows.iter().map(zone_of).collect()
    }
    async fn upsert(&self, zone: &ZoneRecord) -> Result<u64, DomainError> {
        let polygon =
            serde_json::to_string(&zone.polygon).map_err(|_| corrupt("zones", "polygon"))?;
        let mut tx = self.db.pool().begin().await.map_err(db)?;
        sqlx::query(
            "INSERT OR REPLACE INTO zones (id, name, kind, floor, polygon_json, version) \
             VALUES (?, ?, ?, ?, ?, ?)",
        )
        .bind(zone.id.as_str())
        .bind(&zone.name)
        .bind(enum_text(&zone.kind)?)
        .bind(zone.floor)
        .bind(polygon)
        .bind(i64::from(zone.version))
        .execute(&mut *tx)
        .await
        .map_err(db)?;
        let version = bump(&mut tx).await?;
        tx.commit().await.map_err(db)?;
        Ok(version)
    }
    async fn delete(&self, id: &ZoneId) -> Result<Option<u64>, DomainError> {
        let mut tx = self.db.pool().begin().await.map_err(db)?;
        let done = sqlx::query("DELETE FROM zones WHERE id = ?")
            .bind(id.as_str())
            .execute(&mut *tx)
            .await
            .map_err(db)?;
        if done.rows_affected() == 0 {
            return Ok(None);
        }
        let version = bump(&mut tx).await?;
        tx.commit().await.map_err(db)?;
        Ok(Some(version))
    }
    async fn global_version(&self) -> Result<u64, DomainError> {
        let version: Option<i64> = sqlx::query_scalar("SELECT version FROM zone_set WHERE id = 1")
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        u64::try_from(version.unwrap_or(0)).map_err(|_| corrupt("zone_set", "version"))
    }
}
