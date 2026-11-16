//! Task A6: the server-side brain for clients (translate, simplify, summarise, report), the
//! `clinic-brain` process API and its degradation without Python, and the privacy rule
//! (texts in memory only: never in logs, the journal or audit rows).
//!
//! Passing now: the contract (schemas, routes, permissions), the `--mock` canned drafts, the
//! brain process without Python (503 `brain_unavailable` on every route, loopback and token
//! checks), the main server's HTTP client against it (`down`, explicit errors, timeout), and
//! the privacy sentinel through the mock. Ignored until Task 20d: the live server's brain
//! service (journal, reports from server data, degradation through `GET /health`).

mod support;

use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::Duration;

use axum::http::{Method, StatusCode};
use axum::response::IntoResponse as _;
use clinic_server::brain_process::{
    BRAIN_PROCESS_MAX_BODY_BYTES, BrainApiState, build_brain_router,
};
use clinic_server::config::{BRAIN_MAX_BODY_BYTES, BrainClientConfig, BrainToken};
use clinic_server::error::ApiError;
use clinic_server::services::brain::{BrainClient, BrainClientError};
use domain::{
    BrainHealth, BrainReportRequest, BrainStatus, DraftFlag, DraftLine, PrivateText, ReportDraft,
    SimplifyRequest, SimplifyResult, SummariseRequest, SummaryDraft, TextChecks, TranslateRequest,
    TranslateResult,
};
use python_bindings::{BrainEngine, BridgeError, UnavailableEngine};
use serde_json::{Value, json};
use support::{
    FOREIGN_PEER, LiveServer, LogCapture, MockApp, REQUEST_TRACE_LINE, RealApp, Res, TestResult,
    call, call_from, get, map, post_json, post_raw, read_journal, request, with_header,
};
use utoipa::PartialSchema;

/// The token the fake brains and their clients share.
const TOKEN: &str = "test-brain-token-0123456789abcdef";
/// A text that must never appear in a log, the journal or an audit row.
const SENTINEL: &str = "SENTINEL-7f3a-patient-words";

fn token() -> Res<BrainToken> {
    Ok(BrainToken::new(TOKEN.to_owned())?)
}

/// The keys of a schema's properties.
fn keys(schema: utoipa::openapi::RefOr<utoipa::openapi::schema::Schema>) -> Res<BTreeSet<String>> {
    Ok(serde_json::to_value(schema)?
        .get("properties")
        .and_then(Value::as_object)
        .ok_or("no properties")?
        .keys()
        .cloned()
        .collect())
}

fn set(items: &[&str]) -> BTreeSet<String> {
    items.iter().map(|s| (*s).to_owned()).collect()
}

/// A brain engine that echoes: what the HTTP plumbing must carry back unchanged.
struct EchoEngine {
    delay: Duration,
}

impl BrainEngine for EchoEngine {
    fn translate(&self, request: &TranslateRequest) -> Result<TranslateResult, BridgeError> {
        std::thread::sleep(self.delay);
        // An echo has no language detection: without `from`, it says the target language.
        let from = request.from.clone().unwrap_or_else(|| request.to.clone());
        Ok(TranslateResult {
            draft: DraftFlag,
            text: request.text.clone(),
            from,
            to: request.to.clone(),
            checks: TextChecks {
                fixed_terms_ok: true,
                numbers_ok: true,
            },
        })
    }
    fn simplify(&self, request: &SimplifyRequest) -> Result<SimplifyResult, BridgeError> {
        Ok(SimplifyResult {
            draft: DraftFlag,
            text: request.text.clone(),
            lang: request.lang.clone(),
            level: request.level,
            simplified: false,
        })
    }
    fn summarise(&self, request: &SummariseRequest) -> Result<SummaryDraft, BridgeError> {
        Ok(SummaryDraft {
            draft: DraftFlag,
            lang: request.lang.clone(),
            lines: request
                .sources
                .iter()
                .map(|s| DraftLine {
                    text: s.text.clone(),
                    source: s.id.clone(),
                })
                .collect(),
            dropped: 0,
        })
    }
    fn report(&self, request: &BrainReportRequest) -> Result<ReportDraft, BridgeError> {
        Ok(ReportDraft {
            draft: DraftFlag,
            kind: request.request.kind,
            from: request.request.from,
            to: request.request.to,
            lang: request.request.lang.clone(),
            lines: request
                .facts
                .iter()
                .map(|f| DraftLine {
                    text: f.text.clone(),
                    source: f.id.clone(),
                })
                .collect(),
            dropped: 0,
        })
    }
    fn health(&self) -> BrainHealth {
        BrainHealth {
            status: BrainStatus::Up,
            models: vec!["echo".to_owned()],
            queue: 0,
            detail: None,
        }
    }
}

