//! The live server's simulated "happy" robots: listed, teleported, sent home in an
//! emergency, deaf in a deaf zone.

mod support;

use std::time::Duration;

use axum::http::StatusCode;
use clinic_server::sim::fleet::{HappyRobotsDeps, start_happy_robots};
use serde_json::{Value, json};
use storage::SqliteRobotRepository;
use support::{RealApp, Res, TestResult, get, post_json, put_json};
use tokio::task::JoinHandle;

/// Starts the two simulated robots of a fresh live app.
async fn start_robots(app: &RealApp) -> Res<Vec<JoinHandle<()>>> {
    let fleet = app
        .state
        .robots
        .sim_fleet()
        .ok_or("the live wiring has no simulated fleet")?;
    let repo = SqliteRobotRepository::new(app.db.clone());
    Ok(start_happy_robots(
        HappyRobotsDeps {
            fleet,
            hub: app.hub.clone(),
            robots: app.state.robots.clone(),
            clock: app.state.clock.clone(),
            repo: &repo,
        },
        2,
    )
    .await?)
}

/// `GET /robots`, the simulated ones only.
async fn sim_robots(app: &RealApp, token: &str) -> Res<Vec<Value>> {
    let reply = app.call(get("/robots", Some(token))?).await?;
    assert_eq!(reply.status, StatusCode::OK);
    Ok(reply
        .body
        .as_array()
        .ok_or("robots is not a list")?
        .iter()
        .filter(|robot| {
            robot
                .get("id")
                .and_then(Value::as_str)
                .is_some_and(|id| id.starts_with("sim-"))
        })
        .cloned()
        .collect())
}

/// Polls `GET /robots` until `check` holds for some simulated robot (5 s at most).
async fn wait_for(app: &RealApp, token: &str, check: impl Fn(&Value) -> bool) -> Res<Value> {
    for _ in 0..50 {
        if let Some(robot) = sim_robots(app, token).await?.into_iter().find(&check) {
            return Ok(robot);
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    Err("no simulated robot reached the expected state".into())
}

#[tokio::test]
async fn two_simulated_robots_are_listed_and_one_can_be_teleported() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let handles = start_robots(&app).await?;
    let robots = sim_robots(&app, &admin).await?;
    assert_eq!(robots.len(), 2, "{robots:?}");
    for robot in &robots {
        assert_eq!(robot.get("simulated"), Some(&json!(true)));
        assert_eq!(robot.get("connected"), Some(&json!(true)));
        assert!(robot.get("mood").and_then(Value::as_str).is_some());
    }
    let moved = app
        .call(post_json(
            "/robots/sim-pip/teleport",
            Some(&admin),
            &json!({ "x": 12.0, "y": 10.0, "floor": "1" }),
        )?)
        .await?;
    assert_eq!(moved.status, StatusCode::OK, "{:?}", moved.body);
    assert_eq!(moved.body.pointer("/pos/x"), Some(&json!(12.0)));
    let outside = app
        .call(post_json(
            "/robots/sim-pip/teleport",
            Some(&admin),
            &json!({ "x": 500.0, "y": 10.0, "floor": "1" }),
        )?)
        .await?;
    assert_eq!(outside.status, StatusCode::UNPROCESSABLE_ENTITY);
    app.add_robot("real-1", false).await?;
    let real = app
        .call(post_json(
            "/robots/real-1/teleport",
            Some(&admin),
            &json!({ "x": 12.0, "y": 10.0, "floor": 1 }),
        )?)
        .await?;
    assert_eq!(real.status, StatusCode::CONFLICT);
    assert_eq!(real.error_code(), Some("not_simulated"));
    handles.iter().for_each(JoinHandle::abort);
    Ok(())
}

#[tokio::test]
async fn in_an_emergency_the_robots_go_home() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let handles = start_robots(&app).await?;
    let home = app
        .call(put_json(
            "/fleet/home",
            Some(&admin),
            &json!({ "place_id": "dock" }),
        )?)
        .await?;
    assert_eq!(home.status, StatusCode::OK, "{:?}", home.body);
    assert_eq!(home.body.get("place_id"), Some(&json!("dock")));
    assert_eq!(home.body.get("floor"), Some(&json!("1")));
    let read = app.call(get("/fleet/home", Some(&admin))?).await?;
    assert_eq!(read.body, home.body);
    // Put a robot far from home so it has a way to go.
    let moved = app
        .call(post_json(
            "/robots/sim-pip/teleport",
            Some(&admin),
            &json!({ "x": 25.0, "y": 10.0, "floor": 1 }),
        )?)
        .await?;
    assert_eq!(moved.status, StatusCode::OK, "{:?}", moved.body);
    let mode = app
        .call(put_json(
            "/system/mode",
            Some(&admin),
            &json!({ "mode": "emergency", "reason": "drill" }),
        )?)
        .await?;
    assert_eq!(mode.status, StatusCode::OK, "{:?}", mode.body);
    let going = wait_for(&app, &admin, |robot| {
        robot.get("going_home") == Some(&json!(true))
    })
    .await?;
    assert_eq!(going.get("mood"), Some(&json!("alarm")));
    handles.iter().for_each(JoinHandle::abort);
    Ok(())
}

