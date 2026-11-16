//! Task A7: pseudonymous accounts (the server never learns who a user is) and the admin's
//! revert of a non-admin's robot command.
//!
//! - Type-level and `--mock` tests run now: the request bodies carry no user name or
//!   password, the published test vector of `docs/accounts.md` is what the reference
//!   derivation computes, the mock logs in by derived key (and still accepts a user name and
//!   password until frontend task F9), the live mode refuses that body, enrolment codes, and
//!   nurse pause -> admin alert -> admin revert -> the robot resumes.
//! - Tests on the real wiring are ignored until Task 8 (accounts, pepper, login) and Task 14
//!   (robot commands and the revert) fill their stubs.

mod support;

use std::collections::BTreeSet;
use std::time::Duration;

use axum::http::{Method, StatusCode};
use clinic_server::dto::{EnrolRequest, LoginRequest, ServerMode};
use clinic_server::openapi::ApiDoc;
use domain::AccountTag;
use security::{Pepper, derive_account_key};
use serde_json::{Value, json};
use support::{
    LiveServer, MockApp, RealApp, Res, TEST_PASSWORD, TestResult, call, derived_key, get,
    login_body, post_json, request,
};
use utoipa::OpenApi as _;
use utoipa::PartialSchema as _;

const ADMIN: Option<&str> = Some("mock-admin");
const NURSE: Option<&str> = Some("mock-nurse");

/// Words that must never be a field of anything a client sends or the server answers.
const IDENTIFYING_FIELDS: &[&str] = &[
    "username",
    "user_name",
    "password",
    "pin",
    "email",
    "real_name",
    "first_name",
    "last_name",
];

fn property_keys(schema: &Value) -> BTreeSet<String> {
    schema
        .get("properties")
        .and_then(Value::as_object)
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default()
}

fn text<'a>(value: &'a Value, pointer: &str) -> Res<&'a str> {
    value
        .pointer(pointer)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("no {pointer} in {value}").into())
}

// ---------------------------------------------------------------------------------------
// Type level and documents (run now)

/// The request bodies of login and enrolment have no user name or password field, and no
/// schema of the OpenAPI document has one either.
#[test]
fn server_never_receives_username_or_password() -> TestResult {
    let login = property_keys(&serde_json::to_value(LoginRequest::schema())?);
    assert_eq!(
        login,
        ["account_key", "device_id"].map(str::to_owned).into(),
        "LoginRequest"
    );
    let enrol = property_keys(&serde_json::to_value(EnrolRequest::schema())?);
    assert_eq!(
        enrol,
        ["enrolment_code", "account_key", "display_label"]
            .map(str::to_owned)
            .into(),
        "EnrolRequest"
    );
    let document = serde_json::to_value(ApiDoc::openapi())?;
    let schemas = document
        .pointer("/components/schemas")
        .and_then(Value::as_object)
        .ok_or("no schemas")?;
    for (name, schema) in schemas {
        for field in property_keys(schema) {
            assert!(
                !IDENTIFYING_FIELDS.contains(&field.as_str()),
                "schema {name} has the field {field}"
            );
        }
    }
    Ok(())
}

/// One test vector of `docs/accounts.md`: the lines `username:`, `password:`, `clinic_id:`
/// and `account_key:` of a fenced block tagged `vector`.
struct Vector {
    username: String,
    password: String,
    clinic_id: String,
    account_key: String,
}

fn vectors_in(doc: &str) -> Vec<Vector> {
    let mut vectors = Vec::new();
    let mut inside = false;
    let mut fields: Vec<(String, String)> = Vec::new();
    for line in doc.lines() {
        if line.trim_start().starts_with("```vector") {
            inside = true;
            fields.clear();
            continue;
        }
        if inside && line.trim_start().starts_with("```") {
            inside = false;
            let get = |key: &str| {
                fields
                    .iter()
                    .find(|(k, _)| k == key)
                    .map(|(_, v)| v.clone())
                    .unwrap_or_default()
            };
            vectors.push(Vector {
                username: get("username"),
                password: get("password"),
                clinic_id: get("clinic_id"),
                account_key: get("account_key"),
            });
            continue;
        }
        if inside && let Some((key, value)) = line.split_once(": ") {
            fields.push((key.trim().to_owned(), unescape(value)));
        }
    }
    vectors
}

/// Replaces each `\u{XXXX}` of a vector line by the code point U+XXXX (the document writes
/// decomposed accents that way so editors cannot normalise them away).
fn unescape(value: &str) -> String {
    let mut out = String::new();
    let mut rest = value;
    while let Some(start) = rest.find("\\u{") {
        let (before, after) = rest.split_at(start);
        out.push_str(before);
        let digits = after.get(3..).unwrap_or_default();
        let decoded = digits.split_once('}').and_then(|(hex, tail)| {
            u32::from_str_radix(hex, 16)
                .ok()
                .and_then(char::from_u32)
                .map(|c| (c, tail))
        });
        if let Some((c, tail)) = decoded {
            out.push(c);
            rest = tail;
        } else {
            out.push_str("\\u{");
            rest = digits;
        }
    }
    out.push_str(rest);
    out
}

