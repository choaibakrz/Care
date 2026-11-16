//! The detection thresholds and the protected addresses (all from `.env`, with the documented
//! defaults).

use std::net::IpAddr;
use std::num::NonZeroU32;
use std::time::Duration;

use ipnet::IpNet;

use crate::rate_limit::RateLimitConfig;

/// The thresholds of the detection rules. Every number is configuration (`.env`); the
/// defaults are those of `monitoring-security.md`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MonitorConfig {
    /// Rate limit per client address (`RATE_PER_SECOND` 20, `RATE_BURST` 40).
    pub rate: RateLimitConfig,
    /// An address over the limit in this many consecutive seconds is blocked
    /// (`AUTO_BLOCK_AFTER_S`, 5).
    pub excess_seconds: u32,
    /// How long an automatic block lasts (`AUTO_BLOCK_FOR_S`, 600).
    pub auto_block_for: Duration,
    /// Failed `POST /auth/login` from one address that trigger a block
    /// (`LOGIN_FAILURES_MAX`, 10) ...
    pub login_failures: u32,
    /// ... within this window (`LOGIN_FAILURES_WINDOW_S`, 60).
    pub login_window: Duration,
    /// How long per-address counters are kept (`MONITOR_WINDOW_S`, 300; memory only).
    pub window: Duration,
    /// At most one `rate_limited` alert per address in this interval (60 s).
    pub rate_alert_every: Duration,
    /// The emergency service's addresses (`EMERGENCY_SERVICE_ADDRESSES`, a comma-separated
    /// list of addresses or CIDR blocks): never limited, never blocked.
    pub emergency_service: Vec<IpNet>,
}

impl Default for MonitorConfig {
    fn default() -> Self {
        MonitorConfig {
            rate: RateLimitConfig {
                per_second: NonZeroU32::MIN.saturating_add(19),
                burst: NonZeroU32::MIN.saturating_add(39),
            },
            excess_seconds: 5,
            auto_block_for: Duration::from_mins(10),
            login_failures: 10,
            login_window: Duration::from_mins(1),
            window: Duration::from_mins(5),
            rate_alert_every: Duration::from_mins(1),
            emergency_service: Vec::new(),
        }
    }
}

/// The addresses no rule may touch, other than the caller's own (checked per request).
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ProtectedAddresses {
    emergency_service: Vec<IpNet>,
}

impl ProtectedAddresses {
    /// The emergency service's blocks.
    #[must_use]
    pub fn new(emergency_service: Vec<IpNet>) -> ProtectedAddresses {
        ProtectedAddresses { emergency_service }
    }

    /// Whether `ip` is loopback (`127.0.0.0/8`, `::1`) or unspecified (a request with no
    /// peer address, which only an in-process caller makes).
    #[must_use]
    pub fn is_local(ip: IpAddr) -> bool {
        ip.is_loopback() || ip.is_unspecified()
    }

    /// Whether `ip` belongs to the emergency service.
    #[must_use]
    pub fn is_emergency_service(&self, ip: IpAddr) -> bool {
        self.emergency_service.iter().any(|net| net.contains(&ip))
    }

    /// Whether `net` overlaps the emergency service.
    #[must_use]
    pub fn overlaps_emergency_service(&self, net: &IpNet) -> bool {
        self.emergency_service
            .iter()
            .any(|service| overlaps(service, net))
    }
}

/// A block with an IPv4-mapped IPv6 range (`::ffff:a.b.c.d/96+n`) read as the IPv4 block
/// `a.b.c.d/n` (R27), truncated to its network; any other block truncated as is.
#[must_use]
pub fn canonical_net(net: IpNet) -> IpNet {
    if let IpNet::V6(v6) = net
        && let Some(v4) = v6.network().to_ipv4_mapped()
        && v6.prefix_len() >= 96
        && let Ok(mapped) = ipnet::Ipv4Net::new(v4, v6.prefix_len() - 96)
    {
        return IpNet::V4(mapped.trunc());
    }
    net.trunc()
}

/// Whether two blocks share at least one address.
#[must_use]
pub fn overlaps(a: &IpNet, b: &IpNet) -> bool {
    a.contains(&b.network()) || b.contains(&a.network())
}

#[cfg(test)]
mod tests {
    use std::net::IpAddr;

    use ipnet::IpNet;

    use super::{MonitorConfig, ProtectedAddresses, overlaps};

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn defaults_are_the_documented_ones() {
        let config = MonitorConfig::default();
        assert_eq!(config.rate.per_second.get(), 20);
        assert_eq!(config.rate.burst.get(), 40);
        assert_eq!(config.excess_seconds, 5);
        assert_eq!(config.auto_block_for.as_secs(), 600);
        assert_eq!(config.login_failures, 10);
        assert_eq!(config.login_window.as_secs(), 60);
        assert_eq!(config.window.as_secs(), 300);
        assert_eq!(config.rate_alert_every.as_secs(), 60);
    }

    #[test]
    fn local_and_emergency_addresses_are_recognised() -> TestResult {
        let protected = ProtectedAddresses::new(vec!["10.9.0.0/24".parse()?]);
        assert!(ProtectedAddresses::is_local("127.0.0.1".parse()?));
        assert!(ProtectedAddresses::is_local("127.8.0.1".parse()?));
        assert!(ProtectedAddresses::is_local("::1".parse()?));
        assert!(ProtectedAddresses::is_local("0.0.0.0".parse()?));
        assert!(!ProtectedAddresses::is_local("10.0.0.1".parse()?));
        let service: IpAddr = "10.9.0.7".parse()?;
        assert!(protected.is_emergency_service(service));
        let wide: IpNet = "10.9.0.0/16".parse()?;
        assert!(protected.overlaps_emergency_service(&wide));
        let other: IpNet = "10.8.0.0/24".parse()?;
        assert!(!protected.overlaps_emergency_service(&other));
        assert!(overlaps(&"10.0.0.0/8".parse()?, &"10.1.2.3/32".parse()?));
        assert_eq!(
            super::canonical_net("::ffff:203.0.113.0/120".parse()?),
            "203.0.113.0/24".parse::<IpNet>()?
        );
        assert_eq!(
            super::canonical_net("::ffff:0:0/80".parse()?),
            "::/80".parse::<IpNet>()?
        );
        Ok(())
    }
}
