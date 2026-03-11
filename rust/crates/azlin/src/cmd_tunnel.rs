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
    // On Linux/macOS: kill -0 returns success if the process exists
    std::process::Command::new("kill")
        .args(["-0", &pid.to_string()])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
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
        } => {
            cmd_tunnel_open(vm_identifier, ports, local_port, user, key, resource_group).await
        }
        azlin_cli::TunnelAction::List => cmd_tunnel_list(),
        azlin_cli::TunnelAction::Close {
            vm_identifier,
            all,
        } => cmd_tunnel_close(vm_identifier, all),
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

    if use_bastion {
        open_bastion_tunnels(
            &vm,
            &vm_manager,
            &rg,
            username,
            &ports,
            local_port,
            key.as_deref(),
            &mut entries,
        )?;
    } else {
        let ip = vm.public_ip.as_deref().unwrap();
        open_direct_tunnels(ip, username, &ports, local_port, key.as_deref(), &mut entries, &vm_identifier)?;
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
                let remaining = prune_tunnels(load_tunnels().unwrap_or_default());
                let _ = save_tunnels(&remaining);
                break;
            }
            _ = tokio::time::sleep(std::time::Duration::from_secs(1)) => {
                let still_running = entries.iter().any(|e| process_is_running(e.pid));
                if !still_running {
                    println!("All tunnels have closed.");
                    let remaining = prune_tunnels(load_tunnels().unwrap_or_default());
                    let _ = save_tunnels(&remaining);
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

        let child = std::process::Command::new("ssh")
            .args(&args)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .with_context(|| format!("Failed to spawn ssh for port {}", remote_port))?;

        let pid = child.id();
        // Forget the child handle — we track by PID
        std::mem::forget(child);

        println!("Forwarding localhost:{} → {}:{}", lport, vm_name, remote_port);

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
fn open_bastion_tunnels(
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
    let bastions = crate::list_helpers::detect_bastion_hosts(rg)
        .unwrap_or_default();
    let bastion_map: HashMap<String, String> = bastions
        .into_iter()
        .map(|(n, l, _)| (l, n))
        .collect();
    let bastion_name = bastion_map
        .get(&vm.location)
        .ok_or_else(|| anyhow::anyhow!(
            "No bastion host found for region '{}'. Cannot tunnel to private VM.",
            vm.location
        ))?;

    let vm_rid = format!(
        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
        vm_manager.subscription_id(),
        rg,
        vm.name
    );

    // For bastion-routed VMs we open one bastion tunnel per app port.
    // Each bastion tunnel maps a local SSH port → VM port 22 (Azure Bastion handles the
    // inner jump). We then layer an SSH -L on top to forward the desired app port.
    let base_local_port: u16 = 50200;

    for (i, &remote_port) in ports.iter().enumerate() {
        let lport = if ports.len() == 1 {
            local_port.unwrap_or(remote_port)
        } else {
            remote_port
        };

        let bastion_local_port = base_local_port + i as u16;

        // Step 1: open az bastion tunnel → bastion_local_port
        let bastion_child = std::process::Command::new("az")
            .args([
                "network", "bastion", "tunnel",
                "--name", bastion_name,
                "--resource-group", rg,
                "--target-resource-id", &vm_rid,
                "--resource-port", "22",
                "--port", &bastion_local_port.to_string(),
            ])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .context("Failed to spawn az bastion tunnel")?;

        let bastion_pid = bastion_child.id();
        std::mem::forget(bastion_child);

        // Wait for bastion tunnel to establish
        std::thread::sleep(std::time::Duration::from_secs(3));

        // Step 2: ssh -N -L lport:localhost:remote_port -p bastion_local_port user@127.0.0.1
        let mut ssh_args = vec![
            "-N".to_string(),
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "-p".to_string(),
            bastion_local_port.to_string(),
            "-L".to_string(),
            format!("{}:localhost:{}", lport, remote_port),
        ];
        if let Some(k) = key {
            ssh_args.push("-i".to_string());
            ssh_args.push(k.display().to_string());
        }
        ssh_args.push(format!("{}@127.0.0.1", user));

        let ssh_child = std::process::Command::new("ssh")
            .args(&ssh_args)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .with_context(|| format!("Failed to spawn ssh -L for port {}", remote_port))?;

        let ssh_pid = ssh_child.id();
        std::mem::forget(ssh_child);

        println!("Forwarding localhost:{} → {}:{} (via bastion)", lport, vm.name, remote_port);

        // Record both pids — we store the SSH -L pid as the primary; also record bastion pid
        entries.push(TunnelEntry {
            vm_name: vm.name.clone(),
            local_port: lport,
            remote_port,
            pid: ssh_pid,
        });
        // Store bastion tunnel pid as a synthetic entry (remote_port=0 signals bastion helper)
        entries.push(TunnelEntry {
            vm_name: format!("{}__bastion__{}", vm.name, i),
            local_port: bastion_local_port,
            remote_port: 0,
            pid: bastion_pid,
        });
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

fn cmd_tunnel_list() -> Result<()> {
    let entries = prune_tunnels(load_tunnels()?);
    if entries.is_empty() {
        println!("No active tunnels.");
        return Ok(());
    }

    // Hide internal bastion helper entries from the user
    let visible: Vec<_> = entries.iter().filter(|e| e.remote_port != 0).collect();
    if visible.is_empty() {
        println!("No active tunnels.");
        return Ok(());
    }

    println!("{:<20} {:>12}  {:>12}  {:>8}", "VM", "LOCAL PORT", "REMOTE PORT", "PID");
    println!("{}", "-".repeat(58));
    for e in &visible {
        println!("{:<20} {:>12}  {:>12}  {:>8}", e.vm_name, e.local_port, e.remote_port, e.pid);
    }
    Ok(())
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
                .map(|v| e.vm_name == v || e.vm_name.starts_with(&format!("{}__bastion__", v)))
                .unwrap_or(false);

        if should_close {
            let _ = std::process::Command::new("kill")
                .arg(e.pid.to_string())
                .status();
            if e.remote_port != 0 {
                println!("Closed tunnel: localhost:{} → {}:{}", e.local_port, e.vm_name, e.remote_port);
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
