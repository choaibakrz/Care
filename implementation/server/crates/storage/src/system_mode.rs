//! `system_mode(id = 1, mode, since, by_label, reason)` and `system_mode_paused(robot_id)`:
//! the emergency switch (Task A8, fill E1, ruling R26). One row and the robots the server
//! paused, so a restart keeps an emergency on and resumes only those robots on exit.

use async_trait::async_trait;
use domain::ports::SystemModeStore;
use domain::{DomainError, StoredSystemMode};

use domain::{RobotId, SystemModeState};
use sqlx::Row as _;

use crate::pool::Database;
use crate::sql::{db, enum_text, parse_enum, parse_id, parse_opt_ts, ts};

/// The emergency switch in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteSystemModeStore {
    db: Database,
}

impl SqliteSystemModeStore {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteSystemModeStore {
        SqliteSystemModeStore { db }
    }
}

#[async_trait]
impl SystemModeStore for SqliteSystemModeStore {
    async fn load(&self) -> Result<StoredSystemMode, DomainError> {
        let row = sqlx::query("SELECT mode, since, by_label, reason FROM system_mode WHERE id = 1")
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        let state = match row {
            None => SystemModeState::initial(),
            Some(row) => {
                let mode: String = row.try_get("mode").map_err(db)?;
                let since: Option<String> = row.try_get("since").map_err(db)?;
                SystemModeState {
                    mode: parse_enum("system_mode", &mode)?,
                    since: parse_opt_ts("system_mode", since)?,
                    by: row.try_get("by_label").map_err(db)?,
                    reason: row.try_get("reason").map_err(db)?,
                }
            }
        };
        let ids: Vec<String> = sqlx::query_scalar("SELECT robot_id FROM system_mode_paused")
            .fetch_all(self.db.pool())
            .await
            .map_err(db)?;
        let paused_robots = ids
            .iter()
            .map(|id| parse_id::<RobotId>("system_mode_paused", id))
            .collect::<Result<_, _>>()?;
        Ok(StoredSystemMode {
            state,
            paused_robots,
        })
    }
    async fn save(&self, stored: &StoredSystemMode) -> Result<(), DomainError> {
        // `since` is NOT NULL in the table; a never-switched state is stored with now.
        let since = ts(stored.state.since.unwrap_or_else(chrono::Utc::now));
        let mut tx = self.db.pool().begin().await.map_err(db)?;
        sqlx::query(
            "INSERT OR REPLACE INTO system_mode (id, mode, since, by_label, reason) \
             VALUES (1, ?, ?, ?, ?)",
        )
        .bind(enum_text(&stored.state.mode)?)
        .bind(since)
        .bind(stored.state.by.as_deref())
        .bind(stored.state.reason.as_deref())
        .execute(&mut *tx)
        .await
        .map_err(db)?;
        sqlx::query("DELETE FROM system_mode_paused")
            .execute(&mut *tx)
            .await
            .map_err(db)?;
        for robot in &stored.paused_robots {
            sqlx::query("INSERT INTO system_mode_paused (robot_id) VALUES (?)")
                .bind(robot.as_str())
                .execute(&mut *tx)
                .await
                .map_err(db)?;
        }
        tx.commit().await.map_err(db)?;
        Ok(())
    }
}
