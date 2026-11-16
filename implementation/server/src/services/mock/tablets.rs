//! The mock tablet registry (Task A8: what fill T8b does on the live server, for real in
//! memory): the console's demo tablets (staff tablets with invented pseudonyms, bedside
//! tablets labelled with their bed, two free spares on the nurse station's shelf), batteries
//! that drain in use and charge on the shelf, free and hand out.
//!
//! Privacy: a bedside label is a bed ("Bed 12": `services::devices::is_bed_label`, ruling
//! R26), so a name is refused; there is no patient name and no health field anywhere here. A tablet in use has
//! a session token `mock-tablet-<device id>` (mock verifier only), revoked when the tablet is
//! freed, issued again when it is handed out.

use chrono::{DateTime, Utc};
use domain::{DeviceId, DomainError, OwnerLabel, PlaceId, Role};
use locations::{Point2, TabletLive};
use realtime::{AppEvent, TabletKind, TabletView};
use security::{ClientIdentity, VerifiedIdentity};

use super::{MockData, MockServices};
use crate::dto::AssignTabletRequest;
use crate::error::ApiError;

/// Prefix of a mock tablet session token: `mock-tablet-<device id>`.
pub const MOCK_TABLET_TOKEN_PREFIX: &str = "mock-tablet-";
/// Battery used per second by a tablet in use, in thousandths of a percent (1 % in 125 s).
const DRAIN_MILLI_PER_S: i64 = 8;
/// Battery gained per second on the shelf (1 % in 20 s).
const CHARGE_MILLI_PER_S: i64 = 50;
/// A full battery, in thousandths of a percent.
const FULL_MILLI: i64 = 100_000;
/// Where free tablets wait, by floor (the console's demo uses the same shelves).
const SHELVES: &[(i32, &str)] = &[(0, "reception"), (2, "nurse-station")];
/// The shelf of a floor without one.
const DEFAULT_SHELF: &str = "nurse-station";
/// Radius of a staff tablet's position estimate, metres (a bedside one is at its bed).
const STAFF_UNCERTAINTY_M: f64 = 2.5;

/// One seeded tablet (invented).
struct Seed {
    id: &'static str,
    kind: TabletKind,
    label: &'static str,
    speciality: Option<&'static str>,
    place: &'static str,
    battery: u8,
    online: bool,
}

/// The console's demo tablets (`admin/src/mock/sim-tablets.ts`), same ids and places.
const SEEDS: &[Seed] = &[
    Seed {
        id: "tab-bed-11",
        kind: TabletKind::Bedside,
        label: "Bed 11",
        speciality: None,
        place: "room-11",
        battery: 82,
        online: true,
    },
    Seed {
        id: "tab-bed-12",
        kind: TabletKind::Bedside,
        label: "Bed 12",
        speciality: None,
        place: "room-12",
        battery: 64,
        online: true,
    },
    Seed {
        id: "tab-bed-13",
        kind: TabletKind::Bedside,
        label: "Bed 13",
        speciality: None,
        place: "room-13",
        battery: 18,
        online: true,
    },
    Seed {
        id: "tab-bed-14",
        kind: TabletKind::Bedside,
        label: "Bed 14",
        speciality: None,
        place: "room-14",
        battery: 91,
        online: false,
    },
    Seed {
        id: "tab-dr-a",
        kind: TabletKind::Staff,
        label: "Dr. A",
        speciality: Some("Cardiology"),
        place: "room-12",
        battery: 71,
        online: true,
    },
    Seed {
        id: "tab-nurse-2",
        kind: TabletKind::Staff,
        label: "Ward 2 nurse",
        speciality: Some("Nursing"),
        place: "nurse-station",
        battery: 48,
        online: true,
    },
    Seed {
        id: "tab-physio-b",
        kind: TabletKind::Staff,
        label: "Physio B",
        speciality: Some("Physiotherapy"),
        place: "therapy-1",
        battery: 33,
        online: true,
    },
    Seed {
        id: "tab-reception",
        kind: TabletKind::Staff,
        label: "Reception desk",
        speciality: Some("Reception"),
        place: "reception",
        battery: 96,
        online: true,
    },
    Seed {
        id: "tab-spare-1",
        kind: TabletKind::Staff,
        label: "",
        speciality: None,
        place: "nurse-station",
        battery: 100,
        online: true,
    },
    Seed {
        id: "tab-spare-2",
        kind: TabletKind::Bedside,
        label: "",
        speciality: None,
        place: "nurse-station",
        battery: 77,
        online: true,
    },
];

