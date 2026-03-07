#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use dialoguer::Confirm;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Snapshot { action } => {
            let rg = match &action {
                azlin_cli::SnapshotAction::Create { resource_group, .. }
                | azlin_cli::SnapshotAction::List { resource_group, .. }
                | azlin_cli::SnapshotAction::Restore { resource_group, .. }
                | azlin_cli::SnapshotAction::Delete { resource_group, .. }
                | azlin_cli::SnapshotAction::Enable { resource_group, .. }
                | azlin_cli::SnapshotAction::Disable { resource_group, .. }
                | azlin_cli::SnapshotAction::Sync { resource_group, .. }
                | azlin_cli::SnapshotAction::Status { resource_group, .. } => {
                    resolve_resource_group(resource_group.clone())?
                }
            };

            match action {
                azlin_cli::SnapshotAction::Create { vm_name, .. } => {
                    let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
                    let snapshot_name = crate::snapshot_helpers::build_snapshot_name(&vm_name, &ts);
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Creating snapshot {}...", snapshot_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "create",
                            "--resource-group",
                            &rg,
                            "--source-disk",
                            &format!("{}_OsDisk", vm_name),
                            "--name",
                            &snapshot_name,
                            "--output",
                            "json",
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        println!("Created snapshot '{}'", snapshot_name);
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to create snapshot: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::List { vm_name, .. } => {
                    let output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "list",
                            "--resource-group",
                            &rg,
                            "--output",
                            "json",
                        ])
                        .output()?;

                    if output.status.success() {
                        let snapshots: Vec<serde_json::Value> =
                            serde_json::from_slice(&output.stdout)
                                .context("Failed to parse snapshot list JSON")?;
                        let filtered =
                            crate::snapshot_helpers::filter_snapshots(&snapshots, &vm_name);

                        if filtered.is_empty() {
                            println!("No snapshots found for VM '{}'.", vm_name);
                        } else {
                            let mut table = Table::new();
                            table
                                .load_preset(UTF8_FULL)
                                .apply_modifier(UTF8_ROUND_CORNERS)
                                .set_header(vec![
                                    "Name",
                                    "Disk Size (GB)",
                                    "Time Created",
                                    "State",
                                ]);
                            for snap in &filtered {
                                let row = crate::snapshot_helpers::snapshot_row(snap);
                                table.add_row(row);
                            }
                            println!("{table}");
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to list snapshots: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Restore {
                    vm_name,
                    snapshot_name,
                    force,
                    ..
                } => {
                    if !force {
                        let confirmed = Confirm::new()
                            .with_prompt(format!(
                                "Restore VM '{}' from snapshot '{}'? This will replace the current disk.",
                                vm_name, snapshot_name
                            ))
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Restoring {} from {}...", vm_name, snapshot_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let snap_output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "show",
                            "--resource-group",
                            &rg,
                            "--name",
                            &snapshot_name,
                            "--query",
                            "id",
                            "--output",
                            "tsv",
                        ])
                        .output()?;

                    if !snap_output.status.success() {
                        pb.finish_and_clear();
                        anyhow::bail!("Snapshot '{}' not found.", snapshot_name);
                    }

                    let snap_id = String::from_utf8_lossy(&snap_output.stdout)
                        .trim()
                        .to_string();
                    let new_disk = format!("{}_OsDisk_restored", vm_name);

                    let disk_output = std::process::Command::new("az")
                        .args([
                            "disk",
                            "create",
                            "--resource-group",
                            &rg,
                            "--name",
                            &new_disk,
                            "--source",
                            &snap_id,
                            "--output",
                            "json",
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if disk_output.status.success() {
                        println!(
                            "Restored disk '{}' from snapshot '{}'",
                            new_disk, snapshot_name
                        );
                        // Step 3: Deallocate the VM so we can swap the OS disk
                        let pb2 = indicatif::ProgressBar::new_spinner();
                        pb2.set_message(format!("Deallocating VM '{}'...", vm_name));
                        pb2.enable_steady_tick(std::time::Duration::from_millis(100));
                        let dealloc = std::process::Command::new("az")
                            .args([
                                "vm",
                                "deallocate",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                            ])
                            .output()?;
                        pb2.finish_and_clear();
                        if !dealloc.status.success() {
                            let stderr = String::from_utf8_lossy(&dealloc.stderr);
                            anyhow::bail!(
                                "Failed to deallocate VM: {}\n\
                                 Manual swap: az vm update --resource-group {} --name {} --os-disk {}",
                                azlin_core::sanitizer::sanitize(stderr.trim()),
                                rg, vm_name, new_disk
                            );
                        }

                        // Step 4: Swap the OS disk
                        let pb3 = indicatif::ProgressBar::new_spinner();
                        pb3.set_message("Swapping OS disk...");
                        pb3.enable_steady_tick(std::time::Duration::from_millis(100));
                        let swap = std::process::Command::new("az")
                            .args([
                                "vm",
                                "update",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                                "--os-disk",
                                &new_disk,
                                "--output",
                                "json",
                            ])
                            .output()?;
                        pb3.finish_and_clear();
                        if !swap.status.success() {
                            let stderr = String::from_utf8_lossy(&swap.stderr);
                            anyhow::bail!(
                                "Failed to swap OS disk: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }

                        // Step 5: Start the VM back up
                        let pb4 = indicatif::ProgressBar::new_spinner();
                        pb4.set_message(format!("Starting VM '{}'...", vm_name));
                        pb4.enable_steady_tick(std::time::Duration::from_millis(100));
                        let start = std::process::Command::new("az")
                            .args(["vm", "start", "--resource-group", &rg, "--name", &vm_name])
                            .output()?;
                        pb4.finish_and_clear();
                        if start.status.success() {
                            println!(
                                "Restored VM '{}' from snapshot '{}' and restarted.",
                                vm_name, snapshot_name
                            );
                        } else {
                            let stderr = String::from_utf8_lossy(&start.stderr);
                            eprintln!(
                                "VM restored but failed to restart: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&disk_output.stderr);
                        anyhow::bail!(
                            "Failed to restore: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Delete {
                    snapshot_name,
                    force,
                    ..
                } => {
                    if !force {
                        let confirmed = Confirm::new()
                            .with_prompt(format!(
                                "Delete snapshot '{}'? This cannot be undone.",
                                snapshot_name
                            ))
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Deleting snapshot {}...", snapshot_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "delete",
                            "--resource-group",
                            &rg,
                            "--name",
                            &snapshot_name,
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        println!("Deleted snapshot '{}'", snapshot_name);
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to delete snapshot: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Enable {
                    vm_name,
                    every,
                    keep,
                    ..
                } => {
                    if let Err(e) = crate::name_validation::validate_name(&vm_name) {
                        anyhow::bail!("Invalid VM name: {}", e);
                    }
                    let schedule = crate::snapshot_helpers::SnapshotSchedule {
                        vm_name: vm_name.clone(),
                        resource_group: rg.clone(),
                        every_hours: every,
                        keep_count: keep,
                        enabled: true,
                        created: chrono::Utc::now().to_rfc3339(),
                    };
                    crate::snapshot_helpers::save_schedule(&schedule)?;
                    println!(
                        "{}",
                        crate::handlers::build_snapshot_enable_output(&vm_name, &rg, every, keep)
                    );
                }
                azlin_cli::SnapshotAction::Disable { vm_name, .. } => {
                    if let Err(e) = crate::name_validation::validate_name(&vm_name) {
                        anyhow::bail!("Invalid VM name: {}", e);
                    }
                    let path = crate::snapshot_helpers::schedule_path(&vm_name);
                    if let Some(mut sched) = crate::snapshot_helpers::load_schedule(&vm_name) {
                        sched.enabled = false;
                        crate::snapshot_helpers::save_schedule(&sched)?;
                        println!(
                            "{}",
                            crate::handlers::build_snapshot_disable_output(&vm_name, true)
                        );
                    } else if path.exists() {
                        std::fs::remove_file(&path)?;
                        println!(
                            "{}",
                            crate::handlers::build_snapshot_disable_output(&vm_name, true)
                        );
                    } else {
                        println!(
                            "{}",
                            crate::handlers::build_snapshot_disable_output(&vm_name, false)
                        );
                    }
                }
                azlin_cli::SnapshotAction::Sync { vm, .. } => {
                    let schedules = match &vm {
                        Some(name) => crate::snapshot_helpers::load_schedule(name)
                            .into_iter()
                            .collect::<Vec<_>>(),
                        None => crate::snapshot_helpers::load_all_schedules(),
                    };
                    let enabled: Vec<_> = schedules.iter().filter(|s| s.enabled).collect();
                    if enabled.is_empty() {
                        println!("No enabled snapshot schedules found.");
                    } else {
                        for sched in &enabled {
                            // List existing snapshots for this VM to find the most recent
                            let list_output = std::process::Command::new("az")
                                .args([
                                    "snapshot",
                                    "list",
                                    "--resource-group",
                                    &sched.resource_group,
                                    "--output",
                                    "json",
                                ])
                                .output()?;

                            let mut needs_snapshot = true;
                            if list_output.status.success() {
                                let all_snaps: Vec<serde_json::Value> =
                                    serde_json::from_slice(&list_output.stdout).unwrap_or_default();
                                let filtered = crate::snapshot_helpers::filter_snapshots(
                                    &all_snaps,
                                    &sched.vm_name,
                                );
                                let (needed, skip_msg) =
                                    crate::handlers::check_snapshot_sync_needed(
                                        &filtered,
                                        &sched.vm_name,
                                        sched.every_hours,
                                        chrono::Utc::now(),
                                    );
                                needs_snapshot = needed;
                                if let Some(msg) = skip_msg {
                                    println!("{}", msg);
                                }
                            }

                            if needs_snapshot {
                                let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
                                let snap_name = crate::snapshot_helpers::build_snapshot_name(
                                    &sched.vm_name,
                                    &ts,
                                );

                                let pb = indicatif::ProgressBar::new_spinner();
                                pb.set_message(format!("Creating snapshot {}...", snap_name));
                                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                                let disk_id_output = std::process::Command::new("az")
                                    .args([
                                        "vm",
                                        "show",
                                        "--resource-group",
                                        &sched.resource_group,
                                        "--name",
                                        &sched.vm_name,
                                        "--query",
                                        "storageProfile.osDisk.managedDisk.id",
                                        "--output",
                                        "tsv",
                                    ])
                                    .output()?;

                                if !disk_id_output.status.success() {
                                    pb.finish_and_clear();
                                    eprintln!(
                                        "Failed to get disk ID for VM '{}': {}",
                                        sched.vm_name,
                                        String::from_utf8_lossy(&disk_id_output.stderr).trim()
                                    );
                                    continue;
                                }

                                let disk_id = String::from_utf8_lossy(&disk_id_output.stdout)
                                    .trim()
                                    .to_string();

                                let create_output = std::process::Command::new("az")
                                    .args([
                                        "snapshot",
                                        "create",
                                        "--resource-group",
                                        &sched.resource_group,
                                        "--name",
                                        &snap_name,
                                        "--source",
                                        &disk_id,
                                        "--output",
                                        "json",
                                    ])
                                    .output()?;

                                pb.finish_and_clear();
                                if create_output.status.success() {
                                    println!(
                                        "Created snapshot '{}' for VM '{}'",
                                        snap_name, sched.vm_name
                                    );
                                } else {
                                    eprintln!(
                                        "Failed to create snapshot for VM '{}': {}",
                                        sched.vm_name,
                                        String::from_utf8_lossy(&create_output.stderr).trim()
                                    );
                                }
                            }
                        }
                        println!(
                            "{}",
                            crate::handlers::format_snapshot_sync_complete(vm.as_deref())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Status { vm_name, .. } => {
                    match crate::snapshot_helpers::load_schedule(&vm_name) {
                        Some(sched) => {
                            let info = crate::handlers::SnapshotScheduleInfo {
                                vm_name: sched.vm_name.clone(),
                                resource_group: sched.resource_group.clone(),
                                every_hours: sched.every_hours,
                                keep_count: sched.keep_count,
                                enabled: sched.enabled,
                                created: sched.created.clone(),
                            };
                            println!("{}", crate::handlers::format_snapshot_status(&info));
                        }
                        None => {
                            println!("{}", crate::handlers::format_snapshot_no_schedule(&vm_name));
                        }
                    }
                }
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
