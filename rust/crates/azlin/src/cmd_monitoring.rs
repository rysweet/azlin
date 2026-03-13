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
            interval,
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
                // Build initial dashboard entries from the metrics we already collected.
                let mut app = crate::tui_dashboard::DashboardApp::new(interval);
                for m in &metrics {
                    let mut entry =
                        crate::tui_dashboard::VmDashboardEntry::new(m.vm_name.clone());
                    entry.power_state = m.power_state.clone();
                    entry.agent_status = m.agent_status.clone();
                    entry.error_count = m.error_count;
                    entry.cpu_percent = m.cpu_percent;
                    entry.mem_percent = m.mem_percent;
                    entry.disk_percent = m.disk_percent;
                    entry.push_sample(m.cpu_percent, m.mem_percent);
                    app.entries.push(entry);
                }

                // The refresh callback re-collects metrics from all VMs and
                // merges the results into the existing dashboard entries.
                let rg_clone = rg.clone();
                let bastion_map_clone = bastion_map.clone();
                let ssh_key_clone = ssh_key_path.clone();
                let sub_clone = sub_id.clone();

                let refresh = move |entries: &mut Vec<crate::tui_dashboard::VmDashboardEntry>| {
                    let auth = match azlin_azure::AzureAuth::new() {
                        Ok(a) => a,
                        Err(_) => return,
                    };
                    let vm_mgr = azlin_azure::VmManager::new(&auth);
                    let vms = match vm_mgr.list_vms(&rg_clone) {
                        Ok(v) => v,
                        Err(_) => return,
                    };

                    for vm_info in &vms {
                        let ip = match vm_info
                            .public_ip
                            .as_ref()
                            .or(vm_info.private_ip.as_ref())
                        {
                            Some(ip) => ip.clone(),
                            None => continue,
                        };
                        let user = vm_info
                            .admin_username
                            .clone()
                            .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                        let state = vm_info.power_state.to_string();

                        let bastion_info_owned: Option<(
                            String,
                            String,
                            String,
                            Option<std::path::PathBuf>,
                        )> = if vm_info.public_ip.is_none() {
                            bastion_map_clone.get(&vm_info.location).map(|bn| {
                                let vm_rid = format!(
                                    "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                                    sub_clone, vm_info.resource_group, vm_info.name
                                );
                                (
                                    bn.clone(),
                                    vm_info.resource_group.clone(),
                                    vm_rid,
                                    ssh_key_clone.clone(),
                                )
                            })
                        } else {
                            None
                        };
                        let bastion_ref =
                            bastion_info_owned.as_ref().map(|(bn, rg_b, rid, key)| {
                                (
                                    bn.as_str(),
                                    rg_b.as_str(),
                                    rid.as_str(),
                                    key.as_deref(),
                                )
                            });

                        let m = collect_health_metrics(
                            &vm_info.name,
                            &ip,
                            &user,
                            &state,
                            bastion_ref,
                        );

                        // Find or create the entry for this VM
                        let entry = if let Some(pos) =
                            entries.iter().position(|e| e.vm_name == vm_info.name)
                        {
                            &mut entries[pos]
                        } else {
                            entries.push(
                                crate::tui_dashboard::VmDashboardEntry::new(
                                    vm_info.name.clone(),
                                ),
                            );
                            entries.last_mut().unwrap()
                        };

                        entry.power_state = m.power_state;
                        entry.agent_status = m.agent_status;
                        entry.error_count = m.error_count;
                        entry.cpu_percent = m.cpu_percent;
                        entry.mem_percent = m.mem_percent;
                        entry.disk_percent = m.disk_percent;
                        entry.region = vm_info.location.clone();
                        entry.ip = ip;
                        entry.push_sample(m.cpu_percent, m.mem_percent);
                    }
                };

                // Run the interactive dashboard; loop to handle VM actions.
                loop {
                    crate::tui_dashboard::run_dashboard(&mut app, Some(&refresh))?;

                    if app.should_quit {
                        break;
                    }

                    // Execute any pending VM action, then re-enter the TUI.
                    if let Some(action) = app.pending_action.take() {
                        match action {
                            crate::tui_dashboard::VmAction::Connect(name) => {
                                crossterm::terminal::disable_raw_mode()?;
                                std::io::Write::flush(&mut std::io::stdout())?;
                                let targets =
                                    resolve_vm_targets(Some(&name), None, Some(rg.clone()))
                                        .await?;
                                if let Some(t) = targets.first() {
                                    let _ = std::process::Command::new("ssh")
                                        .args(crate::create_helpers::build_ssh_connect_args(
                                            &t.user, &t.ip,
                                        ))
                                        .status();
                                }
                                app.status_message =
                                    format!("Returned from SSH to {}", name);
                            }
                            crate::tui_dashboard::VmAction::Start(name) => {
                                let auth = azlin_azure::AzureAuth::new()?;
                                let vm_mgr = azlin_azure::VmManager::new(&auth);
                                match vm_mgr.start_vm(&rg, &name) {
                                    Ok(_) => {
                                        app.status_message =
                                            format!("Started {}", name);
                                    }
                                    Err(e) => {
                                        app.status_message =
                                            format!("Failed to start {}: {}", name, e);
                                    }
                                }
                            }
                            crate::tui_dashboard::VmAction::Stop(name) => {
                                let auth = azlin_azure::AzureAuth::new()?;
                                let vm_mgr = azlin_azure::VmManager::new(&auth);
                                match vm_mgr.stop_vm(&rg, &name, true) {
                                    Ok(_) => {
                                        app.status_message =
                                            format!("Stopped {}", name);
                                    }
                                    Err(e) => {
                                        app.status_message =
                                            format!("Failed to stop {}: {}", name, e);
                                    }
                                }
                            }
                        }
                    }
                }
            } else {
                println!("Health Dashboard — Four Golden Signals ({})", rg);
                render_health_table(&metrics);
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
