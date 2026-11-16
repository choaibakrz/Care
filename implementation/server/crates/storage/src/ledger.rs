//! `reservations`: the SQLite stock ledger. One `BEGIN IMMEDIATE` transaction per
//! reservation, so SQLite serialises competing writers.

use std::time::Duration;

use async_trait::async_trait;
use domain::{
    ItemId, PlaceId, ReconcileOutcome, Reservation, SeenItem, StockError, StockLedger, TaskId,
};

use chrono::Utc;
use sqlx::Row as _;
use uuid::Uuid;

use crate::pool::Database;
use crate::sql::{db, to_u32, ts};

fn store(error: sqlx::Error) -> StockError {
    StockError::Store(db(error))
}

fn gone(reservation: &Reservation) -> StockError {
    StockError::ReservationGone {
        task: reservation.task.clone(),
    }
}

/// Ledger in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteLedger {
    db: Database,
}

impl SqliteLedger {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteLedger {
        SqliteLedger { db }
    }
}

#[async_trait]
impl StockLedger for SqliteLedger {
    async fn reserve(
        &self,
        task: &TaskId,
        item: &ItemId,
        qty: u32,
    ) -> Result<Reservation, StockError> {
        let mut tx = self
            .db
            .pool()
            .begin_with("BEGIN IMMEDIATE")
            .await
            .map_err(store)?;
        let count: Option<i64> = sqlx::query_scalar("SELECT count FROM inventory WHERE item = ?")
            .bind(item.as_str())
            .fetch_optional(&mut *tx)
            .await
            .map_err(store)?;
        let Some(count) = count else {
            return Err(StockError::UnknownItem { item: item.clone() });
        };
        let reserved: i64 =
            sqlx::query_scalar("SELECT COALESCE(SUM(qty), 0) FROM reservations WHERE item = ?")
                .bind(item.as_str())
                .fetch_one(&mut *tx)
                .await
                .map_err(store)?;
        let count = to_u32("inventory", count)?;
        let reserved = to_u32("reservations", reserved)?;
        let available = count.saturating_sub(reserved);
        if qty > available {
            return Err(StockError::OutOfStock {
                item: item.clone(),
                requested: qty,
                available,
                reserved,
            });
        }
        let reservation = Reservation {
            id: Uuid::new_v4(),
            task: task.clone(),
            item: item.clone(),
            qty,
            created_at: Utc::now(),
        };
        sqlx::query(
            "INSERT INTO reservations (id, task, item, qty, created_at) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(reservation.id.to_string())
        .bind(task.as_str())
        .bind(item.as_str())
        .bind(i64::from(qty))
        .bind(ts(reservation.created_at))
        .execute(&mut *tx)
        .await
        .map_err(store)?;
        tx.commit().await.map_err(store)?;
        Ok(reservation)
    }
    async fn commit(&self, reservation: &Reservation) -> Result<(), StockError> {
        let mut tx = self
            .db
            .pool()
            .begin_with("BEGIN IMMEDIATE")
            .await
            .map_err(store)?;
        let done = sqlx::query("DELETE FROM reservations WHERE id = ?")
            .bind(reservation.id.to_string())
            .execute(&mut *tx)
            .await
            .map_err(store)?;
        if done.rows_affected() == 0 {
            return Err(gone(reservation));
        }
        sqlx::query(
            "UPDATE inventory SET count = MAX(count - ?, 0), updated_at = ? WHERE item = ?",
        )
        .bind(i64::from(reservation.qty))
        .bind(ts(Utc::now()))
        .bind(reservation.item.as_str())
        .execute(&mut *tx)
        .await
        .map_err(store)?;
        tx.commit().await.map_err(store)?;
        Ok(())
    }
    async fn release(&self, reservation: &Reservation) -> Result<(), StockError> {
        let done = sqlx::query("DELETE FROM reservations WHERE id = ?")
            .bind(reservation.id.to_string())
            .execute(self.db.pool())
            .await
            .map_err(store)?;
        if done.rows_affected() == 0 {
            return Err(gone(reservation));
        }
        Ok(())
    }
    async fn expire_older_than(&self, age: Duration) -> Result<u32, StockError> {
        let age = chrono::Duration::from_std(age).unwrap_or(chrono::Duration::MAX);
        let cutoff = Utc::now()
            .checked_sub_signed(age)
            .unwrap_or(chrono::DateTime::<Utc>::MIN_UTC);
        let done = sqlx::query("DELETE FROM reservations WHERE created_at < ?")
            .bind(ts(cutoff))
            .execute(self.db.pool())
            .await
            .map_err(store)?;
        Ok(u32::try_from(done.rows_affected()).unwrap_or(u32::MAX))
    }
    async fn reconcile(
        &self,
        place: &PlaceId,
        seen: &[SeenItem],
    ) -> Result<Vec<ReconcileOutcome>, StockError> {
        let now = Utc::now();
        let mut outcomes = Vec::with_capacity(seen.len());
        for one in seen {
            let row = sqlx::query("SELECT count FROM inventory WHERE item = ? AND place = ?")
                .bind(one.item.as_str())
                .bind(place.as_str())
                .fetch_optional(self.db.pool())
                .await
                .map_err(store)?;
            let (Some(row), Some(counted), false) = (row, one.count, one.uncertain) else {
                outcomes.push(ReconcileOutcome::Uncertain {
                    item: one.item.clone(),
                });
                continue;
            };
            let expected: i64 = row.try_get("count").map_err(store)?;
            let expected = to_u32("inventory", expected)?;
            sqlx::query(
                "UPDATE inventory SET last_robot_count = ?, last_robot_count_at = ? WHERE item = ?",
            )
            .bind(i64::from(counted))
            .bind(ts(now))
            .bind(one.item.as_str())
            .execute(self.db.pool())
            .await
            .map_err(store)?;
            if counted == expected {
                outcomes.push(ReconcileOutcome::Matched {
                    item: one.item.clone(),
                });
            } else {
                sqlx::query("UPDATE inventory SET count = ?, updated_at = ? WHERE item = ?")
                    .bind(i64::from(counted))
                    .bind(ts(now))
                    .bind(one.item.as_str())
                    .execute(self.db.pool())
                    .await
                    .map_err(store)?;
                outcomes.push(ReconcileOutcome::Mismatch {
                    item: one.item.clone(),
                    expected,
                    seen: counted,
                });
            }
        }
        Ok(outcomes)
    }
}
