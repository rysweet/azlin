#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use azlin_azure::orphan_detector::{OrphanedResource, ResourceType};

pub(crate) fn handle_cleanup(
    resource_group: Option<String>,
    dry_run: bool,
    force: bool,
    age_days: u32,
) -> Result<()> {
    use azlin_azure::orphan_detector::{
        find_orphaned_disks, format_orphan_summary, OrphanedResource, ResourceType,
    };

    let rg = resolve_resource_group(resource_group)?;

    println!(
        "{}",
        crate::handlers::format_cleanup_scan_header(&rg, age_days, dry_run)
    );

    let az_list = |args: &[&str]| -> Result<String> {
        let output = std::process::Command::new("az")
            .args(args)
            .args(["-g", &rg, "-o", "json"])
            .output()?;
        if !output.status.success() {
            let err = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!(
                "az command failed: {}",
                azlin_core::sanitizer::sanitize(err.trim())
            );
        }
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    };

    let mut all_orphans: Vec<OrphanedResource> = Vec::new();

    // 1) Orphaned disks
    let disk_json =
        az_list(&["disk", "list"]).context("Failed to list disks for orphan detection")?;
    all_orphans.extend(find_orphaned_disks(&disk_json)?);

    // 2) Orphaned NICs
    let nic_json =
        az_list(&["network", "nic", "list"]).context("Failed to list NICs for orphan detection")?;
    let nics: Vec<serde_json::Value> =
        serde_json::from_str(&nic_json).context("Failed to parse NIC list JSON")?;
    for nic in &nics {
        // Shares `nic_is_unassociated` with the teardown planner. Checking
        // `virtualMachine` alone flags private-endpoint NICs, which Azure then
        // refuses to delete on every run.
        if azlin_azure::teardown::nic_is_unassociated(nic) {
            if let Some(name) = nic.get("name").and_then(|n| n.as_str()) {
                let nic_rg = nic
                    .get("resourceGroup")
                    .and_then(|r| r.as_str())
                    .unwrap_or("unknown");
                all_orphans.push(OrphanedResource {
                    name: name.to_string(),
                    resource_type: ResourceType::NetworkInterface,
                    resource_group: nic_rg.to_string(),
                    estimated_monthly_cost: 0.0,
                });
            }
        }
    }

    // 3) Orphaned public IPs
    //
    // Shares `public_ip_is_unassociated` with the teardown planner so the two
    // paths cannot drift apart.
    let pip_json = az_list(&["network", "public-ip", "list"])
        .context("Failed to list public IPs for orphan detection")?;
    let ips: Vec<serde_json::Value> =
        serde_json::from_str(&pip_json).context("Failed to parse public IP list JSON")?;
    for ip in &ips {
        if azlin_azure::teardown::public_ip_is_unassociated(ip) {
            if let Some(name) = ip.get("name").and_then(|n| n.as_str()) {
                let ip_rg = ip
                    .get("resourceGroup")
                    .and_then(|r| r.as_str())
                    .unwrap_or("unknown");
                all_orphans.push(OrphanedResource {
                    name: name.to_string(),
                    resource_type: ResourceType::PublicIp,
                    resource_group: ip_rg.to_string(),
                    estimated_monthly_cost: ORPHANED_PUBLIC_IP_MONTHLY_COST,
                });
            }
        }
    }

    // 4) Orphaned NSGs
    //
    // Shares `nsg_is_unassociated` with the teardown planner.
    let nsg_json =
        az_list(&["network", "nsg", "list"]).context("Failed to list NSGs for orphan detection")?;
    let nsgs: Vec<serde_json::Value> =
        serde_json::from_str(&nsg_json).context("Failed to parse NSG list JSON")?;
    for nsg in &nsgs {
        if azlin_azure::teardown::nsg_is_unassociated(nsg) {
            if let Some(name) = nsg.get("name").and_then(|n| n.as_str()) {
                let nsg_rg = nsg
                    .get("resourceGroup")
                    .and_then(|r| r.as_str())
                    .unwrap_or("unknown");
                all_orphans.push(OrphanedResource {
                    name: name.to_string(),
                    resource_type: ResourceType::NetworkSecurityGroup,
                    resource_group: nsg_rg.to_string(),
                    estimated_monthly_cost: 0.0,
                });
            }
        }
    }

    if all_orphans.is_empty() {
        println!("{}", format_orphan_summary(&[]));
        return Ok(());
    }

    let mut table = crate::table_render::SimpleTable::new(
        &["Type", "Name", "Resource Group", "Est. Cost/mo"],
        &[22, 30, 20, 12],
    );
    for r in &all_orphans {
        table.add_row(vec![
            format!("{}", r.resource_type),
            r.name.clone(),
            r.resource_group.clone(),
            format!("${:.2}", r.estimated_monthly_cost),
        ]);
    }
    println!("{table}");
    println!("{}", format_orphan_summary(&all_orphans));

    if dry_run {
        println!("Dry run complete -- no resources were deleted.");
        return Ok(());
    }

    if !safe_confirm(
        &format!(
            "Delete {} orphaned resource(s) in '{}'?",
            all_orphans.len(),
            rg
        ),
        force,
    )? {
        println!("Cancelled.");
        return Ok(());
    }

    let mut deleted = 0usize;
    let mut deleted_nics = false;
    for r in &all_orphans {
        let result = match r.resource_type {
            ResourceType::Disk => std::process::Command::new("az")
                .args([
                    "disk",
                    "delete",
                    "--name",
                    &r.name,
                    "-g",
                    &r.resource_group,
                    "--yes",
                    "--no-wait",
                ])
                .output(),
            // Deliberately NOT --no-wait: the recheck pass below re-lists NSGs
            // to find ones freed by these deletions, and that only works once
            // the NIC is actually gone.
            ResourceType::NetworkInterface => std::process::Command::new("az")
                .args([
                    "network",
                    "nic",
                    "delete",
                    "--name",
                    &r.name,
                    "-g",
                    &r.resource_group,
                ])
                .output(),
            ResourceType::PublicIp => std::process::Command::new("az")
                .args([
                    "network",
                    "public-ip",
                    "delete",
                    "--name",
                    &r.name,
                    "-g",
                    &r.resource_group,
                ])
                .output(),
            ResourceType::NetworkSecurityGroup => std::process::Command::new("az")
                .args([
                    "network",
                    "nsg",
                    "delete",
                    "--name",
                    &r.name,
                    "-g",
                    &r.resource_group,
                ])
                .output(),
        };
        match result {
            Ok(o) if o.status.success() => {
                deleted += 1;
                if r.resource_type == ResourceType::NetworkInterface {
                    deleted_nics = true;
                }
                println!("  Deleted {} '{}'", r.resource_type, r.name);
            }
            Ok(o) => {
                let err = String::from_utf8_lossy(&o.stderr);
                eprintln!(
                    "  Failed to delete {} '{}': {}",
                    r.resource_type,
                    r.name,
                    err.trim()
                );
            }
            Err(e) => {
                eprintln!("  Failed to delete {} '{}': {}", r.resource_type, r.name, e);
            }
        }
    }
    // ── Recheck pass ────────────────────────────────────────────────────
    //
    // Association is computed before anything is deleted, so a resource whose
    // only referent is *also* being deleted in this run is never listed. The
    // concrete case: an NSG attached to an orphaned NIC. The NIC is correctly
    // detected, the NSG is skipped as "in use", and after the run the NSG is
    // still there — with nothing left referencing it. It can never be
    // collected, because every future run reaches the same conclusion.
    //
    // `destroy` already solves this with a second planning pass (added in
    // #1071 for the NIC -> NSG ordering). `cleanup` had no equivalent, so
    // clearing an NSG took two manual invocations, which is exactly how the
    // leaked `devNSG`/`ia3NSG`/`devaNSG` survived.
    let freed = if deleted_nics {
        recheck_freed_resources(&rg)?
    } else {
        Vec::new()
    };
    let mut freed_deleted = 0usize;
    for r in &freed {
        let result = delete_orphan(r);
        match result {
            Ok(o) if o.status.success() => {
                freed_deleted += 1;
                println!(
                    "  Deleted {} '{}' (freed by this run)",
                    r.resource_type, r.name
                );
            }
            Ok(o) => eprintln!(
                "  Failed to delete {} '{}': {}",
                r.resource_type,
                r.name,
                String::from_utf8_lossy(&o.stderr).trim()
            ),
            Err(e) => eprintln!("  Failed to delete {} '{}': {}", r.resource_type, r.name, e),
        }
    }

    println!(
        "{}",
        crate::handlers::format_cleanup_complete(
            deleted + freed_deleted,
            all_orphans.len() + freed.len()
        )
    );
    Ok(())
}

