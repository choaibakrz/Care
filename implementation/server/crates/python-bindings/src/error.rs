//! Bridge errors. Python exception text is truncated and contains no file system paths.

use std::time::Duration;

/// Bridge errors.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum BridgeError {
    /// No interpreter (feature off, or Python not found).
    #[error(
        "The Python interpreter is not available ({detail}); build with --features python and set the venv path."
    )]
    InterpreterUnavailable {
        /// Why.
        detail: String,
    },
    /// A module could not be imported.
    #[error(
        "Python module '{module}' could not be imported ({detail}); check repo_root and the venv."
    )]
    ImportFailed {
        /// Module.
        module: String,
        /// Why (no paths).
        detail: String,
    },
    /// Python raised.
    #[error("Python raised {exception_type}: {message}")]
    PythonRaised {
        /// Exception class.
        exception_type: String,
        /// Truncated message, paths removed.
        message: String,
    },
    /// The call took too long.
    #[error(
        "The Python call did not answer within {after:?}; the native dispatcher remains the reference."
    )]
    Timeout {
        /// Timeout.
        after: Duration,
    },
    /// A value could not be converted.
    #[error(
        "The Python result field '{field}' could not be converted; the bridge and the Python code disagree."
    )]
    Conversion {
        /// Field.
        field: String,
    },
    /// The interpreter thread's queue is full (Task A6: one interpreter thread, bounded queue).
    #[error("The brain is busy: {capacity} calls are already waiting. Try again in a moment.")]
    Busy {
        /// Queue capacity.
        capacity: usize,
    },
    /// The Python bricks cannot do this language pair yet (Task A6: `interprete.py` translates
    /// French to English today).
    #[error(
        "Translating from '{from}' to '{to}' is not supported by the brain yet; ask a human interpreter."
    )]
    UnsupportedLanguage {
        /// Source language.
        from: String,
        /// Target language.
        to: String,
    },
}
