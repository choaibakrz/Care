//! The middleware that feeds [`TrafficMonitor`]: `count` around the stack, `gate_outer`
//! before the identity check and `gate_inner` after it.
//!
//! The gate runs before identity so password and token guessing are throttled. Two kinds of
//! request must get through whatever the rules: an authenticated admin's exempt request
//! ([`admin_exempt`]) and a robot reconnecting to its own socket (`/ws/robot/{id}` with that
//! robot's token). Carrying a well-formed `Bearer <token>`, they are **deferred** (ruling
//! R26): the outer gate looks at the address without taking anything
//! ([`TrafficMonitor::peek`]); if it would be refused, the request is marked
//! pending-refusal. After identity, a verified admin (or the robot) passes; anything else
//! goes through the rules, and a 401 from identity on a marked request is rewritten to the
//! pending 403 `blocked` / 429 `rate_limited`. Refused tokens on those deferred routes count
//! per address like failed logins (also when rewritten): past the threshold the address is
//! blocked, and the block stays alive while guessing continues. Deferrable requests are
//! deferred even from a guessing address (R27: the admin's estop first); other routes are
//! refused before the verifier by the block. **An authenticated admin's robot command (the
//! emergency stop included), mode switch, monitoring or block request is never refused.**

use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::Arc;
use std::time::Instant;

use axum::extract::{ConnectInfo, Request, State};
use axum::http::{Method, header};
use axum::middleware::Next;
use axum::response::{IntoResponse as _, Response};
use domain::{Actor, RejectReason, Role};

use super::traffic::{Admission, Outcome, TrafficMonitor};
use crate::error::SecurityError;
use crate::identity::ClientIdentity;

/// Put on a response (extension) by the layer that refused it, so the counter files it
/// under the right reason (`blocked`, `emergency_mode`) rather than by status alone.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RejectMarker(pub RejectReason);

/// Put on a response by `gate_outer` when identity refused the token of a deferred request
/// (an admin-exempt route or `/ws/robot/{id}`), also when the answer was rewritten to the
/// pending 403/429 (R27): the counter files it as a refused token. Refused tokens on other
/// routes (a revoked tablet polling `PUT /me/location`) are not counted, so they cannot
/// block an address many people share.
#[derive(Debug, Clone, Copy)]
struct TokenRefused;

/// Put on a request by `gate_outer` when the decision waits for the identity: `Some` when
/// the address would be refused (pending-refusal), `None` when it would be served.
#[allow(
    dead_code,
    reason = "the admission is carried for the Debug output only"
)]
#[derive(Debug, Clone)]
struct Deferred(Option<Admission>);

/// Whether the request carries a well-formed `Authorization: Bearer <non-empty token>`.
fn has_bearer(request: &Request) -> bool {
    request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split_once(' '))
        .is_some_and(|(scheme, token)| {
            scheme.eq_ignore_ascii_case("bearer") && !token.trim().is_empty()
        })
}

/// The robot id of a `/ws/robot/{id}` path.
fn robot_socket(path: &str) -> Option<&str> {
    path.strip_prefix("/ws/robot/")
        .filter(|id| !id.is_empty() && !id.contains('/'))
}

/// The requests an authenticated admin always gets through, whatever the rules, limits or
/// blocks: `POST /robots/{id}/command` (the emergency stop is one),
/// `POST /robots/{id}/commands/{command_id}/revert`, `/system/mode`, `/monitor/*` and
/// `/security/*`.
#[must_use]
pub fn admin_exempt(method: &Method, path: &str) -> bool {
    let robot_command = *method == Method::POST
        && path.strip_prefix("/robots/").is_some_and(|rest| {
            let parts: Vec<&str> = rest.split('/').collect();
            matches!(parts.as_slice(), [id, "command"] if !id.is_empty())
                || matches!(parts.as_slice(), [id, "commands", command, "revert"] if !id.is_empty() && !command.is_empty())
        });
    robot_command
        || path == "/system/mode"
        || path.starts_with("/monitor/")
        || path == "/security/blocks"
        || path.starts_with("/security/blocks/")
}

/// The client address: the peer (`ConnectInfo`), an IPv4-mapped IPv6 address read as IPv4;
/// unspecified when there is none (an in-process call, protected like loopback).
fn peer_ip(request: &Request) -> IpAddr {
    request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map_or(IpAddr::V4(Ipv4Addr::UNSPECIFIED), |info| {
            info.0.ip().to_canonical()
        })
}

/// Counts every answer: status, refusal reason, time, failed logins.
pub async fn count(
    State(monitor): State<Arc<TrafficMonitor>>,
    request: Request,
    next: Next,
) -> Response {
    let ip = peer_ip(&request);
    let login = request.method() == Method::POST && request.uri().path() == "/auth/login";
    let started = Instant::now();
    let response = next.run(request).await;
    let status = response.status().as_u16();
    monitor.record(
        ip,
        Outcome {
            status,
            marker: response
                .extensions()
                .get::<RejectMarker>()
                .map(|marker| marker.0),
            latency: started.elapsed(),
            login_failure: login && status == 401,
            token_failure: response.extensions().get::<TokenRefused>().is_some(),
        },
    );
    response
}

