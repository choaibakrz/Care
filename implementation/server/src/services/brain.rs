//! The main server's side of the brain (Task A6): [`BrainClient`], the HTTP client to the
//! `clinic-brain` process on this computer, and [`HttpBrainService`], the real
//! [`BrainService`].
//!
//! **Process layout.** The models (Apertus, whisper) and Python run in their own process,
//! `clinic-brain` (`crate::brain_process`), so an out-of-memory or a crash in a model never
//! takes down task dispatch, the alarm mirror or the emergency stop. The main server talks to
//! it over HTTP on loopback with the shared `BRAIN_TOKEN`, and degrades instead of failing:
//! when the brain is down, `GET /health` says `brain: down` and every brain call is 503
//! `brain_unavailable`; nothing else changes.
//!
//! **Privacy.** Texts pass through in memory only. Nothing here logs a request or response
//! body (the domain types print no text in `Debug`); the journal gets only
//! `RecordBody::BrainCall { kind, latency_ms, ok }`.

use std::net::SocketAddr;
use std::sync::Arc;
use std::sync::atomic::{AtomicU8, Ordering};
use std::time::{Duration, Instant};

use async_trait::async_trait;
use audit::Journal;
use audit::{Category, RecordBody, Severity};
use axum::body::Bytes;
use axum::http::{HeaderValue, Method, StatusCode, header};
use chrono::{DateTime, Utc};
use domain::{
    BrainCallKind, BrainHealth, BrainReportRequest, BrainStatus, Clock, ErrorBody, ReportDraft,
    ReportRequest, SimplifyRequest, SimplifyResult, SummariseRequest, SummaryDraft, SummarySource,
    TranslateRequest, TranslateResult,
};
use domain::{Page, Permission, PrivateText, ReportKind, SourceKind, TaskFilter};
use http_body_util::{BodyExt as _, Full, Limited};
use hyper_util::rt::TokioIo;
use realtime::TaskView;
use security::ClientIdentity;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use tokio::net::TcpStream;
use tokio::task::JoinHandle;

use super::{BrainService, IncidentService, RobotService, TaskService};
use crate::config::{BrainClientConfig, BrainToken};
use crate::error::ApiError;

/// How often the main server asks the brain for its health (`GET /health` `brain`).
pub const BRAIN_PROBE_INTERVAL: Duration = Duration::from_secs(5);
/// How long connecting to the brain may take. The brain is on loopback, so a listening
/// brain accepts at once; Windows retries a refused loopback connection for about 2 s, which
/// this cuts short (`Unreachable`, "clinic-brain is not running").
pub const BRAIN_CONNECT_TIMEOUT: Duration = Duration::from_millis(500);
/// Largest brain answer read, in bytes.
pub const MAX_BRAIN_RESPONSE_BYTES: usize = 1024 * 1024;
/// Largest spoken answer read (`/v1/speak`), in bytes: about 3 minutes of 22 kHz 16-bit mono,
/// more than 2 000 characters take to read.
pub const MAX_BRAIN_AUDIO_BYTES: usize = 16 * 1024 * 1024;

/// Why a brain call did not return a draft. Every message is safe to log: it never contains a
/// text of the request or of the answer.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum BrainClientError {
    /// `BRAIN_TOKEN` is not set on the main server.
    #[error(
        "BRAIN_TOKEN is not set on the clinic server; set it to the value clinic-brain uses and restart."
    )]
    NotConfigured,
    /// Nothing answers at the brain's address.
    #[error(
        "clinic-brain at {addr} is not reachable ({detail}); start it with `cargo run --bin clinic-brain`."
    )]
    Unreachable {
        /// The address tried.
        addr: SocketAddr,
        /// The I/O error kind.
        detail: String,
    },
    /// The brain did not answer in time.
    #[error("clinic-brain did not answer within {after:?}; it may be loading a model.")]
    Timeout {
        /// The client timeout.
        after: Duration,
    },
    /// The brain answered with an error body. The Display names the status and code only.
    #[error("clinic-brain refused the call with {status} {code}.")]
    Refused {
        /// HTTP status.
        status: u16,
        /// Its error code (`brain_unavailable`, `brain_token`, …).
        code: String,
        /// Its message, kept for diagnosis only. It may repeat a request text (a 422 quoting
        /// its input): never log it with `%` or `?`, never show it to a client.
        message: BrainMessage,
    },
    /// The answer could not be read.
    #[error(
        "clinic-brain sent an answer that could not be read ({what}); check that both programs are the same version."
    )]
    Malformed {
        /// What was wrong.
        what: &'static str,
    },
}

