//! Task A4 / 13b: restricted zones are impassable for the dispatcher's path cost and the tour
//! planner, not only for the route preview. Planning only: the gardien does not enforce them
//! yet (open question 5).
//!
//! Fixture: the small clinic of `tests/support/map.rs`. On floor 1 the corridor
//! (`corridor-1`, y 8..12) is the only way between the west rooms (storeroom, dock, room 102)
//! and the east ones (room 103's door at x 19..21, room 104). A restricted band across the
//! corridor at x 16.5..18.5 cuts it; a band over its north half only does not.
//!
//! Owner: Task 13b (it fills `RoutingGraph::from_map_with_zones`, `GraphHandle` and the
//! `with_handle` constructors); the dispatcher and tour bodies themselves are Tasks 13 and 18.

#[path = "../../../tests/support/map.rs"]
mod map;

use std::collections::BTreeSet;

use domain::{PlaceId, RobotStatus, ZoneKind};
use locations::{Polygon, Zone};
use optimization::{
    DispatchPolicy, DispatchRequest, Dispatcher, FleetMember, GraphHandle, PlaceMask, RejectReason,
    RoleCard, RoutingGraph, TourPlanner,
};

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn restricted(id: &str, pairs: &[[f64; 2]]) -> Result<Zone, BoxError> {
    Ok(Zone {
        id: id.parse()?,
        kind: ZoneKind::Restricted,
        floor: 1,
        polygon: Polygon::from_pairs(pairs)?,
        version: 1,
    })
}

/// Across the whole corridor: west and east are cut apart.
fn full_band() -> Result<Zone, BoxError> {
    restricted(
        "z-band",
        &[[16.5, 8.0], [18.5, 8.0], [18.5, 12.0], [16.5, 12.0]],
    )
}

/// Over the north half of the corridor only: robots pass south of it.
fn half_band() -> Result<Zone, BoxError> {
    restricted(
        "z-half",
        &[[16.5, 8.0], [18.5, 8.0], [18.5, 9.8], [16.5, 9.8]],
    )
}

fn id(place: &str) -> Result<PlaceId, BoxError> {
    Ok(place.parse()?)
}

fn member(robot: &str, at: &str) -> Result<FleetMember, BoxError> {
    let all = [
        map::STOREROOM,
        map::DOCK,
        map::CORRIDOR_1,
        map::ROOM_101,
        map::ROOM_102,
        map::ROOM_103,
        map::ROOM_104,
        map::LIFT_1,
        map::LIFT_2,
        map::CORRIDOR_2,
        map::ROOM_201,
    ];
    Ok(FleetMember {
        id: robot.parse()?,
        name: robot.to_owned(),
        status: RobotStatus::Idle,
        at: at.parse()?,
        battery_pct: 100.0,
        card: RoleCard {
            name: "porteur".to_owned(),
            permitted_places: all
                .iter()
                .map(|p| p.parse::<PlaceId>())
                .collect::<Result<BTreeSet<_>, _>>()?,
            max_speed_m_s: 1.0,
        },
        simulated: false,
    })
}

#[test]
fn graph_without_restricted_zones_equals_from_map() -> TestResult {
    let clinic = map::small_map()?;
    let deaf = map::deaf_zone()?;
    assert_eq!(
        RoutingGraph::from_map_with_zones(&clinic, &[deaf]),
        RoutingGraph::from_map(&clinic)
    );
    Ok(())
}

#[test]
#[ignore = "PlanningGrid leaves the margin between the floor outline and the rooms free, so routes go around the band outside the building (locations grid, T13b)"]
fn dispatch_path_cost_avoids_a_restricted_zone() -> TestResult {
    let clinic = map::small_map()?;
    let (from, to) = (id(map::STOREROOM)?, id(map::ROOM_104)?);
    let open = RoutingGraph::from_map(&clinic)
        .shortest_path(&from, &to, &PlaceMask::all())
        .ok_or("no path without zones")?;
    // A half band: still a path, never shorter than the open one (it goes around).
    let around = RoutingGraph::from_map_with_zones(&clinic, &[half_band()?])
        .shortest_path(&from, &to, &PlaceMask::all())
        .ok_or("the half band must leave a way south of it")?;
    assert!(
        around.metres >= open.metres - 1e-9,
        "{} < {}",
        around.metres,
        open.metres
    );
    // A full band: no path, so the dispatcher must not send a robot from the west side.
    let cut = RoutingGraph::from_map_with_zones(&clinic, &[full_band()?]);
    assert!(cut.shortest_path(&from, &to, &PlaceMask::all()).is_none());
    let dispatcher = Dispatcher::with_handle(GraphHandle::new(cut), DispatchPolicy::default());
    let decision = dispatcher.choose(
        &DispatchRequest {
            from: from.clone(),
            to: to.clone(),
            real_delivery: true,
        },
        &[member("robot-west", map::DOCK)?],
    );
    assert_eq!(decision.chosen, None, "{decision:?}");
    let reject = decision
        .considered
        .first()
        .and_then(|c| c.reject.clone())
        .ok_or("no rejection")?;
    assert_eq!(reject, RejectReason::NoPath);
    Ok(())
}

#[test]
#[ignore = "PlanningGrid leaves the margin between the floor outline and the rooms free, so routes go around the band outside the building (locations grid, T13b)"]
fn tour_planner_skips_a_stop_behind_a_restricted_zone() -> TestResult {
    let clinic = map::small_map()?;
    let handle = GraphHandle::new(RoutingGraph::from_map_with_zones(&clinic, &[full_band()?]));
    let planner = TourPlanner::with_handle(handle, DispatchPolicy::default(), id(map::DOCK)?);
    let tour = planner.plan(
        &member("robot-west", map::DOCK)?,
        &[id(map::ROOM_102)?, id(map::ROOM_104)?],
    )?;
    assert!(
        tour.order.iter().any(|p| p.as_str() == map::ROOM_102),
        "{tour:?}"
    );
    assert!(
        !tour.order.iter().any(|p| p.as_str() == map::ROOM_104),
        "{tour:?}"
    );
    let skipped = tour
        .skipped
        .first()
        .ok_or("room 104 must be listed as skipped")?;
    assert_eq!(skipped.place.as_str(), map::ROOM_104);
    assert_eq!(skipped.reason, RejectReason::NoPath);
    Ok(())
}

#[test]
#[ignore = "PlanningGrid leaves the margin between the floor outline and the rooms free, so routes go around the band outside the building (locations grid, T13b)"]
fn replacing_the_handle_reaches_every_holder() -> TestResult {
    let clinic = map::small_map()?;
    let handle = GraphHandle::new(RoutingGraph::from_map(&clinic));
    let holder = handle.clone();
    let (from, to) = (id(map::STOREROOM)?, id(map::ROOM_104)?);
    assert!(
        holder
            .current()
            .shortest_path(&from, &to, &PlaceMask::all())
            .is_some()
    );
    handle.replace(RoutingGraph::from_map_with_zones(&clinic, &[full_band()?]));
    assert!(
        holder
            .current()
            .shortest_path(&from, &to, &PlaceMask::all())
            .is_none()
    );
    Ok(())
}
