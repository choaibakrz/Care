//! The brain engine of the `clinic-brain` process (Task A6): translate, simplify, summarise,
//! report, over the existing Python bricks (`briques/clinique/interprete.py`,
//! `briques/clinique/resume.py`, `briques/b06_cerveau/branchements/cascade.py`), run on the
//! bridge's one interpreter thread.
//!
//! Two engines implement [`BrainEngine`]:
//! - [`PythonBrain`] (feature `python`, Task 20b): the real one;
//! - [`UnavailableEngine`]: every call answers `BridgeError::InterpreterUnavailable` with its
//!   reason, and the health is `down`. It is what a build without the `python` feature runs,
//!   and what [`start_engine`] falls back to when Python cannot start, so the brain process
//!   always starts and always answers explicitly.
//!
//! Calls are synchronous: they block until the interpreter thread answers or the bridge's
//! per-call timeout passes. The HTTP layer calls them from `spawn_blocking`.
//!
//! Privacy: requests and results are domain types whose texts are `PrivateText` (no text in
//! `Debug`); nothing here logs, stores or writes a text to a file.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use domain::{
    BrainHealth, BrainReportRequest, BrainStatus, ReportDraft, SimplifyRequest, SimplifyResult,
    SummariseRequest, SummaryDraft, TranslateRequest, TranslateResult,
};

use crate::bridge::{BrainAnswer, BrainCall, PythonBridge, PythonConfig};
use crate::error::BridgeError;
use crate::patient_aid::{
    MAX_AUDIO_BYTES, MAX_SPEAK_CHARS, PatientAidConfig, Transcription, is_supported,
};
use crate::summary::{keep_sourced_lines, simplification_is_safe};
use crate::translate::check_pair;

/// The interpreter thread answered a call with an answer of another kind.
fn wrong_answer() -> BridgeError {
    BridgeError::Conversion {
        field: "answer kind".to_owned(),
    }
}

/// Calls waiting for the interpreter thread before new calls are refused (`BridgeError::Busy`).
pub const DEFAULT_QUEUE_CAPACITY: usize = 8;

/// The cascade cuts an Apertus answer after this long and lets its rules-only step answer
/// (ruling R22; the delay `interprete.py` gives Apertus). Such a draft comes from the
/// fallback, and the health reports `degraded` while Apertus keeps failing. Below the call
/// timeout (`BRAIN_CALL_TIMEOUT_S`, which covers queue wait plus execution), so a call that
/// waited in the queue still gets a rules answer instead of a timeout. Applied by
/// [`PythonBrain`] (Task 20b), which sets the cascade's `Etage.delai_s` from it.
pub const APERTUS_CUTOFF: Duration = Duration::from_secs(15);

/// The fixed reason of an engine whose Python could not start (no venv, a brick that does not
/// import). Never the exception text or a path: those go to the brain's log only.
pub const PYTHON_FAILED_REASON: &str =
    "Python or a brick could not be loaded; see the clinic-brain log";
/// The fixed reason of a build without the `python` feature.
pub const WITHOUT_PYTHON_REASON: &str =
    "this clinic-brain was built without Python; rebuild it with --features python";

/// The four brain functions and the health report.
pub trait BrainEngine: Send + Sync {
    /// Translates with the fixed medical terms, then checks terms and numbers.
    ///
    /// # Errors
    /// `InterpreterUnavailable`, `UnsupportedLanguage`, `Busy`, `Timeout`, `PythonRaised`,
    /// `Conversion`.
    fn translate(&self, request: &TranslateRequest) -> Result<TranslateResult, BridgeError>;
    /// Rewrites in plain language, checked against the source; `simplified: false` with the
    /// source text when the check fails.
    ///
    /// # Errors
    /// As [`BrainEngine::translate`] (without `UnsupportedLanguage`).
    fn simplify(&self, request: &SimplifyRequest) -> Result<SimplifyResult, BridgeError>;
    /// Summarises the sources; every line names its source and passed the source check.
    ///
    /// # Errors
    /// As [`BrainEngine::simplify`].
    fn summarise(&self, request: &SummariseRequest) -> Result<SummaryDraft, BridgeError>;
    /// Writes a report from the facts the main server gathered.
    ///
    /// # Errors
    /// As [`BrainEngine::simplify`].
    fn report(&self, request: &BrainReportRequest) -> Result<ReportDraft, BridgeError>;
    /// Models loaded, queue length, `up`/`degraded`/`down`. Never fails.
    fn health(&self) -> BrainHealth;
    /// HACKATHON: audio passes through to the local brain for transcription, never stored.
    /// Transcribes a recording (webm, ogg, mp4, wav; at most 4 MiB and 60 s) with
    /// faster-whisper, language detected.
    ///
    /// # Errors
    /// `InterpreterUnavailable` (no speech model; the default for engines without one),
    /// `PythonRaised` with `AudioRefuse` (unreadable or too long), `Busy`, `Timeout`.
    fn transcribe(&self, audio: Vec<u8>) -> Result<Transcription, BridgeError> {
        drop(audio);
        Err(BridgeError::InterpreterUnavailable {
            detail: "no speech model is loaded".to_owned(),
        })
    }
    /// Reads `text` (1 to 2 000 characters) aloud in `lang` with a Piper voice: a 16-bit
    /// PCM WAV, built in memory, never stored.
    ///
    /// # Errors
    /// `InterpreterUnavailable` (no voice for `lang`; the default), `Busy`, `Timeout`.
    fn speak(&self, _text: &str, _lang: &str) -> Result<Vec<u8>, BridgeError> {
        Err(BridgeError::InterpreterUnavailable {
            detail: crate::bridge::NO_VOICE.to_owned(),
        })
    }
}

