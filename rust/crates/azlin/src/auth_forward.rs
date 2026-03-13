//! Auth credential forwarding for newly created VMs.
//!
//! Detects local authentication credentials (gh CLI, GitHub Copilot,
//! Claude Code, Azure CLI) and offers to copy them to a remote VM.
//! Best-effort: failures never block VM creation.

use anyhow::Result;
use std::io::IsTerminal;
use std::path::PathBuf;

/// A detected local credential source.
struct CredentialSource {
    name: &'static str,
    description: &'static str,
    forward_fn: fn(&str, &str, Option<u16>) -> Result<()>,
}

/// Entry point: detect credentials and offer to forward each one.
/// `bastion_port` is `Some(port)` when the VM is behind a bastion tunnel on 127.0.0.1.
pub fn forward_auth_credentials(ip: &str, user: &str, force: bool, bastion_port: Option<u16>) -> Result<()> {
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

/// Detect which credential sources are available locally.
fn detect_credentials() -> Vec<CredentialSource> {
    let mut sources = Vec::new();

    // gh CLI
    if is_gh_authenticated() {
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

    // Azure CLI: always present (we just created a VM with it)
    sources.push(CredentialSource {
        name: "az",
        description: "Azure CLI (guidance only)",
        forward_fn: forward_az,
    });

    sources
}

// ---------------------------------------------------------------------------
// Detection helpers
// ---------------------------------------------------------------------------

fn is_gh_authenticated() -> bool {
    std::process::Command::new("gh")
        .args(["auth", "status"])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
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

// ---------------------------------------------------------------------------
// Forwarders
// ---------------------------------------------------------------------------

/// Forward gh CLI auth by piping token via stdin (never as a command arg).
fn forward_gh(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let token_output = std::process::Command::new("gh")
        .args(["auth", "token"])
        .output()?;
    if !token_output.status.success() {
        anyhow::bail!("gh auth token failed");
    }
    let token = String::from_utf8_lossy(&token_output.stdout);
    let token = token.trim();
    if token.is_empty() {
        anyhow::bail!("gh returned empty token");
    }

    // Pipe token into remote gh auth login via stdin
    let (ssh_host, port_args) = ssh_target(ip, user, bastion_port);
    let mut args = vec!["-o", "StrictHostKeyChecking=accept-new"];
    for a in &port_args {
        args.push(a);
    }
    args.push(&ssh_host);
    args.push("gh auth login --with-token");

    let mut child = std::process::Command::new("ssh")
        .args(&args)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .spawn()?;

    if let Some(ref mut stdin) = child.stdin {
        use std::io::Write;
        stdin.write_all(token.as_bytes())?;
    }
    // Drop stdin to signal EOF
    drop(child.stdin.take());

    let output = child.wait_with_output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("remote gh auth login failed: {}", stderr.trim());
    }
    println!("  gh credentials forwarded.");
    Ok(())
}

/// Forward GitHub Copilot config via scp.
fn forward_copilot(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let src = copilot_config_dir().ok_or_else(|| anyhow::anyhow!("copilot config not found"))?;

    // Ensure remote directory exists
    let (ssh_host, port_args) = ssh_target(ip, user, bastion_port);
    let mut mkdir_args = vec!["-o", "StrictHostKeyChecking=accept-new"];
    for a in &port_args {
        mkdir_args.push(a);
    }
    mkdir_args.push(&ssh_host);
    mkdir_args.push("mkdir -p ~/.config/github-copilot");
    let _ = std::process::Command::new("ssh").args(&mkdir_args).output();

    let (scp_dest, scp_port_args) = scp_target(ip, user, "~/.config/github-copilot/", bastion_port);
    let mut scp_args = vec!["-r".to_string(), "-o".to_string(), "StrictHostKeyChecking=accept-new".to_string()];
    scp_args.extend(scp_port_args);
    scp_args.push(src.to_string_lossy().to_string());
    scp_args.push(scp_dest);

    let status = std::process::Command::new("scp")
        .args(&scp_args)
        .status()?;
    if !status.success() {
        anyhow::bail!("scp failed for copilot config");
    }
    println!("  Copilot config forwarded.");
    Ok(())
}

/// Forward Claude Code config via scp.
fn forward_claude(ip: &str, user: &str, bastion_port: Option<u16>) -> Result<()> {
    let src = claude_config_path().ok_or_else(|| anyhow::anyhow!("claude config not found"))?;

    let (scp_dest, scp_port_args) = scp_target(ip, user, "~/.claude.json", bastion_port);
    let mut scp_args = vec!["-o".to_string(), "StrictHostKeyChecking=accept-new".to_string()];
    scp_args.extend(scp_port_args);
    scp_args.push(src.to_string_lossy().to_string());
    scp_args.push(scp_dest);

    let status = std::process::Command::new("scp")
        .args(&scp_args)
        .status()?;
    if !status.success() {
        anyhow::bail!("scp failed for claude config");
    }
    println!("  Claude Code config forwarded.");
    Ok(())
}

/// Azure CLI: print guidance only — no token copying.
fn forward_az(_ip: &str, _user: &str, _bastion_port: Option<u16>) -> Result<()> {
    println!("  Run 'az login' on the VM to authenticate with Azure CLI.");
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
fn scp_target(ip: &str, user: &str, remote_path: &str, bastion_port: Option<u16>) -> (String, Vec<String>) {
    match bastion_port {
        Some(port) => (
            format!("{}@127.0.0.1:{}", user, remote_path),
            vec!["-P".to_string(), port.to_string()],
        ),
        None => (
            format!("{}@{}:{}", user, ip, remote_path),
            vec![],
        ),
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
