//! `ApiError` (every error response is `{ "error": { "code", "message" } }`, plus `details`
//! when a whole document was checked: Task A4), the extractors
//! that turn rejections into `ApiError`, the 404/405 fallbacks, and `StartupError`.

use std::net::SocketAddr;
use std::time::Duration;

use audit::JournalError;
use axum::Json;
use axum::extract::rejection::{JsonRejection, PathRejection, QueryRejection};
use axum::extract::{FromRequest, FromRequestParts, Request};
use axum::http::StatusCode;
use axum::http::request::Parts;
use axum::response::{IntoResponse, Response};
use domain::{DomainError, ErrorBody, ErrorProblem, Permission, StockError};
use locations::{LocationError, PlanErrors, PositioningError};
use optimization::{OptimizationError, RouteError};
use python_bindings::BridgeError;
use realtime::RealtimeError;
use scheduler::SchedulerError;
use security::SecurityError;
use serde::de::DeserializeOwned;
use storage::StorageError;

use crate::config::ConfigError;
use crate::services::brain::BrainClientError;

/// The message of 503 `emergency_mode` (`emergency-mode.md`; the console shows it as is).
pub const EMERGENCY_MODE_MESSAGE: &str =
    "The clinic is in emergency mode: only emergency actions are accepted.";

/// An API error. Built only through the named constructors; `message` is safe to show to a
/// user and never contains SQL, file paths or internals.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
    /// Every problem of a refused document or every user of a thing (empty otherwise).
    details: Vec<ErrorProblem>,
}

impl ApiError {
    /// The one place an `ApiError` is assembled; every named constructor goes through it.
    fn build(status: StatusCode, code: &'static str, message: String) -> ApiError {
        ApiError {
            status,
            code,
            message,
            details: Vec::new(),
        }
    }