/// The published test vectors (shared with the console and the staff app) are what the
/// reference derivation computes.
#[test]
fn derivation_test_vector_matches_docs() -> TestResult {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("docs/accounts.md");
    let doc = std::fs::read_to_string(path)?;
    let vectors = vectors_in(&doc);
    // Ruling R25: one vector types the accents decomposed and must give the composed key.
    assert!(
        vectors
            .iter()
            .any(|v| v.username.contains('\u{301}') && v.password.contains('\u{308}')),
        "docs/accounts.md has no decomposed-accent vector"
    );
    assert!(
        vectors.len() >= 3,
        "docs/accounts.md has {} vectors",
        vectors.len()
    );
    for vector in vectors {
        let key = derive_account_key(
            &vector.username,
            &vector.password,
            &vector.clinic_id.parse()?,
        );
        assert_eq!(
            key.to_hex(),
            vector.account_key,
            "vector for {}",
            vector.username
        );
    }
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Against the `--mock` wiring (run now)

#[tokio::test]
async fn derivation_endpoint_gives_the_parameters_without_a_token() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/auth/derivation", None)?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(
        reply.body,
        json!({
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": 600_000,
            "key_bytes": 32,
            "clinic_id": "demo-clinic",
            "salt": "clinic:demo-clinic:<lowercase(NFC(username))>",
            "normalization": "NFC"
        })
    );
    Ok(())
}

#[tokio::test]
async fn mock_login_with_derived_key_works_and_wrong_key_fails_identically() -> TestResult {
    let app = MockApp::start()?;
    let good = call(
        &app.app,
        post_json("/auth/login", None, &login_body("nurse", "mock", None)?)?,
    )
    .await?;
    assert_eq!(good.status, StatusCode::OK, "{}", good.body);
    assert_eq!(good.body.get("role"), Some(&json!("nurse")));
    let token = text(&good.body, "/token")?;
    let me = call(&app.app, get("/me", Some(token))?).await?;
    assert_eq!(me.status, StatusCode::OK, "{}", me.body);
    let wrong_password = call(
        &app.app,
        post_json("/auth/login", None, &login_body("nurse", "wrong", None)?)?,
    )
    .await?;
    let unknown_user = call(
        &app.app,
        post_json("/auth/login", None, &login_body("ghost", "mock", None)?)?,
    )
    .await?;
    assert_eq!(wrong_password.status, StatusCode::UNAUTHORIZED);
    assert_eq!(wrong_password.status, unknown_user.status);
    assert_eq!(wrong_password.body, unknown_user.body);
    Ok(())
}

/// Mock compatibility until frontend task F9: the console's `{username, password}` still
/// logs in to `--mock` (the mock derives the key itself).
#[tokio::test]
async fn mock_accepts_a_user_name_and_password_until_f9() -> TestResult {
    let app = MockApp::start()?;
    for name in ["admin", "u-admin"] {
        let body = json!({ "username": name, "password": "mock" });
        let reply = call(&app.app, post_json("/auth/login", None, &body)?).await?;
        assert_eq!(reply.status, StatusCode::OK, "{name}: {}", reply.body);
        assert_eq!(reply.body.get("role"), Some(&json!("admin")));
        assert_eq!(reply.body.get("token"), Some(&json!("mock-admin")));
    }
    let wrong = json!({ "username": "admin", "password": "nope" });
    let reply = call(&app.app, post_json("/auth/login", None, &wrong)?).await?;
    assert_eq!(reply.status, StatusCode::UNAUTHORIZED);
    Ok(())
}

/// Outside `--mock` a user name and password body is 422 `key_derivation_required`, with a
/// message pointing to the derivation, and the password is not echoed.
#[tokio::test]
async fn live_mode_refuses_a_user_name_and_password_body() -> TestResult {
    let app = MockApp::start_in_mode(ServerMode::Live)?;
    let secret = "a-password-that-must-not-come-back";
    let body = json!({ "username": "admin", "password": secret });
    let reply = call(&app.app, post_json("/auth/login", None, &body)?).await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    assert_eq!(reply.error_code(), Some("key_derivation_required"));
    assert!(
        reply.error_message().contains("account key")
            && reply.error_message().contains("docs/accounts.md"),
        "{}",
        reply.error_message()
    );
    assert!(!reply.body.to_string().contains(secret));
    // The derived-key login keeps working in that state.
    let key = call(
        &app.app,
        post_json("/auth/login", None, &login_body("admin", "mock", None)?)?,
    )
    .await?;
    assert_eq!(key.status, StatusCode::OK, "{}", key.body);
    Ok(())
}

