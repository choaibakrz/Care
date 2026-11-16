//! Service traits (`#[async_trait]`, used as `Arc<dyn Trait>`), the mock set, and one real
//! implementation per trait. Every method returns `Result<_, ApiError>`.

pub mod assignment;
pub mod audit;
pub mod auth;
pub mod brain;
pub mod clinics;
pub mod demo;
pub mod devices;
pub mod fleet_home;
pub mod incidents;
pub mod inventory;
pub mod location;
pub mod map;
pub mod mock;
pub mod monitor;
pub mod robots;
pub mod routing;
pub mod schedules;
pub mod service_stats;
pub mod stats;
pub mod system_mode;
pub mod tasks;
pub mod zones;

use std::sync::Arc;

use async_trait::async_trait;
use domain::{
    AccountKey, AccountTag, Actor, ApplyOutcome, BrainHealth, BrainStatus, ClinicId, CommandName,
    DeviceId, FailureReason, ItemId, Page, PlaceId, ReconcileOutcome, ReportDraft, ReportRequest,
    RobotId, ScheduleId, SeenItem, SimplifyRequest, SimplifyResult, StockAdjustReason, StockLevel,
    SummariseRequest, SummaryDraft, SystemModeState, Task, TaskFilter, TaskId, TaskState,
    TranslateRequest, TranslateResult, ZoneId, ZoneVersions,
};
use locations::{
    ClinicMap, ClinicPlan, LiveSnapshot, MapView, PlanOverlay, PositionEstimate, TabletLive,
};
use realtime::{AppErrorCode, Incident, IncidentId, RobotDown, RobotSession};
use security::{ClientIdentity, ClientNetwork};
use uuid::Uuid;

use crate::dto::{
    AccountView, AssignTabletRequest, AuditPageView, AuditQueryParams, BlockView, ClientView,
    ClinicSummary, CommandReceipt, EnrolRequest, EnrolledView, EnrolmentCodeRequest,
    EnrolmentCodeView, HeatView, KeyDerivationParams, LoginResponse, MeView, MonitorSummaryView,
    NewBlockRequest, NewTask, RevertReceipt, RobotView, RouteView, ScanBody, SchedulePatch,
    ScheduleView, ServiceStatsView, SetModeRequest, TabletView, TaskPage, TaskView, TrafficView,
    VersionedOverlay, VersionedPlan, ZoneInput, ZoneView,
};
use crate::error::ApiError;