    /// 404 `not_found`: "Task 'x' was not found."
    #[must_use]
    pub fn not_found(what: &str, id: &str) -> ApiError {
        ApiError::build(
            StatusCode::NOT_FOUND,
            "not_found",
            format!("{what} '{id}' was not found. Check the id."),
        )
    }
    /// 422 `invalid_field`.
    #[must_use]
    pub fn invalid_input(field: &str, reason: &str) -> ApiError {
        ApiError::build(
            StatusCode::UNPROCESSABLE_ENTITY,
            "invalid_field",
            format!("Field `{field}` {reason}. Correct it and send the request again."),
        )
    }
    /// 409 with a specific code (`out_of_stock`, `task_not_cancellable`, …).
    #[must_use]
    pub fn conflict(code: &'static str, message: String) -> ApiError {
        ApiError::build(StatusCode::CONFLICT, code, message)
    }
    /// 401 `unauthorized`.
    #[must_use]
    pub fn unauthorized() -> ApiError {
        ApiError::build(
            StatusCode::UNAUTHORIZED,
            "unauthorized",
            "You are not logged in. Log in and try again.".to_owned(),
        )
    }
    /// 401 `invalid_credentials`: "User name or password is incorrect." The same answer for
    /// an unknown user and a wrong password, so neither can be told apart.
    #[must_use]
    pub fn invalid_credentials() -> ApiError {
        ApiError::build(
            StatusCode::UNAUTHORIZED,
            "invalid_credentials",
            "User name or password is incorrect.".to_owned(),
        )
    }
    /// 403 `forbidden`, naming the missing permission.
    #[must_use]
    pub fn forbidden(permission: Permission) -> ApiError {
        ApiError::build(
            StatusCode::FORBIDDEN,
            "forbidden",
            format!("Your role does not have the permission {permission}. Ask an administrator."),
        )
    }
    /// 403 `device_required`: the token is bound to no device (a browser login) and the
    /// endpoint is for tablets only: "This action needs the tablet app: log in on a tablet."
    #[must_use]
    pub fn device_required() -> ApiError {
        ApiError::build(
            StatusCode::FORBIDDEN,
            "device_required",
            "This action needs the tablet app: log in on a tablet.".to_owned(),
        )
    }
    /// 422 `key_derivation_required` (Task A7): a `{username, password}` login body reached
    /// the live server. The server never takes a user name or a password; the client derives
    /// the account key and sends `{account_key}` (`docs/accounts.md`). The password is not
    /// read, logged or journaled.
    #[must_use]
    pub fn key_derivation_required() -> ApiError {
        ApiError::build(
            StatusCode::UNPROCESSABLE_ENTITY,
            "key_derivation_required",
            "This server never receives a user name or a password: the app must derive the account key and send {account_key} (see docs/accounts.md). Update the app.".to_owned(),
        )
    }
    /// 409 `ambiguous_account_tag` (Task A7): two accounts share this 6-digit tag (a 24-bit
    /// collision); the admin must tell them apart by pseudonym in `GET /admin/accounts`.
    #[must_use]
    pub fn ambiguous_account_tag(tag: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "ambiguous_account_tag",
            format!(
                "Several accounts have the tag {tag}. Disable the right one by asking its holder to log in, then contact the server operator."
            ),
        )
    }
    /// 409 `cannot_disable_self` (Task A7): an admin cannot disable their own account.
    #[must_use]
    pub fn cannot_disable_self() -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "cannot_disable_self",
            "You cannot disable your own account. Ask another administrator.".to_owned(),
        )
    }
    /// 409 `not_revertible` (Task A7): the command cannot be undone from the server (an
    /// emergency stop, a shutdown, or a command the admin sent).
    #[must_use]
    pub fn not_revertible(reason: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "not_revertible",
            format!("This command cannot be reverted: {reason}."),
        )
    }
    /// 409 `already_reverted` (Task A7): the command was reverted before.
    #[must_use]
    pub fn already_reverted(by: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "already_reverted",
            format!("This command was already reverted by command {by}. Nothing was sent."),
        )
    }
    /// 409 `already_reverted` (Task A7) while another admin's revert of the same command is
    /// being sent: only one inverse command goes out.
    #[must_use]
    pub fn revert_in_progress() -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "already_reverted",
            "This command is being reverted by another request. Nothing was sent.".to_owned(),
        )
    }
    /// 409 `superseded` (Task A7, ruling R24): a later command was sent to the same robot,
    /// so reverting this one could undo what came after it.
    #[must_use]
    pub fn superseded(robot: &str, later: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "superseded",
            format!(
                "This command can no longer be reverted: command {later} was sent to robot {robot} after it. Send the command you need instead. Nothing was sent."
            ),
        )
    }
    /// 409 `estop_latched` (ruling R24): the robot is in emergency stop; only an admin's
    /// explicit `resume` re-arms it, and no revert targets it meanwhile.
    #[must_use]
    pub fn estop_latched(robot: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "estop_latched",
            format!(
                "Robot {robot} is in emergency stop. Only an admin can re-arm a robot after an emergency stop. Nothing was sent."
            ),
        )
    }
    /// 503 `journal_unavailable`: "Actions are paused because they cannot be recorded."
    #[must_use]
    pub fn journal_unavailable() -> ApiError {
        ApiError::build(
            StatusCode::SERVICE_UNAVAILABLE,
            "journal_unavailable",
            "Actions are paused because they cannot be recorded. Try again later; an administrator has been alerted.".to_owned(),
        )
    }
    /// 501 `not_implemented_yet` (step R1): this part of the live server is not built yet;
    /// the console shows its panel as "not available yet". `task` names the build-out task.
    #[must_use]
    pub fn not_implemented(task: &str) -> ApiError {
        ApiError::build(
            StatusCode::NOT_IMPLEMENTED,
            "not_implemented_yet",
            format!("This feature is not implemented on the server yet ({task})."),
        )
    }
    /// 503 `unavailable` for a dependency that is down.
    #[must_use]
    pub fn unavailable(what: &'static str) -> ApiError {
        ApiError::build(
            StatusCode::SERVICE_UNAVAILABLE,
            "unavailable",
            format!("The {what} is unavailable right now. Try again in a moment."),
        )
    }
    /// 500 `internal`; the detail goes to tracing, not to the client.
    #[must_use]
    pub fn internal(what: &'static str) -> ApiError {
        tracing::error!(what, "internal error answered with 500");
        ApiError::build(
            StatusCode::INTERNAL_SERVER_ERROR,
            "internal",
            format!("Something went wrong on the server ({what}). It was logged."),
        )
    }
    /// 404 `not_found` for an unknown route.
    #[must_use]
    pub fn route_not_found() -> ApiError {
        ApiError::build(
            StatusCode::NOT_FOUND,
            "not_found",
            "This address does not exist. See /docs for the API.".to_owned(),
        )
    }
    /// 405 `method_not_allowed`.
    #[must_use]
    pub fn method_not_allowed() -> ApiError {
        ApiError::build(
            StatusCode::METHOD_NOT_ALLOWED,
            "method_not_allowed",
            "This method is not allowed here. See /docs.".to_owned(),
        )
    }
    /// 422 `invalid_plan`: "The clinic plan has N problem(s); …", with one detail per
    /// problem (`{path, problem}`), never empty.
    #[must_use]
    pub fn invalid_plan(errors: PlanErrors) -> ApiError {
        let message = errors.to_string();
        ApiError {
            details: errors.0.into_iter().map(ErrorProblem::from).collect(),
            ..ApiError::build(StatusCode::UNPROCESSABLE_ENTITY, "invalid_plan", message)
        }
    }
    /// 428 `if_match_required`: "Send the plan version you edited in If-Match, so a newer
    /// change is not overwritten."
    #[must_use]
    pub fn if_match_required() -> ApiError {
        ApiError::build(
            StatusCode::PRECONDITION_REQUIRED,
            "if_match_required",
            "Send the plan version you edited in If-Match, so a newer change is not overwritten."
                .to_owned(),
        )
    }
    /// 412 `version_conflict`: "Clinic plan 'x' was changed by someone else (now version N).
    /// Reload it and redo your change."
    #[must_use]
    pub fn version_conflict(clinic: &str, current: u64) -> ApiError {
        ApiError::build(
            StatusCode::PRECONDITION_FAILED,
            "version_conflict",
            format!(
                "Clinic plan '{clinic}' was changed by someone else (now version {current}). Reload it and redo your change."
            ),
        )
    }
    /// 409 with a code (`place_in_use`, `open_tasks`, `clinic_active`) and one detail per
    /// user of the thing (`{path: "tasks/t-12", problem: "open task to this place"}`).
    #[must_use]
    pub fn conflict_with_users(
        code: &'static str,
        message: String,
        users: Vec<ErrorProblem>,
    ) -> ApiError {
        ApiError {
            details: users,
            ..ApiError::build(StatusCode::CONFLICT, code, message)
        }
    }
    /// 404 `no_route` with the planner's reason ("The route goes from floor 0 to floor 2;
    /// robots do not take the lift, so no route is drawn.").
    #[must_use]
    pub fn no_route(reason: String) -> ApiError {
        ApiError::build(StatusCode::NOT_FOUND, "no_route", reason)
    }
    /// 503 `emergency_mode` (Task A8): the request is not on the emergency allow-list. The
    /// message is the one the console shows as is.
    #[must_use]
    pub fn emergency_mode() -> ApiError {
        ApiError::build(
            StatusCode::SERVICE_UNAVAILABLE,
            "emergency_mode",
            EMERGENCY_MODE_MESSAGE.to_owned(),
        )
    }
    /// 409 `already_free` (Task A8): `POST /devices/{id}/disconnect` on a free tablet.
    #[must_use]
    pub fn already_free(device: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "already_free",
            format!("Tablet {device} is already free."),
        )
    }
    /// 409 `in_use` (Task A8): `POST /devices/{id}/assign` on an assigned tablet.
    #[must_use]
    pub fn tablet_in_use(device: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "in_use",
            format!("Tablet {device} is in use. Free it first."),
        )
    }
    /// 409 `offline` (Task A8): `POST /devices/{id}/assign` on a tablet that is not connected.
    #[must_use]
    pub fn tablet_offline(device: &str) -> ApiError {
        ApiError::build(
            StatusCode::CONFLICT,
            "offline",
            format!("Tablet {device} is offline. Switch it on and connect it first."),
        )
    }
    /// 503 `brain_unavailable` (Task A6): the brain process is not running, not reachable,
    /// refused the token, or runs without Python. `reason` is safe to show (no paths).
    #[must_use]
    pub fn brain_unavailable(reason: &str) -> ApiError {
        ApiError::build(
            StatusCode::SERVICE_UNAVAILABLE,
            "brain_unavailable",
            format!(
                "The brain is not available ({reason}). Translation, simplification, summaries and reports are paused; everything else keeps working. Try again later or ask an administrator to start clinic-brain."
            ),
        )
    }
    /// 503 `brain_busy`: the brain's queue is full.
    #[must_use]
    pub fn brain_busy() -> ApiError {
        ApiError::build(
            StatusCode::SERVICE_UNAVAILABLE,
            "brain_busy",
            "The brain is busy with other requests. Try again in a moment.".to_owned(),
        )
    }
    /// 504 `brain_timeout`: the brain did not answer in time.
    #[must_use]
    pub fn brain_timeout(after: Duration) -> ApiError {
        ApiError::build(
            StatusCode::GATEWAY_TIMEOUT,
            "brain_timeout",
            format!(
                "The brain did not answer within {} s. Try a shorter text, or try again later.",
                after.as_secs()
            ),
        )
    }
    /// 502 `brain_failed`: the brain answered with an error or something unreadable. The
    /// detail goes to the log (never a text of the request).
    #[must_use]
    pub fn brain_failed(what: &'static str) -> ApiError {
        tracing::warn!(what, "brain call failed");
        ApiError::build(
            StatusCode::BAD_GATEWAY,
            "brain_failed",
            format!("The brain could not produce a draft ({what}). Try again, or do it by hand."),
        )
    }
    /// 422 `unsupported_language`: the brain cannot do this language pair yet.
    #[must_use]
    pub fn unsupported_language(message: String) -> ApiError {
        ApiError::build(
            StatusCode::UNPROCESSABLE_ENTITY,
            "unsupported_language",
            message,
        )
    }
    /// 413 `body_too_large` (the code the transport layer gives a 413): "The request body is
    /// too large. Send less data." Also what a brain-side 413 becomes on the main server.
    #[must_use]
    pub fn body_too_large() -> ApiError {
        ApiError::build(
            StatusCode::PAYLOAD_TOO_LARGE,
            "body_too_large",
            "The request body is too large. Send less data.".to_owned(),
        )
    }
    /// 403 `loopback_only`: the brain process serves this computer only.
    #[must_use]
    pub fn loopback_only() -> ApiError {
        ApiError::build(
            StatusCode::FORBIDDEN,
            "loopback_only",
            "The brain answers only the clinic server on this computer.".to_owned(),
        )
    }
    /// 401 `brain_token`: the brain token is missing or wrong.
    #[must_use]
    pub fn brain_token() -> ApiError {
        ApiError::build(
            StatusCode::UNAUTHORIZED,
            "brain_token",
            "The brain token is missing or wrong. Set the same BRAIN_TOKEN for clinic-server and clinic-brain."
                .to_owned(),
        )
    }
    /// The details (empty for most errors).
    #[must_use]
    pub fn details(&self) -> &[ErrorProblem] {
        &self.details
    }
    /// The machine code.
    #[must_use]
    pub fn code(&self) -> &'static str {
        self.code
    }
    /// The status.
    #[must_use]
    pub fn status(&self) -> StatusCode {
        self.status
    }
    /// The message.
    #[must_use]
    pub fn message(&self) -> &str {
        &self.message
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let body = ErrorBody::new(self.code, self.message, None).with_details(self.details);
        (self.status, Json(body)).into_response()
    }
}

