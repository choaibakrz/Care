//! `POST /api/patient/listen`, `/api/patient/translate`, `/api/patient/simplify` and
//! `/api/patient/speak`: the patient app's "Listen & translate", "Simplify" and "Play again"
//! buttons, served by the local brain process (`clinic-brain`: faster-whisper, Apertus, Piper
//! voices) through [`PatientBrain`].
//!
//! `listen` and `translate` also read the translation aloud: `audio` is
//! `{mime: "audio/wav", data: <base64>}`, or `null` when no voice speaks the language or the
//! voice failed (the translation never fails because of the voice; the app then uses the
//! browser's voice). HACKATHON: the audio is generated in memory for the answer only; it is
//! never stored, journaled or logged.
//!
//! A cookie session (account) or a room-tablet session is required. Audio and texts pass
//! through in memory only: nothing here stores, journals or logs a body, a transcript or a
//! translation (only fixed error reasons are logged). Every result is a draft (`draft: true`)
//! that the app shows as "translated automatically". When the brain or the model is down the
//! answer is 503 `translation_unavailable` with a friendly message.

use std::sync::Arc;

use async_trait::async_trait;
use axum::Json;
use axum::Router;
use axum::body::Bytes;
use axum::extract::{DefaultBodyLimit, Query, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::middleware;
use axum::response::{IntoResponse, Response};
use axum::routing::post;
use domain::{
    LangCode, PrivateText, SimplifyLevel, SimplifyRequest, SimplifyResult, TranslateRequest,
    TranslateResult,
};
use serde::Deserialize;
use serde_json::json;
use tower_http::limit::RequestBodyLimitLayer;

use super::{PatientError, PatientStore, ROOM_DEVICE_COOKIE, cookie_value};
use crate::services::brain::{BrainClient, BrainClientError};

/// The languages the patient app can translate between (ISO 639-1).
pub const LANGUAGES: [&str; 17] = [
    "en", "fr", "de", "it", "es", "pt", "nl", "ar", "tr", "zh", "ru", "uk", "pl", "sq", "sr", "hr",
    "ro",
];
/// Largest recording accepted by `/api/patient/listen` (about 60 s of compressed speech).
pub const MAX_AUDIO_BYTES: usize = 4 * 1024 * 1024;
/// Longest text accepted by `/translate` and `/simplify`, in characters.
const MAX_PATIENT_TEXT_CHARS: usize = 2000;

/// What the brain heard in a recording.
#[derive(Clone, PartialEq, Eq)]
pub struct Heard {
    /// The transcript (may be empty: nothing was said).
    pub text: String,
    /// The detected language (ISO 639-1).
    pub lang: String,
}

impl std::fmt::Debug for Heard {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Heard({} chars, {})",
            self.text.chars().count(),
            self.lang
        )
    }
}

/// The brain calls the patient routes need. [`BrainClient`] is the real one; tests use a fake.
#[async_trait]
pub trait PatientBrain: Send + Sync {
    /// Transcribes a recording (`content_type` one of `audio/webm|ogg|mp4|wav`).
    async fn transcribe(
        &self,
        audio: Bytes,
        content_type: &'static str,
    ) -> Result<Heard, BrainClientError>;
    /// Translates a text.
    async fn translate(
        &self,
        request: &TranslateRequest,
    ) -> Result<TranslateResult, BrainClientError>;
    /// Rewrites a text in plain words, same language.
    async fn simplify(&self, request: &SimplifyRequest)
    -> Result<SimplifyResult, BrainClientError>;
    /// Reads a text aloud: a WAV. The default has no voice.
    async fn speak(&self, _text: &str, _lang: &str) -> Result<Bytes, BrainClientError> {
        Err(BrainClientError::NotConfigured)
    }
}

