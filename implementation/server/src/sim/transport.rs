//! The two ways a simulated robot reaches the server: a WebSocket on `/ws/robot/{id}`
//! ([`WsTransport`], the `fake_robot` binary) and the hub's in-process link ([`HubTransport`],
//! the robots of `--mock`). Both carry the same contract C2 messages.

use std::sync::Arc;

use async_trait::async_trait;
use chrono::Utc;
use domain::{Clock, RobotId};
use futures_util::{SinkExt as _, StreamExt as _};
use realtime::{Envelope, RealtimeError, RobotDown, RobotLink, RobotUp};
use tokio::net::TcpStream;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::client::IntoClientRequest as _;
use tokio_tungstenite::tungstenite::http::HeaderValue;
use tokio_tungstenite::tungstenite::http::header::AUTHORIZATION;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

use super::SimError;
use super::driver::RobotTransport;

/// The socket side of a hub robot session, used by an in-process simulated robot.
pub struct HubTransport {
    link: RobotLink,
    robot: RobotId,
    clock: Arc<dyn Clock>,
}

impl HubTransport {
    /// Wraps the link of `robot`'s session; envelopes are stamped with `clock`.
    #[must_use]
    pub fn new(link: RobotLink, robot: RobotId, clock: Arc<dyn Clock>) -> HubTransport {
        HubTransport { link, robot, clock }
    }
}

#[async_trait]
impl RobotTransport for HubTransport {
    async fn send(&mut self, up: RobotUp) -> Result<(), SimError> {
        match self.link.push_up(Envelope::new(up, self.clock.now())) {
            Ok(()) => Ok(()),
            // The service is behind: a dropped state is replaced by the next one.
            Err(RealtimeError::QueueFull { .. }) => {
                tracing::debug!(robot = %self.robot, "simulated robot message dropped: the robot service is behind");
                Ok(())
            }
            Err(error) => Err(SimError::Hub(error)),
        }
    }

    async fn recv(&mut self) -> Result<Option<RobotDown>, SimError> {
        Ok(self.link.next_down().await.map(|envelope| envelope.body))
    }
}

/// A robot WebSocket (`fake_robot`).
pub struct WsTransport {
    stream: WebSocketStream<MaybeTlsStream<TcpStream>>,
}

impl WsTransport {
    /// Connects to `<server>/ws/robot/<robot>` with the robot token as a bearer token.
    ///
    /// # Errors
    /// `SimError::Connect` when the URL is wrong, the server is not reachable or refuses the
    /// upgrade (for example 401 for a wrong token).
    pub async fn connect(
        server: &str,
        robot: &RobotId,
        token: &str,
    ) -> Result<WsTransport, SimError> {
        let url = format!("{}/ws/robot/{robot}", server.trim_end_matches('/'));
        let connect_error = |reason: String| SimError::Connect {
            url: url.clone(),
            reason,
        };
        let mut request = url
            .as_str()
            .into_client_request()
            .map_err(|error| connect_error(error.to_string()))?;
        let bearer = HeaderValue::from_str(&format!("Bearer {token}")).map_err(|_| {
            connect_error("the token contains characters a header cannot carry".to_owned())
        })?;
        request.headers_mut().insert(AUTHORIZATION, bearer);
        let (stream, _response) = tokio_tungstenite::connect_async(request)
            .await
            .map_err(|error| connect_error(error.to_string()))?;
        Ok(WsTransport { stream })
    }
}

#[async_trait]
impl RobotTransport for WsTransport {
    async fn send(&mut self, up: RobotUp) -> Result<(), SimError> {
        let text = realtime::encode(&Envelope::new(up, Utc::now()))?;
        self.stream
            .send(Message::text(text))
            .await
            .map_err(|error| SimError::Transport {
                reason: error.to_string(),
            })
    }

    async fn recv(&mut self) -> Result<Option<RobotDown>, SimError> {
        loop {
            match self.stream.next().await {
                None | Some(Ok(Message::Close(None))) => return Ok(None),
                Some(Err(error)) => {
                    return Err(SimError::Transport {
                        reason: error.to_string(),
                    });
                }
                Some(Ok(Message::Text(text))) => match realtime::decode_robot_down(text.as_bytes())
                {
                    Ok(envelope) => return Ok(Some(envelope.body)),
                    Err(error) => tracing::warn!(%error, "server message ignored"),
                },
                Some(Ok(Message::Close(Some(frame)))) => {
                    let code = u16::from(frame.code);
                    if code == 1000 {
                        return Ok(None);
                    }
                    return Err(SimError::Closed {
                        code,
                        reason: frame.reason.as_str().to_owned(),
                    });
                }
                Some(Ok(_)) => {}
            }
        }
    }
}
