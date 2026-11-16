//! Task 9: seals cover contiguous sequence ranges; nothing falls between two seals.

mod common;

use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use audit::{Category, RecordBody, SealReason, Severity};
use common::{Res, TestJournal};
use domain::{Actor, TaskState};
use tracing_subscriber::layer::SubscriberExt as _;

type TestResult = Res<()>;

/// Ten tasks append 1,000 records while another requests seals. Every record whose `append`
/// had returned before a seal was requested has `seq <= that seal's last_seq`, and the seals
/// cover contiguous ranges (checked by the seal chain and by the verifier).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn seal_covers_every_record_submitted_before_it() -> TestResult {
    let tj = TestJournal::start("seal-race")?;
    // Highest completed seq + 1 (0 = none yet).
    let completed = Arc::new(AtomicU64::new(0));
    let mut writers = Vec::new();
    for task in 0..10_u32 {
        let journal = tj.journal.clone();
        let completed = completed.clone();
        writers.push(tokio::spawn(async move {
            for n in 0..100_u32 {
                let receipt = common::append_event(&journal, task * 1000 + n).await?;
                completed.fetch_max(receipt.seq + 1, Ordering::SeqCst);
            }
            Ok::<(), audit::JournalError>(())
        }));
    }
    let sealer = {
        let journal = tj.journal.clone();
        let completed = completed.clone();
        tokio::spawn(async move {
            let mut violations = Vec::new();
            for _ in 0..20 {
                let floor = completed.load(Ordering::SeqCst);
                let seal = journal.seal_now(SealReason::Interval).await?;
                if floor > 0 && seal.last_seq + 1 < floor {
                    violations.push((floor - 1, seal.last_seq));
                }
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
            Ok::<Vec<(u64, u64)>, audit::JournalError>(violations)
        })
    };
    for writer in writers {
        writer.await??;
    }
    let violations = sealer.await??;
    assert!(
        violations.is_empty(),
        "records completed before a seal request but not covered: {violations:?}"
    );
    let key = tj.verifying_key()?;
    let dir = tj.config.dir.clone();
    let anchors = tj.config.anchor_paths.clone();
    tj.stop().await?;
    let seals = common::read_seals(&dir)?;
    for pair in seals.windows(2) {
        if let [a, b] = pair {
            assert_eq!(
                b.first_seq,
                a.last_seq + 1,
                "seals must cover contiguous ranges"
            );
            assert_eq!(b.prev_seal_hash, a.hash()?, "seal chain broken");
        }
    }
    let report = audit::verify(&dir, &key, &anchors)?;
    assert!(report.is_clean(), "{report:?}");
    assert!(report.gaps.is_empty());
    Ok(())
}

#[tokio::test]
async fn record_submitted_during_a_seal_lands_in_the_next_seal() -> TestResult {
    let tj = TestJournal::start("seal-during")?;
    for n in 0..5 {
        tj.append_event(n).await?;
    }
    let (first, receipt) = tokio::join!(
        tj.journal.seal_now(SealReason::Interval),
        common::append_event(&tj.journal, 99)
    );
    let first = first?;
    let receipt = receipt?;
    let second = tj.journal.seal_now(SealReason::Interval).await?;
    assert!(second.first_seq > first.last_seq, "overlapping seals");
    let in_first = receipt.seq >= first.first_seq && receipt.seq <= first.last_seq;
    let in_second = receipt.seq >= second.first_seq && receipt.seq <= second.last_seq;
    assert!(
        in_first ^ in_second,
        "record {} must be in exactly one seal ({}..={} or {}..={})",
        receipt.seq,
        first.first_seq,
        first.last_seq,
        second.first_seq,
        second.last_seq
    );
    tj.stop().await?;
    Ok(())
}