/// A brain router on `engine` with the test token.
fn brain_router(engine: Arc<dyn BrainEngine>) -> Res<axum::Router> {
    Ok(build_brain_router(BrainApiState::new(
        engine,
        token()?,
        Duration::from_secs(5),
    )))
}

/// A client of a brain at `server` with `token`.
fn client(server: &LiveServer, token: Option<BrainToken>, timeout: Duration) -> Res<BrainClient> {
    Ok(BrainClient::new(&BrainClientConfig::local(
        server.addr,
        token,
        timeout,
    )?))
}

fn translate_body(text: &str) -> Value {
    json!({ "text": text, "from": "fr", "to": "en" })
}

fn translate_request(text: &str) -> Res<TranslateRequest> {
    Ok(TranslateRequest {
        text: PrivateText::new(text.to_owned())?,
        from: Some("fr".parse()?),
        to: "en".parse()?,
    })
}

// ------------------------------------------------------------------------------- contract

#[test]
fn brain_results_have_the_contract_fields() -> TestResult {
    assert_eq!(
        keys(TranslateResult::schema())?,
        set(&["draft", "text", "from", "to", "checks"])
    );
    assert_eq!(
        keys(TextChecks::schema())?,
        set(&["fixed_terms_ok", "numbers_ok"])
    );
    assert_eq!(
        keys(SimplifyResult::schema())?,
        set(&["draft", "text", "lang", "level", "simplified"])
    );
    assert_eq!(
        keys(SummaryDraft::schema())?,
        set(&["draft", "lang", "lines", "dropped"])
    );
    assert_eq!(keys(DraftLine::schema())?, set(&["text", "source"]));
    assert_eq!(
        keys(ReportDraft::schema())?,
        set(&["draft", "kind", "from", "to", "lang", "lines", "dropped"])
    );
    assert_eq!(
        keys(BrainHealth::schema())?,
        set(&["status", "models", "queue", "detail"])
    );
    Ok(())
}

#[test]
fn brain_requests_and_results_print_no_text_in_debug() -> TestResult {
    let request = translate_request(SENTINEL)?;
    assert!(!format!("{request:?}").contains(SENTINEL));
    let line = DraftLine {
        text: PrivateText::new(SENTINEL.to_owned())?,
        source: "note-1".parse()?,
    };
    assert!(!format!("{line:?}").contains(SENTINEL));
    Ok(())
}

#[test]
fn openapi_documents_the_brain_routes_with_bearer() -> TestResult {
    use utoipa::OpenApi as _;
    let doc = serde_json::to_value(clinic_server::openapi::ApiDoc::openapi())?;
    for (path, method) in [
        ("/brain/translate", "post"),
        ("/brain/simplify", "post"),
        ("/brain/summarise", "post"),
        ("/brain/report", "post"),
        ("/brain/health", "get"),
    ] {
        let operation = doc
            .pointer(&format!("/paths/{}/{method}", path.replace('/', "~1")))
            .ok_or_else(|| format!("{method} {path} is not documented"))?;
        assert!(operation.get("security").is_some(), "{path} needs a token");
    }
    // The robot speech round trip (C2 `utterance` / `brain.reply`, Task 20c) is postponed:
    // no route for it.
    let paths = doc.get("paths").and_then(Value::as_object).ok_or("paths")?;
    assert!(!paths.keys().any(|p| p.contains("utterance")));
    Ok(())
}

// ------------------------------------------------------------------------------- --mock

#[tokio::test]
async fn mock_translate_is_a_labelled_draft_with_checks() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        post_json(
            "/brain/translate",
            Some("mock-nurse"),
            &translate_body("Bonjour"),
        )?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("draft"), Some(&json!(true)));
    let text = reply
        .body
        .get("text")
        .and_then(Value::as_str)
        .unwrap_or_default();
    assert!(text.starts_with("MOCK TRANSLATION"), "{text}");
    assert_eq!(reply.body.pointer("/checks/numbers_ok"), Some(&json!(true)));
    assert_eq!(reply.body.get("to"), Some(&json!("en")));
    Ok(())
}