/// One registered tablet of the mock.
pub(super) struct MockTablet {
    id: DeviceId,
    kind: TabletKind,
    label: String,
    speciality: Option<String>,
    /// Thousandths of a percent at `battery_at`.
    battery_milli: i64,
    battery_at: DateTime<Utc>,
    online: bool,
    assigned: bool,
    place: PlaceId,
    last_seen: DateTime<Utc>,
    /// The battery and online state last sent in `device.updated`.
    reported: Option<(u8, bool)>,
    /// The session token while in use.
    session: Option<String>,
}

/// The seeded registry; offline tablets were last heard 30 minutes before `now`.
pub(super) fn seed_tablets(now: DateTime<Utc>) -> Result<Vec<MockTablet>, DomainError> {
    SEEDS
        .iter()
        .map(|seed| {
            let id: DeviceId = seed.id.parse()?;
            let assigned = !seed.label.is_empty();
            Ok(MockTablet {
                session: assigned.then(|| format!("{MOCK_TABLET_TOKEN_PREFIX}{id}")),
                id,
                kind: seed.kind,
                label: seed.label.to_owned(),
                speciality: seed.speciality.map(str::to_owned),
                battery_milli: i64::from(seed.battery) * 1000,
                battery_at: now,
                online: seed.online,
                assigned,
                place: seed.place.parse()?,
                last_seen: if seed.online {
                    now
                } else {
                    now - chrono::Duration::minutes(30)
                },
                reported: None,
            })
        })
        .collect()
}

impl MockTablet {
    /// Drains (in use) or charges (free) the battery up to `now`; an empty battery switches
    /// the tablet off.
    fn advance(&mut self, now: DateTime<Utc>) {
        let seconds = (now - self.battery_at).num_seconds().max(0);
        if seconds == 0 {
            return;
        }
        self.battery_at = now;
        if !self.online {
            return;
        }
        let change = if self.assigned {
            -DRAIN_MILLI_PER_S.saturating_mul(seconds)
        } else {
            CHARGE_MILLI_PER_S.saturating_mul(seconds)
        };
        self.battery_milli = self
            .battery_milli
            .saturating_add(change)
            .clamp(0, FULL_MILLI);
        self.last_seen = now;
        if self.battery_milli == 0 {
            self.online = false;
        }
    }

    fn battery_pct(&self) -> u8 {
        u8::try_from(self.battery_milli / 1000).unwrap_or(100)
    }

    fn is_bedside(&self) -> bool {
        self.kind == TabletKind::Bedside
    }
}

impl MockData {
    /// The shelf of the floor of `place`.
    fn shelf_for(&self, place: &PlaceId) -> PlaceId {
        let floor = self.place(place).map(|(floor, _, _)| floor);
        let name = SHELVES
            .iter()
            .find(|(shelf_floor, _)| Some(*shelf_floor) == floor)
            .map_or(DEFAULT_SHELF, |(_, name)| name);
        name.parse().unwrap_or_else(|_| place.clone())
    }

    /// The view of tablet `index`: free tablets stand in a row beside their shelf, tablets in
    /// one room side by side.
    fn tablet_view(&self, index: usize, now: DateTime<Utc>) -> Option<TabletView> {
        let tablet = self.tablets.get(index)?;
        let neighbours = self
            .tablets
            .iter()
            .take(index)
            .filter(|other| other.place == tablet.place && other.assigned == tablet.assigned)
            .count();
        let slot = f64::from(u32::try_from(neighbours).unwrap_or(0));
        let position = self.place(&tablet.place).map(|(floor, x, y)| {
            if tablet.assigned {
                let angle = slot * 1.9 + 0.6;
                let radius = 0.55 + 0.15 * slot;
                (floor, x + angle.cos() * radius, y + angle.sin() * radius)
            } else {
                (floor, x + 1.4 + slot * 0.75, y + 1.7)
            }
        });
        Some(TabletView {
            device_id: tablet.id.clone(),
            kind: tablet.kind,
            label: tablet.label.clone(),
            speciality: tablet.speciality.clone(),
            battery_pct: Some(tablet.battery_pct()),
            online: tablet.online,
            assigned: tablet.assigned,
            place: Some(tablet.place.clone()),
            floor: position.map(|(floor, _, _)| floor),
            x: position.map(|(_, x, _)| x),
            y: position.map(|(_, _, y)| y),
            uncertainty_m: (tablet.assigned && !tablet.is_bedside()).then_some(STAFF_UNCERTAINTY_M),
            last_seen: Some(if tablet.online { now } else { tablet.last_seen }),
        })
    }

    fn advance_tablets(&mut self, now: DateTime<Utc>) {
        for tablet in &mut self.tablets {
            tablet.advance(now);
        }
    }

