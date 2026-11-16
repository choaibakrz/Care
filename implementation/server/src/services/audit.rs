//! Real `AuditQueryService`, `JournalStatus` for the journal, and the seal forwarder (the
//! admin-panel live anchor).

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use audit::{AuditIndex, IncidentTrigger, Journal, JournalRecord, RecordBody, Seal, VerifyReport};
use chrono::{DateTime, Utc};
use domain::incident::{IncidentChange, IncidentCode, IncidentId};
use domain::ports::AccountRepository;
use domain::{
    AccountTag, Actor, BlockSource, BrainCallKind, ClinicChange, ClinicId, CommandName, DeviceId,
    FailureReason, ItemId, PlaceId, RobotId, Role, ScheduleId, StockAdjustReason, SystemMode,
    TaskId, TaskKind, TaskState, ZoneId,
};
use realtime::{AlertKind, AppEvent, Hub};
use tokio::sync::RwLock;
use tokio::task::JoinHandle;
use uuid::Uuid;

use super::{AuditQueryService, JournalStatus};
use crate::dto::{AuditEntry, AuditPageView, AuditQueryParams, AuditResult};
use crate::error::ApiError;

/// Audit queries over the index.
pub struct JournalAuditQuery {
    index: Arc<dyn AuditIndex>,
    journal: Journal,
    last_report: RwLock<Option<VerifyReport>>,
    verify: Option<VerifyPaths>,
    accounts: Option<Arc<dyn AccountRepository>>,
    /// The last journal `seq` copied into the index (`None` before the first catch-up).
    indexed: tokio::sync::Mutex<Option<u64>>,
}

/// Where `integrity` finds the journal files, the public key and the anchors.
#[derive(Debug, Clone)]
pub struct VerifyPaths {
    /// Journal directory.
    pub dir: PathBuf,
    /// Public key file (`<signing key>.pub`).
    pub public_key: PathBuf,
    /// Anchor files.
    pub anchors: Vec<PathBuf>,
}

impl JournalAuditQuery {
    /// A service.
    #[must_use]
    pub fn new(index: Arc<dyn AuditIndex>, journal: Journal) -> JournalAuditQuery {
        JournalAuditQuery {
            index,
            journal,
            last_report: RwLock::new(None),
            verify: None,
            accounts: None,
            indexed: tokio::sync::Mutex::new(None),
        }
    }

    /// Copies the journal records written since the last call into the index (the journal
    /// files are the source of truth; the index only serves queries). Needs the journal
    /// directory from [`JournalAuditQuery::with_verify`]; without it the index is left as is.
    ///
    /// # Errors
    /// The files cannot be read, or the index refuses a record.
    async fn catch_up_index(&self) -> Result<(), ApiError> {
        let Some(paths) = &self.verify else {
            return Ok(());
        };
        let mut indexed = self.indexed.lock().await;
        let after = *indexed;
        let dir = paths.dir.clone();
        let records = tokio::task::spawn_blocking(move || {
            let mut fresh = Vec::new();
            for (_, path) in audit::segment::segment_files(&dir)? {
                let read = audit::segment::read_segment(&path)?;
                fresh.extend(
                    read.records
                        .into_iter()
                        .filter(|record| after.is_none_or(|last| record.seq > last)),
                );
            }
            Ok::<_, audit::JournalError>(fresh)
        })
        .await
        .map_err(|_| ApiError::internal("journal index"))??;
        for record in &records {
            self.index.insert(record).await?;
            if indexed.is_none_or(|last| record.seq > last) {
                *indexed = Some(record.seq);
            }
        }
        Ok(())
    }

    /// Lets `integrity` run a verification of the journal files.
    #[must_use]
    pub fn with_verify(mut self, paths: VerifyPaths) -> JournalAuditQuery {
        self.verify = Some(paths);
        self
    }

    /// Lets audit rows show users by their owner label (`"<pseudonym> #<tag>"`).
    #[must_use]
    pub fn with_accounts(mut self, accounts: Arc<dyn AccountRepository>) -> JournalAuditQuery {
        self.accounts = Some(accounts);
        self
    }

