//! Handlers of the patient companion API (`openapi.json` at the repository root).

use std::fmt::Write as _;
use std::sync::Arc;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{IntoResponse, Response};
use chrono::{Local, NaiveDate, Utc};
use domain::ClinicId;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use uuid::Uuid;

use super::store::{
    MoodRecord, OtpRecord, PatientStore, QuestionRecord, RequestRecord, SessionRecord, StoreData,
    UserRecord,
};
use super::{PatientError, ROOM_DEVICE_COOKIE, SESSION_COOKIE, cookie_value, session_token};

type Store = State<Arc<PatientStore>>;
type Answer = Result<Response, PatientError>;

/// A session lasts 30 days.
const SESSION_SECONDS: i64 = 30 * 24 * 3600;
/// A phone code lasts 10 minutes.
const OTP_MILLIS: i64 = 10 * 60 * 1000;
/// Wrong guesses before a phone code is dropped.
const OTP_MAX_FAILURES: u32 = 5;
const MIN_PASSWORD_CHARS: usize = 8;
const MAX_FIRST_NAME_CHARS: usize = 40;
const MAX_QUESTION_CHARS: usize = 300;
const REQUEST_KINDS: [&str; 6] = [
    "water",
    "blanket",
    "wheelchair",
    "pain",
    "interpreter",
    "care-team",
];
/// The demo day plan: (time, kind, until).
const DEMO_DAY: [(&str, &str, Option<&str>); 6] = [
    ("07:30", "breakfast", None),
    ("09:00", "round", None),
    ("10:30", "physio", None),
    ("12:00", "lunch", None),
    ("14:00", "visits", Some("18:00")),
    ("18:30", "dinner", None),
];
/// The room tablet's day plan (the Node gateway's seed).
const ROOM_DAY: [(&str, &str, Option<&str>); 6] = [
    ("07:30", "breakfast", None),
    ("10:00", "round", None),
    ("11:00", "physio", None),
    ("12:00", "lunch", None),
    ("14:00", "visits", Some("20:00")),
    ("18:30", "dinner", None),
];

const INVALID_INPUT: PatientError =
    PatientError::unprocessable("invalid_input", "Check the fields and try again.");