/// Re-scan for NSGs and Public IPs that became unassociated during this run.
///
/// Only called when at least one NIC was deleted, since that is the only
/// deletion here that can free another resource.
fn recheck_freed_resources(rg: &str) -> Result<Vec<OrphanedResource>> {
    let az_list = |args: &[&str]| -> Result<String> {
        let out = std::process::Command::new("az")
            .args(args)
            .args(["-g", rg, "-o", "json"])
            .output()?;
        Ok(String::from_utf8_lossy(&out.stdout).to_string())
    };
    let mut freed = Vec::new();

    let nsg_json = az_list(&["network", "nsg", "list"])?;
    if let Ok(nsgs) = serde_json::from_str::<Vec<serde_json::Value>>(&nsg_json) {
        for nsg in &nsgs {
            if azlin_azure::teardown::nsg_is_unassociated(nsg) {
                if let Some(name) = nsg.get("name").and_then(|n| n.as_str()) {
                    freed.push(OrphanedResource {
                        name: name.to_string(),
                        resource_type: ResourceType::NetworkSecurityGroup,
                        resource_group: nsg
                            .get("resourceGroup")
                            .and_then(|r| r.as_str())
                            .unwrap_or(rg)
                            .to_string(),
                        estimated_monthly_cost: 0.0,
                    });
                }
            }
        }
    }

    let pip_json = az_list(&["network", "public-ip", "list"])?;
    if let Ok(ips) = serde_json::from_str::<Vec<serde_json::Value>>(&pip_json) {
        for ip in &ips {
            if azlin_azure::teardown::public_ip_is_unassociated(ip) {
                if let Some(name) = ip.get("name").and_then(|n| n.as_str()) {
                    freed.push(OrphanedResource {
                        name: name.to_string(),
                        resource_type: ResourceType::PublicIp,
                        resource_group: ip
                            .get("resourceGroup")
                            .and_then(|r| r.as_str())
                            .unwrap_or(rg)
                            .to_string(),
                        estimated_monthly_cost: ORPHANED_PUBLIC_IP_MONTHLY_COST,
                    });
                }
            }
        }
    }
    Ok(freed)
}

