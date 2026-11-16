//! Repository ports: traits implemented by `storage` (`SQLite`) and by test fakes.
//!
//! Records here use domain types only, so `domain` stays at the bottom of the graph.
//! Privacy by type: no port takes a tablet position. The only position persistence is
//! [`RobotRepository::save_last_fix`], which takes a [`RobotId`] and a [`RobotFix`].

use std::collections::BTreeMap;
use std::time::Duration;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::account::{AccountEnrolment, AccountId, AccountRecord, AccountTag, EnrolmentRecord};
use crate::error::{DomainError, StockError};
use crate::ids::{
    ClinicId, DeviceId, ItemId, OwnerLabel, PlaceId, RobotId, ScheduleId, TaskId, UserId, ZoneId,
};
use crate::robot::SeenItem;
use crate::system_mode::SystemModeState;
use crate::task::{Page, Task, TaskFilter};

/// A registered device.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeviceRecord {
    /// Id.
    pub id: DeviceId,
    /// Bound account, if any: the account's `UserId` (`AccountId::user_id`).
    pub user_id: Option<UserId>,
    /// First registration.
    pub registered_at: DateTime<Utc>,
}

/// A stored robot. `key_hash` is the SHA-256 of the robot's provisioning key.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RobotRecord {
    /// Id.
    pub id: RobotId,
    /// Display name.
    pub name: String,
    /// Role card name (`seed/role_cards.json`).
    pub role_card: String,
    /// Simulated robots never do real deliveries.
    pub simulated: bool,
    /// Hash of the provisioning key.
    pub key_hash: String,
}

/// The last known position of a robot. Robots only: there is no tablet equivalent.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RobotFix {
    /// Floor level.
    pub floor: i32,
    /// Metres east.
    pub x: f64,
    /// Metres south (y grows south, see `docs/map-format.md`).
    pub y: f64,
    /// Heading in radians, if known.
    pub heading_rad: Option<f64>,
    /// When it was measured.
    pub at: DateTime<Utc>,
}

/// One item of the reserve and its stock. This is also the wire form of `GET /inventory`
/// and of the `inventory.updated` event (contract C3, as the admin console reads it).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct StockLevel {
    /// Item key (wire name `id`).
    #[serde(rename = "id")]
    pub item: ItemId,
    /// Display name.
    pub label: String,
    /// Shelf place where the item is kept.
    pub place: PlaceId,
    /// Units in stock.
    pub count: u32,
    /// Below this the item is reported as low (wire name `low_at`).
    #[serde(rename = "low_at")]
    pub low_threshold: u32,
    /// The last confident count a robot made on the shelf, if any.
    pub last_robot_count: Option<u32>,
    /// When that count was made.
    pub last_robot_count_at: Option<DateTime<Utc>>,
    /// Last change of `count`.
    pub updated_at: DateTime<Utc>,
}

/// Why stock was adjusted by hand. Closed list: no free text.
///
/// The default, `admin_correction`, is used when the admin console sends only a `delta`.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum StockAdjustReason {
    /// A correction made from the admin console, which sends only a `delta` and no reason.
    /// Kept apart from `correction` so the audit trail shows that no reason was given.
    #[default]
    AdminCorrection,
    /// A manual count.
    Count,
    /// Restocked from the supplier.
    Restock,
    /// Damaged or discarded.
    Damaged,
    /// Correction of an earlier mistake, stated as such by the client (tablet or API).
    Correction,
}

/// Kind of zone (C2 `zones.update`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ZoneKind {
    /// The robot closes its microphone inside.
    Deaf,
    /// The robot must not enter (not yet enforced by the gardien).
    Restricted,
}

/// A stored zone. The polygon is validated by `locations::Polygon` before saving.
#[derive(Debug, Clone, PartialEq)]
pub struct ZoneRecord {
    /// Id.
    pub id: ZoneId,
    /// Display name (an admin's label for the zone, never a person's name).
    pub name: String,
    /// Kind.
    pub kind: ZoneKind,
    /// Floor level.
    pub floor: i32,
    /// Vertices in metres, `[x, y]`.
    pub polygon: Vec<[f64; 2]>,
    /// Bumped on every change.
    pub version: u32,
}

