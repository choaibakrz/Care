//! Task 9: the verifier reports tampering precisely, and a torn last line is not tampering.

mod common;

use std::collections::BTreeMap;

use audit::{JournalRecord, RecordBody, VerifyReport};
use common::{Res, TestJournal};

type TestResult = Res<()>;

/// A sealed journal with records `event 0` … `event 4`; returns the root helper (stopped),
/// the seq of `event 3`, and the verifying key.
struct Sealed {
    dir: std::path::PathBuf,
    anchors: Vec<std::path::PathBuf>,
    key: ed25519_dalek::VerifyingKey,
    root: std::path::PathBuf,
    event_3_seq: u64,
}

async fn sealed_journal(name: &str) -> Res<Sealed> {
    let tj = TestJournal::start(name)?;
    let mut event_3_seq = 0;
    for n in 0..5 {
        let receipt = tj.append_event(n).await?;
        if n == 3 {
            event_3_seq = receipt.seq;
        }
    }
    let sealed = Sealed {
        dir: tj.config.dir.clone(),
        anchors: tj.config.anchor_paths.clone(),
        key: tj.verifying_key()?,
        root: tj.root.clone(),
        event_3_seq,
    };
    tj.stop().await?;
    Ok(sealed)
}

fn verify(sealed: &Sealed) -> Res<VerifyReport> {
    Ok(audit::verify(&sealed.dir, &sealed.key, &sealed.anchors)?)
}

#[tokio::test]
async fn changing_one_byte_is_reported_with_its_seq() -> TestResult {
    let sealed = sealed_journal("tamper-byte").await?;
    assert!(verify(&sealed)?.is_clean());
    let touched = common::edit_lines(&sealed.dir, "\"event 3\"", |line| {
        Some(line.replacen("event 3", "evenT 3", 1))
    })?;
    assert_eq!(touched, 1);
    let report = verify(&sealed)?;
    assert_eq!(report.first_bad_record, Some(sealed.event_3_seq));
    assert!(!report.is_clean());
    Ok(())
}

#[tokio::test]
async fn deleting_a_record_is_reported_as_a_gap() -> TestResult {
    let sealed = sealed_journal("tamper-delete").await?;
    let touched = common::edit_lines(&sealed.dir, "\"event 3\"", |_| None)?;
    assert_eq!(touched, 1);
    let report = verify(&sealed)?;
    let seq = sealed.event_3_seq;
    assert!(
        report
            .gaps
            .iter()
            .any(|(from, to)| *from <= seq && seq <= *to),
        "{report:?}"
    );
    assert!(!report.is_clean());
    Ok(())
}

/// An attacker who can write the files changes a record and recomputes every hash after it,
/// including the chain heads inside the seals. Without the signing key, the seal signatures
/// no longer match.
#[tokio::test]
async fn recomputed_chain_without_the_key_fails_the_signature_check() -> TestResult {
    let sealed = sealed_journal("tamper-chain").await?;
    let mut records = common::read_records(&sealed.dir)?;
    let mut prev_hash: Option<[u8; 32]> = None;
    let mut new_hashes: BTreeMap<u64, [u8; 32]> = BTreeMap::new();
    let mut rewritten: BTreeMap<u64, String> = BTreeMap::new();
    for record in &mut records {
        if record.seq < sealed.event_3_seq {
            new_hashes.insert(record.seq, record.hash);
            prev_hash = Some(record.hash);
            continue;
        }
        if let RecordBody::SystemEvent { message, .. } = &mut record.body
            && message == "event 3"
        {
            *message = "event 3 (forged)".to_owned();
        }
        if let Some(prev) = prev_hash {
            record.prev_hash = prev;
        }
        if let RecordBody::Seal(seal) = &mut record.body
            && let Some(head) = new_hashes.get(&seal.last_seq)
        {
            seal.chain_head = *head;
        }
        record.hash = record.compute_hash()?;
        new_hashes.insert(record.seq, record.hash);
        prev_hash = Some(record.hash);
        rewritten.insert(record.seq, serde_json::to_string(record)?);
    }
    for path in common::files(&sealed.dir)? {
        let text = std::fs::read_to_string(&path)?;
        let mut out = String::with_capacity(text.len());
        for line in text.lines() {
            let replacement = serde_json::from_str::<JournalRecord>(line)
                .ok()
                .and_then(|r| rewritten.get(&r.seq).cloned());
            out.push_str(replacement.as_deref().unwrap_or(line));
            out.push('\n');
        }
        std::fs::write(&path, out)?;
    }
    let report = verify(&sealed)?;
    assert_eq!(
        report.first_bad_record, None,
        "the chain itself is consistent"
    );
    assert!(!report.bad_seals.is_empty(), "{report:?}");
    assert!(!report.is_clean());
    Ok(())
}

#[tokio::test]
async fn anchor_disagreement_is_reported() -> TestResult {
    let sealed = sealed_journal("tamper-anchor").await?;
    let anchor = sealed.anchors.first().ok_or("no anchor configured")?;
    let text = std::fs::read_to_string(anchor)?;
    let flipped = flip_first_hash_char(&text).ok_or("no 64-hex hash in the anchor file")?;
    std::fs::write(anchor, flipped)?;
    let report = verify(&sealed)?;
    assert!(!report.anchor_mismatches.is_empty(), "{report:?}");
    assert!(!report.is_clean());
    Ok(())
}

#[tokio::test]
async fn torn_last_line_is_torn_tail_not_tampering() -> TestResult {
    let sealed = sealed_journal("torn").await?;
    let last_file = common::files(&sealed.dir)?
        .into_iter()
        .rfind(|p| {
            std::fs::read_to_string(p).is_ok_and(|t| t.lines().any(|l| l.contains("\"seq\"")))
        })
        .ok_or("no journal segment")?;
    let mut text = std::fs::read_to_string(&last_file)?;
    text.push_str("{\"seq\":99999,\"ingested_at\":\"2026-11-");
    std::fs::write(&last_file, text)?;
    let report = verify(&sealed)?;
    assert!(report.torn_tail, "{report:?}");
    assert_eq!(report.first_bad_record, None);
    assert!(report.bad_seals.is_empty());
    assert!(report.gaps.is_empty());
    assert!(sealed.root.exists());
    Ok(())
}

/// Changes the first character of the first run of 64 lowercase hex digits.
fn flip_first_hash_char(text: &str) -> Option<String> {
    let bytes = text.as_bytes();
    let mut run_start = None;
    let mut run_len = 0;
    for (index, byte) in bytes.iter().enumerate() {
        if byte.is_ascii_digit() || (b'a'..=b'f').contains(byte) {
            if run_len == 0 {
                run_start = Some(index);
            }
            run_len += 1;
            if run_len == 64 {
                let start = run_start?;
                let mut out = text.to_owned();
                let original = text.get(start..=start)?;
                let replacement = if original == "0" { "1" } else { "0" };
                out.replace_range(start..=start, replacement);
                return Some(out);
            }
        } else {
            run_len = 0;
            run_start = None;
        }
    }
    None
}
