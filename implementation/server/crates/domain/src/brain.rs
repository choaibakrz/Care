//! Types of the server-side brain (Task A6): what clients send to `POST /brain/*`, what the
//! main server sends to the `clinic-brain` process (`/v1/*`), and what comes back.
//!
//! **Privacy rule.** Texts sent to the brain pass through the servers *in memory only*: they
//! are never written to the database, the journal, a log or a temporary file. Every text is a
//! [`PrivateText`], whose `Debug` prints only its length and which has no `Display`, so a
//! `tracing` field or an error message cannot carry it by accident. The journal records only
//! [`BrainCallKind`], the latency and whether the call succeeded.
//!
//! **Results are drafts.** Every result carries `draft: true` ([`DraftFlag`]): a staff member
//! reads it before anything is sent anywhere, and the UI shows it as a draft. Summary and
//! report lines each name their `source`.

use std::fmt;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use utoipa::ToSchema;

use crate::error::DomainError;

/// Longest accepted text, in characters (one note, one message, one source).
pub const MAX_TEXT_CHARS: usize = 8_000;
/// Most sources in one summary request.
pub const MAX_SOURCES: usize = 20;
/// Longest report period, in hours (one week).
pub const MAX_REPORT_HOURS: i64 = 7 * 24;

/// A text sent to or produced by the brain. Never logged, stored or journaled.
///
/// Invariant: 1 to [`MAX_TEXT_CHARS`] characters, not only whitespace. `Debug` prints
/// `PrivateText(<n> chars)`; there is no `Display`. Serialises as a plain string.
#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(try_from = "String", into = "String")]
#[schema(value_type = String)]
pub struct PrivateText(String);

impl PrivateText {
    /// Validates and wraps a text.
    ///
    /// # Errors
    /// `DomainError::InvalidBrainInput` (field `text`) when empty, only whitespace or longer
    /// than [`MAX_TEXT_CHARS`]. The message never repeats the text.
    pub fn new(text: String) -> Result<PrivateText, DomainError> {
        let reason = if text.trim().is_empty() {
            Some("it is empty".to_owned())
        } else if text.chars().count() > MAX_TEXT_CHARS {
            Some(format!("it is longer than {MAX_TEXT_CHARS} characters"))
        } else {
            None
        };
        match reason {
            Some(reason) => Err(DomainError::InvalidBrainInput {
                field: "text",
                reason,
            }),
            None => Ok(PrivateText(text)),
        }
    }

    /// The text. Callers must not log it.
    #[must_use]
    pub fn expose(&self) -> &str {
        &self.0
    }

    /// Length in characters (safe to log).
    #[must_use]
    pub fn chars(&self) -> usize {
        self.0.chars().count()
    }
}

impl fmt::Debug for PrivateText {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "PrivateText({} chars)", self.chars())
    }
}

impl TryFrom<String> for PrivateText {
    type Error = DomainError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        PrivateText::new(value)
    }
}

impl From<PrivateText> for String {
    fn from(text: PrivateText) -> String {
        text.0
    }
}

/// A language code such as `fr`, `en`, `de`, `pt-br`.
///
/// Invariant: a 2 or 3 letter primary tag in lowercase, optionally followed by `-` and 2 to 8
/// letters or digits (lowercased on input).
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema)]
#[serde(try_from = "String", into = "String")]
#[schema(value_type = String, example = "fr")]
pub struct LangCode(String);

impl LangCode {
    /// The code.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::str::FromStr for LangCode {
    type Err = DomainError;

    /// # Errors
    /// `DomainError::InvalidBrainInput` (field `lang`) when the code has another shape.
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let lower = value.trim().to_ascii_lowercase();
        let mut parts = lower.splitn(2, '-');
        let primary = parts.next().unwrap_or_default();
        let region = parts.next();
        let primary_ok =
            (2..=3).contains(&primary.len()) && primary.chars().all(|c| c.is_ascii_lowercase());
        let region_ok = region.is_none_or(|r| {
            (2..=8).contains(&r.len()) && r.chars().all(|c| c.is_ascii_alphanumeric())
        });
        if primary_ok && region_ok {
            Ok(LangCode(lower))
        } else {
            Err(DomainError::InvalidBrainInput {
                field: "lang",
                reason: "it is not a language code such as 'fr', 'en' or 'pt-br'".to_owned(),
            })
        }
    }
}

impl TryFrom<String> for LangCode {
    type Error = DomainError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        value.parse()
    }
}

impl From<LangCode> for String {
    fn from(code: LangCode) -> String {
        code.0
    }
}

