//! Persistent bastion tunnel daemon for SSH/SCP through Azure Bastion.
//!
//! Instead of creating/destroying tunnels per operation, this module maintains
//! a tunnel registry at `~/.azlin/tunnels/registry.json`. Tunnels are reused
//! across commands and kept alive by a background watchdog thread.
//!
//! ## Architecture
//!
//! - **Registry**: JSON state file tracking active tunnels (VM, local port, PID)
//! - **Reuse**: `get_or_create_tunnel()` checks registry before spawning new tunnels
//! - **Keepalive**: Background thread periodically checks tunnel health and prunes dead entries
//! - **Cleanup**: `cleanup_all_tunnels()` tears down everything on explicit request
//! - **`ScopedBastionTunnel`**: Backward-compatible wrapper; on drop it does NOT kill the tunnel
//!   (the daemon owns it). Only explicit cleanup removes tunnels.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::io::ErrorKind;
use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use tracing::{debug, warn, Instrument};

/// Whether the keepalive watchdog has been started.
static WATCHDOG_STARTED: AtomicBool = AtomicBool::new(false);

/// Directory for tunnel state files.
/// Uses `~/.azlin/tunnels/` instead of `/tmp` to avoid world-readable race conditions.
fn tunnel_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| {
            warn!("$HOME is unset — falling back to /tmp for tunnel state; tunnel registry will be world-readable");
            PathBuf::from("/tmp")
        })
        .join(".azlin")
        .join("tunnels")
}

/// Registry file path.
fn registry_path() -> PathBuf {
    tunnel_dir().join("registry.json")
}

// ---- Registry data model ----

/// A single tunnel entry in the registry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TunnelRegistryEntry {
    pub vm_resource_id: String,
    pub bastion_name: String,
    pub resource_group: String,
    pub local_port: u16,
    pub pid: u32,
    pub created_at: u64,
    /// Tunnel type: "native" (in-process WSS) or "legacy" (az CLI subprocess).
    /// Defaults to "legacy" for backward compatibility with existing registry files.
    #[serde(default = "default_tunnel_type")]
    pub tunnel_type: String,
    /// Resolved Azure Bastion data-plane FQDN (ARM `properties.dnsName`, e.g.
    /// `bst-<uuid>.bastion.azure.com`). Cached so reused/repeat tunnels don't
    /// re-query ARM. Defaults to empty for registry files written before this
    /// field existed (empty triggers a one-time re-resolve).
    #[serde(default)]
    pub dns_name: String,
}

fn default_tunnel_type() -> String {
    "legacy".to_string()
}

/// The full tunnel registry.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TunnelRegistry {
    pub tunnels: HashMap<String, TunnelRegistryEntry>,
}

impl TunnelRegistry {
    /// Load the registry from disk. Returns empty registry if file doesn't exist.
    pub fn load() -> Self {
        let path = registry_path();
        if !path.exists() {
            return Self::default();
        }
        match std::fs::read_to_string(&path) {
            Ok(data) => serde_json::from_str(&data).unwrap_or_default(),
            Err(_) => Self::default(),
        }
    }

    /// Save the registry to disk.
    pub fn save(&self) -> Result<()> {
        let dir = tunnel_dir();
        if !dir.exists() {
            std::fs::create_dir_all(&dir).context("creating tunnel directory")?;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700))
                .context("setting tunnel directory permissions to 0700")?;
        }
        let data = serde_json::to_string_pretty(self)?;
        let path = registry_path();
        #[cfg(unix)]
        {
            use std::io::Write;
            use std::os::unix::fs::OpenOptionsExt;
            std::fs::OpenOptions::new()
                .write(true)
                .create(true)
                .truncate(true)
                .mode(0o600)
                .open(&path)
                .and_then(|mut f| f.write_all(data.as_bytes()))
                .context("writing tunnel registry")?;
        }
        #[cfg(not(unix))]
        {
            std::fs::write(&path, data).context("writing tunnel registry")?;
        }
        Ok(())
    }

    /// Remove entries whose processes are no longer running.
    pub fn prune(&mut self) {
        self.tunnels.retain(|key, entry| {
            if process_is_running(entry.pid) {
                true
            } else {
                debug!("pruning dead tunnel for {key} (pid {})", entry.pid);
                false
            }
        });
    }

    /// Look up a tunnel by VM resource ID.
    pub fn get(&self, vm_resource_id: &str) -> Option<&TunnelRegistryEntry> {
        self.tunnels.get(vm_resource_id)
    }

    /// Insert or update a tunnel entry.
    pub fn insert(&mut self, entry: TunnelRegistryEntry) {
        self.tunnels.insert(entry.vm_resource_id.clone(), entry);
    }

    /// Remove a specific tunnel and kill its process.
    /// Native tunnels owned by the current process are not killed (they die when we exit).
    pub fn remove(&mut self, vm_resource_id: &str) -> Option<TunnelRegistryEntry> {
        if let Some(entry) = self.tunnels.remove(vm_resource_id) {
            if !is_self_owned_native(&entry) {
                kill_process(entry.pid);
            }
            Some(entry)
        } else {
            None
        }
    }

    /// Kill all tunnels and clear the registry.
    /// Native tunnels owned by the current process are not killed (they die when we exit).
    pub fn remove_all(&mut self) {
        for (_, entry) in self.tunnels.drain() {
            if !is_self_owned_native(&entry) {
                kill_process(entry.pid);
            }
        }
    }
}

/// True when the entry is a native (in-process) tunnel owned by the current process.
/// Killing such an entry would SIGTERM ourselves.
fn is_self_owned_native(entry: &TunnelRegistryEntry) -> bool {
    entry.tunnel_type == "native" && entry.pid == std::process::id()
}

// ---- Process utilities ----

