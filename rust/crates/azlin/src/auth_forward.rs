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
    forward_fn: fn(&str, &str) -> Result<()>,
}

/// Entry point: detect credentials and offer to forward each one.
pub fn forward_auth_credentials(ip: &str, user: &str, force: bool) -> Result<()> {
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
        if let Err(e) = (src.forward_fn)(ip, user) {
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
fn forward_gh(ip: &str, user: &str) -> Result<()> {
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
    let mut child = std::process::Command::new("ssh")
        .args([
            "-o",
            "StrictHostKeyChecking=accept-new",
            &format!("{}@{}", user, ip),
            "gh auth login --with-token",
        ])
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
fn forward_copilot(ip: &str, user: &str) -> Result<()> {
    let src = copilot_config_dir().ok_or_else(|| anyhow::anyhow!("copilot config not found"))?;
    let dest = format!(
        "{}@{}:~/.config/github-copilot/",
        user, ip
    );

    // Ensure remote directory exists
    let _ = std::process::Command::new("ssh")
        .args([
            "-o",
            "StrictHostKeyChecking=accept-new",
            &format!("{}@{}", user, ip),
            "mkdir -p ~/.config/github-copilot",
        ])
        .output();

    let status = std::process::Command::new("scp")
        .args([
            "-r",
            "-o",
            "StrictHostKeyChecking=accept-new",
            &src.to_string_lossy(),
            &dest,
        ])
        .status()?;
    if !status.success() {
        anyhow::bail!("scp failed for copilot config");
    }
    println!("  Copilot config forwarded.");
    Ok(())
}

/// Forward Claude Code config via scp.
fn forward_claude(ip: &str, user: &str) -> Result<()> {
    let src = claude_config_path().ok_or_else(|| anyhow::anyhow!("claude config not found"))?;
    let dest = format!("{}@{}:~/.claude.json", user, ip);

    let status = std::process::Command::new("scp")
        .args([
            "-o",
            "StrictHostKeyChecking=accept-new",
            &src.to_string_lossy(),
            &dest,
        ])
        .status()?;
    if !status.success() {
        anyhow::bail!("scp failed for claude config");
    }
    println!("  Claude Code config forwarded.");
    Ok(())
}

/// Azure CLI: print guidance only — no token copying.
fn forward_az(_ip: &str, _user: &str) -> Result<()> {
    println!("  Run 'az login' on the VM to authenticate with Azure CLI.");
    Ok(())
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
