//! Task A4 / 10b: clinic plans are validated as a whole and refused with every problem, each
//! with a path into the document. Task 13b: the planning grid of the seed plan (port of the
//! cases of `admin/src/lib/nav.test.ts`).
//!
//! The seed tests read the committed `seed/clinic_map.json` (exported from the console's
//! demo clinic by `scripts/export_console_clinic.mjs`). The JSON-shape checks run now; the
//! rest is ignored until `ClinicPlan::validate` (T10b) and the grid (T13b) are filled.

#[path = "../../../tests/support/map.rs"]
mod map;

use std::collections::BTreeSet;
use std::path::PathBuf;

use locations::grid::GRID_CELL_M;
use locations::{
    ClinicPlan, PlanErrors, PlanFloor, PlanPlace, PlanProp, PlanRoom, PlanWall, PlanningGrid,
    Point2, load_plan,
};
use serde_json::{Value, json};
use utoipa::PartialSchema;

type TestResult = Result<(), Box<dyn std::error::Error>>;

fn seed_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../seed/clinic_map.json")
}

fn seed_json() -> Result<Value, Box<dyn std::error::Error>> {
    Ok(serde_json::from_str(
        &std::fs::read_to_string(seed_path())?,
    )?)
}

fn array<'a>(value: &'a Value, key: &str) -> Result<&'a Vec<Value>, Box<dyn std::error::Error>> {
    value
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("no array `{key}`").into())
}

fn schema_keys<T: PartialSchema>() -> Result<BTreeSet<String>, Box<dyn std::error::Error>> {
    let schema = serde_json::to_value(T::schema())?;
    Ok(schema
        .get("properties")
        .and_then(Value::as_object)
        .ok_or("schema has no properties")?
        .keys()
        .cloned()
        .collect())
}

fn object_keys(value: &Value) -> BTreeSet<String> {
    value
        .as_object()
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default()
}

/// Every element of `list` uses only keys of the plan type `T`, and every required key.
fn assert_elements_match<T: PartialSchema>(list: &[Value], optional: &[&str]) -> TestResult {
    let allowed = schema_keys::<T>()?;
    for element in list {
        let keys = object_keys(element);
        assert!(
            keys.is_subset(&allowed),
            "{element} has keys outside {allowed:?}"
        );
        let missing: Vec<&String> = allowed
            .iter()
            .filter(|k| !keys.contains(*k) && !optional.contains(&k.as_str()))
            .collect();
        assert!(missing.is_empty(), "{element} misses {missing:?}");
    }
    Ok(())
}

/// The problems of a refused plan.
fn problems(plan: &Value) -> Result<PlanErrors, Box<dyn std::error::Error>> {
    let plan: ClinicPlan = serde_json::from_value(plan.clone())?;
    match plan.validate() {
        Ok(_) => Err("the plan was accepted".into()),
        Err(errors) => Ok(errors),
    }
}

fn has_problem(errors: &PlanErrors, path: &str, words: &str) -> bool {
    errors
        .0
        .iter()
        .any(|p| p.path == path && p.problem.contains(words))
}

// ---------------------------------------------------------------------------------------
// The exported seed (JSON shape only: runs now)

#[test]
fn seed_plan_matches_console_demo_clinic() -> TestResult {
    // Counts of `admin/src/mock/world.ts` as exported (see docs/progress.md, Task A4).
    let seed = seed_json()?;
    assert_eq!(seed.get("marque"), Some(&json!("inventé")));
    let floors = array(&seed, "floors")?;
    let ids: Vec<i64> = floors
        .iter()
        .filter_map(|f| f.get("id").and_then(Value::as_i64))
        .collect();
    assert_eq!(ids, vec![0, 2], "ground floor and floor 2");
    assert_eq!(array(&seed, "rooms")?.len(), 15);
    assert_eq!(array(&seed, "walls")?.len(), 27);
    assert_eq!(array(&seed, "places")?.len(), 19);
    assert_eq!(array(&seed, "props")?.len(), 51);
    for place in [
        "reception",
        "linen-shelf",
        "supply-a",
        "supply-b",
        "nurse-cabinet",
        "dock-a",
        "dock-w",
    ] {
        assert!(
            array(&seed, "places")?
                .iter()
                .any(|p| p.get("id") == Some(&json!(place))),
            "place {place} missing"
        );
    }
    Ok(())
}

#[test]
fn seed_plan_uses_exactly_the_plan_keys() -> TestResult {
    let seed = seed_json()?;
    let mut top = schema_keys::<ClinicPlan>()?;
    // `connections` is optional and the console's clinic has none (one floor never joins
    // the other: robots do not take the lift there).
    assert!(top.remove("connections"));
    assert_eq!(object_keys(&seed), top.clone());
    top.remove("marque");
    assert_eq!(
        top,
        ["floors", "name", "places", "props", "rooms", "walls"]
            .iter()
            .map(|k| (*k).to_owned())
            .collect()
    );
    assert_elements_match::<PlanFloor>(array(&seed, "floors")?, &[])?;
    assert_elements_match::<PlanRoom>(array(&seed, "rooms")?, &["label_at"])?;
    assert_elements_match::<PlanWall>(array(&seed, "walls")?, &[])?;
    assert_elements_match::<PlanPlace>(array(&seed, "places")?, &[])?;
    assert_elements_match::<PlanProp>(array(&seed, "props")?, &[])?;
    Ok(())
}