#[async_trait]
impl PatientBrain for BrainClient {
    async fn transcribe(
        &self,
        audio: Bytes,
        content_type: &'static str,
    ) -> Result<Heard, BrainClientError> {
        let heard = BrainClient::transcribe(self, audio, content_type).await?;
        Ok(Heard {
            text: heard.text,
            lang: heard.lang,
        })
    }
    async fn translate(
        &self,
        request: &TranslateRequest,
    ) -> Result<TranslateResult, BrainClientError> {
        BrainClient::translate(self, request).await
    }
    async fn simplify(
        &self,
        request: &SimplifyRequest,
    ) -> Result<SimplifyResult, BrainClientError> {
        BrainClient::simplify(self, request).await
    }
    async fn speak(&self, text: &str, lang: &str) -> Result<Bytes, BrainClientError> {
        BrainClient::speak(self, text, lang).await
    }
}

/// No brain wired (tests of other routes, a router built without one): every call is 503.
pub struct NoBrain;

#[async_trait]
impl PatientBrain for NoBrain {
    async fn transcribe(&self, _: Bytes, _: &'static str) -> Result<Heard, BrainClientError> {
        Err(BrainClientError::NotConfigured)
    }
    async fn translate(&self, _: &TranslateRequest) -> Result<TranslateResult, BrainClientError> {
        Err(BrainClientError::NotConfigured)
    }
    async fn simplify(&self, _: &SimplifyRequest) -> Result<SimplifyResult, BrainClientError> {
        Err(BrainClientError::NotConfigured)
    }
}

#[derive(Clone)]
struct TranslateState {
    store: Arc<PatientStore>,
    brain: Arc<dyn PatientBrain>,
}

type Answer = Result<Response, PatientError>;

/// The three routes, with their own body limits (4 MiB for `/listen`, the patient API's
/// small limit for the text routes) and the same-origin check.
pub(super) fn router(store: Arc<PatientStore>, brain: Arc<dyn PatientBrain>) -> Router {
    let listen_route = Router::new()
        .route("/api/patient/listen", post(listen))
        .layer(DefaultBodyLimit::max(MAX_AUDIO_BYTES))
        .layer(RequestBodyLimitLayer::new(MAX_AUDIO_BYTES));
    let text_routes = Router::new()
        .route("/api/patient/translate", post(translate))
        .route("/api/patient/simplify", post(simplify))
        .route("/api/patient/speak", post(speak))
        .layer(RequestBodyLimitLayer::new(super::MAX_BODY_BYTES));
    listen_route
        .merge(text_routes)
        .route_layer(middleware::from_fn(super::check_origin))
        .with_state(TranslateState { store, brain })
}

