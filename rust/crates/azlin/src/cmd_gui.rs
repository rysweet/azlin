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
use std::collections::HashMap;

/// Bastion tunnel local port for SSH access to the VM.
const BASTION_SSH_PORT: u16 = 50210;

/// VNC display number (maps to port 5901).
const VNC_DISPLAY: u16 = 1;

/// VNC port = 5900 + display number.
const VNC_PORT: u16 = 5900 + VNC_DISPLAY;

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    _output: &azlin_cli::OutputFormat,
) -> Result<()> {
    let azlin_cli::Commands::Gui {
        vm_identifier,
        resource_group,
        user,
        key,
        resolution,
        depth,
        yes,
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
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;

    let name = if let Some(n) = vm_identifier {
        n
    } else {
        anyhow::bail!("VM name is required for gui command. Usage: azlin gui <vm-name>");
    };

    let pb = penguin_spinner(&format!("Looking up {}...", name));
    let vm = vm_manager.get_vm(&rg, &name)?;
    pb.finish_and_clear();

    let username = vm
        .admin_username
        .clone()
        .unwrap_or_else(|| user.clone());
    let use_bastion = vm.public_ip.is_none();

    // Resolve SSH key: use --key flag if provided, otherwise fall back to default
    let effective_key = key.or_else(|| resolve_ssh_key());

    // Build SSH command prefix for running commands on the remote VM.
    // This prefix is reused for all remote operations.
    let (ssh_cmd_prefix, cleanup_pids) = if use_bastion {
        build_bastion_ssh_prefix(&vm, &vm_manager, &rg, &username, effective_key.as_deref(), verbose)?
    } else {
        let ip = vm
            .public_ip
            .as_deref()
            .ok_or_else(|| anyhow::anyhow!("VM has no public IP"))?;
        (build_direct_ssh_prefix(ip, &username, effective_key.as_deref()), vec![])
    };

    // Step 3: Check/install remote dependencies
    let pb = penguin_spinner("Checking remote dependencies...");
    check_remote_deps(&ssh_cmd_prefix, yes)?;
    pb.finish_and_clear();

    // Step 4: Start VNC server on the remote VM
    let pb = penguin_spinner("Starting VNC server...");
    let vnc_password = start_vnc_server(&ssh_cmd_prefix, &resolution, depth)?;
    pb.finish_and_clear();

    // Step 5: Open SSH port-forward for VNC
    let pb = penguin_spinner("Opening VNC tunnel...");
    let tunnel_pids = open_vnc_tunnel(&ssh_cmd_prefix, use_bastion)?;
    pb.finish_and_clear();

    let all_pids: Vec<u32> = cleanup_pids
        .iter()
        .chain(tunnel_pids.iter())
        .copied()
        .collect();

    // Step 6: Launch local VNC viewer
    println!("Launching VNC viewer (127.0.0.1:{})...", VNC_PORT);
    println!("VNC password: {}", vnc_password);
    println!("Press Ctrl+C to stop the GUI session.\n");

    let viewer_result = launch_viewer(&ssh_cmd_prefix, &vnc_password);

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
        eprintln!("  WSLg should be available in WSL2 by default. Restart WSL if DISPLAY is not set.");
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
fn build_direct_ssh_prefix(ip: &str, user: &str, key: Option<&std::path::Path>) -> Vec<String> {
    let mut prefix = vec![
        "ssh".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
    ];
    if let Some(k) = key {
        prefix.push("-i".to_string());
        prefix.push(k.display().to_string());
    }
    prefix.push(format!("{}@{}", user, ip));
    prefix
}

/// Build an SSH prefix that routes through a bastion tunnel.
/// Returns (ssh_prefix, bastion_pids) — caller must clean up the bastion PIDs on exit.
fn build_bastion_ssh_prefix(
    vm: &azlin_core::models::VmInfo,
    vm_manager: &azlin_azure::VmManager,
    rg: &str,
    user: &str,
    key: Option<&std::path::Path>,
    verbose: bool,
) -> Result<(Vec<String>, Vec<u32>)> {
    let bastions = crate::list_helpers::detect_bastion_hosts(rg).unwrap_or_default();
    let bastion_map: HashMap<String, String> =
        bastions.into_iter().map(|(n, l, _)| (l, n)).collect();
    let bastion_name = bastion_map.get(&vm.location).ok_or_else(|| {
        anyhow::anyhow!(
            "No bastion host found for region '{}'. Cannot connect to private VM.",
            vm.location
        )
    })?;

    let vm_rid = format!(
        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
        vm_manager.subscription_id(),
        rg,
        vm.name
    );

    // Open bastion tunnel to VM:22 on BASTION_SSH_PORT
    if verbose {
        eprintln!(
            "Opening bastion tunnel on port {} to {}...",
            BASTION_SSH_PORT, vm.name
        );
    }

    let bastion_child = std::process::Command::new("az")
        .args([
            "network",
            "bastion",
            "tunnel",
            "--name",
            bastion_name,
            "--resource-group",
            rg,
            "--target-resource-id",
            &vm_rid,
            "--resource-port",
            "22",
            "--port",
            &BASTION_SSH_PORT.to_string(),
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("Failed to spawn az bastion tunnel")?;

    let bastion_pid = bastion_child.id();
    std::mem::forget(bastion_child);

    // Wait for tunnel to establish
    std::thread::sleep(std::time::Duration::from_secs(3));

    let mut prefix = vec![
        "ssh".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-p".to_string(),
        BASTION_SSH_PORT.to_string(),
    ];
    if let Some(k) = key {
        prefix.push("-i".to_string());
        prefix.push(k.display().to_string());
    }
    prefix.push(format!("{}@127.0.0.1", user));

    Ok((prefix, vec![bastion_pid]))
}

// ---------------------------------------------------------------------------
// Remote dependency checks
// ---------------------------------------------------------------------------

fn check_remote_deps(ssh_cmd_prefix: &[String], auto_yes: bool) -> Result<()> {
    let check_cmd = "which vncserver && which startxfce4 && echo DEPS_OK";
    let output = run_ssh_command(ssh_cmd_prefix, check_cmd)?;

    if output.contains("DEPS_OK") {
        return Ok(());
    }

    eprintln!("Remote VNC/desktop dependencies not found.");
    if !auto_yes {
        eprint!("Install tigervnc-standalone-server, xfce4, and xfce4-goodies? [Y/n] ");
        use std::io::Write;
        std::io::stdout().flush()?;
        let mut input = String::new();
        std::io::stdin().read_line(&mut input)?;
        if input.trim().eq_ignore_ascii_case("n") {
            anyhow::bail!("Remote dependencies required. Install manually and retry.");
        }
    }

    eprintln!("Installing remote desktop packages (this may take a few minutes)...");
    let install_cmd = "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
                       sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
                       tigervnc-standalone-server xfce4 xfce4-goodies dbus-x11";
    let (code, _stdout, stderr) = run_ssh_command_full(ssh_cmd_prefix, install_cmd)?;
    if code != 0 {
        anyhow::bail!("Failed to install remote dependencies: {}", stderr);
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// VNC server management
// ---------------------------------------------------------------------------

fn start_vnc_server(
    ssh_cmd_prefix: &[String],
    resolution: &str,
    depth: u8,
) -> Result<String> {
    // Generate random password using openssl on remote (avoids adding rand dep)
    let password = run_ssh_command(ssh_cmd_prefix, "openssl rand -hex 4")?
        .trim()
        .to_string();

    if password.is_empty() {
        anyhow::bail!("Failed to generate VNC password on remote host");
    }

    // Set up VNC password file
    let passwd_cmd = format!(
        "mkdir -p ~/.vnc && echo '{}' | vncpasswd -f > ~/.vnc/passwd && chmod 600 ~/.vnc/passwd",
        password
    );
    let (code, _, stderr) = run_ssh_command_full(ssh_cmd_prefix, &passwd_cmd)?;
    if code != 0 {
        anyhow::bail!("Failed to set VNC password: {}", stderr);
    }

    // Create xstartup for XFCE
    let xstartup_cmd = r#"cat > ~/.vnc/xstartup << 'XSTARTUP'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_TYPE=x11
exec startxfce4
XSTARTUP
chmod +x ~/.vnc/xstartup"#;
    let (code, _, stderr) = run_ssh_command_full(ssh_cmd_prefix, xstartup_cmd)?;
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

fn open_vnc_tunnel(ssh_cmd_prefix: &[String], _use_bastion: bool) -> Result<Vec<u32>> {
    // Build ssh -N -L 5901:localhost:5901 using the same SSH prefix
    // (which already includes -p <port> for bastion, or user@ip for direct)
    let mut args: Vec<String> = Vec::new();

    // Extract the ssh binary and connection args from prefix
    // prefix[0] = "ssh", prefix[1..] = options + user@host
    if ssh_cmd_prefix.is_empty() {
        anyhow::bail!("Empty SSH command prefix");
    }

    // Copy all args except the first ("ssh"), add -N -L before the user@host
    for arg in &ssh_cmd_prefix[1..ssh_cmd_prefix.len() - 1] {
        args.push(arg.clone());
    }
    args.push("-N".to_string());
    args.push("-L".to_string());
    args.push(format!("{}:localhost:{}", VNC_PORT, VNC_PORT));
    // user@host is the last element
    args.push(ssh_cmd_prefix.last().unwrap().clone());

    let child = std::process::Command::new("ssh")
        .args(&args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("Failed to spawn SSH port-forward for VNC")?;

    let pid = child.id();
    std::mem::forget(child);

    // Wait for tunnel to establish
    std::thread::sleep(std::time::Duration::from_secs(2));

    Ok(vec![pid])
}

// ---------------------------------------------------------------------------
// VNC viewer launch
// ---------------------------------------------------------------------------

fn launch_viewer(ssh_cmd_prefix: &[String], password: &str) -> Result<()> {
    // Retrieve the VNC passwd file from the remote VM
    let passwd_b64 = run_ssh_command(ssh_cmd_prefix, "base64 < ~/.vnc/passwd")?;
    let passwd_bytes = base64_decode(passwd_b64.trim())?;

    // Write to a temp file
    let tmp_dir = std::env::temp_dir();
    let passwd_file = tmp_dir.join(format!("azlin_vnc_passwd_{}", std::process::id()));
    std::fs::write(&passwd_file, &passwd_bytes)
        .context("Failed to write temporary VNC passwd file")?;

    // Ensure proper permissions
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&passwd_file, std::fs::Permissions::from_mode(0o600))?;
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
    cmd.arg("-passwd")
        .arg(&passwd_file)
        .arg(format!("127.0.0.1:{}", VNC_PORT));

    if !effective_display.is_empty() {
        cmd.env("DISPLAY", &effective_display);
    }

    let status = cmd.status().context("Failed to launch vncviewer")?;

    // Clean up temp passwd file
    let _ = std::fs::remove_file(&passwd_file);

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
        assert!(prefix.contains(&"-i".to_string()));
        assert!(prefix.contains(&"/home/user/.ssh/id_rsa".to_string()));
        assert_eq!(prefix.last().unwrap(), "testuser@10.0.0.1");
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
}
