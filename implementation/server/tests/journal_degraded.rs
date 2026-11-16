//! Task 9, degraded mode: when the journal cannot write, mutations get 503 but the emergency
//! stop is still sent, and its record goes to the emergency fallback file.

mod support;

use std::time::Duration;

use axum::http::StatusCode;
use serde_json::json;
use support::{RealApp, TestResult, WsClient, hello, post_json};

#[tokio::test]
async fn journal_failure_returns_503_on_mutations_but_estop_still_goes_out() -> TestResult {
    let app = RealApp::start().await?;
    let robot_token = app.add_robot("robot-r2", true).await?;
    let admin = app.admin_token().await?;
    let server = app.serve().await?;
    let mut robot =
        WsClient::connect_with_token(&server.ws_url("/ws/robot/robot-r2"), &robot_token).await?;
    robot
        .send_json(&hello("robot-r2", true, None, support::start_time()?))
        .await?;

    app.journal.close().await?;
    assert!(!app.state.journal.is_writable());

    let task = json!({ "kind": "go_to", "to_place": "room-101" });
    let refused = app.call(post_json("/tasks", Some(&admin), &task)?).await?;
    assert_eq!(refused.status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(refused.error_code(), Some("journal_unavailable"));
    assert!(
        refused
            .error_message()
            .starts_with("Actions are paused because they cannot be recorded."),
        "{}",
        refused.error_message()
    );

    let estop = app
        .call(post_json(
            "/robots/robot-r2/command",
            Some(&admin),
            &json!({ "name": "estop" }),
        )?)
        .await?;
    assert_eq!(estop.status, StatusCode::OK, "{}", estop.body);
    assert_eq!(estop.body.get("accepted"), Some(&json!(true)));
    let command = robot
        .next_of_type("command", Duration::from_secs(2))
        .await?;
    assert_eq!(command.get("name"), Some(&json!("estop")));

    let fallback = std::fs::read_to_string(&app.config.journal.emergency_fallback)?;
    assert!(fallback.contains("robot-r2"), "{fallback}");
    Ok(())
}
