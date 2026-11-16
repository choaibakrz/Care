//! The mock brain (`--mock`, Task A6): clearly labelled canned drafts, so the console and the
//! staff app can be built against the four endpoints now.
//!
//! - translate: `"MOCK TRANSLATION (fr→en) — "` followed by the text unchanged; both checks
//!   `true`; `from` defaults to `fr`;
//! - simplify: `"MOCK SIMPLIFICATION (plain) — "` followed by the text; `simplified: true`;
//! - summarise: one line per source, `"MOCK SUMMARY — <kind> <id>, <n> characters"`, with
//!   its `source` (the text is not repeated);
//! - report: up to five lines from the mock queue, incidents or robots (whatever the
//!   period), each with its server source (`task:t-1`, `incident:1`, `robot:r1`);
//! - health: `up`, model `mock (canned drafts, no model)`.
//!
//! Like the live server, the mock keeps no text: it adds one audit row per call
//! (`brain_<kind>`, `ok`, detail `mock, 0 ms`), the row the journal's `BrainCall` record gives
//! on the live server, and logs nothing.

use async_trait::async_trait;
use domain::{
    BrainCallKind, BrainHealth, BrainStatus, DraftFlag, DraftLine, LangCode, PrivateText,
    ReportDraft, ReportKind, ReportRequest, SimplifyLevel, SimplifyRequest, SimplifyResult,
    SourceRef, SummariseRequest, SummaryDraft, TranslateRequest, TranslateResult,
};
use security::ClientIdentity;

use super::{MockServices, wire_name};
use crate::dto::{AuditEntry, AuditResult};
use crate::error::ApiError;
use crate::services::BrainService;

/// The model name the mock reports.
pub const MOCK_BRAIN_MODEL: &str = "mock (canned drafts, no model)";
/// Most lines of a mock report.
const MOCK_REPORT_LINES: usize = 5;

impl MockServices {
    /// Adds the audit row of one brain call (never a text).
    fn record_brain_call(&self, actor: &ClientIdentity, kind: BrainCallKind) {
        let label = actor
            .verified
            .owner
            .as_ref()
            .map_or_else(|| "unknown".to_owned(), ToString::to_string);
        let at = self.clock.now();
        let mut data = self.data();
        let id = data.audit.iter().map(|row| row.id).max().unwrap_or(0) + 1;
        data.audit.push(AuditEntry {
            id,
            at,
            actor: label,
            action: format!("brain_{}", kind.name()),
            target: String::new(),
            result: AuditResult::Ok,
            detail: Some("mock, 0 ms".to_owned()),
            category: "audit".to_owned(),
        });
    }
}

/// A labelled mock text (the label keeps it under the length limit by cutting the tail).
fn labelled(label: &str, text: &str) -> Result<PrivateText, ApiError> {
    let mut out = format!("{label} — {text}");
    if out.chars().count() > domain::brain::MAX_TEXT_CHARS {
        out = out.chars().take(domain::brain::MAX_TEXT_CHARS).collect();
    }
    Ok(PrivateText::new(out)?)
}

/// One mock line with its source.
fn line(text: String, source: &str) -> Result<DraftLine, ApiError> {
    Ok(DraftLine {
        text: PrivateText::new(text)?,
        source: source.parse::<SourceRef>()?,
    })
}

#[async_trait]
impl BrainService for MockServices {
    async fn translate(
        &self,
        actor: &ClientIdentity,
        request: TranslateRequest,
    ) -> Result<TranslateResult, ApiError> {
        let from = match request.from {
            Some(from) => from,
            None => "fr".parse::<LangCode>()?,
        };
        let label = format!("MOCK TRANSLATION ({from}→{})", request.to);
        let result = TranslateResult {
            draft: DraftFlag,
            text: labelled(&label, request.text.expose())?,
            from,
            to: request.to,
            checks: domain::TextChecks {
                fixed_terms_ok: true,
                numbers_ok: true,
            },
        };
        self.record_brain_call(actor, BrainCallKind::Translate);
        Ok(result)
    }

