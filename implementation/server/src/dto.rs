//! Request and response bodies of contract C3 that are not domain types.
//!
//! Field names follow architecture.md C3 as the admin console reads them
//! (`implementation/admin/src/lib/adapt.ts`). The views shared with the `WS /ws` events
//! (`RobotView`, `TaskView`, `ZoneView`, `ScheduleView`) live in `realtime::views` and the
//! map view in `locations::view`; they are re-exported here. Every type derives `ToSchema` (or `IntoParams` for
//! query strings) so the OpenAPI document is generated from these definitions.
//!
//! Request bodies use `#[serde(deny_unknown_fields)]`: an extra field (for example free text
//! added to a tablet event) is rejected, never silently dropped.

use audit::AuditQuery;
use chrono::{DateTime, Utc};
use domain::{
    AccountKey, AccountTag, ClinicId, CommandName, DeviceId, EnrolmentCode, ItemId, OwnerLabel,
    Page, PlaceId, RobotId, Role, StockAdjustReason, TaskDraft, TaskFilter, TaskKind, TaskState,
    ZoneId, ZoneKind,
};
use locations::ScanReport;
use locations::positioning::{MotionDelta, Observation};
pub use locations::{ClinicPlan, MapView};
use realtime::AppErrorCode;
pub use realtime::{RobotMood, RobotView, ScheduleView, TaskHistoryEntry, TaskView, ZoneView};
use serde::{Deserialize, Serialize};
use utoipa::{IntoParams, ToSchema};
use uuid::Uuid;

use crate::error::ApiError;

/// How the server was started (`GET /health` `mode`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ServerMode {
    /// Real robots, the database, the journal.
    Live,
    /// `--demo`: the live server plus simulated robots driving the active plan; every
    /// simulated robot and task says "SIMULATED" (Task 5b).
    Demo,
    /// `--mock`: canned, clearly invented answers; no database.
    Mock,
}

/// `GET /health`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct HealthView {
    /// `ok`, or `degraded` when the journal cannot write.
    pub status: String,
    /// Whether actions can be recorded.
    pub journal_writable: bool,
    /// Server version.
    pub version: String,
    /// `live`, `demo` or `mock`.
    pub mode: ServerMode,
    /// The brain process (Task A6): `up`, `degraded` (fallback models only) or `down` (not
    /// running, not configured, or built without Python). Last probe, refreshed every 5 s.
    pub brain: domain::BrainStatus,
}

/// One stored clinic plan in `GET /clinics`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct ClinicSummary {
    /// Id.
    pub id: ClinicId,
    /// The plan's name.
    pub name: String,
    /// Version (the `ETag` of `GET /clinics/{id}`; send it back in `If-Match`).
    pub version: u64,
    /// Whether `GET /map` serves this plan.
    pub active: bool,
    /// Last change.
    pub updated_at: DateTime<Utc>,
}

/// A plan with its identity, as the clinic service returns it; the handler sends `plan` as
/// the body and `version` as the `ETag`.
#[derive(Debug, Clone, PartialEq)]
pub struct VersionedPlan {
    /// Id.
    pub id: ClinicId,
    /// Version.
    pub version: u64,
    /// Whether it is the active plan.
    pub active: bool,
    /// The document.
    pub plan: ClinicPlan,
}

/// A plan's modifications with the version they were saved at.
#[derive(Debug, Clone, PartialEq)]
pub struct VersionedOverlay {
    /// Version of the clinic (the `ETag`).
    pub version: u64,
    /// The modifications.
    pub overlay: locations::PlanOverlay,
}

/// `GET /tasks/{id}/route`: the server's estimate of the remaining path (the real robot plans
/// its own way).
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct RouteView {
    /// Floor level.
    pub floor: i32,
    /// Points `[x, y]`, metres, from the robot (or the start place) to the goal.
    #[schema(value_type = Vec<Vec<f64>>)]
    pub points: Vec<[f64; 2]>,
    /// Length, metres.
    pub length_m: f64,
    /// Always `true`: this is an estimate.
    pub estimate: bool,
}

/// `GET /stats/heat?floor=`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct HeatQuery {
    /// Floor level.
    pub floor: i32,
}

