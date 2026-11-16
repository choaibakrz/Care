//! Task A4 / 11d: `GET /stats/heat`, the heat map (port of `admin/src/lib/heat.ts`): robots
//! only, never tablets; 1 m cells; memory only.

mod support;

use std::collections::BTreeSet;
use std::time::Duration;

use axum::http::StatusCode;
use clinic_server::dto::HeatView;
use clinic_server::services::stats::HEAT_CELL_M;
use serde_json::{Value, json};
use support::{RealApp, Res, TestResult, get, map, put_json};
use utoipa::PartialSchema;

/// The count of the cell containing `(x, y)` in a heat view body.
fn count_at(body: &Value, x: f64, y: f64) -> Res<u64> {
    let origin = body
        .get("origin")
        .and_then(Value::as_array)
        .ok_or("no origin")?;
    let ox = origin.first().and_then(Value::as_f64).ok_or("origin x")?;
    let oy = origin.get(1).and_then(Value::as_f64).ok_or("origin y")?;
    let columns = u32::try_from(
        body.get("columns")
            .and_then(Value::as_u64)
            .ok_or("no columns")?,
    )?;
    let counts = body
        .get("counts")
        .and_then(Value::as_array)
        .ok_or("no counts")?;
    let mut row = 0_u32;
    let mut column = 0_u32;
    for count in counts {
        let x0 = ox + f64::from(column) * HEAT_CELL_M;
        let y0 = oy + f64::from(row) * HEAT_CELL_M;
        if (x0..x0 + HEAT_CELL_M).contains(&x) && (y0..y0 + HEAT_CELL_M).contains(&y) {
            return count.as_u64().ok_or_else(|| "count is not a number".into());
        }
        column += 1;
        if column == columns {
            column = 0;
            row += 1;
        }
    }
    Err(format!("no cell contains ({x}, {y})").into())
}

#[test]
fn heat_view_has_the_grid_fields() -> TestResult {
    let schema = serde_json::to_value(HeatView::schema())?;
    let keys: BTreeSet<&str> = schema
        .get("properties")
        .and_then(Value::as_object)
        .ok_or("no properties")?
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        keys,
        ["cell_m", "columns", "counts", "floor", "origin", "rows"]
            .into_iter()
            .collect()
    );
    assert!((HEAT_CELL_M - 1.0).abs() < f64::EPSILON);
    Ok(())
}

#[tokio::test]
async fn heat_counts_robots_only_never_tablets() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let admin = app.admin_token().await?;
    // A robot standing in the storeroom, a tablet in room 104 (both floor 1).
    let _robot = app.connect_robot(&server, "robot-r1", 5.0, 4.0).await?;
    let nurse = app.nurse_token().await?;
    let placed = app
        .call(put_json(
            "/me/location",
            Some(&nurse),
            &json!({ "place": map::ROOM_104 }),
        )?)
        .await?;
    assert_eq!(placed.status, StatusCode::OK, "{}", placed.body);
    tokio::time::sleep(Duration::from_millis(2_500)).await;
    let reply = app.call(get("/stats/heat?floor=1", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("cell_m"), Some(&json!(1.0)));
    assert!(count_at(&reply.body, 5.0, 4.0)? >= 2, "{}", reply.body);
    // The tablet's room anchor (25, 16) was never counted, nor anything but the robot cell.
    assert_eq!(count_at(&reply.body, 25.0, 16.0)?, 0);
    let total: u64 = reply
        .body
        .get("counts")
        .and_then(Value::as_array)
        .map(|c| c.iter().filter_map(Value::as_u64).sum())
        .unwrap_or_default();
    assert_eq!(total, count_at(&reply.body, 5.0, 4.0)?);
    Ok(())
}

#[tokio::test]
async fn heat_grid_covers_the_floor_outline() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app.call(get("/stats/heat?floor=2", Some(&admin))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    // The fixture outline is -1..31 by -1..21.
    assert_eq!(reply.body.get("origin"), Some(&json!([-1.0, -1.0])));
    assert_eq!(reply.body.get("columns"), Some(&json!(32)));
    assert_eq!(reply.body.get("rows"), Some(&json!(22)));
    let counts = reply
        .body
        .get("counts")
        .and_then(Value::as_array)
        .ok_or("no counts")?;
    assert_eq!(counts.len(), 32 * 22);
    assert!(counts.iter().all(|c| c == &json!(0)));
    Ok(())
}

#[tokio::test]
async fn heat_is_admin_only() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let reply = app.call(get("/stats/heat?floor=1", Some(&nurse))?).await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("forbidden"));
    Ok(())
}

#[tokio::test]
async fn heat_of_unknown_floor_is_422() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let reply = app.call(get("/stats/heat?floor=9", Some(&admin))?).await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    Ok(())
}
