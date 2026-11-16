//! SQLite repositories implementing the `domain` ports, the token store, the stock ledger and
//! the audit index. No `Display` of any error here contains sqlx text.

pub mod accounts;
pub mod audit_index;
pub mod clinics;
pub mod devices;
pub mod error;
pub mod events;
pub mod inventory;
pub mod ledger;
pub mod pool;
pub mod robots;
pub mod schedules;
pub mod seed;
mod sql;
pub mod system_mode;
pub mod tasks;
pub mod tokens;
pub mod zones;

pub use accounts::{SqliteAccountRepository, has_account_data};
pub use audit_index::SqliteAuditIndex;
pub use clinics::SqliteClinicRepository;
pub use devices::SqliteDeviceRepository;
pub use error::StorageError;
pub use inventory::SqliteInventoryRepository;
pub use ledger::SqliteLedger;
pub use pool::Database;
pub use robots::SqliteRobotRepository;
pub use schedules::SqliteScheduleRepository;
pub use seed::{SeedCounts, load_seed};
pub use system_mode::SqliteSystemModeStore;
pub use tasks::SqliteTaskRepository;
pub use tokens::{RawToken, SqliteTokenStore, TokenSubject};
pub use zones::SqliteZoneRepository;

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
