//! `GET /monitor/summary|traffic|clients`, `GET/POST /security/blocks`,
//! `DELETE /security/blocks/{id}` (Task A8): monitoring, attack detection and blocking.
//!
//! Admin only (`monitor_security`), never rate-limited or blocked for an authenticated admin,
//! allowed in emergency mode. No personal data: addresses, network labels and counts.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use domain::ErrorBody;

use crate::dto::{
    BlockView, ClientView, ClientsQuery, MonitorSummaryView, NewBlockRequest, TrafficQuery,
    TrafficView,
};
use crate::error::{ApiError, ApiJson, ApiPath, ApiQuery};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Default and largest `window_s` of `GET /monitor/traffic`.
pub const MAX_TRAFFIC_WINDOW_S: u32 = 300;
/// Default `limit` of `GET /monitor/clients`.
pub const DEFAULT_CLIENTS_LIMIT: u32 = 20;
/// Largest `limit` of `GET /monitor/clients`.
pub const MAX_CLIENTS_LIMIT: u32 = 100;

/// Server health and load: uptime, robots, open sockets, requests and refusals per second and
/// the answer time p95 of the last 10 s, active block rules.
#[utoipa::path(
    get,
    path = "/monitor/summary",
    tag = "monitor",
    responses(
        (status = 200, description = "Summary", body = MonitorSummaryView),
        (status = 403, description = "Admin only", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn summary(
    State(state): State<AppState>,
    _auth: Authorized<perm::MonitorSecurity>,
) -> Result<Json<MonitorSummaryView>, ApiError> {
    Ok(Json(state.monitor.summary().await?))
}

/// One point per second (oldest first, at most 300) of requests served and refused, and the
/// refusals of the window by reason.
#[utoipa::path(
    get,
    path = "/monitor/traffic",
    tag = "monitor",
    params(TrafficQuery),
    responses(
        (status = 200, description = "Traffic", body = TrafficView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "`window_s` not between 1 and 300", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn traffic(
    State(state): State<AppState>,
    _auth: Authorized<perm::MonitorSecurity>,
    ApiQuery(query): ApiQuery<TrafficQuery>,
) -> Result<Json<TrafficView>, ApiError> {
    let window = query.window_s.unwrap_or(MAX_TRAFFIC_WINDOW_S);
    if !(1..=MAX_TRAFFIC_WINDOW_S).contains(&window) {
        return Err(ApiError::invalid_input(
            "window_s",
            "must be between 1 and 300 seconds",
        ));
    }
    Ok(Json(state.monitor.traffic(window).await?))
}

/// The busiest client addresses of the last 5 minutes, busiest first. `label` is what the
/// server knows the address is (a known network, a robot), never a user name.
#[utoipa::path(
    get,
    path = "/monitor/clients",
    tag = "monitor",
    params(ClientsQuery),
    responses(
        (status = 200, description = "Clients", body = Vec<ClientView>),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "`limit` not between 1 and 100", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn clients(
    State(state): State<AppState>,
    _auth: Authorized<perm::MonitorSecurity>,
    ApiQuery(query): ApiQuery<ClientsQuery>,
) -> Result<Json<Vec<ClientView>>, ApiError> {
    let limit = query.limit.unwrap_or(DEFAULT_CLIENTS_LIMIT);
    if !(1..=MAX_CLIENTS_LIMIT).contains(&limit) {
        return Err(ApiError::invalid_input(
            "limit",
            "must be between 1 and 100",
        ));
    }
    Ok(Json(state.monitor.clients(limit).await?))
}

/// The active block rules (automatic and manual).
#[utoipa::path(
    get,
    path = "/security/blocks",
    tag = "monitor",
    responses(
        (status = 200, description = "Rules", body = Vec<BlockView>),
        (status = 403, description = "Admin only", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn list_blocks(
    State(state): State<AppState>,
    _auth: Authorized<perm::MonitorSecurity>,
) -> Result<Json<Vec<BlockView>>, ApiError> {
    Ok(Json(state.monitor.blocks().await?))
}

/// Blocks an address or a block (at most /16 or /48). Takes effect on the next request,
/// including the open WebSockets of the address (closed). Never the caller's own address,
/// loopback, a connected robot or the emergency service.
#[utoipa::path(
    post,
    path = "/security/blocks",
    tag = "monitor",
    request_body = NewBlockRequest,
    responses(
        (status = 201, description = "Rule created", body = BlockView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "`invalid_field` (target not an IP or CIDR, reason empty or over 200 characters), `protected_target` (the message says which), `range_too_broad`", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn add_block(
    State(state): State<AppState>,
    auth: Authorized<perm::MonitorSecurity>,
    ApiJson(body): ApiJson<NewBlockRequest>,
) -> Result<(StatusCode, Json<BlockView>), ApiError> {
    let rule = state.monitor.add_block(&auth.identity, body).await?;
    Ok((StatusCode::CREATED, Json(rule)))
}

/// Removes a block rule.
#[utoipa::path(
    delete,
    path = "/security/blocks/{id}",
    tag = "monitor",
    params(("id" = String, Path, description = "Rule id (`blk-<n>`)")),
    responses(
        (status = 204, description = "Removed"),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "It no longer exists (expired or removed by another admin)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn remove_block(
    State(state): State<AppState>,
    auth: Authorized<perm::MonitorSecurity>,
    ApiPath(id): ApiPath<String>,
) -> Result<StatusCode, ApiError> {
    state.monitor.remove_block(&auth.identity, &id).await?;
    Ok(StatusCode::NO_CONTENT)
}
