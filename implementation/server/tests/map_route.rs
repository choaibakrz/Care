//! Task 10 / 10b: `GET /map` (the active clinic plan) with an `ETag`, and 304 when
//! `If-None-Match` matches.

mod support;

use axum::http::StatusCode;
use support::{RealApp, TestResult, get, with_header};

#[tokio::test]
async fn get_map_returns_etag_and_304_on_match() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let first = app.call(get("/map", Some(&token))?).await?;
    assert_eq!(first.status, StatusCode::OK, "{}", first.body);
    let etag = first.header("etag").ok_or("no ETag")?.to_owned();
    assert!(!etag.is_empty());
    assert!(first.body.get("floors").is_some(), "{}", first.body);
    let second = app
        .call(with_header(
            get("/map", Some(&token))?,
            "if-none-match",
            &etag,
        )?)
        .await?;
    assert_eq!(second.status, StatusCode::NOT_MODIFIED);
    let stale = app
        .call(with_header(
            get("/map", Some(&token))?,
            "if-none-match",
            "\"other\"",
        )?)
        .await?;
    assert_eq!(stale.status, StatusCode::OK);
    Ok(())
}
