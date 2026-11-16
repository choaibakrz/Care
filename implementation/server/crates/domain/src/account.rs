//! Pseudonymous accounts (Task A7): the server never learns who a user is.
//!
//! The client derives an [`AccountKey`] from the user name, the password and the clinic's
//! account clinic id (`docs/accounts.md`, PBKDF2-HMAC-SHA256, 600 000 iterations) and sends
//! only that key. The server never stores the key either: it keeps
//! `account_id = HMAC-SHA256(pepper, account_key)` ([`AccountId`]), the pepper being a key
//! file outside the database (`security::accounts`). A stored account ([`AccountRecord`])
//! holds the id, a role, a pseudonym chosen by the user or the admin ("Nurse 7", never a real
//! name), when it was created and whether it is disabled. No user name, e-mail or real name
//! exists anywhere on the server.
//!
//! Everything that shows a user to people (task `requested_by`, tablet owners, audit actors)
//! shows the pseudonym and the short [`AccountTag`] (the first 6 hex digits of the id):
//! [`account_owner_label`].
//!
//! Inside the server an account is still a [`UserId`]: the 64 lowercase hex digits of its
//! [`AccountId`] (`AccountId::user_id`), so `Actor::User`, tokens and devices keep their
//! types.
//!
//! Parsing and formatting here are real code (pure, needed by the DTOs); what touches the
//! store or the pepper is filled by Task 8.

use std::fmt;
use std::str::FromStr;
use std::time::Duration;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use unicode_normalization::UnicodeNormalization as _;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::error::DomainError;
use crate::ids::{ClinicId, OwnerLabel, UserId};
use crate::role::Role;

/// Length of an account key and of an account id, in bytes.
pub const ACCOUNT_KEY_BYTES: usize = 32;
/// The key derivation every client implements (`docs/accounts.md`).
pub const KEY_DERIVATION_ALGORITHM: &str = "PBKDF2-HMAC-SHA256";
/// PBKDF2 iterations of the account key derivation (OWASP 2023 figure for SHA-256).
pub const KEY_DERIVATION_ITERATIONS: u32 = 600_000;
/// Hex digits of an [`AccountTag`].
pub const ACCOUNT_TAG_LEN: usize = 6;
/// Longest pseudonym, in characters: `"<pseudonym> #<tag>"` must fit an `OwnerLabel` (40).
pub const MAX_PSEUDONYM_LEN: usize = 32;
/// How long an enrolment code can be used.
pub const ENROLMENT_CODE_TTL: Duration = Duration::from_hours(24);
/// Characters of an enrolment code, without the dashes.
pub const ENROLMENT_CODE_LEN: usize = 12;
/// The alphabet of enrolment codes: Crockford base 32 (no I, L, O, U).
pub const ENROLMENT_CODE_ALPHABET: &[u8; 32] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/// The salt of the account key derivation:
/// `"clinic:" + clinic_id + ":" + lowercase(NFC(username))`, UTF-8.
///
/// `NFC` is Unicode normalisation form C (ruling R25: a decomposed "é" typed on one keyboard
/// gives the same key as the composed one typed on another; JavaScript
/// `String.prototype.normalize("NFC")`, Dart `unorm_dart` `nfc`); `lowercase` is then the
/// Unicode default lower-case mapping (Rust `str::to_lowercase`, JavaScript
/// `String.prototype.toLowerCase`, Dart `String.toLowerCase`). Nothing is trimmed (clients
/// trim the input field before deriving).
#[must_use]
pub fn derivation_salt(clinic: &ClinicId, username: &str) -> String {
    let composed: String = username.nfc().collect();
    format!("clinic:{clinic}:{}", composed.to_lowercase())
}

/// The password as the derivation reads it: its Unicode NFC form (ruling R25), nothing
/// trimmed. Its UTF-8 bytes are the PBKDF2 password.
#[must_use]
pub fn derivation_password(password: &str) -> String {
    password.nfc().collect()
}

/// Lowercase hex of some bytes.
fn to_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        for nibble in [byte >> 4, byte & 0x0f] {
            if let Some(digit) = DIGITS.get(usize::from(nibble)) {
                out.push(char::from(*digit));
            }
        }
    }
    out
}

