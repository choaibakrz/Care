//! Task 9: the flight recorder window and the redactor.

mod common;

use std::sync::Arc;
use std::time::Duration;

use audit::{FlightRecorder, Redactor};
use common::Res;
use domain::{Clock, FakeClock};
use tracing_subscriber::layer::SubscriberExt as _;

type TestResult = Res<()>;

#[test]
fn flight_recorder_keeps_only_the_window() -> TestResult {
    let clock = Arc::new(FakeClock::new(common::start_time()?));
    let dyn_clock: Arc<dyn Clock> = clock.clone();
    let recorder = FlightRecorder::new(Duration::from_secs(30), 10_000, dyn_clock);
    let subscriber = tracing_subscriber::registry().with(recorder.clone());
    tracing::subscriber::with_default(subscriber, || {
        tracing::info!("old event");
        clock.advance(Duration::from_secs(31));
        tracing::info!("new event");
    });
    let messages: Vec<String> = recorder.dump().into_iter().map(|e| e.message).collect();
    assert!(
        messages.iter().any(|m| m.contains("new event")),
        "{messages:?}"
    );
    assert!(
        !messages.iter().any(|m| m.contains("old event")),
        "{messages:?}"
    );
    Ok(())
}

#[test]
fn redactor_drops_token_pin_and_tablet_location() {
    let redactor = Redactor::new();
    for field in ["token", "pin", "password", "key"] {
        assert!(!redactor.keep_field(field, false), "{field} kept");
        assert!(!redactor.keep_field(field, true), "{field} kept");
    }
    for field in ["rssi", "point", "position", "place"] {
        assert!(!redactor.keep_field(field, true), "tablet {field} kept");
    }
    assert!(
        redactor.keep_field("place", false),
        "a robot's place was dropped"
    );
    assert!(redactor.keep_field("robot", true));
    let kept = redactor.redact(vec![
        ("token".to_owned(), "abc123".to_owned()),
        ("pin".to_owned(), "4821".to_owned()),
        ("robot".to_owned(), "robot-r2".to_owned()),
    ]);
    assert_eq!(kept, vec![("robot".to_owned(), "robot-r2".to_owned())]);
}