    /// The pseudonym and room of the staff tablet a robot may follow: online, handed out.
    pub(super) fn follow_target(&self, id: &DeviceId) -> Result<(String, PlaceId), ApiError> {
        let tablet = self
            .tablets
            .iter()
            .find(|tablet| &tablet.id == id)
            .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
        if tablet.is_bedside() || !tablet.assigned || !tablet.online {
            return Err(ApiError::invalid_input(
                "target_device",
                "is not an online staff tablet",
            ));
        }
        Ok((tablet.label.clone(), tablet.place.clone()))
    }

    /// The room of a tablet now.
    pub(super) fn tablet_place(&self, id: &DeviceId) -> Option<PlaceId> {
        self.tablets
            .iter()
            .find(|tablet| &tablet.id == id)
            .map(|tablet| tablet.place.clone())
    }

    fn tablet_index(&self, id: &DeviceId) -> Result<usize, ApiError> {
        self.tablets
            .iter()
            .position(|tablet| &tablet.id == id)
            .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))
    }
}

impl MockServices {
    /// `GET /devices`: every tablet, free and offline ones included.
    pub(super) fn mock_tablets(&self) -> Vec<TabletView> {
        let now = self.clock.now();
        let mut data = self.data();
        data.advance_tablets(now);
        (0..data.tablets.len())
            .filter_map(|index| data.tablet_view(index, now))
            .collect()
    }

    /// The tablets whose battery percentage or online state changed since their last
    /// `device.updated` (the ticker calls it every 10 s), marked as reported.
    pub(super) fn tablets_due(&self) -> Vec<TabletView> {
        let now = self.clock.now();
        let mut data = self.data();
        data.advance_tablets(now);
        let due: Vec<usize> = data
            .tablets
            .iter()
            .enumerate()
            .filter(|(_, tablet)| tablet.reported != Some((tablet.battery_pct(), tablet.online)))
            .map(|(index, _)| index)
            .collect();
        let views = due
            .iter()
            .filter_map(|index| data.tablet_view(*index, now))
            .collect();
        for index in due {
            if let Some(tablet) = data.tablets.get_mut(index) {
                tablet.reported = Some((tablet.battery_pct(), tablet.online));
            }
        }
        views
    }

    /// The live tablets of `GET /live`: assigned and online (their label is the owner).
    pub(super) fn live_tablets(&self) -> Result<Vec<TabletLive>, ApiError> {
        self.mock_tablets()
            .into_iter()
            .filter(|tablet| tablet.assigned && tablet.online)
            .filter_map(|tablet| {
                Some((
                    tablet.device_id,
                    tablet.label,
                    tablet.place?,
                    tablet.floor?,
                    tablet.x?,
                    tablet.y?,
                    tablet.uncertainty_m,
                ))
            })
            .map(|(device_id, label, place, floor, x, y, uncertainty_m)| {
                Ok(TabletLive {
                    device_id,
                    owner: OwnerLabel::new(&label)?,
                    place,
                    floor,
                    point: Point2::new(x, y)
                        .map_err(|_| ApiError::internal("mock tablet position"))?,
                    uncertainty_m,
                })
            })
            .collect()
    }

    /// Bedside tablets `(online, total)` (`GET /stats/service`).
    pub(super) fn bedside_counts(&self) -> (u32, u32) {
        let now = self.clock.now();
        let mut data = self.data();
        data.advance_tablets(now);
        let bedside: Vec<&MockTablet> = data.tablets.iter().filter(|t| t.is_bedside()).collect();
        let online = bedside.iter().filter(|tablet| tablet.online).count();
        (
            u32::try_from(online).unwrap_or(u32::MAX),
            u32::try_from(bedside.len()).unwrap_or(u32::MAX),
        )
    }

    /// `POST /devices/{id}/disconnect`.
    pub(super) fn mock_free_tablet(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
    ) -> Result<TabletView, ApiError> {
        let now = self.clock.now();
        let view = {
            let mut data = self.data();
            data.advance_tablets(now);
            let index = data.tablet_index(id)?;
            let place = data
                .tablets
                .get(index)
                .map(|tablet| tablet.place.clone())
                .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
            let home_shelf = data.shelf_for(&place);
            let tablet = data
                .tablets
                .get_mut(index)
                .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
            if !tablet.assigned {
                return Err(ApiError::already_free(id.as_str()));
            }
            tablet.session = None;
            tablet.assigned = false;
            tablet.label.clear();
            tablet.speciality = None;
            tablet.place = home_shelf;
            data.tablet_view(index, now)
                .ok_or_else(|| ApiError::internal("mock tablet view"))?
        };
        self.push_audit(actor, "device_freed", id.as_str(), None, "audit");
        self.publish(AppEvent::DeviceUpdated {
            device: view.clone(),
        });
        Ok(view)
    }

