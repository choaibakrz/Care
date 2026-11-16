//! The `clinic-brain` process (Task A6): a small HTTP API on loopback, in front of the brain
//! engine (`python_bindings::BrainEngine`), called only by the main server.
//!
//! | Route | Body | Answer |
//! |---|---|---|
//! | `POST /v1/translate` | `TranslateRequest` | `TranslateResult` |
//! | `POST /v1/simplify` | `SimplifyRequest` | `SimplifyResult` |
//! | `POST /v1/summarise` | `SummariseRequest` | `SummaryDraft` |
//! | `POST /v1/report` | `BrainReportRequest` | `ReportDraft` |
//! | `POST /v1/transcribe` | raw audio (`audio/webm`, `ogg`, `mp4`, `wav`; 4 MiB, 60 s) | `{text, lang, duration_s}` |
//! | `POST /v1/speak` | `{text (1..2000 chars), lang}` | `audio/wav` (16-bit PCM), 503 `brain_unavailable` without a voice |
//! | `GET /v1/health` | — | `BrainHealth` (voices as `piper:<lang>` in `models`) |
//!
//! Every route needs `Authorization: Bearer <BRAIN_TOKEN>` from a loopback peer: another
//! peer is 403 `loopback_only`, a missing or wrong token 401 `brain_token`. The bind address
//! itself must be loopback (`BrainProcessConfig`). Bodies over
//! [`BRAIN_PROCESS_MAX_BODY_BYTES`] are 413 `body_too_large` with the JSON error body.
//!
//! **Degradation.** Built without the `python` feature (the default), or when Python cannot
//! start, the engine is `UnavailableEngine`: every `/v1/*` call, health included, is 503
//! `brain_unavailable` with the reason, so the main server reports `brain: down`.
//!
//! **Privacy.** Bodies are never logged (no `TraceLayer` here, and the domain types print no
//! text in `Debug`); nothing is written to disk.

use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::body::Bytes;
use axum::extract::{ConnectInfo, DefaultBodyLimit, Request, State};
use axum::http::{HeaderMap, header};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse as _, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use domain::brain::{MAX_SOURCES, MAX_TEXT_CHARS};
use domain::{
    BrainHealth, BrainReportRequest, BrainStatus, ReportDraft, SimplifyRequest, SimplifyResult,
    SummariseRequest, SummaryDraft, TranslateRequest, TranslateResult,
};
use python_bindings::patient_aid::MAX_AUDIO_BYTES;
use python_bindings::{BrainEngine, BridgeError, Transcription};

use crate::config::{BrainProcessConfig, BrainToken};
use crate::error::{ApiError, ApiJson, StartupError};

/// Room for everything around the texts in one request: per source its id (96 bytes), kind,
/// keys, quotes and commas (well under 256 bytes), plus the request's own keys, language and
/// dates: 64 KiB covers it many times over.
pub const BRAIN_JSON_OVERHEAD_BYTES: usize = 64 * 1024;
/// Largest request body the brain reads (ruling R23), computed from the domain limits:
///
/// `MAX_SOURCES × MAX_TEXT_CHARS × 6 + BRAIN_JSON_OVERHEAD_BYTES`
/// = 20 × 8 000 × 6 + 65 536 = 1 025 536 bytes.
///
/// 6 bytes per character, not 4: a character is at most 4 bytes in UTF-8, but JSON writes a
/// control character as `\u00XX` (6 bytes), and the main server re-encodes the texts with
/// `serde_json`. A `/v1/report` has at most `MAX_SOURCES` facts (checked here, capped by the
/// main server), so the same bound holds. Below the main server's `/brain/*` limit
/// (`config::BRAIN_MAX_BODY_BYTES`, 1 MiB = 1 048 576). Over it, the brain answers 413
/// `body_too_large` as a JSON error body, which the main server maps to the same 413.
pub const BRAIN_PROCESS_MAX_BODY_BYTES: usize =
    MAX_SOURCES * MAX_TEXT_CHARS * 6 + BRAIN_JSON_OVERHEAD_BYTES;

// Checked at build time: what the main server lets through (1 MiB) must not be smaller than
// what it may send to the brain, and the brain's limit stays below the route's.
const _: () = assert!(BRAIN_PROCESS_MAX_BODY_BYTES < crate::config::BRAIN_MAX_BODY_BYTES);
/// Added to the engine's own per-call timeout (`BRAIN_CALL_TIMEOUT_S`) before the HTTP layer
/// gives up on a call (ruling R22: route 30 s > client 25 s > call 20 s + this margin).
pub const TIMEOUT_MARGIN: Duration = Duration::from_secs(2);

