//! `azlin tunnel` — SSH local port-forwarding to remote VMs.
//!
//! Spawns `ssh -N -L` subprocesses, records their PIDs in
//! `~/.azlin/tunnels.json`, and provides `list` / `close` subcommands.

#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// Tunnel state persistence
// ---------------------------------------------------------------------------

/// A single active tunnel entry stored in ~/.azlin/tunnels.json.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TunnelEntry {
    pub vm_name: String,
    pub local_port: u16,
    pub remote_port: u16,
    pub pid: u32,
}

fn tunnels_path() -> Result<PathBuf> {
    Ok(azlin_core::AzlinConfig::config_dir()?.join("tunnels.json"))
}

fn load_tunnels() -> Result<Vec<TunnelEntry>> {
    let path = tunnels_path()?;
    if !path.exists() {
        return Ok(vec![]);
    }
    let data = std::fs::read_to_string(&path).context("reading tunnels.json")?;
    Ok(serde_json::from_str(&data).unwrap_or_default())
}

fn save_tunnels(entries: &[TunnelEntry]) -> Result<()> {
    let path = tunnels_path()?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let data = serde_json::to_string_pretty(entries)?;
    std::fs::write(&path, data).context("writing tunnels.json")?;
    Ok(())
}

/// Remove stale entries (processes that are no longer running).
fn prune_tunnels(entries: Vec<TunnelEntry>) -> Vec<TunnelEntry> {
    entries
        .into_iter()
        .filter(|e| process_is_running(e.pid))
        .collect()
}

fn process_is_running(pid: u32) -> bool {
    // Check /proc/{pid} on Linux — zero-cost vs spawning a subprocess per check.
    // Falls back to `kill -0` on other platforms.
    #[cfg(target_os = "linux")]
    {
        std::path::Path::new(&format!("/proc/{}", pid)).exists()
    }
    #[cfg(not(target_os = "linux"))]
    {
        std::process::Command::new("kill")
            .args(["-0", &pid.to_string()])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }
}

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    _verbose: bool,
    _output: &azlin_cli::OutputFormat,
) -> Result<()> {
    let azlin_cli::Commands::Tunnel { action } = command else {
        unreachable!()
    };

    match action {
        azlin_cli::TunnelAction::Open {
            vm_identifier,
            ports,
            local_port,
            user,
            key,
            resource_group,
        } => cmd_tunnel_open(vm_identifier, ports, local_port, user, key, resource_group).await,
        azlin_cli::TunnelAction::List => cmd_tunnel_list(),
        azlin_cli::TunnelAction::Close { vm_identifier, all } => {
            cmd_tunnel_close(vm_identifier, all)
        }
    }
}

// ---------------------------------------------------------------------------
// Open
// ---------------------------------------------------------------------------

async fn cmd_tunnel_open(
    vm_identifier: String,
    ports: Vec<u16>,
    local_port: Option<u16>,
    user: String,
    key: Option<PathBuf>,
    resource_group: Option<String>,
) -> Result<()> {
    if local_port.is_some() && ports.len() > 1 {
        anyhow::bail!("--local-port can only be used with a single port");
    }

    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;

    let pb = penguin_spinner(&format!("Looking up {}...", vm_identifier));
    let vm = vm_manager.get_vm(&rg, &vm_identifier)?;
    pb.finish_and_clear();

    let username = vm.admin_username.as_deref().unwrap_or(&user);
    let use_bastion = vm.public_ip.is_none();

    let mut entries = prune_tunnels(load_tunnels()?);

    let resolved_key = key.or_else(resolve_ssh_key);

    if use_bastion {
        open_bastion_tunnels(
            &vm,
            &vm_manager,
            &rg,
            username,
            &ports,
            local_port,
            resolved_key.as_deref(),
            &mut entries,
        )
        .await?;
    } else {
        let ip = vm.public_ip.as_deref().unwrap();
        open_direct_tunnels(
            ip,
            username,
            &ports,
            local_port,
            resolved_key.as_deref(),
            &mut entries,
            &vm_identifier,
        )?;
    }

    save_tunnels(&entries)?;

    println!("\nPress Ctrl+C to stop all tunnels.");

    // Wait for Ctrl+C or all tunnels to exit
    loop {
        // Check for Ctrl+C via tokio signal
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                println!("\nShutting down tunnels...");
                for e in &entries {
                    let _ = std::process::Command::new("kill")
                        .arg(e.pid.to_string())
                        .status();
                }
                // Prune our in-memory entries — no need to re-read disk
                entries.retain(|e| process_is_running(e.pid));
                let _ = save_tunnels(&entries);
                break;
            }
            _ = tokio::time::sleep(std::time::Duration::from_secs(2)) => {
                let still_running = entries.iter().any(|e| process_is_running(e.pid));
                if !still_running {
                    println!("All tunnels have closed.");
                    entries.clear();
                    let _ = save_tunnels(&entries);
                    break;
                }
            }
        }
    }

    Ok(())
}

