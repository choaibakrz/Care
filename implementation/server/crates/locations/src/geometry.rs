//! Plane geometry in metres: points, validated polygons, walls.

use serde::Serialize;
use utoipa::ToSchema;

use crate::error::LocationError;

/// A finite point in metres (x east, y south).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, ToSchema)]
pub struct Point2 {
    x: f64,
    y: f64,
}

impl Point2 {
    /// A point.
    ///
    /// # Errors
    /// `NonFinite` when a coordinate is NaN or infinite.
    pub fn new(x: f64, y: f64) -> Result<Point2, LocationError> {
        if x.is_finite() && y.is_finite() {
            Ok(Point2 { x, y })
        } else {
            Err(LocationError::NonFinite { what: "point" })
        }
    }
    /// Metres east.
    #[must_use]
    pub fn x(&self) -> f64 {
        self.x
    }
    /// Metres south.
    #[must_use]
    pub fn y(&self) -> f64 {
        self.y
    }
    /// Euclidean distance.
    #[must_use]
    pub fn distance(&self, other: &Point2) -> f64 {
        (self.x - other.x).hypot(self.y - other.y)
    }
}

/// A simple polygon: at least 3 vertices, non-zero area, no self-intersection, no repeated
/// consecutive points.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Polygon {
    vertices: Vec<Point2>,
}

