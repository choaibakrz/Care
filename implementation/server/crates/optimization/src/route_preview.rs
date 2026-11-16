//! The route preview (Task 13b): the path a robot would probably take on one floor, a port of
//! `admin/src/lib/nav.ts` (`findPath`).
//!
//! **An estimate.** The real robot plans its own way; the console draws this path dashed and
//! says so. Steps: build (or reuse) the floor's [`PlanningGrid`] (walls, solid props, lifts,
//! outside of the building, restricted zones), move a start or goal on blocked ground to the
//! nearest free cell, run A*, straighten the cell path with line-of-sight checks, round its
//! corners with [`CORNER_RADIUS_M`](locations::grid::CORNER_RADIUS_M), and measure it.
//!
//! Restricted zones are impassable for planning only: the gardien does not enforce them yet
//! (open question 5). The dispatcher's path cost and the tour planner use the same rule
//! (Task 13b passes the restricted zones to their graph lengths).

use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use locations::grid::CORNER_RADIUS_M;
use locations::{ClinicMap, Disc, PlanningGrid, Point2, Zone};

/// A planned path on one floor.
///
/// Invariant: at least two points; `length_m` is the polyline length of `points`.
#[derive(Debug, Clone, PartialEq)]
pub struct PreviewPath {
    /// Floor level.
    pub floor: i32,
    /// From the start (moved to free ground if needed) to the goal, corners rounded.
    pub points: Vec<Point2>,
    /// Length, metres.
    pub length_m: f64,
}

/// Why no route can be drawn. Each message says what to check.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum RouteError {
    /// Start and goal are on different floors; robots do not take the lift.
    #[error(
        "The route goes from floor {from_floor} to floor {to_floor}; robots do not take the lift, so no route is drawn."
    )]
    DifferentFloors {
        /// Start floor.
        from_floor: i32,
        /// Goal floor.
        to_floor: i32,
    },
    /// The floor is not on the active plan.
    #[error("Floor {floor} is not on the clinic plan; check the plan.")]
    UnknownFloor {
        /// Level.
        floor: i32,
    },
    /// No free ground near the start or the goal.
    #[error(
        "The {end} is surrounded by walls, furniture or a restricted zone; move the place or the furniture in the plan."
    )]
    NoFreeGround {
        /// `start` or `goal`.
        end: &'static str,
    },
    /// Free ground at both ends, but walls, furniture or restricted zones separate them.
    #[error(
        "No way through on floor {floor}: walls, furniture or a restricted zone separate the two places."
    )]
    Unreachable {
        /// Level.
        floor: i32,
    },
}

/// Plans preview routes. Keeps the grids it built, keyed by map version, floor and the
/// restricted zones' ids and versions, so a busy console does not rebuild them.
#[derive(Debug, Default)]
pub struct RoutePreview {
    grids: Mutex<BTreeMap<String, Arc<PlanningGrid>>>,
}

impl RoutePreview {
    /// A planner with an empty cache.
    #[must_use]
    pub fn new() -> RoutePreview {
        RoutePreview::default()
    }

    /// The path from `from` to `to` on `floor` of `plan`, around walls, solid props, lifts
    /// and the restricted zones among `zones` (deaf zones are crossed).
    ///
    /// # Errors
    /// `UnknownFloor`, `NoFreeGround`, `Unreachable`.
    pub fn plan(
        &self,
        plan: &ClinicMap,
        zones: &[Zone],
        from: Point2,
        to: Point2,
        floor: i32,
    ) -> Result<PreviewPath, RouteError> {
        self.plan_around(plan, zones, from, to, floor, &[])
    }

    /// [`RoutePreview::plan`] that also drives around other robots (`others`): demo mode
    /// (Task 5b) uses it to steer simulated robots around each other.
    ///
    /// # Errors
    /// As [`RoutePreview::plan`].
    pub fn plan_around(
        &self,
        plan: &ClinicMap,
        zones: &[Zone],
        from: Point2,
        to: Point2,
        floor: i32,
        others: &[Disc],
    ) -> Result<PreviewPath, RouteError> {
        let grid = self.grid(plan, zones, floor)?;
        let straight = straight_route(&grid, from, to, others)?;
        let points = round_corners(&straight);
        let length_m = polyline_length(&points);
        Ok(PreviewPath {
            floor,
            points,
            length_m,
        })
    }

