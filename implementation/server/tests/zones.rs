//! Task 16: zones are validated, sent to every connected robot, acknowledged per robot, and
//! re-sent on reconnect.

mod support;

use std::time::Duration;

use axum::http::{Method, StatusCode};
use domain::Clock as _;
use serde_json::{Value, json};
use support::{RealApp, Res, TestResult, WsClient, get, put_json, request, robot_message};

const WAIT: Duration = Duration::from_secs(3);

/// A `PUT /zones/{id}` body as the admin console sends it (`id` equals the path id).
fn zone(id: &str, kind: &str, polygon: &Value) -> Value {
    json!({ "id": id, "name": format!("Zone {id}"), "kind": kind, "floor": 1, "polygon": polygon })
}

fn room_101_zone(id: &str) -> Value {
    zone(
        id,
        "deaf",
        &json!([[1.0, 13.0], [9.0, 13.0], [9.0, 19.0], [1.0, 19.0]]),
    )
}

/// Ids of the zones in a `zones.update` message.
fn zone_ids(update: &Value) -> Vec<String> {
    update
        .get("zones")
        .and_then(Value::as_array)
        .map(|zones| {
            zones
                .iter()
                .filter_map(|z| z.get("id").and_then(Value::as_str).map(str::to_owned))
                .collect()
        })
        .unwrap_or_default()
}

/// Reads `zones.update` messages until one contains (or lacks) `id`.
async fn update_where(robot: &mut WsClient, id: &str, present: bool) -> Res<Value> {
    let deadline = tokio::time::Instant::now() + WAIT;
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let update = robot.next_of_type("zones.update", left).await?;
        if zone_ids(&update).iter().any(|z| z == id) == present {
            return Ok(update);
        }
    }
}

#[tokio::test]
async fn self_intersecting_polygon_returns_422_naming_the_edges() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let bowtie = zone(
        "z-bow",
        "deaf",
        &json!([[1.0, 13.0], [9.0, 19.0], [9.0, 13.0], [1.0, 19.0]]),
    );
    let reply = app
        .call(put_json("/zones/z-bow", Some(&admin), &bowtie)?)
        .await?;
    assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(
        reply.error_message().contains("edges 0 and 2"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn polygon_outside_floor_returns_422() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let outside = zone(
        "z-out",
        "deaf",
        &json!([[40.0, 40.0], [50.0, 40.0], [50.0, 50.0]]),
    );
    let reply = app
        .call(put_json("/zones/z-out", Some(&admin), &outside)?)
        .await?;
    assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(
        reply.error_message().contains("z-out"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn nurse_cannot_edit_zones() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(put_json("/zones/z-1", Some(&nurse), &room_101_zone("z-1"))?)
        .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("forbidden"));
    Ok(())
}

#[tokio::test]
async fn edit_sends_zones_update_to_all_connected_robots() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    let mut r1 = app.connect_robot(&server, "robot-r1", 5.0, 4.0).await?;
    let mut r2 = app.connect_robot(&server, "robot-r2", 12.0, 4.0).await?;
    let reply = app
        .call(put_json("/zones/z-1", Some(&admin), &room_101_zone("z-1"))?)
        .await?;
    assert!(
        reply.status.is_success(),
        "{}: {}",
        reply.status,
        reply.body
    );
    update_where(&mut r1, "z-1", true).await?;
    update_where(&mut r2, "z-1", true).await?;
    Ok(())
}

/// A robot that acknowledges is `received`; a connected robot that has not acknowledged is
/// `pending`; a registered robot that is not connected is `pending` with `robot_online: false`.
#[tokio::test]
async fn robot_ack_marks_delivered_and_offline_robot_shows_pending() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    let mut r1 = app.connect_robot(&server, "robot-r1", 5.0, 4.0).await?;
    let _r2 = app.connect_robot(&server, "robot-r2", 12.0, 4.0).await?;
    app.add_robot("robot-r3", false).await?;
    let reply = app
        .call(put_json("/zones/z-1", Some(&admin), &room_101_zone("z-1"))?)
        .await?;
    let version = reply
        .body
        .get("version")
        .and_then(Value::as_u64)
        .ok_or("no zone version")?;
    update_where(&mut r1, "z-1", true).await?;
    r1.send_json(&robot_message(
        "zone.ack",
        &json!({ "zone_version_by_id": { "z-1": version } }),
        app.clock.now(),
    ))
    .await?;
    tokio::time::sleep(Duration::from_millis(300)).await;
    let list = app.call(get("/zones", Some(&admin))?).await?;
    let delivery = list
        .body
        .as_array()
        .and_then(|zones| zones.iter().find(|z| z.get("id") == Some(&json!("z-1"))))
        .and_then(|z| z.get("deliveries"))
        .and_then(Value::as_array)
        .ok_or("no deliveries list for z-1")?
        .clone();
    let field_of = |robot: &str, field: &str| {
        delivery
            .iter()
            .find(|d| d.get("robot_id") == Some(&json!(robot)))
            .and_then(|d| d.get(field))
            .cloned()
    };
    assert_eq!(field_of("robot-r1", "status"), Some(json!("received")));
    assert_eq!(field_of("robot-r2", "status"), Some(json!("pending")));
    assert_eq!(field_of("robot-r2", "robot_online"), Some(json!(true)));
    assert_eq!(field_of("robot-r3", "status"), Some(json!("pending")));
    assert_eq!(field_of("robot-r3", "robot_online"), Some(json!(false)));
    Ok(())
}

