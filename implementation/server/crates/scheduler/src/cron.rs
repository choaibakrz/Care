//! Five-field cron expressions (minute hour day-of-month month day-of-week).
//!
//! The parsed form is our own (sets of allowed values) so errors name the failing field.
//! Task 17 may delegate `next_after` to a cron crate chosen for its DST handling; the fields are
//! private, so that choice does not change this API.

use std::collections::BTreeSet;
use std::fmt;

use chrono::{
    DateTime, Datelike, Duration, LocalResult, NaiveDate, NaiveDateTime, TimeZone, Timelike, Utc,
};
use chrono_tz::Tz;

use crate::error::SchedulerError;

/// A parsed cron expression.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CronExpr {
    source: String,
    minutes: BTreeSet<u8>,
    hours: BTreeSet<u8>,
    days_of_month: BTreeSet<u8>,
    months: BTreeSet<u8>,
    days_of_week: BTreeSet<u8>,
}

impl CronExpr {
    /// Parses `*`, lists, ranges and steps in each of the five fields.
    ///
    /// # Errors
    /// `FieldCount`; `InvalidCron` naming the field ("Field 'hour' has value 25; hours go from
    /// 0 to 23.").
    pub fn parse(text: &str) -> Result<CronExpr, SchedulerError> {
        let fields: Vec<&str> = text.split_whitespace().collect();
        let [minute, hour, dom, month, dow] = fields.as_slice() else {
            return Err(SchedulerError::FieldCount { have: fields.len() });
        };
        let mut days_of_week = parse_field(dow, &DAY_OF_WEEK)?;
        // 7 is Sunday too.
        if days_of_week.remove(&7) {
            days_of_week.insert(0);
        }
        Ok(CronExpr {
            source: text.trim().to_owned(),
            minutes: parse_field(minute, &MINUTE)?,
            hours: parse_field(hour, &HOUR)?,
            days_of_month: parse_field(dom, &DAY_OF_MONTH)?,
            months: parse_field(month, &MONTH)?,
            days_of_week,
        })
    }

    /// The next fire time strictly after `after`, evaluated in `tz` (DST aware).
    #[must_use]
    pub fn next_after(&self, after: DateTime<Utc>, tz: Tz) -> Option<DateTime<Utc>> {
        let start = after.with_timezone(&tz).naive_local();
        // Next whole minute after `after`, in local wall-clock time.
        let mut naive = start
            .with_second(0)
            .and_then(|t| t.with_nanosecond(0))?
            .checked_add_signed(Duration::minutes(1))?;
        // Five years of wall-clock time is enough for any valid expression.
        let limit = start.checked_add_signed(Duration::days(5 * 366))?;
        while naive <= limit {
            if !self.months.contains(&month_u8(naive.date())) || !self.day_matches(naive.date()) {
                naive = naive.date().succ_opt()?.and_hms_opt(0, 0, 0)?;
                continue;
            }
            if !self.hours.contains(&hour_u8(naive)) {
                naive = naive
                    .with_minute(0)?
                    .checked_add_signed(Duration::hours(1))?;
                continue;
            }
            if !self.minutes.contains(&minute_u8(naive)) {
                naive = naive.checked_add_signed(Duration::minutes(1))?;
                continue;
            }
            match tz.from_local_datetime(&naive) {
                LocalResult::Single(at) => {
                    let at = at.with_timezone(&Utc);
                    if at > after {
                        return Some(at);
                    }
                }
                // Repeated wall-clock time (fall back): fire once, at the first occurrence. If
                // that is already past, the run happened and the second occurrence is skipped.
                LocalResult::Ambiguous(first, _) => {
                    let first = first.with_timezone(&Utc);
                    if first > after {
                        return Some(first);
                    }
                }
                // Wall-clock time skipped (spring forward): fire at the next valid minute.
                LocalResult::None => {
                    let mut probe = naive;
                    for _ in 0..(24 * 60) {
                        probe = probe.checked_add_signed(Duration::minutes(1))?;
                        if let Some(at) = tz.from_local_datetime(&probe).earliest() {
                            let at = at.with_timezone(&Utc);
                            if at > after {
                                return Some(at);
                            }
                            break;
                        }
                    }
                }
            }
            naive = naive.checked_add_signed(Duration::minutes(1))?;
        }
        None
    }

