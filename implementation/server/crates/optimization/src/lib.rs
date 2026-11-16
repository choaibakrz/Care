//! Routing graph, dispatcher (port of `repartiteur.py`), stock ledger, tour planner, shelf
//! leases and space-time reservations.

pub mod dispatcher;
pub mod error;
pub mod fleet;
pub mod graph;
pub mod lease;
pub mod reservation;
pub mod route_preview;
pub mod stock;
pub mod tour;

pub use dispatcher::{
    Consideration, Decision, DispatchOracle, DispatchPolicy, DispatchRequest, Dispatcher,
    NativeOracle, RejectReason, Relay,
};
pub use error::OptimizationError;
pub use fleet::{FleetMember, RoleCard};
pub use graph::{GraphHandle, Path, PlaceMask, RoutingGraph};
pub use lease::{Lease, LeaseError, ShelfLeases};
pub use reservation::{Conflict, PlaceOrEdge, ReservationTable};
pub use route_preview::{PreviewPath, RouteError, RoutePreview};
pub use stock::{InMemoryLedger, ReconcileOutcome, Reservation, StockError, StockLedger};
pub use tour::{SkippedStop, Tour, TourPlanner};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