/// Parses exactly 64 lowercase hex digits.
fn parse_hex_32(value: &str) -> Option<[u8; ACCOUNT_KEY_BYTES]> {
    fn digit(c: u8) -> Option<u8> {
        match c {
            b'0'..=b'9' => Some(c - b'0'),
            b'a'..=b'f' => Some(c - b'a' + 10),
            _ => None,
        }
    }
    let raw = value.as_bytes();
    if raw.len() != ACCOUNT_KEY_BYTES * 2 {
        return None;
    }
    let mut out = [0_u8; ACCOUNT_KEY_BYTES];
    for (slot, pair) in out.iter_mut().zip(raw.chunks_exact(2)) {
        let (high, low) = match pair {
            [high, low] => (digit(*high)?, digit(*low)?),
            _ => return None,
        };
        *slot = (high << 4) | low;
    }
    Some(out)
}

/// The key a client derives from user name, password and clinic, sent at login and at
/// enrolment. Password-equivalent: never stored, logged, journaled or echoed. `Debug` prints
/// `AccountKey(***)`; there is no `Display`, no `Serialize`, no `PartialEq` (compare
/// account ids, in constant time, instead) and no `Clone` (a key is read once from a request
/// and turned into an account id; no copy of it lingers).
///
/// Wire form: 64 lowercase hex characters.
#[derive(ToSchema)]
#[schema(
    value_type = String,
    format = "hex",
    min_length = 64,
    max_length = 64,
    pattern = "^[0-9a-f]{64}$"
)]
pub struct AccountKey([u8; ACCOUNT_KEY_BYTES]);

impl AccountKey {
    /// A key from its bytes (the derivation's output).
    #[must_use]
    pub fn from_bytes(bytes: [u8; ACCOUNT_KEY_BYTES]) -> AccountKey {
        AccountKey(bytes)
    }

    /// The bytes, for the pepper HMAC only.
    #[must_use]
    pub fn expose(&self) -> &[u8; ACCOUNT_KEY_BYTES] {
        &self.0
    }

    /// The wire form (64 lowercase hex). For clients and tests; never log it.
    #[must_use]
    pub fn to_hex(&self) -> String {
        to_hex(&self.0)
    }
}

impl fmt::Debug for AccountKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("AccountKey(***)")
    }
}

impl FromStr for AccountKey {
    type Err = DomainError;

    /// # Errors
    /// `InvalidAccountInput` (field `account_key`) unless exactly 64 lowercase hex digits;
    /// the message never repeats the value.
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        parse_hex_32(value)
            .map(AccountKey)
            .ok_or(DomainError::InvalidAccountInput {
                field: "account_key",
                reason: "it must be exactly 64 lowercase hex characters (32 bytes)",
            })
    }
}

impl<'de> Deserialize<'de> for AccountKey {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let raw = String::deserialize(deserializer)?;
        // A fixed message: serde would otherwise quote the value.
        raw.parse().map_err(|_| {
            serde::de::Error::custom(
                "account_key must be exactly 64 lowercase hex characters (32 bytes)",
            )
        })
    }
}

/// `HMAC-SHA256(pepper, account_key)`: the index of an account and of everything tied to
/// it. Says nothing about the person; without the pepper it cannot be recomputed from a
/// guessed password. Wire and storage form: 64 lowercase hex.
#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct AccountId([u8; ACCOUNT_KEY_BYTES]);

impl AccountId {
    /// An id from its bytes (the HMAC output).
    #[must_use]
    pub fn from_bytes(bytes: [u8; ACCOUNT_KEY_BYTES]) -> AccountId {
        AccountId(bytes)
    }

    /// The bytes.
    #[must_use]
    pub fn as_bytes(&self) -> &[u8; ACCOUNT_KEY_BYTES] {
        &self.0
    }

    /// The short tag shown next to the pseudonym: the first 6 hex digits.
    #[must_use]
    pub fn tag(&self) -> AccountTag {
        let mut hex = to_hex(&self.0);
        hex.truncate(ACCOUNT_TAG_LEN);
        AccountTag(hex)
    }

    /// The account as a [`UserId`] (its 64 hex digits), the form `Actor::User`, tokens and
    /// devices carry.
    ///
    /// # Errors
    /// Never in practice: 64 lowercase hex digits are a valid id.
    pub fn user_id(&self) -> Result<UserId, DomainError> {
        self.to_string().parse()
    }

    /// The account behind a [`UserId`] of an account.
    ///
    /// # Errors
    /// `InvalidAccountInput` when the id is not 64 lowercase hex digits (a user id of
    /// another kind).
    pub fn from_user_id(user: &UserId) -> Result<AccountId, DomainError> {
        user.as_str().parse()
    }
}

impl fmt::Display for AccountId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&to_hex(&self.0))
    }
}

/// Prints the short tag only (`AccountId(3fa9c1…)`): logs and panics never carry the full id.
impl fmt::Debug for AccountId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "AccountId({}…)", self.tag())
    }
}

