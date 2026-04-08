#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use console::Style;

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
    let win_ssh_dir = std::path::Path::new("/mnt/c/Users")
        .join(std::env::var("USER").unwrap_or_else(|_| "rysweet".to_string()))
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

/// Replace an existing `Host <alias>` block in an SSH config, or append if absent.
fn upsert_ssh_host_block(
    config_path: &std::path::Path,
    host_alias: &str,
    new_block: &str,
) -> Result<()> {
    let existing = std::fs::read_to_string(config_path).unwrap_or_default();
    let marker = format!("Host {}", host_alias);

    if let Some(start) = existing.find(&marker) {
        // Find the end of this host block (next "Host " line or EOF)
        let rest = &existing[start + marker.len()..];
        let block_end = rest
            .find("\nHost ")
            .or_else(|| rest.find("\n# Added by azlin\nHost "))
            .map(|pos| start + marker.len() + pos)
            .unwrap_or(existing.len());

        // Find start of the comment line above if present
        let comment_prefix = "# Added by azlin\n";
        let block_start = if start >= comment_prefix.len()
            && existing[start - comment_prefix.len()..start] == *comment_prefix
        {
            start - comment_prefix.len()
        } else {
            start
        };

        let mut updated = String::with_capacity(existing.len());
        updated.push_str(&existing[..block_start]);
        updated.push_str(new_block);
        updated.push_str(&existing[block_end..]);
        std::fs::write(config_path, updated)?;
    } else {
        // Append new block
        let mut content = existing;
        content.push_str(new_block);
        std::fs::write(config_path, content)?;
    }
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
                // Route through Azure Bastion — create/reuse a persistent tunnel
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
                let tunnel = crate::bastion_tunnel::ScopedBastionTunnel::new(
                    bastion_name, &rg, &vm_rid,
                )?;
                let local_port = tunnel.local_port;

                // Write SSH config entries so VS Code Remote-SSH can connect
                let ssh_key = key.or_else(resolve_ssh_key);
                write_ssh_config_entry(
                    &name, &user, local_port, ssh_key.as_deref(),
                )?;

                let host_alias = format!("azlin-{}", name);
                println!(
                    "Bastion tunnel active: 127.0.0.1:{} → {} ({})",
                    local_port, name, vm.location
                );
                (host_alias, Some(tunnel))
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
