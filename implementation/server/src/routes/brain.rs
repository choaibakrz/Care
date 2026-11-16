//! `POST /brain/translate`, `/brain/simplify`, `/brain/summarise`, `/brain/report` and
//! `GET /brain/health` (Task A6): the server-side brain for the staff app and the console.
//!
//! Every result is a draft (`draft: true`) a staff member reads before anything is sent
//! anywhere. Texts are processed in memory only: these handlers log nothing of a body, and
//! the journal records only `BrainCall { kind, latency_ms, ok }`. When the brain is down,
//! every call is 503 `brain_unavailable`; the rest of the server keeps working.

use axum::Json;
use axum::extract::State;
use domain::{
    BrainHealth, ErrorBody, ReportDraft, ReportRequest, SimplifyRequest, SimplifyResult,
    SummariseRequest, SummaryDraft, TranslateRequest, TranslateResult,
};

use crate::error::{ApiError, ApiJson};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Translates a text with the fixed medical terms (`interprete_mots.yaml`) and checks that
/// every fixed term and every number came through. A draft: show it as one.
#[utoipa::path(
    post,
    path = "/brain/translate",
    tag = "brain",
    request_body = TranslateRequest,
    responses(
        (status = 200, description = "Translation draft with its checks", body = TranslateResult),
        (status = 403, description = "Staff roles only (use_brain)", body = ErrorBody),
        (status = 413, description = "Body over 1 MiB (body_too_large)", body = ErrorBody),
        (status = 422, description = "Invalid text or language (invalid_field), or a language pair other than French to English: French to English only today (unsupported_language)", body = ErrorBody),
        (status = 503, description = "The brain is down or busy (brain_unavailable, brain_busy)", body = ErrorBody),
        (status = 504, description = "The brain did not answer in time (brain_timeout)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn translate(
    State(state): State<AppState>,
    auth: Authorized<perm::UseBrain>,
    ApiJson(request): ApiJson<TranslateRequest>,
) -> Result<Json<TranslateResult>, ApiError> {
    Ok(Json(state.brain.translate(&auth.identity, request).await?))
}

/// Rewrites a text in plain language for a patient, in the same language. Never adds
/// medical advice; when the rewrite fails its check against the source, `simplified` is
/// `false` and the original text comes back ("could not simplify safely").
#[utoipa::path(
    post,
    path = "/brain/simplify",
    tag = "brain",
    request_body = SimplifyRequest,
    responses(
        (status = 200, description = "Simplification draft", body = SimplifyResult),
        (status = 403, description = "Staff roles only (use_brain)", body = ErrorBody),
        (status = 413, description = "Body over 1 MiB (body_too_large)", body = ErrorBody),
        (status = 422, description = "Invalid text, language or level", body = ErrorBody),
        (status = 503, description = "The brain is down or busy", body = ErrorBody),
        (status = 504, description = "The brain did not answer in time", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn simplify(
    State(state): State<AppState>,
    auth: Authorized<perm::UseBrain>,
    ApiJson(request): ApiJson<SimplifyRequest>,
) -> Result<Json<SimplifyResult>, ApiError> {
    Ok(Json(state.brain.simplify(&auth.identity, request).await?))
}

/// Summarises notes, messages, documents or transcripts. Every line names its source; a line
/// whose numbers are not in its source is dropped (and counted in `dropped`).
#[utoipa::path(
    post,
    path = "/brain/summarise",
    tag = "brain",
    request_body = SummariseRequest,
    responses(
        (status = 200, description = "Summary draft, every line with its source", body = SummaryDraft),
        (status = 403, description = "Doctor, therapist and nurse only (summarise_sources)", body = ErrorBody),
        (status = 413, description = "Body over 1 MiB (body_too_large)", body = ErrorBody),
        (status = 422, description = "No source, more than 20, two with one id, or an invalid text", body = ErrorBody),
        (status = 503, description = "The brain is down or busy", body = ErrorBody),
        (status = 504, description = "The brain did not answer in time", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn summarise(
    State(state): State<AppState>,
    auth: Authorized<perm::SummariseSources>,
    ApiJson(request): ApiJson<SummariseRequest>,
) -> Result<Json<SummaryDraft>, ApiError> {
    Ok(Json(state.brain.summarise(&auth.identity, request).await?))
}

/// Drafts a shift, incident or robot activity report of a period from server data the caller
/// may see (tasks, incidents, robot activity). No audio and no free text from patients.
#[utoipa::path(
    post,
    path = "/brain/report",
    tag = "brain",
    request_body = ReportRequest,
    responses(
        (status = 200, description = "Report draft, every line with its server source", body = ReportDraft),
        (status = 403, description = "Admin and doctor only (draft_report)", body = ErrorBody),
        (status = 413, description = "Body over 1 MiB (body_too_large)", body = ErrorBody),
        (status = 422, description = "`to` not after `from`, or a period longer than 7 days", body = ErrorBody),
        (status = 503, description = "The brain is down or busy", body = ErrorBody),
        (status = 504, description = "The brain did not answer in time", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn report(
    State(state): State<AppState>,
    auth: Authorized<perm::DraftReport>,
    ApiJson(request): ApiJson<ReportRequest>,
) -> Result<Json<ReportDraft>, ApiError> {
    Ok(Json(state.brain.report(&auth.identity, request).await?))
}

/// Asks the brain now: `up`, `degraded` (fallback only) or `down` with the reason, the models
/// loaded and the queue length. Always 200.
#[utoipa::path(
    get,
    path = "/brain/health",
    tag = "brain",
    responses(
        (status = 200, description = "The brain's health", body = BrainHealth),
        (status = 403, description = "Staff roles only (use_brain)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn health(
    State(state): State<AppState>,
    _auth: Authorized<perm::UseBrain>,
) -> Json<BrainHealth> {
    Json(state.brain.health().await)
}