impl BrainClientError {
    /// A short, fixed reason for `BrainHealth.detail` and `brain_unavailable` messages (no
    /// address, no path, never the brain's own message).
    #[must_use]
    pub fn reason(&self) -> String {
        let reason = match self {
            BrainClientError::NotConfigured => "BRAIN_TOKEN is not set",
            BrainClientError::Unreachable { .. } => "clinic-brain is not running",
            BrainClientError::Timeout { .. } => "clinic-brain does not answer",
            BrainClientError::Refused { code, .. } => match code.as_str() {
                "brain_token" => "clinic-brain refused the server's token",
                "loopback_only" => "clinic-brain refused this caller",
                "brain_unavailable" => "clinic-brain cannot run its models (see its log)",
                "brain_busy" => "clinic-brain is busy",
                _ => "clinic-brain refused the call",
            },
            BrainClientError::Malformed { .. } => "clinic-brain answers are unreadable",
        };
        reason.to_owned()
    }
}

/// The message of a brain error body. It may repeat a request text, so its `Debug` prints
/// only its length, it has no `Display`, and it is never forwarded to a client.
#[derive(Clone, PartialEq, Eq)]
pub struct BrainMessage(String);

impl BrainMessage {
    /// The message, for a person diagnosing the brain by hand. Never log it.
    #[must_use]
    pub fn expose(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Debug for BrainMessage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "BrainMessage({} chars)", self.0.chars().count())
    }
}

/// What `clinic-brain` heard in a recording (`POST /v1/transcribe`). `Debug` never prints
/// the text.
#[derive(Clone, PartialEq, Deserialize)]
pub struct Transcription {
    /// The transcript (empty when nothing was said).
    pub text: String,
    /// The detected language (ISO 639-1).
    pub lang: String,
    /// Length of the recording, in seconds.
    pub duration_s: f64,
}

impl std::fmt::Debug for Transcription {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Transcription({} chars, {}, {} s)",
            self.text.chars().count(),
            self.lang,
            self.duration_s
        )
    }
}

/// The HTTP/1 client to `clinic-brain` (one connection per call, loopback only).
#[derive(Debug, Clone)]
pub struct BrainClient {
    addr: SocketAddr,
    token: Option<BrainToken>,
    timeout: Duration,
}

impl BrainClient {
    /// A client for the configured brain. Connects lazily, on each call.
    #[must_use]
    pub fn new(config: &BrainClientConfig) -> BrainClient {
        BrainClient {
            addr: config.addr.socket(),
            token: config.token.clone(),
            timeout: config.timeouts.client(),
        }
    }

    /// `POST /v1/translate`.
    ///
    /// # Errors
    /// Any [`BrainClientError`].
    pub async fn translate(
        &self,
        request: &TranslateRequest,
    ) -> Result<TranslateResult, BrainClientError> {
        self.post("/v1/translate", request).await
    }

    /// `POST /v1/simplify`.
    ///
    /// # Errors
    /// Any [`BrainClientError`].
    pub async fn simplify(
        &self,
        request: &SimplifyRequest,
    ) -> Result<SimplifyResult, BrainClientError> {
        self.post("/v1/simplify", request).await
    }

    /// `POST /v1/summarise`.
    ///
    /// # Errors
    /// Any [`BrainClientError`].
    pub async fn summarise(
        &self,
        request: &SummariseRequest,
    ) -> Result<SummaryDraft, BrainClientError> {
        self.post("/v1/summarise", request).await
    }

    /// `POST /v1/report`.
    ///
    /// # Errors
    /// Any [`BrainClientError`].
    pub async fn report(
        &self,
        request: &BrainReportRequest,
    ) -> Result<ReportDraft, BrainClientError> {
        self.post("/v1/report", request).await
    }

    /// `POST /v1/transcribe` with the raw recording (`content_type` one of `audio/webm`,
    /// `audio/ogg`, `audio/mp4`, `audio/wav`).
    ///
    /// HACKATHON: audio passes through to the local brain for transcription, never stored.
    ///
    /// # Errors
    /// Any [`BrainClientError`] (422 `invalid_input` for an unreadable or too long
    /// recording, 503 `brain_unavailable` without a speech model).
    pub async fn transcribe(
        &self,
        audio: Bytes,
        content_type: &'static str,
    ) -> Result<Transcription, BrainClientError> {
        let (status, answer) = self
            .exchange(
                Method::POST,
                "/v1/transcribe",
                content_type,
                Some(audio),
                MAX_BRAIN_RESPONSE_BYTES,
            )
            .await?;
        decode(status, &answer)
    }

