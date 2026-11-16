//! The transport stack of `clinic-server --mock` **only**.
//!
//! Mock mode serves canned, invented data to the admin console on a developer's laptop. It
//! applies the transport layers that matter for a browser client (CORS, request limits) and a
//! bearer identity check against the mock token verifier, and nothing else:
//!
//! - **no known-network check**: every caller gets the network label
//!   [`MOCK_NETWORK_LABEL`];
//! - **no rate limit** with [`MockStack::apply`]; [`MockStack::apply_monitored`] (what
//!   `clinic-server --mock` serves since Task A8) adds the monitor's counters, rate limit
//!   and blocks (`crate::monitor`), which never refuse an authenticated admin's robot
//!   command and never touch loopback;
//! - **no `X-Client-Id` check** (mock tokens are bound to no device).
//!
//! The live server never uses this type: it uses [`crate::SecurityStack`], with every layer.
//! `clinic-server --mock` says so in its startup log.
//!
//! Layer order, outermost first: trace, catch-panic, error bodies, body and time limits by
//! path (`PathLimits`: the defaults, or a route's override such as `/brain/`), concurrency
//! limit, CORS, mock identity. CORS sits outside identity so a preflight (which
//! carries no token) is answered before any token check.

use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::Arc;

use axum::extract::{ConnectInfo, Request, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse as _, Response};
use axum::{Json, Router};
use domain::ErrorBody;
use tower::limit::ConcurrencyLimitLayer;
use tower_http::catch_panic::CatchPanicLayer;
use tower_http::trace::TraceLayer;

use crate::cors::CorsPolicy;
use crate::error::SecurityError;
use crate::identity::{ClientIdentity, TokenVerifier};
use crate::known_networks::ClientNetwork;
use crate::limits::{PathLimits, RequestLimits};
use crate::monitor::{TrafficMonitor, layer};
use crate::stack::SecurityConfig;

/// The network label every mock-mode request carries (no network is checked).
pub const MOCK_NETWORK_LABEL: &str = "mock (no network check)";

/// CORS, limits and bearer identity for `--mock`. See the module documentation for what it
/// leaves out.
pub struct MockStack {
    cors: CorsPolicy,
    limits: RequestLimits,
    paths: Arc<PathLimits>,
    verifier: Arc<dyn TokenVerifier>,
}

impl MockStack {
    /// Validates the CORS origins and the limits of `config` (its networks, rate and
    /// identity settings are not used in mock mode).
    ///
    /// # Errors
    /// `WildcardOrigin` or `InvalidOrigin` for a bad CORS origin; `InvalidConfig` for a zero
    /// limit.
    pub fn new(
        config: &SecurityConfig,
        verifier: Arc<dyn TokenVerifier>,
    ) -> Result<MockStack, SecurityError> {
        let limits = config.limits;
        if limits.max_body_bytes == 0 {
            return Err(SecurityError::InvalidConfig {
                field: "limits.max_body_bytes",
                reason: "it must be above zero",
            });
        }
        if limits.max_in_flight == 0 {
            return Err(SecurityError::InvalidConfig {
                field: "limits.max_in_flight",
                reason: "it must be above zero",
            });
        }
        if limits.timeout.is_zero() {
            return Err(SecurityError::InvalidConfig {
                field: "limits.timeout",
                reason: "it must be above zero",
            });
        }
        Ok(MockStack {
            cors: CorsPolicy::new(config.cors_origins.clone())?,
            limits,
            paths: Arc::new(PathLimits::new(&limits, config.route_limits.clone())?),
            verifier,
        })
    }

    /// The CORS origins in force (for the startup log).
    #[must_use]
    pub fn cors_origins(&self) -> Vec<String> {
        self.cors.origins()
    }

    /// [`MockStack::apply`] plus the monitor (Task A8): `count` just inside the error
    /// bodies (it sees every final answer), `gate_outer` between CORS and identity,
    /// `gate_inner` inside identity. Layer order, outermost first: trace, catch-panic, error
    /// bodies, count, path limits, concurrency limit, CORS, gate (outer), mock identity, gate
    /// (inner).
    pub fn apply_monitored(&self, router: Router, monitor: Arc<TrafficMonitor>) -> Router {
        router
            .layer(middleware::from_fn_with_state(
                monitor.clone(),
                layer::gate_inner,
            ))
            .layer(middleware::from_fn_with_state(
                self.verifier.clone(),
                mock_identity,
            ))
            .layer(middleware::from_fn_with_state(
                monitor.clone(),
                layer::gate_outer,
            ))
            .layer(self.cors.layer())
            .layer(ConcurrencyLimitLayer::new(self.limits.max_in_flight))
            .layer(middleware::from_fn_with_state(
                self.paths.clone(),
                PathLimits::enforce,
            ))
            .layer(middleware::from_fn_with_state(monitor, layer::count))
            .layer(middleware::map_response(error_bodies))
            .layer(CatchPanicLayer::new())
            .layer(TraceLayer::new_for_http())
    }

