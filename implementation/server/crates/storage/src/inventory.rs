//! `inventory(item, label, count, low_threshold)`.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use domain::ports::InventoryRepository;
use domain::{DomainError, ItemId, StockLevel};

use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;
use crate::sql::{db, parse_id, parse_opt_ts, parse_ts, to_u32, ts};

const COLUMNS: &str = "SELECT item, label, place, count, low_threshold, last_robot_count,      last_robot_count_at, updated_at FROM inventory";

pub(crate) fn level_of(row: &SqliteRow) -> Result<StockLevel, DomainError> {
    let item: String = row.try_get("item").map_err(db)?;
    let place: String = row.try_get("place").map_err(db)?;
    let count: i64 = row.try_get("count").map_err(db)?;
    let low: i64 = row.try_get("low_threshold").map_err(db)?;
    let robot_count: Option<i64> = row.try_get("last_robot_count").map_err(db)?;
    let robot_at: Option<String> = row.try_get("last_robot_count_at").map_err(db)?;
    let updated: String = row.try_get("updated_at").map_err(db)?;
    Ok(StockLevel {
        item: parse_id("inventory", &item)?,
        label: row.try_get("label").map_err(db)?,
        place: parse_id("inventory", &place)?,
        count: to_u32("inventory", count)?,
        low_threshold: to_u32("inventory", low)?,
        last_robot_count: robot_count.map(|c| to_u32("inventory", c)).transpose()?,
        last_robot_count_at: parse_opt_ts("inventory", robot_at)?,
        updated_at: parse_ts("inventory", &updated)?,
    })
}

fn not_found(item: &ItemId) -> DomainError {
    DomainError::NotFound {
        what: format!("Item '{item}'"),
    }
}

impl SqliteInventoryRepository {
    async fn require(&self, item: &ItemId) -> Result<StockLevel, DomainError> {
        self.get(item).await?.ok_or_else(|| not_found(item))
    }
}

/// Inventory in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteInventoryRepository {
    db: Database,
}

impl SqliteInventoryRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteInventoryRepository {
        SqliteInventoryRepository { db }
    }
}

#[async_trait]
impl InventoryRepository for SqliteInventoryRepository {
    async fn list(&self) -> Result<Vec<StockLevel>, DomainError> {
        let rows = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} ORDER BY item")))
            .fetch_all(self.db.pool())
            .await
            .map_err(db)?;
        rows.iter().map(level_of).collect()
    }
    async fn get(&self, item: &ItemId) -> Result<Option<StockLevel>, DomainError> {
        let row = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} WHERE item = ?")))
            .bind(item.as_str())
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        row.as_ref().map(level_of).transpose()
    }
    async fn adjust(&self, item: &ItemId, delta: i32) -> Result<StockLevel, DomainError> {
        let done = sqlx::query(
            "UPDATE inventory SET count = count + ?, updated_at = ? WHERE item = ? AND count + ? >= 0",
        )
        .bind(i64::from(delta))
        .bind(ts(Utc::now()))
        .bind(item.as_str())
        .bind(i64::from(delta))
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        let level = self.require(item).await?;
        if done.rows_affected() == 0 {
            return Err(DomainError::InsufficientStock {
                item: item.clone(),
                requested: delta.unsigned_abs(),
                available: level.count,
            });
        }
        Ok(level)
    }
    async fn set_count(&self, item: &ItemId, count: u32) -> Result<StockLevel, DomainError> {
        sqlx::query("UPDATE inventory SET count = ?, updated_at = ? WHERE item = ?")
            .bind(i64::from(count))
            .bind(ts(Utc::now()))
            .bind(item.as_str())
            .execute(self.db.pool())
            .await
            .map_err(db)?;
        self.require(item).await
    }
    async fn record_robot_count(
        &self,
        item: &ItemId,
        count: u32,
        at: DateTime<Utc>,
    ) -> Result<StockLevel, DomainError> {
        sqlx::query(
            "UPDATE inventory SET last_robot_count = ?, last_robot_count_at = ? WHERE item = ?",
        )
        .bind(i64::from(count))
        .bind(ts(at))
        .bind(item.as_str())
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        self.require(item).await
    }
    async fn upsert(&self, level: &StockLevel) -> Result<(), DomainError> {
        sqlx::query(
            "INSERT OR REPLACE INTO inventory (item, label, place, count, low_threshold,              last_robot_count, last_robot_count_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(level.item.as_str())
        .bind(&level.label)
        .bind(level.place.as_str())
        .bind(i64::from(level.count))
        .bind(i64::from(level.low_threshold))
        .bind(level.last_robot_count.map(i64::from))
        .bind(level.last_robot_count_at.map(ts))
        .bind(ts(level.updated_at))
        .execute(self.db.pool())
        .await
        .map_err(db)?;
        Ok(())
    }
}
