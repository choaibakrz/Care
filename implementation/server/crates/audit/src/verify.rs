//! Offline verification: chain, gaps, seal signatures, anchors, torn tail.

use std::path::{Path, PathBuf};

use ed25519_dalek::VerifyingKey;
use serde::Serialize;
use utoipa::ToSchema;

use crate::error::JournalError;

/// The verification result.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, ToSchema)]
pub struct VerifyReport {
    /// Records read.
    pub records: u64,
    /// Seals read.
    pub seals: u64,
    /// First record whose hash does not match.
    pub first_bad_record: Option<u64>,
    /// Missing `seq` ranges, inclusive.
    pub gaps: Vec<(u64, u64)>,
    /// Seals with a bad signature or range (by `last_seq`).
    pub bad_seals: Vec<u64>,
    /// Seals whose anchor copy is missing or differs (by `last_seq`).
    pub anchor_mismatches: Vec<u64>,
    /// A half-written last line (expected after a crash), distinct from tampering.
    pub torn_tail: bool,
}

impl VerifyReport {
    /// No tampering found (a torn tail alone is clean).
    #[must_use]
    pub fn is_clean(&self) -> bool {
        self.first_bad_record.is_none()
            && self.gaps.is_empty()
            && self.bad_seals.is_empty()
            && self.anchor_mismatches.is_empty()
    }
}

/// Verifies a journal directory.
///
/// # Errors
/// `Io` when the directory cannot be read.
pub fn verify(
    dir: &Path,
    public_key: &VerifyingKey,
    anchors: &[PathBuf],
) -> Result<VerifyReport, JournalError> {
    use ed25519_dalek::Verifier as _;
    use std::collections::HashMap;

    let mut report = VerifyReport::default();
    let anchored = read_anchors(anchors)?;
    let mut hashes: HashMap<u64, [u8; 32]> = HashMap::new();
    let mut expected_seq = 0_u64;
    let mut prev_hash = [0_u8; 32];
    let mut prev_seal_hash = [0_u8; 32];
    let segments = crate::segment::segment_files(dir)?;
    for (_, path) in &segments {
        let read = crate::segment::read_segment(path)?;
        if read.torn {
            // Only the end of the journal may be torn; a torn line in the middle was
            // followed by a new segment on restart, which is also a crash, not tampering.
            report.torn_tail = true;
        }
        if !read.damaged.is_empty() && report.first_bad_record.is_none() {
            report.first_bad_record = Some(expected_seq);
        }
        for record in read.records {
            report.records += 1;
            if record.seq != expected_seq {
                if record.seq > expected_seq {
                    report.gaps.push((expected_seq, record.seq - 1));
                } else if report.first_bad_record.is_none() {
                    report.first_bad_record = Some(record.seq);
                }
            }
            let hash_ok = record.compute_hash().is_ok_and(|hash| hash == record.hash);
            let linked = record.prev_hash == prev_hash;
            if (!hash_ok || !linked) && report.first_bad_record.is_none() {
                report.first_bad_record = Some(record.seq);
            }
            hashes.insert(record.seq, record.hash);
            if let crate::record::RecordBody::Seal(seal) = &record.body {
                report.seals += 1;
                let signed = seal.signing_bytes().is_ok_and(|bytes| {
                    public_key
                        .verify(
                            &bytes,
                            &ed25519_dalek::Signature::from_bytes(&seal.signature.0),
                        )
                        .is_ok()
                });
                let head_ok = seal.count == 0
                    || hashes
                        .get(&seal.last_seq)
                        .is_some_and(|h| *h == seal.chain_head);
                if !signed || !head_ok || seal.prev_seal_hash != prev_seal_hash {
                    report.bad_seals.push(seal.last_seq);
                }
                if let Ok(hash) = seal.hash() {
                    if !anchors.is_empty() && !anchored.contains(&hash) {
                        report.anchor_mismatches.push(seal.last_seq);
                    }
                    prev_seal_hash = hash;
                }
            }
            prev_hash = record.hash;
            expected_seq = record.seq.max(expected_seq) + 1;
        }
    }
    Ok(report)
}

/// Every seal hash written to the anchor files (the first word of each line).
fn read_anchors(anchors: &[PathBuf]) -> Result<std::collections::HashSet<[u8; 32]>, JournalError> {
    let mut hashes = std::collections::HashSet::new();
    for path in anchors {
        let text = std::fs::read_to_string(path).map_err(|source| JournalError::Io {
            action: "read the anchor file",
            path: path.clone(),
            source,
        })?;
        hashes.extend(
            text.lines()
                .filter_map(|line| line.split_whitespace().next())
                .filter_map(crate::record::hex_bytes::from_hex::<32>),
        );
    }
    Ok(hashes)
}
