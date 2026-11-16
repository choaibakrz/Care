//! Task 4: the API shell with the mock services, through the security stack, no network.

mod support;

use axum::http::{Method, StatusCode};
use clinic_server::openapi::ApiDoc;
use serde_json::{Value, json};
use support::{MockApp, TestResult, call, get, post_json, post_raw, put_json, request};
use utoipa::OpenApi as _;

const ADMIN: Option<&str> = Some("mock-admin");

/// Every path of architecture.md C3 (with the Task A4, A6 and A7 additions), plus `/health`.
const C3_PATHS: &[&str] = &[
    "/health",
    "/auth/login",
    "/me",
    "/me/location",
    "/tasks",
    "/tasks/{id}",
    "/tasks/{id}/cancel",
    "/inventory",
    "/inventory/{item}/adjust",
    "/map",
    "/zones",
    "/zones/{id}",
    "/robots",
    "/robots/{id}/command",
    "/schedules",
    "/schedules/{id}",
    "/audit",
    "/clinics",
    "/clinics/{id}",
    "/clinics/{id}/activate",
    "/tasks/{id}/route",
    "/stats/heat",
    "/brain/translate",
    "/brain/simplify",
    "/brain/summarise",
    "/brain/report",
    "/brain/health",
    "/auth/derivation",
    "/auth/enrol",
    "/admin/enrolment-codes",
    "/admin/accounts",
    "/admin/accounts/{account_tag}",
    "/robots/{id}/commands/{command_id}/revert",
];

#[tokio::test]
async fn health_returns_200() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/health", None)?).await?;
    assert_eq!(reply.status, StatusCode::OK);
    assert!(
        reply.body.get("journal_writable").is_some(),
        "{}",
        reply.body
    );
    Ok(())
}

#[tokio::test]
async fn docs_page_is_served() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/docs", None)?).await?;
    assert_eq!(reply.status, StatusCode::OK);
    let content_type = reply.header("content-type").unwrap_or_default();
    assert!(content_type.starts_with("text/html"), "{content_type}");
    Ok(())
}

#[test]
fn openapi_lists_every_c3_path() -> TestResult {
    let doc = serde_json::to_value(ApiDoc::openapi())?;
    let paths = doc
        .get("paths")
        .and_then(Value::as_object)
        .ok_or("the OpenAPI document has no paths")?;
    let missing: Vec<&str> = C3_PATHS
        .iter()
        .copied()
        .filter(|path| !paths.contains_key(*path))
        .collect();
    assert!(
        missing.is_empty(),
        "paths missing from OpenAPI: {missing:?}"
    );
    Ok(())
}

#[tokio::test]
async fn unknown_path_returns_error_body_with_code_not_found() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/no/such/place", ADMIN)?).await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND);
    assert_eq!(reply.error_code(), Some("not_found"));
    assert!(!reply.error_message().is_empty());
    Ok(())
}

#[tokio::test]
async fn wrong_method_returns_405_error_body() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, request(Method::DELETE, "/health", ADMIN, None)?).await?;
    assert_eq!(reply.status, StatusCode::METHOD_NOT_ALLOWED);
    assert_eq!(reply.error_code(), Some("method_not_allowed"));
    Ok(())
}

#[tokio::test]
async fn invalid_json_returns_400_with_position_in_message() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        post_raw("/tasks", ADMIN, r#"{"kind": "fetch", "to_place": "#)?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::BAD_REQUEST);
    assert_eq!(reply.error_code(), Some("invalid_json"));
    assert!(
        reply.error_message().contains("column"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn missing_field_names_the_field() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({ "kind": "fetch", "item": "blanket" });
    let reply = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(reply.error_code(), Some("invalid_field"));
    assert!(
        reply.error_message().contains("`to_place`"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn every_parameterised_route_matches_a_real_id() -> TestResult {
    let app = MockApp::start()?;
    let zone = json!({
        "id": "z-1", "name": "Room 101 quiet", "kind": "deaf", "floor": 1,
        "polygon": [[1.0, 13.0], [9.0, 13.0], [9.0, 19.0]]
    });
    let schedule = json!({ "enabled": true, "time": "02:30" });
    let calls = vec![
        get("/tasks/t-1", ADMIN)?,
        post_json("/tasks/t-1/cancel", ADMIN, &json!({}))?,
        post_json(
            "/inventory/blanket/adjust",
            ADMIN,
            &json!({ "delta": 1, "reason": "restock" }),
        )?,
        put_json("/zones/z-1", ADMIN, &zone)?,
        request(Method::DELETE, "/zones/z-1", ADMIN, None)?,
        post_json(
            "/robots/robot-r2/command",
            ADMIN,
            &json!({ "name": "pause" }),
        )?,
        put_json("/schedules/night-restock", ADMIN, &schedule)?,
        post_json("/incidents/1/ack", ADMIN, &json!({}))?,
        post_json("/incidents/1/close", ADMIN, &json!({}))?,
    ];
    for req in calls {
        let path = req.uri().path().to_owned();
        let reply = call(&app.app, req).await?;
        assert_ne!(
            reply.status,
            StatusCode::NOT_FOUND,
            "{path}: {}",
            reply.body
        );
        assert_ne!(
            reply.status,
            StatusCode::METHOD_NOT_ALLOWED,
            "{path}: {}",
            reply.body
        );
    }
    Ok(())
}

#[tokio::test]
async fn mock_task_creation_returns_requested_state() -> TestResult {
    let app = MockApp::start()?;
    let body = json!({ "kind": "fetch", "item": "blanket", "from_place": "storeroom", "to_place": "room-101" });
    let reply = call(&app.app, post_json("/tasks", ADMIN, &body)?).await?;
    assert!(
        reply.status.is_success(),
        "{}: {}",
        reply.status,
        reply.body
    );
    assert_eq!(reply.body.get("state"), Some(&json!("requested")));
    Ok(())
}

/// Task 4 Step 4: `docs/openapi.yaml` must equal the freshly generated document, so the
/// committed contract cannot drift. JSON is valid YAML; the comparison is on the parsed JSON
/// value. Regenerate with `cargo run -- --print-openapi > docs/openapi.yaml` (Task 4 adds
/// `scripts/export_openapi.sh`). Un-ignored in Task A3, which first wrote the file.
#[test]
fn committed_openapi_yaml_matches_generated() -> TestResult {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("docs")
        .join("openapi.yaml");
    let committed: Value = serde_json::from_str(&std::fs::read_to_string(path)?)?;
    let generated = serde_json::to_value(ApiDoc::openapi())?;
    assert_eq!(committed, generated);
    Ok(())
}
