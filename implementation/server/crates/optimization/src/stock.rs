//! The stock ledger. The trait, `Reservation`, `ReconcileOutcome` and `StockError` live in
//! `domain` (ports pattern: `storage::SqliteLedger` implements them without depending on this
//! crate); this module re-exports them and provides the in-memory ledger for fast tests.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use async_trait::async_trait;
use domain::{Clock, ItemId, PlaceId, SeenItem, TaskId};
pub use domain::{ReconcileOutcome, Reservation, StockError, StockLedger};
use uuid::Uuid;

/// Default reservation lifetime.
pub const DEFAULT_RESERVATION_LIFETIME: Duration = Duration::from_mins(30);

/// Ledger in memory, same rules as the SQLite one.
pub struct InMemoryLedger {
    clock: Arc<dyn Clock>,
    stock: Mutex<HashMap<ItemId, u32>>,
    reservations: Mutex<HashMap<Uuid, Reservation>>,
    shelves: Mutex<HashMap<(PlaceId, ItemId), u32>>,
}

impl InMemoryLedger {
    /// A ledger with initial stock.
    #[must_use]
    pub fn new(clock: Arc<dyn Clock>, stock: HashMap<ItemId, u32>) -> InMemoryLedger {
        InMemoryLedger {
            clock,
            stock: Mutex::new(stock),
            reservations: Mutex::new(HashMap::new()),
            shelves: Mutex::new(HashMap::new()),
        }
    }
}

#[async_trait]
impl StockLedger for InMemoryLedger {
    async fn reserve(
        &self,
        task: &TaskId,
        item: &ItemId,
        qty: u32,
    ) -> Result<Reservation, StockError> {
        // Lock order everywhere: stock, then reservations.
        let stock = self.stock.lock().unwrap_or_else(PoisonError::into_inner);
        let mut reservations = self
            .reservations
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        let in_stock = *stock
            .get(item)
            .ok_or_else(|| StockError::UnknownItem { item: item.clone() })?;
        let reserved: u32 = reservations
            .values()
            .filter(|r| r.item == *item)
            .map(|r| r.qty)
            .fold(0, u32::saturating_add);
        let available = in_stock.saturating_sub(reserved);
        if qty > available {
            return Err(StockError::OutOfStock {
                item: item.clone(),
                requested: qty,
                available,
                reserved,
            });
        }
        let reservation = Reservation {
            id: Uuid::new_v4(),
            task: task.clone(),
            item: item.clone(),
            qty,
            created_at: self.clock.now(),
        };
        reservations.insert(reservation.id, reservation.clone());
        Ok(reservation)
    }

    async fn commit(&self, reservation: &Reservation) -> Result<(), StockError> {
        let mut stock = self.stock.lock().unwrap_or_else(PoisonError::into_inner);
        let mut reservations = self
            .reservations
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        let held =
            reservations
                .remove(&reservation.id)
                .ok_or_else(|| StockError::ReservationGone {
                    task: reservation.task.clone(),
                })?;
        if let Some(count) = stock.get_mut(&held.item) {
            *count = count.saturating_sub(held.qty);
        }
        Ok(())
    }

    async fn release(&self, reservation: &Reservation) -> Result<(), StockError> {
        let mut reservations = self
            .reservations
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        reservations
            .remove(&reservation.id)
            .map(|_| ())
            .ok_or_else(|| StockError::ReservationGone {
                task: reservation.task.clone(),
            })
    }

    async fn expire_older_than(&self, age: Duration) -> Result<u32, StockError> {
        let now = self.clock.now();
        let age = chrono::Duration::from_std(age).unwrap_or(chrono::Duration::MAX);
        let mut reservations = self
            .reservations
            .lock()
            .unwrap_or_else(PoisonError::into_inner);
        let before = reservations.len();
        reservations.retain(|_, r| now.signed_duration_since(r.created_at) <= age);
        let dropped = before.saturating_sub(reservations.len());
        Ok(u32::try_from(dropped).unwrap_or(u32::MAX))
    }

    async fn reconcile(
        &self,
        place: &PlaceId,
        seen: &[SeenItem],
    ) -> Result<Vec<ReconcileOutcome>, StockError> {
        let stock = self.stock.lock().unwrap_or_else(PoisonError::into_inner);
        let mut shelves = self.shelves.lock().unwrap_or_else(PoisonError::into_inner);
        let mut outcomes = Vec::with_capacity(seen.len());
        for item in seen {
            // An uncertain count, or no count, never overwrites stock and never reads as zero.
            let count = match item.count {
                Some(count) if !item.uncertain => count,
                _ => {
                    outcomes.push(ReconcileOutcome::Uncertain {
                        item: item.item.clone(),
                    });
                    continue;
                }
            };
            shelves.insert((place.clone(), item.item.clone()), count);
            let expected = stock.get(&item.item).copied().unwrap_or(0);
            // A mismatch is flagged; stock changes only when an administrator confirms.
            outcomes.push(if expected == count {
                ReconcileOutcome::Matched {
                    item: item.item.clone(),
                }
            } else {
                ReconcileOutcome::Mismatch {
                    item: item.item.clone(),
                    expected,
                    seen: count,
                }
            });
        }
        Ok(outcomes)
    }
}
