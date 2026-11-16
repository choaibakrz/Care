//! Monitoring, attack detection and blocking (Task A8, fill T7b):
//! `implementation/admin/requirements/monitoring-security.md`.
//!
//! [`TrafficMonitor`] keeps per-address counters **in memory only** (5 minutes, never written
//! to disk: network data, not the activity of a person), rate-limits each client address
//! (token bucket, 20/s burst 40 by default), blocks an address automatically after a
//! persistent excess or a burst of failed logins, holds the manual block rules, and reports
//! what it did through [`MonitorHooks`] (`security.alert` to admin sockets, audit rows).
//!
//! Two layers feed it ([`layer`]): `count` around the whole stack (every answer, its status
//! and its time) and `gate` (blocks and rate limit). **An authenticated admin's robot
//! command, mode switch, monitoring or block request is never refused by any of them**, and
//! the protected addresses (loopback, connected robots, the emergency service) are never
//! limited or blocked.
//!
//! `--mock` serves it for real (`MockStack::apply_monitored`); the live stack wires it in
//! Task 7b.

mod blocks;
mod config;
pub mod layer;
mod traffic;

pub use blocks::{BlockError, BlockView, NewBlockRequest};
pub use config::{MonitorConfig, ProtectedAddresses, canonical_net};
pub use domain::SecurityAlert;
pub use layer::{RejectMarker, admin_exempt};
pub use traffic::{
    Admission, BlockAction, BlockJournal, ClientView, MonitorHooks, MonitorNotice, Outcome,
    RejectedBy, TrafficMonitor, TrafficPoint, TrafficTotals, TrafficView,
};
