//! A small invented clinic shared by the test suites (`"marque": "inventé"`), as a clinic
//! plan: the only description of a clinic (ruling R14); the model (`ClinicMap`) is derived with
//! `ClinicPlan::validate`.
//!
//! Two floors, joined only by the explicit connection `lift-1` <-> `lift-2` (4 m). Floor 1 has
//! a corridor (`corridor-1`) with the storeroom, the dock, four rooms and the lift around it;
//! floor 2 has `corridor-2`, `room-201` and `lift-2`. Rooms are the place footprints, walls are
//! two-point segments (ids `<floor>-w<index>`, door gaps between them), places are the anchors.
//! Every room lies strictly inside the floor outline (-1..31 x -1..21). Same-floor links are
//! derived (Task 10b: straight lines; Task 13b: planning-grid routes).
//!
//! Included with `#[path]` by the root tests (`tests/support/mod.rs`) and by the
//! `locations` and `optimization` integration tests, so it depends only on `locations`,
//! `domain` and `serde_json`.
#![allow(dead_code)]

use locations::{ClinicMap, ClinicPlan, Polygon, Zone};
use serde_json::{Value, json};

/// Error of the fixture builders: the text of the underlying error. A concrete type, so `?`
/// converts it into the boxed errors of every test crate (with or without `Send + Sync`).
#[derive(Debug)]
pub struct MapError(String);

impl std::fmt::Display for MapError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for MapError {}

impl From<serde_json::Error> for MapError {
    fn from(error: serde_json::Error) -> MapError {
        MapError(error.to_string())
    }
}

impl From<locations::PlanErrors> for MapError {
    fn from(error: locations::PlanErrors) -> MapError {
        MapError(format!("{error}: {:?}", error.0))
    }
}

impl From<locations::LocationError> for MapError {
    fn from(error: locations::LocationError) -> MapError {
        MapError(error.to_string())
    }
}

impl From<domain::DomainError> for MapError {
    fn from(error: domain::DomainError) -> MapError {
        MapError(error.to_string())
    }
}

/// Place ids of the fixture.
pub const STOREROOM: &str = "storeroom";
/// The dock.
pub const DOCK: &str = "dock";
/// Floor 1 corridor.
pub const CORRIDOR_1: &str = "corridor-1";
/// Rooms on floor 1.
pub const ROOM_101: &str = "room-101";
/// Room 102.
pub const ROOM_102: &str = "room-102";
/// Room 103 (north of the corridor: y grows south).
pub const ROOM_103: &str = "room-103";
/// Room 104.
pub const ROOM_104: &str = "room-104";
/// Lift on floor 1.
pub const LIFT_1: &str = "lift-1";
/// Lift on floor 2.
pub const LIFT_2: &str = "lift-2";
/// Floor 2 corridor.
pub const CORRIDOR_2: &str = "corridor-2";
/// Room on floor 2.
pub const ROOM_201: &str = "room-201";
/// The deaf zone over room 101.
pub const DEAF_ZONE: &str = "z-deaf-101";

fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Value {
    json!([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
}

/// `(id, label, place kind, room kind, floor, footprint corners, anchor)` of every place.
type PlaceRow = (
    &'static str,
    &'static str,
    &'static str,
    &'static str,
    i32,
    [f64; 4],
    [f64; 2],
);

const PLACES: [PlaceRow; 11] = [
    (
        STOREROOM,
        "Réserve",
        "shelf",
        "storage",
        1,
        [0.0, 0.0, 10.0, 8.0],
        [5.0, 4.0],
    ),
    (
        DOCK,
        "Dock",
        "dock",
        "room",
        1,
        [10.0, 0.0, 14.0, 8.0],
        [12.0, 4.0],
    ),
    (
        ROOM_103,
        "Chambre 103",
        "room",
        "room",
        1,
        [14.0, 0.0, 26.0, 8.0],
        [20.0, 4.0],
    ),
    (
        LIFT_1,
        "Ascenseur 1",
        "point",
        "elevator",
        1,
        [26.0, 0.0, 30.0, 8.0],
        [28.0, 4.0],
    ),
    (
        CORRIDOR_1,
        "Couloir 1",
        "point",
        "corridor",
        1,
        [0.0, 8.0, 30.0, 12.0],
        [15.0, 10.0],
    ),
    (
        ROOM_101,
        "Chambre 101",
        "room",
        "room",
        1,
        [0.0, 12.0, 10.0, 20.0],
        [5.0, 16.0],
    ),
    (
        ROOM_102,
        "Chambre 102",
        "room",
        "room",
        1,
        [10.0, 12.0, 20.0, 20.0],
        [15.0, 16.0],
    ),
    (
        ROOM_104,
        "Chambre 104",
        "room",
        "room",
        1,
        [20.0, 12.0, 30.0, 20.0],
        [25.0, 16.0],
    ),
    (
        LIFT_2,
        "Ascenseur 2",
        "point",
        "elevator",
        2,
        [26.0, 0.0, 30.0, 8.0],
        [28.0, 4.0],
    ),
    (
        CORRIDOR_2,
        "Couloir 2",
        "point",
        "corridor",
        2,
        [0.0, 8.0, 30.0, 12.0],
        [15.0, 10.0],
    ),
    (
        ROOM_201,
        "Chambre 201",
        "room",
        "room",
        2,
        [0.0, 12.0, 10.0, 20.0],
        [5.0, 16.0],
    ),
];

/// The walls of the fixture, per floor, as `[x0, y0, x1, y1]` (the same as the model file).
const WALLS: [(i32, [f64; 4]); 20] = [
    (1, [10.0, 12.0, 10.0, 20.0]),
    (1, [20.0, 12.0, 20.0, 20.0]),
    (1, [0.0, 12.0, 4.0, 12.0]),
    (1, [6.0, 12.0, 14.0, 12.0]),
    (1, [16.0, 12.0, 24.0, 12.0]),
    (1, [26.0, 12.0, 30.0, 12.0]),
    (1, [0.0, 8.0, 4.0, 8.0]),
    (1, [6.0, 8.0, 11.0, 8.0]),
    (1, [13.0, 8.0, 19.0, 8.0]),
    (1, [21.0, 8.0, 27.0, 8.0]),
    (1, [29.0, 8.0, 30.0, 8.0]),
    (1, [10.0, 0.0, 10.0, 8.0]),
    (1, [14.0, 0.0, 14.0, 8.0]),
    (1, [26.0, 0.0, 26.0, 8.0]),
    (2, [10.0, 12.0, 10.0, 20.0]),
    (2, [0.0, 12.0, 4.0, 12.0]),
    (2, [6.0, 12.0, 30.0, 12.0]),
    (2, [0.0, 8.0, 27.0, 8.0]),
    (2, [29.0, 8.0, 30.0, 8.0]),
    (2, [26.0, 0.0, 26.0, 8.0]),
];

/// The fixture clinic as a clinic plan document (`ClinicPlan` JSON, `"marque": "inventé"`),
/// with the lift connection.
#[must_use]
pub fn small_plan_json() -> Value {
    small_plan_json_with(true)
}

/// The same clinic without the lift connection: no path between the two floors.
#[must_use]
pub fn small_plan_json_without_lift() -> Value {
    small_plan_json_with(false)
}

fn small_plan_json_with(lift: bool) -> Value {
    let outline = rect(-1.0, -1.0, 31.0, 21.0);
    let rooms: Vec<Value> = PLACES
        .iter()
        .map(|(id, label, _, room_kind, floor, [x0, y0, x1, y1], _)| {
            json!({ "id": id, "floor": floor, "label": label, "kind": room_kind, "polygon": rect(*x0, *y0, *x1, *y1) })
        })
        .collect();
    let places: Vec<Value> = PLACES
        .iter()
        .map(|(id, label, place_kind, _, floor, _, [x, y])| {
            json!({ "id": id, "label": label, "floor": floor, "x": x, "y": y, "kind": place_kind })
        })
        .collect();
    let mut index_on_floor = [0_usize; 3];
    let walls: Vec<Value> = WALLS
        .iter()
        .map(|(floor, [x0, y0, x1, y1])| {
            let slot = usize::try_from(*floor).unwrap_or(0);
            let index = index_on_floor.get(slot).copied().unwrap_or(0);
            if let Some(next) = index_on_floor.get_mut(slot) {
                *next += 1;
            }
            json!({ "id": format!("{floor}-w{index}"), "floor": floor, "points": [[x0, y0], [x1, y1]] })
        })
        .collect();
    let connections = if lift {
        json!([{ "from": LIFT_1, "to": LIFT_2, "metres": 4.0 }])
    } else {
        json!([])
    };
    json!({
        "marque": "inventé",
        "name": "Test clinic",
        "connections": connections,
        "floors": [
            { "id": 1, "label": "Floor 1", "outline": outline },
            { "id": 2, "label": "Floor 2", "outline": outline },
        ],
        "rooms": rooms,
        "walls": walls,
        "places": places,
        "props": [],
    })
}

/// The fixture clinic as a [`ClinicPlan`] (plain deserialisation, not validated).
///
/// # Errors
/// When the JSON does not deserialise (ids are checked by `PlaceId`).
pub fn small_plan() -> Result<ClinicPlan, serde_json::Error> {
    serde_json::from_value(small_plan_json())
}

/// The fixture clinic without the lift connection, as a plan.
///
/// # Errors
/// As [`small_plan`].
pub fn small_plan_without_lift() -> Result<ClinicPlan, serde_json::Error> {
    serde_json::from_value(small_plan_json_without_lift())
}

/// The fixture model, derived from the plan.
///
/// # Errors
/// Deserialisation or validation problems.
pub fn small_map() -> Result<ClinicMap, MapError> {
    Ok(small_plan()?.validate()?)
}

/// The fixture model without the lift connection.
///
/// # Errors
/// As [`small_map`].
pub fn small_map_without_lift() -> Result<ClinicMap, MapError> {
    Ok(small_plan_without_lift()?.validate()?)
}

/// The deaf zone over room 101 (floor 1), as the zone store would give it.
///
/// # Errors
/// Invalid id or polygon.
pub fn deaf_zone() -> Result<Zone, MapError> {
    Ok(Zone {
        id: DEAF_ZONE.parse()?,
        kind: domain::ZoneKind::Deaf,
        floor: 1,
        polygon: Polygon::from_pairs(&[[0.5, 12.5], [9.5, 12.5], [9.5, 19.5], [0.5, 19.5]])?,
        version: 1,
    })
}

/// Replaces the value at a JSON pointer (`/rooms/3/polygon`) in a test document.
///
/// # Errors
/// When nothing is at `pointer`.
pub fn set_at(json: &mut Value, pointer: &str, new: Value) -> Result<(), String> {
    let slot = json
        .pointer_mut(pointer)
        .ok_or_else(|| format!("nothing at {pointer}"))?;
    *slot = new;
    Ok(())
}