/// Login, identity and pseudonymous accounts (Task A7). (`WS /ws` authenticates with the
/// first message, through the `TokenVerifier`; there is no ticket.)
///
/// The server never receives a user name or a password: clients send the account key they
/// derived (`docs/accounts.md`), and the server keeps only `HMAC-SHA256(pepper, key)`.
#[async_trait]
pub trait AuthService: Send + Sync {
    /// Looks the key's account id up (`HMAC-SHA256(pepper, key)`, compared in constant
    /// time), refuses a disabled account, issues a token bound to `device` when given, and
    /// journals `LoginSucceeded` (actor the account) or `LoginFailed`. A device-less token
    /// (browser) cannot use `X-Client-Id` (403 `identity_mismatch`) nor the tablet-only
    /// endpoints (403 `device_required`). An unknown key, a wrong password (which is an
    /// unknown key) and a disabled account give the same 401 `invalid_credentials` in the
    /// same time; nothing of the key is written anywhere. `operator` is the account's owner
    /// label `"<pseudonym> #<tag>"`.
    async fn login(
        &self,
        key: &AccountKey,
        device: Option<DeviceId>,
        network: &ClientNetwork,
    ) -> Result<LoginResponse, ApiError>;
    /// The A3 `{username, password}` body. **Mock compatibility until frontend task F9**:
    /// `--mock` derives the key itself (`security::derive_account_key`) and continues as
    /// [`AuthService::login`]. The live service answers 422 `key_derivation_required`
    /// without reading the password (the handler already refuses outside `--mock`).
    async fn login_with_password(
        &self,
        username: &str,
        password: &str,
        device: Option<DeviceId>,
        network: &ClientNetwork,
    ) -> Result<LoginResponse, ApiError>;
    /// `GET /auth/derivation`: the derivation's parameters and this server's account clinic
    /// id. Never fails.
    fn derivation(&self) -> KeyDerivationParams;
    /// `POST /auth/enrol`: checks the pseudonym (at most 32 characters), consumes the code
    /// and creates the account `HMAC(pepper, key)` with the code's role, in one transaction
    /// (`AccountRepository::enrol`); journals `AccountEnrolled` (by code id and account tag).
    /// 403 `enrolment_refused` for an unknown, used or expired code (one answer); 409
    /// `account_exists` when these credentials are already an account (the code stays
    /// unused).
    async fn enrol(
        &self,
        request: EnrolRequest,
        network: &ClientNetwork,
    ) -> Result<EnrolledView, ApiError>;
    /// `POST /admin/enrolment-codes` (admin; the handler checks `ManageAccounts`): a new
    /// one-time code for `role` (not `robot`: 422), valid 24 h; stores its HMAC, journals
    /// `EnrolmentCodeIssued` by code id. The code is in the answer only.
    async fn issue_enrolment_code(
        &self,
        actor: &ClientIdentity,
        request: EnrolmentCodeRequest,
    ) -> Result<EnrolmentCodeView, ApiError>;
    /// `GET /admin/accounts` (admin): every account, pseudonym and tag only.
    async fn list_accounts(&self) -> Result<Vec<AccountView>, ApiError>;
    /// `DELETE /admin/accounts/{account_tag}` (admin): disables the account and revokes its
    /// tokens; journals `AccountDisabled`. 404 for an unknown tag; 409
    /// `ambiguous_account_tag` when two accounts share it; 409 `cannot_disable_self` for the
    /// caller's own account. There is no recovery: a forgotten password means disable and
    /// issue a new code.
    async fn disable_account(
        &self,
        actor: &ClientIdentity,
        tag: &AccountTag,
    ) -> Result<(), ApiError>;
    /// The caller's view of itself.
    async fn me(&self, identity: &ClientIdentity) -> Result<MeView, ApiError>;
}

/// The task queue. Answers are `TaskView`s: the requester's owner label and the history are
/// joined in.
#[async_trait]
pub trait TaskService: Send + Sync {
    /// Creates a task, reserves stock, and hands it to dispatch.
    async fn create(&self, actor: &ClientIdentity, new: NewTask) -> Result<TaskView, ApiError>;
    /// The same as [`TaskService::create`] for a server component (ruling R15): `actor` must
    /// be `Actor::System` (any other actor is 500 `internal`, a programming error). Demo mode
    /// creates its requests as `Actor::System("demo")`, shown as "SIMULATED request".
    async fn create_as_system(&self, actor: Actor, new: NewTask) -> Result<TaskView, ApiError>;
    /// One task.
    async fn get(&self, id: &TaskId) -> Result<TaskView, ApiError>;
    /// A page of tasks.
    async fn list(&self, filter: TaskFilter, page: Page) -> Result<TaskPage, ApiError>;
    /// Unfinished tasks (for the app snapshot).
    async fn active(&self) -> Result<Vec<TaskView>, ApiError>;
    /// Cancels (admin or the requester) while `requested` or `assigned`: state `cancelled`.
    /// Otherwise 409; another user is 403.
    async fn cancel(&self, actor: &ClientIdentity, id: &TaskId) -> Result<TaskView, ApiError>;
    /// Applies a robot `task.event`, idempotent by `event_id`.
    async fn apply_robot_event(
        &self,
        robot: &RobotId,
        event_id: Uuid,
        task: &TaskId,
        state: TaskState,
        reason: Option<FailureReason>,
    ) -> Result<ApplyOutcome, ApiError>;
    /// A robot was lost: `assigned` tasks go back to `requested`; `en_route` tasks are flagged
    /// "robot lost, human needed". Returns the tasks touched.
    async fn on_robot_lost(&self, robot: &RobotId) -> Result<Vec<TaskId>, ApiError>;
    /// A reconnecting robot says it still runs `task`: a task put back in the queue meanwhile
    /// is given back to it. Nothing to do by default (the mock keeps no queue to settle).
    async fn on_robot_resumed(&self, _robot: &RobotId, _task: &TaskId) -> Result<(), ApiError> {
        Ok(())
    }
}

