//! Loading the invented seed data (`seed/robots.json`) into the database.
//!
//! No account is seeded (Task A7): an account exists only once a person enrolled with a
//! code, so the seed holds no user name, password or account key.
//!
//! Idempotent: running it twice leaves the same rows (Task 6). Every seed file carries
//! `"marque": "inventé"`; a file without it is refused.

use std::path::Path;

use domain::ports::{InventoryRepository as _, RobotRepository as _};
use domain::{ItemId, PlaceId, RobotRecord, StockLevel};
use serde::Deserialize;

use crate::inventory::SqliteInventoryRepository;
use crate::robots::SqliteRobotRepository;

use crate::error::StorageError;
use crate::pool::Database;

/// How many rows the seed files describe.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct SeedCounts {
    /// Robots in `robots.json`.
    pub robots: usize,
}

/// One robot of a seed file. `role` is accepted for `role_card` (the demo fleet's name).
#[derive(Debug, Deserialize)]
struct SeedRobot {
    id: String,
    name: String,
    #[serde(alias = "role")]
    role_card: String,
    #[serde(default = "yes")]
    simulated: bool,
    #[serde(default)]
    key_hash: String,
}

/// One stock item of a seed file (the `GET /inventory` wire names).
#[derive(Debug, Deserialize)]
struct SeedItem {
    id: String,
    label: String,
    place: String,
    count: u32,
    low_at: u32,
}

#[derive(Debug, Deserialize)]
struct SeedFile {
    marque: Option<String>,
    #[serde(default)]
    robots: Vec<SeedRobot>,
    #[serde(default)]
    items: Vec<SeedItem>,
}

fn yes() -> bool {
    true
}

fn seed_corrupt(reason: &str) -> StorageError {
    StorageError::Corrupt {
        table: "seed",
        reason: reason.to_owned(),
    }
}

/// Loads the robots of `seed_dir` (upsert by id, so a second run changes nothing).
///
/// # Errors
/// `StorageError::Corrupt` when a file is unreadable or lacks `"marque": "inventé"`;
/// `Unavailable`.
pub async fn load_seed(db: &Database, seed_dir: &Path) -> Result<SeedCounts, StorageError> {
    // `robots.json` when present, else the demo fleet (which also holds the stock items).
    let robots_file = seed_dir.join("robots.json");
    let path = if robots_file.exists() {
        robots_file
    } else {
        seed_dir.join("demo_fleet.json")
    };
    let text = std::fs::read_to_string(&path).map_err(|_| seed_corrupt("unreadable seed file"))?;
    let file: SeedFile =
        serde_json::from_str(&text).map_err(|_| seed_corrupt("seed file is not valid JSON"))?;
    if file.marque.as_deref() != Some("inventé") {
        return Err(seed_corrupt("seed file lacks \"marque\": \"inventé\""));
    }
    let robots = SqliteRobotRepository::new(db.clone());
    for robot in &file.robots {
        let record = RobotRecord {
            id: robot.id.parse().map_err(|_| seed_corrupt("robot id"))?,
            name: robot.name.clone(),
            role_card: robot.role_card.clone(),
            simulated: robot.simulated,
            key_hash: robot.key_hash.clone(),
        };
        robots
            .upsert(&record)
            .await
            .map_err(|_| StorageError::Unavailable)?;
    }
    // Items are inserted only when missing, so a second run keeps live counts.
    let inventory = SqliteInventoryRepository::new(db.clone());
    for item in &file.items {
        let id: ItemId = item.id.parse().map_err(|_| seed_corrupt("item id"))?;
        let place: PlaceId = item.place.parse().map_err(|_| seed_corrupt("item place"))?;
        if inventory
            .get(&id)
            .await
            .map_err(|_| StorageError::Unavailable)?
            .is_some()
        {
            continue;
        }
        let level = StockLevel {
            item: id,
            label: item.label.clone(),
            place,
            count: item.count,
            low_threshold: item.low_at,
            last_robot_count: None,
            last_robot_count_at: None,
            updated_at: chrono::Utc::now(),
        };
        inventory
            .upsert(&level)
            .await
            .map_err(|_| StorageError::Unavailable)?;
    }
    Ok(SeedCounts {
        robots: file.robots.len(),
    })
}
