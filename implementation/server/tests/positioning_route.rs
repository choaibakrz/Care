//! Task 11b: `POST /me/scans`. Raw scans are processed in memory and dropped: never
//! stored, journaled or logged.

mod support;

use axum::http::StatusCode;
use serde_json::json;
use support::{LogCapture, RealApp, TestResult, post_json};

#[tokio::test]
async fn raw_scans_never_reach_logs_or_journal() -> TestResult {
    let logs = LogCapture::global()?;
    let mark = logs.mark();
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let scan = json!({
        "at": support::start_time()?.to_rfc3339(),
        "observations": [
            { "type": "rssi", "anchor": "beacon-qx7", "dbm": -87 },
            { "type": "rssi", "anchor": "beacon-qx8", "dbm": -64 },
            { "type": "range", "anchor": "beacon-qx9", "metres": 4.25, "sigma_m": 0.5 }
        ],
        "motion": { "steps": 3, "heading_rad": 1.25, "heading_sigma_rad": 0.1, "stride_m": 0.7 },
        "pressure_hpa": 963.25
    });
    let reply = app
        .call(post_json("/me/scans", Some(&token), &scan)?)
        .await?;
    assert!(
        reply.status == StatusCode::OK || reply.status == StatusCode::UNPROCESSABLE_ENTITY,
        "{}: {}",
        reply.status,
        reply.body
    );
    app.journal.seal_now(audit::SealReason::Interval).await?;
    let journal = serde_json::to_string(&support::read_journal(&app.config.journal.dir)?)?;
    let text = logs.since(mark);
    assert!(
        text.contains(support::REQUEST_TRACE_LINE),
        "the request log line was not captured, so the capture proves nothing"
    );
    for leak in ["beacon-qx7", "beacon-qx8", "beacon-qx9", "963.25", "4.25"] {
        assert!(!journal.contains(leak), "the journal contains '{leak}'");
        assert!(!text.contains(leak), "the logs contain '{leak}'");
    }
    Ok(())
}
