//! `POST /devices/me/events`: a tablet reports its own error from the closed catalogue; and
//! the tablet registry of Task A8 (admin): `GET /devices`, `POST /devices/{id}/disconnect`,
//! `POST /devices/{id}/assign`.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use domain::{DeviceId, ErrorBody};

use crate::dto::{AssignTabletRequest, DeviceEventRequest, TabletView};
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authorized, TabletAuthorized, perm};
use crate::state::AppState;

/// Records a device error as an incident on the tablet's room. An unknown code is 422
/// (the catalogue is closed: no free text from any device).
#[utoipa::path(
    post,
    path = "/devices/me/events",
    tag = "incidents",
    request_body = DeviceEventRequest,
    responses(
        (status = 202, description = "Event accepted"),
        (status = 403, description = "Token bound to no device (code `device_required`)", body = ErrorBody),
        (status = 422, description = "Unknown event code", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn report_event(
    State(state): State<AppState>,
    auth: TabletAuthorized<perm::ReportDeviceEvent>,
    ApiJson(body): ApiJson<DeviceEventRequest>,
) -> Result<StatusCode, ApiError> {
    state
        .incidents
        .report_device_event(&auth.identity, body.code)
        .await?;
    Ok(StatusCode::ACCEPTED)
}

/// The tablet registry (admin, Task A8): every registered tablet, free and offline ones
/// included. Labels are staff pseudonyms or beds, never patients; no health field.
#[utoipa::path(
    get,
    path = "/devices",
    tag = "devices",
    responses(
        (status = 200, description = "Tablets", body = Vec<TabletView>),
        (status = 403, description = "Admin only", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ManageDevices>,
) -> Result<Json<Vec<TabletView>>, ApiError> {
    Ok(Json(state.devices.list().await?))
}

/// Frees a tablet (admin): its session token is revoked at once (whoever used it is signed
/// out), its label and speciality are cleared, it goes back to its shelf. Body `{}`.
#[utoipa::path(
    post,
    path = "/devices/{id}/disconnect",
    tag = "devices",
    params(("id" = String, Path, description = "Device id")),
    responses(
        (status = 200, description = "The freed tablet", body = TabletView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "Unknown device (code `not_found`)", body = ErrorBody),
        (status = 409, description = "Already free (code `already_free`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn disconnect(
    State(state): State<AppState>,
    auth: Authorized<perm::ManageDevices>,
    ApiPath(id): ApiPath<DeviceId>,
) -> Result<Json<TabletView>, ApiError> {
    Ok(Json(state.devices.disconnect(&auth.identity, &id).await?))
}

/// Hands a free, connected tablet out (admin): to a staff member (pseudonym, speciality) or
/// to a bed (bed label, its patient room). The tablet's next login is bound to it.
#[utoipa::path(
    post,
    path = "/devices/{id}/assign",
    tag = "devices",
    params(("id" = String, Path, description = "Device id")),
    request_body = AssignTabletRequest,
    responses(
        (status = 200, description = "The assigned tablet", body = TabletView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "Unknown device (code `not_found`)", body = ErrorBody),
        (status = 409, description = "In use (code `in_use`: free it first) or not connected (code `offline`)", body = ErrorBody),
        (status = 422, description = "Label empty, over 40 characters or digits only; bedside without a patient-room place or with a speciality (code `invalid_field`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn assign(
    State(state): State<AppState>,
    auth: Authorized<perm::ManageDevices>,
    ApiPath(id): ApiPath<DeviceId>,
    ApiJson(body): ApiJson<AssignTabletRequest>,
) -> Result<Json<TabletView>, ApiError> {
    Ok(Json(state.devices.assign(&auth.identity, &id, body).await?))
}
