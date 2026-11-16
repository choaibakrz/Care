//! Loading clinic plans (`seed/clinic_map.json`, format in `docs/map-format.md`).
//!
//! There is one description of a clinic (ruling R14): the `ClinicPlan` document. The model
//! (`ClinicMap`) is always derived from it by `ClinicPlan::validate`; there is no second file
//! format.

use std::path::Path;

use crate::error::LocationError;
use crate::plan::ClinicPlan;

/// Reads a clinic plan file (`seed/clinic_map.json`). Does not validate it: call
/// `ClinicPlan::validate`.
///
/// # Errors
/// `MapFile` when unreadable or not a plan (unknown key, wrong type; no file system path in
/// the message); `MapFile` also when `marque` is present and not `"inventé"`.
pub fn load_plan(path: &Path) -> Result<ClinicPlan, LocationError> {
    let text = std::fs::read_to_string(path).map_err(|_| LocationError::MapFile {
        reason: "the file could not be read".to_owned(),
    })?;
    parse_plan(&text)
}

/// Parses a clinic plan document.
///
/// # Errors
/// As [`load_plan`].
pub fn parse_plan(json: &str) -> Result<ClinicPlan, LocationError> {
    let plan: ClinicPlan = serde_json::from_str(json).map_err(|error| LocationError::MapFile {
        reason: format!("not a clinic plan: {error}"),
    })?;
    if plan
        .marque
        .as_deref()
        .is_some_and(|marque| marque != "inventé")
    {
        return Err(LocationError::MapFile {
            reason: "marque must be \"inventé\"".to_owned(),
        });
    }
    Ok(plan)
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::load_plan;

    #[test]
    fn seed_map_loads_and_has_two_floors() -> Result<(), Box<dyn std::error::Error>> {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../seed/clinic_map.json");
        let map = load_plan(&path)?.validate()?;
        assert_eq!(map.floors().len(), 2);
        assert!(!map.places().is_empty());
        Ok(())
    }
}
