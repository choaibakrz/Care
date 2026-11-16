//! Editable clinic plans (Task A4): one versioned document per clinic, in the admin console's
//! map shape.
//!
//! A [`ClinicPlan`] is what an admin draws: floors, rooms, walls, named places and furniture.
//! It serialises exactly like the console's `ClinicMap` type (`admin/src/types.ts`): metres,
//! x east, **y south**, points `[x, y]`, walls with an `id`. `GET /clinics/{id}` returns it,
//! `POST /clinics` and `PUT /clinics/{id}` take it whole, `seed/clinic_map.json` is one (plus
//! `"marque": "inventé"`), and `GET /map` serves the active one ([`crate::MapView`]).
//!
//! The server validates the whole document at once ([`ClinicPlan::validate`]) and refuses it
//! with **every** problem found, each with a path into the document ([`PlanProblem`]). A valid
//! plan becomes the model the rest of the server uses ([`ClinicMap`]): the model is **always**
//! derived from a plan (ruling R14), never written by hand.

use std::collections::{HashMap, HashSet};
use std::sync::{Arc, PoisonError, RwLock};

use domain::{ClinicId, ErrorProblem, PlaceId};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::error::LocationError;
use crate::geometry::{Point2, Polygon, Wall};
use crate::model::{ClinicMap, Floor, Obstacle, ObstacleKind, Place, PlaceKind, PlaceLink};

/// A point `[x, y]` in metres (x east, y south).
pub type MapPoint = [f64; 2];

/// Elevation step between floor levels when a plan is turned into the 3D model: level `n` is
/// at `n * FLOOR_ELEVATION_STEP_M` metres (the console's plan has no heights).
pub const FLOOR_ELEVATION_STEP_M: f64 = 3.5;
/// Ceiling height given to every floor of a plan, metres.
pub const FLOOR_HEIGHT_M: f64 = 3.0;
/// Thickness given to a plan wall, metres (the console draws walls 0.16 m thick).
pub const PLAN_WALL_THICKNESS_M: f64 = 0.16;
/// Longest accepted plan name, in characters.
pub const MAX_PLAN_NAME_LEN: usize = 80;
/// Longest accepted label (floor, room, place), in characters.
pub const MAX_PLAN_LABEL_LEN: usize = 60;

/// One clinic plan: the editable document.
///
/// Invariants after [`ClinicPlan::validate`] succeeds are listed there. Unknown keys are
/// refused (a typo must not be dropped silently); `marque` is accepted so a seed or exported
/// file can be imported as is.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ClinicPlan {
    /// Display name of the clinic ("Demo clinic").
    pub name: String,
    /// Floors.
    pub floors: Vec<PlanFloor>,
    /// Rooms (footprints with a kind).
    pub rooms: Vec<PlanRoom>,
    /// Walls, as open polylines; a door is a gap between two walls.
    pub walls: Vec<PlanWall>,
    /// Named points robots go to.
    pub places: Vec<PlanPlace>,
    /// Furniture; `solid` props block the route planner.
    pub props: Vec<PlanProp>,
    /// Walkable links the drawing cannot show, chiefly a lift between two floors. Optional:
    /// absent (as the console sends it today) means none; never serialised when empty.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub connections: Vec<PlanConnection>,
    /// Seed and export marker, `"inventé"` for invented data. Optional; kept as given.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub marque: Option<String>,
}

/// One floor.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanFloor {
    /// Level (0 ground). Unique in the plan.
    pub id: i32,
    /// Display name ("Ground floor", "Floor 2", …).
    pub label: String,
    /// Outline, a simple polygon.
    #[schema(value_type = Vec<Vec<f64>>)]
    pub outline: Vec<MapPoint>,
}

/// What a room is, in the console's vocabulary.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RoomKind {
    /// Patient room.
    Room,
    /// Corridor or hall.
    Corridor,
    /// Lift. Robots never enter it (the route planner treats it as closed).
    Elevator,
    /// Nurse station, reception or care room.
    Care,
    /// Storeroom.
    Storage,
    /// Therapy room.
    Therapy,
    /// Pool.
    Pool,
    /// Lounge.
    Lounge,
}