    /// The original text.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.source
    }
}

impl fmt::Display for CronExpr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.source)
    }
}

impl CronExpr {
    /// Standard cron rule: when both day fields are restricted, either may match.
    fn day_matches(&self, date: NaiveDate) -> bool {
        let month_day_restricted = self.days_of_month.len() < usize::from(DAY_OF_MONTH.max);
        let week_day_restricted = self.days_of_week.len() < 7;
        let month_day = self.days_of_month.contains(&day_u8(date));
        let week_day = self.days_of_week.contains(&weekday_u8(date));
        match (month_day_restricted, week_day_restricted) {
            (true, true) => month_day || week_day,
            (true, false) => month_day,
            (false, true) => week_day,
            (false, false) => true,
        }
    }
}

fn month_u8(date: NaiveDate) -> u8 {
    u8::try_from(date.month()).unwrap_or(u8::MAX)
}

fn day_u8(date: NaiveDate) -> u8 {
    u8::try_from(date.day()).unwrap_or(u8::MAX)
}

fn weekday_u8(date: NaiveDate) -> u8 {
    u8::try_from(date.weekday().num_days_from_sunday()).unwrap_or(u8::MAX)
}

fn hour_u8(time: NaiveDateTime) -> u8 {
    u8::try_from(time.hour()).unwrap_or(u8::MAX)
}

fn minute_u8(time: NaiveDateTime) -> u8 {
    u8::try_from(time.minute()).unwrap_or(u8::MAX)
}

/// Name, unit and range of one cron field.
struct FieldSpec {
    name: &'static str,
    unit: &'static str,
    min: u8,
    max: u8,
}

const MINUTE: FieldSpec = FieldSpec {
    name: "minute",
    unit: "minutes",
    min: 0,
    max: 59,
};
const HOUR: FieldSpec = FieldSpec {
    name: "hour",
    unit: "hours",
    min: 0,
    max: 23,
};
const DAY_OF_MONTH: FieldSpec = FieldSpec {
    name: "day-of-month",
    unit: "days of the month",
    min: 1,
    max: 31,
};
const MONTH: FieldSpec = FieldSpec {
    name: "month",
    unit: "months",
    min: 1,
    max: 12,
};
const DAY_OF_WEEK: FieldSpec = FieldSpec {
    name: "day-of-week",
    unit: "days of the week",
    min: 0,
    max: 7,
};

/// Parses one field: `*`, `a`, `a-b`, any of them with `/step`, comma separated.
fn parse_field(text: &str, spec: &FieldSpec) -> Result<BTreeSet<u8>, SchedulerError> {
    let invalid = |value: &str| SchedulerError::InvalidCron {
        field: spec.name,
        value: value.to_owned(),
        unit: spec.unit,
        min: spec.min,
        max: spec.max,
    };
    let number = |value: &str| -> Result<u8, SchedulerError> {
        let n: u8 = value.parse().map_err(|_| invalid(value))?;
        if n < spec.min || n > spec.max {
            return Err(invalid(value));
        }
        Ok(n)
    };
    let mut values = BTreeSet::new();
    for part in text.split(',') {
        let (range, step) = match part.split_once('/') {
            Some((range, step)) => {
                let step: u8 = step.parse().map_err(|_| invalid(part))?;
                if step == 0 {
                    return Err(invalid(part));
                }
                (range, Some(step))
            }
            None => (part, None),
        };
        let (low, high) = if range == "*" {
            (spec.min, spec.max)
        } else if let Some((low, high)) = range.split_once('-') {
            (number(low)?, number(high)?)
        } else {
            let low = number(range)?;
            // `a/n` runs from `a` to the end of the range.
            (low, if step.is_some() { spec.max } else { low })
        };
        if low > high {
            return Err(invalid(part));
        }
        let step = usize::from(step.unwrap_or(1));
        values.extend((low..=high).step_by(step));
    }
    Ok(values)
}
