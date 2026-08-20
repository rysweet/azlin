#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use console::Style;

/// Comment line azlin writes directly above every host block it owns.
const AZLIN_MARKER: &str = "# Added by azlin\n";

/// Resolve the login name of the user running this process.
///
/// Used only to locate the Windows-side SSH directory under WSL2
/// (`/mnt/c/Users/<user>/.ssh`). Returns `None` when the environment gives us
/// nothing to go on — cron, systemd units, `env -i`, containers, CI — because
/// guessing a name points azlin at *another person's* SSH directory. Callers
/// must skip the Windows config in that case rather than write somewhere else.
fn resolve_username(
    get_env: impl Fn(&str) -> Option<String>,
    home: Option<std::path::PathBuf>,
) -> Option<String> {
    for var in ["USER", "LOGNAME", "USERNAME"] {
        if let Some(value) = get_env(var) {
            let value = value.trim();
            if !value.is_empty() {
                return Some(value.to_string());
            }
        }
    }
    // Last resort: the basename of this process's home directory. Still the
    // *current* user, never a hardcoded name belonging to somebody else.
    home.and_then(|home| home.file_name().map(|n| n.to_string_lossy().into_owned()))
        .filter(|name| !name.is_empty())
}

fn current_username() -> Option<String> {
    resolve_username(|var| std::env::var(var).ok(), dirs::home_dir())
}

/// Write or update an SSH config entry for a bastion-tunneled VM.
///
/// Creates host entries in both Linux (`~/.ssh/config`) and Windows
/// (`/mnt/c/Users/<user>/.ssh/config`) SSH configs so VS Code Remote-SSH
/// can connect through the bastion tunnel on `127.0.0.1:<port>`.
fn write_ssh_config_entry(
    vm_name: &str,
    user: &str,
    local_port: u16,
    key: Option<&std::path::Path>,
) -> Result<()> {
    let host_alias = format!("azlin-{}", vm_name);
    let linux_home = dirs::home_dir().context("Cannot determine home directory")?;
    let linux_key = key
        .map(|k| k.display().to_string())
        .or_else(|| {
            let k = linux_home.join(".ssh").join("azlin_key");
            k.exists().then(|| k.display().to_string())
        })
        .unwrap_or_else(|| linux_home.join(".ssh").join("id_rsa").display().to_string());

    let linux_block = format!(
        "\n# Added by azlin\nHost {}\n    HostName 127.0.0.1\n    Port {}\n    User {}\n    IdentityFile {}\n    StrictHostKeyChecking no\n    UserKnownHostsFile /dev/null\n    ServerAliveInterval 60\n    ServerAliveCountMax 3\n",
        host_alias, local_port, user, linux_key,
    );

    // Update Linux SSH config
    let linux_ssh_config = linux_home.join(".ssh").join("config");
    upsert_ssh_host_block(&linux_ssh_config, &host_alias, &linux_block)?;

    // Update Windows SSH config if on WSL2
    let Some(win_user) = current_username() else {
        eprintln!(
            "warning: skipping the Windows SSH config — cannot determine the current \
             username ($USER, $LOGNAME and $USERNAME are all unset)"
        );
        return Ok(());
    };
    let win_ssh_dir = std::path::Path::new("/mnt/c/Users")
        .join(win_user)
        .join(".ssh");
    if win_ssh_dir.exists() {
        let win_key = linux_key
            .replace("/home/", "C:\\Users\\")
            .replace('/', "\\");
        let win_block = format!(
            "\n# Added by azlin\nHost {}\n    HostName 127.0.0.1\n    Port {}\n    User {}\n    IdentityFile {}\n    StrictHostKeyChecking no\n    UserKnownHostsFile NUL\n    ServerAliveInterval 60\n    ServerAliveCountMax 3\n",
            host_alias, local_port, user, win_key,
        );
        let win_config = win_ssh_dir.join("config");
        upsert_ssh_host_block(&win_config, &host_alias, &win_block)?;
    }

    Ok(())
}

