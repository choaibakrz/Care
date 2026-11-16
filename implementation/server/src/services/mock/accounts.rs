//! Pseudonymous accounts and command reverts in `--mock` (Task A7), real code.
//!
//! The mock follows the live flow with invented data: it knows the demo accounts only by
//! their derived ids (`HMAC-SHA256(MOCK_PEPPER, key)`, the keys being the published
//! derivation of `<role>` / `mock` with account clinic id [`MOCK_ACCOUNT_CLINIC_ID`]); a
//! login sends `{account_key}`. **Mock compatibility until frontend task F9:** a
//! `{username, password}` body is still accepted here (and only here): the mock derives the
//! key itself, then logs in with it. Enrolment codes, enrolment, the account list and
//! disabling work in memory; tokens of enrolled accounts are
//! `mock-account-<account id>`.
//!
//! Commands: every robot command gets a `command_id`; a non-admin's command adds a
//! `staff_command` alert (warning, with the command) and an audit row; the admin can revert
//! it (the inverse command is sent to the simulated robot and an audit row is added).

use chrono::{DateTime, Utc};
use domain::{
    AccountId, AccountKey, AccountTag, ClinicId, CommandName, DomainError, ENROLMENT_CODE_TTL,
    EnrolmentCode, OwnerLabel, RobotId, Role, check_pseudonym,
};
use realtime::{AlertKind, AppEvent, CommandNotice};
use security::{
    ClientIdentity, Pepper, VerifiedIdentity, account_id, constant_time_eq, derive_account_key,
    enrolment_code_hash,
};
use uuid::Uuid;

use super::{MOCK_TOKEN_PREFIX, MockServices, MockUser};
use crate::dto::{
    AccountView, AuditEntry, AuditResult, EnrolRequest, EnrolledView, EnrolmentCodeRequest,
    EnrolmentCodeView, LoginResponse,
};
use crate::error::ApiError;
use crate::services::robots::{COMMAND_LOG_CAPACITY, LoggedCommand, RevertMark};

/// The account clinic id of `--mock` (the default `ACCOUNT_CLINIC_ID`): the demo keys were
/// derived with it.
pub const MOCK_ACCOUNT_CLINIC_ID: &str = crate::config::DEFAULT_ACCOUNT_CLINIC_ID;
/// The mock's pepper: invented and public (a mock has nothing to protect).
pub const MOCK_PEPPER: [u8; 32] = *b"mock-pepper-invented-not-secret!";
/// Prefix of the token of an account enrolled in the mock: `mock-account-<account id>`.
pub const MOCK_ACCOUNT_TOKEN_PREFIX: &str = "mock-account-";

/// One account of the mock.
pub(super) struct MockAccount {
    pub(super) id: AccountId,
    pub(super) role: Role,
    pub(super) label: OwnerLabel,
    /// The bearer token the mock gives it.
    pub(super) token: String,
    pub(super) created_at: DateTime<Utc>,
    pub(super) disabled: bool,
}

/// One enrolment code of the mock (its HMAC only, as on the live server).
pub(super) struct MockCode {
    id: Uuid,
    hash: [u8; 32],
    role: Role,
    expires_at: DateTime<Utc>,
    used: bool,
}

/// The mock's pepper.
fn mock_pepper() -> Pepper {
    Pepper::from_bytes(MOCK_PEPPER)
}

/// The demo accounts: the published derivation of `<role>` / `mock` (`MockUser::key`), known
/// to the mock by their ids only.
pub(super) fn demo_accounts(
    users: &[MockUser],
    now: DateTime<Utc>,
) -> Result<Vec<MockAccount>, DomainError> {
    let pepper = mock_pepper();
    users
        .iter()
        .map(|user| {
            let key: AccountKey = user.key.parse()?;
            let role_name = user.names.first().copied().unwrap_or("admin");
            Ok(MockAccount {
                id: account_id(&pepper, &key),
                role: user.role,
                label: OwnerLabel::new(user.label)?,
                token: format!("{MOCK_TOKEN_PREFIX}{role_name}"),
                created_at: now,
                disabled: false,
            })
        })
        .collect()
}

impl MockServices {
    /// The account clinic id of the mock.
    pub(super) fn account_clinic() -> ClinicId {
        MOCK_ACCOUNT_CLINIC_ID
            .parse()
            .unwrap_or_else(|_| ClinicId::seed())
    }

