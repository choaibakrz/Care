//! Contract C2 (robots) and the application event stream (C3 `WS /ws`).
//!
//! Every server message is `{ "type": "...", "id": "uuid", "ts": "ISO-8601", ...payload }`.
//! Unknown types are reported as `ProtocolError::UnknownType`; callers log and ignore them.
//! Coordinates are metres, x grows east, y grows south (`docs/map-format.md`); a heading is
//! in radians, 0 = east, positive turns toward south.

use std::collections::BTreeMap;

use chrono::{DateTime, Utc};
use domain::{
    ClinicId, CommandName, DeviceId, FailureReason, ItemId, OwnerLabel, PlaceId, RobotId,
    RobotStatus, SecurityAlert, SeenItem, StockLevel, SystemModeState, TaskId, TaskKind, TaskState,
    TaskSummary, ZoneId, ZoneKind,
};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::error::ProtocolError;
use crate::incidents::{Incident, IncidentColour};
use crate::views::{RobotView, ScheduleView, TabletView, TaskView, ZoneView};

/// Largest accepted WebSocket message, in bytes.
pub const MAX_MESSAGE_BYTES: usize = 64 * 1024;

/// A message: id, timestamp, and a body flattened next to them with its `type` tag.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Envelope<T> {
    /// Unique message id (used for de-duplication of robot events).
    pub id: Uuid,
    /// When the sender created it.
    pub ts: DateTime<Utc>,
    /// The typed body.
    #[serde(flatten)]
    pub body: T,
}

impl<T> Envelope<T> {
    /// Wraps a body with a fresh random id.
    #[must_use]
    pub fn new(body: T, ts: DateTime<Utc>) -> Envelope<T> {
        Envelope {
            id: Uuid::new_v4(),
            ts,
            body,
        }
    }
}

/// Robot position as sent in `robot.state.pos` and in `RobotView.pos`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct RobotPose {
    /// Metres east.
    pub x: f64,
    /// Metres south.
    pub y: f64,
    /// Heading in radians: 0 = east, positive turns toward south.
    pub heading: f64,
    /// Floor level.
    pub floor: i32,
}

/// Robot to server.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum RobotUp {
    /// First message after connecting.
    #[serde(rename = "hello")]
    Hello {
        /// Must equal the path id and the token's robot.
        robot_id: RobotId,
        /// Role card name.
        role_card: String,
        /// Capability keys.
        capabilities: Vec<String>,
        /// Simulated robots never do real deliveries.
        simulated: bool,
        /// Task the robot is running, taken as the truth on reconnect.
        running_task: Option<TaskId>,
        /// The BLE identifier the robot advertises (Task 11b moving anchors).
        #[serde(default)]
        ble_id: Option<String>,
    },
    /// Every second.
    #[serde(rename = "robot.state")]
    State {
        /// Position.
        pos: RobotPose,
        /// Battery percentage (wire name `battery`).
        #[serde(rename = "battery")]
        battery_pct: f32,
        /// Status (wire name `state`).
        #[serde(rename = "state")]
        status: RobotStatus,
        /// Item carried.
        holding: Option<ItemId>,
        /// Whether the microphone is open (deaf zones close it).
        mic_open: bool,
    },
    /// A task changed state on the robot.
    #[serde(rename = "task.event")]
    TaskEvent {
        /// Task.
        task_id: TaskId,
        /// New state.
        state: TaskState,
        /// Set on failure or handover to a human.
        reason: Option<FailureReason>,
    },
    /// What the robot counted on a shelf.
    #[serde(rename = "inventory.seen")]
    InventorySeen {
        /// Shelf place.
        place: PlaceId,
        /// Items seen.
        items: Vec<SeenItem>,
    },
    /// Zone versions the robot has applied.
    #[serde(rename = "zone.ack")]
    ZoneAck {
        /// Version per zone id.
        zone_version_by_id: BTreeMap<ZoneId, u32>,
    },
}

/// A zone as sent to robots.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WireZone {
    /// Id.
    pub id: ZoneId,
    /// Kind.
    pub kind: ZoneKind,
    /// Floor.
    pub floor: i32,
    /// Vertices in metres, `[x, y]`.
    pub polygon: Vec<[f64; 2]>,
    /// Zone version.
    pub version: u32,
}

/// Server to robot.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum RobotDown {
    /// A task for this robot.
    #[serde(rename = "task.assign")]
    TaskAssign {
        /// Task.
        task_id: TaskId,
        /// Kind.
        kind: TaskKind,
        /// Item.
        item: Option<ItemId>,
        /// Origin.
        from_place: Option<PlaceId>,
        /// Destination.
        to_place: PlaceId,
        /// Deadline.
        deadline: Option<DateTime<Utc>>,
    },
    /// Cancel a task.
    #[serde(rename = "task.cancel")]
    TaskCancel {
        /// Task.
        task_id: TaskId,
    },
    /// The full zone list (an empty list removes every zone).
    #[serde(rename = "zones.update")]
    ZonesUpdate {
        /// Every zone.
        zones: Vec<WireZone>,
        /// Global zone-set version.
        version: u64,
    },
    /// The active clinic plan changed (an admin saved it or activated another one); fetch
    /// `GET /map`. Sent only for the active plan.
    #[serde(rename = "map.update")]
    MapUpdate {
        /// The active plan's tag, `<clinic id>-v<version>` (the `ETag` of `GET /map`).
        version: String,
    },
    /// A command. Only `estop` bypasses the gardien.
    #[serde(rename = "command")]
    Command {
        /// Which command.
        name: CommandName,
    },
}

