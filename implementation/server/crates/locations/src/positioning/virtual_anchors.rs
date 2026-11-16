//! The virtual-anchor reduction: a moving tablet with known displacement `d_k` seen from
//! anchors `q_k` equals a static unknown `p_0` seen from `v_k = q_k − d_k`. Unique in 2D with
//! at least 3 non-collinear virtual anchors (proof in `docs/positioning-proof.md`).

use crate::geometry::Point2;

/// Virtual anchors needed for a unique 2D solution.
const MIN_ANCHORS: usize = 3;
/// Points within this distance of the line count as on it, metres.
const COLLINEAR_TOLERANCE_M: f64 = 0.01;

/// A line through two points.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Line2 {
    /// A point on the line.
    pub a: Point2,
    /// Another point on the line.
    pub b: Point2,
}

/// Whether the virtual anchors determine the start point.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Identifiability {
    /// Unique.
    Unique,
    /// Known up to a mirror image across `line` (collinear anchors).
    Mirror {
        /// The mirror line.
        line: Line2,
    },
    /// Not enough anchors.
    Underdetermined {
        /// Anchors available.
        have: usize,
        /// Anchors needed (3).
        need: usize,
    },
}

/// Virtual anchors with their ranges, over a short window.
#[derive(Debug, Clone, Default)]
pub struct VirtualAnchors {
    points: Vec<(Point2, f64)>,
}

impl VirtualAnchors {
    /// Empty.
    #[must_use]
    pub fn new() -> VirtualAnchors {
        VirtualAnchors { points: Vec::new() }
    }

    /// Adds `v = anchor − displacement` with its measured range.
    pub fn push(&mut self, anchor: Point2, displacement: (f64, f64), range_m: f64) {
        if let Ok(point) = Point2::new(anchor.x() - displacement.0, anchor.y() - displacement.1)
            && range_m.is_finite()
        {
            self.points.push((point, range_m));
        }
    }

    /// Clears the window (PDR drift makes old anchors useless).
    pub fn clear(&mut self) {
        self.points.clear();
    }

    /// The identifiability test.
    #[must_use]
    pub fn identifiability(&self) -> Identifiability {
        let have = self.points.len();
        if have < MIN_ANCHORS {
            return Identifiability::Underdetermined {
                have,
                need: MIN_ANCHORS,
            };
        }
        // The farthest pair spans the candidate line.
        let mut best: Option<(f64, Point2, Point2)> = None;
        for (index, (a, _)) in self.points.iter().enumerate() {
            for (b, _) in self.points.iter().skip(index + 1) {
                let length = a.distance(b);
                if best.is_none_or(|(longest, _, _)| length > longest) {
                    best = Some((length, *a, *b));
                }
            }
        }
        let Some((length, a, b)) = best.filter(|(length, _, _)| *length > COLLINEAR_TOLERANCE_M)
        else {
            return Identifiability::Underdetermined {
                have: 1,
                need: MIN_ANCHORS,
            };
        };
        let collinear = self.points.iter().all(|(p, _)| {
            let cross = (b.x() - a.x()) * (p.y() - a.y()) - (b.y() - a.y()) * (p.x() - a.x());
            (cross / length).abs() <= COLLINEAR_TOLERANCE_M
        });
        if collinear {
            Identifiability::Mirror {
                line: Line2 { a, b },
            }
        } else {
            Identifiability::Unique
        }
    }

    /// Number of virtual anchors.
    #[must_use]
    pub fn len(&self) -> usize {
        self.points.len()
    }

    /// Whether there is none.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.points.is_empty()
    }
}
