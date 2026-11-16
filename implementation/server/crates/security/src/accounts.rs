//! Account key primitives (Task A7): the reference key derivation, the pepper, the pepper
//! HMAC that turns an account key into an account id, and a constant-time comparison.
//!
//! The derivation runs on the clients (`WebCrypto` in the console, the Flutter equivalent in
//! the staff app); [`derive_account_key`] is the reference the published test vector of
//! `docs/accounts.md` is computed with, and the `--mock` compatibility path for a console
//! that still sends a user name and password (until frontend task F9). The live server never
//! derives a key.
//!
//! Real code now (pure and small, the tests need it): [`derive_account_key`],
//! [`account_id`], [`enrolment_code_hash`], [`constant_time_eq`], [`Pepper::from_bytes`].
//! Task 8 fills [`Pepper::load_or_create`].

use std::path::Path;

use domain::{
    ACCOUNT_KEY_BYTES, AccountId, AccountKey, ClinicId, EnrolmentCode, KEY_DERIVATION_ITERATIONS,
    derivation_password, derivation_salt,
};
use hmac::{Hmac, KeyInit, Mac as _};
use sha2::Sha256;

use crate::error::SecurityError;

/// Length of the pepper, in bytes.
pub const PEPPER_BYTES: usize = 32;

/// The reference account key derivation (`docs/accounts.md`):
/// `PBKDF2-HMAC-SHA256(NFC(password), "clinic:" + clinic + ":" + lowercase(NFC(username)),
/// 600 000, 32)`.
///
/// Takes about 0.3 to 1 s on a tablet; in the server it runs only for the published test
/// vectors and the `--mock` compatibility login. User name and password are put in Unicode
/// NFC first (ruling R25: composed and decomposed accents give the same key); nothing is
/// trimmed.
#[must_use]
pub fn derive_account_key(username: &str, password: &str, clinic: &ClinicId) -> AccountKey {
    let salt = derivation_salt(clinic, username);
    let password = derivation_password(password);
    let mut out = [0_u8; ACCOUNT_KEY_BYTES];
    pbkdf2::pbkdf2_hmac::<Sha256>(
        password.as_bytes(),
        salt.as_bytes(),
        KEY_DERIVATION_ITERATIONS,
        &mut out,
    );
    AccountKey::from_bytes(out)
}

/// The secret key that turns account keys into account ids. Lives in a key file outside the
/// database (`ACCOUNT_PEPPER`, like the journal key): a database copy without it can neither
/// log in nor test password guesses. Never logged: `Debug` prints `Pepper(***)`.
#[derive(Clone)]
pub struct Pepper([u8; PEPPER_BYTES]);

impl Pepper {
    /// A pepper from its bytes (tests, the mock's fixed invented pepper).
    #[must_use]
    pub fn from_bytes(bytes: [u8; PEPPER_BYTES]) -> Pepper {
        Pepper(bytes)
    }

    /// Loads the pepper file, or creates it with 32 bytes of OS randomness (hex, one line)
    /// on first start, like the journal key.
    ///
    /// Creation (no window where the file exists with loose rights or partial content):
    /// `OpenOptions::new().write(true).create_new(true)` (`O_CREAT | O_EXCL`: never follows
    /// or reuses an existing path, a racing creator makes it fail and the existing file is
    /// then loaded), with Unix mode `0o600` given **at creation** through
    /// `OpenOptionsExt::mode` (never a `chmod` afterwards); the hex is written, then
    /// `sync_all` (fsync) before the pepper is used.
    ///
    /// Loading: the path is checked with `symlink_metadata` first and a symbolic link is
    /// refused (`PepperUnusable`); a file readable by other users (Unix mode
    /// `& 0o077 != 0`) is refused (`PepperPermissions`); the content must be 64 hex digits.
    /// On Windows the ACL is not checked: a `tracing::warn!` at startup says so ("the
    /// pepper file's ACL is not checked on Windows: keep the server directory private"),
    /// documented in `docs/accounts.md`.
    ///
    /// Losing this file locks every account out (there is no recovery by design): back it up
    /// with the journal key.
    ///
    /// # Errors
    /// `PepperPermissions` (readable by others); `PepperUnusable` (a symbolic link, not 64
    /// hex digits, cannot be read or created). Neither message contains the key.
    pub fn load_or_create(path: &Path) -> Result<Pepper, SecurityError> {
        Pepper::open(path, true)
    }