/// Issue the delete for one orphaned resource.
fn delete_orphan(r: &OrphanedResource) -> std::io::Result<std::process::Output> {
    match r.resource_type {
        ResourceType::Disk => std::process::Command::new("az")
            .args([
                "disk",
                "delete",
                "--name",
                &r.name,
                "-g",
                &r.resource_group,
                "--yes",
                "--no-wait",
            ])
            .output(),
        ResourceType::NetworkInterface => std::process::Command::new("az")
            .args([
                "network",
                "nic",
                "delete",
                "--name",
                &r.name,
                "-g",
                &r.resource_group,
            ])
            .output(),
        ResourceType::PublicIp => std::process::Command::new("az")
            .args([
                "network",
                "public-ip",
                "delete",
                "--name",
                &r.name,
                "-g",
                &r.resource_group,
            ])
            .output(),
        ResourceType::NetworkSecurityGroup => std::process::Command::new("az")
            .args([
                "network",
                "nsg",
                "delete",
                "--name",
                &r.name,
                "-g",
                &r.resource_group,
            ])
            .output(),
    }
}

pub(crate) async fn handle_restore(
    resource_group: Option<String>,
    verbose: bool,
    skip_health_check: bool,
    force: bool,
    terminal: Option<String>,
    exclude: Option<String>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    println!("Restoring azlin sessions in '{}'...", rg);
    if verbose {
        println!("  skip_health_check: {}", skip_health_check);
        println!("  force: {}", force);
        if let Some(ref t) = terminal {
            println!("  terminal: {}", t);
        }
        if let Some(ref e) = exclude {
            println!("  exclude: {}", e);
        }
    }

    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let vms = vm_manager.list_vms(&rg)?;

    let mut running: Vec<_> = vms
        .iter()
        .filter(|v| {
            if force {
                true
            } else {
                v.power_state == azlin_core::models::PowerState::Running
            }
        })
        .cloned()
        .collect();

    if let Some(ref pattern) = exclude {
        running.retain(|v| !v.name.contains(pattern.as_str()));
        if verbose {
            println!(
                "After excluding '{}': {} VM(s) remaining",
                pattern,
                running.len()
            );
        }
    }

    if running.is_empty() {
        if force {
            println!("No VMs found in '{}'.", rg);
        } else {
            println!("No running VMs found in '{}'.", rg);
        }
        return Ok(());
    }

    if verbose {
        println!("Found {} VM(s):", running.len());
        for vm in &running {
            println!("  - {} ({})", vm.name, vm.power_state);
        }
        println!("Collecting tmux sessions...");
    } else {
        println!(
            "Found {} running VM(s), collecting tmux sessions...",
            running.len()
        );
    }

    let ssh_timeout = azlin_core::AzlinConfig::load()
        .unwrap_or_default()
        .ssh_connect_timeout;
    let tmux_sessions = crate::cmd_list_data::collect_tmux_sessions(
        &running,
        &rg,
        verbose,
        vm_manager.subscription_id(),
        ssh_timeout,
    )
    .await;

    if tmux_sessions.is_empty() {
        println!("No active tmux sessions found on running VMs.");
        println!("Use 'azlin connect <vm-name>' to start a new session.");
        return Ok(());
    }

    if verbose {
        println!("Found sessions on {} VM(s):", tmux_sessions.len());
        for (vm, sessions) in &tmux_sessions {
            println!("  {}: {:?}", vm, sessions);
        }
    }

    crate::cmd_list_data::restore_tmux_sessions(&tmux_sessions);
    Ok(())
}
