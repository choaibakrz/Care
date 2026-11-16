//! The dispatcher: nearest free robot with the right role card and enough battery, a relay
//! between two robots when one cannot do it alone, else a human (port of `repartiteur.py`).

use domain::{PlaceId, RobotId, RobotStatus};
use serde::Serialize;

use crate::error::OptimizationError;
use crate::fleet::FleetMember;
use crate::graph::{GraphHandle, PlaceMask, RoutingGraph};

/// Battery rules.
#[derive(Debug, Clone, PartialEq)]
pub struct DispatchPolicy {
    /// Battery used per metre (default 0.5 %).
    pub consumption_pct_per_m: f64,
    /// A robot must keep this much after the trip (default 15 %).
    pub battery_threshold_pct: f64,
}

impl Default for DispatchPolicy {
    fn default() -> Self {
        DispatchPolicy {
            consumption_pct_per_m: 0.5,
            battery_threshold_pct: 15.0,
        }
    }
}

/// What to dispatch.
#[derive(Debug, Clone, PartialEq)]
pub struct DispatchRequest {
    /// Pick-up place.
    pub from: PlaceId,
    /// Drop place.
    pub to: PlaceId,
    /// Real deliveries never go to simulated robots.
    pub real_delivery: bool,
}

/// Why a robot was not chosen. `Display` is the explicit English text shown to staff.
///
/// Derives `thiserror::Error` only to get a checked `Display` per variant.
#[derive(Debug, Clone, PartialEq, Serialize, thiserror::Error)]
#[serde(tag = "reason", rename_all = "snake_case")]
pub enum RejectReason {
    /// Simulated robot for a real delivery.
    #[error("it is simulated and this is a real delivery")]
    Simulated,
    /// The robot reports a fault.
    #[error("it reports a fault ({detail})")]
    Faulted {
        /// Detail.
        detail: String,
    },
    /// Not free.
    #[error("it is not free (status {status:?})")]
    Busy {
        /// Status.
        status: RobotStatus,
    },
    /// The card forbids an end place.
    #[error("its role card '{card}' does not allow place '{place}'")]
    CardRefusesPlace {
        /// Place.
        place: PlaceId,
        /// Card.
        card: String,
    },
    /// No path.
    #[error("no path exists between the places for it")]
    NoPath,
    /// Not enough battery.
    #[error("its battery is {have_pct:.0}% but the trip needs {need_pct:.0}%")]
    LowBattery {
        /// Battery.
        have_pct: f64,
        /// Needed.
        need_pct: f64,
    },
    /// The card forbids a place on the route.
    #[error("its role card '{card}' does not allow place '{place}' on the route")]
    CardRefusesPlaceOnRoute {
        /// Place.
        place: PlaceId,
        /// Card.
        card: String,
    },
}

/// One robot's evaluation.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Consideration {
    /// Robot.
    pub robot: RobotId,
    /// Whether it can do the task.
    pub fits: bool,
    /// Why not.
    pub reject: Option<RejectReason>,
    /// Trip length.
    pub metres: Option<f64>,
}

/// A handover between two robots.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Relay {
    /// Handover place.
    pub via: PlaceId,
    /// First robot.
    pub first: RobotId,
    /// Second robot.
    pub second: RobotId,
    /// Total length.
    pub metres: f64,
}

/// The decision with its reasoning.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Decision {
    /// Chosen robot; `None` with no relay means "hand to a human".
    pub chosen: Option<RobotId>,
    /// Every robot considered.
    pub considered: Vec<Consideration>,
    /// Relay plan.
    pub relay: Option<Relay>,
    /// English explanation for staff.
    pub explanation: String,
}

/// The native dispatcher.
#[derive(Debug, Clone)]
pub struct Dispatcher {
    graph: GraphHandle,
    policy: DispatchPolicy,
}

impl Dispatcher {
    /// A dispatcher.
    #[must_use]
    pub fn new(graph: RoutingGraph, policy: DispatchPolicy) -> Dispatcher {
        Dispatcher::with_handle(GraphHandle::new(graph), policy)
    }

