//! Room tablets and the care team's room panel, a port of the Node gateway's `api/_room.js`,
//! `api/room/*` and `api/admin/{rooms,devices,discharge}.js` onto the JSON store.
//!
//! - `/api/room/pair|session|unpair`: a pairing code becomes the `HttpOnly` room-device
//!   cookie ([`ROOM_DEVICE_COOKIE`]); `/api/patient/*` then works for the patient of that room.
//! - `/api/admin/rooms|devices|discharge`: the rooms of the active clinic map, admissions,
//!   tablet pairing codes and discharges. They take the staff bearer token of this server
//!   (admin role). CORS (the console runs on its own origin) is the layer `lib.rs` puts
//!   around the whole patient router.
//! - `/api/admin/login` is deliberately 404: the console then signs in with `/auth/login`.

use std::sync::Arc;

use async_trait::async_trait;
use axum::body::Bytes;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::{any, get, post};
use axum::{Json, Router};
use chrono::{DateTime, SecondsFormat, Utc};
use domain::Role;
use locations::plan::RoomKind;
use security::{TokenVerifier, VerifiedIdentity};
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

use super::handlers::{now_ms, parse, random_hex};
use super::store::{
    PatientStore, RoomAssignmentRecord, RoomDeviceRecord, RoomPatientRecord, StoreData, StoreError,
};
use super::{PatientError, ROOM_DEVICE_COOKIE, cookie_value};
use crate::services::MapService;

/// A tablet session lasts 30 days.
const ROOM_SESSION_SECONDS: i64 = 30 * 24 * 3600;
/// A pairing code lasts 15 minutes.
const PAIRING_MILLIS: i64 = 15 * 60 * 1000;
/// A tablet seen within this delay is online.
const ONLINE_MILLIS: i64 = 120_000;
/// `last_seen_at` is written at most this often.
const HEARTBEAT_MILLIS: i64 = 30_000;
const MAX_DEVICE_LABEL_CHARS: usize = 60;

const NOT_PAIRED: PatientError = PatientError::with_status(
    StatusCode::UNAUTHORIZED,
    "room_device_not_paired",
    "This tablet is not paired with a room.",
);
const SESSION_EXPIRED: PatientError = PatientError::with_status(
    StatusCode::UNAUTHORIZED,
    "room_device_session_expired",
    "This tablet needs to be paired again.",
);
const BAD_CODE_FORMAT: PatientError = PatientError::unprocessable(
    "invalid_pairing_code",
    "Enter the pairing code shown by the care team.",
);
const ADMIN_REQUIRED: PatientError = PatientError::with_status(
    StatusCode::FORBIDDEN,
    "admin_required",
    "An administrator session is required.",
);

// ---------------------------------------------------------------- room directory

/// A room of the clinic, as the room panel lists it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClinicRoom {
    /// Room id (the plan's room id).
    pub id: String,
    /// Display name.
    pub label: String,
    /// The floor's name (the Node gateway's `wing`).
    pub wing: String,
    /// Floor level.
    pub floor: i32,
}

/// Where the patient rooms come from.
#[async_trait]
pub trait RoomDirectory: Send + Sync {
    /// The patient rooms, sorted by floor then label.
    ///
    /// # Errors
    /// A text for the log when the rooms cannot be read.
    async fn rooms(&self) -> Result<Vec<ClinicRoom>, String>;
}

/// A fixed room list (tests, or a server without a map).
#[derive(Debug, Clone, Default)]
pub struct FixedRooms(pub Vec<ClinicRoom>);

#[async_trait]
impl RoomDirectory for FixedRooms {
    async fn rooms(&self) -> Result<Vec<ClinicRoom>, String> {
        Ok(self.0.clone())
    }
}

/// The rooms of kind `room` of the active clinic map.
pub struct MapRooms(pub Arc<dyn MapService>);

