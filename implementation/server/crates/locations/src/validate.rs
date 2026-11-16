//! Map validation rules used by `ClinicMap::new`.

use std::collections::HashSet;

use crate::error::LocationError;
use crate::model::{Floor, Place, PlaceLink, Zone};

/// Checks a map: unique ids, places and zones inside their floor outline, links between
/// known places with positive length.
///
/// # Errors
/// The first rule broken, as a `LocationError`.
pub fn validate(
    floors: &[Floor],
    places: &[Place],
    links: &[PlaceLink],
    zones: &[Zone],
) -> Result<(), LocationError> {
    let mut floor_levels = HashSet::new();
    for floor in floors {
        if !floor_levels.insert(floor.level) {
            return Err(LocationError::DuplicateId {
                kind: "floor",
                id: floor.level.to_string(),
            });
        }
    }
    let outline_of = |level: i32| {
        floors
            .iter()
            .find(|floor| floor.level == level)
            .map(|floor| &floor.outline)
    };

    let mut place_ids = HashSet::new();
    for place in places {
        if !place_ids.insert(&place.id) {
            return Err(LocationError::DuplicateId {
                kind: "place",
                id: place.id.to_string(),
            });
        }
        let outline =
            outline_of(place.floor).ok_or(LocationError::UnknownFloor { floor: place.floor })?;
        if !outline.contains_polygon(&place.footprint) {
            return Err(LocationError::PlaceOutsideFloor {
                place: place.id.clone(),
                floor: place.floor,
            });
        }
    }

    for link in links {
        let bad = |reason| LocationError::BadLink {
            from: link.from.clone(),
            to: link.to.clone(),
            reason,
        };
        if !place_ids.contains(&link.from) || !place_ids.contains(&link.to) {
            return Err(bad("a place it names is not on the map"));
        }
        if !(link.metres.is_finite() && link.metres > 0.0) {
            return Err(bad("its length must be a number greater than 0"));
        }
    }

    let mut zone_ids = HashSet::new();
    for zone in zones {
        if !zone_ids.insert(&zone.id) {
            return Err(LocationError::DuplicateId {
                kind: "zone",
                id: zone.id.to_string(),
            });
        }
        let outline =
            outline_of(zone.floor).ok_or(LocationError::UnknownFloor { floor: zone.floor })?;
        if !outline.contains_polygon(&zone.polygon) {
            return Err(LocationError::ZoneOutsideFloor {
                zone: zone.id.clone(),
                floor: zone.floor,
            });
        }
    }
    Ok(())
}
