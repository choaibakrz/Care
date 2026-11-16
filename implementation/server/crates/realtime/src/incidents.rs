//! Incident wire types (Task 11c). The closed catalogue (codes, severity, colour) lives in
//! `domain::incident` and is re-exported here; this module adds the `Incident` record.

use chrono::{DateTime, Utc};
use domain::{OwnerLabel, PlaceId, SubjectRef};
use serde::Serialize;
use utoipa::ToSchema;

pub use domain::incident::{
    AlarmLevel, AppErrorCode, IncidentChange, IncidentCode, IncidentColour, IncidentId,
    IncidentSeverity, Lang, RobotFaultCode,
};

/// An incident on the map.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Incident {
    /// Id.
    pub id: IncidentId,
    /// Code.
    pub code: IncidentCode,
    /// Severity.
    pub severity: IncidentSeverity,
    /// Robot or tablet concerned.
    pub subject: Option<SubjectRef>,
    /// Room.
    pub place: Option<PlaceId>,
    /// Floor.
    pub floor: Option<i32>,
    /// First raised.
    pub opened_at: DateTime<Utc>,
    /// Last raised again.
    pub last_seen_at: DateTime<Utc>,
    /// Times raised again while open.
    pub repeats: u32,
    /// Who acknowledged it.
    pub acknowledged_by: Option<OwnerLabel>,
    /// When closed.
    pub closed_at: Option<DateTime<Utc>>,
}