/// Read an existing SSH config, distinguishing "absent" from "unreadable".
///
/// A missing file yields an empty string — we are about to create it. Every
/// other failure is fatal: permission denied, a transient I/O error (likelier
/// on the `/mnt/c` mount), or non-UTF-8 bytes, which SSH configs legitimately
/// carry in comments and paths. The caller rewrites the *whole* file from this
/// string, so treating an unreadable config as empty would silently delete
/// every other `Host` entry the user has.
fn read_existing_ssh_config(config_path: &std::path::Path) -> Result<String> {
    let bytes = match std::fs::read(config_path) {
        Ok(bytes) => bytes,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(String::new()),
        Err(e) => {
            return Err(e).with_context(|| {
                format!(
                    "refusing to rewrite {} — could not read existing config",
                    config_path.display()
                )
            });
        }
    };
    String::from_utf8(bytes).map_err(|_| {
        anyhow::anyhow!(
            "refusing to rewrite {} — could not read existing config: it is not valid UTF-8",
            config_path.display()
        )
    })
}

/// Copy the current config aside before azlin rewrites it. Best effort: a
/// failed backup is reported but does not block the update.
fn backup_ssh_config(config_path: &std::path::Path, existing: &str) {
    if existing.is_empty() {
        return;
    }
    let Some(file_name) = config_path.file_name() else {
        return;
    };
    let mut backup_name = file_name.to_os_string();
    backup_name.push(".azlin.bak");
    let backup = config_path.with_file_name(backup_name);
    if let Err(e) = std::fs::write(&backup, existing) {
        eprintln!("warning: could not write {}: {}", backup.display(), e);
    }
}

/// True if `line` is an ssh_config `Host` keyword line.
fn is_host_line(line: &str) -> bool {
    line.split_whitespace()
        .next()
        .is_some_and(|kw| kw.eq_ignore_ascii_case("Host"))
}

/// True if `line` is a `Host` line that declares exactly `alias`.
///
/// Matching is on whole whitespace-separated tokens: `Host azlin-dev` matches
/// the alias `azlin-dev` and **not** `azlin-dev-2`. Pool members are named
/// `{name}-1`, `{name}-2`, so a substring match would rewrite a sibling VM's
/// block with this VM's tunnel port.
fn host_line_declares(line: &str, alias: &str) -> bool {
    let mut tokens = line.split_whitespace();
    match tokens.next() {
        Some(kw) if kw.eq_ignore_ascii_case("Host") => tokens.any(|token| token == alias),
        _ => false,
    }
}

/// Replace the `Host <alias>` block in `existing` with `new_block`, appending
/// it instead when the alias is absent. Pure: no I/O, so it is directly
/// testable against hand-written configs.
fn replace_host_block(existing: &str, host_alias: &str, new_block: &str) -> String {
    let mut block_start = None;
    let mut block_end = existing.len();
    // Start of the run of blank/comment lines immediately before the current
    // line: those introduce the *next* block, so they must survive.
    let mut trailer_start = None;
    let mut offset = 0;
    for line in existing.split_inclusive('\n') {
        let line_start = offset;
        offset += line.len();
        if block_start.is_none() {
            if host_line_declares(line, host_alias) {
                block_start = Some(line_start);
            }
            continue;
        }
        // The block runs until the next Host line, or to end of file.
        if is_host_line(line) {
            block_end = trailer_start.unwrap_or(line_start);
            break;
        }
        let trimmed = line.trim_start();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            trailer_start.get_or_insert(line_start);
        } else {
            trailer_start = None;
        }
    }

    let Some(mut start) = block_start else {
        let mut appended = String::with_capacity(existing.len() + new_block.len());
        appended.push_str(existing);
        appended.push_str(new_block);
        return appended;
    };

    // Absorb the "# Added by azlin" comment line directly above the block.
    if existing[..start].ends_with(AZLIN_MARKER) {
        start -= AZLIN_MARKER.len();
    }
    // `new_block` supplies its own leading blank line, so normalise the
    // newlines before it — otherwise every re-upsert adds another blank line.
    let prefix = existing[..start].trim_end_matches('\n');

    let mut updated = String::with_capacity(existing.len() + new_block.len());
    if !prefix.is_empty() {
        updated.push_str(prefix);
        updated.push('\n');
    }
    updated.push_str(new_block);
    updated.push_str(&existing[block_end..]);
    updated
}

