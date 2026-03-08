//! Data collection helpers for the list command (tmux, latency, health, procs).
#![allow(dead_code)]

use super::*;
use azlin_core::models::VmInfo;
use std::collections::HashMap;

/// Collect tmux sessions for all running VMs via SSH (direct or bastion).
pub(crate) fn collect_tmux_sessions(
    vms: &[VmInfo],
    effective_rg: &str,
    is_table_output: bool,
    verbose: bool,
    subscription_id: &str,
) -> HashMap<String, Vec<String>> {
    let mut tmux_sessions: HashMap<String, Vec<String>> = HashMap::new();

    // Build bastion name map (region -> bastion_name) for private VMs
    let bastion_map: HashMap<String, String> = if is_table_output {
        if let Ok(bastions) = crate::list_helpers::detect_bastion_hosts(effective_rg) {
            bastions
                .into_iter()
                .map(|(name, location, _)| (location, name))
                .collect()
        } else {
            HashMap::new()
        }
    } else {
        HashMap::new()
    };

    // Resolve SSH key path
    let ssh_key = home_dir()
        .ok()
        .map(|h| h.join(".ssh").join("azlin_key"))
        .filter(|p| p.exists())
        .or_else(|| {
            home_dir()
                .ok()
                .map(|h| h.join(".ssh").join("id_rsa"))
                .filter(|p| p.exists())
        });

    let mut tunnel_pool = BastionTunnelPool::new();

    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        let user = vm
            .admin_username
            .as_deref()
            .unwrap_or(DEFAULT_ADMIN_USERNAME);
        let tmux_cmd =
            "tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null || true";

        // Determine whether to use direct SSH or bastion tunnel
        let output = if let Some(ip) = vm.public_ip.as_deref() {
            // Direct SSH to public IP
            let mut ssh_args = vec![
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "BatchMode=yes",
            ];
            let user_host = format!("{}@{}", user, ip);
            if let Some(ref key) = ssh_key {
                ssh_args.push("-i");
                ssh_args.push(key.to_str().unwrap_or(""));
            }
            ssh_args.push(&user_host);
            ssh_args.push(tmux_cmd);

            std::process::Command::new("ssh")
                .args(&ssh_args)
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .output()
        } else if let Some(bastion_name) = bastion_map.get(&vm.location) {
            // Use bastion tunnel
            let vm_id = format!(
                "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                subscription_id, vm.resource_group, vm.name
            );
            match tunnel_pool.get_or_create(&vm.name, bastion_name, &vm.resource_group, &vm_id) {
                Ok(port) => {
                    let mut ssh_args = vec![
                        "-o".to_string(),
                        "StrictHostKeyChecking=accept-new".to_string(),
                        "-o".to_string(),
                        "ConnectTimeout=5".to_string(),
                        "-o".to_string(),
                        "BatchMode=yes".to_string(),
                        "-p".to_string(),
                        port.to_string(),
                    ];
                    if let Some(ref key) = ssh_key {
                        ssh_args.push("-i".to_string());
                        ssh_args.push(key.to_string_lossy().to_string());
                    }
                    ssh_args.push(format!("{}@127.0.0.1", user));
                    ssh_args.push(tmux_cmd.to_string());
                    let str_args: Vec<&str> = ssh_args.iter().map(|s| s.as_str()).collect();
                    std::process::Command::new("ssh")
                        .args(&str_args)
                        .stdout(std::process::Stdio::piped())
                        .stderr(std::process::Stdio::piped())
                        .output()
                }
                Err(e) => {
                    if verbose {
                        eprintln!(
                            "[VERBOSE] Failed to create bastion tunnel for {}: {}",
                            vm.name, e
                        );
                    }
                    continue;
                }
            }
        } else {
            continue; // No bastion available for this region
        };

        if let Ok(out) = output {
            if out.status.success() {
                let sessions: Vec<String> = String::from_utf8_lossy(&out.stdout)
                    .lines()
                    .filter(|l| !l.is_empty() && !l.starts_with('{'))
                    .map(|l| l.to_string())
                    .collect();
                if verbose {
                    eprintln!("[VERBOSE] {} -> {} sessions", vm.name, sessions.len());
                }
                if !sessions.is_empty() {
                    tmux_sessions.insert(vm.name.clone(), sessions);
                }
            }
        }
    }
    tmux_sessions
}

