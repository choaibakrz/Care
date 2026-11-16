//! The planning grid of one floor (Task 13b, port of `admin/src/lib/nav.ts`).
//!
//! The floor is cut into square cells of [`GRID_CELL_M`]. A cell is **blocked** when its
//! centre is outside the floor outline, inside a closed room (a lift), inside a restricted
//! zone, or closer to a wall or a solid prop than the robot's body ([`ROBOT_CLEARANCE_M`]
//! plus half the wall thickness for walls). A cell is **near** when a blocked cell touches
//! it; A* multiplies the cost of a step into it so paths do not hug obstacles. Deaf zones do
//! not block.
//!
//! Every constant of the planner is here, in one place, with the values of `nav.ts` (lead's
//! ruling R13): 0.2 m cells, 0.42 m clearance, near steps cost 2.6 times more, a blocked start
//! or goal is moved at most 12 cells (2.4 m).

use std::cmp::Ordering;
use std::collections::BinaryHeap;
use std::f64::consts::SQRT_2;

use domain::ZoneKind;
use serde::Serialize;

use crate::error::LocationError;
use crate::geometry::{Point2, distance_to_segment};
use crate::model::{ClinicMap, ObstacleKind, Zone};

/// Side of a grid cell, metres (`nav.ts` `CELL`).
pub const GRID_CELL_M: f64 = 0.2;
/// Radius of the robot's body plus margin, metres: no cell centre closer than this to a solid
/// prop, nor closer than this plus half the wall thickness to a wall (`nav.ts`
/// `ROBOT_CLEARANCE`).
pub const ROBOT_CLEARANCE_M: f64 = 0.42;
/// Half the thickness of a plan wall, metres (`nav.ts` `WALL_HALF_THICKNESS`).
pub const WALL_HALF_THICKNESS_M: f64 = 0.08;
/// Radius used to round the corners of a straightened path, metres (`nav.ts`
/// `CORNER_RADIUS`).
pub const CORNER_RADIUS_M: f64 = 0.55;
/// How many cells a start or goal on blocked ground is moved, at most, to reach free ground
/// (searched in growing squares, `nav.ts` `nearestFree`): a place inside a lift or against a
/// shelf is reached from the nearest free cell.
pub const FREE_GROUND_SEARCH_CELLS: usize = 12;
/// The same distance in metres: `FREE_GROUND_SEARCH_CELLS × GRID_CELL_M` = 2.4 m.
pub const FREE_GROUND_SEARCH_M: f64 = 2.4;
/// Factor on the cost of a step into a `near` cell (`nav.ts`: `step * 2.6`).
pub const NEAR_OBSTACLE_COST_FACTOR: f64 = 2.6;

/// One cell: `column` along x, `row` along y (south).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize)]
pub struct GridCell {
    /// Column, from the west edge of the floor's bounding box.
    pub column: usize,
    /// Row, from the north edge.
    pub row: usize,
}

/// A disc other robots occupy, avoided by `PlanningGrid::find_cells` (demo mode: robots
/// drive around a robot standing in the corridor).
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct Disc {
    /// Centre.
    pub center: Point2,
    /// Radius, metres.
    pub radius_m: f64,
}

/// The blocked cells of one floor.
///
/// Invariant: `blocked` and `near` have `columns * rows` entries, row-major.
#[derive(Debug, Clone, PartialEq)]
pub struct PlanningGrid {
    floor: i32,
    columns: usize,
    rows: usize,
    origin: Point2,
    blocked: Vec<bool>,
    near: Vec<bool>,
}

