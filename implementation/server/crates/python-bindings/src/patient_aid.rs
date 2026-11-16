//! The patient app's helpers (hackathon): listen (faster-whisper, local), translate any pair
//! of [`LANGUAGES`] and simplify (Apertus over its OpenAI-compatible endpoint), all done by
//! `briques/clinique/aide_patient.py` on the bridge's interpreter thread.
//!
//! HACKATHON: audio passes through to the local brain for transcription, never stored. The
//! bytes are handed to Python as a `bytes` object, decoded in memory and dropped.

use std::time::Duration;

/// The Python module of the patient helpers.
pub const PATIENT_AID_MODULE: &str = "briques.clinique.aide_patient";

/// The languages the patient helpers translate between (ISO 639-1).
pub const LANGUAGES: [&str; 17] = [
    "en", "fr", "de", "it", "es", "pt", "nl", "ar", "tr", "zh", "ru", "uk", "pl", "sq", "sr", "hr",
    "ro",
];

/// Largest recording `/v1/transcribe` reads (about 60 s of compressed speech).
pub const MAX_AUDIO_BYTES: usize = 4 * 1024 * 1024;

/// Longest text `/v1/speak` reads aloud, in characters.
pub const MAX_SPEAK_CHARS: usize = 2000;

/// Default `APERTUS_URL`.
pub const DEFAULT_APERTUS_URL: &str = "http://127.0.0.1:8089";
/// Default `APERTUS_TIMEOUT_S`.
pub const DEFAULT_APERTUS_TIMEOUT: Duration = Duration::from_secs(15);
/// Default `WHISPER_MODEL`.
pub const DEFAULT_WHISPER_MODEL: &str = "small";

/// Settings of the patient helpers, given to the Python module at start.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PatientAidConfig {
    /// `APERTUS_URL`: base of the OpenAI-compatible endpoint (`{url}/v1/chat/completions`).
    pub apertus_url: String,
    /// `APERTUS_TIMEOUT_S`: one Apertus answer.
    pub apertus_timeout: Duration,
    /// `WHISPER_MODEL`: faster-whisper model size or path.
    pub whisper_model: String,
}

impl Default for PatientAidConfig {
    fn default() -> PatientAidConfig {
        PatientAidConfig {
            apertus_url: DEFAULT_APERTUS_URL.to_owned(),
            apertus_timeout: DEFAULT_APERTUS_TIMEOUT,
            whisper_model: DEFAULT_WHISPER_MODEL.to_owned(),
        }
    }
}

/// What was heard in a recording. `Debug` never prints the text.
#[derive(Clone, PartialEq)]
pub struct Transcription {
    /// The transcript (empty when nothing was said).
    pub text: String,
    /// The detected language (ISO 639-1).
    pub lang: String,
    /// Length of the recording, in seconds.
    pub duration_s: f64,
}

impl std::fmt::Debug for Transcription {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Transcription({} chars, {}, {} s)",
            self.text.chars().count(),
            self.lang,
            self.duration_s
        )
    }
}

/// Whether `code` (`fr`, `pt-br`, …) is one of [`LANGUAGES`], by its primary tag.
#[must_use]
pub fn is_supported(code: &str) -> bool {
    let primary = code.split('-').next().unwrap_or_default();
    LANGUAGES.contains(&primary)
}

#[cfg(test)]
mod tests {
    #[test]
    fn languages_are_checked_by_primary_tag() {
        assert!(super::is_supported("fr"));
        assert!(super::is_supported("pt-br"));
        assert!(!super::is_supported("xx"));
    }
}
