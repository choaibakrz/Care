//! Task 15: the in-memory stock ledger (same trait as `storage::SqliteLedger`).
//!
//! `stock_never_negative_under_random_sequences` is a model-based random test driven by a
//! seeded SplitMix64 generator (200 seeds × 60 operations) rather than proptest, so it adds
//! no dependency; Task 15 may switch it to proptest.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use chrono::{TimeZone, Utc};
use domain::{
    Clock, FakeClock, ItemId, ReconcileOutcome, SeenItem, StockError, StockLedger, TaskId,
};
use optimization::InMemoryLedger;

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn clock() -> Result<Arc<FakeClock>, BoxError> {
    Ok(Arc::new(FakeClock::new(
        Utc.with_ymd_and_hms(2026, 11, 14, 8, 0, 0)
            .single()
            .ok_or("bad test date")?,
    )))
}

fn ledger(clock: &Arc<FakeClock>, items: &[(&str, u32)]) -> Result<InMemoryLedger, BoxError> {
    let dyn_clock: Arc<dyn Clock> = clock.clone();
    let stock = items
        .iter()
        .map(|(item, count)| Ok((item.parse::<ItemId>()?, *count)))
        .collect::<Result<HashMap<_, _>, BoxError>>()?;
    Ok(InMemoryLedger::new(dyn_clock, stock))
}

fn task(n: u32) -> Result<TaskId, BoxError> {
    Ok(format!("t-{n}").parse()?)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn two_tasks_one_unit_exactly_one_wins() -> TestResult {
    let blanket: ItemId = "blanket".parse()?;
    for round in 0..50 {
        let clock = clock()?;
        let ledger = Arc::new(ledger(&clock, &[("blanket", 1)])?);
        let (a, b) = (task(2 * round)?, task(2 * round + 1)?);
        let (first, second) = tokio::join!(
            ledger.reserve(&a, &blanket, 1),
            ledger.reserve(&b, &blanket, 1)
        );
        let wins = usize::from(first.is_ok()) + usize::from(second.is_ok());
        assert_eq!(wins, 1, "round {round}: {first:?} / {second:?}");
        let loser = first.err().or(second.err()).ok_or("no loser")?;
        assert!(matches!(loser, StockError::OutOfStock { .. }), "{loser:?}");
    }
    Ok(())
}

/// SplitMix64: a tiny deterministic generator for the random sequences.
struct SplitMix64(u64);

impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn below(&mut self, n: u64) -> u64 {
        self.next() % n.max(1)
    }
}

#[tokio::test]
async fn stock_never_negative_under_random_sequences() -> TestResult {
    let blanket: ItemId = "blanket".parse()?;
    for seed in 0..200_u64 {
        let initial = 5_u32;
        let clock = clock()?;
        let ledger = ledger(&clock, &[("blanket", initial)])?;
        let mut rng = SplitMix64(seed);
        // Model: units committed (gone) and active reservations.
        let mut committed = 0_u32;
        let mut active = Vec::new();
        for step in 0..60_u32 {
            match rng.below(3) {
                0 => {
                    let qty = u32::try_from(rng.below(3) + 1)?;
                    let reserved: u32 = active.iter().map(|r: &domain::Reservation| r.qty).sum();
                    let free = initial - committed - reserved;
                    let result = ledger.reserve(&task(step)?, &blanket, qty).await;
                    if qty <= free {
                        active.push(result?);
                    } else {
                        match result {
                            Err(StockError::OutOfStock {
                                available,
                                reserved: held,
                                ..
                            }) => {
                                assert_eq!(available, free, "seed {seed} step {step}");
                                assert_eq!(held, reserved, "seed {seed} step {step}");
                            }
                            other => {
                                return Err(format!(
                                    "seed {seed} step {step}: expected OutOfStock, got {other:?}"
                                )
                                .into());
                            }
                        }
                    }
                }
                1 if !active.is_empty() => {
                    let index = usize::try_from(rng.below(active.len() as u64))?;
                    let reservation = active.swap_remove(index);
                    ledger.commit(&reservation).await?;
                    committed += reservation.qty;
                }
                _ if !active.is_empty() => {
                    let index = usize::try_from(rng.below(active.len() as u64))?;
                    let reservation = active.swap_remove(index);
                    ledger.release(&reservation).await?;
                }
                _ => {}
            }
            assert!(committed <= initial, "seed {seed}: stock went negative");
        }
    }
    Ok(())
}

#[tokio::test]
async fn release_makes_unit_available_again() -> TestResult {
    let clock = clock()?;
    let ledger = ledger(&clock, &[("blanket", 1)])?;
    let blanket: ItemId = "blanket".parse()?;
    let held = ledger.reserve(&task(1)?, &blanket, 1).await?;
    assert!(ledger.reserve(&task(2)?, &blanket, 1).await.is_err());
    ledger.release(&held).await?;
    ledger.reserve(&task(2)?, &blanket, 1).await?;
    Ok(())
}

#[tokio::test]
async fn expired_reservation_is_released() -> TestResult {
    let clock = clock()?;
    let ledger = ledger(&clock, &[("blanket", 1)])?;
    let blanket: ItemId = "blanket".parse()?;
    let held = ledger.reserve(&task(1)?, &blanket, 1).await?;
    clock.advance(Duration::from_mins(31));
    assert_eq!(ledger.expire_older_than(Duration::from_mins(30)).await?, 1);
    ledger.reserve(&task(2)?, &blanket, 1).await?;
    let gone = ledger
        .commit(&held)
        .await
        .err()
        .ok_or("an expired reservation was committed")?;
    assert!(
        matches!(gone, StockError::ReservationGone { .. }),
        "{gone:?}"
    );
    Ok(())
}

#[tokio::test]
async fn uncertain_count_never_overwrites_stock() -> TestResult {
    let clock = clock()?;
    let ledger = ledger(&clock, &[("blanket", 3), ("neck-cushion", 2)])?;
    let seen = [
        SeenItem {
            item: "blanket".parse()?,
            count: Some(0),
            uncertain: true,
        },
        SeenItem {
            item: "neck-cushion".parse()?,
            count: None,
            uncertain: false,
        },
    ];
    let outcomes = ledger.reconcile(&"storeroom".parse()?, &seen).await?;
    assert_eq!(
        outcomes,
        vec![
            ReconcileOutcome::Uncertain {
                item: "blanket".parse()?
            },
            ReconcileOutcome::Uncertain {
                item: "neck-cushion".parse()?
            },
        ]
    );
    ledger.reserve(&task(1)?, &"blanket".parse()?, 3).await?;
    ledger
        .reserve(&task(2)?, &"neck-cushion".parse()?, 2)
        .await?;
    Ok(())
}

#[tokio::test]
async fn mismatch_is_flagged_and_stock_unchanged_until_admin_confirms() -> TestResult {
    let clock = clock()?;
    let ledger = ledger(&clock, &[("blanket", 3)])?;
    let seen = [SeenItem {
        item: "blanket".parse()?,
        count: Some(1),
        uncertain: false,
    }];
    let outcomes = ledger.reconcile(&"storeroom".parse()?, &seen).await?;
    assert_eq!(
        outcomes,
        vec![ReconcileOutcome::Mismatch {
            item: "blanket".parse()?,
            expected: 3,
            seen: 1
        }]
    );
    ledger.reserve(&task(1)?, &"blanket".parse()?, 3).await?;
    Ok(())
}