impl FromStr for AccountId {
    type Err = DomainError;

    /// # Errors
    /// `InvalidAccountInput` (field `account_id`) unless 64 lowercase hex digits.
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        parse_hex_32(value)
            .map(AccountId)
            .ok_or(DomainError::InvalidAccountInput {
                field: "account_id",
                reason: "it must be exactly 64 lowercase hex characters",
            })
    }
}

impl Serialize for AccountId {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for AccountId {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let raw = String::deserialize(deserializer)?;
        raw.parse().map_err(serde::de::Error::custom)
    }
}

/// The first 6 lowercase hex digits of an [`AccountId`]: shown next to the pseudonym so two
/// "Nurse 7" can be told apart, and used by the admin to disable an account
/// (`DELETE /admin/accounts/{account_tag}`). Not unique by construction (24 bits): the
/// admin routes answer 409 `ambiguous_account_tag` when two accounts share one.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, ToSchema)]
#[serde(try_from = "String", into = "String")]
#[schema(value_type = String, pattern = "^[0-9a-f]{6}$")]
pub struct AccountTag(String);

impl AccountTag {
    /// The tag as a string slice.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }

    /// Whether `id` carries this tag.
    #[must_use]
    pub fn matches(&self, id: &AccountId) -> bool {
        id.tag() == *self
    }
}

impl FromStr for AccountTag {
    type Err = DomainError;

    /// # Errors
    /// `InvalidAccountInput` (field `account_tag`) unless 6 lowercase hex digits.
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let valid = value.len() == ACCOUNT_TAG_LEN
            && value
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c));
        if valid {
            Ok(AccountTag(value.to_owned()))
        } else {
            Err(DomainError::InvalidAccountInput {
                field: "account_tag",
                reason: "it must be 6 lowercase hex characters",
            })
        }
    }
}

impl TryFrom<String> for AccountTag {
    type Error = DomainError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        value.parse()
    }
}

impl From<AccountTag> for String {
    fn from(tag: AccountTag) -> String {
        tag.0
    }
}

impl fmt::Display for AccountTag {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// Checks a pseudonym: an `OwnerLabel` of at most [`MAX_PSEUDONYM_LEN`] characters (so the
/// label with its tag fits 40), without `#` (the separator of `"<pseudonym> #<tag>"`: a
/// pseudonym "Nurse 7 #3fa9c1" would impersonate another account's tag) and without control
/// characters. The server cannot tell a real name from a pseudonym; the enrolment screen
/// says "never your real name". Real code (pure; used by the mock and Task 8).
///
/// # Errors
/// `InvalidAccountInput` (field `display_label`) when longer than 32 characters, or when it
/// contains `#` or a control character.
pub fn check_pseudonym(label: &OwnerLabel) -> Result<(), DomainError> {
    let text = label.as_str();
    let reason = if text.chars().count() > MAX_PSEUDONYM_LEN {
        Some("it must be at most 32 characters")
    } else if text.contains('#') {
        Some("it must not contain '#' (it separates the pseudonym from the account tag)")
    } else if text.chars().any(char::is_control) {
        Some("it must not contain a control character")
    } else {
        None
    };
    match reason {
        Some(reason) => Err(DomainError::InvalidAccountInput {
            field: "display_label",
            reason,
        }),
        None => Ok(()),
    }
}

/// The owner label of an account as people see it: `"<pseudonym> #<tag>"`, for example
/// `"Nurse 7 #3fa9c1"`. Used for task `requested_by`, tablet owners, audit actors and
/// `LoginResponse.operator`; nothing else about an account is ever shown.
///
/// # Errors
/// `InvalidOwnerLabel` should the result not be a valid label (a pseudonym longer than 32
/// characters is cut to 32 first, so in practice never).
pub fn account_owner_label(
    pseudonym: &OwnerLabel,
    tag: &AccountTag,
) -> Result<OwnerLabel, DomainError> {
    let cut: String = pseudonym.as_str().chars().take(MAX_PSEUDONYM_LEN).collect();
    OwnerLabel::new(&format!("{cut} #{tag}"))
}

/// A stored account. Nothing here identifies a person.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AccountRecord {
    /// `HMAC-SHA256(pepper, account_key)`.
    pub id: AccountId,
    /// Role, from the enrolment code.
    pub role: Role,
    /// The pseudonym ("Nurse 7"), never a real name; at most 32 characters.
    pub display_label: OwnerLabel,
    /// Enrolment time.
    pub created_at: DateTime<Utc>,
    /// A disabled account cannot log in; its tokens are revoked.
    pub disabled: bool,
}

