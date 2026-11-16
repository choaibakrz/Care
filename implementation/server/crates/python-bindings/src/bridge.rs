//! One dedicated OS thread owns the interpreter (so the GIL never blocks the async runtime);
//! requests arrive over a channel.

use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, mpsc};
use std::thread::JoinHandle;
use std::time::Duration;

use domain::{
    BrainReportRequest, DraftFlag, DraftLine, ReportDraft, SimplifyRequest, SimplifyResult,
    SummariseRequest, SummaryDraft, SummarySource, TranslateRequest, TranslateResult,
};
use optimization::{Decision, DispatchOracle, DispatchRequest, FleetMember, OptimizationError};

use crate::error::BridgeError;
use crate::patient_aid::{PatientAidConfig, Transcription};

/// Bridge settings.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PythonConfig {
    /// Repository root (holds `briques/`).
    pub repo_root: PathBuf,
    /// Virtual environment, if any.
    pub venv: Option<PathBuf>,
    /// Per-call timeout.
    pub call_timeout: Duration,
}

/// A request to the interpreter thread.
#[allow(
    dead_code,
    reason = "the Python dispatch oracle and translation are not wired yet"
)]
enum BridgeRequest {
    Choose {
        request: DispatchRequest,
        fleet: Vec<FleetMember>,
        reply: mpsc::Sender<Result<Decision, BridgeError>>,
    },
    /// A brain call (Task A6), answered on the same interpreter thread.
    Brain {
        call: BrainCall,
        reply: mpsc::Sender<Result<BrainAnswer, BridgeError>>,
    },
    Shutdown,
}

/// A brain call for the interpreter thread (Task 20b). The texts stay in memory: they are
/// handed to Python as `str` objects and never written to a file.
#[allow(
    dead_code,
    reason = "the Python dispatch oracle and translation are not wired yet"
)]
pub(crate) enum BrainCall {
    /// `interprete.py`, two-step path.
    Translate(TranslateRequest),
    /// The cascade with the plain-language instruction.
    Simplify(SimplifyRequest),
    /// `resume.py`'s checks over the cascade's lines.
    Summarise(SummariseRequest),
    /// A report over the facts.
    Report(BrainReportRequest),
    /// HACKATHON: audio passes through to the local brain for transcription, never stored.
    /// `aide_patient.transcrire` on the raw bytes (webm, ogg, mp4, wav).
    Transcribe(Vec<u8>),
    /// `aide_patient.parler`: the text read aloud with a Piper voice (sherpa-onnx), a 16-bit
    /// PCM WAV built in memory. HACKATHON: the audio is never stored or logged.
    Speak {
        /// The text to read (1 to 2 000 characters).
        text: String,
        /// Its language (ISO 639-1).
        lang: String,
    },
    /// `aide_patient.etat`: speech model present? Apertus reachable?
    Health,
    /// `aide_patient.configurer`, once at start.
    Configure(PatientAidConfig),
}

/// The interpreter thread's answer to a [`BrainCall`], of the same kind.
#[allow(
    dead_code,
    reason = "the Python dispatch oracle and translation are not wired yet"
)]
pub(crate) enum BrainAnswer {
    /// To `Translate`.
    Translated(TranslateResult),
    /// To `Simplify`.
    Simplified(SimplifyResult),
    /// To `Summarise`.
    Summarised(SummaryDraft),
    /// To `Report`.
    Reported(ReportDraft),
    /// To `Transcribe`.
    Transcribed(Transcription),
    /// To `Speak`: the WAV bytes.
    Spoken(Vec<u8>),
    /// To `Health`.
    Health {
        /// The faster-whisper model is loaded or in the local cache.
        whisper: bool,
        /// Apertus answers at `APERTUS_URL`.
        apertus: bool,
        /// The languages with a Piper voice ready.
        voices: Vec<String>,
    },
    /// To `Configure`.
    Configured,
}

/// The bridge.
pub struct PythonBridge {
    requests: mpsc::Sender<BridgeRequest>,
    worker: Option<JoinHandle<()>>,
    call_timeout: Duration,
    /// Calls queued or running on the interpreter thread.
    waiting: Arc<AtomicUsize>,
}

