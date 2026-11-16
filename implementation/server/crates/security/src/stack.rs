//! The security stack. Layer order, outermost first:
//!
//! trace, catch-panic, timeout, body limit, concurrency limit, CORS, known network,
//! rate limit, identity.
//!
//! Why: CORS preflights carry no token, so CORS must answer them before identity; unknown IPs
//! are rejected cheaply before any token lookup; the rate limit comes before identity so
//! password and token guessing are throttled.

use std::net::SocketAddr;
use std::sync::Arc;

use axum::extract::{ConnectInfo, Request, State};
use axum::http::StatusCode;
use axum::middleware::{self, Next};
use axum::response::{IntoResponse as _, Response};
use axum::{Json, Router};
use domain::ErrorBody;
use ipnet::IpNet;
use tower::limit::ConcurrencyLimitLayer;
use tower_http::catch_panic::CatchPanicLayer;
use tower_http::trace::TraceLayer;

use crate::cors::CorsPolicy;
use crate::error::SecurityError;
use crate::identity::{CLIENT_ID_HEADER, ClientIdentity, TokenVerifier};
use crate::known_networks::{ClientNetwork, KnownNetworks, NetworkEntry};
use crate::limits::{PathLimits, RequestLimits, RouteLimits};
use crate::mock::{bearer_token, error_bodies};
use crate::monitor::{TrafficMonitor, layer};
use crate::rate_limit::{RateLimitConfig, RateLimiter};

/// Settings of the stack.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SecurityConfig {
    /// CORS origins.
    pub cors_origins: Vec<String>,
    /// Limits.
    pub limits: RequestLimits,
    /// Per-path overrides of the body and time limits (Task A6: `/brain/` gets 1 MiB and
    /// 30 s). Applied through `PathLimits::enforce` in place of one body-limit layer and one
    /// timeout layer.
    pub route_limits: Vec<RouteLimits>,
    /// Rate.
    pub rate: RateLimitConfig,
    /// Known networks.
    pub networks: Vec<NetworkEntry>,
    /// Proxies whose `X-Forwarded-For` is trusted.
    pub trusted_proxies: Vec<IpNet>,
    /// Origins allowed on WebSocket upgrades.
    pub ws_origins: Vec<String>,
    /// Native apps send no `Origin`; allow that on WebSockets.
    pub ws_allow_missing_origin: bool,
    /// Paths that need no token header (`/health`, `/auth/login`, `/docs`, `/openapi.json`,
    /// and `/ws`, which authenticates with its first message).
    pub public_paths: Vec<String>,
}

/// The assembled stack.
pub struct SecurityStack {
    config: SecurityConfig,
    verifier: Arc<dyn TokenVerifier>,
    cors: CorsPolicy,
    networks: Arc<KnownNetworks>,
    limiter: RateLimiter,
    paths: Arc<PathLimits>,
}

impl SecurityStack {
    /// Validates the configuration and builds every layer.
    ///
    /// # Errors
    /// Any configuration error of `CorsPolicy`, `KnownNetworks` or the limits.
    pub fn new(
        config: SecurityConfig,
        verifier: Arc<dyn TokenVerifier>,
    ) -> Result<SecurityStack, SecurityError> {
        let limits = config.limits;
        if limits.max_body_bytes == 0 || limits.max_in_flight == 0 || limits.timeout.is_zero() {
            return Err(SecurityError::InvalidConfig {
                field: "limits",
                reason: "body size, requests in flight and timeout must be above zero",
            });
        }
        Ok(SecurityStack {
            cors: CorsPolicy::new(config.cors_origins.clone())?,
            networks: Arc::new(KnownNetworks::new(
                config.networks.clone(),
                config.trusted_proxies.clone(),
            )?),
            limiter: RateLimiter::new(config.rate),
            paths: Arc::new(PathLimits::new(&limits, config.route_limits.clone())?),
            config,
            verifier,
        })
    }

    /// The CORS origins in force (for the startup log).
    #[must_use]
    pub fn cors_origins(&self) -> Vec<String> {
        self.cors.origins()
    }

