//! Robot status, robot commands, and what a robot reports seeing on a shelf.
//!
//! `CommandName` and `SeenItem` are wire types of contract C2; they live here so `audit`,
//! `optimization` and `storage` can use them without depending on `realtime`, which re-exports
//! them.

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::ids::ItemId;

/// Robot status as reported (C2 `robot.state.state`).
///
/// There is no `offline`: the server keeps the last reported status and shows staleness
/// through `last_seen` and an `alert` (the admin console greys a robot silent for 5 s).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RobotStatus {
    /// Free.
    Idle,
    /// Working on a task.
    Busy,
    /// Paused by command.
    Paused,
    /// Reported a fault.
    Fault,
    /// Emergency stop engaged.
    Estop,
}

/// Commands the server may send. Requests, not orders: only `estop` bypasses the gardien.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum CommandName {
    /// Pause the current task.
    Pause,
    /// Resume after a pause.
    Resume,
    /// Go back to the dock.
    Dock,
    /// Emergency stop (admin only, separate code path).
    Estop,
    /// Shut down.
    Shutdown,
}

impl CommandName {
    /// The command that undoes this one when an admin reverts it (Task A7): `pause` ->
    /// `resume`, `resume` -> `pause`, `dock` -> `resume`. `None` for `estop` (admin only,
    /// never reverted this way) and `shutdown` (the robot is off; it cannot be undone from
    /// the server).
    #[must_use]
    pub fn inverse(self) -> Option<CommandName> {
        match self {
            CommandName::Pause | CommandName::Dock => Some(CommandName::Resume),
            CommandName::Resume => Some(CommandName::Pause),
            CommandName::Estop | CommandName::Shutdown => None,
        }
    }
}

/// One item a robot saw on a shelf (C2 `inventory.seen`).
///
/// `count: None` or `uncertain: true` never overwrites stock and never reads as zero.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct SeenItem {
    /// Item key.
    pub item: ItemId,
    /// Counted quantity, when the robot could count.
    pub count: Option<u32>,
    /// The robot is not sure of what it saw.
    #[serde(default)]
    pub uncertain: bool,
}
