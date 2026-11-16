//! Hackathon: `POST /v1/transcribe` of the brain process, through the main server's
//! `BrainClient::transcribe` (happy path, fake engine; the real faster-whisper run is in
//! `docs/brain.md`, "Run the brain on Windows").

mod support;

use std::sync::Arc;
use std::time::Duration;

use axum::body::Bytes;
use clinic_server::brain_process::{BrainApiState, build_brain_router};
use clinic_server::config::{BrainClientConfig, BrainToken};
use clinic_server::services::brain::BrainClient;
use domain::{
    BrainHealth, BrainReportRequest, BrainStatus, ReportDraft, SimplifyRequest, SimplifyResult,
    SummariseRequest, SummaryDraft, TranslateRequest, TranslateResult,
};
use python_bindings::{BrainEngine, BridgeError, Transcription};
use support::{LiveServer, TestResult};

const TOKEN: &str = "test-brain-token-0123456789abcdef";

/// Hears "Bonjour" in French whatever the recording, and checks it got the bytes.
struct EarEngine;

fn refused<T>() -> Result<T, BridgeError> {
    Err(BridgeError::InterpreterUnavailable {
        detail: "not in this test".to_owned(),
    })
}

impl BrainEngine for EarEngine {
    fn translate(&self, _: &TranslateRequest) -> Result<TranslateResult, BridgeError> {
        refused()
    }
    fn simplify(&self, _: &SimplifyRequest) -> Result<SimplifyResult, BridgeError> {
        refused()
    }
    fn summarise(&self, _: &SummariseRequest) -> Result<SummaryDraft, BridgeError> {
        refused()
    }
    fn report(&self, _: &BrainReportRequest) -> Result<ReportDraft, BridgeError> {
        refused()
    }
    fn health(&self) -> BrainHealth {
        BrainHealth {
            status: BrainStatus::Up,
            models: vec!["ear".to_owned()],
            queue: 0,
            detail: None,
        }
    }
    fn transcribe(&self, audio: Vec<u8>) -> Result<Transcription, BridgeError> {
        Ok(Transcription {
            text: format!("Bonjour ({} bytes)", audio.len()),
            lang: "fr".to_owned(),
            duration_s: 1.5,
        })
    }
}

#[tokio::test]
async fn a_recording_goes_through_the_client_and_comes_back_as_text() -> TestResult {
    let token = BrainToken::new(TOKEN.to_owned())?;
    let router = build_brain_router(BrainApiState::new(
        Arc::new(EarEngine),
        token.clone(),
        Duration::from_secs(5),
    ));
    let server = LiveServer::serve(router).await?;
    let client = BrainClient::new(&BrainClientConfig::local(
        server.addr,
        Some(token),
        Duration::from_secs(5),
    )?);
    let heard = client
        .transcribe(Bytes::from_static(b"RIFF....WAVE"), "audio/wav")
        .await?;
    assert_eq!(heard.text, "Bonjour (12 bytes)");
    assert_eq!(heard.lang, "fr");
    assert!((heard.duration_s - 1.5).abs() < f64::EPSILON);
    Ok(())
}
