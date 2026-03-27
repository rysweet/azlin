//! Auth credential forwarding for newly created VMs.
//!
//! Detects local authentication credentials (gh CLI, GitHub Copilot,
//! Claude Code, Azure CLI) and offers to copy config files to a remote VM.
//! All forwarding is done via SCP file copy — no remote login commands.
//! Best-effort: failures never block VM creation.

use anyhow::Result;
use std::io::IsTerminal;
use std::net::TcpStream;
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// A detected local credential source.
struct CredentialSource {
    name: &'static str,
    description: &'static str,
    forward_fn: fn(&str, &str, Option<u16>) -> Result<()>,
}

/// Entry point: detect credentials and offer to forward each one.
/// `bastion_port` is `Some(port)` when the VM is behind a bastion tunnel on 127.0.0.1.
pub fn forward_auth_credentials(
    ip: &str,
    user: &str,
    force: bool,
    bastion_port: Option<u16>,
) -> Result<()> {
    // Wait for SSH to be ready before attempting any forwarding
    let ssh_port = bastion_port.unwrap_or(22);
    let ssh_host = if bastion_port.is_some() { "127.0.0.1" } else { ip };
    wait_for_ssh(ssh_host, ssh_port, user, Duration::from_secs(120))?;

    let sources = detect_credentials();
    if sources.is_empty() {
        return Ok(());
    }

    println!("\nDetected local auth credentials:");
    for src in &sources {
        println!("  - {}: {}", src.name, src.description);
    }
    println!();

    for src in &sources {
        if !confirm(&format!("Forward {} credentials to VM?", src.name), force) {
            continue;
        }
        if let Err(e) = (src.forward_fn)(ip, user, bastion_port) {
            eprintln!("  Warning: failed to forward {}: {}", src.name, e);
        }
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// SSH readiness — poll port + test auth before any forwarding
// ---------------------------------------------------------------------------

/// Wait for SSH to become available on the target. Polls the TCP port first,
/// then verifies actual SSH authentication works (key accepted).
fn wait_for_ssh(host: &str, port: u16, user: &str, timeout: Duration) -> Result<()> {
    let start = Instant::now();
    let interval = Duration::from_secs(5);

    println!("Waiting for SSH to be ready on {}:{}...", host, port);

    loop {
        if start.elapsed() >= timeout {
            anyhow::bail!(
                "SSH not ready after {}s — VM may still be booting. Try: ssh {}@{} -p {}",
                timeout.as_secs(),
                user,
                host,
                port,
            );
        }

        // Step 1: TCP port check
        if TcpStream::connect_timeout(
            &format!("{}:{}", host, port).parse().unwrap_or_else(|_| {
                std::net::SocketAddr::from(([127, 0, 0, 1], port))
            }),
            Duration::from_secs(3),
        )
        .is_ok()
        {
            // Step 2: actual SSH auth test
            if test_ssh_auth(host, port, user) {
                println!("SSH ready.");
                return Ok(());
            }
        }

        std::thread::sleep(interval);
    }
}

/// Test SSH authentication by running `exit 0` on the remote.
fn test_ssh_auth(host: &str, port: u16, user: &str) -> bool {
    let status = std::process::Command::new("ssh")
        .args([
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "LogLevel=ERROR",
            "-p", &port.to_string(),
            &format!("{}@{}", user, host),
            "exit 0",
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    status.map(|s| s.success()).unwrap_or(false)
}

/// Detect which credential sources are available locally.
fn detect_credentials() -> Vec<CredentialSource> {
    let mut sources = Vec::new();

    // gh CLI
    if gh_config_dir().is_some() {
        sources.push(CredentialSource {
            name: "gh",
            description: "GitHub CLI authentication",
            forward_fn: forward_gh,
        });
    }

    // GitHub Copilot CLI
    if copilot_config_dir().is_some() {
        sources.push(CredentialSource {
            name: "copilot",
            description: "GitHub Copilot CLI config",
            forward_fn: forward_copilot,
        });
    }

    // Claude Code
    if claude_config_path().is_some() {
        sources.push(CredentialSource {
            name: "claude",
            description: "Claude Code config",
            forward_fn: forward_claude,
        });
    }

    // Azure CLI
    if az_config_dir().is_some() {
        sources.push(CredentialSource {
            name: "az",
            description: "Azure CLI tokens",
            forward_fn: forward_az,
        });
    }

    sources
}

// ---------------------------------------------------------------------------
// Detection helpers
// ---------------------------------------------------------------------------

/// Returns the gh config directory (~/.config/gh) if it contains hosts.yml.
fn gh_config_dir() -> Option<PathBuf> {
    let base = dirs::home_dir()?.join(".config").join("gh");
    if base.join("hosts.yml").exists() {
        Some(base)
    } else {
        None
    }
}

fn copilot_config_dir() -> Option<PathBuf> {
    let base = dirs::home_dir()?.join(".config").join("github-copilot");
    if base.join("hosts.json").exists() || base.join("apps.json").exists() {
        Some(base)
    } else {
        None
    }
}

fn claude_config_path() -> Option<PathBuf> {
    let p = dirs::home_dir()?.join(".claude.json");
    if p.exists() {
        Some(p)
    } else {
        None
    }
}

/// Returns the Azure CLI config directory (~/.azure) if it exists and has tokens.
fn az_config_dir() -> Option<PathBuf> {
    let base = dirs::home_dir()?.join(".azure");
    if !base.is_dir() {
        return None;
    }
    // Must have at least one token/config file worth forwarding
    let dominated = [
        "azureProfile.json",
        "config",
        "clouds.config",
        "msal_token_cache.json",
        "msal_token_cache.bin",
    ];
    if dominated.iter().any(|f| base.join(f).exists()) {
        Some(base)
    } else {
        None
    }
}

// ---------------------------------------------------------------------------
// Forwarders — all use SCP file copy, no remote login commands
// ---------------------------------------------------------------------------

/// Forward gh CLI config by copying ~/.config/gh/ directory via SCP.
fn forward_gh(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let src = gh_config_dir().ok_or_else(|| anyhow::anyhow!("gh config not found"))?;

    // Ensure remote directory exists
    ssh_run(ip, user, bastion_port, "mkdir -p ~/.config/gh")?;

    scp_recursive(&src, ip, user, "~/.config/gh/", bastion_port)?;
    println!("  gh credentials forwarded.");
    Ok(())
}

/// Forward GitHub Copilot config via scp.
fn forward_copilot(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let src = copilot_config_dir().ok_or_else(|| anyhow::anyhow!("copilot config not found"))?;

    ssh_run(ip, user, bastion_port, "mkdir -p ~/.config/github-copilot")?;

    scp_recursive(&src, ip, user, "~/.config/github-copilot/", bastion_port)?;
    println!("  Copilot config forwarded.");
    Ok(())
}

/// Forward Claude Code config via scp.
fn forward_claude(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let src = claude_config_path().ok_or_else(|| anyhow::anyhow!("claude config not found"))?;

    scp_file(&src, ip, user, "~/.claude.json", bastion_port)?;
    println!("  Claude Code config forwarded.");
    Ok(())
}

/// Forward Azure CLI tokens by copying allowed files from ~/.azure/ via SCP.
/// Copies token caches and config but NOT service principal credentials.
fn forward_az(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let az_dir = az_config_dir().ok_or_else(|| anyhow::anyhow!("az config not found"))?;

    // Only copy safe files — token caches and config, never service principals
    let allowed_files = [
        "azureProfile.json",
        "config",
        "clouds.config",
        "msal_token_cache.json",
        "msal_token_cache.bin",
    ];

    let files_to_copy: Vec<PathBuf> = allowed_files
        .iter()
        .map(|f| az_dir.join(f))
        .filter(|p| p.exists())
        .collect();

    if files_to_copy.is_empty() {
        anyhow::bail!("no Azure CLI token files found to copy");
    }

    ssh_run(ip, user, bastion_port, "mkdir -p ~/.azure")?;

    for file in &files_to_copy {
        let remote_name = file.file_name().unwrap().to_string_lossy();
        let remote_path = format!("~/.azure/{}", remote_name);
        scp_file(file, ip, user, &remote_path, bastion_port)?;
    }
    println!("  Azure CLI tokens forwarded.");
    Ok(())
}

// ---------------------------------------------------------------------------
// SSH/SCP helpers
// ---------------------------------------------------------------------------

/// Run a command on the remote via SSH. Returns Ok(()) on success.
fn ssh_run(ip: &str, user: &str, bastion_port: Option<u16>, command: &str) -> Result<()> {
    let (ssh_host, port_args) = ssh_target(ip, user, bastion_port);
    let mut args = vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
    ];
    args.extend(port_args);
    args.push(ssh_host);
    args.push(command.to_string());

    let output = std::process::Command::new("ssh")
        .args(&args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("ssh command failed: {}", stderr.trim());
    }
    Ok(())
}

/// SCP a single file to the remote.
fn scp_file(
    local: &PathBuf,
    ip: &str,
    user: &str,
    remote_path: &str,
    bastion_port: Option<u16>,
) -> Result<()> {
    let (scp_dest, scp_port_args) = scp_target(ip, user, remote_path, bastion_port);
    let mut args = vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
    ];
    args.extend(scp_port_args);
    args.push(local.to_string_lossy().to_string());
    args.push(scp_dest);

    let status = std::process::Command::new("scp").args(&args).status()?;
    if !status.success() {
        anyhow::bail!("scp failed for {}", local.display());
    }
    Ok(())
}

/// SCP a directory recursively to the remote.
fn scp_recursive(
    local_dir: &PathBuf,
    ip: &str,
    user: &str,
    remote_path: &str,
    bastion_port: Option<u16>,
) -> Result<()> {
    let (scp_dest, scp_port_args) = scp_target(ip, user, remote_path, bastion_port);
    let mut args = vec![
        "-r".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
    ];
    args.extend(scp_port_args);
    args.push(local_dir.to_string_lossy().to_string());
    args.push(scp_dest);

    let status = std::process::Command::new("scp").args(&args).status()?;
    if !status.success() {
        anyhow::bail!("scp failed for {}", local_dir.display());
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Bastion routing helpers
// ---------------------------------------------------------------------------

/// Returns (user@host, port_args) for SSH commands. Routes through 127.0.0.1
/// when a bastion tunnel port is provided.
fn ssh_target(ip: &str, user: &str, bastion_port: Option<u16>) -> (String, Vec<String>) {
    match bastion_port {
        Some(port) => (
            format!("{}@127.0.0.1", user),
            vec!["-p".to_string(), port.to_string()],
        ),
        None => (format!("{}@{}", user, ip), vec![]),
    }
}

/// Returns (user@host:path, port_args) for SCP commands.
fn scp_target(
    ip: &str,
    user: &str,
    remote_path: &str,
    bastion_port: Option<u16>,
) -> (String, Vec<String>) {
    match bastion_port {
        Some(port) => (
            format!("{}@127.0.0.1:{}", user, remote_path),
            vec!["-P".to_string(), port.to_string()],
        ),
        None => (format!("{}@{}:{}", user, ip, remote_path), vec![]),
    }
}

// ---------------------------------------------------------------------------
// Confirmation helper
// ---------------------------------------------------------------------------

/// Prompt for confirmation. Returns `false` on non-TTY (best-effort, no error).
/// If `force` is true, returns `true` without prompting.
fn confirm(prompt: &str, force: bool) -> bool {
    if force {
        return true;
    }
    if !std::io::stdin().is_terminal() {
        return false;
    }
    dialoguer::Confirm::new()
        .with_prompt(prompt)
        .default(false)
        .interact()
        .unwrap_or(false)
}
