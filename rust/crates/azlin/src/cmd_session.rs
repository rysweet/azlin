#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use console::Style;

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
            let mut json = serde_json::to_value(&config)?;

            let sessions_key = "sessions";
            if clear {
                if let Some(obj) = json.as_object_mut() {
                    if let Some(sessions) = obj.get_mut(sessions_key) {
                        if let Some(s) = sessions.as_object_mut() {
                            s.remove(&vm_name);
                        }
                    }
                }
                config = serde_json::from_value(json)?;
                config.save()?;
                println!("Cleared session name for VM '{}'", vm_name);
            } else if let Some(name) = session_name {
                if let Some(obj) = json.as_object_mut() {
                    let sessions = obj
                        .entry(sessions_key)
                        .or_insert_with(|| serde_json::json!({}));
                    if let Some(s) = sessions.as_object_mut() {
                        s.insert(vm_name.clone(), serde_json::json!(name));
                    }
                }
                config = serde_json::from_value(json)?;
                config.save()?;
                println!("Set session for VM '{}' = '{}'", vm_name, name);
            } else {
                let session = json
                    .get(sessions_key)
                    .and_then(|s| s.get(&vm_name))
                    .and_then(|v| v.as_str());
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
            ..
        } => {
            let name = vm_identifier.ok_or_else(|| anyhow::anyhow!("VM name is required."))?;

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = penguin_spinner(&format!("Looking up {}...", name));
            let vm = vm_manager.get_vm(&rg, &name)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

            let remote_uri = format!("ssh-remote+{}@{}", user, ip);
            println!("Opening VS Code: code --remote {}", remote_uri);
            let status = std::process::Command::new("code")
                .args(["--remote", &remote_uri])
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