/// What the brain's handlers share.
#[derive(Clone)]
pub struct BrainApiState {
    engine: Arc<dyn BrainEngine>,
    token: BrainToken,
    call_timeout: Duration,
}

impl BrainApiState {
    /// The state: the engine, the shared token, and how long one call may take.
    #[must_use]
    pub fn new(
        engine: Arc<dyn BrainEngine>,
        token: BrainToken,
        call_timeout: Duration,
    ) -> BrainApiState {
        BrainApiState {
            engine,
            token,
            call_timeout,
        }
    }

    /// Runs one engine call on the blocking pool, within the call timeout plus
    /// [`TIMEOUT_MARGIN`].
    async fn run<R, F>(&self, call: F) -> Result<R, ApiError>
    where
        R: Send + 'static,
        F: FnOnce(&dyn BrainEngine) -> Result<R, python_bindings::BridgeError> + Send + 'static,
    {
        let engine = self.engine.clone();
        let limit = self.call_timeout.saturating_add(TIMEOUT_MARGIN);
        let job = tokio::task::spawn_blocking(move || call(engine.as_ref()));
        match tokio::time::timeout(limit, job).await {
            Err(_) => Err(ApiError::brain_timeout(limit)),
            Ok(Err(_)) => Err(ApiError::brain_failed("the engine call stopped")),
            Ok(Ok(result)) => result.map_err(ApiError::from),
        }
    }
}

/// The brain's router, with the loopback-and-token guard on every route.
pub fn build_brain_router(state: BrainApiState) -> Router {
    Router::new()
        .route("/v1/translate", post(translate))
        .route("/v1/simplify", post(simplify))
        // HACKATHON: audio passes through to the local brain for transcription, never stored
        .route(
            "/v1/transcribe",
            post(transcribe).layer(DefaultBodyLimit::max(MAX_AUDIO_BYTES)),
        )
        .route("/v1/speak", post(speak))
        .route("/v1/summarise", post(summarise))
        .route("/v1/report", post(report))
        .route("/v1/health", get(health))
        .fallback(crate::error::fallback_not_found)
        .layer(DefaultBodyLimit::max(BRAIN_PROCESS_MAX_BODY_BYTES))
        .layer(middleware::from_fn_with_state(state.clone(), guard))
        .with_state(state)
}

/// Refuses any peer that is not loopback (403 `loopback_only`) and any request without the
/// shared token (401 `brain_token`), before a body is read.
async fn guard(State(state): State<BrainApiState>, request: Request, next: Next) -> Response {
    let loopback = request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .is_some_and(|ConnectInfo(peer)| peer.ip().is_loopback());
    if !loopback {
        return ApiError::loopback_only().into_response();
    }
    let presented = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "));
    if !presented.is_some_and(|token| state.token.matches(token)) {
        return ApiError::brain_token().into_response();
    }
    next.run(request).await
}

async fn translate(
    State(state): State<BrainApiState>,
    ApiJson(request): ApiJson<TranslateRequest>,
) -> Result<Json<TranslateResult>, ApiError> {
    state
        .run(move |engine| engine.translate(&request))
        .await
        .map(Json)
}

async fn simplify(
    State(state): State<BrainApiState>,
    ApiJson(request): ApiJson<SimplifyRequest>,
) -> Result<Json<SimplifyResult>, ApiError> {
    state
        .run(move |engine| engine.simplify(&request))
        .await
        .map(Json)
}

/// The recordings `/v1/transcribe` reads, by media type (parameters such as `;codecs=opus`
/// are ignored).
pub const AUDIO_TYPES: [&str; 6] = [
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
];

