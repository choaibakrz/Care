//! Step R1: the live server's first start, as `cargo run` serves it (real wiring, journal,
//! database, security stack): the one-time admin code, enrolment, login, the map, and
//! the real services.

mod support;

use axum::http::StatusCode;
use domain::ports::AccountRepository as _;
use serde_json::json;
use support::{RealApp, TEST_PASSWORD, TestResult, derived_key, get, post_json};

#[tokio::test]
async fn first_admin_enrols_with_the_startup_code_then_logs_in_and_reads_the_map() -> TestResult {
    let app = RealApp::start().await?;
    let code = app
        .first_admin_code
        .clone()
        .ok_or("no admin code was issued on a first start")?;
    let key = derived_key("first.admin", TEST_PASSWORD)?.to_hex();

    let enrolled = app
        .call(post_json(
            "/auth/enrol",
            None,
            &json!({ "enrolment_code": code, "account_key": key, "display_label": "Admin 1" }),
        )?)
        .await?;
    assert_eq!(enrolled.status, StatusCode::CREATED, "{}", enrolled.body);
    assert_eq!(enrolled.body.pointer("/role"), Some(&json!("admin")));

    let login = app
        .call(post_json(
            "/auth/login",
            None,
            &json!({ "account_key": key }),
        )?)
        .await?;
    assert_eq!(login.status, StatusCode::OK, "{}", login.body);
    let token = login
        .body
        .pointer("/token")
        .and_then(|token| token.as_str())
        .ok_or("no token")?
        .to_owned();

    let map = app.call(get("/map", Some(&token))?).await?;
    assert_eq!(map.status, StatusCode::OK, "{}", map.body);

    let robots = app.call(get("/robots", Some(&token))?).await?;
    assert_eq!(robots.status, StatusCode::OK, "{}", robots.body);
    Ok(())
}

#[tokio::test]
async fn no_admin_code_is_issued_once_an_account_exists() -> TestResult {
    let app = RealApp::start().await?;
    app.admin_token().await?;
    let again = app
        .relaunch_with_pepper(app.pepper.as_ref().clone())
        .await?;
    assert_eq!(again.first_admin_code, None);
    Ok(())
}

#[tokio::test]
async fn a_restart_without_account_retires_the_earlier_admin_code() -> TestResult {
    let app = RealApp::start().await?;
    let first = app.first_admin_code.clone().ok_or("no first code")?;
    let again = app
        .relaunch_with_pepper(app.pepper.as_ref().clone())
        .await?;
    let second = again.first_admin_code.clone().ok_or("no second code")?;
    let enrol = |code: &str, user: &str| -> support::Res<_> {
        post_json(
            "/auth/enrol",
            None,
            &json!({
                "enrolment_code": code,
                "account_key": derived_key(user, TEST_PASSWORD)?.to_hex(),
                "display_label": "Admin 1",
            }),
        )
    };
    let old = again.call(enrol(&first, "a")?).await?;
    assert_eq!(old.error_code(), Some("enrolment_refused"), "{}", old.body);
    let new = again.call(enrol(&second, "b")?).await?;
    assert_eq!(new.status, StatusCode::CREATED, "{}", new.body);
    Ok(())
}

#[tokio::test]
async fn a_missing_pepper_is_created_only_on_a_fresh_installation() -> TestResult {
    let dir = support::temp_dir("pepper")?;
    let path = dir.join("keys").join("account.pepper");
    let db = storage::Database::in_memory().await?;
    db.migrate().await?;
    let created = clinic_server::state::load_pepper(&path, &db).await?;
    assert!(path.exists());
    let reloaded = clinic_server::state::load_pepper(&path, &db).await?;
    let key = derived_key("someone", TEST_PASSWORD)?;
    assert_eq!(
        security::account_id(&created, &key),
        security::account_id(&reloaded, &key)
    );

    // An account exists, then the pepper file is lost: refused, nothing created.
    storage::SqliteAccountRepository::new(db.clone())
        .insert(&domain::AccountRecord {
            id: security::account_id(&created, &key),
            role: domain::Role::Admin,
            display_label: domain::OwnerLabel::new("Admin 1")?,
            created_at: support::start_time()?,
            disabled: false,
        })
        .await?;
    std::fs::remove_file(&path)?;
    let refused = clinic_server::state::load_pepper(&path, &db).await.err();
    assert!(
        refused
            .as_ref()
            .is_some_and(|error| error.to_string().contains("missing")),
        "{refused:?}"
    );
    assert!(!path.exists());
    Ok(())
}
