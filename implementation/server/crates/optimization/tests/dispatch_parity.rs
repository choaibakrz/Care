//! Task 13: the dispatcher on the small invented fixture map, and parity with the Python
//! reference on golden scenarios.
//!
//! Golden file format (`tests/golden/dispatch/*.json`, written by
//! `scripts/gen_dispatch_golden.py` from the Python world on `seed/clinic_map.json` and
//! `seed/role_cards.json`):
//!
//! ```json
//! { "name": "...", "marque": "inventé",
//!   "request": { "from": "storeroom", "to": "room-101", "real_delivery": true },
//!   "fleet": [ { "id": "robot-r1", "name": "R1", "status": "idle", "at": "dock",
//!                "battery_pct": 80.0, "card": "porteur", "simulated": false } ],
//!   "expected": { "chosen": "robot-r1", "rejects": { "robot-r2": "low_battery" },
//!                 "relay_via": null } }
//! ```
//! A reject kind is the `reason` tag of `RejectReason` (`simulated`, `faulted`, `busy`,
//! `card_refuses_place`, `no_path`, `low_battery`, `card_refuses_place_on_route`).

#[path = "../../../tests/support/map.rs"]
mod map;

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use domain::{PlaceId, RobotId, RobotStatus};
use locations::ClinicMap;
use optimization::{
    Decision, DispatchPolicy, DispatchRequest, Dispatcher, FleetMember, RejectReason, RoleCard,
    RoutingGraph,
};
use serde::Deserialize;

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn card(name: &str, places: &[&str]) -> Result<RoleCard, BoxError> {
    Ok(RoleCard {
        name: name.to_owned(),
        permitted_places: places
            .iter()
            .map(|p| p.parse::<PlaceId>())
            .collect::<Result<BTreeSet<_>, _>>()?,
        max_speed_m_s: 1.0,
    })
}

fn every_place() -> Result<RoleCard, BoxError> {
    card(
        "porteur",
        &[
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
        ],
    )
}

fn robot(id: &str, at: &str, battery_pct: f64) -> Result<FleetMember, BoxError> {
    Ok(FleetMember {
        id: id.parse()?,
        name: id.to_uppercase(),
        status: RobotStatus::Idle,
        at: at.parse()?,
        battery_pct,
        card: every_place()?,
        simulated: false,
    })
}

fn request(from: &str, to: &str) -> Result<DispatchRequest, BoxError> {
    Ok(DispatchRequest {
        from: from.parse()?,
        to: to.parse()?,
        real_delivery: true,
    })
}

fn dispatcher(map: &ClinicMap) -> Dispatcher {
    Dispatcher::new(RoutingGraph::from_map(map), DispatchPolicy::default())
}

fn reject_of<'a>(decision: &'a Decision, robot: &str) -> Option<&'a RejectReason> {
    decision
        .considered
        .iter()
        .find(|c| c.robot.as_str() == robot)
        .and_then(|c| c.reject.as_ref())
}

fn reject_kind(reason: &RejectReason) -> Result<String, BoxError> {
    let value = serde_json::to_value(reason)?;
    Ok(value
        .get("reason")
        .and_then(serde_json::Value::as_str)
        .ok_or("RejectReason has no reason tag")?
        .to_owned())
}

#[derive(Debug, Deserialize)]
struct Golden {
    name: String,
    request: GoldenRequest,
    fleet: Vec<GoldenRobot>,
    expected: GoldenExpected,
}

#[derive(Debug, Deserialize)]
struct GoldenRequest {
    from: PlaceId,
    to: PlaceId,
    real_delivery: bool,
}

#[derive(Debug, Deserialize)]
struct GoldenRobot {
    id: RobotId,
    name: String,
    status: RobotStatus,
    at: PlaceId,
    battery_pct: f64,
    card: String,
    simulated: bool,
}

#[derive(Debug, Deserialize)]
struct GoldenExpected {
    chosen: Option<RobotId>,
    rejects: BTreeMap<RobotId, String>,
    relay_via: Option<PlaceId>,
}

