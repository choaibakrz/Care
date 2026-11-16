//! Block rules: the wire shapes of `GET/POST /security/blocks` and the checks of a new rule.

use std::net::IpAddr;

use chrono::{DateTime, Utc};
use domain::BlockSource;
use ipnet::IpNet;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// Longest reason of a block rule, in characters.
pub const MAX_BLOCK_REASON_LEN: usize = 200;
/// Longest lifetime of a rule given in seconds (one year); `null` means "until removed".
pub const MAX_BLOCK_SECONDS: u64 = 365 * 24 * 3600;
/// Narrowest allowed IPv4 prefix length of a rule: broader is 422 `range_too_broad`.
pub const MIN_V4_PREFIX: u8 = 16;
/// Narrowest allowed IPv6 prefix length of a rule.
pub const MIN_V6_PREFIX: u8 = 48;

/// One block rule as `GET /security/blocks` lists it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct BlockView {
    /// Rule id (`blk-<n>`).
    pub id: String,
    /// The blocked address or CIDR block.
    pub target: String,
    /// Why (shown to admins only; a blocked client gets no detail).
    pub reason: String,
    /// `manual` or `auto`.
    pub source: BlockSource,
    /// When the rule was made.
    pub created_at: DateTime<Utc>,
    /// When it ends; `null` = until removed.
    pub expires_at: Option<DateTime<Utc>>,
    /// The pseudonymous operator label of the admin who made it; `null` for an automatic rule.
    pub by: Option<String>,
    /// Requests refused because of this rule.
    pub hits: u64,
}

/// `POST /security/blocks`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct NewBlockRequest {
    /// An address (`203.0.113.42`) or a CIDR block (`203.0.113.0/24`), at most `/16`
    /// (IPv4) or `/48` (IPv6) wide.
    pub target: String,
    /// Why, 1 to 200 characters.
    pub reason: String,
    /// Seconds until the rule ends; `null` (or absent) = until removed.
    #[serde(default)]
    pub expires_in_s: Option<u64>,
}

/// Why a block rule was refused or not found.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum BlockError {
    /// The target is not an address or a CIDR block (422 `invalid_field`).
    #[error("is not an IP address or a CIDR block such as 203.0.113.0/24")]
    InvalidTarget,
    /// The reason is empty or too long (422 `invalid_field`).
    #[error("must be 1 to {MAX_BLOCK_REASON_LEN} characters")]
    InvalidReason,
    /// `expires_in_s` is zero or over a year (422 `invalid_field`).
    #[error(
        "must be a number of seconds from 1 to {MAX_BLOCK_SECONDS} (one year), or null for \"until removed\""
    )]
    InvalidExpiry,
    /// Broader than `/16` or `/48` (422 `range_too_broad`).
    #[error(
        "The block {target} is too broad: at most /{MIN_V4_PREFIX} for IPv4 and /{MIN_V6_PREFIX} for IPv6. Block a narrower range."
    )]
    RangeTooBroad {
        /// The refused target.
        target: String,
    },
    /// The rule would cover an address that must stay reachable (422 `protected_target`).
    #[error(
        "The block {target} would cover {what}, which must stay reachable. Nothing was blocked."
    )]
    Protected {
        /// The refused target.
        target: String,
        /// Which protected address, in plain words.
        what: String,
    },
    /// No such rule (404 `not_found`): expired, or removed by another admin.
    #[error("Block rule '{id}' was not found (it expired or another admin removed it).")]
    NotFound {
        /// The id asked for.
        id: String,
    },
}

/// A validated new rule: the block, its displayed target, reason and lifetime.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CheckedBlock {
    pub(crate) net: IpNet,
    pub(crate) target: String,
    pub(crate) reason: String,
    pub(crate) expires_in_s: Option<u64>,
}