#[async_trait]
impl RoomDirectory for MapRooms {
    async fn rooms(&self) -> Result<Vec<ClinicRoom>, String> {
        let (view, _) = self.0.view().await.map_err(|error| format!("{error:?}"))?;
        let mut rooms: Vec<ClinicRoom> = view
            .rooms
            .iter()
            .filter(|room| room.kind == RoomKind::Room)
            .map(|room| ClinicRoom {
                id: room.id.as_str().to_owned(),
                label: room.label.clone(),
                wing: view
                    .floors
                    .iter()
                    .find(|floor| floor.id == room.floor)
                    .map_or_else(|| format!("Floor {}", room.floor), |f| f.label.clone()),
                floor: room.floor,
            })
            .collect();
        rooms.sort_by(|a, b| a.floor.cmp(&b.floor).then_with(|| a.label.cmp(&b.label)));
        Ok(rooms)
    }
}

/// What the `/api/admin/*` room routes need from the staff side.
pub struct StaffAccess {
    /// Checks the staff bearer token (the admin role is required).
    pub verifier: Arc<dyn TokenVerifier>,
    /// The rooms.
    pub rooms: Arc<dyn RoomDirectory>,
}

// ---------------------------------------------------------------- room tablet

/// A paired tablet and the patient of its room.
pub(crate) struct RoomSession {
    device: RoomDeviceRecord,
    pub patient: Option<RoomPatientRecord>,
}

/// The `Set-Cookie` value of the room-device cookie. Never `Secure` over plain http, so a
/// phone on the LAN keeps it.
pub(crate) fn room_cookie(value: &str, max_age: i64, secure: bool) -> String {
    let secure = if secure { "; Secure" } else { "" };
    format!(
        "{ROOM_DEVICE_COOKIE}={value}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Strict{secure}"
    )
}

/// Behind an https proxy (`X-Forwarded-Proto: https`).
fn is_https(headers: &HeaderMap) -> bool {
    headers
        .get("x-forwarded-proto")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(',').next())
        .is_some_and(|value| value.trim().eq_ignore_ascii_case("https"))
}

fn room_down(error: &StoreError) -> PatientError {
    tracing::error!(%error, "room store failed");
    PatientError::with_status(
        StatusCode::SERVICE_UNAVAILABLE,
        "room_access_unavailable",
        "Room access is temporarily unavailable.",
    )
}

/// The tablet of the room-device cookie (401 when there is none or it is no longer valid,
/// clearing the cookie), with the room's patient. Records the heartbeat.
pub(crate) async fn room_session(
    store: &PatientStore,
    headers: &HeaderMap,
) -> Result<RoomSession, PatientError> {
    let token = cookie_value(headers, ROOM_DEVICE_COOKIE).ok_or(NOT_PAIRED)?;
    let now = now_ms();
    let found = store
        .read(|data| {
            let device = data
                .room_devices
                .iter()
                .find(|device| {
                    device.revoked_at.is_none()
                        && device.session_expires_at.is_some_and(|at| at > now)
                        && device.session_token.as_deref().is_some_and(|stored| {
                            security::constant_time_eq(stored.as_bytes(), token.as_bytes())
                        })
                })?
                .clone();
            let patient = active_patient(data, &device.room_id);
            Some(RoomSession { device, patient })
        })
        .await
        .map_err(|error| room_down(&error))?;
    let session = found.ok_or(SESSION_EXPIRED.clearing_room_cookie())?;
    if session
        .device
        .last_seen_at
        .is_none_or(|at| now - at > HEARTBEAT_MILLIS)
    {
        let id = session.device.id;
        let heartbeat = store
            .update(|data| {
                if let Some(device) = data.room_devices.iter_mut().find(|d| d.id == id) {
                    device.last_seen_at = Some(now);
                }
                Ok::<(), PatientError>(())
            })
            .await;
        if let Err(error) = heartbeat {
            tracing::warn!(%error, "room tablet heartbeat not saved");
        }
    }
    Ok(session)
}

fn active_assignment<'a>(data: &'a StoreData, room_id: &str) -> Option<&'a RoomAssignmentRecord> {
    data.room_assignments
        .iter()
        .find(|assignment| assignment.room_id == room_id && assignment.discharged_at.is_none())
}

fn active_patient(data: &StoreData, room_id: &str) -> Option<RoomPatientRecord> {
    let assignment = active_assignment(data, room_id)?;
    data.room_patients
        .iter()
        .find(|patient| patient.id == assignment.patient_id)
        .cloned()
}

