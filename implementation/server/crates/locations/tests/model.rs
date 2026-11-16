//! Task 10 / 10b: the model (`ClinicMap`) derived from the fixture plan, its validation and
//! accessors. Since ruling R14 the model is always derived from a `ClinicPlan`, so these
//! tests edit the plan form of the fixture (before A4 they edited a model file).

#[path = "../../../tests/support/map.rs"]
mod map;

use locations::{ClinicPlan, PlanErrors, Point2, Polygon, Zone};
use serde_json::{Value, json};

type TestResult = Result<(), Box<dyn std::error::Error>>;

fn array_at<'a>(
    json: &'a mut Value,
    pointer: &str,
) -> Result<&'a mut Vec<Value>, Box<dyn std::error::Error>> {
    json.pointer_mut(pointer)
        .and_then(Value::as_array_mut)
        .ok_or_else(|| format!("no array at {pointer}").into())
}

/// The problems of a refused plan.
fn refused(plan: Value) -> Result<PlanErrors, Box<dyn std::error::Error>> {
    let plan: ClinicPlan = serde_json::from_value(plan)?;
    plan.validate()
        .err()
        .ok_or_else(|| "the plan was accepted".into())
}

#[test]
fn room_outside_floor_outline_is_refused_naming_the_room() -> TestResult {
    let mut json = map::small_plan_json();
    map::set_at(
        &mut json,
        "/rooms/7/polygon",
        json!([[20.0, 12.0], [40.0, 12.0], [40.0, 20.0], [20.0, 20.0]]),
    )?;
    let errors = refused(json)?;
    assert!(
        errors
            .0
            .iter()
            .any(|p| p.path == "rooms[7].polygon" && p.problem.contains("outside")),
        "{errors:?}"
    );
    Ok(())
}

#[test]
fn connection_to_unknown_place_is_refused() -> TestResult {
    let mut json = map::small_plan_json();
    array_at(&mut json, "/connections")?
        .push(json!({ "from": map::CORRIDOR_1, "to": "nowhere", "metres": 3.0 }));
    let errors = refused(json)?;
    assert!(
        errors
            .0
            .iter()
            .any(|p| p.path == "connections[1].to" && p.problem.contains("nowhere")),
        "{errors:?}"
    );
    Ok(())
}

#[test]
fn duplicate_place_id_is_refused() -> TestResult {
    let mut json = map::small_plan_json();
    array_at(&mut json, "/places")?.push(json!({
        "id": map::ROOM_101, "label": "Copy", "floor": 2, "x": 5.0, "y": 16.0, "kind": "room"
    }));
    let errors = refused(json)?;
    assert!(
        errors
            .0
            .iter()
            .any(|p| p.path == "places[11].id" && p.problem.contains("twice")),
        "{errors:?}"
    );
    Ok(())
}

#[test]
fn zones_containing_returns_overlapping_zones() -> TestResult {
    let restricted = Zone {
        id: "z-restricted".parse()?,
        kind: domain::ZoneKind::Restricted,
        floor: 1,
        polygon: Polygon::from_pairs(&[[5.0, 13.0], [15.0, 13.0], [15.0, 19.0], [5.0, 19.0]])?,
        version: 1,
    };
    let clinic = map::small_map()?.with_zones(vec![map::deaf_zone()?, restricted])?;
    let mut both: Vec<String> = clinic
        .zones_containing(1, &Point2::new(7.0, 16.0)?)
        .into_iter()
        .map(|z| z.id.to_string())
        .collect();
    both.sort();
    assert_eq!(
        both,
        vec!["z-deaf-101".to_owned(), "z-restricted".to_owned()]
    );
    let one: Vec<String> = clinic
        .zones_containing(1, &Point2::new(2.0, 16.0)?)
        .into_iter()
        .map(|z| z.id.to_string())
        .collect();
    assert_eq!(one, vec![map::DEAF_ZONE.to_owned()]);
    assert!(
        clinic
            .zones_containing(2, &Point2::new(7.0, 16.0)?)
            .is_empty()
    );
    Ok(())
}

#[test]
fn version_changes_when_a_wall_moves() -> TestResult {
    let original = map::small_map()?;
    let same = map::small_map()?;
    assert_eq!(original.version(), same.version());
    let mut json = map::small_plan_json();
    map::set_at(
        &mut json,
        "/walls/0/points",
        json!([[10.5, 12.0], [10.5, 20.0]]),
    )?;
    let moved = serde_json::from_value::<ClinicPlan>(json)?.validate()?;
    assert_ne!(original.version(), moved.version());
    Ok(())
}

#[test]
fn lift_connection_is_the_only_link_between_floors() -> TestResult {
    let with = map::small_map()?;
    let without = map::small_map_without_lift()?;
    let crossing = |clinic: &locations::ClinicMap| {
        clinic
            .links()
            .iter()
            .filter(|l| {
                let floor = |id| clinic.place(id).map(|p| p.floor);
                floor(&l.from) != floor(&l.to)
            })
            .count()
    };
    assert_eq!(crossing(&with), 1);
    assert_eq!(crossing(&without), 0);
    Ok(())
}
