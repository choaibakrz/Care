//! The OpenAPI document (contract C3), built from derives only.
//!
//! `clinic-server --print-openapi` and `GET /openapi.json` serve it; Scalar renders it at
//! `/docs`. Nothing here may call a service, so it works on a bare checkout.

use axum::Json;
use utoipa::openapi::security::{Http, HttpAuthScheme, SecurityScheme};
use utoipa::{Modify, OpenApi};

use crate::routes;
use crate::ws;

/// The API description: every route of C3, `/health`, the WebSockets, and their schemas.
#[derive(OpenApi)]
#[openapi(
    info(
        title = "Iris · Care backend",
        description = "Contract C3. Errors are always `{ \"error\": { \"code\", \"message\" } }`, \
                       plus `details: [{path, problem}]` when a whole document was checked. \
                       All data in this project is invented."
    ),
    paths(
        routes::health::health,
        routes::auth::login,
        routes::auth::derivation,
        routes::auth::enrol,
        routes::auth::issue_enrolment_code,
        routes::auth::list_accounts,
        routes::auth::disable_account,
        routes::auth::me,
        routes::map::put_my_location,
        routes::map::post_my_scans,
        routes::tasks::create,
        routes::tasks::list,
        routes::tasks::get,
        routes::tasks::cancel,
        routes::tasks::route,
        routes::inventory::list,
        routes::inventory::adjust,
        routes::map::get_map,
        routes::map::get_live,
        routes::clinics::list,
        routes::clinics::create,
        routes::clinics::get,
        routes::clinics::update,
        routes::clinics::activate,
        routes::clinics::delete,
        routes::clinics::get_base,
        routes::clinics::put_base,
        routes::clinics::get_overlay,
        routes::clinics::put_overlay,
        routes::clinics::reset_overlay,
        routes::stats::heat,
        routes::stats::service,
        routes::system::get_mode,
        routes::system::put_mode,
        routes::monitor::summary,
        routes::monitor::traffic,
        routes::monitor::clients,
        routes::monitor::list_blocks,
        routes::monitor::add_block,
        routes::monitor::remove_block,
        routes::devices::list,
        routes::devices::disconnect,
        routes::devices::assign,
        routes::brain::translate,
        routes::brain::simplify,
        routes::brain::summarise,
        routes::brain::report,
        routes::brain::health,
        routes::zones::list,
        routes::zones::upsert,
        routes::zones::delete,
        routes::robots::list,
        routes::robots::command,
        routes::robots::revert,
        routes::robots::teleport,
        routes::fleet::get_home,
        routes::fleet::put_home,
        routes::schedules::list,
        routes::schedules::update,
        routes::audit::list,
        routes::audit::integrity,
        routes::incidents::list,
        routes::incidents::ack,
        routes::incidents::close,
        routes::devices::report_event,
        ws::apps::app_socket,
        ws::robots::robot_socket,
    ),
    modifiers(&BearerAuth),
    tags(
        (name = "health", description = "Liveness"),
        (name = "auth", description = "Login and identity. Pseudonymous accounts (Task A7): the server never receives a user name or a password, only the key the client derives (docs/accounts.md)"),
        (name = "accounts", description = "Account administration (admin): enrolment codes, pseudonyms and tags, disabling. No user name exists on the server"),
        (name = "tasks", description = "Task queue: the server creates tasks, never motor commands"),
        (name = "inventory", description = "Stock of the reserve"),
        (name = "map", description = "3D clinic map, live positions, tablet rooms"),
        (name = "clinics", description = "Editable clinic plans (admin): one versioned document per clinic, one active"),
        (name = "stats", description = "Fleet statistics (admin): the heat map (robots only) and service counts (never a person)"),
        (name = "system", description = "Emergency mode (Task A8): one switch; off the allow-list every request is 503 emergency_mode, robots clear the corridors, patient alarms are never touched"),
        (name = "monitor", description = "Monitoring, attack detection and address blocks (admin, Task A8): addresses and counts only, memory only; never refuses an authenticated admin's robot command"),
        (name = "devices", description = "The tablet registry (admin, Task A8): staff pseudonyms and beds, never patients"),
        (name = "brain", description = "Server-side brain (Task A6): translate, simplify, summarise, report. Every result is a draft a staff member reads first; texts are processed in memory only, never stored, logged or journaled"),
        (name = "zones", description = "Deaf and restricted zones"),
        (name = "robots", description = "Robots and commands; estop is admin only; a non-admin's command raises an admin alert and can be reverted by the admin"),
        (name = "schedules", description = "Night restock round"),
        (name = "audit", description = "Audit trail (admin)"),
        (name = "incidents", description = "Incidents on the 3D map"),
        (name = "live", description = "WebSockets")
    )
)]
pub struct ApiDoc;

/// Declares the `bearer` security scheme used by `security(("bearer" = []))`.
struct BearerAuth;

impl Modify for BearerAuth {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        if let Some(components) = openapi.components.as_mut() {
            components.add_security_scheme(
                "bearer",
                SecurityScheme::Http(Http::new(HttpAuthScheme::Bearer)),
            );
        }
    }
}

/// `GET /openapi.json`: the same document as `--print-openapi`.
pub async fn openapi_json() -> Json<utoipa::openapi::OpenApi> {
    Json(ApiDoc::openapi())
}
