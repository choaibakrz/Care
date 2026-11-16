//! The journal handle and its single writer task.

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::{Actor, Clock, RobotId};
use tokio::sync::{broadcast, mpsc, oneshot};
use tokio::task::JoinHandle;

use crate::anchor::{AnchorSink as _, FileAnchor};
use crate::error::JournalError;
use crate::flight_recorder::FlightRecorder;
use crate::record::JournalRecord;
use crate::record::{Category, RecordBody, RecordReceipt, Severity};
use crate::seal::Seal;
use crate::segment::Segment;
use crate::signer::Signer;

/// Journal settings.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JournalConfig {
    /// Segment directory.
    pub dir: PathBuf,
    /// Seal period (default 60 s).
    pub seal_interval: Duration,
    /// Segment rotation size (default 64 MiB).
    pub segment_max_bytes: u64,
    /// Non-critical fsync batch period (default 1 s): the most a power cut can lose.
    pub batch_fsync: Duration,
    /// Signing key, outside `dir`.
    pub key_path: PathBuf,
    /// Anchor files (another disk or USB path).
    pub anchor_paths: Vec<PathBuf>,
    /// Flight-recorder window (default 30 s).
    pub flight_window: Duration,
    /// Flight-recorder capacity (default 10 000 events).
    pub flight_capacity: usize,
    /// Where the emergency-stop record goes when the journal cannot write.
    pub emergency_fallback: PathBuf,
    /// Rotated `tracing-appender` files covered by seals.
    pub log_dir: PathBuf,
}

impl JournalConfig {
    /// Defaults for a journal in `dir` with its key at `key_path`.
    #[must_use]
    pub fn with_defaults(dir: PathBuf, key_path: PathBuf) -> JournalConfig {
        let parent = dir.parent().map(Path::to_path_buf).unwrap_or_default();
        JournalConfig {
            seal_interval: Duration::from_mins(1),
            segment_max_bytes: 64 * 1024 * 1024,
            batch_fsync: Duration::from_secs(1),
            key_path,
            anchor_paths: Vec::new(),
            flight_window: Duration::from_secs(30),
            flight_capacity: 10_000,
            emergency_fallback: parent.join("estop-fallback.log"),
            log_dir: parent.join("logs"),
            dir,
        }
    }
}

/// Why a seal is written.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SealReason {
    /// Every `seal_interval`.
    Interval,
    /// After a critical record.
    Critical,
    /// On shutdown.
    Shutdown,
    /// On segment rotation.
    Rotation,
}

/// Requests to the writer, in one queue so seals cover everything submitted before them.
enum WriterRequest {
    Append {
        severity: Severity,
        category: Category,
        actor: Actor,
        body: Box<RecordBody>,
        event_at: Option<DateTime<Utc>>,
        reply: oneshot::Sender<Result<RecordReceipt, JournalError>>,
    },
    Seal {
        reason: SealReason,
        reply: oneshot::Sender<Result<Seal, JournalError>>,
    },
    Close {
        reply: oneshot::Sender<Result<(), JournalError>>,
    },
}

/// A cheap, cloneable handle on the journal.
#[derive(Clone)]
pub struct Journal {
    requests: mpsc::Sender<WriterRequest>,
    writable: Arc<AtomicBool>,
    recorder: FlightRecorder,
    seals: broadcast::Sender<Seal>,
    emergency_fallback: PathBuf,
}

/// Observes the journal writer's fsync calls. Production passes none; tests count them.
pub trait SyncProbe: Send + Sync {
    /// Called after each successful fsync of a journal segment.
    fn synced(&self);
}

impl Journal {
    /// Opens the last segment, verifies its tail, resumes `seq`, spawns the single writer.
    ///
    /// # Errors
    /// `Io`; `Corrupt`; `KeyInvalid`.
    pub fn start(
        config: JournalConfig,
        clock: Arc<dyn Clock>,
        signer: Box<dyn Signer>,
    ) -> Result<(Journal, JoinHandle<()>), JournalError> {
        Journal::spawn(config, clock, signer, None)
    }

    /// Same as [`Journal::start`], and reports every segment fsync to `probe` (tests count
    /// them to check that a `Critical` record is synced before `append` returns).
    ///
    /// # Errors
    /// Same as [`Journal::start`].
    pub fn start_with_probe(
        config: JournalConfig,
        clock: Arc<dyn Clock>,
        signer: Box<dyn Signer>,
        probe: Arc<dyn SyncProbe>,
    ) -> Result<(Journal, JoinHandle<()>), JournalError> {
        Journal::spawn(config, clock, signer, Some(probe))
    }

