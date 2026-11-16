//! Task 10b: stored clinic plans on an in-memory database.

use chrono::Utc;
use domain::ports::ClinicRepository as _;
use domain::{ClinicId, ClinicRecord, DomainError};
use storage::{Database, SqliteClinicRepository};

type TestResult = Result<(), Box<dyn std::error::Error>>;

fn record(id: &str, active: bool) -> Result<ClinicRecord, Box<dyn std::error::Error>> {
    Ok(ClinicRecord {
        id: id.parse()?,
        name: id.to_owned(),
        version: 1,
        active,
        updated_at: Utc::now(),
        plan_json: "{}".to_owned(),
        overlay_json: String::new(),
    })
}

#[tokio::test]
async fn create_update_activate_delete() -> TestResult {
    let db = Database::in_memory().await?;
    db.migrate().await?;
    let repo = SqliteClinicRepository::new(db);
    repo.insert(&record("seed", true)?).await?;
    repo.insert(&record("other", false)?).await?;
    assert!(matches!(
        repo.insert(&record("other", false)?).await,
        Err(DomainError::Conflict { .. })
    ));
    let other: ClinicId = "other".parse()?;
    let updated = repo
        .update(&other, 1, "renamed", "{\"a\":1}", "", Utc::now())
        .await?;
    assert_eq!((updated.version, updated.name.as_str()), (2, "renamed"));
    assert!(matches!(
        repo.update(&other, 1, "x", "{}", "", Utc::now()).await,
        Err(DomainError::VersionConflict { current: 2, .. })
    ));
    assert!(matches!(
        repo.delete(&"seed".parse()?).await,
        Err(DomainError::Conflict { .. })
    ));
    let now_active = repo.activate(&other, Utc::now()).await?;
    assert!(now_active.active);
    assert_eq!(repo.active().await?.map(|r| r.id), Some(other.clone()));
    assert_eq!(repo.list().await?.len(), 2);
    assert!(repo.delete(&"seed".parse()?).await?);
    Ok(())
}
