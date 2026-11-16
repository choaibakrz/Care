//! The audit index: a database copy of the journal for `GET /audit`. A port (trait) so this
//! crate does not depend on `storage`, which implements it (`SqliteAuditIndex`).
//! The files are the authority; the index can be rebuilt from them.

use async_trait::async_trait;
use chrono::{DateTime, Utc};

use crate::error::JournalError;
use crate::record::{Category, JournalRecord};

/// Largest page.
pub const MAX_AUDIT_LIMIT: u32 = 500;

/// A query.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuditQuery {
    /// From (inclusive).
    pub from: Option<DateTime<Utc>>,
    /// To (exclusive).
    pub to: Option<DateTime<Utc>>,
    /// Actor in `Actor` display form (`user:nurse-1`).
    pub actor: Option<String>,
    /// Category.
    pub category: Option<Category>,
    /// Page size, 1 to 500.
    pub limit: u32,
    /// Continue after this `seq`.
    pub after_seq: Option<u64>,
}

impl AuditQuery {
    /// Checks the limit.
    ///
    /// # Errors
    /// `LimitOutOfRange` for 0 or above 500.
    pub fn validate(&self) -> Result<(), JournalError> {
        if (1..=500).contains(&self.limit) {
            Ok(())
        } else {
            Err(JournalError::LimitOutOfRange {
                limit: self.limit,
                max: 500,
            })
        }
    }
}

/// A page of records.
#[derive(Debug, Clone, PartialEq)]
pub struct AuditPage {
    /// Records, ascending `seq`.
    pub records: Vec<JournalRecord>,
    /// `after_seq` for the next page.
    pub next_after: Option<u64>,
}

/// The index port.
#[async_trait]
pub trait AuditIndex: Send + Sync {
    /// Adds one record.
    ///
    /// # Errors
    /// `Index`.
    async fn insert(&self, record: &JournalRecord) -> Result<(), JournalError>;
    /// Queries.
    ///
    /// # Errors
    /// `LimitOutOfRange`; `Index`.
    async fn query(&self, query: &AuditQuery) -> Result<AuditPage, JournalError>;
    /// Drops and rebuilds from records read from the files.
    ///
    /// # Errors
    /// `Index`.
    async fn rebuild(&self, records: &[JournalRecord]) -> Result<(), JournalError>;
}
