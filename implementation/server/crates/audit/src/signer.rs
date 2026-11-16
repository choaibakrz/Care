//! Seal signing with an Ed25519 key kept outside the journal directory.

use std::path::Path;

use ed25519_dalek::{SigningKey, VerifyingKey};
use serde::{Deserialize, Serialize};

use crate::error::JournalError;
use crate::record::hex_bytes::{from_hex, to_hex};

/// An Ed25519 signature, serialised as hex.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Signature(#[serde(with = "crate::record::hex_bytes")] pub [u8; 64]);

/// Signs seals.
pub trait Signer: Send + Sync {
    /// Signs a message.
    ///
    /// # Errors
    /// `Signature`.
    fn sign(&self, msg: &[u8]) -> Result<Signature, JournalError>;
    /// Short fingerprint of the public key.
    fn fingerprint(&self) -> String;
}

/// A signer whose key lives in a file. The key is created on first start; a key readable by
/// other users is refused with an explicit message.
pub struct Ed25519FileSigner {
    key: SigningKey,
    fingerprint: String,
}

impl Ed25519FileSigner {
    /// Loads (or creates) the key; also writes `<path>.pub` for `journal verify`.
    ///
    /// # Errors
    /// `KeyPermissions`; `KeyInvalid`; `Io`.
    pub fn load(path: &Path) -> Result<Ed25519FileSigner, JournalError> {
        let io = |action: &'static str| {
            let path = path.to_path_buf();
            move |source: std::io::Error| JournalError::Io {
                action,
                path,
                source,
            }
        };
        if !path.exists() {
            if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
                std::fs::create_dir_all(parent).map_err(io("create the key directory"))?;
            }
            let mut seed = [0_u8; 32];
            getrandom::fill(&mut seed).map_err(|error| JournalError::KeyInvalid {
                path: path.to_path_buf(),
                reason: format!("no OS randomness to create it: {error}"),
            })?;
            write_new_private(path, &to_hex(&seed)).map_err(io("create the signing key"))?;
        }
        check_private(path)?;
        let text = std::fs::read_to_string(path).map_err(io("read the signing key"))?;
        let seed = from_hex::<32>(&text).ok_or_else(|| JournalError::KeyInvalid {
            path: path.to_path_buf(),
            reason: "expected 64 hex digits".to_owned(),
        })?;
        let key = SigningKey::from_bytes(&seed);
        let public = key.verifying_key();
        let fingerprint = fingerprint_of(&public);
        let pub_path = public_key_path(path);
        let public_hex = to_hex(public.as_bytes());
        match std::fs::read_to_string(&pub_path) {
            // An existing public key is never overwritten: a different one means the key file
            // was replaced, and `journal verify` would then check old seals against the new key.
            Ok(current) if current.trim() != public_hex => {
                return Err(JournalError::KeyInvalid {
                    path: path.to_path_buf(),
                    reason: format!(
                        "it does not match the public key in '{}' (the key file was replaced?)",
                        pub_path.display()
                    ),
                });
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                std::fs::write(&pub_path, format!("{public_hex}\n"))
                    .map_err(io("write the public key"))?;
            }
            Err(error) => return Err(io("read the public key")(error)),
        }
        Ok(Ed25519FileSigner { key, fingerprint })
    }

    /// [`Ed25519FileSigner::load`] for the journal in `journal_dir`: a missing key is created
    /// only for a new journal (no segment yet). A journal with segments and no key refuses
    /// to start: a new key would orphan every existing seal.
    ///
    /// # Errors
    /// `KeyInvalid` when the key is missing but the journal exists; as `load`.
    pub fn open_for_journal(
        path: &Path,
        journal_dir: &Path,
    ) -> Result<Ed25519FileSigner, JournalError> {
        let has_segments =
            journal_dir.exists() && !crate::segment::segment_files(journal_dir)?.is_empty();
        if !path.exists() && has_segments {
            return Err(JournalError::KeyInvalid {
                path: path.to_path_buf(),
                reason: format!(
                    "it is missing but the journal '{}' already has records; restore the key from the backup",
                    journal_dir.display()
                ),
            });
        }
        Ed25519FileSigner::load(path)
    }

    /// The public key.
    #[must_use]
    pub fn verifying_key(&self) -> VerifyingKey {
        self.key.verifying_key()
    }
}

impl Signer for Ed25519FileSigner {
    fn sign(&self, msg: &[u8]) -> Result<Signature, JournalError> {
        use ed25519_dalek::Signer as _;
        Ok(Signature(self.key.sign(msg).to_bytes()))
    }
    fn fingerprint(&self) -> String {
        self.fingerprint.clone()
    }
}

/// Reads a public key file (`<key>.pub`, hex).
///
/// # Errors
/// `KeyInvalid`; `Io`.
pub fn load_verifying_key(path: &Path) -> Result<VerifyingKey, JournalError> {
    let text = std::fs::read_to_string(path).map_err(|source| JournalError::Io {
        action: "read the public key",
        path: path.to_path_buf(),
        source,
    })?;
    let invalid = |reason: String| JournalError::KeyInvalid {
        path: path.to_path_buf(),
        reason,
    };
    let bytes =
        from_hex::<32>(&text).ok_or_else(|| invalid("expected 64 hex digits".to_owned()))?;
    VerifyingKey::from_bytes(&bytes).map_err(|error| invalid(error.to_string()))
}

/// `<key>.pub`: where [`Ed25519FileSigner::load`] writes the public key.
#[must_use]
pub fn public_key_path(key_path: &Path) -> std::path::PathBuf {
    let mut name = key_path.as_os_str().to_owned();
    name.push(".pub");
    std::path::PathBuf::from(name)
}

/// First 16 hex digits of the SHA-256 of the public key.
fn fingerprint_of(public: &VerifyingKey) -> String {
    use sha2::Digest as _;
    let digest: [u8; 32] = sha2::Sha256::digest(public.as_bytes()).into();
    to_hex(digest.get(..8).unwrap_or(&digest))
}

/// Creates `path` (never overwriting), readable by its owner only on Unix, and writes `text`
/// with an fsync.
pub(crate) fn write_new_private(path: &Path, text: &str) -> std::io::Result<()> {
    use std::io::Write as _;
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.mode(0o600);
    }
    let mut file = options.open(path)?;
    file.write_all(text.as_bytes())?;
    file.write_all(b"\n")?;
    file.sync_all()
}

/// Refuses a key readable by other users (Unix only; on Windows the ACL is not checked).
#[cfg_attr(not(unix), allow(clippy::unnecessary_wraps, unused_variables))]
fn check_private(path: &Path) -> Result<(), JournalError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        let meta = std::fs::metadata(path).map_err(|source| JournalError::Io {
            action: "read the signing key's permissions",
            path: path.to_path_buf(),
            source,
        })?;
        if meta.permissions().mode() & 0o077 != 0 {
            return Err(JournalError::KeyPermissions {
                path: path.to_path_buf(),
            });
        }
    }
    Ok(())
}
