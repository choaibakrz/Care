//! Who did something (`Actor`) and what a position belongs to (`SubjectRef`).

use std::fmt;

use serde::{Deserialize, Deserializer, Serialize};
use utoipa::ToSchema;

use crate::ids::{DeviceId, RobotId, UserId};

/// The author of an action, as recorded in tasks and the journal.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, ToSchema)]
#[serde(tag = "kind", content = "id", rename_all = "snake_case")]
pub enum Actor {
    /// A logged-in staff user.
    User(UserId),
    /// A device acting on its own (a tablet reporting an error).
    Device(DeviceId),
    /// A robot.
    Robot(RobotId),
    /// The server itself; the name is a fixed component name such as `scheduler`.
    System(&'static str),
}

impl Actor {
    /// The only names `Actor::System` may carry. Being a closed list is what lets journal
    /// records be read back into `&'static str` without leaking memory.
    pub const KNOWN_SYSTEM_NAMES: &'static [&'static str] = &[
        "server",
        "scheduler",
        "dispatcher",
        "journal",
        "liveness",
        "security",
        "emergency_mirror",
        // Demo mode's request generator (Task 5b, ruling R15): shown as "SIMULATED request".
        "demo",
    ];
}

impl<'de> Deserialize<'de> for Actor {
    /// Reads the tagged form; a `system` name outside [`Actor::KNOWN_SYSTEM_NAMES`] is an error.
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        #[serde(tag = "kind", content = "id", rename_all = "snake_case")]
        enum Wire {
            User(UserId),
            Device(DeviceId),
            Robot(RobotId),
            System(String),
        }
        Ok(match Wire::deserialize(deserializer)? {
            Wire::User(id) => Actor::User(id),
            Wire::Device(id) => Actor::Device(id),
            Wire::Robot(id) => Actor::Robot(id),
            Wire::System(name) => Actor::System(
                Actor::KNOWN_SYSTEM_NAMES
                    .iter()
                    .find(|known| **known == name)
                    .copied()
                    .ok_or_else(|| {
                        serde::de::Error::custom(format!("unknown system actor '{name}'"))
                    })?,
            ),
        })
    }
}

impl fmt::Display for Actor {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Actor::User(id) => write!(f, "user:{id}"),
            Actor::Device(id) => write!(f, "device:{id}"),
            Actor::Robot(id) => write!(f, "robot:{id}"),
            Actor::System(name) => write!(f, "system:{name}"),
        }
    }
}

/// What a live position or an incident refers to: a robot or a tablet, nothing else.
///
/// Defined here (not in `locations`) so `realtime` incident wire types can use it without
/// depending on `locations`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, ToSchema)]
#[serde(tag = "kind", content = "id", rename_all = "snake_case")]
pub enum SubjectRef {
    /// A robot.
    Robot(RobotId),
    /// A tablet.
    Tablet(DeviceId),
}
