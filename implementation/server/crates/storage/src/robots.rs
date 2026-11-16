//! `robots(id, name, role_card, simulated, key_hash)` and `robot_last_fix`.
//!
//! The only position persistence in the server, and it takes robot types only: no tablet
//! position can reach a repository.

use async_trait::async_trait;
use domain::ports::RobotRepository;
use domain::{DomainError, RobotFix, RobotId, RobotRecord};

use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;
use crate::sql::{db, parse_id, parse_ts, ts};

const COLUMNS: &str = "SELECT id, name, role_card, simulated, key_hash FROM robots";

fn robot_of(row: &SqliteRow) -> Result<RobotRecord, DomainError> {
    let id: String = row.try_get("id").map_err(db)?;
    let simulated: i64 = row.try_get("simulated").map_err(db)?;
    Ok(RobotRecord {
        id: parse_id("robots", &id)?,
        name: row.try_get("name").map_err(db)?,
        role_card: row.try_get("role_card").map_err(db)?,
        simulated: simulated != 0,
        key_hash: row.try_get("key_hash").map_err(db)?,
    })
}

/// Robots in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteRobotRepository {
    db: Database,
}

impl SqliteRobotRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteRobotRepository {
        SqliteRobotRepository { db }
    }
}

#[async_trait]
impl RobotRepository for SqliteRobotRepository {
    async fn list(&self) -> Result<Vec<RobotRecord>, DomainError> {
        let rows = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} ORDER BY id")))
            .fetch_all(self.db.pool())
            .await
            .map_err(db)?;
        rows.iter().map(robot_of).collect()
    }
    async fn find(&self, id: &RobotId) -> Result<Option<RobotRecord>, DomainError> {
        let row = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} WHERE id = ?")))
            .bind(id.as_str())
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        row.as_ref().map(robot_of).transpose()
    }
    async fn upsert(&self, robot: &RobotRecord) -> Result<(), DomainError> {
        sqlx::query(
            "INSERT OR REPLACE INTO robots (id, name, role_card, simulated, key_hash) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(robot.id.as_str())
        .bind(&robot.name)
        .bind(&robot.role_card)
        .bind(i64::from(robot.simulated))
        .bind(&robot.key_hash)
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        Ok(())
    }
    async fn save_last_fix(&self, robot: &RobotId, fix: &RobotFix) -> Result<(), DomainError> {
        sqlx::query(
            "INSERT OR REPLACE INTO robot_last_fix (robot_id, floor, x, y, heading_rad, at) VALUES (?, ?, ?, ?, ?, ?)",
        )
        .bind(robot.as_str())
        .bind(fix.floor)
        .bind(fix.x)
        .bind(fix.y)
        .bind(fix.heading_rad)
        .bind(ts(fix.at))
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        Ok(())
    }
    async fn last_fix(&self, robot: &RobotId) -> Result<Option<RobotFix>, DomainError> {
        let row = sqlx::query(
            "SELECT floor, x, y, heading_rad, at FROM robot_last_fix WHERE robot_id = ?",
        )
        .bind(robot.as_str())
        .fetch_optional(self.db.pool())
        .await
        .map_err(db)?;
        let Some(row) = row else {
            return Ok(None);
        };
        let at: String = row.try_get("at").map_err(db)?;
        Ok(Some(RobotFix {
            floor: row.try_get("floor").map_err(db)?,
            x: row.try_get("x").map_err(db)?,
            y: row.try_get("y").map_err(db)?,
            heading_rad: row.try_get("heading_rad").map_err(db)?,
            at: parse_ts("robot_last_fix", &at)?,
        }))
    }
}
