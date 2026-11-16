//! Token identity. The verifier is a trait so this crate does not depend on `storage`; the
//! binary adapts `SqliteTokenStore` (`TokenStoreVerifier`).

use async_trait::async_trait;
use domain::{Actor, DeviceId, OwnerLabel, Role};

use crate::error::SecurityError;
use crate::known_networks::ClientNetwork;

/// Who a valid token belongs to.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedIdentity {
    /// The subject: `Actor::User` or `Actor::Robot`.
    pub subject_id: Actor,
    /// Role.
    pub role: Role,
    /// Device the token was issued to (users who logged in from a tablet). `None` for a
    /// browser login (the admin console) and for robots. Strict rule for a device-less token:
    /// an `X-Client-Id` header is refused (403 `identity_mismatch`), and the tablet-only
    /// endpoints refuse it (403 `device_required`, see the binary's `TabletAuthorized`).
    pub device_id: Option<DeviceId>,
    /// Owner label (users only).
    pub owner: Option<OwnerLabel>,
}

/// Checks a raw bearer token.
#[async_trait]
pub trait TokenVerifier: Send + Sync {
    /// `Ok(None)` for an unknown, expired or revoked token.
    ///
    /// # Errors
    /// `VerifierUnavailable` when the store cannot be read.
    async fn verify(&self, raw: &str) -> Result<Option<VerifiedIdentity>, SecurityError>;
}

/// Inserted as a request extension by the identity layer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientIdentity {
    /// The token's identity.
    pub verified: VerifiedIdentity,
    /// The network.
    pub network: ClientNetwork,
}

/// The identity header; when present it must equal the token's `device_id` (else 403
/// `identity_mismatch`). A token bound to no device never matches: any `X-Client-Id` with
/// such a token is 403 `identity_mismatch`.
pub const CLIENT_ID_HEADER: &str = "x-client-id";
