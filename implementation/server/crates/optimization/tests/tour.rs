//! Task 18: the tour planner on an invented grid of places (rows × columns, 10 m apart
//! east-west and 7 m apart north-south), plus an isolated room closed by walls (unreachable
//! once Task 13b derives links from the planning grid).

use std::collections::BTreeSet;

use domain::{PlaceId, RobotStatus};
use locations::{ClinicMap, ClinicPlan};
use optimization::{
    DispatchPolicy, FleetMember, OptimizationError, PlaceMask, RejectReason, RoleCard,
    RoutingGraph, TourPlanner,
};
use serde_json::{Value, json};

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

const ROWS: u32 = 6;
const COLS: u32 = 6;
const DOCK: &str = "g-0-0";
const ISLAND: &str = "island";

fn cell(row: u32, col: u32) -> String {
    format!("g-{row}-{col}")
}

/// The grid clinic as a plan (ruling R14: every model comes from a plan): one hall room
/// covering the grid, places `g-<row>-<col>` at the centres of 10 m x 7 m cells, and
/// `island` east of it inside a room closed by a wall loop, so no route reaches it (once Task
/// 13b derives links from the planning grid; with Task 10b's straight-line links it is still
/// linked). Distances are the derived link lengths, so the tests compare tours with the same
/// graph, never with fixed numbers.
fn grid_map() -> Result<ClinicMap, BoxError> {
    let mut places = Vec::new();
    for row in 0..ROWS {
        for col in 0..COLS {
            let (x, y) = (f64::from(col) * 10.0, f64::from(row) * 7.0);
            places.push(json!({
                "id": cell(row, col), "label": cell(row, col), "floor": 1,
                "x": x + 5.0, "y": y + 3.5, "kind": "room"
            }));
        }
    }
    let width = f64::from(COLS) * 10.0;
    let height = f64::from(ROWS) * 7.0;
    places.push(json!({
        "id": ISLAND, "label": "Island", "floor": 1, "x": width + 5.0, "y": 3.5, "kind": "room"
    }));
    let island = [
        [width + 1.0, 1.0],
        [width + 9.0, 1.0],
        [width + 9.0, 6.0],
        [width + 1.0, 6.0],
    ];
    let plan: Value = json!({
        "marque": "inventé",
        "name": "Tour grid",
        "floors": [{ "id": 1, "label": "Floor 1",
                     "outline": [[0.0, 0.0], [width + 10.0, 0.0], [width + 10.0, height], [0.0, height]] }],
        "rooms": [
            { "id": "hall", "floor": 1, "label": "Hall", "kind": "corridor",
              "polygon": [[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]] },
            { "id": ISLAND, "floor": 1, "label": "Island", "kind": "room", "polygon": island },
        ],
        "walls": [{ "id": "island-wall", "floor": 1,
                    "points": [island[0], island[1], island[2], island[3], island[0]] }],
        "places": places,
        "props": [],
    });
    Ok(serde_json::from_value::<ClinicPlan>(plan)?.validate()?)
}

fn all_places() -> Vec<String> {
    let mut ids: Vec<String> = (0..ROWS)
        .flat_map(|r| (0..COLS).map(move |c| cell(r, c)))
        .collect();
    ids.push(ISLAND.to_owned());
    ids
}

fn member(id: &str, at: &str, battery_pct: f64) -> Result<FleetMember, BoxError> {
    Ok(FleetMember {
        id: id.parse()?,
        name: id.to_owned(),
        status: RobotStatus::Idle,
        at: at.parse()?,
        battery_pct,
        card: RoleCard {
            name: "porteur".to_owned(),
            permitted_places: all_places()
                .iter()
                .map(|p| p.parse::<PlaceId>())
                .collect::<Result<BTreeSet<_>, _>>()?,
            max_speed_m_s: 1.0,
        },
        simulated: false,
    })
}

fn places(ids: &[&str]) -> Result<Vec<PlaceId>, BoxError> {
    Ok(ids.iter().map(|id| id.parse()).collect::<Result<_, _>>()?)
}

fn planner(map: &ClinicMap) -> Result<(TourPlanner, RoutingGraph), BoxError> {
    let graph = RoutingGraph::from_map(map);
    Ok((
        TourPlanner::new(graph.clone(), DispatchPolicy::default(), DOCK.parse()?),
        graph,
    ))
}

fn distance(graph: &RoutingGraph, from: &PlaceId, to: &PlaceId) -> Result<f64, BoxError> {
    Ok(graph
        .shortest_path(from, to, &PlaceMask::all())
        .ok_or_else(|| format!("no path {from} -> {to}"))?
        .metres)
}

/// Length of the open path `start -> order[0] -> … -> order[n-1]`.
fn open_length(graph: &RoutingGraph, start: &PlaceId, order: &[PlaceId]) -> Result<f64, BoxError> {
    let mut total = 0.0;
    let mut at = start;
    for next in order {
        total += distance(graph, at, next)?;
        at = next;
    }
    Ok(total)
}

/// Every permutation of `items` (Heap's algorithm), for the brute-force optimum.
fn permutations(items: &[PlaceId]) -> Vec<Vec<PlaceId>> {
    fn heap(k: usize, items: &mut Vec<PlaceId>, out: &mut Vec<Vec<PlaceId>>) {
        if k <= 1 {
            out.push(items.clone());
            return;
        }
        for i in 0..k {
            heap(k - 1, items, out);
            let j = if k.is_multiple_of(2) { i } else { 0 };
            items.swap(j, k - 1);
        }
    }
    let mut items = items.to_vec();
    let mut out = Vec::new();
    heap(items.len(), &mut items, &mut out);
    out
}

