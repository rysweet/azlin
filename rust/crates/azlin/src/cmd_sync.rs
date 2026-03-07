#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Sync {
            vm_name,
            dry_run,
            resource_group,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            let home_dir = home_dir()?.join(".azlin").join("home");

            if !home_dir.exists() {
                anyhow::bail!("No ~/.azlin/home/ directory found. Nothing to sync.");
            }

            let target_vm = vm_name;
            if dry_run {
                let target_name = target_vm.as_deref().unwrap_or("all VMs");
                println!(
                    "Would sync {} to {} in '{}'",
                    home_dir.display(),
                    target_name,
                    rg
                );
            } else {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let vms = vm_manager.list_vms(&rg)?;
                let running_vms: Vec<_> = vms
                    .iter()
                    .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
                    .filter(|v| target_vm.as_ref().is_none_or(|t| &v.name == t))
                    .collect();

                if running_vms.is_empty() {
                    println!("No running VMs found to sync in '{}'", rg);
                    return Ok(());
                }

                // Collect dotfiles from ~/.azlin/home/
                let dotfiles: Vec<String> = std::fs::read_dir(&home_dir)?
                    .filter_map(|e| e.ok())
                    .map(|e| e.path().display().to_string())
                    .collect();

                if dotfiles.is_empty() {
                    println!("No files found in {}", home_dir.display());
                    return Ok(());
                }

                for vm in &running_vms {
                    if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        println!("Syncing dotfiles to {}...", vm.name);
                        let mut args: Vec<&str> = vec!["-avz", "--progress"];
                        let file_refs: Vec<&str> = dotfiles.iter().map(|s| s.as_str()).collect();
                        args.extend_from_slice(&file_refs);
                        let dest = format!("{}@{}:~/", user, ip);
                        args.push(&dest);
                        let status = std::process::Command::new("rsync").args(&args).status()?;
                        if status.success() {
                            println!("  ✓ {} synced", vm.name);
                        } else {
                            eprintln!("  ✗ {} sync failed", vm.name);
                        }
                    } else {
                        eprintln!("  ✗ {} has no IP address", vm.name);
                    }
                }
                println!("Sync complete.");
            }
        }

        // ── SyncKeys ────────────────────────────────────────────────
        azlin_cli::Commands::SyncKeys {
            vm_name,
            resource_group,
            ssh_user,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            let ssh_dir = home_dir()?.join(".ssh");

            let pub_key = ["id_ed25519_azlin.pub", "id_ed25519.pub", "id_rsa.pub"]
                .iter()
                .map(|f| ssh_dir.join(f))
                .find(|p| p.exists());

            match pub_key {
                Some(key_path) => {
                    let key_content = std::fs::read_to_string(&key_path)?;
                    let output = std::process::Command::new("az")
                        .args([
                            "vm",
                            "user",
                            "update",
                            "--resource-group",
                            &rg,
                            "--name",
                            &vm_name,
                            "--username",
                            &ssh_user,
                            "--ssh-key-value",
                            key_content.trim(),
                        ])
                        .output()?;
                    if output.status.success() {
                        println!("Synced SSH key to VM '{}' for user '{}'", vm_name, ssh_user);
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to sync keys: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                None => {
                    anyhow::bail!("No SSH public key found in {}", ssh_dir.display());
                }
            }
        }

        // ── Cp ───────────────────────────────────────────────────────
        azlin_cli::Commands::Cp {
            args,
            dry_run,
            resource_group,
            ..
        } => {
            if args.len() < 2 {
                eprintln!("Usage: azlin cp <source> <destination>");
                anyhow::bail!("Use vm_name:path for remote paths.");
            }

            let source = &args[0];
            let dest = &args[args.len() - 1];
            let rg = resolve_resource_group(resource_group)?;

            let direction = crate::cp_helpers::classify_transfer_direction(source, dest);

            if dry_run {
                println!(
                    "Would copy ({}) {} → {} (rg: {})",
                    direction, source, dest, rg
                );
            } else {
                println!("Copying ({}) {} → {}...", direction, source, dest);
                // For remote transfers, use scp via az CLI resolved IP
                if crate::cp_helpers::is_remote_path(source)
                    || crate::cp_helpers::is_remote_path(dest)
                {
                    let (vm_part, _path_part) = if crate::cp_helpers::is_remote_path(source) {
                        source
                            .split_once(':')
                            .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", source))?
                    } else {
                        dest.split_once(':')
                            .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", dest))?
                    };
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vm = vm_manager.get_vm(&rg, vm_part)?;
                    let ip = vm
                        .public_ip
                        .or(vm.private_ip)
                        .ok_or_else(|| anyhow::anyhow!("No IP for VM '{}'", vm_part))?;
                    let user = vm
                        .admin_username
                        .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

                    let scp_source = if crate::cp_helpers::is_remote_path(source) {
                        crate::cp_helpers::resolve_scp_path(source, vm_part, &user, &ip)
                    } else {
                        source.clone()
                    };
                    let scp_dest = if crate::cp_helpers::is_remote_path(dest) {
                        crate::cp_helpers::resolve_scp_path(dest, vm_part, &user, &ip)
                    } else {
                        dest.clone()
                    };

                    let status = std::process::Command::new("scp")
                        .args([
                            "-o",
                            "StrictHostKeyChecking=accept-new",
                            &scp_source,
                            &scp_dest,
                        ])
                        .status()?;
                    if status.success() {
                        println!("Copy complete.");
                    } else {
                        anyhow::bail!("scp failed.");
                    }
                } else {
                    std::fs::copy(source, dest)?;
                    println!("Copy complete.");
                }
            }
        }

        // ── Logs ─────────────────────────────────────────────────────
        azlin_cli::Commands::Logs {
            vm_identifier,
            lines,
            follow,
            log_type,
            resource_group,
            ..
        } => {
            // Map log types to file paths
            let log_path = match log_type {
                azlin_cli::LogType::CloudInit => "/var/log/cloud-init-output.log",
                azlin_cli::LogType::Syslog => "/var/log/syslog",
                azlin_cli::LogType::Auth => "/var/log/auth.log",
            };

            let target = resolve_vm_ssh_target(&vm_identifier, None, resource_group).await?;

            if follow {
                // Stream logs interactively
                println!("Following {} on {}...", log_path, vm_identifier);
                if let Some(ref b) = target.bastion {
                    // Interactive follow through bastion
                    let mut args = vec![
                        "network".to_string(),
                        "bastion".to_string(),
                        "ssh".to_string(),
                        "--name".to_string(),
                        b.bastion_name.clone(),
                        "--resource-group".to_string(),
                        b.resource_group.clone(),
                        "--target-resource-id".to_string(),
                        b.vm_resource_id.clone(),
                        "--auth-type".to_string(),
                        "ssh-key".to_string(),
                        "--username".to_string(),
                        target.user.clone(),
                    ];
                    if let Some(ref key) = b.ssh_key_path {
                        args.push("--ssh-key".to_string());
                        args.push(key.to_string_lossy().to_string());
                    }
                    args.push("--".to_string());
                    args.push(format!("sudo tail -f {}", log_path));
                    let status = std::process::Command::new("az").args(&args).status()?;
                    if !status.success() {
                        std::process::exit(status.code().unwrap_or(1));
                    }
                } else {
                    let follow_args = crate::connect_helpers::build_log_follow_args(
                        &target.user,
                        &target.ip,
                        log_path,
                    );
                    let status = std::process::Command::new("ssh")
                        .args(&follow_args)
                        .status()?;
                    if !status.success() {
                        std::process::exit(status.code().unwrap_or(1));
                    }
                }
            } else {
                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!(
                    "Fetching {:?} logs for {}...",
                    log_type, vm_identifier
                ));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let tail_cmd = format!("sudo tail -n {} {}", lines, log_path);
                let result = target.exec(&tail_cmd);

                pb.finish_and_clear();
                match result {
                    Ok((0, stdout, _stderr)) => {
                        print!("{}", stdout);
                    }
                    Ok((_, _, stderr)) => {
                        anyhow::bail!(
                            "Failed to fetch logs via SSH: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                    Err(e) => {
                        anyhow::bail!("Failed to fetch logs via SSH: {}", e);
                    }
                }
            }
        }

        // ── Costs (intelligence) ─────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
