//! Clinic server library: builds the router from the application state.
//!
//! The server creates tasks, never motor commands. There is no "drive to x, y" route; the
//! emergency stop is the only command that bypasses the dispatcher (see `services::robots`).

pub mod admin_web;
pub mod brain_process;
pub mod config;
pub mod dto;
pub mod emergency_mirror;
pub mod emergency_mode;
pub mod error;
pub mod extractors;
pub mod openapi;
pub mod patient;
pub mod routes;
pub mod services;
pub mod sim;
pub mod state;
pub mod ws;

use axum::Router;
use axum::extract::{Request, State};
use axum::http::{Method, header};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse as _, Response};
use axum::routing::{delete, get, post, put};
use security::{MockStack, SecurityStack};
use utoipa::OpenApi as _;
use utoipa_scalar::{Scalar, Servable as _};

use crate::error::ApiError;
use crate::openapi::ApiDoc;
use crate::state::AppState;

/// Builds every route of contract C3, both WebSocket endpoints, `/docs` and `/openapi.json`.
///
/// The security stack is not applied here, so tests can exercise handlers directly; the
/// running server uses [`build_app`]. The journal guard (degraded mode) and the emergency
/// mode filter (Task A8, outermost: 503 `emergency_mode` off the allow-list) are applied
/// here because they are behaviour, not transport security.
pub fn build_router(state: AppState) -> Router {
    let api = Router::new()
        .route("/health", get(routes::health::health))
        .route("/auth/login", post(routes::auth::login))
        .route("/auth/derivation", get(routes::auth::derivation))
        .route("/auth/enrol", post(routes::auth::enrol))
        .route(
            "/admin/enrolment-codes",
            post(routes::auth::issue_enrolment_code),
        )
        .route("/admin/accounts", get(routes::auth::list_accounts))
        .route(
            "/admin/accounts/{account_tag}",
            delete(routes::auth::disable_account),
        )
        .route("/me", get(routes::auth::me))
        .route("/me/location", put(routes::map::put_my_location))
        .route("/me/scans", post(routes::map::post_my_scans))
        .route(
            "/tasks",
            post(routes::tasks::create).get(routes::tasks::list),
        )
        .route("/tasks/{id}", get(routes::tasks::get))
        .route("/tasks/{id}/cancel", post(routes::tasks::cancel))
        .route("/tasks/{id}/route", get(routes::tasks::route))
        .route("/inventory", get(routes::inventory::list))
        .route("/inventory/{item}/adjust", post(routes::inventory::adjust))
        .route("/map", get(routes::map::get_map))
        .route("/live", get(routes::map::get_live))
        .route(
            "/clinics",
            get(routes::clinics::list).post(routes::clinics::create),
        )
        .route(
            "/clinics/{id}",
            get(routes::clinics::get)
                .put(routes::clinics::update)
                .delete(routes::clinics::delete),
        )
        .route("/clinics/{id}/activate", post(routes::clinics::activate))
        .route(
            "/clinics/{id}/base",
            get(routes::clinics::get_base).put(routes::clinics::put_base),
        )
        .route(
            "/clinics/{id}/overlay",
            get(routes::clinics::get_overlay)
                .put(routes::clinics::put_overlay)
                .delete(routes::clinics::reset_overlay),
        )
        .route("/stats/heat", get(routes::stats::heat))
        .route("/brain/translate", post(routes::brain::translate))
        .route("/brain/simplify", post(routes::brain::simplify))
        .route("/brain/summarise", post(routes::brain::summarise))
        .route("/brain/report", post(routes::brain::report))
        .route("/brain/health", get(routes::brain::health))
        .route("/zones", get(routes::zones::list))
        .route(
            "/zones/{id}",
            put(routes::zones::upsert).delete(routes::zones::delete),
        )
        .route("/robots", get(routes::robots::list))
        .route("/robots/{id}/command", post(routes::robots::command))
        .route(
            "/robots/{id}/commands/{command_id}/revert",
            post(routes::robots::revert),
        )
        .route("/robots/{id}/teleport", post(routes::robots::teleport))
        .route(
            "/fleet/home",
            get(routes::fleet::get_home).put(routes::fleet::put_home),
        )
        .route("/schedules", get(routes::schedules::list))
        .route("/schedules/{id}", put(routes::schedules::update))
        .route("/audit", get(routes::audit::list))
        .route("/audit/integrity", get(routes::audit::integrity))
        .route("/incidents", get(routes::incidents::list))
        .route("/incidents/{id}/ack", post(routes::incidents::ack))
        .route("/incidents/{id}/close", post(routes::incidents::close))
        .route("/devices/me/events", post(routes::devices::report_event))
        .merge(console_routes())
        .route("/ws", get(ws::apps::app_socket))
        .route("/ws/robot/{id}", get(ws::robots::robot_socket))
        .route("/openapi.json", get(openapi::openapi_json))
        .fallback(error::fallback_not_found)
        .method_not_allowed_fallback(error::fallback_method_not_allowed)
        .route_layer(middleware::from_fn_with_state(state.clone(), journal_guard))
        .route_layer(middleware::from_fn_with_state(
            state.clone(),
            emergency_mode::emergency_filter,
        ))
        .with_state(state);
    let docs = Scalar::with_url("/docs", ApiDoc::openapi())
        .custom_html(DOCS_HTML.replace("$script", DOCS_SCRIPT_PATH))
        .title("Clinic server API");
    api.merge(docs)
        .merge(Router::new().route(DOCS_SCRIPT_PATH, get(docs_script)))
}

