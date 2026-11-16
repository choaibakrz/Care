//! Real `AuthService` (pseudonymous accounts, Task A7) and the `TokenVerifier` adapter over
//! `SqliteTokenStore`.
//!
//! The server never receives a user name or a password: it gets the account key the client
//! derived (`docs/accounts.md`) and keeps only `account_id = HMAC-SHA256(pepper, key)`. The
//! pepper is a key file outside the database (`security::Pepper`).
//!
//! The adapter lives here, not in `storage`, so `storage` never depends on `security`.

use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use domain::ports::{AccountRepository, DeviceRepository};
use domain::{
    AccountId, AccountKey, AccountTag, Actor, ClinicId, Clock, DeviceId, DomainError,
    ENROLMENT_CODE_TTL, EnrolmentCode, EnrolmentRecord, OwnerLabel, Role, check_pseudonym,
};
use security::{
    ClientIdentity, ClientNetwork, Pepper, SecurityError, TokenVerifier, VerifiedIdentity,
    account_id, constant_time_eq, enrolment_code_hash,
};
use storage::{SqliteTokenStore, TokenSubject};
use uuid::Uuid;

use super::AuthService;
use crate::dto::{
    AccountView, EnrolRequest, EnrolledView, EnrolmentCodeRequest, EnrolmentCodeView,
    KeyDerivationParams, LoginResponse, MeView,
};
use crate::error::ApiError;

/// The derivation parameters every client of a server with this account clinic id uses
/// (`GET /auth/derivation`). Real code: constants and the configured id.
#[must_use]
pub fn derivation_params(clinic_id: &ClinicId) -> KeyDerivationParams {
    KeyDerivationParams {
        algorithm: domain::KEY_DERIVATION_ALGORITHM.to_owned(),
        iterations: domain::KEY_DERIVATION_ITERATIONS,
        key_bytes: u32::try_from(domain::ACCOUNT_KEY_BYTES).unwrap_or(32),
        clinic_id: clinic_id.clone(),
        salt: format!("clinic:{clinic_id}:<lowercase(NFC(username))>"),
        normalization: "NFC".to_owned(),
    }
}

/// What `RealAuthService` needs.
pub struct AuthDeps {
    /// Pseudonymous accounts and enrolment codes.
    pub accounts: Arc<dyn AccountRepository>,
    /// Devices.
    pub devices: Arc<dyn DeviceRepository>,
    /// Tokens.
    pub tokens: SqliteTokenStore,
    /// Journal (login, enrolment and account records; never a key or a code).
    pub journal: Journal,
    /// Clock.
    pub clock: Arc<dyn Clock>,
    /// Token lifetime.
    pub token_ttl: Duration,
    /// The pepper (`HMAC-SHA256(pepper, key)` = account id). Never logged.
    pub pepper: Arc<Pepper>,
    /// The account clinic id of the derivation salt (`ACCOUNT_CLINIC_ID`).
    pub clinic_id: ClinicId,
}

/// The real auth service.
pub struct RealAuthService {
    deps: AuthDeps,
}

impl RealAuthService {
    /// A service.
    #[must_use]
    pub fn new(deps: AuthDeps) -> RealAuthService {
        RealAuthService { deps }
    }

    /// First start (step R1): when no account exists, issues a one-time **admin** enrolment
    /// code (valid 24 h, journaled by code id only) and returns it so `main` prints it once
    /// in the startup log. `None` when an account exists (nothing is issued).
    ///
    /// # Errors
    /// Store or journal failures.
    pub async fn bootstrap_admin_code(&self) -> Result<Option<EnrolmentCodeView>, ApiError> {
        if !self.deps.accounts.list().await?.is_empty() {
            return Ok(None);
        }
        // No account yet, so every stored code is an earlier first-admin code: retire it.
        let retired = self
            .deps
            .accounts
            .retire_unused_codes(self.deps.clock.now())
            .await?;
        if retired > 0 {
            tracing::info!(retired, "earlier first-admin codes retired");
        }
        let view = self
            .issue_code(
                Actor::System("server"),
                EnrolmentCodeRequest {
                    role: Role::Admin,
                    label: OwnerLabel::new("Admin").ok(),
                },
            )
            .await?;
        Ok(Some(view))
    }

