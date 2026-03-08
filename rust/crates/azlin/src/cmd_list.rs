#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::List {
            resource_group,
            all,
            tag,
            no_tmux,
            with_latency,
            show_procs,
            with_health,
            wide,
            compact,
            quota,
            show_all_vms,
            vm_pattern,
            include_stopped,
            all_contexts,
            restore,
            contexts,
            no_cache,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let include_all = all || include_stopped;

            // Select cached or uncached list methods based on --no-cache flag
            let list_vms = |mgr: &azlin_azure::VmManager,
                            rg: &str|
             -> Result<Vec<azlin_core::models::VmInfo>> {
                if no_cache {
                    mgr.list_vms_no_cache(rg)
                } else {
                    mgr.list_vms(rg)
                }
            };
            let list_all =
                |mgr: &azlin_azure::VmManager| -> Result<Vec<azlin_core::models::VmInfo>> {
                    if no_cache {
                        mgr.list_all_vms_no_cache()
                    } else {
                        mgr.list_all_vms()
                    }
                };

            // Resolve resource group(s)
            if verbose {
                eprintln!(
                    "[VERBOSE] Fetching VMs from resource group: {}",
                    resource_group.as_deref().unwrap_or("(default)")
                );
            }
            let mut all_vms = if all_contexts {
                // Read all context files from ~/.azlin/contexts/ and aggregate VMs
                let ctx_dir = home_dir()?.join(".azlin").join("contexts");
                if ctx_dir.is_dir() {
                    let mut aggregated = Vec::new();
                    let mut entries: Vec<_> = std::fs::read_dir(&ctx_dir)?
                        .filter_map(|e| e.ok())
                        .filter(|e| e.path().extension().is_some_and(|ext| ext == "toml"))
                        .collect();
                    entries.sort_by_key(|e| e.file_name());
                    for entry in entries {
                        match crate::contexts::read_context_resource_group(&entry.path()) {
                            Ok((ctx_name, Some(rg))) => {
                                // If --contexts pattern provided, filter context names
                                if let Some(ref pattern) = contexts {
                                    let pat = pattern.replace('*', "");
                                    // Simple glob: if pattern contains *, do substring match
                                    // Otherwise exact match
                                    if pattern.contains('*') {
                                        if !ctx_name.contains(&pat) {
                                            continue;
                                        }
                                    } else if ctx_name != *pattern {
                                        continue;
                                    }
                                }
                                match list_vms(&vm_manager, &rg) {
                                    Ok(vms) => {
                                        println!("── context: {} (rg: {}) ──", ctx_name, rg);
                                        aggregated.extend(vms);
                                    }
                                    Err(e) => {
                                        eprintln!("Warning: failed to list VMs for context '{}' (rg: {}): {}", ctx_name, rg, e);
                                    }
                                }
                            }
                            Ok((ctx_name, None)) => {
                                eprintln!(
                                    "Warning: context '{}' has no resource_group, skipping.",
                                    ctx_name
                                );
                            }
                            Err(e) => {
                                eprintln!(
                                    "Warning: failed to read context file {:?}: {}",
                                    entry.path(),
                                    e
                                );
                            }
                        }
                    }
                    aggregated
                } else {
                    eprintln!(
                        "Warning: no contexts directory found at {:?}. Using default VM list.",
                        ctx_dir
                    );
                    match &resource_group {
                        Some(rg) => list_vms(&vm_manager, rg)?,
                        None => {
                            let config = azlin_core::AzlinConfig::load()
                                .context("Failed to load azlin config")?;
                            match config.default_resource_group {
                                Some(rg) => list_vms(&vm_manager, &rg)?,
                                None => {
                                    anyhow::bail!("No resource group specified. Use --resource-group or set in config.");
                                }
                            }
                        }
                    }
                }
            } else if show_all_vms {
                list_all(&vm_manager)?
            } else {
                match &resource_group {
                    Some(rg) => list_vms(&vm_manager, rg)?,
                    None => {
                        let config = azlin_core::AzlinConfig::load()
                            .context("Failed to load azlin config")?;
                        match config.default_resource_group {
                            Some(rg) => list_vms(&vm_manager, &rg)?,
                            None => {
                                anyhow::bail!("No resource group specified. Use --resource-group or set in config.");
                            }
                        }
                    }
                }
            };

            if verbose {
                eprintln!("[VERBOSE] Fetched {} VMs", all_vms.len());
            }

            // Filter stopped VMs unless --all/--include-stopped,
            // then by tag and name pattern.
            crate::list_helpers::apply_filters(
                &mut all_vms,
                include_all,
                tag.as_deref(),
                vm_pattern.as_deref(),
            );

            // Preserve Azure's natural ordering (matches Python behavior)

            if verbose {
                eprintln!("[VERBOSE] Detecting bastion hosts...");
            }
            // Detect and display bastion hosts (matching Python: shown above VM table)
            // Use the resolved resource group from the VMs themselves
            let effective_rg = all_vms
                .first()
                .map(|v| v.resource_group.as_str())
                .unwrap_or("");
            if matches!(output, azlin_cli::OutputFormat::Table) && !effective_rg.is_empty() {
                if let Ok(bastions) = crate::list_helpers::detect_bastion_hosts(effective_rg) {
                    if !bastions.is_empty() {
                        let mut bastion_table = Table::new();
                        bastion_table.load_preset(UTF8_FULL_CONDENSED);
                        bastion_table.set_header(vec![
                            Cell::new("Name").add_attribute(Attribute::Bold),
                            Cell::new("Location").add_attribute(Attribute::Bold),
                            Cell::new("SKU").add_attribute(Attribute::Bold),
                        ]);
                        for (name, location, sku) in &bastions {
                            bastion_table.add_row(vec![
                                Cell::new(name),
                                Cell::new(location),
                                Cell::new(sku),
                            ]);
                        }
                        println!("Azure Bastion Hosts");
                        println!("{bastion_table}");
                        println!();
                    }
                }
            }

            if verbose {
                eprintln!("[VERBOSE] Collecting tmux sessions via bastion SSH...");
            }
            let tmux_sessions = if !no_tmux {
                crate::cmd_list_data::collect_tmux_sessions(
                    &all_vms,
                    effective_rg,
                    matches!(output, azlin_cli::OutputFormat::Table),
                    verbose,
                    vm_manager.subscription_id(),
                )
            } else {
                std::collections::HashMap::new()
            };

            let latencies = if with_latency {
                crate::cmd_list_data::collect_latencies(&all_vms)
            } else {
                std::collections::HashMap::new()
            };

            let health_data = if with_health {
                crate::cmd_list_data::collect_health(&all_vms, verbose)
            } else {
                std::collections::HashMap::new()
            };

            let proc_data = if show_procs {
                crate::cmd_list_data::collect_procs(&all_vms)
            } else {
                std::collections::HashMap::new()
            };

            // Render output (table, JSON, or CSV)
            crate::cmd_list_render::render_list(
                &crate::cmd_list_render::ListRenderConfig {
                    output,
                    show_tmux_col: !no_tmux,
                    wide,
                    compact,
                    with_latency,
                    with_health,
                    show_procs,
                    show_all_vms,
                },
                &crate::cmd_list_render::ListRenderData {
                    vms: &all_vms,
                    tmux_sessions: &tmux_sessions,
                    latencies: &latencies,
                    health_data: &health_data,
                    proc_data: &proc_data,
                },
            )?;

            if restore && !tmux_sessions.is_empty() {
                crate::cmd_list_data::restore_tmux_sessions(&tmux_sessions);
            }

            // Show quota summary if requested
            if quota {
                let _rg = match resource_group {
                    Some(rg) => rg,
                    None => {
                        let config = azlin_core::AzlinConfig::load()
                            .context("Failed to load azlin config")?;
                        config.default_resource_group.ok_or_else(|| {
                            anyhow::anyhow!("No resource group specified. Use --resource-group or set in config.")
                        })?
                    }
                };
                println!("\nvCPU Quota:");
                // Use the configured default region instead of hardcoding "westus"
                let config_for_quota = azlin_core::AzlinConfig::load().unwrap_or_default();
                let quota_location = config_for_quota.default_region.clone();
                let output = std::process::Command::new("az")
                    .args([
                        "vm",
                        "list-usage",
                        "--location",
                        &quota_location,
                        "--query",
                        "[?contains(name.value, 'vCPUs')].{Name:name.localizedValue, Current:currentValue, Limit:limit}",
                        "--output",
                        "table",
                    ])
                    .output()?;
                if output.status.success() {
                    print!("{}", String::from_utf8_lossy(&output.stdout));
                }
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
