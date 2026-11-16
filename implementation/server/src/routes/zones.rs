//! `GET /zones`, `PUT /zones/{id}` (admin), `DELETE /zones/{id}` (admin).

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use domain::{ErrorBody, ZoneId};

use crate::dto::{ZoneInput, ZoneView};
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Every zone with its delivery state per robot.
#[utoipa::path(
    get,
    path = "/zones",
    tag = "zones",
    responses((status = 200, description = "Zones and delivery", body = Vec<ZoneView>)),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewMap>,
) -> Result<Json<Vec<ZoneView>>, ApiError> {
    Ok(Json(state.zones.list().await?))
}

/// Creates or replaces a zone (admin). The body's `id` must equal the path id. The new list
/// is sent to every connected robot.
#[utoipa::path(
    put,
    path = "/zones/{id}",
    tag = "zones",
    params(("id" = String, Path, description = "Zone id")),
    request_body = ZoneInput,
    responses(
        (status = 200, description = "Saved zone", body = ZoneView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "Invalid polygon or floor, or body id differs from the path id", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn upsert(
    State(state): State<AppState>,
    auth: Authorized<perm::EditZones>,
    ApiPath(id): ApiPath<ZoneId>,
    ApiJson(input): ApiJson<ZoneInput>,
) -> Result<Json<ZoneView>, ApiError> {
    if input.id != id {
        return Err(ApiError::invalid_input(
            "id",
            "must equal the zone id in the path",
        ));
    }
    Ok(Json(state.zones.upsert(&auth.identity, id, input).await?))
}

/// Deletes a zone (admin). Robots receive the reduced list.
#[utoipa::path(
    delete,
    path = "/zones/{id}",
    tag = "zones",
    params(("id" = String, Path, description = "Zone id")),
    responses(
        (status = 204, description = "Zone deleted"),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such zone", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn delete(
    State(state): State<AppState>,
    auth: Authorized<perm::EditZones>,
    ApiPath(id): ApiPath<ZoneId>,
) -> Result<StatusCode, ApiError> {
    state.zones.delete(&auth.identity, &id).await?;
    Ok(StatusCode::NO_CONTENT)
}