    /// `POST /v1/speak`: `text` read aloud in `lang`, a 16-bit PCM WAV.
    ///
    /// HACKATHON: the audio is built in memory, returned to the caller and never stored or
    /// logged.
    ///
    /// # Errors
    /// Any [`BrainClientError`] (503 `brain_unavailable` when no voice speaks `lang`).
    pub async fn speak(&self, text: &str, lang: &str) -> Result<Bytes, BrainClientError> {
        let body = serde_json::to_vec(&serde_json::json!({ "text": text, "lang": lang })).map_err(
            |_| BrainClientError::Malformed {
                what: "the request could not be encoded",
            },
        )?;
        let (status, answer) = self
            .exchange(
                Method::POST,
                "/v1/speak",
                JSON,
                Some(Bytes::from(body)),
                MAX_BRAIN_AUDIO_BYTES,
            )
            .await?;
        if status == StatusCode::OK {
            return Ok(answer);
        }
        // Not 200: `decode` turns the error body into `Refused`.
        match decode::<serde_json::Value>(status, &answer) {
            Err(error) => Err(error),
            Ok(_) => Err(BrainClientError::Malformed {
                what: "the answer is not audio",
            }),
        }
    }

    /// `GET /v1/health`.
    ///
    /// # Errors
    /// Any [`BrainClientError`] (a brain without Python answers 503 `brain_unavailable`).
    pub async fn health(&self) -> Result<BrainHealth, BrainClientError> {
        let (status, body) = self
            .exchange(
                Method::GET,
                "/v1/health",
                JSON,
                None,
                MAX_BRAIN_RESPONSE_BYTES,
            )
            .await?;
        decode(status, &body)
    }

    /// The brain's health, never failing: any error is `down` with its reason.
    pub async fn probe(&self) -> BrainHealth {
        match self.health().await {
            Ok(health) => health,
            Err(error) => BrainHealth::down(error.reason()),
        }
    }

    /// Sends a JSON body and reads the answer.
    async fn post<T: Serialize + Sync, R: DeserializeOwned>(
        &self,
        path: &'static str,
        body: &T,
    ) -> Result<R, BrainClientError> {
        let bytes = serde_json::to_vec(body).map_err(|_| BrainClientError::Malformed {
            what: "the request could not be encoded",
        })?;
        let (status, answer) = self
            .exchange(
                Method::POST,
                path,
                JSON,
                Some(Bytes::from(bytes)),
                MAX_BRAIN_RESPONSE_BYTES,
            )
            .await?;
        decode(status, &answer)
    }

    /// One HTTP/1 exchange on a fresh loopback connection, within the client timeout.
    async fn exchange(
        &self,
        method: Method,
        path: &'static str,
        content_type: &'static str,
        body: Option<Bytes>,
        limit: usize,
    ) -> Result<(StatusCode, Bytes), BrainClientError> {
        let token = self.token.as_ref().ok_or(BrainClientError::NotConfigured)?;
        let addr = self.addr;
        let unreachable = move |error: &dyn std::fmt::Display| BrainClientError::Unreachable {
            addr,
            detail: error.to_string(),
        };
        let work = async {
            let stream = tokio::time::timeout(BRAIN_CONNECT_TIMEOUT, TcpStream::connect(addr))
                .await
                .map_err(|_| unreachable(&"no answer to connect"))?
                .map_err(|e| unreachable(&e.kind()))?;
            let (mut sender, connection) =
                hyper::client::conn::http1::handshake(TokioIo::new(stream))
                    .await
                    .map_err(|e| unreachable(&e))?;
            let driver = tokio::spawn(connection);
            let request = hyper::Request::builder()
                .method(method)
                .uri(path)
                .header(header::HOST, addr.to_string())
                .header(header::AUTHORIZATION, authorization(token)?)
                .header(header::CONTENT_TYPE, content_type)
                .body(Full::new(body.unwrap_or_default()))
                .map_err(|_| BrainClientError::Malformed {
                    what: "the request could not be built",
                })?;
            let response = sender
                .send_request(request)
                .await
                .map_err(|e| unreachable(&e))?;
            let status = response.status();
            let collected = Limited::new(response.into_body(), limit)
                .collect()
                .await
                .map_err(|_| BrainClientError::Malformed {
                    what: "the answer was cut or too large",
                })?;
            driver.abort();
            Ok((status, collected.to_bytes()))
        };
        tokio::time::timeout(self.timeout, work)
            .await
            .map_err(|_| BrainClientError::Timeout {
                after: self.timeout,
            })?
    }
}

