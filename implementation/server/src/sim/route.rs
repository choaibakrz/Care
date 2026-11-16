//! Waypoints for simulated robots: a small visibility graph over the walls of one floor.
//!
//! Simplistic on purpose (Task 5). The candidate points are the plan's places, points set
//! diagonally off every wall corner and wall end, and the middle of every gap between two
//! wall ends (a door) with a point on each side of it. Two points are linked when the straight
//! line between them keeps [`EDGE_CLEARANCE_M`] from every wall; the shortest chain of links
//! is the route. So a simulated robot goes through doors and along corridors instead of
//! through walls, but it ignores furniture, zones, other robots and lifts (no route between
//! floors). The real planner is Task 13b (`locations::grid`), the demo's motion Task 5b.

use domain::PlaceId;
use locations::{ClinicPlan, MapPoint, PlanPlace};

/// Smallest distance from a wall for a candidate point to be kept.
const NODE_CLEARANCE_M: f64 = 0.35;
/// Distance from every wall a link must keep (less only next to a place closer to a wall).
const EDGE_CLEARANCE_M: f64 = 0.3;
/// Offset, along each axis, of the points set off a wall corner.
const CORNER_OFFSET_M: f64 = 0.5;
/// Narrowest gap between two wall ends taken as a door.
const DOOR_MIN_M: f64 = 0.7;
/// Widest gap between two wall ends taken as a door (the lounge opening is 4 m).
const DOOR_MAX_M: f64 = 4.5;
/// Distance of the points set on each side of a door.
const DOOR_APPROACH_M: f64 = 0.8;
/// Smallest clearance ever required of a link (it must not touch a wall).
const MIN_EDGE_CLEARANCE_M: f64 = 0.02;

/// One wall segment.
type Segment = (MapPoint, MapPoint);

/// The routes of every floor of one plan, and its places.
#[derive(Debug, Clone)]
pub struct SimPlanner {
    floors: Vec<FloorRouter>,
    places: Vec<PlanPlace>,
}

impl SimPlanner {
    /// Prepares the routes of every floor of `plan`.
    #[must_use]
    pub fn new(plan: &ClinicPlan) -> SimPlanner {
        let floors = plan
            .floors
            .iter()
            .map(|floor| FloorRouter::new(plan, floor.id, floor.outline.clone()))
            .collect();
        SimPlanner {
            floors,
            places: plan.places.clone(),
        }
    }

    /// A place of the plan: its floor and point.
    #[must_use]
    pub fn place(&self, id: &PlaceId) -> Option<(i32, MapPoint)> {
        self.places
            .iter()
            .find(|place| &place.id == id)
            .map(|place| (place.floor, [place.x, place.y]))
    }

    /// The places of one floor, in plan order.
    #[must_use]
    pub fn places_on(&self, floor: i32) -> Vec<&PlanPlace> {
        self.places
            .iter()
            .filter(|place| place.floor == floor)
            .collect()
    }

    /// The waypoints from `from` to `to` on `floor`, `to` included and `from` left out. When no
    /// chain of links joins them (or the floor is unknown) the route is the straight line,
    /// that is `[to]`.
    #[must_use]
    pub fn route(&self, floor: i32, from: MapPoint, to: MapPoint) -> Vec<MapPoint> {
        self.find_route(floor, from, to).unwrap_or_else(|| vec![to])
    }

    /// Like [`SimPlanner::route`], but `None` when no chain of links joins the two points or
    /// the floor is unknown (the destination cannot be reached).
    #[must_use]
    pub fn find_route(&self, floor: i32, from: MapPoint, to: MapPoint) -> Option<Vec<MapPoint>> {
        self.floors
            .iter()
            .find(|router| router.floor == floor)
            .and_then(|router| router.route(from, to))
    }
}

/// The visibility graph of one floor.
#[derive(Debug, Clone)]
struct FloorRouter {
    floor: i32,
    walls: Vec<Segment>,
    /// Candidate points with their clearance from the nearest wall.
    nodes: Vec<(MapPoint, f64)>,
}