impl Polygon {
    /// Validates a polygon.
    ///
    /// Checks, in this order: vertex count, repeated consecutive vertices (the last and the
    /// first count as consecutive), all vertices on one line (`ZeroArea`), crossing edges (non-adjacent edges that touch count as
    /// crossing; adjacent edges that fold back onto each other too), then zero area.
    ///
    /// # Errors
    /// `TooFewVertices`, `RepeatedPoint`, `SelfIntersecting`, `ZeroArea`.
    pub fn new(vertices: Vec<Point2>) -> Result<Polygon, LocationError> {
        let count = vertices.len();
        if count < 3 {
            return Err(LocationError::TooFewVertices { have: count });
        }
        let previous_of_each = vertices.iter().cycle().skip(count - 1);
        for ((index, point), previous) in vertices.iter().enumerate().zip(previous_of_each) {
            if point == previous {
                return Err(LocationError::RepeatedPoint { index });
            }
        }
        if let [first, second, rest @ ..] = vertices.as_slice()
            && rest.iter().all(|other| orient(first, second, other) == 0.0)
        {
            return Err(LocationError::ZeroArea);
        }
        let ring = edges(&vertices);
        for (edge_a, &(a1, a2)) in ring.iter().enumerate() {
            for (edge_b, &(b1, b2)) in ring.iter().enumerate().skip(edge_a + 1) {
                let adjacent = edge_b == edge_a + 1 || (edge_a == 0 && edge_b == count - 1);
                let crossing = if adjacent {
                    // They share one vertex; they only clash when folded back on each other.
                    let (shared_prev, shared, shared_next) = if edge_b == edge_a + 1 {
                        (a1, a2, b2)
                    } else {
                        (b1, b2, a2)
                    };
                    folds_back(shared_prev, shared, shared_next)
                } else {
                    segments_touch(a1, a2, b1, b2)
                };
                if crossing {
                    return Err(LocationError::SelfIntersecting { edge_a, edge_b });
                }
            }
        }
        if signed_area(&vertices).abs() <= ZERO_AREA_M2 {
            return Err(LocationError::ZeroArea);
        }
        Ok(Polygon { vertices })
    }
    /// Builds from `[x, y]` pairs (API and seed form).
    ///
    /// # Errors
    /// `NonFinite` and every error of [`Polygon::new`].
    pub fn from_pairs(pairs: &[[f64; 2]]) -> Result<Polygon, LocationError> {
        let vertices = pairs
            .iter()
            .map(|[x, y]| Point2::new(*x, *y))
            .collect::<Result<Vec<_>, _>>()?;
        Polygon::new(vertices)
    }
    /// Point-in-polygon (boundary counts as inside: a point within [`BOUNDARY_TOLERANCE_M`]
    /// of an edge is inside; the answer is a pure function of the inputs).
    #[must_use]
    pub fn contains(&self, point: &Point2) -> bool {
        let mut inside = false;
        for (a, b) in edges(&self.vertices) {
            if distance_to_segment(point, a, b) <= BOUNDARY_TOLERANCE_M {
                return true;
            }
            if (a.y > point.y) != (b.y > point.y)
                && point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x
            {
                inside = !inside;
            }
        }
        inside
    }
    /// Area centroid.
    #[must_use]
    pub fn centroid(&self) -> Point2 {
        let count = self.vertices.len();
        let area2 = signed_area(&self.vertices) * 2.0;
        let (mut cx, mut cy) = (0.0, 0.0);
        for (a, b) in edges(&self.vertices) {
            let cross = a.x * b.y - b.x * a.y;
            cx += (a.x + b.x) * cross;
            cy += (a.y + b.y) * cross;
        }
        let factor = 3.0 * area2;
        let (x, y) = (cx / factor, cy / factor);
        if x.is_finite() && y.is_finite() {
            return Point2 { x, y };
        }
        // Unreachable for a validated polygon (non-zero area); the vertex mean keeps the
        // function total.
        #[allow(clippy::cast_precision_loss)]
        let n = count as f64;
        Point2 {
            x: self.vertices.iter().map(|p| p.x).sum::<f64>() / n,
            y: self.vertices.iter().map(|p| p.y).sum::<f64>() / n,
        }
    }
    /// Whether `other` lies entirely inside (touching the boundary is allowed).
    #[must_use]
    pub fn contains_polygon(&self, other: &Polygon) -> bool {
        if !other.vertices.iter().all(|p| self.contains(p)) {
            return false;
        }
        let other_edges = edges(&other.vertices);
        let own_edges = edges(&self.vertices);
        for &(a, b) in &other_edges {
            let middle = Point2 {
                x: f64::midpoint(a.x, b.x),
                y: f64::midpoint(a.y, b.y),
            };
            if !self.contains(&middle) {
                return false;
            }
            for &(c, d) in &own_edges {
                if segments_cross_properly(a, b, c, d) {
                    return false;
                }
            }
        }
        // A corner of `self` strictly inside `other` means `other` covers a notch.
        !self.vertices.iter().any(|corner| {
            other.contains(corner)
                && other_edges
                    .iter()
                    .all(|&(a, b)| distance_to_segment(corner, a, b) > BOUNDARY_TOLERANCE_M)
        })
    }
    /// Vertices.
    #[must_use]
    pub fn vertices(&self) -> &[Point2] {
        &self.vertices
    }
    /// `[x, y]` pairs.
    #[must_use]
    pub fn to_pairs(&self) -> Vec<[f64; 2]> {
        self.vertices.iter().map(|p| [p.x, p.y]).collect()
    }
}

/// Areas at or below this (square metres) count as zero.
const ZERO_AREA_M2: f64 = 1e-12;
/// A point this close to an edge (metres) is on the boundary.
pub const BOUNDARY_TOLERANCE_M: f64 = 1e-9;

/// The edges of a closed ring: vertex `i` to vertex `i + 1`, the last back to the first.
fn edges(vertices: &[Point2]) -> Vec<(&Point2, &Point2)> {
    vertices
        .iter()
        .zip(vertices.iter().cycle().skip(1))
        .collect()
}

/// Shoelace area, positive for a counter-clockwise ring in a y-up frame.
fn signed_area(vertices: &[Point2]) -> f64 {
    edges(vertices)
        .iter()
        .map(|(a, b)| a.x * b.y - b.x * a.y)
        .sum::<f64>()
        / 2.0
}

/// Cross product of `(b - a)` and `(c - a)`.
fn orient(a: &Point2, b: &Point2, c: &Point2) -> f64 {
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}

