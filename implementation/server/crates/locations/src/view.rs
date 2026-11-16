//! `GET /map` as the admin console reads it: the active clinic plan, with its identity.
//!
//! One shape, not two (Task A4): the elements are the plan's own types ([`PlanFloor`],
//! [`PlanRoom`], [`PlanWall`], [`PlanPlace`], [`PlanProp`]), so what the console draws is
//! exactly what an admin edits through `/clinics`. Coordinates are metres, x east, y south
//! (`docs/map-format.md`); points are `[x, y]`.

use domain::ClinicId;
use serde::Serialize;
use utoipa::ToSchema;

use crate::plan::{ActivePlan, PlanFloor, PlanPlace, PlanProp, PlanRoom, PlanWall};

/// The active plan for the console: `{clinic_id, version, name, floors, rooms, walls, places,
/// props}`. The `ETag` of `GET /map` is [`ActivePlan::tag`].
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct MapView {
    /// Which stored plan is active.
    pub clinic_id: ClinicId,
    /// Its version (starts at 1, plus one per saved change).
    pub version: u64,
    /// Display name of the clinic.
    pub name: String,
    /// Floors.
    pub floors: Vec<PlanFloor>,
    /// Rooms.
    pub rooms: Vec<PlanRoom>,
    /// Walls, as open polylines; a door is a gap between two walls.
    pub walls: Vec<PlanWall>,
    /// Named points robots go to.
    pub places: Vec<PlanPlace>,
    /// Furniture; `solid` props block the route planner.
    pub props: Vec<PlanProp>,
}

impl MapView {
    /// The view of the active plan: its id, version and every element of the plan, unchanged
    /// (the plan's `marque` is not part of the view).
    #[must_use]
    pub fn of(active: &ActivePlan) -> MapView {
        let plan = &active.plan;
        MapView {
            clinic_id: active.clinic_id.clone(),
            version: active.version,
            name: plan.name.clone(),
            floors: plan.floors.clone(),
            rooms: plan.rooms.clone(),
            walls: plan.walls.clone(),
            places: plan.places.clone(),
            props: plan.props.clone(),
        }
    }
}
