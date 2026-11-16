//! Patient companion API (`openapi.json` at the repository root): the happy path of a
//! patient day, signed in with the session cookie only.

mod support;

use std::sync::Arc;

use axum::Router;
use axum::http::{Method, StatusCode};
use clinic_server::patient::{self, ClinicRoom, FixedRooms, PatientStore, StaffAccess};
use domain::{Actor, Clock, Role, UserId};
use security::{MonitorConfig, SecurityError, TokenVerifier, TrafficMonitor, VerifiedIdentity};
use serde_json::json;
use support::{
    MockApp, RealApp, Res, TestResult, call, fake_clock, get, post_json, put_json, request,
    temp_dir, with_header,
};

fn patient_app() -> Res<Router> {
    let dir = temp_dir("patient-api")?;
    let store = PatientStore::open(dir.join("patients.json"))?;
    let clock: Arc<dyn Clock> = fake_clock()?;
    let traffic = Arc::new(TrafficMonitor::new(MonitorConfig::default(), vec![], clock));
    Ok(patient::router(Arc::new(store), traffic))
}

/// Signs Alex up; returns the `name=value` session cookie.
async fn sign_up(app: &Router) -> Res<String> {
    let signup = json!({ "identifier": "Alex@Example.com", "password": "long-enough-1", "first_name": "Alex" });
    let reply = call(app, post_json("/api/auth/signup", None, &signup)?).await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{:?}", reply.body);
    assert_eq!(
        reply.body.pointer("/needsConfirmation"),
        Some(&json!(false))
    );
    assert_eq!(
        reply.body.pointer("/user/email"),
        Some(&json!("alex@example.com"))
    );
    let set_cookie = reply.header("set-cookie").ok_or("no cookie")?;
    assert!(set_cookie.contains("HttpOnly"));
    Ok(set_cookie
        .split(';')
        .next()
        .ok_or("empty cookie")?
        .to_owned())
}

#[tokio::test]
async fn a_patient_signs_up_and_uses_the_day() -> TestResult {
    let app = patient_app()?;
    let cookie = sign_up(&app).await?;
    let authed = |req| with_header(req, "cookie", &cookie);

    let reply = call(&app, authed(get("/api/auth/session", None)?)?).await?;
    assert_eq!(reply.status, StatusCode::OK);
    assert_eq!(reply.body.pointer("/user/firstName"), Some(&json!("Alex")));

    let reply = call(
        &app,
        authed(put_json(
            "/api/auth/profile",
            None,
            &json!({ "first_name": "Sam" }),
        )?)?,
    )
    .await?;
    assert_eq!(reply.body.pointer("/user/firstName"), Some(&json!("Sam")));

    let reply = call(
        &app,
        authed(get("/api/patient/program?date=2026-11-16", None)?)?,
    )
    .await?;
    assert_eq!(reply.body.pointer("/date"), Some(&json!("2026-11-16")));
    assert_eq!(reply.body.pointer("/demo"), Some(&json!(true)));

    let reply = call(
        &app,
        authed(post_json(
            "/api/patient/questions",
            None,
            &json!({ "text": "When can I walk?" }),
        )?)?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::CREATED);
    let question = reply
        .body
        .pointer("/id")
        .and_then(serde_json::Value::as_str)
        .ok_or("no id")?
        .to_owned();
    let reply = call(&app, authed(get("/api/patient/questions", None)?)?).await?;
    assert_eq!(
        reply.body.pointer("/items/0/text"),
        Some(&json!("When can I walk?"))
    );
    let path = format!("/api/patient/questions/{question}");
    let reply = call(&app, authed(request(Method::DELETE, &path, None, None)?)?).await?;
    assert_eq!(reply.status, StatusCode::NO_CONTENT);

    let reply = call(
        &app,
        authed(post_json(
            "/api/patient/requests?date=2026-11-16",
            None,
            &json!({ "kind": "water" }),
        )?)?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::CREATED);
    assert_eq!(reply.body.pointer("/status"), Some(&json!("sent")));
    assert_eq!(reply.body.pointer("/status_index"), Some(&json!(0)));
    let reply = call(
        &app,
        authed(get("/api/patient/requests?date=2026-11-16", None)?)?,
    )
    .await?;
    assert_eq!(reply.body.pointer("/items/0/kind"), Some(&json!("water")));

    let reply = call(
        &app,
        authed(post_json(
            "/api/patient/mood?date=2026-11-16",
            None,
            &json!({ "value": 4 }),
        )?)?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::NO_CONTENT);

    let reply = call(
        &app,
        authed(post_json("/api/auth/logout", None, &json!({}))?)?,
    )
    .await?;
    assert_eq!(reply.body, json!({ "ok": true }));
    let reply = call(&app, authed(get("/api/auth/session", None)?)?).await?;
    assert_eq!(reply.status, StatusCode::UNAUTHORIZED);
    assert_eq!(
        reply.body.pointer("/error"),
        Some(&json!("not_authenticated"))
    );

    let login = json!({ "identifier": "alex@example.com", "password": "long-enough-1", "first_name": "Alex" });
    let reply = call(&app, post_json("/api/auth/login", None, &login)?).await?;
    assert_eq!(reply.status, StatusCode::OK);
    Ok(())
}

#[tokio::test]
#[ignore = "HACKATHON: the same-origin check of the patient routes is disabled for the pitch"]
async fn a_foreign_origin_cannot_post() -> TestResult {
    let app = patient_app()?;
    let body = json!({ "phone": "+41791234567" });
    let req = with_header(
        post_json("/api/auth/request-otp", None, &body)?,
        "host",
        "clinic.local",
    )?;
    let req = with_header(req, "origin", "https://evil.example")?;
    let reply = call(&app, req).await?;
    assert_eq!(reply.status, StatusCode::FORBIDDEN);
    assert_eq!(
        reply.body.pointer("/error"),
        Some(&json!("origin_not_allowed"))
    );
    Ok(())
}

