//! Request size, time and concurrency limits, with per-route overrides (ruling R22/R23: the
//! brain routes get a longer timeout and a larger body than the rest of the API).

use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::{StatusCode, header};
use axum::middleware::Next;
use axum::response::{IntoResponse as _, Response};
use http_body_util::Limited;

use crate::error::SecurityError;

/// Limits applied to every request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RequestLimits {
    /// Largest body.
    pub max_body_bytes: usize,
    /// Longest request.
    pub timeout: Duration,
    /// Requests served at once.
    pub max_in_flight: usize,
}

impl Default for RequestLimits {
    fn default() -> Self {
        RequestLimits {
            max_body_bytes: 64 * 1024,
            timeout: Duration::from_secs(10),
            max_in_flight: 256,
        }
    }
}

/// Other body and time limits for every path starting with `prefix` (for example `/brain/`:
/// 1 MiB and 30 s, Task A6). They replace the defaults; they do not add to them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouteLimits {
    /// Path prefix, starting with `/`.
    pub prefix: String,
    /// Largest body on these paths.
    pub max_body_bytes: usize,
    /// Longest request on these paths.
    pub timeout: Duration,
}

/// The body and time limits of each request, chosen by path: the first [`RouteLimits`]
/// whose prefix matches, else the defaults. Applied by [`PathLimits::enforce`], which both
/// stacks use in place of a single body-limit layer and a single timeout layer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PathLimits {
    default_body: usize,
    default_timeout: Duration,
    routes: Vec<RouteLimits>,
}

impl PathLimits {
    /// Checks the limits.
    ///
    /// # Errors
    /// `InvalidConfig` for a zero body or timeout, or a prefix not starting with `/`.
    pub fn new(
        defaults: &RequestLimits,
        routes: Vec<RouteLimits>,
    ) -> Result<PathLimits, SecurityError> {
        let zero = |field| SecurityError::InvalidConfig {
            field,
            reason: "it must be above zero",
        };
        if defaults.max_body_bytes == 0 {
            return Err(zero("limits.max_body_bytes"));
        }
        if defaults.timeout.is_zero() {
            return Err(zero("limits.timeout"));
        }
        for route in &routes {
            if !route.prefix.starts_with('/') {
                return Err(SecurityError::InvalidConfig {
                    field: "route_limits.prefix",
                    reason: "it must start with '/'",
                });
            }
            if route.max_body_bytes == 0 {
                return Err(zero("route_limits.max_body_bytes"));
            }
            if route.timeout.is_zero() {
                return Err(zero("route_limits.timeout"));
            }
        }
        Ok(PathLimits {
            default_body: defaults.max_body_bytes,
            default_timeout: defaults.timeout,
            routes,
        })
    }

    /// `(largest body, timeout)` for a path.
    #[must_use]
    pub fn for_path(&self, path: &str) -> (usize, Duration) {
        self.routes
            .iter()
            .find(|route| path.starts_with(&route.prefix))
            .map_or((self.default_body, self.default_timeout), |route| {
                (route.max_body_bytes, route.timeout)
            })
    }

    /// Middleware: refuses a declared `Content-Length` over the path's limit with 413, caps
    /// the body stream at that limit (the JSON extractor then answers 413), and answers 408
    /// when the request takes longer than the path's timeout. Both answers have no body; the
    /// stack's error-body layer gives them the `{error: {code, message}}` shape.
    pub async fn enforce(
        State(limits): State<Arc<PathLimits>>,
        request: Request,
        next: Next,
    ) -> Response {
        let (max_body, timeout) = limits.for_path(request.uri().path());
        let declared = request
            .headers()
            .get(header::CONTENT_LENGTH)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse::<u64>().ok());
        if declared.is_some_and(|length| length > u64::try_from(max_body).unwrap_or(u64::MAX)) {
            return StatusCode::PAYLOAD_TOO_LARGE.into_response();
        }
        let request = request.map(|body| Body::new(Limited::new(body, max_body)));
        match tokio::time::timeout(timeout, next.run(request)).await {
            Ok(response) => response,
            Err(_) => StatusCode::REQUEST_TIMEOUT.into_response(),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::{PathLimits, RequestLimits, RouteLimits};

    #[test]
    fn a_route_prefix_replaces_the_defaults() -> Result<(), crate::SecurityError> {
        let limits = PathLimits::new(
            &RequestLimits::default(),
            vec![RouteLimits {
                prefix: "/brain/".to_owned(),
                max_body_bytes: 1024 * 1024,
                timeout: Duration::from_secs(30),
            }],
        )?;
        assert_eq!(
            limits.for_path("/brain/translate"),
            (1024 * 1024, Duration::from_secs(30))
        );
        assert_eq!(
            limits.for_path("/tasks"),
            (64 * 1024, Duration::from_secs(10))
        );
        assert_eq!(
            limits.for_path("/brainy"),
            (64 * 1024, Duration::from_secs(10))
        );
        Ok(())
    }

    #[test]
    fn bad_route_limits_are_refused() {
        let bad = RouteLimits {
            prefix: "brain".to_owned(),
            max_body_bytes: 1,
            timeout: Duration::from_secs(1),
        };
        assert!(PathLimits::new(&RequestLimits::default(), vec![bad]).is_err());
    }
}
