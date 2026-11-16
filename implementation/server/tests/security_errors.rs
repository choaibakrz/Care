//! Task 7: a handler error comes back as a 500 error body without internal detail.

mod support;

use std::sync::Arc;

use async_trait::async_trait;
use axum::Router;
use axum::http::StatusCode;
use axum::routing::get;
use clinic_server::error::ApiError;
use domain::DomainError;
use security::{SecurityError, SecurityStack, TokenVerifier, VerifiedIdentity};
use support::{TestResult, call, get as get_req, security_config};

/// Knows no token: the test route is public.
struct NoTokens;

#[async_trait]
impl TokenVerifier for NoTokens {
    async fn verify(&self, _raw: &str) -> Result<Option<VerifiedIdentity>, SecurityError> {
        Ok(None)
    }
}

async fn failing() -> Result<(), ApiError> {
    Err(ApiError::from(DomainError::Corrupt {
        table: "tasks",
        reason: r"sqlx: no such column 'secret' in C:\data\clinic.db".to_owned(),
    }))
}

#[tokio::test]
async fn handler_error_returns_500_error_body_without_internal_detail() -> TestResult {
    let mut config = security_config()?;
    config.public_paths.push("/fail".to_owned());
    let stack = SecurityStack::new(config, Arc::new(NoTokens))?;
    let app = stack.apply(Router::new().route("/fail", get(failing)));
    let reply = call(&app, get_req("/fail", None)?).await?;
    assert_eq!(reply.status, StatusCode::INTERNAL_SERVER_ERROR);
    assert!(
        reply.error_code().is_some(),
        "not an error body: {}",
        reply.body
    );
    let message = reply.error_message();
    assert!(!message.is_empty());
    for leak in ["sqlx", "clinic.db", "secret", r"C:\"] {
        assert!(!message.contains(leak), "message leaks '{leak}': {message}");
    }
    Ok(())
}