impl From<DomainError> for ApiError {
    fn from(error: DomainError) -> Self {
        let message = error.to_string();
        match error {
            DomainError::InvalidId { .. }
            | DomainError::InvalidOwnerLabel { .. }
            | DomainError::MissingFailureReason { .. }
            | DomainError::MissingTaskField { .. }
            | DomainError::InvalidPage { .. }
            | DomainError::InvalidBrainInput { .. }
            | DomainError::InvalidAccountInput { .. } => {
                ApiError::build(StatusCode::UNPROCESSABLE_ENTITY, "invalid_field", message)
            }
            DomainError::EnrolmentRefused => {
                ApiError::build(StatusCode::FORBIDDEN, "enrolment_refused", message)
            }
            DomainError::AccountExists => {
                ApiError::build(StatusCode::CONFLICT, "account_exists", message)
            }
            DomainError::IllegalTransition { .. } => {
                ApiError::build(StatusCode::CONFLICT, "illegal_transition", message)
            }
            DomainError::InsufficientStock { .. } => {
                ApiError::build(StatusCode::CONFLICT, "insufficient_stock", message)
            }
            DomainError::Conflict { .. } => {
                ApiError::build(StatusCode::CONFLICT, "conflict", message)
            }
            DomainError::VersionConflict { .. } => {
                ApiError::build(StatusCode::PRECONDITION_FAILED, "version_conflict", message)
            }
            DomainError::NotFound { .. } => {
                ApiError::build(StatusCode::NOT_FOUND, "not_found", message)
            }
            DomainError::StoreUnavailable { .. } => {
                ApiError::build(StatusCode::SERVICE_UNAVAILABLE, "unavailable", message)
            }
            // The reason may name tables, columns or files: it goes to the log only.
            DomainError::Corrupt { table, reason } => {
                tracing::error!(table, %reason, "stored data could not be read back");
                ApiError::internal("stored data")
            }
        }
    }
}