/// Blocks and rate limit, before identity. A request that may be an admin's exempt one or
/// a robot's own socket, with a well-formed bearer token, is always deferred to
/// [`gate_inner`] (marked pending-refusal when the address would be refused).
pub async fn gate_outer(
    State(monitor): State<Arc<TrafficMonitor>>,
    mut request: Request,
    next: Next,
) -> Response {
    let ip = peer_ip(&request);
    let path = request.uri().path();
    let deferrable = (admin_exempt(request.method(), path) || robot_socket(path).is_some())
        && has_bearer(&request);
    // R27: a verified admin's estop outranks "refuse before the verifier": a deferrable
    // request is always deferred, even from an address guessing tokens. The token verifier
    // takes the load of those guesses (a cheap hashed lookup); the guesser itself only ever
    // gets the pending 403/429 once its address is blocked or limited.
    if !deferrable {
        return decide(&monitor, ip, false, request, next).await;
    }
    let pending = match monitor.peek(ip) {
        Admission::Allowed => None,
        refusal => Some(refusal),
    };
    request.extensions_mut().insert(Deferred(pending.clone()));
    let response = next.run(request).await;
    if response.status().as_u16() != 401 {
        return response;
    }
    // Identity refused the token. From an address that could not make the request anyway,
    // the pending refusal, not a 401 that would tell the token was wrong; either way the
    // refused token is counted (it keeps a guesser's block alive).
    let mut response = match pending.as_ref().and_then(refusal_response) {
        Some(refusal) => refusal,
        None => response,
    };
    response.extensions_mut().insert(TokenRefused);
    response
}

/// After identity: decides the deferred requests. A verified admin on an exempt route, or
/// the robot of `/ws/robot/{id}` itself, passes; anyone else goes through the rules.
pub async fn gate_inner(
    State(monitor): State<Arc<TrafficMonitor>>,
    request: Request,
    next: Next,
) -> Response {
    let Some(Deferred(_)) = request.extensions().get::<Deferred>().cloned() else {
        return next.run(request).await;
    };
    let identity = request.extensions().get::<ClientIdentity>();
    let path = request.uri().path();
    let admin = identity.is_some_and(|identity| identity.verified.role == Role::Admin)
        && admin_exempt(request.method(), path);
    let own_socket = robot_socket(path).is_some_and(|id| {
        identity.is_some_and(|identity| {
            matches!(&identity.verified.subject_id, Actor::Robot(robot) if robot.as_str() == id)
        })
    });
    let ip = peer_ip(&request);
    decide(&monitor, ip, admin || own_socket, request, next).await
}

async fn decide(
    monitor: &TrafficMonitor,
    ip: IpAddr,
    exempt: bool,
    request: Request,
    next: Next,
) -> Response {
    let admission = monitor.admit(ip, exempt);
    if let Admission::Blocked { rule } = &admission {
        tracing::debug!(%ip, %rule, "request refused by a block rule");
    }
    match refusal_response(&admission) {
        Some(response) => response,
        None => next.run(request).await,
    }
}

/// The answer of a refusal (403 `blocked`, 429 `rate_limited`, marked); `None` to serve.
fn refusal_response(admission: &Admission) -> Option<Response> {
    match admission {
        Admission::Allowed => None,
        Admission::Blocked { .. } => Some(refused(SecurityError::Blocked, RejectReason::Blocked)),
        Admission::Limited { retry_after_s } => Some(refused(
            SecurityError::RateLimited {
                retry_after_s: *retry_after_s,
            },
            RejectReason::RateLimited,
        )),
    }
}

fn refused(error: SecurityError, reason: RejectReason) -> Response {
    let mut response = error.into_response();
    response.extensions_mut().insert(RejectMarker(reason));
    response
}

#[cfg(test)]
mod tests {
    use axum::http::Method;

    use super::{admin_exempt, robot_socket};

    #[test]
    fn exempt_routes_are_the_documented_ones() {
        for (method, path) in [
            (Method::POST, "/robots/r1/command"),
            (Method::POST, "/robots/r1/commands/abc/revert"),
            (Method::GET, "/system/mode"),
            (Method::PUT, "/system/mode"),
            (Method::GET, "/monitor/summary"),
            (Method::GET, "/monitor/traffic"),
            (Method::GET, "/monitor/clients"),
            (Method::GET, "/security/blocks"),
            (Method::POST, "/security/blocks"),
            (Method::DELETE, "/security/blocks/blk-1"),
        ] {
            assert!(admin_exempt(&method, path), "{method} {path}");
        }
        for (method, path) in [
            (Method::GET, "/robots/r1/command"),
            (Method::POST, "/robots//command"),
            (Method::POST, "/robots/r1/command/x"),
            (Method::POST, "/tasks"),
            (Method::GET, "/robots"),
            (Method::GET, "/security"),
            (Method::GET, "/system/modes"),
        ] {
            assert!(!admin_exempt(&method, path), "{method} {path}");
        }
    }

    #[test]
    fn robot_sockets_are_recognised() {
        assert_eq!(robot_socket("/ws/robot/r1"), Some("r1"));
        assert_eq!(robot_socket("/ws/robot/"), None);
        assert_eq!(robot_socket("/ws/robot/r1/x"), None);
        assert_eq!(robot_socket("/ws"), None);
    }
}
