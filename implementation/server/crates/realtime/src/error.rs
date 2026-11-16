//! Errors of the real-time crate.

use domain::RobotId;

/// A message that could not be decoded or encoded.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ProtocolError {
    /// Above the size limit.
    #[error("Message of {size} bytes is larger than the {max}-byte limit; split it or send less.")]
    TooLarge {
        /// Size received.
        size: usize,
        /// Limit.
        max: usize,
    },
    /// A `type` that the contract does not define.
    #[error("Message type '{type_name}' is not part of contract C2; it was ignored.")]
    UnknownType {
        /// The type received.
        type_name: String,
    },
    /// Not valid JSON or wrong shape.
    #[error("Message is malformed ({reason}); check it against docs/ws_messages.md.")]
    Malformed {
        /// Parser explanation (position and expectation, no message content).
        reason: String,
    },
    /// A required field is missing.
    #[error("Message is missing the field '{field}'; see docs/ws_messages.md.")]
    MissingField {
        /// The field.
        field: String,
    },
}

/// Hub and session errors.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum RealtimeError {
    /// A second connection for the same robot.
    #[error("Robot {robot} is already connected; close the other connection first.")]
    RobotAlreadyConnected {
        /// Robot.
        robot: RobotId,
    },
    /// No connection for the robot.
    #[error("Robot {robot} is not connected; the message was not delivered.")]
    RobotNotConnected {
        /// Robot.
        robot: RobotId,
    },
    /// The robot's outbound queue is full.
    #[error(
        "Robot {robot} is not reading its messages (queue full); the message was not delivered."
    )]
    QueueFull {
        /// Robot.
        robot: RobotId,
    },
    /// The connection closed while sending.
    #[error("The connection to robot {robot} closed; the message was not delivered.")]
    Closed {
        /// Robot.
        robot: RobotId,
    },
    /// A protocol error.
    #[error("Robot message rejected: {0}")]
    Protocol(#[from] ProtocolError),
}