/// Stock.
#[async_trait]
pub trait InventoryService: Send + Sync {
    /// Every item.
    async fn list(&self) -> Result<Vec<StockLevel>, ApiError>;
    /// Admin adjustment; refuses results below zero ("Cannot remove 5 'blanket': only 3 in
    /// stock.").
    async fn adjust(
        &self,
        actor: &ClientIdentity,
        item: &ItemId,
        delta: i32,
        reason: StockAdjustReason,
    ) -> Result<StockLevel, ApiError>;
    /// Delivery hook: commits the task's reservation (decrements stock).
    async fn on_delivered(&self, task: &Task) -> Result<(), ApiError>;
    /// A robot's shelf count (`inventory.seen`).
    async fn on_seen(
        &self,
        robot: &RobotId,
        place: &PlaceId,
        items: &[SeenItem],
    ) -> Result<Vec<ReconcileOutcome>, ApiError>;
}

/// The clinic map.
#[async_trait]
pub trait MapService: Send + Sync {
    /// The current map (the model of the active plan).
    async fn map(&self) -> Result<Arc<ClinicMap>, ApiError>;
    /// `GET /map`: the active plan as the console draws it, and its tag (the `ETag`,
    /// `<clinic id>-v<version>`).
    async fn view(&self) -> Result<(MapView, String), ApiError>;
}

/// Stored clinic plans (Task 10b). Every change is validated as a whole, journaled
/// (`clinic_changed`), and announced: `map.updated` on `/ws` for every change, `map.update`
/// to every connected robot when the active plan changed.
#[async_trait]
pub trait ClinicService: Send + Sync {
    /// Every stored plan.
    async fn list(&self) -> Result<Vec<ClinicSummary>, ApiError>;
    /// One plan; 404 `not_found`.
    async fn get(&self, id: &ClinicId) -> Result<VersionedPlan, ApiError>;
    /// Validates and stores a new plan (version 1, inactive). The id is derived from the
    /// name: lowercased, every run of other characters turned into `-`, cut to 48
    /// characters. 409 `clinic_exists` when that id is already taken (rename the plan);
    /// 422 `invalid_plan` with every problem.
    async fn create(
        &self,
        actor: &ClientIdentity,
        plan: ClinicPlan,
    ) -> Result<ClinicSummary, ApiError>;
    /// `PUT /clinics/{id}`: replaces the base plan and clears the modifications (step L1).
    /// Replaces a plan if `expected_version` is still current (412 `version_conflict`
    /// otherwise), after validation (422 `invalid_plan`) and the referential check: a place
    /// removed or renamed while an open task, a stock item, a schedule stop or a robot's dock
    /// uses it is 409 `place_in_use` listing every user. Returns the plan at `version + 1`.
    /// When the plan is the active one, the active map is replaced and the routing graph
    /// rebuilt.
    async fn update(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        plan: ClinicPlan,
    ) -> Result<VersionedPlan, ApiError>;
    /// Makes a plan the active one. 409 `open_tasks` listing them while any task is not
    /// finished; 409 `place_in_use` when a stock item, schedule stop or dock names a place the
    /// plan does not have. Activating the active plan is a no-op. Then the active map is
    /// replaced and the routing graph rebuilt.
    async fn activate(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
    ) -> Result<ClinicSummary, ApiError>;
    /// The base plan, without the modifications (`get` returns the effective plan).
    async fn base(&self, id: &ClinicId) -> Result<VersionedPlan, ApiError>;
    /// The modifications (empty when none).
    async fn overlay(&self, id: &ClinicId) -> Result<VersionedOverlay, ApiError>;
    /// Stores the modifications (an empty overlay resets to the base) after validating the
    /// effective plan (422 `invalid_plan`); returns the effective plan at `version + 1`.
    async fn put_overlay(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        overlay: PlanOverlay,
    ) -> Result<VersionedPlan, ApiError>;
    /// Replaces the base plan, keeping the modifications; the effective plan is validated.
    async fn put_base(
        &self,
        actor: &ClientIdentity,
        id: &ClinicId,
        expected_version: u64,
        plan: ClinicPlan,
    ) -> Result<VersionedPlan, ApiError>;
    /// Deletes an inactive plan; 409 `clinic_active` for the active one; 404 when unknown.
    async fn delete(&self, actor: &ClientIdentity, id: &ClinicId) -> Result<(), ApiError>;
}