/// The media type of every JSON call.
const JSON: &str = "application/json";

/// The `Authorization` header value, marked sensitive (HTTP/2 never indexes it; tracing and
/// `Debug` of the header map show `Sensitive`).
fn authorization(token: &BrainToken) -> Result<HeaderValue, BrainClientError> {
    let mut value = HeaderValue::from_str(&format!("Bearer {}", token.expose())).map_err(|_| {
        BrainClientError::Malformed {
            what: "the token is not a valid header value",
        }
    })?;
    value.set_sensitive(true);
    Ok(value)
}

/// A 200 answer as `R`, any other status as `Refused` with the brain's error body.
fn decode<R: DeserializeOwned>(status: StatusCode, body: &[u8]) -> Result<R, BrainClientError> {
    if status == StatusCode::OK {
        return serde_json::from_slice(body).map_err(|_| BrainClientError::Malformed {
            what: "the answer is not the expected JSON",
        });
    }
    let error: ErrorBody =
        serde_json::from_slice(body).map_err(|_| BrainClientError::Malformed {
            what: "the error answer is not an error body",
        })?;
    Err(BrainClientError::Refused {
        status: status.as_u16(),
        code: error.error.code,
        message: BrainMessage(error.error.message),
    })
}

/// The last health seen, readable without waiting (`GET /health`).
#[derive(Debug, Default)]
pub struct BrainStatusCell(AtomicU8);

impl BrainStatusCell {
    /// Stores a status.
    pub fn set(&self, status: BrainStatus) {
        let code = match status {
            BrainStatus::Up => 2,
            BrainStatus::Degraded => 1,
            BrainStatus::Down => 0,
        };
        self.0.store(code, Ordering::Relaxed);
    }

    /// The last stored status (`down` until the first probe).
    #[must_use]
    pub fn get(&self) -> BrainStatus {
        match self.0.load(Ordering::Relaxed) {
            2 => BrainStatus::Up,
            1 => BrainStatus::Degraded,
            _ => BrainStatus::Down,
        }
    }
}

/// What [`HttpBrainService`] needs.
pub struct BrainDeps {
    /// The client to `clinic-brain`.
    pub client: Arc<BrainClient>,
    /// Tasks, for reports (what the caller may see).
    pub tasks: Arc<dyn TaskService>,
    /// Incidents, for reports.
    pub incidents: Arc<dyn IncidentService>,
    /// Robots, for robot activity reports.
    pub robots: Arc<dyn RobotService>,
    /// The journal (`BrainCall` records only).
    pub journal: Journal,
    /// Clock.
    pub clock: Arc<dyn Clock>,
}

/// The real brain service: every call goes to `clinic-brain` through [`BrainClient`].
pub struct HttpBrainService {
    client: Arc<BrainClient>,
    tasks: Arc<dyn TaskService>,
    incidents: Arc<dyn IncidentService>,
    robots: Arc<dyn RobotService>,
    journal: Journal,
    clock: Arc<dyn Clock>,
    status: BrainStatusCell,
}

impl HttpBrainService {
    /// A service; the status is `down` until the first probe.
    #[must_use]
    pub fn new(deps: BrainDeps) -> HttpBrainService {
        HttpBrainService {
            client: deps.client,
            tasks: deps.tasks,
            incidents: deps.incidents,
            robots: deps.robots,
            journal: deps.journal,
            clock: deps.clock,
            status: BrainStatusCell::default(),
        }
    }