#[tokio::test]
async fn mock_simplify_summarise_and_report_are_labelled_drafts_with_sources() -> TestResult {
    let app = MockApp::start()?;
    let simplified = call(
        &app.app,
        post_json(
            "/brain/simplify",
            Some("mock-reception"),
            &json!({ "text": "Prenez deux comprimés.", "lang": "fr", "level": "easy" }),
        )?,
    )
    .await?;
    assert_eq!(simplified.status, StatusCode::OK, "{}", simplified.body);
    assert_eq!(simplified.body.get("draft"), Some(&json!(true)));
    assert_eq!(simplified.body.get("simplified"), Some(&json!(true)));

    let summary = call(
        &app.app,
        post_json(
            "/brain/summarise",
            Some("mock-doctor"),
            &json!({ "lang": "en", "sources": [
                { "id": "note-1", "kind": "note", "text": "Slept well." },
                { "id": "msg-2", "kind": "message", "text": "Asks about lunch." }
            ]}),
        )?,
    )
    .await?;
    assert_eq!(summary.status, StatusCode::OK, "{}", summary.body);
    assert_eq!(summary.body.get("draft"), Some(&json!(true)));
    let sources: Vec<&str> = summary
        .body
        .get("lines")
        .and_then(Value::as_array)
        .ok_or("lines")?
        .iter()
        .filter_map(|l| l.get("source").and_then(Value::as_str))
        .collect();
    assert_eq!(sources, ["note-1", "msg-2"]);

    let report = call(
        &app.app,
        post_json(
            "/brain/report",
            Some("mock-admin"),
            &json!({ "kind": "shift", "from": "2026-11-14T06:00:00Z", "to": "2026-11-14T14:00:00Z", "lang": "en" }),
        )?,
    )
    .await?;
    assert_eq!(report.status, StatusCode::OK, "{}", report.body);
    let lines = report
        .body
        .get("lines")
        .and_then(Value::as_array)
        .ok_or("lines")?;
    assert!(!lines.is_empty());
    for line in lines {
        let text = line.get("text").and_then(Value::as_str).unwrap_or_default();
        assert!(text.starts_with("MOCK REPORT"), "{text}");
        let source = line
            .get("source")
            .and_then(Value::as_str)
            .unwrap_or_default();
        assert!(source.starts_with("task:"), "{source}");
    }
    Ok(())
}

#[tokio::test]
async fn brain_permissions_follow_the_roles() -> TestResult {
    let app = MockApp::start()?;
    let summarise =
        json!({ "lang": "en", "sources": [{ "id": "n", "kind": "note", "text": "x" }] });
    let report = json!({ "kind": "incident", "from": "2026-11-14T06:00:00Z", "to": "2026-11-14T14:00:00Z", "lang": "en" });
    let cases: &[(&str, &str, &Value, StatusCode)] = &[
        (
            "mock-reception",
            "/brain/translate",
            &translate_body("x"),
            StatusCode::OK,
        ),
        (
            "mock-robot",
            "/brain/translate",
            &translate_body("x"),
            StatusCode::FORBIDDEN,
        ),
        ("mock-nurse", "/brain/summarise", &summarise, StatusCode::OK),
        (
            "mock-therapist",
            "/brain/summarise",
            &summarise,
            StatusCode::OK,
        ),
        (
            "mock-reception",
            "/brain/summarise",
            &summarise,
            StatusCode::FORBIDDEN,
        ),
        (
            "mock-admin",
            "/brain/summarise",
            &summarise,
            StatusCode::FORBIDDEN,
        ),
        ("mock-doctor", "/brain/report", &report, StatusCode::OK),
        ("mock-admin", "/brain/report", &report, StatusCode::OK),
        (
            "mock-nurse",
            "/brain/report",
            &report,
            StatusCode::FORBIDDEN,
        ),
    ];
    for (token, path, body, expected) in cases {
        let reply = call(&app.app, post_json(path, Some(token), body)?).await?;
        assert_eq!(reply.status, *expected, "{token} {path}: {}", reply.body);
        if *expected == StatusCode::FORBIDDEN {
            assert_eq!(reply.error_code(), Some("forbidden"));
        }
    }
    let anonymous = call(
        &app.app,
        post_json("/brain/translate", None, &translate_body("x"))?,
    )
    .await?;
    assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED);
    Ok(())
}

