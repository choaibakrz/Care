//! Journal records. No free-text field accepts user input, so nothing personal can be put in
//! by accident. `hash = SHA-256(prev_hash ‖ canonical JSON of the record without hash)`.

use chrono::{DateTime, Utc};
use domain::incident::{IncidentChange, IncidentCode, IncidentId};
use domain::{
    AccountTag, Actor, BlockSource, BrainCallKind, ClinicChange, ClinicId, CommandName, DeviceId,
    FailureReason, ItemId, PlaceId, RobotId, Role, ScheduleId, StockAdjustReason, SystemMode,
    TaskId, TaskKind, TaskState, ZoneId,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use uuid::Uuid;

use crate::seal::Seal;

/// Severity. `Critical` is fsynced before `append` returns and triggers an immediate seal.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    /// Routine.
    Info,
    /// Worth noticing.
    Notice,
    /// Something went wrong but was handled.
    Warning,
    /// An error.
    Error,
    /// Grave: dumps the flight recorder and seals now.
    Critical,
}

/// Category.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Category {
    /// Actions by people and robots.
    Audit,
    /// Security decisions.
    Security,
    /// Robot events.
    Robot,
    /// Server events.
    System,
    /// Incident dumps.
    Incident,
    /// Seals.
    Seal,
}

/// What triggered an incident dump (the critical triggers of Task 9).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IncidentTrigger {
    /// An emergency stop was sent.
    EstopSent,
    /// An emergency stop could not be delivered.
    EstopNotDelivered,
    /// Journal verification failed.
    VerificationFailed,
    /// An en-route robot was lost.
    RobotLostEnRoute,
    /// Ten or more rejected logins in a minute from one network.
    LoginFlood,
    /// A journal write failed.
    JournalWriteFailed,
    /// An administrator changed configuration.
    AdminConfigChange,
}

/// One event kept by the flight recorder.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FlightEvent {
    /// When.
    pub at: DateTime<Utc>,
    /// Level (`DEBUG` … `ERROR`).
    pub level: String,
    /// Tracing target.
    pub target: String,
    /// Message, after redaction.
    pub message: String,
}

