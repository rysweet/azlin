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
        azlin_cli::Commands::List {
            resource_group,
            all,
            tag,
            no_tmux,
            show_tmux,
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
            verbose: list_verbose,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let config = crate::dispatch_helpers::load_user_config();
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
            // Explicitly subscription-scoped variant, used by --all-contexts so
            // each context's VMs come from that context's subscription instead
            // of from whichever one the CLI happens to be on (#1090).
            let list_vms_in = |mgr: &azlin_azure::VmManager,
                               sub: &str,
                               rg: &str|
             -> Result<Vec<azlin_core::models::VmInfo>> {
                if no_cache {
                    mgr.list_vms_in_no_cache(sub, rg)
                } else {
                    mgr.list_vms_in(sub, rg)
                }
            };
            // Subscriptions actually queried, so the subscription-scoped
            // enrichment below can be skipped when the listing spans more than
            // one rather than silently attributing everything to the first.
            let mut queried_subscriptions: std::collections::BTreeSet<String> =
                std::collections::BTreeSet::new();
            // `list` resolved the resource group itself against
            // `config.default_resource_group`, so it never saw the active
            // context and `azlin context use prod` left it listing dev's group
            // (#1090). Route it through the one helper that applies the full
            // precedence: --resource-group, then the context, then the config.
            let resolve_rg =
                || crate::dispatch_helpers::resolve_resource_group(resource_group.clone());

            let effective_verbose = verbose || list_verbose;
            if effective_verbose {
                eprintln!(
                    "[VERBOSE] Fetching VMs from resource group: {}",
                    resource_group.as_deref().unwrap_or("(default)")
                );
            }
            let pb = penguin_spinner("Fetching VMs...");
            let mut all_vms = if all_contexts {
                // Read all context files and aggregate VMs, querying each
                // context's own subscription.
                let ctx_dir =
                    crate::active_context::contexts_dir_in(&crate::active_context::state_dir()?);
                if ctx_dir.is_dir() {
                    let mut aggregated = Vec::new();
                    let mut entries: Vec<_> = std::fs::read_dir(&ctx_dir)?
                        .filter_map(|e| e.ok())
                        .filter(|e| e.path().extension().is_some_and(|ext| ext == "toml"))
                        .collect();
                    entries.sort_by_key(|e| e.file_name());
                    for entry in entries {
                        let path = entry.path();
                        let stem = path
                            .file_stem()
                            .and_then(|s| s.to_str())
                            .unwrap_or("unknown")
                            .to_string();
                        let parsed = std::fs::read_to_string(&path)
                            .map_err(anyhow::Error::from)
                            .and_then(|c| crate::active_context::parse_context(&stem, &c));
                        let ctx = match parsed {
                            Ok(ctx) => ctx,
                            Err(e) => {
                                eprintln!("Warning: failed to read context file {:?}: {}", path, e);
                                continue;
                            }
                        };
                        // If --contexts pattern provided, filter context names
                        if let Some(ref pattern) = contexts {
                            let pat = pattern.replace('*', "");
                            // Simple glob: if pattern contains *, do substring match
                            // Otherwise exact match
                            if pattern.contains('*') {
                                if !ctx.name.contains(&pat) {
                                    continue;
                                }
                            } else if ctx.name != *pattern {
                                continue;
                            }
                        }
                        let Some(rg) = ctx.resource_group.clone() else {
                            eprintln!(
                                "Warning: context '{}' has no resource_group, skipping.",
                                ctx.name
                            );
                            continue;
                        };
                        // A context that pins no subscription cannot be
                        // attributed to one; say so in the header rather than
                        // printing the context name over rows read from
                        // whatever subscription the CLI is on.
                        let inherited = ctx.pins_no_subscription();
                        let sub = ctx
                            .subscription_id
                            .clone()
                            .unwrap_or_else(|| vm_manager.subscription_id().to_string());
                        match list_vms_in(&vm_manager, &sub, &rg) {
                            Ok(vms) => {
                                queried_subscriptions.insert(sub.clone());
                                let origin = if inherited {
                                    format!("subscription: {sub} [inherited — context pins none]")
                                } else {
                                    format!("subscription: {sub}")
                                };
                                println!(
                                    "── context: {} ({}, rg: {}) — {} VMs ──",
                                    ctx.name,
                                    origin,
                                    rg,
                                    vms.len()
                                );
                                aggregated.extend(vms);
                            }
                            Err(e) => {
                                eprintln!("Warning: failed to list VMs for context '{}' (subscription: {}, rg: {}): {}", ctx.name, sub, rg, e);
                            }
                        }
                    }
                    aggregated
                } else {
                    eprintln!(
                        "Warning: no contexts directory found at {:?}. Using default VM list.",
                        ctx_dir
                    );
                    list_vms(&vm_manager, &resolve_rg()?)?
                }
            } else if show_all_vms {
                list_all(&vm_manager)?
            } else {
                list_vms(&vm_manager, &resolve_rg()?)?
            };

            pb.finish_and_clear();
            if effective_verbose {
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

            // Bastion, tmux and health enrichment are all scoped to one
            // subscription and one resource group — they use the first VM's
            // resource group and `vm_manager.subscription_id()`. When
            // --all-contexts spanned several subscriptions those lookups were
            // silently attributed to the wrong one, so they are skipped rather
            // than reported wrongly (#1090).
            let cross_subscription = queried_subscriptions.len() > 1;
            if cross_subscription {
                eprintln!(
                    "Note: this listing spans {} subscriptions; bastion, tmux and health \
                     details are subscription-scoped and have been omitted.",
                    queried_subscriptions.len()
                );
            }

            if effective_verbose {
                eprintln!("[VERBOSE] Detecting bastion hosts...");
            }
            // Detect and display bastion hosts (matching Python: shown above VM table)
            // Every resource group in the listing is queried, not just the one
            // belonging to whichever VM sorted first: a listing that spans
            // resource groups used to display one group's bastions and
            // silently omit the others.
            let listing_rgs = crate::cmd_list_data::resource_groups_in_listing(&all_vms);
            if !cross_subscription
                && matches!(output, azlin_cli::OutputFormat::Table)
                && !listing_rgs.is_empty()
            {
                let pb = penguin_spinner("Detecting bastion hosts...");
                // Deduplicated across resource groups: one bastion can serve
                // VMs in several of them, and listing it once per group would
                // read as several bastions.
                let mut seen = std::collections::HashSet::new();
                let mut bastions: Vec<(String, String, String)> = Vec::new();
                let mut failed_rgs: Vec<String> = Vec::new();
                for rg in &listing_rgs {
                    match crate::list_helpers::detect_bastion_hosts(rg) {
                        Ok(found) => {
                            for entry in found {
                                if seen.insert(entry.clone()) {
                                    bastions.push(entry);
                                }
                            }
                        }
                        // A failed lookup makes the table incomplete, which is
                        // indistinguishable from "this group has no bastion"
                        // unless we say so. The cause travels with the group
                        // name: "not authorized" and "no such group" call for
                        // different actions, and a bare group name leaves the
                        // operator to guess which one they hit.
                        Err(e) => {
                            let cause = e.to_string();
                            let first_line = cause.lines().next().unwrap_or("").trim().to_string();
                            failed_rgs.push(if first_line.is_empty() {
                                rg.clone()
                            } else {
                                format!("{} ({})", rg, first_line)
                            });
                        }
                    }
                }
                pb.finish_and_clear();
                bastions.sort();
                if !bastions.is_empty() {
                    let mut bastion_table = crate::table_render::SimpleTable::new(
                        &["Name", "Location", "SKU"],
                        &[30, 14, 15],
                    );
                    for (name, location, sku) in &bastions {
                        bastion_table.add_row(vec![name.clone(), location.clone(), sku.clone()]);
                    }
                    println!("Azure Bastion Hosts");
                    println!("{bastion_table}");
                    println!();
                }
                if !failed_rgs.is_empty() {
                    eprintln!(
                        "Warning: could not list bastion hosts in resource group(s) {}; \
                         any bastion there is missing from the table above.",
                        failed_rgs.join(", ")
                    );
                }
            }

            if effective_verbose {
                eprintln!("[VERBOSE] Collecting tmux sessions via bastion SSH...");
            }
            let ssh_timeout = config.ssh_connect_timeout;
            // `--show-tmux` defaults to true and was discarded, so
            // `--show-tmux false` collected and displayed tmux sessions
            // anyway; only its sibling `--no-tmux` was ever read (#1089).
            // Either flag turning it off is the reading that cannot surprise
            // anyone: both say "off" and neither has ever meant "on".
            let want_tmux = show_tmux && !no_tmux;
            let tmux_sessions = if want_tmux && !cross_subscription {
                let pb = penguin_spinner("Collecting tmux sessions...");
                let sessions = crate::cmd_list_data::collect_tmux_sessions(
                    &all_vms,
                    effective_verbose,
                    vm_manager.subscription_id(),
                    ssh_timeout,
                )
                .await;
                pb.finish_and_clear();
                sessions
            } else {
                std::collections::HashMap::new()
            };

            let latencies = if with_latency {
                let pb = penguin_spinner("Measuring latencies...");
                let result = crate::cmd_list_data::collect_latencies(&all_vms);
                pb.finish_and_clear();
                result
            } else {
                std::collections::HashMap::new()
            };

            // Storage is probed only with --with-health, and in the *same*
            // sweep as the metrics: it is the column that would have made
            // #1131 visible on the day it happened instead of weeks later at
            // 98% full, and a second sweep would have rediscovered every
            // bastion to ask one more question per VM.
            let (health_data, storage_data) = if with_health && !cross_subscription {
                let pb = penguin_spinner("Checking VM health and storage...");
                let result = crate::cmd_list_data::collect_health_and_storage(
                    &all_vms,
                    vm_manager.subscription_id(),
                );
                pb.finish_and_clear();
                result
            } else {
                (
                    std::collections::HashMap::new(),
                    std::collections::HashMap::new(),
                )
            };

            let proc_data = if show_procs {
                let pb = penguin_spinner("Collecting process data...");
                let result = crate::cmd_list_data::collect_procs(
                    &all_vms,
                    ssh_timeout,
                    vm_manager.subscription_id(),
                );
                pb.finish_and_clear();
                result
            } else {
                std::collections::HashMap::new()
            };

            // Render output (table, JSON, or CSV)
            crate::cmd_list_render::render_list(
                &crate::cmd_list_render::ListRenderConfig {
                    output,
                    show_tmux_col: want_tmux,
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
                    storage_data: &storage_data,
                    proc_data: &proc_data,
                },
            )?;

            if restore && !tmux_sessions.is_empty() {
                crate::cmd_list_data::restore_tmux_sessions(&tmux_sessions, true);
            }

            // Show quota summary if requested
            if quota {
                let _rg = resolve_rg()?;
                println!("\nvCPU Quota:");
                // Quota is per-region, so it must be read for the region the
                // active context selects — not the global config default.
                let quota_location = &crate::active_context::resolve_region(
                    None,
                    crate::active_context::load_active()?.as_ref(),
                    config.default_region.clone(),
                );
                let output = std::process::Command::new("az")
                    .args([
                        "vm",
                        "list-usage",
                        "--location",
                        quota_location,
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
