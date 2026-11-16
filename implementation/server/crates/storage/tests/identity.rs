//! Task 6: identity tables (accounts, devices, robots, tokens) and the seed loader. The
//! account table is Task A7's (pseudonymous accounts, filled by Task 8).
//!
//! Each test opens its own in-memory database and runs the migrations. They use
//! `#[tokio::test]` with `Database::in_memory()` rather than `#[sqlx::test]`: the latter needs
//! `DATABASE_URL` and a `migrations/` folder, which Task 6 creates; Task 6 may switch.

use std::path::Path;
use std::time::Duration;

use domain::ports::AccountRepository as _;
use domain::{AccountRecord, DomainError, Role};
use storage::{Database, SqliteAccountRepository, SqliteTokenStore, TokenSubject, load_seed};

type TestResult = Result<(), Box<dyn std::error::Error>>;

async fn database() -> Result<Database, Box<dyn std::error::Error>> {
    let db = Database::in_memory().await?;
    db.migrate().await?;
    Ok(db)
}

/// Every row of every table, as one text (`quote()` of each column).
async fn dump_database(db: &Database) -> Result<String, Box<dyn std::error::Error>> {
    let tables: Vec<String> = sqlx::query_scalar(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )
    .fetch_all(db.pool())
    .await?;
    let mut dump = String::new();
    for table in tables {
        let columns: Vec<String> = sqlx::query_scalar("SELECT name FROM pragma_table_info(?)")
            .bind(&table)
            .fetch_all(db.pool())
            .await?;
        if columns.is_empty() {
            continue;
        }
        let row = columns
            .iter()
            .map(|c| format!("quote(\"{c}\")"))
            .collect::<Vec<_>>()
            .join(" || '|' || ");
        // Audited: table and column names come from sqlite_master, not from input.
        let sql = sqlx::AssertSqlSafe(format!("SELECT {row} FROM \"{table}\""));
        let rows: Vec<String> = sqlx::query_scalar(sql).fetch_all(db.pool()).await?;
        dump.push('[');
        dump.push_str(&table);
        dump.push_str("]\n");
        dump.push_str(&rows.join("\n"));
        dump.push('\n');
    }
    Ok(dump)
}

fn nurse_subject() -> Result<TokenSubject, Box<dyn std::error::Error>> {
    Ok(TokenSubject::User {
        user_id: "u-nurse".parse()?,
        role: Role::Nurse,
        device_id: Some("tab-1".parse()?),
    })
}

#[tokio::test]
async fn token_roundtrip_returns_subject() -> TestResult {
    let store = SqliteTokenStore::new(database().await?);
    let subject = nurse_subject()?;
    let raw = store
        .issue(subject.clone(), Duration::from_hours(1))
        .await?;
    assert_eq!(store.resolve(raw.expose()).await?, Some(subject));
    Ok(())
}

#[tokio::test]
async fn raw_token_is_not_stored() -> TestResult {
    let db = database().await?;
    let store = SqliteTokenStore::new(db.clone());
    let raw = store
        .issue(nurse_subject()?, Duration::from_hours(1))
        .await?;
    let everything = dump_database(&db).await?;
    assert!(
        everything.contains("[tokens]"),
        "the dump missed the tokens table"
    );
    assert!(
        !everything.contains(raw.expose()),
        "the raw token is stored somewhere"
    );
    assert!(
        !format!("{raw:?}").contains(raw.expose()),
        "Debug prints the token"
    );
    Ok(())
}

#[tokio::test]
async fn expired_token_resolves_to_none() -> TestResult {
    let store = SqliteTokenStore::new(database().await?);
    let raw = store.issue(nurse_subject()?, Duration::ZERO).await?;
    tokio::time::sleep(Duration::from_millis(50)).await;
    assert_eq!(store.resolve(raw.expose()).await?, None);
    Ok(())
}

#[tokio::test]
async fn revoked_token_resolves_to_none() -> TestResult {
    let store = SqliteTokenStore::new(database().await?);
    let raw = store
        .issue(nurse_subject()?, Duration::from_hours(1))
        .await?;
    assert!(store.revoke(raw.expose()).await?);
    assert_eq!(store.resolve(raw.expose()).await?, None);
    Ok(())
}

/// Was `duplicate_user_id_returns_conflict_with_id_in_message` (A2): users became
/// pseudonymous accounts (Task A7). Same intent: a second insert of one id is refused and
/// the first record is kept.
#[tokio::test]
async fn duplicate_account_id_returns_account_exists() -> TestResult {
    let accounts = SqliteAccountRepository::new(database().await?);
    let account = AccountRecord {
        id: "3fa9c1"
            .repeat(11)
            .chars()
            .take(64)
            .collect::<String>()
            .parse()?,
        role: Role::Nurse,
        display_label: domain::OwnerLabel::new("Nurse 7")?,
        created_at: chrono::Utc::now(),
        disabled: false,
    };
    accounts.insert(&account).await?;
    let err = accounts
        .insert(&account)
        .await
        .err()
        .ok_or("a duplicate account was accepted")?;
    assert_eq!(err, DomainError::AccountExists);
    assert_eq!(accounts.find(&account.id).await?, Some(account));
    Ok(())
}

#[tokio::test]
async fn seed_is_idempotent_when_run_twice() -> TestResult {
    let db = database().await?;
    let seed_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../seed");
    let first = load_seed(&db, &seed_dir).await?;
    let second = load_seed(&db, &seed_dir).await?;
    assert_eq!(first, second);
    assert!(first.robots > 0, "{first:?}");
    // Task A7: no account is seeded (no user name or password exists in the seed).
    let accounts: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM accounts")
        .fetch_one(db.pool())
        .await?;
    let robots: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM robots")
        .fetch_one(db.pool())
        .await?;
    assert_eq!(accounts, 0);
    assert_eq!(usize::try_from(robots)?, first.robots);
    Ok(())
}
