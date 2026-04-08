//! `azlin gui` — Open a remote GUI desktop via VNC over SSH tunnel.
//!
//! Workflow:
//! 1. Check local prerequisites (X server, vncviewer)
//! 2. Resolve VM and detect bastion route
//! 3. Open bastion tunnel to VM:22
//! 4. Check/install remote deps (tigervnc, xfce4)
//! 5. Generate random VNC password and start VNC server on localhost
//! 6. SSH port-forward VNC port (5901) through tunnel
//! 7. Launch local vncviewer
//! 8. Wait for viewer exit, then clean shutdown

#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

/// VNC session mode.
enum VncMode {
    /// Full XFCE desktop
    Desktop,
    /// Minimal window manager (openbox) only
    Minimal,
    /// Single application, no desktop or WM
    App(String),
}

/// VNC display number (maps to port 5901).
const VNC_DISPLAY: u16 = 1;

/// VNC port = 5900 + display number.
const VNC_PORT: u16 = 5900 + VNC_DISPLAY;

/// Hard timeout for the remote GUI dependency/setup phase.
const GUI_SETUP_TIMEOUT_SECS: u64 = 600;

fn resolve_gui_target_user(requested_user: &str, detected_user: &str) -> String {
    if requested_user != DEFAULT_ADMIN_USERNAME {
        requested_user.to_string()
    } else {
        detected_user.to_string()
    }
}

