//! The flight recorder: a tracing layer keeping the last `flight_window` of events at DEBUG
//! and above in a bounded in-memory ring. On a `Critical` record it is dumped into an
//! `Incident` record.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use domain::Clock;
use tracing::{Event, Subscriber};
use tracing_subscriber::layer::{Context, Layer};

use crate::record::FlightEvent;
use crate::redact::Redactor;

/// Cheap to clone; clones share the ring.
#[derive(Clone)]
pub struct FlightRecorder {
    window: Duration,
    capacity: usize,
    clock: Arc<dyn Clock>,
    redactor: Redactor,
    ring: Arc<Mutex<VecDeque<FlightEvent>>>,
}

impl FlightRecorder {
    /// A recorder.
    #[must_use]
    pub fn new(window: Duration, capacity: usize, clock: Arc<dyn Clock>) -> FlightRecorder {
        FlightRecorder {
            window,
            capacity,
            clock,
            redactor: Redactor::new(),
            ring: Arc::new(Mutex::new(VecDeque::new())),
        }
    }

    /// Events within the window, oldest first.
    #[must_use]
    pub fn dump(&self) -> Vec<FlightEvent> {
        let since = self.clock.now() - chrono::Duration::from_std(self.window).unwrap_or_default();
        let Ok(ring) = self.ring.lock() else {
            return Vec::new();
        };
        ring.iter()
            .filter(|event| event.at >= since)
            .cloned()
            .collect()
    }
}

impl<S: Subscriber> Layer<S> for FlightRecorder {
    fn on_event(&self, event: &Event<'_>, _ctx: Context<'_, S>) {
        let (message, fields) = event_text(event);
        let fields = self.redactor.redact(fields);
        let message = render(message, &fields);
        let entry = FlightEvent {
            at: self.clock.now(),
            level: event.metadata().level().to_string(),
            target: event.metadata().target().to_owned(),
            message,
        };
        if let Ok(mut ring) = self.ring.lock() {
            ring.push_back(entry);
            while ring.len() > self.capacity {
                ring.pop_front();
            }
        }
    }
}

/// Collects an event's `message` and its other fields as text.
#[derive(Default)]
struct Fields {
    message: String,
    fields: Vec<(String, String)>,
}

impl tracing::field::Visit for Fields {
    fn record_debug(&mut self, field: &tracing::field::Field, value: &dyn std::fmt::Debug) {
        if field.name() == "message" {
            self.message = format!("{value:?}");
        } else {
            self.fields
                .push((field.name().to_owned(), format!("{value:?}")));
        }
    }
    fn record_str(&mut self, field: &tracing::field::Field, value: &str) {
        if field.name() == "message" {
            value.clone_into(&mut self.message);
        } else {
            self.fields
                .push((field.name().to_owned(), value.to_owned()));
        }
    }
}

/// The message and the fields of `event`, before redaction.
pub(crate) fn event_text(event: &Event<'_>) -> (String, Vec<(String, String)>) {
    let mut fields = Fields::default();
    event.record(&mut fields);
    (fields.message, fields.fields)
}

/// `message key=value …` after redaction.
pub(crate) fn render(message: String, fields: &[(String, String)]) -> String {
    fields.iter().fold(message, |mut out, (name, value)| {
        out.push(' ');
        out.push_str(name);
        out.push('=');
        out.push_str(value);
        out
    })
}