/// A robot on the live map (wire form of `locations::RobotLive`).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct RobotPosition {
    /// Id.
    pub id: RobotId,
    /// Name.
    pub name: String,
    /// Status.
    pub status: RobotStatus,
    /// Current task.
    pub task: Option<TaskSummary>,
    /// Battery.
    pub battery_pct: f32,
    /// Microphone open.
    pub mic_open: bool,
    /// Floor.
    pub floor: i32,
    /// Metres east.
    pub x: f64,
    /// Metres south.
    pub y: f64,
    /// Heading (0 = east, positive toward south).
    pub heading_rad: Option<f64>,
    /// No fix for longer than the stale threshold.
    pub stale: bool,
}

/// A tablet on the live map (wire form of `locations::TabletLive`): owner label and room,
/// nothing else about the person.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TabletPosition {
    /// Device.
    pub device_id: DeviceId,
    /// Owner label.
    pub owner: OwnerLabel,
    /// Room.
    pub place: PlaceId,
    /// Floor.
    pub floor: i32,
    /// Metres east (room anchor unless the estimate is within 3 m).
    pub x: f64,
    /// Metres south.
    pub y: f64,
    /// `None` when the room was chosen by hand.
    pub uncertainty_m: Option<f64>,
}

/// All live positions.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Positions {
    /// Robots.
    pub robots: Vec<RobotPosition>,
    /// Tablets.
    pub tablets: Vec<TabletPosition>,
    /// Map version the coordinates refer to.
    pub map_version: String,
    /// When the snapshot was taken.
    pub at: DateTime<Utc>,
}

/// The robot command a `staff_command` alert is about (Task A7).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct CommandNotice {
    /// The command's id (`CommandReceipt.command_id`).
    pub command_id: Uuid,
    /// The robot.
    pub robot_id: RobotId,
    /// The command (`pause`, `resume`, `dock`; `shutdown` is admin only since ruling R24, so
    /// a non-admin's shutdown never reaches a robot or this alert).
    pub command: CommandName,
    /// Who sent it: the owner label (`"<pseudonym> #<tag>"`).
    pub by: OwnerLabel,
    /// Whether the command has an inverse the admin could send (`pause`, `resume`, `dock`:
    /// yes, so `true` for every alert today; `false` is kept for a command without one).
    /// The revert can still be refused when asked: only while it is the robot's latest
    /// command (409 `superseded`), never while the robot is in emergency stop (409
    /// `estop_latched`), once only (409 `already_reverted`).
    pub revertible: bool,
}

/// How urgent an alert is (the admin console's three levels).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AlertLevel {
    /// For information.
    Info,
    /// Needs attention.
    Warning,
    /// Needs action now.
    Critical,
}

/// Kinds of alert shown to the apps.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AlertKind {
    /// A robot went silent.
    RobotOffline,
    /// A robot reported a fault.
    RobotFault,
    /// An emergency stop could not be delivered.
    EstopNotDelivered,
    /// A shelf count differs from the ledger.
    StockMismatch,
    /// A schedule run was missed.
    ScheduleMissed,
    /// Actions are paused because the journal cannot write.
    JournalUnavailable,
    /// A journal anchor could not be written.
    AnchorFailed,
    /// No robot can do a task; a human must.
    TaskNeedsHuman,
    /// A journal seal was written (admin panel anchor).
    JournalSealed,
    /// A non-admin sent a robot command (pause, resume, dock, shutdown; Task A7). The alert
    /// carries the command (`command`), so the admin can revert it.
    StaffCommand,
    /// Emergency mode was switched on (Task A8): only emergency actions are accepted, the
    /// robots go to their docks.
    EmergencyModeOn,
    /// Emergency mode was switched off (Task A8).
    EmergencyModeOff,
    /// A robot refused a command the server sent on its own (Task A8: clearing the corridors
    /// for emergency mode). The server does not retry; the refusal is journaled.
    CommandRefused,
}