fn build_vnc_xstartup_body(mode: &VncMode) -> String {
    // DISPLAY must be explicitly exported for apps to find the VNC X server.
    // xhost +local: allows local apps to connect without xauth issues
    // (safe because VNC only listens on localhost).
    let preamble = format!(
        "export DISPLAY=:{}\nxhost +local: >/dev/null 2>&1\nunset SESSION_MANAGER\nunset DBUS_SESSION_BUS_ADDRESS\nif [ -z \"$XDG_RUNTIME_DIR\" ] && [ -d \"/run/user/$(id -u)\" ]; then export XDG_RUNTIME_DIR=\"/run/user/$(id -u)\"; fi\nexport XDG_SESSION_TYPE=x11",
        VNC_DISPLAY
    );
    match mode {
        VncMode::Desktop => {
            format!("{}\nexec startxfce4", preamble)
        }
        VncMode::Minimal => {
            format!("{}\nexec openbox-session", preamble)
        }
        VncMode::App(cmd) => {
            let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(cmd);
            format!(
                "{}\n{}\nvncserver -kill :{} 2>/dev/null",
                preamble, wrapped, VNC_DISPLAY
            )
        }
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
    let azlin_cli::Commands::Gui {
        vm_identifier,
        resource_group,
        user,
        key,
        resolution,
        depth,
        yes: _yes,
        minimal,
        app,
    } = command
    else {
        unreachable!()
    };

    // Validate resolution format
    if !is_valid_resolution(&resolution) {
        anyhow::bail!(
            "Invalid resolution '{}'. Expected format: WIDTHxHEIGHT (e.g. 1920x1080)",
            resolution
        );
    }

    // Step 1: Check local prerequisites
    check_local_deps()?;

    // Step 2: Resolve VM
    let rg = resolve_resource_group(resource_group)?;

    let name = if let Some(n) = vm_identifier {
        n
    } else {
        anyhow::bail!("VM name is required for gui command. Usage: azlin gui <vm-name>");
    };

    let pb = penguin_spinner(&format!("Looking up {}...", name));
    let mut target = resolve_vm_ssh_target(&name, None, Some(rg.clone())).await?;
    target.user = resolve_gui_target_user(&user, &target.user);
    pb.finish_and_clear();
    let config = azlin_core::AzlinConfig::load().unwrap_or_default();
    let effective_key = key.or_else(resolve_ssh_key);
    let (ssh_cmd_prefix, _route_tunnel) = build_gui_ssh_command_prefix(
        &target,
        config.ssh_connect_timeout,
        effective_key.as_deref(),
    )?;

    // Determine VNC mode
    let vnc_mode = if let Some(cmd) = app {
        VncMode::App(cmd)
    } else if minimal {
        VncMode::Minimal
    } else {
        VncMode::Desktop
    };

    // Step 3: Check/install remote dependencies
    let pb = penguin_spinner("Checking remote dependencies...");
    check_remote_deps(&target, effective_key.as_deref(), &vnc_mode)?;
    pb.finish_and_clear();

    // Step 4: Start VNC server on the remote VM
    let pb = penguin_spinner("Starting VNC server...");
    let vnc_password = start_vnc_server(&ssh_cmd_prefix, &resolution, depth, &vnc_mode)?;
    pb.finish_and_clear();

    // Step 5: Open SSH port-forward for VNC
    let pb = penguin_spinner("Opening VNC tunnel...");
    let (local_vnc_port, tunnel_pids) = open_vnc_tunnel(&ssh_cmd_prefix)?;
    pb.finish_and_clear();

    let all_pids: Vec<u32> = tunnel_pids.to_vec();

    // Step 6: Launch local VNC viewer
    println!("Launching VNC viewer (127.0.0.1:{})...", local_vnc_port);
    eprintln!("(VNC password set on remote — not displayed for security)");
    println!("Press Ctrl+C to stop the GUI session.\n");

    let viewer_result = launch_viewer(&ssh_cmd_prefix, &vnc_password, local_vnc_port);

    // Step 7: Cleanup on exit
    cleanup(&all_pids, &ssh_cmd_prefix);

    viewer_result
}

// ---------------------------------------------------------------------------
// Local prerequisite checks
// ---------------------------------------------------------------------------

fn check_local_deps() -> Result<()> {
    // Check for X server availability
    let display_set = std::env::var("DISPLAY")
        .map(|d| !d.is_empty())
        .unwrap_or(false);
    let x_socket_exists = std::path::Path::new("/tmp/.X11-unix/X0").exists();

    if !display_set && !x_socket_exists {
        eprintln!("Warning: No X server detected.");
        eprintln!(
            "  WSLg should be available in WSL2 by default. Restart WSL if DISPLAY is not set."
        );
        eprintln!("  Alternatively, install an X server like VcXsrv or Xming.");
        // Not fatal — vncviewer may still work if DISPLAY gets set before launch
    }

    // Check for vncviewer
    let has_vncviewer = std::process::Command::new("which")
        .arg("vncviewer")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false);

    if !has_vncviewer {
        anyhow::bail!(
            "vncviewer not found. Install it with:\n  \
             sudo apt-get install -y tigervnc-viewer tigervnc-common\n  \
             Or on macOS: brew install --cask tigervnc-viewer"
        );
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// SSH prefix builders
// ---------------------------------------------------------------------------

/// Build an SSH command prefix for direct connection to a public-IP VM.
#[cfg(test)]
fn build_direct_ssh_prefix(ip: &str, user: &str, key: Option<&std::path::Path>) -> Vec<String> {
    let config = azlin_core::AzlinConfig::load().unwrap_or_default();
    let mut prefix = vec!["ssh".to_string()];
    prefix.extend(crate::ssh_arg_helpers::build_ssh_prefix(
        ip,
        user,
        config.ssh_connect_timeout,
    ));
    if let Some(k) = key {
        crate::ssh_arg_helpers::inject_identity_key_before_destination(&mut prefix, k);
    }
    prefix
}

fn build_gui_ssh_command_prefix(
    target: &VmSshTarget,
    connect_timeout: u64,
    key_override: Option<&std::path::Path>,
) -> Result<(
    Vec<String>,
    Option<crate::bastion_tunnel::ScopedBastionTunnel>,
)> {
    let (routed_prefix, tunnel) =
        crate::dispatch_helpers::build_routed_ssh_prefix(target, connect_timeout, key_override)?;
    let mut ssh_cmd_prefix = Vec::with_capacity(routed_prefix.len() + 1);
    ssh_cmd_prefix.push("ssh".to_string());
    ssh_cmd_prefix.extend(routed_prefix);
    Ok((ssh_cmd_prefix, tunnel))
}

// ---------------------------------------------------------------------------
// Remote dependency checks
// ---------------------------------------------------------------------------

fn build_dependency_setup_script(mode: &VncMode) -> String {
    let (check_cmd, install_packages) = match mode {
        VncMode::Desktop => (
            "command -v vncserver >/dev/null 2>&1 && command -v startxfce4 >/dev/null 2>&1",
            "tigervnc-standalone-server xfce4 xfce4-goodies dbus-x11",
        ),
        VncMode::Minimal => (
            "command -v vncserver >/dev/null 2>&1 && command -v openbox >/dev/null 2>&1",
            "tigervnc-standalone-server openbox",
        ),
        VncMode::App(_) => (
            "command -v vncserver >/dev/null 2>&1",
            "tigervnc-standalone-server",
        ),
    };

    let script = format!(
        "if {check_cmd}; then exit 0; fi; \
         sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq || exit $?; \
         sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {install_packages} || exit $?; \
         if ! ({check_cmd}); then \
           echo 'Remote GUI dependencies are still missing after installation.' >&2; \
           exit 1; \
         fi"
    );
    format!("bash -lc {}", crate::shell_escape(&script))
}

fn run_dependency_setup_with_runner<F>(
    mode: &VncMode,
    timeout_secs: u64,
    mut runner: F,
) -> Result<()>
where
    F: FnMut(&str, u64) -> Result<(i32, String, String)>,
{
    let script = build_dependency_setup_script(mode);
    match runner(&script, timeout_secs) {
        Ok((0, _, _)) => Ok(()),
        Ok((code, stdout, stderr)) => {
            let detail = stderr.trim();
            let detail = if detail.is_empty() {
                stdout.trim()
            } else {
                detail
            };
            let detail = if detail.is_empty() {
                format!("exit code {}", code)
            } else {
                azlin_core::sanitizer::sanitize(detail)
            };
            anyhow::bail!(
                "GUI dependency/setup phase failed (exit {}): {}",
                code,
                detail
            );
        }
        Err(err) => {
            let msg = err.to_string();
            if msg.contains("timed out") {
                anyhow::bail!(
                    "GUI dependency/setup phase timed out after {} minutes: {}",
                    timeout_secs / 60,
                    azlin_core::sanitizer::sanitize(&msg)
                );
            }
            anyhow::bail!(
                "GUI dependency/setup phase failed: {}",
                azlin_core::sanitizer::sanitize(&msg)
            );
        }
    }
}

fn check_remote_deps(
    target: &VmSshTarget,
    key_override: Option<&std::path::Path>,
    mode: &VncMode,
) -> Result<()> {
    run_dependency_setup_with_runner(mode, GUI_SETUP_TIMEOUT_SECS, |script, timeout_secs| {
        crate::dispatch_helpers::run_target_command_with_timeout(
            target,
            script,
            timeout_secs,
            key_override,
        )
    })
}

// ---------------------------------------------------------------------------
// VNC server management
// ---------------------------------------------------------------------------

fn start_vnc_server(
    ssh_cmd_prefix: &[String],
    resolution: &str,
    depth: u8,
    mode: &VncMode,
) -> Result<String> {
    // Generate random password using openssl on remote (avoids adding rand dep)
    let password = run_ssh_command(ssh_cmd_prefix, "openssl rand -hex 4")?
        .trim()
        .to_string();

    if password.is_empty() {
        anyhow::bail!("Failed to generate VNC password on remote host");
    }

    // Set up VNC password file (shell-escape password to prevent injection)
    let escaped_password = shell_escape::unix::escape(password.as_str().into());
    let passwd_cmd = format!(
        "mkdir -p ~/.vnc && echo {} | vncpasswd -f > ~/.vnc/passwd && chmod 600 ~/.vnc/passwd",
        escaped_password
    );
    let (code, _, stderr) = run_ssh_command_full(ssh_cmd_prefix, &passwd_cmd)?;
    if code != 0 {
        anyhow::bail!("Failed to set VNC password: {}", stderr);
    }

    let xstartup_body = build_vnc_xstartup_body(mode);

    let xstartup_cmd = format!(
        "cat > ~/.vnc/xstartup << 'XSTARTUP'\n#!/bin/sh\n{}\nXSTARTUP\nchmod +x ~/.vnc/xstartup",
        xstartup_body
    );
    let (code, _, stderr) = run_ssh_command_full(ssh_cmd_prefix, &xstartup_cmd)?;
    if code != 0 {
        anyhow::bail!("Failed to create VNC xstartup: {}", stderr);
    }

    // Kill any existing VNC server on display :1
    let _ = run_ssh_command(
        ssh_cmd_prefix,
        &format!("vncserver -kill :{} 2>/dev/null || true", VNC_DISPLAY),
    );

    // Start VNC server
    let start_cmd = format!(
        "vncserver :{} -localhost yes -geometry {} -depth {}",
        VNC_DISPLAY, resolution, depth
    );
    let (code, _, stderr) = run_ssh_command_full(ssh_cmd_prefix, &start_cmd)?;
    if code != 0 {
        anyhow::bail!("Failed to start VNC server: {}", stderr);
    }

    Ok(password)
}

// ---------------------------------------------------------------------------
// VNC tunnel (SSH -L port forwarding)
// ---------------------------------------------------------------------------

fn build_vnc_tunnel_args(ssh_cmd_prefix: &[String], local_port: u16) -> Result<Vec<String>> {
    // Build ssh -N -L 5901:localhost:5901 using the same SSH prefix
    // (which already includes -p <port> for bastion, or user@ip for direct)
    let mut args: Vec<String> = Vec::new();

    // Extract the ssh binary and connection args from prefix
    // prefix[0] = "ssh", prefix[1..] = options + user@host
    if ssh_cmd_prefix.len() < 2 {
        anyhow::bail!("SSH command prefix must include a destination");
    }

    // Copy all args except the first ("ssh"), add -N -L before the user@host
    for arg in &ssh_cmd_prefix[1..ssh_cmd_prefix.len() - 1] {
        args.push(arg.clone());
    }
    args.push("-N".to_string());
    args.push("-L".to_string());
    args.push(format!("{}:localhost:{}", local_port, VNC_PORT));
    // user@host is the last element
    args.push(ssh_cmd_prefix.last().unwrap().clone());

    Ok(args)
}

fn open_vnc_tunnel(ssh_cmd_prefix: &[String]) -> Result<(u16, Vec<u32>)> {
    let local_port = crate::pick_unused_local_port()?;
    let args = build_vnc_tunnel_args(ssh_cmd_prefix, local_port)?;

    let mut child = std::process::Command::new("ssh")
        .args(&args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("Failed to spawn SSH port-forward for VNC")?;

    let pid = child.id();
    if let Err(error) = crate::bastion_tunnel::wait_for_process_tree_listener(
        local_port,
        pid,
        std::time::Duration::from_secs(10),
        "VNC tunnel",
    ) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error).context(format!(
            "VNC tunnel failed to listen on 127.0.0.1:{}",
            local_port
        ));
    }
    std::mem::forget(child);

    Ok((local_port, vec![pid]))
}

// ---------------------------------------------------------------------------
// VNC viewer launch
// ---------------------------------------------------------------------------

fn build_vnc_viewer_args(passwd_file: &std::path::Path, local_port: u16) -> Vec<String> {
    vec![
        "-SecurityTypes".to_string(),
        "VncAuth".to_string(),
        "-passwd".to_string(),
        passwd_file.display().to_string(),
        format!("127.0.0.1:{}", local_port),
    ]
}

fn launch_viewer(ssh_cmd_prefix: &[String], password: &str, local_port: u16) -> Result<()> {
    // Retrieve the VNC passwd file from the remote VM
    let passwd_b64 = run_ssh_command(ssh_cmd_prefix, "base64 < ~/.vnc/passwd")?;
    let passwd_bytes = base64_decode(passwd_b64.trim())?;

    // Write to a temp file with restricted permissions from creation (no TOCTOU window)
    let tmp_dir = std::env::temp_dir();
    let passwd_file = tmp_dir.join(format!("azlin_vnc_passwd_{}", std::process::id()));
    {
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            std::fs::OpenOptions::new()
                .write(true)
                .create(true)
                .truncate(true)
                .mode(0o600)
                .open(&passwd_file)
                .and_then(|mut f| {
                    use std::io::Write;
                    f.write_all(&passwd_bytes)
                })
                .context("Failed to write temporary VNC passwd file")?;
        }
        #[cfg(not(unix))]
        {
            std::fs::write(&passwd_file, &passwd_bytes)
                .context("Failed to write temporary VNC passwd file")?;
        }
    }

    // Ensure DISPLAY is set for the viewer
    let display = std::env::var("DISPLAY").unwrap_or_default();
    let effective_display = if display.is_empty() {
        // Check if X socket exists (WSLg)
        if std::path::Path::new("/tmp/.X11-unix/X0").exists() {
            ":0".to_string()
        } else {
            display
        }
    } else {
        display
    };

    let mut cmd = std::process::Command::new("vncviewer");
    cmd.args(build_vnc_viewer_args(&passwd_file, local_port));

    if !effective_display.is_empty() {
        cmd.env("DISPLAY", &effective_display);
    }

    let launch_result = cmd.status().context("Failed to launch vncviewer");

    // Clean up temp passwd file unconditionally (before propagating any error)
    if let Err(e) = std::fs::remove_file(&passwd_file) {
        eprintln!(
            "warning: failed to remove temp VNC passwd file {}: {e}",
            passwd_file.display()
        );
    }

    let status = launch_result?;

    if !status.success() {
        let _ = password; // suppress unused warning
        anyhow::bail!(
            "vncviewer exited with status {}",
            status.code().unwrap_or(-1)
        );
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

fn cleanup(pids: &[u32], ssh_cmd_prefix: &[String]) {
    // Kill remote VNC server
    let _ = run_ssh_command(
        ssh_cmd_prefix,
        &format!("vncserver -kill :{} 2>/dev/null || true", VNC_DISPLAY),
    );

    // Kill local tunnel processes
    for pid in pids {
        let _ = std::process::Command::new("kill")
            .arg(pid.to_string())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
}

// ---------------------------------------------------------------------------
// SSH helpers
// ---------------------------------------------------------------------------

/// Run a command on the remote VM via SSH, returning stdout.
fn run_ssh_command(ssh_cmd_prefix: &[String], remote_cmd: &str) -> Result<String> {
    let (code, stdout, stderr) = run_ssh_command_full(ssh_cmd_prefix, remote_cmd)?;
    if code != 0 {
        anyhow::bail!("SSH command failed (exit {}): {}", code, stderr);
    }
    Ok(stdout)
}

/// Run a command on the remote VM via SSH, returning (exit_code, stdout, stderr).
fn run_ssh_command_full(
    ssh_cmd_prefix: &[String],
    remote_cmd: &str,
) -> Result<(i32, String, String)> {
    if ssh_cmd_prefix.is_empty() {
        anyhow::bail!("Empty SSH command prefix");
    }

    let output = std::process::Command::new(&ssh_cmd_prefix[0])
        .args(&ssh_cmd_prefix[1..])
        .arg(remote_cmd)
        .output()
        .context("Failed to execute SSH command")?;

    Ok((
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    ))
}

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

/// Validate resolution string format (WIDTHxHEIGHT).
fn is_valid_resolution(res: &str) -> bool {
    let parts: Vec<&str> = res.split('x').collect();
    if parts.len() != 2 {
        return false;
    }
    parts[0].parse::<u32>().is_ok() && parts[1].parse::<u32>().is_ok()
}

/// Simple base64 decoder (avoids adding a dependency).
/// Handles standard base64 alphabet with optional padding.
fn base64_decode(input: &str) -> Result<Vec<u8>> {
    // Use openssl or a subprocess to decode if available, otherwise manual decode
    let output = std::process::Command::new("base64")
        .arg("-d")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            use std::io::Write;
            if let Some(ref mut stdin) = child.stdin {
                stdin.write_all(input.as_bytes())?;
            }
            child.wait_with_output()
        })
        .context("Failed to decode base64 VNC password")?;

    if !output.status.success() {
        anyhow::bail!("base64 decode failed");
    }

    Ok(output.stdout)
}

/// Build SSH arguments for X11 forwarding (used by connect --x11).
#[allow(dead_code)]
pub fn build_x11_ssh_args() -> Vec<String> {
    vec!["-Y".to_string()]
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_resolution() {
        assert!(is_valid_resolution("1920x1080"));
        assert!(is_valid_resolution("1280x720"));
        assert!(is_valid_resolution("3840x2160"));
    }

    #[test]
    fn test_invalid_resolution() {
        assert!(!is_valid_resolution("1920"));
        assert!(!is_valid_resolution("1920x"));
        assert!(!is_valid_resolution("x1080"));
        assert!(!is_valid_resolution("abc"));
        assert!(!is_valid_resolution("1920x1080x32"));
        assert!(!is_valid_resolution(""));
    }

    #[test]
    fn test_direct_ssh_prefix_no_key() {
        let prefix = build_direct_ssh_prefix("10.0.0.1", "testuser", None);
        assert_eq!(prefix[0], "ssh");
        assert!(prefix.contains(&"-o".to_string()));
        assert!(prefix.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert_eq!(prefix.last().unwrap(), "testuser@10.0.0.1");
    }

    #[test]
    fn test_direct_ssh_prefix_with_key() {
        let key_path = std::path::Path::new("/home/user/.ssh/id_rsa");
        let prefix = build_direct_ssh_prefix("10.0.0.1", "testuser", Some(key_path));
        assert!(prefix.contains(&"IdentitiesOnly=yes".to_string()));
        assert!(prefix.contains(&"-i".to_string()));
        assert!(prefix.contains(&"/home/user/.ssh/id_rsa".to_string()));
        assert_eq!(prefix.last().unwrap(), "testuser@10.0.0.1");
    }

    #[test]
    fn test_gui_routed_ssh_command_prefix_starts_with_ssh_binary() {
        let target = VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "1.2.3.4".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: false,
            bastion: None,
        };

        let (prefix, tunnel) = build_gui_ssh_command_prefix(&target, 30, None).unwrap();
        assert!(tunnel.is_none());
        assert_eq!(prefix.first().map(String::as_str), Some("ssh"));
        assert!(prefix.contains(&"BatchMode=yes".to_string()));
        assert_eq!(prefix.last().map(String::as_str), Some("azureuser@1.2.3.4"));
    }

    #[test]
    fn test_x11_check_with_display_set() {
        // When DISPLAY is set, x11 check should not fail
        // (This tests the logic path, not actual X server availability)
        let display_set = !std::env::var("DISPLAY")
            .map(|d| d.is_empty())
            .unwrap_or(true);
        let x_socket = std::path::Path::new("/tmp/.X11-unix/X0").exists();
        // At least one should be true in a typical dev environment, or both false in CI
        // Either way, this shouldn't panic
        let _has_x = display_set || x_socket;
    }

    #[test]
    fn test_build_x11_ssh_args() {
        let args = build_x11_ssh_args();
        assert_eq!(args, vec!["-Y".to_string()]);
    }

    #[test]
    fn test_resolve_gui_target_user_honors_non_default_override() {
        assert_eq!(
            resolve_gui_target_user("customuser", "azureuser"),
            "customuser"
        );
        assert_eq!(
            resolve_gui_target_user(DEFAULT_ADMIN_USERNAME, "vmadmin"),
            "vmadmin"
        );
    }

    #[test]
    fn test_build_dependency_setup_script_is_noninteractive() {
        let script = build_dependency_setup_script(&VncMode::Desktop);
        assert!(script.contains("DEBIAN_FRONTEND=noninteractive"));
        assert!(!script.contains("read "));
        assert!(!script.contains("[Y/n]"));
        assert!(script.contains("startxfce4"));
        assert!(!script.contains('\n'));
        assert!(script.contains("if ! (command -v vncserver"));
        assert!(!script.contains("set -e"));
    }

    #[test]
    fn test_build_dependency_setup_script_propagates_apt_failures() {
        let script = build_dependency_setup_script(&VncMode::Desktop);
        assert!(script.contains("apt-get update -qq || exit $?"));
        assert!(script.contains(
            "apt-get install -y tigervnc-standalone-server xfce4 xfce4-goodies dbus-x11 || exit $?"
        ));
    }

    #[test]
    fn test_build_vnc_xstartup_body_wraps_direct_chromium_app() {
        let body =
            build_vnc_xstartup_body(&VncMode::App("chromium-browser --no-sandbox".to_string()));

        assert!(body.contains("export XDG_RUNTIME_DIR=\"/run/user/$(id -u)\""));
        assert!(body.contains(
            "systemd-run --user --scope --quiet -- sh -lc 'chromium-browser --no-sandbox'"
        ));
        assert!(
            body.contains("azlin: snap Chromium detected but systemd-run --user is unavailable")
        );
        assert!(body.contains("sh -lc 'chromium-browser --no-sandbox'; fi"));
        assert!(body.contains("vncserver -kill :1 2>/dev/null"));
    }

    #[test]
    fn test_build_vnc_xstartup_body_wraps_env_prefixed_chromium_app() {
        let body = build_vnc_xstartup_body(&VncMode::App(
            "FOO=1 chromium-browser --no-sandbox".to_string(),
        ));

        assert!(body.contains(
            "systemd-run --user --scope --quiet -- sh -lc 'FOO=1 chromium-browser --no-sandbox'"
        ));
        assert!(body.contains("sh -lc 'FOO=1 chromium-browser --no-sandbox'; fi"));
    }

    #[test]
    fn test_build_vnc_xstartup_body_leaves_other_apps_unwrapped() {
        let body = build_vnc_xstartup_body(&VncMode::App("gimp".to_string()));

        assert!(!body.contains("systemd-run --user --scope --quiet --"));
        assert!(body.contains("\ngimp\nvncserver -kill :1 2>/dev/null"));
    }

    #[test]
    fn test_build_vnc_tunnel_args_use_requested_local_port() {
        let args = build_vnc_tunnel_args(
            &[
                "ssh".to_string(),
                "-i".to_string(),
                "/tmp/test-key".to_string(),
                "azureuser@10.0.0.5".to_string(),
            ],
            41234,
        )
        .unwrap();

        assert!(args.contains(&"-N".to_string()));
        assert!(args.contains(&"-L".to_string()));
        assert!(args.contains(&"41234:localhost:5901".to_string()));
        assert_eq!(args.last().map(String::as_str), Some("azureuser@10.0.0.5"));
    }

    #[test]
    fn test_build_vnc_tunnel_args_require_destination() {
        let err = build_vnc_tunnel_args(&["ssh".to_string()], 41234).unwrap_err();
        assert!(err.to_string().contains("must include a destination"));
    }

    #[test]
    fn test_build_vnc_viewer_args_use_requested_local_port() {
        let args = build_vnc_viewer_args(std::path::Path::new("/tmp/passwd"), 41234);
        assert_eq!(
            args,
            vec![
                "-SecurityTypes".to_string(),
                "VncAuth".to_string(),
                "-passwd".to_string(),
                "/tmp/passwd".to_string(),
                "127.0.0.1:41234".to_string(),
            ]
        );
    }

    #[test]
    fn test_dependency_setup_runner_uses_outer_timeout() {
        let mut captured_timeout = None;
        let mut captured_script = None;

        run_dependency_setup_with_runner(
            &VncMode::Minimal,
            GUI_SETUP_TIMEOUT_SECS,
            |script, timeout_secs| {
                captured_timeout = Some(timeout_secs);
                captured_script = Some(script.to_string());
                Ok((0, "GUI_DEPS_OK".to_string(), String::new()))
            },
        )
        .unwrap();

        assert_eq!(captured_timeout, Some(GUI_SETUP_TIMEOUT_SECS));
        assert!(
            captured_script
                .as_deref()
                .is_some_and(|script: &str| script.contains("openbox")),
            "expected minimal mode dependency script"
        );
    }

    #[test]
    fn test_dependency_setup_timeout_is_explicit_failure() {
        let err = run_dependency_setup_with_runner(
            &VncMode::Desktop,
            GUI_SETUP_TIMEOUT_SECS,
            |_script, _timeout_secs| Err(anyhow::anyhow!("ssh timed out after 600s")),
        )
        .unwrap_err();

        let msg = err.to_string();
        assert!(msg.contains("dependency/setup phase"));
        assert!(msg.contains("timed out"));
    }

    #[test]
    fn test_dependency_setup_nonzero_exit_is_explicit_failure() {
        let err = run_dependency_setup_with_runner(
            &VncMode::App("xterm".to_string()),
            GUI_SETUP_TIMEOUT_SECS,
            |_script, _timeout_secs| Ok((100, String::new(), "apt failed".to_string())),
        )
        .unwrap_err();

        let msg = err.to_string();
        assert!(msg.contains("dependency/setup phase"));
        assert!(msg.contains("apt failed"));
    }
}
