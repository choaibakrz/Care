//! De-duplication of robot messages by envelope id (a robot resends after a reconnect).

use std::collections::{HashSet, VecDeque};

use uuid::Uuid;

/// Remembers the last `capacity` message ids.
#[derive(Debug, Clone)]
pub struct Deduper {
    capacity: usize,
    order: VecDeque<Uuid>,
    ids: HashSet<Uuid>,
}

impl Deduper {
    /// Default capacity.
    pub const DEFAULT_CAPACITY: usize = 1024;

    /// A deduper remembering `capacity` ids.
    #[must_use]
    pub fn new(capacity: usize) -> Deduper {
        Deduper {
            capacity: capacity.max(1),
            order: VecDeque::new(),
            ids: HashSet::new(),
        }
    }

    /// `true` if `id` was already seen; otherwise remembers it (evicting the oldest).
    pub fn seen(&mut self, id: Uuid) -> bool {
        if self.ids.contains(&id) {
            return true;
        }
        self.ids.insert(id);
        self.order.push_back(id);
        while self.order.len() > self.capacity {
            if let Some(oldest) = self.order.pop_front() {
                self.ids.remove(&oldest);
            }
        }
        false
    }
}

impl Default for Deduper {
    fn default() -> Self {
        Deduper::new(Deduper::DEFAULT_CAPACITY)
    }
}
