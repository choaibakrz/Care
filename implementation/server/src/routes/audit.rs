//! `GET /audit` (admin) and `GET /audit/integrity` (admin).
//!
//! These read the audit index, a convenience copy of the sealed journal. The journal files
//! are the authority.

use audit::VerifyReport;
use axum::Json;
use axum::extract::State;
use domain::ErrorBody;

use crate::dto::{AuditPageView, AuditQueryParams};
use crate::error::{ApiError, ApiQuery};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Audit rows `{items, next}` filtered by time, actor and category; `limit` 1 to 500.
#[utoipa::path(
    get,
    path = "/audit",
    tag = "audit",
    params(AuditQueryParams),
    responses(
        (status = 200, description = "A page of audit records", body = AuditPageView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 422, description = "Invalid filter or limit above 500", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewAudit>,
    ApiQuery(params): ApiQuery<AuditQueryParams>,
) -> Result<Json<AuditPageView>, ApiError> {
    Ok(Json(state.audit.query(params).await?))
}

/// The last journal verification report (chain, seals, anchors, torn tail).
#[utoipa::path(
    get,
    path = "/audit/integrity",
    tag = "audit",
    responses(
        (status = 200, description = "Last verification report", body = VerifyReport),
        (status = 403, description = "Admin only", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn integrity(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewAudit>,
) -> Result<Json<VerifyReport>, ApiError> {
    Ok(Json(state.audit.integrity().await?))
}
