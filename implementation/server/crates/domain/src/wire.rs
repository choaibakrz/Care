//! The error body shared by the API and the security layers (contract C3).

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// `{ "error": { "code", "message", "request_id"? } }`. `message` is safe to show to a user
/// and never contains SQL, file paths or internals.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct ErrorBody {
    /// The error.
    pub error: ErrorDetail,
}

/// The inside of an [`ErrorBody`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct ErrorDetail {
    /// Stable machine code, `snake_case` (for example `not_found`, `rate_limited`).
    pub code: String,
    /// Human message: what happened, to what, what to do.
    pub message: String,
    /// Request id when one was assigned.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_id: Option<String>,
    /// Every problem found, when the server checked a whole document (Task A4: `invalid_plan`
    /// lists each `{path, problem}`; `place_in_use` and `open_tasks` list each user). Absent
    /// when empty.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub details: Vec<ErrorProblem>,
}

/// One problem of a refused document: where (`path`, for example `rooms[3].polygon`, or
/// `tasks/t-12` for a user of a place) and what, in words safe to show.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct ErrorProblem {
    /// Where, as a JSON-like path into the document (`rooms[3].polygon`) or the id of the
    /// record that uses the thing (`tasks/t-12`, `inventory/blanket`).
    pub path: String,
    /// What is wrong, safe to show to a user.
    pub problem: String,
}

impl ErrorBody {
    /// Builds a body.
    #[must_use]
    pub fn new(code: &str, message: String, request_id: Option<String>) -> ErrorBody {
        ErrorBody {
            error: ErrorDetail {
                code: code.to_owned(),
                message,
                request_id,
                details: Vec::new(),
            },
        }
    }
    /// The same body with its problem list (Task A4: `invalid_plan`, `place_in_use`,
    /// `open_tasks`).
    #[must_use]
    pub fn with_details(mut self, details: Vec<ErrorProblem>) -> ErrorBody {
        self.error.details = details;
        self
    }
}