/// The routes the updated admin console needs (Task A8): service statistics, emergency mode,
/// monitoring and blocks, the tablet registry.
fn console_routes() -> Router<AppState> {
    Router::new()
        .route("/stats/service", get(routes::stats::service))
        .route(
            "/system/mode",
            get(routes::system::get_mode).put(routes::system::put_mode),
        )
        .route("/monitor/summary", get(routes::monitor::summary))
        .route("/monitor/traffic", get(routes::monitor::traffic))
        .route("/monitor/clients", get(routes::monitor::clients))
        .route(
            "/security/blocks",
            get(routes::monitor::list_blocks).post(routes::monitor::add_block),
        )
        .route(
            "/security/blocks/{id}",
            delete(routes::monitor::remove_block),
        )
        .route("/devices", get(routes::devices::list))
        .route(
            "/devices/{id}/disconnect",
            post(routes::devices::disconnect),
        )
        .route("/devices/{id}/assign", post(routes::devices::assign))
}

/// Where `/docs` loads Scalar's script from: served by this server, never from a CDN, so the
/// docs page works offline (ruling R5).
pub const DOCS_SCRIPT_PATH: &str = "/docs/scalar-standalone.js";

/// Scalar's API reference bundle (`@scalar/api-reference` 1.76.4, `dist/browser/
/// standalone.js`, MIT licence, Copyright (c) 2023-present Scalar). Vendored unchanged in
/// `static/scalar/` with its licence; see `LICENCES.md` at the repository root.
static SCALAR_SCRIPT: &[u8] = include_bytes!("../static/scalar/standalone.js");

/// The `/docs` page: the OpenAPI document inlined (`$spec`, filled by `utoipa-scalar`) and
/// rendered by the local Scalar script (`$script`, replaced by [`DOCS_SCRIPT_PATH`]). Default web fonts and telemetry are off, so the page
/// makes no request outside this server.
const DOCS_HTML: &str = r#"<!doctype html>
<html lang="en">
<head>
  <title>$title</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
</head>
<body>
  <div id="app"></div>
  <script id="clinic-openapi" type="application/json">$spec</script>
  <script src="$script"></script>
  <script>
    const spec = JSON.parse(document.getElementById('clinic-openapi').textContent);
    Scalar.createApiReference('#app', {
      content: spec,
      withDefaultFonts: false,
      telemetry: false,
    });
  </script>
</body>
</html>
"#;

/// Serves the vendored Scalar script.
async fn docs_script() -> Response {
    (
        [
            (header::CONTENT_TYPE, "text/javascript; charset=utf-8"),
            (header::CACHE_CONTROL, "public, max-age=86400"),
        ],
        SCALAR_SCRIPT,
    )
        .into_response()
}

/// The running server: [`build_router`] wrapped in the security stack (Task 7 layer order)
/// with the state's traffic monitor (Task A8: counters, rate limit, blocks).
pub fn build_app(state: AppState, security: &SecurityStack) -> Router {
    let traffic = state.traffic.clone();
    let patients = patient_routes(&state, &traffic);
    security
        .apply_monitored(build_router(state), traffic)
        .merge(patients)
        .merge(admin_web::router())
}

/// `clinic-server --mock`: [`build_router`] wrapped in the mock transport stack (CORS,
/// request limits, bearer identity on the mock tokens; no known-network check) and, since
/// Task A8, the state's traffic monitor (counters, rate limit, blocks:
/// `MockStack::apply_monitored`). Never used by the live server.
pub fn build_mock_app(state: AppState, transport: &MockStack) -> Router {
    let traffic = state.traffic.clone();
    let patients = patient_routes(&state, &traffic);
    transport
        .apply_monitored(build_router(state), traffic)
        .merge(patients)
        .merge(admin_web::router())
}

/// The patient companion API and web app (`/api/*`, `/patient/`), outside the staff
/// security stack: patients sign in with a cookie from any network (see [`patient`]).
/// The built admin console (`/admin/`, [`admin_web`]) is merged next to it in both apps.
/// The room panel (`/api/admin/*`) checks staff bearer tokens with the state's verifier and
/// lists the rooms of the active clinic map.
fn patient_routes(state: &AppState, traffic: &std::sync::Arc<security::TrafficMonitor>) -> Router {
    let staff = patient::StaffAccess {
        verifier: state.verifier.clone(),
        rooms: std::sync::Arc::new(patient::MapRooms(state.map.clone())),
    };
    patient::router_with_brain(
        std::sync::Arc::new(patient::PatientStore::from_env()),
        traffic.clone(),
        Some(staff),
        state.brain_client.clone(),
    )
    // HACKATHON: no CORS on the patient routes (same-origin only) disabled: any origin may
    // call them, with the session cookie, restore after the pitch.
    .layer(security::cors::open_layer())
}

/// Degraded mode (Task 9): when the journal cannot write, every mutating route answers 503
/// `journal_unavailable`, because an action that cannot be recorded must not happen.
///
/// The robot command route is exempt here: the emergency stop must always be sent (its record
/// goes to the emergency fallback file). `RobotService::command` refuses the other commands
/// itself while the journal is down.
async fn journal_guard(State(state): State<AppState>, request: Request, next: Next) -> Response {
    let mutating = !matches!(
        *request.method(),
        Method::GET | Method::HEAD | Method::OPTIONS
    );
    let path = request.uri().path();
    let robot_command = path.starts_with("/robots/") && path.ends_with("/command");
    if mutating && !robot_command && !state.journal.is_writable() {
        return ApiError::journal_unavailable().into_response();
    }
    next.run(request).await
}

#[cfg(test)]
mod tests {
    #[test]
    fn workspace_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