/// The fixed reason of a speak call without a voice for its language.
pub const NO_VOICE: &str = "no voice for this language";

/// The module imported at start to check that the bricks are reachable.
pub const DISPATCH_MODULE: &str = "briques.clinique.repartiteur";

impl PythonBridge {
    /// Starts the interpreter thread and imports `briques.clinique.repartiteur`.
    ///
    /// # Errors
    /// `InterpreterUnavailable` (always without the `python` feature); `ImportFailed`.
    pub fn start(config: PythonConfig) -> Result<PythonBridge, BridgeError> {
        #[cfg(feature = "python")]
        {
            let (requests, inbox) = mpsc::channel::<BridgeRequest>();
            let (ready_tx, ready_rx) = mpsc::channel::<Result<(), BridgeError>>();
            let call_timeout = config.call_timeout;
            let worker = std::thread::Builder::new()
                .name("python-bridge".to_owned())
                .spawn(move || {
                    let ready = python::initialise(&config);
                    let ok = ready.is_ok();
                    // The starter may have given up waiting; nothing to do then.
                    let _sent = ready_tx.send(ready);
                    if ok {
                        serve(&inbox);
                    }
                })
                .map_err(|error| BridgeError::InterpreterUnavailable {
                    detail: format!("the interpreter thread could not start ({})", error.kind()),
                })?;
            let ready = ready_rx
                .recv()
                .map_err(|_| BridgeError::InterpreterUnavailable {
                    detail: "the interpreter thread stopped while starting".to_owned(),
                })?;
            ready?;
            Ok(PythonBridge {
                requests,
                worker: Some(worker),
                call_timeout,
                waiting: Arc::new(AtomicUsize::new(0)),
            })
        }
        #[cfg(not(feature = "python"))]
        {
            drop(config);
            Err(BridgeError::InterpreterUnavailable {
                detail: "built without the python feature".to_owned(),
            })
        }
    }

    /// Queues `request` (built around `reply`) and waits for the answer on `answers`.
    fn ask<T>(
        &self,
        request: BridgeRequest,
        answers: &mpsc::Receiver<Result<T, BridgeError>>,
    ) -> Result<T, BridgeError> {
        self.requests.send(request).map_err(|_| thread_stopped())?;
        match answers.recv_timeout(self.call_timeout) {
            Ok(answer) => answer,
            Err(mpsc::RecvTimeoutError::Timeout) => Err(BridgeError::Timeout {
                after: self.call_timeout,
            }),
            Err(mpsc::RecvTimeoutError::Disconnected) => Err(thread_stopped()),
        }
    }
}

impl PythonBridge {
    /// Sends a brain call to the interpreter thread and waits for its answer.
    /// `call_timeout` (`BRAIN_CALL_TIMEOUT_S`) counts from the moment the call is queued: it
    /// covers the wait in the queue plus the execution (ruling R22).
    ///
    /// # Errors
    /// `Busy` when `queue_capacity` calls already wait; `Timeout` after `call_timeout`;
    /// `PythonRaised`, `Conversion` from the thread.
    pub(crate) fn call_brain(
        &self,
        call: BrainCall,
        queue_capacity: usize,
    ) -> Result<BrainAnswer, BridgeError> {
        let _slot = QueueSlot::take(&self.waiting, queue_capacity)?;
        let (reply, answers) = mpsc::channel();
        self.ask(BridgeRequest::Brain { call, reply }, &answers)
    }

    /// Calls waiting for the interpreter thread right now.
    pub(crate) fn queue_len(&self) -> usize {
        self.waiting.load(Ordering::SeqCst)
    }
}

impl Drop for PythonBridge {
    fn drop(&mut self) {
        // The thread may already be gone; then there is nothing to stop.
        let _sent = self.requests.send(BridgeRequest::Shutdown);
        if let Some(worker) = self.worker.take() {
            // A panicked worker has nothing left to clean up.
            let _joined = worker.join();
        }
    }
}