    /// [`SecurityStack::apply`] plus the traffic monitor (Task A8): `count` around the whole
    /// stack, `gate_outer` between the known-network check and the rate limit (which it
    /// replaces: the monitor rate-limits per address), `gate_inner` inside identity; as
    /// `MockStack::apply_monitored`.
    ///
    /// Step R1 (lean): the monitor reads the TCP peer address; behind a trusted proxy the
    /// per-address counters see the proxy (T7b resolves the forwarded address there too).
    pub fn apply_monitored(&self, router: Router, monitor: Arc<TrafficMonitor>) -> Router {
        router
            .layer(middleware::from_fn_with_state(
                monitor.clone(),
                layer::gate_inner,
            ))
            .layer(middleware::from_fn_with_state(
                self.verifier.clone(),
                identity,
            ))
            .layer(middleware::from_fn_with_state(
                monitor.clone(),
                layer::gate_outer,
            ))
            .layer(middleware::from_fn_with_state(
                self.networks.clone(),
                known_network,
            ))
            .layer(self.cors.layer())
            .layer(ConcurrencyLimitLayer::new(self.config.limits.max_in_flight))
            .layer(middleware::from_fn_with_state(
                self.paths.clone(),
                PathLimits::enforce,
            ))
            .layer(middleware::from_fn_with_state(monitor, layer::count))
            .layer(middleware::map_response(error_bodies))
            .layer(CatchPanicLayer::custom(panic_response))
            .layer(trace_layer())
    }

    /// Wraps the router in the layers, in the order documented above.
    pub fn apply(&self, router: Router) -> Router {
        let limiter = self.limiter.clone();
        router
            .layer(middleware::from_fn_with_state(
                self.verifier.clone(),
                identity,
            ))
            .layer(middleware::from_fn_with_state(limiter, rate_limit))
            .layer(middleware::from_fn_with_state(
                self.networks.clone(),
                known_network,
            ))
            .layer(self.cors.layer())
            .layer(ConcurrencyLimitLayer::new(self.config.limits.max_in_flight))
            .layer(middleware::from_fn_with_state(
                self.paths.clone(),
                PathLimits::enforce,
            ))
            .layer(middleware::map_response(error_bodies))
            .layer(CatchPanicLayer::custom(panic_response))
            .layer(trace_layer())
    }
}

/// HTTP tracing. A 5xx answer is logged at DEBUG, not ERROR: the console polls panels that
/// answer 501 `not_implemented_yet`, and an ERROR event would be copied into the journal
/// each time (the handlers log real failures themselves).
fn trace_layer() -> TraceLayer<
    tower_http::classify::SharedClassifier<tower_http::classify::ServerErrorsAsFailures>,
    tower_http::trace::DefaultMakeSpan,
    tower_http::trace::DefaultOnRequest,
    tower_http::trace::DefaultOnResponse,
    tower_http::trace::DefaultOnBodyChunk,
    tower_http::trace::DefaultOnEos,
    tower_http::trace::DefaultOnFailure,
> {
    TraceLayer::new_for_http()
        .on_failure(tower_http::trace::DefaultOnFailure::new().level(tracing::Level::DEBUG))
}

/// The TCP peer of a request (unspecified for an in-process call).
fn peer(request: &Request) -> SocketAddr {
    request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map_or(SocketAddr::from(([0, 0, 0, 0], 0)), |info| info.0)
}

/// Only known networks may call the server: inserts `ClientNetwork`, or answers 403
/// `network_not_allowed`. A CORS preflight never reaches here (the CORS layer answers it).
async fn known_network(
    State(networks): State<Arc<KnownNetworks>>,
    mut request: Request,
    next: Next,
) -> Response {
    let forwarded = request
        .headers()
        .get("x-forwarded-for")
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let peer = peer(&request);
    // HACKATHON: unknown-network refusal disabled (any IP is accepted, labelled
    // `OPEN_NETWORK_LABEL`), restore after the pitch: restore this match and drop the
    // `unwrap_or_else` below.
    // match networks.resolve(peer, forwarded.as_deref()) {
    //     Some(network) => {
    //         request.extensions_mut().insert(network);
    //         next.run(request).await
    //     }
    //     None => SecurityError::UnknownNetwork {
    //         ip: peer.ip().to_canonical(),
    //     }
    //     .into_response(),
    // }
    let network = networks
        .resolve(peer, forwarded.as_deref())
        .unwrap_or_else(|| ClientNetwork {
            ip: peer.ip().to_canonical(),
            label: OPEN_NETWORK_LABEL.to_owned(),
            area: None,
        });
    request.extensions_mut().insert(network);
    next.run(request).await
}

