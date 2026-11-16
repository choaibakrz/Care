//! Task A4 / 10b: editable clinic plans (`/clinics`), the active plan on `GET /map`, and the
//! `map.updated` event.
//!
//! The contract checks (schemas, OpenAPI routes) run now; the behaviour is ignored until the
//! clinic service (T10b) is filled. HTTP tests use the fixture clinic as a plan
//! (`support::map::small_plan_json`), stored as clinic `seed` at start.

mod support;

use std::collections::BTreeSet;
use std::time::Duration;

use axum::http::{Method, StatusCode};
use clinic_server::dto::{ClinicSummary, HealthView, ServerMode};
use clinic_server::openapi::ApiDoc;
use domain::{ErrorDetail, Permission};
use serde_json::{Value, json};
use support::{RealApp, Res, TestResult, get, map, post_json, put_json, request, with_header};
use utoipa::{OpenApi as _, PartialSchema};

const WAIT: Duration = Duration::from_secs(3);

fn schema_keys<T: PartialSchema>() -> Res<BTreeSet<String>> {
    let schema = serde_json::to_value(T::schema())?;
    Ok(schema
        .get("properties")
        .and_then(Value::as_object)
        .ok_or_else(|| format!("schema has no properties: {schema}"))?
        .keys()
        .cloned()
        .collect())
}

fn set(keys: &[&str]) -> BTreeSet<String> {
    keys.iter().map(|k| (*k).to_owned()).collect()
}

/// The fixture plan with one more room on floor 1 (a valid edit).
fn edited_plan() -> Value {
    let mut plan = map::small_plan_json();
    if let Some(name) = plan.get_mut("name") {
        *name = json!("Test clinic, edited");
    }
    plan
}

/// The fixture plan without `place` (a removal).
fn plan_without(place: &str) -> Value {
    let mut plan = map::small_plan_json();
    if let Some(places) = plan.get_mut("places").and_then(Value::as_array_mut) {
        places.retain(|p| p.get("id") != Some(&json!(place)));
    }
    plan
}

/// `GET /clinics/{id}` and its `ETag`.
async fn fetch(app: &RealApp, admin: &str, id: &str) -> Res<(Value, String)> {
    let reply = app
        .call(get(&format!("/clinics/{id}"), Some(admin))?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let etag = reply.header("etag").ok_or("no ETag")?.to_owned();
    Ok((reply.body, etag))
}

/// `PUT /clinics/{id}` with `If-Match`.
async fn put_plan(
    app: &RealApp,
    admin: &str,
    id: &str,
    etag: &str,
    plan: &Value,
) -> Res<support::Reply> {
    app.call(with_header(
        put_json(&format!("/clinics/{id}"), Some(admin), plan)?,
        "if-match",
        etag,
    )?)
    .await
}

/// Stores the fixture plan under another name and returns its id.
async fn second_plan(app: &RealApp, admin: &str) -> Res<String> {
    let mut plan = map::small_plan_json();
    if let Some(name) = plan.get_mut("name") {
        *name = json!("Second clinic");
    }
    let reply = app.call(post_json("/clinics", Some(admin), &plan)?).await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
    reply
        .body
        .get("id")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| format!("no id in {}", reply.body).into())
}

/// A `go_to` task to `place`, still open.
async fn open_task(app: &RealApp, place: &str) -> Res<String> {
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &json!({ "kind": "go_to", "to_place": place }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
    reply
        .body
        .get("id")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| format!("no id in {}", reply.body).into())
}

