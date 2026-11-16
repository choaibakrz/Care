//! The positioning pipeline for every tablet.

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use domain::{DeviceId, PlaceId};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use super::PositioningError;
use super::fingerprint::{FingerprintIndex, SurveySample};
use super::observation::{Anchor, AnchorId, AnchorKind, Observation, ScanReport};
use super::particle_filter::{DEFAULT_PARTICLES, FilterEstimate, ParticleFilter};
use super::path_loss::PathLossModel;
use super::room_tracker::{FINGERPRINT_MIN_CONFIDENCE, ROOM_HYSTERESIS, RoomTracker};
use super::smoothing::SmootherBank;
use super::trilateration::{Trilaterator, WeightedRange};
use super::virtual_anchors::{Identifiability, Line2, VirtualAnchors};
use crate::error::LocationError;
use crate::geometry::Point2;
use crate::live::{DEFAULT_TX_POWER_DBM_1M, LivePositions};
use crate::model::{ClinicMap, Floor};

/// How the room was decided.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Method {
    /// Fingerprint confidence >= 0.6.
    Fingerprint,
    /// Particle filter estimate.
    ParticleFilter,
    /// Single-shot trilateration.
    Trilateration,
    /// Hand pick or QR code.
    Manual,
}

/// The result for one tablet.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct PositionEstimate {
    /// Floor.
    pub floor: i32,
    /// Room.
    pub place: PlaceId,
    /// Estimated point (shown only when `uncertainty_m <= 3`).
    pub point: Point2,
    /// 2σ radius.
    pub uncertainty_m: f64,
    /// Method.
    pub method: Method,
}

/// Site data loaded from `seed/` (`fixed_devices.json`, `beacons.json`, `fingerprints.json`).
#[derive(Debug, Clone)]
pub struct PositionerConfig {
    /// Path-loss calibration.
    pub model: PathLossModel,
    /// Fingerprint survey.
    pub fingerprints: FingerprintIndex,
    /// Fixed devices and beacons.
    pub fixed_anchors: Vec<Anchor>,
    /// Particles per tablet.
    pub particles: usize,
    /// Seed of the filters (deterministic tests).
    pub seed: u64,
}

impl PositionerConfig {
    /// Loads the seed files from `dir`; missing optional files mean empty lists.
    ///
    /// Formats: `fixed_devices.json` and `beacons.json` are arrays of
    /// `{id, floor, x, y, tx_power_dbm_1m?}` (a fixed device's `id` is its device id);
    /// `fingerprints.json` is an array of `{place, rssi: {anchor: dBm}}`. Each file may also
    /// wrap its array in an object (the first array field is read, so a `"marque"` key fits).
    ///
    /// # Errors
    /// `Seed` when a present file is invalid.
    pub fn from_seed_dir(dir: &Path) -> Result<PositionerConfig, PositioningError> {
        let mut fixed_anchors = Vec::new();
        for row in read_rows::<SeedAnchor>(&dir.join("fixed_devices.json"))? {
            let device: DeviceId = row.id.parse().map_err(|error| PositioningError::Seed {
                reason: format!("fixed_devices.json: device id '{}': {error}", row.id),
            })?;
            fixed_anchors.push(row.into_anchor(AnchorKind::FixedDevice(device))?);
        }
        for row in read_rows::<SeedAnchor>(&dir.join("beacons.json"))? {
            fixed_anchors.push(row.into_anchor(AnchorKind::Beacon)?);
        }
        let samples = read_rows::<SurveySample>(&dir.join("fingerprints.json"))?;
        Ok(PositionerConfig {
            model: PathLossModel::default(),
            fingerprints: FingerprintIndex::from_survey(&samples),
            fixed_anchors,
            particles: DEFAULT_PARTICLES,
            seed: DEFAULT_SEED,
        })
    }
}

/// Seed of the filters when none is configured.
const DEFAULT_SEED: u64 = 0x5eed_11b0;
/// EMA factor of the RSSI smoothers.
const SMOOTHING_ALPHA: f64 = 0.5;
/// How long a virtual anchor stays usable (PDR drift makes old ones useless).
const VIRTUAL_ANCHOR_WINDOW: Duration = Duration::from_secs(10);
/// Time step assumed for the first scan of a tablet.
const FIRST_STEP: Duration = Duration::from_secs(1);
/// Variance added to every range weight, square metres (no anchor is perfect).
const RANGE_VARIANCE_FLOOR_M2: f64 = 0.01;