    /// Wraps the router in the layers, in the order documented on the module.
    pub fn apply(&self, router: Router) -> Router {
        router
            .layer(middleware::from_fn_with_state(
                self.verifier.clone(),
                mock_identity,
            ))
            .layer(self.cors.layer())
            .layer(ConcurrencyLimitLayer::new(self.limits.max_in_flight))
            .layer(middleware::from_fn_with_state(
                self.paths.clone(),
                PathLimits::enforce,
            ))
            .layer(middleware::map_response(error_bodies))
            .layer(CatchPanicLayer::new())
            .layer(TraceLayer::new_for_http())
    }
}

/// Inserts the mock `ClientNetwork` on every request and, when a bearer token is sent, the
/// `ClientIdentity` the verifier gives. A refused token is 401 `invalid_token`; no token is
/// left to the handlers (the routes that need one answer 401).
async fn mock_identity(
    State(tokens): State<Arc<dyn TokenVerifier>>,
    mut request: Request,
    next: Next,
) -> Response {
    let ip = request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map_or(IpAddr::V4(Ipv4Addr::UNSPECIFIED), |info| info.0.ip());
    let network = ClientNetwork {
        ip,
        label: MOCK_NETWORK_LABEL.to_owned(),
        area: None,
    };
    request.extensions_mut().insert(network.clone());
    match bearer_token(request.headers()) {
        Ok(None) => {}
        Ok(Some(token)) => match tokens.verify(token).await {
            Ok(Some(verified)) => {
                request
                    .extensions_mut()
                    .insert(ClientIdentity { verified, network });
            }
            Ok(None) => return SecurityError::InvalidToken.into_response(),
            Err(error) => return error.into_response(),
        },
        Err(error) => return error.into_response(),
    }
    next.run(request).await
}

/// The bearer token, if an `Authorization` header is sent. Any other scheme is
/// `MissingToken` (its message says how to send the token).
pub(crate) fn bearer_token(headers: &HeaderMap) -> Result<Option<&str>, SecurityError> {
    let Some(value) = headers.get(header::AUTHORIZATION) else {
        return Ok(None);
    };
    let value = value.to_str().map_err(|_| SecurityError::MissingToken)?;
    let (scheme, token) = value.split_once(' ').ok_or(SecurityError::MissingToken)?;
    let token = token.trim();
    if !scheme.eq_ignore_ascii_case("bearer") || token.is_empty() {
        return Err(SecurityError::MissingToken);
    }
    Ok(Some(token))
}

/// The timeout and body-limit layers answer with an empty body; give those answers the
/// `{error: {code, message}}` shape every client reads.
pub(crate) async fn error_bodies(response: Response) -> Response {
    let has_body_type = response.headers().contains_key(header::CONTENT_TYPE);
    let (code, message) = match response.status() {
        StatusCode::REQUEST_TIMEOUT if !has_body_type => (
            "timeout",
            "The server took too long to answer this request. Try again.",
        ),
        StatusCode::PAYLOAD_TOO_LARGE if !has_body_type => (
            "body_too_large",
            "The request body is too large. Send less data.",
        ),
        _ => return response,
    };
    let status = response.status();
    (status, Json(ErrorBody::new(code, message.to_owned(), None))).into_response()
}

#[cfg(test)]
mod tests {
    use axum::http::{HeaderMap, HeaderValue, header};

    use super::bearer_token;
    use crate::error::SecurityError;

    fn headers(value: &'static str) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(header::AUTHORIZATION, HeaderValue::from_static(value));
        headers
    }

    #[test]
    fn bearer_token_is_read_case_insensitively() -> Result<(), SecurityError> {
        assert_eq!(bearer_token(&headers("Bearer abc"))?, Some("abc"));
        assert_eq!(bearer_token(&headers("bearer abc"))?, Some("abc"));
        assert_eq!(bearer_token(&HeaderMap::new())?, None);
        Ok(())
    }

    #[test]
    fn other_schemes_are_missing_token() {
        for value in ["Basic abc", "Bearer", "Bearer  ", "abc"] {
            assert_eq!(
                bearer_token(&headers(value)),
                Err(SecurityError::MissingToken),
                "{value}"
            );
        }
    }
}
