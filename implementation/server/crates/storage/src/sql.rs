//! Small helpers shared by the repositories: time text, enum text, error mapping.

use chrono::{DateTime, SecondsFormat, Utc};
use domain::DomainError;
use serde::Serialize;
use serde::de::DeserializeOwned;

use crate::error::StorageError;

/// A time as stored: RFC 3339 UTC with microseconds, so text order is time order.
pub(crate) fn ts(at: DateTime<Utc>) -> String {
    at.to_rfc3339_opts(SecondsFormat::Micros, true)
}

/// Reads a stored time back.
pub(crate) fn parse_ts(table: &'static str, text: &str) -> Result<DateTime<Utc>, DomainError> {
    DateTime::parse_from_rfc3339(text)
        .map(|at| at.with_timezone(&Utc))
        .map_err(|_| corrupt(table, "a time"))
}

/// Reads an optional stored time back.
pub(crate) fn parse_opt_ts(
    table: &'static str,
    text: Option<String>,
) -> Result<Option<DateTime<Utc>>, DomainError> {
    text.map(|t| parse_ts(table, &t)).transpose()
}

/// The serde name of a unit enum value (`snake_case`).
pub(crate) fn enum_text<T: Serialize>(value: &T) -> Result<String, DomainError> {
    match serde_json::to_value(value) {
        Ok(serde_json::Value::String(text)) => Ok(text),
        _ => Err(corrupt("enum", "a value has no text form")),
    }
}

/// Parses a serde name back into a unit enum value.
pub(crate) fn parse_enum<T: DeserializeOwned>(
    table: &'static str,
    text: &str,
) -> Result<T, DomainError> {
    serde_json::from_value(serde_json::Value::String(text.to_owned()))
        .map_err(|_| corrupt(table, "an unknown enum value"))
}

/// Parses a stored id (any `FromStr` id newtype).
pub(crate) fn parse_id<T: std::str::FromStr>(
    table: &'static str,
    text: &str,
) -> Result<T, DomainError> {
    text.parse().map_err(|_| corrupt(table, "an id"))
}

/// `Corrupt` for `table`.
pub(crate) fn corrupt(table: &'static str, reason: &str) -> DomainError {
    DomainError::Corrupt {
        table,
        reason: reason.to_owned(),
    }
}

/// Maps a sqlx error to a domain error (no sqlx text kept).
#[allow(clippy::needless_pass_by_value)]
pub(crate) fn db(error: sqlx::Error) -> DomainError {
    StorageError::from(error).into()
}

/// An `i64` column as `u32`.
pub(crate) fn to_u32(table: &'static str, value: i64) -> Result<u32, DomainError> {
    u32::try_from(value).map_err(|_| corrupt(table, "a count out of range"))
}