#[tokio::test]
async fn mock_health_reports_the_brain_up() -> TestResult {
    let app = MockApp::start()?;
    let health = call(&app.app, get("/health", None)?).await?;
    assert_eq!(
        health.body.get("brain"),
        Some(&json!("up")),
        "{}",
        health.body
    );
    let brain = call(&app.app, get("/brain/health", Some("mock-nurse"))?).await?;
    assert_eq!(brain.status, StatusCode::OK);
    assert_eq!(brain.body.get("status"), Some(&json!("up")));
    Ok(())
}

#[tokio::test]
async fn invalid_brain_input_is_422_and_never_repeats_the_text() -> TestResult {
    let app = MockApp::start()?;
    let long = SENTINEL.repeat(400);
    let reply = call(
        &app.app,
        post_json(
            "/brain/translate",
            Some("mock-nurse"),
            &translate_body(&long),
        )?,
    )
    .await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    assert!(!reply.body.to_string().contains(SENTINEL));
    let backwards = call(
        &app.app,
        post_json(
            "/brain/report",
            Some("mock-doctor"),
            &json!({ "kind": "shift", "from": "2026-11-14T14:00:00Z", "to": "2026-11-14T06:00:00Z", "lang": "en" }),
        )?,
    )
    .await?;
    assert_eq!(backwards.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(backwards.error_code(), Some("invalid_field"));
    let duplicate = call(
        &app.app,
        post_json(
            "/brain/summarise",
            Some("mock-doctor"),
            &json!({ "lang": "en", "sources": [
                { "id": "n", "kind": "note", "text": "a" },
                { "id": "n", "kind": "note", "text": "b" }
            ]}),
        )?,
    )
    .await?;
    assert_eq!(duplicate.status, StatusCode::UNPROCESSABLE_ENTITY);
    Ok(())
}

#[tokio::test]
async fn sentinel_text_never_reaches_logs_or_audit_rows() -> TestResult {
    let logs = LogCapture::global()?;
    let mark = logs.mark();
    let app = MockApp::start()?;
    let sent = [
        post_json(
            "/brain/translate",
            Some("mock-nurse"),
            &translate_body(SENTINEL),
        )?,
        post_json(
            "/brain/simplify",
            Some("mock-nurse"),
            &json!({ "text": SENTINEL, "lang": "fr", "level": "plain" }),
        )?,
        post_json(
            "/brain/summarise",
            Some("mock-nurse"),
            &json!({ "lang": "en", "sources": [{ "id": "n-1", "kind": "note", "text": SENTINEL }] }),
        )?,
    ];
    for request in sent {
        let reply = call(&app.app, request).await?;
        assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    }
    let logged = logs.since(mark);
    assert!(logged.contains(REQUEST_TRACE_LINE), "nothing was captured");
    assert!(!logged.contains(SENTINEL), "a brain text reached the logs");
    let audit = call(&app.app, get("/audit?limit=500", Some("mock-admin"))?).await?;
    assert_eq!(audit.status, StatusCode::OK);
    let rows = audit.body.to_string();
    assert!(
        !rows.contains(SENTINEL),
        "a brain text reached the audit rows"
    );
    for action in ["brain_translate", "brain_simplify", "brain_summarise"] {
        assert!(rows.contains(action), "no {action} row: {rows}");
    }
    Ok(())
}

// ------------------------------------------------------------------- clinic-brain process

#[tokio::test]
async fn brain_without_python_answers_503_brain_unavailable_on_every_route() -> TestResult {
    let app = brain_router(Arc::new(UnavailableEngine::without_python()))?;
    let report = json!({
        "request": { "kind": "shift", "from": "2026-11-14T06:00:00Z", "to": "2026-11-14T14:00:00Z", "lang": "en" },
        "facts": []
    });
    let calls = [
        request(
            Method::POST,
            "/v1/translate",
            Some(TOKEN),
            Some(&translate_body("x")),
        )?,
        request(
            Method::POST,
            "/v1/simplify",
            Some(TOKEN),
            Some(&json!({ "text": "x", "lang": "fr", "level": "plain" })),
        )?,
        request(
            Method::POST,
            "/v1/summarise",
            Some(TOKEN),
            Some(&json!({ "lang": "en", "sources": [{ "id": "n", "kind": "note", "text": "x" }] })),
        )?,
        request(Method::POST, "/v1/report", Some(TOKEN), Some(&report))?,
        request(Method::GET, "/v1/health", Some(TOKEN), None)?,
    ];
    for request in calls {
        let path = request.uri().path().to_owned();
        let reply = call(&app, request).await?;
        assert_eq!(
            reply.status,
            StatusCode::SERVICE_UNAVAILABLE,
            "{path}: {}",
            reply.body
        );
        assert_eq!(reply.error_code(), Some("brain_unavailable"), "{path}");
        assert!(
            reply.error_message().contains("--features python"),
            "{path}: {}",
            reply.error_message()
        );
    }
    Ok(())
}

#[tokio::test]
async fn brain_api_refuses_non_localhost() -> TestResult {
    let app = brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?;
    let reply = call_from(
        &app,
        FOREIGN_PEER,
        request(
            Method::POST,
            "/v1/translate",
            Some(TOKEN),
            Some(&translate_body("x")),
        )?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("loopback_only"));
    Ok(())
}

#[tokio::test]
async fn brain_api_refuses_a_missing_or_wrong_token() -> TestResult {
    let app = brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?;
    for token in [None, Some("test-brain-token-0123456789abcdeX")] {
        let reply = call(&app, request(Method::GET, "/v1/health", token, None)?).await?;
        assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{token:?}");
        assert_eq!(reply.error_code(), Some("brain_token"));
    }
    let ok = call(&app, request(Method::GET, "/v1/health", Some(TOKEN), None)?).await?;
    assert_eq!(ok.status, StatusCode::OK, "{}", ok.body);
    Ok(())
}

// --------------------------------------------------------------- main server's client

#[tokio::test]
async fn client_carries_drafts_to_and_from_a_running_brain() -> TestResult {
    let server = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?)
    .await?;
    let client = client(&server, Some(token()?), Duration::from_secs(5))?;
    let health = client.probe().await;
    assert_eq!(health.status, BrainStatus::Up, "{health:?}");
    let result = client
        .translate(&translate_request("Le robot a fait 20 courses.")?)
        .await
        .map_err(|e| e.to_string())?;
    assert_eq!(result.text.expose(), "Le robot a fait 20 courses.");
    assert_eq!(result.to.as_str(), "en");
    Ok(())
}

