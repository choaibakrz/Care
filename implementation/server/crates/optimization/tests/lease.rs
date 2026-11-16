//! Task 18: shelf leases, one robot per shelf, expiring by the clock.

use std::sync::Arc;
use std::time::Duration;

use chrono::{TimeZone, Utc};
use domain::{Clock, FakeClock, PlaceId, RobotId};
use optimization::{LeaseError, ShelfLeases};

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn leases() -> Result<(ShelfLeases, Arc<FakeClock>), BoxError> {
    let clock = Arc::new(FakeClock::new(
        Utc.with_ymd_and_hms(2026, 11, 14, 2, 0, 0)
            .single()
            .ok_or("bad test date")?,
    ));
    let dyn_clock: Arc<dyn Clock> = clock.clone();
    Ok((ShelfLeases::new(dyn_clock), clock))
}

#[test]
fn second_robot_cannot_lease_a_held_shelf_message_names_holder_and_time() -> TestResult {
    let (leases, clock) = leases()?;
    let shelf: PlaceId = "storeroom".parse()?;
    let r1: RobotId = "robot-r1".parse()?;
    let lease = leases.acquire(&shelf, &r1, Duration::from_mins(10))?;
    let until = clock.now() + chrono::Duration::minutes(10);
    assert_eq!(lease.until, until);
    let err = leases
        .acquire(&shelf, &"robot-r2".parse()?, Duration::from_mins(10))
        .err()
        .ok_or("a held shelf was leased twice")?;
    assert_eq!(err, LeaseError::HeldBy { robot: r1, until });
    let message = err.to_string();
    assert!(message.contains("robot-r1"), "{message}");
    assert!(message.contains(&until.to_string()), "{message}");
    Ok(())
}

#[test]
fn lease_expires_after_ttl() -> TestResult {
    let (leases, clock) = leases()?;
    let shelf: PlaceId = "storeroom".parse()?;
    leases.acquire(&shelf, &"robot-r1".parse()?, Duration::from_mins(5))?;
    clock.advance(Duration::from_secs(5 * 60 + 1));
    leases.acquire(&shelf, &"robot-r2".parse()?, Duration::from_mins(5))?;
    Ok(())
}

#[test]
fn release_by_non_holder_is_rejected() -> TestResult {
    let (leases, _clock) = leases()?;
    let shelf: PlaceId = "storeroom".parse()?;
    let r1: RobotId = "robot-r1".parse()?;
    leases.acquire(&shelf, &r1, Duration::from_mins(10))?;
    leases.release(&shelf, &"robot-r2".parse()?);
    let err = leases
        .acquire(&shelf, &"robot-r3".parse()?, Duration::from_mins(10))
        .err()
        .ok_or("a release by another robot freed the shelf")?;
    assert!(matches!(err, LeaseError::HeldBy { robot, .. } if robot == r1));
    leases.release(&shelf, &r1);
    leases.acquire(&shelf, &"robot-r3".parse()?, Duration::from_mins(10))?;
    Ok(())
}