/// Whether `p`, known to be collinear with `a`-`b`, lies within their bounding box.
fn within_box(a: &Point2, b: &Point2, p: &Point2) -> bool {
    p.x >= a.x.min(b.x) && p.x <= a.x.max(b.x) && p.y >= a.y.min(b.y) && p.y <= a.y.max(b.y)
}

/// Whether two closed segments share at least one point.
fn segments_touch(a1: &Point2, a2: &Point2, b1: &Point2, b2: &Point2) -> bool {
    let d1 = orient(a1, a2, b1);
    let d2 = orient(a1, a2, b2);
    let d3 = orient(b1, b2, a1);
    let d4 = orient(b1, b2, a2);
    segments_cross_properly(a1, a2, b1, b2)
        || (d1 == 0.0 && within_box(a1, a2, b1))
        || (d2 == 0.0 && within_box(a1, a2, b2))
        || (d3 == 0.0 && within_box(b1, b2, a1))
        || (d4 == 0.0 && within_box(b1, b2, a2))
}

/// Whether the segments cross at a point interior to both (touching does not count).
fn segments_cross_properly(a1: &Point2, a2: &Point2, b1: &Point2, b2: &Point2) -> bool {
    let d1 = orient(a1, a2, b1);
    let d2 = orient(a1, a2, b2);
    let d3 = orient(b1, b2, a1);
    let d4 = orient(b1, b2, a2);
    ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
        && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
}

/// Whether `previous -> shared -> next` turns back along the same line.
fn folds_back(previous: &Point2, shared: &Point2, next: &Point2) -> bool {
    let cross = orient(previous, shared, next);
    let dot = (shared.x - previous.x) * (next.x - shared.x)
        + (shared.y - previous.y) * (next.y - shared.y);
    cross == 0.0 && dot < 0.0
}

/// Distance from `p` to the closed segment `a`-`b`.
pub(crate) fn distance_to_segment(p: &Point2, a: &Point2, b: &Point2) -> f64 {
    let (dx, dy) = (b.x - a.x, b.y - a.y);
    let length2 = dx * dx + dy * dy;
    if length2 == 0.0 {
        return p.distance(a);
    }
    let t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / length2).clamp(0.0, 1.0);
    p.distance(&Point2 {
        x: a.x + t * dx,
        y: a.y + t * dy,
    })
}

/// A wall segment; particles of the positioning filter cannot cross it.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, ToSchema)]
pub struct Wall {
    /// Start.
    pub start: Point2,
    /// End.
    pub end: Point2,
    /// Thickness in metres.
    pub thickness_m: f64,
}

impl Wall {
    /// Whether the segment `a -> b` crosses this wall.
    #[must_use]
    pub fn crosses(&self, a: &Point2, b: &Point2) -> bool {
        segments_touch(a, b, &self.start, &self.end)
    }
}

#[cfg(test)]
mod tests {
    use super::{Point2, Polygon};
    use crate::error::LocationError;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn points(pairs: &[(f64, f64)]) -> Result<Vec<Point2>, LocationError> {
        pairs.iter().map(|(x, y)| Point2::new(*x, *y)).collect()
    }

    #[test]
    fn point_rejects_nan_and_infinity() -> TestResult {
        for (x, y) in [
            (f64::NAN, 0.0),
            (0.0, f64::NAN),
            (f64::INFINITY, 0.0),
            (0.0, f64::NEG_INFINITY),
        ] {
            let err = Point2::new(x, y)
                .err()
                .ok_or("a non-finite point was accepted")?;
            assert!(matches!(err, LocationError::NonFinite { .. }), "{err:?}");
        }
        let point = Point2::new(1.5, -2.0)?;
        assert!((point.x() - 1.5).abs() < f64::EPSILON);
        assert!((point.y() + 2.0).abs() < f64::EPSILON);
        Ok(())
    }

