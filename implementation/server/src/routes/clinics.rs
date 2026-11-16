//! `GET /clinics`, `POST /clinics`, `GET /clinics/{id}`, `PUT /clinics/{id}`,
//! `DELETE /clinics/{id}`, `POST /clinics/{id}/activate` (admin only, Task A4).
//!
//! A plan is one document, replaced whole. `GET /clinics/{id}` sends its version as the
//! `ETag` (`"3"`); `PUT` must send it back in `If-Match` (428 without, 412 when someone saved
//! in between). A refused plan is 422 `invalid_plan` with every problem in `error.details`.

use axum::Json;
use axum::extract::State;
use axum::http::header::ETAG;
use axum::http::{HeaderMap, HeaderValue, StatusCode};
use axum::response::{IntoResponse as _, Response};
use domain::{ClinicId, ErrorBody};
use locations::{ClinicPlan, PlanOverlay};

use crate::dto::ClinicSummary;
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// The `ETag` of a plan version: the version number in quotes.
fn version_etag(version: u64) -> Result<HeaderValue, ApiError> {
    HeaderValue::from_str(&format!("\"{version}\""))
        .map_err(|_| ApiError::internal("plan version header"))
}

/// The version in `If-Match`: `"3"` or `3`. Missing is 428 `if_match_required`; anything
/// else (a list, `*`, not a number) is 422 `invalid_field` (`If-Match`).
pub fn if_match_version(headers: &HeaderMap) -> Result<u64, ApiError> {
    let mut values = headers.get_all(axum::http::header::IF_MATCH).iter();
    let (Some(value), None) = (values.next(), values.next()) else {
        return match headers.get(axum::http::header::IF_MATCH) {
            None => Err(ApiError::if_match_required()),
            Some(_) => Err(ApiError::invalid_input(
                "If-Match",
                "must be sent once, with one version",
            )),
        };
    };
    let text = value.to_str().unwrap_or_default().trim();
    let bare = text
        .strip_prefix('"')
        .and_then(|rest| rest.strip_suffix('"'))
        .unwrap_or(text);
    if bare.is_empty() || !bare.bytes().all(|b| b.is_ascii_digit()) {
        return Err(ApiError::invalid_input(
            "If-Match",
            "must be the plan version from the ETag, such as \"3\"",
        ));
    }
    bare.parse::<u64>()
        .map_err(|_| ApiError::invalid_input("If-Match", "is too large to be a plan version"))
}

