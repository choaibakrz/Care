//! `GET /fleet/home`, `PUT /fleet/home`: the fleet's home place, where the robots go in an
//! emergency, on `dock` and to recharge.

use axum::Json;
use axum::extract::State;
use domain::ErrorBody;

use crate::dto::{FleetHomeView, SetFleetHomeRequest};
use crate::error::{ApiError, ApiJson};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// The home place (all `null` when none is set). Until an admin sets one, it is the first
/// dock (or charging place) of the active plan.
#[utoipa::path(
    get,
    path = "/fleet/home",
    tag = "robots",
    responses(
        (status = 200, description = "Home place", body = FleetHomeView),
        (status = 503, description = "No fleet on this server", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn get_home(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewRobots>,
) -> Result<Json<FleetHomeView>, ApiError> {
    Ok(Json(state.robots.fleet_home().await?))
}

/// Sets the home place (admin), or clears it with `null` (robots then stop where they are on
/// `dock` and in an emergency). Stored, so a restart keeps it.
#[utoipa::path(
    put,
    path = "/fleet/home",
    tag = "robots",
    request_body = SetFleetHomeRequest,
    responses(
        (status = 200, description = "Home place", body = FleetHomeView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "Not a place of the active plan", body = ErrorBody),
        (status = 503, description = "The home place could not be stored", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn put_home(
    State(state): State<AppState>,
    _auth: Authorized<perm::EditClinics>,
    ApiJson(body): ApiJson<SetFleetHomeRequest>,
) -> Result<Json<FleetHomeView>, ApiError> {
    Ok(Json(state.robots.set_fleet_home(body.place_id).await?))
}
