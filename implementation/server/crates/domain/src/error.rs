//! Errors of the domain crate. Each message says what happened, to what, and what to do.

use crate::ids::{ItemId, TaskId};
use crate::task::TaskState;

/// Errors raised by domain validation and by repository ports.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum DomainError {
    /// An id failed validation.
    #[error(
        "The {kind} id '{value}' is not valid: {reason}. Use 1 to 64 characters among a-z, 0-9, '_' and '-'."
    )]
    InvalidId {
        /// Which kind of id (`task`, `robot`, …).
        kind: &'static str,
        /// The rejected value.
        value: String,
        /// Why it was rejected.
        reason: &'static str,
    },
    /// An owner label failed validation (the value is not repeated: it describes a person).
    #[error(
        "The owner label is not valid: {reason}. Use 1 to 40 visible characters, not only digits."
    )]
    InvalidOwnerLabel {
        /// Why it was rejected.
        reason: &'static str,
    },
    /// A task state change that the state machine forbids.
    #[error(
        "Task '{task}': going from '{from}' to '{to}' is not allowed. See docs/task-states.md for the allowed transitions."
    )]
    IllegalTransition {
        /// The task.
        task: TaskId,
        /// Current state.
        from: TaskState,
        /// Requested state.
        to: TaskState,
    },
    /// A move to `failed` without saying why.
    #[error(
        "Task '{task}' cannot be marked failed without a reason. Send one of the failure reasons listed in docs/task-states.md."
    )]
    MissingFailureReason {
        /// The task.
        task: TaskId,
    },
    /// A task is missing a field its kind requires.
    #[error("A '{kind}' task needs '{field}'. Add it to the request.")]
    MissingTaskField {
        /// Task kind name.
        kind: &'static str,
        /// The missing field.
        field: &'static str,
    },
    /// A page request outside the allowed range.
    #[error("Page limit {limit} is not allowed; use a limit between 1 and {max}.")]
    InvalidPage {
        /// Requested limit.
        limit: u32,
        /// Largest allowed limit.
        max: u32,
    },
    /// A stock change that would go below zero.
    #[error("Cannot remove {requested} '{item}': only {available} in stock.")]
    InsufficientStock {
        /// The item.
        item: ItemId,
        /// How many were to be removed.
        requested: u32,
        /// How many are in stock.
        available: u32,
    },
    /// The store behind a repository is unreachable.
    #[error(
        "The {what} store is unavailable right now. Try again in a moment; if it persists, an administrator must check the database."
    )]
    StoreUnavailable {
        /// Which store.
        what: &'static str,
    },
    /// A record already exists.
    #[error("{what} already exists. Use another id or update the existing record.")]
    Conflict {
        /// What conflicted.
        what: String,
    },
    /// A compare-and-set write found another version (Task A4: clinic plans, `If-Match`).
    #[error(
        "{what} was changed by someone else: it is now version {current}, not {expected}. Reload it and redo your change."
    )]
    VersionConflict {
        /// What was written.
        what: String,
        /// The version the caller had.
        expected: u64,
        /// The stored version.
        current: u64,
    },
    /// A record was not found.
    #[error("{what} was not found. Check the id.")]
    NotFound {
        /// What was looked for.
        what: String,
    },
    /// A brain request field is not valid (Task A6). The message never repeats a text.
    #[error(
        "The field `{field}` of the brain request is not valid: {reason}. Correct it and send the request again."
    )]
    InvalidBrainInput {
        /// The field (`text`, `lang`, `source`, `sources`, `to`).
        field: &'static str,
        /// Why (never the text itself).
        reason: String,
    },
    /// An account key, account id, account tag or enrolment code is not in its format
    /// (Task A7). The message never repeats the value: a key is password-equivalent.
    #[error("The field `{field}` is not valid: {reason}. See docs/accounts.md for the format.")]
    InvalidAccountInput {
        /// The field (`account_key`, `account_tag`, `enrolment_code`, `display_label`).
        field: &'static str,
        /// Why (never the value itself).
        reason: &'static str,
    },
    /// An enrolment code was refused (Task A7): one answer for an unknown, used or expired
    /// code, so none can be told apart.
    #[error(
        "This enrolment code is not valid: it is unknown, already used or expired. Ask an administrator for a new code."
    )]
    EnrolmentRefused,
    /// The derived key of an enrolment is already an account (Task A7).
    #[error(
        "An account with this user name and password already exists. Log in instead, or choose another user name or password."
    )]
    AccountExists,
    /// Stored data could not be read back.
    #[error("Stored {table} data is damaged ({reason}). An administrator must check the database.")]
    Corrupt {
        /// Table or store.
        table: &'static str,
        /// What is wrong.
        reason: String,
    },
}