#[tokio::test]
async fn reconnecting_robot_receives_current_zones() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(put_json("/zones/z-1", Some(&admin), &room_101_zone("z-1"))?)
        .await?;
    assert!(reply.status.is_success(), "{}", reply.body);
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    update_where(&mut robot, "z-1", true).await?;
    Ok(())
}

#[tokio::test]
async fn delete_zone_sends_updated_list_without_it() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    let mut robot = app.connect_robot(&server, "robot-r2", 5.0, 4.0).await?;
    app.call(put_json("/zones/z-a", Some(&admin), &room_101_zone("z-a"))?)
        .await?;
    let other = zone(
        "z-b",
        "deaf",
        &json!([[11.0, 13.0], [19.0, 13.0], [19.0, 19.0]]),
    );
    app.call(put_json("/zones/z-b", Some(&admin), &other)?)
        .await?;
    update_where(&mut robot, "z-b", true).await?;
    let deleted = app
        .call(request(Method::DELETE, "/zones/z-a", Some(&admin), None)?)
        .await?;
    assert!(deleted.status.is_success(), "{}", deleted.body);
    let update = update_where(&mut robot, "z-a", false).await?;
    assert_eq!(zone_ids(&update), vec!["z-b".to_owned()]);
    Ok(())
}

#[tokio::test]
async fn restricted_zone_is_labelled_not_enforced() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let restricted = zone(
        "z-r",
        "restricted",
        &json!([[11.0, 13.0], [19.0, 13.0], [19.0, 19.0]]),
    );
    let reply = app
        .call(put_json("/zones/z-r", Some(&admin), &restricted)?)
        .await?;
    assert!(
        reply.status.is_success(),
        "{}: {}",
        reply.status,
        reply.body
    );
    assert_eq!(reply.body.get("enforced_by_gardien"), Some(&json!(false)));
    Ok(())
}

#[tokio::test]
#[ignore = "locations::PlanningGrid leaves free cells outside the rooms, so routes go around a restricted band (see optimization restricted_zones tests)"]
async fn routing_is_rebuilt_after_a_zone_put() -> TestResult {
    // A restricted band across corridor 1 (x 16.5..18.5) cuts the storeroom off room 104 for
    // the dispatcher and the tour planner (Task A4, ruling on restricted zones); deleting the
    // zone joins them again.
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let (from, to) = ("storeroom".parse()?, "room-104".parse()?);
    let all = optimization::PlaceMask::all();
    let graph = app.routing.handle();
    assert!(graph.current().shortest_path(&from, &to, &all).is_some());
    let band = zone(
        "z-band",
        "restricted",
        &json!([[16.5, 8.0], [18.5, 8.0], [18.5, 12.0], [16.5, 12.0]]),
    );
    let reply = app
        .call(put_json("/zones/z-band", Some(&admin), &band)?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert!(graph.current().shortest_path(&from, &to, &all).is_none());
    let gone = app
        .call(request(
            Method::DELETE,
            "/zones/z-band",
            Some(&admin),
            None,
        )?)
        .await?;
    assert_eq!(gone.status, StatusCode::NO_CONTENT);
    assert!(graph.current().shortest_path(&from, &to, &all).is_some());
    Ok(())
}
