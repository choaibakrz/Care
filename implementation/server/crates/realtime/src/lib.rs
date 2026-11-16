//! Real-time layer: WebSocket protocol types (contract C2), the hub, robot sessions,
//! liveness, de-duplication, zone delivery and incident wire types.

pub mod dedupe;
pub mod error;
pub mod hub;
pub mod incidents;
pub mod liveness;
pub mod protocol;
pub mod robot_session;
pub mod views;
pub mod zone_delivery;

pub use dedupe::Deduper;
pub use domain::{CommandName, SeenItem};
pub use error::{ProtocolError, RealtimeError};
pub use hub::{Hub, RobotLink, RobotSession};
pub use incidents::{
    AlarmLevel, AppErrorCode, Incident, IncidentChange, IncidentCode, IncidentColour, IncidentId,
    IncidentSeverity, Lang, RobotFaultCode,
};
pub use liveness::Liveness;
pub use protocol::{
    APP_AUTH_CLOSE_CODE, APP_AUTH_TIMEOUT_S, AlertKind, AlertLevel, AppEvent, AppUp, CommandNotice,
    Envelope, MAX_MESSAGE_BYTES, Positions, RobotDown, RobotPose, RobotPosition, RobotUp,
    TabletPosition, WireZone, decode_robot_down, decode_robot_up, encode,
};
pub use robot_session::{CloseReason, authorize_robot};
pub use views::{
    MoodInputs, RobotMood, RobotView, SIMULATED_REQUEST_LABEL, ScheduleView, TabletKind,
    TabletView, TaskHistoryEntry, TaskView, ZoneView, requester_label,
};
pub use zone_delivery::{DeliveryState, ZoneDelivery, ZoneDeliveryEntry};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