/// Where robots spent their time on one floor since the server started: one count per
/// square metre, robots only (never tablets), memory only.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct HeatView {
    /// Floor level.
    pub floor: i32,
    /// Cell side, metres (always 1).
    pub cell_m: f64,
    /// North-west corner of cell (0, 0): the floor outline's bounding box corner.
    #[schema(value_type = Vec<f64>)]
    pub origin: [f64; 2],
    /// Cells along x.
    pub columns: u32,
    /// Cells along y.
    pub rows: u32,
    /// `columns * rows` counts, row-major (row 0 is the north edge): robot samples (one per
    /// robot per second) whose position fell in the cell.
    pub counts: Vec<u32>,
}

/// `POST /auth/login` (Task A7): the client never sends the user name or the password, only
/// the key it derived from them (`docs/accounts.md`). `Debug` prints the key as
/// `AccountKey(***)`.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LoginRequest {
    /// `PBKDF2-HMAC-SHA256(NFC(password), "clinic:" + clinic_id + ":" +
    /// lowercase(NFC(username)), 600000, 32 bytes)` as 64 lowercase hex characters (`GET /auth/derivation` gives the
    /// clinic id and the parameters). Password-equivalent: never stored, logged or journaled;
    /// the server keeps only its HMAC with the pepper.
    pub account_key: AccountKey,
    /// The tablet's device id. A browser has none: the token is then bound to no device.
    #[serde(default)]
    pub device_id: Option<DeviceId>,
}

/// The A3 login body `{username, password}`, accepted **only by `--mock`** as a compatibility
/// path until frontend task F9 makes the console derive the key: the mock derives the key
/// itself and continues as for [`LoginRequest`]. The live server answers it 422
/// `key_derivation_required` ([`ApiError::key_derivation_required`]) and never reads the
/// password. Not in the OpenAPI document. No `Debug`: the password must never be printed.
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MockCompatLogin {
    /// The user name as typed.
    pub username: String,
    /// The password as typed.
    pub password: String,
    /// The tablet's device id, if any.
    #[serde(default)]
    pub device_id: Option<DeviceId>,
}

/// What `POST /auth/login` reads: a [`LoginRequest`], or (only to refuse it on the live
/// server, or to serve it in `--mock`) the A3 `{username, password}` body. A body with a
/// `username` or `password` key is a [`MockCompatLogin`]; anything else must be a
/// [`LoginRequest`]. Error messages never repeat a value.
pub enum LoginBody {
    /// The Task A7 body.
    Key(LoginRequest),
    /// The A3 body (mock compatibility until F9).
    Credentials(MockCompatLogin),
}

impl<'de> Deserialize<'de> for LoginBody {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let object = serde_json::Map::<String, serde_json::Value>::deserialize(deserializer)?;
        let legacy = object.contains_key("username") || object.contains_key("password");
        let value = serde_json::Value::Object(object);
        if legacy {
            serde_json::from_value(value)
                .map(LoginBody::Credentials)
                .map_err(|_| {
                    serde::de::Error::custom(
                        "a user name and password body has exactly `username`, `password` and an optional `device_id`",
                    )
                })
        } else {
            serde_json::from_value(value)
                .map(LoginBody::Key)
                .map_err(serde::de::Error::custom)
        }
    }
}

/// `GET /auth/derivation`: how a client derives its account key (public, Task A7). The same
/// for every client of this server; see `docs/accounts.md` for the test vector.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct KeyDerivationParams {
    /// Always `PBKDF2-HMAC-SHA256`.
    pub algorithm: String,
    /// Always 600000.
    pub iterations: u32,
    /// Key length in bytes: 32 (sent as 64 hex characters).
    pub key_bytes: u32,
    /// The clinic id in the salt (`ACCOUNT_CLINIC_ID`; not a plan id: it never changes).
    pub clinic_id: ClinicId,
    /// The salt template: `clinic:<clinic_id>:<lowercase(NFC(username))>`.
    pub salt: String,
    /// The Unicode normalisation applied to the user name and the password before anything
    /// else: always `NFC` (ruling R25).
    pub normalization: String,
}

/// `POST /auth/enrol` (public, Task A7): a person enrols with the one-time code an admin
/// gave them, the key their device derived from the user name and password they chose, and
/// a pseudonym. 201 [`EnrolledView`]; then they log in with the same key.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EnrolRequest {
    /// The code as typed (`XXXX-XXXX-XXXX`; case, dashes and spaces do not matter).
    #[schema(value_type = String, example = "K7QX-M2PD-9F3A")]
    pub enrolment_code: EnrolmentCode,
    /// The derived key, as in [`LoginRequest`].
    pub account_key: AccountKey,
    /// The pseudonym others will see ("Nurse 7"), never a real name; 1 to 32 characters.
    pub display_label: OwnerLabel,
}

