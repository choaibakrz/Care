//! The patient companion's dummy storage: one JSON file, loaded at start, rewritten whole
//! (temporary file, then rename) after every change, behind one async mutex.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use uuid::Uuid;

/// Where the store lives when `PATIENT_STORE` is not set (relative to the working directory,
/// next to the clinic database).
pub const DEFAULT_PATIENT_STORE: &str = "data/patients.json";

/// The store file could not be read, parsed or written.
#[derive(Debug, thiserror::Error)]
#[error("patient store {path}: {reason}")]
pub struct StoreError {
    path: String,
    reason: String,
}

/// A patient account.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct UserRecord {
    pub id: Uuid,
    pub email: Option<String>,
    pub phone: Option<String>,
    pub first_name: Option<String>,
    /// Random salt (hex) of the password key; empty for a phone-code-only account.
    pub salt: String,
    /// Password key (hex), `None` for a phone-code-only account.
    pub password_key: Option<String>,
}

/// A signed-in browser.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct SessionRecord {
    pub token: String,
    pub user_id: Uuid,
    /// Unix milliseconds.
    pub expires_at: i64,
}

/// A pending phone sign-in code.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct OtpRecord {
    pub phone: String,
    pub code: String,
    /// Unix milliseconds.
    pub expires_at: i64,
    pub failures: u32,
}

/// A question for the care team.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct QuestionRecord {
    pub id: Uuid,
    pub user_id: Uuid,
    pub text: String,
    pub created_at: i64,
}

/// A care request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct RequestRecord {
    pub id: Uuid,
    pub user_id: Uuid,
    /// Local patient date, `YYYY-MM-DD`.
    pub date: String,
    pub kind: String,
    pub status: String,
    pub status_index: u8,
    pub created_at: i64,
    pub updated_at: i64,
}

/// A mood check-in (one per patient and day, the last one wins).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct MoodRecord {
    pub user_id: Uuid,
    pub date: String,
    pub value: u8,
    pub at: i64,
}

/// A patient admitted to a room by the care team (no account, no contact details).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct RoomPatientRecord {
    pub id: Uuid,
    pub first_name: String,
    pub medical_record_ref: String,
    /// `admitted` or `discharged`.
    pub status: String,
    /// Unix milliseconds.
    pub admitted_at: i64,
    pub discharged_at: Option<i64>,
    /// The staff subject that admitted the patient.
    pub created_by: String,
}

/// A patient in a room; open while `discharged_at` is `None` (one per room, one per patient).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct RoomAssignmentRecord {
    pub id: Uuid,
    pub room_id: String,
    pub patient_id: Uuid,
    pub assigned_at: i64,
    pub discharged_at: Option<i64>,
}

/// A room tablet. Active while `revoked_at` is `None` (one per room). The room's label, wing
/// and floor are copied from the clinic map when the tablet is registered, so a paired tablet
/// keeps working while the map is edited.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct RoomDeviceRecord {
    pub id: Uuid,
    pub room_id: String,
    pub room_label: String,
    pub room_wing: String,
    pub room_floor: i32,
    pub device_label: String,
    /// Upper-case pairing code, valid until `pairing_expires_at`.
    pub pairing_code: Option<String>,
    pub pairing_expires_at: Option<i64>,
    /// Value of the room-device cookie.
    pub session_token: Option<String>,
    pub session_expires_at: Option<i64>,
    pub last_seen_at: Option<i64>,
    pub revoked_at: Option<i64>,
}

/// Everything the store holds.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub(crate) struct StoreData {
    pub users: Vec<UserRecord>,
    pub sessions: Vec<SessionRecord>,
    pub otps: Vec<OtpRecord>,
    pub questions: Vec<QuestionRecord>,
    pub requests: Vec<RequestRecord>,
    pub moods: Vec<MoodRecord>,
    pub room_patients: Vec<RoomPatientRecord>,
    pub room_assignments: Vec<RoomAssignmentRecord>,
    pub room_devices: Vec<RoomDeviceRecord>,
}

