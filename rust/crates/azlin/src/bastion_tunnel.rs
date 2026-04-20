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
use tracing::{debug, warn};

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
    pub fn remove(&mut self, vm_resource_id: &str) -> Option<TunnelRegistryEntry> {
        if let Some(entry) = self.tunnels.remove(vm_resource_id) {
            kill_process(entry.pid);
            Some(entry)
        } else {
            None
        }
    }

    /// Kill all tunnels and clear the registry.
    pub fn remove_all(&mut self) {
        for (_, entry) in self.tunnels.drain() {
            kill_process(entry.pid);
        }
    }
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

/// Get or create a bastion tunnel for a VM. Reuses existing tunnels from the registry.
///
/// Returns the local port the tunnel is bound to.
pub fn get_or_create_tunnel(
    bastion_name: &str,
    resource_group: &str,
    vm_resource_id: &str,
) -> Result<u16> {
    ensure_watchdog_running();

    let mut registry = TunnelRegistry::load();
    registry.prune();

    // Reuse existing tunnel if it is alive, uniquely mapped, and still listening.
    if let Some(entry) = registry.get(vm_resource_id).cloned() {
        let duplicate_port = registry.tunnels.iter().any(|(other_id, other)| {
            other_id != vm_resource_id && other.local_port == entry.local_port
        });
        if process_is_running(entry.pid)
            && local_port_owned_by_process_tree(entry.local_port, entry.pid)?
            && !duplicate_port
        {
            debug!(
                "reusing existing bastion tunnel for {} on port {}",
                vm_resource_id, entry.local_port
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

    // Spawn a new tunnel
    let port = pick_unused_local_port()?;
    let mut cmd = std::process::Command::new("az");
    cmd.args([
            "network",
            "bastion",
            "tunnel",
            "--name",
            bastion_name,
            "--resource-group",
            resource_group,
            "--target-resource-id",
            vm_resource_id,
            "--resource-port",
            "22",
            "--port",
            &port.to_string(),
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    // Create a new process group so cleanup can terminate the entire tree
    // (az is a bash wrapper that spawns Python).
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            cmd.pre_exec(|| {
                libc::setsid();
                Ok(())
            });
        }
    }
    let mut child = cmd
        .spawn()
        .context("Failed to spawn az bastion tunnel")?;

    let pid = child.id();
    if let Err(error) = wait_for_local_port_listener(port, pid, std::time::Duration::from_secs(10))
    {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error).context(format!(
            "Bastion tunnel for {} failed to listen on 127.0.0.1:{}",
            vm_resource_id, port
        ));
    }
    std::mem::forget(child);

    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    registry.insert(TunnelRegistryEntry {
        vm_resource_id: vm_resource_id.to_string(),
        bastion_name: bastion_name.to_string(),
        resource_group: resource_group.to_string(),
        local_port: port,
        pid,
        created_at: now,
    });
    registry.save()?;

    debug!(
        "started new bastion tunnel for {} on port {} (pid {})",
        vm_resource_id, port, pid
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
    pub fn new(bastion_name: &str, resource_group: &str, vm_resource_id: &str) -> Result<Self> {
        let local_port = get_or_create_tunnel(bastion_name, resource_group, vm_resource_id)?;
        Ok(Self {
            local_port,
            vm_resource_id: vm_resource_id.to_string(),
        })
    }
}

/// Build SSH args that route through a bastion tunnel (127.0.0.1 on a local port).
pub fn bastion_ssh_args(
    user: &str,
    local_port: u16,
    cmd: &str,
    connect_timeout: u64,
) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        "-p".to_string(),
        local_port.to_string(),
        format!("{}@127.0.0.1", user),
        cmd.to_string(),
    ]
}

/// Build SCP args that route through a bastion tunnel.
pub fn bastion_scp_args(
    user: &str,
    local_port: u16,
    sources: &[&str],
    remote_path: &str,
    connect_timeout: u64,
    recursive: bool,
) -> Vec<String> {
    let mut args = Vec::new();
    if recursive {
        args.push("-r".to_string());
    }
    args.extend_from_slice(&[
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        "-P".to_string(),
        local_port.to_string(),
    ]);
    for src in sources {
        args.push(src.to_string());
    }
    args.push(format!("{}@127.0.0.1:{}", user, remote_path));
    args
}

/// Build SCP args for downloading from VM through bastion tunnel.
pub fn bastion_scp_download_args(
    user: &str,
    local_port: u16,
    remote_path: &str,
    local_dest: &str,
    connect_timeout: u64,
) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        "-P".to_string(),
        local_port.to_string(),
        format!("{}@127.0.0.1:{}", user, remote_path),
        local_dest.to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn test_bastion_ssh_args_format() {
        let args = bastion_ssh_args("admin", 50200, "uptime", 30);
        assert!(args.contains(&"-p".to_string()));
        assert!(args.contains(&"50200".to_string()));
        assert!(args.contains(&"admin@127.0.0.1".to_string()));
        assert!(args.contains(&"ConnectTimeout=30".to_string()));
        assert_eq!(args.last().unwrap(), "uptime");
    }

    #[test]
    fn test_bastion_scp_args_format() {
        let args = bastion_scp_args("admin", 50201, &["/tmp/file.txt"], "~/", 30, false);
        assert!(args.contains(&"-P".to_string()));
        assert!(args.contains(&"50201".to_string()));
        assert!(args.contains(&"/tmp/file.txt".to_string()));
        assert!(args.contains(&"admin@127.0.0.1:~/".to_string()));
        assert!(!args.contains(&"-r".to_string()));
    }

    #[test]
    fn test_bastion_scp_args_recursive() {
        let args = bastion_scp_args("user", 50202, &["/tmp/dir"], "~/dest/", 10, true);
        assert_eq!(args[0], "-r");
    }

    #[test]
    fn test_bastion_scp_download_args() {
        let args = bastion_scp_download_args("admin", 50203, "~/file.txt", "/tmp/file.txt", 30);
        assert!(args.contains(&"admin@127.0.0.1:~/file.txt".to_string()));
        assert!(args.contains(&"/tmp/file.txt".to_string()));
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
        });
        registry.insert(TunnelRegistryEntry {
            vm_resource_id: "/vm/b".to_string(),
            bastion_name: "bastion".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50200,
            pid: 2,
            created_at: 2,
        });
        registry.insert(TunnelRegistryEntry {
            vm_resource_id: "/vm/c".to_string(),
            bastion_name: "bastion".to_string(),
            resource_group: "rg".to_string(),
            local_port: 50201,
            pid: 3,
            created_at: 3,
        });

        let removed = purge_registry_entries_for_port(&mut registry, 50200);

        assert_eq!(removed.len(), 2);
        assert!(removed.contains(&"/vm/a".to_string()));
        assert!(removed.contains(&"/vm/b".to_string()));
        assert!(!registry.tunnels.contains_key("/vm/a"));
        assert!(!registry.tunnels.contains_key("/vm/b"));
        assert!(registry.tunnels.contains_key("/vm/c"));
    }
}
