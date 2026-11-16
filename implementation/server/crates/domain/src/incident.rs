//! The incident catalogue (Task 11c): a closed list, no free text from any device.
//!
//! Defined here (not in `realtime`) so the journal (`audit`, which depends only on `domain`)
//! can record incident changes with typed fields. `realtime` re-exports these types.

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// Incident id, assigned by the incident board.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema,
)]
#[serde(transparent)]
pub struct IncidentId(pub u64);

/// Robot fault codes (closed list).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RobotFaultCode {
    /// Drive motor.
    Motor,
    /// Battery.
    Battery,
    /// A sensor.
    Sensor,
    /// Localisation or path.
    Navigation,
    /// Gripper or tray.
    Gripper,
    /// Robot software.
    Software,
}

/// Tablet application error codes (closed list; an unknown code is 422).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AppErrorCode {
    /// The app crashed and restarted.
    Crash,
    /// Lost the network.
    NetworkLost,
    /// Bluetooth is off.
    BluetoothOff,
    /// Camera unavailable (QR scanning).
    CameraUnavailable,
    /// Storage full.
    StorageFull,
}

/// Alarm level mirrored from the emergency service.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum AlarmLevel {
    /// Patient call.
    Call,
    /// Urgent call.
    Urgent,
    /// Emergency.
    Emergency,
}

/// What happened. Each code has fixed English and French labels.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(tag = "code", rename_all = "snake_case")]
pub enum IncidentCode {
    /// A robot reported a fault.
    RobotFault {
        /// Fault.
        fault: RobotFaultCode,
    },
    /// A robot went silent.
    RobotOffline,
    /// A robot is in emergency stop.
    RobotEstop,
    /// A tablet went silent.
    TabletOffline,
    /// A tablet battery is low.
    TabletBatteryLow,
    /// A tablet reported an application error.
    TabletAppError {
        /// Error.
        error: AppErrorCode,
    },
    /// A zone update was not delivered to a robot.
    ZoneNotDelivered,
    /// The journal cannot write.
    JournalDegraded,
    /// Alarm mirrored from the emergency service (read-only here).
    EmergencyAlarm {
        /// Level.
        level: AlarmLevel,
    },
    /// The emergency service's status stream is silent (10 s).
    EmergencyLinkDown,
}

/// UI language of the label tables.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    /// English.
    En,
    /// French.
    Fr,
}

impl IncidentCode {
    /// Fixed UI label.
    #[must_use]
    pub fn label(&self, lang: Lang) -> &'static str {
        match (self, lang) {
            (Self::RobotFault { fault }, Lang::En) => match fault {
                RobotFaultCode::Motor => "Robot fault: motor",
                RobotFaultCode::Battery => "Robot fault: battery",
                RobotFaultCode::Sensor => "Robot fault: sensor",
                RobotFaultCode::Navigation => "Robot fault: navigation",
                RobotFaultCode::Gripper => "Robot fault: gripper",
                RobotFaultCode::Software => "Robot fault: software",
            },
            (Self::RobotFault { fault }, Lang::Fr) => match fault {
                RobotFaultCode::Motor => "Panne du robot : moteur",
                RobotFaultCode::Battery => "Panne du robot : batterie",
                RobotFaultCode::Sensor => "Panne du robot : capteur",
                RobotFaultCode::Navigation => "Panne du robot : navigation",
                RobotFaultCode::Gripper => "Panne du robot : pince",
                RobotFaultCode::Software => "Panne du robot : logiciel",
            },
            (Self::RobotOffline, Lang::En) => "Robot offline",
            (Self::RobotOffline, Lang::Fr) => "Robot hors ligne",
            (Self::RobotEstop, Lang::En) => "Robot emergency stop",
            (Self::RobotEstop, Lang::Fr) => "Arrêt d'urgence du robot",
            (Self::TabletOffline, Lang::En) => "Tablet offline",
            (Self::TabletOffline, Lang::Fr) => "Tablette hors ligne",
            (Self::TabletBatteryLow, Lang::En) => "Tablet battery low",
            (Self::TabletBatteryLow, Lang::Fr) => "Batterie de la tablette faible",
            (Self::TabletAppError { error }, Lang::En) => match error {
                AppErrorCode::Crash => "Tablet app crashed",
                AppErrorCode::NetworkLost => "Tablet lost the network",
                AppErrorCode::BluetoothOff => "Tablet Bluetooth is off",
                AppErrorCode::CameraUnavailable => "Tablet camera unavailable",
                AppErrorCode::StorageFull => "Tablet storage full",
            },
            (Self::TabletAppError { error }, Lang::Fr) => match error {
                AppErrorCode::Crash => "L'application de la tablette a planté",
                AppErrorCode::NetworkLost => "La tablette a perdu le réseau",
                AppErrorCode::BluetoothOff => "Le Bluetooth de la tablette est désactivé",
                AppErrorCode::CameraUnavailable => "Caméra de la tablette indisponible",
                AppErrorCode::StorageFull => "Stockage de la tablette plein",
            },
            (Self::ZoneNotDelivered, Lang::En) => "Zone update not delivered",
            (Self::ZoneNotDelivered, Lang::Fr) => "Mise à jour de zone non livrée",
            (Self::JournalDegraded, Lang::En) => "Journal cannot write",
            (Self::JournalDegraded, Lang::Fr) => "Le journal ne peut plus écrire",
            (Self::EmergencyAlarm { level }, Lang::En) => match level {
                AlarmLevel::Call => "Patient call",
                AlarmLevel::Urgent => "Urgent call",
                AlarmLevel::Emergency => "Emergency",
            },
            (Self::EmergencyAlarm { level }, Lang::Fr) => match level {
                AlarmLevel::Call => "Appel patient",
                AlarmLevel::Urgent => "Appel urgent",
                AlarmLevel::Emergency => "Urgence",
            },
            (Self::EmergencyLinkDown, Lang::En) => "Emergency service link down",
            (Self::EmergencyLinkDown, Lang::Fr) => "Liaison avec le service d'urgence coupée",
        }
    }

    /// Default severity of the code.
    #[must_use]
    pub fn default_severity(&self) -> IncidentSeverity {
        match self {
            Self::EmergencyAlarm { .. } | Self::RobotEstop => IncidentSeverity::Critical,
            Self::RobotFault { .. } | Self::TabletAppError { .. } => IncidentSeverity::Warning,
            Self::RobotOffline
            | Self::TabletOffline
            | Self::TabletBatteryLow
            | Self::ZoneNotDelivered
            | Self::JournalDegraded
            | Self::EmergencyLinkDown => IncidentSeverity::Info,
        }
    }
}

/// Severity; it can rise, never silently fall.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum IncidentSeverity {
    /// Yellow.
    Info,
    /// Orange.
    Warning,
    /// Red.
    Critical,
}

impl IncidentSeverity {
    /// Map colour.
    #[must_use]
    pub fn colour(self) -> IncidentColour {
        match self {
            Self::Critical => IncidentColour::Red,
            Self::Warning => IncidentColour::Orange,
            Self::Info => IncidentColour::Yellow,
        }
    }
}

/// Room colour on the 3D map.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum IncidentColour {
    /// Critical.
    Red,
    /// Warning.
    Orange,
    /// Info.
    Yellow,
}

/// What happened to an incident, as recorded in the journal. Who did it is the record's actor.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum IncidentChange {
    /// Opened, or raised again while open (merged).
    Raised,
    /// Acknowledged.
    Acknowledged,
    /// Closed.
    Closed,
}
