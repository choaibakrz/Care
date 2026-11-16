//! `devices(id, user_id nullable, registered_at)`.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use domain::ports::DeviceRepository;
use domain::{DeviceId, DeviceRecord, DomainError, UserId};

use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;
use crate::sql::{db, parse_id, parse_ts, ts};

fn device_of(row: &SqliteRow) -> Result<DeviceRecord, DomainError> {
    let id: String = row.try_get("id").map_err(db)?;
    let user: Option<String> = row.try_get("user_id").map_err(db)?;
    let at: String = row.try_get("registered_at").map_err(db)?;
    Ok(DeviceRecord {
        id: parse_id("devices", &id)?,
        user_id: user.map(|u| parse_id("devices", &u)).transpose()?,
        registered_at: parse_ts("devices", &at)?,
    })
}

/// Devices in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteDeviceRepository {
    db: Database,
}

impl SqliteDeviceRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteDeviceRepository {
        SqliteDeviceRepository { db }
    }
}

#[async_trait]
impl DeviceRepository for SqliteDeviceRepository {
    async fn register(
        &self,
        device: &DeviceId,
        user: Option<&UserId>,
        at: DateTime<Utc>,
    ) -> Result<DeviceRecord, DomainError> {
        sqlx::query(
            "INSERT INTO devices (id, user_id, registered_at) VALUES (?, ?, ?)              ON CONFLICT(id) DO UPDATE SET user_id = excluded.user_id",
        )
        .bind(device.as_str())
        .bind(user.map(UserId::as_str))
        .bind(ts(at))
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        self.find(device)
            .await?
            .ok_or_else(|| DomainError::NotFound {
                what: format!("Device '{device}'"),
            })
    }
    async fn find(&self, id: &DeviceId) -> Result<Option<DeviceRecord>, DomainError> {
        let row = sqlx::query("SELECT id, user_id, registered_at FROM devices WHERE id = ?")
            .bind(id.as_str())
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        row.as_ref().map(device_of).transpose()
    }
}
