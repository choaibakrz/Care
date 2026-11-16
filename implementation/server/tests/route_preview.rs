//! Task 13b: the route preview, a port of `admin/src/lib/nav.ts`, on the seed plan (the
//! console's demo clinic, `seed/clinic_map.json`), and `GET /tasks/{id}/route`.
//!
//! The reference cases are those of `admin/src/lib/nav.test.ts`. The schema check runs now;
//! everything else is ignored until the planner (T13b) and the plan validation (T10b) exist.

mod support;

use std::path::PathBuf;

use axum::http::StatusCode;
use clinic_server::dto::RouteView;
use domain::ZoneKind;
use locations::grid::ROBOT_CLEARANCE_M;
use locations::{ClinicMap, ClinicPlan, Disc, Point2, Polygon, Zone, load_plan};
use optimization::{RouteError, RoutePreview};
use serde_json::{Value, json};
use support::{RealApp, Res, TestResult, get, map, post_json};
use utoipa::PartialSchema;

fn seed() -> Res<(ClinicPlan, ClinicMap)> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("seed/clinic_map.json");
    let plan = load_plan(&path)?;
    let map = plan.validate()?;
    Ok((plan, map))
}

fn point(x: f64, y: f64) -> Res<Point2> {
    Ok(Point2::new(x, y)?)
}

fn zone(id: &str, kind: ZoneKind, floor: i32, pairs: &[[f64; 2]]) -> Res<Zone> {
    Ok(Zone {
        id: id.parse()?,
        kind,
        floor,
        polygon: Polygon::from_pairs(pairs)?,
        version: 1,
    })
}

/// Distance from `p` to the segment `a b`.
fn distance_to_segment(p: Point2, a: [f64; 2], b: [f64; 2]) -> f64 {
    let [ax, ay] = a;
    let [bx, by] = b;
    let (dx, dy) = (bx - ax, by - ay);
    let length_sq = dx * dx + dy * dy;
    let t = if length_sq > 0.0 {
        (((p.x() - ax) * dx + (p.y() - ay) * dy) / length_sq).clamp(0.0, 1.0)
    } else {
        0.0
    };
    (p.x() - (ax + t * dx)).hypot(p.y() - (ay + t * dy))
}

/// The points of `path`, plus ten samples on each leg.
fn samples(points: &[Point2]) -> Res<Vec<Point2>> {
    let mut out = Vec::new();
    for pair in points.windows(2) {
        if let [a, b] = pair {
            for step in 0..=10 {
                let t = f64::from(step) / 10.0;
                out.push(point(
                    a.x() + (b.x() - a.x()) * t,
                    a.y() + (b.y() - a.y()) * t,
                )?);
            }
        }
    }
    Ok(out)
}

fn smallest_wall_distance(plan: &ClinicPlan, floor: i32, points: &[Point2]) -> Res<f64> {
    let mut smallest = f64::INFINITY;
    for p in samples(points)? {
        for wall in plan.walls.iter().filter(|w| w.floor == floor) {
            for pair in wall.points.windows(2) {
                if let [a, b] = pair {
                    smallest = smallest.min(distance_to_segment(p, *a, *b));
                }
            }
        }
    }
    Ok(smallest)
}

#[test]
fn route_view_has_floor_points_length_and_estimate() -> TestResult {
    let schema = serde_json::to_value(RouteView::schema())?;
    let keys: Vec<&String> = schema
        .get("properties")
        .and_then(Value::as_object)
        .ok_or("no properties")?
        .keys()
        .collect();
    assert_eq!(keys, vec!["estimate", "floor", "length_m", "points"]);
    Ok(())
}

#[test]
fn every_place_reaches_every_other_place_of_its_floor() -> TestResult {
    let (plan, map) = seed()?;
    let preview = RoutePreview::new();
    for from in &plan.places {
        for to in plan
            .places
            .iter()
            .filter(|p| p.floor == from.floor && p.id != from.id)
        {
            let path = preview.plan(
                &map,
                &[],
                point(from.x, from.y)?,
                point(to.x, to.y)?,
                from.floor,
            );
            assert!(path.is_ok(), "{} to {}: {path:?}", from.id, to.id);
        }
    }
    Ok(())
}

#[test]
fn route_avoids_walls_and_solid_props() -> TestResult {
    let (plan, map) = seed()?;
    let preview = RoutePreview::new();
    // Dock N to the lounge, floor 2 (nav.test.ts: "a path never crosses solid furniture").
    let path = preview.plan(&map, &[], point(1.5, 11.0)?, point(20.4, 10.4)?, 2)?;
    assert!(path.points.len() >= 2);
    for p in samples(&path.points)? {
        for prop in plan.props.iter().filter(|p| p.floor == 2 && p.solid) {
            let inside = (p.x() - prop.x).abs() < prop.width / 2.0
                && (p.y() - prop.y).abs() < prop.depth / 2.0;
            assert!(!inside, "crosses {:?} {} at {p:?}", prop.kind, prop.id);
        }
    }
    // "A path never comes closer to a wall than the robot body", on every pair of places.
    for from in &plan.places {
        for to in plan
            .places
            .iter()
            .filter(|p| p.floor == from.floor && p.id != from.id)
        {
            let path = preview.plan(
                &map,
                &[],
                point(from.x, from.y)?,
                point(to.x, to.y)?,
                from.floor,
            )?;
            let clearance = smallest_wall_distance(&plan, from.floor, &path.points)?;
            assert!(clearance > 0.3, "{} to {}: {clearance}", from.id, to.id);
        }
    }
    const { assert!(ROBOT_CLEARANCE_M > 0.3) };
    Ok(())
}

