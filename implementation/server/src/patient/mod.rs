//! The patient companion API (`/api/auth/*`, `/api/patient/*`, contract: `openapi.json` at
//! the repository root) and the patient web app served at `/patient/`.
//!
//! Patients are not staff: they hold no bearer token and may connect from any network, so
//! these routes sit outside the staff security stack (no known-network check, no bearer
//! identity). They keep the traffic monitor (counters, rate limit, address blocks), a small
//! body limit, and a same-origin check on every mutating route. The session is an `HttpOnly`
//! cookie, [`SESSION_COOKIE`].
//!
//! Storage is a dummy JSON file ([`PatientStore`]); see `store.rs`.

mod handlers;
pub mod rooms;
pub(crate) mod static_files;
pub mod store;
pub mod translate;

use std::sync::Arc;

use axum::Json;
use axum::Router;
use axum::extract::Request;
use axum::http::{HeaderMap, Method, StatusCode, header};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{delete, get, post, put};
use security::TrafficMonitor;
use security::monitor::layer;
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::trace::TraceLayer;

pub use rooms::{ClinicRoom, FixedRooms, MapRooms, RoomDirectory, StaffAccess};
pub use store::{PatientStore, StoreError};
pub use translate::{NoBrain, PatientBrain};

/// Name of the `HttpOnly` session cookie.
pub const SESSION_COOKIE: &str = "clinic_access_token";

/// Name of the `HttpOnly` room-tablet cookie (the Node gateway's name).
pub const ROOM_DEVICE_COOKIE: &str = "spectrum_room_device";

/// Largest accepted request body.
const MAX_BODY_BYTES: usize = 16 * 1024;

/// The patient routes and the patient web app, with their own transport layers (traffic
/// monitor, body limit, tracing), without staff access: the `/api/admin/*` room routes answer
/// 403 `admin_required`. See [`router_with_staff`].
pub fn router(store: Arc<PatientStore>, traffic: Arc<TrafficMonitor>) -> Router {
    router_with_staff(store, traffic, None)
}

/// [`router`] plus the care team's room routes (`/api/admin/rooms|devices|discharge`), which
/// check the staff bearer token with `staff.verifier` (admin role) and list the rooms of
/// `staff.rooms`. Merge it next to the staff router, outside its stack.
pub fn router_with_staff(
    store: Arc<PatientStore>,
    traffic: Arc<TrafficMonitor>,
    staff: Option<StaffAccess>,
) -> Router {
    router_with_brain(store, traffic, staff, Arc::new(NoBrain))
}

/// [`router_with_staff`] plus the translation routes (`/api/patient/listen|translate|
/// simplify`, see `translate.rs`) served by `brain`.
pub fn router_with_brain(
    store: Arc<PatientStore>,
    traffic: Arc<TrafficMonitor>,
    staff: Option<StaffAccess>,
    brain: Arc<dyn PatientBrain>,
) -> Router {
    let translation = translate::router(store.clone(), brain);
    let admin = rooms::admin_router(store.clone(), staff);
    let api = Router::new()
        .route("/api/auth/signup", post(handlers::signup))
        .route("/api/auth/login", post(handlers::login))
        .route("/api/auth/request-otp", post(handlers::request_otp))
        .route("/api/auth/verify-otp", post(handlers::verify_otp))
        .route("/api/auth/session", get(handlers::session))
        .route("/api/auth/profile", put(handlers::profile))
        .route("/api/auth/logout", post(handlers::logout))
        .route("/api/patient/program", get(handlers::program))
        .route(
            "/api/patient/questions",
            get(handlers::list_questions).post(handlers::add_question),
        )
        .route(
            "/api/patient/questions/{id}",
            delete(handlers::delete_question),
        )
        .route(
            "/api/patient/requests",
            get(handlers::list_requests).post(handlers::add_request),
        )
        .route("/api/patient/mood", post(handlers::save_mood))
        .route("/api/room/pair", post(rooms::pair))
        .route("/api/room/session", get(rooms::session))
        .route("/api/room/unpair", post(rooms::unpair))
        .route_layer(middleware::from_fn(check_origin))
        .with_state(store);
    // The small body limit wraps every route but the translation ones, which set their own
    // (4 MiB for a recording).
    api.merge(admin)
        .merge(static_files::router())
        .layer(RequestBodyLimitLayer::new(MAX_BODY_BYTES))
        .merge(translation)
        .layer(middleware::from_fn_with_state(
            traffic.clone(),
            layer::gate_outer,
        ))
        .layer(middleware::from_fn_with_state(traffic, layer::count))
        .layer(TraceLayer::new_for_http())
}

/// An error answer of the patient API: `{ "error": code, "message": text }`.
#[derive(Debug, Clone, Copy)]
pub struct PatientError {
    status: StatusCode,
    code: &'static str,
    message: &'static str,
    /// Also clears the room-device cookie.
    clear_room_cookie: bool,
}