#[tokio::test]
async fn main_server_reports_down_for_a_brain_without_python() -> TestResult {
    let server =
        LiveServer::serve(brain_router(Arc::new(UnavailableEngine::without_python()))?).await?;
    let client = client(&server, Some(token()?), Duration::from_secs(5))?;
    let health = client.probe().await;
    assert_eq!(health.status, BrainStatus::Down);
    assert!(
        health.detail.as_deref() == Some("clinic-brain cannot run its models (see its log)"),
        "{health:?}"
    );
    let error = client
        .translate(&translate_request("Bonjour")?)
        .await
        .err()
        .ok_or("a brain without Python must refuse")?;
    let api = ApiError::from(error);
    assert_eq!(api.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(api.code(), "brain_unavailable");
    Ok(())
}

#[tokio::test]
async fn client_says_why_the_brain_is_down() -> TestResult {
    // Nothing listens: a port that was free a moment ago.
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    let free = listener.local_addr()?;
    drop(listener);
    let nobody = BrainClient::new(&BrainClientConfig::local(
        free,
        Some(token()?),
        Duration::from_secs(2),
    )?);
    let health = nobody.probe().await;
    assert_eq!(health.status, BrainStatus::Down);
    assert_eq!(
        health.detail.as_deref(),
        Some("clinic-brain is not running")
    );

    // No token configured on the main server.
    let unconfigured = BrainClient::new(&BrainClientConfig::default());
    let error = unconfigured
        .translate(&translate_request("x")?)
        .await
        .err()
        .ok_or("expected NotConfigured")?;
    assert_eq!(error, BrainClientError::NotConfigured);
    assert_eq!(ApiError::from(error).code(), "brain_unavailable");

    // A wrong token: the brain refuses, the server says so.
    let server = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?)
    .await?;
    let wrong = client(
        &server,
        Some(BrainToken::new(
            "another-token-0123456789abcdef".to_owned(),
        )?),
        Duration::from_secs(2),
    )?;
    let health = wrong.probe().await;
    assert_eq!(health.status, BrainStatus::Down);
    assert_eq!(
        health.detail.as_deref(),
        Some("clinic-brain refused the server's token")
    );
    Ok(())
}

