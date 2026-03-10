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
        azlin_cli::Commands::W {
            resource_group,
            vm,
            ip,
            ..
        } => {
            let targets = resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
            for target in &targets {
                println!("── {} ──", target.vm_name);
                match target.exec_checked("w") {
                    Ok(output) => print!("{}", output),
                    Err(e) => eprintln!("  Error: {}", e),
                }
            }
        }
        azlin_cli::Commands::Ps {
            resource_group,
            vm,
            ip,
            ..
        } => {
            let targets = resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
            for target in &targets {
                println!("── {} ──", target.vm_name);
                match target.exec_checked("ps aux --sort=-%mem | head -20") {
                    Ok(output) => print!("{}", output),
                    Err(e) => eprintln!("  Error: {}", e),
                }
            }
        }
        azlin_cli::Commands::Top {
            resource_group,
            vm,
            ip,
            ..
        } => {
            let targets = resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
            for target in &targets {
                println!("── {} ──", target.vm_name);
                match target.exec_checked("top -b -n 1 | head -30") {
                    Ok(output) => print!("{}", output),
                    Err(e) => eprintln!("  Error: {}", e),
                }
            }
        }
        azlin_cli::Commands::Health {
            vm,
            resource_group,
            tui,
            ..
        } => {
            let auth = match azlin_azure::AzureAuth::new() {
                Ok(a) => a,
                Err(_) => {
                    anyhow::bail!(
                        "Azure authentication failed.\n\
                         Hint: use 'az login' or specify --vm and --ip flags for direct SSH."
                    );
                }
            };
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = penguin_spinner("Collecting health metrics...");

            // Detect bastion hosts for private-IP-only VMs
            let bastion_map: std::collections::HashMap<String, String> =
                crate::list_helpers::detect_bastion_hosts(&rg)
                    .unwrap_or_default()
                    .into_iter()
                    .map(|(name, location, _)| (location, name))
                    .collect();

            // Resolve SSH key path for bastion tunnelling
            let ssh_key_path = home_dir()
                .ok()
                .map(|h| h.join(".ssh").join("azlin_key"))
                .filter(|p| p.exists())
                .or_else(|| {
                    home_dir()
                        .ok()
                        .map(|h| h.join(".ssh").join("id_rsa"))
                        .filter(|p| p.exists())
                });

            let sub_id = vm_manager.subscription_id().to_string();

            let metrics: Vec<HealthMetrics> = if let Some(vm_name) = vm {
                let vm_info = vm_manager.get_vm(&rg, &vm_name)?;
                let ip = vm_info
                    .public_ip
                    .clone()
                    .or(vm_info.private_ip.clone())
                    .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_name))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                let state = vm_info.power_state.to_string();

                // Use bastion when there is no public IP
                let bastion_info_owned: Option<(
                    String,
                    String,
                    String,
                    Option<std::path::PathBuf>,
                )> = if vm_info.public_ip.is_none() {
                    bastion_map.get(&vm_info.location).map(|bn| {
                            let vm_rid = format!(
                                "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                                sub_id, vm_info.resource_group, vm_info.name
                            );
                            (bn.clone(), vm_info.resource_group.clone(), vm_rid, ssh_key_path.clone())
                        })
                } else {
                    None
                };
                let bastion_ref = bastion_info_owned.as_ref().map(|(bn, rg_b, rid, key)| {
                    (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref())
                });

                vec![collect_health_metrics(
                    &vm_name,
                    &ip,
                    &user,
                    &state,
                    bastion_ref,
                )]
            } else {
                let vms = vm_manager.list_vms(&rg)?;
                vms.iter()
                    .filter_map(|vm_info| {
                        let ip = vm_info.public_ip.as_ref().or(vm_info.private_ip.as_ref())?;
                        let user = vm_info
                            .admin_username
                            .clone()
                            .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                        let state = vm_info.power_state.to_string();

                        // Use bastion when there is no public IP
                        let bastion_info_owned: Option<(String, String, String, Option<std::path::PathBuf>)> =
                            if vm_info.public_ip.is_none() {
                                bastion_map.get(&vm_info.location).map(|bn| {
                                    let vm_rid = format!(
                                        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                                        sub_id, vm_info.resource_group, vm_info.name
                                    );
                                    (bn.clone(), vm_info.resource_group.clone(), vm_rid, ssh_key_path.clone())
                                })
                            } else {
                                None
                            };
                        let bastion_ref = bastion_info_owned.as_ref().map(|(bn, rg_b, rid, key)| {
                            (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref())
                        });

                        Some(collect_health_metrics(&vm_info.name, ip, &user, &state, bastion_ref))
                    })
                    .collect()
            };
            pb.finish_and_clear();

            if metrics.is_empty() {
                println!("No VMs found in resource group '{}'", rg);
            } else if tui {
                run_health_tui(&metrics)?;
            } else {
                println!("Health Dashboard — Four Golden Signals ({})", rg);
                render_health_table(&metrics);
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