    /// Opens the journal directory, resumes the chain and spawns the writer task.
    fn spawn(
        config: JournalConfig,
        clock: Arc<dyn Clock>,
        signer: Box<dyn Signer>,
        probe: Option<Arc<dyn SyncProbe>>,
    ) -> Result<(Journal, JoinHandle<()>), JournalError> {
        let (segment, tail) = Segment::open_last(&config.dir)?;
        if tail.torn {
            tracing::warn!(
                target: "audit",
                "the last journal line was half-written (a crash?); a new segment was started"
            );
        }
        let (last_seal, last_seal_seq) = last_seal(&config.dir)?;
        if let Some(seal) = &last_seal
            && seal.key_fingerprint != signer.fingerprint()
        {
            return Err(JournalError::KeyInvalid {
                path: config.key_path.clone(),
                reason: format!(
                    "the journal was sealed with key {}, the current key is {}; restore the key from the backup",
                    seal.key_fingerprint,
                    signer.fingerprint()
                ),
            });
        }
        let prev_seal_hash = match &last_seal {
            Some(seal) => seal.hash()?,
            None => [0; 32],
        };
        let next_seq = tail.last_seq.map_or(0, |seq| seq + 1);
        let (requests, receiver) = mpsc::channel(1024);
        let writable = Arc::new(AtomicBool::new(true));
        let (seals, _) = broadcast::channel(16);
        let recorder =
            FlightRecorder::new(config.flight_window, config.flight_capacity, clock.clone());
        let journal = Journal {
            requests,
            writable: writable.clone(),
            recorder,
            seals: seals.clone(),
            emergency_fallback: config.emergency_fallback.clone(),
        };
        let writer = Writer {
            anchors: config
                .anchor_paths
                .iter()
                .cloned()
                .map(FileAnchor::new)
                .collect(),
            config,
            clock,
            signer,
            probe,
            segment,
            next_seq,
            last_hash: tail.last_hash,
            prev_seal_hash,
            // The previous seal's own record is the first one the next seal covers.
            first_unsealed: last_seal_seq.unwrap_or(next_seq),
            pending: 0,
            dirty: false,
            oldest_event: None,
            latest_event: None,
            late: 0,
            last_seal,
            writable,
            seals,
        };
        let handle = tokio::spawn(writer.run(receiver));
        Ok((journal, handle))
    }

    /// Appends a record. `Critical` records are fsynced before returning and trigger a seal.
    ///
    /// # Errors
    /// `WriterStopped`; `Io` (the journal then turns non-writable: degraded mode).
    pub async fn append(
        &self,
        severity: Severity,
        category: Category,
        actor: Actor,
        body: RecordBody,
        event_at: Option<DateTime<Utc>>,
    ) -> Result<RecordReceipt, JournalError> {
        let (reply, answer) = oneshot::channel();
        self.requests
            .send(WriterRequest::Append {
                severity,
                category,
                actor,
                body: Box::new(body),
                event_at,
                reply,
            })
            .await
            .map_err(|_| JournalError::WriterStopped)?;
        answer.await.map_err(|_| JournalError::WriterStopped)?
    }

    /// Seals now.
    ///
    /// # Errors
    /// `WriterStopped`; `Signature`; `Io`.
    pub async fn seal_now(&self, reason: SealReason) -> Result<Seal, JournalError> {
        let (reply, answer) = oneshot::channel();
        self.requests
            .send(WriterRequest::Seal { reason, reply })
            .await
            .map_err(|_| JournalError::WriterStopped)?;
        answer.await.map_err(|_| JournalError::WriterStopped)?
    }

    /// Flushes and stops the writer (after the final seal).
    ///
    /// # Errors
    /// `WriterStopped`; `Io`.
    pub async fn close(&self) -> Result<(), JournalError> {
        let (reply, answer) = oneshot::channel();
        self.requests
            .send(WriterRequest::Close { reply })
            .await
            .map_err(|_| JournalError::WriterStopped)?;
        answer.await.map_err(|_| JournalError::WriterStopped)?
    }

    /// Whether records can be written (false means degraded mode).
    #[must_use]
    pub fn is_writable(&self) -> bool {
        self.writable.load(Ordering::SeqCst)
    }

    /// The flight recorder (a tracing layer) owned by this journal.
    #[must_use]
    pub fn flight_recorder(&self) -> FlightRecorder {
        self.recorder.clone()
    }