impl FloorRouter {
    #[allow(
        clippy::needless_pass_by_value,
        reason = "owned arguments keep the call sites simple"
    )]
    fn new(plan: &ClinicPlan, floor: i32, outline: Vec<MapPoint>) -> FloorRouter {
        let polylines: Vec<&Vec<MapPoint>> = plan
            .walls
            .iter()
            .filter(|wall| wall.floor == floor)
            .map(|wall| &wall.points)
            .collect();
        let walls: Vec<Segment> = polylines
            .iter()
            .flat_map(|points| {
                points.windows(2).filter_map(|pair| match pair {
                    [a, b] => Some((*a, *b)),
                    _ => None,
                })
            })
            .collect();
        let mut candidates: Vec<MapPoint> = plan
            .places
            .iter()
            .filter(|place| place.floor == floor)
            .map(|place| [place.x, place.y])
            .collect();
        for point in polylines.iter().flat_map(|points| points.iter()) {
            for (dx, dy) in [(1.0, 1.0), (1.0, -1.0), (-1.0, 1.0), (-1.0, -1.0)] {
                candidates.push([
                    point[0] + dx * CORNER_OFFSET_M,
                    point[1] + dy * CORNER_OFFSET_M,
                ]);
            }
        }
        let ends: Vec<MapPoint> = polylines
            .iter()
            .flat_map(|points| points.first().into_iter().chain(points.last()))
            .copied()
            .collect();
        for (index, a) in ends.iter().enumerate() {
            for b in ends.iter().skip(index + 1) {
                candidates.extend(door_points(*a, *b));
            }
        }
        let mut router = FloorRouter {
            floor,
            walls,
            nodes: Vec::new(),
        };
        let nodes = candidates
            .into_iter()
            .filter(|point| inside(&outline, *point))
            .map(|point| (point, router.clearance(point)))
            .filter(|(_, clearance)| *clearance >= NODE_CLEARANCE_M)
            .collect();
        router.nodes = nodes;
        router
    }

    /// Distance from a point to the nearest wall (infinite on a floor with no wall).
    fn clearance(&self, point: MapPoint) -> f64 {
        self.walls
            .iter()
            .map(|(a, b)| point_segment_distance(point, *a, *b))
            .fold(f64::INFINITY, f64::min)
    }

    /// Whether the straight line `a`–`b` keeps `needed` metres from every wall.
    fn clear_line(&self, a: MapPoint, b: MapPoint, needed: f64) -> bool {
        self.walls
            .iter()
            .all(|(c, d)| segment_distance(a, b, *c, *d) >= needed)
    }

    /// Dijkstra over the candidate points plus `from` and `to`; `None` when they are not
    /// joined.
    fn route(&self, from: MapPoint, to: MapPoint) -> Option<Vec<MapPoint>> {
        let mut points: Vec<(MapPoint, f64)> = self.nodes.clone();
        points.push((from, self.clearance(from)));
        points.push((to, self.clearance(to)));
        let count = points.len();
        let start = count.checked_sub(2)?;
        let goal = count.checked_sub(1)?;
        let mut distance = vec![f64::INFINITY; count];
        let mut previous: Vec<Option<usize>> = vec![None; count];
        let mut settled = vec![false; count];
        *distance.get_mut(start)? = 0.0;
        loop {
            let current = (0..count)
                .filter(|index| !settled.get(*index).copied().unwrap_or(true))
                .filter(|index| distance.get(*index).is_some_and(|d| d.is_finite()))
                .min_by(|a, b| {
                    let da = distance.get(*a).copied().unwrap_or(f64::INFINITY);
                    let db = distance.get(*b).copied().unwrap_or(f64::INFINITY);
                    da.total_cmp(&db)
                })?;
            if current == goal {
                break;
            }
            *settled.get_mut(current)? = true;
            let (here, here_clearance) = *points.get(current)?;
            let here_distance = *distance.get(current)?;
            for (next, (there, there_clearance)) in points.iter().enumerate() {
                if settled.get(next).copied().unwrap_or(true) || next == current {
                    continue;
                }
                let step = length(here, *there);
                let through = here_distance + step;
                if through >= distance.get(next).copied().unwrap_or(f64::INFINITY) {
                    continue;
                }
                let needed = EDGE_CLEARANCE_M
                    .min(here_clearance - MIN_EDGE_CLEARANCE_M)
                    .min(there_clearance - MIN_EDGE_CLEARANCE_M)
                    .max(MIN_EDGE_CLEARANCE_M);
                if self.clear_line(here, *there, needed) {
                    *distance.get_mut(next)? = through;
                    *previous.get_mut(next)? = Some(current);
                }
            }
        }
        let mut chain = vec![to];
        let mut at = goal;
        while let Some(before) = previous.get(at).copied().flatten() {
            if before == start {
                break;
            }
            chain.push(points.get(before)?.0);
            at = before;
        }
        chain.reverse();
        Some(chain)
    }
}

