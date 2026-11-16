//! Roles (from `clinique/badges.yaml`) and permissions.

use std::fmt;

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// The role of a caller. Robots have their own role.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    /// Nurse.
    Nurse,
    /// Doctor.
    Doctor,
    /// Therapist.
    Therapist,
    /// Reception desk.
    Reception,
    /// Administrator: zones, estop, stock adjustments, schedules, audit.
    Admin,
    /// A robot connection.
    Robot,
}

/// What a caller may do. Each route requires exactly one.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Permission {
    /// Read tasks.
    ViewTasks,
    /// Create tasks.
    CreateTask,
    /// Cancel tasks.
    CancelTask,
    /// Read stock.
    ViewInventory,
    /// Adjust stock by hand (admin).
    AdjustInventory,
    /// Read the map, zones and live positions.
    ViewMap,
    /// Report one's own tablet room or scans.
    ReportLocation,
    /// Edit zones (admin only).
    EditZones,
    /// Read robots.
    ViewRobots,
    /// Send pause, resume, dock (nurse and admin). A nurse's command raises the admin alert
    /// `staff_command`; a nurse never lifts an emergency stop (409 `estop_latched`).
    RobotControl,
    /// Shut a robot down (admin only, ruling R24): a shutdown cannot be undone from the
    /// server, so only the administrator may send it.
    RobotShutdown,
    /// Send the emergency stop (admin only).
    Estop,
    /// Read schedules.
    ViewSchedules,
    /// Edit schedules (admin).
    EditSchedules,
    /// Read the audit trail (admin).
    ViewAudit,
    /// Read incidents.
    ViewIncidents,
    /// Acknowledge incidents.
    AckIncident,
    /// Close incidents (admin).
    CloseIncident,
    /// Report one's own device errors.
    ReportDeviceEvent,
    /// List, read, create, edit, activate and delete clinic plans (admin only, Task A4).
    EditClinics,
    /// Read fleet statistics such as the heat map (admin only, Task A4).
    ViewStats,
    /// Translate and simplify a text, read the brain's health (Task A6). Every staff role:
    /// talking with a patient in their language is part of every job at the clinic.
    UseBrain,
    /// Summarise care notes and messages (Task A6). Doctor, therapist and nurse only: they
    /// write and read care notes; reception and the administrator do not read clinical text.
    SummariseSources,
    /// Draft a shift, incident or robot activity report from server data (Task A6). Admin
    /// and doctor: the admin runs the fleet, the doctor signs the shift handover.
    DraftReport,
    /// Issue enrolment codes, list accounts (pseudonyms and tags only) and disable an
    /// account (admin only, Task A7).
    ManageAccounts,
    /// Undo a robot command sent by a non-admin (admin only, Task A7): every pause, resume,
    /// dock or shutdown from another role raises an admin alert.
    RevertCommand,
    /// Read whether the clinic is in emergency mode (`GET /system/mode`, Task A8): every
    /// signed-in caller, robots included.
    ViewSystemMode,
    /// Switch emergency mode on or off (`PUT /system/mode`, admin only, Task A8).
    SwitchSystemMode,
    /// Read the server's monitoring and manage address blocks (`/monitor/*`,
    /// `/security/blocks`, admin only, Task A8).
    MonitorSecurity,
    /// See the tablet registry, free a tablet and hand one out (`/devices`, admin only,
    /// Task A8).
    ManageDevices,
}

impl Permission {
    /// The `snake_case` name used in `forbidden` messages.
    #[must_use]
    pub fn name(self) -> &'static str {
        match self {
            Permission::ViewTasks => "view_tasks",
            Permission::CreateTask => "create_task",
            Permission::CancelTask => "cancel_task",
            Permission::ViewInventory => "view_inventory",
            Permission::AdjustInventory => "adjust_inventory",
            Permission::ViewMap => "view_map",
            Permission::ReportLocation => "report_location",
            Permission::EditZones => "edit_zones",
            Permission::ViewRobots => "view_robots",
            Permission::RobotControl => "robot_control",
            Permission::RobotShutdown => "robot_shutdown",
            Permission::Estop => "estop",
            Permission::ViewSchedules => "view_schedules",
            Permission::EditSchedules => "edit_schedules",
            Permission::ViewAudit => "view_audit",
            Permission::ViewIncidents => "view_incidents",
            Permission::AckIncident => "ack_incident",
            Permission::CloseIncident => "close_incident",
            Permission::ReportDeviceEvent => "report_device_event",
            Permission::EditClinics => "edit_clinics",
            Permission::ViewStats => "view_stats",
            Permission::UseBrain => "use_brain",
            Permission::SummariseSources => "summarise_sources",
            Permission::DraftReport => "draft_report",
            Permission::ManageAccounts => "manage_accounts",
            Permission::RevertCommand => "revert_command",
            Permission::ViewSystemMode => "view_system_mode",
            Permission::SwitchSystemMode => "switch_system_mode",
            Permission::MonitorSecurity => "monitor_security",
            Permission::ManageDevices => "manage_devices",
        }
    }
}