    /// Every seal written from now on (admin-panel live anchor).
    #[must_use]
    pub fn subscribe_seals(&self) -> broadcast::Receiver<Seal> {
        self.seals.subscribe()
    }

    /// Records an emergency stop in the fallback file when the journal cannot write.
    /// Safety before bookkeeping: the stop has already been sent.
    ///
    /// # Errors
    /// `Io` on the fallback file.
    pub fn record_estop_fallback(
        &self,
        actor: &Actor,
        robot: &RobotId,
        delivered: bool,
        at: DateTime<Utc>,
    ) -> Result<(), JournalError> {
        use std::io::Write as _;
        let line = serde_json::json!({
            "type": "estop_fallback",
            "actor": actor,
            "robot": robot,
            "delivered": delivered,
            "at": at,
        });
        let io = |source| JournalError::Io {
            action: "write the emergency-stop fallback file",
            path: self.emergency_fallback.clone(),
            source,
        };
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.emergency_fallback)
            .map_err(io)?;
        file.write_all(format!("{line}\n").as_bytes())
            .and_then(|()| file.sync_data())
            .map_err(io)
    }
}

/// The last seal of the journal in `dir` and the `seq` of its record.
fn last_seal(dir: &Path) -> Result<(Option<Seal>, Option<u64>), JournalError> {
    let mut found = (None, None);
    for (_, path) in crate::segment::segment_files(dir)? {
        for record in crate::segment::read_segment(&path)?.records {
            if let RecordBody::Seal(seal) = record.body {
                found = (Some(seal), Some(record.seq));
            }
        }
    }
    Ok(found)
}

/// The single writer: owns the open segment and the chain state.
struct Writer {
    config: JournalConfig,
    clock: Arc<dyn Clock>,
    signer: Box<dyn Signer>,
    probe: Option<Arc<dyn SyncProbe>>,
    anchors: Vec<FileAnchor>,
    segment: Segment,
    next_seq: u64,
    last_hash: [u8; 32],
    prev_seal_hash: [u8; 32],
    /// First `seq` the next seal covers.
    first_unsealed: u64,
    /// Records other than seals since the last seal.
    pending: u64,
    /// Written but not yet fsynced.
    dirty: bool,
    oldest_event: Option<DateTime<Utc>>,
    latest_event: Option<DateTime<Utc>>,
    late: u32,
    last_seal: Option<Seal>,
    writable: Arc<AtomicBool>,
    seals: broadcast::Sender<Seal>,
}

impl Writer {
    async fn run(mut self, mut requests: mpsc::Receiver<WriterRequest>) {
        let mut seal_timer =
            tokio::time::interval(self.config.seal_interval.max(Duration::from_secs(1)));
        let mut fsync_timer =
            tokio::time::interval(self.config.batch_fsync.max(Duration::from_millis(10)));
        seal_timer.tick().await;
        fsync_timer.tick().await;
        loop {
            tokio::select! {
                request = requests.recv() => {
                    let Some(request) = request else { break };
                    if self.handle(request) {
                        break;
                    }
                }
                _ = seal_timer.tick() => {
                    if self.pending > 0
                        && let Err(error) = self.seal(SealReason::Interval)
                    {
                        tracing::error!(target: "audit", %error, "interval seal failed");
                    }
                }
                _ = fsync_timer.tick() => {
                    if let Err(error) = self.sync() {
                        tracing::error!(target: "audit", %error, "journal fsync failed");
                    }
                }
            }
        }
    }

    /// Serves one request; `true` when the writer must stop.
    fn handle(&mut self, request: WriterRequest) -> bool {
        match request {
            WriterRequest::Append {
                severity,
                category,
                actor,
                body,
                event_at,
                reply,
            } => {
                let result = self.append(severity, category, actor, *body, event_at);
                let _ignored = reply.send(result);
                false
            }
            WriterRequest::Seal { reason, reply } => {
                let _ignored = reply.send(self.seal(reason));
                false
            }
            WriterRequest::Close { reply } => {
                let synced = self.sync();
                // A closed journal records nothing more: the server is in degraded mode.
                self.writable.store(false, Ordering::SeqCst);
                let _ignored = reply.send(synced);
                true
            }
        }
    }

    fn sync(&mut self) -> Result<(), JournalError> {
        if !self.dirty {
            return Ok(());
        }
        self.segment.sync().inspect_err(|_| self.degrade())?;
        self.dirty = false;
        if let Some(probe) = &self.probe {
            probe.synced();
        }
        Ok(())
    }

