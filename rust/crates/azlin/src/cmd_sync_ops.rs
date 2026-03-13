#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn handle_sync(
    vm_name: Option<String>,
    dry_run: bool,
    resource_group: Option<String>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group.clone())?;
    let home_sync_dir = home_dir()?.join(".azlin").join("home");

    if !home_sync_dir.exists() {
        anyhow::bail!("No ~/.azlin/home/ directory found. Nothing to sync.");
    }

    let target_vm = vm_name;
    if dry_run {
        let target_name = target_vm.as_deref().unwrap_or("all VMs");
        println!(
            "{}",
            crate::sync_helpers::format_sync_dry_run(
                &home_sync_dir.display().to_string(),
                target_name,
                &rg,
            )
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

        let dotfiles: Vec<String> = std::fs::read_dir(&home_sync_dir)?
            .filter_map(|e| e.ok())
            .map(|e| e.path().display().to_string())
            .collect();

        if dotfiles.is_empty() {
            println!("No files found in {}", home_sync_dir.display());
            return Ok(());
        }

        for vm in &running_vms {
            let target =
                resolve_vm_ssh_target(&vm.name, None, resource_group.clone()).await?;
            println!("Syncing dotfiles to {}...", vm.name);

            let status = if let Some(ref bastion) = target.bastion {
                // Route rsync through bastion tunnel
                let tunnel = crate::bastion_tunnel::ScopedBastionTunnel::new(
                    &bastion.bastion_name,
                    &bastion.resource_group,
                    &bastion.vm_resource_id,
                )?;
                let ssh_cmd = format!(
                    "ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -p {}",
                    tunnel.local_port
                );
                let dest = format!("{}@127.0.0.1:~/", target.user);
                let mut args: Vec<&str> = vec!["-avz", "--progress", "-e", &ssh_cmd];
                for f in &dotfiles {
                    args.push(f.as_str());
                }
                args.push(&dest);
                std::process::Command::new("rsync").args(&args).status()?
            } else {
                let (mut args, dest) =
                    crate::sync_helpers::build_sync_rsync_args(&dotfiles, &target.user, &target.ip);
                args.push(&dest);
                std::process::Command::new("rsync").args(&args).status()?
            };

            if status.success() {
                println!("  {} synced", vm.name);
            } else {
                eprintln!("  {} sync failed", vm.name);
            }
        }
        println!("Sync complete.");
    }
    Ok(())
}

pub(crate) fn handle_sync_keys(
    vm_name: &str,
    resource_group: Option<String>,
    ssh_user: &str,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let ssh_dir = home_dir()?.join(".ssh");

    let pub_key = crate::key_helpers::find_preferred_pubkey(&ssh_dir);

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
                    vm_name,
                    "--username",
                    ssh_user,
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
    Ok(())
}

pub(crate) async fn handle_cp(
    args: &[String],
    dry_run: bool,
    resource_group: Option<String>,
) -> Result<()> {
    if args.len() < 2 {
        eprintln!("Usage: azlin cp <source> <destination>");
        anyhow::bail!("Use vm_name:path for remote paths.");
    }

    let source = &args[0];
    let dest = &args[args.len() - 1];
    let rg = resolve_resource_group(resource_group.clone())?;

    let direction = crate::cp_helpers::classify_transfer_direction(source, dest);

    if dry_run {
        println!(
            "Would copy ({}) {} -> {} (rg: {})",
            direction, source, dest, rg
        );
    } else {
        let config = azlin_core::AzlinConfig::load().unwrap_or_default();
        println!("Copying ({}) {} -> {}...", direction, source, dest);
        if crate::cp_helpers::is_remote_path(source) || crate::cp_helpers::is_remote_path(dest) {
            let (vm_part, _path_part) = if crate::cp_helpers::is_remote_path(source) {
                source
                    .split_once(':')
                    .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", source))?
            } else {
                dest.split_once(':')
                    .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", dest))?
            };

            let target = resolve_vm_ssh_target(vm_part, None, resource_group).await?;
            let timeout_val = format!("ConnectTimeout={}", config.ssh_connect_timeout);

            // Route through bastion tunnel if VM has no public IP
            let status = if let Some(ref bastion) = target.bastion {
                let tunnel = crate::bastion_tunnel::ScopedBastionTunnel::new(
                    &bastion.bastion_name,
                    &bastion.resource_group,
                    &bastion.vm_resource_id,
                )?;
                let port_str = tunnel.local_port.to_string();

                let scp_source = if crate::cp_helpers::is_remote_path(source) {
                    let remote_path = source.split_once(':').unwrap().1;
                    format!("{}@127.0.0.1:{}", target.user, remote_path)
                } else {
                    source.clone()
                };
                let scp_dest = if crate::cp_helpers::is_remote_path(dest) {
                    let remote_path = dest.split_once(':').unwrap().1;
                    format!("{}@127.0.0.1:{}", target.user, remote_path)
                } else {
                    dest.clone()
                };

                let mut scp_args = vec![
                    "-o".to_string(), "StrictHostKeyChecking=accept-new".to_string(),
                    "-o".to_string(), timeout_val.clone(),
                    "-o".to_string(), "BatchMode=yes".to_string(),
                    "-P".to_string(), port_str,
                ];
                if let Some(ref key) = bastion.ssh_key_path {
                    scp_args.push("-i".to_string());
                    scp_args.push(key.to_string_lossy().to_string());
                }
                scp_args.push(scp_source);
                scp_args.push(scp_dest);
                std::process::Command::new("scp")
                    .args(&scp_args)
                    .status()?
            } else {
                let scp_source = if crate::cp_helpers::is_remote_path(source) {
                    crate::cp_helpers::resolve_scp_path(source, vm_part, &target.user, &target.ip)
                } else {
                    source.clone()
                };
                let scp_dest = if crate::cp_helpers::is_remote_path(dest) {
                    crate::cp_helpers::resolve_scp_path(dest, vm_part, &target.user, &target.ip)
                } else {
                    dest.clone()
                };

                std::process::Command::new("scp")
                    .args([
                        "-o", "StrictHostKeyChecking=accept-new",
                        "-o", &timeout_val,
                        "-o", "BatchMode=yes",
                        &scp_source,
                        &scp_dest,
                    ])
                    .status()?
            };

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
    Ok(())
}

pub(crate) async fn handle_logs(
    vm_identifier: &str,
    lines: u32,
    follow: bool,
    log_type: azlin_cli::LogType,
    resource_group: Option<String>,
) -> Result<()> {
    let log_path = match log_type {
        azlin_cli::LogType::CloudInit => "/var/log/cloud-init-output.log",
        azlin_cli::LogType::Syslog => "/var/log/syslog",
        azlin_cli::LogType::Auth => "/var/log/auth.log",
    };

    let config = azlin_core::AzlinConfig::load().unwrap_or_default();
    let target = resolve_vm_ssh_target(vm_identifier, None, resource_group).await?;

    if follow {
        println!("Following {} on {}...", log_path, vm_identifier);
        if let Some(ref b) = target.bastion {
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
            let follow_args =
                crate::connect_helpers::build_log_follow_args(&target.user, &target.ip, log_path, config.ssh_connect_timeout);
            let status = std::process::Command::new("ssh")
                .args(&follow_args)
                .status()?;
            if !status.success() {
                std::process::exit(status.code().unwrap_or(1));
            }
        }
    } else {
        let pb = penguin_spinner(&format!(
            "Fetching {:?} logs for {}...",
            log_type, vm_identifier
        ));

        let tail_cmd = crate::sync_helpers::build_tail_command(lines, log_path);
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
    Ok(())
}