impl AlertKind {
    /// The fixed level of each kind: `estop_not_delivered`, `journal_unavailable`,
    /// `anchor_failed` and `emergency_mode_on` are `critical`; `robot_offline`, `robot_fault`,
    /// `stock_mismatch`, `schedule_missed`, `task_needs_human`, `staff_command` and
    /// `command_refused` are `warning`; `journal_sealed` and `emergency_mode_off` are `info`.
    #[must_use]
    pub fn level(self) -> AlertLevel {
        match self {
            AlertKind::EstopNotDelivered
            | AlertKind::JournalUnavailable
            | AlertKind::AnchorFailed
            | AlertKind::EmergencyModeOn => AlertLevel::Critical,
            AlertKind::RobotOffline
            | AlertKind::RobotFault
            | AlertKind::StockMismatch
            | AlertKind::ScheduleMissed
            | AlertKind::TaskNeedsHuman
            | AlertKind::StaffCommand
            | AlertKind::CommandRefused => AlertLevel::Warning,
            AlertKind::JournalSealed | AlertKind::EmergencyModeOff => AlertLevel::Info,
        }
    }
}

/// Application to server on `WS /ws`. One message exists: the first one, which
/// authenticates the connection (the token never travels in the URL). No `Debug`: the token
/// must never be printed.
#[derive(Clone, PartialEq, Eq, Deserialize)]
#[serde(tag = "type")]
pub enum AppUp {
    /// `{"type":"auth","token":"…"}`, within [`APP_AUTH_TIMEOUT_S`] seconds of opening.
    #[serde(rename = "auth")]
    Auth {
        /// The bearer token from `POST /auth/login`.
        token: String,
    },
}

/// Seconds an application has to send its `auth` message after the socket opens.
pub const APP_AUTH_TIMEOUT_S: u64 = 5;

/// Close code sent when the `auth` message is missing, late, malformed or its token is
/// refused (4401, mirroring HTTP 401). The close reason says which, in plain words.
pub const APP_AUTH_CLOSE_CODE: u16 = 4401;

/// Server to applications (`WS /ws`). The admin console reads `robot.updated`,
/// `task.updated`, `inventory.updated`, `zone.updated`, `zone.deleted`, `schedule.updated`,
/// `map.updated` and `alert`, and ignores the others.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "type")]
pub enum AppEvent {
    /// First message after authentication, and after `resync`.
    #[serde(rename = "snapshot")]
    Snapshot {
        /// Unfinished tasks.
        tasks: Vec<TaskView>,
        /// Live positions.
        positions: Positions,
        /// Emergency mode or not (Task A8; the same object as `GET /system/mode`). Absent
        /// only when the mode could not be read.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        mode: Option<SystemModeState>,
    },
    /// A task changed.
    #[serde(rename = "task.updated")]
    TaskUpdated {
        /// The task.
        task: TaskView,
    },
    /// A robot's state, sent on every change and at least once per second per connected
    /// robot (heartbeat), so the console can grey a robot silent for 5 s.
    #[serde(rename = "robot.updated")]
    RobotUpdated {
        /// The robot.
        robot: RobotView,
    },
    /// Positions that changed since the last delta (every 200 ms, coalesced).
    #[serde(rename = "positions.delta")]
    PositionsDelta {
        /// Changed robots.
        robots: Vec<RobotPosition>,
        /// Changed tablets.
        tablets: Vec<TabletPosition>,
        /// Tablets that expired.
        removed_tablets: Vec<DeviceId>,
    },
    /// Stock changed.
    #[serde(rename = "inventory.updated")]
    InventoryUpdated {
        /// The item, as `GET /inventory` lists it.
        item: StockLevel,
    },
    /// A zone was created or changed.
    #[serde(rename = "zone.updated")]
    ZoneUpdated {
        /// The zone, as `GET /zones` lists it.
        zone: ZoneView,
    },
    /// A zone was deleted.
    #[serde(rename = "zone.deleted")]
    ZoneDeleted {
        /// Its id.
        zone_id: ZoneId,
    },
    /// A schedule changed or ran.
    #[serde(rename = "schedule.updated")]
    ScheduleUpdated {
        /// The schedule, as `GET /schedules` lists it.
        schedule: ScheduleView,
    },
    /// Something needs attention.
    #[serde(rename = "alert")]
    Alert {
        /// Level, from `AlertKind::level`.
        level: AlertLevel,
        /// Kind (extra field).
        kind: AlertKind,
        /// Human message, safe to show.
        message: String,
        /// The robot command this alert is about (`staff_command` only, Task A7): what
        /// `POST /robots/{id}/commands/{command_id}/revert` names. Absent on other alerts.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        command: Option<CommandNotice>,
    },
    /// A clinic plan was created, saved, activated or deleted (Task A4). When `active` is
    /// true the map the console draws changed: reload `GET /map`.
    #[serde(rename = "map.updated")]
    MapUpdated {
        /// Which plan.
        clinic_id: ClinicId,
        /// Its version after the change (the last version for a deleted plan).
        version: u64,
        /// Whether it is the active plan (what `GET /map` serves) after the change.
        active: bool,
    },
    /// The client fell behind; a fresh snapshot follows.
    #[serde(rename = "resync")]
    Resync,
    /// Emergency mode was switched on or off (Task A8), sent to every app on each switch.
    #[serde(rename = "mode.updated")]
    ModeUpdated {
        /// The new mode, as `GET /system/mode` answers it.
        mode: SystemModeState,
    },
    /// A tablet was assigned, freed, went online or offline, or reported a battery change
    /// (at most every 10 s per tablet; Task A8).
    #[serde(rename = "device.updated")]
    DeviceUpdated {
        /// The full tablet object, as `GET /devices` lists it.
        device: TabletView,
    },
    /// Something happened to the server's defences (Task A8). Sent to **admin** sockets only
    /// ([`AppEvent::admin_only`]); at most one `rate_limited` per address per minute.
    #[serde(rename = "security.alert")]
    SecurityAlert {
        /// The alert.
        alert: SecurityAlert,
    },
    /// An incident was raised, updated or closed.
    #[serde(rename = "incident.updated")]
    IncidentUpdated {
        /// The incident.
        incident: Incident,
        /// Map colour.
        colour: IncidentColour,
    },
}

