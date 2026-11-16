//! Anchors: copies of each seal hash where the server cannot rewrite them in the same
//! operation (a second append-only file on another disk or USB path). Anchor failures are
//! `Error` records and an admin alert, never silent. The live admin-panel anchor is the seal
//! broadcast (`Journal::subscribe_seals`), forwarded to the hub by the binary.

use std::path::PathBuf;

use chrono::{DateTime, Utc};

use crate::error::JournalError;

/// A place a seal hash is copied to.
pub trait AnchorSink: Send + Sync {
    /// Appends one anchor line.
    ///
    /// # Errors
    /// `Anchor`.
    fn append(
        &self,
        seal_hash: &[u8; 32],
        last_seq: u64,
        sealed_at: DateTime<Utc>,
    ) -> Result<(), JournalError>;
}

/// An append-only anchor file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileAnchor {
    path: PathBuf,
}

impl FileAnchor {
    /// An anchor at `path`.
    #[must_use]
    pub fn new(path: PathBuf) -> FileAnchor {
        FileAnchor { path }
    }
}

impl AnchorSink for FileAnchor {
    fn append(
        &self,
        seal_hash: &[u8; 32],
        last_seq: u64,
        sealed_at: DateTime<Utc>,
    ) -> Result<(), JournalError> {
        use std::io::Write as _;
        let failed = |reason: String| JournalError::Anchor {
            path: self.path.clone(),
            reason,
        };
        if let Some(parent) = self.path.parent().filter(|p| !p.as_os_str().is_empty()) {
            std::fs::create_dir_all(parent).map_err(|e| failed(e.to_string()))?;
        }
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .map_err(|e| failed(e.to_string()))?;
        let line = format!(
            "{} {last_seq} {}\n",
            crate::record::hex_bytes::to_hex(seal_hash),
            sealed_at.to_rfc3339()
        );
        file.write_all(line.as_bytes())
            .and_then(|()| file.sync_data())
            .map_err(|e| failed(e.to_string()))
    }
}
