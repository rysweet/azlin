#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use comfy_table::{
    modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Color, Table,
};

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
                        bastion_table
                            .load_preset(UTF8_FULL)
                            .apply_modifier(UTF8_ROUND_CORNERS);
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
            // Collect tmux sessions if not disabled
            let mut tmux_sessions: std::collections::HashMap<String, Vec<String>> =
                std::collections::HashMap::new();
            if !no_tmux {
                // Build bastion name map (region -> bastion_name) for private VMs
                let bastion_map: std::collections::HashMap<String, String> =
                    if matches!(output, azlin_cli::OutputFormat::Table) {
                        if let Ok(bastions) =
                            crate::list_helpers::detect_bastion_hosts(effective_rg)
                        {
                            bastions
                                .into_iter()
                                .map(|(name, location, _)| (location, name))
                                .collect()
                        } else {
                            std::collections::HashMap::new()
                        }
                    } else {
                        std::collections::HashMap::new()
                    };

                // Resolve SSH key path
                let ssh_key = home_dir()
                    .ok()
                    .map(|h| h.join(".ssh").join("azlin_key"))
                    .filter(|p| p.exists())
                    .or_else(|| {
                        home_dir()
                            .ok()
                            .map(|h| h.join(".ssh").join("id_rsa"))
                            .filter(|p| p.exists())
                    });

                let mut tunnel_pool = BastionTunnelPool::new();

                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let user = vm
                        .admin_username
                        .as_deref()
                        .unwrap_or(DEFAULT_ADMIN_USERNAME);
                    let tmux_cmd = "tmux list-sessions -F '#{session_name}' 2>/dev/null || true";

                    let output = if let Some(ip) = &vm.public_ip {
                        // Direct SSH for VMs with public IPs
                        std::process::Command::new("ssh")
                            .args([
                                "-o",
                                "StrictHostKeyChecking=accept-new",
                                "-o",
                                "ConnectTimeout=5",
                                "-o",
                                "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                tmux_cmd,
                            ])
                            .output()
                    } else if let Some(bastion_name) = bastion_map.get(&vm.location) {
                        // Use bastion tunnel pooling: first VM sets up the tunnel (~2s),
                        // subsequent VMs in the same region reuse it (~0s overhead).
                        let vm_id = format!(
                            "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                            vm_manager.subscription_id(), vm.resource_group, vm.name
                        );
                        match tunnel_pool.get_or_create(
                            &vm.name,
                            bastion_name,
                            &vm.resource_group,
                            &vm_id,
                        ) {
                            Ok(port) => {
                                let mut ssh_args = vec![
                                    "-o".to_string(),
                                    "StrictHostKeyChecking=accept-new".to_string(),
                                    "-o".to_string(),
                                    "ConnectTimeout=5".to_string(),
                                    "-o".to_string(),
                                    "BatchMode=yes".to_string(),
                                    "-p".to_string(),
                                    port.to_string(),
                                ];
                                if let Some(ref key) = ssh_key {
                                    ssh_args.push("-i".to_string());
                                    ssh_args.push(key.to_string_lossy().to_string());
                                }
                                ssh_args.push(format!("{}@127.0.0.1", user));
                                ssh_args.push(tmux_cmd.to_string());
                                let str_args: Vec<&str> =
                                    ssh_args.iter().map(|s| s.as_str()).collect();
                                std::process::Command::new("ssh")
                                    .args(&str_args)
                                    .stdout(std::process::Stdio::piped())
                                    .stderr(std::process::Stdio::piped())
                                    .output()
                            }
                            Err(e) => {
                                if verbose {
                                    eprintln!(
                                        "[VERBOSE] Failed to create bastion tunnel for {}: {}",
                                        vm.name, e
                                    );
                                }
                                continue;
                            }
                        }
                    } else {
                        continue; // No bastion available for this region
                    };

                    if let Ok(out) = output {
                        if out.status.success() {
                            let sessions: Vec<String> = String::from_utf8_lossy(&out.stdout)
                                .lines()
                                .filter(|l| !l.is_empty() && !l.starts_with('{'))
                                .map(|l| l.to_string())
                                .collect();
                            if verbose {
                                eprintln!("[VERBOSE] {} -> {} sessions", vm.name, sessions.len());
                            }
                            if !sessions.is_empty() {
                                tmux_sessions.insert(vm.name.clone(), sessions);
                            }
                        }
                    }
                }
            }

            // Collect latency if requested
            let mut latencies: std::collections::HashMap<String, u64> =
                std::collections::HashMap::new();
            if with_latency {
                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let addr = match format!("{}:22", ip).parse() {
                            Ok(addr) => addr,
                            Err(_) => continue,
                        };
                        let start = std::time::Instant::now();
                        let _ = std::net::TcpStream::connect_timeout(
                            &addr,
                            std::time::Duration::from_secs(5),
                        );
                        latencies.insert(vm.name.clone(), start.elapsed().as_millis() as u64);
                    }
                }
            }

            // Collect health metrics if requested
            let mut health_data: std::collections::HashMap<String, String> =
                std::collections::HashMap::new();
            if with_health {
                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        let output = std::process::Command::new("ssh")
                            .args([
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=10",
                                "-o", "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                "echo \"CPU:$(top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{printf \"%.1f\", 100 - $1}')% MEM:$(free -m | awk '/Mem:/{printf \"%.0f%%\", $3/$2*100}') DISK:$(df -h / | awk 'NR==2{print $5}')\"",
                            ])
                            .output();
                        if let Ok(out) = output {
                            if out.status.success() {
                                let metrics =
                                    String::from_utf8_lossy(&out.stdout).trim().to_string();
                                health_data.insert(vm.name.clone(), metrics);
                            }
                        }
                    }
                }
            }

            // Collect top processes if requested
            let mut proc_data: std::collections::HashMap<String, String> =
                std::collections::HashMap::new();
            if show_procs {
                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        let output = std::process::Command::new("ssh")
                            .args([
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=10",
                                "-o", "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                "ps aux --sort=-%mem | head -6 | tail -5 | awk '{print $11}' | tr '\\n' ', '",
                            ])
                            .output();
                        if let Ok(out) = output {
                            if out.status.success() {
                                let procs = String::from_utf8_lossy(&out.stdout).trim().to_string();
                                proc_data.insert(vm.name.clone(), procs);
                            }
                        }
                    }
                }
            }

            // Build and render table
            let show_tmux_col = !no_tmux;
            let mut headers = vec!["Session"];
            if show_tmux_col {
                headers.push("Tmux");
            }
            if wide {
                headers.push("VM Name");
            }
            headers.extend_from_slice(&["OS", "Status", "IP", "Region"]);
            if wide {
                headers.push("SKU");
            }
            headers.extend_from_slice(&["CPU", "Mem"]);
            if with_latency {
                headers.push("Latency");
            }
            if with_health {
                headers.push("Health");
            }
            if show_procs {
                headers.push("Top Procs");
            }

            match output {
                azlin_cli::OutputFormat::Json => {
                    let json_vms: Vec<serde_json::Value> = all_vms
                        .iter()
                        .map(|vm| {
                            let ip_display = crate::display_helpers::format_ip_display(
                                vm.public_ip.as_deref(),
                                vm.private_ip.as_deref(),
                            );
                            let os_display = crate::display_helpers::format_os_display(
                                vm.os_offer.as_deref(),
                                &vm.os_type,
                            );
                            let (cpu, mem) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
                            let mut obj = serde_json::json!({
                                "name": vm.name,
                                "resource_group": vm.resource_group,
                                "power_state": vm.power_state.to_string(),
                                "ip": ip_display,
                                "public_ip": vm.public_ip,
                                "private_ip": vm.private_ip,
                                "location": vm.location,
                                "vm_size": vm.vm_size,
                                "os": os_display,
                                "os_offer": vm.os_offer,
                                "cpu": cpu,
                                "mem": mem,
                                "session": vm.tags.get("azlin-session").unwrap_or(&"-".to_string()),
                                "tmux_sessions": tmux_sessions.get(&vm.name).cloned().unwrap_or_default(),
                            });
                            if with_latency {
                                obj["latency_ms"] = serde_json::json!(latencies.get(&vm.name));
                            }
                            if with_health {
                                obj["health"] = serde_json::json!(health_data.get(&vm.name));
                            }
                            obj
                        })
                        .collect();
                    println!("{}", serde_json::to_string_pretty(&json_vms)?);
                }
                azlin_cli::OutputFormat::Csv => {
                    println!("{}", headers.join(","));
                    for vm in &all_vms {
                        let session = vm
                            .tags
                            .get("azlin-session")
                            .map(|s| s.as_str())
                            .unwrap_or("-");
                        let tmux = tmux_sessions
                            .get(&vm.name)
                            .map(|s| s.join(";"))
                            .unwrap_or_default();
                        let ip_display = crate::display_helpers::format_ip_display(
                            vm.public_ip.as_deref(),
                            vm.private_ip.as_deref(),
                        );
                        let os_display = crate::display_helpers::format_os_display(
                            vm.os_offer.as_deref(),
                            &vm.os_type,
                        );
                        let (cpu, mem) =
                            crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
                        let mut row = session.to_string();
                        if show_tmux_col {
                            row.push_str(&format!(",{}", tmux));
                        }
                        if wide {
                            row.push_str(&format!(",{}", vm.name));
                        }
                        row.push_str(&format!(
                            ",{},{},{},{}",
                            os_display, vm.power_state, ip_display, vm.location
                        ));
                        if wide {
                            row.push_str(&format!(",{}", vm.vm_size));
                        }
                        row.push_str(&format!(",{},{}", cpu, mem));
                        if with_latency {
                            row.push_str(&format!(
                                ",{}",
                                latencies
                                    .get(&vm.name)
                                    .map(|l| format!("{}ms", l))
                                    .unwrap_or_default()
                            ));
                        }
                        println!("{}", row);
                    }
                }
                azlin_cli::OutputFormat::Table => {
                    let mut table = Table::new();
                    table
                        .load_preset(UTF8_FULL)
                        .apply_modifier(UTF8_ROUND_CORNERS);
                    let header_cells: Vec<Cell> = headers
                        .iter()
                        .map(|h| Cell::new(h).add_attribute(Attribute::Bold))
                        .collect();
                    table.set_header(header_cells);

                    // Adapt table width to terminal size (matching Python behavior)
                    let term_width = crossterm::terminal::size()
                        .map(|(w, _)| w as u16)
                        .unwrap_or(120);
                    if compact {
                        table.set_width(80.min(term_width));
                    } else {
                        table.set_width(term_width);
                    }

                    for vm in &all_vms {
                        let session = vm
                            .tags
                            .get("azlin-session")
                            .map(|s| s.as_str())
                            .unwrap_or("-");
                        let tmux = tmux_sessions
                            .get(&vm.name)
                            .map(|s| crate::display_helpers::format_tmux_sessions(s, 3))
                            .unwrap_or_else(|| "-".to_string());
                        let ip_display = crate::display_helpers::format_ip_display(
                            vm.public_ip.as_deref(),
                            vm.private_ip.as_deref(),
                        );
                        let os_display = crate::display_helpers::format_os_display(
                            vm.os_offer.as_deref(),
                            &vm.os_type,
                        );
                        let (cpu, mem) =
                            crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
                        let state_color = match vm.power_state {
                            azlin_core::models::PowerState::Running => Color::Green,
                            azlin_core::models::PowerState::Stopped
                            | azlin_core::models::PowerState::Deallocated => Color::Red,
                            _ => Color::Yellow,
                        };

                        let vm_name_display = if wide {
                            vm.name.clone()
                        } else {
                            crate::display_helpers::truncate_vm_name(&vm.name, 20)
                        };

                        let mut row = vec![Cell::new(session)];
                        if show_tmux_col {
                            row.push(Cell::new(&tmux));
                        }
                        if wide {
                            row.push(Cell::new(&vm_name_display));
                        }
                        row.extend_from_slice(&[
                            Cell::new(&os_display),
                            Cell::new(vm.power_state.to_string()).fg(state_color),
                            Cell::new(&ip_display),
                            Cell::new(&vm.location),
                        ]);
                        if wide {
                            row.push(Cell::new(&vm.vm_size));
                        }
                        row.extend_from_slice(&[Cell::new(&cpu), Cell::new(&mem)]);
                        if with_latency {
                            let lat = latencies
                                .get(&vm.name)
                                .map(|l| format!("{}ms", l))
                                .unwrap_or_else(|| "-".to_string());
                            row.push(Cell::new(lat));
                        }
                        if with_health {
                            let h = health_data
                                .get(&vm.name)
                                .cloned()
                                .unwrap_or_else(|| "-".to_string());
                            row.push(Cell::new(h));
                        }
                        if show_procs {
                            let p = proc_data
                                .get(&vm.name)
                                .cloned()
                                .unwrap_or_else(|| "-".to_string());
                            row.push(Cell::new(p));
                        }
                        table.add_row(row);
                    }
                    println!("{table}");

                    // Summary footer
                    let total = all_vms.len();
                    let total_tmux: usize = tmux_sessions.values().map(|v| v.len()).sum();

                    println!();
                    if total_tmux > 0 {
                        println!("Total: {} VMs | {} tmux sessions", total, total_tmux);
                    } else {
                        println!("Total: {} VMs", total);
                    }

                    if !show_all_vms {
                        println!();
                        println!("Hints:");
                        println!("  azlin list -a        Show all VMs across all resource groups");
                        println!("  azlin list -w        Wide mode (show VM Name, SKU columns)");
                        println!(
                            "  azlin list -r        Restore all tmux sessions in new terminal window"
                        );
                        println!("  azlin list -q        Show quota usage (slower)");
                        println!("  azlin list -v        Verbose mode (show tunnel/SSH details)");
                    }
                }
            }

            // Restore tmux sessions if requested (connect to each VM with active tmux)
            if restore && !tmux_sessions.is_empty() {
                println!("\nRestoring tmux sessions...");
                let use_wt = std::env::var("WT_SESSION").is_ok();
                for (vm_name, sessions) in &tmux_sessions {
                    if let Some(first_session) = sessions.first() {
                        if use_wt {
                            println!("  Opening tab: {} (session: {})", vm_name, first_session);
                            let _ = std::process::Command::new("wt.exe")
                                .args([
                                    "-w",
                                    "0",
                                    "new-tab",
                                    "azlin",
                                    "connect",
                                    vm_name,
                                    "--tmux-session",
                                    first_session,
                                ])
                                .spawn();
                        } else {
                            println!("  Connecting to {} (session: {})", vm_name, first_session);
                            let _ = std::process::Command::new("azlin")
                                .args(["connect", vm_name, "--tmux-session", first_session])
                                .spawn();
                        }
                    }
                }
                println!("Session restore initiated.");
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
