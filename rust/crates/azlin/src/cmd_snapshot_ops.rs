#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn handle_snapshot_create(vm_name: &str, rg: &str) -> Result<()> {
    let (disk_id, location) = crate::dispatch_helpers::lookup_vm_disk_info(rg, vm_name)?;

    let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
    let snapshot_name = crate::snapshot_helpers::build_snapshot_name(vm_name, &ts);
    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message(format!("Creating snapshot {}...", snapshot_name));
    pb.enable_steady_tick(std::time::Duration::from_millis(100));

    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "create",
            "--resource-group",
            rg,
            "--source",
            &disk_id,
            "--name",
            &snapshot_name,
            "--location",
            &location,
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
    Ok(())
}

pub(crate) async fn handle_snapshot_list(vm_name: &str, rg: &str) -> Result<()> {
    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let snapshots: Vec<serde_json::Value> =
            serde_json::from_slice(&output.stdout).context("Failed to parse snapshot list JSON")?;
        let filtered = crate::snapshot_helpers::filter_snapshots(&snapshots, vm_name);

        if filtered.is_empty() {
            println!("No snapshots found for VM '{}'.", vm_name);
        } else {
            let mut table = new_table(
                &["Name", "Disk Size (GB)", "Time Created", "State"],
                &[35, 14, 22, 10],
            );
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
    Ok(())
}

pub(crate) async fn handle_snapshot_restore(
    vm_name: &str,
    snapshot_name: &str,
    force: bool,
    rg: &str,
) -> Result<()> {
    if !safe_confirm(
        &format!(
            "Restore VM '{}' from snapshot '{}'? This will replace the current disk.",
            vm_name, snapshot_name
        ),
        force,
    )? {
        println!("Cancelled.");
        return Ok(());
    }

    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message(format!("Restoring {} from {}...", vm_name, snapshot_name));
    pb.enable_steady_tick(std::time::Duration::from_millis(100));

    let snap_output = std::process::Command::new("az")
        .args([
            "snapshot",
            "show",
            "--resource-group",
            rg,
            "--name",
            snapshot_name,
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
            rg,
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
                rg,
                "--name",
                vm_name,
            ])
            .output()?;
        pb2.finish_and_clear();
        if !dealloc.status.success() {
            let stderr = String::from_utf8_lossy(&dealloc.stderr);
            anyhow::bail!(
                "Failed to deallocate VM: {}\n\
                 Manual swap: az vm update --resource-group {} --name {} --os-disk {}",
                azlin_core::sanitizer::sanitize(stderr.trim()),
                rg,
                vm_name,
                new_disk
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
                rg,
                "--name",
                vm_name,
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
            .args(["vm", "start", "--resource-group", rg, "--name", vm_name])
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
    Ok(())
}