fn process_is_running(pid: u32) -> bool {
    std::process::Command::new("kill")
        .args(["-0", &pid.to_string()])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn kill_process(pid: u32) {
    let _ = std::process::Command::new("kill")
        .arg(pid.to_string())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
}

fn pick_unused_local_port() -> Result<u16> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .context("Failed to allocate a local port for bastion tunnel")?;
    let port = listener
        .local_addr()
        .context("Failed to inspect allocated bastion tunnel port")?
        .port();
    Ok(port)
}

fn process_tree_pids(root_pid: u32) -> Result<HashSet<u32>> {
    let output = std::process::Command::new("ps")
        .args(["-eo", "pid=,ppid="])
        .output()
        .context("Failed to inspect process tree for bastion tunnel ownership")?;
    if !output.status.success() {
        anyhow::bail!("ps failed while inspecting bastion tunnel ownership");
    }

    let mut children_by_parent: HashMap<u32, Vec<u32>> = HashMap::new();
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        let mut parts = line.split_whitespace();
        let Some(pid) = parts.next().and_then(|value| value.parse::<u32>().ok()) else {
            continue;
        };
        let Some(ppid) = parts.next().and_then(|value| value.parse::<u32>().ok()) else {
            continue;
        };
        children_by_parent.entry(ppid).or_default().push(pid);
    }

    let mut tree = HashSet::from([root_pid]);
    let mut stack = vec![root_pid];
    while let Some(pid) = stack.pop() {
        if let Some(children) = children_by_parent.get(&pid) {
            for &child in children {
                if tree.insert(child) {
                    stack.push(child);
                }
            }
        }
    }

    Ok(tree)
}

fn listener_owner_pids_with_ss(port: u16) -> Result<Option<HashSet<u32>>> {
    let output = match std::process::Command::new("ss").args(["-lntpH"]).output() {
        Ok(output) => output,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error).context("Failed to run ss for bastion tunnel ownership"),
    };
    if !output.status.success() {
        anyhow::bail!("ss failed while inspecting bastion tunnel ownership");
    }

    let port_suffix = format!(":{port}");
    let mut pids = HashSet::new();
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() < 5 || !fields[3].ends_with(&port_suffix) {
            continue;
        }
        for segment in line.split("pid=").skip(1) {
            let digits: String = segment
                .chars()
                .take_while(|character| character.is_ascii_digit())
                .collect();
            if let Ok(pid) = digits.parse::<u32>() {
                pids.insert(pid);
            }
        }
    }

    Ok(Some(pids))
}

fn listener_owner_pids_with_lsof(port: u16) -> Result<Option<HashSet<u32>>> {
    let output = match std::process::Command::new("lsof")
        .args(["-nP", &format!("-iTCP:{port}"), "-sTCP:LISTEN", "-Fp"])
        .output()
    {
        Ok(output) => output,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error).context("Failed to run lsof for bastion tunnel ownership"),
    };
    if !output.status.success() {
        if output.status.code() == Some(1) {
            return Ok(Some(HashSet::new()));
        }
        anyhow::bail!("lsof failed while inspecting bastion tunnel ownership");
    }

    let mut pids = HashSet::new();
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        if let Some(pid_text) = line.strip_prefix('p') {
            if let Ok(pid) = pid_text.parse::<u32>() {
                pids.insert(pid);
            }
        }
    }

    Ok(Some(pids))
}

#[cfg(target_os = "linux")]
fn collect_listener_inodes(port: u16, proc_net: &str, inodes: &mut HashSet<String>) {
    for line in proc_net.lines().skip(1) {
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() <= 9 || fields[3] != "0A" {
            continue;
        }
        let Some((_, port_hex)) = fields[1].rsplit_once(':') else {
            continue;
        };
        let Ok(listener_port) = u16::from_str_radix(port_hex, 16) else {
            continue;
        };
        if listener_port == port {
            inodes.insert(fields[9].to_string());
        }
    }
}

#[cfg(target_os = "linux")]
fn listener_owner_pids_with_proc(port: u16) -> Result<Option<HashSet<u32>>> {
    let mut inodes = HashSet::new();
    let mut proc_net_available = false;
    for path in ["/proc/net/tcp", "/proc/net/tcp6"] {
        match std::fs::read_to_string(path) {
            Ok(content) => {
                proc_net_available = true;
                collect_listener_inodes(port, &content, &mut inodes);
            }
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Err(error) => {
                return Err(error)
                    .context("Failed to inspect /proc/net/tcp for bastion tunnel ownership");
            }
        }
    }

    if !proc_net_available {
        return Ok(None);
    }

    let mut pids = HashSet::new();
    for entry in std::fs::read_dir("/proc")
        .context("Failed to inspect /proc for bastion tunnel ownership")?
    {
        let entry = match entry {
            Ok(entry) => entry,
            Err(_) => continue,
        };
        let pid_text = entry.file_name();
        let Ok(pid) = pid_text.to_string_lossy().parse::<u32>() else {
            continue;
        };

        let fd_dir = entry.path().join("fd");
        let read_dir = match std::fs::read_dir(&fd_dir) {
            Ok(read_dir) => read_dir,
            Err(_) => continue,
        };
        for fd_entry in read_dir {
            let Ok(fd_entry) = fd_entry else {
                continue;
            };
            let Ok(target) = std::fs::read_link(fd_entry.path()) else {
                continue;
            };
            let target = target.to_string_lossy();
            let Some(inode) = target
                .strip_prefix("socket:[")
                .and_then(|value| value.strip_suffix(']'))
            else {
                continue;
            };
            if inodes.contains(inode) {
                pids.insert(pid);
                break;
            }
        }
    }

    Ok(Some(pids))
}

#[cfg(not(target_os = "linux"))]
fn listener_owner_pids_with_proc(_port: u16) -> Result<Option<HashSet<u32>>> {
    Ok(None)
}

