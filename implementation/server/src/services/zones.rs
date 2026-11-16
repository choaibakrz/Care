//! Real `ZoneService`: edit, deliver to robots, track acknowledgements.

use std::sync::Arc;

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use domain::ports::{RobotRepository, ZoneRepository};
use domain::{Clock, RobotId, ZoneId, ZoneKind, ZoneRecord, ZoneVersions};
use locations::{ClinicMap, Polygon};
use realtime::{AppEvent, Hub, RobotDown, WireZone, ZoneDelivery};
use security::ClientIdentity;

use super::ZoneService;
use super::routing::RoutingCache;
use crate::dto::{ZoneInput, ZoneView};
use crate::error::ApiError;

/// What `RealZoneService` needs.
pub struct ZoneDeps {
    /// Zones.
    pub repo: Arc<dyn ZoneRepository>,
    /// Map (floor outlines).
    pub map: Arc<ClinicMap>,
    /// Acknowledged versions.
    pub delivery: Arc<ZoneDelivery>,
    /// The dispatcher's graph: rebuilt after every change, since a restricted zone is
    /// impassable for planning (Task A4).
    pub routing: Arc<RoutingCache>,
    /// Hub.
    pub hub: Arc<Hub>,
    /// Registered robots (the delivery list shows offline robots too).
    pub robots: Arc<dyn RobotRepository>,
    /// Journal.
    pub journal: Journal,
    /// Clock.
    pub clock: Arc<dyn Clock>,
}

/// The real zone service.
pub struct RealZoneService {
    deps: ZoneDeps,
}

impl RealZoneService {
    /// A service.
    #[must_use]
    pub fn new(deps: ZoneDeps) -> RealZoneService {
        RealZoneService { deps }
    }

    /// Every known robot with whether it is connected: the registered ones (an unreadable
    /// store only drops the offline ones) plus any connected robot.
    async fn robot_lines(&self) -> Vec<(RobotId, bool)> {
        let connected = self.deps.hub.connected_robots();
        let mut lines: Vec<(RobotId, bool)> = match self.deps.robots.list().await {
            Ok(records) => records
                .into_iter()
                .map(|record| {
                    let online = connected.contains(&record.id);
                    (record.id, online)
                })
                .collect(),
            Err(error) => {
                tracing::warn!(%error, "zone deliveries without the offline robots");
                Vec::new()
            }
        };
        for robot in connected {
            if !lines.iter().any(|(known, _)| *known == robot) {
                lines.push((robot, true));
            }
        }
        lines
    }

    /// The console view of a stored zone, with one delivery line per known robot.
    fn view(&self, zone: ZoneRecord, robots: &[(RobotId, bool)]) -> ZoneView {
        ZoneView {
            deliveries: self
                .deps
                .delivery
                .entries_for(&zone.id, zone.version, robots),
            enforced_by_gardien: zone.kind == ZoneKind::Deaf,
            id: zone.id,
            name: zone.name,
            floor: zone.floor,
            kind: zone.kind,
            polygon: zone.polygon,
            version: zone.version,
        }
    }

    /// Journals a change (a failure is logged, never fatal).
    async fn journal_change(&self, actor: &ClientIdentity, body: RecordBody) {
        if let Err(error) = self
            .deps
            .journal
            .append(
                Severity::Notice,
                Category::Audit,
                actor.verified.subject_id.clone(),
                body,
                None,
            )
            .await
        {
            tracing::warn!(%error, "zone change not journaled");
        }
    }

    /// Sends the current list to every connected robot and rebuilds the routing graph.
    async fn after_change(&self) {
        match self.zones_update().await {
            Ok(down) => {
                let version = match &down {
                    RobotDown::ZonesUpdate { version, .. } => *version,
                    _ => 0,
                };
                for robot in self.deps.hub.broadcast_to_robots(down) {
                    tracing::warn!(%robot, "zones.update not delivered");
                    self.deps.delivery.record_send_failed(&robot, version);
                }
            }
            Err(error) => tracing::warn!(error = error.message(), "zones.update not built"),
        }
        if let Err(error) = self.deps.routing.rebuild().await {
            tracing::warn!(
                error = error.message(),
                "routing graph not rebuilt after a zone change"
            );
        }
    }
}

