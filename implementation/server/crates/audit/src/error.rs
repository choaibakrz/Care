//! Journal errors. These are operator-facing (logs, CLI); the API maps them to
//! `journal_unavailable` without details.

use std::path::PathBuf;

/// Journal errors.
#[derive(Debug, thiserror::Error)]
pub enum JournalError {
    /// A file operation failed.
    #[error("Journal could not {action} '{}': {source}. Check the disk and the directory permissions.", path.display())]
    Io {
        /// What was attempted.
        action: &'static str,
        /// File or directory.
        path: PathBuf,
        /// Cause.
        #[source]
        source: std::io::Error,
    },
    /// The signing key is readable by others.
    #[error("Signing key '{}' is readable by other users; restrict it to the server account (chmod 600) and restart.", path.display())]
    KeyPermissions {
        /// Key file.
        path: PathBuf,
    },
    /// The signing key is invalid.
    #[error("Signing key '{}' is not a valid Ed25519 key ({reason}); restore it from backup, never regenerate it silently.", path.display())]
    KeyInvalid {
        /// Key file.
        path: PathBuf,
        /// Why.
        reason: String,
    },
    /// A record could not be serialised.
    #[error("A journal record could not be serialised ({reason}); this is a bug, report it.")]
    Serialize {
        /// Why.
        reason: String,
    },
    /// A segment line is unreadable (not the torn tail).
    #[error(
        "Journal segment '{segment}' line {line} is damaged ({reason}); run `clinic-server journal verify`."
    )]
    Corrupt {
        /// Segment file name.
        segment: String,
        /// Line number.
        line: u64,
        /// Why.
        reason: String,
    },
    /// The writer task is gone.
    #[error("The journal writer has stopped; actions are paused until the server restarts.")]
    WriterStopped,
    /// Signing failed.
    #[error("A journal seal could not be signed ({reason}); check the signing key.")]
    Signature {
        /// Why.
        reason: String,
    },
    /// An anchor could not be written.
    #[error("Journal anchor '{}' could not be written ({reason}); check that the anchor disk is mounted.", path.display())]
    Anchor {
        /// Anchor file.
        path: PathBuf,
        /// Why.
        reason: String,
    },
    /// An audit query limit out of range.
    #[error("Audit limit {limit} is not allowed; use a limit between 1 and {max}.")]
    LimitOutOfRange {
        /// Requested.
        limit: u32,
        /// Largest.
        max: u32,
    },
    /// The audit index store failed.
    #[error(
        "The audit index cannot be read right now ({reason}); the journal files remain the authority."
    )]
    Index {
        /// Why.
        reason: String,
    },
}