/// Replace an existing `Host <alias>` block in an SSH config, or append if absent.
fn upsert_ssh_host_block(
    config_path: &std::path::Path,
    host_alias: &str,
    new_block: &str,
) -> Result<()> {
    let existing = read_existing_ssh_config(config_path)?;
    let updated = replace_host_block(&existing, host_alias, new_block);
    if updated == existing {
        return Ok(());
    }
    backup_ssh_config(config_path, &existing);
    std::fs::write(config_path, updated)
        .with_context(|| format!("Failed to write SSH config {}", config_path.display()))?;
    Ok(())
}

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Session {
            vm_name,
            session_name,
            clear,
            ..
        } => {
            let mut config =
                azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;

            if clear {
                if let Some(ref mut sessions) = config.session_names {
                    sessions.remove(&vm_name);
                }
                config.save()?;
                println!("Cleared session name for VM '{}'", vm_name);
            } else if let Some(name) = session_name {
                config
                    .session_names
                    .get_or_insert_with(std::collections::HashMap::new)
                    .insert(vm_name.clone(), name.clone());
                config.save()?;
                println!("Set session for VM '{}' = '{}'", vm_name, name);
            } else {
                let session = config
                    .session_names
                    .as_ref()
                    .and_then(|s| s.get(&vm_name))
                    .map(|v| v.as_str());
                match session {
                    Some(s) => println!("Session for VM '{}': {}", vm_name, s),
                    None => println!("No session name set for VM '{}'", vm_name),
                }
            }
        }

        // ── Status ───────────────────────────────────────────────────
        azlin_cli::Commands::Sessions { action } => match action {
            azlin_cli::SessionsAction::Save {
                session_name,
                resource_group,
                vms,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let sessions_dir = home_dir()?.join(".azlin").join("sessions");
                std::fs::create_dir_all(&sessions_dir)?;

                let session_val = crate::sessions::build_session_toml(&session_name, &rg, &vms);
                let path = sessions_dir.join(format!("{}.toml", session_name));
                std::fs::write(&path, toml::to_string_pretty(&session_val)?)?;
                println!("Saved session '{}' to {}", session_name, path.display());
            }
            azlin_cli::SessionsAction::Load { session_name } => {
                let path = home_dir()?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.toml", session_name));
                if !path.exists() {
                    anyhow::bail!("Session '{}' not found.", session_name);
                }
                let content = std::fs::read_to_string(&path)?;
                let (rg, vms, created) = crate::sessions::parse_session_toml(&content)?;
                println!("Loaded session '{}':", session_name);
                println!("  Resource group: {}", rg);
                if !vms.is_empty() {
                    println!("  VMs:            {}", vms.join(", "));
                }
                println!("  Created:        {}", created);
            }
            azlin_cli::SessionsAction::Delete {
                session_name,
                force,
            } => {
                let path = home_dir()?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.toml", session_name));
                if !path.exists() {
                    anyhow::bail!("Session '{}' not found.", session_name);
                }
                if !safe_confirm(&format!("Delete session '{}'?", session_name), force)? {
                    println!("Cancelled.");
                    return Ok(());
                }
                std::fs::remove_file(&path)?;
                println!("Deleted session '{}'.", session_name);
            }
            azlin_cli::SessionsAction::List => {
                let dir = home_dir()?.join(".azlin").join("sessions");
                let names = crate::sessions::list_session_names(&dir)?;
                if names.is_empty() {
                    println!("No saved sessions.");
                } else {
                    let rows: Vec<Vec<String>> = names.into_iter().map(|n| vec![n]).collect();
                    match output {
                        azlin_cli::OutputFormat::Table => {
                            for row in &rows {
                                println!("  {}", row[0]);
                            }
                        }
                        _ => {
                            azlin_cli::table::render_rows(&["Session"], &rows, output);
                        }
                    }
                }
            }
        },

        // ── Sync ─────────────────────────────────────────────────────
        azlin_cli::Commands::Status {
            resource_group, vm, ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = penguin_spinner("Fetching VM status...");

            let vms = vm_manager.list_vms(&rg)?;
            pb.finish_and_clear();

            let filtered: Vec<_> = match &vm {
                Some(name) => vms.into_iter().filter(|v| &v.name == name).collect(),
                None => vms,
            };

            if filtered.is_empty() {
                println!("No VMs found.");
                return Ok(());
            }

            let key_style = Style::new().cyan().bold();
            for v in &filtered {
                println!("{}:", key_style.apply_to(&v.name));
                println!("  Power State:        {}", v.power_state);
                println!("  Provisioning State: {}", v.provisioning_state);
                println!("  VM Size:            {}", v.vm_size);
                println!("  Location:           {}", v.location);
                if let Some(ip) = &v.public_ip {
                    println!("  Public IP:          {}", ip);
                }
                if let Some(ip) = &v.private_ip {
                    println!("  Private IP:         {}", ip);
                }
                println!();
            }
        }

        // ── Code (VS Code Remote-SSH) ────────────────────────────────
        azlin_cli::Commands::Code {
            vm_identifier,
            resource_group,
            auth_profile: _,
            user: _user,
            key,
            no_extensions: _no_extensions,
            workspace,
            ..
        } => {
            let name = vm_identifier;

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = penguin_spinner(&format!("Looking up {}...", name));
            let vm = vm_manager.get_vm(&rg, &name)?;
            pb.finish_and_clear();

            let user = vm
                .admin_username
                .clone()
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
            let use_bastion = vm.public_ip.is_none();

            let (ssh_host, _tunnel) = if use_bastion {
                // Route through Azure Bastion. The tunnel must OUTLIVE this
                // short-lived `azlin code` process so VS Code Remote-SSH can make
                // its multiple long-lived connections (issue #1063). We therefore
                // reuse a live tunnel-host if one exists, otherwise spawn a fully
                // DETACHED `azlin __tunnel-host` that owns the native tunnel.
                let bastion_map: std::collections::HashMap<String, String> =
                    crate::list_helpers::detect_bastion_hosts(&rg)
                        .unwrap_or_default()
                        .into_iter()
                        .map(|(n, l, _)| (l, n))
                        .collect();
                let bastion_name = bastion_map.get(&vm.location).ok_or_else(|| {
                    anyhow::anyhow!(
                        "No bastion host found for region '{}'. Cannot connect to private VM.",
                        vm.location
                    )
                })?;
                let vm_rid = format!(
                    "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                    vm_manager.subscription_id(), rg, name
                );

                let local_port =
                    if let Some(port) = crate::bastion_tunnel::existing_live_tunnel_port(&vm_rid) {
                        port
                    } else {
                        let pb = penguin_spinner("Starting persistent bastion tunnel...");
                        let child_pid = crate::bastion_tunnel::spawn_detached_tunnel_host(
                            bastion_name,
                            &rg,
                            &vm_rid,
                        )?;
                        // Wait until the detached host has the loopback listener up.
                        // Bounded by config (setup + connect timeouts) — never an
                        // arbitrary constant — so slow ARM/WSS setups are tolerated.
                        let config = crate::dispatch_helpers::load_user_config();
                        let wait_timeout = std::time::Duration::from_secs(
                            config.bastion_tunnel_timeout + config.bastion_connect_timeout,
                        );
                        let result = crate::bastion_tunnel::wait_for_host_tunnel(
                            &vm_rid,
                            child_pid,
                            wait_timeout,
                        );
                        pb.finish_and_clear();
                        result?
                    };

                // Write SSH config entries so VS Code Remote-SSH can connect
                let ssh_key = key.or_else(resolve_ssh_key);
                write_ssh_config_entry(&name, &user, local_port, ssh_key.as_deref())?;

                let host_alias = format!("azlin-{}", name);
                println!(
                    "Bastion tunnel active: 127.0.0.1:{} → {} ({})",
                    local_port, name, vm.location
                );
                (host_alias, None::<()>)
            } else {
                let ip = vm.public_ip.as_deref().unwrap();
                (ip.to_string(), None)
            };

            // VS Code Remote-SSH URI: vscode-remote://ssh-remote+<host>/<folder>
            // The <host> must match an SSH config Host entry (bastion) or be an IP (direct).
            let folder_uri = format!(
                "vscode-remote://ssh-remote+{}/{}",
                ssh_host,
                workspace.trim_start_matches('/')
            );
            println!("Opening VS Code: code --folder-uri {}", folder_uri);
            let status = std::process::Command::new("code")
                .args(["--folder-uri", &folder_uri])
                .status();

            match status {
                Ok(s) if s.success() => println!("VS Code opened for VM '{}'", name),
                _ => {
                    anyhow::bail!("Failed to open VS Code. Ensure 'code' is in your PATH.");
                }
            }
        }

        // ── Batch ────────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}

