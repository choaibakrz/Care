//! Tour planner for restock rounds: nearest neighbour then 2-opt, dock visits inserted when
//! the battery would fall under the threshold. Skipped stops are listed, never dropped.

use domain::{PlaceId, RobotId};
use serde::Serialize;

use crate::dispatcher::{DispatchPolicy, RejectReason};
use crate::error::OptimizationError;
use crate::fleet::FleetMember;
use crate::graph::{GraphHandle, RoutingGraph};

/// Most stops per tour.
pub const MAX_STOPS: usize = 25;

/// A stop that could not be planned.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SkippedStop {
    /// Place.
    pub place: PlaceId,
    /// Why.
    pub reason: RejectReason,
}

/// A planned tour.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Tour {
    /// Stops in order (dock visits included).
    pub order: Vec<PlaceId>,
    /// Length.
    pub metres: f64,
    /// Indexes in `order` that are dock visits.
    pub dock_visits: Vec<usize>,
    /// Stops not planned.
    pub skipped: Vec<SkippedStop>,
}

/// The planner.
#[derive(Debug, Clone)]
pub struct TourPlanner {
    graph: GraphHandle,
    policy: DispatchPolicy,
    dock: PlaceId,
}

impl TourPlanner {
    /// A planner returning to `dock` to charge.
    #[must_use]
    pub fn new(graph: RoutingGraph, policy: DispatchPolicy, dock: PlaceId) -> TourPlanner {
        TourPlanner::with_handle(GraphHandle::new(graph), policy, dock)
    }

    /// A planner reading the shared graph in force (Task A4): stops behind a restricted zone
    /// are skipped with `NoPath`, or reached around it.
    #[must_use]
    pub fn with_handle(graph: GraphHandle, policy: DispatchPolicy, dock: PlaceId) -> TourPlanner {
        TourPlanner {
            graph,
            policy,
            dock,
        }
    }

    /// Plans one robot's tour.
    ///
    /// # Errors
    /// `TooManyStops` above 25.
    pub fn plan(&self, robot: &FleetMember, stops: &[PlaceId]) -> Result<Tour, OptimizationError> {
        if stops.len() > MAX_STOPS {
            return Err(OptimizationError::TooManyStops {
                given: stops.len(),
                max: MAX_STOPS,
            });
        }
        let graph = self.graph.current();
        let mask = robot.card.mask();
        let dist = |a: &PlaceId, b: &PlaceId| graph.shortest_path(a, b, &mask).map(|p| p.metres);
        let mut skipped = Vec::new();
        let mut reachable: Vec<PlaceId> = Vec::new();
        for stop in stops {
            if reachable.contains(stop) || skipped.iter().any(|s: &SkippedStop| s.place == *stop) {
                continue;
            }
            if !mask.permits(stop) {
                skipped.push(SkippedStop {
                    place: stop.clone(),
                    reason: RejectReason::CardRefusesPlace {
                        place: stop.clone(),
                        card: robot.card.name.clone(),
                    },
                });
            } else if dist(&robot.at, stop).is_none() {
                skipped.push(SkippedStop {
                    place: stop.clone(),
                    reason: RejectReason::NoPath,
                });
            } else {
                reachable.push(stop.clone());
            }
        }
        // Node 0 is the start; node i + 1 is reachable stop i.
        let nodes: Vec<&PlaceId> = std::iter::once(&robot.at).chain(reachable.iter()).collect();
        let matrix = Matrix::build(&nodes, |a, b| dist(a, b).unwrap_or(f64::INFINITY));
        let order = if reachable.len() <= EXACT_UP_TO {
            exact_order(&matrix, reachable.len())
        } else {
            two_opt(&matrix, nearest_neighbour(&matrix, reachable.len()))
        };
        // Walk the order, going to the dock first whenever a leg would leave the battery at
        // or under the threshold.
        let consumption = self.policy.consumption_pct_per_m;
        let mut battery = robot.battery_pct;
        let mut at = robot.at.clone();
        let mut tour = Tour {
            order: Vec::new(),
            metres: 0.0,
            dock_visits: Vec::new(),
            skipped,
        };
        for index in order {
            let Some(next) = reachable.get(index) else {
                continue;
            };
            let mut leg = dist(&at, next).unwrap_or(0.0);
            if battery - leg * consumption <= self.policy.battery_threshold_pct
                && at != self.dock
                && let (Some(to_dock), Some(from_dock)) =
                    (dist(&at, &self.dock), dist(&self.dock, next))
            {
                tour.metres += to_dock;
                tour.dock_visits.push(tour.order.len());
                tour.order.push(self.dock.clone());
                battery = 100.0;
                leg = from_dock;
            }
            tour.metres += leg;
            battery -= leg * consumption;
            tour.order.push(next.clone());
            at = next.clone();
        }
        Ok(tour)
    }

