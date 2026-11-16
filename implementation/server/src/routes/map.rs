//! `GET /map` (with `ETag`), `GET /live`, `PUT /me/location`, `POST /me/scans`.

use axum::Json;
use axum::extract::State;
use axum::http::header::{ETAG, IF_NONE_MATCH};
use axum::http::{HeaderMap, HeaderValue, StatusCode};
use axum::response::{IntoResponse as _, Response};
use domain::ErrorBody;
use locations::{LiveSnapshot, MapView, PositionEstimate, TabletLive};

use crate::dto::{LocationUpdate, ScanBody};
use crate::error::{ApiError, ApiJson};
use crate::extractors::{Authorized, TabletAuthorized, perm};
use crate::state::AppState;

/// The active clinic plan as the admin console draws it: `{clinic_id, version, name, floors,
/// rooms, walls, places, props}`, in metres, x east, y south. Admins edit it through
/// `/clinics`; on `map.updated` with `active: true` the console fetches it again.
///
/// The `ETag` is the active plan's tag (`<clinic id>-v<version>`); `If-None-Match` with it
/// answers `304 Not Modified`.
#[utoipa::path(
    get,
    path = "/map",
    tag = "map",
    responses(
        (status = 200, description = "The active plan; `ETag` carries its tag", body = MapView),
        (status = 304, description = "The caller's copy is current")
    ),
    security(("bearer" = []))
)]
pub async fn get_map(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewMap>,
    headers: HeaderMap,
) -> Result<Response, ApiError> {
    let (view, tag) = state.map.view().await?;
    let etag = format!("\"{tag}\"");
    let etag_value =
        HeaderValue::from_str(&etag).map_err(|_| ApiError::internal("map version header"))?;
    let unchanged = headers
        .get(IF_NONE_MATCH)
        .is_some_and(|sent| sent.as_bytes() == etag.as_bytes());
    if unchanged {
        return Ok((StatusCode::NOT_MODIFIED, [(ETAG, etag_value)]).into_response());
    }
    Ok(([(ETAG, etag_value)], Json(view)).into_response())
}

/// Live positions: robots (id, task, battery, microphone) and tablets (owner label and room).
///
/// Tablets carry nothing else about a person, by construction of `TabletLive`.
#[utoipa::path(
    get,
    path = "/live",
    tag = "map",
    responses((status = 200, description = "Current live positions", body = LiveSnapshot)),
    security(("bearer" = []))
)]
pub async fn get_live(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewMap>,
) -> Result<Json<LiveSnapshot>, ApiError> {
    Ok(Json(state.locations.live().await?))
}

/// Sets the room of the caller's tablet (hand pick or QR code). Kept in memory only.
#[utoipa::path(
    put,
    path = "/me/location",
    tag = "map",
    request_body = LocationUpdate,
    responses(
        (status = 200, description = "The tablet's live entry", body = TabletLive),
        (status = 403, description = "Token bound to no device (code `device_required`)", body = ErrorBody),
        (status = 422, description = "Place is not on the map (code `unknown_place`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn put_my_location(
    State(state): State<AppState>,
    auth: TabletAuthorized<perm::ReportLocation>,
    ApiJson(body): ApiJson<LocationUpdate>,
) -> Result<Json<TabletLive>, ApiError> {
    Ok(Json(
        state
            .locations
            .set_my_location(&auth.identity, &body.place)
            .await?,
    ))
}

/// Accepts one Bluetooth scan (about 1 Hz) and returns the position estimate.
///
/// Raw scans are processed in memory and dropped: never stored, journaled or logged.
#[utoipa::path(
    post,
    path = "/me/scans",
    tag = "map",
    request_body = ScanBody,
    responses(
        (status = 200, description = "Current estimate for this tablet", body = PositionEstimate),
        (status = 403, description = "Token bound to no device (code `device_required`)", body = ErrorBody),
        (status = 422, description = "Scan rejected by validation", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn post_my_scans(
    State(state): State<AppState>,
    auth: TabletAuthorized<perm::ReportLocation>,
    ApiJson(body): ApiJson<ScanBody>,
) -> Result<Json<PositionEstimate>, ApiError> {
    Ok(Json(
        state.locations.ingest_scan(&auth.identity, body).await?,
    ))
}