/// A malformed key is 422 and its value is never repeated.
#[tokio::test]
async fn bad_account_key_is_refused_without_echo() -> TestResult {
    let app = MockApp::start()?;
    let typed = "my-password-pasted-in-the-key-field";
    let reply = call(
        &app.app,
        post_json("/auth/login", None, &json!({ "account_key": typed }))?,
    )
    .await?;
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{}",
        reply.body
    );
    assert!(!reply.body.to_string().contains(typed), "{}", reply.body);
    assert!(reply.error_message().contains("64 lowercase hex"));
    Ok(())
}

/// The mock's enrolment: admin issues a code, a person enrols with a derived key and a
/// pseudonym, logs in; the code works once; a nurse cannot issue codes; a disabled account
/// cannot log in.
#[tokio::test]
async fn mock_enrolment_code_is_single_use_and_disable_locks_out() -> TestResult {
    let app = MockApp::start()?;
    let refused = call(
        &app.app,
        post_json("/admin/enrolment-codes", NURSE, &json!({ "role": "nurse" }))?,
    )
    .await?;
    assert_eq!(refused.status, StatusCode::FORBIDDEN);
    let issued = call(
        &app.app,
        post_json(
            "/admin/enrolment-codes",
            ADMIN,
            &json!({ "role": "nurse", "label": "Nurse 7" }),
        )?,
    )
    .await?;
    assert_eq!(issued.status, StatusCode::CREATED, "{}", issued.body);
    let code = text(&issued.body, "/code")?.to_owned();
    let key = derived_key("Nurse.Seven", "seven-is-a-good-number")?.to_hex();
    let enrol = json!({ "enrolment_code": code, "account_key": key, "display_label": "Nurse 7" });
    let enrolled = call(&app.app, post_json("/auth/enrol", None, &enrol)?).await?;
    assert_eq!(enrolled.status, StatusCode::CREATED, "{}", enrolled.body);
    assert_eq!(enrolled.body.get("role"), Some(&json!("nurse")));
    let tag: AccountTag = text(&enrolled.body, "/account_tag")?.parse()?;
    let again = call(&app.app, post_json("/auth/enrol", None, &enrol)?).await?;
    assert_eq!(again.status, StatusCode::FORBIDDEN, "{}", again.body);
    assert_eq!(again.error_code(), Some("enrolment_refused"));
    let login = json!({ "account_key": key });
    let ok = call(&app.app, post_json("/auth/login", None, &login)?).await?;
    assert_eq!(ok.status, StatusCode::OK, "{}", ok.body);
    let listed = call(&app.app, get("/admin/accounts", ADMIN)?).await?;
    assert_eq!(listed.status, StatusCode::OK, "{}", listed.body);
    assert!(listed.body.to_string().contains(tag.as_str()));
    assert!(!listed.body.to_string().contains("Nurse.Seven"));
    let disabled = call(
        &app.app,
        request(
            Method::DELETE,
            &format!("/admin/accounts/{tag}"),
            ADMIN,
            None,
        )?,
    )
    .await?;
    assert_eq!(disabled.status, StatusCode::NO_CONTENT, "{}", disabled.body);
    let locked = call(&app.app, post_json("/auth/login", None, &login)?).await?;
    assert_eq!(locked.status, StatusCode::UNAUTHORIZED, "{}", locked.body);
    Ok(())
}