impl DispatchOracle for PythonBridge {
    fn choose(
        &self,
        request: &DispatchRequest,
        fleet: &[FleetMember],
    ) -> Result<Decision, OptimizationError> {
        let (reply, answers) = mpsc::channel();
        let message = BridgeRequest::Choose {
            request: request.clone(),
            fleet: fleet.to_vec(),
            reply,
        };
        self.ask(message, &answers)
            .map_err(|error| OptimizationError::Oracle {
                detail: error.to_string(),
            })
    }
}

/// A place in the interpreter thread's queue, given back when the call ends.
struct QueueSlot<'a> {
    waiting: &'a AtomicUsize,
}

impl<'a> QueueSlot<'a> {
    fn take(waiting: &'a AtomicUsize, capacity: usize) -> Result<QueueSlot<'a>, BridgeError> {
        let before = waiting.fetch_add(1, Ordering::SeqCst);
        if before >= capacity {
            waiting.fetch_sub(1, Ordering::SeqCst);
            return Err(BridgeError::Busy { capacity });
        }
        Ok(QueueSlot { waiting })
    }
}

impl Drop for QueueSlot<'_> {
    fn drop(&mut self) {
        self.waiting.fetch_sub(1, Ordering::SeqCst);
    }
}

fn thread_stopped() -> BridgeError {
    BridgeError::InterpreterUnavailable {
        detail: "the interpreter thread stopped".to_owned(),
    }
}

/// The interpreter thread's loop: answers requests in order until `Shutdown`.
#[cfg_attr(
    not(feature = "python"),
    allow(
        dead_code,
        reason = "only the python build starts the interpreter thread"
    )
)]
fn serve(inbox: &mpsc::Receiver<BridgeRequest>) {
    while let Ok(request) = inbox.recv() {
        match request {
            BridgeRequest::Choose { reply, .. } => {
                // The caller may have timed out; the answer is then dropped.
                let _sent = reply.send(Err(BridgeError::PythonRaised {
                    exception_type: "NotImplementedError".to_owned(),
                    message: "the Python dispatch oracle is not wired yet".to_owned(),
                }));
            }
            BridgeRequest::Brain { call, reply } => {
                let _sent = reply.send(answer(call));
            }
            BridgeRequest::Shutdown => break,
        }
    }
}

/// One brain call on the interpreter thread: the patient helpers in Python with the
/// `python` feature, the rules-only step otherwise.
#[cfg_attr(
    not(feature = "python"),
    allow(
        dead_code,
        reason = "only the python build starts the interpreter thread"
    )
)]
fn answer(call: BrainCall) -> Result<BrainAnswer, BridgeError> {
    #[cfg(feature = "python")]
    {
        python::brain(call)
    }
    #[cfg(not(feature = "python"))]
    {
        rules_only(call)
    }
}

/// The cascade's rules-only step, done on the interpreter thread: no model is loaded, so a
/// simplification keeps the source, a summary or report copies one line per source, and a
/// translation is refused (a rule cannot translate).
#[cfg_attr(
    not(feature = "python"),
    allow(
        dead_code,
        reason = "only the python build starts the interpreter thread"
    )
)]
pub(crate) fn rules_only(call: BrainCall) -> Result<BrainAnswer, BridgeError> {
    let copy = |sources: &[SummarySource]| -> Vec<DraftLine> {
        sources
            .iter()
            .map(|source| DraftLine {
                text: source.text.clone(),
                source: source.id.clone(),
            })
            .collect()
    };
    match call {
        BrainCall::Transcribe(_) => Err(BridgeError::InterpreterUnavailable {
            detail: "no speech model is loaded".to_owned(),
        }),
        BrainCall::Speak { .. } => Err(BridgeError::InterpreterUnavailable {
            detail: NO_VOICE.to_owned(),
        }),
        BrainCall::Health => Ok(BrainAnswer::Health {
            whisper: false,
            apertus: false,
            voices: Vec::new(),
        }),
        BrainCall::Configure(_) => Ok(BrainAnswer::Configured),
        BrainCall::Translate(_) => Err(BridgeError::PythonRaised {
            exception_type: "RuntimeError".to_owned(),
            message: "no translation model is loaded; ask a human interpreter".to_owned(),
        }),
        BrainCall::Simplify(request) => Ok(BrainAnswer::Simplified(SimplifyResult {
            draft: DraftFlag,
            text: request.text,
            lang: request.lang,
            level: request.level,
            simplified: false,
        })),
        BrainCall::Summarise(request) => Ok(BrainAnswer::Summarised(SummaryDraft {
            draft: DraftFlag,
            lines: copy(&request.sources),
            lang: request.lang,
            dropped: 0,
        })),
        BrainCall::Report(report) => Ok(BrainAnswer::Reported(ReportDraft {
            draft: DraftFlag,
            kind: report.request.kind,
            from: report.request.from,
            to: report.request.to,
            lines: copy(&report.facts),
            lang: report.request.lang,
            dropped: 0,
        })),
    }
}