#[tokio::test]
async fn brain_call_timeout_returns_explicit_error() -> TestResult {
    let server = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::from_millis(1_500),
    }))?)
    .await?;
    let client = client(&server, Some(token()?), Duration::from_millis(200))?;
    let error = client
        .translate(&translate_request("x")?)
        .await
        .err()
        .ok_or("expected a timeout")?;
    assert!(matches!(error, BrainClientError::Timeout { .. }), "{error}");
    let api = ApiError::from(error);
    assert_eq!(api.status(), StatusCode::GATEWAY_TIMEOUT);
    assert_eq!(api.code(), "brain_timeout");
    Ok(())
}

// ------------------------------------------------------------------- live server (T20d)

#[tokio::test]
async fn brain_down_main_server_keeps_dispatching_and_answers_degraded() -> TestResult {
    let app = RealApp::start().await?;
    app.set_stock("blanket", 3).await?;
    let nurse = app.nurse_token().await?;
    let health = app.call(get("/health", None)?).await?;
    assert_eq!(
        health.body.get("brain"),
        Some(&json!("down")),
        "{}",
        health.body
    );
    assert_eq!(health.body.get("status"), Some(&json!("ok")));
    let translated = app
        .call(post_json(
            "/brain/translate",
            Some(&nurse),
            &translate_body("x"),
        )?)
        .await?;
    assert_eq!(translated.status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(translated.error_code(), Some("brain_unavailable"));
    let task = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &json!({ "kind": "fetch", "item": "blanket", "from_place": map::STOREROOM, "to_place": map::ROOM_101 }),
        )?)
        .await?;
    assert!(task.status.is_success(), "{}: {}", task.status, task.body);
    Ok(())
}

#[tokio::test]
async fn brain_texts_are_never_written_to_journal_or_logs() -> TestResult {
    let logs = LogCapture::global()?;
    let brain = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?)
    .await?;
    let app = RealApp::start_with_brain(BrainClientConfig::local(
        brain.addr,
        Some(token()?),
        Duration::from_secs(5),
    )?)
    .await?;
    let nurse = app.nurse_token().await?;
    let mark = logs.mark();
    let reply = app
        .call(post_json(
            "/brain/translate",
            Some(&nurse),
            &translate_body(SENTINEL),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("draft"), Some(&json!(true)));
    assert!(
        !logs.since(mark).contains(SENTINEL),
        "a brain text reached the logs"
    );
    let records = read_journal(&app.config.journal.dir)?;
    let journal = serde_json::to_string(&records)?;
    assert!(
        !journal.contains(SENTINEL),
        "a brain text reached the journal"
    );
    assert!(records.iter().any(|r| matches!(
        &r.body,
        audit::RecordBody::BrainCall {
            kind: domain::BrainCallKind::Translate,
            ok: true,
            ..
        }
    )));
    let audit = app
        .call(get("/audit?limit=500", Some(&app.admin_token().await?))?)
        .await?;
    assert!(!audit.body.to_string().contains(SENTINEL));
    Ok(())
}

#[tokio::test]
async fn report_lines_point_to_server_records_the_caller_may_see() -> TestResult {
    let brain = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?)
    .await?;
    let app = RealApp::start_with_brain(BrainClientConfig::local(
        brain.addr,
        Some(token()?),
        Duration::from_secs(5),
    )?)
    .await?;
    app.set_stock("blanket", 3).await?;
    let nurse = app.nurse_token().await?;
    let created = app
        .call(post_json(
            "/tasks",
            Some(&nurse),
            &json!({ "kind": "fetch", "item": "blanket", "from_place": map::STOREROOM, "to_place": map::ROOM_101 }),
        )?)
        .await?;
    let task = created
        .body
        .get("id")
        .and_then(Value::as_str)
        .ok_or("task id")?;
    let admin = app.admin_token().await?;
    let report = app
        .call(post_json(
            "/brain/report",
            Some(&admin),
            &json!({ "kind": "shift", "from": "2026-11-14T00:00:00Z", "to": "2026-11-15T00:00:00Z", "lang": "en" }),
        )?)
        .await?;
    assert_eq!(report.status, StatusCode::OK, "{}", report.body);
    let sources: Vec<&str> = report
        .body
        .get("lines")
        .and_then(Value::as_array)
        .ok_or("lines")?
        .iter()
        .filter_map(|l| l.get("source").and_then(Value::as_str))
        .collect();
    assert!(
        sources.contains(&format!("task:{task}").as_str()),
        "{sources:?}"
    );
    Ok(())
}