impl From<(&'static str, security::BlockError)> for ApiError {
    /// A refused block rule (Task A8): 422 `invalid_field` naming the field, 422
    /// `range_too_broad`, 422 `protected_target` (the message says which address), 404
    /// `not_found`.
    fn from((field, error): (&'static str, security::BlockError)) -> Self {
        use security::BlockError;
        match error {
            BlockError::InvalidTarget | BlockError::InvalidReason | BlockError::InvalidExpiry => {
                ApiError::invalid_input(field, &error.to_string())
            }
            BlockError::RangeTooBroad { .. } => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "range_too_broad",
                error.to_string(),
            ),
            BlockError::Protected { .. } => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "protected_target",
                error.to_string(),
            ),
            BlockError::NotFound { .. } => {
                ApiError::build(StatusCode::NOT_FOUND, "not_found", error.to_string())
            }
        }
    }
}

impl From<SecurityError> for ApiError {
    fn from(error: SecurityError) -> Self {
        if error.is_configuration() {
            tracing::error!(%error, "security configuration error reached a request");
            return ApiError::internal("security configuration");
        }
        ApiError::build(error.status(), error.code(), error.to_string())
    }
}

impl From<LocationError> for ApiError {
    fn from(error: LocationError) -> Self {
        match error {
            LocationError::InvalidPlan(errors) => ApiError::invalid_plan(errors),
            LocationError::UnknownPlace { .. } => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "unknown_place",
                error.to_string(),
            ),
            other => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "invalid_field",
                other.to_string(),
            ),
        }
    }
}