/// A room: a footprint with a kind.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanRoom {
    /// Id, unique among rooms (`[a-z0-9_-]`, 1 to 64 characters).
    pub id: PlaceId,
    /// Floor level.
    pub floor: i32,
    /// Display name.
    pub label: String,
    /// Kind.
    pub kind: RoomKind,
    /// Footprint, a simple polygon inside the floor outline.
    #[schema(value_type = Vec<Vec<f64>>)]
    pub polygon: Vec<MapPoint>,
    /// Where to draw the label; inside the polygon when given.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    #[schema(value_type = Option<Vec<f64>>)]
    pub label_at: Option<MapPoint>,
}

/// A wall: an open polyline of at least two points.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanWall {
    /// Id, unique among walls (the seed uses `<floor>-w<index>`).
    pub id: String,
    /// Floor level.
    pub floor: i32,
    /// Polyline, at least two points, inside or on the floor outline.
    #[schema(value_type = Vec<Vec<f64>>)]
    pub points: Vec<MapPoint>,
}

/// What a place point is, in the console's vocabulary.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PlaceViewKind {
    /// A room's anchor.
    Room,
    /// A shelf (stock is counted there).
    Shelf,
    /// A robot dock.
    Dock,
    /// Any other point (corridor, lift landing, …).
    Point,
}

/// A named place: the point a robot goes to.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanPlace {
    /// Id, unique among places. Tasks, stock items and schedules refer to it.
    pub id: PlaceId,
    /// Display name.
    pub label: String,
    /// Floor level.
    pub floor: i32,
    /// Metres east.
    pub x: f64,
    /// Metres south.
    pub y: f64,
    /// Kind.
    pub kind: PlaceViewKind,
}

/// What a prop is (the console's furniture list).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PropKind {
    /// Bed.
    Bed,
    /// Counter.
    Counter,
    /// Desk.
    Desk,
    /// Shelf.
    Shelf,
    /// Cabinet.
    Cabinet,
    /// Sofa.
    Sofa,
    /// Armchair.
    Armchair,
    /// Table.
    Table,
    /// Plant.
    Plant,
    /// Dock.
    Dock,
    /// Pool.
    Pool,
    /// Bench.
    Bench,
    /// Crate.
    Crate,
    /// Mat.
    Mat,
    /// Parallel bars.
    Bars,
    /// Nightstand.
    Nightstand,
    /// Door.
    Door,
}

/// An explicit walkable link between two places (Task A4, ruling R14): the only way to join
/// two floors (a lift robots may use). Same-floor links are derived from the drawing.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanConnection {
    /// One end (a place id of the plan).
    pub from: PlaceId,
    /// The other end.
    pub to: PlaceId,
    /// Walking length, metres, > 0 (for a lift: the ride counted as distance).
    pub metres: f64,
}

/// A piece of furniture: an axis-aligned rectangle centred on `(x, y)`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanProp {
    /// Id, unique among props.
    pub id: String,
    /// Floor level.
    pub floor: i32,
    /// Kind.
    pub kind: PropKind,
    /// Centre, metres east.
    pub x: f64,
    /// Centre, metres south.
    pub y: f64,
    /// Size along x, metres, > 0.
    pub width: f64,
    /// Size along y, metres, > 0.
    pub depth: f64,
    /// Blocks robots (the route planner keeps the robot's clearance around it).
    pub solid: bool,
}

/// One problem of a refused plan.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct PlanProblem {
    /// Where, as a path into the document: `name`, `floors[0].outline`, `rooms[3].polygon`,
    /// `walls[2].points[1]`, `places[5]`, `props[7].width`.
    pub path: String,
    /// What is wrong, safe to show: "edges 1–2 and 3–4 cross", "is outside every floor
    /// outline", "id 'room-11' is used twice (also rooms[4])".
    pub problem: String,
}

