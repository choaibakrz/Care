//! The clinic map: floors, places, links, zones.

use domain::{PlaceId, ZoneId, ZoneKind};
use serde::Serialize;
use utoipa::ToSchema;

use crate::error::LocationError;
use crate::geometry::{Point2, Polygon, Wall};

/// One floor.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Floor {
    /// Level (0 ground).
    pub level: i32,
    /// Floor height above level 0, metres.
    pub elevation_m: f64,
    /// Ceiling height, metres.
    pub height_m: f64,
    /// Outline.
    pub outline: Polygon,
    /// Walls.
    pub walls: Vec<Wall>,
}

/// What a place is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PlaceKind {
    /// Patient or therapy room.
    Room,
    /// Corridor.
    Corridor,
    /// Storeroom (reserve, shelves).
    Storeroom,
    /// Nurse station.
    NurseStation,
    /// Robot dock.
    Dock,
    /// Lift.
    Lift,
    /// Anything else.
    Other,
}

/// A place.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Place {
    /// Id.
    pub id: PlaceId,
    /// Display name.
    pub name: String,
    /// Kind.
    pub kind: PlaceKind,
    /// Floor.
    pub floor: i32,
    /// Footprint, inside the floor outline.
    pub footprint: Polygon,
    /// Point used for robots and for tablets known only to the room.
    pub anchor: Point2,
}

/// A walkable link between two places.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct PlaceLink {
    /// From.
    pub from: PlaceId,
    /// To.
    pub to: PlaceId,
    /// Length, > 0.
    pub metres: f64,
}

/// A deaf or restricted zone.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Zone {
    /// Id.
    pub id: ZoneId,
    /// Kind.
    pub kind: ZoneKind,
    /// Floor.
    pub floor: i32,
    /// Outline.
    pub polygon: Polygon,
    /// Version, bumped on every change.
    pub version: u32,
}

/// How an obstacle blocks the route planner.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObstacleKind {
    /// Furniture: blocked inside and within the robot's clearance around it.
    Solid,
    /// A room robots never enter (a lift): blocked inside only.
    Closed,
}

/// Something robots drive around (Task A4): a solid prop or a closed room of the plan.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct Obstacle {
    /// The prop or room id it comes from.
    pub id: String,
    /// Floor.
    pub floor: i32,
    /// How it blocks.
    pub kind: ObstacleKind,
    /// Its area.
    pub area: Polygon,
}

/// Hash of the canonical map content, used as `ETag`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, ToSchema)]
#[serde(transparent)]
pub struct MapVersion(String);

impl MapVersion {
    /// The version string.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }

    /// A version named by a plan tag (`ActivePlan::tag`, `<clinic id>-v<version>`), for
    /// snapshots built where no model exists (the `--mock` services).
    #[must_use]
    pub fn from_tag(tag: impl Into<String>) -> MapVersion {
        MapVersion(tag.into())
    }
}

/// FNV-1a 64-bit hash: stable across Rust versions and platforms (unlike `DefaultHasher`).
/// For change detection (`ETag`, map version) only: it is not a security hash and must never
/// authenticate anything. `marque` is deliberately outside the hashed content.
fn fnv1a(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf2_9ce4_8422_2325, |hash, byte| {
        (hash ^ u64::from(*byte)).wrapping_mul(0x0100_0000_01b3)
    })
}

/// The version of a map: a hash of its canonical content (the JSON of every part, in
/// order), as 16 hex digits. Any change to a wall, place, link, zone or obstacle changes it.
pub(crate) fn content_version(
    floors: &[Floor],
    places: &[Place],
    links: &[PlaceLink],
    zones: &[Zone],
    obstacles: &[Obstacle],
) -> Result<MapVersion, LocationError> {
    let canonical =
        serde_json::to_vec(&(floors, places, links, zones, obstacles)).map_err(|error| {
            LocationError::MapFile {
                reason: format!("the map content could not be hashed: {error}"),
            }
        })?;
    Ok(MapVersion(format!("{:016x}", fnv1a(&canonical))))
}

/// The validated clinic map.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
pub struct ClinicMap {
    floors: Vec<Floor>,
    places: Vec<Place>,
    links: Vec<PlaceLink>,
    zones: Vec<Zone>,
    /// Solid props and closed rooms.
    obstacles: Vec<Obstacle>,
    version: MapVersion,
    /// Seed data marker: always `"inventé"` in this project.
    marque: String,
}

