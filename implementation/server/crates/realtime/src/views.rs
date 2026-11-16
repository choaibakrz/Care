//! The wire views the admin console reads (contract C3, `implementation/admin/src/lib/adapt.ts`).
//!
//! They live here, not in the binary, because the `WS /ws` events carry the same objects as
//! the REST answers: `robot.updated {robot}` is a [`RobotView`], `task.updated {task}` a
//! [`TaskView`], `zone.updated {zone}` a [`ZoneView`], `schedule.updated {schedule}` a
//! [`ScheduleView`]. Field names are `snake_case`; the console ignores unknown fields, so the
//! extra fields here (`connected`, `version`, …) are for the other clients and the tests.

use chrono::{DateTime, Utc};
use domain::{
    Actor, DeviceId, ItemId, OwnerLabel, PlaceId, RobotId, RobotStatus, RoundResult, ScheduleId,
    ShelfCount, Task, TaskId, TaskKind, TaskState, ZoneId, ZoneKind,
};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::protocol::RobotPose;
use crate::zone_delivery::ZoneDeliveryEntry;

/// A robot in `GET /robots` and in `robot.updated`.
///
/// `state` is never `offline` (the type has no such value): it is the last reported state.
/// Staleness is shown by `last_seen` and by an `alert`. A robot never heard from is listed
/// with its seeded start position and `last_seen: null`.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[allow(
    clippy::struct_excessive_bools,
    reason = "wire view: independent flags the console reads"
)]
pub struct RobotView {
    /// Id.
    pub id: RobotId,
    /// Display name.
    pub name: String,
    /// Role card name.
    pub role: String,
    /// Simulated robots never do real deliveries.
    pub simulated: bool,
    /// Last known position (metres, y grows south), or the seeded start position.
    pub pos: RobotPose,
    /// Battery percentage; `null` until the robot reports one.
    pub battery: Option<f32>,
    /// Last reported state (`idle` until the robot reports one).
    pub state: RobotStatus,
    /// Item carried.
    pub holding: Option<ItemId>,
    /// Microphone open. `false` when unknown: never claim a robot listens.
    pub mic_open: bool,
    /// Current task.
    pub task_id: Option<TaskId>,
    /// Last message from the robot; `null` if never heard from.
    pub last_seen: Option<DateTime<Utc>>,
    /// Whether its WebSocket is connected now (extra field; the console uses `last_seen`).
    pub connected: bool,
    /// Whether its last position is inside a deaf zone of its floor.
    pub in_deaf_zone: bool,
    /// Whether it is driving to the fleet's home place (emergency, `dock`, low battery).
    pub going_home: bool,
    /// Server-derived mood the console shows as an emoji.
    pub mood: RobotMood,
}

/// A robot's mood, derived by the server from its state (the console shows an emoji).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RobotMood {
    /// Wandering or idle, all fine.
    #[default]
    Happy,
    /// Working on a task.
    Busy,
    /// Inside a deaf zone (microphone closed).
    Deaf,
    /// Charging its battery.
    Charging,
    /// Going to, or waiting at, the home place.
    Home,
    /// Emergency mode or a fault.
    Alarm,
    /// Paused or emergency-stopped.
    Stopped,
    /// Not connected.
    Offline,
}

/// What [`RobotMood::derive`] looks at.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[allow(
    clippy::struct_excessive_bools,
    reason = "independent flags of one robot"
)]
pub struct MoodInputs {
    /// Connected now.
    pub connected: bool,
    /// Clinic in emergency mode.
    pub emergency: bool,
    /// Charging its battery.
    pub charging: bool,
    /// Going to, or at, the home place.
    pub home: bool,
    /// Inside a deaf zone.
    pub in_deaf_zone: bool,
    /// Has a task.
    pub has_task: bool,
}

