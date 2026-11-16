//! Real `MapService`: the active clinic plan (Task A4: editable, see `services::clinics`).

use std::sync::Arc;

use async_trait::async_trait;
use locations::{ActiveMap, ClinicMap, MapView};

use super::MapService;
use crate::error::ApiError;

/// Serves the plan in force.
pub struct RealMapService {
    active: Arc<ActiveMap>,
}

impl RealMapService {
    /// A service.
    #[must_use]
    pub fn new(active: Arc<ActiveMap>) -> RealMapService {
        RealMapService { active }
    }
}

#[async_trait]
impl MapService for RealMapService {
    async fn map(&self) -> Result<Arc<ClinicMap>, ApiError> {
        Ok(Arc::clone(&self.active.current().map))
    }
    async fn view(&self) -> Result<(MapView, String), ApiError> {
        let current = self.active.current();
        Ok((MapView::of(&current), current.tag()))
    }
}