/// A stored schedule; `scheduler::Schedule` is built from it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScheduleRecord {
    /// Id.
    pub id: ScheduleId,
    /// Name.
    pub name: String,
    /// Five-field cron expression.
    pub cron: String,
    /// IANA time zone name.
    pub timezone: String,
    /// Places of the restock round.
    pub places: Vec<PlaceId>,
    /// Whether it runs.
    pub enabled: bool,
    /// Last scheduled time that fired.
    pub last_run: Option<DateTime<Utc>>,
    /// How late a missed run may still fire, in seconds.
    pub grace_s: u64,
    /// Robot the round is given to; `None` lets the dispatcher choose.
    pub robot: Option<RobotId>,
    /// Result of the last round.
    pub last_result: RoundResult,
    /// What the last round counted, shelf by shelf.
    pub last_counts: Vec<ShelfCount>,
}

/// Result of the last restock round of a schedule.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RoundResult {
    /// Every shelf was counted and matched or was restocked.
    Success,
    /// Some shelves were counted, some not.
    Partial,
    /// The round did not complete.
    Failed,
    /// The schedule has never run.
    #[default]
    Never,
}

/// One shelf line of a round's result.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct ShelfCount {
    /// Shelf place.
    pub place: PlaceId,
    /// Item.
    pub item: ItemId,
    /// What the ledger expected.
    pub expected: u32,
    /// What the robot counted.
    pub counted: u32,
}

/// Result of applying a robot event: idempotent through `processed_events`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ApplyOutcome {
    /// First time this event id was seen; the change is saved.
    Applied,
    /// Already processed; nothing changed.
    Duplicate,
}

/// Tasks.
#[async_trait]
pub trait TaskRepository: Send + Sync {
    /// Inserts a new task.
    ///
    /// # Errors
    /// `Conflict` when the id exists; `StoreUnavailable`.
    async fn insert(&self, task: &Task) -> Result<(), DomainError>;
    /// Saves a changed task.
    ///
    /// # Errors
    /// `NotFound`; `StoreUnavailable`.
    async fn update(&self, task: &Task) -> Result<(), DomainError>;
    /// One task.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn get(&self, id: &TaskId) -> Result<Option<Task>, DomainError>;
    /// A page of tasks, newest first.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn list(&self, filter: &TaskFilter, page: &Page) -> Result<Vec<Task>, DomainError>;
    /// Applies a robot event in one transaction: marks `event_id` processed, saves the task,
    /// and applies the optional stock decrement. Returns `Duplicate` if the event was seen.
    ///
    /// # Errors
    /// `NotFound`; `InsufficientStock`; `StoreUnavailable`.
    async fn apply_robot_event(
        &self,
        event_id: Uuid,
        task: &Task,
        stock_decrement: Option<(&ItemId, u32)>,
    ) -> Result<ApplyOutcome, DomainError>;
}

/// Inventory.
#[async_trait]
pub trait InventoryRepository: Send + Sync {
    /// Every item.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn list(&self) -> Result<Vec<StockLevel>, DomainError>;
    /// One item.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn get(&self, item: &ItemId) -> Result<Option<StockLevel>, DomainError>;
    /// Adds `delta` (may be negative) atomically.
    ///
    /// # Errors
    /// `InsufficientStock` when the result would be negative; `NotFound`; `StoreUnavailable`.
    async fn adjust(&self, item: &ItemId, delta: i32) -> Result<StockLevel, DomainError>;
    /// Overwrites a count after a confident robot count.
    ///
    /// # Errors
    /// `NotFound`; `StoreUnavailable`.
    async fn set_count(&self, item: &ItemId, count: u32) -> Result<StockLevel, DomainError>;
    /// Records a robot's confident shelf count (`last_robot_count`, `last_robot_count_at`)
    /// without touching `count`; the reconciliation decides separately whether to overwrite.
    ///
    /// # Errors
    /// `NotFound`; `StoreUnavailable`.
    async fn record_robot_count(
        &self,
        item: &ItemId,
        count: u32,
        at: DateTime<Utc>,
    ) -> Result<StockLevel, DomainError>;
    /// Inserts or replaces an item (seeding).
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn upsert(&self, level: &StockLevel) -> Result<(), DomainError>;
}