impl fmt::Display for LangCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// Where a summary or report line comes from: a client source id (`note-3`) or a server
/// record (`task:t-12`, `incident:4`, `robot:r1`).
///
/// Invariant: 1 to 96 characters among ASCII letters, digits, `.`, `_`, `:` and `-`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema)]
#[serde(try_from = "String", into = "String")]
#[schema(value_type = String, example = "note-1")]
pub struct SourceRef(String);

impl SourceRef {
    /// The reference.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::str::FromStr for SourceRef {
    type Err = DomainError;

    /// # Errors
    /// `DomainError::InvalidBrainInput` (field `source`) when empty, longer than 96 or with
    /// another character.
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let ok = (1..=96).contains(&value.len())
            && value
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | ':' | '-'));
        if ok {
            Ok(SourceRef(value.to_owned()))
        } else {
            Err(DomainError::InvalidBrainInput {
                field: "source",
                reason: "use 1 to 96 characters among letters, digits, '.', '_', ':' and '-'"
                    .to_owned(),
            })
        }
    }
}

impl TryFrom<String> for SourceRef {
    type Error = DomainError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        value.parse()
    }
}

impl From<SourceRef> for String {
    fn from(source: SourceRef) -> String {
        source.0
    }
}

impl fmt::Display for SourceRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// The `draft: true` of every brain result: always serialised as `true`, and only `true` is
/// accepted when reading a result back (the main server reads the brain's answers).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct DraftFlag;

impl Serialize for DraftFlag {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_bool(true)
    }
}

impl<'de> Deserialize<'de> for DraftFlag {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        if bool::deserialize(deserializer)? {
            Ok(DraftFlag)
        } else {
            Err(serde::de::Error::custom(
                "a brain result must be a draft (draft: true)",
            ))
        }
    }
}

/// Which brain function was called (the only thing the journal keeps about a call, with its
/// latency and outcome).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum BrainCallKind {
    /// `POST /brain/translate`.
    Translate,
    /// `POST /brain/simplify`.
    Simplify,
    /// `POST /brain/summarise`.
    Summarise,
    /// `POST /brain/report`.
    Report,
}

impl BrainCallKind {
    /// The `snake_case` name (audit rows, metrics).
    #[must_use]
    pub fn name(self) -> &'static str {
        match self {
            BrainCallKind::Translate => "translate",
            BrainCallKind::Simplify => "simplify",
            BrainCallKind::Summarise => "summarise",
            BrainCallKind::Report => "report",
        }
    }
}

/// Whether the brain answers (`GET /health` `brain`, `GET /brain/health` `status`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum BrainStatus {
    /// Every model loaded; calls are served.
    Up,
    /// Served with the fallback only (for example the rules-only step of the cascade, or
    /// the one-step whisper translation without the fixed terms).
    Degraded,
    /// Not running, unreachable, wrong token, or built without Python. Brain calls answer
    /// 503 `brain_unavailable`; everything else on the server keeps working.
    #[default]
    Down,
}

/// `POST /brain/translate` and `/v1/translate`: the two-step path of
/// `briques/clinique/interprete.py` (the text, then Apertus with the fixed terms of
/// `interprete_mots.yaml`, then the number check).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct TranslateRequest {
    /// The text to translate.
    pub text: PrivateText,
    /// Source language; only French is supported today. Without it, French is assumed (no
    /// detection).
    #[serde(default)]
    pub from: Option<LangCode>,
    /// The target language; only English is supported today (any other pair is 422
    /// `unsupported_language`).
    pub to: LangCode,
}

/// What the program can check in a translation (it does not judge the meaning).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct TextChecks {
    /// Every fixed medical term of the source has its fixed translation, and no fixed
    /// translation appears without its term.
    pub fixed_terms_ok: bool,
    /// Every number of the source is in the translation, written in digits.
    pub numbers_ok: bool,
}

/// A translation draft.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct TranslateResult {
    /// Always `true`: a staff member reads it before using it.
    #[schema(value_type = bool)]
    pub draft: DraftFlag,
    /// The translation.
    pub text: PrivateText,
    /// The source language (given or detected).
    pub from: LangCode,
    /// The target language.
    pub to: LangCode,
    /// The checks; a failed check is shown next to the draft, the text is not altered.
    pub checks: TextChecks,
}

/// How plain the rewrite is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SimplifyLevel {
    /// Plain language for an adult patient.
    Plain,
    /// Easy-to-read language (short sentences, common words).
    Easy,
}

/// `POST /brain/simplify` and `/v1/simplify`: a plain-language rewrite for a patient. Never
/// adds medical advice.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SimplifyRequest {
    /// The text to rewrite.
    pub text: PrivateText,
    /// Its language (the rewrite is in the same language).
    pub lang: LangCode,
    /// How plain.
    pub level: SimplifyLevel,
}