/// An account as anyone may see it: pseudonym and tag (201 of `POST /auth/enrol`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct EnrolledView {
    /// The first 6 hex digits of the account id.
    pub account_tag: AccountTag,
    /// Role, from the code.
    pub role: Role,
    /// `"<pseudonym> #<tag>"`, as tasks and the audit will show this account.
    pub operator: OwnerLabel,
}

/// `POST /admin/enrolment-codes` (admin, Task A7).
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EnrolmentCodeRequest {
    /// Role of the account the code creates (not `robot`).
    pub role: Role,
    /// A suggested pseudonym, shown with the code (never a real name).
    #[serde(default)]
    pub label: Option<OwnerLabel>,
}

/// 201 of `POST /admin/enrolment-codes`: shown once to the admin, who hands it to the person.
/// The server keeps only its HMAC; it is journaled by `code_id`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct EnrolmentCodeView {
    /// The code, `XXXX-XXXX-XXXX`. Single use.
    pub code: String,
    /// The code's id (in the journal).
    pub code_id: Uuid,
    /// Role it grants.
    pub role: Role,
    /// The suggested pseudonym, if any.
    pub label: Option<OwnerLabel>,
    /// After this (24 h) the code is refused.
    pub expires_at: DateTime<Utc>,
}

/// One account in `GET /admin/accounts` (admin, Task A7): what the server knows of it, which
/// is nothing that names a person.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct AccountView {
    /// The first 6 hex digits of the account id (what `DELETE /admin/accounts/{tag}` takes).
    pub account_tag: AccountTag,
    /// The pseudonym.
    pub display_label: OwnerLabel,
    /// Role.
    pub role: Role,
    /// Enrolment time.
    pub created_at: DateTime<Utc>,
    /// Whether it is disabled.
    pub disabled: bool,
}

/// Login result.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct LoginResponse {
    /// Bearer token (also the `token` of the `/ws` auth message).
    pub token: String,
    /// Role.
    pub role: Role,
    /// The user's pseudonymous display label (never a real name).
    pub operator: OwnerLabel,
    /// Expiry.
    pub expires_at: DateTime<Utc>,
}

/// `GET /me`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct MeView {
    /// `user:<id>` or `robot:<id>`.
    pub subject: String,
    /// Role.
    pub role: Role,
    /// Device.
    pub device_id: Option<DeviceId>,
    /// Owner label.
    pub owner_label: Option<OwnerLabel>,
    /// Network label.
    pub network: String,
    /// Area of the network.
    pub area: Option<PlaceId>,
}

/// `POST /tasks`.
#[derive(Debug, Clone, PartialEq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct NewTask {
    /// Kind.
    pub kind: TaskKind,
    /// Item (required for `fetch`).
    pub item: Option<ItemId>,
    /// Origin place.
    pub from_place: Option<PlaceId>,
    /// Destination place (required except for `follow`).
    #[serde(default)]
    pub to_place: Option<PlaceId>,
    /// Deadline.
    pub deadline: Option<DateTime<Utc>>,
    /// Admin only (Step C1, mock path): give the task to this robot instead of dispatching it.
    #[serde(default)]
    pub robot_id: Option<RobotId>,
    /// `follow`: the staff tablet to follow.
    #[serde(default)]
    pub target_device: Option<DeviceId>,
}

impl NewTask {
    /// The domain draft.
    ///
    /// # Errors
    /// 422 when `to_place` is missing (a `follow` task resolves its destination before).
    pub fn into_draft(self) -> Result<TaskDraft, ApiError> {
        let to = self
            .to_place
            .ok_or_else(|| ApiError::invalid_input("to_place", "is required"))?;
        Ok(TaskDraft {
            kind: self.kind,
            item: self.item,
            from: self.from_place,
            to,
            deadline: self.deadline,
        })
    }
}

/// `GET /tasks` query.
#[derive(Debug, Clone, PartialEq, Eq, Default, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct TaskListQuery {
    /// Only this state.
    pub state: Option<TaskState>,
    /// Only this robot's tasks.
    pub robot: Option<RobotId>,
    /// Only unfinished tasks.
    pub active: Option<bool>,
    /// Page size, 1 to 500 (default 50).
    pub limit: Option<u32>,
    /// Offset.
    pub offset: Option<u32>,
}