    /// `user:<id>` -> owner label, for every known account.
    async fn user_labels(&self) -> Result<HashMap<String, String>, ApiError> {
        let mut labels = HashMap::new();
        let Some(accounts) = &self.accounts else {
            return Ok(labels);
        };
        for account in accounts.list().await? {
            let (Ok(user), Ok(label)) = (account.id.user_id(), account.owner_label()) else {
                continue;
            };
            labels.insert(Actor::User(user).to_string(), label.as_str().to_owned());
        }
        Ok(labels)
    }
}

#[async_trait]
impl AuditQueryService for JournalAuditQuery {
    async fn query(&self, params: AuditQueryParams) -> Result<AuditPageView, ApiError> {
        self.catch_up_index().await?;
        let labels = self.user_labels().await?;
        let mut query = params.into_query()?;
        // The filter names an owner label: the index stores `user:<id>`.
        if let Some(actor) = &query.actor
            && let Some((user, _)) = labels.iter().find(|(_, label)| *label == actor)
        {
            query.actor = Some(user.clone());
        }
        let page = self.index.query(&query).await?;
        let items = page
            .records
            .iter()
            .map(|record| {
                let label = actor_label(&record.actor).unwrap_or_else(|| {
                    labels
                        .get(&record.actor.to_string())
                        .cloned()
                        .unwrap_or_else(|| "unknown account".to_owned())
                });
                audit_row(record, label)
            })
            .collect();
        Ok(AuditPageView {
            items,
            next: page.next_after,
        })
    }
    async fn integrity(&self) -> Result<VerifyReport, ApiError> {
        if let Some(report) = self.last_report.read().await.clone() {
            return Ok(report);
        }
        let Some(paths) = self.verify.clone() else {
            return Err(ApiError::unavailable("journal verification"));
        };
        let report = tokio::task::spawn_blocking(move || {
            let key = audit::load_verifying_key(&paths.public_key)?;
            audit::verify(&paths.dir, &key, &paths.anchors)
        })
        .await
        .map_err(|_| ApiError::internal("journal verification"))??;
        // Only a clean report is kept: a tampered journal is checked again each time.
        if report.is_clean() {
            *self.last_report.write().await = Some(report.clone());
        }
        let _ = &self.journal;
        Ok(report)
    }
}

impl JournalStatus for Journal {
    fn is_writable(&self) -> bool {
        Journal::is_writable(self)
    }
}

/// Forwards each seal to the apps as an `alert` of kind `journal_sealed` (live anchor).
#[must_use]
pub fn spawn_seal_forwarder(journal: &Journal, hub: Arc<Hub>) -> JoinHandle<()> {
    let mut seals = journal.subscribe_seals();
    tokio::spawn(async move {
        loop {
            match seals.recv().await {
                Ok(seal) => hub.publish(AppEvent::Alert {
                    level: AlertKind::JournalSealed.level(),
                    kind: AlertKind::JournalSealed,
                    message: format!(
                        "Journal sealed: records {}..{}.",
                        seal.first_seq, seal.last_seq
                    ),
                    command: None,
                }),
                Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => {}
                Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
            }
        }
    })
}

/// What one record says, before the common fields are added: `action`, `target`, `result`,
/// `detail`. Each `RecordBody` variant has one fixed mapping function below; none copies free
/// text sent by a client.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuditFacts {
    /// `action` of the row.
    pub action: &'static str,
    /// `target` of the row (an id, or empty).
    pub target: String,
    /// `result` of the row.
    pub result: AuditResult,
    /// `detail` of the row, built from typed fields.
    pub detail: Option<String>,
}

