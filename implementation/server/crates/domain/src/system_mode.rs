//! Emergency mode (Task A8, fill E1): one switch for the admin. While it is on the server
//! refuses every request that is not needed for the emergency (503 `emergency_mode`), sends
//! the robots out of the corridors and starts no task (`implementation/admin/requirements/
//! emergency-mode.md`). Patient alarms go through the separate emergency service and are
//! never touched.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// Longest reason given with a switch, in characters.
pub const MAX_MODE_REASON_LEN: usize = 200;

/// The two modes of the server.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SystemMode {
    /// Normal operation.
    Normal,
    /// Emergency mode: only emergency actions are accepted.
    Emergency,
}

/// The current mode as `GET /system/mode`, `mode.updated` and the `snapshot` carry it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct SystemModeState {
    /// `normal` or `emergency`.
    pub mode: SystemMode,
    /// When the current mode started; `null` if never switched since the server started.
    pub since: Option<DateTime<Utc>>,
    /// The pseudonymous operator label of whoever switched it; `null` before the first switch.
    pub by: Option<String>,
    /// Free text given with the switch (at most 200 characters), or `null`.
    pub reason: Option<String>,
}

impl SystemModeState {
    /// Normal operation, never switched (the state of a fresh server).
    #[must_use]
    pub fn initial() -> SystemModeState {
        SystemModeState {
            mode: SystemMode::Normal,
            since: None,
            by: None,
            reason: None,
        }
    }

    /// Whether emergency mode is on.
    #[must_use]
    pub fn is_emergency(&self) -> bool {
        self.mode == SystemMode::Emergency
    }
}

/// An admin's short free text (a mode switch's or a block rule's reason) as it may be stored
/// and shown (ruling R26): control characters and bidirectional formatting characters
/// (U+061C, U+200E, U+200F, U+202A to U+202E, U+2066 to U+2069), line and paragraph
/// separators (U+2028, U+2029) and zero-width characters (U+200B to U+200D, U+FEFF)
/// removed, then trimmed.
#[must_use]
pub fn clean_admin_text(text: &str) -> String {
    text.chars()
        .filter(|c| !c.is_control() && !is_bidi_control(*c))
        .collect::<String>()
        .trim()
        .to_owned()
}

/// The bidirectional formatting characters (they can make a text read differently).
fn is_bidi_control(c: char) -> bool {
    matches!(
        c,
        '\u{061C}'
            | '\u{200B}'..='\u{200F}'
            | '\u{2028}'..='\u{2029}'
            | '\u{202A}'..='\u{202E}'
            | '\u{2066}'..='\u{2069}'
            | '\u{FEFF}'
    )
}

/// Checks the reason of a switch: cleaned ([`clean_admin_text`]), at most
/// [`MAX_MODE_REASON_LEN`] characters; blank is `None`.
///
/// # Errors
/// The reason in plain words when it is too long.
pub fn check_mode_reason(reason: Option<&str>) -> Result<Option<String>, String> {
    let cleaned = reason.map(clean_admin_text);
    let Some(reason) = cleaned.as_deref().filter(|text| !text.is_empty()) else {
        return Ok(None);
    };
    if reason.chars().count() > MAX_MODE_REASON_LEN {
        return Err(format!(
            "is longer than {MAX_MODE_REASON_LEN} characters; shorten it"
        ));
    }
    Ok(Some(reason.to_owned()))
}

#[cfg(test)]
mod tests {
    use super::{SystemMode, SystemModeState, check_mode_reason};

    #[test]
    fn initial_state_is_normal_and_never_switched() -> Result<(), Box<dyn std::error::Error>> {
        let state = SystemModeState::initial();
        assert!(!state.is_emergency());
        let json = serde_json::to_value(&state)?;
        assert_eq!(
            json,
            serde_json::json!({"mode": "normal", "since": null, "by": null, "reason": null})
        );
        assert_eq!(
            serde_json::to_value(SystemMode::Emergency)?,
            serde_json::json!("emergency")
        );
        Ok(())
    }

    #[test]
    fn reason_is_trimmed_and_capped() {
        assert_eq!(check_mode_reason(None), Ok(None));
        assert_eq!(check_mode_reason(Some("  ")), Ok(None));
        assert_eq!(
            check_mode_reason(Some(" Fire alarm ")),
            Ok(Some("Fire alarm".to_owned()))
        );
        assert!(check_mode_reason(Some(&"x".repeat(201))).is_err());
        assert!(check_mode_reason(Some(&"é".repeat(200))).is_ok());
        assert_eq!(
            check_mode_reason(Some("Fire\u{202E}alarm\u{0007}\n wing B")),
            Ok(Some("Firealarm wing B".to_owned()))
        );
        assert_eq!(check_mode_reason(Some("\u{200F}\u{2066}")), Ok(None));
        assert_eq!(
            check_mode_reason(Some(
                "Wing\u{2028}B\u{200B}\u{200C}\u{200D}\u{FEFF}\u{2029}"
            )),
            Ok(Some("WingB".to_owned()))
        );
    }
}