impl RobotMood {
    /// The mood, first match wins: offline, stopped (paused, estop), alarm (fault,
    /// emergency), charging, home, deaf, busy, happy.
    #[must_use]
    pub fn derive(state: RobotStatus, inputs: MoodInputs) -> RobotMood {
        if !inputs.connected {
            RobotMood::Offline
        } else if matches!(state, RobotStatus::Paused | RobotStatus::Estop) {
            RobotMood::Stopped
        } else if state == RobotStatus::Fault || inputs.emergency {
            RobotMood::Alarm
        } else if inputs.charging {
            RobotMood::Charging
        } else if inputs.home {
            RobotMood::Home
        } else if inputs.in_deaf_zone {
            RobotMood::Deaf
        } else if state == RobotStatus::Busy || inputs.has_task {
            RobotMood::Busy
        } else {
            RobotMood::Happy
        }
    }
}

/// One line of a task's history.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct TaskHistoryEntry {
    /// When.
    pub at: DateTime<Utc>,
    /// Who: an owner label, `robot:<id>` or `server`. Never a user id or a name.
    pub actor: String,
    /// What happened: the new state name (`requested`, `assigned`, …).
    pub label: String,
}

/// A task as `GET /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel` and `task.updated`
/// send it.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct TaskView {
    /// Id.
    pub id: TaskId,
    /// Kind.
    pub kind: TaskKind,
    /// Item.
    pub item: Option<ItemId>,
    /// Origin place.
    pub from_place: Option<PlaceId>,
    /// Destination place.
    pub to_place: PlaceId,
    /// State.
    pub state: TaskState,
    /// Assigned robot.
    pub robot_id: Option<RobotId>,
    /// Who asked, from [`requester_label`]: the requester's owner label, `SIMULATED request`
    /// for demo mode's system actor `demo`, `server` for the other system actors. Never a
    /// user id or name.
    pub requested_by: String,
    /// Created.
    pub created_at: DateTime<Utc>,
    /// Last change.
    pub updated_at: DateTime<Utc>,
    /// Why it failed (a `FailureReason` code) or why a human must take over (the
    /// dispatcher's explanation). Built from typed fields only.
    pub reason: Option<String>,
    /// State changes, oldest first.
    pub history: Vec<TaskHistoryEntry>,
    /// `follow` tasks (Step C1): the staff tablet being followed.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_device: Option<domain::DeviceId>,
    /// `follow` tasks: the tablet's owner pseudonym ("Dr. A"), never a real name.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_label: Option<String>,
    /// `follow` tasks: when the robot stops following.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub until: Option<DateTime<Utc>>,
}

/// `requested_by` of the tasks created by demo mode (`Actor::System("demo")`).
pub const SIMULATED_REQUEST_LABEL: &str = "SIMULATED request";

/// The `requested_by` text of a task (ruling R15): a user's owner label (`owner`, looked up by
/// the caller); [`SIMULATED_REQUEST_LABEL`] for `Actor::System("demo")`; `server` for every
/// other system actor; `robot:<id>` for a robot; the device's owner label (`owner`) for a
/// device. A user or device without a label shows `unknown`.
#[must_use]
pub fn requester_label(actor: &Actor, owner: Option<&OwnerLabel>) -> String {
    match actor {
        Actor::System("demo") => SIMULATED_REQUEST_LABEL.to_owned(),
        Actor::System(_) => "server".to_owned(),
        Actor::Robot(robot) => format!("robot:{robot}"),
        Actor::User(_) | Actor::Device(_) => {
            owner.map_or_else(|| "unknown".to_owned(), |label| label.as_str().to_owned())
        }
    }
}

/// The wire code of a failure reason (its serde spelling).
fn failure_code(reason: domain::FailureReason) -> &'static str {
    use domain::FailureReason;
    match reason {
        FailureReason::ItemMissing => "item_missing",
        FailureReason::PathBlocked => "path_blocked",
        FailureReason::RobotFault => "robot_fault",
        FailureReason::RobotLost => "robot_lost",
        FailureReason::HandedToHuman => "handed_to_human",
        FailureReason::DeadlinePassed => "deadline_passed",
    }
}