/// Route previews of tasks (Task 13b).
#[async_trait]
pub trait RouteService: Send + Sync {
    /// The estimated remaining path of a task: from its robot's live position (or, without a
    /// live robot, from its `from_place`, else from the configured dock) through its
    /// `from_place` when the item is not picked up yet, to its `to_place`, on the active plan
    /// with the restricted zones impassable. 404 `not_found` for an unknown task; 404
    /// `no_route` with the reason (different floors, no free ground, unreachable, finished
    /// task).
    async fn task_route(&self, id: &TaskId) -> Result<RouteView, ApiError>;
}

/// Fleet statistics (Task 11d).
#[async_trait]
pub trait StatsService: Send + Sync {
    /// The heat map of a floor; 422 `invalid_field` (`floor`) when the active plan has no
    /// such floor.
    async fn heat(&self, floor: i32) -> Result<HeatView, ApiError>;
}

/// Emergency mode (Task A8, fill E1; `implementation/admin/requirements/emergency-mode.md`).
///
/// While the mode is `emergency`, the router's emergency filter (`crate::emergency_mode`)
/// answers 503 `emergency_mode` to every request not on the allow-list, no task is handed
/// out and no night round starts. It never touches the emergency service (patient alarms).
#[async_trait]
pub trait SystemModeService: Send + Sync {
    /// `GET /system/mode` (any signed-in caller).
    async fn mode(&self) -> Result<SystemModeState, ApiError>;
    /// `PUT /system/mode` (admin; the handler checks `SwitchSystemMode`). Switching to the
    /// mode in force is 200 with no change (idempotent). Otherwise: stores the mode (a
    /// restart keeps an emergency on), journals `system_mode_changed` (from, to, by,
    /// reason), publishes `mode.updated` and an `alert` (`emergency_mode_on`, critical, on
    /// entry; `emergency_mode_off`, info, on exit), and clears or restores the robots:
    ///
    /// - entry: a robot with no task or driving home gets `dock`; a robot with a task and
    ///   nothing in its hands gets `task.cancel` (the task goes back to `requested`, history
    ///   `held: emergency mode`) then `dock`; a robot carrying an item gets `pause` and is
    ///   remembered; robots in `estop` or `fault` (or charging) are left alone;
    /// - exit: `resume` only the robots the server paused, then hand out the queue again.
    ///
    /// A robot that refuses a command is not retried: the refusal goes to the journal and an
    /// `alert` (`command_refused`). 422 `invalid_field` for a reason over 200 characters.
    async fn set_mode(
        &self,
        actor: &ClientIdentity,
        request: SetModeRequest,
    ) -> Result<SystemModeState, ApiError>;
    /// Whether emergency mode is on now (synchronous and cheap: read by the router's filter
    /// on every request).
    fn is_emergency(&self) -> bool;
}

/// The tablet registry (Task A8, fill T8b; `tablets.md`): every registered tablet, free and
/// offline ones included. Admin only. No answer carries a patient name or a health field;
/// the A5 `patient_name` of a staff tablet never appears here.
#[async_trait]
pub trait DeviceAdminService: Send + Sync {
    /// `GET /devices`.
    async fn list(&self) -> Result<Vec<TabletView>, ApiError>;
    /// `POST /devices/{id}/disconnect`: revokes the tablet's session token at once (its
    /// user is signed out), clears `label` and `speciality`, sets `assigned: false`, puts it
    /// back on its shelf place; journals `device_freed` (device id only); publishes
    /// `device.updated`. 404 `not_found`; 409 `already_free`.
    async fn disconnect(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
    ) -> Result<TabletView, ApiError>;
    /// `POST /devices/{id}/assign`: binds the tablet's next login to this assignment;
    /// journals `device_assigned` (device id, kind, and the label of a bedside tablet only);
    /// publishes `device.updated`. 404 `not_found`; 409 `in_use` (free it first); 409
    /// `offline`; 422 `invalid_field` (label empty, over 40 characters or digits only; a
    /// bedside tablet without a patient-room `place`, or with a `speciality`).
    async fn assign(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
        request: AssignTabletRequest,
    ) -> Result<TabletView, ApiError>;
}