impl NewBlockRequest {
    /// Parses the target, checks the reason, the lifetime and the width. Protection is
    /// checked by the monitor, which knows the caller, the robots and the emergency service.
    ///
    /// # Errors
    /// `(field, error)`: `InvalidTarget`, `InvalidReason`, `InvalidExpiry` with the field they
    /// concern, or `RangeTooBroad`.
    pub(crate) fn check(&self) -> Result<CheckedBlock, (&'static str, BlockError)> {
        let (net, target) =
            parse_target(self.target.trim()).ok_or(("target", BlockError::InvalidTarget))?;
        // Control and bidirectional characters are removed before the reason is stored or
        // shown (ruling R26).
        let reason = domain::clean_admin_text(&self.reason);
        if reason.is_empty() || reason.chars().count() > MAX_BLOCK_REASON_LEN {
            return Err(("reason", BlockError::InvalidReason));
        }
        if self
            .expires_in_s
            .is_some_and(|seconds| seconds == 0 || seconds > MAX_BLOCK_SECONDS)
        {
            return Err(("expires_in_s", BlockError::InvalidExpiry));
        }
        let too_broad = match net {
            IpNet::V4(v4) => v4.prefix_len() < MIN_V4_PREFIX,
            IpNet::V6(v6) => v6.prefix_len() < MIN_V6_PREFIX,
        };
        if too_broad {
            return Err(("target", BlockError::RangeTooBroad { target }));
        }
        Ok(CheckedBlock {
            net,
            target,
            reason,
            expires_in_s: self.expires_in_s,
        })
    }
}

/// An address (shown as itself, blocking `/32` or `/128`) or a CIDR block (shown truncated
/// to its network: `203.0.113.9/24` is `203.0.113.0/24`).
pub(crate) fn parse_target(text: &str) -> Option<(IpNet, String)> {
    if let Ok(ip) = text.parse::<IpAddr>() {
        let ip = ip.to_canonical();
        return Some((IpNet::from(ip), ip.to_string()));
    }
    let net = super::config::canonical_net(text.parse::<IpNet>().ok()?);
    Some((net, net.to_string()))
}

#[cfg(test)]
mod tests {
    use super::{BlockError, NewBlockRequest, parse_target};

    fn request(target: &str, reason: &str, expires: Option<u64>) -> NewBlockRequest {
        NewBlockRequest {
            target: target.to_owned(),
            reason: reason.to_owned(),
            expires_in_s: expires,
        }
    }

    #[test]
    fn targets_are_addresses_or_blocks() {
        assert_eq!(
            parse_target("203.0.113.42").map(|(_, shown)| shown),
            Some("203.0.113.42".to_owned())
        );
        assert_eq!(
            parse_target("203.0.113.9/24").map(|(_, shown)| shown),
            Some("203.0.113.0/24".to_owned())
        );
        assert!(parse_target("example.org").is_none());
        assert_eq!(
            parse_target("::ffff:203.0.113.7").map(|(_, shown)| shown),
            Some("203.0.113.7".to_owned())
        );
        assert_eq!(
            parse_target("::ffff:203.0.113.0/120").map(|(_, shown)| shown),
            Some("203.0.113.0/24".to_owned())
        );
        assert!(parse_target("203.0.113.0/33").is_none());
    }

    #[test]
    fn checks_refuse_bad_fields_and_broad_ranges() {
        assert!(matches!(
            request("nope", "x", None).check(),
            Err(("target", BlockError::InvalidTarget))
        ));
        assert!(matches!(
            request("203.0.113.1", " ", None).check(),
            Err(("reason", BlockError::InvalidReason))
        ));
        assert!(matches!(
            request("203.0.113.1", &"x".repeat(201), None).check(),
            Err(("reason", BlockError::InvalidReason))
        ));
        assert!(matches!(
            request("203.0.113.1", "x", Some(0)).check(),
            Err(("expires_in_s", BlockError::InvalidExpiry))
        ));
        assert!(matches!(
            request("203.0.113.1", "x", Some(365 * 24 * 3600 + 1)).check(),
            Err(("expires_in_s", BlockError::InvalidExpiry))
        ));
        assert!(matches!(
            request("203.0.0.0/15", "x", None).check(),
            Err(("target", BlockError::RangeTooBroad { .. }))
        ));
        assert!(matches!(
            request("2001:db8::/47", "x", None).check(),
            Err(("target", BlockError::RangeTooBroad { .. }))
        ));
        assert!(request("203.0.0.0/16", "x", None).check().is_ok());
        assert_eq!(
            request("203.0.113.1", "Flood\u{202E}ing\u{0000}", None)
                .check()
                .map(|checked| checked.reason)
                .ok(),
            Some("Flooding".to_owned())
        );
        assert!(matches!(
            request("203.0.113.1", "\u{2066}\u{0007}", None).check(),
            Err(("reason", BlockError::InvalidReason))
        ));
        assert!(request("2001:db8::/48", "x", Some(60)).check().is_ok());
    }
}
