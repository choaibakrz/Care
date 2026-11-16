//! Room classification by RSSI fingerprints (k nearest neighbours, k = 5).

use std::collections::BTreeMap;

use domain::PlaceId;
use serde::Deserialize;

use super::MIN_RSSI_DBM;
use super::observation::{AnchorId, Observation};

/// Neighbours voting on the room.
const NEIGHBOURS: usize = 5;

/// One survey reading taken in a room.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SurveySample {
    /// Room.
    pub place: PlaceId,
    /// Mean RSSI per anchor.
    pub rssi: BTreeMap<AnchorId, f64>,
}

/// The survey index.
#[derive(Debug, Clone, Default)]
pub struct FingerprintIndex {
    samples: Vec<SurveySample>,
    k: usize,
}

impl FingerprintIndex {
    /// Builds the index (empty survey gives an index that never classifies).
    #[must_use]
    pub fn from_survey(samples: &[SurveySample]) -> FingerprintIndex {
        FingerprintIndex {
            samples: samples.to_vec(),
            k: NEIGHBOURS,
        }
    }

    /// The most likely room and its confidence (share of the k neighbours).
    #[must_use]
    pub fn classify(&self, observations: &[Observation]) -> Option<(PlaceId, f64)> {
        let heard: BTreeMap<&AnchorId, f64> = observations
            .iter()
            .filter_map(|observation| match observation {
                Observation::Rssi { anchor, dbm } => Some((anchor, f64::from(*dbm))),
                Observation::Range { .. } => None,
            })
            .collect();
        if heard.is_empty() || self.samples.is_empty() {
            return None;
        }
        let missing = f64::from(MIN_RSSI_DBM);
        let mut distances: Vec<(f64, &PlaceId)> = self
            .samples
            .iter()
            .map(|sample| {
                let mut sum = 0.0;
                for (anchor, value) in &heard {
                    let surveyed = sample.rssi.get(*anchor).copied().unwrap_or(missing);
                    sum += (value - surveyed).powi(2);
                }
                for (anchor, surveyed) in &sample.rssi {
                    if !heard.contains_key(anchor) {
                        sum += (missing - surveyed).powi(2);
                    }
                }
                (sum.sqrt(), &sample.place)
            })
            .collect();
        distances.sort_by(|a, b| {
            a.0.total_cmp(&b.0)
                .then_with(|| a.1.as_str().cmp(b.1.as_str()))
        });
        let k = self.k.max(1);
        let nearest: Vec<&PlaceId> = distances.iter().take(k).map(|(_, place)| *place).collect();
        let mut votes: BTreeMap<&PlaceId, usize> = BTreeMap::new();
        for place in &nearest {
            *votes.entry(place).or_insert(0) += 1;
        }
        let (place, count) = votes
            .into_iter()
            .max_by(|a, b| a.1.cmp(&b.1).then_with(|| b.0.as_str().cmp(a.0.as_str())))?;
        #[allow(clippy::cast_precision_loss)]
        let confidence = count as f64 / nearest.len() as f64;
        Some((place.clone(), confidence))
    }
}