#[test]
fn seed_walls_have_unique_ids() -> TestResult {
    let seed = seed_json()?;
    let ids: Vec<&str> = array(&seed, "walls")?
        .iter()
        .filter_map(|w| w.get("id").and_then(Value::as_str))
        .collect();
    let unique: BTreeSet<&&str> = ids.iter().collect();
    assert_eq!(ids.len(), 27);
    assert_eq!(unique.len(), ids.len());
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Validation (T10b)

#[test]
fn seed_plan_validates_into_the_model() -> TestResult {
    let map = load_plan(&seed_path())?.validate()?;
    assert_eq!(map.floors().len(), 2);
    assert_eq!(map.places().len(), 19);
    assert!(
        map.obstacles().iter().any(|o| o.id == "elevator-0"),
        "the ground-floor lift is a closed obstacle"
    );
    Ok(())
}

#[test]
fn fixture_plan_validates() -> TestResult {
    let map = map::small_plan()?.validate()?;
    assert_eq!(map.places().len(), 11);
    Ok(())
}

#[test]
fn plan_with_crossing_room_edges_lists_the_problem_path() -> TestResult {
    let mut plan = map::small_plan_json();
    // rooms[3] (lift-1): a bowtie, edges 1–2 and 3–4 cross.
    map::set_at(
        &mut plan,
        "/rooms/3/polygon",
        json!([[26.0, 0.0], [30.0, 8.0], [30.0, 0.0], [26.0, 8.0]]),
    )?;
    let errors = problems(&plan)?;
    assert!(
        has_problem(&errors, "rooms[3].polygon", "edges 1–2 and 3–4 cross"),
        "{errors:?}"
    );
    Ok(())
}

#[test]
fn plan_with_place_outside_every_floor_is_refused() -> TestResult {
    let mut plan = map::small_plan_json();
    map::set_at(&mut plan, "/places/0/x", json!(80.0))?;
    map::set_at(&mut plan, "/places/1/floor", json!(7))?;
    let errors = problems(&plan)?;
    assert!(
        has_problem(&errors, "places[0]", "outside every floor"),
        "{errors:?}"
    );
    assert!(
        has_problem(&errors, "places[1]", "outside every floor"),
        "{errors:?}"
    );
    Ok(())
}

#[test]
fn plan_lists_every_problem_not_only_the_first() -> TestResult {
    let mut plan = map::small_plan_json();
    map::set_at(&mut plan, "/name", json!("  "))?;
    map::set_at(&mut plan, "/walls/2/id", json!("1-w1"))?;
    map::set_at(&mut plan, "/walls/4/points", json!([[1.0, 1.0]]))?;
    map::set_at(
        &mut plan,
        "/props",
        json!([{ "id": "p-1", "floor": 1, "kind": "bed", "x": 3.0, "y": 3.0, "width": 0.0, "depth": 1.0, "solid": true }]),
    )?;
    let errors = problems(&plan)?;
    assert!(has_problem(&errors, "name", ""), "{errors:?}");
    assert!(has_problem(&errors, "walls[2].id", "twice"), "{errors:?}");
    assert!(
        has_problem(&errors, "walls[4].points", "two points"),
        "{errors:?}"
    );
    assert!(has_problem(&errors, "props[0].width", ""), "{errors:?}");
    assert!(errors.0.len() >= 4, "{errors:?}");
    Ok(())
}

#[test]
fn room_on_unknown_floor_is_refused() -> TestResult {
    let mut plan = map::small_plan_json();
    map::set_at(&mut plan, "/rooms/0/floor", json!(9))?;
    let errors = problems(&plan)?;
    assert!(has_problem(&errors, "rooms[0].floor", "9"), "{errors:?}");
    Ok(())
}

#[test]
fn plan_with_unknown_key_does_not_deserialise() -> TestResult {
    // `deny_unknown_fields`: a typo is refused, never dropped. Runs now: the key is refused
    // before any id is read (keys are read in order: `connections` is empty here).
    let mut plan = map::small_plan_json_without_lift();
    plan.as_object_mut()
        .ok_or("the plan is an object")?
        .insert("florrs".to_owned(), json!([]));
    assert!(serde_json::from_value::<ClinicPlan>(plan).is_err());
    Ok(())
}

// ---------------------------------------------------------------------------------------
// The planning grid on the seed plan (T13b), from `admin/src/lib/nav.test.ts`

fn seed_grid(floor: i32) -> Result<PlanningGrid, Box<dyn std::error::Error>> {
    let map = load_plan(&seed_path())?.validate()?;
    Ok(PlanningGrid::build(&map, floor, &[])?)
}

#[test]
fn every_named_place_stands_on_free_ground() -> TestResult {
    let plan = load_plan(&seed_path())?;
    for floor in [0, 2] {
        let grid = seed_grid(floor)?;
        for place in plan.places.iter().filter(|p| p.floor == floor) {
            assert!(
                grid.is_free(&Point2::new(place.x, place.y)?),
                "{}",
                place.id
            );
        }
    }
    Ok(())
}

#[test]
fn grid_cells_are_a_fifth_of_a_metre() -> TestResult {
    let grid = seed_grid(0)?;
    // 24 m by 14 m floors, 0.2 m cells (nav.ts).
    assert_eq!(grid.columns(), 120);
    assert_eq!(grid.rows(), 70);
    assert!((GRID_CELL_M - 0.2).abs() < f64::EPSILON);
    Ok(())
}

#[test]
fn inside_the_elevator_is_blocked() -> TestResult {
    let grid = seed_grid(0)?;
    assert!(!grid.is_free(&Point2::new(8.5, 2.5)?));
    Ok(())
}
