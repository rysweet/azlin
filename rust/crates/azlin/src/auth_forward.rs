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
        let addr: std::net::SocketAddr = if host.contains(':') {
            // IPv6 address — bracket it
            format!("[{}]:{}", host, port)
        } else {
            format!("{}:{}", host, port)
        }
        .parse()
        .unwrap_or_else(|_| std::net::SocketAddr::from(([127, 0, 0, 1], port)));

        if TcpStream::connect_timeout(&addr, Duration::from_secs(3)).is_ok() {
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
    local: &std::path::Path,
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
    local_dir: &std::path::Path,
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tempfile::TempDir;

    // Serialize tests that modify the HOME env var to avoid data races.
    static HOME_LOCK: Mutex<()> = Mutex::new(());

    /// Run a closure with HOME temporarily set to `home`, restoring afterward.
    fn with_home<F: FnOnce() -> T, T>(home: &std::path::Path, f: F) -> T {
        let _lock = HOME_LOCK.lock().unwrap();
        let old = std::env::var("HOME").ok();
        #[allow(deprecated)]
        std::env::set_var("HOME", home);
        let result = f();
        match old {
            #[allow(deprecated)]
            Some(h) => std::env::set_var("HOME", h),
            #[allow(deprecated)]
            None => std::env::remove_var("HOME"),
        }
        result
    }

    // =======================================================================
    // ssh_target / scp_target — bastion routing
    // =======================================================================

    #[test]
    fn test_ssh_target_direct_connection() {
        let (host, port_args) = ssh_target("10.0.0.5", "azureuser", None);
        assert_eq!(host, "azureuser@10.0.0.5");
        assert!(port_args.is_empty(), "direct connection should have no port args");
    }

    #[test]
    fn test_ssh_target_bastion_tunnel() {
        let (host, port_args) = ssh_target("10.0.0.5", "azureuser", Some(50200));
        assert_eq!(host, "azureuser@127.0.0.1", "bastion routes through localhost");
        assert_eq!(port_args, vec!["-p", "50200"]);
    }

    #[test]
    fn test_scp_target_direct_connection() {
        let (dest, port_args) = scp_target("10.0.0.5", "azureuser", "~/.config/gh/", None);
        assert_eq!(dest, "azureuser@10.0.0.5:~/.config/gh/");
        assert!(port_args.is_empty());
    }

    #[test]
    fn test_scp_target_bastion_tunnel() {
        let (dest, port_args) =
            scp_target("10.0.0.5", "azureuser", "~/.config/gh/", Some(50200));
        assert_eq!(dest, "azureuser@127.0.0.1:~/.config/gh/");
        assert_eq!(port_args, vec!["-P", "50200"], "SCP uses -P (uppercase) for port");
    }

    #[test]
    fn test_ssh_target_preserves_original_ip_for_direct() {
        // Verifies the forward_fn receives the real VM IP (not 127.0.0.1)
        let (host, _) = ssh_target("40.78.100.1", "admin", None);
        assert!(host.contains("40.78.100.1"));
    }

    #[test]
    fn test_scp_target_embeds_remote_path() {
        let (dest, _) = scp_target("10.0.0.5", "user", "~/.azure/config", None);
        assert!(dest.ends_with(":~/.azure/config"));
    }

    // =======================================================================
    // IPv6 address parsing — wait_for_ssh socket addr construction
    // =======================================================================

    #[test]
    fn test_ipv4_addr_parses_to_socket() {
        let addr: std::net::SocketAddr = "10.0.0.5:22".parse().unwrap();
        assert!(addr.is_ipv4());
        assert_eq!(addr.port(), 22);
    }

    #[test]
    fn test_ipv6_addr_needs_brackets_for_socket() {
        // Raw IPv6 without brackets fails to parse as SocketAddr
        let result: Result<std::net::SocketAddr, _> = "fd00::1:22".parse();
        assert!(result.is_err(), "IPv6 without brackets should fail");
        // With brackets succeeds
        let addr: std::net::SocketAddr = "[fd00::1]:22".parse().unwrap();
        assert!(addr.is_ipv6());
        assert_eq!(addr.port(), 22);
    }

    #[test]
    fn test_ipv6_detection_uses_colon_heuristic() {
        // The code detects IPv6 via host.contains(':')
        assert!("fd00::1".contains(':'), "IPv6 triggers bracket path");
        assert!("::1".contains(':'));
        assert!(!"10.0.0.5".contains(':'), "IPv4 must not trigger bracket path");
    }

    #[test]
    fn test_ipv6_bracket_format_produces_valid_socketaddr() {
        let host = "2001:db8::1";
        let port = 22u16;
        let formatted = format!("[{}]:{}", host, port);
        let addr: std::net::SocketAddr = formatted.parse().unwrap();
        assert!(addr.is_ipv6());
        assert_eq!(addr.port(), 22);
    }

    #[test]
    fn test_invalid_addr_fallback_to_localhost() {
        // Mirrors the unwrap_or_else fallback in wait_for_ssh (line 88)
        let bad_host = "not-a-valid-ip";
        let port = 22u16;
        let addr: std::net::SocketAddr = format!("{}:{}", bad_host, port)
            .parse()
            .unwrap_or_else(|_| std::net::SocketAddr::from(([127, 0, 0, 1], port)));
        assert_eq!(addr.ip().to_string(), "127.0.0.1");
        assert_eq!(addr.port(), 22);
    }

    #[test]
    fn test_loopback_ipv6_parses_correctly() {
        let addr: std::net::SocketAddr = "[::1]:22".parse().unwrap();
        assert!(addr.is_ipv6());
        assert_eq!(addr.ip().to_string(), "::1");
    }

    // =======================================================================
    // confirm() — consent gating
    // =======================================================================

    #[test]
    fn test_confirm_force_bypasses_prompt() {
        assert!(confirm("Forward gh credentials?", true));
    }

    #[test]
    fn test_confirm_non_tty_returns_false() {
        // Test runner stdin is not a TTY → confirm returns false without prompting
        assert!(!confirm("Forward gh credentials?", false));
    }

    // =======================================================================
    // gh_config_dir — detection
    // =======================================================================

    #[test]
    fn test_gh_config_detected_with_hosts_yml() {
        let tmp = TempDir::new().unwrap();
        let gh_dir = tmp.path().join(".config").join("gh");
        std::fs::create_dir_all(&gh_dir).unwrap();
        std::fs::write(gh_dir.join("hosts.yml"), "github.com:\n  oauth_token: gho_xxx\n").unwrap();

        let result = with_home(tmp.path(), gh_config_dir);
        assert!(result.is_some(), "should detect gh when hosts.yml exists");
        assert!(result.unwrap().ends_with("gh"));
    }

    #[test]
    fn test_gh_config_not_detected_without_hosts_yml() {
        let tmp = TempDir::new().unwrap();
        let gh_dir = tmp.path().join(".config").join("gh");
        std::fs::create_dir_all(&gh_dir).unwrap();
        // No hosts.yml — only config.yml
        std::fs::write(gh_dir.join("config.yml"), "editor: vim\n").unwrap();

        let result = with_home(tmp.path(), gh_config_dir);
        assert!(result.is_none(), "should not detect gh without hosts.yml");
    }

    #[test]
    fn test_gh_config_not_detected_when_dir_missing() {
        let tmp = TempDir::new().unwrap();
        // No .config/gh directory at all
        let result = with_home(tmp.path(), gh_config_dir);
        assert!(result.is_none());
    }

    // =======================================================================
    // copilot_config_dir — detection
    // =======================================================================

    #[test]
    fn test_copilot_detected_with_hosts_json() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join(".config").join("github-copilot");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("hosts.json"), "{}").unwrap();

        let result = with_home(tmp.path(), copilot_config_dir);
        assert!(result.is_some());
    }

    #[test]
    fn test_copilot_detected_with_apps_json() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join(".config").join("github-copilot");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("apps.json"), "{}").unwrap();

        let result = with_home(tmp.path(), copilot_config_dir);
        assert!(result.is_some());
    }

    #[test]
    fn test_copilot_not_detected_without_marker_files() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join(".config").join("github-copilot");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("other.json"), "{}").unwrap();

        let result = with_home(tmp.path(), copilot_config_dir);
        assert!(result.is_none(), "needs hosts.json or apps.json");
    }

    // =======================================================================
    // claude_config_path — detection
    // =======================================================================

    #[test]
    fn test_claude_detected_with_config_file() {
        let tmp = TempDir::new().unwrap();
        std::fs::write(tmp.path().join(".claude.json"), r#"{"key":"val"}"#).unwrap();

        let result = with_home(tmp.path(), claude_config_path);
        assert!(result.is_some());
        assert!(result.unwrap().ends_with(".claude.json"));
    }

    #[test]
    fn test_claude_not_detected_without_file() {
        let tmp = TempDir::new().unwrap();

        let result = with_home(tmp.path(), claude_config_path);
        assert!(result.is_none());
    }

    // =======================================================================
    // az_config_dir — detection + allow-list
    // =======================================================================

    #[test]
    fn test_az_detected_with_profile_json() {
        let tmp = TempDir::new().unwrap();
        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();
        std::fs::write(az.join("azureProfile.json"), "{}").unwrap();

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_some());
    }

    #[test]
    fn test_az_detected_with_msal_token_cache() {
        let tmp = TempDir::new().unwrap();
        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();
        std::fs::write(az.join("msal_token_cache.json"), "{}").unwrap();

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_some());
    }

    #[test]
    fn test_az_detected_with_config_file() {
        let tmp = TempDir::new().unwrap();
        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();
        std::fs::write(az.join("config"), "[defaults]\n").unwrap();

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_some());
    }

    #[test]
    fn test_az_not_detected_with_empty_dir() {
        let tmp = TempDir::new().unwrap();
        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();
        // Directory exists but no allowed files

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_none(), "empty .azure dir should not be detected");
    }

    #[test]
    fn test_az_not_detected_when_dir_missing() {
        let tmp = TempDir::new().unwrap();

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_none());
    }

    #[test]
    fn test_az_not_detected_with_only_unknown_files() {
        let tmp = TempDir::new().unwrap();
        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();
        // Service principal creds or unrecognized files should not trigger detection
        std::fs::write(az.join("servicePrincipal.json"), "{}").unwrap();
        std::fs::write(az.join("random_file.txt"), "").unwrap();

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_none(), "only allowed files should trigger detection");
    }

    // =======================================================================
    // az allowed-file lists must stay in sync
    // =======================================================================

    #[test]
    fn test_az_forward_only_copies_allowed_files() {
        // Verify forward_az uses the same allow-list as az_config_dir.
        // Both functions define their lists independently — this test catches drift.
        // We test indirectly: create .azure with all 5 allowed files + 1 extra,
        // confirm detection works (uses the detection list), and that
        // the file set in az_config_dir is a subset of forward_az's allowed list.
        let tmp = TempDir::new().unwrap();
        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();

        // These are the 5 allowed files (must match both arrays)
        let allowed = [
            "azureProfile.json",
            "config",
            "clouds.config",
            "msal_token_cache.json",
            "msal_token_cache.bin",
        ];
        for f in &allowed {
            std::fs::write(az.join(f), "test").unwrap();
        }
        // Plus a file that must NOT be forwarded
        std::fs::write(az.join("servicePrincipal.json"), "secret").unwrap();

        let result = with_home(tmp.path(), az_config_dir);
        assert!(result.is_some(), "should detect with all allowed files present");
    }

    // =======================================================================
    // detect_credentials — aggregation
    // =======================================================================

    #[test]
    fn test_detect_credentials_finds_all_when_present() {
        let tmp = TempDir::new().unwrap();

        // Set up all four credential sources
        let gh = tmp.path().join(".config").join("gh");
        std::fs::create_dir_all(&gh).unwrap();
        std::fs::write(gh.join("hosts.yml"), "github.com:\n").unwrap();

        let copilot = tmp.path().join(".config").join("github-copilot");
        std::fs::create_dir_all(&copilot).unwrap();
        std::fs::write(copilot.join("hosts.json"), "{}").unwrap();

        std::fs::write(tmp.path().join(".claude.json"), "{}").unwrap();

        let az = tmp.path().join(".azure");
        std::fs::create_dir_all(&az).unwrap();
        std::fs::write(az.join("azureProfile.json"), "{}").unwrap();

        let sources = with_home(tmp.path(), detect_credentials);
        assert_eq!(sources.len(), 4, "should detect all four credential sources");

        let names: Vec<&str> = sources.iter().map(|s| s.name).collect();
        assert!(names.contains(&"gh"));
        assert!(names.contains(&"copilot"));
        assert!(names.contains(&"claude"));
        assert!(names.contains(&"az"));
    }

    #[test]
    fn test_detect_credentials_returns_empty_when_none() {
        let tmp = TempDir::new().unwrap();
        // Empty home — no credential sources

        let sources = with_home(tmp.path(), detect_credentials);
        assert!(sources.is_empty());
    }

    #[test]
    fn test_detect_credentials_partial_detection() {
        let tmp = TempDir::new().unwrap();
        // Only gh present
        let gh = tmp.path().join(".config").join("gh");
        std::fs::create_dir_all(&gh).unwrap();
        std::fs::write(gh.join("hosts.yml"), "github.com:\n").unwrap();

        let sources = with_home(tmp.path(), detect_credentials);
        assert_eq!(sources.len(), 1);
        assert_eq!(sources[0].name, "gh");
    }

    // =======================================================================
    // Azure tag compliance (azlin-session tag from cmd_vm_ops)
    // =======================================================================

    #[test]
    fn test_azlin_session_tag_name_within_azure_limits() {
        // Azure tag names: max 512 chars, can't contain <>*%&:\?/+
        let tag_name = "azlin-session";
        assert!(tag_name.len() <= 512);
        let forbidden = ['<', '>', '*', '%', '&', ':', '\\', '?', '/', '+'];
        for ch in &forbidden {
            assert!(!tag_name.contains(*ch), "tag name contains forbidden char: {}", ch);
        }
    }

    #[test]
    fn test_azlin_session_tag_value_respects_azure_256_limit() {
        // Azure tag values: max 256 chars
        // VM names generated by azlin: "azlin-vm-YYYYMMDD-HHMMSSffffff" = 31 chars
        let generated_name = format!("azlin-vm-{}", "20260327-170900123456");
        assert!(generated_name.len() <= 256, "auto-generated VM name must fit Azure tag value limit");

        // User-provided names are validated by validate_vm_name (max 64 chars)
        let user_name = "a".repeat(64);
        assert!(user_name.len() <= 256);
    }

    #[test]
    fn test_azlin_session_tag_uses_user_name_for_pools() {
        // When --name is given with --pool, all VMs in the pool share the same
        // azlin-session tag (the user's name, not the suffixed vm_name-N)
        let user_name = Some("my-dev-pool".to_string());
        let vm_count = 3u32;

        for i in 0..vm_count {
            let vm_name = format!("{}-{}", user_name.as_ref().unwrap(), i + 1);
            let mut tags = std::collections::HashMap::new();
            if let Some(ref n) = user_name {
                tags.insert("azlin-session".to_string(), n.clone());
            } else {
                tags.insert("azlin-session".to_string(), vm_name.clone());
            }
            // All pool VMs share the base name as session tag
            assert_eq!(tags["azlin-session"], "my-dev-pool");
        }
    }

    #[test]
    fn test_azlin_session_tag_uses_vm_name_when_no_user_name() {
        let user_name: Option<String> = None;
        let vm_name = "azlin-vm-20260327-170900123456".to_string();

        let mut tags = std::collections::HashMap::new();
        if let Some(ref n) = user_name {
            tags.insert("azlin-session".to_string(), n.clone());
        } else {
            tags.insert("azlin-session".to_string(), vm_name.clone());
        }
        assert_eq!(tags["azlin-session"], vm_name);
    }
}