/// One fixed device or beacon of the seed files.
#[derive(Debug, Deserialize)]
struct SeedAnchor {
    id: String,
    floor: i32,
    x: f64,
    y: f64,
    #[serde(default)]
    tx_power_dbm_1m: Option<f64>,
}

impl SeedAnchor {
    fn into_anchor(self, kind: AnchorKind) -> Result<Anchor, PositioningError> {
        Ok(Anchor {
            id: AnchorId(self.id),
            kind,
            floor: self.floor,
            point: Point2::new(self.x, self.y)?,
            spread_m: 0.0,
            tx_power_dbm_1m: self.tx_power_dbm_1m.unwrap_or(DEFAULT_TX_POWER_DBM_1M),
        })
    }
}

/// Rows of an optional seed file: an array, or the first array inside an object.
fn read_rows<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>, PositioningError> {
    let text = match std::fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => {
            return Err(PositioningError::Seed {
                reason: format!("{}: {error}", path.display()),
            });
        }
    };
    let invalid = |error: serde_json::Error| PositioningError::Seed {
        reason: format!("{}: {error}", path.display()),
    };
    let value: serde_json::Value = serde_json::from_str(&text).map_err(invalid)?;
    let rows = match value {
        serde_json::Value::Array(_) => value,
        serde_json::Value::Object(fields) => fields
            .into_iter()
            .map(|(_, field)| field)
            .find(serde_json::Value::is_array)
            .unwrap_or(serde_json::Value::Array(Vec::new())),
        _ => serde_json::Value::Array(Vec::new()),
    };
    serde_json::from_value(rows).map_err(invalid)
}

/// A range to a virtual anchor, kept for the short window.
#[derive(Debug, Clone, Copy)]
struct WindowEntry {
    at: DateTime<Utc>,
    /// The anchor's position minus the tablet's PDR displacement at that scan.
    anchor: Point2,
    /// The real anchor, for the identifiability test.
    real_anchor: Point2,
    /// The displacement at that scan.
    displacement: (f64, f64),
    metres: f64,
    weight: f64,
}

/// Per-tablet state, in memory only.
#[derive(Debug, Clone)]
struct DeviceTrack {
    filter: Option<ParticleFilter>,
    smoothers: SmootherBank,
    rooms: RoomTracker,
    virtual_anchors: VirtualAnchors,
    last_scan: Option<DateTime<Utc>>,
    /// PDR displacement accumulated since the track began.
    displacement: (f64, f64),
    /// Floor of the window and the filter.
    floor: Option<i32>,
    window: Vec<WindowEntry>,
    last: Option<PositionEstimate>,
}

impl DeviceTrack {
    fn new() -> DeviceTrack {
        DeviceTrack {
            filter: None,
            smoothers: SmootherBank::new(SMOOTHING_ALPHA),
            rooms: RoomTracker::new(ROOM_HYSTERESIS),
            virtual_anchors: VirtualAnchors::new(),
            last_scan: None,
            displacement: (0.0, 0.0),
            floor: None,
            window: Vec::new(),
            last: None,
        }
    }
}

/// A heard anchor with its distance.
struct Heard<'a> {
    anchor: &'a Anchor,
    metres: f64,
    weight: f64,
}

/// The positioning pipeline.
pub struct Positioner {
    map: Arc<ClinicMap>,
    live: Arc<LivePositions>,
    config: PositionerConfig,
    tracks: HashMap<DeviceId, DeviceTrack>,
}

impl Positioner {
    /// A positioner over the map, reading robot anchors from live positions.
    #[must_use]
    pub fn new(
        map: Arc<ClinicMap>,
        live: Arc<LivePositions>,
        config: PositionerConfig,
    ) -> Positioner {
        Positioner {
            map,
            live,
            config,
            tracks: HashMap::new(),
        }
    }

