//! The words of server monitoring and blocking (Task A8, fill T7b), shared by the `security`
//! crate (which counts and blocks) and `realtime` (which carries `security.alert`).
//! `implementation/admin/requirements/monitoring-security.md` is the contract. Nothing here
//! is about a person: addresses, network labels and counts only.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// Why a request was refused (the keys of `rejected_by` in `GET /monitor/traffic`).
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum RejectReason {
    /// 401.
    Unauthorized,
    /// 403 other than a block.
    Forbidden,
    /// 429.
    RateLimited,
    /// Refused by a block rule (403 `blocked`).
    Blocked,
    /// 503 `emergency_mode`.
    EmergencyMode,
    /// Other 4xx (400, 404, 409, 413, 422, …).
    Invalid,
}

impl RejectReason {
    /// Every reason, in the order of the console's table.
    pub const ALL: [RejectReason; 6] = [
        RejectReason::Unauthorized,
        RejectReason::Forbidden,
        RejectReason::RateLimited,
        RejectReason::Blocked,
        RejectReason::EmergencyMode,
        RejectReason::Invalid,
    ];

    /// The position of this reason in [`RejectReason::ALL`].
    #[must_use]
    pub fn index(self) -> usize {
        match self {
            RejectReason::Unauthorized => 0,
            RejectReason::Forbidden => 1,
            RejectReason::RateLimited => 2,
            RejectReason::Blocked => 3,
            RejectReason::EmergencyMode => 4,
            RejectReason::Invalid => 5,
        }
    }
}

/// The kinds of `security.alert`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SecurityAlertKind {
    /// An address went over the rate limit (at most once per address per minute).
    RateLimited,
    /// An address was blocked automatically after a persistent excess.
    AutoBlocked,
    /// An address was blocked automatically after too many failed logins.
    LoginBurst,
    /// An admin added a block rule.
    Blocked,
    /// A block rule expired or was removed.
    Unblocked,
}

/// `security.alert`: sent to the admin sockets only, shown as is.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct SecurityAlert {
    /// When.
    pub at: DateTime<Utc>,
    /// `rate_limited`, `auto_blocked`, `login_burst`, `blocked` or `unblocked`.
    pub kind: SecurityAlertKind,
    /// The address or block concerned.
    pub ip: String,
    /// Plain words, shown as is.
    pub message: String,
}

/// Who made a block rule.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum BlockSource {
    /// An admin, by hand.
    Manual,
    /// The server's detection rules.
    Auto,
}

/// What the server currently does with a client address.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ClientStatus {
    /// Served normally.
    Ok,
    /// Over the rate limit right now (some requests get 429).
    Limited,
    /// Covered by a block rule (403 `blocked`).
    Blocked,
}

#[cfg(test)]
mod tests {
    use super::{BlockSource, ClientStatus, RejectReason, SecurityAlertKind};

    #[test]
    fn wire_names_are_the_console_names() -> Result<(), Box<dyn std::error::Error>> {
        let reasons: Vec<String> = RejectReason::ALL
            .iter()
            .map(serde_json::to_value)
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .filter_map(|value| value.as_str().map(str::to_owned))
            .collect();
        assert_eq!(
            reasons,
            [
                "unauthorized",
                "forbidden",
                "rate_limited",
                "blocked",
                "emergency_mode",
                "invalid"
            ]
        );
        for (index, reason) in RejectReason::ALL.iter().enumerate() {
            assert_eq!(reason.index(), index);
        }
        assert_eq!(
            serde_json::to_value(SecurityAlertKind::LoginBurst)?,
            "login_burst"
        );
        assert_eq!(serde_json::to_value(BlockSource::Auto)?, "auto");
        assert_eq!(serde_json::to_value(ClientStatus::Limited)?, "limited");
        Ok(())
    }
}