impl From<PlanErrors> for ApiError {
    fn from(errors: PlanErrors) -> Self {
        ApiError::invalid_plan(errors)
    }
}

impl From<RouteError> for ApiError {
    fn from(error: RouteError) -> Self {
        ApiError::no_route(error.to_string())
    }
}

impl From<PositioningError> for ApiError {
    fn from(error: PositioningError) -> Self {
        match error {
            PositioningError::Map(inner) => ApiError::from(inner),
            PositioningError::Seed { reason } => {
                tracing::error!(%reason, "positioning seed data reached a request");
                ApiError::internal("positioning seed data")
            }
            other => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "invalid_scan",
                other.to_string(),
            ),
        }
    }
}

impl From<StockError> for ApiError {
    fn from(error: StockError) -> Self {
        match error {
            StockError::OutOfStock { .. } => {
                ApiError::build(StatusCode::CONFLICT, "out_of_stock", error.to_string())
            }
            StockError::UnknownItem { item } => ApiError::not_found("Item", item.as_str()),
            StockError::ReservationGone { .. } => {
                ApiError::build(StatusCode::CONFLICT, "reservation_gone", error.to_string())
            }
            StockError::Store(inner) => ApiError::from(inner),
        }
    }
}

impl From<SchedulerError> for ApiError {
    fn from(error: SchedulerError) -> Self {
        match error {
            SchedulerError::Repository(inner) => ApiError::from(inner),
            SchedulerError::TaskCreation { .. } => {
                tracing::warn!(%error, "a schedule could not create its task");
                ApiError::unavailable("task creation")
            }
            other => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "invalid_schedule",
                other.to_string(),
            ),
        }
    }
}

