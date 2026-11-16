//! Task 9: the journal writer (sequence numbers, fsync of critical records, key file, query
//! limits).

mod common;

use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use audit::{
    AuditQuery, Category, Ed25519FileSigner, Journal, JournalError, RecordBody, Severity, SyncProbe,
};
use common::{Res, TestJournal};
use domain::{Actor, Clock, FakeClock};

type TestResult = Res<()>;

#[tokio::test]
async fn seq_is_gapless_and_survives_restart() -> TestResult {
    let first = TestJournal::start("restart")?;
    let root = first.root.clone();
    let clock = first.clock.clone();
    let mut receipts = Vec::new();
    for n in 0..3 {
        receipts.push(first.append_event(n).await?);
    }
    for pair in receipts.windows(2) {
        if let [a, b] = pair {
            assert_eq!(b.seq, a.seq + 1);
        }
    }
    let last_before_restart = receipts.last().ok_or("no receipt")?.seq;
    let dir = first.config.dir.clone();
    first.stop().await?;

    let second = TestJournal::start_in(&root, clock)?;
    let after_restart = second.append_event(3).await?;
    assert!(after_restart.seq > last_before_restart);
    second.stop().await?;

    let records = common::read_records(&dir)?;
    for pair in records.windows(2) {
        if let [a, b] = pair {
            assert_eq!(b.seq, a.seq + 1, "gap between {} and {}", a.seq, b.seq);
        }
    }
    Ok(())
}

/// Counts fsync calls of the journal writer.
#[derive(Default)]
struct CountingProbe {
    syncs: AtomicUsize,
}

impl SyncProbe for CountingProbe {
    fn synced(&self) {
        self.syncs.fetch_add(1, Ordering::SeqCst);
    }
}

#[tokio::test]
async fn critical_record_is_fsynced_before_append_returns() -> TestResult {
    let root = common::temp_dir("fsync")?;
    let config = common::config(&root)?;
    let clock: Arc<dyn Clock> = Arc::new(FakeClock::new(common::start_time()?));
    let probe = Arc::new(CountingProbe::default());
    let signer = Ed25519FileSigner::load(&config.key_path)?;
    let (journal, writer) =
        Journal::start_with_probe(config, clock, Box::new(signer), probe.clone())?;
    let before = probe.syncs.load(Ordering::SeqCst);
    journal
        .append(
            Severity::Critical,
            Category::Robot,
            Actor::System("server"),
            RecordBody::EstopSent {
                robot: "robot-r2".parse()?,
                delivered: false,
            },
            None,
        )
        .await?;
    let after = probe.syncs.load(Ordering::SeqCst);
    assert!(
        after > before,
        "no fsync before append returned ({before} -> {after})"
    );
    journal.close().await?;
    writer.await?;
    Ok(())
}

#[cfg(unix)]
#[test]
fn world_readable_key_is_refused_with_explicit_message() -> TestResult {
    use std::os::unix::fs::PermissionsExt as _;

    let root = common::temp_dir("key")?;
    let config = common::config(&root)?;
    Ed25519FileSigner::load(&config.key_path)?;
    std::fs::set_permissions(&config.key_path, std::fs::Permissions::from_mode(0o644))?;
    let err = Ed25519FileSigner::load(&config.key_path)
        .err()
        .ok_or("a world-readable key was accepted")?;
    assert!(
        matches!(err, JournalError::KeyPermissions { .. }),
        "{err:?}"
    );
    assert!(err.to_string().contains("chmod 600"), "{err}");
    Ok(())
}

#[test]
fn audit_query_limit_above_500_is_rejected() -> TestResult {
    let query = |limit| AuditQuery {
        from: None,
        to: None,
        actor: None,
        category: None,
        limit,
        after_seq: None,
    };
    assert!(query(500).validate().is_ok());
    assert!(query(1).validate().is_ok());
    assert!(
        matches!(
            query(0).validate(),
            Err(JournalError::LimitOutOfRange { limit: 0, max: 500 })
        ),
        "limit 0 was accepted"
    );
    let err = query(501)
        .validate()
        .err()
        .ok_or("limit 501 was accepted")?;
    assert!(matches!(
        err,
        JournalError::LimitOutOfRange {
            limit: 501,
            max: 500
        }
    ));
    assert_eq!(
        err.to_string(),
        "Audit limit 501 is not allowed; use a limit between 1 and 500."
    );
    Ok(())
}

/// A lost journal key is never silently replaced (security review of step R1).
#[tokio::test]
async fn a_replaced_or_missing_key_is_refused_for_an_existing_journal() -> TestResult {
    let tj = TestJournal::start("key-lost")?;
    tj.append_event(1).await?;
    let clock = tj.clock.clone();
    let config = tj.config.clone();
    tj.stop().await?;

    // Missing key, journal has records: refused, nothing created.
    std::fs::remove_file(&config.key_path)?;
    let missing = Ed25519FileSigner::open_for_journal(&config.key_path, &config.dir).err();
    assert!(
        matches!(missing, Some(JournalError::KeyInvalid { .. })),
        "{missing:?}"
    );
    assert!(!config.key_path.exists());

    // A new key next to the old public key: refused, the old `.pub` is kept.
    let pub_path = audit::signer::public_key_path(&config.key_path);
    let old_pub = std::fs::read_to_string(&pub_path)?;
    let replaced = Ed25519FileSigner::load(&config.key_path).err();
    assert!(
        matches!(replaced, Some(JournalError::KeyInvalid { .. })),
        "{replaced:?}"
    );
    assert_eq!(std::fs::read_to_string(&pub_path)?, old_pub);

    // Even with the old `.pub` gone, the journal refuses a key its seals were not made with.
    std::fs::remove_file(&pub_path)?;
    let signer = Ed25519FileSigner::load(&config.key_path)?;
    let dyn_clock: Arc<dyn Clock> = clock;
    let started = Journal::start(config, dyn_clock, Box::new(signer)).err();
    assert!(
        matches!(&started, Some(JournalError::KeyInvalid { reason, .. }) if reason.contains("sealed with key")),
        "{:?}",
        started.map(|e| e.to_string())
    );
    Ok(())
}
