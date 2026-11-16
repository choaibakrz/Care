//! Task 11c: incidents on the 3D map, and the read-only mirror of the emergency service.
//!
//! The fake emergency service below serves a WebSocket status stream at `/status`. The alarm
//! message it sends, `{"type":"alarm","alarm_id","room","level"}`, is this suite's assumption
//! of the emergency service's format (implementation/emergency.md does not fix it yet);
//! Task 11c adjusts the fake if the real format differs.

mod support;

use std::collections::BTreeSet;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use audit::{Ed25519FileSigner, Journal, RecordBody};
use axum::Router;
use axum::extract::ws::{Message, WebSocketUpgrade};
use axum::extract::{Request, State};
use axum::http::StatusCode;
use axum::middleware::{self, Next};
use axum::response::Response;
use axum::routing::{any, get};
use clinic_server::dto::DeviceEventRequest;
use clinic_server::emergency_mirror::{EmergencyMirror, EmergencyMirrorConfig, LINK_SILENCE_LIMIT};
use clinic_server::services::IncidentService as _;
use clinic_server::services::incidents::{IncidentBoard, IncidentBoardDeps};
use domain::incident::{
    AlarmLevel, IncidentChange, IncidentCode, IncidentSeverity, RobotFaultCode,
};
use domain::{Clock, OwnerLabel, RobotStatus, SubjectRef, SystemClock};
use locations::{Attribution, LivePositions, Point2, PositionFix, PositionTtl, RobotInfo};
use realtime::{Hub, Incident, IncidentColour};
use serde_json::{Value, json};
use support::{LiveServer, RealApp, Res, TestResult, api, get as get_req, map, post_json};
use utoipa::PartialSchema as _;

/// An incident board on the fixture map, with its own journal and hub.
struct BoardWorld {
    board: Arc<IncidentBoard>,
    live: Arc<LivePositions>,
    hub: Arc<Hub>,
    journal: Journal,
    clock: Arc<dyn Clock>,
}

impl BoardWorld {
    fn start(clock: Arc<dyn Clock>) -> Res<BoardWorld> {
        let dir = support::temp_dir("incidents")?;
        let config = support::journal_config(&dir);
        support::create_journal_dirs(&config)?;
        let signer = Ed25519FileSigner::load(&config.key_path)?;
        let (journal, _writer) = Journal::start(config, clock.clone(), Box::new(signer))?;
        let live = Arc::new(LivePositions::new(
            Arc::new(map::small_map()?),
            clock.clone(),
            PositionTtl::default(),
        ));
        let hub = Arc::new(Hub::with_clock(clock.clone()));
        let board = Arc::new(IncidentBoard::new(IncidentBoardDeps {
            journal: journal.clone(),
            hub: hub.clone(),
            attribution: Attribution::new(live.clone()),
            clock: clock.clone(),
        }));
        Ok(BoardWorld {
            board,
            live,
            hub,
            journal,
            clock,
        })
    }

    fn robot_in_room_102(&self) -> Res<SubjectRef> {
        let robot = "robot-r2".parse()?;
        self.live.update_robot(
            PositionFix {
                subject: SubjectRef::Robot(robot),
                floor: 1,
                point: Point2::new(15.0, 16.0)?,
                heading_rad: None,
                at: self.clock.now(),
            },
            RobotInfo {
                name: "R2".to_owned(),
                status: RobotStatus::Fault,
                task: None,
                battery_pct: 60.0,
                mic_open: false,
            },
        )?;
        Ok(SubjectRef::Robot("robot-r2".parse()?))
    }

    async fn open(&self) -> Res<Vec<Incident>> {
        api(self.board.list_incidents(true).await)
    }
}

#[tokio::test]
async fn robot_fault_opens_incident_on_the_robots_current_room() -> TestResult {
    let world = BoardWorld::start(support::fake_clock()?)?;
    let robot = world.robot_in_room_102()?;
    let code = IncidentCode::RobotFault {
        fault: RobotFaultCode::Motor,
    };
    let id = world
        .board
        .raise(code, Some(robot.clone()), world.clock.now())
        .await;
    let open = world.open().await?;
    let incident = open
        .iter()
        .find(|i| i.id == id)
        .ok_or("incident not listed")?;
    assert_eq!(incident.code, code);
    assert_eq!(incident.subject, Some(robot));
    assert_eq!(
        incident.place.as_ref().map(domain::PlaceId::as_str),
        Some(map::ROOM_102)
    );
    assert_eq!(incident.floor, Some(1));
    Ok(())
}