// ------------------------------------------- the sentinel through the client (no mock)

/// A fake brain whose every route answers `status` with an error body that repeats the
/// request body (the worst a brain could do).
fn echoing_brain(status: StatusCode, code: &'static str) -> axum::Router {
    axum::Router::new().fallback(move |body: String| async move {
        let message = format!("cannot use this request: {body}");
        (
            status,
            axum::Json(domain::ErrorBody::new(code, message, None)),
        )
    })
}

/// What a client would receive for an `ApiError`: the response body as text.
async fn client_body(error: ApiError) -> Res<String> {
    let response = error.into_response();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX).await?;
    Ok(String::from_utf8(bytes.to_vec())?)
}

#[tokio::test]
async fn sentinel_never_reaches_logs_or_client_errors_through_the_brain_client() -> TestResult {
    let logs = LogCapture::global()?;
    let mark = logs.mark();
    tracing::info!("brain sentinel test: capture works");
    let sentinel = translate_request(SENTINEL)?;

    // Success: the draft comes back (to the caller only).
    let echo = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?)
    .await?;
    let ok = client(&echo, Some(token()?), Duration::from_secs(5))?
        .translate(&sentinel)
        .await
        .map_err(|e| e.to_string())?;
    assert_eq!(ok.text.expose(), SENTINEL);

    // Timeout, wrong token, and a brain whose 422 repeats the input.
    let slow = LiveServer::serve(brain_router(Arc::new(EchoEngine {
        delay: Duration::from_millis(1_500),
    }))?)
    .await?;
    let echoing = LiveServer::serve(echoing_brain(
        StatusCode::UNPROCESSABLE_ENTITY,
        "invalid_field",
    ))
    .await?;
    let failures = [
        client(&slow, Some(token()?), Duration::from_millis(200))?,
        client(
            &echo,
            Some(BrainToken::new(
                "another-token-0123456789abcdef".to_owned(),
            )?),
            Duration::from_secs(5),
        )?,
        client(&echoing, Some(token()?), Duration::from_secs(5))?,
    ];
    let mut codes = Vec::new();
    for failing in failures {
        let error = failing
            .translate(&sentinel)
            .await
            .err()
            .ok_or("expected a failure")?;
        assert!(!error.to_string().contains(SENTINEL), "Display: {error}");
        assert!(
            !format!("{error:?}").contains(SENTINEL),
            "Debug leaks the text"
        );
        let api = ApiError::from(error);
        codes.push(api.code());
        assert!(!api.message().contains(SENTINEL), "{}", api.message());
        let body = client_body(api).await?;
        assert!(!body.contains(SENTINEL), "client body: {body}");
    }
    assert_eq!(
        codes,
        ["brain_timeout", "brain_unavailable", "invalid_field"]
    );

    let logged = logs.since(mark);
    assert!(logged.contains("capture works"), "nothing was captured");
    assert!(!logged.contains(SENTINEL), "a brain text reached the logs");
    Ok(())
}

// ------------------------------------------------------------------ size contract (R23)

/// A summarise body of 20 sources, each with `text`.
fn twenty_sources(text: &str) -> Value {
    let sources: Vec<Value> = (0..20)
        .map(|i| json!({ "id": format!("note-{i}"), "kind": "note", "text": text }))
        .collect();
    json!({ "lang": "en", "sources": sources })
}

