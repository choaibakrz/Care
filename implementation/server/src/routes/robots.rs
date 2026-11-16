//! `GET /robots`, `POST /robots/{id}/command`, `POST /robots/{id}/commands/{command_id}/revert`.
//!
//! There is no route that moves a robot. Commands are `pause`, `resume`, `dock` (permission
//! `robot_control`, they go through the robot's gardien), `shutdown` (permission
//! `robot_shutdown`, admin only, ruling R24) and `estop` (permission `estop`, admin only),
//! which takes its own code path: `EstopPath::trigger`. After an emergency stop only an
//! admin's `resume` re-arms the robot (409 `estop_latched` for anyone else).

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use domain::{CommandName, ErrorBody, Permission, RobotId};
use uuid::Uuid;

use crate::dto::{CommandReceipt, CommandRequest, RevertReceipt, RobotView, TeleportRequest};
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authenticated, Authorized, perm};
use crate::state::AppState;

/// Every known robot with its last reported state; a robot never heard from is listed at its
/// seeded start position with `last_seen: null`.
#[utoipa::path(
    get,
    path = "/robots",
    tag = "robots",
    responses((status = 200, description = "Robots", body = Vec<RobotView>)),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewRobots>,
) -> Result<Json<Vec<RobotView>>, ApiError> {
    Ok(Json(state.robots.list().await?))
}

/// Sends a command to one robot. `estop` needs the `estop` permission and is sent before
/// anything else, even when the dispatcher or the journal is stuck.
///
/// 200 `{accepted, reason, sent_at, command, command_id}` when the command reached the
/// robot's connection. A command from a non-admin (a nurse may pause, resume, dock) raises the
/// admin alert `staff_command` with its `command_id`, which the admin may revert; a
/// refusal is 409 with a readable message. `shutdown` is admin only (403 `forbidden` naming
/// `robot_shutdown`). While a robot is in `estop`, a non-admin `resume` is 409
/// `estop_latched` "Only an admin can re-arm a robot after an emergency stop." An estop to an
/// offline robot is 409 "Robot X is offline: the stop was not delivered. Use the physical
/// button."
#[utoipa::path(
    post,
    path = "/robots/{id}/command",
    tag = "robots",
    params(("id" = String, Path, description = "Robot id")),
    request_body = CommandRequest,
    responses(
        (status = 200, description = "Command sent", body = CommandReceipt),
        (status = 403, description = "Permission missing", body = ErrorBody),
        (status = 404, description = "No such robot", body = ErrorBody),
        (status = 409, description = "Refused (`estop_latched`, …), or robot offline (estop not delivered)", body = ErrorBody),
        (status = 503, description = "Journal unavailable (not for estop)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn command(
    State(state): State<AppState>,
    Authenticated(identity): Authenticated,
    ApiPath(robot): ApiPath<RobotId>,
    ApiJson(body): ApiJson<CommandRequest>,
) -> Result<Json<CommandReceipt>, ApiError> {
    if body.name == CommandName::Estop {
        if !identity.verified.role.allows(Permission::Estop) {
            return Err(ApiError::forbidden(Permission::Estop));
        }
        return Ok(Json(state.robots.estop(&identity, &robot).await?));
    }
    if body.name == CommandName::Shutdown
        && !identity.verified.role.allows(Permission::RobotShutdown)
    {
        return Err(ApiError::forbidden(Permission::RobotShutdown));
    }
    if !identity.verified.role.allows(Permission::RobotControl) {
        return Err(ApiError::forbidden(Permission::RobotControl));
    }
    Ok(Json(
        state.robots.command(&identity, &robot, body.name).await?,
    ))
}

/// Reverts a robot command a non-admin sent (admin, Task A7): sends the inverse command
/// (`pause` -> `resume`, `resume` -> `pause`, `dock` -> `resume`) and journals the revert. An
/// emergency stop is admin-only and never revertible this way; a shutdown (admin only)
/// cannot be undone from the server. Only the robot's latest command can be reverted (409
/// `superseded` otherwise); nothing is reverted on a robot in `estop` (409 `estop_latched`:
/// the admin re-arms it with an explicit `resume`); two concurrent reverts of one command
/// send one inverse (the other is 409 `already_reverted`).
#[utoipa::path(
    post,
    path = "/robots/{id}/commands/{command_id}/revert",
    tag = "robots",
    params(
        ("id" = String, Path, description = "Robot id"),
        ("command_id" = String, Path, description = "The `command_id` of the receipt or of the `staff_command` alert")
    ),
    responses(
        (status = 202, description = "Inverse command sent", body = RevertReceipt),
        (status = 403, description = "Permission missing (admin only)", body = ErrorBody),
        (status = 404, description = "No such command for this robot", body = ErrorBody),
        (status = 409, description = "`not_revertible`, `already_reverted`, `superseded`, `estop_latched` or `robot_offline`", body = ErrorBody),
        (status = 503, description = "Journal unavailable", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn revert(
    State(state): State<AppState>,
    auth: Authorized<perm::RevertCommand>,
    ApiPath((robot, command_id)): ApiPath<(RobotId, Uuid)>,
) -> Result<(StatusCode, Json<RevertReceipt>), ApiError> {
    let receipt = state
        .robots
        .revert(&auth.identity, &robot, command_id)
        .await?;
    Ok((StatusCode::ACCEPTED, Json(receipt)))
}

/// Moves a simulated robot to a point (admin; a testing tool for the simulated fleet). The
/// robot then wanders on from there (its route is planned again).
///
/// 200 with the updated robot (also published as `robot.updated`). 409 `not_simulated` for a
/// real robot; 422 when the point is outside the floor outline or inside a restricted zone.
#[utoipa::path(
    post,
    path = "/robots/{id}/teleport",
    tag = "robots",
    params(("id" = String, Path, description = "Robot id")),
    request_body = TeleportRequest,
    responses(
        (status = 200, description = "Robot moved", body = RobotView),
        (status = 403, description = "Admin only", body = ErrorBody),
        (status = 404, description = "No such robot", body = ErrorBody),
        (status = 409, description = "`not_simulated`: a real robot is never teleported", body = ErrorBody),
        (status = 422, description = "Outside the floor outline or inside a restricted zone", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn teleport(
    State(state): State<AppState>,
    _auth: Authorized<perm::EditClinics>,
    ApiPath(robot): ApiPath<RobotId>,
    ApiJson(body): ApiJson<TeleportRequest>,
) -> Result<Json<RobotView>, ApiError> {
    Ok(Json(state.robots.teleport(&robot, body).await?))
}