/// Server monitoring and address blocks (Task A8, fill T7b; `monitoring-security.md`).
/// Admin only, never rate-limited for an authenticated admin, allowed in emergency mode.
/// Addresses, network labels and counts only: never a user name.
#[async_trait]
pub trait MonitorService: Send + Sync {
    /// `GET /monitor/summary`.
    async fn summary(&self) -> Result<MonitorSummaryView, ApiError>;
    /// `GET /monitor/traffic?window_s=` (1 to 300).
    async fn traffic(&self, window_s: u32) -> Result<TrafficView, ApiError>;
    /// `GET /monitor/clients?limit=` (1 to 100): the busiest addresses of the last 5 minutes.
    async fn clients(&self, limit: u32) -> Result<Vec<ClientView>, ApiError>;
    /// `GET /security/blocks`: the active rules.
    async fn blocks(&self) -> Result<Vec<BlockView>, ApiError>;
    /// `POST /security/blocks`: a manual rule (the caller's own address, loopback, a
    /// connected robot and the emergency service are refused with 422 `protected_target`;
    /// broader than /16 or /48 with 422 `range_too_broad`). Journals `client_blocked`, sends
    /// `security.alert` `blocked`, closes the open WebSockets of the address.
    async fn add_block(
        &self,
        actor: &ClientIdentity,
        request: NewBlockRequest,
    ) -> Result<BlockView, ApiError>;
    /// `DELETE /security/blocks/{id}`: journals `client_unblocked`, sends `unblocked`. 404
    /// `not_found` when it expired or another admin removed it.
    async fn remove_block(&self, actor: &ClientIdentity, id: &str) -> Result<(), ApiError>;
}

/// Service statistics (Task A8, fill T11e): `GET /stats/service`, counts only.
#[async_trait]
pub trait ServiceStatsService: Send + Sync {
    /// The requests created in the last `hours` (1 to 720): how many, delivered, failed, the
    /// wait from `requested` to `delivered` (median, p90), the top 6 items and destination
    /// places, and the bedside tablets online. A place with fewer requests than the
    /// configured k-anonymity threshold is folded into `other` (off by default).
    async fn service(&self, hours: u32) -> Result<ServiceStatsView, ApiError>;
}

/// Live positions and tablet rooms (memory only).
#[async_trait]
pub trait LocationService: Send + Sync {
    /// Every live position.
    async fn live(&self) -> Result<LiveSnapshot, ApiError>;
    /// Sets the caller's tablet room; unknown place is 422 `unknown_place` with suggestions.
    /// The handler only lets device-bound tokens through (`TabletAuthorized`).
    async fn set_my_location(
        &self,
        identity: &ClientIdentity,
        place: &PlaceId,
    ) -> Result<TabletLive, ApiError>;
    /// One Bluetooth scan from the caller's tablet (device-bound tokens only).
    async fn ingest_scan(
        &self,
        identity: &ClientIdentity,
        scan: ScanBody,
    ) -> Result<PositionEstimate, ApiError>;
}

/// Zones.
#[async_trait]
pub trait ZoneService: Send + Sync {
    /// Zones with delivery state.
    async fn list(&self) -> Result<Vec<ZoneView>, ApiError>;
    /// Validates, bumps the version, saves, journals, publishes, sends to robots, and
    /// rebuilds the dispatcher's routing graph (`RoutingCache::rebuild`, restricted zones are
    /// impassable for planning).
    async fn upsert(
        &self,
        actor: &ClientIdentity,
        id: ZoneId,
        input: ZoneInput,
    ) -> Result<ZoneView, ApiError>;
    /// Deletes, propagates the reduced set and rebuilds the routing graph.
    async fn delete(&self, actor: &ClientIdentity, id: &ZoneId) -> Result<(), ApiError>;
    /// The full `zones.update` message (sent to a robot on reconnect).
    async fn zones_update(&self) -> Result<RobotDown, ApiError>;
    /// Records a robot's `zone.ack`.
    async fn record_ack(&self, robot: &RobotId, versions: &ZoneVersions) -> Result<(), ApiError>;
}