/// Settings of the engine.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrainEngineConfig {
    /// The interpreter (repository root, `.venv`, per-call timeout). `python.call_timeout`
    /// is `BRAIN_CALL_TIMEOUT_S` and covers the wait in the queue plus the execution.
    pub python: PythonConfig,
    /// Bounded queue of the interpreter thread.
    pub queue_capacity: usize,
    /// The patient helpers: `APERTUS_URL`, `APERTUS_TIMEOUT_S`, `WHISPER_MODEL`.
    pub patient: PatientAidConfig,
}

/// Starts the engine. Never fails: without the `python` feature, or when Python cannot
/// start, it returns an [`UnavailableEngine`] saying why.
#[must_use]
pub fn start_engine(config: BrainEngineConfig) -> Arc<dyn BrainEngine> {
    start_engine_reporting(config).0
}

/// [`start_engine`], plus why Python could not start (for the brain's log: this crate has
/// no logger). The engine's own reason stays the fixed phrase (no paths).
#[must_use]
pub fn start_engine_reporting(
    config: BrainEngineConfig,
) -> (Arc<dyn BrainEngine>, Option<BridgeError>) {
    #[cfg(feature = "python")]
    {
        match PythonBrain::start(config) {
            Ok(brain) => (Arc::new(brain), None),
            Err(error) => (
                Arc::new(UnavailableEngine::new(PYTHON_FAILED_REASON)),
                Some(error),
            ),
        }
    }
    #[cfg(not(feature = "python"))]
    {
        drop(config);
        (Arc::new(UnavailableEngine::without_python()), None)
    }
}

/// The engine of a brain that cannot run models: every call is refused with the reason.
/// The reason is a fixed phrase (`'static`), so no exception text or path can reach a client.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnavailableEngine {
    reason: &'static str,
}

impl UnavailableEngine {
    /// An engine refusing every call with a fixed `reason` ([`WITHOUT_PYTHON_REASON`],
    /// [`PYTHON_FAILED_REASON`]).
    #[must_use]
    pub fn new(reason: &'static str) -> UnavailableEngine {
        UnavailableEngine { reason }
    }

    /// The engine of a build without the `python` feature.
    #[must_use]
    pub fn without_python() -> UnavailableEngine {
        UnavailableEngine::new(WITHOUT_PYTHON_REASON)
    }

    /// Why calls are refused.
    #[must_use]
    pub fn reason(&self) -> &'static str {
        self.reason
    }

    fn refuse<T>(&self) -> Result<T, BridgeError> {
        Err(BridgeError::InterpreterUnavailable {
            detail: self.reason.to_owned(),
        })
    }
}

impl BrainEngine for UnavailableEngine {
    fn translate(&self, _request: &TranslateRequest) -> Result<TranslateResult, BridgeError> {
        self.refuse()
    }
    fn simplify(&self, _request: &SimplifyRequest) -> Result<SimplifyResult, BridgeError> {
        self.refuse()
    }
    fn summarise(&self, _request: &SummariseRequest) -> Result<SummaryDraft, BridgeError> {
        self.refuse()
    }
    fn report(&self, _request: &BrainReportRequest) -> Result<ReportDraft, BridgeError> {
        self.refuse()
    }
    fn health(&self) -> BrainHealth {
        BrainHealth::down(self.reason.to_owned())
    }
    fn transcribe(&self, audio: Vec<u8>) -> Result<Transcription, BridgeError> {
        drop(audio);
        self.refuse()
    }
    fn speak(&self, _text: &str, _lang: &str) -> Result<Vec<u8>, BridgeError> {
        self.refuse()
    }
}

