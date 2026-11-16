//! Identifier newtypes and the pseudonymous `OwnerLabel`.
//!
//! Every id is 1 to 64 characters of `[a-z0-9_-]`, validated by `FromStr` and
//! `TryFrom<String>`, and serialised as a plain string.

use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::error::DomainError;

/// Longest accepted id, in characters.
pub const MAX_ID_LEN: usize = 64;

/// Checks the shared id rule: 1 to 64 characters among `a-z`, `0-9`, `_` and `-`.
fn validate_id(kind: &'static str, value: &str) -> Result<(), DomainError> {
    let reason = if value.is_empty() {
        Some("it is empty")
    } else if value.chars().count() > MAX_ID_LEN {
        Some("it is longer than 64 characters")
    } else if !value
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
    {
        Some("it contains a character outside a-z, 0-9, '_' and '-'")
    } else {
        None
    };
    match reason {
        Some(reason) => Err(DomainError::InvalidId {
            kind,
            value: value.to_owned(),
            reason,
        }),
        None => Ok(()),
    }
}

macro_rules! define_id {
    ($(#[$doc:meta])* $name:ident, $kind:literal) => {
        $(#[$doc])*
        ///
        /// Invariant: 1 to 64 characters of `[a-z0-9_-]`.
        #[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema)]
        #[serde(try_from = "String", into = "String")]
        #[schema(value_type = String)]
        pub struct $name(String);

        impl $name {
            /// The kind name used in error messages.
            pub const KIND: &'static str = $kind;

            /// The id as a string slice.
            #[must_use]
            pub fn as_str(&self) -> &str {
                &self.0
            }
        }

        impl FromStr for $name {
            type Err = DomainError;

            /// # Errors
            /// `DomainError::InvalidId` when empty, longer than 64 or outside `[a-z0-9_-]`.
            fn from_str(value: &str) -> Result<Self, Self::Err> {
                validate_id($kind, value)?;
                Ok($name(value.to_owned()))
            }
        }

        impl TryFrom<String> for $name {
            type Error = DomainError;

            fn try_from(value: String) -> Result<Self, Self::Error> {
                validate_id($kind, &value)?;
                Ok($name(value))
            }
        }

        impl From<$name> for String {
            fn from(id: $name) -> String {
                id.0
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str(&self.0)
            }
        }
    };
}

define_id!(
    /// A task id.
    TaskId,
    "task"
);
define_id!(
    /// A robot id (for example `robot-r2`).
    RobotId,
    "robot"
);
define_id!(
    /// A device (tablet) id, chosen by the app and bound to tokens.
    DeviceId,
    "device"
);
define_id!(
    /// A staff user id.
    UserId,
    "user"
);
define_id!(
    /// A place (room, corridor, storeroom, dock) on the clinic map.
    PlaceId,
    "place"
);
define_id!(
    /// A deaf or restricted zone.
    ZoneId,
    "zone"
);
define_id!(
    /// A reserve item (class key shared with job 1's `classes.yaml`).
    ItemId,
    "item"
);
define_id!(
    /// A schedule (for example the night restock round).
    ScheduleId,
    "schedule"
);
define_id!(
    /// A stored clinic plan (Task A4). The seed plan is `seed`; plans created through
    /// `POST /clinics` get an id derived from their name.
    ClinicId,
    "clinic"
);

impl ClinicId {
    /// The seed plan's id, `seed` (valid by construction).
    #[must_use]
    pub fn seed() -> ClinicId {
        ClinicId("seed".to_owned())
    }
}

/// Longest accepted owner label, in characters.
pub const MAX_OWNER_LABEL_LEN: usize = 40;

/// The display label of a tablet's owner: 1 to 40 visible characters, trimmed, not digits only.
///
/// By convention a pseudonymous label ("Nurse station 2", "Dr. A"), never a full name. It is
/// the only thing the server holds about a person besides the tablet's room.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(try_from = "String", into = "String")]
#[schema(value_type = String)]
pub struct OwnerLabel(String);

impl OwnerLabel {
    /// Validates and trims a label.
    ///
    /// # Errors
    /// `DomainError::InvalidOwnerLabel` when empty after trimming, longer than 40 characters,
    /// made of digits only, or containing control characters.
    pub fn new(raw: &str) -> Result<OwnerLabel, DomainError> {
        let label = raw.trim();
        let reason = if label.is_empty() {
            Some("it is empty")
        } else if label.chars().count() > MAX_OWNER_LABEL_LEN {
            Some("it is longer than 40 characters")
        } else if label.chars().any(char::is_control) {
            Some("it contains a control character")
        } else if label.chars().all(char::is_numeric) {
            Some("it is made of digits only")
        } else {
            None
        };
        match reason {
            Some(reason) => Err(DomainError::InvalidOwnerLabel { reason }),
            None => Ok(OwnerLabel(label.to_owned())),
        }
    }

    /// The label as a string slice.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl TryFrom<String> for OwnerLabel {
    type Error = DomainError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        OwnerLabel::new(&value)
    }
}

impl From<OwnerLabel> for String {
    fn from(label: OwnerLabel) -> String {
        label.0
    }
}

impl fmt::Display for OwnerLabel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::{OwnerLabel, RobotId};
    use crate::error::DomainError;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn id_rejects_uppercase_and_spaces() -> TestResult {
        for bad in ["Robot-r2", "robot r2", " robot-r2"] {
            let err = bad
                .parse::<RobotId>()
                .err()
                .ok_or("an invalid id was accepted")?;
            assert!(
                matches!(err, DomainError::InvalidId { kind: "robot", .. }),
                "{err}"
            );
        }
        let ok: RobotId = "robot-r2_1".parse()?;
        assert_eq!(ok.as_str(), "robot-r2_1");
        Ok(())
    }

    #[test]
    fn id_rejects_65_chars() -> TestResult {
        let at_limit = "a".repeat(64);
        assert!(at_limit.parse::<RobotId>().is_ok());
        let too_long = "a".repeat(65);
        let err = too_long
            .parse::<RobotId>()
            .err()
            .ok_or("a 65-char id was accepted")?;
        assert!(matches!(err, DomainError::InvalidId { .. }));
        Ok(())
    }

    #[test]
    fn owner_label_rejects_empty_and_whitespace_only() -> TestResult {
        for bad in ["", " ", "   \t  "] {
            let err = OwnerLabel::new(bad)
                .err()
                .ok_or("an empty label was accepted")?;
            assert!(matches!(err, DomainError::InvalidOwnerLabel { .. }));
        }
        assert_eq!(OwnerLabel::new("  Dr. A ")?.as_str(), "Dr. A");
        Ok(())
    }
}
