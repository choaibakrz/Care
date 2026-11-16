//! The incident board (Task 11c): raised by robot faults, offline and estop states, journal
//! degradation, tablet errors and mirrored emergency alarms; shown on the 3D map.

use std::collections::BTreeMap;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use chrono::{DateTime, Utc};
use domain::{Actor, Clock, OwnerLabel, PlaceId, SubjectRef};
use locations::Attribution;
use realtime::{AppErrorCode, AppEvent, Hub, Incident, IncidentChange, IncidentCode, IncidentId};
use security::ClientIdentity;
use tokio::sync::Mutex;

use super::IncidentService;
use crate::error::ApiError;

/// What `IncidentBoard` needs.
pub struct IncidentBoardDeps {
    /// Journal (every change is journaled).
    pub journal: Journal,
    /// Hub (`incident.updated`).
    pub hub: Arc<Hub>,
    /// Room of a subject.
    pub attribution: Attribution,
    /// Clock.
    pub clock: Arc<dyn Clock>,
}

/// Open and recent incidents (memory).
pub struct IncidentBoard {
    deps: IncidentBoardDeps,
    incidents: Mutex<BTreeMap<IncidentId, Incident>>,
    next_id: AtomicU64,
}

impl IncidentBoard {
    /// An empty board.
    #[must_use]
    pub fn new(deps: IncidentBoardDeps) -> IncidentBoard {
        IncidentBoard {
            deps,
            incidents: Mutex::new(BTreeMap::new()),
            next_id: AtomicU64::new(1),
        }
    }

    /// Raises an incident. The same open code for the same subject is merged
    /// (`repeats += 1`); severity can rise, never silently fall. Journaled and published.
    pub async fn raise(
        &self,
        code: IncidentCode,
        subject: Option<SubjectRef>,
        at: DateTime<Utc>,
    ) -> IncidentId {
        let room = subject
            .as_ref()
            .and_then(|subject| self.deps.attribution.place_of(subject));
        self.raise_with(code, subject, room, at).await
    }

    /// The floor of a place of the map, `None` for an unknown place.
    #[must_use]
    pub fn floor_of_place(&self, place: &PlaceId) -> Option<i32> {
        self.deps.attribution.floor_of_place(place)
    }

    /// Raises an incident on a known room (mirrored emergency alarms carry their room, not
    /// a subject). Merged like [`IncidentBoard::raise`], per room.
    pub async fn raise_in_room(
        &self,
        code: IncidentCode,
        place: PlaceId,
        floor: i32,
        at: DateTime<Utc>,
    ) -> IncidentId {
        self.raise_with(code, None, Some((place, floor)), at).await
    }

    /// Merges into the open incident of the same kind of code, subject and room, or opens a
    /// new one.
    async fn raise_with(
        &self,
        code: IncidentCode,
        subject: Option<SubjectRef>,
        room: Option<(PlaceId, i32)>,
        at: DateTime<Utc>,
    ) -> IncidentId {
        let severity = code.default_severity();
        let place = room.as_ref().map(|(place, _)| place.clone());
        let incident = {
            let mut incidents = self.incidents.lock().await;
            let open = incidents.values_mut().find(|incident| {
                incident.closed_at.is_none()
                    && std::mem::discriminant(&incident.code) == std::mem::discriminant(&code)
                    && incident.subject == subject
                    && (subject.is_some() || incident.place == place)
            });
            if let Some(incident) = open {
                incident.repeats = incident.repeats.saturating_add(1);
                incident.last_seen_at = at;
                if severity >= incident.severity {
                    incident.code = code;
                    incident.severity = severity;
                }
                incident.clone()
            } else {
                let id = IncidentId(self.next_id.fetch_add(1, Ordering::Relaxed));
                let incident = Incident {
                    id,
                    code,
                    severity,
                    subject,
                    place,
                    floor: room.map(|(_, floor)| floor),
                    opened_at: at,
                    last_seen_at: at,
                    repeats: 0,
                    acknowledged_by: None,
                    closed_at: None,
                };
                incidents.insert(id, incident.clone());
                incident
            }
        };
        self.changed(&incident, IncidentChange::Raised, Actor::System("server"))
            .await;
        incident.id
    }

