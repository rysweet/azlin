//! `azlin gui` — Open a remote GUI desktop over an SSH tunnel.
//!
//! Two desktop backends are supported:
//!
//! * **Native** (default, unchanged): the VNC server and desktop are installed
//!   on the VM with its package manager. Works wherever the VM's repositories
//!   carry `tigervnc`/`xfce4`.
//! * **Containerised**: the whole stack runs as a pinned container on the VM's
//!   Docker, put there by `azlin gui install` (see [`crate::cmd_gui_install`]).
//!   This is the only option on distributions whose repositories have no desktop
//!   stack, and it additionally supports RDP.
//!
//! `azlin gui` probes for a containerised desktop first and uses it when one is
//! installed; otherwise it takes the native path exactly as before. It never
//! installs a container implicitly — if the native path cannot provide a
//! desktop, it prints the exact `azlin gui install` command to run.
//!
//! Workflow:
//! 1. Resolve VM and detect bastion route
//! 2. Probe the VM for a containerised desktop
//! 3. Container found: start it if stopped, tunnel to its loopback port, launch
//!    the local VNC viewer or RDP client
//! 4. No container: check/install native deps, start the VNC server, tunnel,
//!    launch the local viewer
//! 5. Wait for the client to exit, then clean shutdown

#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use azlin_core::gui_container::{
    build_detect_script, build_start_script, no_desktop_remedy, parse_detect_output, ContainerState,
    GuiProtocol, GuiStatus, HOST_RDP_PASSWD_PATH, HOST_VNC_PASSWD_PATH, RDP_USERNAME,
};

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

/// Hard timeout for the containerised-desktop detection probe.
const GUI_DETECT_TIMEOUT_SECS: u64 = 60;