/// The middle of the gap between two wall ends and a point on each side, when the gap is as
/// wide as a door.
fn door_points(a: MapPoint, b: MapPoint) -> Vec<MapPoint> {
    let width = length(a, b);
    if !(DOOR_MIN_M..=DOOR_MAX_M).contains(&width) {
        return Vec::new();
    }
    let middle = [f64::midpoint(a[0], b[0]), f64::midpoint(a[1], b[1])];
    let normal = [-(b[1] - a[1]) / width, (b[0] - a[0]) / width];
    vec![
        middle,
        [
            middle[0] + normal[0] * DOOR_APPROACH_M,
            middle[1] + normal[1] * DOOR_APPROACH_M,
        ],
        [
            middle[0] - normal[0] * DOOR_APPROACH_M,
            middle[1] - normal[1] * DOOR_APPROACH_M,
        ],
    ]
}

/// Euclidean distance.
fn length(a: MapPoint, b: MapPoint) -> f64 {
    (b[0] - a[0]).hypot(b[1] - a[1])
}

/// Distance from `p` to the segment `a`–`b`.
fn point_segment_distance(p: MapPoint, a: MapPoint, b: MapPoint) -> f64 {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let squared = dx * dx + dy * dy;
    if squared <= f64::EPSILON {
        return length(p, a);
    }
    let t = (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / squared).clamp(0.0, 1.0);
    length(p, [a[0] + t * dx, a[1] + t * dy])
}

/// Signed area test: which side of `a`–`b` the point `c` is on.
fn orientation(a: MapPoint, b: MapPoint, c: MapPoint) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}

/// Distance between the segments `a`–`b` and `c`–`d` (0 when they cross).
fn segment_distance(a: MapPoint, b: MapPoint, c: MapPoint, d: MapPoint) -> f64 {
    let (o1, o2) = (orientation(a, b, c), orientation(a, b, d));
    let (o3, o4) = (orientation(c, d, a), orientation(c, d, b));
    if o1 * o2 < 0.0 && o3 * o4 < 0.0 {
        return 0.0;
    }
    point_segment_distance(a, c, d)
        .min(point_segment_distance(b, c, d))
        .min(point_segment_distance(c, a, b))
        .min(point_segment_distance(d, a, b))
}

/// Whether a point is inside a polygon (ray casting; a floor with no outline holds every
/// point).
fn inside(outline: &[MapPoint], point: MapPoint) -> bool {
    if outline.len() < 3 {
        return true;
    }
    let mut within = false;
    for (a, b) in outline.iter().zip(outline.iter().cycle().skip(1)) {
        let crosses = (a[1] > point[1]) != (b[1] > point[1]);
        if crosses {
            let x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
            if point[0] < x {
                within = !within;
            }
        }
    }
    within
}

#[cfg(test)]
mod tests {
    use super::{SimPlanner, segment_distance};
    use crate::sim::seed_plan;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    /// Every leg of a route keeps clear of every wall of its floor.
    fn crosses_no_wall(
        plan: &locations::ClinicPlan,
        floor: i32,
        from: [f64; 2],
        route: &[[f64; 2]],
    ) -> bool {
        let walls: Vec<([f64; 2], [f64; 2])> = plan
            .walls
            .iter()
            .filter(|wall| wall.floor == floor)
            .flat_map(|wall| {
                wall.points.windows(2).filter_map(|pair| match pair {
                    [a, b] => Some((*a, *b)),
                    _ => None,
                })
            })
            .collect();
        let mut at = from;
        for next in route {
            if walls
                .iter()
                .any(|(c, d)| segment_distance(at, *next, *c, *d) <= 0.0)
            {
                return false;
            }
            at = *next;
        }
        true
    }

    #[test]
    fn seed_routes_go_through_doors_not_walls() -> TestResult {
        let plan = seed_plan()?;
        let planner = SimPlanner::new(&plan);
        let pairs = [
            ("dock-w", "room-12"),
            ("supply-a", "room-14"),
            ("dock-n", "lounge"),
            ("dock-a", "therapy-2"),
            ("linen-shelf", "pool"),
            ("dock-b", "reception"),
        ];
        for (from, to) in pairs {
            let (floor, start) = planner.place(&from.parse()?).ok_or(from)?;
            let (_, goal) = planner.place(&to.parse()?).ok_or(to)?;
            let route = planner.route(floor, start, goal);
            assert!(route.len() > 1, "{from} -> {to}: straight line {route:?}");
            assert_eq!(route.last(), Some(&goal));
            assert!(
                crosses_no_wall(&plan, floor, start, &route),
                "{from} -> {to} crosses a wall: {route:?}"
            );
        }
        Ok(())
    }

    #[test]
    fn unknown_floor_falls_back_to_the_straight_line() -> TestResult {
        let planner = SimPlanner::new(&seed_plan()?);
        assert_eq!(planner.route(9, [0.0, 0.0], [1.0, 1.0]), vec![[1.0, 1.0]]);
        Ok(())
    }
}