impl AccountRecord {
    /// The short tag.
    #[must_use]
    pub fn tag(&self) -> AccountTag {
        self.id.tag()
    }

    /// The label people see: [`account_owner_label`] of the pseudonym and the tag.
    ///
    /// # Errors
    /// As [`account_owner_label`].
    pub fn owner_label(&self) -> Result<OwnerLabel, DomainError> {
        account_owner_label(&self.display_label, &self.tag())
    }
}

/// A one-time enrolment code as the admin reads it out: 12 Crockford base-32 characters,
/// shown `XXXX-XXXX-XXXX` (60 bits). Secret until used: `Debug` prints
/// `EnrolmentCode(***)`; only its HMAC is stored.
#[derive(Clone, PartialEq, Eq)]
pub struct EnrolmentCode(String);

impl EnrolmentCode {
    /// A code from 60 random bits (the low 60 bits of `bytes`).
    #[must_use]
    pub fn from_random(bytes: [u8; 8]) -> EnrolmentCode {
        let mut bits = u64::from_be_bytes(bytes);
        let mut chars = [b'0'; ENROLMENT_CODE_LEN];
        for slot in chars.iter_mut().rev() {
            let index = usize::try_from(bits & 0x1f).unwrap_or(0);
            *slot = ENROLMENT_CODE_ALPHABET.get(index).copied().unwrap_or(b'0');
            bits >>= 5;
        }
        EnrolmentCode(chars.iter().map(|c| char::from(*c)).collect())
    }

    /// The canonical form (12 characters, no dashes), the input of the code's HMAC.
    #[must_use]
    pub fn canonical(&self) -> &str {
        &self.0
    }

    /// The form shown to people: `XXXX-XXXX-XXXX`.
    #[must_use]
    pub fn display(&self) -> String {
        let mut out = String::with_capacity(ENROLMENT_CODE_LEN + 2);
        for (index, c) in self.0.chars().enumerate() {
            if index > 0 && index % 4 == 0 {
                out.push('-');
            }
            out.push(c);
        }
        out
    }
}

impl fmt::Debug for EnrolmentCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("EnrolmentCode(***)")
    }
}

impl FromStr for EnrolmentCode {
    type Err = DomainError;

    /// Reads a typed code: dashes and spaces are ignored, letters are upper-cased, and the
    /// Crockford look-alikes are mapped (`I`/`L` → `1`, `O` → `0`).
    ///
    /// # Errors
    /// `InvalidAccountInput` (field `enrolment_code`) unless 12 characters of the alphabet
    /// remain; the message never repeats the value.
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let canonical: String = value
            .chars()
            .filter(|c| *c != '-' && !c.is_whitespace())
            .map(|c| match c.to_ascii_uppercase() {
                'I' | 'L' => '1',
                'O' => '0',
                other => other,
            })
            .collect();
        let valid = canonical.len() == ENROLMENT_CODE_LEN
            && canonical
                .bytes()
                .all(|c| ENROLMENT_CODE_ALPHABET.contains(&c));
        if valid {
            Ok(EnrolmentCode(canonical))
        } else {
            Err(DomainError::InvalidAccountInput {
                field: "enrolment_code",
                reason: "it must be 12 letters and digits, shown as XXXX-XXXX-XXXX",
            })
        }
    }
}

impl<'de> Deserialize<'de> for EnrolmentCode {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let raw = String::deserialize(deserializer)?;
        raw.parse().map_err(|_| {
            serde::de::Error::custom(
                "enrolment_code must be 12 letters and digits, shown as XXXX-XXXX-XXXX",
            )
        })
    }
}

/// A stored enrolment code: only `HMAC-SHA256(pepper, "enrol:" + canonical code)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnrolmentRecord {
    /// Id (journaled instead of the code).
    pub id: Uuid,
    /// HMAC of the code.
    pub code_hash: [u8; 32],
    /// Role the new account gets.
    pub role: Role,
    /// The pseudonym the admin suggested, if any.
    pub suggested_label: Option<OwnerLabel>,
    /// Issue time.
    pub created_at: DateTime<Utc>,
    /// After this the code is refused (`created_at` + 24 h).
    pub expires_at: DateTime<Utc>,
    /// When it was used; a used code is refused.
    pub used_at: Option<DateTime<Utc>>,
}

/// What a successful enrolment stored.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AccountEnrolment {
    /// The new account.
    pub account: AccountRecord,
    /// The code that was used (journaled by id only).
    pub code_id: Uuid,
}

#[cfg(test)]
mod tests {
    use super::{AccountId, AccountKey, AccountTag, EnrolmentCode, derivation_salt};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    const HEX: &str = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";

