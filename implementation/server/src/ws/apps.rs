//! `GET /ws`: the application event stream.
//!
//! The `Origin` header is checked before the upgrade. The token never travels in the URL:
//! the client's first message must be `{"type":"auth","token":"…"}` within
//! `APP_AUTH_TIMEOUT_S` (5 s). A missing, late, malformed or refused auth message closes the
//! socket with code 4401 and a reason that says which. A token in the query string is
//! ignored. Once authenticated, the client receives a `snapshot`, then events. A client too
//! slow to keep up receives `resync` and a fresh `snapshot`; it never blocks the hub. A client
//! whose socket takes no event for [`APP_SEND_TIMEOUT`] is disconnected.
//!
//! Task A8: `security.alert` goes to admin sockets only; a socket whose address gets blocked
//! (`POST /security/blocks`) is closed at once with [`BLOCKED_CLOSE_CODE`].

use std::time::Duration;

use axum::extract::State;
use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::http::HeaderMap;
use axum::response::Response;
use domain::{Actor, ErrorBody, Role};
use realtime::{
    APP_AUTH_CLOSE_CODE, APP_AUTH_TIMEOUT_S, AppEvent, AppUp, Envelope, MAX_MESSAGE_BYTES,
};
use security::{ClientIdentity, ClientNetwork};
use tokio::sync::broadcast::error::RecvError;

use crate::error::ApiError;
use crate::extractors::Network;
use crate::state::AppState;

/// How long one event may take to reach a client's socket. A client that stops reading
/// fills its socket buffer; after this delay it is disconnected rather than kept forever (the
/// hub itself never waits: a lagging subscriber gets `resync` and a fresh snapshot).
pub const APP_SEND_TIMEOUT: Duration = Duration::from_secs(10);

/// Close code of a socket whose address was blocked while it was open (1008, policy
/// violation); the reason is `close_reason::BLOCKED`.
pub const BLOCKED_CLOSE_CODE: u16 = 1008;

/// Close reasons of the first-message authentication (sent with code 4401).
pub mod close_reason {
    /// No message within 5 s.
    pub const TIMEOUT: &str =
        "No auth message within 5 seconds. Send {\"type\":\"auth\",\"token\":\"...\"} first.";
    /// The first message was not an auth message.
    pub const NOT_AUTH: &str = "The first message must be {\"type\":\"auth\",\"token\":\"...\"}.";
    /// The token is unknown, expired or revoked.
    pub const REFUSED: &str = "The token was refused. Please sign in again.";
    /// A robot token on the application socket.
    pub const ROBOT: &str = "Robot tokens connect on /ws/robot/{id}, not /ws.";
    /// The token could not be checked now.
    pub const UNAVAILABLE: &str = "The server cannot check the token right now. Try again.";
    /// The address was blocked by an admin or by the server's detection rules (Task A8).
    pub const BLOCKED: &str = "Access from this address is blocked.";
}

/// Upgrades to the application event stream after checking `Origin`. Authentication happens
/// on the socket (first message).
#[utoipa::path(
    get,
    path = "/ws",
    tag = "live",
    responses(
        (status = 101, description = "Switching to WebSocket. First client message: {\"type\":\"auth\",\"token\"} within 5 s, else close 4401; then events follow contract C3"),
        (status = 403, description = "Origin not allowed (code `origin_not_allowed`)", body = ErrorBody)
    )
)]
pub async fn app_socket(
    State(state): State<AppState>,
    Network(network): Network,
    headers: HeaderMap,
    upgrade: WebSocketUpgrade,
) -> Result<Response, ApiError> {
    state.ws_origins.check(&headers)?;
    Ok(upgrade
        .max_message_size(MAX_MESSAGE_BYTES)
        .on_upgrade(move |socket| serve_app(state, network, socket)))
}