impl From<PlanProblem> for ErrorProblem {
    fn from(problem: PlanProblem) -> ErrorProblem {
        ErrorProblem {
            path: problem.path,
            problem: problem.problem,
        }
    }
}

/// Every problem of a refused plan, in document order (floors, rooms, walls, places, props).
/// Never empty.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error("The clinic plan has {count} problem(s); fix each one listed and save again.", count = .0.len())]
pub struct PlanErrors(pub Vec<PlanProblem>);

impl ClinicPlan {
    /// Checks the whole plan and builds the server's model of it.
    ///
    /// Checks, each reported with its path (all of them, not the first one):
    /// - `name`: 1 to [`MAX_PLAN_NAME_LEN`] characters after trimming.
    /// - `floors`: at least one; ids unique; labels 1 to [`MAX_PLAN_LABEL_LEN`] characters;
    ///   each outline a simple polygon (at least 3 points, finite, non-zero area, no repeated
    ///   consecutive point, no crossing edges: "edges 1–2 and 3–4 cross", 1-based vertices).
    /// - `rooms`: ids unique; floor exists; polygon simple and inside the floor outline;
    ///   `label_at` inside the polygon.
    /// - `walls`: ids unique and non-empty; floor exists; at least two finite points, each
    ///   inside or on the floor outline.
    /// - `places`: ids unique; floor exists ("is outside every floor outline" when the floor
    ///   is unknown or the point outside its outline); point inside a room of its floor.
    /// - `props`: ids unique; floor exists; centre inside the floor outline; `width` and
    ///   `depth` finite and > 0.
    /// - `connections`: both ends are places of the plan, different from each other;
    ///   `metres` finite and > 0; no pair twice (either direction).
    ///
    /// Task 13b adds one check on the planning grid ([`crate::grid::PlanningGrid`]): every
    /// place stands on free ground. Two places of a floor that the grid cannot join are not an
    /// error: they simply get no link (a place behind closed walls is unreachable).
    ///
    /// The model: floors (level = `id`, elevation `id * FLOOR_ELEVATION_STEP_M`, height
    /// [`FLOOR_HEIGHT_M`], each wall polyline cut into segments of
    /// [`PLAN_WALL_THICKNESS_M`]); one `Place` per plan place (name = label, anchor = the
    /// point, footprint = the smallest room containing it, kind: `shelf` -> storeroom,
    /// `dock` -> dock, `room` -> room, `point` -> from the room: corridor -> corridor,
    /// elevator -> lift, otherwise other); links between every two places of the same floor
    /// (straight-line length until Task 13b replaces it by the planning-grid route length and
    /// drops the pairs the grid cannot join), plus one link per `connections` entry (the only
    /// links between floors); obstacles: solid props (`Solid`)
    /// and elevator rooms (`Closed`); no zones (zones live in the zone store and are passed
    /// to the planners separately).
    ///
    /// # Errors
    /// [`PlanErrors`] with every problem found.
    pub fn validate(&self) -> Result<ClinicMap, PlanErrors> {
        let mut problems = Vec::new();
        let outlines = self.check_document(&mut problems);
        if !problems.is_empty() {
            return Err(PlanErrors(problems));
        }
        self.build_model(&outlines).map_err(|error| {
            PlanErrors(vec![PlanProblem {
                path: "plan".to_owned(),
                problem: error.to_string(),
            }])
        })
    }

    /// The place ids of the plan, in order.
    #[must_use]
    pub fn place_ids(&self) -> Vec<&PlaceId> {
        self.places.iter().map(|place| &place.id).collect()
    }
}

/// Items to add or replace (same id), per list.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct OverlayUpsert {
    /// Floors.
    #[serde(default)]
    pub floors: Vec<PlanFloor>,
    /// Rooms.
    #[serde(default)]
    pub rooms: Vec<PlanRoom>,
    /// Walls.
    #[serde(default)]
    pub walls: Vec<PlanWall>,
    /// Places.
    #[serde(default)]
    pub places: Vec<PlanPlace>,
    /// Furniture.
    #[serde(default)]
    pub props: Vec<PlanProp>,
}