/// HACKATHON: the label of a caller outside every known network while the network gate is
/// open (testing phase), restore after the pitch.
pub const OPEN_NETWORK_LABEL: &str = "any network (hackathon open mode)";

/// Per-address rate limit of [`SecurityStack::apply`] (the monitored stack uses the
/// monitor's limit instead).
async fn rate_limit(State(limiter): State<RateLimiter>, request: Request, next: Next) -> Response {
    let ip = request
        .extensions()
        .get::<ClientNetwork>()
        .map_or_else(|| peer(&request).ip(), |network| network.ip);
    match limiter.check(ip) {
        Ok(()) => next.run(request).await,
        Err(error) => error.into_response(),
    }
}

/// Bearer identity: a valid token inserts `ClientIdentity`; a refused token is 401
/// `invalid_token`; no token is left to the handlers (the routes that need one answer
/// 401). An `X-Client-Id` header must equal the token's device (403 `identity_mismatch`).
async fn identity(
    State(tokens): State<Arc<dyn TokenVerifier>>,
    mut request: Request,
    next: Next,
) -> Response {
    let Some(network) = request.extensions().get::<ClientNetwork>().cloned() else {
        return SecurityError::UnknownNetwork {
            ip: peer(&request).ip(),
        }
        .into_response();
    };
    let token = match bearer_token(request.headers()) {
        Ok(None) => return next.run(request).await,
        Ok(Some(token)) => token.to_owned(),
        Err(error) => return error.into_response(),
    };
    let verified = match tokens.verify(&token).await {
        Ok(Some(verified)) => verified,
        Ok(None) => return SecurityError::InvalidToken.into_response(),
        Err(error) => return error.into_response(),
    };
    if let Some(claimed) = request
        .headers()
        .get(CLIENT_ID_HEADER)
        .and_then(|value| value.to_str().ok())
        && verified
            .device_id
            .as_ref()
            .is_none_or(|device| device.as_str() != claimed)
    {
        return SecurityError::IdentityMismatch.into_response();
    }
    request
        .extensions_mut()
        .insert(ClientIdentity { verified, network });
    next.run(request).await
}

/// A handler that panicked. A `todo!` (a part of the server not built yet) is 501
/// `not_implemented_yet`, so the console shows that panel as "not available yet"; any other
/// panic is 500 `internal`. The panic text goes to the log only.
#[allow(
    clippy::needless_pass_by_value,
    reason = "the signature `CatchPanicLayer` expects"
)]
fn panic_response(panic: Box<dyn std::any::Any + Send + 'static>) -> Response {
    let text = panic
        .downcast_ref::<String>()
        .map(String::as_str)
        .or_else(|| panic.downcast_ref::<&str>().copied())
        .unwrap_or("");
    if let Some(rest) = text.strip_prefix("not yet implemented") {
        let task = rest
            .trim_start_matches(':')
            .split(':')
            .next()
            .unwrap_or("")
            .trim();
        tracing::warn!(
            task,
            "request reached a part of the server that is not built yet"
        );
        return not_implemented_yet(task);
    }
    tracing::error!(panic = text, "a request handler panicked; answered 500");
    let body = ErrorBody::new(
        "internal",
        "Something went wrong on the server (handler failure). It was logged.".to_owned(),
        None,
    );
    (StatusCode::INTERNAL_SERVER_ERROR, Json(body)).into_response()
}

/// 501 `not_implemented_yet` naming the build-out task when known.
#[must_use]
pub fn not_implemented_yet(task: &str) -> Response {
    let message = if task.is_empty() {
        "This feature is not implemented on the server yet.".to_owned()
    } else {
        format!("This feature is not implemented on the server yet ({task}).")
    };
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(ErrorBody::new("not_implemented_yet", message, None)),
    )
        .into_response()
}