/// Typed record body.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum RecordBody {
    /// Login succeeded.
    LoginSucceeded {
        /// Device, when the client sent one (a browser sends none).
        device: Option<DeviceId>,
    },
    /// Login failed (no password anywhere).
    LoginFailed {
        /// Device, when the client sent one.
        device: Option<DeviceId>,
        /// Network label.
        network: String,
    },
    /// Task created.
    TaskCreated {
        /// Task.
        task: TaskId,
        /// Kind.
        kind: TaskKind,
        /// Item.
        item: Option<ItemId>,
        /// Destination.
        to: PlaceId,
    },
    /// Task state changed.
    TaskStateChanged {
        /// Task.
        task: TaskId,
        /// Before.
        from: TaskState,
        /// After.
        to: TaskState,
        /// Reason.
        reason: Option<FailureReason>,
    },
    /// Stock changed.
    StockAdjusted {
        /// Item.
        item: ItemId,
        /// Change.
        delta: i32,
        /// Count after.
        count_after: u32,
        /// Why.
        reason: StockAdjustReason,
    },
    /// Zone changed.
    ZoneChanged {
        /// Zone.
        zone: ZoneId,
        /// Version.
        version: u32,
        /// Deleted.
        deleted: bool,
    },
    /// A clinic plan was created, saved, activated or deleted (Task A4). The plan itself is
    /// not copied into the journal; it is in the clinic store under this id and version.
    ClinicChanged {
        /// Plan.
        clinic: ClinicId,
        /// Version after the change.
        version: u64,
        /// What changed.
        change: ClinicChange,
    },
    /// A brain call was served or failed (Task A6). Nothing of the text: the privacy rule
    /// keeps texts in memory only; the record says which function, how long it took, and
    /// whether it succeeded. The caller is the record's `actor`.
    BrainCall {
        /// Which function.
        kind: BrainCallKind,
        /// Time from request to answer, milliseconds.
        latency_ms: u64,
        /// Whether a draft was returned.
        ok: bool,
    },
    /// A non-estop command was sent. The actor is who sent it; a command from a non-admin
    /// also raises the admin alert `staff_command` carrying `command_id` (Task A7).
    RobotCommandSent {
        /// Robot.
        robot: RobotId,
        /// Command.
        command: CommandName,
        /// Delivered to the robot's queue.
        delivered: bool,
        /// The command's id (`CommandReceipt.command_id`), what a revert names.
        command_id: Uuid,
    },
    /// An admin reverted a non-admin's command by sending its inverse (Task A7). The actor
    /// is the admin.
    RobotCommandReverted {
        /// Robot.
        robot: RobotId,
        /// The command that was undone.
        command_id: Uuid,
        /// The inverse command sent (`resume` for `pause` and `dock`, `pause` for `resume`).
        inverse: CommandName,
        /// The id of that inverse command.
        reverted_by_command_id: Uuid,
    },
    /// An admin issued an enrolment code (Task A7). Journaled by code id only: the code
    /// itself is a secret until used.
    EnrolmentCodeIssued {
        /// The code's id.
        code_id: Uuid,
        /// The role the new account will get.
        role: Role,
        /// When the code stops working.
        expires_at: DateTime<Utc>,
    },
    /// A person enrolled with a code (Task A7). The actor is the new account.
    AccountEnrolled {
        /// The code's id.
        code_id: Uuid,
        /// The new account's tag.
        account: AccountTag,
        /// Its role.
        role: Role,
    },
    /// An admin disabled an account (Task A7); its tokens were revoked.
    AccountDisabled {
        /// The account's tag.
        account: AccountTag,
    },
    /// Emergency mode was switched on or off (Task A8, E1). The actor is the admin. `reason`
    /// is the admin's own short text (at most 200 characters, `emergency-mode.md` asks for
    /// it); the console tells the admin it is journaled.
    SystemModeChanged {
        /// The mode before.
        from: SystemMode,
        /// The mode after.
        to: SystemMode,
        /// Why, as given with the switch.
        reason: Option<String>,
    },
    /// An admin freed a tablet (Task A8, T8b): its session was revoked. No label: a staff
    /// pseudonym is never journaled with a device.
    DeviceFreed {
        /// The tablet.
        device: DeviceId,
    },
    /// An admin handed a tablet out (Task A8, T8b). The bed label for a bedside tablet only;
    /// never a staff pseudonym, never a patient.
    DeviceAssigned {
        /// The tablet.
        device: DeviceId,
        /// A bedside tablet (else a staff one).
        bedside: bool,
        /// The bed label of a bedside tablet ("Bed 12"); `None` for a staff tablet.
        bed_label: Option<String>,
    },
    /// A client address or block was blocked (Task A8, T7b): by an admin (the actor) or by
    /// the server's detection rules (actor `system:server`).
    ClientBlocked {
        /// Rule id (`blk-<n>`).
        rule: String,
        /// The address or CIDR block.
        target: String,
        /// Why (the admin's text, or the rule that fired).
        reason: String,
        /// `manual` or `auto`.
        source: BlockSource,
        /// When it ends; `None` = until removed.
        expires_at: Option<DateTime<Utc>>,
    },
    /// A block rule ended (Task A8, T7b): it expired, or an admin (the actor) removed it.
    ClientUnblocked {
        /// Rule id.
        rule: String,
        /// The address or CIDR block.
        target: String,
        /// It expired (else it was removed).
        expired: bool,
    },
    /// The emergency stop was sent.
    EstopSent {
        /// Robot.
        robot: RobotId,
        /// Delivered.
        delivered: bool,
    },
    /// A schedule changed.
    ScheduleChanged {
        /// Schedule.
        schedule: ScheduleId,
        /// Enabled after the change.
        enabled: bool,
    },
    /// A schedule run was skipped (older than grace).
    ScheduleMissed {
        /// Schedule.
        schedule: ScheduleId,
        /// Scheduled time.
        scheduled_for: DateTime<Utc>,
    },
    /// An incident was raised, acknowledged or closed. Who acknowledged or closed it is the
    /// record's `actor`; there is no free-text field.
    IncidentChanged {
        /// Incident.
        id: IncidentId,
        /// Code from the closed catalogue.
        code: IncidentCode,
        /// What changed.
        change: IncidentChange,
    },
    /// The security stack rejected a request.
    SecurityRejected {
        /// Error code (fixed list).
        code: String,
        /// Network label.
        network: String,
    },
    /// WARN+ tracing event copied by `JournalLayer` (redacted).
    SystemEvent {
        /// Target.
        target: String,
        /// Message.
        message: String,
    },
    /// Flight-recorder dump on a critical record.
    Incident {
        /// Trigger.
        trigger: IncidentTrigger,
        /// Events that led up to it.
        recent: Vec<FlightEvent>,
    },
    /// A seal.
    Seal(Seal),
}