/// Ids to drop from the base, per list (floor ids are numbers).
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct OverlayRemove {
    /// Floor levels.
    #[serde(default)]
    pub floors: Vec<i32>,
    /// Room ids.
    #[serde(default)]
    pub rooms: Vec<String>,
    /// Wall ids.
    #[serde(default)]
    pub walls: Vec<String>,
    /// Place ids.
    #[serde(default)]
    pub places: Vec<String>,
    /// Prop ids.
    #[serde(default)]
    pub props: Vec<String>,
}

/// The modifications of a base plan (ruling R28): applied on top of the base, never
/// merged into it. The effective plan is the base without `remove`, then `upsert`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanOverlay {
    /// Informational: the base version the modifications were drawn on.
    #[serde(default)]
    pub base_version: u64,
    /// Items added or replaced.
    #[serde(default)]
    pub upsert: OverlayUpsert,
    /// Ids removed from the base.
    #[serde(default)]
    pub remove: OverlayRemove,
}

/// `items` without the removed ids, then each upsert replacing the same id or appended.
fn merge<T: Clone, K: PartialEq>(
    items: &[T],
    key: impl Fn(&T) -> K,
    removed: &[K],
    upsert: &[T],
) -> Vec<T> {
    let mut out: Vec<T> = items
        .iter()
        .filter(|item| !removed.contains(&key(item)))
        .cloned()
        .collect();
    for new in upsert {
        match out.iter_mut().find(|item| key(item) == key(new)) {
            Some(slot) => *slot = new.clone(),
            None => out.push(new.clone()),
        }
    }
    out
}

impl PlanOverlay {
    /// Whether it changes nothing.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.upsert == OverlayUpsert::default() && self.remove == OverlayRemove::default()
    }

    /// How many items it upserts or removes.
    #[must_use]
    pub fn count(&self) -> usize {
        let (u, r) = (&self.upsert, &self.remove);
        u.floors.len()
            + u.rooms.len()
            + u.walls.len()
            + u.places.len()
            + u.props.len()
            + r.floors.len()
            + r.rooms.len()
            + r.walls.len()
            + r.places.len()
            + r.props.len()
    }

    /// The effective plan: `base` with the removals dropped, then the upserts replacing
    /// same-id items or added. A removal of an id the base lacks is ignored (logged by the
    /// service). Not validated: run [`ClinicPlan::validate`] on the result.
    #[must_use]
    pub fn apply(&self, base: &ClinicPlan) -> ClinicPlan {
        let (u, r) = (&self.upsert, &self.remove);
        let ids = |list: &[String]| list.to_vec();
        ClinicPlan {
            floors: merge(&base.floors, |f| f.id, &r.floors, &u.floors),
            rooms: merge(
                &base.rooms,
                |x| x.id.as_str().to_owned(),
                &ids(&r.rooms),
                &u.rooms,
            ),
            walls: merge(&base.walls, |x| x.id.clone(), &ids(&r.walls), &u.walls),
            places: merge(
                &base.places,
                |x| x.id.as_str().to_owned(),
                &ids(&r.places),
                &u.places,
            ),
            props: merge(&base.props, |x| x.id.clone(), &ids(&r.props), &u.props),
            ..base.clone()
        }
    }

    /// Removed ids the base does not have (ignored by [`PlanOverlay::apply`]).
    #[must_use]
    pub fn unknown_removals(&self, base: &ClinicPlan) -> Vec<String> {
        let r = &self.remove;
        let mut out = Vec::new();
        out.extend(
            r.floors
                .iter()
                .filter(|id| !base.floors.iter().any(|f| f.id == **id))
                .map(|id| format!("floors/{id}")),
        );
        out.extend(
            r.rooms
                .iter()
                .filter(|id| !base.rooms.iter().any(|x| x.id.as_str() == id.as_str()))
                .map(|id| format!("rooms/{id}")),
        );
        out.extend(
            r.walls
                .iter()
                .filter(|id| !base.walls.iter().any(|x| &x.id == *id))
                .map(|id| format!("walls/{id}")),
        );
        out.extend(
            r.places
                .iter()
                .filter(|id| !base.places.iter().any(|x| x.id.as_str() == id.as_str()))
                .map(|id| format!("places/{id}")),
        );
        out.extend(
            r.props
                .iter()
                .filter(|id| !base.props.iter().any(|x| &x.id == *id))
                .map(|id| format!("props/{id}")),
        );
        out
    }
}