    /// The planning grid of `floor`, from the cache or built and cached.
    fn grid(
        &self,
        plan: &ClinicMap,
        zones: &[Zone],
        floor: i32,
    ) -> Result<Arc<PlanningGrid>, RouteError> {
        let mut key = format!("{}|{floor}", plan.version().as_str());
        for zone in zones
            .iter()
            .filter(|z| z.floor == floor && PlanningGrid::blocks(z))
        {
            key = format!("{key}|{}:{}", zone.id, zone.version);
        }
        let mut grids = self
            .grids
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if let Some(grid) = grids.get(&key) {
            return Ok(Arc::clone(grid));
        }
        let grid = Arc::new(
            PlanningGrid::build(plan, floor, zones)
                .map_err(|_| RouteError::UnknownFloor { floor })?,
        );
        grids.insert(key, Arc::clone(&grid));
        Ok(grid)
    }
}

/// A straightened (corners not rounded) route from `from` to `to` on `grid`, avoiding
/// `others`: ends on blocked ground move to the nearest free cell, A* joins them, and the
/// cell path is straightened with line-of-sight checks. At least two points.
pub(crate) fn straight_route(
    grid: &PlanningGrid,
    from: Point2,
    to: Point2,
    others: &[Disc],
) -> Result<Vec<Point2>, RouteError> {
    let start_cell = grid
        .nearest_free(&from)
        .ok_or(RouteError::NoFreeGround { end: "start" })?;
    let goal_cell = grid
        .nearest_free(&to)
        .ok_or(RouteError::NoFreeGround { end: "goal" })?;
    let start = if grid.is_free(&from) {
        from
    } else {
        grid.center_of(start_cell)
    };
    let goal = if grid.is_free(&to) {
        to
    } else {
        grid.center_of(goal_cell)
    };
    let cells = grid
        .find_cells(start_cell, goal_cell, others)
        .ok_or(RouteError::Unreachable {
            floor: grid.floor(),
        })?;
    let mut raw = vec![start];
    raw.extend(cells.iter().map(|cell| grid.center_of(*cell)));
    raw.push(goal);
    raw.dedup_by(|b, a| a.distance(b) < 1e-9);
    // Greedy line of sight: from each kept point, go as far along the cell path as a free
    // straight line allows.
    let mut points = Vec::new();
    let mut index = 0;
    while let Some(at) = raw.get(index) {
        points.push(*at);
        let mut next = index + 1;
        while let Some(further) = raw.get(next + 1) {
            if !grid.line_is_free(at, further) {
                break;
            }
            next += 1;
        }
        index = next;
    }
    if points.len() < 2 {
        points.push(goal);
    }
    Ok(points)
}

/// Length of a polyline, metres.
pub(crate) fn polyline_length(points: &[Point2]) -> f64 {
    points
        .windows(2)
        .map(|pair| match pair {
            [a, b] => a.distance(b),
            _ => 0.0,
        })
        .sum()
}

/// Rounds each interior corner with a quadratic curve of radius at most
/// [`CORNER_RADIUS_M`](locations::grid::CORNER_RADIUS_M) (half a segment at most).
fn round_corners(points: &[Point2]) -> Vec<Point2> {
    let mut out = Vec::with_capacity(points.len() * 3);
    if let Some(first) = points.first() {
        out.push(*first);
    }
    for triple in points.windows(3) {
        let [before, corner, after] = triple else {
            continue;
        };
        let (to_before, to_after) = (corner.distance(before), corner.distance(after));
        let radius = CORNER_RADIUS_M.min(to_before / 2.0).min(to_after / 2.0);
        if radius <= 1e-9 {
            out.push(*corner);
            continue;
        }
        let toward = |target: &Point2, length: f64| {
            Point2::new(
                corner.x() + (target.x() - corner.x()) / length * radius,
                corner.y() + (target.y() - corner.y()) / length * radius,
            )
        };
        let (Ok(entry), Ok(exit)) = (toward(before, to_before), toward(after, to_after)) else {
            out.push(*corner);
            continue;
        };
        out.push(entry);
        for share in [0.25, 0.5, 0.75] {
            let rest = 1.0 - share;
            let x = rest * rest * entry.x()
                + 2.0 * rest * share * corner.x()
                + share * share * exit.x();
            let y = rest * rest * entry.y()
                + 2.0 * rest * share * corner.y()
                + share * share * exit.y();
            if let Ok(point) = Point2::new(x, y) {
                out.push(point);
            }
        }
        out.push(exit);
    }
    if points.len() >= 2
        && let Some(last) = points.last()
    {
        out.push(*last);
    }
    out
}
