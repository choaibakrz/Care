//! The routing graph built from the map's links. Floors connect only through explicit links:
//! no link means no path ("robots do not change floors").
//!
//! Restricted zones (Task A4, Task 13b) are impassable for every planner: the dispatcher's
//! path cost and the tour planner read a graph built with [`RoutingGraph::from_map_with_zones`]
//! through a [`GraphHandle`], which the service layer (`services::routing::RoutingCache`)
//! replaces when a zone changes or another plan is activated. Planning only: the gardien does
//! not enforce restricted zones yet (open question 5).

use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, RwLock};

use domain::PlaceId;
use locations::{ClinicMap, Place, PlanningGrid, Zone};
use serde::Serialize;

use crate::route_preview;

/// A path between places.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Path {
    /// Places in order, both ends included.
    pub places: Vec<PlaceId>,
    /// Length.
    pub metres: f64,
}

/// Which places a path may use (from a role card).
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct PlaceMask {
    allowed: Option<BTreeSet<PlaceId>>,
}

impl PlaceMask {
    /// Every place.
    #[must_use]
    pub fn all() -> PlaceMask {
        PlaceMask { allowed: None }
    }
    /// Only these places.
    #[must_use]
    pub fn only(places: BTreeSet<PlaceId>) -> PlaceMask {
        PlaceMask {
            allowed: Some(places),
        }
    }
    /// Whether a place is allowed.
    #[must_use]
    pub fn permits(&self, place: &PlaceId) -> bool {
        self.allowed
            .as_ref()
            .is_none_or(|allowed| allowed.contains(place))
    }
}

/// Undirected weighted graph of places.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct RoutingGraph {
    adjacency: BTreeMap<PlaceId, Vec<(PlaceId, f64)>>,
}

impl RoutingGraph {
    /// Builds the graph from the map's links.
    #[must_use]
    pub fn from_map(map: &ClinicMap) -> RoutingGraph {
        let mut graph = RoutingGraph::default();
        for place in map.places() {
            graph.adjacency.entry(place.id.clone()).or_default();
        }
        for link in map.links() {
            graph.add_link(&link.from, &link.to, link.metres);
        }
        graph
    }

    /// Builds the graph from the map's links with the restricted zones among `zones` made
    /// impassable (deaf zones are ignored): a place whose anchor lies in a restricted zone is
    /// left out; a same-floor link is re-measured on the planning grid with those zones
    /// blocked (`locations::PlanningGrid`) and dropped when the grid cannot join its ends;
    /// explicit connections (lifts) are kept unless an end is left out. With no restricted
    /// zone it equals [`RoutingGraph::from_map`].
    ///
    /// Only the floors that carry a restricted zone are re-measured; the other floors keep
    /// the map's link lengths.
    #[must_use]
    pub fn from_map_with_zones(map: &ClinicMap, zones: &[Zone]) -> RoutingGraph {
        let restricted: Vec<Zone> = zones
            .iter()
            .filter(|zone| PlanningGrid::blocks(zone))
            .cloned()
            .collect();
        if restricted.is_empty() {
            return RoutingGraph::from_map(map);
        }
        let left_out = |place: &Place| {
            restricted
                .iter()
                .any(|zone| zone.floor == place.floor && zone.polygon.contains(&place.anchor))
        };
        let mut grids: BTreeMap<i32, Option<PlanningGrid>> = BTreeMap::new();
        for zone in &restricted {
            grids
                .entry(zone.floor)
                .or_insert_with(|| PlanningGrid::build(map, zone.floor, &restricted).ok());
        }
        let mut graph = RoutingGraph::default();
        for place in map.places().iter().filter(|place| !left_out(place)) {
            graph.adjacency.entry(place.id.clone()).or_default();
        }
        for link in map.links() {
            let (Some(a), Some(b)) = (map.place(&link.from), map.place(&link.to)) else {
                continue;
            };
            if left_out(a) || left_out(b) {
                continue;
            }
            let metres = match grids.get(&a.floor) {
                Some(Some(grid)) if a.floor == b.floor => {
                    match route_preview::straight_route(grid, a.anchor, b.anchor, &[]) {
                        Ok(points) => route_preview::polyline_length(&points).max(0.01),
                        Err(_) => continue,
                    }
                }
                _ => link.metres,
            };
            graph.add_link(&link.from, &link.to, metres);
        }
        graph
    }