/// The active plan with its identity, as the services read it.
#[derive(Debug, Clone)]
pub struct ActivePlan {
    /// Which stored plan.
    pub clinic_id: ClinicId,
    /// Its version.
    pub version: u64,
    /// The document.
    pub plan: Arc<ClinicPlan>,
    /// Its validated model.
    pub map: Arc<ClinicMap>,
}

impl ActivePlan {
    /// The tag that names this exact plan content: `<clinic id>-v<version>`. Used as the
    /// `ETag` of `GET /map` and as the `version` of the robots' `map.update`.
    #[must_use]
    pub fn tag(&self) -> String {
        format!("{}-v{}", self.clinic_id, self.version)
    }
}

/// The plan in force, shared by every service that reads the map. Replaced as a whole when an
/// admin saves the active plan or activates another one; readers keep the `Arc` they took.
#[derive(Debug)]
pub struct ActiveMap {
    current: RwLock<Arc<ActivePlan>>,
}

impl ActiveMap {
    /// Starts with `plan`.
    #[must_use]
    pub fn new(plan: ActivePlan) -> ActiveMap {
        ActiveMap {
            current: RwLock::new(Arc::new(plan)),
        }
    }

    /// The plan in force now (cheap: one `Arc` clone). A poisoned lock still yields the last
    /// plan written.
    #[must_use]
    pub fn current(&self) -> Arc<ActivePlan> {
        let guard = self.current.read().unwrap_or_else(PoisonError::into_inner);
        Arc::clone(&guard)
    }

    /// Replaces the plan in force.
    pub fn replace(&self, plan: ActivePlan) {
        let mut guard = self.current.write().unwrap_or_else(PoisonError::into_inner);
        *guard = Arc::new(plan);
    }
}

fn problem(path: String, problem: impl Into<String>) -> PlanProblem {
    PlanProblem {
        path,
        problem: problem.into(),
    }
}

/// Records a duplicate id; `seen` maps an id to the index of its first use.
fn check_unique(
    seen: &mut HashMap<String, usize>,
    list: &str,
    index: usize,
    id: &str,
    problems: &mut Vec<PlanProblem>,
) {
    if let Some(first) = seen.get(id) {
        problems.push(problem(
            format!("{list}[{index}].id"),
            format!("id '{id}' is used twice (also {list}[{first}])"),
        ));
    } else {
        seen.insert(id.to_owned(), index);
    }
}

/// The message of a polygon error; crossing edges are named by 1-based vertices.
fn polygon_message(error: &LocationError, vertices: usize) -> String {
    if let LocationError::SelfIntersecting { edge_a, edge_b } = error {
        let edge = |e: usize| format!("{}–{}", e + 1, (e + 1) % vertices.max(1) + 1);
        return format!("edges {} and {} cross", edge(*edge_a), edge(*edge_b));
    }
    error.to_string()
}

fn label_problem(label: &str, path: String, problems: &mut Vec<PlanProblem>) {
    let len = label.trim().chars().count();
    if len == 0 || len > MAX_PLAN_LABEL_LEN {
        problems.push(problem(
            path,
            format!("must have 1 to {MAX_PLAN_LABEL_LEN} characters"),
        ));
    }
}

