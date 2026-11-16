//! Task A4 / 5b: `clinic-server --demo`, the server-side port of the console's demo
//! (`admin/src/mock/sim*.ts`) on the seed plan and `seed/demo_fleet.json`.
//!
//! The seed file check runs now; the demo itself is ignored until Task 5b (it also needs the
//! plan validation of 10b and the route preview of 13b). Nothing here is tested against a
//! real robot.

mod support;

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::time::Duration;

use axum::http::StatusCode;
use clinic_server::services::demo::{DEFAULT_DEMO_SEED, DemoFleet, SIMULATED_SUFFIX};
use domain::Actor;
use realtime::{SIMULATED_REQUEST_LABEL, requester_label};
use serde_json::{Value, json};
use support::{RealApp, Res, TestResult, get};

fn seed_file(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("seed")
        .join(name)
}

fn read_json(name: &str) -> Res<Value> {
    Ok(serde_json::from_str(&std::fs::read_to_string(seed_file(
        name,
    ))?)?)
}

fn ids(list: Option<&Value>, key: &str) -> BTreeSet<String> {
    list.and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|i| i.get(key).and_then(Value::as_str).map(str::to_owned))
                .collect()
        })
        .unwrap_or_default()
}

/// `(x, y)` of a `robot.updated` event.
fn position(event: &Value) -> Option<(f64, f64)> {
    let pos = event.pointer("/robot/pos")?;
    Some((pos.get("x")?.as_f64()?, pos.get("y")?.as_f64()?))
}

#[test]
fn demo_fleet_matches_console_seed() -> TestResult {
    let fleet = read_json("demo_fleet.json")?;
    let plan = read_json("clinic_map.json")?;
    assert_eq!(fleet.get("marque"), Some(&json!("inventé")));
    assert_eq!(
        ids(fleet.get("robots"), "id"),
        ["r1", "r2", "r3", "r4"]
            .iter()
            .map(|s| (*s).to_owned())
            .collect()
    );
    let places = ids(plan.get("places"), "id");
    // Every home, shelf and destination is a place of the seed plan.
    let homes = ids(fleet.get("robots"), "home");
    let shelves = ids(fleet.get("items"), "place");
    assert!(homes.is_subset(&places), "{homes:?}");
    assert!(shelves.is_subset(&places), "{shelves:?}");
    let destinations = fleet
        .get("destinations")
        .and_then(Value::as_object)
        .ok_or("no destinations")?;
    for (shelf, targets) in destinations {
        assert!(places.contains(shelf), "{shelf}");
        for target in targets.as_array().ok_or("destinations are lists")? {
            let target = target.as_str().ok_or("destination is a string")?;
            assert!(places.contains(target), "{target}");
        }
    }
    assert_eq!(
        fleet.get("items").and_then(Value::as_array).map(Vec::len),
        Some(10)
    );
    assert_eq!(
        fleet.get("zones").and_then(Value::as_array).map(Vec::len),
        Some(3)
    );
    Ok(())
}

#[test]
fn demo_fleet_loads() -> TestResult {
    let fleet = DemoFleet::load(&seed_file("demo_fleet.json"))?;
    assert_eq!(fleet.robots.len(), 4);
    assert_eq!(fleet.marque, "inventé");
    Ok(())
}

#[tokio::test]
async fn health_reports_demo_mode() -> TestResult {
    let app = RealApp::start_demo(DEFAULT_DEMO_SEED).await?;
    let reply = app.call(get("/health", None)?).await?;
    assert_eq!(reply.status, StatusCode::OK);
    assert_eq!(reply.body.get("mode"), Some(&json!("demo")));
    Ok(())
}

#[tokio::test]
async fn demo_mode_labels_every_robot_simulated() -> TestResult {
    let app = RealApp::start_demo(DEFAULT_DEMO_SEED).await?;
    let admin = app.admin_token().await?;
    let reply = app.call(get("/robots", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let robots = reply.body.as_array().ok_or("robots is a list")?;
    assert_eq!(robots.len(), 4, "{}", reply.body);
    for robot in robots {
        assert_eq!(robot.get("simulated"), Some(&json!(true)), "{robot}");
        let name = robot
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default();
        assert!(name.ends_with(SIMULATED_SUFFIX), "{name}");
    }
    Ok(())
}

#[tokio::test]
async fn demo_mode_robots_move_and_send_robot_updated_every_second() -> TestResult {
    let app = RealApp::start_demo(DEFAULT_DEMO_SEED).await?;
    let server = app.serve().await?;
    let mut socket = app.app_socket(&server).await?;
    let mut seen: BTreeMap<String, Vec<(f64, f64)>> = BTreeMap::new();
    let deadline = tokio::time::Instant::now() + Duration::from_secs(15);
    while tokio::time::Instant::now() < deadline {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let Ok(event) = socket.next_of_type("robot.updated", left).await else {
            break;
        };
        let id = event
            .pointer("/robot/id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        if let Some(at) = position(&event) {
            seen.entry(id).or_default().push(at);
        }
    }
    // Heartbeat: at least one `robot.updated` per robot per second (15 s: at least 12 each).
    assert_eq!(seen.len(), 4, "{:?}", seen.keys());
    for (robot, positions) in &seen {
        assert!(
            positions.len() >= 12,
            "{robot}: {} updates",
            positions.len()
        );
    }
    // Requests appear by themselves (the first after about 2 s), so some robot drives.
    let moved = seen.values().any(|positions| {
        positions
            .first()
            .zip(positions.last())
            .is_some_and(|((x0, y0), (x1, y1))| (x1 - x0).hypot(y1 - y0) > 1.0)
    });
    assert!(moved, "no robot moved more than 1 m in 15 s");
    Ok(())
}

#[tokio::test]
async fn demo_requests_say_simulated() -> TestResult {
    let app = RealApp::start_demo(DEFAULT_DEMO_SEED).await?;
    let admin = app.admin_token().await?;
    tokio::time::sleep(Duration::from_secs(4)).await;
    let reply = app.call(get("/tasks", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let items = reply
        .body
        .get("items")
        .and_then(Value::as_array)
        .ok_or("no items")?;
    assert!(!items.is_empty(), "no request was generated in 4 s");
    // Ruling R15: created as `Actor::System("demo")`, shown as exactly "SIMULATED request".
    for task in items {
        assert_eq!(
            task.get("requested_by"),
            Some(&json!(SIMULATED_REQUEST_LABEL)),
            "{task}"
        );
    }
    Ok(())
}

#[test]
fn demo_is_a_known_system_actor() {
    assert!(Actor::KNOWN_SYSTEM_NAMES.contains(&"demo"));
    assert_eq!(SIMULATED_REQUEST_LABEL, "SIMULATED request");
}

#[test]
fn demo_requests_are_labelled_simulated_and_other_system_actors_server() -> TestResult {
    assert_eq!(
        requester_label(&Actor::System("demo"), None),
        SIMULATED_REQUEST_LABEL
    );
    assert_eq!(requester_label(&Actor::System("scheduler"), None), "server");
    assert_eq!(requester_label(&Actor::System("server"), None), "server");
    let label = domain::OwnerLabel::new("Nurse station 2")?;
    assert_eq!(
        requester_label(&Actor::User("u-nurse".parse()?), Some(&label)),
        "Nurse station 2"
    );
    Ok(())
}