#[tokio::test]
async fn twenty_sources_of_8000_multibyte_chars_pass_through_the_brain_route() -> TestResult {
    let app = MockApp::start()?;
    let text = "😀".repeat(domain::brain::MAX_TEXT_CHARS);
    let body = twenty_sources(&text);
    assert!(
        body.to_string().len() > 600_000,
        "the test must exceed 64 KiB by far"
    );
    let reply = call(
        &app.app,
        post_json("/brain/summarise", Some("mock-doctor"), &body)?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.error_message());
    let lines = reply
        .body
        .get("lines")
        .and_then(Value::as_array)
        .ok_or("lines")?;
    assert_eq!(lines.len(), 20);
    Ok(())
}

/// A raw translate body of exactly `size` bytes.
fn body_of(size: usize) -> Res<String> {
    let frame = r#"{"to":"en","text":""}"#;
    let pad = size.checked_sub(frame.len()).ok_or("size too small")?;
    Ok(format!(r#"{{"to":"en","text":"{}"}}"#, "a".repeat(pad)))
}

#[tokio::test]
async fn one_byte_over_the_brain_route_cap_is_413_json() -> TestResult {
    let app = MockApp::start()?;
    for declared in [false, true] {
        let over = body_of(BRAIN_MAX_BODY_BYTES + 1)?;
        let mut request = post_raw("/brain/translate", Some("mock-nurse"), &over)?;
        if declared {
            request = with_header(request, "content-length", &over.len().to_string())?;
        }
        let reply = call(&app.app, request).await?;
        assert_eq!(
            reply.status,
            StatusCode::PAYLOAD_TOO_LARGE,
            "declared {declared}"
        );
        assert_eq!(reply.error_code(), Some("body_too_large"), "{}", reply.body);
    }
    // At the cap the body is read: the text is then refused as too long (422), not 413.
    let at_cap = body_of(BRAIN_MAX_BODY_BYTES)?;
    let reply = call(
        &app.app,
        post_raw("/brain/translate", Some("mock-nurse"), &at_cap)?,
    )
    .await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    // Every other route keeps 64 KiB.
    let tasks = call(
        &app.app,
        post_raw("/tasks", Some("mock-nurse"), &body_of(64 * 1024 + 1)?)?,
    )
    .await?;
    assert_eq!(tasks.status, StatusCode::PAYLOAD_TOO_LARGE);
    Ok(())
}

#[test]
fn the_worst_case_request_fits_the_brain_process_limit() -> TestResult {
    // Control characters are the longest in JSON (`\u0001`, 6 bytes each); ids are 96 long.
    let text = PrivateText::new("\u{1}".repeat(domain::brain::MAX_TEXT_CHARS))?;
    let sources = (0..domain::brain::MAX_SOURCES)
        .map(|i| -> Res<domain::SummarySource> {
            Ok(domain::SummarySource {
                id: format!("{i:0>96}").parse()?,
                kind: domain::SourceKind::Transcript,
                text: text.clone(),
            })
        })
        .collect::<Res<Vec<_>>>()?;
    let request = SummariseRequest {
        sources,
        lang: "pt-br".parse()?,
    };
    let size = serde_json::to_vec(&request)?.len();
    assert!(
        size <= BRAIN_PROCESS_MAX_BODY_BYTES,
        "{size} > {BRAIN_PROCESS_MAX_BODY_BYTES}"
    );
    Ok(())
}

#[tokio::test]
async fn brain_process_answers_413_as_json_and_the_server_keeps_413() -> TestResult {
    let app = brain_router(Arc::new(EchoEngine {
        delay: Duration::ZERO,
    }))?;
    let over = body_of(BRAIN_PROCESS_MAX_BODY_BYTES + 1)?;
    let reply = call(&app, post_raw("/v1/translate", Some(TOKEN), &over)?).await?;
    assert_eq!(reply.status, StatusCode::PAYLOAD_TOO_LARGE);
    assert_eq!(reply.error_code(), Some("body_too_large"), "{}", reply.body);

    // The main server's client maps the brain's 413 to its own 413, not 502.
    let refusing = LiveServer::serve(echoing_brain(
        StatusCode::PAYLOAD_TOO_LARGE,
        "body_too_large",
    ))
    .await?;
    let error = client(&refusing, Some(token()?), Duration::from_secs(5))?
        .translate(&translate_request("x")?)
        .await
        .err()
        .ok_or("expected a refusal")?;
    let api = ApiError::from(error);
    assert_eq!(api.status(), StatusCode::PAYLOAD_TOO_LARGE);
    assert_eq!(api.code(), "body_too_large");
    Ok(())
}
