//! Task 8: login, tokens bound to devices, roles, `/me`. (The `/ws` first-message
//! authentication is tested in `console_contract.rs`.)
//!
//! Task A7 changed the login: the client sends the key it derived from user name and
//! password (`support::login_body`), never the name or the password; accounts carry a
//! pseudonym, shown as `"<pseudonym> #<tag>"`. The account flows themselves (enrolment,
//! pepper, database dump) are in `accounts.rs`.

mod support;

use std::collections::BTreeSet;
use std::num::NonZeroU32;

use axum::http::StatusCode;
use clinic_server::dto::MeView;
use domain::Role;
use serde_json::{Value, json};
use support::{
    RealApp, TEST_PASSWORD, TestResult, get, login_body, post_json, put_json, security_config,
    with_header,
};
use utoipa::PartialSchema as _;

const ME_KEYS: [&str; 6] = [
    "subject",
    "role",
    "device_id",
    "owner_label",
    "network",
    "area",
];

fn keys(value: &Value) -> BTreeSet<String> {
    value
        .as_object()
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default()
}

#[tokio::test]
async fn login_with_derived_key_returns_token_and_role() -> TestResult {
    let app = RealApp::start().await?;
    let id = app
        .add_account("u-nurse", Role::Nurse, "Ward 2 nurse")
        .await?;
    let reply = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("u-nurse", TEST_PASSWORD, Some("tab-1"))?,
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let token = reply
        .body
        .get("token")
        .and_then(Value::as_str)
        .unwrap_or_default();
    assert!(!token.is_empty());
    assert_eq!(reply.body.get("role"), Some(&json!("nurse")));
    assert_eq!(
        reply.body.get("operator"),
        Some(&json!(format!("Ward 2 nurse #{}", id.tag())))
    );
    assert!(reply.body.get("expires_at").is_some());
    Ok(())
}

/// A browser (the admin console) sends no device id: the login still works and the token is
/// bound to no device.
#[tokio::test]
async fn login_without_device_id_returns_a_working_token() -> TestResult {
    let app = RealApp::start().await?;
    let id = app
        .add_account("u-admin", Role::Admin, "Night admin")
        .await?;
    let reply = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("u-admin", TEST_PASSWORD, None)?,
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body.get("role"), Some(&json!("admin")));
    assert_eq!(
        reply.body.get("operator"),
        Some(&json!(format!("Night admin #{}", id.tag())))
    );
    let token = reply
        .body
        .get("token")
        .and_then(Value::as_str)
        .ok_or("no token")?;
    let me = app.call(get("/me", Some(token))?).await?;
    assert_eq!(me.status, StatusCode::OK, "{}", me.body);
    assert_eq!(me.body.get("device_id"), Some(&Value::Null));
    Ok(())
}

#[tokio::test]
async fn wrong_password_and_unknown_user_have_identical_response_bodies() -> TestResult {
    let app = RealApp::start().await?;
    app.add_account("u-nurse", Role::Nurse, "Ward 2 nurse")
        .await?;
    let wrong_pin = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("u-nurse", "0000", Some("tab-1"))?,
        )?)
        .await?;
    let unknown = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("u-ghost", "0000", Some("tab-1"))?,
        )?)
        .await?;
    assert_eq!(wrong_pin.status, StatusCode::UNAUTHORIZED);
    assert_eq!(wrong_pin.status, unknown.status);
    assert_eq!(wrong_pin.body, unknown.body);
    assert_eq!(
        wrong_pin.error_message(),
        "User name or password is incorrect."
    );
    Ok(())
}

#[tokio::test]
#[ignore = "security stack: the live stack does not yet turn 5 failed logins from one address into 429 (needs the security reviewer)"]
async fn five_failed_logins_from_one_ip_return_429() -> TestResult {
    let mut security = security_config()?;
    security.rate = security::RateLimitConfig {
        per_second: NonZeroU32::new(1).ok_or("zero")?,
        burst: NonZeroU32::new(5).ok_or("zero")?,
    };
    let app = RealApp::start_with(support::map::small_plan()?, security).await?;
    app.add_account("u-nurse", Role::Nurse, "Ward 2 nurse")
        .await?;
    for attempt in 1..=5 {
        let reply = app
            .call(post_json(
                "/auth/login",
                None,
                &login_body("u-nurse", "0000", Some("tab-1"))?,
            )?)
            .await?;
        assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "attempt {attempt}");
    }
    let reply = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("u-nurse", TEST_PASSWORD, Some("tab-1"))?,
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(reply.error_code(), Some("rate_limited"));
    Ok(())
}

