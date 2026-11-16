//! Source checks of summaries, reports and simplifications (Task 20b), the rule of
//! `briques/clinique/resume.py` (`garder_les_phrases_sures`): a line is kept only when its
//! source is one of the request's sources and every run of digits of the line appears in that
//! source. The check does not judge meaning (same known limit as `resume.py`).
//!
//! The Python brick applies the rule first; these functions apply it again on the Rust side
//! before a draft leaves the brain, so a model answer can never add a number.

use domain::{DraftLine, SummarySource};

/// The Python module of the summary brick.
pub const SUMMARY_MODULE: &str = "briques.clinique.resume";

/// The runs of ASCII digits of a text, in order (`"20 courses, 3 robots"` → `["20", "3"]`).
#[must_use]
pub fn digit_runs(text: &str) -> Vec<&str> {
    text.split(|c: char| !c.is_ascii_digit())
        .filter(|run| !run.is_empty())
        .collect()
}

/// Whether a line names one of `sources` and every digit run of the line is in that source.
#[must_use]
pub fn line_is_sourced(line: &DraftLine, sources: &[SummarySource]) -> bool {
    let Some(source) = sources.iter().find(|source| source.id == line.source) else {
        return false;
    };
    let known = digit_runs(source.text.expose());
    digit_runs(line.text.expose())
        .iter()
        .all(|run| known.contains(run))
}

/// The lines that pass [`line_is_sourced`], and how many were dropped.
#[must_use]
pub fn keep_sourced_lines(
    lines: Vec<DraftLine>,
    sources: &[SummarySource],
) -> (Vec<DraftLine>, u32) {
    let total = lines.len();
    let kept: Vec<DraftLine> = lines
        .into_iter()
        .filter(|line| line_is_sourced(line, sources))
        .collect();
    let dropped = u32::try_from(total.saturating_sub(kept.len())).unwrap_or(u32::MAX);
    (kept, dropped)
}

/// Whether a plain-language rewrite kept the source's numbers and added none.
#[must_use]
pub fn simplification_is_safe(source: &str, rewrite: &str) -> bool {
    use std::collections::BTreeSet;
    if rewrite.trim().is_empty() {
        return false;
    }
    let before: BTreeSet<&str> = digit_runs(source).into_iter().collect();
    let after: BTreeSet<&str> = digit_runs(rewrite).into_iter().collect();
    before == after
}

#[cfg(test)]
mod tests {
    use domain::{DraftLine, PrivateText, SourceKind, SummarySource};

    use super::{keep_sourced_lines, simplification_is_safe};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn source(id: &str, text: &str) -> Result<SummarySource, Box<dyn std::error::Error>> {
        Ok(SummarySource {
            id: id.parse()?,
            kind: SourceKind::Note,
            text: PrivateText::new(text.to_owned())?,
        })
    }

    fn line(source: &str, text: &str) -> Result<DraftLine, Box<dyn std::error::Error>> {
        Ok(DraftLine {
            text: PrivateText::new(text.to_owned())?,
            source: source.parse()?,
        })
    }

    #[test]
    fn a_line_with_a_number_not_in_its_source_is_dropped() -> TestResult {
        let sources = [source("note-1", "Temperature 38 at 7 h.")?];
        let (kept, dropped) = keep_sourced_lines(
            vec![
                line("note-1", "Fever 38.")?,
                line("note-1", "Fever 39.")?,
                line("note-9", "Unknown source.")?,
            ],
            &sources,
        );
        assert_eq!(kept.len(), 1);
        assert_eq!(dropped, 2);
        Ok(())
    }

    #[test]
    fn a_rewrite_that_changes_a_number_is_not_safe() {
        assert!(simplification_is_safe(
            "Take 2 tablets at 8 h.",
            "At 8, take 2 pills."
        ));
        assert!(!simplification_is_safe(
            "Take 2 tablets at 8 h.",
            "Take 3 pills."
        ));
    }
}