impl AppEvent {
    /// Whether only admin sockets may receive this event (`security.alert`).
    #[must_use]
    pub fn admin_only(&self) -> bool {
        matches!(self, AppEvent::SecurityAlert { .. })
    }
}

/// Decodes one robot message.
///
/// # Errors
/// `TooLarge` above [`MAX_MESSAGE_BYTES`]; `UnknownType` for a `type` not in C2 (log and
/// ignore); `MissingField`; `Malformed` for anything else.
pub fn decode_robot_up(bytes: &[u8]) -> Result<Envelope<RobotUp>, ProtocolError> {
    let envelope: Envelope<RobotUp> = decode_checked(bytes, ROBOT_UP_TYPES)?;
    validate_robot_up(&envelope.body)?;
    Ok(envelope)
}

/// The `type` values of [`RobotUp`].
const ROBOT_UP_TYPES: &[&str] = &[
    "hello",
    "robot.state",
    "task.event",
    "inventory.seen",
    "zone.ack",
];

/// The `type` values of [`RobotDown`].
const ROBOT_DOWN_TYPES: &[&str] = &[
    "task.assign",
    "task.cancel",
    "zones.update",
    "map.update",
    "command",
];

/// Size check, `type` check, then a typed decode with the errors mapped to [`ProtocolError`].
fn decode_checked<T: serde::de::DeserializeOwned>(
    bytes: &[u8],
    known_types: &[&str],
) -> Result<Envelope<T>, ProtocolError> {
    if bytes.len() > MAX_MESSAGE_BYTES {
        return Err(ProtocolError::TooLarge {
            size: bytes.len(),
            max: MAX_MESSAGE_BYTES,
        });
    }
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|e| ProtocolError::Malformed {
            reason: e.to_string(),
        })?;
    let object = value.as_object().ok_or_else(|| ProtocolError::Malformed {
        reason: "the message is not a JSON object".to_owned(),
    })?;
    let type_name = match object.get("type") {
        None => {
            return Err(ProtocolError::MissingField {
                field: "type".to_owned(),
            });
        }
        Some(serde_json::Value::String(name)) => name.as_str(),
        Some(_) => {
            return Err(ProtocolError::Malformed {
                reason: "the field 'type' is not a string".to_owned(),
            });
        }
    };
    if !known_types.contains(&type_name) {
        return Err(ProtocolError::UnknownType {
            type_name: type_name.to_owned(),
        });
    }
    serde_json::from_value(value).map_err(|e| map_serde_error(&e))
}

/// Turns a serde error into `MissingField` when it names a missing field, else `Malformed`.
fn map_serde_error(error: &serde_json::Error) -> ProtocolError {
    let text = error.to_string();
    if let Some(rest) = text.strip_prefix("missing field `")
        && let Some((field, _)) = rest.split_once('`')
    {
        return ProtocolError::MissingField {
            field: field.to_owned(),
        };
    }
    ProtocolError::Malformed { reason: text }
}

/// Values that parse but cannot be true: a battery is a percentage, a position is finite.
fn validate_robot_up(body: &RobotUp) -> Result<(), ProtocolError> {
    if let RobotUp::State {
        pos, battery_pct, ..
    } = body
    {
        if !battery_pct.is_finite() || !(0.0..=100.0).contains(battery_pct) {
            return Err(ProtocolError::Malformed {
                reason: format!("battery {battery_pct} is not a percentage between 0 and 100"),
            });
        }
        if !(pos.x.is_finite() && pos.y.is_finite() && pos.heading.is_finite()) {
            return Err(ProtocolError::Malformed {
                reason: "the position holds a value that is not a finite number".to_owned(),
            });
        }
    }
    Ok(())
}

/// Decodes one server-to-robot message (used by the fake robot and tests).
///
/// # Errors
/// Same as [`decode_robot_up`].
pub fn decode_robot_down(bytes: &[u8]) -> Result<Envelope<RobotDown>, ProtocolError> {
    decode_checked(bytes, ROBOT_DOWN_TYPES)
}

