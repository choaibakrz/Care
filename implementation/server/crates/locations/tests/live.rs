//! Task 11: live positions in memory, staleness and expiry by the clock, the privacy shape
//! of tablets, and validation of robot fixes.

#[path = "../../../tests/support/map.rs"]
mod map;

use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, TimeZone, Utc};
use domain::{Clock, FakeClock, OwnerLabel, RobotStatus, SubjectRef};
use locations::{
    LivePositions, LocationError, Point2, PositionFix, PositionTtl, RobotInfo, TabletLive,
};
use utoipa::PartialSchema as _;

type TestResult = Result<(), Box<dyn std::error::Error>>;

fn start() -> Result<DateTime<Utc>, Box<dyn std::error::Error>> {
    Ok(Utc
        .with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
        .single()
        .ok_or("bad test date")?)
}

fn live() -> Result<(LivePositions, Arc<FakeClock>), Box<dyn std::error::Error>> {
    let clock = Arc::new(FakeClock::new(start()?));
    let dyn_clock: Arc<dyn Clock> = clock.clone();
    let positions = LivePositions::new(
        Arc::new(map::small_map()?),
        dyn_clock,
        PositionTtl::default(),
    );
    Ok((positions, clock))
}

fn info() -> RobotInfo {
    RobotInfo {
        name: "R2".to_owned(),
        status: RobotStatus::Idle,
        task: None,
        battery_pct: 80.0,
        mic_open: true,
    }
}

fn fix(
    floor: i32,
    x: f64,
    y: f64,
    heading: Option<f64>,
    at: DateTime<Utc>,
) -> Result<PositionFix, Box<dyn std::error::Error>> {
    Ok(PositionFix {
        subject: SubjectRef::Robot("robot-r2".parse()?),
        floor,
        point: Point2::new(x, y)?,
        heading_rad: heading,
        at,
    })
}

#[test]
fn robot_silent_over_5s_is_marked_stale() -> TestResult {
    let (live, clock) = live()?;
    live.update_robot(fix(1, 15.0, 10.0, Some(0.0), start()?)?, info())?;
    let stale_after = |live: &LivePositions| -> Result<bool, Box<dyn std::error::Error>> {
        Ok(live.snapshot().robots.first().ok_or("no robot")?.stale)
    };
    assert!(!stale_after(&live)?);
    clock.advance(Duration::from_millis(4_900));
    assert!(!stale_after(&live)?, "stale after 4.9 s");
    clock.advance(Duration::from_millis(100));
    assert!(
        !stale_after(&live)?,
        "stale at exactly 5.0 s (the rule is over 5 s)"
    );
    clock.advance(Duration::from_millis(100));
    assert!(stale_after(&live)?, "not stale after 5.1 s");
    Ok(())
}

#[test]
fn stale_robot_keeps_last_position_but_flag_is_true() -> TestResult {
    let (live, clock) = live()?;
    live.update_robot(fix(1, 15.0, 10.0, Some(0.5), start()?)?, info())?;
    clock.advance(Duration::from_secs(30));
    let snapshot = live.snapshot();
    let robot = snapshot.robots.first().ok_or("a stale robot disappeared")?;
    assert!(robot.stale);
    assert_eq!(robot.floor, 1);
    assert_eq!(robot.point, Point2::new(15.0, 10.0)?);
    assert_eq!(robot.heading_rad, Some(0.5));
    Ok(())
}

#[test]
fn tablet_disappears_after_expiry() -> TestResult {
    let (live, clock) = live()?;
    live.set_tablet(
        "tab-1".parse()?,
        OwnerLabel::new("Ward 2 nurse")?,
        &map::ROOM_101.parse()?,
    )?;
    assert_eq!(live.snapshot().tablets.len(), 1);
    clock.advance(Duration::from_secs(119));
    assert_eq!(live.snapshot().tablets.len(), 1);
    clock.advance(Duration::from_secs(2));
    assert!(live.snapshot().tablets.is_empty());
    Ok(())
}

/// Golden key set: a tablet is shown with these six keys and nothing else (type-level).
#[test]
fn tablet_json_has_exactly_the_six_allowed_keys() -> TestResult {
    let schema = serde_json::to_value(TabletLive::schema())?;
    let keys: BTreeSet<&str> = schema
        .get("properties")
        .and_then(serde_json::Value::as_object)
        .ok_or("TabletLive has no properties")?
        .keys()
        .map(String::as_str)
        .collect();
    let expected: BTreeSet<&str> = [
        "device_id",
        "owner",
        "place",
        "floor",
        "point",
        "uncertainty_m",
    ]
    .into_iter()
    .collect();
    assert_eq!(keys, expected);
    Ok(())
}

#[test]
fn position_with_nan_is_rejected() -> TestResult {
    let (live, _clock) = live()?;
    let err = live
        .update_robot(fix(1, 15.0, 10.0, Some(f64::NAN), start()?)?, info())
        .err()
        .ok_or("a NaN heading was accepted")?;
    assert!(matches!(err, LocationError::NonFinite { .. }), "{err:?}");
    assert!(live.snapshot().robots.is_empty());
    Ok(())
}

#[test]
fn position_on_floor_9_is_rejected_naming_the_floor() -> TestResult {
    let (live, _clock) = live()?;
    let err = live
        .update_robot(fix(9, 15.0, 10.0, None, start()?)?, info())
        .err()
        .ok_or("floor 9 was accepted")?;
    assert_eq!(err, LocationError::UnknownFloor { floor: 9 });
    assert!(err.to_string().contains("Floor 9"), "{err}");
    Ok(())
}

#[test]
fn position_outside_floor_outline_is_rejected() -> TestResult {
    let (live, _clock) = live()?;
    let err = live
        .update_robot(fix(1, 100.0, 100.0, None, start()?)?, info())
        .err()
        .ok_or("a point outside the floor was accepted")?;
    assert!(
        matches!(err, LocationError::PositionOutOfMap { floor: 1, .. }),
        "{err:?}"
    );
    Ok(())
}
