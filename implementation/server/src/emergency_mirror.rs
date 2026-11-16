//! Read-only mirror of the emergency service's alarms (Task 11c).
//!
//! It only listens: there is no method to acknowledge or create an alarm. That happens only in
//! the emergency service, which keeps working when this server is down. Alarms become
//! `EmergencyAlarm` incidents on their room; 10 s of silence raises `EmergencyLinkDown` so the
//! map never looks calm because the link is broken.

use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::incident::{AlarmLevel, IncidentCode};
use domain::{Clock, PlaceId};
use futures_util::StreamExt as _;
use serde::Deserialize;
use tokio::sync::watch;
use tokio::task::JoinHandle;

use crate::services::incidents::IncidentBoard;

/// Silence after which the link is reported down.
pub const LINK_SILENCE_LIMIT: Duration = Duration::from_secs(10);

/// Where to listen.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EmergencyMirrorConfig {
    /// Status stream URL of the emergency service (LAN).
    pub status_url: String,
    /// Silence limit (default 10 s).
    pub silence: Duration,
}

/// What the mirror currently knows of the link.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MirrorStatus {
    /// Receiving.
    pub connected: bool,
    /// Last message.
    pub last_message_at: Option<DateTime<Utc>>,
}

/// The mirror.
pub struct EmergencyMirror {
    config: EmergencyMirrorConfig,
    board: Arc<IncidentBoard>,
    clock: Arc<dyn Clock>,
    status: watch::Sender<MirrorStatus>,
}

/// Longest wait between two connection attempts.
const MAX_BACKOFF: Duration = Duration::from_secs(10);

/// One alarm of the status stream: `{"type":"alarm","alarm_id","room","level"}`.
#[derive(Debug, Deserialize)]
struct AlarmMessage {
    #[serde(rename = "type")]
    kind: String,
    #[serde(default)]
    room: Option<String>,
    #[serde(default)]
    level: Option<AlarmLevel>,
}

impl EmergencyMirror {
    /// A mirror raising incidents on `board`.
    #[must_use]
    pub fn new(
        config: EmergencyMirrorConfig,
        board: Arc<IncidentBoard>,
        clock: Arc<dyn Clock>,
    ) -> EmergencyMirror {
        let (status, _) = watch::channel(MirrorStatus {
            connected: false,
            last_message_at: None,
        });
        EmergencyMirror {
            config,
            board,
            clock,
            status,
        }
    }

    /// Listens until aborted, reconnecting with back-off.
    #[must_use]
    pub fn spawn(self: Arc<Self>) -> JoinHandle<()> {
        tokio::spawn(async move {
            let mut backoff = Duration::from_millis(250);
            loop {
                match tokio::time::timeout(
                    self.config.silence,
                    tokio_tungstenite::connect_async(self.config.status_url.as_str()),
                )
                .await
                {
                    Ok(Ok((stream, _))) => {
                        backoff = Duration::from_millis(250);
                        self.set_connected(true, None);
                        self.listen(stream).await;
                        self.set_connected(false, None);
                    }
                    Ok(Err(error)) => {
                        tracing::warn!(%error, "emergency status stream unreachable");
                        self.link_down().await;
                    }
                    Err(_) => self.link_down().await,
                }
                tokio::time::sleep(backoff).await;
                backoff = (backoff * 2).min(MAX_BACKOFF);
            }
        })
    }

    /// Reads one connection until it closes; silence raises `EmergencyLinkDown`.
    async fn listen<S>(&self, mut stream: S)
    where
        S: futures_util::Stream<
                Item = Result<
                    tokio_tungstenite::tungstenite::Message,
                    tokio_tungstenite::tungstenite::Error,
                >,
            > + Unpin,
    {
        loop {
            match tokio::time::timeout(self.config.silence, stream.next()).await {
                Err(_) => self.link_down().await,
                Ok(None | Some(Err(_))) => {
                    self.link_down().await;
                    return;
                }
                Ok(Some(Ok(message))) => {
                    let now = self.clock.now();
                    self.set_connected(true, Some(now));
                    if let Ok(text) = message.to_text() {
                        self.on_text(text, now).await;
                    }
                }
            }
        }
    }

    /// Mirrors an alarm message; anything else only proves the link is alive.
    async fn on_text(&self, text: &str, now: DateTime<Utc>) {
        let Ok(message) = serde_json::from_str::<AlarmMessage>(text) else {
            return;
        };
        if message.kind != "alarm" {
            return;
        }
        let level = message.level.unwrap_or(AlarmLevel::Emergency);
        tracing::warn!(room = ?message.room, ?level, "emergency alarm mirrored");
        let code = IncidentCode::EmergencyAlarm { level };
        let room = message
            .room
            .as_deref()
            .and_then(|room| room.parse::<PlaceId>().ok())
            .and_then(|place| {
                let floor = self.board.floor_of_place(&place)?;
                Some((place, floor))
            });
        match room {
            Some((place, floor)) => {
                self.board.raise_in_room(code, place, floor, now).await;
            }
            None => {
                self.board.raise(code, None, now).await;
            }
        }
    }

    async fn link_down(&self) {
        self.set_connected(false, None);
        self.board
            .raise(IncidentCode::EmergencyLinkDown, None, self.clock.now())
            .await;
    }

    fn set_connected(&self, connected: bool, message_at: Option<DateTime<Utc>>) {
        self.status.send_modify(|status| {
            status.connected = connected;
            if message_at.is_some() {
                status.last_message_at = message_at;
            }
        });
    }

    /// Current link status.
    #[must_use]
    pub fn status(&self) -> MirrorStatus {
        *self.status.borrow()
    }

    /// Status changes.
    #[must_use]
    pub fn subscribe(&self) -> watch::Receiver<MirrorStatus> {
        self.status.subscribe()
    }
}