/// Encodes a message as JSON text.
///
/// # Errors
/// `Malformed` when serialisation fails; `TooLarge` above [`MAX_MESSAGE_BYTES`].
pub fn encode<T: Serialize>(envelope: &Envelope<T>) -> Result<String, ProtocolError> {
    let text = serde_json::to_string(envelope).map_err(|e| ProtocolError::Malformed {
        reason: e.to_string(),
    })?;
    if text.len() > MAX_MESSAGE_BYTES {
        return Err(ProtocolError::TooLarge {
            size: text.len(),
            max: MAX_MESSAGE_BYTES,
        });
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use chrono::{TimeZone, Utc};
    use uuid::Uuid;

    use chrono::DateTime;
    use domain::{OwnerLabel, RobotStatus};

    use super::{
        AlertKind, AlertLevel, AppEvent, AppUp, Envelope, MAX_MESSAGE_BYTES, Positions, RobotDown,
        RobotPose, RobotPosition, RobotUp, TabletPosition, decode_robot_down, decode_robot_up,
        encode,
    };
    use crate::error::ProtocolError;
    use crate::incidents::{Incident, IncidentCode, IncidentColour, IncidentId, IncidentSeverity};
    use crate::views::{RobotView, ScheduleView, TaskHistoryEntry, TaskView, ZoneView};
    use crate::zone_delivery::{DeliveryState, ZoneDeliveryEntry};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    const ID: &str = "00000000-0000-4000-8000-000000000001";
    const TS: &str = "2026-11-14T08:00:00Z";

    #[test]
    fn hello_roundtrips_json() -> TestResult {
        let hello = Envelope {
            id: Uuid::parse_str(ID)?,
            ts: Utc
                .with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
                .single()
                .ok_or("bad test date")?,
            body: RobotUp::Hello {
                robot_id: "robot-r2".parse()?,
                role_card: "porteur".to_owned(),
                capabilities: vec!["carry".to_owned()],
                simulated: true,
                running_task: None,
                ble_id: None,
            },
        };
        let json = serde_json::to_string(&hello)?;
        let value: serde_json::Value = serde_json::from_str(&json)?;
        assert_eq!(value.get("type"), Some(&serde_json::json!("hello")));
        let back = decode_robot_up(json.as_bytes())?;
        assert_eq!(back, hello);
        Ok(())
    }

    #[test]
    fn decode_rejects_message_over_64kib_with_sizes_in_message() -> TestResult {
        let bytes = vec![b' '; MAX_MESSAGE_BYTES + 1];
        let err = decode_robot_up(&bytes)
            .err()
            .ok_or("an oversized message was accepted")?;
        assert_eq!(
            err,
            ProtocolError::TooLarge {
                size: 65_537,
                max: 65_536
            }
        );
        let message = err.to_string();
        assert!(message.contains("65537"), "{message}");
        assert!(message.contains("65536"), "{message}");
        Ok(())
    }

    #[test]
    fn decode_unknown_type_returns_unknown_type_not_malformed() -> TestResult {
        let json = format!(r#"{{"type":"robot.dance","id":"{ID}","ts":"{TS}"}}"#);
        let err = decode_robot_up(json.as_bytes())
            .err()
            .ok_or("an unknown type was accepted")?;
        assert_eq!(
            err,
            ProtocolError::UnknownType {
                type_name: "robot.dance".to_owned()
            }
        );
        Ok(())
    }

    #[test]
    fn decode_missing_task_id_names_the_field() -> TestResult {
        let json = format!(
            r#"{{"type":"task.event","id":"{ID}","ts":"{TS}","state":"delivered","reason":null}}"#
        );
        let err = decode_robot_up(json.as_bytes())
            .err()
            .ok_or("a task event without task_id was accepted")?;
        assert_eq!(
            err,
            ProtocolError::MissingField {
                field: "task_id".to_owned()
            }
        );
        assert!(err.to_string().contains("task_id"));
        Ok(())
    }

    #[test]
    fn state_with_nan_battery_is_rejected() -> TestResult {
        let state = |battery: &str| {
            format!(
                r#"{{"type":"robot.state","id":"{ID}","ts":"{TS}","pos":{{"x":1.0,"y":2.0,"heading":0.0,"floor":1}},"battery":{battery},"state":"idle","holding":null,"mic_open":true}}"#
            )
        };
        let nan = decode_robot_up(state("NaN").as_bytes())
            .err()
            .ok_or("a NaN battery was accepted")?;
        assert!(matches!(nan, ProtocolError::Malformed { .. }), "{nan:?}");
        // Valid JSON, impossible values: a battery is a percentage.
        for battery in ["150.0", "-1.0"] {
            let err = decode_robot_up(state(battery).as_bytes())
                .err()
                .ok_or_else(|| format!("battery {battery} was accepted"))?;
            assert!(matches!(err, ProtocolError::Malformed { .. }), "{err:?}");
        }
        assert!(decode_robot_up(state("80.0").as_bytes()).is_ok());
        Ok(())
    }

    // ----- the examples of docs/ws_messages.md -----

    const DOC: &str = include_str!("../../../docs/ws_messages.md");

    // The fenced blocks opened with "```json <tag>", each one JSON document.
    fn doc_examples(tag: &str) -> Vec<serde_json::Value> {
        let opener = format!("```json {tag}");
        let mut found = Vec::new();
        let mut current: Option<String> = None;
        for line in DOC.lines() {
            match current.as_mut() {
                None if line.trim_end() == opener => current = Some(String::new()),
                None => {}
                Some(_) if line.trim_end() == "```" => {
                    if let Some(text) = current.take()
                        && let Ok(value) = serde_json::from_str(&text)
                    {
                        found.push(value);
                    }
                }
                Some(text) => {
                    text.push_str(line);
                    text.push('\n');
                }
            }
        }
        found
    }

    fn type_of(value: &serde_json::Value) -> String {
        value
            .get("type")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default()
            .to_owned()
    }

    #[test]
    fn every_robot_up_example_in_the_doc_decodes_and_reencodes_identically() -> TestResult {
        let examples = doc_examples("up");
        let mut seen: Vec<String> = examples.iter().map(type_of).collect();
        seen.sort();
        assert_eq!(
            seen,
            [
                "hello",
                "inventory.seen",
                "robot.state",
                "task.event",
                "zone.ack"
            ]
        );
        for example in examples {
            let decoded = decode_robot_up(example.to_string().as_bytes())?;
            let again: serde_json::Value = serde_json::from_str(&encode(&decoded)?)?;
            assert_eq!(again, example);
        }
        Ok(())
    }

    #[test]
    fn every_robot_down_example_in_the_doc_decodes_and_reencodes_identically() -> TestResult {
        let examples = doc_examples("down");
        let mut seen: Vec<String> = examples.iter().map(type_of).collect();
        seen.sort();
        assert_eq!(
            seen,
            [
                "command",
                "map.update",
                "task.assign",
                "task.cancel",
                "zones.update"
            ]
        );
        for example in examples {
            let decoded = decode_robot_down(example.to_string().as_bytes())?;
            let again: serde_json::Value = serde_json::from_str(&encode(&decoded)?)?;
            assert_eq!(again, example);
        }
        Ok(())
    }

    #[test]
    fn the_auth_example_in_the_doc_decodes() -> TestResult {
        let examples = doc_examples("auth");
        assert_eq!(examples.len(), 1);
        for example in examples {
            let AppUp::Auth { token } = serde_json::from_value(example)?;
            assert!(!token.is_empty());
        }
        Ok(())
    }

    fn at() -> Result<DateTime<Utc>, Box<dyn std::error::Error>> {
        Ok(TS.parse()?)
    }

    fn pose() -> RobotPose {
        RobotPose {
            x: 12.0,
            y: 4.0,
            heading: 0.0,
            floor: 1,
        }
    }

    #[allow(clippy::too_many_lines)] // one literal sample per AppEvent variant
    fn sample_events() -> Result<Vec<AppEvent>, Box<dyn std::error::Error>> {
        let t = at()?;
        let task = TaskView {
            id: "t-17".parse()?,
            kind: domain::TaskKind::Fetch,
            item: Some("blanket".parse()?),
            from_place: Some("reserve".parse()?),
            to_place: "room-101".parse()?,
            state: domain::TaskState::EnRoute,
            robot_id: Some("robot-r2".parse()?),
            requested_by: "Nurse A".to_owned(),
            created_at: t,
            updated_at: t,
            reason: None,
            history: vec![TaskHistoryEntry {
                at: t,
                actor: "server".to_owned(),
                label: "requested".to_owned(),
            }],
            target_device: None,
            target_label: None,
            until: None,
        };
        let robot_position = RobotPosition {
            id: "robot-r2".parse()?,
            name: "R2".to_owned(),
            status: RobotStatus::Busy,
            task: Some(domain::TaskSummary {
                id: "t-17".parse()?,
                kind: domain::TaskKind::Fetch,
            }),
            battery_pct: 81.0,
            mic_open: false,
            floor: 1,
            x: 12.0,
            y: 4.0,
            heading_rad: Some(0.0),
            stale: false,
        };
        let tablet = TabletPosition {
            device_id: "tablet-1".parse()?,
            owner: OwnerLabel::new("Nurse A")?,
            place: "room-101".parse()?,
            floor: 1,
            x: 20.0,
            y: 8.0,
            uncertainty_m: Some(2.5),
        };
        Ok(vec![
            AppEvent::Snapshot {
                tasks: vec![task.clone()],
                positions: Positions {
                    robots: vec![robot_position.clone()],
                    tablets: vec![tablet.clone()],
                    map_version: "seed-v2".to_owned(),
                    at: t,
                },
                mode: Some(domain::SystemModeState::initial()),
            },
            AppEvent::TaskUpdated { task },
            AppEvent::RobotUpdated {
                robot: RobotView {
                    id: "robot-r2".parse()?,
                    name: "R2".to_owned(),
                    role: "porteur".to_owned(),
                    simulated: true,
                    pos: pose(),
                    battery: Some(81.0),
                    state: RobotStatus::Busy,
                    holding: Some("blanket".parse()?),
                    mic_open: false,
                    task_id: Some("t-17".parse()?),
                    last_seen: Some(t),
                    connected: true,
                    in_deaf_zone: false,
                    going_home: false,
                    mood: crate::views::RobotMood::Busy,
                },
            },
            AppEvent::PositionsDelta {
                robots: vec![robot_position],
                tablets: vec![tablet],
                removed_tablets: vec!["tablet-2".parse()?],
            },
            AppEvent::InventoryUpdated {
                item: domain::StockLevel {
                    item: "blanket".parse()?,
                    label: "Blanket".to_owned(),
                    place: "reserve".parse()?,
                    count: 7,
                    low_threshold: 3,
                    last_robot_count: Some(7),
                    last_robot_count_at: Some(t),
                    updated_at: t,
                },
            },
            AppEvent::ZoneUpdated {
                zone: ZoneView {
                    id: "z-deaf-101".parse()?,
                    name: "Room 101 (deaf)".to_owned(),
                    floor: 1,
                    kind: domain::ZoneKind::Deaf,
                    polygon: vec![[0.0, 0.0], [5.0, 0.0], [5.0, 4.0]],
                    deliveries: vec![ZoneDeliveryEntry {
                        robot_id: "robot-r2".parse()?,
                        status: DeliveryState::Received,
                        acked_version: Some(3),
                        robot_online: true,
                    }],
                    enforced_by_gardien: true,
                    version: 3,
                },
            },
            AppEvent::ZoneDeleted {
                zone_id: "z-deaf-101".parse()?,
            },
            AppEvent::ScheduleUpdated {
                schedule: ScheduleView {
                    id: "night-restock".parse()?,
                    label: "Night restock round".to_owned(),
                    enabled: true,
                    time: "02:30".to_owned(),
                    robot_id: None,
                    last_run: Some(t),
                    last_result: domain::RoundResult::Success,
                    last_counts: vec![domain::ShelfCount {
                        place: "reserve".parse()?,
                        item: "blanket".parse()?,
                        expected: 8,
                        counted: 7,
                    }],
                    timezone: "Europe/Zurich".to_owned(),
                    next_run: Some(t),
                },
            },
            AppEvent::Alert {
                level: AlertKind::RobotOffline.level(),
                kind: AlertKind::RobotOffline,
                message: "Robot robot-r2 has been silent for 5 s.".to_owned(),
                command: None,
            },
            AppEvent::MapUpdated {
                clinic_id: "seed".parse()?,
                version: 2,
                active: true,
            },
            AppEvent::Resync,
            AppEvent::ModeUpdated {
                mode: domain::SystemModeState {
                    mode: domain::SystemMode::Emergency,
                    since: Some(t),
                    by: Some("Admin A".to_owned()),
                    reason: Some("Fire alarm, wing B".to_owned()),
                },
            },
            AppEvent::DeviceUpdated {
                device: crate::views::TabletView {
                    device_id: "tab-spare-1".parse()?,
                    kind: crate::views::TabletKind::Staff,
                    label: String::new(),
                    speciality: None,
                    battery_pct: Some(100),
                    online: true,
                    assigned: false,
                    place: Some("nurse-station".parse()?),
                    floor: Some(2),
                    x: Some(4.6),
                    y: Some(9.5),
                    uncertainty_m: None,
                    last_seen: Some(t),
                },
            },
            AppEvent::SecurityAlert {
                alert: domain::SecurityAlert {
                    at: t,
                    kind: domain::SecurityAlertKind::AutoBlocked,
                    ip: "203.0.113.42".to_owned(),
                    message:
                        "203.0.113.42 blocked automatically for 10 min: over 20 requests/s for 5 s."
                            .to_owned(),
                },
            },
            AppEvent::IncidentUpdated {
                incident: Incident {
                    id: IncidentId(4),
                    code: IncidentCode::RobotOffline,
                    severity: IncidentSeverity::Warning,
                    subject: None,
                    place: Some("room-101".parse()?),
                    floor: Some(1),
                    opened_at: t,
                    last_seen_at: t,
                    repeats: 0,
                    acknowledged_by: None,
                    closed_at: None,
                },
                colour: IncidentColour::Orange,
            },
        ])
    }

    #[test]
    fn every_app_event_example_in_the_doc_equals_what_the_server_encodes() -> TestResult {
        let id = Uuid::parse_str(ID)?;
        let ts = at()?;
        let examples = doc_examples("app");
        let events = sample_events()?;
        let mut encoded = Vec::new();
        for event in events {
            let text = encode(&Envelope {
                id,
                ts,
                body: event,
            })?;
            encoded.push(serde_json::from_str::<serde_json::Value>(&text)?);
        }
        assert_eq!(
            examples.len(),
            encoded.len(),
            "one doc example per AppEvent"
        );
        for value in encoded {
            let documented = examples
                .iter()
                .find(|example| type_of(example) == type_of(&value))
                .ok_or_else(|| format!("no doc example for {}", type_of(&value)))?;
            assert_eq!(documented, &value, "doc example of {}", type_of(&value));
        }
        Ok(())
    }

    #[test]
    fn app_event_json_matches_what_the_console_reads() -> TestResult {
        let value = serde_json::to_value(Envelope {
            id: Uuid::parse_str(ID)?,
            ts: at()?,
            body: AppEvent::ZoneDeleted {
                zone_id: "z-1".parse()?,
            },
        })?;
        assert_eq!(value.get("type"), Some(&serde_json::json!("zone.deleted")));
        assert_eq!(value.get("zone_id"), Some(&serde_json::json!("z-1")));
        assert!(value.get("id").is_some() && value.get("ts").is_some());
        Ok(())
    }

    #[test]
    fn only_security_alerts_are_admin_only() -> TestResult {
        for event in sample_events()? {
            assert_eq!(
                event.admin_only(),
                matches!(event, AppEvent::SecurityAlert { .. }),
                "{event:?}"
            );
        }
        Ok(())
    }

    #[test]
    fn alert_levels_follow_the_fixed_table() {
        assert_eq!(AlertKind::EmergencyModeOn.level(), AlertLevel::Critical);
        assert_eq!(AlertKind::EmergencyModeOff.level(), AlertLevel::Info);
        assert_eq!(AlertKind::CommandRefused.level(), AlertLevel::Warning);
        assert_eq!(AlertKind::EstopNotDelivered.level(), AlertLevel::Critical);
        assert_eq!(AlertKind::JournalUnavailable.level(), AlertLevel::Critical);
        assert_eq!(AlertKind::AnchorFailed.level(), AlertLevel::Critical);
        assert_eq!(AlertKind::RobotOffline.level(), AlertLevel::Warning);
        assert_eq!(AlertKind::TaskNeedsHuman.level(), AlertLevel::Warning);
        assert_eq!(AlertKind::JournalSealed.level(), AlertLevel::Info);
    }

    #[test]
    fn encode_rejects_a_message_over_the_limit() -> TestResult {
        let envelope = Envelope::new(
            RobotUp::Hello {
                robot_id: "robot-r2".parse()?,
                role_card: "x".repeat(MAX_MESSAGE_BYTES),
                capabilities: Vec::new(),
                simulated: true,
                running_task: None,
                ble_id: None,
            },
            at()?,
        );
        let err = encode(&envelope)
            .err()
            .ok_or("an oversized message was encoded")?;
        assert!(matches!(err, ProtocolError::TooLarge { .. }), "{err:?}");
        Ok(())
    }

    #[test]
    fn envelope_new_gives_each_message_a_fresh_id() -> TestResult {
        let cancel = || -> Result<RobotDown, Box<dyn std::error::Error>> {
            Ok(RobotDown::TaskCancel {
                task_id: "t-1".parse()?,
            })
        };
        let a = Envelope::new(cancel()?, at()?);
        let b = Envelope::new(cancel()?, at()?);
        assert_ne!(a.id, b.id);
        assert_eq!(a.ts, at()?);
        Ok(())
    }

    #[test]
    fn a_robot_down_type_sent_up_is_unknown_not_fatal() -> TestResult {
        let json = format!(r#"{{"type":"task.cancel","id":"{ID}","ts":"{TS}","task_id":"t-1"}}"#);
        let err = decode_robot_up(json.as_bytes()).err().ok_or("accepted")?;
        assert!(matches!(err, ProtocolError::UnknownType { .. }), "{err:?}");
        Ok(())
    }

    #[test]
    fn garbage_is_malformed() {
        for bytes in [&b"not json"[..], b"[1,2]", b"{\"id\":1}"] {
            assert!(decode_robot_up(bytes).is_err());
        }
    }

    /// Task A7: a `staff_command` alert carries the command; other alerts have no `command`
    /// key (their JSON is unchanged).
    #[test]
    fn staff_command_alert_carries_the_command_and_others_do_not() -> TestResult {
        let id = Uuid::parse_str(ID)?;
        let alert = AppEvent::Alert {
            level: AlertKind::StaffCommand.level(),
            kind: AlertKind::StaffCommand,
            message: "Nurse 7 #3fa9c1 sent pause to robot r1.".to_owned(),
            command: Some(super::CommandNotice {
                command_id: id,
                robot_id: "r1".parse()?,
                command: domain::CommandName::Pause,
                by: OwnerLabel::new("Nurse 7 #3fa9c1")?,
                revertible: true,
            }),
        };
        let value = serde_json::to_value(&alert)?;
        assert_eq!(value.get("kind"), Some(&serde_json::json!("staff_command")));
        assert_eq!(value.get("level"), Some(&serde_json::json!("warning")));
        assert_eq!(
            value.pointer("/command/command_id"),
            Some(&serde_json::json!(ID))
        );
        let plain = serde_json::to_value(AppEvent::Alert {
            level: AlertKind::RobotOffline.level(),
            kind: AlertKind::RobotOffline,
            message: "x".to_owned(),
            command: None,
        })?;
        assert!(plain.get("command").is_none(), "{plain}");
        Ok(())
    }
}
