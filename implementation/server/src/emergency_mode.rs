//! The emergency mode filter (Task A8, E1): while the clinic is in emergency mode, every
//! request that is not on [`EMERGENCY_ALLOW_LIST`] is answered 503 `emergency_mode` with the
//! message of `implementation/admin/requirements/emergency-mode.md`, before its handler
//! runs. One middleware, one table (route pattern as the router matched it).
//!
//! The emergency stop and every robot command are always allowed: robots must stay
//! controllable (and A7's estop latch still applies, in the robot service).

use axum::extract::{MatchedPath, Request, State};
use axum::http::Method;
use axum::middleware::Next;
use axum::response::{IntoResponse as _, Response};
use domain::RejectReason;
use security::RejectMarker;

use crate::error::ApiError;
use crate::state::AppState;

/// What is still served in emergency mode: `(method, route pattern)`. `None` as the method
/// means every method of that route (the WebSocket upgrades, the mode itself).
///
/// The documented table, plus additions that add no work: `GET /health` (liveness),
/// `GET /auth/derivation` (signing in needs it), the admin's revert of a staff robot
/// command (a robot command too) and disabling an account (ruling R26). The tablet registry routes are allowed by `tablets.md`
/// ("handing a tablet to a doctor may be part of the emergency").
pub const EMERGENCY_ALLOW_LIST: &[(Option<&str>, &str)] = &[
    (Some("GET"), "/health"),
    (Some("POST"), "/auth/login"),
    (Some("GET"), "/auth/derivation"),
    (Some("GET"), "/me"),
    // Lead's decision (R26): an admin can still lock out a stolen account.
    (Some("DELETE"), "/admin/accounts/{account_tag}"),
    (None, "/system/mode"),
    (Some("POST"), "/robots/{id}/command"),
    (Some("POST"), "/robots/{id}/commands/{command_id}/revert"),
    (Some("GET"), "/robots"),
    (Some("GET"), "/fleet/home"),
    (Some("GET"), "/map"),
    (Some("GET"), "/live"),
    (Some("GET"), "/zones"),
    (Some("GET"), "/tasks"),
    (Some("GET"), "/tasks/{id}"),
    (Some("POST"), "/tasks/{id}/cancel"),
    (Some("PUT"), "/me/location"),
    (Some("POST"), "/me/scans"),
    (Some("POST"), "/devices/me/events"),
    (Some("GET"), "/incidents"),
    (Some("POST"), "/incidents/{id}/ack"),
    (Some("POST"), "/incidents/{id}/close"),
    (Some("GET"), "/monitor/summary"),
    (Some("GET"), "/monitor/traffic"),
    (Some("GET"), "/monitor/clients"),
    (Some("GET"), "/security/blocks"),
    (Some("POST"), "/security/blocks"),
    (Some("DELETE"), "/security/blocks/{id}"),
    (Some("GET"), "/devices"),
    (Some("POST"), "/devices/{id}/disconnect"),
    (Some("POST"), "/devices/{id}/assign"),
    (None, "/ws"),
    (None, "/ws/robot/{id}"),
];

/// Whether `method` on the route `pattern` is served in emergency mode. `HEAD` and
/// `OPTIONS` follow `GET` (they change nothing).
#[must_use]
pub fn allowed_in_emergency(method: &Method, pattern: &str) -> bool {
    let method = if *method == Method::HEAD || *method == Method::OPTIONS {
        Method::GET
    } else {
        method.clone()
    };
    EMERGENCY_ALLOW_LIST.iter().any(|(allowed, route)| {
        *route == pattern && allowed.is_none_or(|name| name == method.as_str())
    })
}

/// The filter (a route layer, so the route pattern is known): 503 `emergency_mode`, marked
/// for the monitor's counters, for anything off the list while the mode is on.
pub async fn emergency_filter(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    if !state.system.is_emergency() {
        return next.run(request).await;
    }
    let allowed = request
        .extensions()
        .get::<MatchedPath>()
        .is_some_and(|pattern| allowed_in_emergency(request.method(), pattern.as_str()));
    if allowed {
        return next.run(request).await;
    }
    let mut response = ApiError::emergency_mode().into_response();
    response
        .extensions_mut()
        .insert(RejectMarker(RejectReason::EmergencyMode));
    response
}

#[cfg(test)]
mod tests {
    use axum::http::Method;

