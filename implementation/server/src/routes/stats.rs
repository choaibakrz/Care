//! `GET /stats/heat?floor=` (admin only, Task A4): where robots spend their time; and
//! `GET /stats/service?hours=` (admin only, Task A8): service counts.

use axum::Json;
use axum::extract::State;
use domain::ErrorBody;

use crate::dto::{HeatQuery, HeatView, ServiceStatsQuery, ServiceStatsView};
use crate::error::{ApiError, ApiQuery};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// The heat map of one floor: robot samples (one per robot per second) per square metre since
/// the server started. Robots only, never tablets; memory only.
#[utoipa::path(
    get,
    path = "/stats/heat",
    tag = "stats",
    params(HeatQuery),
    responses(
        (status = 200, description = "Counts per 1 m cell, row-major", body = HeatView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "Missing floor, or no such floor on the active plan", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn heat(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewStats>,
    ApiQuery(query): ApiQuery<HeatQuery>,
) -> Result<Json<HeatView>, ApiError> {
    Ok(Json(state.stats.heat(query.floor).await?))
}

/// Largest `hours` of `GET /stats/service` (30 days).
pub const MAX_SERVICE_HOURS: u32 = 720;

/// Service statistics (admin, Task A8): requests, deliveries, failures, waits, top items and
/// places, bedside tablets online. Counts only, never a person.
#[utoipa::path(
    get,
    path = "/stats/service",
    tag = "stats",
    params(ServiceStatsQuery),
    responses(
        (status = 200, description = "Counts of the window", body = ServiceStatsView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "`hours` not between 1 and 720", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn service(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewStats>,
    ApiQuery(query): ApiQuery<ServiceStatsQuery>,
) -> Result<Json<ServiceStatsView>, ApiError> {
    let hours = query.hours.unwrap_or(24);
    if !(1..=MAX_SERVICE_HOURS).contains(&hours) {
        return Err(ApiError::invalid_input(
            "hours",
            "must be between 1 and 720",
        ));
    }
    Ok(Json(state.service_stats.service(hours).await?))
}