    /// Dijkstra over permitted places; `None` when unreachable.
    #[must_use]
    pub fn shortest_path(
        &self,
        from: &PlaceId,
        to: &PlaceId,
        permitted: &PlaceMask,
    ) -> Option<Path> {
        if !permitted.permits(from) || !permitted.permits(to) || !self.contains(from) {
            return None;
        }
        let mut dist: BTreeMap<&PlaceId, f64> = BTreeMap::new();
        let mut prev: BTreeMap<&PlaceId, &PlaceId> = BTreeMap::new();
        let mut done: BTreeSet<&PlaceId> = BTreeSet::new();
        dist.insert(from, 0.0);
        loop {
            // Smallest tentative distance; ties go to the smaller place id (BTreeMap order).
            let mut best: Option<(&PlaceId, f64)> = None;
            for (place, d) in &dist {
                if !done.contains(place) && best.is_none_or(|(_, b)| *d < b) {
                    best = Some((place, *d));
                }
            }
            let (at, d) = best?;
            if at == to {
                break;
            }
            done.insert(at);
            for (next, metres) in self.adjacency.get(at).into_iter().flatten() {
                if done.contains(next) || !permitted.permits(next) {
                    continue;
                }
                let candidate = d + metres;
                if dist.get(next).is_none_or(|old| candidate < *old) {
                    dist.insert(next, candidate);
                    prev.insert(next, at);
                }
            }
        }
        let metres = *dist.get(to)?;
        let mut places = vec![to.clone()];
        let mut at = to;
        while let Some(before) = prev.get(at) {
            places.push((*before).clone());
            at = before;
        }
        places.reverse();
        Some(Path { places, metres })
    }

    /// Whether the graph knows a place.
    #[must_use]
    pub fn contains(&self, place: &PlaceId) -> bool {
        self.adjacency.contains_key(place)
    }

    /// Every place of the graph, in id order.
    pub(crate) fn places(&self) -> impl Iterator<Item = &PlaceId> {
        self.adjacency.keys()
    }

    /// Adds both directions of a link, keeping the shorter of two links between the same
    /// places.
    fn add_link(&mut self, a: &PlaceId, b: &PlaceId, metres: f64) {
        if a == b {
            return;
        }
        for (from, to) in [(a, b), (b, a)] {
            let edges = self.adjacency.entry(from.clone()).or_default();
            match edges.iter_mut().find(|(other, _)| other == to) {
                Some(edge) => edge.1 = edge.1.min(metres),
                None => edges.push((to.clone(), metres)),
            }
        }
    }
}

/// The routing graph in force, shared by the dispatcher and the tour planner. Cheap to clone;
/// [`GraphHandle::replace`] swaps the graph for every holder at once. Readers keep the `Arc`
/// they took (a plan in progress finishes on the graph it started with).
#[derive(Debug, Clone, Default)]
pub struct GraphHandle {
    current: Arc<RwLock<Arc<RoutingGraph>>>,
}

impl GraphHandle {
    /// A handle on `graph`.
    #[must_use]
    pub fn new(graph: RoutingGraph) -> GraphHandle {
        GraphHandle {
            current: Arc::new(RwLock::new(Arc::new(graph))),
        }
    }

    /// The graph in force (a poisoned lock still yields the last graph written).
    #[must_use]
    pub fn current(&self) -> Arc<RoutingGraph> {
        match self.current.read() {
            Ok(graph) => Arc::clone(&graph),
            Err(poisoned) => Arc::clone(&poisoned.into_inner()),
        }
    }

    /// Replaces the graph in force.
    pub fn replace(&self, graph: RoutingGraph) {
        match self.current.write() {
            Ok(mut current) => *current = Arc::new(graph),
            Err(poisoned) => *poisoned.into_inner() = Arc::new(graph),
        }
    }
}