#[test]
#[ignore = "needs seed/role_cards.json and tests/golden/dispatch/*.json (scripts/gen_dispatch_golden.py), neither exists yet"]
fn golden_scenarios_match_python_choice_and_reject_kinds() -> TestResult {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    // The seed is a clinic plan since Task A4 (the console's demo clinic).
    let clinic = locations::load_plan(&root.join("../../seed/clinic_map.json"))?.validate()?;
    let cards = RoleCard::load_all(&root.join("../../seed/role_cards.json"))?;
    let dispatcher = dispatcher(&clinic);
    let mut files: Vec<_> = std::fs::read_dir(root.join("tests/golden/dispatch"))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|e| e == "json"))
        .collect();
    files.sort();
    assert!(!files.is_empty(), "no golden scenario found");
    for path in files {
        let golden: Golden = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
        let fleet = golden
            .fleet
            .iter()
            .map(|r| -> Result<FleetMember, BoxError> {
                Ok(FleetMember {
                    id: r.id.clone(),
                    name: r.name.clone(),
                    status: r.status,
                    at: r.at.clone(),
                    battery_pct: r.battery_pct,
                    card: cards
                        .get(&r.card)
                        .cloned()
                        .ok_or_else(|| format!("{}: unknown card {}", golden.name, r.card))?,
                    simulated: r.simulated,
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let decision = dispatcher.choose(
            &DispatchRequest {
                from: golden.request.from.clone(),
                to: golden.request.to.clone(),
                real_delivery: golden.request.real_delivery,
            },
            &fleet,
        );
        assert_eq!(decision.chosen, golden.expected.chosen, "{}", golden.name);
        for (robot, kind) in &golden.expected.rejects {
            let reason = reject_of(&decision, robot.as_str())
                .ok_or_else(|| format!("{}: {robot} not rejected", golden.name))?;
            assert_eq!(&reject_kind(reason)?, kind, "{}: {robot}", golden.name);
        }
        let relay_via = decision.relay.as_ref().map(|r| r.via.clone());
        assert_eq!(relay_via, golden.expected.relay_via, "{}", golden.name);
    }
    Ok(())
}

#[test]
fn nearest_free_robot_wins() -> TestResult {
    let clinic = map::small_map()?;
    let fleet = [
        robot("robot-r1", map::ROOM_104, 100.0)?,
        robot("robot-r2", map::DOCK, 100.0)?,
    ];
    let decision = dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_101)?, &fleet);
    assert_eq!(
        decision.chosen.as_ref().map(RobotId::as_str),
        Some("robot-r2")
    );
    Ok(())
}

#[test]
fn equal_distance_ties_break_by_robot_id() -> TestResult {
    let clinic = map::small_map()?;
    let fleet = [
        robot("robot-b", map::ROOM_102, 100.0)?,
        robot("robot-a", map::ROOM_102, 100.0)?,
    ];
    let decision = dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_101)?, &fleet);
    assert_eq!(
        decision.chosen.as_ref().map(RobotId::as_str),
        Some("robot-a")
    );
    Ok(())
}

#[test]
fn battery_exactly_at_threshold_is_rejected() -> TestResult {
    let clinic = map::small_map()?;
    let threshold = DispatchPolicy::default().battery_threshold_pct;
    let fleet = [robot("robot-r2", map::STOREROOM, threshold)?];
    let decision = dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_102)?, &fleet);
    assert_eq!(decision.chosen, None);
    assert!(
        matches!(
            reject_of(&decision, "robot-r2"),
            Some(RejectReason::LowBattery { .. })
        ),
        "{decision:?}"
    );
    Ok(())
}

#[test]
fn no_link_between_floors_means_no_path() -> TestResult {
    let clinic = map::small_map_without_lift()?;
    let fleet = [robot("robot-r2", map::STOREROOM, 100.0)?];
    let decision = dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_201)?, &fleet);
    assert_eq!(decision.chosen, None);
    assert_eq!(
        reject_of(&decision, "robot-r2"),
        Some(&RejectReason::NoPath)
    );
    let graph = RoutingGraph::from_map(&clinic);
    let path = graph.shortest_path(
        &map::STOREROOM.parse()?,
        &map::ROOM_201.parse()?,
        &optimization::PlaceMask::all(),
    );
    assert_eq!(path, None);
    Ok(())
}