#[test]
fn five_stops_match_brute_force_optimum() -> TestResult {
    let map = grid_map()?;
    let (planner, graph) = planner(&map)?;
    let robot = member("robot-r1", DOCK, 100.0)?;
    let stops = places(&["g-5-5", "g-0-4", "g-3-1", "g-2-5", "g-4-0"])?;
    let tour = planner.plan(&robot, &stops)?;
    let mut best = f64::INFINITY;
    for order in permutations(&stops) {
        best = best.min(open_length(&graph, &robot.at, &order)?);
    }
    assert!(
        (tour.metres - best).abs() < 1e-6,
        "{} vs optimum {best}",
        tour.metres
    );
    let visited: BTreeSet<&PlaceId> = tour.order.iter().filter(|p| p.as_str() != DOCK).collect();
    let wanted: BTreeSet<&PlaceId> = stops.iter().collect();
    assert_eq!(visited, wanted);
    assert!(tour.skipped.is_empty());
    Ok(())
}

#[test]
fn ten_stops_not_worse_than_nearest_neighbour() -> TestResult {
    let map = grid_map()?;
    let (planner, graph) = planner(&map)?;
    let robot = member("robot-r1", DOCK, 100.0)?;
    let stops = places(&[
        "g-5-5", "g-0-4", "g-3-1", "g-2-5", "g-4-0", "g-1-1", "g-5-2", "g-0-2", "g-3-4", "g-4-3",
    ])?;
    let mut left = stops.clone();
    let mut at = robot.at.clone();
    let mut nearest_neighbour = 0.0;
    while !left.is_empty() {
        let mut best: Option<(usize, f64)> = None;
        for (index, stop) in left.iter().enumerate() {
            let d = distance(&graph, &at, stop)?;
            if best.is_none_or(|(_, b)| d < b) {
                best = Some((index, d));
            }
        }
        let (index, d) = best.ok_or("no stop left")?;
        nearest_neighbour += d;
        at = left.swap_remove(index);
    }
    let tour = planner.plan(&robot, &stops)?;
    assert!(
        tour.metres <= nearest_neighbour + 1e-6,
        "{} is worse than nearest neighbour {nearest_neighbour}",
        tour.metres
    );
    Ok(())
}

/// 0.5 % per metre and a 15 % floor: at 40 % the robot has 50 m before it must recharge,
/// far less than the tour.
#[test]
fn low_battery_inserts_dock_visit_before_the_unreachable_leg() -> TestResult {
    let map = grid_map()?;
    let (planner, _graph) = planner(&map)?;
    let robot = member("robot-r1", DOCK, 40.0)?;
    let stops = places(&["g-0-3", "g-5-5", "g-5-0"])?;
    let tour = planner.plan(&robot, &stops)?;
    assert!(!tour.dock_visits.is_empty(), "{tour:?}");
    for index in &tour.dock_visits {
        assert_eq!(
            tour.order.get(*index).map(PlaceId::as_str),
            Some(DOCK),
            "{tour:?}"
        );
    }
    let visited: BTreeSet<&PlaceId> = tour.order.iter().filter(|p| p.as_str() != DOCK).collect();
    assert_eq!(visited.len(), 3);
    Ok(())
}

#[test]
#[ignore = "same-floor links are still straight lines between every two places (ClinicPlan::validate), so the walled island stays linked (locations, T13b)"]
fn unreachable_stop_is_reported_in_skipped_with_reason() -> TestResult {
    let map = grid_map()?;
    let (planner, _graph) = planner(&map)?;
    let robot = member("robot-r1", DOCK, 100.0)?;
    let tour = planner.plan(&robot, &places(&["g-2-2", ISLAND])?)?;
    assert_eq!(tour.skipped.len(), 1);
    let skipped = tour.skipped.first().ok_or("nothing skipped")?;
    assert_eq!(skipped.place.as_str(), ISLAND);
    assert_eq!(skipped.reason, RejectReason::NoPath);
    assert!(tour.order.iter().any(|p| p.as_str() == "g-2-2"));
    assert!(!tour.order.iter().any(|p| p.as_str() == ISLAND));
    Ok(())
}

#[test]
fn thirty_stops_returns_too_many_stops_with_both_numbers() -> TestResult {
    let map = grid_map()?;
    let (planner, _graph) = planner(&map)?;
    let robot = member("robot-r1", DOCK, 100.0)?;
    let stops: Vec<PlaceId> = all_places()
        .iter()
        .filter(|p| p.as_str() != ISLAND)
        .take(30)
        .map(|p| p.parse())
        .collect::<Result<_, _>>()?;
    let err = planner
        .plan(&robot, &stops)
        .err()
        .ok_or("30 stops were accepted")?;
    assert_eq!(err, OptimizationError::TooManyStops { given: 30, max: 25 });
    let message = err.to_string();
    assert!(
        message.contains("30") && message.contains("25"),
        "{message}"
    );
    Ok(())
}

#[test]
fn two_robots_get_disjoint_stop_sets_covering_all_reachable_stops() -> TestResult {
    let map = grid_map()?;
    let (planner, _graph) = planner(&map)?;
    let fleet = [
        member("robot-r1", DOCK, 100.0)?,
        member("robot-r2", "g-5-5", 100.0)?,
    ];
    let stops = places(&[
        "g-0-1", "g-1-0", "g-1-1", "g-5-4", "g-4-5", "g-4-4", "g-2-3", "g-3-2",
    ])?;
    let split = planner.assign_stops(&fleet, &stops)?;
    let mut seen = BTreeSet::new();
    for (_robot, assigned) in &split {
        for stop in assigned {
            assert!(seen.insert(stop.clone()), "{stop} assigned twice");
        }
    }
    let wanted: BTreeSet<PlaceId> = stops.into_iter().collect();
    assert_eq!(seen, wanted);
    Ok(())
}