#[async_trait]
impl ZoneService for RealZoneService {
    async fn list(&self) -> Result<Vec<ZoneView>, ApiError> {
        let zones = self.deps.repo.list().await?;
        let robots = self.robot_lines().await;
        Ok(zones
            .into_iter()
            .map(|zone| self.view(zone, &robots))
            .collect())
    }

    async fn upsert(
        &self,
        actor: &ClientIdentity,
        id: ZoneId,
        input: ZoneInput,
    ) -> Result<ZoneView, ApiError> {
        if input.name.trim().is_empty() {
            return Err(ApiError::invalid_input("name", "must not be empty"));
        }
        let polygon = Polygon::from_pairs(&input.polygon)
            .map_err(|error| ApiError::invalid_input("polygon", &error.to_string()))?;
        let floor = self.deps.map.floor(input.floor).ok_or_else(|| {
            ApiError::invalid_input("floor", &format!("floor {} is not on the map", input.floor))
        })?;
        if !floor.outline.contains_polygon(&polygon) {
            return Err(ApiError::invalid_input(
                "polygon",
                &format!("of zone '{id}' must lie inside the floor outline"),
            ));
        }
        let version = self
            .deps
            .repo
            .list()
            .await?
            .iter()
            .find(|zone| zone.id == id)
            .map_or(1, |zone| zone.version.saturating_add(1));
        let record = ZoneRecord {
            id: id.clone(),
            name: input.name.trim().to_owned(),
            kind: input.kind,
            floor: input.floor,
            polygon: input.polygon,
            version,
        };
        self.deps.repo.upsert(&record).await?;
        self.journal_change(
            actor,
            RecordBody::ZoneChanged {
                zone: id,
                version,
                deleted: false,
            },
        )
        .await;
        let robots = self.robot_lines().await;
        let view = self.view(record, &robots);
        self.deps
            .hub
            .publish(AppEvent::ZoneUpdated { zone: view.clone() });
        self.after_change().await;
        Ok(view)
    }

    async fn delete(&self, actor: &ClientIdentity, id: &ZoneId) -> Result<(), ApiError> {
        let version = self
            .deps
            .repo
            .list()
            .await?
            .iter()
            .find(|zone| &zone.id == id)
            .map_or(0, |zone| zone.version);
        if self.deps.repo.delete(id).await?.is_none() {
            return Err(ApiError::not_found("Zone", id.as_str()));
        }
        self.journal_change(
            actor,
            RecordBody::ZoneChanged {
                zone: id.clone(),
                version,
                deleted: true,
            },
        )
        .await;
        self.deps.hub.publish(AppEvent::ZoneDeleted {
            zone_id: id.clone(),
        });
        self.after_change().await;
        Ok(())
    }

    async fn zones_update(&self) -> Result<RobotDown, ApiError> {
        let zones = self.deps.repo.list().await?;
        let version = self.deps.repo.global_version().await?;
        Ok(RobotDown::ZonesUpdate {
            zones: zones
                .into_iter()
                .map(|zone| WireZone {
                    id: zone.id,
                    kind: zone.kind,
                    floor: zone.floor,
                    polygon: zone.polygon,
                    version: zone.version,
                })
                .collect(),
            version,
        })
    }

    async fn record_ack(&self, robot: &RobotId, versions: &ZoneVersions) -> Result<(), ApiError> {
        self.deps.delivery.record_ack(robot, versions);
        // The console's "Received by" list follows `zone.updated`: publish each acked zone so
        // "waiting…" turns into "received" without a reload.
        let zones = self.deps.repo.list().await?;
        let robots = self.robot_lines().await;
        for zone in zones {
            if versions.contains_key(&zone.id) {
                let view = self.view(zone, &robots);
                self.deps.hub.publish(AppEvent::ZoneUpdated { zone: view });
            }
        }
        Ok(())
    }
}
