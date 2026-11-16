//! `POST /auth/login`, `GET /auth/derivation`, `POST /auth/enrol`, `GET /me`, and the
//! account administration of Task A7 (`POST /admin/enrolment-codes`, `GET /admin/accounts`,
//! `DELETE /admin/accounts/{account_tag}`).
//!
//! Pseudonymous accounts: the server never receives a user name or a password, only the key
//! the client derived from them (`docs/accounts.md`).

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use domain::{AccountTag, ErrorBody};

use crate::dto::{
    AccountView, EnrolRequest, EnrolledView, EnrolmentCodeRequest, EnrolmentCodeView,
    KeyDerivationParams, LoginBody, LoginRequest, LoginResponse, MeView, ServerMode,
};
use crate::error::{ApiError, ApiJson, ApiPath};
use crate::extractors::{Authenticated, Authorized, Network, perm};
use crate::state::AppState;

/// Logs in with the account key the client derived (`{account_key, device_id?}`); returns a
/// bearer token, bound to `device_id` when the client sent one (a browser sends none).
///
/// An unknown key (a wrong user name or password gives one), and a disabled account, get the
/// same answer ("User name or password is incorrect."). A `{username, password}` body is 422
/// `key_derivation_required`: the server never takes them (only `--mock` still accepts them,
/// until frontend task F9).
#[utoipa::path(
    post,
    path = "/auth/login",
    tag = "auth",
    request_body = LoginRequest,
    responses(
        (status = 200, description = "Logged in", body = LoginResponse),
        (status = 401, description = "User name or password is incorrect", body = ErrorBody),
        (status = 422, description = "Malformed request, or `key_derivation_required` for a user name and password body", body = ErrorBody),
        (status = 429, description = "Too many attempts", body = ErrorBody)
    )
)]
pub async fn login(
    State(state): State<AppState>,
    Network(network): Network,
    ApiJson(body): ApiJson<LoginBody>,
) -> Result<Json<LoginResponse>, ApiError> {
    let response = match body {
        LoginBody::Key(request) => {
            state
                .auth
                .login(&request.account_key, request.device_id, &network)
                .await?
        }
        // Mock compatibility until frontend task F9; the live server never reads them.
        LoginBody::Credentials(credentials) if state.mode == ServerMode::Mock => {
            state
                .auth
                .login_with_password(
                    &credentials.username,
                    &credentials.password,
                    credentials.device_id,
                    &network,
                )
                .await?
        }
        LoginBody::Credentials(_) => return Err(ApiError::key_derivation_required()),
    };
    Ok(Json(response))
}

/// How a client derives its account key: algorithm, iterations, key length and this server's
/// account clinic id (the salt is `clinic:<clinic_id>:<lowercase username>`). Public.
#[utoipa::path(
    get,
    path = "/auth/derivation",
    tag = "auth",
    responses((status = 200, description = "Derivation parameters", body = KeyDerivationParams))
)]
pub async fn derivation(State(state): State<AppState>) -> Json<KeyDerivationParams> {
    Json(state.auth.derivation())
}

/// Enrols with a one-time code from an admin, the derived key of the user name and password
/// the person chose on their device, and a pseudonym. Public (the code is the credential).
#[utoipa::path(
    post,
    path = "/auth/enrol",
    tag = "auth",
    request_body = EnrolRequest,
    responses(
        (status = 201, description = "Account created; log in with the same key", body = EnrolledView),
        (status = 403, description = "`enrolment_refused`: unknown, used or expired code", body = ErrorBody),
        (status = 409, description = "`account_exists`: these credentials are already an account", body = ErrorBody),
        (status = 422, description = "Malformed request (key, code or pseudonym)", body = ErrorBody),
        (status = 429, description = "Too many attempts", body = ErrorBody)
    )
)]
pub async fn enrol(
    State(state): State<AppState>,
    Network(network): Network,
    ApiJson(body): ApiJson<EnrolRequest>,
) -> Result<(StatusCode, Json<EnrolledView>), ApiError> {
    let view = state.auth.enrol(body, &network).await?;
    Ok((StatusCode::CREATED, Json(view)))
}

/// Issues a one-time enrolment code for a role (admin). The code is shown once; it works for
/// 24 h and only its HMAC is kept.
#[utoipa::path(
    post,
    path = "/admin/enrolment-codes",
    tag = "accounts",
    request_body = EnrolmentCodeRequest,
    responses(
        (status = 201, description = "Code issued", body = EnrolmentCodeView),
        (status = 403, description = "Permission missing", body = ErrorBody),
        (status = 422, description = "Malformed request, or role `robot`", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn issue_enrolment_code(
    State(state): State<AppState>,
    auth: Authorized<perm::ManageAccounts>,
    ApiJson(body): ApiJson<EnrolmentCodeRequest>,
) -> Result<(StatusCode, Json<EnrolmentCodeView>), ApiError> {
    let view = state
        .auth
        .issue_enrolment_code(&auth.identity, body)
        .await?;
    Ok((StatusCode::CREATED, Json(view)))
}

/// Every account: pseudonym, tag, role, creation time, disabled (admin). No user name exists.
#[utoipa::path(
    get,
    path = "/admin/accounts",
    tag = "accounts",
    responses(
        (status = 200, description = "Accounts", body = Vec<AccountView>),
        (status = 403, description = "Permission missing", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn list_accounts(
    State(state): State<AppState>,
    _auth: Authorized<perm::ManageAccounts>,
) -> Result<Json<Vec<AccountView>>, ApiError> {
    Ok(Json(state.auth.list_accounts().await?))
}

/// Disables an account by its tag and revokes its tokens (admin). A forgotten password is
/// handled this way: disable, then issue a new enrolment code.
#[utoipa::path(
    delete,
    path = "/admin/accounts/{account_tag}",
    tag = "accounts",
    params(("account_tag" = String, Path, description = "The account's 6 hex digit tag")),
    responses(
        (status = 204, description = "Disabled"),
        (status = 403, description = "Permission missing", body = ErrorBody),
        (status = 404, description = "No such account", body = ErrorBody),
        (status = 409, description = "`ambiguous_account_tag` or `cannot_disable_self`", body = ErrorBody),
        (status = 422, description = "Not a tag", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn disable_account(
    State(state): State<AppState>,
    auth: Authorized<perm::ManageAccounts>,
    ApiPath(tag): ApiPath<AccountTag>,
) -> Result<StatusCode, ApiError> {
    state.auth.disable_account(&auth.identity, &tag).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Who am I: role, device, owner label and network of the caller.
#[utoipa::path(
    get,
    path = "/me",
    tag = "auth",
    responses(
        (status = 200, description = "The caller", body = MeView),
        (status = 401, description = "Not logged in", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn me(
    State(state): State<AppState>,
    Authenticated(identity): Authenticated,
) -> Result<Json<MeView>, ApiError> {
    Ok(Json(state.auth.me(&identity).await?))
}
