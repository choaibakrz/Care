//! `GET /health`: liveness, journal state, mode (`live`, `demo`, `mock`) and the brain's
//! status (`up`, `degraded`, `down`), no authentication.

use axum::Json;
use axum::extract::State;

use crate::dto::HealthView;
use crate::state::AppState;

/// Reports whether the server runs, whether actions can currently be recorded, how it was
/// started (`mode`: `live`, `demo` with simulated robots, or `mock`), and whether the brain
/// answers (`brain`; `down` never makes `status` `degraded`: the server works without it).
#[utoipa::path(
    get,
    path = "/health",
    tag = "health",
    responses((status = 200, description = "Server is running", body = HealthView))
)]
pub async fn health(State(state): State<AppState>) -> Json<HealthView> {
    let journal_writable = state.journal.is_writable();
    Json(HealthView {
        status: if journal_writable { "ok" } else { "degraded" }.to_owned(),
        journal_writable,
        version: env!("CARGO_PKG_VERSION").to_owned(),
        mode: state.mode,
        brain: state.brain.status(),
    })
}