    #[test]
    fn account_key_parses_64_lowercase_hex_and_never_prints_itself() -> TestResult {
        let key: AccountKey = HEX.parse()?;
        assert_eq!(key.to_hex(), HEX);
        assert_eq!(format!("{key:?}"), "AccountKey(***)");
        assert!(HEX.to_uppercase().parse::<AccountKey>().is_err());
        assert!(HEX.get(..62).ok_or("short")?.parse::<AccountKey>().is_err());
        let error = "zz"
            .repeat(32)
            .parse::<AccountKey>()
            .err()
            .ok_or("accepted")?;
        assert!(!error.to_string().contains("zz"), "{error}");
        Ok(())
    }

    #[test]
    fn serde_error_of_a_bad_key_does_not_quote_it() -> TestResult {
        let secret = "secret-password-typed-by-mistake";
        let error = serde_json::from_value::<AccountKey>(serde_json::json!(secret))
            .err()
            .ok_or("accepted")?;
        assert!(!error.to_string().contains(secret), "{error}");
        Ok(())
    }

    #[test]
    fn account_id_round_trips_and_gives_its_tag_and_user_id() -> TestResult {
        let id: AccountId = HEX.parse()?;
        assert_eq!(id.to_string(), HEX);
        assert_eq!(id.tag(), "001122".parse::<AccountTag>()?);
        let user = id.user_id()?;
        assert_eq!(AccountId::from_user_id(&user)?, id);
        assert!(AccountId::from_user_id(&"u-admin".parse()?).is_err());
        let json = serde_json::to_string(&id)?;
        assert_eq!(serde_json::from_str::<AccountId>(&json)?, id);
        Ok(())
    }

    #[test]
    fn account_tag_is_six_lowercase_hex() {
        assert!("3fa9c1".parse::<AccountTag>().is_ok());
        assert!("3FA9C1".parse::<AccountTag>().is_err());
        assert!("3fa9c".parse::<AccountTag>().is_err());
        assert!("3fa9cg".parse::<AccountTag>().is_err());
    }

    #[test]
    fn enrolment_code_reads_typed_forms_and_hides_itself() -> TestResult {
        let code = EnrolmentCode::from_random([0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0]);
        assert_eq!(code.canonical().len(), 12);
        let typed = code.display().to_lowercase().replace('-', " ");
        assert_eq!(typed.parse::<EnrolmentCode>()?, code);
        assert_eq!(format!("{code:?}"), "EnrolmentCode(***)");
        assert_eq!(
            "oooo-iiii-llll".parse::<EnrolmentCode>()?.canonical(),
            "000011111111"
        );
        assert!("ABCD-EFGH".parse::<EnrolmentCode>().is_err());
        Ok(())
    }

    #[test]
    fn pseudonym_refuses_hash_control_characters_and_length() -> TestResult {
        use super::check_pseudonym;
        use crate::ids::OwnerLabel;
        assert!(check_pseudonym(&OwnerLabel::new("Nurse 7")?).is_ok());
        assert!(check_pseudonym(&OwnerLabel::new("Nurse 7 #3fa9c1")?).is_err());
        assert!(check_pseudonym(&OwnerLabel::new("#1")?).is_err());
        assert!(check_pseudonym(&OwnerLabel::new(&"n".repeat(33))?).is_err());
        assert!(check_pseudonym(&OwnerLabel::new(&"n".repeat(32))?).is_ok());
        // `OwnerLabel` already refuses control characters.
        assert!(OwnerLabel::new("Nurse\u{7}7").is_err());
        Ok(())
    }

    #[test]
    fn account_id_debug_prints_the_tag_only() -> TestResult {
        let id: AccountId = HEX.parse()?;
        assert_eq!(format!("{id:?}"), "AccountId(001122…)");
        Ok(())
    }

    #[test]
    fn salt_and_password_are_nfc_so_decomposed_letters_match() -> TestResult {
        use super::derivation_password;
        let clinic = "demo-clinic".parse()?;
        assert_eq!(
            derivation_salt(&clinic, "Zoe\u{301}"),
            derivation_salt(&clinic, "Zo\u{e9}")
        );
        assert_eq!(derivation_password("pa\u{308}ss"), "p\u{e4}ss");
        Ok(())
    }

    #[test]
    fn salt_lowercases_the_user_name_only() -> TestResult {
        assert_eq!(
            derivation_salt(&"demo-clinic".parse()?, "Nurse.Example"),
            "clinic:demo-clinic:nurse.example"
        );
        Ok(())
    }
}