#[tokio::test]
async fn repeated_fault_merges_and_counts() -> TestResult {
    let world = BoardWorld::start(support::fake_clock()?)?;
    let robot = world.robot_in_room_102()?;
    let code = IncidentCode::RobotFault {
        fault: RobotFaultCode::Battery,
    };
    let first = world
        .board
        .raise(code, Some(robot.clone()), world.clock.now())
        .await;
    let repeats_after_first = world
        .open()
        .await?
        .into_iter()
        .find(|i| i.id == first)
        .ok_or("incident not listed")?
        .repeats;
    let second = world
        .board
        .raise(code, Some(robot), world.clock.now())
        .await;
    assert_eq!(first, second, "the same open fault was not merged");
    let open = world.open().await?;
    assert_eq!(open.len(), 1);
    let incident = open.first().ok_or("no incident")?;
    assert_eq!(incident.repeats, repeats_after_first + 1);
    Ok(())
}

/// Alarm levels of the same subject merge into one incident whose severity follows the
/// highest level seen: it rises with a higher level and does not fall with a lower one.
#[tokio::test]
async fn severity_rises_but_never_silently_falls() -> TestResult {
    let world = BoardWorld::start(support::fake_clock()?)?;
    world.live.set_tablet(
        "tab-12".parse()?,
        OwnerLabel::new("Room 102 tablet")?,
        &map::ROOM_102.parse()?,
    )?;
    let tablet = SubjectRef::Tablet("tab-12".parse()?);
    let mut severities = Vec::new();
    for level in [AlarmLevel::Urgent, AlarmLevel::Call, AlarmLevel::Emergency] {
        world
            .board
            .raise(
                IncidentCode::EmergencyAlarm { level },
                Some(tablet.clone()),
                world.clock.now(),
            )
            .await;
        let open = world.open().await?;
        assert_eq!(open.len(), 1, "alarms of one subject were not merged");
        severities.push(open.first().ok_or("no incident")?.severity);
    }
    for pair in severities.windows(2) {
        if let [before, after] = pair {
            assert!(after >= before, "severity fell: {severities:?}");
        }
    }
    assert_eq!(severities.last(), Some(&IncidentSeverity::Critical));
    Ok(())
}