#[derive(Deserialize)]
struct ListenQuery {
    to: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TranslateInput {
    text: String,
    to: String,
    #[serde(default)]
    from: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SpeakInput {
    text: String,
    lang: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SimplifyInput {
    text: String,
    lang: String,
}

/// `POST /api/patient/listen?to=`: transcribes a recording, then translates it into `to`.
/// `translated` is `null` when nothing was heard or only the translation step is down.
async fn listen(
    State(state): State<TranslateState>,
    headers: HeaderMap,
    Query(query): Query<ListenQuery>,
    body: Bytes,
) -> Answer {
    check_session(&state.store, &headers).await?;
    let to = language(&query.to)?;
    let content_type = audio_type(&headers)?;
    if body.is_empty() {
        return Err(PatientError::unprocessable(
            "empty_recording",
            "Nothing was recorded. Tap the button and speak.",
        ));
    }
    // HACKATHON: audio passes through to the local brain for transcription, never stored
    let heard = state
        .brain
        .transcribe(body, content_type)
        .await
        .map_err(|error| match error {
            BrainClientError::Refused {
                status: 400 | 415 | 422,
                ..
            } => PatientError::unprocessable(
                "invalid_audio",
                "The recording could not be read. Please try again.",
            ),
            other => brain_error(other),
        })?;
    let text = heard.text.trim().to_owned();
    let heard_lang = base_code(&heard.lang);
    let translated = if text.is_empty() {
        None
    } else if heard_lang == to.as_str() {
        Some(text.clone())
    } else {
        let from = language(&heard_lang).ok();
        match translate_text(state.brain.as_ref(), &text, from, to.clone()).await {
            Ok(result) => Some(result.text.expose().to_owned()),
            Err(error) => {
                tracing::warn!(reason = %error.reason(), "patient translation after listening failed");
                None
            }
        }
    };
    let audio = match &translated {
        Some(said) => spoken(state.brain.as_ref(), said, &to).await,
        None => serde_json::Value::Null,
    };
    let body = json!({
        "heard": { "text": text, "lang": heard_lang },
        "translated": translated.map(|said| json!({ "text": said, "lang": to })),
        "audio": audio,
        "draft": true,
    });
    Ok(Json(body).into_response())
}

/// `POST /api/patient/translate`: `{text, to, from?}`; same language: the text unchanged.
async fn translate(State(state): State<TranslateState>, headers: HeaderMap, body: Bytes) -> Answer {
    check_session(&state.store, &headers).await?;
    let input: TranslateInput = super::handlers::parse(&body, INVALID_TEXT)?;
    let text = patient_text(&input.text)?;
    let to = language(&input.to)?;
    let from = input.from.as_deref().map(language).transpose()?;
    if from.as_ref() == Some(&to) {
        let audio = spoken(state.brain.as_ref(), &text, &to).await;
        let body = json!({ "text": text, "from": to, "to": to, "audio": audio, "draft": true });
        return Ok(Json(body).into_response());
    }
    let result = translate_text(state.brain.as_ref(), &text, from, to)
        .await
        .map_err(brain_error)?;
    let audio = spoken(state.brain.as_ref(), result.text.expose(), &result.to).await;
    let body = json!({
        "text": result.text,
        "from": result.from,
        "to": result.to,
        "audio": audio,
        "draft": true,
    });
    Ok(Json(body).into_response())
}

/// `POST /api/patient/speak`: `{text, lang}` read aloud, `audio/wav`; 503
/// `voice_unavailable` when no voice speaks `lang` (the app then uses the browser's voice).
///
/// HACKATHON: the audio is generated in memory for this answer only; never stored or logged.
async fn speak(State(state): State<TranslateState>, headers: HeaderMap, body: Bytes) -> Answer {
    check_session(&state.store, &headers).await?;
    let input: SpeakInput = super::handlers::parse(&body, INVALID_TEXT)?;
    let text = patient_text(&input.text)?;
    let lang = language(&input.lang)?;
    match state.brain.speak(&text, lang.as_str()).await {
        Ok(wav) if !wav.is_empty() => {
            Ok(([(header::CONTENT_TYPE, "audio/wav")], wav).into_response())
        }
        Ok(_) => Err(VOICE_UNAVAILABLE),
        Err(error) => {
            tracing::info!(reason = %error.reason(), "no voice for the patient text");
            Err(VOICE_UNAVAILABLE)
        }
    }
}

const VOICE_UNAVAILABLE: PatientError = PatientError::with_status(
    StatusCode::SERVICE_UNAVAILABLE,
    "voice_unavailable",
    "No voice for this language here. Your device will read it.",
);

/// The text read aloud as `{mime, data}` (base64 WAV), or `null` when no voice speaks `lang`
/// or the voice failed: the translation never fails because of the voice. Only the fixed
/// reason is logged.
async fn spoken(brain: &dyn PatientBrain, text: &str, lang: &LangCode) -> serde_json::Value {
    match brain.speak(text, lang.as_str()).await {
        Ok(wav) if !wav.is_empty() => json!({ "mime": "audio/wav", "data": base64(&wav) }),
        Ok(_) => serde_json::Value::Null,
        Err(error) => {
            tracing::info!(reason = %error.reason(), "no voice for the translation");
            serde_json::Value::Null
        }
    }
}

/// Standard base64 with padding (RFC 4648).
fn base64(bytes: &[u8]) -> String {
    fn digit(value: u8) -> char {
        let code = match value & 63 {
            v @ 0..=25 => b'A' + v,
            v @ 26..=51 => b'a' + (v - 26),
            v @ 52..=61 => b'0' + (v - 52),
            62 => b'+',
            _ => b'/',
        };
        char::from(code)
    }
    let mut out = String::with_capacity(bytes.len().div_ceil(3).saturating_mul(4));
    for chunk in bytes.chunks(3) {
        let (a, b, c, len) = match *chunk {
            [a, b, c] => (a, b, c, 3),
            [a, b] => (a, b, 0, 2),
            [a] => (a, 0, 0, 1),
            _ => continue,
        };
        out.push(digit(a >> 2));
        out.push(digit((a << 4) | (b >> 4)));
        out.push(if len > 1 {
            digit((b << 2) | (c >> 6))
        } else {
            '='
        });
        out.push(if len > 2 { digit(c) } else { '=' });
    }
    out
}

/// `POST /api/patient/simplify`: `{text, lang}`, a plain-language rewrite in `lang`.
async fn simplify(State(state): State<TranslateState>, headers: HeaderMap, body: Bytes) -> Answer {
    check_session(&state.store, &headers).await?;
    let input: SimplifyInput = super::handlers::parse(&body, INVALID_TEXT)?;
    let text = patient_text(&input.text)?;
    let lang = language(&input.lang)?;
    let request = SimplifyRequest {
        text: PrivateText::new(text).map_err(|_| INVALID_TEXT)?,
        lang,
        level: SimplifyLevel::Plain,
    };
    let result = state.brain.simplify(&request).await.map_err(brain_error)?;
    let body = json!({
        "text": result.text,
        "lang": result.lang,
        "simplified": result.simplified,
        "draft": true,
    });
    Ok(Json(body).into_response())
}

const INVALID_TEXT: PatientError =
    PatientError::unprocessable("invalid_text", "Enter a text of 1 to 2000 characters.");

async fn translate_text(
    brain: &dyn PatientBrain,
    text: &str,
    from: Option<LangCode>,
    to: LangCode,
) -> Result<TranslateResult, BrainClientError> {
    let text = PrivateText::new(text.to_owned()).map_err(|_| BrainClientError::Malformed {
        what: "the text is not valid",
    })?;
    brain.translate(&TranslateRequest { text, from, to }).await
}

/// A room-tablet session or an account session, or 401.
async fn check_session(store: &PatientStore, headers: &HeaderMap) -> Result<(), PatientError> {
    if cookie_value(headers, ROOM_DEVICE_COOKIE).is_some() {
        super::rooms::room_session(store, headers).await?;
        return Ok(());
    }
    super::handlers::current_user(store, headers, PatientError::data_down)
        .await
        .map(|_| ())
}

/// A text of 1 to [`MAX_PATIENT_TEXT_CHARS`] characters, trimmed.
fn patient_text(text: &str) -> Result<String, PatientError> {
    let text = text.trim();
    if text.is_empty() || text.chars().count() > MAX_PATIENT_TEXT_CHARS {
        return Err(INVALID_TEXT);
    }
    Ok(text.to_owned())
}

/// `fr`, `fr-CH`, `FR` → `fr`.
fn base_code(code: &str) -> String {
    code.trim()
        .split(['-', '_'])
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase()
}

/// One of [`LANGUAGES`] (region dropped), or 422 `unsupported_language`.
fn language(code: &str) -> Result<LangCode, PatientError> {
    let base = base_code(code);
    if !LANGUAGES.contains(&base.as_str()) {
        return Err(PatientError::unprocessable(
            "unsupported_language",
            "This language is not supported yet.",
        ));
    }
    base.parse().map_err(|_| {
        PatientError::unprocessable(
            "unsupported_language",
            "This language is not supported yet.",
        )
    })
}

/// The recording's type without parameters (`audio/webm;codecs=opus` → `audio/webm`).
fn audio_type(headers: &HeaderMap) -> Result<&'static str, PatientError> {
    let value = headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    let base = value
        .split(';')
        .next()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    match base.as_str() {
        "audio/webm" => Ok("audio/webm"),
        "audio/ogg" => Ok("audio/ogg"),
        "audio/mp4" | "audio/x-m4a" | "audio/m4a" => Ok("audio/mp4"),
        "audio/wav" | "audio/x-wav" | "audio/wave" => Ok("audio/wav"),
        _ => Err(PatientError::with_status(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "unsupported_audio",
            "This recording format is not supported. Try another browser.",
        )),
    }
}

/// A friendly answer for a brain failure. Logs only the fixed reason, never a text.
fn brain_error(error: BrainClientError) -> PatientError {
    tracing::warn!(reason = %error.reason(), "patient translation call failed");
    match error {
        BrainClientError::Timeout { .. } | BrainClientError::Refused { status: 504, .. } => {
            PatientError::with_status(
                StatusCode::GATEWAY_TIMEOUT,
                "translation_timeout",
                "Translation took too long. Please try again.",
            )
        }
        BrainClientError::Refused { status: 413, .. } => PatientError::with_status(
            StatusCode::PAYLOAD_TOO_LARGE,
            "recording_too_long",
            "The recording is too long. Keep it under 30 seconds.",
        ),
        BrainClientError::Refused {
            status: 400 | 415 | 422,
            code,
            ..
        } => match code.as_str() {
            "unsupported_language" => PatientError::unprocessable(
                "unsupported_language",
                "This language is not supported yet.",
            ),
            "unsupported_audio" | "invalid_audio" => PatientError::unprocessable(
                "invalid_audio",
                "The recording could not be read. Please try again.",
            ),
            _ => PatientError::unprocessable(
                "translation_rejected",
                "This could not be translated. Try a shorter or clearer text.",
            ),
        },
        _ => PatientError::with_status(
            StatusCode::SERVICE_UNAVAILABLE,
            "translation_unavailable",
            "Translation is not available right now.",
        ),
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use async_trait::async_trait;
    use axum::body::{Body, Bytes};
    use axum::http::{Request, StatusCode, header};
    use domain::{
        DraftFlag, SimplifyRequest, SimplifyResult, TextChecks, TranslateRequest, TranslateResult,
    };
    use http_body_util::BodyExt as _;
    use security::{MonitorConfig, TrafficMonitor};
    use serde_json::{Value, json};
    use tower::ServiceExt as _;

    use super::{Heard, PatientBrain};
    use crate::patient::{PatientStore, router_with_brain};
    use crate::services::brain::BrainClientError;

    /// Answers every translation with `[to] text`.
    struct FakeBrain;

    #[async_trait]
    impl PatientBrain for FakeBrain {
        async fn transcribe(&self, _: Bytes, _: &'static str) -> Result<Heard, BrainClientError> {
            Ok(Heard {
                text: "Guten Tag".to_owned(),
                lang: "de".to_owned(),
            })
        }
        async fn translate(
            &self,
            request: &TranslateRequest,
        ) -> Result<TranslateResult, BrainClientError> {
            let text = format!("[{}] {}", request.to.as_str(), request.text.expose());
            Ok(TranslateResult {
                draft: DraftFlag,
                text: domain::PrivateText::new(text)
                    .map_err(|_| BrainClientError::Malformed { what: "fake" })?,
                from: request.from.clone().unwrap_or(request.to.clone()),
                to: request.to.clone(),
                checks: TextChecks {
                    fixed_terms_ok: true,
                    numbers_ok: true,
                },
            })
        }
        async fn simplify(&self, _: &SimplifyRequest) -> Result<SimplifyResult, BrainClientError> {
            Err(BrainClientError::NotConfigured)
        }
    }

    async fn send(
        app: &axum::Router,
        request: Request<Body>,
    ) -> Result<(StatusCode, Value), Box<dyn std::error::Error>> {
        let response = app.clone().oneshot(request).await?;
        let status = response.status();
        let bytes = response.into_body().collect().await?.to_bytes();
        Ok((status, serde_json::from_slice(&bytes)?))
    }

    /// [`FakeBrain`] with a voice: reads every text as the WAV `RIFF<lang>`.
    struct VoiceBrain;

    #[async_trait]
    impl PatientBrain for VoiceBrain {
        async fn transcribe(
            &self,
            audio: Bytes,
            kind: &'static str,
        ) -> Result<Heard, BrainClientError> {
            FakeBrain.transcribe(audio, kind).await
        }
        async fn translate(
            &self,
            request: &TranslateRequest,
        ) -> Result<TranslateResult, BrainClientError> {
            FakeBrain.translate(request).await
        }
        async fn simplify(
            &self,
            request: &SimplifyRequest,
        ) -> Result<SimplifyResult, BrainClientError> {
            FakeBrain.simplify(request).await
        }
        async fn speak(&self, _: &str, lang: &str) -> Result<Bytes, BrainClientError> {
            Ok(Bytes::from(format!("RIFF{lang}")))
        }
    }

    /// Signs a patient up, then translates "Bonjour" from French into British English.
    async fn translate_bonjour(
        brain: Arc<dyn PatientBrain>,
    ) -> Result<(StatusCode, Value), Box<dyn std::error::Error>> {
        let dir = std::env::temp_dir()
            .join("clinic-server-tests")
            .join(format!("patient-translate-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir)?;
        let store = Arc::new(PatientStore::open(dir.join("patients.json"))?);
        let clock: Arc<dyn domain::Clock> = Arc::new(domain::SystemClock);
        let traffic = Arc::new(TrafficMonitor::new(MonitorConfig::default(), vec![], clock));
        let app = router_with_brain(store, traffic, None, brain);

        let signup = json!({ "identifier": "kim@example.com", "password": "long-enough-1", "first_name": "Kim" });
        let request = Request::post("/api/auth/signup")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(signup.to_string()))?;
        let response = app.clone().oneshot(request).await?;
        assert_eq!(response.status(), StatusCode::CREATED);
        let cookie = response
            .headers()
            .get(header::SET_COOKIE)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.split(';').next())
            .ok_or("no session cookie")?
            .to_owned();

        let body = json!({ "text": "Bonjour", "to": "en-GB", "from": "fr" });
        let request = Request::post("/api/patient/translate")
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::COOKIE, &cookie)
            .body(Body::from(body.to_string()))?;
        send(&app, request).await
    }

    #[tokio::test]
    async fn translates_for_a_signed_in_patient() -> Result<(), Box<dyn std::error::Error>> {
        let (status, answer) = translate_bonjour(Arc::new(FakeBrain)).await?;
        assert_eq!(status, StatusCode::OK, "{answer}");
        assert_eq!(
            answer,
            json!({ "text": "[en] Bonjour", "from": "fr", "to": "en", "audio": null, "draft": true })
        );
        Ok(())
    }

    #[tokio::test]
    async fn the_translation_comes_with_its_audio_when_the_brain_has_a_voice()
    -> Result<(), Box<dyn std::error::Error>> {
        let (status, answer) = translate_bonjour(Arc::new(VoiceBrain)).await?;
        assert_eq!(status, StatusCode::OK, "{answer}");
        assert_eq!(answer.get("text"), Some(&json!("[en] Bonjour")));
        // "RIFFen" in base64.
        assert_eq!(
            answer.get("audio"),
            Some(&json!({ "mime": "audio/wav", "data": "UklGRmVu" }))
        );
        Ok(())
    }

    #[test]
    fn base64_pads_like_the_standard() {
        assert_eq!(super::base64(b"RIFF"), "UklGRg==");
        assert_eq!(super::base64(b"RIFFw"), "UklGRnc=");
    }
}
