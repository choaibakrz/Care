//! Storage errors. sqlx details go to tracing, never into `Display`.

use domain::DomainError;

/// Storage errors.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum StorageError {
    /// The database cannot be reached or is busy.
    #[error(
        "The database is unavailable right now. Try again in a moment; if it persists, check the database file and disk."
    )]
    Unavailable,
    /// A uniqueness conflict.
    #[error("{what} already exists. Use another id or update the existing record.")]
    Conflict {
        /// What.
        what: String,
    },
    /// Not found.
    #[error("{what} was not found. Check the id.")]
    NotFound {
        /// What.
        what: String,
    },
    /// A stored row cannot be decoded.
    #[error("Stored {table} data is damaged ({reason}). An administrator must check the database.")]
    Corrupt {
        /// Table.
        table: &'static str,
        /// Why (no SQL).
        reason: String,
    },
    /// Migrations failed.
    #[error(
        "The database schema could not be updated ({reason}). Restore a backup or check the migrations folder."
    )]
    Migration {
        /// Why (migration version, no SQL).
        reason: String,
    },
}

impl From<sqlx::Error> for StorageError {
    fn from(error: sqlx::Error) -> Self {
        match &error {
            sqlx::Error::RowNotFound => StorageError::NotFound {
                what: "The record".to_owned(),
            },
            sqlx::Error::Database(db) if db.is_unique_violation() => StorageError::Conflict {
                what: "The record".to_owned(),
            },
            sqlx::Error::ColumnDecode { .. } | sqlx::Error::Decode(_) => StorageError::Corrupt {
                table: "unknown",
                reason: "a column could not be decoded".to_owned(),
            },
            _ => StorageError::Unavailable,
        }
    }
}

impl From<StorageError> for DomainError {
    fn from(error: StorageError) -> Self {
        match error {
            StorageError::Unavailable | StorageError::Migration { .. } => {
                DomainError::StoreUnavailable { what: "database" }
            }
            StorageError::Conflict { what } => DomainError::Conflict { what },
            StorageError::NotFound { what } => DomainError::NotFound { what },
            StorageError::Corrupt { table, reason } => DomainError::Corrupt { table, reason },
        }
    }
}