/// The lead's rule: a nurse may pause r1, the admin is alerted with the command id, the admin
/// reverts it, r1 resumes; a second revert is refused.
#[tokio::test]
async fn nurse_pause_alerts_admin_and_admin_revert_resumes_r1() -> TestResult {
    let app = MockApp::start()?;
    let server = LiveServer::serve(app.app.clone()).await?;
    let mut admin_socket = support::app_socket_with_token(&server, "mock-admin").await?;
    admin_socket
        .next_of_type("snapshot", Duration::from_secs(2))
        .await?;
    let pause = call(
        &app.app,
        post_json("/robots/r1/command", NURSE, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(pause.status, StatusCode::OK, "{}", pause.body);
    let command_id = text(&pause.body, "/command_id")?.to_owned();
    let alert = loop {
        let event = admin_socket
            .next_of_type("alert", Duration::from_secs(2))
            .await?;
        if event.get("kind") == Some(&json!("staff_command")) {
            break event;
        }
    };
    assert_eq!(alert.get("level"), Some(&json!("warning")));
    assert_eq!(text(&alert, "/command/command_id")?, command_id);
    assert_eq!(text(&alert, "/command/robot_id")?, "r1");
    assert_eq!(text(&alert, "/command/command")?, "pause");
    assert_eq!(alert.pointer("/command/revertible"), Some(&json!(true)));
    assert!(text(&alert, "/message")?.contains(&command_id));

    let path = format!("/robots/r1/commands/{command_id}/revert");
    let by_nurse = call(&app.app, post_json(&path, NURSE, &json!({}))?).await?;
    assert_eq!(by_nurse.status, StatusCode::FORBIDDEN, "{}", by_nurse.body);
    let reverted = call(&app.app, request(Method::POST, &path, ADMIN, None)?).await?;
    assert_eq!(reverted.status, StatusCode::ACCEPTED, "{}", reverted.body);
    let by = text(&reverted.body, "/reverted_by_command_id")?;
    assert_ne!(by, command_id);
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    let r1 = robots
        .body
        .as_array()
        .and_then(|list| list.iter().find(|r| r.get("id") == Some(&json!("r1"))))
        .ok_or("r1 not listed")?;
    assert_ne!(r1.get("state"), Some(&json!("paused")), "{r1}");
    let twice = call(&app.app, request(Method::POST, &path, ADMIN, None)?).await?;
    assert_eq!(twice.status, StatusCode::CONFLICT, "{}", twice.body);
    assert_eq!(twice.error_code(), Some("already_reverted"));
    let audit = call(&app.app, get("/audit", ADMIN)?).await?;
    assert!(
        audit.body.to_string().contains("robot_command_reverted"),
        "{}",
        audit.body
    );
    Ok(())
}

/// An admin's own command raises no alert and is not revertible; an unknown command is 404.
#[tokio::test]
async fn admin_commands_are_not_revertible_and_unknown_ids_are_404() -> TestResult {
    let app = MockApp::start()?;
    let pause = call(
        &app.app,
        post_json("/robots/r2/command", ADMIN, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(pause.status, StatusCode::OK, "{}", pause.body);
    let id = text(&pause.body, "/command_id")?;
    let path = format!("/robots/r2/commands/{id}/revert");
    let reply = call(&app.app, request(Method::POST, &path, ADMIN, None)?).await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("not_revertible"));
    let other_robot = format!("/robots/r1/commands/{id}/revert");
    let reply = call(&app.app, request(Method::POST, &other_robot, ADMIN, None)?).await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND, "{}", reply.body);
    let estop = call(
        &app.app,
        post_json("/robots/r2/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert_eq!(estop.status, StatusCode::OK, "{}", estop.body);
    let id = text(&estop.body, "/command_id")?;
    let reply = call(
        &app.app,
        request(
            Method::POST,
            &format!("/robots/r2/commands/{id}/revert"),
            ADMIN,
            None,
        )?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("not_revertible"));
    Ok(())
}

/// A pseudonym with `#` (it would fake another account's tag) or a control character is
/// refused at enrolment, and the code stays usable.
#[tokio::test]
async fn mock_enrolment_refuses_hash_and_control_characters_in_pseudonyms() -> TestResult {
    let app = MockApp::start()?;
    let issued = call(
        &app.app,
        post_json("/admin/enrolment-codes", ADMIN, &json!({ "role": "nurse" }))?,
    )
    .await?;
    assert_eq!(issued.status, StatusCode::CREATED, "{}", issued.body);
    let code = text(&issued.body, "/code")?.to_owned();
    let key = derived_key("Nurse.Eight", "eight-is-a-good-number")?.to_hex();
    for label in ["Nurse 7 #3fa9c1", "Nurse\u{7}8", "Nurse\n8"] {
        let enrol = json!({ "enrolment_code": code, "account_key": key, "display_label": label });
        let reply = call(&app.app, post_json("/auth/enrol", None, &enrol)?).await?;
        assert_eq!(
            reply.status,
            StatusCode::UNPROCESSABLE_ENTITY,
            "{label:?}: {}",
            reply.body
        );
    }
    let enrol = json!({ "enrolment_code": code, "account_key": key, "display_label": "Nurse 8" });
    let reply = call(&app.app, post_json("/auth/enrol", None, &enrol)?).await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
    Ok(())
}

/// Ruling R24: `shutdown` is admin only; a nurse gets 403 naming `robot_shutdown`.
#[tokio::test]
async fn nurse_shutdown_is_forbidden() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(
        &app.app,
        post_json("/robots/r1/command", NURSE, &json!({ "name": "shutdown" }))?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("forbidden"));
    assert!(
        reply.error_message().contains("robot_shutdown"),
        "{}",
        reply.error_message()
    );
    Ok(())
}

/// Robot `id` as `GET /robots` shows it.
async fn robot_view(app: &MockApp, id: &str) -> Res<Value> {
    let robots = call(&app.app, get("/robots", ADMIN)?).await?;
    robots
        .body
        .as_array()
        .and_then(|list| list.iter().find(|r| r.get("id") == Some(&json!(id))))
        .cloned()
        .ok_or_else(|| format!("{id} not listed: {}", robots.body).into())
}

/// Waits until the in-process simulated robot `id` has reported once.
async fn wait_reported(app: &MockApp, id: &str) -> TestResult {
    for _ in 0..50 {
        if robot_view(app, id).await?.get("last_seen") != Some(&Value::Null) {
            return Ok(());
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    Err(format!("robot {id} never reported").into())
}

/// Ruling R24: after an admin's emergency stop a nurse's `resume` is 409 `estop_latched` and
/// the robot stays still; the admin's explicit `resume` re-arms it and it moves again.
#[tokio::test]
async fn nurse_resume_after_admin_estop_is_refused_and_only_admin_resume_moves_it() -> TestResult {
    let app = MockApp::start()?;
    wait_reported(&app, "r1").await?;
    let estop = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert_eq!(estop.status, StatusCode::OK, "{}", estop.body);
    tokio::time::sleep(Duration::from_millis(600)).await;
    let stopped = robot_view(&app, "r1").await?;
    let resume = call(
        &app.app,
        post_json("/robots/r1/command", NURSE, &json!({ "name": "resume" }))?,
    )
    .await?;
    assert_eq!(resume.status, StatusCode::CONFLICT, "{}", resume.body);
    assert_eq!(resume.error_code(), Some("estop_latched"));
    assert!(
        resume
            .error_message()
            .contains("Only an admin can re-arm a robot after an emergency stop."),
        "{}",
        resume.error_message()
    );
    tokio::time::sleep(Duration::from_millis(1500)).await;
    let still = robot_view(&app, "r1").await?;
    assert_eq!(still.get("state"), Some(&json!("estop")), "{still}");
    assert_eq!(still.get("pos"), stopped.get("pos"), "the robot moved");

    let rearm = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "resume" }))?,
    )
    .await?;
    assert_eq!(rearm.status, StatusCode::OK, "{}", rearm.body);
    let mut moved = false;
    for _ in 0..50 {
        tokio::time::sleep(Duration::from_millis(100)).await;
        let now = robot_view(&app, "r1").await?;
        if now.get("pos") != still.get("pos") && now.get("state") != Some(&json!("estop")) {
            moved = true;
            break;
        }
    }
    assert!(moved, "the admin's resume did not move r1");
    Ok(())
}

/// Ruling R24: an old nurse pause cannot be reverted after a later estop of the robot (the
/// revert would lift the stop), and a command followed by another is `superseded`.
#[tokio::test]
async fn reverts_are_refused_after_a_later_estop_or_a_later_command() -> TestResult {
    let app = MockApp::start()?;
    wait_reported(&app, "r1").await?;
    wait_reported(&app, "r2").await?;
    let pause = call(
        &app.app,
        post_json("/robots/r1/command", NURSE, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(pause.status, StatusCode::OK, "{}", pause.body);
    let paused = text(&pause.body, "/command_id")?.to_owned();
    let estop = call(
        &app.app,
        post_json("/robots/r1/command", ADMIN, &json!({ "name": "estop" }))?,
    )
    .await?;
    assert_eq!(estop.status, StatusCode::OK, "{}", estop.body);
    let path = format!("/robots/r1/commands/{paused}/revert");
    let reply = call(&app.app, request(Method::POST, &path, ADMIN, None)?).await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("estop_latched"));
    assert_eq!(
        robot_view(&app, "r1").await?.get("state"),
        Some(&json!("estop"))
    );

    let first = call(
        &app.app,
        post_json("/robots/r2/command", NURSE, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(first.status, StatusCode::OK, "{}", first.body);
    let first = text(&first.body, "/command_id")?.to_owned();
    let later = call(
        &app.app,
        post_json("/robots/r2/command", NURSE, &json!({ "name": "dock" }))?,
    )
    .await?;
    assert_eq!(later.status, StatusCode::OK, "{}", later.body);
    let path = format!("/robots/r2/commands/{first}/revert");
    let reply = call(&app.app, request(Method::POST, &path, ADMIN, None)?).await?;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.error_code(), Some("superseded"));
    Ok(())
}

/// Two reverts of one command at once: exactly one inverse is sent (one 202, one 409
/// `already_reverted`, one `robot_command_reverted` audit row).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_reverts_send_exactly_one_inverse() -> TestResult {
    let app = MockApp::start()?;
    wait_reported(&app, "r1").await?;
    let pause = call(
        &app.app,
        post_json("/robots/r1/command", NURSE, &json!({ "name": "pause" }))?,
    )
    .await?;
    assert_eq!(pause.status, StatusCode::OK, "{}", pause.body);
    let id = text(&pause.body, "/command_id")?.to_owned();
    let path = format!("/robots/r1/commands/{id}/revert");
    let one = tokio::spawn({
        let app = app.app.clone();
        let req = request(Method::POST, &path, ADMIN, None)?;
        async move { call(&app, req).await.map_err(|e| e.to_string()) }
    });
    let two = tokio::spawn({
        let app = app.app.clone();
        let req = request(Method::POST, &path, ADMIN, None)?;
        async move { call(&app, req).await.map_err(|e| e.to_string()) }
    });
    let one = one.await??;
    let two = two.await??;
    let mut statuses = vec![one.status, two.status];
    statuses.sort();
    assert_eq!(statuses, vec![StatusCode::ACCEPTED, StatusCode::CONFLICT]);
    let refused = if one.status == StatusCode::CONFLICT {
        &one
    } else {
        &two
    };
    assert_eq!(refused.error_code(), Some("already_reverted"));
    let audit = call(&app.app, get("/audit", ADMIN)?).await?;
    let reverted = audit
        .body
        .to_string()
        .matches("robot_command_reverted")
        .count();
    assert_eq!(reverted, 1, "{}", audit.body);
    Ok(())
}

// ---------------------------------------------------------------------------------------
// Against the real wiring (Task 8: accounts, pepper, login; Task 14: commands)

/// Enrols `username` / `password` as `label` with a code the admin issues; returns the tag.
async fn enrol(
    app: &RealApp,
    role: &str,
    username: &str,
    password: &str,
    label: &str,
) -> Res<AccountTag> {
    let admin = app.admin_token().await?;
    let issued = app
        .call(post_json(
            "/admin/enrolment-codes",
            Some(&admin),
            &json!({ "role": role, "label": label }),
        )?)
        .await?;
    if issued.status != StatusCode::CREATED {
        return Err(format!("code not issued: {}", issued.body).into());
    }
    let body = json!({
        "enrolment_code": text(&issued.body, "/code")?,
        "account_key": derived_key(username, password)?.to_hex(),
        "display_label": label,
    });
    let enrolled = app.call(post_json("/auth/enrol", None, &body)?).await?;
    if enrolled.status != StatusCode::CREATED {
        return Err(format!("not enrolled: {}", enrolled.body).into());
    }
    Ok(text(&enrolled.body, "/account_tag")?.parse()?)
}

#[tokio::test]
async fn login_with_derived_key_works_and_wrong_key_fails_identically() -> TestResult {
    let app = RealApp::start().await?;
    let tag = enrol(&app, "nurse", "Nurse.Seven", TEST_PASSWORD, "Nurse 7").await?;
    let good = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("Nurse.Seven", TEST_PASSWORD, None)?,
        )?)
        .await?;
    assert_eq!(good.status, StatusCode::OK, "{}", good.body);
    assert_eq!(
        good.body.get("operator"),
        Some(&json!(format!("Nurse 7 #{tag}")))
    );
    // The salt lowercases the user name: the same person typing capitals logs in.
    let caps = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("NURSE.SEVEN", TEST_PASSWORD, None)?,
        )?)
        .await?;
    assert_eq!(caps.status, StatusCode::OK, "{}", caps.body);
    let wrong = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("Nurse.Seven", "wrong", None)?,
        )?)
        .await?;
    let unknown = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body("Nobody", TEST_PASSWORD, None)?,
        )?)
        .await?;
    assert_eq!(wrong.status, StatusCode::UNAUTHORIZED);
    assert_eq!(wrong.body, unknown.body);
    let legacy = app
        .call(post_json(
            "/auth/login",
            None,
            &json!({ "username": "Nurse.Seven", "password": TEST_PASSWORD }),
        )?)
        .await?;
    assert_eq!(legacy.error_code(), Some("key_derivation_required"));
    Ok(())
}