impl PlanningGrid {
    /// Builds the grid of `floor` from the map's outline, walls and obstacles, and the
    /// restricted zones among `zones` on that floor (deaf zones are ignored).
    ///
    /// # Errors
    /// `UnknownFloor` when the map has no such floor.
    pub fn build(
        map: &ClinicMap,
        floor: i32,
        zones: &[Zone],
    ) -> Result<PlanningGrid, LocationError> {
        let level = map
            .floor(floor)
            .ok_or(LocationError::UnknownFloor { floor })?;
        let vertices = level.outline.vertices();
        let min_x = vertices.iter().map(Point2::x).fold(f64::INFINITY, f64::min);
        let min_y = vertices.iter().map(Point2::y).fold(f64::INFINITY, f64::min);
        let max_x = vertices
            .iter()
            .map(Point2::x)
            .fold(f64::NEG_INFINITY, f64::max);
        let max_y = vertices
            .iter()
            .map(Point2::y)
            .fold(f64::NEG_INFINITY, f64::max);
        let origin = Point2::new(min_x, min_y)?;
        let columns = cells_along(max_x - min_x);
        let rows = cells_along(max_y - min_y);
        let mut grid = PlanningGrid {
            floor,
            columns,
            rows,
            origin,
            blocked: vec![false; columns * rows],
            near: vec![false; columns * rows],
        };
        let obstacles: Vec<_> = map
            .obstacles()
            .iter()
            .filter(|obstacle| obstacle.floor == floor)
            .collect();
        let restricted: Vec<&Zone> = zones
            .iter()
            .filter(|zone| zone.floor == floor && PlanningGrid::blocks(zone))
            .collect();
        for row in 0..rows {
            for column in 0..columns {
                let centre = grid.center_of(GridCell { column, row });
                let outside = !level.outline.contains(&centre);
                let near_wall = level.walls.iter().any(|wall| {
                    distance_to_segment(&centre, &wall.start, &wall.end)
                        < wall.thickness_m / 2.0 + ROBOT_CLEARANCE_M
                });
                let in_obstacle = obstacles.iter().any(|obstacle| match obstacle.kind {
                    ObstacleKind::Closed => obstacle.area.contains(&centre),
                    ObstacleKind::Solid => {
                        obstacle.area.contains(&centre)
                            || distance_to_polygon(&centre, obstacle.area.vertices())
                                < ROBOT_CLEARANCE_M
                    }
                });
                let in_zone = restricted.iter().any(|zone| zone.polygon.contains(&centre));
                if (outside || near_wall || in_obstacle || in_zone)
                    && let Some(slot) = grid.blocked.get_mut(row * columns + column)
                {
                    *slot = true;
                }
            }
        }
        for row in 0..rows {
            for column in 0..columns {
                if grid.blocked_at(column, row) {
                    continue;
                }
                let touches = neighbours(column, row)
                    .any(|(c, r)| grid.inside(c, r) && grid.blocked_signed(c, r));
                if touches && let Some(slot) = grid.near.get_mut(row * columns + column) {
                    *slot = true;
                }
            }
        }
        Ok(grid)
    }

    /// Whether a zone blocks planning: only `restricted` zones do.
    #[must_use]
    pub fn blocks(zone: &Zone) -> bool {
        zone.kind == ZoneKind::Restricted
    }

    /// Floor level.
    #[must_use]
    pub fn floor(&self) -> i32 {
        self.floor
    }

    /// Columns (x).
    #[must_use]
    pub fn columns(&self) -> usize {
        self.columns
    }

    /// Rows (y).
    #[must_use]
    pub fn rows(&self) -> usize {
        self.rows
    }

    /// North-west corner of the grid (the floor outline's bounding box).
    #[must_use]
    pub fn origin(&self) -> Point2 {
        self.origin
    }

    /// The cell containing `point`, `None` outside the grid.
    #[must_use]
    pub fn cell_at(&self, point: &Point2) -> Option<GridCell> {
        let (column, row) = self.signed_cell(point);
        self.to_cell(column, row)
    }

    /// Centre of a cell.
    #[must_use]
    pub fn center_of(&self, cell: GridCell) -> Point2 {
        #[allow(clippy::cast_precision_loss)]
        let (column, row) = (cell.column as f64, cell.row as f64);
        let x = self.origin.x() + (column + 0.5) * GRID_CELL_M;
        let y = self.origin.y() + (row + 0.5) * GRID_CELL_M;
        Point2::new(x, y).unwrap_or(self.origin)
    }

    /// Whether the cell containing `point` is free.
    #[must_use]
    pub fn is_free(&self, point: &Point2) -> bool {
        let (column, row) = self.signed_cell(point);
        !self.blocked_signed(column, row)
    }