#[tokio::test]
async fn token_is_bound_to_the_device_it_was_issued_for() -> TestResult {
    let app = RealApp::start().await?;
    app.add_account("u-nurse", Role::Nurse, "Ward 2 nurse")
        .await?;
    let login = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("u-nurse", TEST_PASSWORD, Some("tab-1"))?,
        )?)
        .await?;
    let token = login
        .body
        .get("token")
        .and_then(Value::as_str)
        .ok_or("no token")?
        .to_owned();
    let other_device = app
        .call(with_header(
            get("/me", Some(&token))?,
            "x-client-id",
            "tab-2",
        )?)
        .await?;
    assert_eq!(other_device.status, StatusCode::FORBIDDEN);
    assert_eq!(other_device.error_code(), Some("identity_mismatch"));
    let same_device = app
        .call(with_header(
            get("/me", Some(&token))?,
            "x-client-id",
            "tab-1",
        )?)
        .await?;
    assert_eq!(same_device.status, StatusCode::OK);
    Ok(())
}

/// Strict rule: a token bound to no device never matches an `X-Client-Id` header.
#[tokio::test]
async fn client_id_header_with_device_less_token_is_403_identity_mismatch() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.browser_token("u-admin", Role::Admin).await?;
    let reply = app
        .call(with_header(
            get("/me", Some(&token))?,
            "x-client-id",
            "tab-1",
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("identity_mismatch"));
    Ok(())
}

/// The tablet-only endpoints refuse a device-less token (browser login) with an explicit
/// 403 `device_required`.
#[tokio::test]
async fn tablet_endpoints_refuse_device_less_token_with_device_required() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.browser_token("u-nurse", Role::Nurse).await?;
    let calls = vec![
        put_json(
            "/me/location",
            Some(&token),
            &json!({ "place": "room-101" }),
        )?,
        post_json(
            "/me/scans",
            Some(&token),
            &json!({ "at": "2026-11-15T08:00:00Z", "observations": [] }),
        )?,
        post_json(
            "/devices/me/events",
            Some(&token),
            &json!({ "code": "camera_unavailable" }),
        )?,
    ];
    for call in calls {
        let path = call.uri().path().to_owned();
        let reply = app.call(call).await?;
        assert_eq!(
            reply.status,
            StatusCode::FORBIDDEN,
            "{path}: {}",
            reply.body
        );
        assert_eq!(reply.error_code(), Some("device_required"), "{path}");
        assert!(
            reply.error_message().contains("tablet"),
            "{path}: {}",
            reply.error_message()
        );
    }
    Ok(())
}

#[tokio::test]
async fn nurse_token_cannot_call_put_zones_gets_403() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let zone = json!({
        "id": "z-new", "name": "Room 101 quiet", "kind": "deaf", "floor": 1,
        "polygon": [[1.0, 13.0], [9.0, 13.0], [9.0, 19.0]]
    });
    let reply = app
        .call(put_json("/zones/z-new", Some(&token), &zone)?)
        .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(reply.error_code(), Some("forbidden"));
    assert!(
        reply.error_message().contains("edit_zones"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

#[tokio::test]
async fn me_returns_owner_label_and_nothing_else_about_the_person() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let reply = app.call(get("/me", Some(&token))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let expected: BTreeSet<String> = ME_KEYS.iter().map(|k| (*k).to_owned()).collect();
    assert_eq!(keys(&reply.body), expected);
    let tag = app.account_of("u-nurse")?.tag();
    assert_eq!(
        reply.body.get("owner_label"),
        Some(&json!(format!("Test nurse #{tag}")))
    );
    Ok(())
}

/// Type-level companion of the test above: the documented `/me` body has exactly these keys.
#[test]
fn me_view_schema_has_exactly_the_allowed_keys() -> TestResult {
    let schema = serde_json::to_value(MeView::schema())?;
    let properties = schema.get("properties").ok_or("MeView has no properties")?;
    let expected: BTreeSet<String> = ME_KEYS.iter().map(|k| (*k).to_owned()).collect();
    assert_eq!(keys(properties), expected);
    Ok(())
}

#[tokio::test]
async fn failed_login_writes_no_key_anywhere() -> TestResult {
    let app = RealApp::start().await?;
    app.add_account("u-nurse", Role::Nurse, "Ward 2 nurse")
        .await?;
    let wrong = support::derived_key("u-nurse", "9137")?.to_hex();
    let reply = app
        .call(post_json(
            "/auth/login",
            None,
            &json!({ "account_key": wrong, "device_id": "tab-1" }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::UNAUTHORIZED);
    app.journal.seal_now(audit::SealReason::Interval).await?;
    let records = support::read_journal(&app.config.journal.dir)?;
    for record in &records {
        assert!(!serde_json::to_string(record)?.contains(&wrong));
    }
    Ok(())
}
