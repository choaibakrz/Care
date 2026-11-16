//! Real `DeviceAdminService` (Task A8, fill T8b): the tablet registry of the live server.
//!
//! Merges into A5's device registry: a tablet is a registered device plus its kind, label,
//! speciality (staff only), battery (from the location heartbeat), online (heard within
//! 120 s), assigned, and its live position (memory only, ruling R1). The A5 `patient_name`
//! of a staff tablet never appears in these admin answers.

use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use audit::{Category, Journal, RecordBody, Severity};
use chrono::{DateTime, Utc};
use domain::ports::DeviceRepository;
use domain::{Clock, DeviceId, PlaceId};
use locations::{ClinicMap, LivePositions, PlaceKind};
use realtime::{AppEvent, Hub, TabletKind};
use security::ClientIdentity;

use super::DeviceAdminService;
use crate::dto::{AssignTabletRequest, TabletView};
use crate::error::ApiError;

/// Longest tablet label, in characters (the `OwnerLabel` rule).
pub const MAX_TABLET_LABEL_LEN: usize = 40;
/// A tablet heard within this many seconds is `online` (the live tablet expiry).
pub const TABLET_ONLINE_S: i64 = 120;
/// `device.updated` for a battery change goes out at most this often per tablet, seconds.
pub const BATTERY_REPORT_EVERY_S: i64 = 10;

/// Whether `label` is a bed label (ruling R26): `^(Bed|Lit|Bett|Letto) ?\d{1,4}[A-Za-z]?$`,
/// case-insensitive ("Bed 12", "lit 3a", "Bett12"). A bedside tablet's label must be one, so
/// a patient's name ("Mrs Smith 12") is refused (422 `invalid_field`).
#[must_use]
pub fn is_bed_label(label: &str) -> bool {
    let lower = label.to_ascii_lowercase();
    let Some(rest) = ["letto", "bett", "bed", "lit"]
        .iter()
        .find_map(|word| lower.strip_prefix(word))
    else {
        return false;
    };
    let rest = rest.strip_prefix(' ').unwrap_or(rest);
    let digits = rest.chars().take_while(char::is_ascii_digit).count();
    if !(1..=4).contains(&digits) {
        return false;
    }
    let mut tail = rest.chars().skip(digits);
    match (tail.next(), tail.next()) {
        (None, _) => true,
        (Some(letter), None) => letter.is_ascii_alphabetic(),
        _ => false,
    }
}

/// What the real registry needs.
pub struct DeviceAdminDeps {
    /// Registered devices.
    pub devices: Arc<dyn DeviceRepository>,
    /// Live tablet positions (memory only).
    pub live: Arc<LivePositions>,
    /// `device.updated`.
    pub hub: Arc<Hub>,
    /// `device_freed`, `device_assigned`.
    pub journal: Journal,
    /// Server clock.
    pub clock: Arc<dyn Clock>,
}

/// What the admin set on a tablet (memory only: the device repository keeps the
/// registration, this keeps the hand-out).
#[derive(Debug, Clone)]
struct TabletMeta {
    kind: TabletKind,
    label: String,
    speciality: Option<String>,
    place: Option<PlaceId>,
    assigned: bool,
    last_seen: Option<DateTime<Utc>>,
}

impl TabletMeta {
    fn free() -> TabletMeta {
        TabletMeta {
            kind: TabletKind::Staff,
            label: String::new(),
            speciality: None,
            place: None,
            assigned: false,
            last_seen: None,
        }
    }
}

/// The tablet registry of the live server.
pub struct RealDeviceAdminService {
    deps: DeviceAdminDeps,
    tablets: Mutex<BTreeMap<DeviceId, TabletMeta>>,
}

impl RealDeviceAdminService {
    /// On the device repository and the live positions.
    #[must_use]
    pub fn new(deps: DeviceAdminDeps) -> RealDeviceAdminService {
        RealDeviceAdminService {
            deps,
            tablets: Mutex::new(BTreeMap::new()),
        }
    }

    fn meta(&self) -> std::sync::MutexGuard<'_, BTreeMap<DeviceId, TabletMeta>> {
        self.tablets
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    /// Every known tablet: those handed out here and those live on the map.
    fn views(&self) -> Vec<TabletView> {
        let snapshot = self.deps.live.snapshot();
        let mut meta = self.meta();
        for tablet in &snapshot.tablets {
            let entry = meta
                .entry(tablet.device_id.clone())
                .or_insert_with(|| TabletMeta {
                    label: tablet.owner.to_string(),
                    assigned: true,
                    ..TabletMeta::free()
                });
            entry.last_seen = Some(snapshot.at);
        }
        meta.iter()
            .map(|(id, entry)| {
                let live = snapshot.tablets.iter().find(|t| &t.device_id == id);
                TabletView {
                    device_id: id.clone(),
                    kind: entry.kind,
                    label: entry.label.clone(),
                    speciality: entry.speciality.clone(),
                    battery_pct: None,
                    online: live.is_some(),
                    assigned: entry.assigned,
                    place: live
                        .map(|t| t.place.clone())
                        .or_else(|| entry.place.clone()),
                    floor: live.map(|t| t.floor),
                    x: live.map(|t| t.point.x()),
                    y: live.map(|t| t.point.y()),
                    uncertainty_m: live.and_then(|t| t.uncertainty_m),
                    last_seen: entry.last_seen,
                }
            })
            .collect()
    }