    /// The free cell nearest to `point` within [`FREE_GROUND_SEARCH_CELLS`] (growing squares,
    /// smallest distance in each ring), the point's own cell when free.
    #[must_use]
    pub fn nearest_free(&self, point: &Point2) -> Option<GridCell> {
        let (column, row) = self.signed_cell(point);
        if !self.blocked_signed(column, row) {
            return self.to_cell(column, row);
        }
        #[allow(clippy::cast_possible_wrap)]
        let reach = FREE_GROUND_SEARCH_CELLS as i64;
        for radius in 1..=reach {
            let mut best: Option<(f64, i64, i64)> = None;
            for dr in -radius..=radius {
                for dc in -radius..=radius {
                    if dr.abs().max(dc.abs()) != radius
                        || self.blocked_signed(column + dc, row + dr)
                    {
                        continue;
                    }
                    #[allow(clippy::cast_precision_loss)]
                    let distance = (dc as f64).hypot(dr as f64);
                    if best.is_none_or(|(d, _, _)| distance < d) {
                        best = Some((distance, column + dc, row + dr));
                    }
                }
            }
            if let Some((_, c, r)) = best {
                return self.to_cell(c, r);
            }
        }
        None
    }

    /// Whether the straight segment `a -> b` crosses only free cells (used to straighten
    /// paths).
    #[must_use]
    #[allow(clippy::many_single_char_names)]
    pub fn line_is_free(&self, a: &Point2, b: &Point2) -> bool {
        let length = a.distance(b);
        #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
        let steps = ((length / (GRID_CELL_M / 2.0)).ceil() as u64).max(1);
        (0..=steps).all(|index| {
            #[allow(clippy::cast_precision_loss)]
            let t = index as f64 / steps as f64;
            let x = a.x() + (b.x() - a.x()) * t;
            let y = a.y() + (b.y() - a.y()) * t;
            Point2::new(x, y).is_ok_and(|point| self.is_free(&point))
        })
    }

    /// A* over free cells, 8-connected (diagonals only when both side cells are free), cost
    /// 1 or √2 per step, times [`NEAR_OBSTACLE_COST_FACTOR`] into a near cell; cells inside a disc of
    /// `others` count as blocked. `None` when the goal cannot be reached.
    #[must_use]
    pub fn find_cells(
        &self,
        from: GridCell,
        to: GridCell,
        others: &[Disc],
    ) -> Option<Vec<GridCell>> {
        let start = self.index(from)?;
        let goal = self.index(to)?;
        if start == goal {
            return Some(vec![from]);
        }
        if self.blocked_with(to.column, to.row, others) {
            return None;
        }
        let total = self.columns * self.rows;
        let mut cost = vec![f64::INFINITY; total];
        let mut parent: Vec<Option<usize>> = vec![None; total];
        let mut closed = vec![false; total];
        *cost.get_mut(start)? = 0.0;
        let mut heap = BinaryHeap::new();
        heap.push(Open {
            score: 0.0,
            cell: from,
        });
        let heuristic = |cell: GridCell| {
            #[allow(clippy::cast_precision_loss)]
            let dx = cell.column.abs_diff(to.column) as f64;
            #[allow(clippy::cast_precision_loss)]
            let dy = cell.row.abs_diff(to.row) as f64;
            dx.max(dy) + (SQRT_2 - 1.0) * dx.min(dy)
        };
        while let Some(Open { cell, .. }) = heap.pop() {
            let current = self.index(cell)?;
            if current == goal {
                break;
            }
            if closed.get(current).copied().unwrap_or(true) {
                continue;
            }
            if let Some(slot) = closed.get_mut(current) {
                *slot = true;
            }
            let here = cost.get(current).copied().unwrap_or(f64::INFINITY);
            for (dc, dr, step) in STEPS {
                let Some(next) = self.offset(cell, dc, dr) else {
                    continue;
                };
                if self.blocked_with(next.column, next.row, others) {
                    continue;
                }
                if dc != 0 && dr != 0 {
                    let side_a = self.offset(cell, dc, 0);
                    let side_b = self.offset(cell, 0, dr);
                    let squeezed = [side_a, side_b].into_iter().any(|side| {
                        side.is_none_or(|side| self.blocked_with(side.column, side.row, others))
                    });
                    if squeezed {
                        continue;
                    }
                }
                let Some(next_index) = self.index(next) else {
                    continue;
                };
                let factor = if self.near.get(next_index).copied().unwrap_or(false) {
                    NEAR_OBSTACLE_COST_FACTOR
                } else {
                    1.0
                };
                let next_cost = here + step * factor;
                if next_cost >= cost.get(next_index).copied().unwrap_or(f64::INFINITY) {
                    continue;
                }
                if let Some(slot) = cost.get_mut(next_index) {
                    *slot = next_cost;
                }
                if let Some(slot) = parent.get_mut(next_index) {
                    *slot = Some(current);
                }
                heap.push(Open {
                    score: next_cost + heuristic(next),
                    cell: next,
                });
            }
        }
        parent.get(goal).copied().flatten()?;
        let mut cells = Vec::new();
        let mut walk = Some(goal);
        while let Some(index) = walk {
            cells.push(GridCell {
                column: index % self.columns,
                row: index / self.columns,
            });
            if index == start {
                break;
            }
            walk = parent.get(index).copied().flatten();
        }
        cells.reverse();
        Some(cells)
    }

