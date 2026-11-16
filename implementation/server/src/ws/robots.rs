//! `GET /ws/robot/{id}`: one WebSocket per robot (contract C2).
//!
//! The robot authenticates with its bearer token (`TokenSubject::Robot`) through the security
//! stack. After the upgrade:
//! - a token for another robot closes with 4403 ("Token belongs to robot X but the connection
//!   asks for robot Y."),
//! - an unknown robot id closes with 4404 naming it.
//!
//! This handler is a pump: socket frames go up into the robot's session, queued messages go
//! down to the socket (the emergency stop first). The robot logic runs in
//! `RobotService::run_session`. Unknown message types are logged and ignored, never fatal.

use axum::extract::State;
use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::response::Response;
use domain::{Actor, ErrorBody, RobotId};
use realtime::{CloseReason, MAX_MESSAGE_BYTES, authorize_robot, decode_robot_up};

use crate::error::{ApiError, ApiPath};
use crate::extractors::Authenticated;
use crate::state::AppState;

/// Upgrades a robot connection; identity checks that need a close code happen after upgrade.
#[utoipa::path(
    get,
    path = "/ws/robot/{id}",
    tag = "live",
    params(("id" = String, Path, description = "Robot id")),
    responses(
        (status = 101, description = "Switching to WebSocket; messages follow contract C2. Closes 4403 on a token for another robot, 4404 for an unknown robot"),
        (status = 401, description = "Missing or invalid robot token", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn robot_socket(
    State(state): State<AppState>,
    Authenticated(identity): Authenticated,
    ApiPath(robot): ApiPath<RobotId>,
    upgrade: WebSocketUpgrade,
) -> Result<Response, ApiError> {
    let known = state.robots.is_known(&robot).await?;
    let token_robot = match &identity.verified.subject_id {
        Actor::Robot(id) => Some(id.clone()),
        _ => None,
    };
    let ip = identity.network.ip;
    Ok(upgrade
        .max_message_size(MAX_MESSAGE_BYTES)
        .on_upgrade(move |socket| serve_robot(state, robot, token_robot, known, ip, socket)))
}

/// Runs one robot connection until the socket closes.
async fn serve_robot(
    state: AppState,
    robot: RobotId,
    token_robot: Option<RobotId>,
    known: bool,
    ip: std::net::IpAddr,
    mut socket: WebSocket,
) {
    let authorized = match &token_robot {
        Some(token_robot) => authorize_robot(token_robot, &robot),
        None => Err(CloseReason::not_a_robot()),
    };
    if let Err(reason) = authorized {
        close(&mut socket, reason).await;
        return;
    }
    if !known {
        close(&mut socket, CloseReason::unknown_robot(&robot)).await;
        return;
    }
    let mut session = match state.hub.register_robot(robot.clone()) {
        Ok(session) => session,
        Err(error) => {
            close(&mut socket, CloseReason::from_realtime(&error)).await;
            return;
        }
    };
    let Some(mut link) = session.take_link() else {
        tracing::error!(%robot, "robot session has no socket link; closing");
        state.hub.unregister_robot(&robot);
        return;
    };
    // Task A8 (R26): this address is the robot's own while the session lasts: never limited
    // or blocked, so the emergency stop always reaches it.
    let protection = state.traffic.robot_session_started(ip, robot.as_str());
    let robots = state.robots.clone();
    let service = tokio::spawn(async move { robots.run_session(session).await });

    loop {
        tokio::select! {
            incoming = socket.recv() => match incoming {
                Some(Ok(Message::Text(text))) => match decode_robot_up(text.as_bytes()) {
                    Ok(envelope) => {
                        if link.push_up(envelope).is_err() {
                            break;
                        }
                    }
                    Err(error) => tracing::warn!(%robot, %error, "robot message ignored"),
                },
                Some(Ok(Message::Binary(_))) => {
                    tracing::warn!(%robot, "binary robot frame ignored; contract C2 is JSON text");
                }
                Some(Ok(Message::Close(_)) | Err(_)) | None => break,
                Some(Ok(Message::Ping(_) | Message::Pong(_))) => {}
            },
            down = link.next_down() => match down {
                Some(envelope) => match realtime::encode(&envelope) {
                    Ok(text) => {
                        if socket.send(Message::Text(text.into())).await.is_err() {
                            break;
                        }
                    }
                    Err(error) => tracing::error!(%robot, %error, "cannot encode a robot message"),
                },
                None => break,
            },
        }
    }

    // This session's protection only (R27): a reconnect that already started keeps its own.
    state
        .traffic
        .robot_session_ended(ip, robot.as_str(), protection);
    state.hub.unregister_robot(&robot);
    service.abort();
    state.robots.on_disconnect(&robot).await;
}

/// Sends a close frame with an application close code (4403, 4404, …).
async fn close(socket: &mut WebSocket, reason: CloseReason) {
    let frame = CloseFrame {
        code: reason.code(),
        reason: reason.text().to_owned().into(),
    };
    if socket.send(Message::Close(Some(frame))).await.is_err() {
        tracing::debug!("robot socket already gone before the close frame");
    }
}