    /// Processes one scan. The caller then stores the result with
    /// `LivePositions::set_tablet_estimate` (it knows the owner label).
    ///
    /// # Errors
    /// Validation errors of `ScanReport::validate`; `TooFewAnchors` with no previous estimate.
    // Taken by value on purpose: the raw scan is consumed and dropped here, never kept.
    #[allow(clippy::needless_pass_by_value)]
    pub fn ingest(&mut self, scan: ScanReport) -> Result<PositionEstimate, PositioningError> {
        let now = self.live.now();
        let mut anchors = self.config.fixed_anchors.clone();
        anchors.extend(self.live.anchors(&scan.device));
        let model = self.config.model;
        let seed = self.config.seed ^ device_seed(&scan.device);
        let particles = self.config.particles;
        let map = Arc::clone(&self.map);
        let track = self
            .tracks
            .entry(scan.device.clone())
            .or_insert_with(DeviceTrack::new);
        scan.validate(now, track.last_scan)?;

        let dt = track.advance(&scan);
        let heard = hear(&scan.observations, &anchors, &mut track.smoothers, &model);

        // The floor heard most (ties: the larger total weight), else the previous one.
        let floor = choose_floor(&heard).or(track.floor);
        let Some(floor) = floor else {
            return Err(PositioningError::TooFewAnchors { have: 0, need: 3 });
        };
        if track.floor != Some(floor) {
            track.floor = Some(floor);
            track.window.clear();
            track.filter = None;
        }
        let level = map
            .floor(floor)
            .ok_or(LocationError::UnknownFloor { floor })?;

        let on_floor: Vec<&Heard> = heard.iter().filter(|h| h.anchor.floor == floor).collect();
        track.extend_window(scan.at, &on_floor);

        // Layer 3: trilateration (this scan, or the window), then the particle filter.
        let solver = Trilaterator::default();
        let previous_point = track.last.as_ref().map(|estimate| estimate.point);
        let trilaterated = if on_floor.len() >= 3 {
            trilaterate(&on_floor, &solver)
        } else {
            solve_window(track, &solver, level, previous_point)
        };
        let trilaterated = trilaterated.filter(|(point, _)| level.outline.contains(point));

        if track.filter.is_none() && trilaterated.is_some() {
            track.filter = Some(ParticleFilter::new(level, particles, seed));
        }
        let filtered = track.filter.as_mut().map(|filter| {
            filter.set_motion(scan.motion);
            filter.predict(dt);
            filter.update(&scan.observations, &anchors, &model);
            filter.estimate()
        });

        let chosen = choose(trilaterated, filtered);
        let Some((point, uncertainty_m, mut method)) = chosen else {
            return match &track.last {
                Some(last) => Ok(last.clone()),
                None => Err(PositioningError::TooFewAnchors {
                    have: track.window.len(),
                    need: 3,
                }),
            };
        };

        // Layer 4: the room (fingerprint when confident, else the room under the point).
        let fingerprint = self
            .config
            .fingerprints
            .classify(&scan.observations)
            .filter(|(place, confidence)| {
                *confidence >= FINGERPRINT_MIN_CONFIDENCE
                    && map.place(place).is_some_and(|found| found.floor == floor)
            });
        let proposed = match fingerprint {
            Some((place, _)) => {
                method = Method::Fingerprint;
                Some(place)
            }
            None => room_of(&map, floor, &point),
        };
        let Some(proposed) = proposed else {
            return Err(PositioningError::TooFewAnchors {
                have: track.window.len(),
                need: 3,
            });
        };
        if track.rooms.manual_active(scan.at) {
            method = Method::Manual;
        }
        let (place, decided_floor) = track
            .rooms
            .observe(proposed.clone(), floor, scan.at)
            .unwrap_or((proposed, floor));
        let estimate = PositionEstimate {
            floor: decided_floor,
            place,
            point,
            uncertainty_m,
            method,
        };
        track.last = Some(estimate.clone());
        Ok(estimate)
    }

    /// Records a manual pick so Bluetooth does not override it for 5 minutes.
    pub fn set_manual(&mut self, device: &DeviceId, place: PlaceId, floor: i32, at: DateTime<Utc>) {
        self.tracks
            .entry(device.clone())
            .or_insert_with(DeviceTrack::new)
            .rooms
            .set_manual(place, floor, at);
    }
}

