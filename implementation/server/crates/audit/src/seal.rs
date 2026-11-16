//! Seals: signed records covering a contiguous `seq` range and the rotated log files.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::error::JournalError;
use crate::signer::Signature;

/// Digest of one rotated operational log file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileDigest {
    /// File name (no directory).
    pub name: String,
    /// SHA-256.
    #[serde(with = "crate::record::hex_bytes")]
    pub sha256: [u8; 32],
    /// Size.
    pub bytes: u64,
}

/// A seal.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Seal {
    /// First covered record.
    pub first_seq: u64,
    /// Last covered record.
    pub last_seq: u64,
    /// Records covered.
    pub count: u64,
    /// Hash of the last covered record.
    #[serde(with = "crate::record::hex_bytes")]
    pub chain_head: [u8; 32],
    /// Hash of the previous seal.
    #[serde(with = "crate::record::hex_bytes")]
    pub prev_seal_hash: [u8; 32],
    /// When sealed.
    pub sealed_at: DateTime<Utc>,
    /// Oldest `event_at` covered.
    pub oldest_event_at: Option<DateTime<Utc>>,
    /// Latest `event_at` covered.
    pub latest_event_at: Option<DateTime<Utc>>,
    /// Records flagged late.
    pub late_records: u32,
    /// Rotated log files covered.
    pub sealed_files: Vec<FileDigest>,
    /// Fingerprint of the signing key.
    pub key_fingerprint: String,
    /// Signature over `signing_bytes`.
    pub signature: Signature,
}

impl Seal {
    /// The signed bytes: canonical JSON of the seal without `signature`.
    ///
    /// # Errors
    /// `Serialize`.
    pub fn signing_bytes(&self) -> Result<Vec<u8>, JournalError> {
        crate::record::canonical_json(self, Some("signature"))
    }

    /// Hash of the whole seal (chained into the next seal and the anchors).
    ///
    /// # Errors
    /// `Serialize`.
    pub fn hash(&self) -> Result<[u8; 32], JournalError> {
        use sha2::Digest as _;
        Ok(sha2::Sha256::digest(crate::record::canonical_json(self, None)?).into())
    }
}