pub(crate) fn resolve_gui_target_user(requested_user: &str, detected_user: &str) -> String {
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
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    let azlin_cli::Commands::Gui {
        action,
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

    if let Some(action) = action {
        return crate::cmd_gui_install::dispatch(action, verbose, output).await;
    }

    // Validate resolution format
    if !is_valid_resolution(&resolution) {
        anyhow::bail!(
            "Invalid resolution '{}'. Expected format: WIDTHxHEIGHT (e.g. 1920x1080)",
            resolution
        );
    }

    // Step 1: Resolve VM
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
    let config = crate::dispatch_helpers::load_user_config();
    let effective_key = key.or_else(resolve_ssh_key);
    let (ssh_cmd_prefix, _route_tunnel) = build_gui_ssh_command_prefix(
        &target,
        config.ssh_connect_timeout,
        effective_key.as_deref(),
    )
    .await?;

    // Step 2: Prefer a containerised desktop if `azlin gui install` put one
    // there. A probe failure is not fatal: the native path below reports
    // transport problems with a better message.
    let pb = penguin_spinner("Checking for a remote desktop...");
    let status = detect_desktop(&target, effective_key.as_deref()).await;
    pb.finish_and_clear();
    let status = match status {
        Ok(status) => status,
        Err(err) => {
            if verbose {
                eprintln!("note: could not probe for a containerised desktop: {err}");
            }
            GuiStatus {
                docker_present: false,
                docker_usable: false,
                container_state: ContainerState::Missing,
                protocol: None,
                host_port: None,
            }
        }
    };

    if status.is_installed() {
        return connect_containerised(&ssh_cmd_prefix, &status, minimal, app.is_some()).await;
    }

    // Step 3: No container — take the native package-based path unchanged.
    check_local_deps()?;

    // Determine VNC mode
    let vnc_mode = if let Some(cmd) = app {
        VncMode::App(cmd)
    } else if minimal {
        VncMode::Minimal
    } else {
        VncMode::Desktop
    };

    // Step 4: Check/install remote dependencies
    let pb = penguin_spinner("Checking remote dependencies...");
    let deps = check_remote_deps(&target, effective_key.as_deref(), &vnc_mode).await;
    pb.finish_and_clear();
    // A distribution whose repositories carry no desktop stack fails here and
    // can never succeed on the native path, so name the containerised
    // alternative explicitly rather than leaving the user stuck.
    deps.with_context(|| no_desktop_remedy(&name, &status))?;

    // Step 5: Start VNC server on the remote VM
    let pb = penguin_spinner("Starting VNC server...");
    let _vnc_password = start_vnc_server(&ssh_cmd_prefix, &resolution, depth, &vnc_mode)?;
    pb.finish_and_clear();

    // Step 6: Open SSH port-forward for VNC
    let pb = penguin_spinner("Opening VNC tunnel...");
    let (local_vnc_port, tunnel_pids) = open_desktop_tunnel(&ssh_cmd_prefix, VNC_PORT, "VNC")?;
    pb.finish_and_clear();

    let all_pids: Vec<u32> = tunnel_pids.to_vec();

    // Step 7: Launch local VNC viewer
    println!("Launching VNC viewer (127.0.0.1:{})...", local_vnc_port);
    eprintln!("(VNC password set on remote — not displayed for security)");
    println!("Press Ctrl+C to stop the GUI session.\n");

    let viewer_result = launch_viewer(&ssh_cmd_prefix, "~/.vnc/passwd", local_vnc_port);

    // Step 8: Cleanup on exit
    cleanup(&all_pids, &ssh_cmd_prefix);

    viewer_result
}

// ---------------------------------------------------------------------------
// Containerised desktop
// ---------------------------------------------------------------------------

/// Connect to a containerised desktop that the probe already found.
async fn connect_containerised(
    ssh_cmd_prefix: &[String],
    status: &GuiStatus,
    minimal: bool,
    app: bool,
) -> Result<()> {
    // Session-shape flags only ever applied to a VNC server installed directly
    // on the host. The containerised desktop owns its own session, so honouring
    // them is impossible; say so rather than silently ignoring them.
    if minimal || app {
        eprintln!(
            "warning: --minimal and --app do not apply to the containerised desktop and are ignored."
        );
        eprintln!("         Run the application from inside the desktop session instead.");
    }

    if status.container_state == ContainerState::Stopped {
        let pb = penguin_spinner("Starting the remote desktop container...");
        let started = start_desktop(ssh_cmd_prefix);
        pb.finish_and_clear();
        started?;
    }

    let protocol = status.protocol.unwrap_or(GuiProtocol::Vnc);
    let remote_port = status.effective_port();

    // Local client prerequisites are checked only once we know which protocol
    // the desktop speaks: demanding a VNC viewer for an RDP desktop would be
    // wrong.
    if protocol == GuiProtocol::Vnc {
        check_local_deps()?;
    }

    let pb = penguin_spinner("Opening the desktop tunnel...");
    let opened = open_desktop_tunnel(ssh_cmd_prefix, remote_port, "desktop");
    pb.finish_and_clear();
    let (local_port, tunnel_pids) = opened?;

    let result = match protocol {
        GuiProtocol::Vnc => {
            println!("Launching VNC viewer (127.0.0.1:{})...", local_port);
            eprintln!("(desktop password set on the VM — not displayed for security)");
            println!("Press Ctrl+C to stop the GUI session.\n");
            launch_viewer(ssh_cmd_prefix, HOST_VNC_PASSWD_PATH, local_port)
        }
        GuiProtocol::Rdp => launch_rdp_client(ssh_cmd_prefix, local_port),
    };

    // The container is left running so reconnecting is fast; remove it with
    // `azlin gui install <vm> --uninstall`.
    kill_tunnels(&tunnel_pids);

    result
}

/// Probe the VM for a containerised desktop.
async fn detect_desktop(
    target: &VmSshTarget,
    key_override: Option<&std::path::Path>,
) -> Result<GuiStatus> {
    let script = crate::cmd_gui_install::wrap_for_shell(&build_detect_script());
    let result = crate::dispatch_helpers::run_target_command_with_timeout(
        target,
        &script,
        GUI_DETECT_TIMEOUT_SECS,
        key_override,
    )
    .await;
    classify_detect_result(result)
}

/// Interpret the detection probe's result.
///
/// The probe always exits zero, so a non-zero exit means the SSH transport
/// failed and must be reported as such rather than as "not installed".
fn classify_detect_result(result: Result<(i32, String, String)>) -> Result<GuiStatus> {
    match result {
        Ok((0, stdout, _)) => Ok(parse_detect_output(&stdout)),
        Ok((code, _, stderr)) => anyhow::bail!(
            "Could not check the VM for a remote desktop (exit {}): {}",
            code,
            azlin_core::sanitizer::sanitize(stderr.trim())
        ),
        Err(err) => anyhow::bail!(
            "Could not check the VM for a remote desktop: {}",
            azlin_core::sanitizer::sanitize(&err.to_string())
        ),
    }
}

fn start_desktop(ssh_cmd_prefix: &[String]) -> Result<()> {
    let script = crate::cmd_gui_install::wrap_for_shell(&build_start_script());
    let (code, _, stderr) = run_ssh_command_full(ssh_cmd_prefix, &script)?;
    if code != 0 {
        anyhow::bail!(
            "The remote desktop container exists but could not be started: {}\n\
             Inspect it on the VM with: docker logs azlin-gui",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
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

    // Check for vncviewer (PATH first, then macOS app bundles)
    if find_vncviewer().is_none() {
        anyhow::bail!("{}", vncviewer_missing_message());
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// vncviewer discovery
// ---------------------------------------------------------------------------

/// Relative paths (inside an applications directory) of known macOS VNC viewer
/// app bundles. `brew install --cask tigervnc` installs an app bundle and does
/// not put `vncviewer` on PATH, so a PATH-only probe misses it.
#[cfg(target_os = "macos")]
const MACOS_VIEWER_BUNDLE_PATHS: &[&str] = &["TigerVNC.app/Contents/MacOS/vncviewer"];

/// Absolute macOS app-bundle locations to probe, in priority order.
#[cfg(target_os = "macos")]
fn macos_viewer_candidates() -> Vec<std::path::PathBuf> {
    let mut roots = vec![std::path::PathBuf::from("/Applications")];
    if let Some(home) = std::env::var_os("HOME") {
        roots.push(std::path::Path::new(&home).join("Applications"));
    }
    roots
        .iter()
        .flat_map(|root| MACOS_VIEWER_BUNDLE_PATHS.iter().map(move |p| root.join(p)))
        .collect()
}

/// True when `vncviewer` is resolvable on PATH.
fn vncviewer_on_path() -> bool {
    std::process::Command::new("which")
        .arg("vncviewer")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Resolve the vncviewer command, given whether it is already on PATH.
///
/// PATH always wins (unchanged behaviour on every platform). Only when PATH
/// lookup fails does macOS fall back to well-known app-bundle locations.
fn find_vncviewer_with(on_path: bool) -> Option<std::path::PathBuf> {
    if on_path {
        return Some(std::path::PathBuf::from("vncviewer"));
    }
    #[cfg(target_os = "macos")]
    {
        macos_viewer_candidates()
            .into_iter()
            .find(|candidate| candidate.is_file())
    }
    #[cfg(not(target_os = "macos"))]
    {
        None
    }
}

/// Locate the vncviewer binary to launch, or `None` if it is not installed.
fn find_vncviewer() -> Option<std::path::PathBuf> {
    find_vncviewer_with(vncviewer_on_path())
}

/// Error text for a genuinely missing viewer, naming every location probed.
fn vncviewer_missing_message() -> String {
    let mut msg = String::from("vncviewer not found on PATH");
    #[cfg(target_os = "macos")]
    {
        msg.push_str(" or in any known app bundle:");
        for candidate in macos_viewer_candidates() {
            msg.push_str(&format!("\n  {}", candidate.display()));
        }
    }
    msg.push_str(
        "\nInstall it with:\n  \
         macOS:         brew install --cask tigervnc\n  \
         Debian/Ubuntu: sudo apt-get install -y tigervnc-viewer tigervnc-common",
    );
    msg
}

// ---------------------------------------------------------------------------
// SSH prefix builders
// ---------------------------------------------------------------------------

/// Build an SSH command prefix for direct connection to a public-IP VM.
#[cfg(test)]
fn build_direct_ssh_prefix(ip: &str, user: &str, key: Option<&std::path::Path>) -> Vec<String> {
    let config = crate::dispatch_helpers::load_user_config();
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

async fn build_gui_ssh_command_prefix(
    target: &VmSshTarget,
    connect_timeout: u64,
    key_override: Option<&std::path::Path>,
) -> Result<(
    Vec<String>,
    Option<crate::bastion_tunnel::ScopedBastionTunnel>,
)> {
    let (routed_prefix, tunnel) =
        crate::dispatch_helpers::build_routed_ssh_prefix(target, connect_timeout, key_override).await?;
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

#[cfg(test)]
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

async fn check_remote_deps(
    target: &VmSshTarget,
    key_override: Option<&std::path::Path>,
    mode: &VncMode,
) -> Result<()> {
    let script = build_dependency_setup_script(mode);
    let timeout_secs = GUI_SETUP_TIMEOUT_SECS;
    match crate::dispatch_helpers::run_target_command_with_timeout(
        target,
        &script,
        timeout_secs,
        key_override,
    )
    .await
    {
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
// Desktop tunnel (SSH -L port forwarding)
// ---------------------------------------------------------------------------

/// Build `ssh -N -L <local>:localhost:<remote>` from an existing SSH prefix.
///
/// `remote_port` is the loopback port the desktop listens on inside the VM, so
/// the same code path serves the native VNC server (5901) and a containerised
/// VNC (5901) or RDP (3389) desktop.
fn build_desktop_tunnel_args(
    ssh_cmd_prefix: &[String],
    local_port: u16,
    remote_port: u16,
) -> Result<Vec<String>> {
    let mut args: Vec<String> = Vec::new();

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
    args.push(format!("{}:localhost:{}", local_port, remote_port));
    // user@host is the last element
    args.push(ssh_cmd_prefix.last().unwrap().clone());

    Ok(args)
}

fn open_desktop_tunnel(
    ssh_cmd_prefix: &[String],
    remote_port: u16,
    label: &str,
) -> Result<(u16, Vec<u32>)> {
    let local_port = crate::pick_unused_local_port()?;
    let args = build_desktop_tunnel_args(ssh_cmd_prefix, local_port, remote_port)?;

    let mut child = std::process::Command::new("ssh")
        .args(&args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .with_context(|| format!("Failed to spawn SSH port-forward for the {label}"))?;

    let pid = child.id();
    if let Err(error) = crate::bastion_tunnel::wait_for_process_tree_listener(
        local_port,
        pid,
        std::time::Duration::from_secs(10),
        &format!("{label} tunnel"),
    ) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error).context(format!(
            "{label} tunnel failed to listen on 127.0.0.1:{}",
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

fn launch_viewer(
    ssh_cmd_prefix: &[String],
    remote_passwd_path: &str,
    local_port: u16,
) -> Result<()> {
    // Retrieve the VNC passwd file from the remote VM. The native path writes it
    // with `vncpasswd`; the containerised path exports the container's own blob.
    let passwd_b64 = run_ssh_command(ssh_cmd_prefix, &format!("base64 < {}", remote_passwd_path))
        .with_context(|| {
            format!("Could not read the VNC password file {remote_passwd_path} from the VM")
        })?;
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

    let viewer = match find_vncviewer() {
        Some(v) => v,
        None => {
            let _ = std::fs::remove_file(&passwd_file);
            anyhow::bail!("{}", vncviewer_missing_message());
        }
    };
    let mut cmd = std::process::Command::new(&viewer);
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
        anyhow::bail!(
            "vncviewer exited with status {}",
            status.code().unwrap_or(-1)
        );
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// RDP client launch (containerised desktop only)
// ---------------------------------------------------------------------------

/// Local RDP clients azlin knows how to drive, in preference order.
const RDP_CLIENTS: &[&str] = &["xfreerdp3", "xfreerdp", "mstsc.exe", "mstsc"];

/// Find the first available local RDP client.
fn find_rdp_client(is_available: impl Fn(&str) -> bool) -> Option<&'static str> {
    RDP_CLIENTS.iter().copied().find(|c| is_available(c))
}

/// Build the argument list for a given RDP client binary.
fn build_rdp_client_args(client: &str, local_port: u16, username: &str) -> Vec<String> {
    if client.starts_with("mstsc") {
        // mstsc takes only the endpoint; it prompts for credentials.
        vec![format!("/v:127.0.0.1:{}", local_port)]
    } else {
        vec![
            format!("/v:127.0.0.1:{}", local_port),
            format!("/u:{}", username),
            "/cert:ignore".to_string(),
            "/dynamic-resolution".to_string(),
        ]
    }
}

/// Instructions printed when no local RDP client is available.
fn rdp_manual_instructions(local_port: u16, username: &str) -> String {
    format!(
        "The RDP tunnel is open on 127.0.0.1:{local_port}.\n\
         Connect with any RDP client using:\n  \
           host:     127.0.0.1:{local_port}\n  \
           username: {username}\n  \
           password: read ~/.azlin/gui/rdppasswd on the VM\n\n\
         Examples:\n  \
           xfreerdp /v:127.0.0.1:{local_port} /u:{username} /cert:ignore\n  \
           mstsc /v:127.0.0.1:{local_port}\n  \
           macOS: open Microsoft Remote Desktop and add PC 127.0.0.1:{local_port}\n\n\
         Press Ctrl+C to close the tunnel."
    )
}

fn launch_rdp_client(ssh_cmd_prefix: &[String], local_port: u16) -> Result<()> {
    let username = RDP_USERNAME;

    let Some(client) = find_rdp_client(|c| {
        std::process::Command::new("which")
            .arg(c)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }) else {
        println!("{}", rdp_manual_instructions(local_port, username));
        // Hold the tunnel open until interrupted so the printed endpoint is usable.
        wait_for_interrupt();
        return Ok(());
    };

    // Surface the password so the user can paste it into the client prompt. It
    // never leaves the SSH channel and is not written to disk locally.
    match run_ssh_command(ssh_cmd_prefix, &format!("cat {}", HOST_RDP_PASSWD_PATH)) {
        Ok(password) if !password.trim().is_empty() => {
            println!("RDP login: {} / {}", username, password.trim());
        }
        _ => {
            eprintln!("warning: could not read the RDP password from the VM ({HOST_RDP_PASSWD_PATH}).");
            eprintln!("         Re-run `azlin gui install <vm> --protocol rdp` to regenerate it.");
        }
    }

    println!("Launching {} (127.0.0.1:{})...", client, local_port);
    println!("Press Ctrl+C to stop the GUI session.\n");

    let status = std::process::Command::new(client)
        .args(build_rdp_client_args(client, local_port, username))
        .status()
        .with_context(|| format!("Failed to launch {}", client))?;

    if !status.success() {
        anyhow::bail!(
            "{} exited with status {}",
            client,
            status.code().unwrap_or(-1)
        );
    }

    Ok(())
}

/// Block until the user interrupts, keeping a tunnel usable meanwhile.
fn wait_for_interrupt() {
    loop {
        std::thread::sleep(std::time::Duration::from_secs(3600));
    }
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

/// Tear down local tunnel processes.
fn kill_tunnels(pids: &[u32]) {
    for pid in pids {
        let _ = std::process::Command::new("kill")
            .arg(pid.to_string())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
}

fn cleanup(pids: &[u32], ssh_cmd_prefix: &[String]) {
    // Kill remote VNC server (native path only; the container is left running so
    // reconnecting is fast, and is removed by `azlin gui install --uninstall`).
    let _ = run_ssh_command(
        ssh_cmd_prefix,
        &format!("vncserver -kill :{} 2>/dev/null || true", VNC_DISPLAY),
    );

    kill_tunnels(pids);
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
pub(crate) fn is_valid_resolution(res: &str) -> bool {
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

    #[tokio::test]
    async fn test_gui_routed_ssh_command_prefix_starts_with_ssh_binary() {
        let target = VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "1.2.3.4".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: false,
            bastion: None,
        };

        let (prefix, tunnel) = build_gui_ssh_command_prefix(&target, 30, None).await.unwrap();
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
        let args = build_desktop_tunnel_args(
            &[
                "ssh".to_string(),
                "-i".to_string(),
                "/tmp/test-key".to_string(),
                "azureuser@10.0.0.5".to_string(),
            ],
            41234,
            VNC_PORT,
        )
        .unwrap();

        assert!(args.contains(&"-N".to_string()));
        assert!(args.contains(&"-L".to_string()));
        assert!(args.contains(&"41234:localhost:5901".to_string()));
        assert_eq!(args.last().map(String::as_str), Some("azureuser@10.0.0.5"));
    }

    #[test]
    fn test_build_vnc_tunnel_args_require_destination() {
        let err = build_desktop_tunnel_args(&["ssh".to_string()], 41234, VNC_PORT).unwrap_err();
        assert!(err.to_string().contains("must include a destination"));
    }

    #[test]
    fn test_build_desktop_tunnel_args_support_rdp_remote_port() {
        let args = build_desktop_tunnel_args(
            &[
                "ssh".to_string(),
                "-p".to_string(),
                "2222".to_string(),
                "azureuser@127.0.0.1".to_string(),
            ],
            41235,
            3389,
        )
        .unwrap();

        assert!(args.contains(&"41235:localhost:3389".to_string()));
        assert!(args.contains(&"-p".to_string()));
        assert!(args.contains(&"2222".to_string()));
    }

    #[test]
    fn test_find_rdp_client_prefers_xfreerdp3() {
        let found = find_rdp_client(|c| c == "xfreerdp3" || c == "mstsc");
        assert_eq!(found, Some("xfreerdp3"));

        let found = find_rdp_client(|c| c == "mstsc");
        assert_eq!(found, Some("mstsc"));

        assert_eq!(find_rdp_client(|_| false), None);
    }

    #[test]
    fn test_build_rdp_client_args_shapes() {
        let free = build_rdp_client_args("xfreerdp3", 41235, "abc");
        assert!(free.contains(&"/v:127.0.0.1:41235".to_string()));
        assert!(free.contains(&"/u:abc".to_string()));
        assert!(free.contains(&"/cert:ignore".to_string()));

        // mstsc has no /u: flag - it prompts instead.
        let ms = build_rdp_client_args("mstsc.exe", 41235, "abc");
        assert_eq!(ms, vec!["/v:127.0.0.1:41235".to_string()]);
    }

    #[test]
    fn test_rdp_manual_instructions_are_actionable() {
        let text = rdp_manual_instructions(41235, "abc");
        assert!(text.contains("127.0.0.1:41235"));
        assert!(text.contains("abc"));
        assert!(text.contains("xfreerdp"));
        // Must never suggest exposing the port publicly.
        assert!(!text.contains("0.0.0.0"));
    }

    #[test]
    fn test_classify_detect_result_maps_states() {
        let ok = classify_detect_result(Ok((0, "docker=yes\ncontainer=running\n".into(), String::new())));
        assert!(ok.is_ok());

        let failed = classify_detect_result(Err(anyhow::anyhow!("ssh blew up")));
        assert!(failed.is_err());
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

    // ── vncviewer discovery ────────────────────────────────────────────

    #[test]
    fn test_find_vncviewer_prefers_path() {
        assert_eq!(
            find_vncviewer_with(true),
            Some(std::path::PathBuf::from("vncviewer"))
        );
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn test_macos_viewer_candidates_include_system_and_user_bundles() {
        let candidates = macos_viewer_candidates();
        assert!(candidates.contains(&std::path::PathBuf::from(
            "/Applications/TigerVNC.app/Contents/MacOS/vncviewer"
        )));
        if let Some(home) = std::env::var_os("HOME") {
            let user_bundle = std::path::Path::new(&home)
                .join("Applications/TigerVNC.app/Contents/MacOS/vncviewer");
            assert!(candidates.contains(&user_bundle));
        }
        // /Applications is probed before ~/Applications.
        assert!(candidates[0].starts_with("/Applications"));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn test_find_vncviewer_falls_back_to_app_bundle_when_present() {
        // When TigerVNC.app is installed, a PATH miss must still resolve to
        // the bundle binary rather than reporting "not found".
        let installed = macos_viewer_candidates().into_iter().find(|c| c.is_file());
        match installed {
            Some(expected) => assert_eq!(find_vncviewer_with(false), Some(expected)),
            None => assert_eq!(find_vncviewer_with(false), None),
        }
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn test_find_vncviewer_no_fallback_off_macos() {
        assert_eq!(find_vncviewer_with(false), None);
    }

    #[test]
    fn test_vncviewer_missing_message_mentions_install_commands() {
        let msg = vncviewer_missing_message();
        assert!(msg.contains("vncviewer not found on PATH"));
        assert!(msg.contains("brew install --cask tigervnc"));
        assert!(msg.contains("tigervnc-viewer"));
        #[cfg(target_os = "macos")]
        assert!(msg.contains("/Applications/TigerVNC.app/Contents/MacOS/vncviewer"));
    }
}