fn listener_owner_pids(port: u16) -> Result<HashSet<u32>> {
    if let Some(pids) = listener_owner_pids_with_ss(port)? {
        return Ok(pids);
    }
    if let Some(pids) = listener_owner_pids_with_lsof(port)? {
        return Ok(pids);
    }
    if let Some(pids) = listener_owner_pids_with_proc(port)? {
        return Ok(pids);
    }
    anyhow::bail!(
        "No supported listener-ownership inspection mechanism is available for bastion tunnel port {}",
        port
    );
}

fn local_port_owned_by_process_tree(port: u16, root_pid: u32) -> Result<bool> {
    let listener_pids = listener_owner_pids(port)?;
    if listener_pids.is_empty() {
        return Ok(false);
    }

    let process_tree = process_tree_pids(root_pid)?;
    Ok(listener_pids
        .iter()
        .any(|listener_pid| process_tree.contains(listener_pid)))
}

fn wait_for_named_local_port_listener(
    port: u16,
    root_pid: u32,
    timeout: std::time::Duration,
    listener_name: &str,
) -> Result<()> {
    let deadline = std::time::Instant::now() + timeout;
    while std::time::Instant::now() < deadline {
        let listener_pids = listener_owner_pids(port)?;
        if !listener_pids.is_empty() {
            if local_port_owned_by_process_tree(port, root_pid)? {
                return Ok(());
            }
            anyhow::bail!(
                "{} port 127.0.0.1:{} is owned by unrelated process(es): {:?}",
                listener_name,
                port,
                listener_pids
            );
        }
        if !process_is_running(root_pid) {
            anyhow::bail!(
                "{} process {} exited before listening on 127.0.0.1:{}",
                listener_name,
                root_pid,
                port
            );
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    anyhow::bail!(
        "Timed out waiting for {} process {} to listen on 127.0.0.1:{}",
        listener_name,
        root_pid,
        port
    );
}

pub(crate) fn wait_for_process_tree_listener(
    port: u16,
    root_pid: u32,
    timeout: std::time::Duration,
    listener_name: &str,
) -> Result<()> {
    wait_for_named_local_port_listener(port, root_pid, timeout, listener_name)
}

fn wait_for_local_port_listener(
    port: u16,
    root_pid: u32,
    timeout: std::time::Duration,
) -> Result<()> {
    wait_for_named_local_port_listener(port, root_pid, timeout, "Bastion tunnel")
}

fn purge_registry_entries_for_port(registry: &mut TunnelRegistry, port: u16) -> Vec<String> {
    let claimants: Vec<String> = registry
        .tunnels
        .iter()
        .filter_map(|(vm_resource_id, entry)| {
            (entry.local_port == port).then_some(vm_resource_id.clone())
        })
        .collect();
    for claimant in &claimants {
        registry.tunnels.remove(claimant);
    }
    claimants
}

// ---- Keepalive watchdog ----

/// Start the background keepalive watchdog (idempotent).
///
/// The watchdog runs every 30 seconds, prunes dead tunnels from the registry.
pub fn ensure_watchdog_running() {
    if WATCHDOG_STARTED
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::Relaxed)
        .is_ok()
    {
        std::thread::Builder::new()
            .name("azlin-tunnel-watchdog".to_string())
            .spawn(|| {
                debug!("bastion tunnel watchdog started");
                loop {
                    std::thread::sleep(std::time::Duration::from_secs(30));
                    let mut registry = TunnelRegistry::load();
                    let before = registry.tunnels.len();
                    registry.prune();
                    let after = registry.tunnels.len();
                    if before != after {
                        debug!(
                            "watchdog pruned {} dead tunnels ({} remaining)",
                            before - after,
                            after
                        );
                        let _ = registry.save();
                    }
                }
            })
            .ok();
    }
}

// ---- Public API ----

/// Validate and normalize the Azure Bastion data-plane FQDN returned by
/// `az network bastion show --query dnsName -o tsv`.
///
/// This is the pure, offline-testable seam for the issue #1046 fix. It fails
/// closed: any output that isn't a single, clean `*.bastion.azure.com` host is
/// rejected so a malformed/hostile ARM response can never be smuggled into a
/// request URL (SSRF / authority-spoofing defense). There is NO fallback to the
/// old `{name}.bastion.azure.com` construction.
fn parse_dns_name(az_stdout: &str) -> Result<String> {
    const SUFFIX: &str = ".bastion.azure.com";

    // Take only the first line so a multiline response cannot smuggle a second host.
    let host = az_stdout.lines().next().unwrap_or("").trim();

    if host.is_empty() {
        anyhow::bail!("bastion dnsName lookup returned empty output");
    }
    if host
        .chars()
        .any(|c| c.is_whitespace() || c.is_control() || c == '@' || c == '/' || c == '\\')
    {
        anyhow::bail!("bastion dnsName contains invalid characters: {host:?}");
    }
    if !host.ends_with(SUFFIX) || host.len() <= SUFFIX.len() || host.starts_with('.') {
        anyhow::bail!(
            "bastion dnsName {host:?} is not a valid *.bastion.azure.com data-plane host"
        );
    }

    Ok(host.to_string())
}

/// Resolve the real Azure Bastion data-plane FQDN (ARM `properties.dnsName`)
/// for a bastion resource. Runs `az network bastion show` on a blocking thread.
///
/// Fails closed with an actionable error (never falling back to a constructed
/// `{name}.bastion.azure.com` host, which does not exist in DNS — issue #1046).
async fn resolve_bastion_dns_name(bastion_name: &str, resource_group: &str) -> Result<String> {
    let name = bastion_name.to_string();
    let rg = resource_group.to_string();

    let output = tokio::task::spawn_blocking(move || {
        std::process::Command::new("az")
            .args([
                "network",
                "bastion",
                "show",
                "--name",
                &name,
                "--resource-group",
                &rg,
                // `az` flattens the ARM resource, so the data-plane FQDN is
                // queried as `dnsName` (not `properties.dnsName`).
                "--query",
                "dnsName",
                "-o",
                "tsv",
            ])
            .output()
    })
    .await
    .context("bastion dnsName lookup task panicked")?
    .with_context(|| {
        format!(
            "failed to run 'az network bastion show' for bastion {bastion_name:?} in resource group {resource_group:?}"
        )
    })?;

    if !output.status.success() {
        anyhow::bail!(
            "az network bastion show failed for bastion {bastion_name:?} in resource group {resource_group:?}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    parse_dns_name(&stdout).with_context(|| {
        format!(
            "could not resolve a valid data-plane dnsName for bastion {bastion_name:?} in resource group {resource_group:?}"
        )
    })
}

/// Fetch a fresh ARM access token together with its expiry via `az`.
///
/// This is the token provider body for the native bastion tunnel (issue #1059):
/// the tunnel calls it whenever its cached token is about to expire, so a
/// long-lived in-process tunnel keeps working past the ~60-90 min token
/// lifetime instead of failing every new connection's token exchange.
///
/// Runs `az` on a blocking thread and asks for both `accessToken` and
/// `expiresOn` in one invocation so the cache learns the token's real lifetime.
///
/// SECRET SAFETY: the returned token value is never logged; error paths only
/// surface `az` stderr / parser positions, never stdout (which carries the token).
async fn fetch_arm_token_with_expiry() -> std::result::Result<
    azlin_azure::native_tunnel::TokenWithExpiry,
    azlin_azure::native_tunnel::NativeTunnelError,
> {
    use azlin_azure::native_tunnel::{NativeTunnelError, TokenWithExpiry};

    let output = tokio::task::spawn_blocking(|| {
        std::process::Command::new("az")
            .args([
                "account",
                "get-access-token",
                "--query",
                "{t:accessToken,e:expiresOn}",
                "-o",
                "json",
            ])
            .output()
    })
    .await
    .map_err(|e| NativeTunnelError::Http(format!("az token task panicked: {e}")))?
    .map_err(|e| {
        NativeTunnelError::Http(format!("failed to run az account get-access-token: {e}"))
    })?;

    if !output.status.success() {
        return Err(NativeTunnelError::TokenExchange(format!(
            "az account get-access-token failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed: serde_json::Value = serde_json::from_str(stdout.trim()).map_err(|e| {
        // The serde error carries only a byte position, never the token text.
        NativeTunnelError::TokenExchange(format!("failed to parse az token JSON: {e}"))
    })?;

    let value = parsed
        .get("t")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    if value.is_empty() {
        return Err(NativeTunnelError::TokenExchange(
            "az account get-access-token returned an empty accessToken".to_string(),
        ));
    }

    let issued_at = std::time::Instant::now();
    let expires_at = parsed
        .get("e")
        .and_then(|v| v.as_str())
        .and_then(|s| parse_expires_on_to_instant(s, issued_at));

    Ok(TokenWithExpiry {
        value,
        issued_at,
        expires_at,
    })
}

/// Convert an `az`-emitted `expiresOn` string into a monotonic [`Instant`],
/// relative to `issued_at`.
///
/// `az` emits `expiresOn` as a **local-time naive** string on this platform
/// (e.g. `2026-07-22 10:20:00.000000`); newer CLIs may emit RFC3339 with an
/// offset. We parse the local-naive form first, then fall back to RFC3339. The
/// wall-clock expiry is projected onto the monotonic clock via
/// `issued_at + (expires - now)`.
///
/// Returns `None` if the string is unparseable or already in the past, so the
/// cache treats the token as short-lived and refreshes eagerly (fail-safe).
fn parse_expires_on_to_instant(
    expires_on: &str,
    issued_at: std::time::Instant,
) -> Option<std::time::Instant> {
    use chrono::{DateTime, Local, NaiveDateTime};

    let local_now = Local::now();

    let when: DateTime<Local> = NaiveDateTime::parse_from_str(expires_on, "%Y-%m-%d %H:%M:%S%.f")
        .ok()
        .and_then(|ndt| ndt.and_local_timezone(Local).single())
        .or_else(|| {
            DateTime::parse_from_rfc3339(expires_on)
                .ok()
                .map(|dt| dt.with_timezone(&Local))
        })?;

    let delta_ms = when.signed_duration_since(local_now).num_milliseconds();
    if delta_ms <= 0 {
        return None;
    }
    Some(issued_at + std::time::Duration::from_millis(delta_ms as u64))
}

/// Get or create a bastion tunnel for a VM. Reuses existing tunnels from the registry.
///
/// Returns the local port the tunnel is bound to.
pub async fn get_or_create_tunnel(
    bastion_name: &str,
    resource_group: &str,
    vm_resource_id: &str,
) -> Result<u16> {
    ensure_watchdog_running();

    let mut registry = TunnelRegistry::load();
    registry.prune();

    // Cache the previously-resolved data-plane dnsName (if any) so a recreate
    // for this VM does not re-query ARM. Empty/legacy entries trigger a re-resolve.
    // The registry file is treated as untrusted input: re-validate the cached host
    // through parse_dns_name so a poisoned registry.json cannot smuggle a hostile
    // host past the *.bastion.azure.com allowlist (issue #1046 hardening). A cached
    // value that fails validation is discarded, forcing a fresh ARM re-resolve.
    let cached_dns_name = registry
        .get(vm_resource_id)
        .map(|e| e.dns_name.clone())
        .filter(|d| !d.is_empty())
        .and_then(|d| parse_dns_name(&d).ok());

    // Reuse existing tunnel if it is alive, uniquely mapped, and still listening.
    if let Some(entry) = registry.get(vm_resource_id).cloned() {
        let duplicate_port = registry.tunnels.iter().any(|(other_id, other)| {
            other_id != vm_resource_id && other.local_port == entry.local_port
        });

        let is_alive = if is_self_owned_native(&entry) {
            // In-process native tunnel — if we're running, it's alive (mem::forget keeps it going)
            true
        } else if entry.tunnel_type == "native" {
            // Native tunnel in another process — just check the process
            process_is_running(entry.pid)
        } else {
            // For legacy tunnels, check if the PID-based process owns the port
            process_is_running(entry.pid)
                && local_port_owned_by_process_tree(entry.local_port, entry.pid).unwrap_or(false)
        };

        if is_alive && !duplicate_port {
            debug!(
                "reusing existing {} bastion tunnel for {} on port {}",
                entry.tunnel_type, vm_resource_id, entry.local_port
            );
            return Ok(entry.local_port);
        }

        if duplicate_port {
            let claimants = purge_registry_entries_for_port(&mut registry, entry.local_port);
            warn!(
                "bastion tunnel registry entry for {} is ambiguous: local port {} is claimed by {:?}; creating a fresh tunnel",
                vm_resource_id, entry.local_port, claimants
            );
        } else {
            registry.tunnels.remove(vm_resource_id);
        }
    }

    // Build a reusable ARM token provider (issue #1059). A long-lived native
    // tunnel is an in-process background task; the ARM access token it was
    // created with expires (~60-90 min), so previously every NEW connection
    // through an old tunnel failed the `aztoken` exchange. The provider lets the
    // tunnel refresh the token adaptively for as long as it lives. It shells out
    // to `az` on a blocking thread and parses `expiresOn` so the cache knows the
    // token's real lifetime. `azlin-azure` stays CLI-agnostic — the closure
    // lives here in the `azlin` crate.
    let token_provider: azlin_azure::native_tunnel::TokenProvider =
        std::sync::Arc::new(|| Box::pin(fetch_arm_token_with_expiry()));

    // Load config for timeout
    let config = azlin_core::AzlinConfig::load().unwrap_or_default();
    let timeout = std::time::Duration::from_secs(config.bastion_tunnel_timeout);
    let connect_timeout = std::time::Duration::from_secs(config.bastion_connect_timeout);

    // Resolve the REAL Azure Bastion data-plane FQDN from ARM (`properties.dnsName`).
    // The old `format!("{}.bastion.azure.com", bastion_name)` construction does not
    // exist in DNS and broke every Standard/Premium connect (issue #1046). Reuse the
    // cached value when available to avoid a repeat ARM query.
    let bastion_endpoint = match cached_dns_name {
        Some(dns_name) => dns_name,
        None => resolve_bastion_dns_name(bastion_name, resource_group).await?,
    };

    // Open native tunnel (NodeScoped = Standard/Premium SKU, the common case for
    // .bastion.azure.com). Wrapped in a span so token-exchange failures (issue
    // #1045) are correlated in logs, and the classified `[KIND: hint]` remediation
    // carried in the error text is surfaced to the operator on failure.
    let tunnel_span = tracing::info_span!(
        "bastion_open_tunnel",
        bastion = %bastion_name,
        resource_group = %resource_group,
        vm_resource_id = %vm_resource_id,
    );
    let (port, handle) = azlin_azure::native_tunnel::open_tunnel_with_timeouts(
        &bastion_endpoint,
        vm_resource_id,
        22,
        token_provider,
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        timeout,
        connect_timeout,
    )
    .instrument(tunnel_span)
    .await
    .map_err(|e| {
        // The error text already embeds the classified remediation hint; log it
        // at the caller so operators see actionable guidance, not just a stack.
        warn!("native bastion tunnel setup failed: {e}");
        e
    })
    .context("failed to open native bastion tunnel")?;

    // Detach the background task (it runs until the process exits)
    std::mem::forget(handle);

    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    registry.insert(TunnelRegistryEntry {
        vm_resource_id: vm_resource_id.to_string(),
        bastion_name: bastion_name.to_string(),
        resource_group: resource_group.to_string(),
        local_port: port,
        pid: std::process::id(),
        created_at: now,
        tunnel_type: "native".to_string(),
        dns_name: bastion_endpoint,
    });
    registry.save()?;

    debug!(
        "started new native bastion tunnel for {} on port {}",
        vm_resource_id, port
    );

    Ok(port)
}

/// Clean up all bastion tunnels.
pub fn cleanup_all_tunnels() {
    let mut registry = TunnelRegistry::load();
    let count = registry.tunnels.len();
    registry.remove_all();
    if registry.save().is_err() {
        let _ = std::fs::remove_file(registry_path());
    }
    if count > 0 {
        debug!("cleaned up {} bastion tunnels", count);
    }
}

/// Clean up a specific tunnel by VM resource ID.
pub fn cleanup_tunnel(vm_resource_id: &str) -> Result<()> {
    let mut registry = TunnelRegistry::load();
    if registry.remove(vm_resource_id).is_some() {
        registry.save()?;
    }
    Ok(())
}

// ---- Backward-compatible ScopedBastionTunnel ----

/// A bastion tunnel handle. Dropping this does NOT kill the tunnel; the daemon
/// registry owns tunnel lifecycles. The tunnel persists for reuse.
pub struct ScopedBastionTunnel {
    pub local_port: u16,
    pub vm_resource_id: String,
}

impl ScopedBastionTunnel {
    /// Get or create a bastion tunnel. The tunnel persists beyond this handle's lifetime.
    pub async fn new(
        bastion_name: &str,
        resource_group: &str,
        vm_resource_id: &str,
    ) -> Result<Self> {
        let local_port = get_or_create_tunnel(bastion_name, resource_group, vm_resource_id).await?;
        Ok(Self {
            local_port,
            vm_resource_id: vm_resource_id.to_string(),
        })
    }
}

/// Canonical SSH `-o` options for connecting through a bastion tunnel on
/// 127.0.0.1, as separate argv tokens.
///
/// A bastion tunnel is an ephemeral loopback listener whose local port is
/// assigned by the OS and therefore reused across different VMs over time.
/// Recording the VM's host key against `[127.0.0.1]:port` in the user's
/// `known_hosts` means the NEXT connection that happens to reuse that port for
/// a DIFFERENT VM sees a mismatched key and SSH aborts with
/// "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!" — even though the real
/// host is fine. The tunnel itself is already TLS-secured end-to-end to Azure
/// Bastion, so pinning a host key on the throwaway loopback port adds no real
/// protection. Disable host-key persistence entirely for these connections by
/// using `StrictHostKeyChecking=no` and discarding known_hosts via
/// `UserKnownHostsFile=/dev/null`. `LogLevel=Error` suppresses the
/// "Warning: Permanently added ..." line SSH would otherwise print.
///
/// These are exactly the options the Azure CLI native bastion client uses
/// (`az network bastion ssh` → `azext_bastion/custom.py`:
/// `ssh username@localhost -p <port> -o StrictHostKeyChecking=no
/// -o UserKnownHostsFile=/dev/null -o LogLevel=Error`).
///
/// This is the single source of truth for every 127.0.0.1 bastion SSH/SCP call
/// site; keep new bastion connections routed through it (or
/// [`BASTION_LOOPBACK_SSH_OPTS_STR`]) rather than re-hardcoding the options.
pub(crate) fn bastion_loopback_ssh_opts() -> [&'static str; 6] {
    [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=Error",
    ]
}

/// The same options as [`bastion_loopback_ssh_opts`], pre-joined for embedding
/// inside an rsync `-e "ssh ..."` transport string.
pub(crate) const BASTION_LOOPBACK_SSH_OPTS_STR: &str =
    "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=Error";

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    // ── parse_expires_on_to_instant table tests (issue #1059 fast-follow, F3) ──
    //
    // The timezone heuristic (parse local-naive first, fall back to RFC3339) was
    // previously untested. The safety property under test: a past or unparseable
    // `expiresOn` must return None so the cache refreshes eagerly, and a naive
    // string is interpreted as LOCAL time (az's documented shape on this
    // platform) — never silently over-extended.

    #[test]
    fn test_parse_expires_on_local_naive_future_maps_to_local_time() {
        let issued_at = std::time::Instant::now();
        // A local-naive timestamp one hour ahead (az's documented shape here).
        let future = chrono::Local::now() + chrono::Duration::hours(1);
        let s = future.format("%Y-%m-%d %H:%M:%S%.f").to_string();

        let parsed = parse_expires_on_to_instant(&s, issued_at)
            .expect("a future local-naive expiresOn must parse");

        let delta = parsed.saturating_duration_since(issued_at);
        assert!(
            delta >= std::time::Duration::from_secs(3540)
                && delta <= std::time::Duration::from_secs(3660),
            "a local-naive expiry must map to ~1h ahead with no timezone over-extension, got {delta:?}"
        );
    }

    #[test]
    fn test_parse_expires_on_rfc3339_offset_future_parses_via_fallback() {
        use chrono::SecondsFormat;
        let issued_at = std::time::Instant::now();
        let future = chrono::Local::now() + chrono::Duration::minutes(30);
        // RFC3339 with an explicit offset (never 'Z'), forcing the fallback arm.
        let s = future.to_rfc3339_opts(SecondsFormat::Secs, false);

        let parsed = parse_expires_on_to_instant(&s, issued_at)
            .expect("a future RFC3339 expiresOn must parse via the fallback");

        let delta = parsed.saturating_duration_since(issued_at);
        assert!(
            delta >= std::time::Duration::from_secs(1740)
                && delta <= std::time::Duration::from_secs(1860),
            "an RFC3339 expiry must map to ~30m ahead, got {delta:?}"
        );
    }

    #[test]
    fn test_parse_expires_on_past_returns_none_failsafe() {
        let issued_at = std::time::Instant::now();
        let past = chrono::Local::now() - chrono::Duration::hours(1);
        let s = past.format("%Y-%m-%d %H:%M:%S%.f").to_string();
        assert!(
            parse_expires_on_to_instant(&s, issued_at).is_none(),
            "an already-past expiresOn must return None so the cache refreshes eagerly"
        );
    }

    #[test]
    fn test_parse_expires_on_unparseable_returns_none() {
        let issued_at = std::time::Instant::now();
        for s in ["", "not-a-timestamp", "2026/07/22 10:00", "20260722T100000"] {
            assert!(
                parse_expires_on_to_instant(s, issued_at).is_none(),
                "unparseable expiresOn {s:?} must fail closed to None"
            );
        }
    }

    #[test]
    fn test_bastion_loopback_ssh_opts_disable_known_hosts() {
        let opts = bastion_loopback_ssh_opts();
        // Must disable host-key persistence so reused 127.0.0.1 tunnel ports
        // across different VMs never trigger "REMOTE HOST IDENTIFICATION
        // CHANGED".
        assert!(opts.contains(&"StrictHostKeyChecking=no"));
        assert!(opts.contains(&"UserKnownHostsFile=/dev/null"));
        // LogLevel=Error suppresses the "Permanently added" warning, matching
        // the Azure CLI native bastion client.
        assert!(opts.contains(&"LogLevel=Error"));
        // Must NOT use accept-new, which would still record per-port keys.
        assert!(!opts.contains(&"StrictHostKeyChecking=accept-new"));
    }

    #[test]
    fn test_bastion_loopback_ssh_opts_str_matches_tokens() {
        // The rsync `-e` string form must stay in sync with the token form.
        assert_eq!(
            BASTION_LOOPBACK_SSH_OPTS_STR,
            bastion_loopback_ssh_opts().join(" ")
        );
    }

    #[test]
    fn test_registry_load_empty() {
        let r = TunnelRegistry::default();
        assert!(r.tunnels.is_empty());
    }

    #[test]
    fn test_registry_roundtrip() {
        let mut r = TunnelRegistry::default();
        r.insert(TunnelRegistryEntry {
            vm_resource_id: "/sub/rg/vm/test".to_string(),
            bastion_name: "bastion1".to_string(),
            resource_group: "rg1".to_string(),
            local_port: 50200,
            pid: 99999,
            created_at: 1000,
            tunnel_type: "legacy".to_string(),
            dns_name: String::new(),
        });

        let json = serde_json::to_string(&r).unwrap();
        let r2: TunnelRegistry = serde_json::from_str(&json).unwrap();
        assert_eq!(r2.tunnels.len(), 1);
        assert_eq!(r2.tunnels["/sub/rg/vm/test"].local_port, 50200);
    }

    #[test]
    fn test_registry_prune_removes_dead() {
        let mut r = TunnelRegistry::default();
        r.insert(TunnelRegistryEntry {
            vm_resource_id: "/dead/vm".to_string(),
            bastion_name: "b".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50200,
            pid: 999999999,
            created_at: 1000,
            tunnel_type: "legacy".to_string(),
            dns_name: String::new(),
        });
        r.prune();
        assert!(r.tunnels.is_empty(), "dead PID should be pruned");
    }

    #[test]
    fn test_pick_unused_local_port_returns_bindable_port() {
        let port = pick_unused_local_port().unwrap();
        let bind_ok = TcpListener::bind(("127.0.0.1", port)).is_ok();
        assert!(
            bind_ok,
            "pick_unused_local_port returned port {port} which could not be bound"
        );
    }

    #[test]
    fn test_pick_unused_local_port_skips_occupied_listener() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let occupied = listener.local_addr().unwrap().port();

        for _ in 0..8 {
            let candidate = pick_unused_local_port().unwrap();
            assert_ne!(candidate, occupied);
        }
    }

    #[test]
    fn test_wait_for_local_port_listener_detects_ready_socket() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();

        wait_for_local_port_listener(
            port,
            std::process::id(),
            std::time::Duration::from_millis(100),
        )
        .unwrap();
    }

    #[test]
    fn test_wait_for_local_port_listener_bails_on_dead_process() {
        let port = {
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            listener.local_addr().unwrap().port()
        };

        let mut child = std::process::Command::new("true")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("failed to spawn 'true'");
        let dead_pid = child.id();
        child.wait().expect("wait failed");

        let result =
            wait_for_local_port_listener(port, dead_pid, std::time::Duration::from_secs(5));
        assert!(
            result.is_err(),
            "expected an error for dead process but got Ok(())"
        );
        let message = format!("{}", result.unwrap_err());
        assert!(
            message.contains("exited before listening"),
            "expected 'exited before listening' in error message, got: {message}"
        );
    }

    #[test]
    fn test_wait_for_local_port_listener_bails_on_foreign_listener() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();

        let mut child = std::process::Command::new("sleep")
            .arg("5")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("failed to spawn 'sleep'");
        let foreign_pid = child.id();

        let result =
            wait_for_local_port_listener(port, foreign_pid, std::time::Duration::from_secs(1));
        let _ = child.kill();
        let _ = child.wait();

        assert!(
            result.is_err(),
            "expected an error for a foreign listener but got Ok(())"
        );
        let message = format!("{}", result.unwrap_err());
        assert!(
            message.contains("owned by unrelated process"),
            "expected unrelated-listener error message, got: {message}"
        );
    }

    #[test]
    fn test_wait_for_local_port_listener_times_out_when_no_listener() {
        let port = {
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            listener.local_addr().unwrap().port()
        };

        let result = wait_for_local_port_listener(
            port,
            std::process::id(),
            std::time::Duration::from_millis(50),
        );
        assert!(result.is_err(), "expected a timeout error but got Ok(())");
        let message = format!("{}", result.unwrap_err());
        assert!(
            message.contains("Timed out"),
            "expected 'Timed out' in error message, got: {message}"
        );
    }

    #[test]
    fn test_purge_registry_entries_for_port_removes_all_claimants() {
        let mut registry = TunnelRegistry::default();
        registry.insert(TunnelRegistryEntry {
            vm_resource_id: "/vm/a".to_string(),
            bastion_name: "bastion".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50200,
            pid: 1,
            created_at: 1,
            tunnel_type: "legacy".to_string(),
            dns_name: String::new(),
        });
        registry.insert(TunnelRegistryEntry {
            vm_resource_id: "/vm/b".to_string(),
            bastion_name: "bastion".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50200,
            pid: 2,
            created_at: 2,
            tunnel_type: "legacy".to_string(),
            dns_name: String::new(),
        });
        registry.insert(TunnelRegistryEntry {
            vm_resource_id: "/vm/c".to_string(),
            bastion_name: "bastion".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50201,
            pid: 3,
            created_at: 3,
            tunnel_type: "legacy".to_string(),
            dns_name: String::new(),
        });

        let removed = purge_registry_entries_for_port(&mut registry, 50200);

        assert_eq!(removed.len(), 2);
        assert!(removed.contains(&"/vm/a".to_string()));
        assert!(removed.contains(&"/vm/b".to_string()));
        assert!(!registry.tunnels.contains_key("/vm/a"));
        assert!(!registry.tunnels.contains_key("/vm/b"));
        assert!(registry.tunnels.contains_key("/vm/c"));
    }

    // ── Regression tests: bastion data-plane dnsName resolution (issue #1046) ──
    //
    // The regression (v2.6.83): get_or_create_tunnel built the data-plane host as
    // `format!("{}.bastion.azure.com", bastion_name)`, which does not exist in DNS.
    // The fix resolves the REAL ARM `properties.dnsName` (e.g. `bst-<uuid>.bastion.azure.com`)
    // and feeds it, validated, to the native tunnel. These tests pin that contract.
    //
    // `parse_dns_name` is the pure, offline-testable validation/normalization seam
    // applied to `az network bastion show --query dnsName -o tsv` output.

    #[test]
    fn test_parse_dns_name_accepts_real_arm_form() {
        // ARM returns the real data-plane FQDN with a `bst-<uuid>` prefix.
        let out = "bst-7299861d-50e0-4142-8b50-2f8bc6f5b549.bastion.azure.com";
        assert_eq!(parse_dns_name(out).unwrap(), out);
    }

    #[test]
    fn test_parse_dns_name_trims_trailing_newline_and_spaces() {
        // `-o tsv` output typically carries a trailing newline; surrounding
        // whitespace must be trimmed to yield a clean host.
        let out = "  bst-abc123.bastion.azure.com \n";
        assert_eq!(parse_dns_name(out).unwrap(), "bst-abc123.bastion.azure.com");
    }

    #[test]
    fn test_parse_dns_name_rejects_empty() {
        // Empty ARM output must fail closed (no fallback to a constructed host).
        assert!(parse_dns_name("").is_err());
    }

    #[test]
    fn test_parse_dns_name_rejects_whitespace_only() {
        assert!(parse_dns_name("   \n\t ").is_err());
    }

    #[test]
    fn test_parse_dns_name_rejects_wrong_suffix() {
        // SSRF/tamper defense: only genuine `.bastion.azure.com` hosts are allowed.
        assert!(parse_dns_name("evil.example.com").is_err());
        assert!(parse_dns_name("bst-abc.bastion.azure.com.evil.com").is_err());
    }

    #[test]
    fn test_parse_dns_name_rejects_at_injection() {
        // A userinfo-style '@' must never survive into the host (URL authority spoofing).
        assert!(parse_dns_name("bst-abc.bastion.azure.com@evil.com").is_err());
    }

    #[test]
    fn test_parse_dns_name_rejects_path_and_control_chars() {
        assert!(parse_dns_name("bst-abc.bastion.azure.com/api/tokens").is_err());
        assert!(parse_dns_name("bst-abc\t.bastion.azure.com").is_err());
    }

    #[test]
    fn test_parse_dns_name_takes_first_line_and_drops_injected_tail() {
        // Hostile multiline output must not smuggle a second host past validation.
        let hostile = "bst-good.bastion.azure.com\nevil.example.com";
        let parsed = parse_dns_name(hostile).unwrap();
        assert_eq!(parsed, "bst-good.bastion.azure.com");
        assert!(!parsed.contains("evil"));
        assert!(!parsed.contains('\n'));
    }

    #[test]
    fn test_resolved_endpoint_is_arm_dns_name_not_constructed() {
        // Core regression guard: the endpoint fed to the tunnel is the ARM dnsName,
        // NOT the buggy `{name}.bastion.azure.com` construction.
        let bastion_name = "azlin-bastion-southcentralus";
        let arm_output = "bst-7299861d-50e0-4142-8b50-2f8bc6f5b549.bastion.azure.com\n";

        let resolved = parse_dns_name(arm_output).unwrap();
        assert_eq!(
            resolved,
            "bst-7299861d-50e0-4142-8b50-2f8bc6f5b549.bastion.azure.com"
        );

        let regressed = format!("{bastion_name}.bastion.azure.com");
        assert_ne!(
            resolved, regressed,
            "endpoint must be the ARM dnsName, never {{name}}.bastion.azure.com (issue #1046)"
        );
    }

    // ── Registry back-compat: TunnelRegistryEntry.dns_name caching ──

    #[test]
    fn test_registry_entry_dns_name_defaults_for_old_files() {
        // registry.json written before the `dns_name` field must still deserialize,
        // yielding an empty dns_name (which triggers a one-time ARM re-resolve).
        let old_json = r#"{
            "tunnels": {
                "/sub/rg/vm/x": {
                    "vm_resource_id": "/sub/rg/vm/x",
                    "bastion_name": "b",
                    "resource_group": "rg",
                    "local_port": 50200,
                    "pid": 1234,
                    "created_at": 1000,
                    "tunnel_type": "native"
                }
            }
        }"#;
        let reg: TunnelRegistry = serde_json::from_str(old_json).unwrap();
        assert_eq!(reg.tunnels["/sub/rg/vm/x"].dns_name, "");
    }

    #[test]
    fn test_registry_roundtrip_preserves_dns_name() {
        // A resolved dnsName must survive a save/load cycle so reused tunnels and
        // repeat connects do not re-query ARM.
        let mut r = TunnelRegistry::default();
        r.insert(TunnelRegistryEntry {
            vm_resource_id: "/sub/rg/vm/y".to_string(),
            bastion_name: "b".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50210,
            pid: 4321,
            created_at: 2000,
            tunnel_type: "native".to_string(),
            dns_name: "bst-abc123.bastion.azure.com".to_string(),
        });

        let json = serde_json::to_string(&r).unwrap();
        let r2: TunnelRegistry = serde_json::from_str(&json).unwrap();
        assert_eq!(
            r2.tunnels["/sub/rg/vm/y"].dns_name,
            "bst-abc123.bastion.azure.com"
        );
    }

    #[test]
    fn test_cached_dns_name_is_revalidated_before_use() {
        // Defense-in-depth (issue #1046 hardening): the registry file is untrusted
        // input. A poisoned cached dns_name must be rejected by the same validator
        // that gates fresh ARM output, so it can never bypass the *.bastion.azure.com
        // allowlist. get_or_create_tunnel re-runs parse_dns_name on the cached value
        // and discards it on failure (forcing a fresh ARM re-resolve).
        let poisoned = "bst-abc.bastion.azure.com@evil.com";
        assert!(
            parse_dns_name(poisoned).is_err(),
            "a poisoned cached host must not pass validation"
        );

        // A clean cached value still validates and is reused (no re-resolve).
        let clean = "bst-abc123.bastion.azure.com";
        assert_eq!(parse_dns_name(clean).unwrap(), clean);
    }
}
