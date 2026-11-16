//! CORS with an explicit origin list (never `*`).

use std::time::Duration;

use axum::http::{HeaderName, HeaderValue, Method, header};
use tower_http::cors::{AllowOrigin, CorsLayer};

use crate::error::SecurityError;

/// Preflight cache duration.
pub const CORS_MAX_AGE: Duration = Duration::from_mins(10);

/// Validated CORS policy. Methods GET, POST, PUT, DELETE, OPTIONS; headers `authorization`,
/// `content-type`, `if-match`, `x-client-id`; `ETag` exposed (clinic plans); max-age 600 s.
#[derive(Debug, Clone)]
pub struct CorsPolicy {
    allowed: Vec<HeaderValue>,
}

impl CorsPolicy {
    /// Validates the origins.
    ///
    /// # Errors
    /// `WildcardOrigin` for `"*"`; `InvalidOrigin` for anything not `scheme://host[:port]`.
    pub fn new(allowed_origins: Vec<String>) -> Result<CorsPolicy, SecurityError> {
        let allowed = allowed_origins
            .into_iter()
            .map(|origin| parse_origin(&origin))
            .collect::<Result<Vec<_>, _>>()?;
        Ok(CorsPolicy { allowed })
    }

    /// The tower-http layer.
    #[allow(
        clippy::unused_self,
        reason = "HACKATHON: the origin list is unused while CORS is open"
    )]
    pub fn layer(&self) -> CorsLayer {
        // HACKATHON: CORS origin allow-list disabled (any origin mirrored, credentials
        // allowed), restore after the pitch: uncomment this and drop `open_layer()` below.
        // CorsLayer::new()
        //     .allow_origin(AllowOrigin::list(self.allowed.clone()))
        //     .allow_methods([
        //         Method::GET,
        //         Method::POST,
        //         Method::PUT,
        //         Method::DELETE,
        //         Method::OPTIONS,
        //     ])
        //     .allow_headers([
        //         header::AUTHORIZATION,
        //         header::CONTENT_TYPE,
        //         header::IF_MATCH,
        //         HeaderName::from_static(crate::identity::CLIENT_ID_HEADER),
        //     ])
        //     .expose_headers([header::ETAG])
        //     .max_age(CORS_MAX_AGE)
        open_layer()
    }

    /// The allowed origins, as configured.
    #[must_use]
    pub fn origins(&self) -> Vec<String> {
        self.allowed
            .iter()
            .filter_map(|value| value.to_str().ok().map(str::to_owned))
            .collect()
    }
}

/// HACKATHON: the open CORS policy of the testing phase, restore after the pitch. Any origin
/// is accepted (the request `Origin` is mirrored, so credentials, the patient session
/// cookie, are allowed too); methods GET, POST, PUT, PATCH, DELETE, OPTIONS; headers
/// `authorization`, `content-type`, `x-client-id`, `if-match`; `ETag`, `Retry-After` and
/// `Content-Disposition` exposed.
pub fn open_layer() -> CorsLayer {
    CorsLayer::new()
        .allow_origin(AllowOrigin::mirror_request())
        .allow_credentials(true)
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([
            header::AUTHORIZATION,
            header::CONTENT_TYPE,
            header::IF_MATCH,
            HeaderName::from_static(crate::identity::CLIENT_ID_HEADER),
        ])
        .expose_headers([
            header::ETAG,
            header::RETRY_AFTER,
            header::CONTENT_DISPOSITION,
        ])
        .vary([header::ORIGIN])
        .max_age(CORS_MAX_AGE)
}

/// Checks one origin: `http` or `https`, a host, an optional port, nothing else (no path,
/// no trailing slash, no wildcard). The result is lowercased: scheme and host are not case
/// sensitive and browsers send them in lower case, so `http://LocalHost:5173` matches.
fn parse_origin(origin: &str) -> Result<HeaderValue, SecurityError> {
    if origin.trim() == "*" {
        return Err(SecurityError::WildcardOrigin);
    }
    let invalid = |reason: &'static str| SecurityError::InvalidOrigin {
        origin: origin.to_owned(),
        reason,
    };
    let normalized = origin.to_ascii_lowercase();
    let rest = normalized
        .strip_prefix("http://")
        .or_else(|| normalized.strip_prefix("https://"))
        .ok_or_else(|| invalid("it must start with http:// or https://"))?;
    if rest.is_empty() {
        return Err(invalid("it has no host"));
    }
    if rest.contains('*') {
        return Err(invalid("wildcards are not allowed"));
    }
    if rest
        .chars()
        .any(|c| matches!(c, '/' | '?' | '#' | '@') || c.is_whitespace())
    {
        return Err(invalid("it must not contain a path, query, user or spaces"));
    }
    let (host, port) = if let Some(after) = rest.strip_prefix('[') {
        // An IPv6 literal: `[::1]` or `[::1]:5173`.
        let (inside, tail) = after
            .split_once(']')
            .ok_or_else(|| invalid("the IPv6 address has no closing ]"))?;
        let port = match tail {
            "" => None,
            tail => Some(
                tail.strip_prefix(':')
                    .ok_or_else(|| invalid("only a port may follow the IPv6 address"))?,
            ),
        };
        (inside, port)
    } else {
        match rest.split_once(':') {
            Some((host, port)) => (host, Some(port)),
            None => (rest, None),
        }
    };
    if host.is_empty() {
        return Err(invalid("it has no host"));
    }
    if let Some(port) = port
        && port.parse::<u16>().is_err()
    {
        return Err(invalid("the port is not a number from 0 to 65535"));
    }
    HeaderValue::from_str(&normalized)
        .map_err(|_| invalid("it contains characters not allowed in a header"))
}

#[cfg(test)]
mod tests {
    use super::CorsPolicy;
    use crate::error::SecurityError;

    #[test]
    fn console_origins_are_accepted() -> Result<(), SecurityError> {
        let policy = CorsPolicy::new(vec![
            "http://localhost:5173".to_owned(),
            "http://127.0.0.1:5173".to_owned(),
            "https://clinic.example".to_owned(),
        ])?;
        assert_eq!(policy.origins().len(), 3);
        Ok(())
    }

    #[test]
    fn origins_are_lowercased() -> Result<(), SecurityError> {
        let policy = CorsPolicy::new(vec!["HTTP://LocalHost:5173".to_owned()])?;
        assert_eq!(policy.origins(), ["http://localhost:5173"]);
        Ok(())
    }

    #[test]
    fn malformed_origins_are_refused() {
        for bad in [
            "localhost:5173",
            "http://",
            "http://localhost:5173/",
            "http://localhost:99999",
            "http://*.example",
            "ftp://host",
        ] {
            let result = CorsPolicy::new(vec![bad.to_owned()]);
            assert!(
                matches!(result, Err(SecurityError::InvalidOrigin { .. })),
                "{bad}: {result:?}"
            );
        }
        assert!(matches!(
            CorsPolicy::new(vec!["*".to_owned()]),
            Err(SecurityError::WildcardOrigin)
        ));
    }
}