fn active_device<'a>(data: &'a StoreData, room_id: &str) -> Option<&'a RoomDeviceRecord> {
    data.room_devices
        .iter()
        .find(|device| device.room_id == room_id && device.revoked_at.is_none())
}

/// `publicRoomSession` of the Node gateway.
fn session_view(session: &RoomSession) -> Value {
    let device = &session.device;
    json!({
        "device": { "id": device.id, "label": device.device_label },
        "room": {
            "id": device.room_id,
            "label": device.room_label,
            "wing": device.room_wing,
            "floor": device.room_floor,
        },
        "patient": session.patient.as_ref().map(|patient| json!({
            "id": patient.id,
            "firstName": patient.first_name,
            "status": patient.status,
        })),
    })
}

#[derive(Deserialize)]
pub(crate) struct PairRequest {
    #[serde(default)]
    code: String,
}

/// `POST /api/room/pair`: a valid pairing code becomes the room-device cookie (the code is
/// spent).
pub(crate) async fn pair(
    State(store): State<Arc<PatientStore>>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, PatientError> {
    let input: PairRequest = parse(&body, BAD_CODE_FORMAT)?;
    let code = input.code.trim().to_uppercase();
    let well_formed = (8..=32).contains(&code.len())
        && code
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'-');
    if !well_formed {
        return Err(BAD_CODE_FORMAT);
    }
    let token = random_hex(32)?;
    let now = now_ms();
    let session = store
        .update(|data| {
            let device = data
                .room_devices
                .iter_mut()
                .find(|device| {
                    device.revoked_at.is_none()
                        && device.pairing_expires_at.is_some_and(|at| at > now)
                        && device.pairing_code.as_deref().is_some_and(|stored| {
                            security::constant_time_eq(stored.as_bytes(), code.as_bytes())
                        })
                })
                .ok_or(PatientError::with_status(
                    StatusCode::UNAUTHORIZED,
                    "invalid_pairing_code",
                    "This pairing code is invalid or has expired.",
                ))?;
            device.pairing_code = None;
            device.pairing_expires_at = None;
            device.session_token = Some(token.clone());
            device.session_expires_at = Some(now + ROOM_SESSION_SECONDS * 1000);
            device.last_seen_at = Some(now);
            let device = device.clone();
            let patient = active_patient(data, &device.room_id);
            Ok(RoomSession { device, patient })
        })
        .await
        .map_err(|error| room_down(&error))??;
    let cookie = room_cookie(&token, ROOM_SESSION_SECONDS, is_https(&headers));
    Ok(([(header::SET_COOKIE, cookie)], Json(session_view(&session))).into_response())
}

/// `GET /api/room/session`.
pub(crate) async fn session(
    State(store): State<Arc<PatientStore>>,
    headers: HeaderMap,
) -> Result<Response, PatientError> {
    let session = room_session(&store, &headers).await?;
    Ok(Json(session_view(&session)).into_response())
}

/// `POST /api/room/unpair`: always succeeds, clears the cookie and ends the tablet session,
/// so the care team can show a new pairing code.
pub(crate) async fn unpair(State(store): State<Arc<PatientStore>>, headers: HeaderMap) -> Response {
    if let Some(token) = cookie_value(&headers, ROOM_DEVICE_COOKIE) {
        let ended = store
            .update(|data| {
                for device in &mut data.room_devices {
                    let mine = device.session_token.as_deref().is_some_and(|stored| {
                        security::constant_time_eq(stored.as_bytes(), token.as_bytes())
                    });
                    if mine {
                        device.session_token = None;
                        device.session_expires_at = None;
                    }
                }
                Ok::<(), PatientError>(())
            })
            .await;
        if let Err(error) = ended {
            tracing::warn!(%error, "room tablet session not ended in the store");
        }
    }
    let cookie = room_cookie("", 0, is_https(&headers));
    ([(header::SET_COOKIE, cookie)], Json(json!({ "ok": true }))).into_response()
}

// ---------------------------------------------------------------- care team

#[derive(Clone)]
struct AdminState {
    store: Arc<PatientStore>,
    staff: Option<Arc<StaffAccess>>,
}

