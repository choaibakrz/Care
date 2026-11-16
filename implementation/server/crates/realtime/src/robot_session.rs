//! Robot connection checks and WebSocket close reasons (Task 14).

use domain::RobotId;

use crate::error::RealtimeError;

/// Close code: the token belongs to another robot, or is not a robot token.
pub const CLOSE_FORBIDDEN: u16 = 4403;
/// Close code: unknown robot id.
pub const CLOSE_UNKNOWN_ROBOT: u16 = 4404;
/// Close code: the robot already has a connection.
pub const CLOSE_CONFLICT: u16 = 4409;
/// Close code: the server could not set up the session (standard 1011, internal error).
pub const CLOSE_INTERNAL: u16 = 1011;

/// Why the server closes a robot WebSocket: an application close code and a readable text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CloseReason {
    code: u16,
    text: String,
}

impl CloseReason {
    /// 4403: "Token belongs to robot X but the connection asks for robot Y."
    #[must_use]
    pub fn token_mismatch(token_robot: &RobotId, path_robot: &RobotId) -> CloseReason {
        CloseReason {
            code: CLOSE_FORBIDDEN,
            text: format!(
                "Token belongs to robot {token_robot} but the connection asks for robot {path_robot}."
            ),
        }
    }

    /// 4403: the token is a user token, not a robot token.
    #[must_use]
    pub fn not_a_robot() -> CloseReason {
        CloseReason {
            code: CLOSE_FORBIDDEN,
            text: "This connection needs a robot token; user tokens cannot open /ws/robot."
                .to_owned(),
        }
    }

    /// 4404: unknown robot id, named in the text.
    #[must_use]
    pub fn unknown_robot(robot: &RobotId) -> CloseReason {
        CloseReason {
            code: CLOSE_UNKNOWN_ROBOT,
            text: format!("Robot {robot} is not registered on this server."),
        }
    }

    /// Close reason for a hub refusal (4409 already connected, 1011 otherwise).
    #[must_use]
    pub fn from_realtime(error: &RealtimeError) -> CloseReason {
        let code = match error {
            RealtimeError::RobotAlreadyConnected { .. } => CLOSE_CONFLICT,
            _ => CLOSE_INTERNAL,
        };
        CloseReason {
            code,
            text: error.to_string(),
        }
    }

    /// The close code.
    #[must_use]
    pub fn code(&self) -> u16 {
        self.code
    }

    /// The close text.
    #[must_use]
    pub fn text(&self) -> &str {
        &self.text
    }
}

/// Checks that the robot token's id equals the id in the path.
///
/// # Errors
/// `CloseReason::token_mismatch` when they differ.
pub fn authorize_robot(token_robot: &RobotId, path_robot: &RobotId) -> Result<(), CloseReason> {
    if token_robot == path_robot {
        Ok(())
    } else {
        Err(CloseReason::token_mismatch(token_robot, path_robot))
    }
}

#[cfg(test)]
mod tests {
    use domain::RobotId;

    use super::{CLOSE_CONFLICT, CLOSE_FORBIDDEN, CloseReason, authorize_robot};
    use crate::error::RealtimeError;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn mismatch_names_both_robots() -> TestResult {
        let a: RobotId = "robot-r1".parse()?;
        let b: RobotId = "robot-r2".parse()?;
        assert!(authorize_robot(&a, &a).is_ok());
        let refused = authorize_robot(&a, &b).err().ok_or("mismatch accepted")?;
        assert_eq!(refused.code(), CLOSE_FORBIDDEN);
        assert_eq!(
            refused.text(),
            "Token belongs to robot robot-r1 but the connection asks for robot robot-r2."
        );
        Ok(())
    }

    #[test]
    fn already_connected_is_4409() -> TestResult {
        let robot: RobotId = "robot-r1".parse()?;
        let reason = CloseReason::from_realtime(&RealtimeError::RobotAlreadyConnected { robot });
        assert_eq!(reason.code(), CLOSE_CONFLICT);
        assert!(reason.text().contains("already connected"));
        Ok(())
    }
}