/// Pseudonymous accounts and their enrolment codes (Task A7). Nothing stored here
/// identifies a person: no user name, no password, no account key, no enrolment code in
/// clear (only HMACs keyed by the pepper, which is not in the database).
#[async_trait]
pub trait AccountRepository: Send + Sync {
    /// One account.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn find(&self, id: &AccountId) -> Result<Option<AccountRecord>, DomainError>;
    /// Every account whose id starts with the tag (normally one; two is a 24-bit
    /// collision the admin routes report as 409 `ambiguous_account_tag`).
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn find_by_tag(&self, tag: &AccountTag) -> Result<Vec<AccountRecord>, DomainError>;
    /// Every account, oldest first (`GET /admin/accounts`: pseudonyms and tags only).
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn list(&self) -> Result<Vec<AccountRecord>, DomainError>;
    /// Inserts a new account (tests and the first-start bootstrap); never overwrites.
    ///
    /// # Errors
    /// `AccountExists` when the id is taken; `StoreUnavailable`.
    async fn insert(&self, account: &AccountRecord) -> Result<(), DomainError>;
    /// Sets the `disabled` flag; `false` when no such account.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn set_disabled(&self, id: &AccountId, disabled: bool) -> Result<bool, DomainError>;
    /// Marks every unused enrolment code as used (step R1: before a new first-admin code is
    /// issued on a restart with no account, so an older printed code stops working). Returns
    /// how many. The default does nothing.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn retire_unused_codes(&self, now: DateTime<Utc>) -> Result<u64, DomainError> {
        let _ = now;
        Ok(0)
    }
    /// Stores a new enrolment code (its HMAC only).
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn add_enrolment_code(&self, code: &EnrolmentRecord) -> Result<(), DomainError>;
    /// In one transaction: finds the unused code with this HMAC that has not expired at
    /// `now`, inserts the account `id` with the code's role and `display_label`, and marks
    /// the code used. An unknown, used or expired code is `EnrolmentRefused` (one answer for
    /// all three); an id already taken is `AccountExists` and leaves the code unused.
    ///
    /// # Errors
    /// `EnrolmentRefused`; `AccountExists`; `StoreUnavailable`.
    async fn enrol(
        &self,
        code_hash: &[u8; 32],
        now: DateTime<Utc>,
        id: AccountId,
        display_label: &OwnerLabel,
    ) -> Result<AccountEnrolment, DomainError>;
}

/// Devices.
#[async_trait]
pub trait DeviceRepository: Send + Sync {
    /// Registers a device on first login, or rebinds it to a user.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn register(
        &self,
        device: &DeviceId,
        user: Option<&UserId>,
        at: DateTime<Utc>,
    ) -> Result<DeviceRecord, DomainError>;
    /// One device.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn find(&self, id: &DeviceId) -> Result<Option<DeviceRecord>, DomainError>;
}

/// What is stored of emergency mode (Task A8, fill E1, ruling R26): the mode and the robots
/// the server paused on entry (only they are resumed on exit, also after a restart).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredSystemMode {
    /// The mode in force.
    pub state: SystemModeState,
    /// The robots the server paused when it entered emergency mode.
    pub paused_robots: std::collections::BTreeSet<RobotId>,
}

/// The emergency mode switch (Task A8, fill E1): one row and the paused robots, so a restart
/// keeps an emergency on and still knows which robots to resume.
#[async_trait]
pub trait SystemModeStore: Send + Sync {
    /// The stored mode; [`SystemModeState::initial`] and no robot when never switched.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt` when a row cannot be read back.
    async fn load(&self) -> Result<StoredSystemMode, DomainError>;
    /// Replaces the stored mode and the paused robots, in one transaction.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn save(&self, stored: &StoredSystemMode) -> Result<(), DomainError>;
}