impl fmt::Display for Permission {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.name())
    }
}

impl Role {
    /// Whether this role holds the permission. `Estop`, `RobotShutdown`, `EditZones`,
    /// `EditClinics`, `ViewStats`, `ManageAccounts`, `RevertCommand`, `SwitchSystemMode`,
    /// `MonitorSecurity` and `ManageDevices` are `Admin` only; `ViewSystemMode` is every
    /// role's. The admin holds every permission except `SummariseSources` (Task A6: the admin
    /// reads no clinical text).
    #[must_use]
    pub fn allows(&self, permission: Permission) -> bool {
        match self {
            // The admin holds every permission but the clinical summary.
            Role::Admin => permission != Permission::SummariseSources,
            // The clinical roles read and request; only the nurse may also pause a robot.
            Role::Nurse => {
                Role::clinical_staff(permission)
                    || matches!(
                        permission,
                        Permission::RobotControl | Permission::SummariseSources
                    )
            }
            Role::Doctor => {
                Role::clinical_staff(permission)
                    || matches!(
                        permission,
                        Permission::SummariseSources | Permission::DraftReport
                    )
            }
            Role::Therapist => {
                Role::clinical_staff(permission) || permission == Permission::SummariseSources
            }
            Role::Reception => Role::clinical_staff(permission),
            // A robot connection reads what it needs to do its tasks and nothing else.
            Role::Robot => matches!(
                permission,
                Permission::ViewTasks
                    | Permission::ViewMap
                    | Permission::ViewInventory
                    | Permission::ViewSystemMode
            ),
        }
    }
}

impl Role {
    /// The permissions shared by every human non-admin role.
    fn clinical_staff(permission: Permission) -> bool {
        matches!(
            permission,
            Permission::ViewTasks
                | Permission::CreateTask
                | Permission::CancelTask
                | Permission::ViewInventory
                | Permission::ViewMap
                | Permission::ReportLocation
                | Permission::ViewRobots
                | Permission::ViewSchedules
                | Permission::ViewIncidents
                | Permission::AckIncident
                | Permission::ReportDeviceEvent
                | Permission::UseBrain
                | Permission::ViewSystemMode
        )
    }
}

impl fmt::Display for Role {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Role::Nurse => "nurse",
            Role::Doctor => "doctor",
            Role::Therapist => "therapist",
            Role::Reception => "reception",
            Role::Admin => "admin",
            Role::Robot => "robot",
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{Permission, Role};

    #[test]
    fn nurse_cannot_estop() {
        assert!(!Role::Nurse.allows(Permission::Estop));
    }

    #[test]
    fn admin_can_estop() {
        assert!(Role::Admin.allows(Permission::Estop));
    }

    #[test]
    fn admin_only_permissions_are_refused_to_every_other_role() {
        let others = [
            Role::Nurse,
            Role::Doctor,
            Role::Therapist,
            Role::Reception,
            Role::Robot,
        ];
        for permission in [
            Permission::Estop,
            Permission::RobotShutdown,
            Permission::EditZones,
            Permission::EditClinics,
            Permission::ViewStats,
            Permission::ViewAudit,
            Permission::EditSchedules,
            Permission::AdjustInventory,
            Permission::CloseIncident,
            Permission::ManageAccounts,
            Permission::RevertCommand,
            Permission::SwitchSystemMode,
            Permission::MonitorSecurity,
            Permission::ManageDevices,
        ] {
            for role in others {
                assert!(
                    !role.allows(permission),
                    "{role} must not hold {permission}"
                );
            }
        }
    }

    #[test]
    fn brain_permissions_follow_the_task_a6_table() {
        let all = [
            Role::Nurse,
            Role::Doctor,
            Role::Therapist,
            Role::Reception,
            Role::Admin,
        ];
        for role in all {
            assert!(role.allows(Permission::UseBrain), "{role} translates");
        }
        assert!(!Role::Robot.allows(Permission::UseBrain));
        let summarise: Vec<Role> = all
            .into_iter()
            .chain([Role::Robot])
            .filter(|r| r.allows(Permission::SummariseSources))
            .collect();
        assert_eq!(summarise, [Role::Nurse, Role::Doctor, Role::Therapist]);
        let report: Vec<Role> = all
            .into_iter()
            .chain([Role::Robot])
            .filter(|r| r.allows(Permission::DraftReport))
            .collect();
        assert_eq!(report, [Role::Doctor, Role::Admin]);
    }

    #[test]
    fn every_role_reads_the_system_mode() {
        for role in [
            Role::Nurse,
            Role::Doctor,
            Role::Therapist,
            Role::Reception,
            Role::Admin,
            Role::Robot,
        ] {
            assert!(role.allows(Permission::ViewSystemMode), "{role}");
        }
        assert!(Role::Admin.allows(Permission::SwitchSystemMode));
    }

    #[test]
    fn permission_names_are_snake_case() {
        assert_eq!(Permission::Estop.name(), "estop");
        assert_eq!(Permission::EditClinics.to_string(), "edit_clinics");
    }
}
