//! Role cards and the fleet as seen by the dispatcher.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path as FsPath;

use domain::{PlaceId, RobotId, RobotStatus};
use serde::Deserialize;

use crate::error::OptimizationError;
use crate::graph::PlaceMask;

/// What a robot may do (port of `cartes_de_role/*.yaml`, loaded from `seed/role_cards.json`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct RoleCard {
    /// Card name.
    pub name: String,
    /// Places the robot may enter.
    pub permitted_places: BTreeSet<PlaceId>,
    /// Speed limit.
    pub max_speed_m_s: f64,
}

impl RoleCard {
    /// Loads every card, keyed by name.
    ///
    /// # Errors
    /// `RoleCards` when the file is unreadable, invalid, or has duplicate names.
    pub fn load_all(path: &FsPath) -> Result<BTreeMap<String, RoleCard>, OptimizationError> {
        let json = std::fs::read_to_string(path).map_err(|error| OptimizationError::RoleCards {
            reason: format!("the file cannot be read: {}", error.kind()),
        })?;
        RoleCard::parse_all(&json)
    }

    /// Parses the cards file content.
    ///
    /// # Errors
    /// As [`RoleCard::load_all`].
    pub fn parse_all(json: &str) -> Result<BTreeMap<String, RoleCard>, OptimizationError> {
        let file: CardsFile =
            serde_json::from_str(json).map_err(|error| OptimizationError::RoleCards {
                reason: format!("invalid JSON: {error}"),
            })?;
        if file.marque.trim().is_empty() {
            return Err(OptimizationError::RoleCards {
                reason: "`marque` is empty; seed data must say it is invented".to_owned(),
            });
        }
        let mut cards = BTreeMap::new();
        for card in file.cards {
            let name = card.name.clone();
            if cards.insert(name.clone(), card).is_some() {
                return Err(OptimizationError::RoleCards {
                    reason: format!("the card name '{name}' appears twice"),
                });
            }
        }
        Ok(cards)
    }

    /// The card as a routing mask.
    #[must_use]
    pub fn mask(&self) -> PlaceMask {
        PlaceMask::only(self.permitted_places.clone())
    }
}

/// The cards file: `{"marque": "inventé", "cards": [RoleCard, ...]}`.
#[derive(Debug, Deserialize)]
struct CardsFile {
    marque: String,
    cards: Vec<RoleCard>,
}

/// A robot as the dispatcher sees it.
#[derive(Debug, Clone, PartialEq)]
pub struct FleetMember {
    /// Id.
    pub id: RobotId,
    /// Name.
    pub name: String,
    /// Status.
    pub status: RobotStatus,
    /// Current place.
    pub at: PlaceId,
    /// Battery.
    pub battery_pct: f64,
    /// Role card.
    pub card: RoleCard,
    /// Simulated robots never do real deliveries.
    pub simulated: bool,
}