    /// Row-major index of a cell inside the grid.
    fn index(&self, cell: GridCell) -> Option<usize> {
        (cell.column < self.columns && cell.row < self.rows)
            .then_some(cell.row * self.columns + cell.column)
    }

    /// The cell at a signed position, `None` outside the grid.
    fn to_cell(&self, column: i64, row: i64) -> Option<GridCell> {
        let column = usize::try_from(column).ok()?;
        let row = usize::try_from(row).ok()?;
        (column < self.columns && row < self.rows).then_some(GridCell { column, row })
    }

    /// `floor((p - origin) / GRID_CELL_M)` as signed indices.
    fn signed_cell(&self, point: &Point2) -> (i64, i64) {
        #[allow(clippy::cast_possible_truncation)]
        let column = ((point.x() - self.origin.x()) / GRID_CELL_M).floor() as i64;
        #[allow(clippy::cast_possible_truncation)]
        let row = ((point.y() - self.origin.y()) / GRID_CELL_M).floor() as i64;
        (column, row)
    }

    fn inside(&self, column: i64, row: i64) -> bool {
        self.to_cell(column, row).is_some()
    }

    /// Blocked, counting cells outside the grid as blocked.
    fn blocked_signed(&self, column: i64, row: i64) -> bool {
        self.to_cell(column, row)
            .is_none_or(|cell| self.blocked_at(cell.column, cell.row))
    }

    fn blocked_at(&self, column: usize, row: usize) -> bool {
        self.blocked
            .get(row * self.columns + column)
            .copied()
            .unwrap_or(true)
    }

    /// Blocked, or inside one of `others`.
    fn blocked_with(&self, column: usize, row: usize, others: &[Disc]) -> bool {
        if column >= self.columns || row >= self.rows || self.blocked_at(column, row) {
            return true;
        }
        if others.is_empty() {
            return false;
        }
        let centre = self.center_of(GridCell { column, row });
        others
            .iter()
            .any(|disc| centre.distance(&disc.center) < disc.radius_m)
    }

    fn offset(&self, cell: GridCell, dc: i64, dr: i64) -> Option<GridCell> {
        let column = i64::try_from(cell.column).ok()? + dc;
        let row = i64::try_from(cell.row).ok()? + dr;
        self.to_cell(column, row)
    }
}

/// The 8 moves with their length in cells.
const STEPS: [(i64, i64, f64); 8] = [
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, SQRT_2),
    (1, -1, SQRT_2),
    (-1, 1, SQRT_2),
    (-1, -1, SQRT_2),
];

/// Number of cells covering `length` metres (a hair of float noise does not add a cell).
fn cells_along(length: f64) -> usize {
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let cells = (length / GRID_CELL_M - 1e-9).ceil().max(0.0) as usize;
    cells
}

/// The 3 x 3 block around a cell (itself included), as signed indices.
fn neighbours(column: usize, row: usize) -> impl Iterator<Item = (i64, i64)> {
    let column = i64::try_from(column).unwrap_or(i64::MAX);
    let row = i64::try_from(row).unwrap_or(i64::MAX);
    (-1..=1).flat_map(move |dr| {
        (-1..=1).map(move |dc| (column.saturating_add(dc), row.saturating_add(dr)))
    })
}

/// Distance from `point` to the boundary of a closed ring.
fn distance_to_polygon(point: &Point2, vertices: &[Point2]) -> f64 {
    vertices
        .iter()
        .zip(vertices.iter().cycle().skip(1))
        .map(|(a, b)| distance_to_segment(point, a, b))
        .fold(f64::INFINITY, f64::min)
}

/// An open A* node; the heap pops the lowest score, ties by (row, column).
#[derive(Debug, Clone, Copy, PartialEq)]
struct Open {
    score: f64,
    cell: GridCell,
}

impl Eq for Open {}

impl Ord for Open {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .score
            .total_cmp(&self.score)
            .then_with(|| other.cell.row.cmp(&self.cell.row))
            .then_with(|| other.cell.column.cmp(&self.cell.column))
    }
}

impl PartialOrd for Open {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
