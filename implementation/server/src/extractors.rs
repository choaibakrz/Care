//! Identity and permission extractors.
//!
//! The security stack inserts `ClientNetwork` and `ClientIdentity` as request extensions;
//! these extractors read them. A role without the permission gets 403 `forbidden` naming it.

use std::marker::PhantomData;

use std::net::SocketAddr;

use axum::extract::{ConnectInfo, FromRequestParts};
use axum::http::request::Parts;
use domain::{DeviceId, Permission};
use security::{ClientIdentity, ClientNetwork, SecurityError};

use crate::error::ApiError;

/// The caller's identity (any role). Missing identity is 401.
#[derive(Debug, Clone)]
pub struct Authenticated(pub ClientIdentity);

impl<S: Send + Sync> FromRequestParts<S> for Authenticated {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        parts
            .extensions
            .get::<ClientIdentity>()
            .cloned()
            .map(Authenticated)
            .ok_or_else(ApiError::unauthorized)
    }
}

/// The caller's network (also for unauthenticated routes such as login).
#[derive(Debug, Clone)]
pub struct Network(pub ClientNetwork);

impl<S: Send + Sync> FromRequestParts<S> for Network {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        if let Some(network) = parts.extensions.get::<ClientNetwork>() {
            return Ok(Network(network.clone()));
        }
        // The security stack inserts the network on every request it lets through; without
        // it, the peer is on no known network (or the router runs without the stack).
        match parts.extensions.get::<ConnectInfo<SocketAddr>>() {
            Some(ConnectInfo(peer)) => Err(SecurityError::UnknownNetwork { ip: peer.ip() }.into()),
            None => Err(ApiError::internal("client network")),
        }
    }
}

/// A permission as a type, for [`Authorized`].
pub trait PermissionMarker: Send + Sync + 'static {
    /// The permission required.
    const PERMISSION: Permission;
}

/// The caller, checked to hold `P::PERMISSION`.
#[derive(Debug, Clone)]
pub struct Authorized<P: PermissionMarker> {
    /// The caller.
    pub identity: ClientIdentity,
    _permission: PhantomData<P>,
}

impl<S: Send + Sync, P: PermissionMarker> FromRequestParts<S> for Authorized<P> {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let Authenticated(identity) = Authenticated::from_request_parts(parts, state).await?;
        if !identity.verified.role.allows(P::PERMISSION) {
            return Err(ApiError::forbidden(P::PERMISSION));
        }
        Ok(Authorized {
            identity,
            _permission: PhantomData,
        })
    }
}

/// The caller, checked to hold `P::PERMISSION` and to use a token bound to a device (a
/// tablet). For the tablet-only endpoints: `PUT /me/location`, `POST /me/scans`,
/// `POST /devices/me/events`. A device-less token (browser login) is 403 `device_required`.
#[derive(Debug, Clone)]
pub struct TabletAuthorized<P: PermissionMarker> {
    /// The caller; `identity.verified.device_id` is `Some`.
    pub identity: ClientIdentity,
    /// The caller's device.
    pub device: DeviceId,
    _permission: PhantomData<P>,
}

impl<S: Send + Sync, P: PermissionMarker> FromRequestParts<S> for TabletAuthorized<P> {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let Authorized { identity, .. } = Authorized::<P>::from_request_parts(parts, state).await?;
        let device = identity
            .verified
            .device_id
            .clone()
            .ok_or_else(ApiError::device_required)?;
        Ok(TabletAuthorized {
            identity,
            device,
            _permission: PhantomData,
        })
    }
}

/// Permission marker types, one per `Permission`.
pub mod perm {
    use domain::Permission;

    use super::PermissionMarker;

    macro_rules! markers {
        ($($name:ident),* $(,)?) => {$(
            #[doc = concat!("Requires `Permission::", stringify!($name), "`.")]
            #[derive(Debug, Clone, Copy)]
            pub struct $name;
            impl PermissionMarker for $name {
                const PERMISSION: Permission = Permission::$name;
            }
        )*};
    }

    markers!(
        ViewTasks,
        CreateTask,
        CancelTask,
        ViewInventory,
        AdjustInventory,
        ViewMap,
        ReportLocation,
        EditZones,
        ViewRobots,
        RobotControl,
        Estop,
        ViewSchedules,
        EditSchedules,
        ViewAudit,
        ViewIncidents,
        AckIncident,
        CloseIncident,
        ReportDeviceEvent,
        EditClinics,
        ViewStats,
        UseBrain,
        SummariseSources,
        DraftReport,
        ManageAccounts,
        RevertCommand,
        ViewSystemMode,
        SwitchSystemMode,
        MonitorSecurity,
        ManageDevices,
    );
}