/// `POST /v1/transcribe`: raw audio in, `{text, lang, duration_s}` out. 422 `invalid_input`
/// for another media type, an empty body, or a recording that cannot be decoded or lasts
/// over 60 s; 503 `brain_unavailable` without a speech model.
///
/// HACKATHON: audio passes through to the local brain for transcription, never stored. The
/// bytes live in this request only; nothing logs or writes them.
async fn transcribe(
    State(state): State<BrainApiState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Json<serde_json::Value>, ApiError> {
    let media = headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(';').next())
        .map(|value| value.trim().to_ascii_lowercase());
    if !media.is_some_and(|media| AUDIO_TYPES.contains(&media.as_str())) {
        return Err(ApiError::invalid_input(
            "content_type",
            "send the recording as audio/webm, audio/ogg, audio/mp4 or audio/wav",
        ));
    }
    if body.is_empty() {
        return Err(ApiError::invalid_input("audio", "the recording is empty"));
    }
    let audio = body.to_vec();
    drop(body);
    let heard: Result<Transcription, String> = state
        .run(move |engine| match engine.transcribe(audio) {
            Ok(heard) => Ok(Ok(heard)),
            Err(BridgeError::PythonRaised {
                exception_type,
                message,
            }) if exception_type == "AudioRefuse" => Ok(Err(message)),
            Err(error) => Err(error),
        })
        .await?;
    let heard = heard.map_err(|reason| ApiError::invalid_input("audio", &reason))?;
    Ok(Json(serde_json::json!({
        "text": heard.text,
        "lang": heard.lang,
        "duration_s": heard.duration_s,
    })))
}

/// The body of `POST /v1/speak`. `Debug` is not derived: the text is private.
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SpeakRequest {
    text: String,
    lang: String,
}

/// `POST /v1/speak`: `{text, lang}` in, a 16-bit PCM WAV out (`audio/wav`). 422
/// `invalid_field` for an empty text or one over 2 000 characters; 503 `brain_unavailable`
/// when no voice speaks `lang`.
///
/// HACKATHON: the audio is built in memory for this answer only; it is never stored or
/// logged.
async fn speak(
    State(state): State<BrainApiState>,
    ApiJson(request): ApiJson<SpeakRequest>,
) -> Result<Response, ApiError> {
    let length = request.text.trim().chars().count();
    if length == 0 || length > python_bindings::patient_aid::MAX_SPEAK_CHARS {
        return Err(ApiError::invalid_input(
            "text",
            "must hold 1 to 2000 characters",
        ));
    }
    let wav = state
        .run(move |engine| engine.speak(&request.text, &request.lang))
        .await?;
    Ok(([(header::CONTENT_TYPE, "audio/wav")], wav).into_response())
}

async fn summarise(
    State(state): State<BrainApiState>,
    ApiJson(request): ApiJson<SummariseRequest>,
) -> Result<Json<SummaryDraft>, ApiError> {
    request.check()?;
    state
        .run(move |engine| engine.summarise(&request))
        .await
        .map(Json)
}

async fn report(
    State(state): State<BrainApiState>,
    ApiJson(request): ApiJson<BrainReportRequest>,
) -> Result<Json<ReportDraft>, ApiError> {
    request.check()?;
    state
        .run(move |engine| engine.report(&request))
        .await
        .map(Json)
}

/// 200 with the health while the engine runs (`up` or `degraded`); 503 `brain_unavailable`
/// with the reason when it is down.
async fn health(State(state): State<BrainApiState>) -> Result<Json<BrainHealth>, ApiError> {
    let health = state.run(|engine| Ok(engine.health())).await?;
    if health.status == BrainStatus::Down {
        let reason = health.detail.as_deref().unwrap_or("no reason given");
        return Err(ApiError::brain_unavailable(reason));
    }
    Ok(Json(health))
}

/// Starts the engine and serves the brain API on `config.bind` until Ctrl-C.
///
/// # Errors
/// `StartupError::Bind` when the address is taken; `StartupError::Serve`.
pub async fn serve_brain(config: BrainProcessConfig) -> Result<(), StartupError> {
    let call_timeout = config.engine.python.call_timeout;
    let (engine, failure) = python_bindings::start_engine_reporting(config.engine);
    if let Some(error) = failure {
        // Bridge errors carry exception type names only, never a path or a text.
        tracing::error!(%error, "the Python engine could not start");
    }
    let health = engine.health();
    tracing::info!(
        status = ?health.status,
        detail = health.detail.as_deref().unwrap_or(""),
        "clinic-brain engine started"
    );
    let app = build_brain_router(BrainApiState::new(engine, config.token, call_timeout));
    let listener = tokio::net::TcpListener::bind(config.bind)
        .await
        .map_err(|source| StartupError::Bind {
            addr: config.bind,
            source,
        })?;
    tracing::info!(addr = %config.bind, "clinic-brain listening (loopback only)");
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .with_graceful_shutdown(async {
        let _stopped = tokio::signal::ctrl_c().await;
    })
    .await
    .map_err(StartupError::Serve)
}