    /// Issues a one-time code: 60 random bits, only its HMAC stored, journaled by id.
    async fn issue_code(
        &self,
        actor: Actor,
        request: EnrolmentCodeRequest,
    ) -> Result<EnrolmentCodeView, ApiError> {
        if request.role == Role::Robot {
            return Err(ApiError::invalid_input(
                "role",
                "must be a staff role (robots get their keys at provisioning)",
            ));
        }
        let mut random = [0_u8; 8];
        getrandom::fill(&mut random).map_err(|_| ApiError::internal("randomness"))?;
        let code = EnrolmentCode::from_random(random);
        let now = self.deps.clock.now();
        let expires_at = now
            + chrono::Duration::from_std(ENROLMENT_CODE_TTL)
                .unwrap_or_else(|_| chrono::Duration::hours(24));
        let record = EnrolmentRecord {
            id: Uuid::new_v4(),
            code_hash: enrolment_code_hash(&self.deps.pepper, &code),
            role: request.role,
            suggested_label: request.label.clone(),
            created_at: now,
            expires_at,
            used_at: None,
        };
        self.deps.accounts.add_enrolment_code(&record).await?;
        self.journal(
            actor,
            RecordBody::EnrolmentCodeIssued {
                code_id: record.id,
                role: record.role,
                expires_at,
            },
        )
        .await?;
        Ok(EnrolmentCodeView {
            code: code.display(),
            code_id: record.id,
            role: record.role,
            label: request.label,
            expires_at,
        })
    }

    /// Appends one audit record; a journal that cannot write refuses the action.
    async fn journal(&self, actor: Actor, body: RecordBody) -> Result<(), ApiError> {
        self.deps
            .journal
            .append(Severity::Notice, Category::Audit, actor, body, None)
            .await
            .map_err(|_| ApiError::journal_unavailable())?;
        Ok(())
    }
}

#[async_trait]
impl AuthService for RealAuthService {
    async fn login(
        &self,
        key: &AccountKey,
        device: Option<DeviceId>,
        network: &ClientNetwork,
    ) -> Result<LoginResponse, ApiError> {
        let id = account_id(&self.deps.pepper, key);
        let account = self
            .deps
            .accounts
            .find(&id)
            .await?
            .filter(|account| constant_time_eq(account.id.as_bytes(), id.as_bytes()))
            .filter(|account| !account.disabled);
        let Some(account) = account else {
            self.journal(
                Actor::System("security"),
                RecordBody::LoginFailed {
                    device,
                    network: network.label.clone(),
                },
            )
            .await?;
            return Err(ApiError::invalid_credentials());
        };
        let user = account.id.user_id()?;
        // BUILD-OUT (step R1): the tablet registry (`DeviceRepository::register`, T6) is not
        // written yet; the token is still bound to the device the client named.
        let token = self
            .deps
            .tokens
            .issue(
                TokenSubject::User {
                    user_id: user.clone(),
                    role: account.role,
                    device_id: device.clone(),
                },
                self.deps.token_ttl,
            )
            .await
            .map_err(DomainError::from)?;
        self.journal(Actor::User(user), RecordBody::LoginSucceeded { device })
            .await?;
        Ok(LoginResponse {
            token: token.expose().to_owned(),
            role: account.role,
            operator: account.owner_label()?,
            expires_at: self.deps.clock.now()
                + chrono::Duration::from_std(self.deps.token_ttl)
                    .unwrap_or_else(|_| chrono::Duration::hours(12)),
        })
    }
    async fn login_with_password(
        &self,
        _username: &str,
        _password: &str,
        _device: Option<DeviceId>,
        _network: &ClientNetwork,
    ) -> Result<LoginResponse, ApiError> {
        // The live server never derives a key and never reads a password (Task A7). The
        // handler refuses this body before calling; this is the second line.
        Err(ApiError::key_derivation_required())
    }
    fn derivation(&self) -> KeyDerivationParams {
        derivation_params(&self.deps.clinic_id)
    }
    async fn enrol(
        &self,
        request: EnrolRequest,
        _network: &ClientNetwork,
    ) -> Result<EnrolledView, ApiError> {
        check_pseudonym(&request.display_label)?;
        let enrolled = self
            .deps
            .accounts
            .enrol(
                &enrolment_code_hash(&self.deps.pepper, &request.enrolment_code),
                self.deps.clock.now(),
                account_id(&self.deps.pepper, &request.account_key),
                &request.display_label,
            )
            .await?;
        let account = enrolled.account;
        self.journal(
            Actor::User(account.id.user_id()?),
            RecordBody::AccountEnrolled {
                code_id: enrolled.code_id,
                account: account.tag(),
                role: account.role,
            },
        )
        .await?;
        Ok(EnrolledView {
            account_tag: account.tag(),
            role: account.role,
            operator: account.owner_label()?,
        })
    }
    async fn issue_enrolment_code(
        &self,
        actor: &ClientIdentity,
        request: EnrolmentCodeRequest,
    ) -> Result<EnrolmentCodeView, ApiError> {
        self.issue_code(actor.verified.subject_id.clone(), request)
            .await
    }
    async fn list_accounts(&self) -> Result<Vec<AccountView>, ApiError> {
        Ok(self
            .deps
            .accounts
            .list()
            .await?
            .into_iter()
            .map(|account| AccountView {
                account_tag: account.tag(),
                display_label: account.display_label,
                role: account.role,
                created_at: account.created_at,
                disabled: account.disabled,
            })
            .collect())
    }
    async fn disable_account(
        &self,
        actor: &ClientIdentity,
        tag: &AccountTag,
    ) -> Result<(), ApiError> {
        let found = self.deps.accounts.find_by_tag(tag).await?;
        let account = match found.as_slice() {
            [] => return Err(ApiError::not_found("Account", tag.as_str())),
            [account] => account,
            _ => return Err(ApiError::ambiguous_account_tag(tag.as_str())),
        };
        if let Actor::User(user) = &actor.verified.subject_id
            && AccountId::from_user_id(user).is_ok_and(|own| own == account.id)
        {
            return Err(ApiError::cannot_disable_self());
        }
        self.deps.accounts.set_disabled(&account.id, true).await?;
        self.deps
            .tokens
            .revoke_user(&account.id.user_id()?)
            .await
            .map_err(DomainError::from)?;
        self.journal(
            actor.verified.subject_id.clone(),
            RecordBody::AccountDisabled {
                account: account.tag(),
            },
        )
        .await
    }
    async fn me(&self, identity: &ClientIdentity) -> Result<MeView, ApiError> {
        Ok(MeView {
            subject: identity.verified.subject_id.to_string(),
            role: identity.verified.role,
            device_id: identity.verified.device_id.clone(),
            owner_label: identity.verified.owner.clone(),
            network: identity.network.label.clone(),
            area: identity.network.area.clone(),
        })
    }
}