    /// Splits stops between robots by path length so no shelf is covered twice.
    ///
    /// # Errors
    /// `EmptyFleet`; `TooManyStops`.
    pub fn assign_stops(
        &self,
        fleet: &[FleetMember],
        stops: &[PlaceId],
    ) -> Result<Vec<(RobotId, Vec<PlaceId>)>, OptimizationError> {
        if fleet.is_empty() {
            return Err(OptimizationError::EmptyFleet);
        }
        let max = MAX_STOPS.saturating_mul(fleet.len());
        if stops.len() > max {
            return Err(OptimizationError::TooManyStops {
                given: stops.len(),
                max,
            });
        }
        let graph = self.graph.current();
        let mut split: Vec<(RobotId, Vec<PlaceId>)> =
            fleet.iter().map(|r| (r.id.clone(), Vec::new())).collect();
        let mut assigned: Vec<&PlaceId> = Vec::new();
        for stop in stops {
            if assigned.contains(&stop) {
                continue;
            }
            // Nearest robot (by path from where it stands) with room left; ties by robot id.
            let mut best: Option<(usize, f64, &RobotId)> = None;
            for (index, robot) in fleet.iter().enumerate() {
                let full = split
                    .get(index)
                    .is_none_or(|(_, mine)| mine.len() >= MAX_STOPS);
                if full {
                    continue;
                }
                let Some(path) = graph.shortest_path(&robot.at, stop, &robot.card.mask()) else {
                    continue;
                };
                let better = best.is_none_or(|(_, metres, id)| {
                    path.metres
                        .total_cmp(&metres)
                        .then_with(|| robot.id.cmp(id))
                        .is_lt()
                });
                if better {
                    best = Some((index, path.metres, &robot.id));
                }
            }
            if let Some((index, _, _)) = best
                && let Some((_, mine)) = split.get_mut(index)
            {
                mine.push(stop.clone());
                assigned.push(stop);
            }
        }
        Ok(split)
    }
}

/// Up to this many stops the order is exact (every permutation, pruned).
const EXACT_UP_TO: usize = 8;

/// Pairwise path lengths between the start (node 0) and the stops (nodes 1..).
struct Matrix {
    size: usize,
    cells: Vec<f64>,
}

impl Matrix {
    fn build(nodes: &[&PlaceId], dist: impl Fn(&PlaceId, &PlaceId) -> f64) -> Matrix {
        let mut cells = Vec::with_capacity(nodes.len() * nodes.len());
        for a in nodes {
            for b in nodes {
                cells.push(dist(a, b));
            }
        }
        Matrix {
            size: nodes.len(),
            cells,
        }
    }

    /// Length between nodes `a` and `b` (infinite when unknown).
    fn at(&self, a: usize, b: usize) -> f64 {
        self.cells
            .get(a * self.size + b)
            .copied()
            .unwrap_or(f64::INFINITY)
    }

    /// Length between stop `a` (or the start when `None`) and stop `b`.
    fn leg(&self, a: Option<usize>, b: usize) -> f64 {
        self.at(a.map_or(0, |a| a + 1), b + 1)
    }
}

/// The shortest open order of `count` stops from the start, by depth-first search.
fn exact_order(matrix: &Matrix, count: usize) -> Vec<usize> {
    fn search(
        matrix: &Matrix,
        count: usize,
        path: &mut Vec<usize>,
        length: f64,
        best: &mut (f64, Vec<usize>),
    ) {
        if length >= best.0 {
            return;
        }
        if path.len() == count {
            *best = (length, path.clone());
            return;
        }
        for next in 0..count {
            if path.contains(&next) {
                continue;
            }
            let leg = matrix.leg(path.last().copied(), next);
            path.push(next);
            search(matrix, count, path, length + leg, best);
            path.pop();
        }
    }
    let mut best = (f64::INFINITY, nearest_neighbour(matrix, count));
    let mut path = Vec::with_capacity(count);
    search(matrix, count, &mut path, 0.0, &mut best);
    best.1
}

/// Nearest neighbour from the start; ties go to the earlier stop.
fn nearest_neighbour(matrix: &Matrix, count: usize) -> Vec<usize> {
    let mut order = Vec::with_capacity(count);
    let mut at = None;
    while order.len() < count {
        let next = (0..count)
            .filter(|stop| !order.contains(stop))
            .min_by(|a, b| matrix.leg(at, *a).total_cmp(&matrix.leg(at, *b)));
        let Some(next) = next else { break };
        order.push(next);
        at = Some(next);
    }
    order
}

/// Length of an open order from the start.
fn open_length(matrix: &Matrix, order: &[usize]) -> f64 {
    let mut at = None;
    let mut total = 0.0;
    for stop in order {
        total += matrix.leg(at, *stop);
        at = Some(*stop);
    }
    total
}

/// 2-opt on an open order (the start stays first): reverse a segment while that shortens it.
fn two_opt(matrix: &Matrix, mut order: Vec<usize>) -> Vec<usize> {
    let mut best = open_length(matrix, &order);
    for _ in 0..1_000 {
        let mut improved = false;
        for i in 0..order.len() {
            for j in (i + 1)..order.len() {
                let mut candidate = order.clone();
                if let Some(segment) = candidate.get_mut(i..=j) {
                    segment.reverse();
                }
                let length = open_length(matrix, &candidate);
                if length + 1e-9 < best {
                    best = length;
                    order = candidate;
                    improved = true;
                }
            }
        }
        if !improved {
            break;
        }
    }
    order
}
