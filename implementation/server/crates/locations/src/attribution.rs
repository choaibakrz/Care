//! Which room an incident belongs to (Task 11c).

use std::sync::Arc;

use domain::{PlaceId, SubjectRef};

use crate::live::LivePositions;

/// Finds the room of a robot or tablet from live positions.
#[derive(Clone)]
pub struct Attribution {
    live: Arc<LivePositions>,
}

impl Attribution {
    /// Over the live positions.
    #[must_use]
    pub fn new(live: Arc<LivePositions>) -> Attribution {
        Attribution { live }
    }

    /// A robot's current place (from its fix), or a tablet's room.
    #[must_use]
    pub fn place_of(&self, subject: &SubjectRef) -> Option<(PlaceId, i32)> {
        match subject {
            SubjectRef::Robot(robot) => {
                let fix = self.live.robot_fix(robot)?;
                let place = self.live.map().place_at(fix.floor, &fix.point)?;
                Some((place.id.clone(), fix.floor))
            }
            SubjectRef::Tablet(device) => self.live.tablet_place(device),
        }
    }

    /// The floor of a place of the map, `None` for an unknown place.
    #[must_use]
    pub fn floor_of_place(&self, place: &PlaceId) -> Option<i32> {
        self.live.map().place(place).map(|found| found.floor)
    }
}