#[test]
#[ignore = "the plan derives a direct link between every two places of a floor (ClinicPlan::validate), so no path crosses corridor-1; needs sparser derived links (locations, T13b)"]
fn card_refusing_a_traversed_place_rejects_the_robot() -> TestResult {
    let clinic = map::small_map()?;
    let mut member = robot("robot-r2", map::STOREROOM, 100.0)?;
    member.card = card(
        "no-corridor",
        &[map::STOREROOM, map::DOCK, map::ROOM_101, map::ROOM_102],
    )?;
    let decision = dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_101)?, &[member]);
    assert_eq!(decision.chosen, None);
    match reject_of(&decision, "robot-r2") {
        Some(RejectReason::CardRefusesPlaceOnRoute { place, card }) => {
            assert_eq!(place.as_str(), map::CORRIDOR_1);
            assert_eq!(card, "no-corridor");
        }
        other => return Err(format!("expected CardRefusesPlaceOnRoute, got {other:?}").into()),
    }
    Ok(())
}

fn unfit_fleet() -> Result<Vec<FleetMember>, BoxError> {
    let mut simulated = robot("robot-sim", map::DOCK, 100.0)?;
    simulated.simulated = true;
    let mut faulted = robot("robot-fault", map::DOCK, 100.0)?;
    faulted.status = RobotStatus::Fault;
    let mut busy = robot("robot-busy", map::DOCK, 100.0)?;
    busy.status = RobotStatus::Busy;
    let low = robot("robot-low", map::DOCK, 5.0)?;
    Ok(vec![simulated, faulted, busy, low])
}

#[test]
fn no_robot_fits_returns_none_with_every_reason_listed() -> TestResult {
    let clinic = map::small_map()?;
    let decision =
        dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_101)?, &unfit_fleet()?);
    assert_eq!(decision.chosen, None);
    assert_eq!(decision.relay, None);
    assert_eq!(decision.considered.len(), 4);
    assert_eq!(
        reject_of(&decision, "robot-sim"),
        Some(&RejectReason::Simulated)
    );
    assert!(matches!(
        reject_of(&decision, "robot-fault"),
        Some(RejectReason::Faulted { .. })
    ));
    assert!(matches!(
        reject_of(&decision, "robot-busy"),
        Some(RejectReason::Busy { .. })
    ));
    assert!(matches!(
        reject_of(&decision, "robot-low"),
        Some(RejectReason::LowBattery { .. })
    ));
    assert!(decision.considered.iter().all(|c| !c.fits));
    Ok(())
}

#[test]
fn explanation_names_each_rejected_robot_and_why() -> TestResult {
    let clinic = map::small_map()?;
    let decision =
        dispatcher(&clinic).choose(&request(map::STOREROOM, map::ROOM_101)?, &unfit_fleet()?);
    for consideration in &decision.considered {
        assert!(
            decision.explanation.contains(consideration.robot.as_str()),
            "{} missing from: {}",
            consideration.robot,
            decision.explanation
        );
        let why = consideration
            .reject
            .as_ref()
            .ok_or("a robot was rejected without a reason")?
            .to_string();
        assert!(
            decision.explanation.contains(&why),
            "'{why}' missing from: {}",
            decision.explanation
        );
    }
    Ok(())
}

#[test]
fn real_delivery_excludes_simulated() -> TestResult {
    let clinic = map::small_map()?;
    let mut near_simulated = robot("robot-sim", map::STOREROOM, 100.0)?;
    near_simulated.simulated = true;
    let far_real = robot("robot-real", map::ROOM_104, 100.0)?;
    let fleet = [near_simulated, far_real];
    let dispatcher = dispatcher(&clinic);
    let real = dispatcher.choose(&request(map::STOREROOM, map::ROOM_101)?, &fleet);
    assert_eq!(
        real.chosen.as_ref().map(RobotId::as_str),
        Some("robot-real")
    );
    assert_eq!(
        reject_of(&real, "robot-sim"),
        Some(&RejectReason::Simulated)
    );
    let mut rehearsal = request(map::STOREROOM, map::ROOM_101)?;
    rehearsal.real_delivery = false;
    let simulated = dispatcher.choose(&rehearsal, &fleet);
    assert_eq!(
        simulated.chosen.as_ref().map(RobotId::as_str),
        Some("robot-sim")
    );
    Ok(())
}