#[tokio::test]
async fn tablet_event_with_unknown_code_is_422() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let reply = app
        .call(post_json(
            "/devices/me/events",
            Some(&token),
            &json!({ "code": "exploded" }),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(reply.error_code().is_some());
    Ok(())
}

/// No free text from a device: an extra field is rejected, never dropped silently.
#[test]
fn tablet_event_body_with_extra_text_field_is_rejected() {
    let with_text = json!({ "code": "crash", "text": "patient in 102 fell" });
    assert!(serde_json::from_value::<DeviceEventRequest>(with_text).is_err());
    let plain = json!({ "code": "crash" });
    assert!(serde_json::from_value::<DeviceEventRequest>(plain).is_ok());
}

/// Raises a `TabletAppError` incident through the API and returns its id.
async fn reported_incident(app: &RealApp, token: &str) -> Res<u64> {
    let reply = app
        .call(post_json(
            "/devices/me/events",
            Some(token),
            &json!({ "code": "crash" }),
        )?)
        .await?;
    assert!(
        reply.status.is_success(),
        "{}: {}",
        reply.status,
        reply.body
    );
    let list = app
        .call(get_req("/incidents?open=true", Some(token))?)
        .await?;
    let id = list
        .body
        .as_array()
        .and_then(|a| a.first())
        .and_then(|i| i.get("id"))
        .and_then(Value::as_u64)
        .ok_or("no incident listed")?;
    Ok(id)
}

#[tokio::test]
async fn ack_records_owner_label_and_journals() -> TestResult {
    let app = RealApp::start().await?;
    let token = app.nurse_token().await?;
    let id = reported_incident(&app, &token).await?;
    let reply = app
        .call(post_json(
            &format!("/incidents/{id}/ack"),
            Some(&token),
            &json!({}),
        )?)
        .await?;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    // Task A7: an account's owner label is "<pseudonym> #<tag>".
    let tag = app.account_of("u-nurse")?.tag();
    assert_eq!(
        reply.body.get("acknowledged_by"),
        Some(&json!(format!("Test nurse #{tag}")))
    );
    app.journal.seal_now(audit::SealReason::Interval).await?;
    let acknowledged = support::read_journal(&app.config.journal.dir)?
        .into_iter()
        .any(|r| {
            matches!(
                r.body,
                RecordBody::IncidentChanged {
                    change: IncidentChange::Acknowledged,
                    ..
                }
            )
        });
    assert!(acknowledged, "the acknowledgement was not journaled");
    Ok(())
}

#[tokio::test]
async fn nurse_cannot_close_admin_can() -> TestResult {
    let app = RealApp::start().await?;
    let nurse = app.nurse_token().await?;
    let admin = app.admin_token().await?;
    let id = reported_incident(&app, &nurse).await?;
    let path = format!("/incidents/{id}/close");
    let refused = app
        .call(post_json(&path, Some(&nurse), &json!({}))?)
        .await?;
    assert_eq!(refused.status, StatusCode::FORBIDDEN);
    assert_eq!(refused.error_code(), Some("forbidden"));
    let closed = app
        .call(post_json(&path, Some(&admin), &json!({}))?)
        .await?;
    assert_eq!(closed.status, StatusCode::OK, "{}", closed.body);
    assert!(closed.body.get("closed_at").is_some_and(|v| !v.is_null()));
    Ok(())
}

/// A fake emergency service: records every request (method and path) and serves `/status`
/// as a WebSocket that sends `messages` and then stays silent.
#[derive(Clone, Default)]
struct FakeEmergency {
    requests: Arc<Mutex<Vec<(String, String)>>>,
    messages: Arc<Vec<String>>,
}

impl FakeEmergency {
    fn requests(&self) -> Vec<(String, String)> {
        self.requests.lock().map(|r| r.clone()).unwrap_or_default()
    }
}

async fn record(State(fake): State<FakeEmergency>, request: Request, next: Next) -> Response {
    if let Ok(mut requests) = fake.requests.lock() {
        requests.push((
            request.method().to_string(),
            request.uri().path().to_owned(),
        ));
    }
    next.run(request).await
}

async fn status_stream(State(fake): State<FakeEmergency>, upgrade: WebSocketUpgrade) -> Response {
    upgrade.on_upgrade(move |mut socket| async move {
        for message in fake.messages.iter() {
            if socket
                .send(Message::Text(message.clone().into()))
                .await
                .is_err()
            {
                return;
            }
        }
        tokio::time::sleep(Duration::from_mins(1)).await;
    })
}

async fn fake_emergency(messages: Vec<String>) -> Res<(FakeEmergency, LiveServer)> {
    let fake = FakeEmergency {
        requests: Arc::default(),
        messages: Arc::new(messages),
    };
    let app = Router::new()
        .route("/status", get(status_stream))
        .fallback(any(|| async { StatusCode::NOT_FOUND }))
        .layer(middleware::from_fn_with_state(fake.clone(), record))
        .with_state(fake.clone());
    let server = LiveServer::serve(app).await?;
    Ok((fake, server))
}

fn alarm(room: &str, level: &str) -> String {
    json!({ "type": "alarm", "alarm_id": "btn-102-7", "room": room, "level": level }).to_string()
}

async fn wait_for_incident(
    board: &BoardWorld,
    within: Duration,
    wanted: impl Fn(&Incident) -> bool,
) -> Res<Incident> {
    let deadline = tokio::time::Instant::now() + within;
    loop {
        if let Some(found) = board.open().await?.into_iter().find(|i| wanted(i)) {
            return Ok(found);
        }
        if tokio::time::Instant::now() >= deadline {
            return Err("the expected incident did not appear in time".into());
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}

#[tokio::test]
async fn mirrored_alarm_paints_room_red() -> TestResult {
    let world = BoardWorld::start(Arc::new(SystemClock))?;
    let (_fake, server) = fake_emergency(vec![alarm(map::ROOM_102, "emergency")]).await?;
    let mut events = world.hub.subscribe_apps();
    let mirror = Arc::new(EmergencyMirror::new(
        EmergencyMirrorConfig {
            status_url: server.ws_url("/status"),
            silence: LINK_SILENCE_LIMIT,
        },
        world.board.clone(),
        world.clock.clone(),
    ));
    let task = mirror.spawn();
    let incident = wait_for_incident(&world, Duration::from_secs(3), |i| {
        matches!(i.code, IncidentCode::EmergencyAlarm { .. })
    })
    .await?;
    task.abort();
    assert_eq!(
        incident.place.as_ref().map(domain::PlaceId::as_str),
        Some(map::ROOM_102)
    );
    assert_eq!(incident.severity, IncidentSeverity::Critical);
    assert_eq!(incident.severity.colour(), IncidentColour::Red);
    let mut painted_red = false;
    while let Ok(event) = events.try_recv() {
        let value = serde_json::to_value(&event)?;
        if value.get("type") == Some(&json!("incident.updated"))
            && value.get("colour") == Some(&json!("red"))
        {
            painted_red = true;
        }
    }
    assert!(painted_red, "no red incident.updated event was published");
    Ok(())
}

#[tokio::test]
async fn silent_emergency_stream_raises_link_down_within_10s() -> TestResult {
    assert_eq!(LINK_SILENCE_LIMIT, Duration::from_secs(10));
    let world = BoardWorld::start(Arc::new(SystemClock))?;
    let (_fake, server) = fake_emergency(Vec::new()).await?;
    let mirror = Arc::new(EmergencyMirror::new(
        EmergencyMirrorConfig {
            status_url: server.ws_url("/status"),
            silence: Duration::from_millis(300),
        },
        world.board.clone(),
        world.clock.clone(),
    ));
    let task = mirror.spawn();
    let incident = wait_for_incident(&world, Duration::from_secs(3), |i| {
        i.code == IncidentCode::EmergencyLinkDown
    })
    .await;
    task.abort();
    incident?;
    Ok(())
}

/// Ruling R2: the mirror only reads the status stream. After it has mirrored an alarm and
/// the incident was acknowledged on this server, the fake emergency service has received
/// nothing but the stream request.
#[tokio::test]
async fn mirror_has_no_way_to_ack_or_create_alarms() -> TestResult {
    let world = BoardWorld::start(Arc::new(SystemClock))?;
    let (fake, server) = fake_emergency(vec![alarm(map::ROOM_102, "urgent")]).await?;
    let mirror = Arc::new(EmergencyMirror::new(
        EmergencyMirrorConfig {
            status_url: server.ws_url("/status"),
            silence: LINK_SILENCE_LIMIT,
        },
        world.board.clone(),
        world.clock.clone(),
    ));
    let task = mirror.spawn();
    let incident = wait_for_incident(&world, Duration::from_secs(3), |i| {
        matches!(i.code, IncidentCode::EmergencyAlarm { .. })
    })
    .await?;
    api(world
        .board
        .ack(incident.id, OwnerLabel::new("Ward 2 nurse")?)
        .await)?;
    tokio::time::sleep(Duration::from_millis(300)).await;
    task.abort();
    let requests = fake.requests();
    assert!(!requests.is_empty(), "the mirror never connected");
    for (method, path) in &requests {
        assert_eq!((method.as_str(), path.as_str()), ("GET", "/status"));
    }
    drop(world.journal);
    Ok(())
}

#[test]
fn incident_json_contains_no_personal_fields() -> TestResult {
    let schema = serde_json::to_value(Incident::schema())?;
    let keys: BTreeSet<String> = schema
        .get("properties")
        .and_then(Value::as_object)
        .ok_or("Incident has no properties")?
        .keys()
        .cloned()
        .collect();
    let expected: BTreeSet<String> = [
        "id",
        "code",
        "severity",
        "subject",
        "place",
        "floor",
        "opened_at",
        "last_seen_at",
        "repeats",
        "acknowledged_by",
        "closed_at",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    assert_eq!(keys, expected);
    for personal in [
        "name", "user", "user_id", "patient", "text", "message", "note",
    ] {
        assert!(!keys.contains(personal), "personal field '{personal}'");
    }
    Ok(())
}
