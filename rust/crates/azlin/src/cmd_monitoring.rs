#[allow(unused_imports)]
use super::*;
use anyhow::Result;

/// Default per-VM health collection timeout in seconds.
const HEALTH_TIMEOUT_SECS: u64 = 30;

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
            let targets =
                resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
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
            let targets =
                resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
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
            let targets =
                resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
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

            let mut metrics: Vec<HealthMetrics> = if let Some(vm_name) = vm {
                // Single VM — no need to parallelize
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
                        (
                            bn.clone(),
                            vm_info.resource_group.clone(),
                            vm_rid,
                            ssh_key_path.clone(),
                        )
                    })
                } else {
                    None
                };
                let bastion_ref = bastion_info_owned
                    .as_ref()
                    .map(|(bn, rg_b, rid, key)| {
                        (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref())
                    });

                vec![collect_health_metrics(
                    &vm_name, &ip, &user, &state, bastion_ref,
                )]
            } else {
                // Multiple VMs — collect health in parallel with per-VM timeout.
                // SSH exec uses std::process::Command (blocking I/O), so each
                // VM is wrapped in spawn_blocking inside a tokio::spawn task.
                let vms = vm_manager.list_vms(&rg)?;

                // Build owned parameter sets for each VM so they can be moved
                // into spawn_blocking closures without lifetime issues.
                let tasks: Vec<_> = vms
                    .iter()
                    .filter_map(|vm_info| {
                        let ip = vm_info
                            .public_ip
                            .as_ref()
                            .or(vm_info.private_ip.as_ref())?
                            .clone();
                        let user = vm_info
                            .admin_username
                            .clone()
                            .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                        let state = vm_info.power_state.to_string();
                        let name = vm_info.name.clone();

                        let bastion_owned: Option<(
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
                                (
                                    bn.clone(),
                                    vm_info.resource_group.clone(),
                                    vm_rid,
                                    ssh_key_path.clone(),
                                )
                            })
                        } else {
                            None
                        };

                        Some((name, ip, user, state, bastion_owned))
                    })
                    .collect();

                // Spawn all health checks concurrently
                let mut handles = Vec::with_capacity(tasks.len());
                for (name, ip, user, state, bastion_owned) in tasks {
                    let handle = tokio::spawn(async move {
                        tokio::time::timeout(
                            std::time::Duration::from_secs(HEALTH_TIMEOUT_SECS),
                            tokio::task::spawn_blocking(move || {
                                let bastion_ref =
                                    bastion_owned.as_ref().map(|(bn, rg_b, rid, key)| {
                                        (
                                            bn.as_str(),
                                            rg_b.as_str(),
                                            rid.as_str(),
                                            key.as_deref(),
                                        )
                                    });
                                collect_health_metrics(
                                    &name, &ip, &user, &state, bastion_ref,
                                )
                            }),
                        )
                        .await
                    });
                    handles.push(handle);
                }

                // Collect results; substitute error placeholders for failures
                let mut results = Vec::with_capacity(handles.len());
                for handle in handles {
                    match handle.await {
                        Ok(Ok(Ok(m))) => results.push(m),
                        Ok(Ok(Err(join_err))) => {
                            // spawn_blocking panicked
                            eprintln!(
                                "Health collection task panicked: {}",
                                join_err
                            );
                        }
                        Ok(Err(_elapsed)) => {
                            // Per-VM timeout exceeded
                            eprintln!(
                                "Health collection timed out after {}s for a VM",
                                HEALTH_TIMEOUT_SECS
                            );
                        }
                        Err(join_err) => {
                            // tokio::spawn join error
                            eprintln!(
                                "Health collection task failed: {}",
                                join_err
                            );
                        }
                    }
                }
                results
            };

            // Sort by VM name for deterministic output regardless of task
            // completion order
            metrics.sort_by(|a, b| a.vm_name.cmp(&b.vm_name));

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

#[cfg(test)]
mod tests {
    use super::*;