fn details(reply: &support::Reply) -> Vec<(String, String)> {
    reply
        .body
        .pointer("/error/details")
        .and_then(Value::as_array)
        .map(|list| {
            list.iter()
                .map(|d| {
                    (
                        d.get("path")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_owned(),
                        d.get("problem")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_owned(),
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

// ---------------------------------------------------------------------------------------
// Contract (runs now)

#[test]
fn clinic_summary_has_id_name_version_active_updated_at() -> TestResult {
    assert_eq!(
        schema_keys::<ClinicSummary>()?,
        set(&["id", "name", "version", "active", "updated_at"])
    );
    Ok(())
}

#[test]
fn error_detail_can_list_problems() -> TestResult {
    assert_eq!(
        schema_keys::<ErrorDetail>()?,
        set(&["code", "message", "request_id", "details"])
    );
    // Absent when empty, so every existing error keeps `{code, message}`.
    let body = serde_json::to_value(ErrorDetail {
        code: "not_found".to_owned(),
        message: "Task 't-1' was not found.".to_owned(),
        request_id: None,
        details: Vec::new(),
    })?;
    assert_eq!(
        body,
        json!({ "code": "not_found", "message": "Task 't-1' was not found." })
    );
    let with = serde_json::to_value(ErrorDetail {
        code: "invalid_plan".to_owned(),
        message: "The clinic plan has 1 problem(s).".to_owned(),
        request_id: None,
        details: vec![domain::ErrorProblem {
            path: "rooms[3].polygon".to_owned(),
            problem: "edges 1–2 and 3–4 cross".to_owned(),
        }],
    })?;
    assert_eq!(
        with.get("details"),
        Some(&json!([{ "path": "rooms[3].polygon", "problem": "edges 1–2 and 3–4 cross" }]))
    );
    Ok(())
}

#[test]
fn health_reports_the_mode() -> TestResult {
    assert_eq!(
        schema_keys::<HealthView>()?,
        set(&["status", "journal_writable", "version", "mode", "brain"])
    );
    for (mode, wire) in [
        (ServerMode::Live, "live"),
        (ServerMode::Demo, "demo"),
        (ServerMode::Mock, "mock"),
    ] {
        assert_eq!(serde_json::to_value(mode)?, json!(wire));
    }
    Ok(())
}

#[test]
fn permissions_for_clinics_and_stats_exist() -> TestResult {
    assert_eq!(
        serde_json::to_value(Permission::EditClinics)?,
        json!("edit_clinics")
    );
    assert_eq!(
        serde_json::to_value(Permission::ViewStats)?,
        json!("view_stats")
    );
    Ok(())
}

#[test]
fn openapi_lists_the_a4_routes() -> TestResult {
    let doc = serde_json::to_value(ApiDoc::openapi())?;
    let paths = doc.get("paths").ok_or("no paths")?;
    for (path, method) in [
        ("/clinics", "get"),
        ("/clinics", "post"),
        ("/clinics/{id}", "get"),
        ("/clinics/{id}", "put"),
        ("/clinics/{id}", "delete"),
        ("/clinics/{id}/activate", "post"),
        ("/tasks/{id}/route", "get"),
        ("/stats/heat", "get"),
        ("/map", "get"),
    ] {
        assert!(
            paths.get(path).and_then(|p| p.get(method)).is_some(),
            "{method} {path} missing from OpenAPI"
        );
    }
    let put = paths
        .pointer("/~1clinics~1{id}/put/parameters")
        .and_then(Value::as_array)
        .ok_or("PUT /clinics/{id} has no parameters")?;
    assert!(
        put.iter()
            .any(|p| p.get("name") == Some(&json!("If-Match"))),
        "If-Match is documented"
    );
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Behaviour (T10b)

#[tokio::test]
async fn seed_plan_is_stored_and_active_at_start() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app.call(get("/clinics", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(
        reply.body,
        json!([{
            "id": "seed", "name": "Test clinic", "version": 1, "active": true,
            "updated_at": reply.body.pointer("/0/updated_at").cloned().unwrap_or(Value::Null)
        }])
    );
    Ok(())
}

#[tokio::test]
async fn get_clinic_round_trips_through_post() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let (plan, etag) = fetch(&app, &admin, "seed").await?;
    assert_eq!(etag, "\"1\"");
    assert_eq!(plan, map::small_plan_json());
    let reply = app
        .call(post_json("/clinics", Some(&admin), &plan)?)
        .await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
    assert_eq!(reply.body.get("active"), Some(&json!(false)));
    assert_eq!(reply.body.get("version"), Some(&json!(1)));
    Ok(())
}

#[tokio::test]
async fn nurse_cannot_list_or_edit_clinics() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let list = app.call(get("/clinics", Some(&nurse))?).await?;
    assert_eq!(list.status, StatusCode::FORBIDDEN);
    assert_eq!(list.error_code(), Some("forbidden"));
    let put = put_plan(&app, &nurse, "seed", "\"1\"", &edited_plan()).await?;
    assert_eq!(put.status, StatusCode::FORBIDDEN);
    Ok(())
}

#[tokio::test]
async fn put_returns_the_next_version() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let (_, etag) = fetch(&app, &admin, "seed").await?;
    let reply = put_plan(&app, &admin, "seed", &etag, &edited_plan()).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.header("etag"), Some("\"2\""));
    assert_eq!(reply.body.get("name"), Some(&json!("Test clinic, edited")));
    Ok(())
}

#[tokio::test]
async fn put_with_stale_if_match_is_412() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let (_, etag) = fetch(&app, &admin, "seed").await?;
    let first = put_plan(&app, &admin, "seed", &etag, &edited_plan()).await?;
    assert_eq!(first.status, StatusCode::OK, "{}", first.body);
    // A second editor still holds version 1.
    let stale = put_plan(&app, &admin, "seed", &etag, &map::small_plan_json()).await?;
    assert_eq!(
        stale.status,
        StatusCode::PRECONDITION_FAILED,
        "{}",
        stale.body
    );
    assert_eq!(stale.error_code(), Some("version_conflict"));
    assert!(
        stale.error_message().contains('2'),
        "{}",
        stale.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn put_without_if_match_is_428() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(put_json("/clinics/seed", Some(&admin), &edited_plan())?)
        .await?;
    assert_eq!(
        reply.status,
        StatusCode::PRECONDITION_REQUIRED,
        "{}",
        reply.body
    );
    assert_eq!(reply.error_code(), Some("if_match_required"));
    Ok(())
}

#[tokio::test]
async fn invalid_plan_is_422_with_every_problem_and_its_path() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let mut plan = map::small_plan_json();
    map::set_at(
        &mut plan,
        "/rooms/3/polygon",
        json!([[26.0, 0.0], [30.0, 8.0], [30.0, 0.0], [26.0, 8.0]]),
    )?;
    map::set_at(&mut plan, "/places/0/x", json!(80.0))?;
    let reply = put_plan(&app, &admin, "seed", "\"1\"", &plan).await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    assert_eq!(reply.error_code(), Some("invalid_plan"));
    let found = details(&reply);
    assert!(
        found
            .iter()
            .any(|(path, problem)| path == "rooms[3].polygon"
                && problem.contains("edges 1–2 and 3–4 cross")),
        "{found:?}"
    );
    assert!(
        found.iter().any(|(path, _)| path == "places[0]"),
        "{found:?}"
    );
    // Nothing was saved.
    let (_, etag) = fetch(&app, &admin, "seed").await?;
    assert_eq!(etag, "\"1\"");
    Ok(())
}

#[tokio::test]
async fn deleting_a_place_used_by_an_open_task_is_409_listing_the_task() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let task = open_task(&app, map::ROOM_102).await?;
    let (_, etag) = fetch(&app, &admin, "seed").await?;
    let reply = put_plan(&app, &admin, "seed", &etag, &plan_without(map::ROOM_102)).await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("place_in_use"));
    let found = details(&reply);
    assert!(
        found
            .iter()
            .any(|(path, _)| path == &format!("tasks/{task}")),
        "{found:?}"
    );
    Ok(())
}

#[tokio::test]
async fn deleting_a_place_used_by_a_stock_item_is_409() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    app.set_stock("blanket", 3).await?;
    let (_, etag) = fetch(&app, &admin, "seed").await?;
    let reply = put_plan(&app, &admin, "seed", &etag, &plan_without(map::STOREROOM)).await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert!(
        details(&reply)
            .iter()
            .any(|(path, _)| path == "inventory/blanket"),
        "{}",
        reply.body
    );
    Ok(())
}