/// The JSON-file store. `None` data means the file exists but could not be loaded: every
/// call then fails (503) and the file is never overwritten.
#[derive(Debug)]
pub struct PatientStore {
    path: PathBuf,
    data: Mutex<Option<StoreData>>,
}

impl PatientStore {
    /// Loads the store at `path`; a missing file is an empty store (created on first write).
    ///
    /// # Errors
    /// When the file exists but cannot be read or is not a valid store.
    pub fn open(path: PathBuf) -> Result<PatientStore, StoreError> {
        let data = match std::fs::read(&path) {
            Ok(bytes) => {
                serde_json::from_slice(&bytes).map_err(|error| store_error(&path, &error))?
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => StoreData::default(),
            Err(error) => return Err(store_error(&path, &error)),
        };
        Ok(PatientStore {
            path,
            data: Mutex::new(Some(data)),
        })
    }

    /// [`PatientStore::open`], or an unavailable store (every call answers 503) when the
    /// file cannot be loaded; the failure is logged.
    #[must_use]
    pub fn open_or_unavailable(path: PathBuf) -> PatientStore {
        match PatientStore::open(path.clone()) {
            Ok(store) => store,
            Err(error) => {
                tracing::error!(%error, "patient store unusable; the patient API answers 503");
                PatientStore {
                    path,
                    data: Mutex::new(None),
                }
            }
        }
    }

    /// The store at `PATIENT_STORE`, or [`DEFAULT_PATIENT_STORE`].
    #[must_use]
    pub fn from_env() -> PatientStore {
        let path = std::env::var_os("PATIENT_STORE")
            .map_or_else(|| PathBuf::from(DEFAULT_PATIENT_STORE), PathBuf::from);
        PatientStore::open_or_unavailable(path)
    }

    /// Reads the store.
    pub(crate) async fn read<R>(&self, f: impl FnOnce(&StoreData) -> R) -> Result<R, StoreError> {
        let guard = self.data.lock().await;
        let data = guard.as_ref().ok_or_else(|| self.unavailable())?;
        Ok(f(data))
    }

    /// Changes the store and writes it. `f` works on a copy, so a refused change (`Ok(Err)`)
    /// or a failed write leaves the store as it was.
    pub(crate) async fn update<R, E>(
        &self,
        f: impl FnOnce(&mut StoreData) -> Result<R, E>,
    ) -> Result<Result<R, E>, StoreError> {
        let mut guard = self.data.lock().await;
        let current = guard.as_mut().ok_or_else(|| self.unavailable())?;
        let mut next = current.clone();
        let out = match f(&mut next) {
            Ok(out) => out,
            Err(refusal) => return Ok(Err(refusal)),
        };
        self.persist(&next).await?;
        *current = next;
        Ok(Ok(out))
    }

    async fn persist(&self, data: &StoreData) -> Result<(), StoreError> {
        let fail = |error: &dyn std::fmt::Display| store_error(&self.path, error);
        let bytes = serde_json::to_vec_pretty(data).map_err(|error| fail(&error))?;
        if let Some(parent) = self.path.parent()
            && !parent.as_os_str().is_empty()
        {
            tokio::fs::create_dir_all(parent)
                .await
                .map_err(|error| fail(&error))?;
        }
        let temporary = self.path.with_extension("json.tmp");
        tokio::fs::write(&temporary, bytes)
            .await
            .map_err(|error| fail(&error))?;
        tokio::fs::rename(&temporary, &self.path)
            .await
            .map_err(|error| fail(&error))
    }

    fn unavailable(&self) -> StoreError {
        store_error(&self.path, &"the file could not be loaded at start")
    }
}

fn store_error(path: &Path, reason: &dyn std::fmt::Display) -> StoreError {
    StoreError {
        path: path.display().to_string(),
        reason: reason.to_string(),
    }
}