    /// `POST /auth/login {account_key}` in the mock: the same answer for an unknown key and a
    /// disabled account.
    pub(super) fn mock_login(&self, key: &AccountKey) -> Result<LoginResponse, ApiError> {
        let id = account_id(&mock_pepper(), key);
        let data = self.data();
        let account = data
            .accounts
            .iter()
            .find(|account| constant_time_eq(account.id.as_bytes(), id.as_bytes()))
            .filter(|account| !account.disabled)
            .ok_or_else(ApiError::invalid_credentials)?;
        Ok(LoginResponse {
            token: account.token.clone(),
            role: account.role,
            operator: account.label.clone(),
            expires_at: self.clock.now() + chrono::Duration::hours(super::MOCK_TOKEN_TTL_H),
        })
    }

    /// Mock compatibility until frontend task F9: derives the key of a typed user name and
    /// password (the demo aliases `u-<role>` are read as `<role>`), off the async threads,
    /// then logs in with it.
    pub(super) async fn mock_login_with_password(
        &self,
        username: &str,
        password: &str,
    ) -> Result<LoginResponse, ApiError> {
        let name = username
            .strip_prefix("u-")
            .filter(|rest| {
                super::MOCK_USERS
                    .iter()
                    .any(|user| user.names.contains(rest))
            })
            .unwrap_or(username)
            .to_owned();
        let password = password.to_owned();
        let clinic = Self::account_clinic();
        let key =
            tokio::task::spawn_blocking(move || derive_account_key(&name, &password, &clinic))
                .await
                .map_err(|_| ApiError::internal("key derivation"))?;
        self.mock_login(&key)
    }

    /// The identity of a mock user token (`mock-<role>` or `mock-account-<id>`), `None`
    /// for an unknown token or a disabled account.
    pub(super) fn account_identity(
        &self,
        raw: &str,
    ) -> Result<Option<VerifiedIdentity>, DomainError> {
        let data = self.data();
        let Some(account) = data
            .accounts
            .iter()
            .find(|account| constant_time_eq(account.token.as_bytes(), raw.as_bytes()))
        else {
            return Ok(None);
        };
        if account.disabled {
            return Ok(None);
        }
        Ok(Some(VerifiedIdentity {
            subject_id: domain::Actor::User(account.id.user_id()?),
            role: account.role,
            device_id: None,
            owner: Some(account.label.clone()),
        }))
    }

    /// `POST /admin/enrolment-codes` in the mock.
    pub(super) fn mock_issue_code(
        &self,
        request: EnrolmentCodeRequest,
    ) -> Result<EnrolmentCodeView, ApiError> {
        if request.role == Role::Robot {
            return Err(ApiError::invalid_input(
                "role",
                "must be a staff role (robots get their keys at provisioning)",
            ));
        }
        let mut random = [0_u8; 8];
        for (slot, byte) in random.iter_mut().zip(Uuid::new_v4().as_bytes()) {
            *slot = *byte;
        }
        let code = EnrolmentCode::from_random(random);
        let id = Uuid::new_v4();
        let expires_at = self.clock.now()
            + chrono::Duration::from_std(ENROLMENT_CODE_TTL)
                .unwrap_or_else(|_| chrono::Duration::hours(24));
        self.data().codes.push(MockCode {
            id,
            hash: enrolment_code_hash(&mock_pepper(), &code),
            role: request.role,
            expires_at,
            used: false,
        });
        Ok(EnrolmentCodeView {
            code: code.display(),
            code_id: id,
            role: request.role,
            label: request.label,
            expires_at,
        })
    }

    /// `POST /auth/enrol` in the mock.
    pub(super) fn mock_enrol(&self, request: EnrolRequest) -> Result<EnrolledView, ApiError> {
        // As on the live server: at most 32 characters, no `#` (the tag separator), no
        // control character.
        check_pseudonym(&request.display_label)?;
        let pepper = mock_pepper();
        let hash = enrolment_code_hash(&pepper, &request.enrolment_code);
        let id = account_id(&pepper, &request.account_key);
        let now = self.clock.now();
        let mut data = self.data();
        let Some(index) = data.codes.iter().position(|code| {
            constant_time_eq(&code.hash, &hash) && !code.used && code.expires_at > now
        }) else {
            return Err(DomainError::EnrolmentRefused.into());
        };
        if data.accounts.iter().any(|account| account.id == id) {
            return Err(DomainError::AccountExists.into());
        }
        let Some(code) = data.codes.get_mut(index) else {
            return Err(DomainError::EnrolmentRefused.into());
        };
        code.used = true;
        let role = code.role;
        tracing::info!(code = %code.id, account = %id.tag(), "mock: account enrolled");
        data.accounts.push(MockAccount {
            id,
            role,
            label: request.display_label.clone(),
            token: format!("{MOCK_ACCOUNT_TOKEN_PREFIX}{id}"),
            created_at: now,
            disabled: false,
        });
        Ok(EnrolledView {
            account_tag: id.tag(),
            role,
            operator: request.display_label,
        })
    }