/// The real engine (Task 20b): the bridge's interpreter thread runs the Python bricks.
///
/// - transcribe (hackathon): `aide_patient.transcrire`, faster-whisper on this computer
///   (`WHISPER_MODEL`, cpu, int8, VAD, language detected), audio in memory only.
/// - translate (hackathon): `aide_patient.traduire`, Apertus over its OpenAI-compatible
///   endpoint, any pair of `crate::patient_aid::LANGUAGES`, `from` optional (detected); the
///   same language returns the text unchanged. `checks.numbers_ok` says whether every digit
///   run of the source is in the translation (no fixed-terms list for these pairs).
/// - simplify (hackathon): `aide_patient.simplifier` (plain words, same facts and numbers,
///   no advice), then `crate::summary::simplification_is_safe`; a failed check returns the
///   source text with `simplified: false`.
/// - summarise and report: still the rules-only step (one line per source).
/// - Apertus down: translate and simplify are `InterpreterUnavailable` (503
///   `brain_unavailable`); the health is `degraded` (one model missing) or `down` (both),
///   measured at most every [`HEALTH_CACHE`].
pub struct PythonBrain {
    bridge: PythonBridge,
    queue_capacity: usize,
    whisper_model: String,
    /// The last health measured and when; asked again after [`HEALTH_CACHE`].
    last_health: Mutex<Option<(Instant, BrainHealth)>>,
}

/// How long a measured health is reused (the main server probes every 5 s; asking Python
/// each time would queue behind transcriptions).
pub const HEALTH_CACHE: Duration = Duration::from_secs(30);

impl PythonBrain {
    /// Starts the interpreter thread, imports the bricks and loads the fixed terms.
    ///
    /// # Errors
    /// `InterpreterUnavailable` (always without the `python` feature), `ImportFailed`.
    pub fn start(config: BrainEngineConfig) -> Result<PythonBrain, BridgeError> {
        let bridge = PythonBridge::start(config.python)?;
        let whisper_model = config.patient.whisper_model.clone();
        match bridge.call_brain(BrainCall::Configure(config.patient), config.queue_capacity)? {
            BrainAnswer::Configured => {}
            _ => return Err(wrong_answer()),
        }
        Ok(PythonBrain {
            bridge,
            queue_capacity: config.queue_capacity,
            whisper_model,
            last_health: Mutex::new(None),
        })
    }

    /// Asks Python whether whisper is present and Apertus answers.
    fn measure_health(&self) -> BrainHealth {
        let (whisper, apertus, voices) = match self
            .bridge
            .call_brain(BrainCall::Health, self.queue_capacity)
        {
            Ok(BrainAnswer::Health {
                whisper,
                apertus,
                voices,
            }) => (whisper, apertus, voices),
            _ => (false, false, Vec::new()),
        };
        let mut models = Vec::new();
        if whisper {
            models.push(format!("faster-whisper-{}", self.whisper_model));
        }
        if apertus {
            models.push("apertus".to_owned());
        }
        models.extend(voices.iter().map(|lang| format!("piper:{lang}")));
        let (status, detail) = match (whisper, apertus) {
            (true, true) => (BrainStatus::Up, None),
            (true, false) => (
                BrainStatus::Degraded,
                Some("listening works; translation is not available (Apertus is not reachable)"),
            ),
            (false, true) => (
                BrainStatus::Degraded,
                Some("translation works; listening is not available (no speech model)"),
            ),
            (false, false) => (
                BrainStatus::Down,
                Some("no speech model and Apertus is not reachable"),
            ),
        };
        BrainHealth {
            status,
            models,
            queue: 0,
            detail: detail.map(str::to_owned),
        }
    }
}