#[tokio::test]
async fn database_dump_contains_no_account_key_and_no_username() -> TestResult {
    let app = RealApp::start().await?;
    let username = "Nurse.Seven";
    let password = "pässwörd-λ-seven";
    enrol(&app, "nurse", username, password, "Nurse 7").await?;
    let login = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body(username, password, None)?,
        )?)
        .await?;
    assert_eq!(login.status, StatusCode::OK, "{}", login.body);
    let dump = dump_database(&app).await?.to_lowercase();
    let key = derived_key(username, password)?.to_hex();
    for secret in [
        key.as_str(),
        &username.to_lowercase(),
        &password.to_lowercase(),
    ] {
        assert!(!dump.contains(secret), "the database contains {secret}");
    }
    assert!(dump.contains("nurse 7"), "the pseudonym is stored");
    Ok(())
}

#[tokio::test]
async fn enrolment_code_is_single_use_and_expires() -> TestResult {
    let app = RealApp::start().await?;
    let admin = app.admin_token().await?;
    let mut codes = Vec::new();
    for _ in 0..2 {
        let issued = app
            .call(post_json(
                "/admin/enrolment-codes",
                Some(&admin),
                &json!({ "role": "nurse" }),
            )?)
            .await?;
        assert_eq!(issued.status, StatusCode::CREATED, "{}", issued.body);
        codes.push(text(&issued.body, "/code")?.to_owned());
    }
    let body = |code: &str, user: &str| -> Res<Value> {
        Ok(json!({
            "enrolment_code": code,
            "account_key": derived_key(user, TEST_PASSWORD)?.to_hex(),
            "display_label": "Nurse 8",
        }))
    };
    let first = codes.first().ok_or("no code")?;
    let used = app
        .call(post_json("/auth/enrol", None, &body(first, "a")?)?)
        .await?;
    assert_eq!(used.status, StatusCode::CREATED, "{}", used.body);
    let reused = app
        .call(post_json("/auth/enrol", None, &body(first, "b")?)?)
        .await?;
    assert_eq!(reused.error_code(), Some("enrolment_refused"));
    app.clock
        .advance(Duration::from_hours(24) + Duration::from_secs(1));
    let second = codes.get(1).ok_or("no code")?;
    let expired = app
        .call(post_json("/auth/enrol", None, &body(second, "c")?)?)
        .await?;
    assert_eq!(expired.status, StatusCode::FORBIDDEN, "{}", expired.body);
    assert_eq!(
        expired.body, reused.body,
        "used and expired codes are told apart"
    );
    Ok(())
}