impl DeviceTrack {
    /// Records the scan time and PDR motion; returns the time since the previous scan.
    fn advance(&mut self, scan: &ScanReport) -> Duration {
        let dt = self
            .last_scan
            .and_then(|last| scan.at.signed_duration_since(last).to_std().ok())
            .unwrap_or(FIRST_STEP);
        self.last_scan = Some(scan.at);
        if let Some(motion) = scan.motion {
            let length = f64::from(motion.steps) * motion.stride_m;
            if length.is_finite() && motion.heading_rad.is_finite() {
                self.displacement.0 += length * motion.heading_rad.cos();
                self.displacement.1 += length * motion.heading_rad.sin();
            }
        }
        dt
    }

    /// Drops virtual anchors older than the window, then adds this scan's.
    fn extend_window(&mut self, at: DateTime<Utc>, heard: &[&Heard]) {
        let window =
            chrono::TimeDelta::from_std(VIRTUAL_ANCHOR_WINDOW).unwrap_or(chrono::TimeDelta::zero());
        self.window
            .retain(|entry| at.signed_duration_since(entry.at) <= window);
        let (dx, dy) = self.displacement;
        for entry in heard {
            if let Ok(anchor) =
                Point2::new(entry.anchor.point.x() - dx, entry.anchor.point.y() - dy)
            {
                self.window.push(WindowEntry {
                    at,
                    anchor,
                    real_anchor: entry.anchor.point,
                    displacement: self.displacement,
                    metres: entry.metres,
                    weight: entry.weight,
                });
            }
        }
    }
}

/// Known anchors among the observations, with a distance and a weight (inverse variance);
/// RSSI is smoothed per anchor, then turned into metres by the path-loss model.
fn hear<'a>(
    observations: &[Observation],
    anchors: &'a [Anchor],
    smoothers: &mut SmootherBank,
    model: &PathLossModel,
) -> Vec<Heard<'a>> {
    let mut heard = Vec::new();
    for observation in observations {
        let (id, metres, sigma) = match observation {
            Observation::Range {
                anchor,
                metres,
                sigma_m,
            } => (anchor, *metres, *sigma_m),
            Observation::Rssi { anchor, dbm } => {
                let Some(found) = anchors.iter().find(|a| &a.id == anchor) else {
                    continue;
                };
                let smoothed = smoothers.push(anchor, *dbm);
                let metres = model.distance_m(smoothed, found.tx_power_dbm_1m);
                let sigma =
                    metres * std::f64::consts::LN_10 * model.sigma_db / (10.0 * model.exponent_n);
                (anchor, metres, sigma)
            }
        };
        if let Some(found) = anchors.iter().find(|a| &a.id == id) {
            let variance =
                sigma * sigma + found.spread_m * found.spread_m + RANGE_VARIANCE_FLOOR_M2;
            heard.push(Heard {
                anchor: found,
                metres,
                weight: 1.0 / variance,
            });
        }
    }
    heard
}

/// Single-shot trilateration of this scan's anchors.
fn trilaterate(heard: &[&Heard], solver: &Trilaterator) -> Option<(Point2, f64)> {
    let ranges: Vec<WeightedRange> = heard
        .iter()
        .map(|h| WeightedRange {
            anchor: h.anchor.point,
            metres: h.metres,
            weight: h.weight,
        })
        .collect();
    solver
        .solve(&ranges)
        .ok()
        .map(|estimate| (estimate.point, uncertainty_of(&ranges, estimate.residual_m)))
}

/// The more certain of the trilateration and the filter.
fn choose(
    trilaterated: Option<(Point2, f64)>,
    filtered: Option<FilterEstimate>,
) -> Option<(Point2, f64, Method)> {
    match (trilaterated, filtered) {
        (Some((_, uncertainty)), Some(filtered)) if filtered.uncertainty_m < uncertainty => Some((
            filtered.point,
            filtered.uncertainty_m,
            Method::ParticleFilter,
        )),
        (Some((point, uncertainty)), _) => Some((point, uncertainty, Method::Trilateration)),
        (None, Some(filtered)) => Some((
            filtered.point,
            filtered.uncertainty_m,
            Method::ParticleFilter,
        )),
        (None, None) => None,
    }
}