fn area(polygon: &Polygon) -> f64 {
    let pairs = polygon.to_pairs();
    pairs
        .iter()
        .zip(pairs.iter().cycle().skip(1))
        .map(|(a, b)| a[0] * b[1] - b[0] * a[1])
        .sum::<f64>()
        .abs()
        / 2.0
}

impl ClinicPlan {
    /// Runs every document check; returns the floor outlines by level.
    fn check_document(&self, problems: &mut Vec<PlanProblem>) -> HashMap<i32, Polygon> {
        let name_len = self.name.trim().chars().count();
        if name_len == 0 || name_len > MAX_PLAN_NAME_LEN {
            problems.push(problem(
                "name".to_owned(),
                format!("must have 1 to {MAX_PLAN_NAME_LEN} characters"),
            ));
        }
        let mut outlines = HashMap::new();
        if self.floors.is_empty() {
            problems.push(problem("floors".to_owned(), "needs at least one floor"));
        }
        for (index, floor) in self.floors.iter().enumerate() {
            if outlines.contains_key(&floor.id) {
                problems.push(problem(
                    format!("floors[{index}].id"),
                    format!("floor {} is used twice", floor.id),
                ));
            }
            label_problem(&floor.label, format!("floors[{index}].label"), problems);
            match Polygon::from_pairs(&floor.outline) {
                Ok(polygon) => {
                    outlines.entry(floor.id).or_insert(polygon);
                }
                Err(error) => problems.push(problem(
                    format!("floors[{index}].outline"),
                    polygon_message(&error, floor.outline.len()),
                )),
            }
        }
        let room_polygons = self.check_rooms(&outlines, problems);
        self.check_walls(&outlines, problems);
        self.check_places(&outlines, &room_polygons, problems);
        self.check_props(&outlines, problems);
        self.check_connections(problems);
        outlines
    }

    fn check_rooms(
        &self,
        outlines: &HashMap<i32, Polygon>,
        problems: &mut Vec<PlanProblem>,
    ) -> Vec<Option<Polygon>> {
        let mut seen = HashMap::new();
        let mut polygons = Vec::new();
        for (index, room) in self.rooms.iter().enumerate() {
            check_unique(&mut seen, "rooms", index, room.id.as_str(), problems);
            label_problem(&room.label, format!("rooms[{index}].label"), problems);
            let path = format!("rooms[{index}].polygon");
            let polygon = match Polygon::from_pairs(&room.polygon) {
                Ok(polygon) => Some(polygon),
                Err(error) => {
                    problems.push(problem(
                        path.clone(),
                        polygon_message(&error, room.polygon.len()),
                    ));
                    None
                }
            };
            match (outlines.get(&room.floor), &polygon) {
                (None, _) => problems.push(problem(
                    format!("rooms[{index}].floor"),
                    format!("floor {} is not in the plan", room.floor),
                )),
                (Some(outline), Some(polygon)) if !outline.contains_polygon(polygon) => {
                    problems.push(problem(path, "is outside the floor outline"));
                }
                _ => {}
            }
            if let (Some(polygon), Some([x, y])) = (&polygon, room.label_at) {
                let inside = Point2::new(x, y).is_ok_and(|point| polygon.contains(&point));
                if !inside {
                    problems.push(problem(
                        format!("rooms[{index}].label_at"),
                        "is outside the room",
                    ));
                }
            }
            polygons.push(polygon);
        }
        polygons
    }

    fn check_walls(&self, outlines: &HashMap<i32, Polygon>, problems: &mut Vec<PlanProblem>) {
        let mut seen = HashMap::new();
        for (index, wall) in self.walls.iter().enumerate() {
            if wall.id.trim().is_empty() {
                problems.push(problem(format!("walls[{index}].id"), "must not be empty"));
            } else {
                check_unique(&mut seen, "walls", index, &wall.id, problems);
            }
            let Some(outline) = outlines.get(&wall.floor) else {
                problems.push(problem(
                    format!("walls[{index}].floor"),
                    format!("floor {} is not in the plan", wall.floor),
                ));
                continue;
            };
            if wall.points.len() < 2 {
                problems.push(problem(
                    format!("walls[{index}].points"),
                    "needs at least two points",
                ));
            }
            for (at, [x, y]) in wall.points.iter().enumerate() {
                if !Point2::new(*x, *y).is_ok_and(|point| outline.contains(&point)) {
                    problems.push(problem(
                        format!("walls[{index}].points[{at}]"),
                        "is outside the floor outline",
                    ));
                }
            }
        }
    }