    /// A dispatcher reading the shared graph in force (Task A4): the real wiring uses it so
    /// a restricted zone or another active plan reaches the path costs without a restart.
    #[must_use]
    pub fn with_handle(graph: GraphHandle, policy: DispatchPolicy) -> Dispatcher {
        Dispatcher { graph, policy }
    }

    /// Chooses a robot (same decision as `repartiteur.py`).
    #[must_use]
    pub fn choose(&self, request: &DispatchRequest, fleet: &[FleetMember]) -> Decision {
        let graph = self.graph.current();
        let (from, to) = (&request.from, &request.to);
        let considered: Vec<Consideration> = fleet
            .iter()
            .map(|robot| self.consider(&graph, robot, from, to, request.real_delivery))
            .collect();
        let rejected = considered
            .iter()
            .zip(fleet)
            .filter_map(|(c, robot)| {
                c.reject
                    .as_ref()
                    .map(|why| format!("{} ({}): {why}", robot.name, robot.id))
            })
            .collect::<Vec<_>>()
            .join("; ");
        if let Some((chosen, robot)) = nearest(&considered, fleet) {
            let mut explanation = format!(
                "Sending {} ({}): it is free, the nearest ({:.0} m from '{from}'), and its role card '{}' allows '{from}' and '{to}'.",
                robot.name,
                robot.id,
                chosen.metres.unwrap_or(0.0),
                robot.card.name
            );
            if !rejected.is_empty() {
                explanation.push_str(" Not chosen: ");
                explanation.push_str(&rejected);
                explanation.push('.');
            }
            return Decision {
                chosen: Some(chosen.robot.clone()),
                considered,
                relay: None,
                explanation,
            };
        }
        let relay = if request.real_delivery {
            None
        } else {
            self.relay(&graph, from, to, fleet)
        };
        let explanation = if let Some(relay) = &relay {
            format!(
                "No robot can do the whole trip without leaving its permitted places. {} carries from '{from}' to '{}', then hands over to {}, who carries to '{to}'.",
                relay.first, relay.via, relay.second
            )
        } else {
            let why = if rejected.is_empty() {
                "no robot".to_owned()
            } else {
                rejected
            };
            format!("No robot fits ({why}): the task goes to a human.")
        };
        Decision {
            chosen: None,
            considered,
            relay,
            explanation,
        }
    }

    /// Evaluates one robot (port of `_regarder`), checks in the Python order.
    fn consider(
        &self,
        graph: &RoutingGraph,
        robot: &FleetMember,
        from: &PlaceId,
        to: &PlaceId,
        real_delivery: bool,
    ) -> Consideration {
        let all = PlaceMask::all();
        let approach = graph.shortest_path(&robot.at, from, &all);
        let trip = graph.shortest_path(from, to, &all);
        let metres = approach.as_ref().map(|p| p.metres);
        let card = &robot.card;
        let refused_end = [from, to]
            .into_iter()
            .find(|place| !card.permitted_places.contains(*place));
        let refused_on_route = approach
            .iter()
            .chain(trip.iter())
            .flat_map(|path| path.places.iter())
            .find(|place| !card.permitted_places.contains(*place));
        let need = match (&approach, &trip) {
            (Some(a), Some(t)) => Some((a.metres + t.metres) * self.policy.consumption_pct_per_m),
            _ => None,
        };
        let reject = if real_delivery && robot.simulated {
            Some(RejectReason::Simulated)
        } else if robot.status == RobotStatus::Fault {
            Some(RejectReason::Faulted {
                detail: "status fault".to_owned(),
            })
        } else if robot.status != RobotStatus::Idle {
            Some(RejectReason::Busy {
                status: robot.status,
            })
        } else if let Some(place) = refused_end {
            Some(RejectReason::CardRefusesPlace {
                place: place.clone(),
                card: card.name.clone(),
            })
        } else if let Some(need) = need {
            // `<=` as in the Python world: at the limit it would fail on arrival.
            if robot.battery_pct - need <= self.policy.battery_threshold_pct {
                Some(RejectReason::LowBattery {
                    have_pct: robot.battery_pct,
                    need_pct: need + self.policy.battery_threshold_pct,
                })
            } else {
                refused_on_route.map(|place| RejectReason::CardRefusesPlaceOnRoute {
                    place: place.clone(),
                    card: card.name.clone(),
                })
            }
        } else {
            Some(RejectReason::NoPath)
        };
        Consideration {
            robot: robot.id.clone(),
            fits: reject.is_none(),
            reject,
            metres,
        }
    }

