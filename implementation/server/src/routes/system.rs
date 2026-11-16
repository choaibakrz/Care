//! `GET /system/mode`, `PUT /system/mode` (Task A8): emergency mode.

use axum::Json;
use axum::extract::State;
use domain::{ErrorBody, SystemModeState};

use crate::dto::SetModeRequest;
use crate::error::{ApiError, ApiJson};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Whether the clinic is in emergency mode (any signed-in caller). Allowed in emergency
/// mode, never rate-limited for an authenticated admin.
#[utoipa::path(
    get,
    path = "/system/mode",
    tag = "system",
    responses(
        (status = 200, description = "The mode in force", body = SystemModeState),
        (status = 401, description = "Not signed in", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn get_mode(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewSystemMode>,
) -> Result<Json<SystemModeState>, ApiError> {
    Ok(Json(state.system.mode().await?))
}

/// Switches emergency mode on or off (admin). Always allowed, in both modes; switching to the
/// mode in force is 200 with no change. Entering: every other request is refused with 503
/// `emergency_mode`, robots go to their docks (a robot carrying an item is paused where it
/// is), no task is handed out. Leaving: only the robots the server paused are resumed.
/// Patient alarms (the emergency service) are never touched.
#[utoipa::path(
    put,
    path = "/system/mode",
    tag = "system",
    request_body = SetModeRequest,
    responses(
        (status = 200, description = "The mode in force after the switch", body = SystemModeState),
        (status = 403, description = "Not an admin (code `forbidden`)", body = ErrorBody),
        (status = 422, description = "`mode` not `normal`/`emergency`, or `reason` over 200 characters (code `invalid_field`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn put_mode(
    State(state): State<AppState>,
    auth: Authorized<perm::SwitchSystemMode>,
    ApiJson(body): ApiJson<SetModeRequest>,
) -> Result<Json<SystemModeState>, ApiError> {
    Ok(Json(state.system.set_mode(&auth.identity, body).await?))
}