#[tokio::test]
async fn activating_another_plan_with_open_tasks_is_409() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let other = second_plan(&app, &admin).await?;
    let task = open_task(&app, map::ROOM_101).await?;
    let reply = app
        .call(post_json(
            &format!("/clinics/{other}/activate"),
            Some(&admin),
            &json!({}),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("open_tasks"));
    assert!(
        details(&reply)
            .iter()
            .any(|(path, _)| path == &format!("tasks/{task}")),
        "{}",
        reply.body
    );
    Ok(())
}

#[tokio::test]
async fn activating_switches_get_map() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let other = second_plan(&app, &admin).await?;
    let reply = app
        .call(post_json(
            &format!("/clinics/{other}/activate"),
            Some(&admin),
            &json!({}),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let view = app.call(get("/map", Some(&admin))?).await?;
    assert_eq!(view.body.get("clinic_id"), Some(&json!(other)));
    assert_eq!(view.body.get("name"), Some(&json!("Second clinic")));
    assert_eq!(
        view.header("etag"),
        Some(format!("\"{other}-v1\"").as_str())
    );
    Ok(())
}

#[tokio::test]
async fn the_active_plan_cannot_be_deleted() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(request(
            Method::DELETE,
            "/clinics/seed",
            Some(&admin),
            None,
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("clinic_active"));
    let other = second_plan(&app, &admin).await?;
    let gone = app
        .call(request(
            Method::DELETE,
            &format!("/clinics/{other}"),
            Some(&admin),
            None,
        )?)
        .await?;
    assert_eq!(gone.status, StatusCode::NO_CONTENT);
    Ok(())
}

#[tokio::test]
async fn map_updated_is_broadcast_after_put() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    let mut socket = app.app_socket(&server).await?;
    let mut robot = app.connect_robot(&server, "robot-r1", 5.0, 4.0).await?;
    let (_, etag) = fetch(&app, &admin, "seed").await?;
    let reply = put_plan(&app, &admin, "seed", &etag, &edited_plan()).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let event = socket.next_of_type("map.updated", WAIT).await?;
    assert_eq!(event.get("clinic_id"), Some(&json!("seed")));
    assert_eq!(event.get("version"), Some(&json!(2)));
    assert_eq!(event.get("active"), Some(&json!(true)));
    let down = robot.next_of_type("map.update", WAIT).await?;
    assert_eq!(down.get("version"), Some(&json!("seed-v2")));
    // Journaled.
    app.journal.seal_now(audit::SealReason::Interval).await?;
    let journaled = support::read_journal(&app.config.journal.dir)?
        .iter()
        .any(|r| matches!(&r.body, audit::RecordBody::ClinicChanged { version: 2, .. }));
    assert!(journaled, "clinic_changed version 2 is in the journal");
    Ok(())
}

