//! `audit_index`: the database copy of the journal behind `GET /audit` (Task 9).

use async_trait::async_trait;
use audit::{AuditIndex, AuditPage, AuditQuery, JournalError, JournalRecord};

use sqlx::Row as _;

use crate::pool::Database;
use crate::sql::{enum_text, ts};

fn index_error(reason: &str) -> JournalError {
    JournalError::Index {
        reason: reason.to_owned(),
    }
}

#[allow(clippy::needless_pass_by_value)]
fn sql_error(_error: sqlx::Error) -> JournalError {
    index_error("the database is unavailable")
}

/// Inserts one record on `conn`.
async fn insert_on(
    conn: &mut sqlx::SqliteConnection,
    record: &JournalRecord,
) -> Result<(), JournalError> {
    let seq = i64::try_from(record.seq).map_err(|_| index_error("seq out of range"))?;
    let severity = enum_text(&record.severity).map_err(|_| index_error("severity"))?;
    let category = enum_text(&record.category).map_err(|_| index_error("category"))?;
    let json = serde_json::to_string(record).map_err(|_| index_error("record not serialisable"))?;
    sqlx::query(
        "INSERT OR REPLACE INTO audit_index (seq, ingested_at, severity, category, actor, \
         record_json) VALUES (?, ?, ?, ?, ?, ?)",
    )
    .bind(seq)
    .bind(ts(record.ingested_at))
    .bind(severity)
    .bind(category)
    .bind(record.actor.to_string())
    .bind(json)
    .execute(conn)
    .await
    .map_err(sql_error)?;
    Ok(())
}

/// Audit index in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteAuditIndex {
    db: Database,
}

impl SqliteAuditIndex {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteAuditIndex {
        SqliteAuditIndex { db }
    }
}

#[async_trait]
impl AuditIndex for SqliteAuditIndex {
    async fn insert(&self, record: &JournalRecord) -> Result<(), JournalError> {
        let mut conn = self.db.pool().acquire().await.map_err(sql_error)?;
        insert_on(&mut conn, record).await
    }
    async fn query(&self, query: &AuditQuery) -> Result<AuditPage, JournalError> {
        query.validate()?;
        let after = query
            .after_seq
            .map(i64::try_from)
            .transpose()
            .map_err(|_| index_error("after_seq out of range"))?;
        let category = query
            .category
            .map(|c| enum_text(&c))
            .transpose()
            .map_err(|_| index_error("category"))?;
        let rows = sqlx::query(
            "SELECT record_json FROM audit_index WHERE (?1 IS NULL OR seq > ?1) \
             AND (?2 IS NULL OR ingested_at >= ?2) AND (?3 IS NULL OR ingested_at < ?3) \
             AND (?4 IS NULL OR actor = ?4) AND (?5 IS NULL OR category = ?5) \
             ORDER BY seq LIMIT ?6",
        )
        .bind(after)
        .bind(query.from.map(ts))
        .bind(query.to.map(ts))
        .bind(query.actor.as_deref())
        .bind(category)
        .bind(i64::from(query.limit))
        .fetch_all(self.db.pool())
        .await
        .map_err(sql_error)?;
        let mut records = Vec::with_capacity(rows.len());
        for row in &rows {
            let json: String = row.try_get("record_json").map_err(sql_error)?;
            let record: JournalRecord = serde_json::from_str(&json)
                .map_err(|_| index_error("a stored record is damaged"))?;
            records.push(record);
        }
        let full = u32::try_from(records.len()).is_ok_and(|n| n == query.limit);
        let next_after = if full {
            records.last().map(|r| r.seq)
        } else {
            None
        };
        Ok(AuditPage {
            records,
            next_after,
        })
    }
    async fn rebuild(&self, records: &[JournalRecord]) -> Result<(), JournalError> {
        let mut tx = self.db.pool().begin().await.map_err(sql_error)?;
        sqlx::query("DELETE FROM audit_index")
            .execute(&mut *tx)
            .await
            .map_err(sql_error)?;
        for record in records {
            insert_on(&mut tx, record).await?;
        }
        tx.commit().await.map_err(sql_error)
    }
}
