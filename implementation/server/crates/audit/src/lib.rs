//! The sealed, append-only journal: the authority on what happened.
//!
//! One writer task assigns a gapless `seq` to every record; seals are requests in the same
//! queue, so nothing falls between two seals. Seals are signed (Ed25519, key outside the
//! journal directory) and anchored to places the server cannot rewrite in the same operation.
//! See `docs/journal.md`.

pub mod anchor;
pub mod error;
pub mod flight_recorder;
pub mod index;
pub mod journal;
pub mod record;
pub mod redact;
pub mod seal;
pub mod segment;
pub mod signer;
pub mod tracing_layer;
pub mod verify;

pub use anchor::{AnchorSink, FileAnchor};
pub use error::JournalError;
pub use flight_recorder::FlightRecorder;
pub use index::{AuditIndex, AuditPage, AuditQuery};
pub use journal::{Journal, JournalConfig, SealReason, SyncProbe};
pub use record::{
    Category, FlightEvent, IncidentTrigger, JournalRecord, RecordBody, RecordReceipt, Severity,
};
pub use redact::Redactor;
pub use seal::{FileDigest, Seal};
pub use signer::{Ed25519FileSigner, Signature, Signer, load_verifying_key};
pub use tracing_layer::JournalLayer;
pub use verify::{VerifyReport, verify};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
