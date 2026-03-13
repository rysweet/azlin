//! Persistent bastion tunnel daemon for SSH/SCP through Azure Bastion.
//!
//! Instead of creating/destroying tunnels per operation, this module maintains
//! a tunnel registry at `/tmp/azlin-tunnels/registry.json`. Tunnels are reused
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
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU16, Ordering};
use tracing::debug;

/// Global port counter to avoid collisions across concurrent tunnels.
static NEXT_PORT: AtomicU16 = AtomicU16::new(50200);

/// Whether the keepalive watchdog has been started.
static WATCHDOG_STARTED: AtomicBool = AtomicBool::new(false);

/// Directory for tunnel state files.
const TUNNEL_DIR: &str = "/tmp/azlin-tunnels";

/// Registry file path.
fn registry_path() -> PathBuf {
    PathBuf::from(TUNNEL_DIR).join("registry.json")
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
        let dir = Path::new(TUNNEL_DIR);
        if !dir.exists() {
            std::fs::create_dir_all(dir).context("creating tunnel directory")?;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700));
        }
        let data = serde_json::to_string_pretty(self)?;
        std::fs::write(registry_path(), data).context("writing tunnel registry")?;
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

    // Reuse existing tunnel if alive
    if let Some(entry) = registry.get(vm_resource_id) {
        if process_is_running(entry.pid) {
            debug!(
                "reusing existing bastion tunnel for {} on port {}",
                vm_resource_id, entry.local_port
            );
            return Ok(entry.local_port);
        }
    }

    // Spawn a new tunnel
    let port = NEXT_PORT.fetch_add(1, Ordering::SeqCst);
    let child = std::process::Command::new("az")
        .args([
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
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("Failed to spawn az bastion tunnel")?;

    let pid = child.id();
    std::mem::forget(child);

    // Wait for tunnel to establish
    std::thread::sleep(std::time::Duration::from_secs(2));

    if !process_is_running(pid) {
        anyhow::bail!(
            "Bastion tunnel for {} failed to start (process exited immediately)",
            vm_resource_id
        );
    }

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
}
