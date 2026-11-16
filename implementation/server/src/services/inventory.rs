//! Real `InventoryService`.

use std::sync::Arc;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use domain::ports::{InventoryRepository, StockLedger};
use domain::{
    ItemId, PlaceId, ReconcileOutcome, RobotId, SeenItem, StockAdjustReason, StockLevel, Task,
};
use realtime::{AlertKind, AppEvent, Hub};
use security::ClientIdentity;

use super::InventoryService;
use crate::error::ApiError;

/// The real inventory service.
pub struct RealInventoryService {
    repo: Arc<dyn InventoryRepository>,
    ledger: Arc<dyn StockLedger>,
    journal: Journal,
    hub: Arc<Hub>,
}

impl RealInventoryService {
    /// A service.
    #[must_use]
    pub fn new(
        repo: Arc<dyn InventoryRepository>,
        ledger: Arc<dyn StockLedger>,
        journal: Journal,
        hub: Arc<Hub>,
    ) -> RealInventoryService {
        RealInventoryService {
            repo,
            ledger,
            journal,
            hub,
        }
    }
}

#[async_trait]
impl InventoryService for RealInventoryService {
    async fn list(&self) -> Result<Vec<StockLevel>, ApiError> {
        Ok(self.repo.list().await?)
    }
    async fn adjust(
        &self,
        actor: &ClientIdentity,
        item: &ItemId,
        delta: i32,
        reason: StockAdjustReason,
    ) -> Result<StockLevel, ApiError> {
        let level = self.repo.adjust(item, delta).await?;
        self.journal
            .append(
                Severity::Info,
                Category::Audit,
                actor.verified.subject_id.clone(),
                RecordBody::StockAdjusted {
                    item: item.clone(),
                    delta,
                    count_after: level.count,
                    reason,
                },
                None,
            )
            .await?;
        self.hub.publish(AppEvent::InventoryUpdated {
            item: level.clone(),
        });
        Ok(level)
    }
    async fn on_delivered(&self, task: &Task) -> Result<(), ApiError> {
        // The stock decrement is written with the task in one transaction
        // (`TaskRepository::apply_robot_event`); the reservation is released by the task
        // service. Here the new level is announced.
        let Some(item) = task.item() else {
            return Ok(());
        };
        if let Some(level) = self.repo.get(item).await? {
            self.hub.publish(AppEvent::InventoryUpdated { item: level });
        }
        Ok(())
    }
    async fn on_seen(
        &self,
        robot: &RobotId,
        place: &PlaceId,
        items: &[SeenItem],
    ) -> Result<Vec<ReconcileOutcome>, ApiError> {
        let outcomes = self.ledger.reconcile(place, items).await?;
        for outcome in &outcomes {
            let item = match outcome {
                ReconcileOutcome::Mismatch {
                    item,
                    expected,
                    seen,
                } => {
                    self.hub.publish(AppEvent::Alert {
                        level: AlertKind::StockMismatch.level(),
                        kind: AlertKind::StockMismatch,
                        message: format!(
                            "Robot {robot} counted {seen} '{item}' at {place}; the ledger says {expected}."
                        ),
                        command: None,
                    });
                    item
                }
                ReconcileOutcome::Matched { item } | ReconcileOutcome::Uncertain { item } => item,
            };
            if let Some(level) = self.repo.get(item).await? {
                self.hub.publish(AppEvent::InventoryUpdated { item: level });
            }
        }
        Ok(outcomes)
    }
}
