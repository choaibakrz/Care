//! `GET /incidents`, `POST /incidents/{id}/ack`, `POST /incidents/{id}/close` (admin).
//!
//! Emergency alarms mirrored from the emergency service appear here read-only; they are
//! acknowledged only in the emergency service.

use axum::Json;
use axum::extract::State;
use domain::ErrorBody;
use realtime::{Incident, IncidentId};

use crate::dto::IncidentListQuery;
use crate::error::{ApiError, ApiPath, ApiQuery};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Incidents, open only by default (`?open=false` includes closed ones).
#[utoipa::path(
    get,
    path = "/incidents",
    tag = "incidents",
    params(IncidentListQuery),
    responses((status = 200, description = "Incidents", body = Vec<Incident>)),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewIncidents>,
    ApiQuery(query): ApiQuery<IncidentListQuery>,
) -> Result<Json<Vec<Incident>>, ApiError> {
    Ok(Json(
        state
            .incidents
            .list_incidents(query.open.unwrap_or(true))
            .await?,
    ))
}

/// Acknowledges an incident; the caller's owner label is recorded.
#[utoipa::path(
    post,
    path = "/incidents/{id}/ack",
    tag = "incidents",
    params(("id" = u64, Path, description = "Incident id")),
    responses(
        (status = 200, description = "Acknowledged", body = Incident),
        (status = 404, description = "No such incident", body = ErrorBody),
        (status = 409, description = "Emergency alarms are acknowledged in the emergency service", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn ack(
    State(state): State<AppState>,
    auth: Authorized<perm::AckIncident>,
    ApiPath(id): ApiPath<IncidentId>,
) -> Result<Json<Incident>, ApiError> {
    Ok(Json(state.incidents.acknowledge(&auth.identity, id).await?))
}

/// Closes an incident (admin).
#[utoipa::path(
    post,
    path = "/incidents/{id}/close",
    tag = "incidents",
    params(("id" = u64, Path, description = "Incident id")),
    responses(
        (status = 200, description = "Closed", body = Incident),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such incident", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn close(
    State(state): State<AppState>,
    auth: Authorized<perm::CloseIncident>,
    ApiPath(id): ApiPath<IncidentId>,
) -> Result<Json<Incident>, ApiError> {
    Ok(Json(
        state.incidents.close_incident(&auth.identity, id).await?,
    ))
}