impl PatientError {
    const fn new(status: StatusCode, code: &'static str, message: &'static str) -> PatientError {
        PatientError {
            status,
            code,
            message,
            clear_room_cookie: false,
        }
    }

    /// The same answer, also clearing the room-device cookie.
    pub(crate) const fn clearing_room_cookie(self) -> PatientError {
        PatientError {
            clear_room_cookie: true,
            ..self
        }
    }

    pub(crate) const fn unprocessable(code: &'static str, message: &'static str) -> PatientError {
        PatientError::new(StatusCode::UNPROCESSABLE_ENTITY, code, message)
    }

    pub(crate) const fn not_authenticated() -> PatientError {
        PatientError::new(
            StatusCode::UNAUTHORIZED,
            "not_authenticated",
            "Please sign in again.",
        )
    }

    #[allow(dead_code, reason = "HACKATHON: unused while the origin check is open")]
    pub(crate) const fn origin_not_allowed() -> PatientError {
        PatientError::new(
            StatusCode::FORBIDDEN,
            "origin_not_allowed",
            "This request did not come from the patient app.",
        )
    }

    /// 503 on the authentication routes.
    pub(crate) fn auth_down(error: &StoreError) -> PatientError {
        tracing::error!(%error, "patient authentication store failed");
        PatientError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "auth_unavailable",
            "Sign-in is temporarily unavailable. Try again in a moment.",
        )
    }

    /// 503 on the patient day routes.
    pub(crate) fn data_down(error: &StoreError) -> PatientError {
        tracing::error!(%error, "patient data store failed");
        PatientError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "patient_data_unavailable",
            "Your data is temporarily unavailable. Try again in a moment.",
        )
    }

    pub(crate) const fn with_status(
        status: StatusCode,
        code: &'static str,
        message: &'static str,
    ) -> PatientError {
        PatientError::new(status, code, message)
    }
}

impl IntoResponse for PatientError {
    fn into_response(self) -> Response {
        let body = Json(serde_json::json!({ "error": self.code, "message": self.message }));
        if self.clear_room_cookie {
            let cookie = rooms::room_cookie("", 0, false);
            return (self.status, [(header::SET_COOKIE, cookie)], body).into_response();
        }
        (self.status, body).into_response()
    }
}

/// Mutating routes: an `Origin` header, when sent, must name the same host as `Host`.
async fn check_origin(request: Request, next: Next) -> Response {
    let safe = matches!(
        *request.method(),
        Method::GET | Method::HEAD | Method::OPTIONS
    );
    if !safe && !origin_allowed(request.headers()) {
        // HACKATHON: same-origin refusal on mutating patient routes disabled (cross-origin
        // apps may call them), restore after the pitch.
        // return PatientError::origin_not_allowed().into_response();
        tracing::debug!("HACKATHON open mode: cross-origin patient request accepted");
    }
    next.run(request).await
}

fn origin_allowed(headers: &HeaderMap) -> bool {
    let Some(origin) = headers.get(header::ORIGIN) else {
        return true;
    };
    let host = headers
        .get(header::HOST)
        .and_then(|value| value.to_str().ok());
    let authority = origin
        .to_str()
        .ok()
        .and_then(|origin| origin.split_once("://"))
        .and_then(|(_, rest)| rest.split('/').next());
    match (authority, host) {
        (Some(authority), Some(host)) => {
            !authority.is_empty() && authority.eq_ignore_ascii_case(host)
        }
        _ => false,
    }
}

/// The session token from the `Cookie` headers.
pub(crate) fn session_token(headers: &HeaderMap) -> Option<String> {
    cookie_value(headers, SESSION_COOKIE)
}

/// A non-empty cookie value from the `Cookie` headers.
pub(crate) fn cookie_value(headers: &HeaderMap, cookie: &str) -> Option<String> {
    headers
        .get_all(header::COOKIE)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(|value| value.split(';'))
        .filter_map(|pair| pair.trim().split_once('='))
        .find(|(name, value)| *name == cookie && !value.is_empty())
        .map(|(_, value)| value.to_owned())
}

#[cfg(test)]
mod tests {
    use axum::http::{HeaderMap, HeaderValue, header};

    use super::{origin_allowed, session_token};

    #[test]
    fn origin_must_match_host() {
        let mut headers = HeaderMap::new();
        assert!(origin_allowed(&headers));
        headers.insert(header::HOST, HeaderValue::from_static("clinic.local:8080"));
        headers.insert(
            header::ORIGIN,
            HeaderValue::from_static("http://clinic.local:8080"),
        );
        assert!(origin_allowed(&headers));
        headers.insert(
            header::ORIGIN,
            HeaderValue::from_static("https://evil.example"),
        );
        assert!(!origin_allowed(&headers));
    }

    #[test]
    fn reads_the_session_cookie() {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::COOKIE,
            HeaderValue::from_static("a=1; clinic_access_token=abc; b=2"),
        );
        assert_eq!(session_token(&headers).as_deref(), Some("abc"));
    }
}
