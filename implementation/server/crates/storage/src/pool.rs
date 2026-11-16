//! The SQLite connection pool.

use std::time::Duration;

use sqlx::SqlitePool;
use sqlx::sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions};

use crate::error::StorageError;

/// A cheap, cloneable handle on the database.
#[derive(Debug, Clone)]
pub struct Database {
    pool: SqlitePool,
}

impl Database {
    /// Connects (WAL mode, foreign keys on, busy timeout).
    ///
    /// # Errors
    /// `Unavailable` when the file cannot be opened (for example a missing `data/` directory).
    pub async fn connect(url: &str) -> Result<Database, StorageError> {
        let options = url
            .parse::<SqliteConnectOptions>()
            .map_err(|_| StorageError::Unavailable)?
            .create_if_missing(true)
            .journal_mode(SqliteJournalMode::Wal)
            .foreign_keys(true)
            .busy_timeout(Duration::from_secs(5));
        let pool = SqlitePoolOptions::new()
            .max_connections(4)
            .connect_with(options)
            .await
            .map_err(|_| StorageError::Unavailable)?;
        Ok(Database { pool })
    }

    /// An in-memory database for tests.
    ///
    /// # Errors
    /// `Unavailable`.
    pub async fn in_memory() -> Result<Database, StorageError> {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .map_err(|_| StorageError::Unavailable)?;
        Ok(Database { pool })
    }

    /// Applies `migrations/`.
    ///
    /// # Errors
    /// `Migration`.
    pub async fn migrate(&self) -> Result<(), StorageError> {
        sqlx::migrate!("../../migrations")
            .run(&self.pool)
            .await
            .map_err(|error| StorageError::Migration {
                reason: error.to_string(),
            })
    }

    /// The pool.
    #[must_use]
    pub fn pool(&self) -> &SqlitePool {
        &self.pool
    }
}
