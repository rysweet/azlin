//! Data collection helpers for the list command (tmux, latency, health, procs).
#![allow(dead_code)]

use super::*;
use azlin_core::models::VmInfo;
use std::collections::HashMap;

/// Maximum number of tmux sessions to restore per VM to prevent resource exhaustion.
const MAX_SESSIONS_PER_VM: usize = 20;

/// Resolve SSH key path from the shared azlin private-key priority list.
fn resolve_ssh_key() -> Option<std::path::PathBuf> {
    let ssh_dir = dirs::home_dir()?.join(".ssh");
    crate::key_helpers::find_preferred_private_key(&ssh_dir)
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
                    let port_str = port.to_string();
                    let user_host = format!("{}@127.0.0.1", user);
                    let mut ssh_args: Vec<&str> = vec![
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        "-o",
                        &timeout_str,
                        "-o",
                        "BatchMode=yes",
                        "-p",
                        &port_str,
                    ];
                    let key_str;
                    if let Some(ref key) = ssh_key {
                        key_str = key.to_string_lossy();
                        ssh_args.push("-i");
                        ssh_args.push(&key_str);
                    }
                    ssh_args.push(&user_host);
                    ssh_args.push(tmux_cmd);
                    std::process::Command::new("ssh")
                        .args(&ssh_args)
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
    if name.is_empty() || name.len() > 256 {
        return false;
    }
    name.chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

/// Build the Windows Terminal argument list for restoring a single tmux session.
///
/// When `wsl_distro` is non-empty, the command is wrapped in `bash -lc '...'`
/// so the user's login shell environment (PATH, SSH_AUTH_SOCK, etc.) is loaded.
/// Without that wrapper, `wsl.exe -d <distro> -- <binary>` runs outside any
/// shell, so tools like `ssh` and `az` may not be found.
///
/// `restore_mode` controls window placement:
/// - `Tab` → `wt.exe -w 0 new-tab ...` (reuse existing window)
/// - `Window` → `wt.exe -w new new-tab ...` (new window per session)
/// - `Auto` is resolved by the caller before reaching here; treated as `Tab`.
pub(crate) fn build_wt_restore_args(
    wsl_distro: &str,
    self_exe: &str,
    vm_name: &str,
    session: &str,
    restore_mode: &azlin_core::RestoreMode,
) -> Vec<String> {
    let mut args: Vec<String> = match restore_mode {
        azlin_core::RestoreMode::Window => vec!["-w".into(), "new".into(), "new-tab".into()],
        _ => vec!["-w".into(), "0".into(), "new-tab".into()],
    };
    if !wsl_distro.is_empty() {
        let inner_cmd = format!(
            "exec {} connect {} --tmux-session {}",
            crate::dispatch_helpers::shell_escape(self_exe),
            crate::dispatch_helpers::shell_escape(vm_name),
            crate::dispatch_helpers::shell_escape(session),
        );
        args.extend_from_slice(&[
            "wsl.exe".into(),
            "-d".into(),
            wsl_distro.into(),
            "--".into(),
            "bash".into(),
            "-lc".into(),
            inner_cmd,
        ]);
    } else {
        args.extend_from_slice(&[
            self_exe.into(),
            "connect".into(),
            vm_name.into(),
            "--tmux-session".into(),
            session.into(),
        ]);
    }
    args
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
                    vm_name,
                    MAX_SESSIONS_PER_VM,
                    sessions.len()
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

    let detected_wt = std::env::var("WT_SESSION").is_ok();

    // Load config for restore_mode preference.
    let config = azlin_core::AzlinConfig::load().unwrap_or_default();
    let restore_mode = &config.restore_mode;

    // If restore_mode is explicitly set to tab or window, force wt.exe usage
    // — but only when we're in WSL where wt.exe is actually available.
    let in_wsl = std::env::var("WSL_DISTRO_NAME").is_ok_and(|v| !v.is_empty());
    let force_wt = in_wsl
        && matches!(
            restore_mode,
            azlin_core::RestoreMode::Tab | azlin_core::RestoreMode::Window
        );
    let use_wt = detected_wt || force_wt;
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
                vm_name,
                MAX_SESSIONS_PER_VM,
                sessions.len()
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
                let wsl_distro =
                    std::env::var("WSL_DISTRO_NAME").unwrap_or_else(|_| "".to_string());
                let wt_args = build_wt_restore_args(&wsl_distro, &self_exe, vm_name, &session, restore_mode);
                let wt_str_args: Vec<&str> = wt_args.iter().map(|s| s.as_str()).collect();
                match std::process::Command::new("wt.exe")
                    .args(&wt_str_args)
                    .stdin(std::process::Stdio::null())
                    .stdout(std::process::Stdio::piped())
                    .stderr(std::process::Stdio::piped())
                    .spawn()
                    .and_then(|child| child.wait_with_output())
                {
                    Ok(output) if !output.status.success() => {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        eprintln!(
                            "  Warning: wt.exe failed for {} (exit {}): {}",
                            vm_name,
                            output.status.code().unwrap_or(-1),
                            stderr.trim()
                        );
                    }
                    Err(e) => {
                        eprintln!("  Warning: failed to open tab for {}: {}", vm_name, e);
                    }
                    _ => {}
                }
                // Windows Terminal silently drops new-tab commands when
                // many are issued simultaneously. A small delay between
                // spawns prevents lost tabs.
                std::thread::sleep(std::time::Duration::from_millis(500));
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
                // On Linux without Windows Terminal, open a terminal emulator.
                let connect_cmd = format!(
                    "{} connect {} --tmux-session {}",
                    crate::dispatch_helpers::shell_escape(&self_exe),
                    crate::dispatch_helpers::shell_escape(vm_name),
                    crate::dispatch_helpers::shell_escape(&session),
                );
                if let Some(term) = detect_linux_terminal() {
                    println!("  Opening terminal: {} (session: {})", vm_name, session);
                    if let Err(e) = open_linux_terminal(&term, &connect_cmd) {
                        eprintln!("  Warning: failed to open terminal for {}: {}", vm_name, e);
                    }
                } else {
                    eprintln!(
                        "  No terminal emulator detected for {}. Run manually:",
                        vm_name
                    );
                    eprintln!(
                        "    azlin connect {} --tmux-session {}",
                        vm_name, session
                    );
                    eprintln!("  Tip: set AZLIN_TERMINAL=<your-terminal> to enable auto-restore.");
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

// ── Linux terminal support ──────────────────────────────────────────────

/// Supported Linux terminal emulators.
#[derive(Debug, PartialEq)]
enum LinuxTerminal {
    Custom(String),
    GnomeTerminal,
    Xfce4Terminal,
    Konsole,
    Xterm,
}

/// Detect an available Linux terminal emulator.
///
/// Checks `AZLIN_TERMINAL` env var first (user override, like `$EDITOR`),
/// then probes known emulators via `which`.
fn detect_linux_terminal() -> Option<LinuxTerminal> {
    if let Ok(custom) = std::env::var("AZLIN_TERMINAL") {
        if !custom.is_empty() {
            // Reject values containing shell metacharacters to prevent injection.
            if custom.contains([';', '&', '|', '$', '`', '\n', '(', ')'])
            {
                eprintln!(
                    "  Warning: AZLIN_TERMINAL contains shell metacharacters, ignoring: {}",
                    custom
                );
            } else if which_exists(&custom) {
                return Some(LinuxTerminal::Custom(custom));
            } else {
                eprintln!(
                    "  Warning: AZLIN_TERMINAL binary not found on PATH: {}",
                    custom
                );
            }
        }
    }
    let candidates = [
        ("gnome-terminal", LinuxTerminal::GnomeTerminal),
        ("xfce4-terminal", LinuxTerminal::Xfce4Terminal),
        ("konsole", LinuxTerminal::Konsole),
        ("xterm", LinuxTerminal::Xterm),
    ];
    for (bin, variant) in candidates {
        if which_exists(bin) {
            return Some(variant);
        }
    }
    None
}

/// Check if a binary exists on PATH.
fn which_exists(name: &str) -> bool {
    std::process::Command::new("which")
        .arg(name)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Open a new Linux terminal window running the given shell command string.
fn open_linux_terminal(terminal: &LinuxTerminal, command: &str) -> Result<(), String> {
    let result = match terminal {
        LinuxTerminal::GnomeTerminal => std::process::Command::new("gnome-terminal")
            .args(["--", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
        LinuxTerminal::Konsole => std::process::Command::new("konsole")
            .args(["-e", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
        LinuxTerminal::Xfce4Terminal => {
            // xfce4-terminal -e expects a single command string (shell-parsed)
            let wrapped = format!("bash -lc {}", crate::dispatch_helpers::shell_escape(command));
            std::process::Command::new("xfce4-terminal")
                .args(["-e", &wrapped])
                .stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn()
        }
        LinuxTerminal::Xterm => std::process::Command::new("xterm")
            .args(["-e", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
        LinuxTerminal::Custom(bin) => std::process::Command::new(bin)
            .args(["-e", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
    };
    match result {
        Ok(_) => Ok(()),
        Err(e) => Err(format!("failed to launch terminal: {}", e)),
    }
}