/// A record as written.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct JournalRecord {
    /// Gapless sequence number.
    pub seq: u64,
    /// When written (server clock).
    pub ingested_at: DateTime<Utc>,
    /// When it happened (source clock).
    pub event_at: Option<DateTime<Utc>>,
    /// Set when `event_at` is older than the previous seal.
    pub late_by_ms: Option<u64>,
    /// Severity.
    pub severity: Severity,
    /// Category.
    pub category: Category,
    /// Author.
    pub actor: Actor,
    /// Body.
    pub body: RecordBody,
    /// Previous record's hash.
    #[serde(with = "crate::record::hex_bytes")]
    pub prev_hash: [u8; 32],
    /// This record's hash.
    #[serde(with = "crate::record::hex_bytes")]
    pub hash: [u8; 32],
}

impl JournalRecord {
    /// Canonical JSON of the record without `hash` (the hashed bytes).
    ///
    /// # Errors
    /// `Serialize`.
    pub fn canonical_bytes(&self) -> Result<Vec<u8>, crate::JournalError> {
        canonical_json(self, Some("hash"))
    }

    /// Recomputes the hash from `prev_hash` and the canonical bytes.
    ///
    /// # Errors
    /// `Serialize`.
    pub fn compute_hash(&self) -> Result<[u8; 32], crate::JournalError> {
        let mut hasher = Sha256::new();
        hasher.update(self.prev_hash);
        hasher.update(self.canonical_bytes()?);
        Ok(hasher.finalize().into())
    }
}

/// Canonical JSON of `value`: object keys sorted at every level, no spaces, with the
/// top-level key `without` removed (the hash or the signature being computed).
///
/// # Errors
/// `Serialize`.
pub(crate) fn canonical_json<T: Serialize>(
    value: &T,
    without: Option<&str>,
) -> Result<Vec<u8>, crate::JournalError> {
    let serialize = |error: serde_json::Error| crate::JournalError::Serialize {
        reason: error.to_string(),
    };
    let mut value = serde_json::to_value(value).map_err(serialize)?;
    if let (Some(key), Some(object)) = (without, value.as_object_mut()) {
        object.remove(key);
    }
    serde_json::to_vec(&sorted(value)).map_err(serialize)
}

/// `value` with every object's keys in sorted order.
fn sorted(value: serde_json::Value) -> serde_json::Value {
    match value {
        serde_json::Value::Object(object) => {
            let mut entries: Vec<(String, serde_json::Value)> = object.into_iter().collect();
            entries.sort_by(|a, b| a.0.cmp(&b.0));
            serde_json::Value::Object(
                entries
                    .into_iter()
                    .map(|(key, value)| (key, sorted(value)))
                    .collect(),
            )
        }
        serde_json::Value::Array(items) => {
            serde_json::Value::Array(items.into_iter().map(sorted).collect())
        }
        other => other,
    }
}

/// Returned by `Journal::append`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RecordReceipt {
    /// Sequence number.
    pub seq: u64,
    /// Record hash.
    pub hash: [u8; 32],
}

/// Hex (lowercase) serde for fixed-size byte arrays: hashes, signatures.
pub mod hex_bytes {
    use serde::{Deserializer, Serializer};

    /// Writes lowercase hex.
    ///
    /// # Errors
    /// Never fails beyond the serializer's own errors.
    pub fn serialize<S: Serializer, const N: usize>(
        bytes: &[u8; N],
        serializer: S,
    ) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&to_hex(bytes))
    }

    /// Lowercase hex of `bytes`.
    #[must_use]
    pub fn to_hex(bytes: &[u8]) -> String {
        use std::fmt::Write as _;
        bytes
            .iter()
            .fold(String::with_capacity(bytes.len() * 2), |mut out, byte| {
                let _ignored = write!(out, "{byte:02x}");
                out
            })
    }

    /// Bytes of exactly `N` from hex (either case); `None` when malformed.
    #[must_use]
    pub fn from_hex<const N: usize>(text: &str) -> Option<[u8; N]> {
        let text = text.trim();
        if text.len() != N * 2 || !text.is_ascii() {
            return None;
        }
        let mut out = [0_u8; N];
        for (slot, pair) in out.iter_mut().zip(text.as_bytes().chunks(2)) {
            let pair = std::str::from_utf8(pair).ok()?;
            *slot = u8::from_str_radix(pair, 16).ok()?;
        }
        Some(out)
    }

    /// Reads lowercase hex of exactly `N` bytes.
    ///
    /// # Errors
    /// Wrong length or non-hex characters.
    pub fn deserialize<'de, D: Deserializer<'de>, const N: usize>(
        deserializer: D,
    ) -> Result<[u8; N], D::Error> {
        let text = <String as serde::Deserialize>::deserialize(deserializer)?;
        from_hex::<N>(&text)
            .ok_or_else(|| serde::de::Error::custom(format!("expected {} hex digits", N * 2)))
    }
}