#[tokio::test]
async fn late_robot_event_is_flagged_with_lag_and_still_sealed() -> TestResult {
    let tj = TestJournal::start("late")?;
    let start = common::start_time()?;
    tj.journal.seal_now(SealReason::Interval).await?;
    tj.clock.advance(Duration::from_mins(1));
    let happened = start - chrono::Duration::minutes(5);
    let receipt = tj
        .journal
        .append(
            Severity::Info,
            Category::Robot,
            Actor::Robot("robot-r2".parse()?),
            RecordBody::TaskStateChanged {
                task: "t-1".parse()?,
                from: TaskState::EnRoute,
                to: TaskState::Delivered,
                reason: None,
            },
            Some(happened),
        )
        .await?;
    let seal = tj.journal.seal_now(SealReason::Interval).await?;
    assert!(receipt.seq >= seal.first_seq && receipt.seq <= seal.last_seq);
    assert!(seal.late_records >= 1);
    assert_eq!(seal.oldest_event_at, Some(happened));
    let dir = tj.config.dir.clone();
    tj.stop().await?;
    let record = common::read_records(&dir)?
        .into_iter()
        .find(|r| r.seq == receipt.seq)
        .ok_or("the late record is not in the files")?;
    assert_eq!(record.event_at, Some(happened));
    let lag = record.late_by_ms.ok_or("the late record is not flagged")?;
    assert!(lag >= 300_000, "lag {lag} ms is under 5 minutes");
    Ok(())
}

#[tokio::test]
#[ignore = "todo(T9): the incident dump of the flight recorder (step R1 left it out)"]
async fn critical_record_triggers_seal_and_incident_with_recent_events() -> TestResult {
    let tj = TestJournal::start("critical")?;
    let subscriber = tracing_subscriber::registry().with(tj.journal.flight_recorder());
    let _guard = tracing::subscriber::set_default(subscriber);
    tracing::warn!(robot = "robot-r2", "battery low before the stop");
    tracing::info!("corridor-1 blocked");
    let mut seals = tj.journal.subscribe_seals();
    let receipt = tj
        .journal
        .append(
            Severity::Critical,
            Category::Robot,
            Actor::User("u-admin".parse()?),
            RecordBody::EstopSent {
                robot: "robot-r2".parse()?,
                delivered: true,
            },
            None,
        )
        .await?;
    let seal = tokio::time::timeout(Duration::from_secs(2), seals.recv()).await??;
    assert!(
        seal.last_seq >= receipt.seq,
        "the seal does not cover the critical record"
    );
    let dir = tj.config.dir.clone();
    tj.stop().await?;
    let recent = common::read_records(&dir)?
        .into_iter()
        .find_map(|r| match r.body {
            RecordBody::Incident { recent, .. } => Some(recent),
            _ => None,
        })
        .ok_or("no incident record after a critical record")?;
    assert!(
        recent
            .iter()
            .any(|e| e.message.contains("battery low before the stop")),
        "{recent:?}"
    );
    Ok(())
}

#[tokio::test]
#[ignore = "todo(T9): log file digests in seals (step R1 left them out)"]
async fn rotated_log_file_digest_appears_in_next_seal() -> TestResult {
    let root = common::temp_dir("rotated")?;
    let config = common::config(&root)?;
    let rotated = "clinic-server.log.2026-11-13";
    let content = b"2026-11-13T23:59:59Z INFO invented log line\n";
    std::fs::write(config.log_dir.join(rotated), content)?;
    let clock = Arc::new(domain::FakeClock::new(common::start_time()?));
    let tj = TestJournal::start_in(&root, clock)?;
    tj.append_event(1).await?;
    let seal = tj.journal.seal_now(SealReason::Rotation).await?;
    let digest = seal
        .sealed_files
        .iter()
        .find(|f| f.name.ends_with(rotated))
        .ok_or("the rotated log file is not in the seal")?;
    assert_eq!(digest.bytes, u64::try_from(content.len())?);
    assert_ne!(digest.sha256, [0_u8; 32]);
    tj.stop().await?;
    Ok(())
}