#[tokio::test]
async fn leaked_db_without_pepper_cannot_log_in() -> TestResult {
    let app = RealApp::start().await?;
    enrol(&app, "nurse", "Nurse.Seven", TEST_PASSWORD, "Nurse 7").await?;
    let body = login_body("Nurse.Seven", TEST_PASSWORD, None)?;
    let real = app.call(post_json("/auth/login", None, &body)?).await?;
    assert_eq!(real.status, StatusCode::OK, "{}", real.body);
    // The same database with another pepper: what a copy of the database alone gives.
    let thief = app
        .relaunch_with_pepper(Pepper::from_bytes([0x77; 32]))
        .await?;
    let stolen = thief.call(post_json("/auth/login", None, &body)?).await?;
    assert_eq!(stolen.status, StatusCode::UNAUTHORIZED, "{}", stolen.body);
    Ok(())
}

#[tokio::test]
async fn audit_shows_pseudonym_and_account_tag_only() -> TestResult {
    let app = RealApp::start().await?;
    let username = "Nurse.Seven";
    let tag = enrol(&app, "nurse", username, TEST_PASSWORD, "Nurse 7").await?;
    let login = app
        .call(post_json(
            "/auth/login",
            None,
            &login_body(username, TEST_PASSWORD, None)?,
        )?)
        .await?;
    let token = text(&login.body, "/token")?.to_owned();
    let created = app
        .call(post_json(
            "/tasks",
            Some(&token),
            &json!({ "kind": "go_to", "to_place": support::map::ROOM_101 }),
        )?)
        .await?;
    assert_eq!(created.status, StatusCode::CREATED, "{}", created.body);
    assert_eq!(
        created.body.get("requested_by"),
        Some(&json!(format!("Nurse 7 #{tag}")))
    );
    let admin = app.admin_token().await?;
    let audit = app.call(get("/audit", Some(&admin))?).await?;
    assert_eq!(audit.status, StatusCode::OK, "{}", audit.body);
    let rows = audit
        .body
        .get("items")
        .and_then(Value::as_array)
        .ok_or("no rows")?;
    let label = format!("Nurse 7 #{tag}");
    assert!(
        rows.iter()
            .any(|row| row.get("actor") == Some(&json!(label)))
    );
    let account = app.account_of(username)?;
    let text = audit.body.to_string().to_lowercase();
    assert!(
        !text.contains(&account.to_string()),
        "the full account id is shown"
    );
    assert!(!text.contains(&username.to_lowercase()));
    Ok(())
}