    /// [`Pepper::load_or_create`], creating a missing file only when `may_create` (a fresh
    /// installation: no account and no enrolment code stored). Otherwise a missing file is
    /// refused: a new pepper would orphan every account (security review of step R1).
    ///
    /// # Errors
    /// As [`Pepper::load_or_create`]; `PepperUnusable` for a missing file when not allowed.
    pub fn open(path: &Path, may_create: bool) -> Result<Pepper, SecurityError> {
        let shown = path.display().to_string();
        let unusable = |reason: String| SecurityError::PepperUnusable {
            path: shown.clone(),
            reason,
        };
        match std::fs::symlink_metadata(path) {
            Ok(meta) if meta.file_type().is_symlink() => {
                return Err(unusable("it is a symbolic link".to_owned()));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound && !may_create => {
                return Err(unusable(
                    "the file is missing but the database already has accounts".to_owned(),
                ));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                create_pepper_file(path).map_err(|error| unusable(error.to_string()))?;
            }
            Err(error) => return Err(unusable(error.to_string())),
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt as _;
            let meta = std::fs::metadata(path).map_err(|error| unusable(error.to_string()))?;
            if meta.permissions().mode() & 0o077 != 0 {
                return Err(SecurityError::PepperPermissions { path: shown });
            }
        }
        #[cfg(not(unix))]
        tracing::warn!(
            "the pepper file's ACL is not checked on Windows: keep the server directory private"
        );
        let text = std::fs::read_to_string(path).map_err(|error| unusable(error.to_string()))?;
        let text = text.trim();
        let mut bytes = [0_u8; PEPPER_BYTES];
        let valid = text.len() == PEPPER_BYTES * 2
            && bytes.iter_mut().enumerate().all(|(index, slot)| {
                text.get(index * 2..index * 2 + 2)
                    .and_then(|pair| u8::from_str_radix(pair, 16).ok())
                    .map(|byte| *slot = byte)
                    .is_some()
            });
        if !valid {
            return Err(unusable("it is not 64 hex digits".to_owned()));
        }
        Ok(Pepper(bytes))
    }
}

/// Creates the pepper file with 32 bytes of OS randomness: `create_new` (never follows or
/// reuses a path), Unix mode `0600` at creation, the hex written and fsynced. A racing
/// creator makes it fail with `AlreadyExists`; the existing file is then loaded.
fn create_pepper_file(path: &Path) -> std::io::Result<()> {
    use std::io::Write as _;
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        std::fs::create_dir_all(parent)?;
    }
    let mut bytes = [0_u8; PEPPER_BYTES];
    getrandom::fill(&mut bytes).map_err(|error| std::io::Error::other(error.to_string()))?;
    let hex = bytes.iter().fold(String::new(), |mut out, byte| {
        use std::fmt::Write as _;
        let _infallible = write!(out, "{byte:02x}");
        out
    });
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.mode(0o600);
    }
    let mut file = match options.open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => return Ok(()),
        Err(error) => return Err(error),
    };
    file.write_all(hex.as_bytes())?;
    file.write_all(b"\n")?;
    file.sync_all()
}

impl Pepper {}

impl std::fmt::Debug for Pepper {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Pepper(***)")
    }
}