impl ClinicMap {
    /// Validates and builds a map. Crate-internal: a map is always derived from a plan by
    /// `ClinicPlan::validate` (ruling R14).
    ///
    /// # Errors
    /// `DuplicateId`, `PlaceOutsideFloor`, `BadLink` (unknown place, `metres <= 0`),
    /// `ZoneOutsideFloor`, `UnknownFloor`.
    pub(crate) fn new(
        floors: Vec<Floor>,
        places: Vec<Place>,
        links: Vec<PlaceLink>,
        zones: Vec<Zone>,
    ) -> Result<ClinicMap, LocationError> {
        crate::validate::validate(&floors, &places, &links, &zones)?;
        let version = content_version(&floors, &places, &links, &zones, &[])?;
        Ok(ClinicMap {
            floors,
            places,
            links,
            zones,
            obstacles: Vec::new(),
            version,
            marque: "inventé".to_owned(),
        })
    }
    /// The same map with obstacles for the route planner (Task A4), version re-hashed.
    ///
    /// # Errors
    /// `UnknownFloor` when an obstacle names a floor the map does not have.
    pub fn with_obstacles(mut self, obstacles: Vec<Obstacle>) -> Result<ClinicMap, LocationError> {
        for obstacle in &obstacles {
            if self.floor(obstacle.floor).is_none() {
                return Err(LocationError::UnknownFloor {
                    floor: obstacle.floor,
                });
            }
        }
        self.obstacles = obstacles;
        self.version = content_version(
            &self.floors,
            &self.places,
            &self.links,
            &self.zones,
            &self.obstacles,
        )?;
        Ok(self)
    }
    /// The same map with these deaf and restricted zones (from the zone store), version
    /// re-hashed. `ClinicPlan::validate` gives a map without zones.
    ///
    /// # Errors
    /// `ZoneOutsideFloor`, `UnknownFloor`, `DuplicateId`.
    pub fn with_zones(mut self, zones: Vec<Zone>) -> Result<ClinicMap, LocationError> {
        crate::validate::validate(&self.floors, &self.places, &self.links, &zones)?;
        self.zones = zones;
        self.version = content_version(
            &self.floors,
            &self.places,
            &self.links,
            &self.zones,
            &self.obstacles,
        )?;
        Ok(self)
    }
    /// Solid props and closed rooms.
    #[must_use]
    pub fn obstacles(&self) -> &[Obstacle] {
        &self.obstacles
    }
    /// One place.
    #[must_use]
    pub fn place(&self, id: &PlaceId) -> Option<&Place> {
        self.places.iter().find(|place| &place.id == id)
    }
    /// One floor.
    #[must_use]
    pub fn floor(&self, level: i32) -> Option<&Floor> {
        self.floors.iter().find(|floor| floor.level == level)
    }
    /// Every floor.
    #[must_use]
    pub fn floors(&self) -> &[Floor] {
        &self.floors
    }
    /// Every place.
    #[must_use]
    pub fn places(&self) -> &[Place] {
        &self.places
    }
    /// Places on a floor.
    #[must_use]
    pub fn places_on(&self, level: i32) -> Vec<&Place> {
        self.places
            .iter()
            .filter(|place| place.floor == level)
            .collect()
    }
    /// Every link.
    #[must_use]
    pub fn links(&self) -> &[PlaceLink] {
        &self.links
    }
    /// Every zone.
    #[must_use]
    pub fn zones(&self) -> &[Zone] {
        &self.zones
    }
    /// Zones on `level` containing the point.
    #[must_use]
    pub fn zones_containing(&self, level: i32, point: &Point2) -> Vec<&Zone> {
        self.zones
            .iter()
            .filter(|zone| zone.floor == level && zone.polygon.contains(point))
            .collect()
    }
    /// The place on `level` whose footprint contains the point.
    #[must_use]
    pub fn place_at(&self, level: i32, point: &Point2) -> Option<&Place> {
        self.places
            .iter()
            .find(|place| place.floor == level && place.footprint.contains(point))
    }
    /// Map version.
    #[must_use]
    pub fn version(&self) -> MapVersion {
        self.version.clone()
    }
    /// An `UnknownPlace` error with up to 10 suggestions from `floor`.
    #[must_use]
    pub fn unknown_place_error(&self, place: &PlaceId, floor: i32) -> LocationError {
        let suggestions = self
            .places_on(floor)
            .iter()
            .take(10)
            .map(|candidate| candidate.id.to_string())
            .collect::<Vec<_>>()
            .join(", ");
        LocationError::UnknownPlace {
            place: place.clone(),
            floor,
            suggestions,
        }
    }
}