/// Errors of the stock ledger port (Task 15).
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum StockError {
    /// Not enough free stock to reserve.
    #[error(
        "Cannot reserve {requested} '{item}': {available} available ({reserved} more are reserved by other tasks)."
    )]
    OutOfStock {
        /// The item.
        item: ItemId,
        /// Requested quantity.
        requested: u32,
        /// Free quantity.
        available: u32,
        /// Quantity held by other reservations.
        reserved: u32,
    },
    /// The item is not in the reserve.
    #[error("Item '{item}' is not in the reserve. Check the item id against GET /inventory.")]
    UnknownItem {
        /// The item.
        item: ItemId,
    },
    /// The reservation is no longer active (committed, released or expired).
    #[error(
        "Reservation for task '{task}' is no longer active (already committed, released or expired). Reserve again."
    )]
    ReservationGone {
        /// The task that held it.
        task: TaskId,
    },
    /// The ledger store failed.
    #[error("The stock ledger cannot be read or written right now: {0}")]
    Store(#[from] DomainError),
}

#[cfg(test)]
impl DomainError {
    /// One value of every variant, for message tests (test helper).
    ///
    /// # Errors
    /// `InvalidId` if a sample id fails validation.
    pub(crate) fn samples() -> Result<Vec<DomainError>, DomainError> {
        let task: TaskId = "t-1".parse()?;
        Ok(vec![
            DomainError::InvalidId {
                kind: "robot",
                value: "Robot 1".to_owned(),
                reason: "uppercase letters are not allowed",
            },
            DomainError::InvalidOwnerLabel {
                reason: "it is empty",
            },
            DomainError::IllegalTransition {
                task: task.clone(),
                from: TaskState::Delivered,
                to: TaskState::EnRoute,
            },
            DomainError::MissingFailureReason { task },
            DomainError::MissingTaskField {
                kind: "fetch",
                field: "item",
            },
            DomainError::InvalidPage {
                limit: 501,
                max: 500,
            },
            DomainError::InsufficientStock {
                item: "blanket".parse()?,
                requested: 5,
                available: 3,
            },
            DomainError::StoreUnavailable { what: "task" },
            DomainError::Conflict {
                what: "User 'u-1'".to_owned(),
            },
            DomainError::VersionConflict {
                what: "Clinic plan 'seed'".to_owned(),
                expected: 3,
                current: 4,
            },
            DomainError::NotFound {
                what: "Task 't-9'".to_owned(),
            },
            DomainError::InvalidBrainInput {
                field: "text",
                reason: "it is empty".to_owned(),
            },
            DomainError::InvalidAccountInput {
                field: "account_key",
                reason: "it must be 64 lowercase hex characters",
            },
            DomainError::EnrolmentRefused,
            DomainError::AccountExists,
            DomainError::Corrupt {
                table: "tasks",
                reason: "assigned without a robot".to_owned(),
            },
        ])
    }
}

#[cfg(test)]
mod tests {
    use super::DomainError;

    #[test]
    fn every_error_variant_has_nonempty_message() -> Result<(), Box<dyn std::error::Error>> {
        let samples = DomainError::samples()?;
        assert_eq!(samples.len(), 16);
        for sample in samples {
            let message = sample.to_string();
            assert!(!message.trim().is_empty(), "{sample:?}");
            assert!(message.ends_with('.'), "{message}");
        }
        Ok(())
    }
}