impl From<JournalError> for ApiError {
    fn from(error: JournalError) -> Self {
        match error {
            JournalError::LimitOutOfRange { .. } => ApiError::build(
                StatusCode::UNPROCESSABLE_ENTITY,
                "invalid_field",
                error.to_string(),
            ),
            other => {
                tracing::error!(error = %other, "journal error reached a request");
                ApiError::journal_unavailable()
            }
        }
    }
}

impl From<RealtimeError> for ApiError {
    fn from(error: RealtimeError) -> Self {
        match error {
            RealtimeError::RobotNotConnected { .. } => {
                ApiError::build(StatusCode::CONFLICT, "robot_offline", error.to_string())
            }
            other => ApiError::build(
                StatusCode::SERVICE_UNAVAILABLE,
                "unavailable",
                other.to_string(),
            ),
        }
    }
}

impl From<BridgeError> for ApiError {
    /// Errors of the brain engine (in the `clinic-brain` process). Python exception texts and
    /// import details go to the log only.
    fn from(error: BridgeError) -> Self {
        match error {
            BridgeError::InterpreterUnavailable { detail } => ApiError::brain_unavailable(&detail),
            BridgeError::ImportFailed { module, .. } => {
                tracing::error!(%module, "a Python brick could not be imported");
                ApiError::brain_unavailable("a Python brick could not be loaded")
            }
            BridgeError::Busy { .. } => ApiError::brain_busy(),
            BridgeError::Timeout { after } => ApiError::brain_timeout(after),
            BridgeError::UnsupportedLanguage { .. } => {
                ApiError::unsupported_language(error.to_string())
            }
            BridgeError::PythonRaised { exception_type, .. } => {
                tracing::warn!(%exception_type, "a Python brick raised");
                ApiError::brain_failed("the model raised an error")
            }
            BridgeError::Conversion { field } => {
                tracing::warn!(%field, "a Python result could not be converted");
                ApiError::brain_failed("unreadable model answer")
            }
        }
    }
}

impl From<BrainClientError> for ApiError {
    /// Errors of the main server's brain client. The brain's refusals keep their **code**,
    /// but the message the client sees is always a fixed text of this server: the brain's own
    /// message may repeat a request text (a 422 quoting its input), so it is never forwarded
    /// (nor logged). A brain that is not running, not configured, or refusing the server's
    /// token is 503 `brain_unavailable`.
    fn from(error: BrainClientError) -> Self {
        match &error {
            BrainClientError::Timeout { after } => ApiError::brain_timeout(*after),
            BrainClientError::Malformed { .. } => ApiError::brain_failed("unreadable answer"),
            BrainClientError::Refused { code, .. } => match code.as_str() {
                "brain_busy" => ApiError::brain_busy(),
                "brain_timeout" => ApiError::build(
                    StatusCode::GATEWAY_TIMEOUT,
                    "brain_timeout",
                    "The brain did not finish in time. Try a shorter text, or try again later."
                        .to_owned(),
                ),
                "brain_failed" => ApiError::brain_failed("the model could not produce a draft"),
                "unsupported_language" => ApiError::unsupported_language(
                    "The brain cannot translate this language pair yet (French to English only today); ask a human interpreter."
                        .to_owned(),
                ),
                "invalid_field" | "invalid_json" => ApiError::build(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    "invalid_field",
                    "The brain refused the request as invalid. Check the texts and languages, then try again."
                        .to_owned(),
                ),
                "body_too_large" => ApiError::body_too_large(),
                _ => ApiError::brain_unavailable(&error.reason()),
            },
            BrainClientError::NotConfigured | BrainClientError::Unreachable { .. } => {
                ApiError::brain_unavailable(&error.reason())
            }
        }
    }
}