impl TaskListQuery {
    /// Filter and validated page.
    ///
    /// # Errors
    /// 422 when `limit` is out of range.
    pub fn into_parts(self) -> Result<(TaskFilter, Page), ApiError> {
        let page = Page::new(
            self.limit.unwrap_or(Page::DEFAULT_LIMIT),
            self.offset.unwrap_or(0),
        )?;
        let filter = TaskFilter {
            state: self.state,
            robot: self.robot,
            requested_by: None,
            since: None,
            active_only: self.active.unwrap_or(false),
        };
        Ok((filter, page))
    }
}

/// A page of tasks: `{items, next}` (the admin console reads `items`).
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct TaskPage {
    /// Tasks, newest first.
    pub items: Vec<TaskView>,
    /// `offset` of the next page, if any.
    pub next: Option<u32>,
}

/// `POST /inventory/{item}/adjust`. The admin console sends only `delta`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AdjustRequest {
    /// Change, a non-zero integer (negative removes).
    pub delta: i32,
    /// Why (default `admin_correction`).
    #[serde(default)]
    pub reason: StockAdjustReason,
}

impl AdjustRequest {
    /// The checked change.
    ///
    /// # Errors
    /// 422 `invalid_field` naming `delta` when it is zero.
    pub fn checked_delta(&self) -> Result<i32, ApiError> {
        if self.delta == 0 {
            return Err(ApiError::invalid_input(
                "delta",
                "must not be zero (positive adds, negative removes)",
            ));
        }
        Ok(self.delta)
    }
}

/// `PUT /me/location`: a room id, from a hand pick or a QR payload.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LocationUpdate {
    /// Place id.
    pub place: PlaceId,
}

/// `POST /me/scans`. The device comes from the caller's identity, never from the body.
#[derive(Debug, Clone, PartialEq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ScanBody {
    /// When scanned.
    pub at: DateTime<Utc>,
    /// Observations (at most 64).
    pub observations: Vec<Observation>,
    /// Motion since the previous scan.
    pub motion: Option<MotionDelta>,
    /// Air pressure.
    pub pressure_hpa: Option<f64>,
}

impl ScanBody {
    /// The scan report for `device`.
    #[must_use]
    pub fn into_report(self, device: DeviceId) -> ScanReport {
        ScanReport {
            device,
            at: self.at,
            observations: self.observations,
            motion: self.motion,
            pressure_hpa: self.pressure_hpa,
        }
    }
}

/// `PUT /zones/{id}`, as the admin console sends it. `id` must equal the path id (else 422).
#[derive(Debug, Clone, PartialEq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ZoneInput {
    /// Id; must equal the path id.
    pub id: ZoneId,
    /// Display name (a label for the zone, never a person's name).
    pub name: String,
    /// Floor.
    pub floor: i32,
    /// Kind.
    pub kind: ZoneKind,
    /// Vertices in metres, `[x, y]`, y grows south.
    #[schema(value_type = Vec<Vec<f64>>)]
    pub polygon: Vec<[f64; 2]>,
}

/// `POST /robots/{id}/teleport` (admin, simulated robots only): where to put the robot.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct TeleportRequest {
    /// Metres east.
    pub x: f64,
    /// Metres south.
    pub y: f64,
    /// Floor level, as a string (`"0"`) or a number (`0`).
    #[serde(deserialize_with = "floor_level")]
    #[schema(value_type = String, example = "0")]
    pub floor: i32,
}

/// A floor level written as a number or as a string holding one.
fn floor_level<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<i32, D::Error> {
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Level {
        Number(i32),
        Text(String),
    }
    match Level::deserialize(deserializer)? {
        Level::Number(level) => Ok(level),
        Level::Text(text) => text
            .trim()
            .parse()
            .map_err(|_| serde::de::Error::custom("floor must be a floor level such as \"0\"")),
    }
}

/// `GET /fleet/home` and `PUT /fleet/home`: where the robots go in an emergency, on `dock`
/// and to recharge. All `null` when no home place is set.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct FleetHomeView {
    /// The home place id.
    pub place_id: Option<PlaceId>,
    /// Its display name.
    pub label: Option<String>,
    /// Its floor level, as a string.
    pub floor: Option<String>,
}

/// `PUT /fleet/home` (admin): the home place, or `null` to clear it.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetFleetHomeRequest {
    /// A place of the active clinic plan, or `null`.
    pub place_id: Option<PlaceId>,
}

/// `POST /robots/{id}/command`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CommandRequest {
    /// Command.
    pub name: CommandName,
}