#[tokio::test]
async fn get_map_is_the_active_plan_with_its_tag() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let reply = app.call(get("/map", Some(&nurse))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.header("etag"), Some("\"seed-v1\""));
    assert_eq!(reply.body.get("clinic_id"), Some(&json!("seed")));
    assert_eq!(reply.body.get("version"), Some(&json!(1)));
    let walls = reply
        .body
        .get("walls")
        .and_then(Value::as_array)
        .ok_or("no walls")?;
    assert!(
        walls.iter().all(|w| w.get("id").is_some()),
        "every wall has an id"
    );
    Ok(())
}

#[tokio::test]
async fn post_with_a_taken_name_is_409_clinic_exists() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let first = second_plan(&app, &admin).await?;
    let mut plan = map::small_plan_json();
    map::set_at(&mut plan, "/name", json!("Second clinic"))?;
    let reply = app
        .call(post_json("/clinics", Some(&admin), &plan)?)
        .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("clinic_exists"));
    assert!(
        reply.error_message().contains(&first),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn seed_plan_is_stored_before_the_first_request() -> TestResult {
    // Ruling R16: `Wiring::finish` awaits the bootstrap, so the very first call sees it.
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app.call(get("/clinics/seed", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    Ok(())
}

#[tokio::test]
async fn mock_put_with_a_bowtie_room_is_422_invalid_plan_and_stores_nothing() -> TestResult {
    let app = support::MockApp::start()?;
    let admin = Some("mock-admin");
    let list = support::call(&app.app, get("/clinics", admin)?).await?;
    assert_eq!(list.status, StatusCode::OK, "{}", list.body);
    let id = list
        .body
        .pointer("/0/id")
        .and_then(Value::as_str)
        .ok_or("no clinic")?
        .to_owned();
    let url = format!("/clinics/{id}");
    let before = support::call(&app.app, get(&url, admin)?).await?;
    let etag = before.header("etag").ok_or("no ETag")?.to_owned();
    let mut plan = before.body.clone();
    map::set_at(
        &mut plan,
        "/rooms/0/polygon",
        json!([[0.0, 0.0], [4.0, 4.0], [4.0, 0.0], [0.0, 4.0]]),
    )?;
    let reply = support::call(
        &app.app,
        with_header(put_json(&url, admin, &plan)?, "if-match", &etag)?,
    )
    .await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    assert_eq!(reply.error_code(), Some("invalid_plan"));
    let found = details(&reply);
    assert_eq!(
        found.first().map(|(path, _)| path.as_str()),
        Some("rooms[0].polygon"),
        "{found:?}"
    );
    let after = support::call(&app.app, get(&url, admin)?).await?;
    assert_eq!(after.header("etag"), Some(etag.as_str()));
    assert_eq!(after.body, before.body);
    Ok(())
}

#[tokio::test]
async fn mock_overlay_adds_a_room_and_a_prop_then_resets_and_refuses_a_bad_one() -> TestResult {
    let app = support::MockApp::start()?;
    let admin = Some("mock-admin");
    let url = "/clinics/seed";
    let base_rooms = support::call(&app.app, get("/map", admin)?)
        .await?
        .body
        .get("rooms")
        .and_then(Value::as_array)
        .map_or(0, Vec::len);
    let etag = support::call(&app.app, get(url, admin)?)
        .await?
        .header("etag")
        .ok_or("no ETag")?
        .to_owned();
    let overlay = json!({
        "base_version": 1,
        "upsert": {
            "rooms": [{"id": "new-room", "floor": 0, "label": "New", "kind": "room",
                       "polygon": [[20.0, 10.0], [23.0, 10.0], [23.0, 13.0], [20.0, 13.0]]}],
            "props": [{"id": "new-prop", "floor": 0, "kind": "plant", "x": 21.0, "y": 11.0,
                       "width": 0.5, "depth": 0.5, "solid": false}]
        },
        "remove": {"props": ["no-such-prop"]}
    });
    let put = |body: Value, etag: String| -> Res<_> {
        with_header(
            put_json(&format!("{url}/overlay"), admin, &body)?,
            "if-match",
            &etag,
        )
    };
    let saved = support::call(&app.app, put(overlay.clone(), etag.clone())?).await?;
    assert_eq!(saved.status, StatusCode::OK, "{}", saved.body);
    let etag2 = saved.header("etag").ok_or("no ETag")?.to_owned();
    let map = support::call(&app.app, get("/map", admin)?).await?.body;
    let has = |key: &str, id: &str| {
        map.get(key)
            .and_then(Value::as_array)
            .is_some_and(|list| list.iter().any(|x| x.get("id") == Some(&json!(id))))
    };
    assert!(
        has("rooms", "new-room") && has("props", "new-prop"),
        "{map}"
    );
    // The base is untouched; the overlay reads back.
    let base = support::call(&app.app, get(&format!("{url}/base"), admin)?).await?;
    assert_eq!(
        base.body
            .get("rooms")
            .and_then(Value::as_array)
            .map(Vec::len),
        Some(base_rooms)
    );
    let back = support::call(&app.app, get(&format!("{url}/overlay"), admin)?).await?;
    assert_eq!(
        back.body.pointer("/upsert/rooms/0/id"),
        Some(&json!("new-room")),
        "{}",
        back.body
    );
    // A bad overlay is 422 with a path into the effective plan, nothing stored.
    let bad = json!({"upsert": {"rooms": [{"id": "bowtie", "floor": 0, "label": "Bad", "kind": "room",
        "polygon": [[0.0, 0.0], [4.0, 4.0], [4.0, 0.0], [0.0, 4.0]]}]}});
    let refused = support::call(&app.app, put(bad, etag2.clone())?).await?;
    assert_eq!(
        refused.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        refused.body
    );
    assert_eq!(refused.error_code(), Some("invalid_plan"));
    assert!(
        details(&refused)
            .iter()
            .any(|(path, _)| path.starts_with("rooms[")),
        "{:?}",
        details(&refused)
    );
    // Reset: the room is gone again.
    let reset = support::call(
        &app.app,
        with_header(
            request(Method::DELETE, &format!("{url}/overlay"), admin, None)?,
            "if-match",
            &etag2,
        )?,
    )
    .await?;
    assert_eq!(reset.status, StatusCode::OK, "{}", reset.body);
    let map = support::call(&app.app, get("/map", admin)?).await?.body;
    assert_eq!(
        map.get("rooms").and_then(Value::as_array).map(Vec::len),
        Some(base_rooms)
    );
    Ok(())
}
