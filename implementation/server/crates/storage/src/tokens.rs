//! `tokens(hash, subject_json, expires_at, revoked_at)`: only the SHA-256 of a 32-byte random
//! value is stored. `impl TokenVerifier` lives in the binary (`TokenStoreVerifier`), so this
//! crate does not depend on `security`.

use std::fmt;
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::{DeviceId, RobotId, Role, UserId};
use serde::{Deserialize, Serialize};
use sqlx::Row as _;

use crate::error::StorageError;
use crate::pool::Database;

/// Whom a token stands for.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum TokenSubject {
    /// A user, on a device when the client sent one (a tablet does; a browser does not).
    User {
        /// User.
        user_id: UserId,
        /// Role at issue time.
        role: Role,
        /// Device the token is bound to, if any.
        #[serde(default)]
        device_id: Option<DeviceId>,
    },
    /// A robot.
    Robot {
        /// Robot.
        robot_id: RobotId,
    },
}

/// The raw token, given to the client once. Never logged: `Debug` prints a placeholder.
#[derive(Clone, PartialEq, Eq)]
pub struct RawToken(String);

impl RawToken {
    /// The token text (to send to the client).
    #[must_use]
    pub fn expose(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for RawToken {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("RawToken(<redacted>)")
    }
}

/// The token store.
#[derive(Debug, Clone)]
pub struct SqliteTokenStore {
    db: Database,
}

impl SqliteTokenStore {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteTokenStore {
        SqliteTokenStore { db }
    }

    /// Issues a token valid for `ttl`.
    ///
    /// # Errors
    /// `Unavailable`.
    pub async fn issue(
        &self,
        subject: TokenSubject,
        ttl: Duration,
    ) -> Result<RawToken, StorageError> {
        let mut bytes = [0_u8; 32];
        getrandom::fill(&mut bytes).map_err(|_| StorageError::Unavailable)?;
        let raw = hex(&bytes);
        let subject_json =
            serde_json::to_string(&subject).map_err(|error| StorageError::Corrupt {
                table: "tokens",
                reason: error.to_string(),
            })?;
        let user_id = match &subject {
            TokenSubject::User { user_id, .. } => Some(user_id.to_string()),
            TokenSubject::Robot { .. } => None,
        };
        let ttl = chrono::Duration::from_std(ttl).unwrap_or_else(|_| chrono::Duration::hours(12));
        let expires_at = (Utc::now() + ttl).to_rfc3339();
        sqlx::query(
            "INSERT INTO tokens (hash, subject_json, user_id, expires_at) VALUES (?, ?, ?, ?)",
        )
        .bind(digest(&raw).to_vec())
        .bind(subject_json)
        .bind(user_id)
        .bind(expires_at)
        .execute(self.db.pool())
        .await?;
        Ok(RawToken(raw))
    }

    /// The subject of a valid (known, unexpired, unrevoked) token.
    ///
    /// # Errors
    /// `Unavailable`; `Corrupt`.
    pub async fn resolve(&self, raw: &str) -> Result<Option<TokenSubject>, StorageError> {
        let row =
            sqlx::query("SELECT subject_json, expires_at, revoked_at FROM tokens WHERE hash = ?")
                .bind(digest(raw).to_vec())
                .fetch_optional(self.db.pool())
                .await?;
        let Some(row) = row else {
            return Ok(None);
        };
        let revoked: Option<String> = row.try_get("revoked_at")?;
        let expires: String = row.try_get("expires_at")?;
        let expires =
            DateTime::parse_from_rfc3339(&expires).map_err(|_| StorageError::Corrupt {
                table: "tokens",
                reason: "expires_at".to_owned(),
            })?;
        if revoked.is_some() || expires <= Utc::now() {
            return Ok(None);
        }
        let subject: String = row.try_get("subject_json")?;
        serde_json::from_str(&subject)
            .map(Some)
            .map_err(|error| StorageError::Corrupt {
                table: "tokens",
                reason: error.to_string(),
            })
    }

    /// Revokes a token; `false` if it was unknown.
    ///
    /// # Errors
    /// `Unavailable`.
    pub async fn revoke(&self, raw: &str) -> Result<bool, StorageError> {
        let done =
            sqlx::query("UPDATE tokens SET revoked_at = ? WHERE hash = ? AND revoked_at IS NULL")
                .bind(Utc::now().to_rfc3339())
                .bind(digest(raw).to_vec())
                .execute(self.db.pool())
                .await?;
        Ok(done.rows_affected() > 0)
    }

    /// Revokes every token of a user (a disabled account); returns how many.
    ///
    /// # Errors
    /// `Unavailable`.
    pub async fn revoke_user(&self, user: &UserId) -> Result<u64, StorageError> {
        let done = sqlx::query(
            "UPDATE tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        )
        .bind(Utc::now().to_rfc3339())
        .bind(user.to_string())
        .execute(self.db.pool())
        .await?;
        Ok(done.rows_affected())
    }
}

/// SHA-256 of the raw token text (what is stored).
fn digest(raw: &str) -> [u8; 32] {
    use sha2::Digest as _;
    sha2::Sha256::digest(raw.as_bytes()).into()
}

/// Lowercase hex.
fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    bytes
        .iter()
        .fold(String::with_capacity(bytes.len() * 2), |mut out, byte| {
            let _infallible = write!(out, "{byte:02x}");
            out
        })
}
