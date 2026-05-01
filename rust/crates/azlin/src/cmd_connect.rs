#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) fn build_effective_remote_command(x11: bool, remote_command: &[String]) -> Vec<String> {
    crate::gui_launch_helpers::maybe_wrap_x11_remote_command(x11, remote_command)
        .unwrap_or_else(|| remote_command.to_vec())
}

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Connect {
            vm_identifier,
            resource_group,
            user,
            key,
            no_tmux,
            tmux_session,
            no_reconnect,
            max_retries,
            yes,
            x11,
            no_status,
            remote_command,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            // Parse compound identifier: "vm:session" → (vm_name, Some(session))
            let (raw_name, colon_session) = if let Some(ref id) = vm_identifier {
                if let Some((vm_part, sess_part)) = id.split_once(':') {
                    (Some(vm_part.to_string()), Some(sess_part.to_string()))
                } else {
                    (Some(id.clone()), None)
                }
            } else {
                (None, None)
            };

            // If no VM specified, show interactive picker of running VMs
            let name = if let Some(n) = raw_name {
                n
            } else {
                let vms = vm_manager.list_vms(&rg)?;
                let running: Vec<_> = vms
                    .iter()
                    .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
                    .collect();
                if running.is_empty() {
                    anyhow::bail!("No running VMs found in resource group '{}'", rg);
                }
                println!("Select a VM to connect to:");
                for (i, vm) in running.iter().enumerate() {
                    let ip = vm
                        .public_ip
                        .as_deref()
                        .or(vm.private_ip.as_deref())
                        .unwrap_or("-");
                    println!("  [{}] {} ({})", i + 1, vm.name, ip);
                }
                print!("> ");
                use std::io::Write;
                std::io::stdout().flush()?;
                let mut input = String::new();
                std::io::stdin().read_line(&mut input)?;
                let idx: usize = input
                    .trim()
                    .parse::<usize>()
                    .context("Invalid selection")?
                    .checked_sub(1)
                    .context("Selection out of range")?;
                if idx >= running.len() {
                    anyhow::bail!("Selection out of range");
                }
                running[idx].name.clone()
            };

            let pb = penguin_spinner(&format!("Looking up {}...", name));
            let vm = vm_manager.get_vm(&rg, &name)?;
            pb.finish_and_clear();

            let username = vm.admin_username.unwrap_or_else(|| user.clone());
            let use_bastion = vm.public_ip.is_none();

            // Display SSH status bar unless disabled
            if !no_status {
                let ip_display = vm
                    .public_ip
                    .as_deref()
                    .or(vm.private_ip.as_deref())
                    .unwrap_or("-")
                    .to_string();
                crate::ssh_status::display_ssh_status(&crate::ssh_status::SshConnectionInfo {
                    vm_name: name.clone(),
                    ip: ip_display,
                    user: username.clone(),
                    via_bastion: use_bastion,
                });
            }

            // Build the remote command (with optional tmux wrapping)
            // Priority: --tmux-session flag > colon notation (vm:session) > default "azlin"
            let tmux_sess = if !no_tmux {
                let sess = tmux_session
                    .as_deref()
                    .or(colon_session.as_deref())
                    .unwrap_or("azlin");
                if !sess
                    .chars()
                    .all(|c| c.is_alphanumeric() || c == '_' || c == '-')
                {
                    anyhow::bail!(
                        "Invalid tmux session name: must be alphanumeric, underscore, or hyphen"
                    );
                }
                Some(sess.to_string())
            } else {
                None
            };

            // X11 forwarding: verify local X server is available
            if x11 {
                let display_set = std::env::var("DISPLAY")
                    .map(|d| !d.is_empty())
                    .unwrap_or(false);
                let x_socket_exists = std::path::Path::new("/tmp/.X11-unix/X0").exists();
                if !display_set && !x_socket_exists {
                    eprintln!("Warning: X11 forwarding requires a local X server.");
                    eprintln!("  On WSL2, ensure WSLg is enabled (restart WSL if needed).");
                    eprintln!("  Set DISPLAY env var or verify /tmp/.X11-unix/X0 exists.");
                }
            }

            let effective_remote_command = build_effective_remote_command(x11, &remote_command);

            let mut attempt = 0u32;
            let max = if no_reconnect { 1 } else { max_retries + 1 };
            loop {
                let status = if use_bastion {
                    // Route through Azure Bastion for private-only VMs
                    let bastion_map: std::collections::HashMap<String, String> =
                        if let Ok(bastions) = crate::list_helpers::detect_bastion_hosts(&rg) {
                            bastions.into_iter().map(|(n, l, _)| (l, n)).collect()
                        } else {
                            std::collections::HashMap::new()
                        };
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
                    // Ensure an SSH key exists; auto-generate if missing.
                    let (ssh_key, newly_generated_pubkey) = if let Some(k) = key.clone() {
                        (Some(k), None)
                    } else {
                        match crate::key_helpers::ensure_ssh_keypair() {
                            Ok(kp) => {
                                let gen_pub = if kp.generated {
                                    Some(kp.public_key.clone())
                                } else {
                                    None
                                };
                                (Some(kp.private_key), gen_pub)
                            }
                            Err(e) => {
                                eprintln!("Warning: {e}");
                                (None, None)
                            }
                        }
                    };

                    // If we just generated a new key, push it to the VM before connecting.
                    if let Some(ref pub_path) = newly_generated_pubkey {
                        if let Ok(pub_key) = std::fs::read_to_string(pub_path) {
                            eprintln!(
                                "Pushing new SSH key to {}...",
                                name
                            );
                            let sync_status = std::process::Command::new("az")
                                .args([
                                    "vm",
                                    "user",
                                    "update",
                                    "--resource-group",
                                    &rg,
                                    "--name",
                                    &name,
                                    "--username",
                                    &username,
                                    "--ssh-key-value",
                                    pub_key.trim(),
                                ])
                                .stdout(std::process::Stdio::null())
                                .stderr(std::process::Stdio::piped())
                                .status();
                            match sync_status {
                                Ok(s) if s.success() => {
                                    eprintln!("SSH key pushed successfully.");
                                }
                                _ => {
                                    anyhow::bail!(
                                        "Failed to push SSH key to {}. Run: az vm user update --resource-group {} --name {} --username {} --ssh-key-value \"$(cat {})\"",
                                        name, rg, name, username, pub_path.display()
                                    );
                                }
                            }
                        }
                    }
                    let mut args = vec![
                        "network".to_string(),
                        "bastion".to_string(),
                        "ssh".to_string(),
                        "--name".to_string(),
                        bastion_name.clone(),
                        "--resource-group".to_string(),
                        rg.clone(),
                        "--target-resource-id".to_string(),
                        vm_rid,
                        "--auth-type".to_string(),
                        "ssh-key".to_string(),
                        "--username".to_string(),
                        username.clone(),
                    ];
                    if let Some(ref k) = ssh_key {
                        args.push("--ssh-key".to_string());
                        args.push(k.to_string_lossy().to_string());
                    }
                    args.push("--".to_string());
                    // Enable X11 forwarding through bastion
                    if x11 {
                        args.push("-Y".to_string());
                    }
                    // Force TTY allocation for interactive sessions (tmux needs it)
                    if tmux_sess.is_some() || effective_remote_command.is_empty() {
                        args.push("-t".to_string());
                    }
                    // Build the remote command
                    if let Some(ref sess) = tmux_sess {
                        if effective_remote_command.is_empty() {
                            args.push(format!("tmux new-session -A -s {}", sess));
                        } else {
                            args.extend(effective_remote_command.iter().cloned());
                        }
                    } else if !effective_remote_command.is_empty() {
                        args.extend(effective_remote_command.iter().cloned());
                    }
                    let str_args: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
                    std::process::Command::new("az").args(&str_args).status()?
                } else {
                    // Direct SSH for VMs with public IPs
                    let ip = vm.public_ip.as_deref().unwrap();
                    let resolved_key = key.clone().or_else(resolve_ssh_key);
                    let mut ssh_args = crate::connect_helpers::build_ssh_args(
                        &username,
                        ip,
                        resolved_key.as_deref(),
                    );
                    // Enable X11 forwarding for direct SSH
                    if x11 {
                        // Insert -Y before the user@host argument (last element)
                        let user_host = ssh_args.pop().unwrap();
                        ssh_args.push("-Y".to_string());
                        ssh_args.push(user_host);
                    }
                    if let Some(ref sess) = tmux_sess {
                        if effective_remote_command.is_empty() {
                            ssh_args.push("-t".to_string());
                            ssh_args.push(format!("tmux new-session -A -s {}", sess));
                        } else {
                            ssh_args.extend(effective_remote_command.iter().cloned());
                        }
                    } else if !effective_remote_command.is_empty() {
                        ssh_args.extend(effective_remote_command.iter().cloned());
                    }
                    std::process::Command::new("ssh").args(&ssh_args).status()?
                };
                attempt += 1;
                if status.success() || attempt >= max {
                    if !no_status {
                        crate::ssh_status::clear_ssh_status();
                    }
                    std::process::exit(status.code().unwrap_or(1));
                }
                if !yes {
                    eprint!(
                        "SSH disconnected. Reconnect? (attempt {}/{}) [Y/n] ",
                        attempt,
                        max - 1
                    );
                    let mut input = String::new();
                    std::io::stdin().read_line(&mut input)?;
                    if input.trim().eq_ignore_ascii_case("n") {
                        if !no_status {
                            crate::ssh_status::clear_ssh_status();
                        }
                        std::process::exit(status.code().unwrap_or(1));
                    }
                } else {
                    eprintln!(
                        "SSH disconnected. Reconnecting (attempt {}/{})...",
                        attempt,
                        max - 1
                    );
                }
                std::thread::sleep(std::time::Duration::from_secs(2));
            }
        }
        azlin_cli::Commands::Show {
            name,
            resource_group,
            config: _,
            output,
            verbose: _,
            auth_profile: _,
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = penguin_spinner(&format!("Fetching {}...", name));
            let vm = crate::handlers::handle_show(&vm_manager, &rg, &name)?;
            pb.finish_and_clear();

            match output {
                azlin_cli::OutputFormat::Json => {
                    println!("{}", crate::handlers::format_show_json(&vm)?);
                }
                azlin_cli::OutputFormat::Csv => {
                    print!("{}", crate::handlers::format_show_csv(&vm));
                }
                azlin_cli::OutputFormat::Table => {
                    print!("{}", crate::handlers::format_show_table(&vm));
                }
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
