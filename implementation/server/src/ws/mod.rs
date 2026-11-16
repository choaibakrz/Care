//! WebSocket upgrade handlers: `/ws` for the apps, `/ws/robot/{id}` for robots (contract C2).
// BUILD-OUT: handler errors are documented per status code in each
// `#[utoipa::path(responses(...))]`. Task 21 removes this allowance and adds `# Errors` sections.
#![allow(clippy::missing_errors_doc)]

pub mod apps;
pub mod robots;