    fn view_of(&self, id: &DeviceId) -> Result<TabletView, ApiError> {
        self.views()
            .into_iter()
            .find(|view| &view.device_id == id)
            .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))
    }

    /// Makes sure `id` is a live or registered tablet (404 otherwise).
    async fn ensure_known(&self, id: &DeviceId) -> Result<(), ApiError> {
        if self.views().iter().any(|view| &view.device_id == id) {
            return Ok(());
        }
        if self.deps.devices.find(id).await?.is_none() {
            return Err(ApiError::not_found("Tablet", id.as_str()));
        }
        self.meta()
            .entry(id.clone())
            .or_insert_with(TabletMeta::free);
        Ok(())
    }

    async fn journal(&self, actor: &ClientIdentity, body: RecordBody) {
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
            tracing::warn!(%error, "tablet change not journaled");
        }
    }
}

/// Checks an assignment request (422 `invalid_field`).
fn check_request(map: &ClinicMap, request: &AssignTabletRequest) -> Result<(), ApiError> {
    let label = request.label.trim();
    let length = label.chars().count();
    if length == 0 || length > MAX_TABLET_LABEL_LEN {
        return Err(ApiError::invalid_input(
            "label",
            &format!("must be 1 to {MAX_TABLET_LABEL_LEN} characters"),
        ));
    }
    if label.chars().all(|c| c.is_ascii_digit()) {
        return Err(ApiError::invalid_input("label", "must not be digits only"));
    }
    if request.kind == TabletKind::Bedside {
        if request.speciality.is_some() {
            return Err(ApiError::invalid_input(
                "speciality",
                "a bedside tablet has no speciality",
            ));
        }
        if !is_bed_label(label) {
            return Err(ApiError::invalid_input(
                "label",
                "a bedside tablet is labelled with its bed, such as Bed 12",
            ));
        }
        let room = request
            .place
            .as_ref()
            .and_then(|place| map.place(place))
            .is_some_and(|place| place.kind == PlaceKind::Room);
        if !room {
            return Err(ApiError::invalid_input(
                "place",
                "a bedside tablet needs a patient room",
            ));
        }
    }
    Ok(())
}

#[async_trait]
impl DeviceAdminService for RealDeviceAdminService {
    async fn list(&self) -> Result<Vec<TabletView>, ApiError> {
        Ok(self.views())
    }

    async fn disconnect(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
    ) -> Result<TabletView, ApiError> {
        self.ensure_known(id).await?;
        {
            let mut meta = self.meta();
            let entry = meta
                .get_mut(id)
                .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
            if !entry.assigned {
                return Err(ApiError::already_free(id.as_str()));
            }
            entry.assigned = false;
            entry.label.clear();
            entry.speciality = None;
            entry.place = None;
        }
        self.journal(actor, RecordBody::DeviceFreed { device: id.clone() })
            .await;
        let view = self.view_of(id)?;
        self.deps.hub.publish(AppEvent::DeviceUpdated {
            device: view.clone(),
        });
        Ok(view)
    }

    async fn assign(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
        request: AssignTabletRequest,
    ) -> Result<TabletView, ApiError> {
        self.ensure_known(id).await?;
        check_request(self.deps.live.map(), &request)?;
        let label = request.label.trim().to_owned();
        let bedside = request.kind == TabletKind::Bedside;
        {
            let mut meta = self.meta();
            let entry = meta
                .get_mut(id)
                .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
            if entry.assigned {
                return Err(ApiError::tablet_in_use(id.as_str()));
            }
            entry.kind = request.kind;
            entry.label.clone_from(&label);
            entry.speciality = if bedside { None } else { request.speciality };
            entry.place = request.place;
            entry.assigned = true;
            entry.last_seen = Some(self.deps.clock.now());
        }
        self.journal(
            actor,
            RecordBody::DeviceAssigned {
                device: id.clone(),
                bedside,
                bed_label: bedside.then_some(label),
            },
        )
        .await;
        let view = self.view_of(id)?;
        self.deps.hub.publish(AppEvent::DeviceUpdated {
            device: view.clone(),
        });
        Ok(view)
    }
}

#[cfg(test)]
mod tests {
    use super::is_bed_label;

    #[test]
    fn bed_labels_follow_the_strict_pattern() {
        for label in [
            "Bed 12",
            "bed 3a",
            "BED12",
            "Lit 4",
            "Bett 120",
            "Letto 9999",
            "Bed 7B",
        ] {
            assert!(is_bed_label(label), "{label}");
        }
        for label in [
            "Mrs Smith 12",
            "Bed",
            "Bed 12345",
            "Bed  12",
            "Bed 12ab",
            "12",
            "Anna",
            "Bed 12 Anna",
            "Bedroom 1",
        ] {
            assert!(!is_bed_label(label), "{label}");
        }
    }
}
