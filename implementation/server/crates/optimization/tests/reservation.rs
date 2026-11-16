//! Task 19: space-time reservations. Paths are on the small fixture map; robots move at
//! 1 m/s. This plans around other robots on the server side only; physical safety stays on
//! the robot.

use std::sync::Arc;

use chrono::{DateTime, TimeZone, Utc};
use domain::{Clock, FakeClock, RobotId};
use optimization::{Path, ReservationTable};

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn t0() -> Result<DateTime<Utc>, BoxError> {
    Ok(Utc
        .with_ymd_and_hms(2026, 11, 14, 2, 0, 0)
        .single()
        .ok_or("bad test date")?)
}

fn table() -> Result<ReservationTable, BoxError> {
    let clock: Arc<dyn Clock> = Arc::new(FakeClock::new(t0()?));
    Ok(ReservationTable::new(clock))
}

fn path(places: &[&str], metres: f64) -> Result<Path, BoxError> {
    Ok(Path {
        places: places.iter().map(|p| p.parse()).collect::<Result<_, _>>()?,
        metres,
    })
}

fn robot(id: &str) -> Result<RobotId, BoxError> {
    Ok(id.parse()?)
}

#[test]
fn same_corridor_overlapping_windows_conflict() -> TestResult {
    let table = table()?;
    table.try_reserve(
        &robot("robot-r1")?,
        &path(&["storeroom", "corridor-1", "room-101"], 24.0)?,
        t0()?,
        1.0,
    )?;
    let conflict = table
        .try_reserve(
            &robot("robot-r2")?,
            &path(&["dock", "corridor-1", "room-102"], 13.0)?,
            t0()? + chrono::Duration::seconds(2),
            1.0,
        )
        .err()
        .ok_or("two robots were given the corridor at the same time")?;
    assert_eq!(conflict.with, robot("robot-r1")?);
    assert!(conflict.window.0 < conflict.window.1);
    Ok(())
}

#[test]
fn head_on_swap_through_one_corridor_is_a_conflict() -> TestResult {
    let table = table()?;
    table.try_reserve(
        &robot("robot-r1")?,
        &path(&["room-101", "corridor-1", "room-102"], 18.0)?,
        t0()?,
        1.0,
    )?;
    let conflict = table
        .try_reserve(
            &robot("robot-r2")?,
            &path(&["room-102", "corridor-1", "room-101"], 18.0)?,
            t0()?,
            1.0,
        )
        .err()
        .ok_or("a head-on swap was accepted")?;
    assert_eq!(conflict.with, robot("robot-r1")?);
    Ok(())
}

#[test]
fn adjacent_non_overlapping_windows_are_fine() -> TestResult {
    let table = table()?;
    let route = path(&["storeroom", "corridor-1", "room-101"], 24.0)?;
    table.try_reserve(&robot("robot-r1")?, &route, t0()?, 1.0)?;
    table.try_reserve(
        &robot("robot-r2")?,
        &route,
        t0()? + chrono::Duration::minutes(10),
        1.0,
    )?;
    Ok(())
}

#[test]
fn earliest_start_waits_until_corridor_is_free() -> TestResult {
    let table = table()?;
    table.try_reserve(
        &robot("robot-r1")?,
        &path(&["storeroom", "corridor-1", "room-101"], 24.0)?,
        t0()?,
        1.0,
    )?;
    let other = path(&["dock", "corridor-1", "room-102"], 13.0)?;
    let start = table.earliest_start(&robot("robot-r2")?, &other, t0()?, 1.0);
    assert!(start > t0()?, "it did not wait");
    assert!(
        start <= t0()? + chrono::Duration::seconds(24),
        "it waited too long: {start}"
    );
    table.try_reserve(&robot("robot-r2")?, &other, start, 1.0)?;
    Ok(())
}

#[test]
fn release_frees_all_windows_of_that_robot() -> TestResult {
    let table = table()?;
    let r1 = robot("robot-r1")?;
    table.try_reserve(
        &r1,
        &path(&["storeroom", "corridor-1", "room-101"], 24.0)?,
        t0()?,
        1.0,
    )?;
    table.try_reserve(
        &r1,
        &path(&["room-101", "corridor-1", "room-104"], 24.0)?,
        t0()? + chrono::Duration::minutes(1),
        1.0,
    )?;
    table.release(&r1);
    let r2 = robot("robot-r2")?;
    table.try_reserve(
        &r2,
        &path(&["dock", "corridor-1", "room-102"], 13.0)?,
        t0()?,
        1.0,
    )?;
    table.try_reserve(
        &r2,
        &path(&["room-102", "corridor-1", "room-104"], 18.0)?,
        t0()? + chrono::Duration::minutes(1),
        1.0,
    )?;
    Ok(())
}