    /// Asks the brain for its health every `every` and keeps the status for `GET /health`.
    #[must_use]
    pub fn spawn_health_probe(self: Arc<Self>, every: Duration) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut ticks = tokio::time::interval(every);
            loop {
                ticks.tick().await;
                let health = self.client.probe().await;
                self.status.set(health.status);
            }
        })
    }

    /// The facts of a report the caller may see, each a source with a server reference:
    /// `task:<id>` (kind, item, places, state changes in the period; never free text),
    /// `incident:<id>` (code, severity, place, acknowledged/closed), `robot:<id>` (tasks done
    /// and failed, failure reasons, time offline). Built from the services, so the caller's
    /// view rules apply; a robot activity report needs `ViewRobots`, an incident report
    /// `ViewIncidents`. Capped (ruling R23) at `domain::brain::MAX_SOURCES` facts of at most
    /// `MAX_TEXT_CHARS` each, the most recent first, so `/v1/report` stays within the brain's
    /// body limit (`brain_process::BRAIN_PROCESS_MAX_BODY_BYTES`).
    async fn report_facts(
        &self,
        actor: &ClientIdentity,
        request: &ReportRequest,
    ) -> Result<Vec<SummarySource>, ApiError> {
        let role = actor.verified.role;
        let needed = match request.kind {
            ReportKind::Shift => Permission::ViewTasks,
            ReportKind::Incident => Permission::ViewIncidents,
            ReportKind::RobotActivity => Permission::ViewRobots,
        };
        if !role.allows(needed) {
            return Err(ApiError::forbidden(needed));
        }
        let mut facts = match request.kind {
            ReportKind::Shift => {
                let mut facts = self.task_facts(request).await?;
                if role.allows(Permission::ViewIncidents) {
                    facts.extend(self.incident_facts(request).await?);
                }
                facts
            }
            ReportKind::Incident => self.incident_facts(request).await?,
            ReportKind::RobotActivity => self.robot_facts(request).await?,
        };
        facts.sort_by_key(|fact| std::cmp::Reverse(fact.0));
        facts
            .into_iter()
            .take(domain::brain::MAX_SOURCES)
            .map(|(_, reference, kind, text)| {
                let text: String = text.chars().take(domain::brain::MAX_TEXT_CHARS).collect();
                Ok(SummarySource {
                    id: reference.parse()?,
                    kind,
                    text: PrivateText::new(text)?,
                })
            })
            .collect()
    }

    /// Tasks created since the start of the period (at most one page of 500).
    async fn period_tasks(&self, request: &ReportRequest) -> Result<Vec<TaskView>, ApiError> {
        let filter = TaskFilter {
            state: None,
            robot: None,
            requested_by: None,
            since: Some(request.from),
            active_only: false,
        };
        let page = Page::new(Page::MAX_LIMIT, 0)?;
        Ok(self.tasks.list(filter, page).await?.items)
    }

    /// `task:<id>` facts: kind, item, places, state changes in the period.
    async fn task_facts(&self, request: &ReportRequest) -> Result<Vec<Fact>, ApiError> {
        let in_period = |at: DateTime<Utc>| at >= request.from && at < request.to;
        let mut facts = Vec::new();
        for task in self.period_tasks(request).await? {
            if !in_period(task.created_at) {
                continue;
            }
            let changes: Vec<String> = task
                .history
                .iter()
                .filter(|entry| in_period(entry.at))
                .map(|entry| entry.label.clone())
                .collect();
            let item = task
                .item
                .as_ref()
                .map_or_else(|| "no item".to_owned(), ToString::to_string);
            let from = task
                .from_place
                .as_ref()
                .map_or_else(|| "anywhere".to_owned(), ToString::to_string);
            facts.push((
                task.updated_at,
                format!("task:{}", task.id),
                SourceKind::Task,
                format!(
                    "Task {} ({}) of {item} from {from} to {}: now {}; changes: {}.",
                    task.id,
                    wire_name(&task.kind),
                    task.to_place,
                    task.state,
                    changes.join(", ")
                ),
            ));
        }
        Ok(facts)
    }

    /// `incident:<id>` facts: code, severity, place, status.
    async fn incident_facts(&self, request: &ReportRequest) -> Result<Vec<Fact>, ApiError> {
        let in_period = |at: DateTime<Utc>| at >= request.from && at < request.to;
        let mut facts = Vec::new();
        for incident in self.incidents.list_incidents(false).await? {
            if !in_period(incident.last_seen_at) && !in_period(incident.opened_at) {
                continue;
            }
            let place = incident
                .place
                .as_ref()
                .map_or_else(|| "unknown place".to_owned(), ToString::to_string);
            let status = if incident.closed_at.is_some() {
                "closed"
            } else if incident.acknowledged_by.is_some() {
                "acknowledged"
            } else {
                "open"
            };
            facts.push((
                incident.last_seen_at,
                format!("incident:{}", incident.id.0),
                SourceKind::Incident,
                format!(
                    "Incident {} ({}, {}) at {place}: {status}, raised {} times.",
                    incident.id.0,
                    wire_name(&incident.code),
                    wire_name(&incident.severity),
                    incident.repeats.saturating_add(1)
                ),
            ));
        }
        Ok(facts)
    }

    /// `robot:<id>` facts: tasks delivered and failed in the period, failure reasons, state.
    async fn robot_facts(&self, request: &ReportRequest) -> Result<Vec<Fact>, ApiError> {
        let tasks = self.period_tasks(request).await?;
        let mut facts = Vec::new();
        for robot in self.robots.list().await? {
            let mine = tasks
                .iter()
                .filter(|task| task.robot_id.as_ref() == Some(&robot.id));
            let done = mine
                .clone()
                .filter(|task| task.state == domain::TaskState::Delivered)
                .count();
            let failed: Vec<String> = mine
                .filter(|task| task.state == domain::TaskState::Failed)
                .map(|task| task.reason.clone().unwrap_or_else(|| "unknown".to_owned()))
                .collect();
            facts.push((
                robot.last_seen.unwrap_or(request.from),
                format!("robot:{}", robot.id),
                SourceKind::RobotActivity,
                format!(
                    "Robot {}: {done} tasks delivered, {} failed ({}); now {}.",
                    robot.id,
                    failed.len(),
                    failed.join(", "),
                    wire_name(&robot.state)
                ),
            ));
        }
        Ok(facts)
    }

    /// Journals one call: `RecordBody::BrainCall { kind, latency_ms, ok }`, actor the caller,
    /// category `audit`, severity `info`. Never a text.
    async fn record(
        &self,
        actor: &ClientIdentity,
        kind: BrainCallKind,
        started: Instant,
        ok: bool,
    ) -> Result<(), ApiError> {
        let latency_ms = u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX);
        self.journal
            .append(
                Severity::Info,
                Category::Audit,
                actor.verified.subject_id.clone(),
                RecordBody::BrainCall {
                    kind,
                    latency_ms,
                    ok,
                },
                Some(self.clock.now()),
            )
            .await?;
        Ok(())
    }
}

