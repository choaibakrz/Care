//! Security errors. Each maps to an HTTP status and a stable `code` in the error body.

use std::net::IpAddr;

use axum::Json;
use axum::http::{HeaderValue, StatusCode, header};
use axum::response::{IntoResponse, Response};
use domain::ErrorBody;

/// Security errors: configuration problems at startup, and request rejections.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum SecurityError {
    /// `"*"` in the CORS list.
    #[error("CORS origin '*' is not allowed; list each allowed origin explicitly.")]
    WildcardOrigin,
    /// A malformed origin.
    #[error("CORS origin '{origin}' is not a valid origin ({reason}); use scheme://host[:port].")]
    InvalidOrigin {
        /// The value.
        origin: String,
        /// Why.
        reason: &'static str,
    },
    /// A malformed CIDR in the networks file.
    #[error("Network '{value}' is not a valid CIDR block; use a form like 192.168.1.0/24.")]
    InvalidCidr {
        /// The value.
        value: String,
    },
    /// Configuration value out of range.
    #[error("Security setting '{field}' is invalid: {reason}.")]
    InvalidConfig {
        /// Setting.
        field: &'static str,
        /// Why.
        reason: &'static str,
    },
    /// The networks file could not be loaded.
    #[error(
        "The known networks file could not be loaded ({reason}); check seed/known_networks.json."
    )]
    NetworkFile {
        /// Why (no file system path).
        reason: String,
    },
    /// Request from a network not on the list (code `network_not_allowed`).
    #[error(
        "Address {ip} is not on a network registered with the clinic server. Ask an administrator to add it."
    )]
    UnknownNetwork {
        /// The client address that was refused.
        ip: IpAddr,
    },
    /// Too many requests.
    #[error("Too many requests from this device. Wait {retry_after_s} s and try again.")]
    RateLimited {
        /// Seconds to wait.
        retry_after_s: u64,
    },
    /// The client address is covered by a block rule (Task A8): 403 `blocked`, with no other
    /// detail (the rule, its reason and who made it are for the admin only).
    #[error("Access from this address is blocked.")]
    Blocked,
    /// No bearer token.
    #[error("You are not logged in. Log in and send the token as 'Authorization: Bearer <token>'.")]
    MissingToken,
    /// Unknown, expired or revoked token.
    #[error("Your session is not valid (expired or revoked). Log in again.")]
    InvalidToken,
    /// `X-Client-Id` differs from the token's device.
    #[error(
        "The X-Client-Id header does not match the device this token was issued to. Log in again on this device."
    )]
    IdentityMismatch,
    /// WebSocket `Origin` missing or not allowed.
    #[error("This page's origin is not allowed to open a live connection. Use the clinic apps.")]
    OriginNotAllowed,
    /// The pepper key file can be read by other users of the computer (Task A7). Its
    /// path is in the operator's configuration (`ACCOUNT_PEPPER`), so it is named.
    #[error(
        "The account pepper file {path} can be read by other users. Restrict it to the server's user (chmod 600) and start again."
    )]
    PepperPermissions {
        /// The key file.
        path: String,
    },
    /// The pepper key file is not 32 bytes of hex, or cannot be read or created (Task A7).
    #[error(
        "The account pepper file {path} cannot be used ({reason}). Restore it from the backup: without it no account can log in."
    )]
    PepperUnusable {
        /// The key file.
        path: String,
        /// Why (never the key).
        reason: String,
    },
    /// The token store is down.
    #[error("Sessions cannot be checked right now. Try again in a moment.")]
    VerifierUnavailable,
}

impl SecurityError {
    /// Stable machine code.
    #[must_use]
    pub fn code(&self) -> &'static str {
        match self {
            SecurityError::WildcardOrigin => "wildcard_origin",
            SecurityError::InvalidOrigin { .. } => "invalid_origin",
            SecurityError::InvalidCidr { .. } => "invalid_cidr",
            SecurityError::InvalidConfig { .. } => "invalid_security_config",
            SecurityError::NetworkFile { .. } => "network_file_unreadable",
            SecurityError::UnknownNetwork { .. } => "network_not_allowed",
            SecurityError::RateLimited { .. } => "rate_limited",
            SecurityError::Blocked => "blocked",
            SecurityError::MissingToken => "missing_token",
            SecurityError::InvalidToken => "invalid_token",
            SecurityError::IdentityMismatch => "identity_mismatch",
            SecurityError::OriginNotAllowed => "origin_not_allowed",
            SecurityError::VerifierUnavailable => "verifier_unavailable",
            SecurityError::PepperPermissions { .. } => "pepper_permissions",
            SecurityError::PepperUnusable { .. } => "pepper_unusable",
        }
    }

    /// HTTP status.
    #[must_use]
    pub fn status(&self) -> StatusCode {
        match self {
            SecurityError::WildcardOrigin
            | SecurityError::InvalidOrigin { .. }
            | SecurityError::InvalidCidr { .. }
            | SecurityError::InvalidConfig { .. }
            | SecurityError::NetworkFile { .. }
            | SecurityError::PepperPermissions { .. }
            | SecurityError::PepperUnusable { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            SecurityError::UnknownNetwork { .. }
            | SecurityError::IdentityMismatch
            | SecurityError::OriginNotAllowed
            | SecurityError::Blocked => StatusCode::FORBIDDEN,
            SecurityError::RateLimited { .. } => StatusCode::TOO_MANY_REQUESTS,
            SecurityError::MissingToken | SecurityError::InvalidToken => StatusCode::UNAUTHORIZED,
            SecurityError::VerifierUnavailable => StatusCode::SERVICE_UNAVAILABLE,
        }
    }

    /// Whether this is a startup configuration problem (never sent to a client as such).
    #[must_use]
    pub fn is_configuration(&self) -> bool {
        self.status() == StatusCode::INTERNAL_SERVER_ERROR
    }
}

impl IntoResponse for SecurityError {
    fn into_response(self) -> Response {
        let status = self.status();
        // A configuration problem is an internal error: its text is for the operator's log.
        let body = if self.is_configuration() {
            ErrorBody::new(
                "internal",
                "Something went wrong on the server (security configuration). It was logged."
                    .to_owned(),
                None,
            )
        } else {
            ErrorBody::new(self.code(), self.to_string(), None)
        };
        let mut response = (status, Json(body)).into_response();
        if let SecurityError::RateLimited { retry_after_s } = self
            && let Ok(value) = HeaderValue::from_str(&retry_after_s.to_string())
        {
            response.headers_mut().insert(header::RETRY_AFTER, value);
        }
        response
    }
}