    async fn simplify(
        &self,
        actor: &ClientIdentity,
        request: SimplifyRequest,
    ) -> Result<SimplifyResult, ApiError> {
        let level = match request.level {
            SimplifyLevel::Plain => "plain",
            SimplifyLevel::Easy => "easy",
        };
        let result = SimplifyResult {
            draft: DraftFlag,
            text: labelled(
                &format!("MOCK SIMPLIFICATION ({level})"),
                request.text.expose(),
            )?,
            lang: request.lang,
            level: request.level,
            simplified: true,
        };
        self.record_brain_call(actor, BrainCallKind::Simplify);
        Ok(result)
    }

    async fn summarise(
        &self,
        actor: &ClientIdentity,
        request: SummariseRequest,
    ) -> Result<SummaryDraft, ApiError> {
        request.check()?;
        let lines = request
            .sources
            .iter()
            .map(|source| {
                line(
                    format!(
                        "MOCK SUMMARY — {} {}, {} characters",
                        wire_name(&source.kind),
                        source.id,
                        source.text.chars()
                    ),
                    source.id.as_str(),
                )
            })
            .collect::<Result<Vec<_>, _>>()?;
        self.record_brain_call(actor, BrainCallKind::Summarise);
        Ok(SummaryDraft {
            draft: DraftFlag,
            lang: request.lang,
            lines,
            dropped: 0,
        })
    }

    async fn report(
        &self,
        actor: &ClientIdentity,
        request: ReportRequest,
    ) -> Result<ReportDraft, ApiError> {
        request.check()?;
        let lines = {
            let data = self.data();
            match request.kind {
                ReportKind::Shift => data
                    .tasks
                    .iter()
                    .take(MOCK_REPORT_LINES)
                    .map(|task| {
                        line(
                            format!(
                                "MOCK REPORT — task {} ({}) is {}",
                                task.id.as_str(),
                                wire_name(&task.kind),
                                wire_name(&task.state)
                            ),
                            &format!("task:{}", task.id.as_str()),
                        )
                    })
                    .collect::<Result<Vec<_>, _>>()?,
                ReportKind::Incident => data
                    .incidents
                    .iter()
                    .take(MOCK_REPORT_LINES)
                    .map(|incident| {
                        line(
                            format!(
                                "MOCK REPORT — incident {} ({}), {}",
                                incident.id.0,
                                wire_name(&incident.code),
                                if incident.closed_at.is_some() {
                                    "closed"
                                } else {
                                    "open"
                                }
                            ),
                            &format!("incident:{}", incident.id.0),
                        )
                    })
                    .collect::<Result<Vec<_>, _>>()?,
                ReportKind::RobotActivity => data
                    .robots
                    .iter()
                    .take(MOCK_REPORT_LINES)
                    .map(|robot| {
                        line(
                            format!(
                                "MOCK REPORT — robot {} is {}",
                                robot.view.id.as_str(),
                                wire_name(&robot.view.state)
                            ),
                            &format!("robot:{}", robot.view.id.as_str()),
                        )
                    })
                    .collect::<Result<Vec<_>, _>>()?,
            }
        };
        self.record_brain_call(actor, BrainCallKind::Report);
        Ok(ReportDraft {
            draft: DraftFlag,
            kind: request.kind,
            from: request.from,
            to: request.to,
            lang: request.lang,
            lines,
            dropped: 0,
        })
    }

    async fn health(&self) -> BrainHealth {
        BrainHealth {
            status: BrainStatus::Up,
            models: vec![MOCK_BRAIN_MODEL.to_owned()],
            queue: 0,
            detail: Some("mock server: canned drafts, no model runs".to_owned()),
        }
    }

    fn status(&self) -> BrainStatus {
        BrainStatus::Up
    }
}
