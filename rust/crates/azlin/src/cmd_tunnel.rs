//! `azlin tunnel` — port-forwarding to remote VMs via Azure Bastion or SSH.
//!
//! For non-SSH ports, uses direct `az bastion tunnel` (single hop).
//! For SSH (port 22), layers `ssh -N -L` on top of a bastion tunnel.
//! Records PIDs in `~/.azlin/tunnels.json` and provides `list`/`close`.

#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::os::unix::process::CommandExt;
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

/// Kill a process and its entire process group.
/// `az` spawns bash→python3, so killing just the parent leaves orphans.
fn kill_process_tree(pid: u32) {
    let _ = std::process::Command::new("kill")
        .args(["--", &format!("-{}", pid)])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    let _ = std::process::Command::new("kill")
        .arg(pid.to_string())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
}

/// Spawn a command as a new process group leader so we can kill the
/// entire tree (e.g. az → bash → python3) with a single signal.
fn spawn_as_group_leader(cmd: &mut std::process::Command) -> Result<std::process::Child> {
    unsafe {
        cmd.pre_exec(|| {
            libc::setsid();
            Ok(())
        });
    }
    cmd.spawn().map_err(Into::into)
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
                    kill_process_tree(e.pid);
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

    // For non-SSH ports, use a direct `az bastion tunnel` with
    // `--resource-port <app_port>` — single hop, no fragile SSH layer.
    // Only use the two-hop approach (bastion→22 + SSH -L) for port 22.

    for (i, &remote_port) in ports.iter().enumerate() {
        let lport = if ports.len() == 1 {
            local_port.unwrap_or(remote_port)
        } else {
            remote_port
        };

        if remote_port == 22 {
            open_bastion_ssh_tunnel(
                bastion_name, rg, &vm_rid, vm, user, lport, key, entries, i,
            )?;
        } else {
            open_bastion_direct_tunnel(
                bastion_name, rg, &vm_rid, vm, lport, remote_port, entries,
            )?;
        }
    }
    Ok(())
}

/// Direct bastion tunnel for application (non-SSH) ports.
///
/// `az bastion tunnel --resource-port <app_port> --port <local_port>`
/// maps localhost:<local_port> straight to VM:<app_port> through the bastion.
fn open_bastion_direct_tunnel(
    bastion_name: &str,
    rg: &str,
    vm_rid: &str,
    vm: &azlin_core::models::VmInfo,
    local_port: u16,
    remote_port: u16,
    entries: &mut Vec<TunnelEntry>,
) -> Result<()> {
    let mut cmd = std::process::Command::new("az");
    cmd.args([
            "network",
            "bastion",
            "tunnel",
            "--name",
            bastion_name,
            "--resource-group",
            rg,
            "--target-resource-id",
            vm_rid,
            "--resource-port",
            &remote_port.to_string(),
            "--port",
            &local_port.to_string(),
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    let bastion_child = spawn_as_group_leader(&mut cmd)
        .context("Failed to spawn az bastion tunnel")?;

    let pid = bastion_child.id();
    std::mem::forget(bastion_child);

    wait_for_listener(local_port, std::time::Duration::from_secs(15))?;

    println!(
        "Forwarding localhost:{} → {}:{} (via bastion)",
        local_port, vm.name, remote_port
    );

    entries.push(TunnelEntry {
        vm_name: vm.name.clone(),
        local_port,
        remote_port,
        pid,
    });

    Ok(())
}

/// Two-hop bastion tunnel for SSH (port 22) forwarding.
///
/// Step 1: `az bastion tunnel --resource-port 22 --port <ephemeral>`
/// Step 2: `ssh -N -L <lport>:localhost:22 -p <ephemeral> user@127.0.0.1`
#[allow(clippy::too_many_arguments)]
fn open_bastion_ssh_tunnel(
    bastion_name: &str,
    rg: &str,
    vm_rid: &str,
    vm: &azlin_core::models::VmInfo,
    user: &str,
    local_port: u16,
    key: Option<&std::path::Path>,
    entries: &mut Vec<TunnelEntry>,
    index: usize,
) -> Result<()> {
    let bastion_local_port: u16 = 50200 + index as u16;

    let mut cmd = std::process::Command::new("az");
    cmd.args([
            "network",
            "bastion",
            "tunnel",
            "--name",
            bastion_name,
            "--resource-group",
            rg,
            "--target-resource-id",
            vm_rid,
            "--resource-port",
            "22",
            "--port",
            &bastion_local_port.to_string(),
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    let bastion_child = spawn_as_group_leader(&mut cmd)
        .context("Failed to spawn az bastion tunnel")?;

    let bastion_pid = bastion_child.id();
    std::mem::forget(bastion_child);

    wait_for_listener(bastion_local_port, std::time::Duration::from_secs(15))?;

    let mut ssh_args = vec![
        "-N".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        "ServerAliveInterval=15".to_string(),
        "-o".to_string(),
        "ServerAliveCountMax=3".to_string(),
        "-o".to_string(),
        "ExitOnForwardFailure=yes".to_string(),
        "-p".to_string(),
        bastion_local_port.to_string(),
        "-L".to_string(),
        format!("{}:localhost:22", local_port),
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
        .with_context(|| "Failed to spawn ssh -L for port 22".to_string())?;

    let ssh_pid = ssh_child.id();
    std::mem::forget(ssh_child);

    wait_for_listener(local_port, std::time::Duration::from_secs(10))?;

    println!(
        "Forwarding localhost:{} → {}:22 (via bastion + SSH)",
        local_port, vm.name
    );

    entries.push(TunnelEntry {
        vm_name: vm.name.clone(),
        local_port,
        remote_port: 22,
        pid: ssh_pid,
    });
    entries.push(TunnelEntry {
        vm_name: format!("{}__bastion__{}", vm.name, index),
        local_port: bastion_local_port,
        remote_port: 0,
        pid: bastion_pid,
    });

    Ok(())
}

/// Poll until a TCP listener appears on 127.0.0.1:<port>, or timeout.
fn wait_for_listener(port: u16, timeout: std::time::Duration) -> Result<()> {
    let start = std::time::Instant::now();
    let addr: std::net::SocketAddr = ([127, 0, 0, 1], port).into();
    while start.elapsed() < timeout {
        if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_millis(200))
            .is_ok()
        {
            return Ok(());
        }
        std::thread::sleep(std::time::Duration::from_millis(300));
    }
    anyhow::bail!(
        "Timed out waiting for listener on localhost:{} (waited {:?})",
        port,
        timeout
    )
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

    // Hide internal bastion helper entries from the user
    let visible: Vec<_> = entries.iter().filter(|e| e.remote_port != 0).collect();
    if visible.is_empty() {
        println!("No active tunnels.");
        return Ok(());
    }

    println!(
        "{:<20} {:>12}  {:>12}  {:>8}",
        "VM", "LOCAL PORT", "REMOTE PORT", "PID"
    );
    println!("{}", "-".repeat(58));
    for e in &visible {
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
                .map(|v| e.vm_name == v || e.vm_name.starts_with(&format!("{}__bastion__", v)))
                .unwrap_or(false);

        if should_close {
            kill_process_tree(e.pid);
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