    #[test]
    fn bowtie_polygon_is_rejected_with_the_crossing_edges_named() -> TestResult {
        let bowtie = points(&[(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0)])?;
        let err = Polygon::new(bowtie)
            .err()
            .ok_or("a bowtie polygon was accepted")?;
        assert_eq!(
            err,
            LocationError::SelfIntersecting {
                edge_a: 0,
                edge_b: 2
            }
        );
        assert!(err.to_string().contains("edges 0 and 2"), "{err}");
        Ok(())
    }

    #[test]
    fn polygon_with_two_points_is_rejected() -> TestResult {
        let err = Polygon::new(points(&[(0.0, 0.0), (1.0, 1.0)])?)
            .err()
            .ok_or("a two-point polygon was accepted")?;
        assert_eq!(err, LocationError::TooFewVertices { have: 2 });
        Ok(())
    }

    #[test]
    fn contains_boundary_point_is_deterministic() -> TestResult {
        let square = || Polygon::from_pairs(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]]);
        let first = square()?;
        let second = square()?;
        for (x, y) in [(4.0, 2.0), (0.0, 0.0), (2.0, 4.0), (0.0, 1.0)] {
            let point = Point2::new(x, y)?;
            let answer = first.contains(&point);
            for _ in 0..100 {
                assert_eq!(first.contains(&point), answer, "({x}, {y}) flickers");
            }
            assert_eq!(second.contains(&point), answer, "({x}, {y}) differs");
        }
        assert!(first.contains(&Point2::new(2.0, 2.0)?));
        assert!(!first.contains(&Point2::new(5.0, 2.0)?));
        Ok(())
    }

    fn square() -> Result<Polygon, LocationError> {
        Polygon::from_pairs(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
    }

    #[test]
    fn repeated_zero_area_and_non_finite_input_are_rejected() -> TestResult {
        let repeated = Polygon::new(points(&[(0.0, 0.0), (0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])?);
        assert_eq!(repeated, Err(LocationError::RepeatedPoint { index: 1 }));
        let wrapped = Polygon::new(points(&[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)])?);
        assert_eq!(wrapped, Err(LocationError::RepeatedPoint { index: 0 }));
        let flat = Polygon::from_pairs(&[[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]);
        assert_eq!(flat, Err(LocationError::ZeroArea));
        let message = LocationError::ZeroArea.to_string();
        assert!(message.contains("all vertices on one line"), "{message}");
        let flat_folded = Polygon::from_pairs(&[[0.0, 0.0], [2.0, 0.0], [1.0, 0.0], [3.0, 0.0]]);
        assert_eq!(flat_folded, Err(LocationError::ZeroArea));
        let sliver = Polygon::from_pairs(&[[0.0, 0.0], [1.0, 0.0], [1.0, 1e-13]]);
        assert_eq!(sliver, Err(LocationError::ZeroArea));
        let folded = Polygon::from_pairs(&[[0.0, 0.0], [2.0, 0.0], [1.0, 0.0], [1.0, 1.0]]);
        assert!(
            matches!(folded, Err(LocationError::SelfIntersecting { .. })),
            "{folded:?}"
        );
        let nan = Polygon::from_pairs(&[[0.0, 0.0], [1.0, f64::NAN], [1.0, 1.0]]);
        assert!(matches!(nan, Err(LocationError::NonFinite { .. })));
        let touching =
            Polygon::from_pairs(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [2.0, 0.0], [0.0, 4.0]]);
        assert!(
            matches!(touching, Err(LocationError::SelfIntersecting { .. })),
            "{touching:?}"
        );
        Ok(())
    }

    #[test]
    fn contains_handles_concave_clockwise_and_tiny_polygons() -> TestResult {
        let l_shape = Polygon::from_pairs(&[
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 1.0],
            [1.0, 1.0],
            [1.0, 4.0],
            [0.0, 4.0],
        ])?;
        assert!(l_shape.contains(&Point2::new(0.5, 3.0)?));
        assert!(l_shape.contains(&Point2::new(3.0, 0.5)?));
        assert!(!l_shape.contains(&Point2::new(3.0, 3.0)?), "the notch");
        let clockwise = Polygon::from_pairs(&[[0.0, 0.0], [0.0, 4.0], [4.0, 4.0], [4.0, 0.0]])?;
        assert!(clockwise.contains(&Point2::new(2.0, 2.0)?));
        let sliver = Polygon::from_pairs(&[[0.0, 0.0], [1e-3, 0.0], [0.0, 1e-3]])?;
        assert!(sliver.contains(&Point2::new(1e-4, 1e-4)?));
        assert!(!sliver.contains(&Point2::new(1.0, 1.0)?));
        Ok(())
    }

    #[test]
    fn contains_includes_every_edge_and_corner_and_excludes_just_outside() -> TestResult {
        let square = square()?;
        for (x, y) in [
            (0.0, 0.0),
            (4.0, 4.0),
            (4.0, 0.0),
            (0.0, 4.0),
            (2.0, 0.0),
            (4.0, 3.0),
        ] {
            assert!(
                square.contains(&Point2::new(x, y)?),
                "({x}, {y}) is on the boundary"
            );
        }
        for (x, y) in [
            (4.001, 2.0),
            (-0.001, 2.0),
            (2.0, -0.001),
            (2.0, 4.001),
            (1e9, 1e9),
        ] {
            assert!(
                !square.contains(&Point2::new(x, y)?),
                "({x}, {y}) is outside"
            );
        }
        Ok(())
    }

    #[test]
    fn centroid_is_the_area_centre_for_both_windings() -> TestResult {
        let centre = square()?.centroid();
        assert!((centre.x() - 2.0).abs() < 1e-9 && (centre.y() - 2.0).abs() < 1e-9);
        let clockwise = Polygon::from_pairs(&[[0.0, 0.0], [0.0, 3.0], [6.0, 3.0], [6.0, 0.0]])?;
        let centre = clockwise.centroid();
        assert!((centre.x() - 3.0).abs() < 1e-9 && (centre.y() - 1.5).abs() < 1e-9);
        let triangle = Polygon::from_pairs(&[[0.0, 0.0], [3.0, 0.0], [0.0, 3.0]])?;
        let centre = triangle.centroid();
        assert!((centre.x() - 1.0).abs() < 1e-9 && (centre.y() - 1.0).abs() < 1e-9);
        Ok(())
    }

    #[test]
    fn contains_polygon_accepts_touching_and_refuses_overhang_and_notch_cover() -> TestResult {
        let outer = square()?;
        let inner = Polygon::from_pairs(&[[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]])?;
        assert!(outer.contains_polygon(&inner));
        assert!(outer.contains_polygon(&outer.clone()), "equal polygons");
        let corner = Polygon::from_pairs(&[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])?;
        assert!(outer.contains_polygon(&corner));
        let overhang = Polygon::from_pairs(&[[3.0, 3.0], [5.0, 3.0], [5.0, 5.0], [3.0, 5.0]])?;
        assert!(!outer.contains_polygon(&overhang));
        let l_shape = Polygon::from_pairs(&[
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 1.0],
            [1.0, 1.0],
            [1.0, 4.0],
            [0.0, 4.0],
        ])?;
        let across_notch = Polygon::from_pairs(&[[0.5, 0.5], [3.5, 0.5], [3.5, 3.5], [0.5, 3.5]])?;
        assert!(!l_shape.contains_polygon(&across_notch));
        Ok(())
    }

    #[test]
    fn pairs_round_trip() -> TestResult {
        let pairs = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]];
        let polygon = Polygon::from_pairs(&pairs)?;
        assert_eq!(polygon.to_pairs(), pairs.to_vec());
        assert_eq!(polygon.vertices().len(), 3);
        Ok(())
    }
}