// ── SSH config upsert tests ──────────────────────────────────────────
//
// Every test here works inside a tempdir. Nothing in this module may touch the
// real $HOME or the real ~/.ssh — see #1079, where tests corrupted a
// developer's own SSH config.
#[cfg(test)]
mod ssh_config_tests {
    use super::*;

    /// The shape azlin writes for one host block (leading blank line, marker
    /// comment, then the block itself).
    fn azlin_block(alias: &str, port: u16) -> String {
        format!(
            "\n# Added by azlin\nHost {}\n    HostName 127.0.0.1\n    Port {}\n    User azureuser\n",
            alias, port
        )
    }

    fn backup_path(config: &std::path::Path) -> std::path::PathBuf {
        config.with_file_name("config.azlin.bak")
    }

    // ── Problem 1: unreadable config must never be treated as empty ──

    #[test]
    fn upsert_refuses_when_existing_config_is_not_utf8() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        // A comment with a Latin-1 byte — legal in an SSH config, rejected by
        // read_to_string — plus a host entry the user cannot afford to lose.
        let original: Vec<u8> =
            b"# caf\xE9 bastion\nHost prod-db\n    HostName 10.0.0.1\n".to_vec();
        std::fs::write(&path, &original).unwrap();

        let err = upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222))
            .expect_err("non-UTF-8 config must be refused, not silently truncated");

        assert!(
            err.to_string().contains("refusing to rewrite"),
            "unexpected error: {err}"
        );
        assert_eq!(
            std::fs::read(&path).unwrap(),
            original,
            "the config must be left byte-identical"
        );
    }

    #[cfg(unix)]
    #[test]
    fn upsert_refuses_when_existing_config_is_unreadable() {
        use std::os::unix::fs::PermissionsExt;

        // root ignores mode bits, so the read would succeed and prove nothing.
        if unsafe { libc::geteuid() } == 0 {
            return;
        }

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        let original = "Host prod-db\n    HostName 10.0.0.1\n";
        std::fs::write(&path, original).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o000)).unwrap();

        let result = upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222));

        // Restore before asserting so the tempdir can always be cleaned up.
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();

        let err = result.expect_err("permission-denied config must be refused");
        assert!(
            err.to_string().contains("refusing to rewrite"),
            "unexpected error: {err}"
        );
        assert_eq!(std::fs::read_to_string(&path).unwrap(), original);
    }

    #[test]
    fn upsert_creates_config_when_absent() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        assert!(!path.exists());

        upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222)).unwrap();

        let written = std::fs::read_to_string(&path).unwrap();
        assert!(written.contains("\nHost azlin-dev\n"), "{written}");
        assert!(written.contains("    Port 2222\n"), "{written}");
        assert!(
            !backup_path(&path).exists(),
            "nothing to back up when the file did not exist"
        );
    }

    #[test]
    fn upsert_preserves_other_hosts_and_writes_a_backup() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        let original = "Host prod-db\n    HostName 10.0.0.1\n\nHost git\n    HostName github.com\n";
        std::fs::write(&path, original).unwrap();

        upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222)).unwrap();

        let written = std::fs::read_to_string(&path).unwrap();
        assert!(written.contains("Host prod-db"), "{written}");
        assert!(written.contains("Host git"), "{written}");
        assert!(written.contains("Host azlin-dev"), "{written}");
        assert_eq!(
            std::fs::read_to_string(backup_path(&path)).unwrap(),
            original,
            "the pre-modification config must be preserved alongside"
        );
    }

    // ── Problem 2: `azlin-dev` must not match `azlin-dev-2` ──────────

    #[test]
    fn upsert_azlin_dev_does_not_touch_azlin_dev_2() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        let sibling = azlin_block("azlin-dev-2", 3333);
        std::fs::write(&path, &sibling).unwrap();

        upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222)).unwrap();

        let written = std::fs::read_to_string(&path).unwrap();
        assert!(
            written.contains(&sibling),
            "azlin-dev-2's block was rewritten by an azlin-dev upsert:\n{written}"
        );
        assert!(written.contains("\nHost azlin-dev\n"), "{written}");
        assert!(written.contains("    Port 2222\n"), "{written}");
        assert!(
            written.contains("    Port 3333\n"),
            "azlin-dev-2 must keep its own tunnel port:\n{written}"
        );
    }

    #[test]
    fn upsert_replaces_only_the_matching_pool_member() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        let sibling = azlin_block("azlin-pool-2", 3333);
        let original = format!("{}{}", azlin_block("azlin-pool-1", 2222), sibling);
        std::fs::write(&path, &original).unwrap();

        upsert_ssh_host_block(&path, "azlin-pool-1", &azlin_block("azlin-pool-1", 4444)).unwrap();

        let written = std::fs::read_to_string(&path).unwrap();
        assert!(written.contains(&sibling), "{written}");
        assert!(written.contains("    Port 4444\n"), "{written}");
        assert!(!written.contains("    Port 2222\n"), "{written}");
        assert_eq!(
            written.matches("Host azlin-pool-1\n").count(),
            1,
            "the block must be replaced, not duplicated:\n{written}"
        );
    }

    #[test]
    fn upsert_replaces_in_place_and_keeps_following_hosts() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        let original = format!(
            "Host prod-db\n    HostName 10.0.0.1\n{}Host git\n    HostName github.com\n",
            azlin_block("azlin-dev", 2222)
        );
        std::fs::write(&path, &original).unwrap();

        upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 9999)).unwrap();

        let written = std::fs::read_to_string(&path).unwrap();
        assert!(written.contains("Host prod-db"), "{written}");
        assert!(
            written.contains("Host git\n    HostName github.com"),
            "{written}"
        );
        assert!(written.contains("    Port 9999\n"), "{written}");
        assert!(!written.contains("    Port 2222\n"), "{written}");
    }

    #[test]
    fn upsert_is_idempotent() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        std::fs::write(&path, "Host prod-db\n    HostName 10.0.0.1\n").unwrap();

        upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222)).unwrap();
        let once = std::fs::read_to_string(&path).unwrap();
        upsert_ssh_host_block(&path, "azlin-dev", &azlin_block("azlin-dev", 2222)).unwrap();
        let twice = std::fs::read_to_string(&path).unwrap();

        assert_eq!(once, twice, "re-upserting must not drift the file");
    }

    #[test]
    fn upsert_is_idempotent_when_the_block_is_first_in_the_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config");
        let original = format!(
            "{}{}",
            azlin_block("azlin-pool-1", 2222),
            azlin_block("azlin-pool-2", 3333)
        );
        std::fs::write(&path, &original).unwrap();

        upsert_ssh_host_block(&path, "azlin-pool-1", &azlin_block("azlin-pool-1", 2222)).unwrap();
        let once = std::fs::read_to_string(&path).unwrap();
        upsert_ssh_host_block(&path, "azlin-pool-1", &azlin_block("azlin-pool-1", 2222)).unwrap();
        let twice = std::fs::read_to_string(&path).unwrap();

        assert_eq!(once, original, "an unchanged block must not move the file");
        assert_eq!(once, twice);
    }

    #[test]
    fn host_line_matching_is_anchored_to_whole_tokens() {
        assert!(host_line_declares("Host azlin-dev", "azlin-dev"));
        assert!(host_line_declares("    Host azlin-dev\n", "azlin-dev"));
        assert!(host_line_declares("host azlin-dev\n", "azlin-dev"));
        assert!(host_line_declares("Host azlin-dev other\n", "azlin-dev"));

        assert!(!host_line_declares("Host azlin-dev-2\n", "azlin-dev"));
        assert!(!host_line_declares("HostName azlin-dev\n", "azlin-dev"));
        assert!(!host_line_declares(
            "    IdentityFile /k/azlin-dev\n",
            "azlin-dev"
        ));

        assert!(is_host_line("Host x\n"));
        assert!(!is_host_line("HostName x\n"));
        assert!(!is_host_line("    Port 22\n"));
    }

    // ── Problem 3: never guess somebody else's username ──────────────

    #[test]
    fn resolve_username_returns_none_when_environment_is_empty() {
        assert_eq!(resolve_username(|_| None, None), None);
    }

    #[test]
    fn resolve_username_prefers_user_and_trims() {
        let got = resolve_username(
            |var| (var == "USER").then(|| "  alice \n".to_string()),
            Some(std::path::PathBuf::from("/home/bob")),
        );
        assert_eq!(got.as_deref(), Some("alice"));
    }

    #[test]
    fn resolve_username_falls_back_through_logname_then_home() {
        let logname = resolve_username(|var| (var == "LOGNAME").then(|| "alice".to_string()), None);
        assert_eq!(logname.as_deref(), Some("alice"));

        let from_home = resolve_username(|_| None, Some(std::path::PathBuf::from("/home/alice")));
        assert_eq!(from_home.as_deref(), Some("alice"));
    }

    #[test]
    fn resolve_username_ignores_blank_values() {
        let got = resolve_username(|_| Some("   ".to_string()), None);
        assert_eq!(got, None);
    }
}