    fn check_places(
        &self,
        outlines: &HashMap<i32, Polygon>,
        room_polygons: &[Option<Polygon>],
        problems: &mut Vec<PlanProblem>,
    ) {
        let mut seen = HashMap::new();
        for (index, place) in self.places.iter().enumerate() {
            check_unique(&mut seen, "places", index, place.id.as_str(), problems);
            label_problem(&place.label, format!("places[{index}].label"), problems);
            let path = format!("places[{index}]");
            let point = Point2::new(place.x, place.y).ok();
            let in_floor = match (outlines.get(&place.floor), &point) {
                (Some(outline), Some(point)) => outline.contains(point),
                _ => false,
            };
            if !in_floor {
                problems.push(problem(path, "is outside every floor outline"));
                continue;
            }
            let in_room = point.is_some_and(|point| {
                self.rooms.iter().zip(room_polygons).any(|(room, polygon)| {
                    room.floor == place.floor
                        && polygon.as_ref().is_some_and(|p| p.contains(&point))
                })
            });
            if !in_room {
                problems.push(problem(path, "is not inside any room of its floor"));
            }
        }
    }

    fn check_props(&self, outlines: &HashMap<i32, Polygon>, problems: &mut Vec<PlanProblem>) {
        let mut seen = HashMap::new();
        for (index, prop) in self.props.iter().enumerate() {
            check_unique(&mut seen, "props", index, &prop.id, problems);
            for (name, value) in [("width", prop.width), ("depth", prop.depth)] {
                if !(value.is_finite() && value > 0.0) {
                    problems.push(problem(
                        format!("props[{index}].{name}"),
                        "must be a number greater than 0",
                    ));
                }
            }
            let inside = outlines.get(&prop.floor).is_some_and(|outline| {
                Point2::new(prop.x, prop.y).is_ok_and(|point| outline.contains(&point))
            });
            if !inside {
                problems.push(problem(
                    format!("props[{index}]"),
                    "is outside every floor outline",
                ));
            }
        }
    }

    fn check_connections(&self, problems: &mut Vec<PlanProblem>) {
        let ids: HashSet<&PlaceId> = self.places.iter().map(|place| &place.id).collect();
        let mut pairs = HashSet::new();
        for (index, link) in self.connections.iter().enumerate() {
            let path = format!("connections[{index}]");
            for (end, id) in [("from", &link.from), ("to", &link.to)] {
                if !ids.contains(id) {
                    problems.push(problem(
                        format!("{path}.{end}"),
                        format!("place '{id}' is not in the plan"),
                    ));
                }
            }
            if link.from == link.to {
                problems.push(problem(path.clone(), "joins a place to itself"));
            }
            if !(link.metres.is_finite() && link.metres > 0.0) {
                problems.push(problem(
                    format!("{path}.metres"),
                    "must be a number greater than 0",
                ));
            }
            let (a, b) = (link.from.to_string(), link.to.to_string());
            let key = if a <= b { (a, b) } else { (b, a) };
            if !pairs.insert(key) {
                problems.push(problem(path, "is listed twice"));
            }
        }
    }

