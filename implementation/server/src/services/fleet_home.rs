//! The fleet's home place: where robots go in an emergency, on `dock` and to recharge.
//!
//! Kept in a small JSON file (`{"place_id": "dock-a"}` or `{"place_id": null}`) next to the
//! data directory, so a restart keeps it. Until an admin sets it, the home is the first place
//! of the active plan that looks like a charging place (a dock, or a place whose id or name
//! says dock, charge or base).

use std::path::{Path, PathBuf};
use std::sync::{Mutex, PoisonError};

use domain::PlaceId;
use locations::{ClinicPlan, PlaceViewKind, PlanPlace};
use serde::{Deserialize, Serialize};

use crate::dto::FleetHomeView;
use crate::error::ApiError;

/// File name of the stored home place.
pub const FLEET_HOME_FILE: &str = "fleet_home.json";

/// What the file holds.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct Stored {
    place_id: Option<PlaceId>,
}

/// What an admin chose.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Choice {
    /// Nothing yet: the default home applies.
    Default,
    /// A place, or `None` when cleared.
    Chosen(Option<PlaceId>),
}

/// The home place, stored in a JSON file.
#[derive(Debug)]
pub struct FleetHome {
    path: PathBuf,
    chosen: Mutex<Choice>,
}

impl FleetHome {
    /// Reads the stored home from `path`; a missing or unreadable file means "not set yet".
    #[must_use]
    pub fn load(path: PathBuf) -> FleetHome {
        let chosen = std::fs::read_to_string(&path)
            .ok()
            .and_then(|text| serde_json::from_str::<Stored>(&text).ok())
            .map_or(Choice::Default, |stored| Choice::Chosen(stored.place_id));
        FleetHome {
            path,
            chosen: Mutex::new(chosen),
        }
    }

    /// The file a data directory keeps it in: next to the journal directory (`data/` when
    /// the journal directory has no parent).
    #[must_use]
    pub fn path_near(journal_dir: &Path) -> PathBuf {
        journal_dir
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
            .map_or_else(|| PathBuf::from("data"), Path::to_path_buf)
            .join(FLEET_HOME_FILE)
    }

    fn chosen(&self) -> Choice {
        self.chosen
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// The home place on `plan`, or `None` (cleared, or not on the plan).
    #[must_use]
    pub fn place<'a>(&self, plan: &'a ClinicPlan) -> Option<&'a PlanPlace> {
        match self.chosen() {
            Choice::Chosen(Some(id)) => plan.places.iter().find(|place| place.id == id),
            Choice::Chosen(None) => None,
            Choice::Default => default_home(plan),
        }
    }

    /// The view of the home place on `plan`.
    #[must_use]
    pub fn view(&self, plan: &ClinicPlan) -> FleetHomeView {
        match self.place(plan) {
            Some(place) => FleetHomeView {
                place_id: Some(place.id.clone()),
                label: Some(place.label.clone()),
                floor: Some(place.floor.to_string()),
            },
            None => FleetHomeView {
                place_id: None,
                label: None,
                floor: None,
            },
        }
    }

    /// Sets (or clears) the home place and stores it.
    ///
    /// # Errors
    /// 422 `invalid_field` when the place is not on `plan`; 503 when the file cannot be
    /// written.
    pub fn set(
        &self,
        plan: &ClinicPlan,
        place_id: Option<PlaceId>,
    ) -> Result<FleetHomeView, ApiError> {
        if let Some(id) = &place_id
            && !plan.places.iter().any(|place| &place.id == id)
        {
            return Err(ApiError::invalid_input(
                "place_id",
                &format!("'{id}' is not a place of the active clinic plan"),
            ));
        }
        let text = serde_json::to_string_pretty(&Stored {
            place_id: place_id.clone(),
        })
        .map_err(|_| ApiError::unavailable("fleet home store"))?;
        if let Some(parent) = self.path.parent()
            && !parent.as_os_str().is_empty()
        {
            std::fs::create_dir_all(parent).map_err(|error| {
                tracing::warn!(%error, "fleet home directory not created");
                ApiError::unavailable("fleet home store")
            })?;
        }
        std::fs::write(&self.path, text).map_err(|error| {
            tracing::warn!(%error, path = %self.path.display(), "fleet home not stored");
            ApiError::unavailable("fleet home store")
        })?;
        *self.chosen.lock().unwrap_or_else(PoisonError::into_inner) = Choice::Chosen(place_id);
        Ok(self.view(plan))
    }
}

/// The first dock of the plan, else the first place whose id or name says dock, charge or
/// base.
#[must_use]
pub fn default_home(plan: &ClinicPlan) -> Option<&PlanPlace> {
    plan.places
        .iter()
        .find(|place| place.kind == PlaceViewKind::Dock)
        .or_else(|| {
            plan.places.iter().find(|place| {
                let text = format!("{} {}", place.id, place.label).to_lowercase();
                ["dock", "charg", "base"]
                    .iter()
                    .any(|word| text.contains(word))
            })
        })
}