    /// `GET /admin/accounts` in the mock.
    pub(super) fn mock_accounts(&self) -> Vec<AccountView> {
        self.data()
            .accounts
            .iter()
            .map(|account| AccountView {
                account_tag: account.id.tag(),
                display_label: account.label.clone(),
                role: account.role,
                created_at: account.created_at,
                disabled: account.disabled,
            })
            .collect()
    }

    /// `DELETE /admin/accounts/{tag}` in the mock.
    pub(super) fn mock_disable(
        &self,
        actor: &ClientIdentity,
        tag: &AccountTag,
    ) -> Result<(), ApiError> {
        let mut data = self.data();
        let matching: Vec<usize> = data
            .accounts
            .iter()
            .enumerate()
            .filter(|(_, account)| tag.matches(&account.id))
            .map(|(index, _)| index)
            .collect();
        let index = match matching.as_slice() {
            [] => return Err(ApiError::not_found("Account", tag.as_str())),
            [index] => *index,
            _ => return Err(ApiError::ambiguous_account_tag(tag.as_str())),
        };
        let Some(account) = data.accounts.get_mut(index) else {
            return Err(ApiError::not_found("Account", tag.as_str()));
        };
        if let domain::Actor::User(user) = &actor.verified.subject_id
            && AccountId::from_user_id(user).is_ok_and(|own| own == account.id)
        {
            return Err(ApiError::cannot_disable_self());
        }
        account.disabled = true;
        Ok(())
    }

    /// Remembers a sent command; a non-admin's command raises the `staff_command` alert and
    /// adds an audit row. Returns the command id.
    pub(super) fn log_command(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        name: CommandName,
    ) -> Uuid {
        let id = Uuid::new_v4();
        let by_admin = actor.verified.role == Role::Admin;
        {
            let mut data = self.data();
            data.commands.push_back(LoggedCommand {
                id,
                robot: robot.clone(),
                name,
                by_admin,
                reverted_by: None,
            });
            while data.commands.len() > COMMAND_LOG_CAPACITY {
                data.commands.pop_front();
            }
        }
        if !by_admin && name != CommandName::Estop {
            let by = actor
                .verified
                .owner
                .clone()
                .or_else(|| OwnerLabel::new("unknown").ok());
            let command_name = super::wire_name(&name);
            self.add_audit_row(
                actor,
                &format!("robot_{command_name}"),
                robot.as_str(),
                format!("command {id}"),
            );
            if let Some(by) = by {
                let revertible = name.inverse().is_some();
                self.publish(AppEvent::Alert {
                    level: AlertKind::StaffCommand.level(),
                    kind: AlertKind::StaffCommand,
                    message: format!(
                        "{by} sent {command_name} to robot {robot} (command {id}).{} (mock server)",
                        if revertible {
                            " You can revert it."
                        } else {
                            " It cannot be reverted from the server."
                        }
                    ),
                    command: Some(CommandNotice {
                        command_id: id,
                        robot_id: robot.clone(),
                        command: name,
                        by,
                        revertible,
                    }),
                });
            }
        }
        id
    }

    /// Reserves the command `id` of `robot` for an admin's revert, under the one lock (so two
    /// concurrent reverts send one inverse), and returns its inverse. In this order: 404
    /// unknown or another robot's; 409 `already_reverted` (done, or being sent by another
    /// request); 409 `not_revertible`; 409 `estop_latched` while the robot is in emergency
    /// stop; 409 `superseded` when a later command of the robot was sent (ruling R24).
    pub(super) fn reserve_revert(
        &self,
        robot: &RobotId,
        id: Uuid,
    ) -> Result<CommandName, ApiError> {
        let mut data = self.data();
        let latched = data.estop_latched.contains(robot);
        let position = data
            .commands
            .iter()
            .position(|command| command.id == id && &command.robot == robot)
            .ok_or_else(|| ApiError::not_found("Command", &id.to_string()))?;
        let later = data
            .commands
            .iter()
            .skip(position + 1)
            .rfind(|command| &command.robot == robot)
            .map(|command| command.id);
        let command = data
            .commands
            .get_mut(position)
            .ok_or_else(|| ApiError::not_found("Command", &id.to_string()))?;
        match command.reverted_by {
            Some(RevertMark::Done(by)) => return Err(ApiError::already_reverted(&by.to_string())),
            Some(RevertMark::Pending) => return Err(ApiError::revert_in_progress()),
            None => {}
        }
        if command.by_admin {
            return Err(ApiError::not_revertible(
                "an administrator sent it; send the opposite command instead",
            ));
        }
        let inverse = command.name.inverse().ok_or_else(|| {
            ApiError::not_revertible(match command.name {
                CommandName::Shutdown => "the robot was shut down; restart it on site",
                _ => "an emergency stop is released on the robot itself",
            })
        })?;
        if latched {
            return Err(ApiError::estop_latched(robot.as_str()));
        }
        if let Some(later) = later {
            return Err(ApiError::superseded(robot.as_str(), &later.to_string()));
        }
        command.reverted_by = Some(RevertMark::Pending);
        Ok(inverse)
    }