/// Interpreter start-up (feature `python`).
#[cfg(feature = "python")]
mod python {
    use domain::{DraftFlag, LangCode, PrivateText, SimplifyResult, TextChecks, TranslateResult};
    use pyo3::prelude::*;
    use pyo3::types::PyBytes;

    use super::{BrainAnswer, BrainCall, DISPATCH_MODULE, NO_VOICE, PythonConfig, rules_only};
    use crate::error::BridgeError;
    use crate::patient_aid::{PATIENT_AID_MODULE, Transcription};
    use crate::summary::digit_runs;

    /// Initialises the interpreter, puts the repository root (and the venv's packages) on
    /// `sys.path` and imports the dispatch brick.
    pub(super) fn initialise(config: &PythonConfig) -> Result<(), BridgeError> {
        Python::initialize();
        Python::attach(|py| {
            let raised = |error: PyErr| BridgeError::ImportFailed {
                module: DISPATCH_MODULE.to_owned(),
                detail: error
                    .get_type(py)
                    .name()
                    .map_or_else(|_| "an exception".to_owned(), |name| name.to_string()),
            };
            let sys = py.import("sys").map_err(raised)?;
            let path = sys.getattr("path").map_err(raised)?;
            let mut roots = vec![config.repo_root.to_string_lossy().into_owned()];
            if let Some(venv) = &config.venv {
                roots.push(
                    venv.join("Lib")
                        .join("site-packages")
                        .to_string_lossy()
                        .into_owned(),
                );
            }
            for root in roots {
                path.call_method1("insert", (0, root)).map_err(raised)?;
            }
            py.import(DISPATCH_MODULE).map_err(raised)?;
            Ok(())
        })
    }

