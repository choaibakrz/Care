//! `GET /schedules`, `PUT /schedules/{id}` (admin; the night restock round).

use axum::Json;
use axum::extract::State;
use domain::{ErrorBody, ScheduleId};

use crate::dto::{SchedulePatch, ScheduleView};
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Every schedule (daily, at a local time) with its last result.
#[utoipa::path(
    get,
    path = "/schedules",
    tag = "schedules",
    responses((status = 200, description = "Schedules", body = Vec<ScheduleView>)),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewSchedules>,
) -> Result<Json<Vec<ScheduleView>>, ApiError> {
    Ok(Json(state.schedules.list().await?))
}

/// Changes a schedule (admin): only the fields given in the partial body change.
#[utoipa::path(
    put,
    path = "/schedules/{id}",
    tag = "schedules",
    params(("id" = String, Path, description = "Schedule id")),
    request_body = SchedulePatch,
    responses(
        (status = 200, description = "Saved schedule", body = ScheduleView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such schedule", body = ErrorBody),
        (status = 422, description = "Invalid time or unknown robot", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn update(
    State(state): State<AppState>,
    auth: Authorized<perm::EditSchedules>,
    ApiPath(id): ApiPath<ScheduleId>,
    ApiJson(patch): ApiJson<SchedulePatch>,
) -> Result<Json<ScheduleView>, ApiError> {
    Ok(Json(
        state.schedules.update(&auth.identity, &id, patch).await?,
    ))
}