/// A simplification draft.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct SimplifyResult {
    /// Always `true`.
    #[schema(value_type = bool)]
    pub draft: DraftFlag,
    /// The rewrite; when `simplified` is `false`, the source text unchanged.
    pub text: PrivateText,
    /// Language.
    pub lang: LangCode,
    /// Level asked for.
    pub level: SimplifyLevel,
    /// `false` when the rewrite failed its check against the source (a number lost or
    /// added, a fixed term changed) or no model answered: the UI says "could not simplify
    /// safely" and shows the original.
    pub simplified: bool,
}

/// What a source is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    /// A care note written by staff.
    Note,
    /// A message.
    Message,
    /// A document (letter, report).
    Document,
    /// The transcript of an interpreter exchange.
    Transcript,
    /// A task of the server (reports only).
    Task,
    /// An incident of the server (reports only).
    Incident,
    /// Robot activity of the server (reports only).
    RobotActivity,
}

/// One source of a summary or report.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SummarySource {
    /// The id lines point to (`note-1`); unique within the request.
    pub id: SourceRef,
    /// What it is.
    pub kind: SourceKind,
    /// Its text.
    pub text: PrivateText,
}

/// `POST /brain/summarise` and `/v1/summarise`: the `briques/clinique/resume.py` rule: every
/// line points to its source, every number of a line is in that source, a line that fails
/// is dropped (and counted).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SummariseRequest {
    /// 1 to [`MAX_SOURCES`] sources with unique ids.
    pub sources: Vec<SummarySource>,
    /// Language of the summary.
    pub lang: LangCode,
}

impl SummariseRequest {
    /// Checks the source count and that ids are unique.
    ///
    /// # Errors
    /// `DomainError::InvalidBrainInput` (field `sources`).
    pub fn check(&self) -> Result<(), DomainError> {
        let invalid = |reason: &str| DomainError::InvalidBrainInput {
            field: "sources",
            reason: reason.to_owned(),
        };
        if self.sources.is_empty() {
            return Err(invalid("it is empty"));
        }
        if self.sources.len() > MAX_SOURCES {
            return Err(invalid(&format!("it has more than {MAX_SOURCES} sources")));
        }
        let mut ids: Vec<&SourceRef> = self.sources.iter().map(|s| &s.id).collect();
        ids.sort();
        ids.dedup();
        if ids.len() != self.sources.len() {
            return Err(invalid("two sources have the same id"));
        }
        Ok(())
    }
}

/// One line of a summary or report, with its source.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct DraftLine {
    /// The line.
    pub text: PrivateText,
    /// The source it comes from (a request source id, or a server record).
    pub source: SourceRef,
}

/// A summary draft.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct SummaryDraft {
    /// Always `true`.
    #[schema(value_type = bool)]
    pub draft: DraftFlag,
    /// Language.
    pub lang: LangCode,
    /// Every line, each with its source; empty when nothing passed the check (the UI then
    /// says "nothing new").
    pub lines: Vec<DraftLine>,
    /// Lines the brain wrote but the source check removed.
    pub dropped: u32,
}

/// Which report.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ReportKind {
    /// What happened during a shift: tasks and incidents.
    Shift,
    /// The incidents of the period.
    Incident,
    /// What the robots did: tasks, failures, time offline.
    RobotActivity,
}

impl ReportKind {
    /// The `snake_case` name.
    #[must_use]
    pub fn name(self) -> &'static str {
        match self {
            ReportKind::Shift => "shift",
            ReportKind::Incident => "incident",
            ReportKind::RobotActivity => "robot_activity",
        }
    }
}

/// `POST /brain/report` (clients): a report built from server data the caller may see
/// (tasks, incidents, robot activity). No audio and no free text from patients go in.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReportRequest {
    /// Which report.
    pub kind: ReportKind,
    /// Start of the period (UTC).
    pub from: DateTime<Utc>,
    /// End of the period (UTC), after `from`, at most [`MAX_REPORT_HOURS`] later.
    pub to: DateTime<Utc>,
    /// Language of the report.
    pub lang: LangCode,
}

impl ReportRequest {
    /// Checks the period.
    ///
    /// # Errors
    /// `DomainError::InvalidBrainInput` (field `to`) when `to` is not after `from` or the
    /// period is longer than [`MAX_REPORT_HOURS`].
    pub fn check(&self) -> Result<(), DomainError> {
        let hours = (self.to - self.from).num_hours();
        if self.to <= self.from {
            Err(DomainError::InvalidBrainInput {
                field: "to",
                reason: "it must be after `from`".to_owned(),
            })
        } else if hours > MAX_REPORT_HOURS {
            Err(DomainError::InvalidBrainInput {
                field: "to",
                reason: format!("the period is longer than {MAX_REPORT_HOURS} hours"),
            })
        } else {
            Ok(())
        }
    }
}