/// Collect latency measurements for running VMs via TCP connect.
pub(crate) fn collect_latencies(vms: &[VmInfo]) -> HashMap<String, u64> {
    let mut latencies = HashMap::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        if let Some(ip) = vm.public_ip.as_deref().or(vm.private_ip.as_deref()) {
            let start = std::time::Instant::now();
            if std::net::TcpStream::connect_timeout(
                &format!("{}:22", ip)
                    .parse()
                    .unwrap_or_else(|_| std::net::SocketAddr::from(([0, 0, 0, 0], 22))),
                std::time::Duration::from_secs(2),
            )
            .is_ok()
            {
                latencies.insert(vm.name.clone(), start.elapsed().as_millis() as u64);
            }
        }
    }
    latencies
}

/// Collect health data for running VMs via SSH uptime check.
pub(crate) fn collect_health(vms: &[VmInfo], _verbose: bool) -> HashMap<String, String> {
    let mut health_data = HashMap::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
        if let Some(ip) = ip {
            let user = vm
                .admin_username
                .as_deref()
                .unwrap_or(DEFAULT_ADMIN_USERNAME);
            let output = std::process::Command::new("ssh")
                .args([
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "BatchMode=yes",
                    &format!("{}@{}", user, ip),
                    "uptime -p 2>/dev/null || uptime",
                ])
                .output();
            if let Ok(out) = output {
                if out.status.success() {
                    let summary = String::from_utf8_lossy(&out.stdout).trim().to_string();
                    if !summary.is_empty() {
                        health_data.insert(vm.name.clone(), summary);
                    }
                }
            }
        }
    }
    health_data
}

/// Collect top process data for running VMs.
pub(crate) fn collect_procs(vms: &[VmInfo]) -> HashMap<String, String> {
    let mut proc_data = HashMap::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
        if let Some(ip) = ip {
            let user = vm
                .admin_username
                .as_deref()
                .unwrap_or(DEFAULT_ADMIN_USERNAME);
            let output = std::process::Command::new("ssh")
                .args([
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    "ConnectTimeout=10",
                    "-o",
                    "BatchMode=yes",
                    &format!("{}@{}", user, ip),
                    "ps aux --sort=-%mem | head -6 | tail -5 | awk '{print $11}' | tr '\\n' ', '",
                ])
                .output();
            if let Ok(out) = output {
                if out.status.success() {
                    let procs = String::from_utf8_lossy(&out.stdout).trim().to_string();
                    proc_data.insert(vm.name.clone(), procs);
                }
            }
        }
    }
    proc_data
}

/// Restore tmux sessions by connecting to each VM.
pub(crate) fn restore_tmux_sessions(tmux_sessions: &HashMap<String, Vec<String>>) {
    println!("\nRestoring tmux sessions...");
    let use_wt = std::env::var("WT_SESSION").is_ok();
    for (vm_name, sessions) in tmux_sessions {
        if let Some(first_session) = sessions.first() {
            if use_wt {
                println!("  Opening tab: {} (session: {})", vm_name, first_session);
                let _ = std::process::Command::new("wt.exe")
                    .args([
                        "-w",
                        "0",
                        "new-tab",
                        "azlin",
                        "connect",
                        vm_name,
                        "--tmux-session",
                        first_session,
                    ])
                    .spawn();
            } else {
                println!("  Connecting to {} (session: {})", vm_name, first_session);
                let _ = std::process::Command::new("azlin")
                    .args(["connect", vm_name, "--tmux-session", first_session])
                    .spawn();
            }
        }
    }
    println!("Session restore initiated.");
}