/// The floor with the most heard anchors (ties: the larger total weight).
fn choose_floor(heard: &[Heard]) -> Option<i32> {
    let mut per_floor: Vec<(i32, usize, f64)> = Vec::new();
    for entry in heard {
        match per_floor
            .iter_mut()
            .find(|(floor, _, _)| *floor == entry.anchor.floor)
        {
            Some((_, count, weight)) => {
                *count += 1;
                *weight += entry.weight;
            }
            None => per_floor.push((entry.anchor.floor, 1, entry.weight)),
        }
    }
    per_floor
        .into_iter()
        .max_by(|a, b| a.1.cmp(&b.1).then_with(|| a.2.total_cmp(&b.2)))
        .map(|(floor, _, _)| floor)
}

/// 2σ radius of a trilateration: residual and range noise together.
fn uncertainty_of(ranges: &[WeightedRange], residual_m: f64) -> f64 {
    let total: f64 = ranges.iter().map(|range| range.weight).sum();
    #[allow(clippy::cast_precision_loss)]
    let count = ranges.len() as f64;
    let variance = if total > 0.0 { count / total } else { 1.0 };
    2.0 * (residual_m * residual_m + variance).sqrt()
}

/// Solves the start point from the window's virtual anchors and moves it by the PDR
/// displacement; a mirror ambiguity is settled by the floor outline and then by the previous
/// estimate.
fn solve_window(
    track: &mut DeviceTrack,
    solver: &Trilaterator,
    level: &Floor,
    previous: Option<Point2>,
) -> Option<(Point2, f64)> {
    track.virtual_anchors.clear();
    for entry in &track.window {
        track
            .virtual_anchors
            .push(entry.real_anchor, entry.displacement, entry.metres);
    }
    let ranges: Vec<WeightedRange> = track
        .window
        .iter()
        .map(|entry| WeightedRange {
            anchor: entry.anchor,
            metres: entry.metres,
            weight: entry.weight,
        })
        .collect();
    let identifiability = track.virtual_anchors.identifiability();
    if matches!(identifiability, Identifiability::Underdetermined { .. }) {
        return None;
    }
    let estimate = solver.solve(&ranges).ok()?;
    let uncertainty = uncertainty_of(&ranges, estimate.residual_m);
    let (dx, dy) = track.displacement;
    let shift = |start: Point2| Point2::new(start.x() + dx, start.y() + dy).ok();
    let mut candidates = vec![estimate.point];
    if let Identifiability::Mirror { line } = identifiability
        && let Some(mirror) = reflect(estimate.point, &line)
    {
        candidates.push(mirror);
    }
    let mut points: Vec<Point2> = candidates.into_iter().filter_map(shift).collect();
    let inside: Vec<Point2> = points
        .iter()
        .copied()
        .filter(|point| level.outline.contains(point))
        .collect();
    if !inside.is_empty() {
        points = inside;
    }
    if let Some(previous) = previous {
        points.sort_by(|a, b| a.distance(&previous).total_cmp(&b.distance(&previous)));
    }
    points.first().map(|point| (*point, uncertainty))
}

/// Mirror image of `point` across `line`.
fn reflect(point: Point2, line: &Line2) -> Option<Point2> {
    let (ax, ay) = (line.a.x(), line.a.y());
    let (ux, uy) = (line.b.x() - ax, line.b.y() - ay);
    let length2 = ux * ux + uy * uy;
    if length2 <= 0.0 {
        return None;
    }
    let t = ((point.x() - ax) * ux + (point.y() - ay) * uy) / length2;
    let (fx, fy) = (ax + t * ux, ay + t * uy);
    Point2::new(2.0 * fx - point.x(), 2.0 * fy - point.y()).ok()
}

/// The room under the point, else the place of the floor with the nearest anchor point.
fn room_of(map: &ClinicMap, floor: i32, point: &Point2) -> Option<PlaceId> {
    if let Some(place) = map.place_at(floor, point) {
        return Some(place.id.clone());
    }
    map.places_on(floor)
        .into_iter()
        .min_by(|a, b| {
            a.anchor
                .distance(point)
                .total_cmp(&b.anchor.distance(point))
        })
        .map(|place| place.id.clone())
}

/// A per-device filter seed (FNV-1a of the device id).
fn device_seed(device: &DeviceId) -> u64 {
    device
        .as_str()
        .bytes()
        .fold(0xcbf2_9ce4_8422_2325, |hash, byte| {
            (hash ^ u64::from(byte)).wrapping_mul(0x0100_0000_01b3)
        })
}