impl TaskView {
    /// The view of `task`, with the requester's owner label and the task's history.
    ///
    /// `reason` is the failure code when the task failed, else the dispatcher's explanation
    /// when a human must take over, else `None`.
    #[must_use]
    pub fn new(task: &Task, requested_by: String, history: Vec<TaskHistoryEntry>) -> TaskView {
        let reason = match task.failure() {
            Some(failure) => Some(failure_code(failure).to_owned()),
            None => task.needs_human().map(str::to_owned),
        };
        TaskView {
            id: task.id().clone(),
            kind: task.kind(),
            item: task.item().cloned(),
            from_place: task.from().cloned(),
            to_place: task.to().clone(),
            state: task.state(),
            robot_id: task.assigned_robot().cloned(),
            requested_by,
            created_at: task.created_at(),
            updated_at: task.updated_at(),
            reason,
            history,
            target_device: None,
            target_label: None,
            until: None,
        }
    }
}

/// A zone as `GET /zones`, `PUT /zones/{id}` and `zone.updated` send it.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct ZoneView {
    /// Id.
    pub id: ZoneId,
    /// Display name.
    pub name: String,
    /// Floor.
    pub floor: i32,
    /// Kind.
    pub kind: ZoneKind,
    /// Vertices in metres, `[x, y]`, y grows south.
    #[schema(value_type = Vec<Vec<f64>>)]
    pub polygon: Vec<[f64; 2]>,
    /// Delivery to each robot.
    pub deliveries: Vec<ZoneDeliveryEntry>,
    /// `false` for restricted zones for now (architecture.md open question 5).
    pub enforced_by_gardien: bool,
    /// Version, bumped on every change; robots acknowledge it (extra field).
    pub version: u32,
}

/// A schedule (the night restock round) as `GET /schedules`, `PUT /schedules/{id}` and
/// `schedule.updated` send it. Schedules are daily: the API shows `time`, the server keeps
/// the cron expression `"MM HH * * *"` internally.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct ScheduleView {
    /// Id.
    pub id: ScheduleId,
    /// Display name.
    pub label: String,
    /// Enabled.
    pub enabled: bool,
    /// Local time `HH:MM` in `timezone` (Europe/Zurich by default).
    pub time: String,
    /// Robot the round is given to; `null` lets the dispatcher choose.
    pub robot_id: Option<RobotId>,
    /// Last run.
    pub last_run: Option<DateTime<Utc>>,
    /// Result of the last run.
    pub last_result: RoundResult,
    /// Counts of the last run.
    pub last_counts: Vec<ShelfCount>,
    /// Time zone of `time` (extra field).
    pub timezone: String,
    /// Next run (extra field).
    pub next_run: Option<DateTime<Utc>>,
}

/// What a tablet is for (Task A8, `tablets.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TabletKind {
    /// Goes with a person (a staff member's pseudonym).
    Staff,
    /// Stays with a bed (labelled with the bed, never the patient).
    Bedside,
}

/// A tablet as `GET /devices`, `POST /devices/{id}/disconnect|assign` and `device.updated`
/// send it (Task A8, fill T8b).
///
/// Privacy: `label` is a staff pseudonym ("Dr. A") or a bed ("Bed 12"), never a patient and
/// never a full name; there is no health field; `speciality` is for staff tablets only
/// (`null` for bedside ones). The position is never persisted (ruling R1).
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct TabletView {
    /// Device id.
    pub device_id: DeviceId,
    /// `staff` or `bedside`.
    pub kind: TabletKind,
    /// Owner pseudonym or bed label; `""` when the tablet is free.
    pub label: String,
    /// Work information of a staff tablet ("Cardiology"); `null` for bedside tablets.
    pub speciality: Option<String>,
    /// Battery 0 to 100, reported with the location heartbeat; `null` if unknown.
    pub battery_pct: Option<u8>,
    /// Heard within the last 120 s.
    pub online: bool,
    /// `false`: nobody uses it, it is free to hand out.
    pub assigned: bool,
    /// Its room (staff), its bed's room (bedside), its shelf (free); `null` if never seen.
    pub place: Option<PlaceId>,
    /// Floor of the position; `null` without one.
    pub floor: Option<i32>,
    /// Position, metres east; `null` without one.
    pub x: Option<f64>,
    /// Position, metres south; `null` without one.
    pub y: Option<f64>,
    /// Radius of the position estimate in metres; `null` when the place was given by hand.
    pub uncertainty_m: Option<f64>,
    /// Last heartbeat; `null` if never heard from.
    pub last_seen: Option<DateTime<Utc>>,
}
