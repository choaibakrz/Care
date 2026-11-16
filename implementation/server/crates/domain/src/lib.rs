//! Domain types shared by every crate of the clinic server.
//!
//! This crate depends on no other workspace crate. Lower crates that need a type defined
//! "above" them get it from here instead (ports pattern): `SeenItem`, `CommandName`,
//! `SubjectRef`, `ZoneKind`, `StockLedger` live here so `storage`, `audit` and
//! `optimization` never need `realtime` or each other.

pub mod account;
pub mod actor;
pub mod brain;
pub mod clock;
pub mod error;
pub mod ids;
pub mod incident;
pub mod monitor;
pub mod ports;
pub mod robot;
pub mod role;
pub mod system_mode;
pub mod task;
pub mod wire;

pub use account::{
    ACCOUNT_KEY_BYTES, AccountEnrolment, AccountId, AccountKey, AccountRecord, AccountTag,
    ENROLMENT_CODE_TTL, EnrolmentCode, EnrolmentRecord, KEY_DERIVATION_ALGORITHM,
    KEY_DERIVATION_ITERATIONS, MAX_PSEUDONYM_LEN, account_owner_label, check_pseudonym,
    derivation_password, derivation_salt,
};
pub use actor::{Actor, SubjectRef};
pub use brain::{
    BrainCallKind, BrainHealth, BrainReportRequest, BrainStatus, DraftFlag, DraftLine, LangCode,
    PrivateText, ReportDraft, ReportKind, ReportRequest, SimplifyLevel, SimplifyRequest,
    SimplifyResult, SourceKind, SourceRef, SummariseRequest, SummaryDraft, SummarySource,
    TextChecks, TranslateRequest, TranslateResult,
};
#[cfg(feature = "testing")]
pub use clock::FakeClock;
pub use clock::{Clock, SystemClock};
pub use error::{DomainError, StockError};
pub use ids::{
    ClinicId, DeviceId, ItemId, OwnerLabel, PlaceId, RobotId, ScheduleId, TaskId, UserId, ZoneId,
};
pub use monitor::{BlockSource, ClientStatus, RejectReason, SecurityAlert, SecurityAlertKind};
pub use ports::{
    ApplyOutcome, ClinicChange, ClinicRecord, DeviceRecord, ReconcileOutcome, Reservation,
    RobotFix, RobotRecord, RoundResult, ScheduleRecord, ShelfCount, StockAdjustReason, StockLedger,
    StockLevel, StoredSystemMode, SystemModeStore, ZoneKind, ZoneRecord, ZoneVersions,
};
pub use robot::{CommandName, RobotStatus, SeenItem};
pub use role::{Permission, Role};
pub use system_mode::{
    MAX_MODE_REASON_LEN, SystemMode, SystemModeState, check_mode_reason, clean_admin_text,
};
pub use task::{
    FailureReason, Page, Task, TaskDraft, TaskFilter, TaskKind, TaskParts, TaskState, TaskSummary,
};
pub use wire::{ErrorBody, ErrorDetail, ErrorProblem};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
