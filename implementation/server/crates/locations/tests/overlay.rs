//! Ruling R28: a base plan plus a `PlanOverlay` gives the effective plan.

use std::path::PathBuf;

use locations::{ClinicPlan, PlanOverlay, load_plan};
use serde_json::json;

type TestResult = Result<(), Box<dyn std::error::Error>>;

fn base() -> Result<ClinicPlan, Box<dyn std::error::Error>> {
    Ok(load_plan(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../seed/clinic_map.json"),
    )?)
}

fn overlay(value: serde_json::Value) -> Result<PlanOverlay, serde_json::Error> {
    serde_json::from_value(value)
}

#[test]
fn upsert_replaces_adds_and_remove_drops() -> TestResult {
    let base = base()?;
    let prop = json!({"id":"prop-1","floor":0,"kind":"counter","x":4.0,"y":3.6,"width":2.0,"depth":0.8,"solid":false});
    let new = json!({"id":"extra","floor":0,"kind":"plant","x":2.0,"y":2.0,"width":0.5,"depth":0.5,"solid":true});
    let modified = overlay(json!({
        "upsert": {"props": [prop, new]},
        "remove": {"props": ["prop-2", "no-such-prop"]}
    }))?;
    let effective = modified.apply(&base);
    assert_eq!(effective.props.len(), base.props.len() + 1 - 1);
    let replaced = effective.props.iter().find(|p| p.id == "prop-1");
    assert_eq!(replaced.map(|p| (p.x, p.solid)), Some((4.0, false)));
    assert!(effective.props.iter().any(|p| p.id == "extra"));
    assert!(!effective.props.iter().any(|p| p.id == "prop-2"));
    assert_eq!(modified.unknown_removals(&base), vec!["props/no-such-prop"]);
    assert!(effective.validate().is_ok());
    assert!(PlanOverlay::default().is_empty());
    assert_eq!(PlanOverlay::default().apply(&base), base);
    Ok(())
}
