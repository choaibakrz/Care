//! Field redaction before anything reaches the journal or the flight recorder.

/// Dropped from every event.
pub const ALWAYS_REDACTED: &[&str] = &["token", "pin", "password", "key"];
/// Dropped when the event is attached to a tablet (`device` or `tablet` field present).
pub const TABLET_REDACTED: &[&str] = &["rssi", "point", "position", "place"];

/// Decides which fields survive.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Redactor;

impl Redactor {
    /// The redactor.
    #[must_use]
    pub fn new() -> Redactor {
        Redactor
    }

    /// Whether a field may be kept.
    #[must_use]
    pub fn keep_field(&self, name: &str, tablet_context: bool) -> bool {
        let name = name.to_ascii_lowercase();
        let always = ALWAYS_REDACTED.iter().any(|word| name.contains(word));
        let tablet = tablet_context && TABLET_REDACTED.contains(&name.as_str());
        !(always || tablet)
    }

    /// Filters `(name, value)` pairs.
    #[must_use]
    pub fn redact(&self, fields: Vec<(String, String)>) -> Vec<(String, String)> {
        let tablet = fields
            .iter()
            .any(|(name, _)| name == "device" || name == "tablet");
        fields
            .into_iter()
            .filter(|(name, _)| self.keep_field(name, tablet))
            .collect()
    }
}