const INVALID_FIRST_NAME: PatientError = PatientError::unprocessable(
    "invalid_first_name",
    "Enter a first name of 1 to 40 characters.",
);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PasswordAuthRequest {
    identifier: String,
    password: String,
    first_name: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PhoneRequest {
    phone: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct OtpVerificationRequest {
    phone: String,
    token: String,
    first_name: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ProfileRequest {
    first_name: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct QuestionRequest {
    text: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RequestCreate {
    kind: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct MoodRequest {
    value: u8,
}

/// `?date=YYYY-MM-DD`.
#[derive(Deserialize)]
pub(crate) struct DateQuery {
    date: Option<String>,
}

/// `User` of the contract.
#[derive(Serialize)]
struct UserView {
    id: Uuid,
    email: Option<String>,
    phone: Option<String>,
    #[serde(rename = "firstName")]
    first_name: Option<String>,
}

impl From<&UserRecord> for UserView {
    fn from(user: &UserRecord) -> UserView {
        UserView {
            id: user.id,
            email: user.email.clone(),
            phone: user.phone.clone(),
            first_name: user.first_name.clone(),
        }
    }
}

fn question_view(question: &QuestionRecord) -> Value {
    json!({ "id": question.id, "text": question.text, "created_at": question.created_at })
}

fn request_view(request: &RequestRecord) -> Value {
    json!({
        "id": request.id,
        "kind": request.kind,
        "status": request.status,
        "status_index": request.status_index,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
    })
}

/// HACKATHON: no care-team screen moves patient requests along yet, so a request still at
/// `sent` is shown advancing with its age (seen after 20 s, on the way after 60 s, done after
/// 3 min). Remove after the pitch, when staff update the status themselves.
const DEMO_STATUS_STEPS: [(i64, &str, u8); 3] = [
    (180_000, "done", 3),
    (60_000, "on_the_way", 2),
    (20_000, "seen", 1),
];

fn demo_progress(mut request: RequestRecord, now: i64) -> RequestRecord {
    if request.status_index != 0 {
        return request;
    }
    let age = now.saturating_sub(request.created_at);
    if let Some((after, status, index)) =
        DEMO_STATUS_STEPS.iter().find(|(after, _, _)| age >= *after)
    {
        (*status).clone_into(&mut request.status);
        request.status_index = *index;
        request.updated_at = request.created_at.saturating_add(*after);
    }
    request
}

// ---------------------------------------------------------------- authentication

/// `POST /api/auth/signup`: creates the account and signs it in (no confirmation step).
pub(crate) async fn signup(State(store): Store, body: Bytes) -> Answer {
    let input: PasswordAuthRequest = parse(&body, INVALID_INPUT)?;
    let contact = parse_identifier(&input.identifier).ok_or(INVALID_INPUT)?;
    let first_name = clean_first_name(&input.first_name).ok_or(INVALID_FIRST_NAME)?;
    if input.password.chars().count() < MIN_PASSWORD_CHARS {
        return Err(PatientError::unprocessable(
            "invalid_input",
            "Choose a password of at least 8 characters.",
        ));
    }
    let salt = random_hex(16)?;
    let key = password_key(salt.clone(), contact.key(), input.password).await?;
    let token = random_hex(32)?;
    let user = store
        .update(|data| {
            if data.users.iter().any(|user| contact.matches(user)) {
                return Err(PatientError::with_status(
                    StatusCode::BAD_REQUEST,
                    "signup_failed",
                    "An account already exists for this contact. Sign in instead.",
                ));
            }
            let (email, phone) = contact.split();
            let user = UserRecord {
                id: Uuid::new_v4(),
                email,
                phone,
                first_name: Some(first_name),
                salt,
                password_key: Some(key),
            };
            data.users.push(user.clone());
            open_session(data, &token, user.id);
            Ok(user)
        })
        .await
        .map_err(|error| PatientError::auth_down(&error))??;
    let body = json!({ "user": UserView::from(&user), "needsConfirmation": false });
    Ok(signed_in(StatusCode::CREATED, &token, &body))
}

/// `POST /api/auth/login`.
pub(crate) async fn login(State(store): Store, body: Bytes) -> Answer {
    let input: PasswordAuthRequest = parse(&body, INVALID_INPUT)?;
    let contact = parse_identifier(&input.identifier).ok_or(INVALID_INPUT)?;
    let first_name = clean_first_name(&input.first_name).ok_or(INVALID_FIRST_NAME)?;
    let invalid = PatientError::with_status(
        StatusCode::UNAUTHORIZED,
        "invalid_credentials",
        "The sign-in details are not valid.",
    );
    let found = store
        .read(|data| {
            data.users
                .iter()
                .find(|user| contact.matches(user))
                .map(|user| (user.id, user.salt.clone(), user.password_key.clone()))
        })
        .await
        .map_err(|error| PatientError::auth_down(&error))?;
    // Unknown contacts still pay for one derivation, so timing does not reveal accounts.
    let (user_id, salt, stored) = match found {
        Some(found) => found,
        None => (Uuid::nil(), random_hex(16)?, None),
    };
    let key = password_key(salt, contact.key(), input.password).await?;
    let Some(stored) = stored else {
        return Err(invalid);
    };
    if !security::constant_time_eq(key.as_bytes(), stored.as_bytes()) {
        return Err(invalid);
    }
    let token = random_hex(32)?;
    let user = store
        .update(|data| {
            let user = data
                .users
                .iter_mut()
                .find(|user| user.id == user_id)
                .ok_or(PatientError::not_authenticated())?;
            user.first_name = Some(first_name);
            let user = user.clone();
            open_session(data, &token, user.id);
            Ok(user)
        })
        .await
        .map_err(|error| PatientError::auth_down(&error))??;
    Ok(signed_in(
        StatusCode::OK,
        &token,
        &json!({ "user": UserView::from(&user) }),
    ))
}

/// `POST /api/auth/request-otp`: the code is logged (dummy SMS), never returned.
pub(crate) async fn request_otp(State(store): Store, body: Bytes) -> Answer {
    let invalid_phone = PatientError::unprocessable(
        "invalid_phone",
        "Enter the phone number in international format, for example +41 79 123 45 67.",
    );
    let input: PhoneRequest = parse(&body, invalid_phone)?;
    let phone = normalize_phone(&input.phone).ok_or(invalid_phone)?;
    let code = six_digit_code()?;
    let record = OtpRecord {
        phone: phone.clone(),
        code: code.clone(),
        expires_at: now_ms() + OTP_MILLIS,
        failures: 0,
    };
    store
        .update(|data| {
            data.otps.retain(|otp| otp.phone != phone);
            data.otps.push(record);
            Ok::<(), PatientError>(())
        })
        .await
        .map_err(|error| PatientError::auth_down(&error))??;
    let ending: String = phone
        .chars()
        .rev()
        .take(2)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    tracing::info!(
        phone_ending = %ending,
        code = %code,
        "patient sign-in code (dummy SMS, valid 10 minutes)"
    );
    Ok(Json(json!({
        "ok": true,
        "message": "If the number is registered, a six-digit code has been sent.",
    }))
    .into_response())
}

/// `POST /api/auth/verify-otp`: signs in, creating the account on first use.
pub(crate) async fn verify_otp(State(store): Store, body: Bytes) -> Answer {
    let malformed = PatientError::unprocessable("invalid_code", "Enter the six-digit code.");
    let input: OtpVerificationRequest = parse(&body, malformed)?;
    let phone = normalize_phone(&input.phone).ok_or(malformed)?;
    let code = input.token.trim().to_owned();
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(malformed);
    }
    let first_name = clean_first_name(&input.first_name).ok_or(INVALID_FIRST_NAME)?;
    let token = random_hex(32)?;
    let now = now_ms();
    // A wrong guess must be recorded, so the closure answers Ok(Err(..)) for it.
    let outcome = store
        .update(|data| {
            let Some(otp) = data
                .otps
                .iter_mut()
                .find(|otp| otp.phone == phone && otp.expires_at > now)
            else {
                return Ok(None);
            };
            if !security::constant_time_eq(otp.code.as_bytes(), code.as_bytes()) {
                otp.failures += 1;
                let failures = otp.failures;
                if failures >= OTP_MAX_FAILURES {
                    data.otps.retain(|otp| otp.phone != phone);
                }
                return Ok(None);
            }
            data.otps.retain(|otp| otp.phone != phone);
            let user = if let Some(user) = data
                .users
                .iter_mut()
                .find(|user| user.phone.as_deref() == Some(phone.as_str()))
            {
                user.first_name = Some(first_name);
                user.clone()
            } else {
                let user = UserRecord {
                    id: Uuid::new_v4(),
                    email: None,
                    phone: Some(phone.clone()),
                    first_name: Some(first_name),
                    salt: String::new(),
                    password_key: None,
                };
                data.users.push(user.clone());
                user
            };
            open_session(data, &token, user.id);
            Ok::<_, PatientError>(Some(user))
        })
        .await
        .map_err(|error| PatientError::auth_down(&error))??;
    let user = outcome.ok_or(PatientError::with_status(
        StatusCode::UNAUTHORIZED,
        "invalid_code",
        "The code is invalid or has expired. Ask for a new one.",
    ))?;
    Ok(signed_in(
        StatusCode::OK,
        &token,
        &json!({ "user": UserView::from(&user) }),
    ))
}

/// `GET /api/auth/session`.
pub(crate) async fn session(State(store): Store, headers: HeaderMap) -> Answer {
    let user = current_user(&store, &headers, PatientError::auth_down).await?;
    Ok(Json(json!({ "user": UserView::from(&user) })).into_response())
}

/// `PUT /api/auth/profile`.
pub(crate) async fn profile(State(store): Store, headers: HeaderMap, body: Bytes) -> Answer {
    let user = current_user(&store, &headers, PatientError::auth_down).await?;
    let input: ProfileRequest = parse(&body, INVALID_FIRST_NAME)?;
    let first_name = clean_first_name(&input.first_name).ok_or(INVALID_FIRST_NAME)?;
    let user = store
        .update(|data| {
            let record = data
                .users
                .iter_mut()
                .find(|record| record.id == user.id)
                .ok_or(PatientError::not_authenticated())?;
            record.first_name = Some(first_name);
            Ok(record.clone())
        })
        .await
        .map_err(|error| PatientError::auth_down(&error))??;
    Ok(Json(json!({ "user": UserView::from(&user) })).into_response())
}

/// `POST /api/auth/logout`: always succeeds and clears the cookie.
pub(crate) async fn logout(State(store): Store, headers: HeaderMap) -> Answer {
    if let Some(token) = session_token(&headers) {
        store
            .update(|data| {
                data.sessions.retain(|session| session.token != token);
                Ok::<(), PatientError>(())
            })
            .await
            .map_err(|error| PatientError::auth_down(&error))??;
    }
    let cookie = format!("{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0");
    Ok(([(header::SET_COOKIE, cookie)], Json(json!({ "ok": true }))).into_response())
}

// ---------------------------------------------------------------- patient day

/// `GET /api/patient/program`: the fixed demo day for an account; the room day plan (the
/// Node gateway's seed, `demo: false`) for a room tablet.
pub(crate) async fn program(
    State(store): Store,
    headers: HeaderMap,
    Query(query): Query<DateQuery>,
) -> Answer {
    let patient = current_patient(&store, &headers).await?;
    let date = parse_date(query.date.as_deref())?;
    let day = if patient.room { &ROOM_DAY } else { &DEMO_DAY };
    let items: Vec<Value> = day
        .iter()
        .map(|(time, kind, until)| json!({ "time": time, "kind": kind, "until": until }))
        .collect();
    Ok(Json(json!({ "date": date, "items": items, "demo": !patient.room })).into_response())
}

/// `GET /api/patient/questions`.
pub(crate) async fn list_questions(State(store): Store, headers: HeaderMap) -> Answer {
    let user = current_patient(&store, &headers).await?;
    let mut items = store
        .read(|data| {
            data.questions
                .iter()
                .filter(|question| question.user_id == user.id)
                .cloned()
                .collect::<Vec<_>>()
        })
        .await
        .map_err(|error| PatientError::data_down(&error))?;
    items.sort_by_key(|question| question.created_at);
    let items: Vec<Value> = items.iter().map(question_view).collect();
    Ok(Json(json!({ "items": items })).into_response())
}

/// `POST /api/patient/questions`.
pub(crate) async fn add_question(State(store): Store, headers: HeaderMap, body: Bytes) -> Answer {
    let invalid = PatientError::unprocessable(
        "invalid_question",
        "Write a question of 1 to 300 characters.",
    );
    let user = current_patient(&store, &headers).await?;
    let input: QuestionRequest = parse(&body, invalid)?;
    let text = input.text.trim().to_owned();
    let length = text.chars().count();
    if length == 0 || length > MAX_QUESTION_CHARS {
        return Err(invalid);
    }
    let question = QuestionRecord {
        id: Uuid::new_v4(),
        user_id: user.id,
        text,
        created_at: now_ms(),
    };
    let view = question_view(&question);
    store
        .update(|data| {
            data.questions.push(question);
            Ok::<(), PatientError>(())
        })
        .await
        .map_err(|error| PatientError::data_down(&error))??;
    Ok((StatusCode::CREATED, Json(view)).into_response())
}

/// `DELETE /api/patient/questions/{id}`: only the patient's own; unknown ids are ignored.
pub(crate) async fn delete_question(
    State(store): Store,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Answer {
    let user = current_patient(&store, &headers).await?;
    let id = Uuid::parse_str(&id).map_err(|_| {
        PatientError::unprocessable("invalid_question", "This question id is not valid.")
    })?;
    store
        .update(|data| {
            data.questions
                .retain(|question| !(question.id == id && question.user_id == user.id));
            Ok::<(), PatientError>(())
        })
        .await
        .map_err(|error| PatientError::data_down(&error))??;
    Ok(StatusCode::NO_CONTENT.into_response())
}

/// `GET /api/patient/requests?date=`: newest first.
pub(crate) async fn list_requests(
    State(store): Store,
    headers: HeaderMap,
    Query(query): Query<DateQuery>,
) -> Answer {
    let user = current_patient(&store, &headers).await?;
    let date = parse_date(query.date.as_deref())?.to_string();
    let mut items = store
        .read(|data| {
            data.requests
                .iter()
                .filter(|request| request.user_id == user.id && request.date == date)
                .cloned()
                .collect::<Vec<_>>()
        })
        .await
        .map_err(|error| PatientError::data_down(&error))?;
    items.sort_by_key(|request| std::cmp::Reverse(request.created_at));
    let now = now_ms();
    let items: Vec<Value> = items
        .into_iter()
        .map(|request| request_view(&demo_progress(request, now)))
        .collect();
    Ok(Json(json!({ "date": date, "items": items })).into_response())
}

/// `POST /api/patient/requests?date=`: created with status `sent`.
pub(crate) async fn add_request(
    State(store): Store,
    headers: HeaderMap,
    Query(query): Query<DateQuery>,
    body: Bytes,
) -> Answer {
    let invalid = PatientError::unprocessable("invalid_request", "This request type is not known.");
    let user = current_patient(&store, &headers).await?;
    let date = parse_date(query.date.as_deref())?.to_string();
    let input: RequestCreate = parse(&body, invalid)?;
    if !REQUEST_KINDS.contains(&input.kind.as_str()) {
        return Err(invalid);
    }
    let now = now_ms();
    let request = RequestRecord {
        id: Uuid::new_v4(),
        user_id: user.id,
        date,
        kind: input.kind,
        status: "sent".to_owned(),
        status_index: 0,
        created_at: now,
        updated_at: now,
    };
    let view = request_view(&request);
    store
        .update(|data| {
            data.requests.push(request);
            Ok::<(), PatientError>(())
        })
        .await
        .map_err(|error| PatientError::data_down(&error))??;
    Ok((StatusCode::CREATED, Json(view)).into_response())
}

/// `POST /api/patient/mood?date=`: one check-in per day, the last one wins.
pub(crate) async fn save_mood(
    State(store): Store,
    headers: HeaderMap,
    Query(query): Query<DateQuery>,
    body: Bytes,
) -> Answer {
    let invalid = PatientError::unprocessable(
        "invalid_mood",
        "The mood value must be an integer from 1 to 5.",
    );
    let user = current_patient(&store, &headers).await?;
    let date = parse_date(query.date.as_deref())?.to_string();
    let input: MoodRequest = parse(&body, invalid)?;
    if !(1..=5).contains(&input.value) {
        return Err(invalid);
    }
    let mood = MoodRecord {
        user_id: user.id,
        date,
        value: input.value,
        at: now_ms(),
    };
    store
        .update(|data| {
            data.moods
                .retain(|old| !(old.user_id == mood.user_id && old.date == mood.date));
            data.moods.push(mood);
            Ok::<(), PatientError>(())
        })
        .await
        .map_err(|error| PatientError::data_down(&error))??;
    Ok(StatusCode::NO_CONTENT.into_response())
}

// ---------------------------------------------------------------- helpers

/// Whose data a patient-day route works on.
struct Patient {
    id: Uuid,
    /// A paired room tablet (the patient admitted to that room), not an account.
    room: bool,
}

/// As the Node gateway: a room-device cookie means the patient of that room (401 when the
/// tablet session is gone, 409 `no_patient_in_room`); otherwise the signed-in account.
async fn current_patient(
    store: &PatientStore,
    headers: &HeaderMap,
) -> Result<Patient, PatientError> {
    if cookie_value(headers, ROOM_DEVICE_COOKIE).is_some() {
        let session = super::rooms::room_session(store, headers).await?;
        let patient = session.patient.ok_or(PatientError::with_status(
            StatusCode::CONFLICT,
            "no_patient_in_room",
            "No patient is assigned to this room yet.",
        ))?;
        return Ok(Patient {
            id: patient.id,
            room: true,
        });
    }
    let user = current_user(store, headers, PatientError::data_down).await?;
    Ok(Patient {
        id: user.id,
        room: false,
    })
}

/// The signed-in patient, or 401.
pub(super) async fn current_user(
    store: &PatientStore,
    headers: &HeaderMap,
    down: fn(&super::StoreError) -> PatientError,
) -> Result<UserRecord, PatientError> {
    let token = session_token(headers).ok_or(PatientError::not_authenticated())?;
    let now = now_ms();
    store
        .read(|data| {
            data.sessions
                .iter()
                .find(|session| {
                    session.expires_at > now
                        && security::constant_time_eq(session.token.as_bytes(), token.as_bytes())
                })
                .and_then(|session| data.users.iter().find(|user| user.id == session.user_id))
                .cloned()
        })
        .await
        .map_err(|error| down(&error))?
        .ok_or(PatientError::not_authenticated())
}

/// Adds a session (and drops the expired sessions and codes).
fn open_session(data: &mut StoreData, token: &str, user_id: Uuid) {
    let now = now_ms();
    data.sessions.retain(|session| session.expires_at > now);
    data.otps.retain(|otp| otp.expires_at > now);
    data.sessions.push(SessionRecord {
        token: token.to_owned(),
        user_id,
        expires_at: now + SESSION_SECONDS * 1000,
    });
}

/// A JSON answer that also sets the session cookie.
fn signed_in(status: StatusCode, token: &str, body: &Value) -> Response {
    let cookie = format!(
        "{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_SECONDS}"
    );
    (status, [(header::SET_COOKIE, cookie)], Json(body.clone())).into_response()
}

pub(crate) fn parse<T: DeserializeOwned>(
    body: &[u8],
    invalid: PatientError,
) -> Result<T, PatientError> {
    serde_json::from_slice(body).map_err(|_| invalid)
}

fn parse_date(raw: Option<&str>) -> Result<NaiveDate, PatientError> {
    match raw {
        None => Ok(Local::now().date_naive()),
        Some(raw) => NaiveDate::parse_from_str(raw, "%Y-%m-%d").map_err(|_| {
            PatientError::unprocessable("invalid_input", "The date must be YYYY-MM-DD.")
        }),
    }
}

pub(crate) fn now_ms() -> i64 {
    Utc::now().timestamp_millis()
}

/// `bytes` bytes of OS randomness, in hex.
pub(crate) fn random_hex(bytes: usize) -> Result<String, PatientError> {
    let mut buffer = vec![0_u8; bytes];
    getrandom::fill(&mut buffer).map_err(|_| randomness_failed())?;
    Ok(hex(&buffer))
}

fn six_digit_code() -> Result<String, PatientError> {
    let mut buffer = [0_u8; 4];
    getrandom::fill(&mut buffer).map_err(|_| randomness_failed())?;
    Ok(format!("{:06}", u32::from_le_bytes(buffer) % 1_000_000))
}

fn randomness_failed() -> PatientError {
    tracing::error!("OS randomness failed for the patient API");
    PatientError::with_status(
        StatusCode::SERVICE_UNAVAILABLE,
        "auth_unavailable",
        "Sign-in is temporarily unavailable. Try again in a moment.",
    )
}

fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        let _ = write!(out, "{byte:02x}");
    }
    out
}

/// The password key: the staff account derivation (PBKDF2-HMAC-SHA256, 600 000 rounds) with
/// a per-account random salt, run off the async threads.
async fn password_key(
    salt: String,
    identifier: String,
    password: String,
) -> Result<String, PatientError> {
    tokio::task::spawn_blocking(move || {
        let key = security::derive_account_key(
            &format!("patient:{salt}:{identifier}"),
            &password,
            &ClinicId::seed(),
        );
        hex(key.expose())
    })
    .await
    .map_err(|_| randomness_failed())
}

/// An email address or a phone number.
enum Contact {
    Email(String),
    Phone(String),
}

impl Contact {
    fn key(&self) -> String {
        match self {
            Contact::Email(value) | Contact::Phone(value) => value.clone(),
        }
    }

    fn matches(&self, user: &UserRecord) -> bool {
        match self {
            Contact::Email(email) => user.email.as_deref() == Some(email.as_str()),
            Contact::Phone(phone) => user.phone.as_deref() == Some(phone.as_str()),
        }
    }

    fn split(&self) -> (Option<String>, Option<String>) {
        match self {
            Contact::Email(email) => (Some(email.clone()), None),
            Contact::Phone(phone) => (None, Some(phone.clone())),
        }
    }
}

fn parse_identifier(raw: &str) -> Option<Contact> {
    if raw.contains('@') {
        normalize_email(raw).map(Contact::Email)
    } else {
        normalize_phone(raw).map(Contact::Phone)
    }
}

fn normalize_email(raw: &str) -> Option<String> {
    let email = raw.trim().to_lowercase();
    let (local, domain) = email.split_once('@')?;
    let valid = !local.is_empty()
        && domain.contains('.')
        && !domain.starts_with('.')
        && !domain.ends_with('.')
        && !domain.contains('@')
        && email.len() <= 254
        && !email.chars().any(char::is_whitespace);
    valid.then_some(email)
}

/// `+` then 7 to 15 digits; spaces, dashes, dots and brackets are ignored.
fn normalize_phone(raw: &str) -> Option<String> {
    let compact: String = raw
        .chars()
        .filter(|c| !matches!(c, ' ' | '-' | '.' | '(' | ')'))
        .collect();
    let digits = compact.strip_prefix('+')?;
    let valid =
        (7..=15).contains(&digits.len()) && digits.bytes().all(|byte| byte.is_ascii_digit());
    valid.then(|| format!("+{digits}"))
}

fn clean_first_name(raw: &str) -> Option<String> {
    let name = raw.trim();
    let length = name.chars().count();
    let valid = (1..=MAX_FIRST_NAME_CHARS).contains(&length) && !name.chars().any(char::is_control);
    valid.then(|| name.to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_sent_request_advances_with_its_age() {
        let request = RequestRecord {
            id: Uuid::nil(),
            user_id: Uuid::nil(),
            date: "2026-11-16".to_owned(),
            kind: "water".to_owned(),
            status: "sent".to_owned(),
            status_index: 0,
            created_at: 1_000,
            updated_at: 1_000,
        };
        assert_eq!(demo_progress(request.clone(), 5_000).status, "sent");
        assert_eq!(demo_progress(request.clone(), 31_000).status, "seen");
        assert_eq!(demo_progress(request.clone(), 70_000).status_index, 2);
        assert_eq!(demo_progress(request, 400_000).status, "done");
    }
}