impl From<OptimizationError> for ApiError {
    fn from(error: OptimizationError) -> Self {
        match error {
            OptimizationError::TooManyStops { .. } | OptimizationError::UnknownPlace { .. } => {
                ApiError::build(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    "invalid_field",
                    error.to_string(),
                )
            }
            OptimizationError::EmptyFleet => {
                ApiError::build(StatusCode::CONFLICT, "no_robot", error.to_string())
            }
            OptimizationError::RoleCards { reason } => {
                tracing::error!(%reason, "role cards error reached a request");
                ApiError::internal("role cards")
            }
            OptimizationError::Oracle { detail } => {
                tracing::error!(%detail, "dispatch oracle error reached a request");
                ApiError::internal("dispatch oracle")
            }
        }
    }
}

/// JSON body extractor: every rejection becomes `invalid_json` or `invalid_field` with the
/// parser's position in the message.
#[derive(Debug, Clone, Copy, Default)]
pub struct ApiJson<T>(pub T);

impl<S, T> FromRequest<S> for ApiJson<T>
where
    T: DeserializeOwned,
    S: Send + Sync,
{
    type Rejection = ApiError;

    async fn from_request(req: Request, state: &S) -> Result<Self, Self::Rejection> {
        match Json::<T>::from_request(req, state).await {
            Ok(Json(value)) => Ok(ApiJson(value)),
            Err(rejection) => Err(json_rejection(&rejection)),
        }
    }
}

/// Query extractor with `ApiError` rejections (`invalid_field`).
#[derive(Debug, Clone, Copy, Default)]
pub struct ApiQuery<T>(pub T);

impl<S, T> FromRequestParts<S> for ApiQuery<T>
where
    T: DeserializeOwned,
    S: Send + Sync,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        match axum::extract::Query::<T>::from_request_parts(parts, state).await {
            Ok(axum::extract::Query(value)) => Ok(ApiQuery(value)),
            Err(rejection) => Err(query_rejection(&rejection)),
        }
    }
}

/// Path extractor with `ApiError` rejections (an invalid id is 422 `invalid_field`).
#[derive(Debug, Clone, Copy, Default)]
pub struct ApiPath<T>(pub T);

impl<S, T> FromRequestParts<S> for ApiPath<T>
where
    T: DeserializeOwned + Send,
    S: Send + Sync,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        match axum::extract::Path::<T>::from_request_parts(parts, state).await {
            Ok(axum::extract::Path(value)) => Ok(ApiPath(value)),
            Err(rejection) => Err(path_rejection(&rejection)),
        }
    }
}

/// A JSON body rejection: a syntax error is 400 `invalid_json`, a well-formed body of the
/// wrong shape 422 `invalid_field`; both messages quote the parser (field name, line and
/// column). The body itself is never echoed.
fn json_rejection(rejection: &JsonRejection) -> ApiError {
    match rejection {
        JsonRejection::JsonSyntaxError(_) => ApiError::build(
            StatusCode::BAD_REQUEST,
            "invalid_json",
            format!(
                "The request body is not valid JSON ({}). Fix it and send it again.",
                rejection.body_text()
            ),
        ),
        JsonRejection::JsonDataError(_) => ApiError::build(
            StatusCode::UNPROCESSABLE_ENTITY,
            "invalid_field",
            format!(
                "The request body does not have the expected fields ({}). See /docs for this route.",
                rejection.body_text()
            ),
        ),
        // A body over the route's limit (the stack's or the brain's): the JSON shape of 413.
        _ if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => ApiError::body_too_large(),
        JsonRejection::MissingJsonContentType(_) => ApiError::build(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "invalid_json",
            "Send the body as JSON with the header 'Content-Type: application/json'.".to_owned(),
        ),
        _ => ApiError::build(
            rejection.status(),
            "invalid_json",
            format!(
                "The request body could not be read ({}).",
                rejection.body_text()
            ),
        ),
    }
}

