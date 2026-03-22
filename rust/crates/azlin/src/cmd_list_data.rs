//! Data collection helpers for the list command (tmux, latency, health, procs).
#![allow(dead_code)]

use super::*;
use azlin_core::models::VmInfo;
use std::collections::HashMap;

/// Maximum number of tmux sessions to restore per VM to prevent resource exhaustion.
const MAX_SESSIONS_PER_VM: usize = 20;

/// Resolve SSH key path, preferring azlin_key over id_rsa.
fn resolve_ssh_key() -> Option<std::path::PathBuf> {
    home_dir()
        .ok()
        .map(|h| h.join(".ssh").join("azlin_key"))
        .filter(|p| p.exists())
        .or_else(|| {
            home_dir()
                .ok()
                .map(|h| h.join(".ssh").join("id_rsa"))
                .filter(|p| p.exists())
        })
}

/// Collect tmux sessions for all running VMs via SSH (direct or bastion).
pub(crate) fn collect_tmux_sessions(
    vms: &[VmInfo],
    effective_rg: &str,
    is_table_output: bool,
    verbose: bool,
    subscription_id: &str,
    connect_timeout: u64,
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

    let ssh_key = resolve_ssh_key();
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
        let timeout_str = format!("ConnectTimeout={}", connect_timeout);
        let output = if let Some(ip) = vm.public_ip.as_deref() {
            // Direct SSH to public IP
            let mut ssh_args = vec![
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                &timeout_str,
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
            match tunnel_pool.get_or_create(&vm_id, bastion_name, &vm.resource_group) {
                Ok(port) => {
                    let mut ssh_args = vec![
                        "-o".to_string(),
                        "StrictHostKeyChecking=accept-new".to_string(),
                        "-o".to_string(),
                        timeout_str.clone(),
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

/// Collect detailed health metrics (CPU, Mem, Disk, Agent) for running VMs via SSH.
pub(crate) fn collect_health_data(
    vms: &[VmInfo],
    effective_rg: &str,
    subscription_id: &str,
) -> HashMap<String, crate::HealthMetrics> {
    let mut health_data = HashMap::new();

    // Build bastion name map (region -> bastion_name) for private VMs
    let bastion_map: HashMap<String, String> =
        crate::list_helpers::detect_bastion_hosts(effective_rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();

    let ssh_key_path = resolve_ssh_key();

    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        let ip = match vm.public_ip.as_deref().or(vm.private_ip.as_deref()) {
            Some(ip) => ip,
            None => continue,
        };
        let user = vm
            .admin_username
            .as_deref()
            .unwrap_or(DEFAULT_ADMIN_USERNAME);
        let state = vm.power_state.to_string();

        // Build bastion info when there is no public IP
        let bastion_info_owned: Option<(String, String, String, Option<std::path::PathBuf>)> = if vm
            .public_ip
            .is_none()
        {
            bastion_map.get(&vm.location).map(|bn| {
                    let vm_rid = format!(
                        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                        subscription_id, vm.resource_group, vm.name
                    );
                    (
                        bn.clone(),
                        vm.resource_group.clone(),
                        vm_rid,
                        ssh_key_path.clone(),
                    )
                })
        } else {
            None
        };
        let bastion_ref = bastion_info_owned
            .as_ref()
            .map(|(bn, rg_b, rid, key)| (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref()));

        let metrics = crate::collect_health_metrics(&vm.name, ip, user, &state, bastion_ref);
        health_data.insert(vm.name.clone(), metrics);
    }
    health_data
}

/// Collect top process data for running VMs.
pub(crate) fn collect_procs(vms: &[VmInfo], connect_timeout: u64) -> HashMap<String, String> {
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
            let timeout_val = format!("ConnectTimeout={}", connect_timeout);
            let output = std::process::Command::new("ssh")
                .args([
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    &timeout_val,
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

/// Parse a raw tmux session string (e.g. `"main:1"`) into a validated session name.
///
/// Splits on `:` to strip the `attached` count suffix, trims whitespace, then validates
/// the name against the alphanumeric + `_` + `-` allowlist.  Returns `None` when the
/// name is empty, exceeds 128 characters, or contains any disallowed character.
pub(crate) fn parse_session_name(raw: &str) -> Option<String> {
    let name = raw.split(':').next().unwrap_or("").trim().to_string();
    if name.is_empty() || name.len() > 128 {
        return None;
    }
    if !name
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return None;
    }
    Some(name)
}

/// Validate a VM name before using it in process arguments.
///
/// Allowlist permits alphanumeric characters, underscores, hyphens, and dots (dots are
/// required for Azure FQDNs) and rejects everything else, preventing argument injection.
pub(crate) fn is_valid_restore_vm_name(name: &str) -> bool {
    if name.is_empty() {
        return false;
    }
    name.chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

/// Restore tmux sessions by connecting to each VM.
pub(crate) fn restore_tmux_sessions(tmux_sessions: &HashMap<String, Vec<String>>) {
    println!("\nRestoring tmux sessions...");

    // In test builds, skip spawning real terminal processes to avoid
    // opening windows on the developer's screen during cargo test.
    if cfg!(test) || std::env::var("AZLIN_TEST_MODE").is_ok() {
        for (vm_name, sessions) in tmux_sessions {
            if !is_valid_restore_vm_name(vm_name) {
                eprintln!("  Warning: skipping VM with invalid name");
                continue;
            }
            // Iterate over all sessions, not just the first
            if sessions.len() > MAX_SESSIONS_PER_VM {
                eprintln!(
                    "  Warning: limiting {} to {} sessions (found {})",
                    vm_name, MAX_SESSIONS_PER_VM, sessions.len()
                );
            }
            for raw_session in sessions.iter().take(MAX_SESSIONS_PER_VM) {
                if let Some(session) = parse_session_name(raw_session) {
                    println!(
                        "  [dry-run] Would connect to {} (session: {})",
                        vm_name, session
                    );
                } else {
                    eprintln!("  Warning: skipping invalid session name for {}", vm_name);
                }
            }
        }
        return;
    }

    let use_wt = std::env::var("WT_SESSION").is_ok();
    let use_macos = cfg!(target_os = "macos") && !use_wt;

    // Resolve the current executable path so we can re-invoke ourselves
    // in new terminal tabs. Using bare "azlin" fails when installed via
    // uvx or cargo install since it may not be in PATH for new shells.
    let self_exe = std::env::current_exe()
        .ok()
        .and_then(|p| p.to_str().map(|s| s.to_string()))
        .unwrap_or_else(|| "azlin".to_string());

    // Detect which macOS terminal emulator is running (if on macOS).
    let macos_terminal = if use_macos {
        detect_macos_terminal()
    } else {
        MacTerminal::Unknown
    };

    for (vm_name, sessions) in tmux_sessions {
        if !is_valid_restore_vm_name(vm_name) {
            eprintln!("  Warning: skipping VM with invalid name");
            continue;
        }

        // Check if we need to limit the number of sessions
        if sessions.len() > MAX_SESSIONS_PER_VM {
            eprintln!(
                "  Warning: limiting {} to {} sessions (found {})",
                vm_name, MAX_SESSIONS_PER_VM, sessions.len()
            );
        }

        // Iterate over all sessions up to MAX_SESSIONS_PER_VM
        for raw_session in sessions.iter().take(MAX_SESSIONS_PER_VM) {
            let session = match parse_session_name(raw_session) {
                Some(s) => s,
                None => {
                    eprintln!("  Warning: skipping invalid session name for {}", vm_name);
                    continue;
                }
            };

            if use_wt {
                println!("  Opening tab: {} (session: {})", vm_name, session);
                // WT_SESSION is set inside WSL when running under Windows Terminal.
                // wt.exe new-tab runs its command in the default WT profile (often
                // PowerShell), so we must explicitly use wsl.exe to re-enter WSL
                // where the azlin binary lives.
                let wsl_distro =
                    std::env::var("WSL_DISTRO_NAME").unwrap_or_else(|_| "".to_string());
                let mut wt_args: Vec<&str> = vec!["-w", "0", "new-tab"];
                if !wsl_distro.is_empty() {
                    wt_args.extend_from_slice(&["wsl.exe", "-d", &wsl_distro, "--"]);
                }
                wt_args.extend_from_slice(&[
                    &self_exe,
                    "connect",
                    vm_name,
                    "--tmux-session",
                    &session,
                ]);
                if let Err(e) = std::process::Command::new("wt.exe")
                    .args(&wt_args)
                    .stdin(std::process::Stdio::null())
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn()
                {
                    eprintln!("  Warning: failed to open tab for {}: {}", vm_name, e);
                }
            } else if use_macos {
                println!("  Opening window: {} (session: {})", vm_name, session);
                let connect_cmd = escape_for_applescript(&format!(
                    "{} connect {} --tmux-session {}",
                    &self_exe, vm_name, &session
                ));
                if let Err(e) = open_macos_terminal(&macos_terminal, &connect_cmd) {
                    eprintln!("  Warning: failed to open window for {}: {}", vm_name, e);
                }
            } else {
                println!("  Connecting to {} (session: {})", vm_name, session);
                // On Linux without Windows Terminal, spawn in background.
                // SSH needs a TTY for interactive use, but without a known
                // terminal emulator we can only fire-and-forget.
                if let Err(e) = std::process::Command::new(&self_exe)
                    .args(["connect", vm_name, "--tmux-session", &session])
                    .stdin(std::process::Stdio::null())
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn()
                {
                    eprintln!("  Warning: failed to connect to {}: {}", vm_name, e);
                }
            }
        }
    }
    println!("Session restore initiated.");
}

/// Supported macOS terminal emulators.
#[derive(Debug, PartialEq)]
enum MacTerminal {
    TerminalApp,
    ITerm2,
    Unknown,
}

/// Detect which macOS terminal emulator is running.
fn detect_macos_terminal() -> MacTerminal {
    // TERM_PROGRAM is set by most macOS terminal emulators.
    match std::env::var("TERM_PROGRAM").as_deref() {
        Ok("Apple_Terminal") => MacTerminal::TerminalApp,
        Ok("iTerm.app") => MacTerminal::ITerm2,
        _ => MacTerminal::Unknown,
    }
}

/// Escape a string for safe embedding in AppleScript double-quoted strings.
/// Handles `\` and `"` which are the two special characters in AppleScript strings.
fn escape_for_applescript(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Open a new macOS terminal window running the given command string.
/// The command string must already be escaped via `escape_for_applescript`.
fn open_macos_terminal(terminal: &MacTerminal, command: &str) -> Result<(), String> {
    match terminal {
        MacTerminal::ITerm2 => {
            // iTerm2: create a new window (or tab in existing window).
            // Check for existing windows first to avoid errors.
            let script = format!(
                r#"tell application "iTerm2"
    if (count of windows) = 0 then
        create window with default profile
        tell current session of current window
            write text "{cmd}"
        end tell
    else
        tell current window
            create tab with default profile
            tell current session
                write text "{cmd}"
            end tell
        end tell
    end if
end tell"#,
                cmd = command
            );
            run_osascript(&script)
        }
        MacTerminal::TerminalApp | MacTerminal::Unknown => {
            // Terminal.app: `do script` opens a new window.
            // For Unknown, fall back to Terminal.app since it's always available on macOS.
            let script = format!(
                r#"tell application "Terminal"
    activate
    do script "{}"
end tell"#,
                command
            );
            run_osascript(&script)
        }
    }
}

/// Execute an AppleScript via osascript.
fn run_osascript(script: &str) -> Result<(), String> {
    let result = std::process::Command::new("osascript")
        .args(["-e", script])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .output();
    match result {
        Ok(output) if output.status.success() => Ok(()),
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            Err(format!("osascript failed: {}", stderr.trim()))
        }
        Err(e) => Err(format!("failed to run osascript: {}", e)),
    }
}