    /// A brain call on the interpreter thread: the patient helpers of `aide_patient.py`
    /// (transcribe, translate, simplify, health, configure); summaries and reports keep the
    /// rules-only step. Texts and audio stay in memory; Python writes and logs nothing.
    pub(super) fn brain(call: BrainCall) -> Result<BrainAnswer, BridgeError> {
        Python::attach(|py| {
            let fail = |error: PyErr| python_error(py, &error);
            let aid = py.import(PATIENT_AID_MODULE).map_err(fail)?;
            match call {
                BrainCall::Configure(config) => {
                    aid.call_method1(
                        "configurer",
                        (
                            config.apertus_url,
                            config.apertus_timeout.as_secs_f64(),
                            config.whisper_model,
                        ),
                    )
                    .map_err(fail)?;
                    Ok(BrainAnswer::Configured)
                }
                BrainCall::Health => {
                    let state = aid.call_method0("etat").map_err(fail)?;
                    let voices = state
                        .get_item("voix")
                        .ok()
                        .and_then(|value| value.extract::<Vec<String>>().ok())
                        .unwrap_or_default();
                    Ok(BrainAnswer::Health {
                        whisper: flag(&state, "whisper")?,
                        apertus: flag(&state, "apertus")?,
                        voices,
                    })
                }
                BrainCall::Speak { text, lang } => {
                    // HACKATHON: the audio is built in memory and never stored or logged.
                    let wav = aid
                        .call_method1("parler", (text, lang))
                        .map_err(fail)?
                        .extract::<Vec<u8>>()
                        .map_err(|_| conversion("audio"))?;
                    Ok(BrainAnswer::Spoken(wav))
                }
                BrainCall::Transcribe(audio) => {
                    // HACKATHON: audio passes through to the local brain for transcription,
                    // never stored.
                    let heard = aid
                        .call_method1("transcrire", (PyBytes::new(py, &audio),))
                        .map_err(fail)?;
                    Ok(BrainAnswer::Transcribed(Transcription {
                        text: text(&heard, "text")?,
                        lang: text(&heard, "lang")?,
                        duration_s: number(&heard, "duration_s")?,
                    }))
                }
                BrainCall::Translate(request) => {
                    let from = request.from.as_ref().map(|lang| lang.as_str().to_owned());
                    let out = aid
                        .call_method1(
                            "traduire",
                            (request.text.expose(), request.to.as_str(), from),
                        )
                        .map_err(fail)?;
                    let translated = text(&out, "text")?;
                    let kept = digit_runs(&translated);
                    let numbers_ok = digit_runs(request.text.expose())
                        .iter()
                        .all(|run| kept.contains(run));
                    let from: LangCode = text(&out, "from")?
                        .parse()
                        .map_err(|_| conversion("from"))?;
                    Ok(BrainAnswer::Translated(TranslateResult {
                        draft: DraftFlag,
                        text: PrivateText::new(translated).map_err(|_| conversion("text"))?,
                        from,
                        to: request.to,
                        checks: TextChecks {
                            fixed_terms_ok: true,
                            numbers_ok,
                        },
                    }))
                }
                BrainCall::Simplify(request) => {
                    let out = aid
                        .call_method1("simplifier", (request.text.expose(), request.lang.as_str()))
                        .map_err(fail)?;
                    Ok(BrainAnswer::Simplified(SimplifyResult {
                        draft: DraftFlag,
                        text: PrivateText::new(text(&out, "text")?)
                            .map_err(|_| conversion("text"))?,
                        simplified: flag(&out, "simplified")?,
                        lang: request.lang,
                        level: request.level,
                    }))
                }
                other => rules_only(other),
            }
        })
    }

    fn conversion(field: &str) -> BridgeError {
        BridgeError::Conversion {
            field: field.to_owned(),
        }
    }

    fn text(object: &Bound<'_, PyAny>, key: &str) -> Result<String, BridgeError> {
        object
            .get_item(key)
            .ok()
            .and_then(|value| value.extract::<String>().ok())
            .ok_or_else(|| conversion(key))
    }

    fn flag(object: &Bound<'_, PyAny>, key: &str) -> Result<bool, BridgeError> {
        object
            .get_item(key)
            .ok()
            .and_then(|value| value.extract::<bool>().ok())
            .ok_or_else(|| conversion(key))
    }

    fn number(object: &Bound<'_, PyAny>, key: &str) -> Result<f64, BridgeError> {
        object
            .get_item(key)
            .ok()
            .and_then(|value| value.extract::<f64>().ok())
            .ok_or_else(|| conversion(key))
    }

    /// A Python exception as a bridge error, without its text (it may quote a request) except
    /// for `AudioRefuse`, whose messages are fixed phrases of `aide_patient.py`.
    fn python_error(py: Python<'_>, error: &PyErr) -> BridgeError {
        let kind = error
            .get_type(py)
            .name()
            .map_or_else(|_| "Exception".to_owned(), |name| name.to_string());
        match kind.as_str() {
            "Indisponible" => {
                let what = error
                    .value(py)
                    .getattr("quoi")
                    .ok()
                    .and_then(|value| value.extract::<String>().ok())
                    .unwrap_or_default();
                let detail = if what == "whisper" {
                    "the speech model (faster-whisper) could not be loaded"
                } else if what == "voix" {
                    NO_VOICE
                } else {
                    "the translation model (Apertus) is not reachable"
                };
                BridgeError::InterpreterUnavailable {
                    detail: detail.to_owned(),
                }
            }
            "AudioRefuse" => BridgeError::PythonRaised {
                exception_type: kind,
                message: error
                    .value(py)
                    .str()
                    .map_or_else(|_| "the audio was refused".to_owned(), |m| m.to_string()),
            },
            _ => BridgeError::PythonRaised {
                exception_type: kind,
                message: "a Python brick raised".to_owned(),
            },
        }
    }
}