/// The audit row of one journal record. `actor_label` is the actor as shown: the owner
/// label of a user (resolved by the caller), `robot:<id>`, or `system:<name>`.
#[must_use]
pub fn audit_row(record: &JournalRecord, actor_label: String) -> AuditEntry {
    let facts = match &record.body {
        RecordBody::LoginSucceeded { device } => login_succeeded(device.as_ref()),
        RecordBody::LoginFailed { device, network } => login_failed(device.as_ref(), network),
        RecordBody::TaskCreated {
            task,
            kind,
            item,
            to,
        } => task_created(task, *kind, item.as_ref(), to),
        RecordBody::TaskStateChanged {
            task,
            from,
            to,
            reason,
        } => task_state_changed(task, *from, *to, *reason),
        RecordBody::StockAdjusted {
            item,
            delta,
            count_after,
            reason,
        } => stock_adjusted(item, *delta, *count_after, *reason),
        RecordBody::ZoneChanged {
            zone,
            version,
            deleted,
        } => zone_changed(zone, *version, *deleted),
        RecordBody::ClinicChanged {
            clinic,
            version,
            change,
        } => clinic_changed(clinic, *version, *change),
        RecordBody::BrainCall {
            kind,
            latency_ms,
            ok,
        } => brain_call(*kind, *latency_ms, *ok),
        RecordBody::RobotCommandSent {
            robot,
            command,
            delivered,
            command_id,
        } => robot_command_sent(robot, *command, *delivered, *command_id),
        RecordBody::RobotCommandReverted {
            robot,
            command_id,
            inverse,
            reverted_by_command_id,
        } => robot_command_reverted(robot, *command_id, *inverse, *reverted_by_command_id),
        RecordBody::EnrolmentCodeIssued {
            code_id,
            role,
            expires_at,
        } => enrolment_code_issued(*code_id, *role, *expires_at),
        RecordBody::AccountEnrolled {
            code_id,
            account,
            role,
        } => account_enrolled(*code_id, account, *role),
        RecordBody::AccountDisabled { account } => account_disabled(account),
        RecordBody::SystemModeChanged { from, to, reason } => {
            system_mode_changed(*from, *to, reason.as_deref())
        }
        RecordBody::DeviceFreed { device } => device_freed(device),
        RecordBody::DeviceAssigned {
            device,
            bedside,
            bed_label,
        } => device_assigned(device, *bedside, bed_label.as_deref()),
        RecordBody::ClientBlocked {
            rule,
            target,
            reason,
            source,
            expires_at,
        } => client_blocked(rule, target, reason, *source, *expires_at),
        RecordBody::ClientUnblocked {
            rule,
            target,
            expired,
        } => client_unblocked(rule, target, *expired),
        RecordBody::EstopSent { robot, delivered } => estop_sent(robot, *delivered),
        RecordBody::ScheduleChanged { schedule, enabled } => schedule_changed(schedule, *enabled),
        RecordBody::ScheduleMissed {
            schedule,
            scheduled_for,
        } => schedule_missed(schedule, *scheduled_for),
        RecordBody::IncidentChanged { id, code, change } => incident_changed(*id, *code, *change),
        RecordBody::SecurityRejected { code, network } => security_rejected(code, network),
        RecordBody::SystemEvent { target, message } => system_event(target, message),
        RecordBody::Incident { trigger, recent } => incident_dump(*trigger, recent.len()),
        RecordBody::Seal(seal) => seal_written(seal),
    };
    audit_entry(record, actor_label, facts)
}

/// Adds the common fields (`id` = seq, `at` = ingested time, `category`) to the facts.
#[must_use]
pub fn audit_entry(record: &JournalRecord, actor_label: String, facts: AuditFacts) -> AuditEntry {
    AuditEntry {
        id: record.seq,
        at: record.ingested_at,
        actor: actor_label,
        action: facts.action.to_owned(),
        target: facts.target,
        result: facts.result,
        detail: facts.detail,
        category: snake(&record.category),
    }
}

/// The actor as an audit row shows it, for robots and system actors (users need their owner
/// label, which the caller looks up: an account shows as `"<pseudonym> #<tag>"`
/// (`domain::account_owner_label`, Task A7), never anything else).
#[must_use]
pub fn actor_label(actor: &Actor) -> Option<String> {
    match actor {
        Actor::User(_) => None,
        Actor::Device(id) => Some(format!("device:{id}")),
        Actor::Robot(id) => Some(format!("robot:{id}")),
        Actor::System(name) => Some(format!("system:{name}")),
    }
}