/// Every stored plan with its version and the active marker.
#[utoipa::path(
    get,
    path = "/clinics",
    tag = "clinics",
    responses(
        (status = 200, description = "Stored plans", body = Vec<ClinicSummary>),
        (status = 403, description = "Admin only", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::EditClinics>,
) -> Result<Json<Vec<ClinicSummary>>, ApiError> {
    Ok(Json(state.clinics.list().await?))
}

/// Stores a new plan (validated as a whole; version 1, not active). The id is derived from
/// the name; a name whose id is taken is 409 `clinic_exists`.
#[utoipa::path(
    post,
    path = "/clinics",
    tag = "clinics",
    request_body = ClinicPlan,
    responses(
        (status = 201, description = "Plan stored; `ETag` is its version", body = ClinicSummary),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 409, description = "A plan with the id derived from this name exists (code `clinic_exists`); rename the plan", body = ErrorBody),
        (status = 422, description = "Invalid plan (code `invalid_plan`, every problem in `error.details`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn create(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiJson(plan): ApiJson<ClinicPlan>,
) -> Result<Response, ApiError> {
    let summary = state.clinics.create(&auth.identity, plan).await?;
    let etag = version_etag(summary.version)?;
    Ok((StatusCode::CREATED, [(ETAG, etag)], Json(summary)).into_response())
}

/// One plan, as a document that `POST /clinics` and `PUT /clinics/{id}` accept back.
#[utoipa::path(
    get,
    path = "/clinics/{id}",
    tag = "clinics",
    params(("id" = String, Path, description = "Clinic plan id")),
    responses(
        (status = 200, description = "The plan; `ETag` is its version", body = ClinicPlan),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such plan", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn get(
    State(state): State<AppState>,
    _auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
) -> Result<Response, ApiError> {
    let found = state.clinics.get(&id).await?;
    let etag = version_etag(found.version)?;
    Ok(([(ETAG, etag)], Json(found.plan)).into_response())
}

/// Replaces the base plan whole and clears the modifications. Needs `If-Match` with the version that was edited. The active plan
/// takes effect at once: `map.updated` on `/ws`, `map.update` to the robots.
#[utoipa::path(
    put,
    path = "/clinics/{id}",
    tag = "clinics",
    params(
        ("id" = String, Path, description = "Clinic plan id"),
        ("If-Match" = String, Header, description = "The version that was edited, as sent in the ETag")
    ),
    request_body = ClinicPlan,
    responses(
        (status = 200, description = "The saved plan; `ETag` is the new version", body = ClinicPlan),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such plan", body = ErrorBody),
        (status = 409, description = "A removed or renamed place is still used (code `place_in_use`, users in `error.details`)", body = ErrorBody),
        (status = 412, description = "Someone saved a newer version (code `version_conflict`)", body = ErrorBody),
        (status = 422, description = "Invalid plan (code `invalid_plan`, every problem in `error.details`)", body = ErrorBody),
        (status = 428, description = "No If-Match (code `if_match_required`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn update(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
    headers: HeaderMap,
    ApiJson(plan): ApiJson<ClinicPlan>,
) -> Result<Response, ApiError> {
    let expected = if_match_version(&headers)?;
    let saved = state
        .clinics
        .update(&auth.identity, &id, expected, plan)
        .await?;
    let etag = version_etag(saved.version)?;
    Ok(([(ETAG, etag)], Json(saved.plan)).into_response())
}

/// Makes a plan the active one (what `GET /map` serves and the robots use). Refused while
/// tasks are open.
#[utoipa::path(
    post,
    path = "/clinics/{id}/activate",
    tag = "clinics",
    params(("id" = String, Path, description = "Clinic plan id")),
    responses(
        (status = 200, description = "The plan is active", body = ClinicSummary),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such plan", body = ErrorBody),
        (status = 409, description = "Open tasks (code `open_tasks`) or a place still used is missing (code `place_in_use`); the list is in `error.details`", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn activate(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
) -> Result<Json<ClinicSummary>, ApiError> {
    Ok(Json(state.clinics.activate(&auth.identity, &id).await?))
}

/// Deletes a plan that is not active.
#[utoipa::path(
    delete,
    path = "/clinics/{id}",
    tag = "clinics",
    params(("id" = String, Path, description = "Clinic plan id")),
    responses(
        (status = 204, description = "Plan deleted"),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such plan", body = ErrorBody),
        (status = 409, description = "The active plan cannot be deleted (code `clinic_active`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn delete(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
) -> Result<StatusCode, ApiError> {
    state.clinics.delete(&auth.identity, &id).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// The base plan, without the modifications (`GET /clinics/{id}` is the effective plan).
#[utoipa::path(
    get,
    path = "/clinics/{id}/base",
    tag = "clinics",
    params(("id" = String, Path, description = "Clinic plan id")),
    responses(
        (status = 200, description = "The base plan; `ETag` is the clinic version", body = ClinicPlan),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such plan", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn get_base(
    State(state): State<AppState>,
    _auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
) -> Result<Response, ApiError> {
    let found = state.clinics.base(&id).await?;
    let etag = version_etag(found.version)?;
    Ok(([(ETAG, etag)], Json(found.plan)).into_response())
}

/// Replaces the base plan and keeps the modifications; the effective plan is validated.
/// Returns the effective plan.
#[utoipa::path(
    put,
    path = "/clinics/{id}/base",
    tag = "clinics",
    params(
        ("id" = String, Path, description = "Clinic plan id"),
        ("If-Match" = String, Header, description = "The clinic version that was edited")
    ),
    request_body = ClinicPlan,
    responses(
        (status = 200, description = "The effective plan; `ETag` is the new version", body = ClinicPlan),
        (status = 404, description = "No such plan", body = ErrorBody),
        (status = 409, description = "A removed place is still used (code `place_in_use`)", body = ErrorBody),
        (status = 412, description = "Stale version (code `version_conflict`)", body = ErrorBody),
        (status = 422, description = "Invalid effective plan (code `invalid_plan`)", body = ErrorBody),
        (status = 428, description = "No If-Match (code `if_match_required`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn put_base(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
    headers: HeaderMap,
    ApiJson(plan): ApiJson<ClinicPlan>,
) -> Result<Response, ApiError> {
    let expected = if_match_version(&headers)?;
    let saved = state
        .clinics
        .put_base(&auth.identity, &id, expected, plan)
        .await?;
    let etag = version_etag(saved.version)?;
    Ok(([(ETAG, etag)], Json(saved.plan)).into_response())
}

/// The modifications of a plan (empty when none).
#[utoipa::path(
    get,
    path = "/clinics/{id}/overlay",
    tag = "clinics",
    params(("id" = String, Path, description = "Clinic plan id")),
    responses(
        (status = 200, description = "The modifications; `ETag` is the clinic version", body = PlanOverlay),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such plan", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn get_overlay(
    State(state): State<AppState>,
    _auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
) -> Result<Response, ApiError> {
    let found = state.clinics.overlay(&id).await?;
    let etag = version_etag(found.version)?;
    Ok(([(ETAG, etag)], Json(found.overlay)).into_response())
}

/// Stores the modifications. The effective plan (base plus modifications) is validated as
/// a whole; the active plan takes effect at once (`map.updated`). Returns the effective plan.
#[utoipa::path(
    put,
    path = "/clinics/{id}/overlay",
    tag = "clinics",
    params(
        ("id" = String, Path, description = "Clinic plan id"),
        ("If-Match" = String, Header, description = "The clinic version that was edited")
    ),
    request_body = PlanOverlay,
    responses(
        (status = 200, description = "The effective plan; `ETag` is the new version", body = ClinicPlan),
        (status = 404, description = "No such plan", body = ErrorBody),
        (status = 409, description = "A removed place is still used (code `place_in_use`)", body = ErrorBody),
        (status = 412, description = "Stale version (code `version_conflict`)", body = ErrorBody),
        (status = 422, description = "Invalid effective plan (code `invalid_plan`, every problem in `error.details`)", body = ErrorBody),
        (status = 428, description = "No If-Match (code `if_match_required`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn put_overlay(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
    headers: HeaderMap,
    ApiJson(overlay): ApiJson<PlanOverlay>,
) -> Result<Response, ApiError> {
    let expected = if_match_version(&headers)?;
    let saved = state
        .clinics
        .put_overlay(&auth.identity, &id, expected, overlay)
        .await?;
    let etag = version_etag(saved.version)?;
    Ok(([(ETAG, etag)], Json(saved.plan)).into_response())
}

/// Drops all modifications: the effective plan is the base again.
#[utoipa::path(
    delete,
    path = "/clinics/{id}/overlay",
    tag = "clinics",
    params(
        ("id" = String, Path, description = "Clinic plan id"),
        ("If-Match" = String, Header, description = "The clinic version that was edited")
    ),
    responses(
        (status = 200, description = "The base plan, now effective; `ETag` is the new version", body = ClinicPlan),
        (status = 404, description = "No such plan", body = ErrorBody),
        (status = 409, description = "A place that the modifications added is still used (code `place_in_use`)", body = ErrorBody),
        (status = 412, description = "Stale version (code `version_conflict`)", body = ErrorBody),
        (status = 428, description = "No If-Match (code `if_match_required`)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn reset_overlay(
    State(state): State<AppState>,
    auth: Authorized<perm::EditClinics>,
    ApiPath(id): ApiPath<ClinicId>,
    headers: HeaderMap,
) -> Result<Response, ApiError> {
    let expected = if_match_version(&headers)?;
    let saved = state
        .clinics
        .put_overlay(&auth.identity, &id, expected, PlanOverlay::default())
        .await?;
    let etag = version_etag(saved.version)?;
    Ok(([(ETAG, etag)], Json(saved.plan)).into_response())
}