/// Robots.
#[async_trait]
pub trait RobotService: Send + Sync {
    /// Every robot with its last reported state (never `offline`) and `last_seen`.
    async fn list(&self) -> Result<Vec<RobotView>, ApiError>;
    /// `pause`, `resume`, `dock`, `shutdown` (permissions checked by the handler: `shutdown`
    /// is admin only, ruling R24). Refused with `journal_unavailable` while the journal cannot
    /// write; 409 when the robot is offline. While the robot is latched in emergency stop, a
    /// non-admin `resume` is 409 `estop_latched` ("Only an admin can re-arm a robot after an
    /// emergency stop.") and nothing is sent; an admin's `resume` re-arms it (clears the
    /// latch once sent). Every command gets a fresh `command_id` (in the receipt and the
    /// journal record). A command from a non-admin also publishes the alert `staff_command`
    /// (warning) with a `CommandNotice`, so the admin can revert it (Task A7).
    async fn command(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        name: CommandName,
    ) -> Result<CommandReceipt, ApiError>;
    /// `POST /robots/{id}/commands/{command_id}/revert` (admin; the handler checks
    /// `RevertCommand`, Task A7): sends the inverse of a command a non-admin sent (`pause` ->
    /// `resume`, `resume` -> `pause`, `dock` -> `resume`) as a new command of the admin,
    /// journals `RobotCommandReverted`, and answers the inverse's id. 404 when the command is
    /// unknown or not this robot's; 409 `not_revertible` for an emergency stop, a shutdown
    /// or an admin's own command; 409 `already_reverted` (also while another revert of it is
    /// being sent: the entry is reserved under the log's lock before the inverse goes out,
    /// released if the send fails); 409 `estop_latched` while the robot is in emergency stop;
    /// 409 `superseded` when a later command was sent to the robot (only the latest command
    /// is revertible); 409 `robot_offline`; 503 while the journal cannot write.
    async fn revert(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        command_id: Uuid,
    ) -> Result<RevertReceipt, ApiError>;
    /// The emergency stop, through `EstopPath::trigger`: sent first, recorded after, works
    /// with the journal down. Offline robot: 409 "Robot X is offline: the stop was not
    /// delivered. Use the physical button." (and still recorded).
    async fn estop(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
    ) -> Result<CommandReceipt, ApiError>;
    /// Whether the robot is registered.
    async fn is_known(&self, robot: &RobotId) -> Result<bool, ApiError>;
    /// Runs one robot's session until the socket closes (hello, state, task events, inventory,
    /// zone acks; zones sent on connect).
    async fn run_session(&self, session: RobotSession);
    /// The socket closed.
    async fn on_disconnect(&self, robot: &RobotId);
    /// Finds robots silent for 5 s: alerts (`robot_offline`), hands their tasks back, and
    /// returns them. Their `state` keeps the last reported value.
    async fn check_liveness(&self) -> Vec<RobotId>;
    /// `POST /robots/{id}/teleport` (admin; the handler checks it): moves a simulated robot.
    /// 404 unknown robot; 409 `not_simulated` for a real robot; 422 outside the floor outline
    /// or inside a restricted zone. Publishes `robot.updated`.
    async fn teleport(
        &self,
        robot: &RobotId,
        to: crate::dto::TeleportRequest,
    ) -> Result<RobotView, ApiError> {
        let _ = to;
        Err(ApiError::conflict(
            "not_simulated",
            format!(
                "Robot {robot} is not a simulated robot of this server: it cannot be teleported."
            ),
        ))
    }
    /// `GET /fleet/home`: the fleet's home place (all `null` when none).
    async fn fleet_home(&self) -> Result<crate::dto::FleetHomeView, ApiError> {
        Ok(crate::dto::FleetHomeView {
            place_id: None,
            label: None,
            floor: None,
        })
    }
    /// `PUT /fleet/home` (admin): sets or clears the home place (422 unknown place).
    async fn set_fleet_home(
        &self,
        place_id: Option<domain::PlaceId>,
    ) -> Result<crate::dto::FleetHomeView, ApiError> {
        let _ = place_id;
        Err(ApiError::unavailable("fleet home store"))
    }
    /// The in-process simulated fleet of the live server, when one is attached.
    fn sim_fleet(&self) -> Option<std::sync::Arc<crate::sim::fleet::SimFleet>> {
        None
    }
}