fn open_direct_tunnels(
    ip: &str,
    user: &str,
    ports: &[u16],
    local_port: Option<u16>,
    key: Option<&std::path::Path>,
    entries: &mut Vec<TunnelEntry>,
    vm_name: &str,
) -> Result<()> {
    for (i, &remote_port) in ports.iter().enumerate() {
        let lport = if ports.len() == 1 {
            local_port.unwrap_or(remote_port)
        } else {
            remote_port
        };

        let args = build_direct_ssh_args(lport, remote_port, user, ip, key);

        let child = std::process::Command::new("ssh")
            .args(&args)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .with_context(|| format!("Failed to spawn ssh for port {}", remote_port))?;

        let pid = child.id();
        // Forget the child handle — we track by PID
        std::mem::forget(child);

        println!(
            "Forwarding localhost:{} → {}:{}",
            lport, vm_name, remote_port
        );

        entries.push(TunnelEntry {
            vm_name: vm_name.to_string(),
            local_port: lport,
            remote_port,
            pid,
        });

        // Small delay between spawns to avoid race on shared key socket
        if i + 1 < ports.len() {
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn open_bastion_tunnels(
    vm: &azlin_core::models::VmInfo,
    vm_manager: &azlin_azure::VmManager,
    rg: &str,
    user: &str,
    ports: &[u16],
    local_port: Option<u16>,
    key: Option<&std::path::Path>,
    entries: &mut Vec<TunnelEntry>,
) -> Result<()> {
    // Locate the bastion for this VM's region
    let bastions = crate::list_helpers::detect_bastion_hosts(rg).unwrap_or_default();
    let bastion_map: HashMap<String, String> =
        bastions.into_iter().map(|(n, l, _)| (l, n)).collect();
    let bastion_name = bastion_map.get(&vm.location).ok_or_else(|| {
        anyhow::anyhow!(
            "No bastion host found for region '{}'. Cannot tunnel to private VM.",
            vm.location
        )
    })?;

    let vm_rid = format!(
        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
        vm_manager.subscription_id(),
        rg,
        vm.name
    );

    // For bastion-routed VMs we open a native bastion tunnel per app port.
    // Each native tunnel maps a local SSH port → VM port 22 (Azure Bastion handles the
    // inner jump). We then layer an SSH -L on top to forward the desired app port.

    for &remote_port in ports.iter() {
        let lport = if ports.len() == 1 {
            local_port.unwrap_or(remote_port)
        } else {
            remote_port
        };

        // Open native bastion tunnel to get a local SSH port
        let bastion_local_port = crate::bastion_tunnel::get_or_create_tunnel(
            bastion_name,
            rg,
            &vm_rid,
        )
        .await
        .with_context(|| format!("Failed to open bastion tunnel for port {}", remote_port))?;

        // Layer ssh -N -L lport:localhost:remote_port -p bastion_local_port user@127.0.0.1
        let ssh_args = build_bastion_ssh_args(lport, remote_port, bastion_local_port, user, key);

        let ssh_child = std::process::Command::new("ssh")
            .args(&ssh_args)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .with_context(|| format!("Failed to spawn ssh -L for port {}", remote_port))?;

        let ssh_pid = ssh_child.id();
        std::mem::forget(ssh_child);

        println!(
            "Forwarding localhost:{} → {}:{} (via bastion)",
            lport, vm.name, remote_port
        );

        entries.push(TunnelEntry {
            vm_name: vm.name.clone(),
            local_port: lport,
            remote_port,
            pid: ssh_pid,
        });
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

fn cmd_tunnel_list() -> Result<()> {
    let raw = load_tunnels()?;
    let entries = prune_tunnels(raw);
    // Persist pruned list so subsequent calls skip dead-PID checks
    let _ = save_tunnels(&entries);
    if entries.is_empty() {
        println!("No active tunnels.");
        return Ok(());
    }

    println!(
        "{:<20} {:>12}  {:>12}  {:>8}",
        "VM", "LOCAL PORT", "REMOTE PORT", "PID"
    );
    println!("{}", "-".repeat(58));
    for e in &entries {
        println!(
            "{:<20} {:>12}  {:>12}  {:>8}",
            e.vm_name, e.local_port, e.remote_port, e.pid
        );
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// SSH arg builders (used by production code and tests)
// ---------------------------------------------------------------------------

/// Build SSH args for a bastion tunnel (loopback via bastion port).
/// Uses `StrictHostKeyChecking=no` because 127.0.0.1 ports are reused across VMs.
pub(crate) fn build_bastion_ssh_args(
    lport: u16,
    remote_port: u16,
    bastion_local_port: u16,
    user: &str,
    key: Option<&std::path::Path>,
) -> Vec<String> {
    let mut args = vec![
        "-N".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=no".to_string(),
        "-o".to_string(),
        "UserKnownHostsFile=/dev/null".to_string(),
        "-p".to_string(),
        bastion_local_port.to_string(),
        "-L".to_string(),
        format!("{}:localhost:{}", lport, remote_port),
    ];
    if let Some(k) = key {
        args.push("-i".to_string());
        args.push(k.display().to_string());
    }
    args.push(format!("{}@127.0.0.1", user));
    args
}

/// Build SSH args for a direct tunnel (real public IP).
/// Uses `StrictHostKeyChecking=accept-new` for genuine host-key verification.
pub(crate) fn build_direct_ssh_args(
    lport: u16,
    remote_port: u16,
    user: &str,
    ip: &str,
    key: Option<&std::path::Path>,
) -> Vec<String> {
    let mut args = vec![
        "-N".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-L".to_string(),
        format!("{}:localhost:{}", lport, remote_port),
    ];
    if let Some(k) = key {
        args.push("-i".to_string());
        args.push(k.display().to_string());
    }
    args.push(format!("{}@{}", user, ip));
    args
}

// ---------------------------------------------------------------------------
// Close
// ---------------------------------------------------------------------------

fn cmd_tunnel_close(vm_identifier: Option<String>, all: bool) -> Result<()> {
    if vm_identifier.is_none() && !all {
        anyhow::bail!("Specify a VM name or use --all to close all tunnels");
    }

    let entries = prune_tunnels(load_tunnels()?);
    let mut kept = vec![];
    let mut closed = 0u32;

    for e in entries {
        let should_close = all
            || vm_identifier
                .as_deref()
                .map(|v| e.vm_name == v)
                .unwrap_or(false);

        if should_close {
            let _ = std::process::Command::new("kill")
                .arg(e.pid.to_string())
                .status();
            if e.remote_port != 0 {
                println!(
                    "Closed tunnel: localhost:{} → {}:{}",
                    e.local_port, e.vm_name, e.remote_port
                );
                closed += 1;
            }
        } else {
            kept.push(e);
        }
    }

    save_tunnels(&kept)?;

    if closed == 0 {
        println!("No matching tunnels found.");
    }
    Ok(())
}
