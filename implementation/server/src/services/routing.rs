//! Real `RouteService` (Task 13b): the route preview of a task on the active plan, and the
//! `RoutingCache` that keeps the dispatcher's and tour planner's graph in step with the
//! active plan and the restricted zones.

use std::sync::Arc;

use async_trait::async_trait;
use domain::ports::{TaskRepository, ZoneRecord, ZoneRepository};
use domain::{PlaceId, TaskId, TaskState};
use locations::{ActiveMap, ClinicMap, LivePositions, Point2, Polygon, Zone};
use optimization::{GraphHandle, RouteError, RoutePreview, RoutingGraph};

use super::RouteService;
use crate::dto::RouteView;
use crate::error::ApiError;

/// What `RealRouteService` needs.
pub struct RouteDeps {
    /// Tasks (places, robot, state).
    pub tasks: Arc<dyn TaskRepository>,
    /// Zones: the restricted ones are impassable for planning (deaf ones are crossed).
    pub zones: Arc<dyn ZoneRepository>,
    /// The plan in force.
    pub active: Arc<ActiveMap>,
    /// Robot fixes (robots only).
    pub live: Arc<LivePositions>,
    /// The planner (grid cache).
    pub preview: Arc<RoutePreview>,
    /// Where a task with neither a robot nor a `from_place` starts.
    pub dock: PlaceId,
}

/// The real route service.
pub struct RealRouteService {
    deps: RouteDeps,
}

impl RealRouteService {
    /// A service.
    #[must_use]
    pub fn new(deps: RouteDeps) -> RealRouteService {
        RealRouteService { deps }
    }
}

#[async_trait]
impl RouteService for RealRouteService {
    async fn task_route(&self, id: &TaskId) -> Result<RouteView, ApiError> {
        let task = self
            .deps
            .tasks
            .get(id)
            .await?
            .ok_or_else(|| ApiError::not_found("Task", id.as_str()))?;
        if task.state().is_terminal() {
            return Err(ApiError::no_route(format!(
                "Task '{id}' is {}; it has no route left.",
                task.state()
            )));
        }
        let active = self.deps.active.current();
        let map: &ClinicMap = &active.map;
        let zones = to_zones(&self.deps.zones.list().await?);
        let anchor = |place: &PlaceId| -> Result<(i32, Point2), ApiError> {
            map.place(place)
                .map(|found| (found.floor, found.anchor))
                .ok_or_else(|| {
                    ApiError::no_route(format!(
                        "Place '{place}' is not on the active clinic plan; no route is drawn."
                    ))
                })
        };
        let robot_start = task
            .assigned_robot()
            .and_then(|robot| self.deps.live.robot_fix(robot))
            .map(|fix| (fix.floor, fix.point));
        let picked_up = matches!(task.state(), TaskState::EnRoute);
        let mut stops: Vec<(i32, Point2)> = Vec::new();
        match (robot_start, task.from()) {
            (Some(start), Some(from)) => {
                stops.push(start);
                if !picked_up {
                    stops.push(anchor(from)?);
                }
            }
            (Some(start), None) => stops.push(start),
            (None, Some(from)) => stops.push(anchor(from)?),
            (None, None) => stops.push(anchor(&self.deps.dock)?),
        }
        stops.push(anchor(task.to())?);
        let mut floor = None;
        let mut points: Vec<[f64; 2]> = Vec::new();
        let mut length_m = 0.0;
        for pair in stops.windows(2) {
            let (Some(&(from_floor, from)), Some(&(to_floor, to))) = (pair.first(), pair.get(1))
            else {
                continue;
            };
            if from_floor != to_floor {
                return Err(RouteError::DifferentFloors {
                    from_floor,
                    to_floor,
                }
                .into());
            }
            floor = Some(from_floor);
            let leg = self.deps.preview.plan(map, &zones, from, to, from_floor)?;
            length_m += leg.length_m;
            for point in leg.points {
                let pair = [point.x(), point.y()];
                if points.last() != Some(&pair) {
                    points.push(pair);
                }
            }
        }
        let floor =
            floor.ok_or_else(|| ApiError::no_route("The task has no leg to draw.".to_owned()))?;
        Ok(RouteView {
            floor,
            points,
            length_m,
            estimate: true,
        })
    }
}

/// The stored zones as the planner reads them; a zone whose outline is invalid is skipped.
fn to_zones(records: &[ZoneRecord]) -> Vec<Zone> {
    records
        .iter()
        .filter_map(|record| match Polygon::from_pairs(&record.polygon) {
            Ok(polygon) => Some(Zone {
                id: record.id.clone(),
                kind: record.kind,
                floor: record.floor,
                polygon,
                version: record.version,
            }),
            Err(error) => {
                tracing::warn!(zone = %record.id, %error, "stored zone skipped: invalid outline");
                None
            }
        })
        .collect()
}

/// The routing graph of the dispatcher and the tour planner, rebuilt from the active plan
/// and the restricted zones (Task A4, Task 13b).
///
/// Rebuild triggers, each awaited before the change is answered: `ZoneService::upsert` and
/// `ZoneService::delete` (a restricted zone appears, moves or goes), `ClinicService::update`
/// of the active plan and `ClinicService::activate`, and `Wiring::finish` at startup.
pub struct RoutingCache {
    graph: GraphHandle,
    active: Arc<ActiveMap>,
    zones: Arc<dyn ZoneRepository>,
}

impl RoutingCache {
    /// A cache serving `graph` until the first rebuild.
    #[must_use]
    pub fn new(
        graph: GraphHandle,
        active: Arc<ActiveMap>,
        zones: Arc<dyn ZoneRepository>,
    ) -> RoutingCache {
        RoutingCache {
            graph,
            active,
            zones,
        }
    }

    /// The handle the dispatcher and the tour planner read (`Dispatcher::with_handle`,
    /// `TourPlanner::with_handle`).
    #[must_use]
    pub fn handle(&self) -> GraphHandle {
        self.graph.clone()
    }

    /// Rebuilds the graph: the active plan's model, the zones from the store (as
    /// `locations::Zone`), `RoutingGraph::from_map_with_zones`, then `GraphHandle::replace`.
    ///
    /// # Errors
    /// Store failures; a stored zone that no longer fits the plan is skipped and logged.
    pub async fn rebuild(&self) -> Result<(), ApiError> {
        let zones = to_zones(&self.zones.list().await?);
        let active = self.active.current();
        self.graph
            .replace(RoutingGraph::from_map_with_zones(&active.map, &zones));
        tracing::debug!(clinic = %active.clinic_id, "routing graph rebuilt");
        Ok(())
    }
}