impl BrainEngine for PythonBrain {
    fn translate(&self, request: &TranslateRequest) -> Result<TranslateResult, BridgeError> {
        check_pair(request.from.as_ref(), &request.to)?;
        match self
            .bridge
            .call_brain(BrainCall::Translate(request.clone()), self.queue_capacity)?
        {
            BrainAnswer::Translated(result) => Ok(result),
            _ => Err(wrong_answer()),
        }
    }
    fn simplify(&self, request: &SimplifyRequest) -> Result<SimplifyResult, BridgeError> {
        match self
            .bridge
            .call_brain(BrainCall::Simplify(request.clone()), self.queue_capacity)?
        {
            BrainAnswer::Simplified(result) => {
                if result.simplified
                    && !simplification_is_safe(request.text.expose(), result.text.expose())
                {
                    return Ok(SimplifyResult {
                        text: request.text.clone(),
                        simplified: false,
                        ..result
                    });
                }
                Ok(result)
            }
            _ => Err(wrong_answer()),
        }
    }
    fn summarise(&self, request: &SummariseRequest) -> Result<SummaryDraft, BridgeError> {
        match self
            .bridge
            .call_brain(BrainCall::Summarise(request.clone()), self.queue_capacity)?
        {
            BrainAnswer::Summarised(draft) => {
                let (lines, dropped) = keep_sourced_lines(draft.lines, &request.sources);
                Ok(SummaryDraft {
                    lines,
                    dropped: draft.dropped.saturating_add(dropped),
                    ..draft
                })
            }
            _ => Err(wrong_answer()),
        }
    }
    fn report(&self, request: &BrainReportRequest) -> Result<ReportDraft, BridgeError> {
        match self
            .bridge
            .call_brain(BrainCall::Report(request.clone()), self.queue_capacity)?
        {
            BrainAnswer::Reported(draft) => {
                let (lines, dropped) = keep_sourced_lines(draft.lines, &request.facts);
                Ok(ReportDraft {
                    lines,
                    dropped: draft.dropped.saturating_add(dropped),
                    ..draft
                })
            }
            _ => Err(wrong_answer()),
        }
    }
    fn health(&self) -> BrainHealth {
        let queue = self.bridge.queue_len();
        let cached = self.last_health.lock().ok().and_then(|last| last.clone());
        let health = match cached {
            // Fresh enough, or the thread is busy (a measure would wait behind the calls).
            Some((at, health)) if at.elapsed() < HEALTH_CACHE || queue > 0 => health,
            _ => {
                let health = self.measure_health();
                if let Ok(mut last) = self.last_health.lock() {
                    *last = Some((Instant::now(), health.clone()));
                }
                health
            }
        };
        BrainHealth {
            queue: u32::try_from(queue).unwrap_or(u32::MAX),
            ..health
        }
    }
    fn transcribe(&self, audio: Vec<u8>) -> Result<Transcription, BridgeError> {
        if audio.is_empty() || audio.len() > MAX_AUDIO_BYTES {
            return Err(BridgeError::PythonRaised {
                exception_type: "AudioRefuse".to_owned(),
                message: "the recording is empty or larger than 4 MiB".to_owned(),
            });
        }
        match self
            .bridge
            .call_brain(BrainCall::Transcribe(audio), self.queue_capacity)?
        {
            BrainAnswer::Transcribed(heard) => Ok(heard),
            _ => Err(wrong_answer()),
        }
    }
    fn speak(&self, text: &str, lang: &str) -> Result<Vec<u8>, BridgeError> {
        let length = text.trim().chars().count();
        if length == 0 || length > MAX_SPEAK_CHARS || !is_supported(lang) {
            return Err(BridgeError::InterpreterUnavailable {
                detail: crate::bridge::NO_VOICE.to_owned(),
            });
        }
        let call = BrainCall::Speak {
            text: text.to_owned(),
            lang: lang.split('-').next().unwrap_or_default().to_owned(),
        };
        match self.bridge.call_brain(call, self.queue_capacity)? {
            BrainAnswer::Spoken(wav) => Ok(wav),
            _ => Err(wrong_answer()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{BrainEngine as _, UnavailableEngine};
    use domain::BrainStatus;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn unavailable_engine_refuses_every_call_with_its_reason() -> TestResult {
        let engine = UnavailableEngine::new(super::PYTHON_FAILED_REASON);
        let request = domain::TranslateRequest {
            text: domain::PrivateText::new("Bonjour".to_owned())?,
            from: None,
            to: "en".parse()?,
        };
        let error = engine
            .translate(&request)
            .err()
            .ok_or("expected a refusal")?;
        assert!(
            error.to_string().contains("see the clinic-brain log"),
            "{error}"
        );
        let health = engine.health();
        assert_eq!(health.status, BrainStatus::Down);
        assert_eq!(health.detail.as_deref(), Some(super::PYTHON_FAILED_REASON));
        assert!(health.models.is_empty());
        Ok(())
    }

    #[cfg(not(feature = "python"))]
    #[test]
    fn engine_without_python_is_unavailable_and_says_how_to_fix_it() {
        let engine = super::start_engine(super::BrainEngineConfig {
            python: crate::PythonConfig {
                repo_root: std::path::PathBuf::from("."),
                venv: None,
                call_timeout: std::time::Duration::from_secs(1),
            },
            queue_capacity: super::DEFAULT_QUEUE_CAPACITY,
            patient: crate::patient_aid::PatientAidConfig::default(),
        });
        let health = engine.health();
        assert_eq!(health.status, BrainStatus::Down);
        assert!(
            health
                .detail
                .as_deref()
                .is_some_and(|d| d.contains("--features python")),
            "{health:?}"
        );
    }
}