/// A query string rejection: 422 `invalid_field` quoting the parser.
fn query_rejection(rejection: &QueryRejection) -> ApiError {
    ApiError::build(
        StatusCode::UNPROCESSABLE_ENTITY,
        "invalid_field",
        format!(
            "The query string is not valid ({}). See /docs for this route.",
            rejection.body_text()
        ),
    )
}

/// A path rejection: an invalid id is 422 `invalid_field`; a route without the expected
/// parameters is a programming error (500).
fn path_rejection(rejection: &PathRejection) -> ApiError {
    if let PathRejection::FailedToDeserializePathParams(_) = rejection {
        return ApiError::build(
            StatusCode::UNPROCESSABLE_ENTITY,
            "invalid_field",
            format!(
                "The id in the address is not valid ({}).",
                rejection.body_text()
            ),
        );
    }
    tracing::error!(rejection = %rejection.body_text(), "path parameters missing");
    ApiError::internal("route parameters")
}

/// Fallback for unknown routes.
pub async fn fallback_not_found() -> ApiError {
    ApiError::route_not_found()
}

/// Fallback for a known route with the wrong method.
pub async fn fallback_method_not_allowed() -> ApiError {
    ApiError::method_not_allowed()
}

/// Why the server could not start or stop cleanly.
#[derive(Debug, thiserror::Error)]
pub enum StartupError {
    /// Configuration.
    #[error("Configuration problem: {0}")]
    Config(#[from] ConfigError),
    /// Journal.
    #[error("Journal problem: {0}")]
    Journal(#[from] JournalError),
    /// Database.
    #[error("Database problem: {0}")]
    Storage(#[from] StorageError),
    /// Security configuration.
    #[error("Security configuration problem: {0}")]
    Security(#[from] SecurityError),
    /// Map.
    #[error("Map problem: {0}")]
    Map(#[from] LocationError),
    /// Startup work after the wiring (clinic bootstrap, routing graph) failed.
    #[error("Startup could not finish: {reason}")]
    Bootstrap {
        /// Why (the API error's safe message).
        reason: String,
    },
    /// Demo mode seed data (`seed/demo_fleet.json`).
    #[error("Demo mode problem: {reason}. Re-run scripts/export_console_clinic.mjs.")]
    Demo {
        /// Why.
        reason: String,
    },
    /// Positioning seed data.
    #[error("Positioning problem: {0}")]
    Positioning(#[from] PositioningError),
    /// Role cards.
    #[error("Dispatch configuration problem: {0}")]
    Optimization(#[from] OptimizationError),
    /// Cannot listen.
    #[error("Cannot listen on {addr}: {source}. Is another server running on that port?")]
    Bind {
        /// Address.
        addr: SocketAddr,
        /// Cause.
        #[source]
        source: std::io::Error,
    },
    /// The server stopped with an error.
    #[error("The server stopped with an error: {0}")]
    Serve(#[source] std::io::Error),
    /// An I/O operation.
    #[error("Could not {action}: {source}")]
    Io {
        /// What.
        action: &'static str,
        /// Cause.
        #[source]
        source: std::io::Error,
    },
    /// JSON output.
    #[error("Could not produce JSON output: {0}")]
    OpenApi(#[source] serde_json::Error),
    /// Tracing setup.
    #[error("Could not start logging: {detail}")]
    Tracing {
        /// Why.
        detail: String,
    },
    /// A background task failed.
    #[error("The {what} task ended abnormally: {detail}")]
    Task {
        /// Which.
        what: &'static str,
        /// Why.
        detail: String,
    },
    /// `journal verify` found tampering.
    #[error(
        "The journal is not clean (first bad record: {first_bad_record:?}); see the report above."
    )]
    JournalNotClean {
        /// First bad record.
        first_bad_record: Option<u64>,
    },
}
