//! Cron schedules and the night restock round. Time zone defaults to `Europe/Zurich`.

pub mod cron;
pub mod error;
pub mod schedule;
pub mod service;

pub use cron::CronExpr;
pub use error::SchedulerError;
pub use schedule::{DEFAULT_GRACE, FiredJob, RunOutcome, Schedule, ScheduledJob};
pub use service::{SchedulerService, TaskCreator};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