    /// Gives a reservation back: the inverse was not sent.
    pub(super) fn release_revert(&self, id: Uuid) {
        if let Some(command) = self
            .data()
            .commands
            .iter_mut()
            .find(|command| command.id == id)
            && command.reverted_by == Some(RevertMark::Pending)
        {
            command.reverted_by = None;
        }
    }

    /// Marks `id` reverted by `by` and adds the audit row.
    pub(super) fn mark_reverted(
        &self,
        actor: &ClientIdentity,
        robot: &RobotId,
        id: Uuid,
        by: Uuid,
    ) {
        if let Some(command) = self
            .data()
            .commands
            .iter_mut()
            .find(|command| command.id == id)
        {
            command.reverted_by = Some(RevertMark::Done(by));
        }
        self.add_audit_row(
            actor,
            "robot_command_reverted",
            robot.as_str(),
            format!("{id} undone by {by}"),
        );
    }

    /// Adds one audit row (actor the caller's owner label).
    fn add_audit_row(&self, actor: &ClientIdentity, action: &str, target: &str, detail: String) {
        let label = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        let at = self.clock.now();
        let mut data = self.data();
        let id = data.audit.iter().map(|row| row.id).max().unwrap_or(0) + 1;
        data.audit.push(AuditEntry {
            id,
            at,
            actor: label,
            action: action.to_owned(),
            target: target.to_owned(),
            result: AuditResult::Ok,
            detail: Some(detail),
            category: "robot".to_owned(),
        });
    }
}

#[cfg(test)]
mod tests {
    use super::super::{MOCK_USERS, MockServices};
    use super::{LoggedCommand, MOCK_ACCOUNT_CLINIC_ID, RevertMark};
    use domain::CommandName;
    use uuid::Uuid;

    /// A reservation is taken under the lock: while one revert is sending the inverse, a
    /// second is 409 `already_reverted`; a released reservation can be taken again; a done
    /// revert stays refused.
    #[test]
    fn a_reserved_revert_refuses_a_second_one_until_released()
    -> Result<(), Box<dyn std::error::Error>> {
        let mock = MockServices::new();
        let robot: domain::RobotId = "r1".parse()?;
        let id = Uuid::new_v4();
        mock.data().commands.push_back(LoggedCommand {
            id,
            robot: robot.clone(),
            name: CommandName::Pause,
            by_admin: false,
            reverted_by: None,
        });
        assert_eq!(
            mock.reserve_revert(&robot, id).map_err(|e| e.code())?,
            CommandName::Resume
        );
        let second = mock
            .reserve_revert(&robot, id)
            .err()
            .ok_or("reserved twice")?;
        assert_eq!(second.code(), "already_reverted");
        mock.release_revert(id);
        assert_eq!(
            mock.reserve_revert(&robot, id).map_err(|e| e.code())?,
            CommandName::Resume
        );
        let by = Uuid::new_v4();
        if let Some(command) = mock.data().commands.iter_mut().find(|c| c.id == id) {
            command.reverted_by = Some(RevertMark::Done(by));
        }
        let done = mock
            .reserve_revert(&robot, id)
            .err()
            .ok_or("reverted twice")?;
        assert_eq!(done.code(), "already_reverted");
        Ok(())
    }

    /// The demo keys in `MOCK_USERS` are the published derivation of `<role>` / `mock`.
    #[test]
    fn demo_keys_are_the_derivation_of_the_demo_credentials()
    -> Result<(), Box<dyn std::error::Error>> {
        let clinic = MOCK_ACCOUNT_CLINIC_ID.parse()?;
        for user in MOCK_USERS {
            let name = user.names.first().copied().ok_or("no name")?;
            let key = security::derive_account_key(name, super::super::MOCK_PASSWORD, &clinic);
            assert_eq!(key.to_hex(), user.key, "{name}");
        }
        Ok(())
    }
}
