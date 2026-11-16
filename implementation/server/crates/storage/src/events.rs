//! `processed_events(event_id primary key)`: idempotency of robot events, used inside the
//! same transaction as the state change, the stock change and the audit insert.

use sqlx::SqliteConnection;
use uuid::Uuid;

use crate::error::StorageError;

/// Marks an event processed; `false` when it already was.
///
/// # Errors
/// `Unavailable`.
pub(crate) async fn mark_processed(
    conn: &mut SqliteConnection,
    event_id: Uuid,
) -> Result<bool, StorageError> {
    let done = sqlx::query("INSERT OR IGNORE INTO processed_events (event_id) VALUES (?)")
        .bind(event_id.to_string())
        .execute(conn)
        .await?;
    Ok(done.rows_affected() == 1)
}
