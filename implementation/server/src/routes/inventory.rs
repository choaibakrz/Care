//! `GET /inventory`, `POST /inventory/{item}/adjust` (admin).

use axum::Json;
use axum::extract::State;
use domain::{ErrorBody, ItemId, StockLevel};

use crate::dto::AdjustRequest;
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Stock of every item in the reserve.
#[utoipa::path(
    get,
    path = "/inventory",
    tag = "inventory",
    responses((status = 200, description = "Stock levels", body = Vec<StockLevel>)),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewInventory>,
) -> Result<Json<Vec<StockLevel>>, ApiError> {
    Ok(Json(state.inventory.list().await?))
}

/// Adds or removes stock by hand (admin). `delta` is a non-zero integer; `reason` defaults to
/// `admin_correction`. A result below zero is refused.
#[utoipa::path(
    post,
    path = "/inventory/{item}/adjust",
    tag = "inventory",
    params(("item" = String, Path, description = "Item id")),
    request_body = AdjustRequest,
    responses(
        (status = 200, description = "New stock level", body = StockLevel),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such item", body = ErrorBody),
        (status = 409, description = "Not enough stock to remove", body = ErrorBody),
        (status = 422, description = "`delta` is zero or not an integer", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn adjust(
    State(state): State<AppState>,
    auth: Authorized<perm::AdjustInventory>,
    ApiPath(item): ApiPath<ItemId>,
    ApiJson(body): ApiJson<AdjustRequest>,
) -> Result<Json<StockLevel>, ApiError> {
    let level = state
        .inventory
        .adjust(&auth.identity, &item, body.checked_delta()?, body.reason)
        .await?;
    Ok(Json(level))
}