/// `HMAC-SHA256(key, message)` for a 32-byte key, built infallibly: the key is zero-padded
/// to SHA-256's 64-byte block, which is exactly what HMAC does with a key shorter than the
/// block (RFC 2104 §2), so the result equals the textbook HMAC. No error path, no fallback.
fn hmac_sha256(key: &[u8; PEPPER_BYTES], message: &[u8]) -> [u8; 32] {
    let mut block = hmac::digest::Key::<Hmac<Sha256>>::default();
    for (slot, byte) in block.iter_mut().zip(key) {
        *slot = *byte;
    }
    let mut mac = <Hmac<Sha256> as KeyInit>::new(&block);
    mac.update(message);
    mac.finalize().into_bytes().into()
}

/// `account_id = HMAC-SHA256(pepper, account_key)`.
#[must_use]
pub fn account_id(pepper: &Pepper, key: &AccountKey) -> AccountId {
    AccountId::from_bytes(hmac_sha256(&pepper.0, key.expose()))
}

/// What is stored for an enrolment code: `HMAC-SHA256(pepper, "enrol:" + canonical code)`.
#[must_use]
pub fn enrolment_code_hash(pepper: &Pepper, code: &EnrolmentCode) -> [u8; 32] {
    let message = format!("enrol:{}", code.canonical());
    hmac_sha256(&pepper.0, message.as_bytes())
}

/// Compares two byte strings without stopping at the first difference (the time depends on
/// the length only).
#[must_use]
pub fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0_u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

#[cfg(test)]
mod tests {
    use super::{Pepper, account_id, constant_time_eq, derive_account_key};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    /// The first test vector of `docs/accounts.md` (also checked against the document by
    /// `tests/accounts.rs::derivation_test_vector_matches_docs`).
    #[test]
    fn reference_derivation_matches_the_published_vector() -> TestResult {
        let key = derive_account_key(
            "Nurse.Example",
            "correct horse battery staple",
            &"demo-clinic".parse()?,
        );
        assert_eq!(
            key.to_hex(),
            "944e5f69478ecbcb2ab4b779ae9391ac89f3c4cbebca198d82398805115f993d"
        );
        Ok(())
    }

    #[test]
    fn the_account_id_depends_on_the_pepper() -> TestResult {
        let key = "00".repeat(32).parse()?;
        let one = account_id(&Pepper::from_bytes([1; 32]), &key);
        let two = account_id(&Pepper::from_bytes([2; 32]), &key);
        assert_ne!(one, two);
        assert_eq!(one, account_id(&Pepper::from_bytes([1; 32]), &key));
        assert_eq!(format!("{:?}", Pepper::from_bytes([1; 32])), "Pepper(***)");
        Ok(())
    }

    /// A user name and password with decomposed accents give the key of the composed ones
    /// (ruling R25; the third vector of `docs/accounts.md`).
    #[test]
    fn decomposed_accents_give_the_composed_key() -> TestResult {
        let clinic = "demo-clinic".parse()?;
        let composed = derive_account_key(
            "\u{c4}rztin.Zo\u{e9}",
            "p\u{e4}ssw\u{f6}rd-\u{3bb}",
            &clinic,
        );
        let decomposed = derive_account_key(
            "A\u{308}rztin.Zoe\u{301}",
            "pa\u{308}sswo\u{308}rd-\u{3bb}",
            &clinic,
        );
        assert_eq!(composed.to_hex(), decomposed.to_hex());
        Ok(())
    }

    /// The infallible (zero-padded key) HMAC equals the crate's slice constructor for a
    /// 32-byte key.
    #[test]
    fn padded_key_hmac_equals_the_slice_constructor() -> TestResult {
        use hmac::{KeyInit as _, Mac as _};
        let key = [7_u8; 32];
        let mut reference = hmac::Hmac::<sha2::Sha256>::new_from_slice(&key)?;
        reference.update(b"message");
        let expected: [u8; 32] = reference.finalize().into_bytes().into();
        assert_eq!(super::hmac_sha256(&key, b"message"), expected);
        Ok(())
    }

    #[test]
    fn constant_time_eq_compares_whole_strings() {
        assert!(constant_time_eq(b"abc", b"abc"));
        assert!(!constant_time_eq(b"abc", b"abd"));
        assert!(!constant_time_eq(b"abc", b"abcd"));
    }
}
