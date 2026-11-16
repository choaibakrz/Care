//! Bridge to the Python code (`briques/`): the dispatch parity oracle (Task 20) and, since
//! Task A6, the brain engine of the `clinic-brain` process (translate, simplify, summarise,
//! report; [`brain`]).
//!
//! pyo3 is an optional dependency behind the `python` feature, off by default: the workspace
//! builds and tests with no Python present. Without the feature, `PythonBridge::start`
//! returns `BridgeError::InterpreterUnavailable`. Task 20 sets this crate's `unsafe_code` lint
//! to `deny` (pyo3 macros expand to `unsafe`) and records why in `docs/pyo3-decision.md`.

pub mod brain;
pub mod bridge;
pub mod error;
pub mod patient_aid;
pub mod summary;
pub mod translate;

pub use brain::{
    BrainEngine, BrainEngineConfig, DEFAULT_QUEUE_CAPACITY, PythonBrain, UnavailableEngine,
    start_engine, start_engine_reporting,
};
pub use bridge::{PythonBridge, PythonConfig};
pub use error::BridgeError;
pub use patient_aid::{PatientAidConfig, Transcription};

#[cfg(test)]
mod tests {
    #[test]
    fn crate_compiles() -> Result<(), Box<dyn std::error::Error>> {
        let n: u32 = "1".parse()?;
        assert_eq!(n, 1);
        Ok(())
    }
}
