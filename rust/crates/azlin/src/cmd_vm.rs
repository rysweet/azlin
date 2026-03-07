#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use console::Style;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::New {
            repo,
            vm_size,
            region,
            resource_group,
            name,
            pool,
            no_auto_connect,
            template,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let vm_count = pool.unwrap_or(1);
            // Use config defaults instead of hardcoded values
            let config_defaults = azlin_core::AzlinConfig::load().unwrap_or_default();
            let user_specified_size = vm_size.is_some();
            let user_specified_region = region.is_some();
            let size = vm_size.unwrap_or_else(|| config_defaults.default_vm_size.clone());
            let loc = region.unwrap_or_else(|| config_defaults.default_region.clone());
            let admin_user = DEFAULT_ADMIN_USERNAME.to_string();
            let ssh_key_path = {
                let ssh_dir = dirs::home_dir().unwrap_or_default().join(".ssh");
                // Same fallback order as resolve_ssh_key: azlin_key > id_rsa
                [
                    "azlin_key.pub",
                    "id_ed25519_azlin.pub",
                    "id_ed25519.pub",
                    "id_rsa.pub",
                ]
                .iter()
                .map(|f| ssh_dir.join(f))
                .find(|p| p.exists())
                .unwrap_or_else(|| ssh_dir.join("id_rsa.pub"))
            };

            // Load template defaults if specified
            let (tmpl_size, tmpl_region) = if let Some(ref tmpl_name) = template {
                if let Err(e) = crate::name_validation::validate_name(tmpl_name) {
                    anyhow::bail!("Invalid template name: {}", e);
                }
                let templates_dir = dirs::home_dir()
                    .unwrap_or_default()
                    .join(".config")
                    .join("azlin")
                    .join("templates");
                let tmpl_path = templates_dir.join(format!("{}.toml", tmpl_name));
                if tmpl_path.exists() {
                    let content = std::fs::read_to_string(&tmpl_path)?;
                    let tmpl: toml::Value = content.parse()?;
                    let ts = tmpl
                        .get("vm_size")
                        .and_then(|v| v.as_str())
                        .map(String::from);
                    let tr = tmpl
                        .get("region")
                        .and_then(|v| v.as_str())
                        .map(String::from);
                    (ts, tr)
                } else {
                    eprintln!(
                        "Template '{}' not found at {}",
                        tmpl_name,
                        tmpl_path.display()
                    );
                    (None, None)
                }
            } else {
                (None, None)
            };

            // If the user didn't specify --vm-size or --region explicitly (i.e.,
            // they're still the config defaults), allow the template to override.
            let final_size = if !user_specified_size {
                tmpl_size.unwrap_or(size)
            } else {
                size
            };
            let final_loc = if !user_specified_region {
                tmpl_region.unwrap_or(loc)
            } else {
                loc
            };

            for i in 0..vm_count {
                let vm_name = if let Some(ref n) = name {
                    if vm_count > 1 {
                        format!("{}-{}", n, i + 1)
                    } else {
                        n.clone()
                    }
                } else {
                    format!("azlin-vm-{}", chrono::Utc::now().format("%Y%m%d-%H%M%S"))
                };

                azlin_core::models::validate_vm_name(&vm_name).map_err(|e| anyhow::anyhow!(e))?;

                let params = azlin_core::models::CreateVmParams {
                    name: vm_name.clone(),
                    resource_group: rg.clone(),
                    region: final_loc.clone(),
                    vm_size: final_size.clone(),
                    admin_username: admin_user.clone(),
                    ssh_key_path: ssh_key_path.clone(),
                    image: azlin_core::models::VmImage::default(),
                    tags: std::collections::HashMap::new(),
                };

                if let Err(e) = params.validate() {
                    anyhow::bail!("Invalid VM parameters: {}", e);
                }

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Creating VM '{}'...", vm_name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm = vm_manager.create_vm(&params)?;
                pb.finish_and_clear();

                println!("VM '{}' created successfully!", vm.name);

                let mut table = Table::new();
                table
                    .load_preset(UTF8_FULL)
                    .apply_modifier(UTF8_ROUND_CORNERS);
                table.set_header(vec!["Property", "Value"]);
                table.add_row(vec!["Name", &vm.name]);
                table.add_row(vec!["Resource Group", &rg]);
                table.add_row(vec!["Size", &final_size]);
                table.add_row(vec!["Region", &final_loc]);
                table.add_row(vec!["State", &vm.power_state.to_string()]);
                if let Some(ref ip) = vm.public_ip {
                    table.add_row(vec!["Public IP", ip]);
                }
                if let Some(ref ip) = vm.private_ip {
                    table.add_row(vec!["Private IP", ip]);
                }
                println!("{table}");

                // Clone repo if specified
                if let Some(ref repo_url) = repo {
                    if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                        let clone_cmd = match crate::create_helpers::build_clone_cmd(repo_url) {
                            Ok(cmd) => cmd,
                            Err(e) => {
                                eprintln!("Invalid repository URL: {}", e);
                                return Ok(());
                            }
                        };
                        println!("Cloning repository '{}'...", repo_url);
                        let (exit_code, stdout, stderr) = ssh_exec(ip, &admin_user, &clone_cmd)?;
                        if exit_code == 0 {
                            println!("Repository cloned successfully.");
                            if !stdout.is_empty() {
                                print!("{}", stdout);
                            }
                        } else {
                            eprintln!(
                                "Failed to clone repository: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                }

                // Auto-connect if not disabled and single VM
                if !no_auto_connect && vm_count == 1 {
                    if let Some(ref ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                        println!("Connecting to '{}'...", vm_name);
                        let status = std::process::Command::new("ssh")
                            .args([
                                "-o",
                                "StrictHostKeyChecking=accept-new",
                                &format!("{}@{}", admin_user, ip),
                            ])
                            .status()?;
                        if !status.success() {
                            eprintln!("SSH connection ended with exit code: {:?}", status.code());
                        }
                    }
                }
            }
        }
        azlin_cli::Commands::Update {
            vm_identifier,
            resource_group,
            timeout: _,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", vm_identifier));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &vm_identifier)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

            println!("Updating development tools on '{}'...", vm_identifier);
            let update_script = crate::update_helpers::build_dev_update_script();
            let (code, stdout, stderr) = ssh_exec(&ip, &user, update_script)?;
            if code == 0 {
                let green = Style::new().green();
                println!(
                    "{}",
                    green.apply_to(format!("Update completed on '{}'", vm_identifier))
                );
                if !stdout.trim().is_empty() {
                    println!("{}", stdout.trim());
                }
            } else {
                let detail = if stderr.trim().is_empty() {
                    String::new()
                } else {
                    format!(": {}", azlin_core::sanitizer::sanitize(stderr.trim()))
                };
                anyhow::bail!("Update failed on '{}'{}", vm_identifier, detail);
            }
        }

        // ── Clone ────────────────────────────────────────────────────
        azlin_cli::Commands::Clone {
            source_vm,
            num_replicas,
            resource_group,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            let snapshot_name = format!(
                "{}_clone_snap_{}",
                source_vm,
                chrono::Utc::now().format("%Y%m%d_%H%M%S")
            );

            println!(
                "Cloning VM '{}' ({} replica(s))...",
                source_vm, num_replicas
            );

            // Step 1: create snapshot of source
            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Snapshotting {}...", source_vm));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let snap_out = std::process::Command::new("az")
                .args([
                    "snapshot",
                    "create",
                    "--resource-group",
                    &rg,
                    "--source-disk",
                    &format!("{}_OsDisk", source_vm),
                    "--name",
                    &snapshot_name,
                    "--output",
                    "json",
                ])
                .output()?;
            pb.finish_and_clear();

            if !snap_out.status.success() {
                let stderr = String::from_utf8_lossy(&snap_out.stderr);
                anyhow::bail!(
                    "Failed to snapshot source VM: {}",
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
            println!("Created snapshot '{}'", snapshot_name);

            // Step 2: create VMs from snapshot
            for i in 0..num_replicas {
                let clone_name = format!("{}-clone-{}", source_vm, i + 1);
                println!("Creating clone '{}'...", clone_name);
                let disk_name = format!("{}_OsDisk", clone_name);

                let disk_out = std::process::Command::new("az")
                    .args([
                        "disk",
                        "create",
                        "--resource-group",
                        &rg,
                        "--name",
                        &disk_name,
                        "--source",
                        &snapshot_name,
                        "--output",
                        "json",
                    ])
                    .output()?;

                if disk_out.status.success() {
                    println!("  Created disk '{}' from snapshot", disk_name);
                    // Step 3: create VM from the disk
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Creating VM '{}'...", clone_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let vm_out = std::process::Command::new("az")
                        .args([
                            "vm",
                            "create",
                            "--resource-group",
                            &rg,
                            "--name",
                            &clone_name,
                            "--attach-os-disk",
                            &disk_name,
                            "--os-type",
                            "Linux",
                            "--nsg",
                            "",
                            "--output",
                            "json",
                        ])
                        .output()?;
                    pb.finish_and_clear();

                    if vm_out.status.success() {
                        println!("  Created VM '{}'", clone_name);
                    } else {
                        let stderr = String::from_utf8_lossy(&vm_out.stderr);
                        eprintln!(
                            "  Failed to create VM '{}': {}",
                            clone_name,
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                } else {
                    let stderr = String::from_utf8_lossy(&disk_out.stderr);
                    eprintln!(
                        "  Failed to create disk for clone '{}': {}",
                        clone_name,
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
        }

        // ── Session ──────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
