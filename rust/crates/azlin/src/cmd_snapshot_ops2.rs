#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use dialoguer::Confirm;
pub(crate) async fn handle_snapshot_delete(
    snapshot_name: &str,
    force: bool,
    rg: &str,
) -> Result<()> {
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
            rg,
            "--name",
            snapshot_name,
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
    Ok(())
}

pub(crate) fn handle_snapshot_enable(vm_name: &str, rg: &str, every: u32, keep: u32) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: vm_name.to_string(),
        resource_group: rg.to_string(),
        every_hours: every,
        keep_count: keep,
        enabled: true,
        created: chrono::Utc::now().to_rfc3339(),
    };
    crate::snapshot_helpers::save_schedule(&schedule)?;
    println!(
        "{}",
        crate::handlers::build_snapshot_enable_output(vm_name, rg, every, keep)
    );
    Ok(())
}

pub(crate) fn handle_snapshot_disable(vm_name: &str) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let path = crate::snapshot_helpers::schedule_path(vm_name);
    if let Some(mut sched) = crate::snapshot_helpers::load_schedule(vm_name) {
        sched.enabled = false;
        crate::snapshot_helpers::save_schedule(&sched)?;
        println!(
            "{}",
            crate::handlers::build_snapshot_disable_output(vm_name, true)
        );
    } else if path.exists() {
        std::fs::remove_file(&path)?;
        println!(
            "{}",
            crate::handlers::build_snapshot_disable_output(vm_name, true)
        );
    } else {
        println!(
            "{}",
            crate::handlers::build_snapshot_disable_output(vm_name, false)
        );
    }
    Ok(())
}

pub(crate) async fn handle_snapshot_sync(vm: Option<&str>, _rg: &str) -> Result<()> {
    let schedules = match vm {
        Some(name) => crate::snapshot_helpers::load_schedule(name)
            .into_iter()
            .collect::<Vec<_>>(),
        None => crate::snapshot_helpers::load_all_schedules(),
    };
    let enabled: Vec<_> = schedules.iter().filter(|s| s.enabled).collect();
    if enabled.is_empty() {
        println!("No enabled snapshot schedules found.");
        return Ok(());
    }

    for sched in &enabled {
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
            let filtered = crate::snapshot_helpers::filter_snapshots(&all_snaps, &sched.vm_name);
            let (needed, skip_msg) = crate::handlers::check_snapshot_sync_needed(
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
            let snap_name = crate::snapshot_helpers::build_snapshot_name(&sched.vm_name, &ts);

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Creating snapshot {}...", snap_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let disk_info =
                crate::dispatch_helpers::lookup_vm_disk_info(&sched.resource_group, &sched.vm_name);

            let (disk_id, location) = match disk_info {
                Ok(info) => info,
                Err(e) => {
                    pb.finish_and_clear();
                    eprintln!("Failed to get disk ID for VM '{}': {}", sched.vm_name, e);
                    continue;
                }
            };

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
                    "--location",
                    &location,
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
                let stderr = String::from_utf8_lossy(&create_output.stderr);
                eprintln!(
                    "Failed to create snapshot for VM '{}': {}",
                    sched.vm_name,
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
        }
    }
    println!("{}", crate::handlers::format_snapshot_sync_complete(vm));
    Ok(())
}

pub(crate) fn handle_snapshot_status(vm_name: &str) -> Result<()> {
    match crate::snapshot_helpers::load_schedule(vm_name) {
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
            println!("{}", crate::handlers::format_snapshot_no_schedule(vm_name));
        }
    }
    Ok(())
}