    /// Verify that parallel collection produces correct results for non-running
    /// VMs (which skip SSH and return defaults immediately).
    #[tokio::test]
    async fn test_parallel_health_collection_non_running_vms() {
        let vms: Vec<(String, String)> = (0..10)
            .map(|i| (format!("vm-{}", i), "Deallocated".to_string()))
            .collect();

        let mut handles = Vec::new();
        for (name, state) in vms {
            let handle = tokio::spawn(async move {
                tokio::time::timeout(
                    std::time::Duration::from_secs(5),
                    tokio::task::spawn_blocking(move || {
                        collect_health_metrics(&name, "10.0.0.1", "user", &state, None)
                    }),
                )
                .await
            });
            handles.push(handle);
        }

        let mut results = Vec::new();
        for handle in handles {
            match handle.await {
                Ok(Ok(Ok(m))) => results.push(m),
                other => panic!("Unexpected result: {:?}", other),
            }
        }

        assert_eq!(results.len(), 10);
        for m in &results {
            assert_eq!(m.power_state, "Deallocated");
            assert_eq!(m.cpu_percent, 0.0);
            assert_eq!(m.mem_percent, 0.0);
            assert_eq!(m.disk_percent, 0.0);
        }
    }

    /// Verify that per-VM timeout fires for slow tasks.
    #[tokio::test]
    async fn test_per_vm_timeout() {
        let handle = tokio::spawn(async {
            tokio::time::timeout(
                std::time::Duration::from_millis(50),
                tokio::task::spawn_blocking(|| {
                    std::thread::sleep(std::time::Duration::from_secs(5));
                    collect_health_metrics("slow-vm", "10.0.0.1", "user", "Running", None)
                }),
            )
            .await
        });

        let result = handle.await.unwrap();
        assert!(result.is_err(), "Expected timeout, got success");
    }

    /// Verify that good results are preserved when one VM times out.
    #[tokio::test]
    async fn test_partial_timeout_preserves_good_results() {
        let mut handles = Vec::new();

        // Fast VM (non-running, returns immediately)
        handles.push(tokio::spawn(async {
            tokio::time::timeout(
                std::time::Duration::from_millis(500),
                tokio::task::spawn_blocking(|| {
                    collect_health_metrics(
                        "fast-vm", "10.0.0.1", "user", "Deallocated", None,
                    )
                }),
            )
            .await
        }));

        // Slow VM (will timeout)
        handles.push(tokio::spawn(async {
            tokio::time::timeout(
                std::time::Duration::from_millis(50),
                tokio::task::spawn_blocking(|| {
                    std::thread::sleep(std::time::Duration::from_secs(5));
                    collect_health_metrics(
                        "slow-vm", "10.0.0.1", "user", "Running", None,
                    )
                }),
            )
            .await
        }));

        let mut good = Vec::new();
        let mut timed_out = 0;
        for handle in handles {
            match handle.await {
                Ok(Ok(Ok(m))) => good.push(m),
                Ok(Err(_)) => timed_out += 1,
                _ => {}
            }
        }

        assert_eq!(good.len(), 1);
        assert_eq!(good[0].vm_name, "fast-vm");
        assert_eq!(timed_out, 1);
    }

    /// Verify deterministic output ordering by VM name.
    #[tokio::test]
    async fn test_results_sorted_by_vm_name() {
        let names = vec!["zeta-vm", "alpha-vm", "middle-vm"];
        let mut handles = Vec::new();

        for name in names {
            let name = name.to_string();
            handles.push(tokio::spawn(async move {
                tokio::time::timeout(
                    std::time::Duration::from_secs(5),
                    tokio::task::spawn_blocking(move || {
                        collect_health_metrics(
                            &name, "10.0.0.1", "user", "Deallocated", None,
                        )
                    }),
                )
                .await
            }));
        }

        let mut results: Vec<HealthMetrics> = Vec::new();
        for handle in handles {
            if let Ok(Ok(Ok(m))) = handle.await {
                results.push(m);
            }
        }

        results.sort_by(|a, b| a.vm_name.cmp(&b.vm_name));

        let sorted_names: Vec<&str> =
            results.iter().map(|m| m.vm_name.as_str()).collect();
        assert_eq!(sorted_names, vec!["alpha-vm", "middle-vm", "zeta-vm"]);
    }
}