#[test]
fn owner_label_is_pseudonym_hash_tag() -> TestResult {
    let tag: AccountTag = "3fa9c1".parse()?;
    let label = domain::account_owner_label(&domain::OwnerLabel::new("Nurse 7")?, &tag)?;
    assert_eq!(label.as_str(), "Nurse 7 #3fa9c1");
    let long = domain::OwnerLabel::new(&"x".repeat(40))?;
    let cut = domain::account_owner_label(&long, &tag)?;
    assert_eq!(cut.as_str(), format!("{} #3fa9c1", "x".repeat(32)));
    Ok(())
}

#[tokio::test]
async fn disabled_account_cannot_log_in_and_its_tokens_stop_working() -> TestResult {
    let app = RealApp::start().await?;
    let tag = enrol(&app, "nurse", "Nurse.Seven", TEST_PASSWORD, "Nurse 7").await?;
    let body = login_body("Nurse.Seven", TEST_PASSWORD, None)?;
    let login = app.call(post_json("/auth/login", None, &body)?).await?;
    let token = text(&login.body, "/token")?.to_owned();
    let admin = app.admin_token().await?;
    let disabled = app
        .call(request(
            Method::DELETE,
            &format!("/admin/accounts/{tag}"),
            Some(&admin),
            None,
        )?)
        .await?;
    assert_eq!(disabled.status, StatusCode::NO_CONTENT, "{}", disabled.body);
    let again = app.call(post_json("/auth/login", None, &body)?).await?;
    assert_eq!(again.status, StatusCode::UNAUTHORIZED);
    let me = app.call(get("/me", Some(&token))?).await?;
    assert_eq!(me.status, StatusCode::UNAUTHORIZED);
    Ok(())
}