/// `/v1/report` (main server to brain): the client's request plus the facts the main server
/// gathered for the caller, each a source with a server reference (`task:t-12`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct BrainReportRequest {
    /// The client's request.
    pub request: ReportRequest,
    /// The facts (kinds `task`, `incident`, `robot_activity` only).
    pub facts: Vec<SummarySource>,
}

impl BrainReportRequest {
    /// Checks the period and the fact count (at most [`MAX_SOURCES`], so the request stays
    /// within the brain's body limit).
    ///
    /// # Errors
    /// `DomainError::InvalidBrainInput` (`to` or `facts`).
    pub fn check(&self) -> Result<(), DomainError> {
        self.request.check()?;
        if self.facts.len() > MAX_SOURCES {
            return Err(DomainError::InvalidBrainInput {
                field: "facts",
                reason: format!("it has more than {MAX_SOURCES} facts"),
            });
        }
        Ok(())
    }
}

/// A report draft.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct ReportDraft {
    /// Always `true`.
    #[schema(value_type = bool)]
    pub draft: DraftFlag,
    /// Which report.
    pub kind: ReportKind,
    /// Period start.
    pub from: DateTime<Utc>,
    /// Period end.
    pub to: DateTime<Utc>,
    /// Language.
    pub lang: LangCode,
    /// Every line with its server source.
    pub lines: Vec<DraftLine>,
    /// Lines removed by the source check.
    pub dropped: u32,
}

/// `GET /brain/health` and `/v1/health`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct BrainHealth {
    /// `up`, `degraded` or `down`.
    pub status: BrainStatus,
    /// Models loaded (`apertus-8b`, `rules`, …); empty when down.
    pub models: Vec<String>,
    /// Calls waiting in the brain's queue.
    pub queue: u32,
    /// Why it is degraded or down, safe to show (no paths).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

impl BrainHealth {
    /// A `down` health with its reason.
    #[must_use]
    pub fn down(detail: String) -> BrainHealth {
        BrainHealth {
            status: BrainStatus::Down,
            models: Vec::new(),
            queue: 0,
            detail: Some(detail),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{DraftFlag, LangCode, PrivateText, ReportKind, ReportRequest, SourceRef};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn private_text_debug_never_prints_the_text() -> TestResult {
        let text = PrivateText::new("SENTINEL-patient-words".to_owned())?;
        let shown = format!("{text:?}");
        assert!(!shown.contains("SENTINEL"), "{shown}");
        assert_eq!(shown, "PrivateText(22 chars)");
        Ok(())
    }

    #[test]
    fn private_text_rejects_empty_and_too_long_without_repeating_it() {
        assert!(PrivateText::new("   ".to_owned()).is_err());
        let long = "x".repeat(super::MAX_TEXT_CHARS + 1);
        let message = PrivateText::new(long)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default();
        assert!(message.contains("longer than"), "{message}");
        assert!(!message.contains("xxxx"), "{message}");
    }

    #[test]
    fn lang_codes() -> TestResult {
        assert_eq!("FR".parse::<LangCode>()?.as_str(), "fr");
        assert_eq!("pt-BR".parse::<LangCode>()?.as_str(), "pt-br");
        assert!("french".parse::<LangCode>().is_err());
        assert!("f".parse::<LangCode>().is_err());
        Ok(())
    }

    #[test]
    fn source_refs() -> TestResult {
        assert_eq!("task:t-12".parse::<SourceRef>()?.as_str(), "task:t-12");
        assert!("a b".parse::<SourceRef>().is_err());
        Ok(())
    }

    #[test]
    fn draft_flag_is_always_true() -> TestResult {
        assert_eq!(serde_json::to_string(&DraftFlag)?, "true");
        assert!(serde_json::from_str::<DraftFlag>("false").is_err());
        assert_eq!(serde_json::from_str::<DraftFlag>("true")?, DraftFlag);
        Ok(())
    }

    #[test]
    fn report_period_is_checked() -> TestResult {
        let at = |h: u32| chrono::TimeZone::with_ymd_and_hms(&chrono::Utc, 2026, 11, 14, h, 0, 0);
        let from = at(8).single().ok_or("date")?;
        let to = at(16).single().ok_or("date")?;
        let ok = ReportRequest {
            kind: ReportKind::Shift,
            from,
            to,
            lang: "en".parse()?,
        };
        assert!(ok.check().is_ok());
        let backwards = ReportRequest {
            from: to,
            to: from,
            ..ok
        };
        assert!(backwards.check().is_err());
        Ok(())
    }
}
