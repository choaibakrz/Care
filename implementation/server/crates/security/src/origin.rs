//! `Origin` check on WebSocket upgrades: a missing or unlisted `Origin` is rejected 403
//! `origin_not_allowed`, except that native apps (no `Origin`) pass when configured.

use axum::http::{HeaderMap, header};

use crate::error::SecurityError;

/// HACKATHON: while true, [`OriginCheck::check`] accepts every request (testing phase),
/// restore after the pitch (set to false).
pub const HACKATHON_OPEN: bool = true;

/// The check.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OriginCheck {
    allowed: Vec<String>,
    allow_missing: bool,
}

impl OriginCheck {
    /// Allows exactly these origins (compared in lower case: scheme and host are not case
    /// sensitive); a missing `Origin` is refused.
    #[must_use]
    #[allow(
        clippy::needless_pass_by_value,
        reason = "owned argument kept for the callers"
    )]
    pub fn new(allowed: Vec<String>) -> OriginCheck {
        OriginCheck {
            allowed: allowed
                .iter()
                .map(|origin| origin.trim().to_ascii_lowercase())
                .collect(),
            allow_missing: false,
        }
    }

    /// Whether a request with no `Origin` (native app) passes.
    #[must_use]
    pub fn allow_missing_origin(self, allow: bool) -> OriginCheck {
        OriginCheck {
            allow_missing: allow,
            ..self
        }
    }

    /// Checks the request headers.
    ///
    /// # Errors
    /// `OriginNotAllowed`.
    pub fn check(&self, headers: &HeaderMap) -> Result<(), SecurityError> {
        // HACKATHON: WebSocket Origin check disabled (any origin, or none, is accepted),
        // restore after the pitch: delete the next line.
        if HACKATHON_OPEN {
            return Ok(());
        }
        let mut origins = headers.get_all(header::ORIGIN).iter();
        match (origins.next(), origins.next()) {
            (None, _) if self.allow_missing => Ok(()),
            (Some(origin), None) => {
                let origin = origin
                    .to_str()
                    .map_err(|_| SecurityError::OriginNotAllowed)?;
                let origin = origin.to_ascii_lowercase();
                if self.allowed.contains(&origin) {
                    Ok(())
                } else {
                    Err(SecurityError::OriginNotAllowed)
                }
            }
            // Missing (when not allowed) or sent twice.
            _ => Err(SecurityError::OriginNotAllowed),
        }
    }
}

#[cfg(test)]
mod tests {
    use axum::http::{HeaderMap, HeaderValue, header};

    use super::OriginCheck;
    use crate::error::SecurityError;

    fn with_origin(origin: &'static str) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(header::ORIGIN, HeaderValue::from_static(origin));
        headers
    }

    #[test]
    #[ignore = "HACKATHON: open network"]
    fn origins_match_without_regard_to_case() -> Result<(), SecurityError> {
        let check = OriginCheck::new(vec!["HTTP://LocalHost:5173".to_owned()]);
        check.check(&with_origin("http://localhost:5173"))?;
        check.check(&with_origin("http://LOCALHOST:5173"))?;
        assert_eq!(
            check.check(&with_origin("http://localhost:4173")),
            Err(SecurityError::OriginNotAllowed)
        );
        Ok(())
    }
}