    /// Solid props and closed (elevator) rooms.
    fn obstacles(&self, room_polygons: &[Polygon]) -> Result<Vec<Obstacle>, LocationError> {
        let mut obstacles = Vec::new();
        for prop in self.props.iter().filter(|prop| prop.solid) {
            let (hw, hd) = (prop.width / 2.0, prop.depth / 2.0);
            obstacles.push(Obstacle {
                id: prop.id.clone(),
                floor: prop.floor,
                kind: ObstacleKind::Solid,
                area: Polygon::from_pairs(&[
                    [prop.x - hw, prop.y - hd],
                    [prop.x + hw, prop.y - hd],
                    [prop.x + hw, prop.y + hd],
                    [prop.x - hw, prop.y + hd],
                ])?,
            });
        }
        for (room, polygon) in self.rooms.iter().zip(room_polygons) {
            if room.kind == RoomKind::Elevator {
                obstacles.push(Obstacle {
                    id: room.id.to_string(),
                    floor: room.floor,
                    kind: ObstacleKind::Closed,
                    area: polygon.clone(),
                });
            }
        }
        Ok(obstacles)
    }

    /// Builds the model of a plan whose document checks passed.
    fn build_model(&self, outlines: &HashMap<i32, Polygon>) -> Result<ClinicMap, LocationError> {
        let room_polygons = self
            .rooms
            .iter()
            .map(|room| Polygon::from_pairs(&room.polygon))
            .collect::<Result<Vec<_>, _>>()?;
        let mut floors = Vec::new();
        for floor in &self.floors {
            let Some(outline) = outlines.get(&floor.id) else {
                return Err(LocationError::UnknownFloor { floor: floor.id });
            };
            let mut walls = Vec::new();
            for wall in self.walls.iter().filter(|wall| wall.floor == floor.id) {
                for pair in wall.points.windows(2) {
                    if let [a, b] = pair {
                        walls.push(Wall {
                            start: Point2::new(a[0], a[1])?,
                            end: Point2::new(b[0], b[1])?,
                            thickness_m: PLAN_WALL_THICKNESS_M,
                        });
                    }
                }
            }
            floors.push(Floor {
                level: floor.id,
                elevation_m: f64::from(floor.id) * FLOOR_ELEVATION_STEP_M,
                height_m: FLOOR_HEIGHT_M,
                outline: outline.clone(),
                walls,
            });
        }
        let mut places = Vec::new();
        for place in &self.places {
            let anchor = Point2::new(place.x, place.y)?;
            let found = self
                .rooms
                .iter()
                .zip(&room_polygons)
                .filter(|(room, polygon)| room.floor == place.floor && polygon.contains(&anchor))
                .min_by(|a, b| area(a.1).total_cmp(&area(b.1)));
            let Some((room, footprint)) = found else {
                return Err(LocationError::PlaceOutsideFloor {
                    place: place.id.clone(),
                    floor: place.floor,
                });
            };
            let kind = match place.kind {
                PlaceViewKind::Shelf => PlaceKind::Storeroom,
                PlaceViewKind::Dock => PlaceKind::Dock,
                PlaceViewKind::Room => PlaceKind::Room,
                PlaceViewKind::Point => match room.kind {
                    RoomKind::Corridor => PlaceKind::Corridor,
                    RoomKind::Elevator => PlaceKind::Lift,
                    _ => PlaceKind::Other,
                },
            };
            places.push(Place {
                id: place.id.clone(),
                name: place.label.clone(),
                kind,
                floor: place.floor,
                footprint: footprint.clone(),
                anchor,
            });
        }
        let mut links = Vec::new();
        for (index, a) in places.iter().enumerate() {
            for b in places.iter().skip(index + 1).filter(|b| b.floor == a.floor) {
                links.push(PlaceLink {
                    from: a.id.clone(),
                    to: b.id.clone(),
                    metres: a.anchor.distance(&b.anchor).max(0.01),
                });
            }
        }
        links.extend(self.connections.iter().map(|link| PlaceLink {
            from: link.from.clone(),
            to: link.to.clone(),
            metres: link.metres,
        }));
        let obstacles = self.obstacles(&room_polygons)?;
        ClinicMap::new(floors, places, links, Vec::new())?.with_obstacles(obstacles)
    }
}