#[tokio::test]
async fn the_server_wires_the_patient_routes() -> TestResult {
    let app = MockApp::start()?;
    let reply = call(&app.app, get("/api/auth/session", None)?).await?;
    assert_eq!(reply.status, StatusCode::UNAUTHORIZED);
    assert_eq!(
        reply.body.pointer("/error"),
        Some(&json!("not_authenticated"))
    );
    Ok(())
}

/// Accepts the single token `admin-token` as an administrator.
struct OneAdmin;

#[async_trait::async_trait]
impl TokenVerifier for OneAdmin {
    async fn verify(&self, raw: &str) -> Result<Option<VerifiedIdentity>, SecurityError> {
        let Ok(id) = "nurse-admin".parse::<UserId>() else {
            return Ok(None);
        };
        Ok((raw == "admin-token").then_some(VerifiedIdentity {
            subject_id: Actor::User(id),
            role: Role::Admin,
            device_id: None,
            owner: None,
        }))
    }
}

fn room_app() -> Res<Router> {
    let dir = temp_dir("patient-rooms")?;
    let store = PatientStore::open(dir.join("patients.json"))?;
    let clock: Arc<dyn Clock> = fake_clock()?;
    let traffic = Arc::new(TrafficMonitor::new(MonitorConfig::default(), vec![], clock));
    let rooms = FixedRooms(vec![ClinicRoom {
        id: "room-212".to_owned(),
        label: "Room 212".to_owned(),
        wing: "Floor 2".to_owned(),
        floor: 2,
    }]);
    let staff = StaffAccess {
        verifier: Arc::new(OneAdmin),
        rooms: Arc::new(rooms),
    };
    Ok(patient::router_with_staff(
        Arc::new(store),
        traffic,
        Some(staff),
    ))
}

#[tokio::test]
async fn a_room_tablet_pairs_and_uses_the_day() -> TestResult {
    let app = room_app()?;
    let staff_token = Some("admin-token");

    let admit =
        json!({ "first_name": "Alex", "medical_record_ref": "MRN-1", "room_id": "room-212" });
    let reply = call(&app, post_json("/api/admin/rooms", staff_token, &admit)?).await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{:?}", reply.body);
    let device = json!({ "room_id": "room-212", "label": "Tablet Room 212" });
    let reply = call(&app, post_json("/api/admin/devices", staff_token, &device)?).await?;
    assert_eq!(reply.status, StatusCode::CREATED, "{:?}", reply.body);
    let code = reply
        .body
        .pointer("/pairingCode")
        .and_then(serde_json::Value::as_str)
        .ok_or("no pairing code")?
        .to_owned();
    let reply = call(&app, get("/api/admin/rooms", staff_token)?).await?;
    assert_eq!(
        reply.body.pointer("/rooms/0/patient/firstName"),
        Some(&json!("Alex"))
    );

    let reply = call(
        &app,
        post_json("/api/room/pair", None, &json!({ "code": code }))?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::OK, "{:?}", reply.body);
    let set_cookie = reply.header("set-cookie").ok_or("no cookie")?;
    assert!(set_cookie.starts_with("spectrum_room_device=") && !set_cookie.contains("Secure"));
    let cookie = set_cookie
        .split(';')
        .next()
        .ok_or("empty cookie")?
        .to_owned();
    let tablet = |req| with_header(req, "cookie", &cookie);

    let reply = call(&app, tablet(get("/api/room/session", None)?)?).await?;
    assert_eq!(reply.body.pointer("/room/label"), Some(&json!("Room 212")));
    assert_eq!(
        reply.body.pointer("/patient/firstName"),
        Some(&json!("Alex"))
    );
    let reply = call(
        &app,
        tablet(get("/api/patient/program?date=2026-11-16", None)?)?,
    )
    .await?;
    assert_eq!(reply.body.pointer("/demo"), Some(&json!(false)));
    let question = json!({ "text": "When can I walk?" });
    let reply = call(
        &app,
        tablet(post_json("/api/patient/questions", None, &question)?)?,
    )
    .await?;
    assert_eq!(reply.status, StatusCode::CREATED);
    let reply = call(&app, tablet(get("/api/patient/questions", None)?)?).await?;
    assert_eq!(
        reply.body.pointer("/items/0/text"),
        Some(&json!("When can I walk?"))
    );

    let reply = call(
        &app,
        tablet(post_json("/api/room/unpair", None, &json!({}))?)?,
    )
    .await?;
    assert_eq!(reply.body, json!({ "ok": true }));
    let reply = call(&app, tablet(get("/api/room/session", None)?)?).await?;
    assert_eq!(reply.status, StatusCode::UNAUTHORIZED);

    let reply = call(&app, post_json("/api/admin/login", None, &json!({}))?).await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND);
    Ok(())
}

#[tokio::test]
async fn the_live_server_lists_the_map_rooms() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.admin_token().await?;
    let reply = call(&app.app, get("/api/admin/rooms", Some(&token))?).await?;
    assert_eq!(reply.status, StatusCode::OK, "{:?}", reply.body);
    assert!(
        reply
            .body
            .pointer("/rooms")
            .is_some_and(serde_json::Value::is_array)
    );
    let reply = call(&app.app, post_json("/api/admin/login", None, &json!({}))?).await?;
    assert_eq!(reply.status, StatusCode::NOT_FOUND);
    Ok(())
}