    use super::{EMERGENCY_ALLOW_LIST, allowed_in_emergency};

    /// Every row of the documented table, route by route.
    #[test]
    fn every_documented_route_is_allowed() {
        for (method, pattern) in [
            (Method::POST, "/auth/login"),
            (Method::GET, "/me"),
            (Method::GET, "/system/mode"),
            (Method::PUT, "/system/mode"),
            (Method::POST, "/robots/{id}/command"),
            (Method::GET, "/robots"),
            (Method::GET, "/map"),
            (Method::GET, "/live"),
            (Method::GET, "/zones"),
            (Method::GET, "/tasks"),
            (Method::GET, "/tasks/{id}"),
            (Method::POST, "/tasks/{id}/cancel"),
            (Method::PUT, "/me/location"),
            (Method::POST, "/me/scans"),
            (Method::POST, "/devices/me/events"),
            (Method::GET, "/incidents"),
            (Method::POST, "/incidents/{id}/ack"),
            (Method::POST, "/incidents/{id}/close"),
            (Method::GET, "/monitor/summary"),
            (Method::GET, "/monitor/traffic"),
            (Method::GET, "/monitor/clients"),
            (Method::GET, "/security/blocks"),
            (Method::POST, "/security/blocks"),
            (Method::DELETE, "/security/blocks/{id}"),
            (Method::GET, "/ws"),
            (Method::GET, "/ws/robot/{id}"),
            (Method::GET, "/devices"),
            (Method::DELETE, "/admin/accounts/{account_tag}"),
            (Method::POST, "/devices/{id}/disconnect"),
            (Method::POST, "/devices/{id}/assign"),
        ] {
            assert!(allowed_in_emergency(&method, pattern), "{method} {pattern}");
        }
    }

    #[test]
    fn the_documented_refusals_are_refused() {
        for (method, pattern) in [
            (Method::POST, "/tasks"),
            (Method::POST, "/inventory/{item}/adjust"),
            (Method::PUT, "/zones/{id}"),
            (Method::DELETE, "/zones/{id}"),
            (Method::PUT, "/schedules/{id}"),
            (Method::POST, "/clinics"),
            (Method::PUT, "/clinics/{id}"),
            (Method::DELETE, "/clinics/{id}"),
            (Method::POST, "/clinics/{id}/activate"),
            (Method::POST, "/brain/translate"),
            (Method::GET, "/brain/health"),
            (Method::GET, "/stats/heat"),
            (Method::GET, "/stats/service"),
            (Method::GET, "/inventory"),
            (Method::GET, "/schedules"),
            (Method::GET, "/audit"),
            (Method::GET, "/tasks/{id}/route"),
            (Method::POST, "/admin/enrolment-codes"),
        ] {
            assert!(
                !allowed_in_emergency(&method, pattern),
                "{method} {pattern}"
            );
        }
    }

    /// Every row names a route the router really has (the OpenAPI document lists every route
    /// with its methods), so a typo cannot silently refuse an emergency action.
    #[test]
    fn every_allowed_pattern_is_a_real_route() -> Result<(), Box<dyn std::error::Error>> {
        use utoipa::OpenApi as _;
        let doc = serde_json::to_value(crate::openapi::ApiDoc::openapi())?;
        let paths = doc.get("paths").ok_or("no paths")?;
        for (method, pattern) in EMERGENCY_ALLOW_LIST {
            let route = paths
                .get(*pattern)
                .ok_or_else(|| format!("{pattern} is not a route"))?;
            if let Some(method) = method {
                assert!(
                    route.get(method.to_lowercase()).is_some(),
                    "{method} {pattern} is not a route"
                );
            }
        }
        Ok(())
    }

    #[test]
    fn head_and_options_follow_get_and_writes_need_their_own_row() {
        assert!(allowed_in_emergency(&Method::HEAD, "/robots"));
        assert!(allowed_in_emergency(&Method::OPTIONS, "/map"));
        assert!(!allowed_in_emergency(&Method::POST, "/robots"));
        assert!(!allowed_in_emergency(&Method::DELETE, "/tasks/{id}"));
        // Every pattern of the table is written as the router declares it.
        for (_, pattern) in EMERGENCY_ALLOW_LIST {
            assert!(pattern.starts_with('/'), "{pattern}");
        }
    }
}