/// Schedules.
#[async_trait]
pub trait ScheduleService: Send + Sync {
    /// Every schedule with its last result.
    async fn list(&self) -> Result<Vec<ScheduleView>, ApiError>;
    /// Applies a partial change (admin): `time` becomes the cron `"MM HH * * *"`. 404 for an
    /// unknown schedule; publishes `schedule.updated`.
    async fn update(
        &self,
        actor: &ClientIdentity,
        id: &ScheduleId,
        patch: SchedulePatch,
    ) -> Result<ScheduleView, ApiError>;
}

/// Audit queries.
#[async_trait]
pub trait AuditQueryService: Send + Sync {
    /// A page of the audit index, as audit rows (`services::audit::audit_row`).
    async fn query(&self, params: AuditQueryParams) -> Result<AuditPageView, ApiError>;
    /// The last verification report.
    async fn integrity(&self) -> Result<::audit::VerifyReport, ApiError>;
}

/// Incidents.
#[async_trait]
pub trait IncidentService: Send + Sync {
    /// Incidents, open only or all.
    async fn list_incidents(&self, open_only: bool) -> Result<Vec<Incident>, ApiError>;
    /// Acknowledges; emergency alarms are refused (409, acknowledged in the emergency service).
    async fn acknowledge(
        &self,
        actor: &ClientIdentity,
        id: IncidentId,
    ) -> Result<Incident, ApiError>;
    /// Closes (admin).
    async fn close_incident(
        &self,
        actor: &ClientIdentity,
        id: IncidentId,
    ) -> Result<Incident, ApiError>;
    /// A tablet's own error from the catalogue (device-bound tokens only).
    async fn report_device_event(
        &self,
        actor: &ClientIdentity,
        code: AppErrorCode,
    ) -> Result<(), ApiError>;
}

/// The server-side brain for clients (Task A6): translate, simplify, summarise, report.
///
/// Every result is a draft (`draft: true`) a staff member reads before anything is sent
/// anywhere. Texts are processed in memory only: an implementation never stores, logs or
/// journals them; the live one journals `BrainCall { kind, latency_ms, ok }` per call. When
/// the brain is down every call is 503 `brain_unavailable` and the rest of the server keeps
/// working. The handler checks the permission (`UseBrain`, `SummariseSources`,
/// `DraftReport`).
#[async_trait]
pub trait BrainService: Send + Sync {
    /// A translation with the fixed medical terms and the number check. 422
    /// `unsupported_language` for a pair the brain cannot do.
    async fn translate(
        &self,
        actor: &ClientIdentity,
        request: TranslateRequest,
    ) -> Result<TranslateResult, ApiError>;
    /// A plain-language rewrite for a patient (never medical advice); `simplified: false`
    /// with the original text when it could not be simplified safely.
    async fn simplify(
        &self,
        actor: &ClientIdentity,
        request: SimplifyRequest,
    ) -> Result<SimplifyResult, ApiError>;
    /// A summary whose every line names its source (422 `invalid_field` for an empty list,
    /// more than 20 sources, or two sources with one id).
    async fn summarise(
        &self,
        actor: &ClientIdentity,
        request: SummariseRequest,
    ) -> Result<SummaryDraft, ApiError>;
    /// A report from server data the caller may see (422 `invalid_field` for a bad period).
    async fn report(
        &self,
        actor: &ClientIdentity,
        request: ReportRequest,
    ) -> Result<ReportDraft, ApiError>;
    /// Asks the brain now (`GET /brain/health`); never fails: `down` with the reason.
    async fn health(&self) -> BrainHealth;
    /// The last known status, without waiting (`GET /health` `brain`).
    fn status(&self) -> BrainStatus;
}

/// Whether actions can be recorded now (degraded mode check, synchronous and cheap).
pub trait JournalStatus: Send + Sync {
    /// `false` while the journal cannot write.
    fn is_writable(&self) -> bool;
}
