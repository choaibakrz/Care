//! The optional HTTPS listener (`HTTPS_PORT`, default 8443).
//!
//! HACKATHON: self-signed certificate. Phone browsers only give the microphone to https pages
//! (or localhost), so the patient app needs https on the LAN. Without `TLS_CERT`/`TLS_KEY` a
//! self-signed certificate is generated at first start under `TLS_DIR` (default `data/tls`),
//! naming localhost, 127.0.0.1, this computer's name and every non-loopback IPv4 address,
//! and reused on the next starts (regenerated when an address is new or it nears expiry).
//! Phones show a certificate warning once. Use a real certificate after the pitch.

use std::collections::BTreeSet;
use std::io;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};

use axum::Router;
use axum_server::Handle;
use axum_server::tls_rustls::RustlsConfig;
use chrono::{Datelike as _, Days, NaiveDate, Utc};
use clinic_server::config::TlsConfig;
use serde::{Deserialize, Serialize};

/// Lifetime of a generated certificate (Apple refuses server certificates over 825 days).
const VALID_DAYS: u64 = 365;
/// A generated certificate this close to expiry is replaced at start.
const RENEW_DAYS: u64 = 30;

/// What was generated with the certificate: its names and its last valid day.
#[derive(Debug, Serialize, Deserialize)]
struct Generated {
    names: BTreeSet<String>,
    not_after: NaiveDate,
}

/// The rustls configuration from `TLS_CERT`/`TLS_KEY`, or from the (generated if needed)
/// self-signed certificate.
///
/// # Errors
/// A file that cannot be read or written, or a certificate rustls refuses.
pub async fn rustls_config(config: &TlsConfig) -> io::Result<RustlsConfig> {
    // `ring` only (see Cargo.toml); an already installed provider is fine.
    let _already = rustls::crypto::ring::default_provider().install_default();
    let (cert, key) = match &config.pem_files {
        Some((cert, key)) => (cert.clone(), key.clone()),
        None => self_signed(&config.generated_dir)?,
    };
    RustlsConfig::from_pem_file(cert, key).await
}

/// Serves `app` over https on `addr` until `handle` shuts it down. A failure (port taken, …)
/// is logged and leaves the HTTP listener running.
pub fn spawn(
    addr: SocketAddr,
    tls: RustlsConfig,
    app: Router,
    handle: Handle<SocketAddr>,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let served = axum_server::bind_rustls(addr, tls)
            .handle(handle)
            .serve(app.into_make_service_with_connect_info::<SocketAddr>())
            .await;
        if let Err(error) = served {
            tracing::error!(%addr, %error, "https listener stopped; http keeps running");
        }
    })
}

/// Every non-loopback IPv4 address of this computer (for the certificate and the start log).
pub fn lan_ipv4() -> Vec<Ipv4Addr> {
    let mut ips: Vec<Ipv4Addr> = if_addrs::get_if_addrs()
        .unwrap_or_default()
        .into_iter()
        .filter(|iface| !iface.is_loopback())
        .filter_map(|iface| match iface.ip() {
            IpAddr::V4(ip) if !ip.is_link_local() && !ip.is_unspecified() => Some(ip),
            _ => None,
        })
        .collect();
    ips.sort_unstable();
    ips.dedup();
    ips
}

/// This computer's name, when the system tells it.
fn hostname() -> Option<String> {
    std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .ok()
        .or_else(|| std::fs::read_to_string("/etc/hostname").ok())
        .map(|name| name.trim().to_ascii_lowercase())
        .filter(|name| !name.is_empty())
}

/// The names the certificate must cover now.
fn wanted_names() -> BTreeSet<String> {
    let mut names: BTreeSet<String> = ["localhost".to_owned(), "127.0.0.1".to_owned()].into();
    if let Some(host) = hostname() {
        names.insert(host);
    }
    names.extend(lan_ipv4().into_iter().map(|ip| ip.to_string()));
    names
}

/// The self-signed certificate and key files in `dir`, generated when missing, missing a
/// current name, or near expiry.
fn self_signed(dir: &Path) -> io::Result<(PathBuf, PathBuf)> {
    let cert_path = dir.join("self-signed-cert.pem");
    let key_path = dir.join("self-signed-key.pem");
    let meta_path = dir.join("self-signed.json");
    let names = wanted_names();
    let today = Utc::now().date_naive();
    let reusable = std::fs::read(&meta_path)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Generated>(&bytes).ok())
        .filter(|meta| names.is_subset(&meta.names))
        .filter(|meta| today.checked_add_days(Days::new(RENEW_DAYS)) < Some(meta.not_after));
    if reusable.is_some() && cert_path.is_file() && key_path.is_file() {
        tracing::info!(cert = %cert_path.display(), "https: reusing the self-signed certificate");
        return Ok((cert_path, key_path));
    }

    let not_after = today
        .checked_add_days(Days::new(VALID_DAYS))
        .ok_or_else(|| io::Error::other("certificate expiry date out of range"))?;
    let mut params = rcgen::CertificateParams::new(names.iter().cloned().collect::<Vec<_>>())
        .map_err(io::Error::other)?;
    params.distinguished_name = rcgen::DistinguishedName::new();
    params.distinguished_name.push(
        rcgen::DnType::CommonName,
        "Clinic server (HACKATHON self-signed)",
    );
    params.extended_key_usages = vec![rcgen::ExtendedKeyUsagePurpose::ServerAuth];
    let (year, month, day) = ymd(today)?;
    params.not_before = rcgen::date_time_ymd(year, month, day);
    let (year, month, day) = ymd(not_after)?;
    params.not_after = rcgen::date_time_ymd(year, month, day);
    let key = rcgen::KeyPair::generate().map_err(io::Error::other)?;
    let cert = params.self_signed(&key).map_err(io::Error::other)?;

    std::fs::create_dir_all(dir)?;
    write_private(&key_path, key.serialize_pem().as_bytes())?;
    std::fs::write(&cert_path, cert.pem())?;
    let meta =
        serde_json::to_vec_pretty(&Generated { names, not_after }).map_err(io::Error::other)?;
    std::fs::write(&meta_path, meta)?;
    tracing::info!(cert = %cert_path.display(), "https: generated a self-signed certificate");
    Ok((cert_path, key_path))
}

fn ymd(date: NaiveDate) -> io::Result<(i32, u8, u8)> {
    let month = u8::try_from(date.month()).map_err(io::Error::other)?;
    let day = u8::try_from(date.day()).map_err(io::Error::other)?;
    Ok((date.year(), month, day))
}

/// Writes the private key readable by this user only (Unix; Windows keeps the folder's ACL).
fn write_private(path: &Path, bytes: &[u8]) -> io::Result<()> {
    use std::io::Write as _;
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.mode(0o600);
    }
    options.open(path)?.write_all(bytes)
}

#[cfg(test)]
mod tests {
    type TestResult = Result<(), Box<dyn std::error::Error>>;

    #[test]
    fn generated_certificate_is_reused() -> TestResult {
        let dir = std::env::temp_dir().join(format!("clinic-tls-test-{}", std::process::id()));
        let (cert, _key) = super::self_signed(&dir)?;
        let first = std::fs::read(&cert)?;
        let (cert, _key) = super::self_signed(&dir)?;
        assert_eq!(first, std::fs::read(&cert)?);
        let _ignored = std::fs::remove_dir_all(&dir);
        Ok(())
    }
}