    /// Acknowledges.
    ///
    /// # Errors
    /// 404 unknown id. A mirrored emergency alarm is acknowledged on this board only: nothing
    /// is ever sent to the emergency service (ruling R2).
    pub async fn ack(&self, id: IncidentId, by: OwnerLabel) -> Result<Incident, ApiError> {
        self.ack_as(id, by, Actor::System("server")).await
    }

    /// Closes (admin).
    ///
    /// # Errors
    /// 404 unknown id.
    pub async fn close(&self, id: IncidentId, by: OwnerLabel) -> Result<Incident, ApiError> {
        self.close_as(id, by, Actor::System("server")).await
    }

    /// Acknowledges, journaled under `actor`.
    async fn ack_as(
        &self,
        id: IncidentId,
        by: OwnerLabel,
        actor: Actor,
    ) -> Result<Incident, ApiError> {
        let incident = {
            let mut incidents = self.incidents.lock().await;
            let incident = incidents
                .get_mut(&id)
                .ok_or_else(|| ApiError::not_found("Incident", &id.0.to_string()))?;
            incident.acknowledged_by = Some(by);
            incident.clone()
        };
        self.changed(&incident, IncidentChange::Acknowledged, actor)
            .await;
        Ok(incident)
    }

    /// Closes, journaled under `actor`.
    async fn close_as(
        &self,
        id: IncidentId,
        by: OwnerLabel,
        actor: Actor,
    ) -> Result<Incident, ApiError> {
        let now = self.deps.clock.now();
        let incident = {
            let mut incidents = self.incidents.lock().await;
            let incident = incidents
                .get_mut(&id)
                .ok_or_else(|| ApiError::not_found("Incident", &id.0.to_string()))?;
            incident.closed_at.get_or_insert(now);
            if incident.acknowledged_by.is_none() {
                incident.acknowledged_by = Some(by);
            }
            incident.clone()
        };
        self.changed(&incident, IncidentChange::Closed, actor).await;
        Ok(incident)
    }

    /// Journals a change and publishes `incident.updated`.
    async fn changed(&self, incident: &Incident, change: IncidentChange, actor: Actor) {
        let appended = self
            .deps
            .journal
            .append(
                Severity::Notice,
                Category::Audit,
                actor,
                RecordBody::IncidentChanged {
                    id: incident.id,
                    code: incident.code,
                    change,
                },
                Some(self.deps.clock.now()),
            )
            .await;
        if let Err(error) = appended {
            tracing::warn!(%error, "incident change not journaled");
        }
        self.deps.hub.publish(AppEvent::IncidentUpdated {
            incident: incident.clone(),
            colour: incident.severity.colour(),
        });
    }
}

#[async_trait]
impl IncidentService for IncidentBoard {
    async fn list_incidents(&self, open_only: bool) -> Result<Vec<Incident>, ApiError> {
        Ok(self
            .incidents
            .lock()
            .await
            .values()
            .filter(|incident| !open_only || incident.closed_at.is_none())
            .cloned()
            .collect())
    }
    async fn acknowledge(
        &self,
        actor: &ClientIdentity,
        id: IncidentId,
    ) -> Result<Incident, ApiError> {
        let by = actor
            .verified
            .owner
            .clone()
            .ok_or_else(ApiError::unauthorized)?;
        self.ack_as(id, by, actor.verified.subject_id.clone()).await
    }
    async fn close_incident(
        &self,
        actor: &ClientIdentity,
        id: IncidentId,
    ) -> Result<Incident, ApiError> {
        let by = actor
            .verified
            .owner
            .clone()
            .ok_or_else(ApiError::unauthorized)?;
        self.close_as(id, by, actor.verified.subject_id.clone())
            .await
    }
    async fn report_device_event(
        &self,
        actor: &ClientIdentity,
        code: AppErrorCode,
    ) -> Result<(), ApiError> {
        let device = actor
            .verified
            .device_id
            .clone()
            .ok_or_else(ApiError::device_required)?;
        let now = self.deps.clock.now();
        self.raise(
            IncidentCode::TabletAppError { error: code },
            Some(SubjectRef::Tablet(device)),
            now,
        )
        .await;
        Ok(())
    }
}