/// Command result (200). Every command gets a `command_id`; a command from a non-admin raises
/// the admin alert `staff_command` with it, and the admin may revert it
/// (`POST /robots/{id}/commands/{command_id}/revert`, Task A7). A refusal is not a receipt: it is 409 with a readable
/// `error.message` (for estop to an offline robot: "Robot X is offline: the stop was not
/// delivered. Use the physical button.").
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct CommandReceipt {
    /// `true`: the command reached the robot's connection.
    pub accepted: bool,
    /// Optional note safe to show (for example "already paused"); `null` otherwise.
    pub reason: Option<String>,
    /// When sent.
    pub sent_at: DateTime<Utc>,
    /// Command (extra field).
    pub command: CommandName,
    /// The command's id (Task A7): what a revert names; in the journal record.
    pub command_id: Uuid,
}

/// 202 of `POST /robots/{id}/commands/{command_id}/revert` (admin, Task A7): the inverse
/// command was sent (`pause` -> `resume`, `resume` -> `pause`, `dock` -> `resume`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
pub struct RevertReceipt {
    /// The id of the inverse command.
    pub reverted_by_command_id: Uuid,
}

/// `PUT /schedules/{id}`: a partial body. Only the given fields change; the schedule must
/// exist (404 otherwise).
#[derive(Debug, Clone, PartialEq, Eq, Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SchedulePatch {
    /// Enabled.
    #[serde(default)]
    pub enabled: Option<bool>,
    /// Daily time `HH:MM` in the schedule's time zone (kept internally as cron
    /// `"MM HH * * *"`); 422 when not a valid time.
    #[serde(default)]
    pub time: Option<String>,
    /// Robot the round is given to.
    #[serde(default)]
    pub robot_id: Option<RobotId>,
}

/// `GET /audit` query.
#[derive(Debug, Clone, PartialEq, Eq, Default, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct AuditQueryParams {
    /// From (inclusive).
    pub from: Option<DateTime<Utc>>,
    /// To (exclusive).
    pub to: Option<DateTime<Utc>>,
    /// The actor exactly as audit rows show it (an owner label, `robot:<id>` or
    /// `system:<name>`): the admin console filters by a value taken from a row. Task 9
    /// resolves an owner label to the matching user(s); a user id is not accepted here.
    pub actor: Option<String>,
    /// Category (`audit`, `security`, `robot`, `system`, `incident`, `seal`).
    pub category: Option<String>,
    /// Page size, 1 to 500 (default 100).
    pub limit: Option<u32>,
    /// Continue after this sequence number.
    pub after: Option<u64>,
}

impl AuditQueryParams {
    /// The validated index query.
    ///
    /// # Errors
    /// 422 for an unknown category or a limit out of range.
    pub fn into_query(self) -> Result<AuditQuery, ApiError> {
        let category = match self.category.as_deref() {
            None => None,
            Some(text) => Some(
                serde_json::from_value::<audit::Category>(serde_json::Value::String(
                    text.to_owned(),
                ))
                .map_err(|_| {
                    ApiError::invalid_input(
                        "category",
                        "must be one of audit, security, robot, system, incident, seal",
                    )
                })?,
            ),
        };
        let query = AuditQuery {
            from: self.from,
            to: self.to,
            actor: self.actor,
            category,
            limit: self.limit.unwrap_or(100),
            after_seq: self.after,
        };
        query.validate()?;
        Ok(query)
    }
}

/// The result of an audited action, as the admin console reads it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AuditResult {
    /// Done.
    Ok,
    /// Refused (permission, validation, security).
    Refused,
    /// Attempted but failed (for example an estop not delivered).
    Failed,
}

/// One audit row, derived from a journal record by a fixed mapping per `RecordBody` variant
/// (`services::audit::audit_row`). `detail` is built from typed fields only, never from
/// free text sent by a client.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct AuditEntry {
    /// The record's sequence number.
    pub id: u64,
    /// When written.
    pub at: DateTime<Utc>,
    /// Who: an owner label, `robot:<id>` or `system:<name>`. Never a user id or name.
    pub actor: String,
    /// What, in `snake_case` (`task_created`, `estop_sent`, …).
    pub action: String,
    /// On what (a task, zone, robot, item, schedule id), or empty.
    pub target: String,
    /// Result.
    pub result: AuditResult,
    /// Short detail built from typed fields, or `null`.
    pub detail: Option<String>,
    /// Journal category (extra field).
    pub category: String,
}

/// A page of audit rows: `{items, next}`.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct AuditPageView {
    /// Rows, ascending.
    pub items: Vec<AuditEntry>,
    /// `after` for the next page, if any.
    pub next: Option<u64>,
}

