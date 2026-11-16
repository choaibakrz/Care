//! Shared helpers for the journal tests: a journal in a fresh temporary directory, driven by
//! a `FakeClock`, with its signing key and anchor outside the journal directory.
#![allow(dead_code)]

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use audit::{
    Category, Ed25519FileSigner, Journal, JournalConfig, JournalRecord, RecordBody, RecordReceipt,
    SealReason, Severity,
};
use chrono::{DateTime, TimeZone, Utc};
use domain::{Actor, Clock, FakeClock};
use tokio::task::JoinHandle;

/// Error type of the helpers.
pub type BoxError = Box<dyn std::error::Error + Send + Sync>;
/// Result of the helpers and tests.
pub type Res<T> = Result<T, BoxError>;

/// 2026-11-14 08:00:00 UTC.
///
/// # Errors
/// Never in practice.
pub fn start_time() -> Res<DateTime<Utc>> {
    Utc.with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
        .single()
        .ok_or_else(|| "invalid test start time".into())
}

/// A fresh directory under the system temporary directory.
///
/// # Errors
/// When it cannot be created.
pub fn temp_dir(name: &str) -> Res<PathBuf> {
    let dir = std::env::temp_dir()
        .join("clinic-journal-tests")
        .join(format!("{name}-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

/// Journal settings rooted in `root`: `journal/`, `keys/`, `anchor/`, `logs/`.
///
/// # Errors
/// When the directories cannot be created.
pub fn config(root: &Path) -> Res<JournalConfig> {
    let config = JournalConfig {
        dir: root.join("journal"),
        seal_interval: Duration::from_mins(1),
        segment_max_bytes: 64 * 1024 * 1024,
        batch_fsync: Duration::from_secs(1),
        key_path: root.join("keys").join("journal.key"),
        anchor_paths: vec![root.join("anchor").join("anchor.log")],
        flight_window: Duration::from_secs(30),
        flight_capacity: 10_000,
        emergency_fallback: root.join("estop-fallback.log"),
        log_dir: root.join("logs"),
    };
    for dir in [
        &config.dir,
        &config.log_dir,
        &root.join("keys"),
        &root.join("anchor"),
    ] {
        std::fs::create_dir_all(dir)?;
    }
    Ok(config)
}

/// A running journal and what the tests need around it.
pub struct TestJournal {
    /// The journal.
    pub journal: Journal,
    /// The writer task.
    pub writer: JoinHandle<()>,
    /// Settings.
    pub config: JournalConfig,
    /// The fake clock.
    pub clock: Arc<FakeClock>,
    /// The root temporary directory.
    pub root: PathBuf,
}

impl TestJournal {
    /// Starts a journal in a fresh directory.
    ///
    /// # Errors
    /// Startup errors.
    pub fn start(name: &str) -> Res<TestJournal> {
        let root = temp_dir(name)?;
        let clock = Arc::new(FakeClock::new(start_time()?));
        TestJournal::start_in(&root, clock)
    }

    /// Starts (or restarts) a journal in `root`.
    ///
    /// # Errors
    /// Startup errors.
    pub fn start_in(root: &Path, clock: Arc<FakeClock>) -> Res<TestJournal> {
        let config = config(root)?;
        let signer = Ed25519FileSigner::load(&config.key_path)?;
        let dyn_clock: Arc<dyn Clock> = clock.clone();
        let (journal, writer) = Journal::start(config.clone(), dyn_clock, Box::new(signer))?;
        Ok(TestJournal {
            journal,
            writer,
            config,
            clock,
            root: root.to_path_buf(),
        })
    }

    /// Appends `SystemEvent { target: "test", message: "event <n>" }` at `Info`.
    ///
    /// # Errors
    /// Journal errors.
    pub async fn append_event(&self, n: u32) -> Res<RecordReceipt> {
        Ok(append_event(&self.journal, n).await?)
    }

    /// Seals (`Shutdown`), closes and waits for the writer.
    ///
    /// # Errors
    /// Journal errors.
    pub async fn stop(self) -> Res<()> {
        self.journal.seal_now(SealReason::Shutdown).await?;
        self.journal.close().await?;
        self.writer.await?;
        Ok(())
    }

    /// The public key matching the signing key.
    ///
    /// # Errors
    /// Key errors.
    pub fn verifying_key(&self) -> Res<ed25519_dalek::VerifyingKey> {
        Ok(Ed25519FileSigner::load(&self.config.key_path)?.verifying_key())
    }
}

/// Appends `SystemEvent { target: "test", message: "event <n>" }` at `Info`.
///
/// # Errors
/// Journal errors.
pub async fn append_event(journal: &Journal, n: u32) -> Result<RecordReceipt, audit::JournalError> {
    journal
        .append(
            Severity::Info,
            Category::System,
            Actor::System("server"),
            RecordBody::SystemEvent {
                target: "test".to_owned(),
                message: format!("event {n}"),
            },
            None,
        )
        .await
}

/// Regular files of `dir`, sorted by name.
///
/// # Errors
/// When the directory cannot be read.
pub fn files(dir: &Path) -> Res<Vec<PathBuf>> {
    let mut files = Vec::new();
    for entry in std::fs::read_dir(dir)? {
        let path = entry?.path();
        if path.is_file() {
            files.push(path);
        }
    }
    files.sort();
    Ok(files)
}

/// Every record of the journal files of `dir` (lines that parse), sorted by `seq`.
///
/// # Errors
/// When a file cannot be read.
pub fn read_records(dir: &Path) -> Res<Vec<JournalRecord>> {
    let mut records = Vec::new();
    for path in files(dir)? {
        let text = std::fs::read_to_string(&path)?;
        records.extend(
            text.lines()
                .filter_map(|line| serde_json::from_str::<JournalRecord>(line).ok()),
        );
    }
    records.sort_by_key(|r| r.seq);
    Ok(records)
}

/// The seals found in the journal files, in `seq` order of their records.
///
/// # Errors
/// When a file cannot be read.
pub fn read_seals(dir: &Path) -> Res<Vec<audit::Seal>> {
    Ok(read_records(dir)?
        .into_iter()
        .filter_map(|r| match r.body {
            RecordBody::Seal(seal) => Some(seal),
            _ => None,
        })
        .collect())
}

/// Rewrites the journal files of `dir`, replacing each line that contains `needle` with
/// what `edit` returns (`None` deletes the line). Returns how many lines were touched.
///
/// # Errors
/// When a file cannot be read or written.
pub fn edit_lines(dir: &Path, needle: &str, edit: impl Fn(&str) -> Option<String>) -> Res<usize> {
    let mut touched = 0;
    for path in files(dir)? {
        let text = std::fs::read_to_string(&path)?;
        let mut out = String::with_capacity(text.len());
        for line in text.split_inclusive('\n') {
            if line.contains(needle) {
                touched += 1;
                if let Some(new) = edit(line) {
                    out.push_str(&new);
                }
            } else {
                out.push_str(line);
            }
        }
        std::fs::write(&path, out)?;
    }
    Ok(touched)
}