    fn degrade(&self) {
        self.writable.store(false, Ordering::SeqCst);
    }

    /// Writes one record (hash-chained); `Critical` is fsynced and sealed at once.
    fn append(
        &mut self,
        severity: Severity,
        category: Category,
        actor: Actor,
        body: RecordBody,
        event_at: Option<DateTime<Utc>>,
    ) -> Result<RecordReceipt, JournalError> {
        let is_seal = matches!(body, RecordBody::Seal(_));
        let now = self.clock.now();
        let late_by_ms = match (event_at, &self.last_seal) {
            (Some(at), Some(seal)) if at < seal.sealed_at => {
                Some(u64::try_from((now - at).num_milliseconds()).unwrap_or(0))
            }
            _ => None,
        };
        let mut record = JournalRecord {
            seq: self.next_seq,
            ingested_at: now,
            event_at,
            late_by_ms,
            severity,
            category,
            actor,
            body,
            prev_hash: self.last_hash,
            hash: [0; 32],
        };
        record.hash = record.compute_hash()?;
        let line = serde_json::to_vec(&record).map_err(|error| JournalError::Serialize {
            reason: error.to_string(),
        })?;
        let size = u64::try_from(line.len()).unwrap_or(u64::MAX);
        if self.segment.bytes() > 0
            && self.segment.bytes().saturating_add(size) > self.config.segment_max_bytes
        {
            self.segment = self
                .segment
                .rotate(&self.config.dir)
                .inspect_err(|_| self.degrade())?;
        }
        self.segment
            .append_line(&line)
            .inspect_err(|_| self.degrade())?;
        self.dirty = true;
        self.next_seq += 1;
        self.last_hash = record.hash;
        if !is_seal {
            self.pending += 1;
            if let Some(at) = event_at {
                self.oldest_event = Some(self.oldest_event.map_or(at, |old| old.min(at)));
                self.latest_event = Some(self.latest_event.map_or(at, |old| old.max(at)));
            }
            if late_by_ms.is_some() {
                self.late = self.late.saturating_add(1);
            }
        }
        let receipt = RecordReceipt {
            seq: record.seq,
            hash: record.hash,
        };
        if severity == Severity::Critical {
            self.sync()?;
            self.seal(SealReason::Critical)?;
        }
        Ok(receipt)
    }

    /// Seals every record since the previous seal, signs, writes the seal record, fsyncs,
    /// copies the hash to the anchors and broadcasts it. With nothing new to seal, returns
    /// the previous seal.
    fn seal(&mut self, reason: SealReason) -> Result<Seal, JournalError> {
        if self.pending == 0
            && let Some(seal) = &self.last_seal
        {
            return Ok(seal.clone());
        }
        let last_seq = self.next_seq.saturating_sub(1);
        let count = self.next_seq.saturating_sub(self.first_unsealed);
        let mut seal = Seal {
            first_seq: self.first_unsealed,
            last_seq,
            count,
            chain_head: self.last_hash,
            prev_seal_hash: self.prev_seal_hash,
            sealed_at: self.clock.now(),
            oldest_event_at: self.oldest_event,
            latest_event_at: self.latest_event,
            late_records: self.late,
            // BUILD-OUT (step R1): rotated log files are not digested yet.
            sealed_files: Vec::new(),
            key_fingerprint: self.signer.fingerprint(),
            signature: crate::signer::Signature([0; 64]),
        };
        seal.signature = self.signer.sign(&seal.signing_bytes()?)?;
        let seal_hash = seal.hash()?;
        let receipt = self.append(
            Severity::Notice,
            Category::Seal,
            Actor::System("journal"),
            RecordBody::Seal(seal.clone()),
            None,
        )?;
        self.sync()?;
        self.first_unsealed = receipt.seq;
        self.prev_seal_hash = seal_hash;
        self.pending = 0;
        self.oldest_event = None;
        self.latest_event = None;
        self.late = 0;
        self.last_seal = Some(seal.clone());
        for anchor in &self.anchors {
            if let Err(error) = anchor.append(&seal_hash, seal.last_seq, seal.sealed_at) {
                tracing::error!(target: "audit", %error, "journal anchor not written");
            }
        }
        tracing::debug!(target: "audit", ?reason, last_seq = seal.last_seq, "journal sealed");
        let _no_listener = self.seals.send(seal.clone());
        Ok(seal)
    }
}