#[async_trait]
impl BrainService for HttpBrainService {
    async fn translate(
        &self,
        actor: &ClientIdentity,
        request: TranslateRequest,
    ) -> Result<TranslateResult, ApiError> {
        let started = Instant::now();
        let answer = self.client.translate(&request).await;
        self.record(actor, BrainCallKind::Translate, started, answer.is_ok())
            .await?;
        Ok(answer?)
    }
    async fn simplify(
        &self,
        actor: &ClientIdentity,
        request: SimplifyRequest,
    ) -> Result<SimplifyResult, ApiError> {
        let started = Instant::now();
        let answer = self.client.simplify(&request).await;
        self.record(actor, BrainCallKind::Simplify, started, answer.is_ok())
            .await?;
        Ok(answer?)
    }
    async fn summarise(
        &self,
        actor: &ClientIdentity,
        request: SummariseRequest,
    ) -> Result<SummaryDraft, ApiError> {
        request.check()?;
        let started = Instant::now();
        let answer = self.client.summarise(&request).await;
        self.record(actor, BrainCallKind::Summarise, started, answer.is_ok())
            .await?;
        Ok(answer?)
    }
    async fn report(
        &self,
        actor: &ClientIdentity,
        request: ReportRequest,
    ) -> Result<ReportDraft, ApiError> {
        request.check()?;
        let facts = self.report_facts(actor, &request).await?;
        let brain_request = BrainReportRequest { request, facts };
        brain_request.check()?;
        let started = Instant::now();
        let answer = self.client.report(&brain_request).await;
        self.record(actor, BrainCallKind::Report, started, answer.is_ok())
            .await?;
        Ok(answer?)
    }
    async fn health(&self) -> BrainHealth {
        let health = self.client.probe().await;
        self.status.set(health.status);
        health
    }
    fn status(&self) -> BrainStatus {
        self.status.get()
    }
}

/// The `snake_case` wire name of a value (its serde string, or its `code` field).
fn wire_name<T: Serialize>(value: &T) -> String {
    match serde_json::to_value(value) {
        Ok(serde_json::Value::String(name)) => name,
        Ok(serde_json::Value::Object(map)) => map
            .get("code")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("unknown")
            .to_owned(),
        _ => "unknown".to_owned(),
    }
}

/// One report fact before it becomes a source: (when, reference, kind, text).
type Fact = (DateTime<Utc>, String, SourceKind, String);
