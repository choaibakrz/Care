//! Step C1: an admin gives one robot a task (`robot_id`), follows a staff tablet, and re-arms
//! a robot after an emergency stop. Against the mock with its simulated robots.

mod support;

use serde_json::{Value, json};
use support::{MockApp, Res, TestResult, call, get, post_json};

const ADMIN: Option<&str> = Some("mock-admin");
const NURSE: Option<&str> = Some("mock-nurse");

async fn robot(app: &MockApp, id: &str) -> Res<Value> {
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    robots
        .body
        .as_array()
        .and_then(|list| list.iter().find(|r| r.get("id") == Some(&json!(id))))
        .cloned()
        .ok_or_else(|| format!("robot {id} not listed").into())
}

#[tokio::test]
async fn an_admin_gives_a_robot_a_go_to_and_others_may_not() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({ "kind": "go_to", "to_place": "room-12", "robot_id": "r3" });
    let refused = call(&app.app, post_json("/tasks", NURSE, &body)?).await?;
    assert_eq!(refused.status.as_u16(), 403, "{}", refused.body);
    let created = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert_eq!(created.status.as_u16(), 201, "{}", created.body);
    let id = created.body.get("id").cloned().unwrap_or(Value::Null);
    assert_eq!(robot(&app, "r3").await?.get("task_id"), Some(&id));
    let again = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert_eq!(again.error_code(), Some("robot_busy"), "{}", again.body);
    Ok(())
}

#[tokio::test]
async fn an_estopped_robot_refuses_tasks_until_an_admin_re_arms_it() -> TestResult {
    let app = MockApp::start()?;
    let stop = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert!(stop.status.is_success(), "{}", stop.body);
    let body = json!({ "kind": "go_to", "to_place": "room-12", "robot_id": "r1" });
    let refused = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert_eq!(
        refused.error_code(),
        Some("estop_latched"),
        "{}",
        refused.body
    );
    let resume = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "resume" }))?,
    )
    .await?;
    assert!(resume.status.is_success(), "{}", resume.body);
    let created = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert_eq!(created.status.as_u16(), 201, "{}", created.body);
    Ok(())
}

#[tokio::test]
async fn a_robot_follows_a_staff_tablet_until_cancelled() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({ "kind": "follow", "target_device": "tab-dr-a", "robot_id": "r2" });
    let created = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert_eq!(created.status.as_u16(), 201, "{}", created.body);
    assert_eq!(created.body.get("target_label"), Some(&json!("Dr. A")));
    assert_eq!(created.body.get("state"), Some(&json!("en_route")));
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?;
    // Bedside tablets cannot be followed.
    let bed = json!({ "kind": "follow", "target_device": "tab-bed-12", "robot_id": "r3" });
    let refused = call(&app.app, post_json("/tasks", ADMIN, &bed)?).await?;
    assert_eq!(refused.status.as_u16(), 422, "{}", refused.body);
    let cancelled = call(
        &app.app,
        post_json(&format!("/tasks/{id}/cancel"), ADMIN, &json!({}))?,
    )
    .await?;
    assert_eq!(cancelled.body.get("state"), Some(&json!("cancelled")));
    assert_eq!(robot(&app, "r2").await?.get("task_id"), Some(&Value::Null));
    Ok(())
}

#[tokio::test]
async fn an_emergency_stop_ends_a_follow_and_nothing_is_sent_after_the_re_arm() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({ "kind": "follow", "target_device": "tab-dr-a", "robot_id": "r2" });
    let created = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    let id = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("no id")?;
    let stop = call(
        &app.app,
        post_json("/robots/r2/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert!(stop.status.is_success(), "{}", stop.body);
    // The tablet changes room while the robot is stopped.
    for (path, body) in [
        ("/devices/tab-dr-a/disconnect", json!({})),
        (
            "/devices/tab-dr-a/assign",
            json!({ "kind": "staff", "label": "Dr. A", "speciality": "Cardiology", "place": "room-14" }),
        ),
    ] {
        let reply = call(&app.app, post_json(path, ADMIN, &body)?).await?;
        assert!(reply.status.is_success(), "{}", reply.body);
    }
    tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
    let task = call(&app.app, get(&format!("/tasks/{id}"), ADMIN)?).await?;
    assert_eq!(
        task.body.get("state"),
        Some(&json!("failed")),
        "{}",
        task.body
    );
    assert!(
        task.body.get("reason").is_some_and(Value::is_string),
        "{}",
        task.body
    );
    let resume = call(
        &app.app,
        post_json("/robots/r2/command", ADMIN, &json!({ "name": "resume" }))?,
    )
    .await?;
    assert!(resume.status.is_success(), "{}", resume.body);
    tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
    assert_eq!(robot(&app, "r2").await?.get("task_id"), Some(&Value::Null));
    Ok(())
}