#[test]
fn pepper_file_is_created_once_and_reused() -> TestResult {
    let dir = support::temp_dir("pepper")?;
    let path = dir.join("keys").join("account.pepper");
    std::fs::create_dir_all(dir.join("keys"))?;
    let first = Pepper::load_or_create(&path)?;
    let second = Pepper::load_or_create(&path)?;
    let key = derived_key("a", "b")?;
    assert_eq!(
        security::account_id(&first, &key),
        security::account_id(&second, &key)
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644))?;
        let refused = Pepper::load_or_create(&path).err().ok_or("accepted")?;
        assert_eq!(refused.code(), "pepper_permissions");
    }
    Ok(())
}

#[tokio::test]
async fn nurse_command_raises_staff_command_alert_and_journals_its_id() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let _robot = app.connect_robot(&server, "robot-r1", 1.0, 1.0).await?;
    let mut admin_socket = app.app_socket(&server).await?;
    let nurse = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/robots/robot-r1/command",
            Some(&nurse),
            &json!({ "name": "pause" }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let id = text(&reply.body, "/command_id")?.to_owned();
    let alert = admin_socket
        .next_of_type("alert", Duration::from_secs(2))
        .await?;
    assert_eq!(alert.get("kind"), Some(&json!("staff_command")));
    assert_eq!(text(&alert, "/command/command_id")?, id);
    app.journal.seal_now(audit::SealReason::Interval).await?;
    let journaled = support::read_journal(&app.config.journal.dir)?
        .into_iter()
        .any(|record| matches!(record.body, audit::RecordBody::RobotCommandSent { command_id, .. } if command_id.to_string() == id));
    assert!(journaled, "no RobotCommandSent with the command id");
    Ok(())
}

#[tokio::test]
async fn admin_revert_sends_inverse_and_is_journaled() -> TestResult {
    let app = RealApp::start().await?;
    let server = app.serve().await?;
    let mut robot = app.connect_robot(&server, "robot-r1", 1.0, 1.0).await?;
    let nurse = app.nurse_token().await?;
    let admin = app.admin_token().await?;
    let reply = app
        .call(post_json(
            "/robots/robot-r1/command",
            Some(&nurse),
            &json!({ "name": "dock" }),
        )?)
        .await?;
    let id = text(&reply.body, "/command_id")?.to_owned();
    let reverted = app
        .call(request(
            Method::POST,
            &format!("/robots/robot-r1/commands/{id}/revert"),
            Some(&admin),
            None,
        )?)
        .await?;
    assert_eq!(reverted.status, StatusCode::ACCEPTED, "{}", reverted.body);
    let mut saw_resume = false;
    for _ in 0..4 {
        let message = robot
            .next_of_type("command", Duration::from_secs(2))
            .await?;
        if message.get("name") == Some(&json!("resume")) {
            saw_resume = true;
            break;
        }
    }
    assert!(saw_resume, "the robot did not receive resume");
    app.journal.seal_now(audit::SealReason::Interval).await?;
    let journaled = support::read_journal(&app.config.journal.dir)?
        .into_iter()
        .any(|record| {
            matches!(
                record.body,
                audit::RecordBody::RobotCommandReverted {
                    inverse: domain::CommandName::Resume,
                    ..
                }
            )
        });
    assert!(journaled, "no RobotCommandReverted");
    Ok(())
}

/// Every row of every table, as one text (`quote()` of each column).
async fn dump_database(app: &RealApp) -> Res<String> {
    let tables: Vec<String> = sqlx::query_scalar(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )
    .fetch_all(app.db.pool())
    .await?;
    let mut dump = String::new();
    for table in tables {
        let columns: Vec<String> = sqlx::query_scalar("SELECT name FROM pragma_table_info(?)")
            .bind(&table)
            .fetch_all(app.db.pool())
            .await?;
        if columns.is_empty() {
            continue;
        }
        let row = columns
            .iter()
            .map(|c| format!("quote(\"{c}\")"))
            .collect::<Vec<_>>()
            .join(" || '|' || ");
        // Audited: table and column names come from sqlite_master, not from input.
        let sql = sqlx::AssertSqlSafe(format!("SELECT {row} FROM \"{table}\""));
        let rows: Vec<String> = sqlx::query_scalar(sql).fetch_all(app.db.pool()).await?;
        dump.push_str(&table);
        dump.push('\n');
        dump.push_str(&rows.join("\n"));
        dump.push('\n');
    }
    Ok(dump)
}
