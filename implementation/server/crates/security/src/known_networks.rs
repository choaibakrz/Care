//! Known networks: only listed networks may call the server; each has a label and an area.

use std::net::{IpAddr, SocketAddr};
use std::path::Path;

use domain::PlaceId;
use ipnet::IpNet;
use serde::Deserialize;

use crate::error::SecurityError;

/// One network from `seed/known_networks.json`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct NetworkEntry {
    /// Block.
    pub cidr: IpNet,
    /// Label ("ward 2 Wi-Fi").
    pub label: String,
    /// Area the network covers, if one.
    pub area: Option<PlaceId>,
}

impl NetworkEntry {
    /// Loads the networks file.
    ///
    /// # Errors
    /// `NetworkFile`; `InvalidCidr`.
    pub fn load_file(path: &Path) -> Result<Vec<NetworkEntry>, SecurityError> {
        #[derive(Deserialize)]
        struct File {
            #[serde(default)]
            marque: Option<String>,
            networks: Vec<NetworkEntry>,
        }
        let text = std::fs::read_to_string(path).map_err(|error| SecurityError::NetworkFile {
            reason: error.kind().to_string(),
        })?;
        let file: File =
            serde_json::from_str(&text).map_err(|error| SecurityError::NetworkFile {
                reason: format!("not valid JSON: {error}"),
            })?;
        if let Some(marque) = &file.marque {
            tracing::debug!(%marque, "known networks file loaded");
        }
        Ok(file.networks)
    }

    /// The networks used when no known networks file exists (step R1): this computer
    /// (loopback) and the private LAN ranges (RFC 1918 IPv4, IPv6 unique-local and
    /// link-local). A deployment lists its real networks in `seed/known_networks.json`.
    #[must_use]
    pub fn defaults() -> Vec<NetworkEntry> {
        [
            ("127.0.0.0/8", "this computer"),
            ("::1/128", "this computer"),
            ("10.0.0.0/8", "private network (default)"),
            ("172.16.0.0/12", "private network (default)"),
            ("192.168.0.0/16", "private network (default)"),
            ("fc00::/7", "private network (default)"),
            ("fe80::/10", "link-local network (default)"),
        ]
        .into_iter()
        .filter_map(|(cidr, label)| {
            cidr.parse().ok().map(|cidr| NetworkEntry {
                cidr,
                label: label.to_owned(),
                area: None,
            })
        })
        .collect()
    }
}

/// The network a request came from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientNetwork {
    /// Client IP.
    pub ip: IpAddr,
    /// Network label.
    pub label: String,
    /// Area.
    pub area: Option<PlaceId>,
}

/// The list of known networks and trusted proxies.
#[derive(Debug, Clone)]
pub struct KnownNetworks {
    entries: Vec<NetworkEntry>,
    trusted_proxies: Vec<IpNet>,
}

impl KnownNetworks {
    /// Validates the list.
    ///
    /// # Errors
    /// `InvalidConfig` when the list is empty or two entries overlap.
    pub fn new(
        entries: Vec<NetworkEntry>,
        trusted_proxies: Vec<IpNet>,
    ) -> Result<KnownNetworks, SecurityError> {
        if entries.is_empty() {
            return Err(SecurityError::InvalidConfig {
                field: "networks",
                reason: "the known networks list is empty, so nobody could connect",
            });
        }
        for (index, a) in entries.iter().enumerate() {
            for b in entries.iter().skip(index + 1) {
                if a.cidr.contains(&b.cidr) || b.cidr.contains(&a.cidr) {
                    return Err(SecurityError::InvalidConfig {
                        field: "networks",
                        reason: "two known networks overlap; list each block once",
                    });
                }
            }
        }
        Ok(KnownNetworks {
            entries,
            trusted_proxies,
        })
    }

    /// The client's network. `forwarded_for` is read only when `peer` is a trusted proxy.
    #[must_use]
    pub fn resolve(&self, peer: SocketAddr, forwarded_for: Option<&str>) -> Option<ClientNetwork> {
        let peer_ip = peer.ip().to_canonical();
        let from_proxy = self
            .trusted_proxies
            .iter()
            .any(|proxy| proxy.contains(&peer_ip));
        let ip = forwarded_for
            .filter(|_| from_proxy)
            .and_then(|header| header.split(',').next_back())
            .and_then(|last| last.trim().parse::<IpAddr>().ok())
            .map_or(peer_ip, |ip| ip.to_canonical());
        self.entries
            .iter()
            .filter(|entry| entry.cidr.contains(&ip))
            .max_by_key(|entry| entry.cidr.prefix_len())
            .map(|entry| ClientNetwork {
                ip,
                label: entry.label.clone(),
                area: entry.area.clone(),
            })
    }
}