#[test]
fn goal_inside_the_elevator_is_moved_outside() -> TestResult {
    let (plan, map) = seed()?;
    let path = RoutePreview::new().plan(&map, &[], point(4.0, 7.0)?, point(8.5, 2.5)?, 0)?;
    let end = path.points.last().ok_or("empty path")?;
    let elevator = plan
        .rooms
        .iter()
        .find(|r| r.id.as_str() == "elevator-0")
        .ok_or("no elevator-0")?;
    assert!(!Polygon::from_pairs(&elevator.polygon)?.contains(end));
    Ok(())
}

#[test]
fn drives_around_a_robot_standing_in_the_corridor() -> TestResult {
    let (_, map) = seed()?;
    let other = Disc {
        center: point(12.0, 7.0)?,
        radius_m: 0.85,
    };
    let path = RoutePreview::new().plan_around(
        &map,
        &[],
        point(2.0, 7.0)?,
        point(22.0, 7.0)?,
        2,
        &[other],
    )?;
    for p in &path.points {
        assert!(p.distance(&other.center) >= 0.75, "{p:?}");
    }
    Ok(())
}

#[test]
fn route_avoids_restricted_zone_but_crosses_deaf_zone() -> TestResult {
    let (_, map) = seed()?;
    let preview = RoutePreview::new();
    // Floor 2 corridor, west to east. A restricted band across the middle of the corridor
    // leaves no way: the planner must refuse rather than cross it.
    let band = [[11.0, 5.5], [13.0, 5.5], [13.0, 8.5], [11.0, 8.5]];
    let restricted = zone("z-band", ZoneKind::Restricted, 2, &band)?;
    let refused = preview.plan(&map, &[restricted], point(2.0, 7.0)?, point(22.0, 7.0)?, 2);
    assert!(
        matches!(refused, Err(RouteError::Unreachable { floor: 2 })),
        "{refused:?}"
    );
    // The same band as a deaf zone is crossed.
    let deaf = zone("z-band", ZoneKind::Deaf, 2, &band)?;
    let path = preview.plan(&map, &[deaf], point(2.0, 7.0)?, point(22.0, 7.0)?, 2)?;
    // Straight along the corridor: about 20 m, no detour.
    assert!(path.length_m < 22.0, "{}", path.length_m);
    // The console's restricted pool edge (ground floor) is avoided: Hall to Pool goes around.
    let pool_edge = zone(
        "zone-pool-edge",
        ZoneKind::Restricted,
        0,
        &[[11.4, 9.9], [21.6, 9.9], [21.6, 13.9], [11.4, 13.9]],
    )?;
    let around = preview.plan(
        &map,
        std::slice::from_ref(&pool_edge),
        point(4.4, 10.2)?,
        point(13.9, 9.45)?,
        0,
    )?;
    for p in samples(&around.points)? {
        assert!(
            !pool_edge.polygon.contains(&p),
            "enters the restricted zone at {p:?}"
        );
    }
    Ok(())
}

#[test]
fn route_length_is_the_polyline_length() -> TestResult {
    let (_, map) = seed()?;
    let path = RoutePreview::new().plan(&map, &[], point(2.0, 7.0)?, point(22.0, 7.0)?, 2)?;
    let length: f64 = path
        .points
        .windows(2)
        .filter_map(|pair| match pair {
            [a, b] => Some(a.distance(b)),
            _ => None,
        })
        .sum();
    assert!((length - path.length_m).abs() < 1e-6);
    assert!(path.length_m >= 20.0);
    Ok(())
}

// ---------------------------------------------------------------------------------------
// `GET /tasks/{id}/route` on the real wiring (fixture clinic)

/// Creates a `go_to` task as a nurse and returns its id.
async fn go_to(app: &RealApp, token: &str, place: &str) -> Res<String> {
    let reply = app
        .call(post_json(
            "/tasks",
            Some(token),
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

#[tokio::test]
async fn task_route_is_an_estimate_on_the_task_floor() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let task = go_to(&app, &nurse, map::ROOM_101).await?;
    let reply = app
        .call(get(&format!("/tasks/{task}/route"), Some(&nurse))?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("estimate"), Some(&json!(true)));
    assert_eq!(reply.body.get("floor"), Some(&json!(1)));
    let points = reply
        .body
        .get("points")
        .and_then(Value::as_array)
        .ok_or("no points")?;
    assert!(points.len() >= 2, "{}", reply.body);
    Ok(())
}

#[tokio::test]
async fn route_between_floors_is_404_no_route() -> TestResult {
    // The fixture's dock is on floor 1 and room 201 on floor 2: the route preview has no lift.
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let task = go_to(&app, &nurse, map::ROOM_201).await?;
    let reply = app
        .call(get(&format!("/tasks/{task}/route"), Some(&nurse))?)
        .await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("no_route"));
    assert!(
        reply.error_message().contains("lift"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn route_of_unknown_task_is_404_not_found() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let reply = app.call(get("/tasks/t-none/route", Some(&nurse))?).await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND);
    assert_eq!(reply.error_code(), Some("not_found"));
    Ok(())
}
