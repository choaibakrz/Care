//! `accounts(id, role, display_label, created_at, disabled)` and
//! `enrolment_codes(id, code_hash, role, suggested_label, created_at, expires_at, used_at)`
//! (migration `0110_accounts.sql`, Task A7).
//!
//! No user name, password, account key or enrolment code in clear: `accounts.id` is
//! `HMAC-SHA256(pepper, account_key)` as 64 hex digits, `enrolment_codes.code_hash` the HMAC
//! of the code. The pepper is a key file, never in this database.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use domain::ports::AccountRepository;
use domain::{
    AccountEnrolment, AccountId, AccountRecord, AccountTag, DomainError, EnrolmentRecord,
    OwnerLabel, Role,
};
use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::pool::Database;

/// Accounts and enrolment codes in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteAccountRepository {
    db: Database,
}

impl SqliteAccountRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteAccountRepository {
        SqliteAccountRepository { db }
    }
}

#[async_trait]
impl AccountRepository for SqliteAccountRepository {
    async fn find(&self, id: &AccountId) -> Result<Option<AccountRecord>, DomainError> {
        let row = sqlx::query(
            "SELECT id, role, display_label, created_at, disabled FROM accounts WHERE id = ?",
        )
        .bind(id.to_string())
        .fetch_optional(self.db.pool())
        .await
        .map_err(unavailable)?;
        row.as_ref().map(record_of).transpose()
    }
    async fn find_by_tag(&self, tag: &AccountTag) -> Result<Vec<AccountRecord>, DomainError> {
        let rows = sqlx::query(
            "SELECT id, role, display_label, created_at, disabled FROM accounts WHERE substr(id, 1, 6) = ? ORDER BY created_at",
        )
            .bind(tag.as_str())
            .fetch_all(self.db.pool())
            .await
            .map_err(unavailable)?;
        rows.iter().map(record_of).collect()
    }
    async fn list(&self) -> Result<Vec<AccountRecord>, DomainError> {
        let rows = sqlx::query("SELECT id, role, display_label, created_at, disabled FROM accounts ORDER BY created_at, id")
            .fetch_all(self.db.pool())
            .await
            .map_err(unavailable)?;
        rows.iter().map(record_of).collect()
    }
    async fn insert(&self, account: &AccountRecord) -> Result<(), DomainError> {
        insert_account(self.db.pool(), account).await
    }
    async fn set_disabled(&self, id: &AccountId, disabled: bool) -> Result<bool, DomainError> {
        let done = sqlx::query("UPDATE accounts SET disabled = ? WHERE id = ?")
            .bind(i64::from(disabled))
            .bind(id.to_string())
            .execute(self.db.pool())
            .await
            .map_err(unavailable)?;
        Ok(done.rows_affected() > 0)
    }
    async fn retire_unused_codes(&self, now: DateTime<Utc>) -> Result<u64, DomainError> {
        let done = sqlx::query("UPDATE enrolment_codes SET used_at = ? WHERE used_at IS NULL")
            .bind(now.to_rfc3339())
            .execute(self.db.pool())
            .await
            .map_err(unavailable)?;
        Ok(done.rows_affected())
    }
    async fn add_enrolment_code(&self, code: &EnrolmentRecord) -> Result<(), DomainError> {
        sqlx::query(
            "INSERT INTO enrolment_codes (id, code_hash, role, suggested_label, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(code.id.to_string())
        .bind(code.code_hash.to_vec())
        .bind(role_text(code.role))
        .bind(code.suggested_label.as_ref().map(|label| label.as_str().to_owned()))
        .bind(code.created_at.to_rfc3339())
        .bind(code.expires_at.to_rfc3339())
        .bind(code.used_at.map(|at| at.to_rfc3339()))
        .execute(self.db.pool())
        .await
        .map_err(unavailable)?;
        Ok(())
    }
    async fn enrol(
        &self,
        code_hash: &[u8; 32],
        now: DateTime<Utc>,
        id: AccountId,
        display_label: &OwnerLabel,
    ) -> Result<AccountEnrolment, DomainError> {
        let mut tx = self.db.pool().begin().await.map_err(unavailable)?;
        let row = sqlx::query(
            "SELECT id, role, expires_at FROM enrolment_codes WHERE code_hash = ? AND used_at IS NULL",
        )
        .bind(code_hash.to_vec())
        .fetch_optional(&mut *tx)
        .await
        .map_err(unavailable)?;
        let Some(row) = row else {
            return Err(DomainError::EnrolmentRefused);
        };
        let expires: String = row.try_get("expires_at").map_err(unavailable)?;
        if parse_time(&expires)? <= now {
            return Err(DomainError::EnrolmentRefused);
        }
        let code_id: String = row.try_get("id").map_err(unavailable)?;
        let role: String = row.try_get("role").map_err(unavailable)?;
        let account = AccountRecord {
            id,
            role: parse_role(&role)?,
            display_label: display_label.clone(),
            created_at: now,
            disabled: false,
        };
        insert_account(&mut *tx, &account).await?;
        let marked =
            sqlx::query("UPDATE enrolment_codes SET used_at = ? WHERE id = ? AND used_at IS NULL")
                .bind(now.to_rfc3339())
                .bind(&code_id)
                .execute(&mut *tx)
                .await
                .map_err(unavailable)?;
        if marked.rows_affected() != 1 {
            // Used by a concurrent enrolment: the transaction is dropped (rolled back).
            return Err(DomainError::EnrolmentRefused);
        }
        tx.commit().await.map_err(unavailable)?;
        Ok(AccountEnrolment {
            account,
            code_id: code_id.parse().map_err(|_| corrupt("enrolment code id"))?,
        })
    }
}

/// Whether the database holds any account or enrolment code (then the installation is not
/// fresh, and a missing pepper must not be created again).
///
/// # Errors
/// `Unavailable`.
pub async fn has_account_data(db: &Database) -> Result<bool, crate::StorageError> {
    let row = sqlx::query(
        "SELECT EXISTS(SELECT 1 FROM accounts) OR EXISTS(SELECT 1 FROM enrolment_codes) AS found",
    )
    .fetch_one(db.pool())
    .await?;
    let found: i64 = row.try_get("found")?;
    Ok(found != 0)
}

fn unavailable(_error: sqlx::Error) -> DomainError {
    DomainError::StoreUnavailable { what: "account" }
}

fn corrupt(reason: &str) -> DomainError {
    DomainError::Corrupt {
        table: "accounts",
        reason: reason.to_owned(),
    }
}

fn parse_time(text: &str) -> Result<DateTime<Utc>, DomainError> {
    DateTime::parse_from_rfc3339(text)
        .map(|at| at.with_timezone(&Utc))
        .map_err(|_| corrupt("time"))
}

/// The stored form of a role (`nurse`, `admin`, ...).
fn role_text(role: Role) -> String {
    serde_json::to_value(role)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_default()
}

fn parse_role(text: &str) -> Result<Role, DomainError> {
    serde_json::from_value(serde_json::Value::String(text.to_owned())).map_err(|_| corrupt("role"))
}

fn record_of(row: &SqliteRow) -> Result<AccountRecord, DomainError> {
    let id: String = row.try_get("id").map_err(unavailable)?;
    let role: String = row.try_get("role").map_err(unavailable)?;
    let label: String = row.try_get("display_label").map_err(unavailable)?;
    let created: String = row.try_get("created_at").map_err(unavailable)?;
    let disabled: i64 = row.try_get("disabled").map_err(unavailable)?;
    Ok(AccountRecord {
        id: id.parse().map_err(|_| corrupt("id"))?,
        role: parse_role(&role)?,
        display_label: OwnerLabel::new(&label).map_err(|_| corrupt("display_label"))?,
        created_at: parse_time(&created)?,
        disabled: disabled != 0,
    })
}

async fn insert_account<'e, E>(executor: E, account: &AccountRecord) -> Result<(), DomainError>
where
    E: sqlx::Executor<'e, Database = sqlx::Sqlite>,
{
    sqlx::query(
        "INSERT INTO accounts (id, role, display_label, created_at, disabled) VALUES (?, ?, ?, ?, ?)",
    )
    .bind(account.id.to_string())
    .bind(role_text(account.role))
    .bind(account.display_label.as_str().to_owned())
    .bind(account.created_at.to_rfc3339())
    .bind(i64::from(account.disabled))
    .execute(executor)
    .await
    .map_err(|error| match &error {
        sqlx::Error::Database(db) if db.is_unique_violation() => DomainError::AccountExists,
        _ => unavailable(error),
    })?;
    Ok(())
}