    /// Two robots and a handover place both cards allow; the shortest total trip wins
    /// (port of `_relais`). Places are tried in id order.
    fn relay(
        &self,
        graph: &RoutingGraph,
        from: &PlaceId,
        to: &PlaceId,
        fleet: &[FleetMember],
    ) -> Option<Relay> {
        let all = PlaceMask::all();
        let mut best: Option<Relay> = None;
        for via in graph.places() {
            if via == from || via == to {
                continue;
            }
            let (Some(first_leg), Some(second_leg)) = (
                graph.shortest_path(from, via, &all),
                graph.shortest_path(via, to, &all),
            ) else {
                continue;
            };
            let first_round: Vec<Consideration> = fleet
                .iter()
                .map(|robot| self.consider(graph, robot, from, via, false))
                .collect();
            let Some((first, _)) = nearest(&first_round, fleet) else {
                continue;
            };
            let others: Vec<FleetMember> = fleet
                .iter()
                .filter(|robot| robot.id != first.robot)
                .cloned()
                .collect();
            let second_round: Vec<Consideration> = others
                .iter()
                .map(|robot| self.consider(graph, robot, via, to, false))
                .collect();
            let Some((second, _)) = nearest(&second_round, &others) else {
                continue;
            };
            let metres = first_leg.metres + second_leg.metres;
            if best.as_ref().is_none_or(|b| metres < b.metres) {
                best = Some(Relay {
                    via: via.clone(),
                    first: first.robot.clone(),
                    second: second.robot.clone(),
                    metres,
                });
            }
        }
        best
    }
}

/// The fitting robot nearest to the pick-up, ties broken by robot id.
fn nearest<'a>(
    considered: &'a [Consideration],
    fleet: &'a [FleetMember],
) -> Option<(&'a Consideration, &'a FleetMember)> {
    considered
        .iter()
        .zip(fleet)
        .filter(|(c, _)| c.fits)
        .min_by(|(a, _), (b, _)| {
            a.metres
                .unwrap_or(f64::INFINITY)
                .total_cmp(&b.metres.unwrap_or(f64::INFINITY))
                .then_with(|| a.robot.cmp(&b.robot))
        })
}

/// Anything that can decide a dispatch: the native dispatcher or the Python parity oracle.
pub trait DispatchOracle: Send + Sync {
    /// Decides. Blocking callers run it in `spawn_blocking` if it may block (Python).
    ///
    /// # Errors
    /// `Oracle` when an external oracle fails.
    fn choose(
        &self,
        request: &DispatchRequest,
        fleet: &[FleetMember],
    ) -> Result<Decision, OptimizationError>;
}

/// The default oracle: the native dispatcher.
#[derive(Debug, Clone)]
pub struct NativeOracle {
    dispatcher: Dispatcher,
}

impl NativeOracle {
    /// Wraps a dispatcher.
    #[must_use]
    pub fn new(dispatcher: Dispatcher) -> NativeOracle {
        NativeOracle { dispatcher }
    }
}

impl DispatchOracle for NativeOracle {
    fn choose(
        &self,
        request: &DispatchRequest,
        fleet: &[FleetMember],
    ) -> Result<Decision, OptimizationError> {
        Ok(self.dispatcher.choose(request, fleet))
    }
}