/// `/api/admin/rooms|devices|discharge` and the 404 `/api/admin/login`.
pub(crate) fn admin_router(store: Arc<PatientStore>, staff: Option<StaffAccess>) -> Router {
    Router::new()
        .route("/api/admin/rooms", get(list_rooms).post(admit))
        .route("/api/admin/devices", post(create_device))
        .route("/api/admin/discharge", post(discharge))
        .route("/api/admin/login", any(no_admin_login))
        .with_state(AdminState {
            store,
            staff: staff.map(Arc::new),
        })
}

/// The console tries the Node gateway's `/api/admin/login` first and falls back to this
/// server's `/auth/login` on 404.
async fn no_admin_login() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "error": "not_found",
            "message": "Administrators sign in with POST /auth/login on this server.",
        })),
    )
        .into_response()
}

impl AdminState {
    /// The staff access, or 403 `admin_required` when the server has none.
    fn staff(&self) -> Result<&StaffAccess, PatientError> {
        self.staff.as_deref().ok_or(ADMIN_REQUIRED)
    }

    /// The bearer token's identity, which must have the admin role.
    async fn require_admin(&self, headers: &HeaderMap) -> Result<VerifiedIdentity, PatientError> {
        let staff = self.staff()?;
        let token = headers
            .get(header::AUTHORIZATION)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.strip_prefix("Bearer "))
            .map(str::trim)
            .filter(|token| !token.is_empty())
            .ok_or(ADMIN_REQUIRED)?;
        let identity = staff.verifier.verify(token).await.map_err(|error| {
            tracing::error!(%error, "admin token check failed");
            PatientError::with_status(
                StatusCode::SERVICE_UNAVAILABLE,
                "auth_unavailable",
                "Administrator authentication is temporarily unavailable.",
            )
        })?;
        identity
            .filter(|identity| identity.role == Role::Admin)
            .ok_or(ADMIN_REQUIRED)
    }

    async fn room(&self, room_id: &str) -> Result<Option<ClinicRoom>, PatientError> {
        let rooms = self
            .staff()?
            .rooms
            .rooms()
            .await
            .map_err(|error| rooms_down(&error))?;
        Ok(rooms.into_iter().find(|room| room.id == room_id))
    }
}

fn rooms_down(error: &str) -> PatientError {
    tracing::error!(%error, "clinic rooms could not be read");
    PatientError::with_status(
        StatusCode::SERVICE_UNAVAILABLE,
        "room_operation_unavailable",
        "The room operation is temporarily unavailable.",
    )
}

fn admin_store_down(error: &StoreError) -> PatientError {
    tracing::error!(%error, "room store failed");
    PatientError::with_status(
        StatusCode::SERVICE_UNAVAILABLE,
        "room_operation_unavailable",
        "The room operation is temporarily unavailable.",
    )
}

fn iso(ms: i64) -> Option<String> {
    DateTime::<Utc>::from_timestamp_millis(ms)
        .map(|at| at.to_rfc3339_opts(SecondsFormat::Millis, true))
}

fn patient_view(patient: &RoomPatientRecord) -> Value {
    json!({
        "id": patient.id,
        "firstName": patient.first_name,
        "medicalRecordRef": patient.medical_record_ref,
        "status": patient.status,
        "admittedAt": iso(patient.admitted_at),
    })
}

fn device_view(device: &RoomDeviceRecord, pairing_code: Option<&str>, now: i64) -> Value {
    json!({
        "id": device.id,
        "label": device.device_label,
        "roomId": device.room_id,
        "online": device.last_seen_at.is_some_and(|at| now - at < ONLINE_MILLIS),
        "paired": device.session_token.is_some() && device.revoked_at.is_none(),
        "pairingCode": pairing_code,
    })
}

/// `GET /api/admin/rooms`: the rooms of the clinic map with their patient and tablet.
async fn list_rooms(
    State(state): State<AdminState>,
    headers: HeaderMap,
) -> Result<Response, PatientError> {
    state.require_admin(&headers).await?;
    let rooms = state
        .staff()?
        .rooms
        .rooms()
        .await
        .map_err(|error| rooms_down(&error))?;
    let now = now_ms();
    let views = state
        .store
        .read(|data| {
            rooms
                .iter()
                .map(|room| {
                    json!({
                        "id": room.id,
                        "label": room.label,
                        "wing": room.wing,
                        "floor": room.floor,
                        "patient": active_patient(data, &room.id)
                            .filter(|patient| patient.status == "admitted")
                            .as_ref()
                            .map(patient_view),
                        "device": active_device(data, &room.id)
                            .map(|device| device_view(device, None, now)),
                    })
                })
                .collect::<Vec<_>>()
        })
        .await
        .map_err(|error| admin_store_down(&error))?;
    Ok(Json(json!({ "rooms": views })).into_response())
}