    /// `POST /devices/{id}/assign`.
    #[allow(
        clippy::needless_pass_by_value,
        reason = "owned arguments keep the call sites simple"
    )]
    pub(super) fn mock_assign_tablet(
        &self,
        actor: &ClientIdentity,
        id: &DeviceId,
        request: AssignTabletRequest,
    ) -> Result<TabletView, ApiError> {
        let now = self.clock.now();
        let view = {
            let mut data = self.data();
            data.advance_tablets(now);
            let index = data.tablet_index(id)?;
            let (assigned, online, current) = data
                .tablets
                .get(index)
                .map(|tablet| (tablet.assigned, tablet.online, tablet.place.clone()))
                .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
            if assigned {
                return Err(ApiError::tablet_in_use(id.as_str()));
            }
            if !online {
                return Err(ApiError::tablet_offline(id.as_str()));
            }
            let label = OwnerLabel::new(&request.label)?.to_string();
            let (place, speciality) = match request.kind {
                TabletKind::Bedside => {
                    if request.speciality.is_some() {
                        return Err(ApiError::invalid_input(
                            "speciality",
                            "must be null for a bedside tablet (staff tablets only)",
                        ));
                    }
                    if !crate::services::devices::is_bed_label(&label) {
                        return Err(ApiError::invalid_input(
                            "label",
                            "must be a bed label such as \"Bed 12\" (Bed, Lit, Bett or Letto and the bed number), never a patient's name",
                        ));
                    }
                    let place = request.place.clone().ok_or_else(|| {
                        ApiError::invalid_input(
                            "place",
                            "is required for a bedside tablet: the bed's patient room",
                        )
                    })?;
                    if !data.is_room(&place) {
                        return Err(ApiError::invalid_input(
                            "place",
                            "must be a patient room of the active plan for a bedside tablet",
                        ));
                    }
                    (place, None)
                }
                TabletKind::Staff => {
                    let place = match request.place.clone() {
                        Some(place) if data.place(&place).is_none() => {
                            return Err(ApiError::invalid_input(
                                "place",
                                "is not a place of the active plan",
                            ));
                        }
                        Some(place) => place,
                        None => current,
                    };
                    let speciality = request
                        .speciality
                        .as_deref()
                        .map(str::trim)
                        .filter(|text| !text.is_empty())
                        .map(str::to_owned);
                    if speciality
                        .as_ref()
                        .is_some_and(|text| text.chars().count() > 40)
                    {
                        return Err(ApiError::invalid_input(
                            "speciality",
                            "is longer than 40 characters",
                        ));
                    }
                    (place, speciality)
                }
            };
            let tablet = data
                .tablets
                .get_mut(index)
                .ok_or_else(|| ApiError::not_found("Tablet", id.as_str()))?;
            tablet.kind = request.kind;
            tablet.label = label;
            tablet.speciality = speciality;
            tablet.assigned = true;
            tablet.place = place;
            tablet.session = Some(format!("{MOCK_TABLET_TOKEN_PREFIX}{id}"));
            data.tablet_view(index, now)
                .ok_or_else(|| ApiError::internal("mock tablet view"))?
        };
        // The bed label is journaled for a bedside tablet only (never a staff pseudonym).
        let detail = match view.kind {
            TabletKind::Bedside => format!("bedside, {}", view.label),
            TabletKind::Staff => "staff".to_owned(),
        };
        self.push_audit(actor, "device_assigned", id.as_str(), Some(detail), "audit");
        self.publish(AppEvent::DeviceUpdated {
            device: view.clone(),
        });
        Ok(view)
    }

    /// The identity of a tablet session token (`mock-tablet-<id>`) while the tablet is in
    /// use: bound to the device, its label as the owner; a staff tablet acts as a nurse, a
    /// bedside one as the reception desk (the least privileged human role of the mock).
    pub(super) fn tablet_identity(&self, raw: &str) -> Option<VerifiedIdentity> {
        raw.strip_prefix(MOCK_TABLET_TOKEN_PREFIX)?;
        let data = self.data();
        let tablet = data
            .tablets
            .iter()
            .find(|tablet| tablet.session.as_deref() == Some(raw))?;
        Some(VerifiedIdentity {
            subject_id: domain::Actor::Device(tablet.id.clone()),
            role: if tablet.is_bedside() {
                Role::Reception
            } else {
                Role::Nurse
            },
            device_id: Some(tablet.id.clone()),
            owner: OwnerLabel::new(&tablet.label).ok(),
        })
    }
}