/// `TokenVerifier` over the SQLite token store (newtype adapter).
pub struct TokenStoreVerifier {
    tokens: SqliteTokenStore,
    accounts: Arc<dyn AccountRepository>,
}

impl TokenStoreVerifier {
    /// The adapter; `accounts` supplies the owner label (`"<pseudonym> #<tag>"`) and the
    /// disabled flag.
    #[must_use]
    pub fn new(
        tokens: SqliteTokenStore,
        accounts: Arc<dyn AccountRepository>,
    ) -> TokenStoreVerifier {
        TokenStoreVerifier { tokens, accounts }
    }
}

#[async_trait]
impl TokenVerifier for TokenStoreVerifier {
    async fn verify(&self, raw: &str) -> Result<Option<VerifiedIdentity>, SecurityError> {
        let subject = self
            .tokens
            .resolve(raw)
            .await
            .map_err(|_| SecurityError::VerifierUnavailable)?;
        match subject {
            None => Ok(None),
            Some(TokenSubject::Robot { robot_id }) => Ok(Some(VerifiedIdentity {
                subject_id: Actor::Robot(robot_id),
                role: Role::Robot,
                device_id: None,
                owner: None,
            })),
            Some(TokenSubject::User {
                user_id,
                role,
                device_id,
            }) => {
                let Ok(id) = AccountId::from_user_id(&user_id) else {
                    return Ok(None);
                };
                let account = self
                    .accounts
                    .find(&id)
                    .await
                    .map_err(|_| SecurityError::VerifierUnavailable)?;
                let Some(account) = account.filter(|account| !account.disabled) else {
                    return Ok(None);
                };
                Ok(Some(VerifiedIdentity {
                    subject_id: Actor::User(user_id),
                    role,
                    device_id,
                    owner: account.owner_label().ok(),
                }))
            }
        }
    }
}
