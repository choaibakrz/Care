//! HTTP handlers, one file per area of contract C3.
//!
//! Handlers stay thin: extract, check the permission (through the extractor), call one
//! service, shape the response. Every handler carries `#[utoipa::path]`.
// BUILD-OUT: handler errors are documented per status code in each
// `#[utoipa::path(responses(...))]`. Task 21 removes this allowance and adds `# Errors` sections.
#![allow(clippy::missing_errors_doc)]

pub mod audit;
pub mod auth;
pub mod brain;
pub mod clinics;
pub mod devices;
pub mod fleet;
pub mod health;
pub mod incidents;
pub mod inventory;
pub mod map;
pub mod monitor;
pub mod robots;
pub mod schedules;
pub mod stats;
pub mod system;
pub mod tasks;
pub mod zones;