#[tokio::test]
async fn a_robot_in_a_deaf_zone_closes_its_microphone() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let handles = start_robots(&app).await?;
    let zone = json!({
        "id": "z-quiet",
        "name": "Quiet room",
        "kind": "deaf",
        "floor": 1,
        "polygon": [[1.0, 13.0], [9.0, 13.0], [9.0, 19.0], [1.0, 19.0]],
    });
    let stored = app
        .call(put_json("/zones/z-quiet", Some(&admin), &zone)?)
        .await?;
    assert!(stored.status.is_success(), "{:?}", stored.body);
    // Stop it first so it stays in the zone.
    let paused = app
        .call(post_json(
            "/robots/sim-sunny/command",
            Some(&admin),
            &json!({ "name": "pause" }),
        )?)
        .await?;
    assert_eq!(paused.status, StatusCode::OK, "{:?}", paused.body);
    let moved = app
        .call(post_json(
            "/robots/sim-sunny/teleport",
            Some(&admin),
            &json!({ "x": 5.0, "y": 16.0, "floor": "1" }),
        )?)
        .await?;
    assert_eq!(moved.status, StatusCode::OK, "{:?}", moved.body);
    assert_eq!(moved.body.get("in_deaf_zone"), Some(&json!(true)));
    tokio::time::sleep(Duration::from_millis(1500)).await;
    let sunny = wait_for(&app, &admin, |robot| {
        robot.get("id") == Some(&json!("sim-sunny"))
    })
    .await?;
    assert_eq!(sunny.get("mic_open"), Some(&json!(false)), "{sunny:?}");
    assert_eq!(sunny.get("in_deaf_zone"), Some(&json!(true)), "{sunny:?}");
    handles.iter().for_each(JoinHandle::abort);
    Ok(())
}

#[tokio::test]
async fn a_busy_simulated_robot_refuses_a_second_task_and_keeps_the_first() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let handles = start_robots(&app).await?;
    let first = app
        .call(post_json(
            "/tasks",
            Some(&admin),
            &json!({ "kind": "go_to", "to_place": support::map::ROOM_104, "robot_id": "sim-pip" }),
        )?)
        .await?;
    assert_eq!(first.status, StatusCode::CREATED, "{:?}", first.body);
    let first_id = first
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no task id")?;
    // At once: the first task is stored as assigned before the order leaves.
    let second = app
        .call(post_json(
            "/tasks",
            Some(&admin),
            &json!({ "kind": "go_to", "to_place": support::map::ROOM_102, "robot_id": "sim-pip" }),
        )?)
        .await?;
    assert_eq!(second.status, StatusCode::CONFLICT, "{:?}", second.body);
    let task = app
        .call(get(&format!("/tasks/{first_id}"), Some(&admin))?)
        .await?;
    assert_ne!(
        task.body.get("state"),
        Some(&json!("cancelled")),
        "{:?}",
        task.body
    );
    handles.iter().for_each(JoinHandle::abort);
    Ok(())
}