/// Robots.
#[async_trait]
pub trait RobotRepository: Send + Sync {
    /// Every robot.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn list(&self) -> Result<Vec<RobotRecord>, DomainError>;
    /// One robot.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn find(&self, id: &RobotId) -> Result<Option<RobotRecord>, DomainError>;
    /// Inserts or replaces a robot (seeding).
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn upsert(&self, robot: &RobotRecord) -> Result<(), DomainError>;
    /// Saves a robot's last position, so a restart knows where it was. Robots only.
    ///
    /// # Errors
    /// `NotFound`; `StoreUnavailable`.
    async fn save_last_fix(&self, robot: &RobotId, fix: &RobotFix) -> Result<(), DomainError>;
    /// The last saved position.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn last_fix(&self, robot: &RobotId) -> Result<Option<RobotFix>, DomainError>;
}

/// Zones.
#[async_trait]
pub trait ZoneRepository: Send + Sync {
    /// Every zone.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn list(&self) -> Result<Vec<ZoneRecord>, DomainError>;
    /// Inserts or replaces a zone and bumps the global version; returns the new global version.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn upsert(&self, zone: &ZoneRecord) -> Result<u64, DomainError>;
    /// Deletes a zone and bumps the global version; `None` if it did not exist.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn delete(&self, id: &ZoneId) -> Result<Option<u64>, DomainError>;
    /// The global zone-set version sent with `zones.update`.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn global_version(&self) -> Result<u64, DomainError>;
}

/// A stored clinic plan (Task A4). The plan itself is kept as the JSON text of a
/// `locations::ClinicPlan` (this crate cannot name that type); the clinic service parses and
/// validates it. At most one record is `active`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClinicRecord {
    /// Id.
    pub id: ClinicId,
    /// The plan's display name (copied out of the plan for listing).
    pub name: String,
    /// Starts at 1, plus one on every saved change.
    pub version: u64,
    /// Whether this is the plan `GET /map` serves and the robots use.
    pub active: bool,
    /// Last change.
    pub updated_at: DateTime<Utc>,
    /// The plan, as canonical JSON (`locations::ClinicPlan`).
    pub plan_json: String,
    /// The modifications (`locations::PlanOverlay`) as JSON; empty text means none.
    pub overlay_json: String,
}

/// What happened to a clinic plan (journal `clinic_changed`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ClinicChange {
    /// `POST /clinics`, or the seed plan stored at first start.
    Created,
    /// `PUT /clinics/{id}`.
    Updated,
    /// `POST /clinics/{id}/activate`.
    Activated,
    /// `DELETE /clinics/{id}`.
    Deleted,
}

/// Clinic plans.
#[async_trait]
pub trait ClinicRepository: Send + Sync {
    /// Every plan, oldest first.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn list(&self) -> Result<Vec<ClinicRecord>, DomainError>;
    /// One plan.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn get(&self, id: &ClinicId) -> Result<Option<ClinicRecord>, DomainError>;
    /// The active plan, `None` before the first plan is stored.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn active(&self) -> Result<Option<ClinicRecord>, DomainError>;
    /// Stores a new plan as given (version and `active` included).
    ///
    /// # Errors
    /// `Conflict` when the id exists; `StoreUnavailable`.
    async fn insert(&self, record: &ClinicRecord) -> Result<(), DomainError>;
    /// Replaces the plan if its stored version is still `expected_version` (one statement:
    /// `UPDATE … WHERE id = ? AND version = ?`), and returns the record with `version + 1`.
    ///
    /// # Errors
    /// `NotFound`; `VersionConflict` naming the current version; `StoreUnavailable`.
    async fn update(
        &self,
        id: &ClinicId,
        expected_version: u64,
        name: &str,
        plan_json: &str,
        overlay_json: &str,
        at: DateTime<Utc>,
    ) -> Result<ClinicRecord, DomainError>;
    /// Makes `id` the only active plan, in one transaction.
    ///
    /// # Errors
    /// `NotFound`; `StoreUnavailable`.
    async fn activate(&self, id: &ClinicId, at: DateTime<Utc>)
    -> Result<ClinicRecord, DomainError>;
    /// Deletes an inactive plan; `false` when it did not exist.
    ///
    /// # Errors
    /// `Conflict` when the plan is the active one; `StoreUnavailable`.
    async fn delete(&self, id: &ClinicId) -> Result<bool, DomainError>;
}