#[cfg(test)]
mod tests {
    use domain::ZoneKind;

    use super::{ClinicMap, Floor, Place, PlaceKind, PlaceLink, Zone};
    use crate::error::LocationError;
    use crate::geometry::{Point2, Polygon, Wall};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Result<Polygon, LocationError> {
        Polygon::from_pairs(&[[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    }

    fn floor(level: i32, wall_x: f64) -> Result<Floor, LocationError> {
        Ok(Floor {
            level,
            elevation_m: f64::from(level) * 3.5,
            height_m: 3.0,
            outline: rect(0.0, 0.0, 20.0, 10.0)?,
            walls: vec![Wall {
                start: Point2::new(wall_x, 0.0)?,
                end: Point2::new(wall_x, 10.0)?,
                thickness_m: 0.2,
            }],
        })
    }

    fn place(id: &str, level: i32, x0: f64) -> Result<Place, Box<dyn std::error::Error>> {
        Ok(Place {
            id: id.parse()?,
            name: id.to_owned(),
            kind: PlaceKind::Room,
            floor: level,
            footprint: rect(x0, 1.0, x0 + 4.0, 5.0)?,
            anchor: Point2::new(x0 + 2.0, 3.0)?,
        })
    }

    fn link(from: &str, to: &str, metres: f64) -> Result<PlaceLink, Box<dyn std::error::Error>> {
        Ok(PlaceLink {
            from: from.parse()?,
            to: to.parse()?,
            metres,
        })
    }

    fn zone(id: &str, level: i32, x0: f64) -> Result<Zone, Box<dyn std::error::Error>> {
        Ok(Zone {
            id: id.parse()?,
            kind: ZoneKind::Deaf,
            floor: level,
            polygon: rect(x0, 1.0, x0 + 3.0, 4.0)?,
            version: 1,
        })
    }

    fn valid() -> Result<ClinicMap, Box<dyn std::error::Error>> {
        Ok(ClinicMap::new(
            vec![floor(0, 10.0)?, floor(1, 10.0)?],
            vec![
                place("room-a", 0, 1.0)?,
                place("room-b", 0, 8.0)?,
                place("room-c", 1, 1.0)?,
            ],
            vec![link("room-a", "room-b", 7.0)?],
            vec![zone("z-1", 0, 1.0)?, zone("z-2", 0, 2.0)?],
        )?)
    }

    #[test]
    fn accessors_answer_from_the_validated_content() -> TestResult {
        let map = valid()?;
        assert_eq!(map.floors().len(), 2);
        assert_eq!(map.places().len(), 3);
        assert_eq!(map.links().len(), 1);
        assert_eq!(map.zones().len(), 2);
        assert!(map.floor(1).is_some() && map.floor(2).is_none());
        assert_eq!(map.place(&"room-c".parse()?).map(|p| p.floor), Some(1));
        assert!(map.place(&"nowhere".parse()?).is_none());
        assert_eq!(map.places_on(0).len(), 2);
        assert_eq!(map.places_on(1).len(), 1);
        assert!(map.places_on(7).is_empty());
        let found = map
            .place_at(0, &Point2::new(9.0, 3.0)?)
            .map(|p| p.id.to_string());
        assert_eq!(found.as_deref(), Some("room-b"));
        assert!(map.place_at(1, &Point2::new(9.0, 3.0)?).is_none());
        assert_eq!(map.version().as_str().len(), 16);
        Ok(())
    }

    #[test]
    fn zones_containing_returns_overlapping_zones_of_the_floor_only() -> TestResult {
        let map = valid()?;
        assert_eq!(map.zones_containing(0, &Point2::new(3.0, 2.0)?).len(), 2);
        assert_eq!(map.zones_containing(0, &Point2::new(1.5, 2.0)?).len(), 1);
        assert!(map.zones_containing(1, &Point2::new(3.0, 2.0)?).is_empty());
        Ok(())
    }

    #[test]
    fn version_is_stable_and_changes_when_a_wall_moves() -> TestResult {
        let rebuild = |wall_x: f64| -> Result<ClinicMap, Box<dyn std::error::Error>> {
            Ok(ClinicMap::new(
                vec![floor(0, wall_x)?],
                vec![place("room-a", 0, 1.0)?],
                Vec::new(),
                Vec::new(),
            )?)
        };
        assert_eq!(rebuild(10.0)?.version(), rebuild(10.0)?.version());
        assert_ne!(rebuild(10.0)?.version(), rebuild(10.5)?.version());
        Ok(())
    }

    #[test]
    fn place_outside_floor_outline_is_rejected_naming_the_place() -> TestResult {
        let mut outside = place("room-x", 0, 1.0)?;
        outside.footprint = rect(18.0, 1.0, 24.0, 5.0)?;
        let err = ClinicMap::new(vec![floor(0, 10.0)?], vec![outside], Vec::new(), Vec::new())
            .err()
            .ok_or("accepted")?;
        assert_eq!(
            err,
            LocationError::PlaceOutsideFloor {
                place: "room-x".parse()?,
                floor: 0
            }
        );
        assert!(err.to_string().contains("room-x"), "{err}");
        Ok(())
    }

    #[test]
    fn place_on_a_missing_floor_is_rejected() -> TestResult {
        let err = ClinicMap::new(
            vec![floor(0, 10.0)?],
            vec![place("room-x", 3, 1.0)?],
            Vec::new(),
            Vec::new(),
        )
        .err()
        .ok_or("accepted")?;
        assert_eq!(err, LocationError::UnknownFloor { floor: 3 });
        Ok(())
    }

    #[test]
    fn link_to_unknown_place_or_with_bad_length_is_rejected() -> TestResult {
        let build = |links: Vec<PlaceLink>| -> Result<ClinicMap, Box<dyn std::error::Error>> {
            Ok(ClinicMap::new(
                vec![floor(0, 10.0)?],
                vec![place("room-a", 0, 1.0)?, place("room-b", 0, 8.0)?],
                links,
                Vec::new(),
            )?)
        };
        for links in [
            vec![link("room-a", "ghost", 3.0)?],
            vec![link("ghost", "room-b", 3.0)?],
        ] {
            let err = build(links).err().ok_or("accepted")?.to_string();
            assert!(err.contains("ghost"), "{err}");
            assert!(err.contains("not on the map"), "{err}");
        }
        for metres in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            let err = build(vec![link("room-a", "room-b", metres)?])
                .err()
                .ok_or("accepted")?
                .to_string();
            assert!(err.contains("greater than 0"), "{err}");
        }
        Ok(())
    }

    #[test]
    fn duplicate_ids_are_rejected() -> TestResult {
        let places = ClinicMap::new(
            vec![floor(0, 10.0)?],
            vec![place("room-a", 0, 1.0)?, place("room-a", 0, 8.0)?],
            Vec::new(),
            Vec::new(),
        )
        .err()
        .ok_or("accepted")?;
        assert!(
            matches!(places, LocationError::DuplicateId { kind: "place", .. }),
            "{places:?}"
        );
        let zones = ClinicMap::new(
            vec![floor(0, 10.0)?],
            Vec::new(),
            Vec::new(),
            vec![zone("z-1", 0, 1.0)?, zone("z-1", 0, 5.0)?],
        )
        .err()
        .ok_or("accepted")?;
        assert!(
            matches!(zones, LocationError::DuplicateId { kind: "zone", .. }),
            "{zones:?}"
        );
        let floors = ClinicMap::new(
            vec![floor(0, 10.0)?, floor(0, 11.0)?],
            Vec::new(),
            Vec::new(),
            Vec::new(),
        )
        .err()
        .ok_or("accepted")?;
        assert!(
            matches!(floors, LocationError::DuplicateId { kind: "floor", .. }),
            "{floors:?}"
        );
        Ok(())
    }

    #[test]
    fn zone_outside_its_floor_is_rejected() -> TestResult {
        let mut outside = zone("z-out", 0, 1.0)?;
        outside.polygon = rect(15.0, 1.0, 25.0, 4.0)?;
        let err = ClinicMap::new(vec![floor(0, 10.0)?], Vec::new(), Vec::new(), vec![outside])
            .err()
            .ok_or("accepted")?;
        assert_eq!(
            err,
            LocationError::ZoneOutsideFloor {
                zone: "z-out".parse()?,
                floor: 0
            }
        );
        let on_missing = ClinicMap::new(
            vec![floor(0, 10.0)?],
            Vec::new(),
            Vec::new(),
            vec![zone("z-up", 4, 1.0)?],
        )
        .err()
        .ok_or("accepted")?;
        assert_eq!(on_missing, LocationError::UnknownFloor { floor: 4 });
        Ok(())
    }
}
