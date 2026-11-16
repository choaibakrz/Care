//! `JournalLayer`: copies WARN and above into the journal as `SystemEvent`, after redaction.

use tracing::{Event, Subscriber};
use tracing_subscriber::layer::{Context, Layer};

use domain::Actor;

use crate::journal::Journal;
use crate::record::{Category, RecordBody, Severity};
use crate::redact::Redactor;

/// The layer. Appends without awaiting (a tracing callback cannot block).
#[derive(Clone)]
pub struct JournalLayer {
    journal: Journal,
    redactor: Redactor,
}

impl JournalLayer {
    /// A layer writing into `journal`.
    #[must_use]
    pub fn new(journal: Journal) -> JournalLayer {
        JournalLayer {
            journal,
            redactor: Redactor::new(),
        }
    }
}

impl<S: Subscriber> Layer<S> for JournalLayer {
    fn on_event(&self, event: &Event<'_>, _ctx: Context<'_, S>) {
        let target = event.metadata().target();
        if target.starts_with("audit") {
            return;
        }
        let Ok(runtime) = tokio::runtime::Handle::try_current() else {
            return;
        };
        let (message, fields) = crate::flight_recorder::event_text(event);
        let message = crate::flight_recorder::render(message, &self.redactor.redact(fields));
        let severity = if *event.metadata().level() == tracing::Level::ERROR {
            Severity::Error
        } else {
            Severity::Warning
        };
        let journal = self.journal.clone();
        let target = target.to_owned();
        runtime.spawn(async move {
            // A failed append cannot be logged here (it would loop back into this layer).
            let _ignored = journal
                .append(
                    severity,
                    Category::System,
                    Actor::System("server"),
                    RecordBody::SystemEvent { target, message },
                    None,
                )
                .await;
        });
    }
}