/// Schedules.
#[async_trait]
pub trait ScheduleRepository: Send + Sync {
    /// Every schedule.
    ///
    /// # Errors
    /// `StoreUnavailable`; `Corrupt`.
    async fn list(&self) -> Result<Vec<ScheduleRecord>, DomainError>;
    /// One schedule.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn get(&self, id: &ScheduleId) -> Result<Option<ScheduleRecord>, DomainError>;
    /// Inserts or replaces a schedule.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn upsert(&self, schedule: &ScheduleRecord) -> Result<(), DomainError>;
    /// Claims the run at `scheduled` with one statement
    /// (`UPDATE … WHERE last_run < scheduled RETURNING`). `true` means this caller fires it;
    /// two ticks or two servers cannot both get `true`.
    ///
    /// # Errors
    /// `StoreUnavailable`.
    async fn claim_run(
        &self,
        id: &ScheduleId,
        scheduled: DateTime<Utc>,
    ) -> Result<bool, DomainError>;
}

/// An active stock reservation held by a task.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Reservation {
    /// Reservation id.
    pub id: Uuid,
    /// Holding task.
    pub task: TaskId,
    /// Item.
    pub item: ItemId,
    /// Quantity.
    pub qty: u32,
    /// When it was made (reservations expire after 30 min by default).
    pub created_at: DateTime<Utc>,
}

/// Result of comparing a robot's shelf count with the ledger.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum ReconcileOutcome {
    /// Count agrees.
    Matched {
        /// Item.
        item: ItemId,
    },
    /// Count differs; flagged, and overwritten only when the robot was confident.
    Mismatch {
        /// Item.
        item: ItemId,
        /// Ledger count.
        expected: u32,
        /// Robot count.
        seen: u32,
    },
    /// The robot was unsure or could not count; stock unchanged.
    Uncertain {
        /// Item.
        item: ItemId,
    },
}

/// The stock ledger (Task 15). Port here so `storage::SqliteLedger` and
/// `optimization::InMemoryLedger` implement the same trait without a forbidden edge.
#[async_trait]
pub trait StockLedger: Send + Sync {
    /// Reserves `qty` of `item` for `task`.
    ///
    /// # Errors
    /// `StockError::OutOfStock` with the reserved count in the message; `UnknownItem`.
    async fn reserve(
        &self,
        task: &TaskId,
        item: &ItemId,
        qty: u32,
    ) -> Result<Reservation, StockError>;
    /// Turns a reservation into a stock decrement (on delivery).
    ///
    /// # Errors
    /// `ReservationGone`; `Store`.
    async fn commit(&self, reservation: &Reservation) -> Result<(), StockError>;
    /// Gives a reservation back (cancel, failure).
    ///
    /// # Errors
    /// `ReservationGone`; `Store`.
    async fn release(&self, reservation: &Reservation) -> Result<(), StockError>;
    /// Releases reservations older than `age`; returns how many.
    ///
    /// # Errors
    /// `Store`.
    async fn expire_older_than(&self, age: Duration) -> Result<u32, StockError>;
    /// Compares a robot's shelf count at `place` with the ledger.
    ///
    /// # Errors
    /// `Store`.
    async fn reconcile(
        &self,
        place: &PlaceId,
        seen: &[SeenItem],
    ) -> Result<Vec<ReconcileOutcome>, StockError>;
}

/// Acknowledged zone versions per zone id, as sent in C2 `zone.ack`.
pub type ZoneVersions = BTreeMap<ZoneId, u32>;