#[derive(Deserialize)]
struct AdmitRequest {
    #[serde(default)]
    first_name: String,
    #[serde(default)]
    medical_record_ref: String,
    #[serde(default)]
    room_id: String,
}

/// `POST /api/admin/rooms`: admits a patient to a free room.
async fn admit(
    State(state): State<AdminState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, PatientError> {
    let invalid = PatientError::unprocessable(
        "invalid_patient",
        "Enter a first name, a medical record reference and a valid room.",
    );
    let admin = state.require_admin(&headers).await?;
    let input: AdmitRequest = parse(&body, invalid)?;
    let first_name = normalize_first_name(&input.first_name).ok_or(invalid)?;
    let record_ref = normalize_record_ref(&input.medical_record_ref).ok_or(invalid)?;
    let room_id = input.room_id.trim().to_owned();
    state.room(&room_id).await?.ok_or(invalid)?;
    let now = now_ms();
    let patient = RoomPatientRecord {
        id: Uuid::new_v4(),
        first_name,
        medical_record_ref: record_ref,
        status: "admitted".to_owned(),
        admitted_at: now,
        discharged_at: None,
        created_by: admin.subject_id.to_string(),
    };
    let view = patient_view(&patient);
    state
        .store
        .update(|data| {
            if active_assignment(data, &room_id).is_some() {
                return Err(PatientError::with_status(
                    StatusCode::CONFLICT,
                    "room_occupied",
                    "Discharge the current patient before assigning another patient to this room.",
                ));
            }
            let duplicate = data.room_patients.iter().any(|other| {
                other.status == "admitted"
                    && other
                        .medical_record_ref
                        .eq_ignore_ascii_case(&patient.medical_record_ref)
            });
            if duplicate {
                return Err(PatientError::with_status(
                    StatusCode::CONFLICT,
                    "patient_already_admitted",
                    "A patient with this medical record reference is already admitted.",
                ));
            }
            data.room_assignments.push(RoomAssignmentRecord {
                id: Uuid::new_v4(),
                room_id: room_id.clone(),
                patient_id: patient.id,
                assigned_at: now,
                discharged_at: None,
            });
            data.room_patients.push(patient);
            Ok(())
        })
        .await
        .map_err(|error| admin_store_down(&error))??;
    Ok((
        StatusCode::CREATED,
        Json(json!({ "patient": view, "roomId": room_id })),
    )
        .into_response())
}

#[derive(Deserialize)]
struct DeviceRequest {
    #[serde(default)]
    room_id: String,
    #[serde(default)]
    label: String,
}

/// `POST /api/admin/devices`: registers the room's tablet (or reuses it) and gives a new
/// pairing code, valid 15 minutes. A paired tablet keeps working until the code is used.
async fn create_device(
    State(state): State<AdminState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, PatientError> {
    let invalid = PatientError::unprocessable(
        "invalid_device",
        "Choose a room of the clinic map and a valid tablet label.",
    );
    state.require_admin(&headers).await?;
    let input: DeviceRequest = parse(&body, invalid)?;
    let room_id = input.room_id.trim().to_owned();
    let room = state.room(&room_id).await?.ok_or(invalid)?;
    let label = match input.label.trim() {
        "" => format!("Tablet {}", room.label),
        label => label.to_owned(),
    };
    if label.chars().count() > MAX_DEVICE_LABEL_CHARS {
        return Err(invalid);
    }
    let code = random_hex(6)?.to_uppercase();
    let now = now_ms();
    let device = state
        .store
        .update(|data| {
            let device = if let Some(device) = data
                .room_devices
                .iter_mut()
                .find(|device| device.room_id == room.id && device.revoked_at.is_none())
            {
                device
            } else {
                data.room_devices.push(RoomDeviceRecord {
                    id: Uuid::new_v4(),
                    room_id: room.id.clone(),
                    room_label: String::new(),
                    room_wing: String::new(),
                    room_floor: 0,
                    device_label: String::new(),
                    pairing_code: None,
                    pairing_expires_at: None,
                    session_token: None,
                    session_expires_at: None,
                    last_seen_at: None,
                    revoked_at: None,
                });
                data.room_devices
                    .last_mut()
                    .ok_or(PatientError::with_status(
                        StatusCode::SERVICE_UNAVAILABLE,
                        "device_operation_unavailable",
                        "The tablet operation is temporarily unavailable.",
                    ))?
            };
            device.room_label.clone_from(&room.label);
            device.room_wing.clone_from(&room.wing);
            device.room_floor = room.floor;
            device.device_label = label;
            device.pairing_code = Some(code.clone());
            device.pairing_expires_at = Some(now + PAIRING_MILLIS);
            Ok(device.clone())
        })
        .await
        .map_err(|error| admin_store_down(&error))??;
    Ok((
        StatusCode::CREATED,
        Json(json!({ "device": device_view(&device, Some(&code), now), "pairingCode": code })),
    )
        .into_response())
}

#[derive(Deserialize)]
struct DischargeRequest {
    #[serde(default)]
    room_id: String,
}

/// `POST /api/admin/discharge`: closes the room's assignment, discharges the patient and
/// revokes the room's tablet.
async fn discharge(
    State(state): State<AdminState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, PatientError> {
    let invalid = PatientError::unprocessable("invalid_room", "Choose a valid room.");
    let admin = state.require_admin(&headers).await?;
    let input: DischargeRequest = parse(&body, invalid)?;
    let room_id = input.room_id.trim().to_owned();
    let valid = (1..=64).contains(&room_id.len())
        && room_id
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_alphanumeric())
        && room_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-');
    if !valid {
        return Err(invalid);
    }
    let now = now_ms();
    let patient_id = state
        .store
        .update(|data| {
            let assignment = data
                .room_assignments
                .iter_mut()
                .find(|assignment| {
                    assignment.room_id == room_id && assignment.discharged_at.is_none()
                })
                .ok_or(PatientError::with_status(
                    StatusCode::NOT_FOUND,
                    "room_empty",
                    "There is no admitted patient in this room.",
                ))?;
            assignment.discharged_at = Some(now);
            let patient_id = assignment.patient_id;
            for patient in &mut data.room_patients {
                if patient.id == patient_id && patient.status == "admitted" {
                    "discharged".clone_into(&mut patient.status);
                    patient.discharged_at = Some(now);
                }
            }
            for device in &mut data.room_devices {
                if device.room_id == room_id && device.revoked_at.is_none() {
                    device.revoked_at = Some(now);
                    device.pairing_code = None;
                    device.pairing_expires_at = None;
                    device.session_token = None;
                    device.session_expires_at = None;
                }
            }
            Ok(patient_id)
        })
        .await
        .map_err(|error| admin_store_down(&error))??;
    Ok(Json(json!({
        "roomId": room_id,
        "patientId": patient_id,
        "dischargedAt": iso(now),
        "dischargedBy": admin.subject_id.to_string(),
    }))
    .into_response())
}

/// Letters, then letters, apostrophes, spaces or dashes; 1 to 40 characters.
fn normalize_first_name(raw: &str) -> Option<String> {
    let name = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut chars = name.chars();
    let valid = chars.next().is_some_and(char::is_alphabetic)
        && chars.all(|c| c.is_alphabetic() || matches!(c, '\'' | '\u{2019}' | ' ' | '-'))
        && name.chars().count() <= 40;
    valid.then_some(name)
}

/// A letter or digit, then letters, digits, `.`, `_`, `/`, spaces or dashes; up to 64.
fn normalize_record_ref(raw: &str) -> Option<String> {
    let reference = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut chars = reference.chars();
    let valid = chars.next().is_some_and(char::is_alphanumeric)
        && chars.all(|c| c.is_alphanumeric() || matches!(c, '.' | '_' | '/' | ' ' | '-'))
        && reference.chars().count() <= 64;
    valid.then_some(reference)
}