/// Authenticates, then pumps hub events to one application until either side closes.
async fn serve_app(state: AppState, network: ClientNetwork, mut socket: WebSocket) {
    let ip = network.ip;
    // Watch the block rules from the start: a rule added during authentication counts.
    let mut blocks = state.traffic.subscribe_blocks();
    let identity = match authenticate(&state, network, &mut socket).await {
        Ok(identity) => identity,
        Err(reason) => {
            close_unauthorized(&mut socket, reason).await;
            return;
        }
    };
    // Subscribe before the snapshot so no event falls between the two.
    let mut events = state.hub.subscribe_apps();
    let admin = identity.verified.role == Role::Admin;
    if state.traffic.is_blocked(ip) {
        close_blocked(&mut socket).await;
        return;
    }
    if send_snapshot(&state, &mut socket).await.is_err() {
        return;
    }
    loop {
        tokio::select! {
            incoming = socket.recv() => match incoming {
                // Apps only listen after auth; anything they send except close is ignored.
                Some(Ok(Message::Close(_)) | Err(_)) | None => break,
                Some(Ok(_)) => {}
            },
            changed = blocks.changed() => {
                if changed.is_err() || state.traffic.is_blocked(ip) {
                    close_blocked(&mut socket).await;
                    break;
                }
            }
            event = events.recv() => match event {
                // `security.alert` is for admin sockets only.
                Ok(event) if event.admin_only() && !admin => {}
                Ok(event) => {
                    if send_event(&state, &mut socket, event).await.is_err() {
                        break;
                    }
                }
                Err(RecvError::Lagged(missed)) => {
                    tracing::warn!(missed, role = ?identity.verified.role, "app subscriber lagged; sending resync and snapshot");
                    if send_event(&state, &mut socket, AppEvent::Resync).await.is_err()
                        || send_snapshot(&state, &mut socket).await.is_err()
                    {
                        break;
                    }
                }
                Err(RecvError::Closed) => break,
            },
        }
    }
}

/// Waits for the first message and checks its token. Returns the close reason on failure.
async fn authenticate(
    state: &AppState,
    network: ClientNetwork,
    socket: &mut WebSocket,
) -> Result<ClientIdentity, &'static str> {
    // Pings and pongs are transport: skip them. Anything else first is not an auth message.
    let first_text = async {
        loop {
            match socket.recv().await {
                Some(Ok(Message::Ping(_) | Message::Pong(_))) => {}
                Some(Ok(Message::Text(text))) => return Some(text),
                _ => return None,
            }
        }
    };
    let text = tokio::time::timeout(Duration::from_secs(APP_AUTH_TIMEOUT_S), first_text)
        .await
        .map_err(|_| close_reason::TIMEOUT)?
        .ok_or(close_reason::NOT_AUTH)?;
    let AppUp::Auth { token } =
        serde_json::from_str::<AppUp>(text.as_str()).map_err(|_| close_reason::NOT_AUTH)?;
    let verified = state
        .verifier
        .verify(&token)
        .await
        .map_err(|_| close_reason::UNAVAILABLE)?
        .ok_or(close_reason::REFUSED)?;
    if matches!(verified.subject_id, Actor::Robot(_)) {
        return Err(close_reason::ROBOT);
    }
    Ok(ClientIdentity { verified, network })
}

/// Closes a socket whose address is now blocked (1008, no other detail).
async fn close_blocked(socket: &mut WebSocket) {
    let frame = CloseFrame {
        code: BLOCKED_CLOSE_CODE,
        reason: close_reason::BLOCKED.into(),
    };
    if socket.send(Message::Close(Some(frame))).await.is_err() {
        tracing::debug!("app socket closed before the blocked close frame");
    }
}

/// Closes with 4401 and a reason that says what was wrong.
async fn close_unauthorized(socket: &mut WebSocket, reason: &'static str) {
    let frame = CloseFrame {
        code: APP_AUTH_CLOSE_CODE,
        reason: reason.into(),
    };
    if socket.send(Message::Close(Some(frame))).await.is_err() {
        tracing::debug!("app socket closed before the 4401 close frame");
    }
}

/// Sends the current snapshot (active tasks and live positions).
async fn send_snapshot(state: &AppState, socket: &mut WebSocket) -> Result<(), ()> {
    match state.snapshot_event().await {
        Ok(event) => send_event(state, socket, event).await,
        Err(error) => {
            tracing::warn!(
                code = error.code(),
                "cannot build the app snapshot; closing the socket"
            );
            Err(())
        }
    }
}

/// Wraps one event in an envelope and writes it as a text frame.
async fn send_event(state: &AppState, socket: &mut WebSocket, event: AppEvent) -> Result<(), ()> {
    let envelope = Envelope::new(event, state.clock.now());
    let text = realtime::encode(&envelope).map_err(|error| {
        tracing::warn!(%error, "cannot encode an app event; closing the socket");
    })?;
    let sending = socket.send(Message::Text(text.into()));
    if let Ok(sent) = tokio::time::timeout(APP_SEND_TIMEOUT, sending).await {
        sent.map_err(|_| ())
    } else {
        tracing::warn!(
            "app socket did not take an event within {} s; closing it (the client reconnects \
             and gets a fresh snapshot)",
            APP_SEND_TIMEOUT.as_secs()
        );
        Err(())
    }
}
