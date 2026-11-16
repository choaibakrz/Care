//! Errors of the scheduler.

use domain::{DomainError, ScheduleId};

/// Scheduler errors.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum SchedulerError {
    /// Not five fields.
    #[error(
        "A cron expression needs 5 fields (minute hour day-of-month month day-of-week); this one has {have}."
    )]
    FieldCount {
        /// Fields given.
        have: usize,
    },
    /// A field value out of range.
    #[error("Field '{field}' has value {value}; {unit} go from {min} to {max}.")]
    InvalidCron {
        /// Field name (`minute`, `hour`, …).
        field: &'static str,
        /// The rejected text.
        value: String,
        /// Plural unit (`minutes`, `hours`, …).
        unit: &'static str,
        /// Lowest value.
        min: u8,
        /// Highest value.
        max: u8,
    },
    /// Unknown IANA time zone.
    #[error("Time zone '{tz}' is unknown; use an IANA name such as Europe/Zurich.")]
    UnknownTimezone {
        /// The name.
        tz: String,
    },
    /// A schedule that cannot be saved.
    #[error("Schedule '{schedule}' is invalid: {reason}.")]
    InvalidSchedule {
        /// Schedule.
        schedule: ScheduleId,
        /// Why.
        reason: &'static str,
    },
    /// Creating the task failed.
    #[error(
        "Schedule '{schedule}' could not create its task: {reason}. It will be retried on the next tick."
    )]
    TaskCreation {
        /// Schedule.
        schedule: ScheduleId,
        /// Why.
        reason: String,
    },
    /// The schedule store failed.
    #[error("Schedules could not be read or saved: {0}")]
    Repository(#[from] DomainError),
}