/// `GET /incidents` query.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct IncidentListQuery {
    /// Only open incidents (default `true`).
    pub open: Option<bool>,
}

/// `POST /devices/me/events`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct DeviceEventRequest {
    /// Error code from the closed catalogue.
    pub code: AppErrorCode,
}

// ----- Task A8: emergency mode, tablets, monitoring, service statistics -----

pub use domain::{SystemMode, SystemModeState};
pub use realtime::{TabletKind, TabletView};
pub use security::monitor::{
    BlockView, ClientView, NewBlockRequest, RejectedBy, TrafficPoint, TrafficView,
};

/// `PUT /system/mode` (admin). An unknown `mode` is 422 `invalid_field`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetModeRequest {
    /// `normal` or `emergency`.
    pub mode: SystemMode,
    /// Why, at most 200 characters (422 `invalid_field` above); `null` or absent for none.
    #[serde(default)]
    pub reason: Option<String>,
}

/// `POST /devices/{id}/assign` (admin): hand a free, connected tablet to a staff member
/// (pseudonym) or a bed.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AssignTabletRequest {
    /// `staff` or `bedside`.
    pub kind: TabletKind,
    /// A staff pseudonym ("Dr. C") or a bed ("Bed 12"): 1 to 40 characters, not digits only.
    /// Never a patient's name.
    pub label: String,
    /// Staff only ("Neurology"); must be `null` for a bedside tablet.
    #[serde(default)]
    pub speciality: Option<String>,
    /// The bed's patient room (required for bedside); for staff, `null` keeps the tablet
    /// where it is.
    #[serde(default)]
    pub place: Option<PlaceId>,
}

/// `GET /monitor/summary` (admin). Counts and states only, no personal data.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct MonitorSummaryView {
    /// When the server started.
    pub started_at: DateTime<Utc>,
    /// Seconds since.
    pub uptime_s: u64,
    /// Server version.
    pub version: String,
    /// Robots with a session now.
    pub robots_connected: u32,
    /// Registered robots.
    pub robots_total: u32,
    /// Open `/ws` connections.
    pub app_clients: u32,
    /// Whether the journal can write; `null` when not checked (mock mode).
    pub journal_ok: Option<bool>,
    /// Whether the database answers; `null` when not checked (mock mode).
    pub database_ok: Option<bool>,
    /// Requests per second over the last 10 s.
    pub requests_per_s: f64,
    /// Refused requests per second over the last 10 s.
    pub rejected_per_s: f64,
    /// Answer time p95 of the last 10 s, ms; `null` without a request.
    pub p95_ms: Option<u64>,
    /// Active block rules.
    pub blocked_clients: u64,
}

/// `GET /monitor/traffic?window_s=` (default and largest 300).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct TrafficQuery {
    /// Seconds of history, 1 to 300 (default 300).
    pub window_s: Option<u32>,
}

/// `GET /monitor/clients?limit=` (default 20, at most 100).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct ClientsQuery {
    /// How many addresses, 1 to 100 (default 20).
    pub limit: Option<u32>,
}

/// `GET /stats/service?hours=` (default 24, 1 to 720).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct ServiceStatsQuery {
    /// Hours back from now, 1 to 720 (default 24).
    pub hours: Option<u32>,
}

/// Requests per item in `GET /stats/service`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct ItemCount {
    /// The item's label as the stock lists it.
    pub label: String,
    /// Requests.
    pub count: u32,
}

/// Requests per destination place in `GET /stats/service`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct PlaceCount {
    /// Place id, or `other` for the places folded for k-anonymity.
    pub place: String,
    /// Requests.
    pub count: u32,
}

/// `GET /stats/service` (admin): counts only, never a person (no patient, no staff name, no
/// room-to-person link).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct ServiceStatsView {
    /// The window, hours.
    pub hours: u32,
    /// Requests created in the window.
    pub requests: u32,
    /// Of those, delivered.
    pub delivered: u32,
    /// Of those, failed.
    pub failed: u32,
    /// Median wait from `requested` to `delivered`, seconds; `null` without a delivery.
    pub median_wait_s: Option<u64>,
    /// 90th percentile of that wait; `null` without a delivery.
    pub p90_wait_s: Option<u64>,
    /// Top 6 items.
    pub by_item: Vec<ItemCount>,
    /// Top 6 destination places (small ones may be folded into `other`).
    pub by_place: Vec<PlaceCount>,
    /// Bedside tablets heard within 120 s.
    pub bedside_online: u32,
    /// Registered bedside tablets.
    pub bedside_total: u32,
}