/// `login_succeeded`, target the device (empty without one), `ok`, no detail.
fn login_succeeded(device: Option<&DeviceId>) -> AuditFacts {
    AuditFacts {
        action: "login_succeeded",
        target: device.map(ToString::to_string).unwrap_or_default(),
        result: AuditResult::Ok,
        detail: None,
    }
}
/// `login_failed`, target the device (empty without one), `refused`, detail
/// "from <network label>".
fn login_failed(device: Option<&DeviceId>, network: &str) -> AuditFacts {
    AuditFacts {
        action: "login_failed",
        target: device.map(ToString::to_string).unwrap_or_default(),
        result: AuditResult::Refused,
        detail: Some(format!("from {network}")),
    }
}
/// `task_created`, target the task, `ok`, detail "<kind> of <item> to <place>".
fn task_created(task: &TaskId, kind: TaskKind, item: Option<&ItemId>, to: &PlaceId) -> AuditFacts {
    let item = item.map_or_else(|| "nothing".to_owned(), ToString::to_string);
    AuditFacts {
        action: "task_created",
        target: task.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!("{} of {item} to {to}", snake(&kind))),
    }
}
/// `task_<to state>` (for example `task_cancelled`), target the task; `failed` when `to` is
/// `failed`, else `ok`; detail "<from> -> <to>" plus the failure code.
fn task_state_changed(
    task: &TaskId,
    from: TaskState,
    to: TaskState,
    reason: Option<FailureReason>,
) -> AuditFacts {
    let action = match to {
        TaskState::Requested => "task_requested",
        TaskState::Assigned => "task_assigned",
        TaskState::EnRoute => "task_en_route",
        TaskState::Delivered => "task_delivered",
        TaskState::Failed => "task_failed",
        TaskState::Resumed => "task_resumed",
        TaskState::Cancelled => "task_cancelled",
    };
    let result = if to == TaskState::Failed {
        AuditResult::Failed
    } else {
        AuditResult::Ok
    };
    let detail = match reason {
        Some(reason) => format!("{from} -> {to} ({})", snake(&reason)),
        None => format!("{from} -> {to}"),
    };
    AuditFacts {
        action,
        target: task.to_string(),
        result,
        detail: Some(detail),
    }
}
/// `stock_adjusted`, target the item, `ok`, detail "<+/-delta> (<reason>), now <count>".
fn stock_adjusted(
    item: &ItemId,
    delta: i32,
    count_after: u32,
    reason: StockAdjustReason,
) -> AuditFacts {
    AuditFacts {
        action: "stock_adjusted",
        target: item.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!("{delta:+} ({}), now {count_after}", snake(&reason))),
    }
}
/// `zone_saved` or `zone_deleted`, target the zone, `ok`, detail "version <n>".
fn zone_changed(zone: &ZoneId, version: u32, deleted: bool) -> AuditFacts {
    let action = if deleted {
        "zone_deleted"
    } else {
        "zone_saved"
    };
    AuditFacts {
        action,
        target: zone.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!("version {version}")),
    }
}
/// `clinic_<change>` (`clinic_created`, `clinic_updated`, `clinic_activated`,
/// `clinic_deleted`), target the clinic id, `ok`, detail "version <n>".
fn clinic_changed(clinic: &ClinicId, version: u64, change: ClinicChange) -> AuditFacts {
    let action = match change {
        ClinicChange::Created => "clinic_created",
        ClinicChange::Updated => "clinic_updated",
        ClinicChange::Activated => "clinic_activated",
        ClinicChange::Deleted => "clinic_deleted",
    };
    AuditFacts {
        action,
        target: clinic.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!("version {version}")),
    }
}
/// `brain_<kind>` (`brain_translate`, `brain_simplify`, `brain_summarise`, `brain_report`),
/// no target, `ok` or `failed`, detail "<latency> ms". Never any text (Task A6 privacy rule).
fn brain_call(kind: BrainCallKind, latency_ms: u64, ok: bool) -> AuditFacts {
    let action = match kind {
        BrainCallKind::Translate => "brain_translate",
        BrainCallKind::Simplify => "brain_simplify",
        BrainCallKind::Summarise => "brain_summarise",
        BrainCallKind::Report => "brain_report",
    };
    let result = if ok {
        AuditResult::Ok
    } else {
        AuditResult::Failed
    };
    AuditFacts {
        action,
        target: String::new(),
        result,
        detail: Some(format!("{latency_ms} ms")),
    }
}
/// `robot_<command>`, target the robot, `ok` or `failed` (not delivered), detail
/// `"command <command_id>"` (what the admin names to revert it, Task A7).
fn robot_command_sent(
    robot: &RobotId,
    command: CommandName,
    delivered: bool,
    command_id: Uuid,
) -> AuditFacts {
    let action = match command {
        CommandName::Pause => "robot_pause",
        CommandName::Resume => "robot_resume",
        CommandName::Dock => "robot_dock",
        CommandName::Estop => "robot_estop",
        CommandName::Shutdown => "robot_shutdown",
    };
    let result = if delivered {
        AuditResult::Ok
    } else {
        AuditResult::Failed
    };
    AuditFacts {
        action,
        target: robot.to_string(),
        result,
        detail: Some(format!("command {command_id}")),
    }
}
/// `robot_command_reverted`, target the robot, `ok`, detail
/// `"<command_id> undone by <inverse> <reverted_by_command_id>"` (Task A7).
fn robot_command_reverted(
    robot: &RobotId,
    command_id: Uuid,
    inverse: CommandName,
    reverted_by_command_id: Uuid,
) -> AuditFacts {
    AuditFacts {
        action: "robot_command_reverted",
        target: robot.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!(
            "{command_id} undone by {} {reverted_by_command_id}",
            snake(&inverse)
        )),
    }
}
/// `enrolment_code_issued`, target the code id, `ok`, detail "<role>, expires <time>". Never
/// the code (Task A7).
fn enrolment_code_issued(code_id: Uuid, role: Role, expires_at: DateTime<Utc>) -> AuditFacts {
    AuditFacts {
        action: "enrolment_code_issued",
        target: code_id.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!("{role}, expires {}", expires_at.to_rfc3339())),
    }
}
/// `account_enrolled`, target the account tag, `ok`, detail `"<role>, code <code_id>"`
/// (Task A7).
fn account_enrolled(code_id: Uuid, account: &AccountTag, role: Role) -> AuditFacts {
    AuditFacts {
        action: "account_enrolled",
        target: account.to_string(),
        result: AuditResult::Ok,
        detail: Some(format!("{role}, code {code_id}")),
    }
}
/// `account_disabled`, target the account tag, `ok`, no detail (Task A7).
fn account_disabled(account: &AccountTag) -> AuditFacts {
    AuditFacts {
        action: "account_disabled",
        target: account.to_string(),
        result: AuditResult::Ok,
        detail: None,
    }
}
/// `system_mode_changed`, target `system`, `ok`, detail "normal -> emergency (reason)".
fn system_mode_changed(from: SystemMode, to: SystemMode, reason: Option<&str>) -> AuditFacts {
    let detail = match reason {
        Some(reason) => format!("{} -> {} ({reason})", snake(&from), snake(&to)),
        None => format!("{} -> {}", snake(&from), snake(&to)),
    };
    AuditFacts {
        action: "system_mode_changed",
        target: "system".to_owned(),
        result: AuditResult::Ok,
        detail: Some(detail),
    }
}
/// `device_freed`, target the device, `ok`, no detail (no label).
fn device_freed(device: &DeviceId) -> AuditFacts {
    AuditFacts {
        action: "device_freed",
        target: device.to_string(),
        result: AuditResult::Ok,
        detail: None,
    }
}
/// `device_assigned`, target the device, `ok`, detail "staff" or "bedside, <bed label>".
fn device_assigned(device: &DeviceId, bedside: bool, bed_label: Option<&str>) -> AuditFacts {
    let detail = if bedside {
        format!("bedside, {}", bed_label.unwrap_or("no label"))
    } else {
        "staff".to_owned()
    };
    AuditFacts {
        action: "device_assigned",
        target: device.to_string(),
        result: AuditResult::Ok,
        detail: Some(detail),
    }
}
/// `client_blocked`, target the address or block, `ok`, detail "<source> <rule>: <reason>
/// (until <time>)".
fn client_blocked(
    rule: &str,
    target: &str,
    reason: &str,
    source: BlockSource,
    expires_at: Option<DateTime<Utc>>,
) -> AuditFacts {
    let detail = match expires_at {
        Some(until) => format!(
            "{} {rule}: {reason} (until {})",
            snake(&source),
            until.to_rfc3339()
        ),
        None => format!("{} {rule}: {reason}", snake(&source)),
    };
    AuditFacts {
        action: "client_blocked",
        target: target.to_owned(),
        result: AuditResult::Ok,
        detail: Some(detail),
    }
}
/// `client_unblocked`, target the address or block, `ok`, detail "<rule> expired" or
/// "<rule> removed".
fn client_unblocked(rule: &str, target: &str, expired: bool) -> AuditFacts {
    let detail = if expired {
        format!("{rule} expired")
    } else {
        format!("{rule} removed")
    };
    AuditFacts {
        action: "client_unblocked",
        target: target.to_owned(),
        result: AuditResult::Ok,
        detail: Some(detail),
    }
}
/// `estop`, target the robot, `ok` or `failed` with detail "not delivered: robot offline".
fn estop_sent(robot: &RobotId, delivered: bool) -> AuditFacts {
    if delivered {
        AuditFacts {
            action: "estop",
            target: robot.to_string(),
            result: AuditResult::Ok,
            detail: None,
        }
    } else {
        AuditFacts {
            action: "estop",
            target: robot.to_string(),
            result: AuditResult::Failed,
            detail: Some("not delivered: robot offline".to_owned()),
        }
    }
}
/// `schedule_changed`, target the schedule, `ok`, detail "enabled" or "disabled".
fn schedule_changed(schedule: &ScheduleId, enabled: bool) -> AuditFacts {
    AuditFacts {
        action: "schedule_changed",
        target: schedule.to_string(),
        result: AuditResult::Ok,
        detail: Some(if enabled { "enabled" } else { "disabled" }.to_owned()),
    }
}
/// `schedule_missed`, target the schedule, `failed`, detail "due <time>".
fn schedule_missed(schedule: &ScheduleId, scheduled_for: DateTime<Utc>) -> AuditFacts {
    AuditFacts {
        action: "schedule_missed",
        target: schedule.to_string(),
        result: AuditResult::Failed,
        detail: Some(format!("due {}", scheduled_for.to_rfc3339())),
    }
}
/// `incident_<change>`, target the incident id, `ok`, detail the incident code.
fn incident_changed(id: IncidentId, code: IncidentCode, change: IncidentChange) -> AuditFacts {
    let action = match change {
        IncidentChange::Raised => "incident_raised",
        IncidentChange::Acknowledged => "incident_acknowledged",
        IncidentChange::Closed => "incident_closed",
    };
    AuditFacts {
        action,
        target: id.0.to_string(),
        result: AuditResult::Ok,
        detail: Some(incident_code_name(code)),
    }
}
/// `security_rejected`, no target, `refused`, detail "<code> from <network label>" (the code
/// comes from a fixed list).
fn security_rejected(code: &str, network: &str) -> AuditFacts {
    AuditFacts {
        action: "security_rejected",
        target: String::new(),
        result: AuditResult::Refused,
        detail: Some(format!("{code} from {network}")),
    }
}
/// `system_event`, target the tracing target, `failed`, detail none: the message is redacted
/// server text, still not shown (it is in the journal for the verifier).
fn system_event(target: &str, message: &str) -> AuditFacts {
    let _ = message;
    AuditFacts {
        action: "system_event",
        target: target.to_owned(),
        result: AuditResult::Failed,
        detail: None,
    }
}
/// `incident_dump`, no target, `ok`, detail "<trigger>, <n> events".
fn incident_dump(trigger: IncidentTrigger, events: usize) -> AuditFacts {
    AuditFacts {
        action: "incident_dump",
        target: String::new(),
        result: AuditResult::Ok,
        detail: Some(format!("{}, {events} events", snake(&trigger))),
    }
}
/// `journal_sealed`, no target, `ok`, detail "records <first>..<last>".
fn seal_written(seal: &Seal) -> AuditFacts {
    AuditFacts {
        action: "journal_sealed",
        target: String::new(),
        result: AuditResult::Ok,
        detail: Some(format!("records {}..{}", seal.first_seq, seal.last_seq)),
    }
}

/// The `snake_case` serde name of a unit enum value (`"unknown"` if it has none).
fn snake<T: serde::Serialize>(value: &T) -> String {
    match serde_json::to_value(value) {
        Ok(serde_json::Value::String(name)) => name,
        _ => "unknown".to_owned(),
    }
}

/// The `code` name of an incident code (`robot_fault`, `robot_offline`, ...).
fn incident_code_name(code: IncidentCode) -> String {
    serde_json::to_value(code)
        .ok()
        .and_then(|value| {
            value
                .get("code")
                .and_then(serde_json::Value::as_str)
                .map(str::to_owned)
        })
        .unwrap_or_else(|| "unknown".to_owned())
}
