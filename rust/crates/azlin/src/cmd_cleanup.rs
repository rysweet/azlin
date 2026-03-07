#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Table};
use dialoguer::Confirm;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Cleanup {
            resource_group,
            dry_run,
            force,
            age_days,
            ..
        } => {
            use azlin_azure::orphan_detector::{
                find_orphaned_disks, format_orphan_summary, OrphanedResource, ResourceType,
            };

            let rg = resolve_resource_group(resource_group)?;

            println!(
                "{}",
                crate::handlers::format_cleanup_scan_header(&rg, age_days, dry_run)
            );

            // Helper: run an az CLI query and return stdout as String
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

            // 2) Orphaned NICs (no VM attached)
            let nic_json = az_list(&["network", "nic", "list"])
                .context("Failed to list NICs for orphan detection")?;
            let nics: Vec<serde_json::Value> =
                serde_json::from_str(&nic_json).context("Failed to parse NIC list JSON")?;
            for nic in &nics {
                let attached = nic
                    .get("virtualMachine")
                    .map(|v| !v.is_null())
                    .unwrap_or(false);
                if !attached {
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

            // 3) Orphaned public IPs (no ipConfiguration)
            let pip_json = az_list(&["network", "public-ip", "list"])
                .context("Failed to list public IPs for orphan detection")?;
            let ips: Vec<serde_json::Value> =
                serde_json::from_str(&pip_json).context("Failed to parse public IP list JSON")?;
            for ip in &ips {
                let attached = ip
                    .get("ipConfiguration")
                    .map(|v| !v.is_null())
                    .unwrap_or(false);
                if !attached {
                    if let Some(name) = ip.get("name").and_then(|n| n.as_str()) {
                        let ip_rg = ip
                            .get("resourceGroup")
                            .and_then(|r| r.as_str())
                            .unwrap_or("unknown");
                        all_orphans.push(OrphanedResource {
                            name: name.to_string(),
                            resource_type: ResourceType::PublicIp,
                            resource_group: ip_rg.to_string(),
                            // Azure Standard public IP ~$3.65/month
                            estimated_monthly_cost: ORPHANED_PUBLIC_IP_MONTHLY_COST,
                        });
                    }
                }
            }

            // 4) Orphaned NSGs (no attached NICs or subnets)
            let nsg_json = az_list(&["network", "nsg", "list"])
                .context("Failed to list NSGs for orphan detection")?;
            let nsgs: Vec<serde_json::Value> =
                serde_json::from_str(&nsg_json).context("Failed to parse NSG list JSON")?;
            for nsg in &nsgs {
                let has_nics = nsg
                    .get("networkInterfaces")
                    .and_then(|v| v.as_array())
                    .map(|a| !a.is_empty())
                    .unwrap_or(false);
                let has_subnets = nsg
                    .get("subnets")
                    .and_then(|v| v.as_array())
                    .map(|a| !a.is_empty())
                    .unwrap_or(false);
                if !has_nics && !has_subnets {
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

            // Display findings in a table
            let mut table = Table::new();
            table
                .load_preset(UTF8_FULL)
                .apply_modifier(UTF8_ROUND_CORNERS)
                .set_header(vec![
                    Cell::new("Type").add_attribute(Attribute::Bold),
                    Cell::new("Name").add_attribute(Attribute::Bold),
                    Cell::new("Resource Group").add_attribute(Attribute::Bold),
                    Cell::new("Est. Cost/mo").add_attribute(Attribute::Bold),
                ]);
            for r in &all_orphans {
                table.add_row(vec![
                    Cell::new(format!("{}", r.resource_type)),
                    Cell::new(&r.name),
                    Cell::new(&r.resource_group),
                    Cell::new(format!("${:.2}", r.estimated_monthly_cost)),
                ]);
            }
            println!("{table}");
            println!("{}", format_orphan_summary(&all_orphans));

            if dry_run {
                println!("Dry run complete — no resources were deleted.");
                return Ok(());
            }

            if !force {
                let ok = Confirm::new()
                    .with_prompt(format!(
                        "Delete {} orphaned resource(s) in '{}'?",
                        all_orphans.len(),
                        rg
                    ))
                    .default(false)
                    .interact()?;
                if !ok {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            // Delete orphaned resources
            let mut deleted = 0usize;
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
                    ResourceType::NetworkInterface => std::process::Command::new("az")
                        .args([
                            "network",
                            "nic",
                            "delete",
                            "--name",
                            &r.name,
                            "-g",
                            &r.resource_group,
                            "--no-wait",
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
                        println!("  ✓ Deleted {} '{}'", r.resource_type, r.name);
                    }
                    Ok(o) => {
                        let err = String::from_utf8_lossy(&o.stderr);
                        eprintln!(
                            "  ✗ Failed to delete {} '{}': {}",
                            r.resource_type,
                            r.name,
                            err.trim()
                        );
                    }
                    Err(e) => {
                        eprintln!(
                            "  ✗ Failed to delete {} '{}': {}",
                            r.resource_type, r.name, e
                        );
                    }
                }
            }
            println!(
                "{}",
                crate::handlers::format_cleanup_complete(deleted, all_orphans.len())
            );
        }

        // ── Help ─────────────────────────────────────────────────────
        // ── Bastion ───────────────────────────────────────────────────
        azlin_cli::Commands::Costs { action } => {
            crate::cmd_cleanup_costs::dispatch_costs(action)?;
        }

        // ── Killall ──────────────────────────────────────────────────
        azlin_cli::Commands::Restore { resource_group, .. } => {
            let rg = resolve_resource_group(resource_group)?;
            println!("Restoring azlin sessions in '{}'...", rg);

            // Find running VMs with session tags
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let vms = vm_manager.list_vms(&rg)?;
            let running: Vec<_> = vms
                .iter()
                .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
                .collect();

            if running.is_empty() {
                println!("No running VMs found in '{}'.", rg);
                return Ok(());
            }

            println!("Found {} running VM(s):", running.len());
            for vm in &running {
                let session = vm
                    .tags
                    .get("azlin-session")
                    .map(|s| s.as_str())
                    .unwrap_or("-");
                let ip = vm
                    .public_ip
                    .as_deref()
                    .or(vm.private_ip.as_deref())
                    .unwrap_or("no-ip");
                println!("  {} (session: {}, ip: {})", vm.name, session, ip);
            }
            println!("Session restore complete. Use 'azlin connect <vm-name>' to reconnect.");
        }

        // ── Sessions ─────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
