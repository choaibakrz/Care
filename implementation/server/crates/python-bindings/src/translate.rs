//! The translate call (Task 20b) over `briques/clinique/interprete.py`: the two-step path
//! (the text, then Apertus with the fixed terms), `chiffres_en_chiffres`, then `controler`.
//!
//! Hackathon: translation now goes through `aide_patient.py` (Apertus) for any pair of
//! [`crate::patient_aid::LANGUAGES`]; `from` may be absent (detected by the model).
//! [`check_pair`] refuses other languages explicitly instead of returning a wrong draft.

use domain::{LangCode, TextChecks};

use crate::error::BridgeError;
use crate::patient_aid::is_supported;

/// The Python module of the interpreter brick.
pub const INTERPRETER_MODULE: &str = "briques.clinique.interprete";
/// The fixed medical terms, relative to the repository root (Hiba reads and edits it).
pub const FIXED_TERMS_FILE: &str = "briques/clinique/interprete_mots.yaml";
/// Whether the brain can translate from `from` (absent: detected) into `to`.
///
/// # Errors
/// `BridgeError::UnsupportedLanguage` when a language is not in
/// [`crate::patient_aid::LANGUAGES`].
pub fn check_pair(from: Option<&LangCode>, to: &LangCode) -> Result<(), BridgeError> {
    let from_ok = from.is_none_or(|lang| is_supported(lang.as_str()));
    if from_ok && is_supported(to.as_str()) {
        Ok(())
    } else {
        Err(BridgeError::UnsupportedLanguage {
            from: from.map_or("auto", LangCode::as_str).to_owned(),
            to: to.as_str().to_owned(),
        })
    }
}

/// The two booleans of a draft from the problem list of `controler` (French texts):
/// a "mot fixé" problem clears `fixed_terms_ok`, a "chiffre perdu ou changé" problem clears
/// `numbers_ok`. The problem texts themselves are not returned (they may quote numbers of the
/// source).
#[must_use]
pub fn checks_from_problems(problems: &[String]) -> TextChecks {
    TextChecks {
        fixed_terms_ok: !problems.iter().any(|p| p.starts_with("mot fixé")),
        numbers_ok: !problems
            .iter()
            .any(|p| p.starts_with("chiffre perdu ou changé")),
    }
}

#[cfg(test)]
mod tests {
    use super::{check_pair, checks_from_problems};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn the_seventeen_languages_are_supported_and_others_refused() -> TestResult {
        assert!(check_pair(Some(&"fr".parse()?), &"en".parse()?).is_ok());
        assert!(check_pair(None, &"uk".parse()?).is_ok());
        let refused = check_pair(None, &"xx".parse()?)
            .err()
            .ok_or("expected a refusal")?;
        assert!(
            refused.to_string().contains("human interpreter"),
            "{refused}"
        );
        Ok(())
    }

    #[test]
    fn problems_map_to_the_two_checks() {
        let none = checks_from_problems(&[]);
        assert!(none.fixed_terms_ok && none.numbers_ok);
        let terms = checks_from_problems(&[
            "mot fixé non respecté : « gardien » doit donner « guardian »".to_owned(),
        ]);
        assert!(!terms.fixed_terms_ok && terms.numbers_ok);
        let numbers = checks_from_problems(&["chiffre perdu ou changé : 20".to_owned()]);
        assert!(numbers.fixed_terms_ok && !numbers.numbers_ok);
    }
}
