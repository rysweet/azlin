//! `azlin disk check` and `azlin disk repair` (issue #1131).
//!
//! The defect was not only that cloud-init left the data disks unformatted. It
//! was that nothing said so: `azlin list` reported the VM Running and healthy
//! for weeks while 1.2 TB of attached, billed Premium SSD sat unused and `/`
//! ran at 98%. These two commands make the condition askable and fixable
//! without reprovisioning.
//!
//! The layout they compare against lives in `azlin_azure::disk_layout`, shared
//! with the cloud-init generator, so a detector cannot drift from the thing it
//! detects.

#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use azlin_azure::cloud_init::DiskConfig;
use azlin_azure::disk_layout::{
    build_disk_probe_script, build_disk_repair_script, parse_disk_probe, roles, DiskFinding,
    DiskReport, DiskStage, StorageStatus,
};

/// Process exit status for a completed (or attempted) check.
///
/// The verdict is in the exit status, not only in the text, so the command is
/// usable in a cron job. `2` for `Unknown` is the load-bearing one: a check
/// that could not be completed is not a passing check, and reporting `0` there
/// is how a fleet sweep concludes everything is fine because SSH was down.
pub fn check_exit_code(status: StorageStatus) -> i32 {
    match status {
        StorageStatus::Ok | StorageStatus::NoDisks => 0,
        StorageStatus::Degraded => 1,
        StorageStatus::Unknown => 2,
    }
}

/// The command to print when a surface reports a degraded VM.
///
/// Nothing formats a disk as a side effect of a status query, so the surfaces
/// print this instead — which means it has to be a command that works when
/// pasted. Deliberately without `--force`: an operator should look at the disk
/// before reaching for the only flag that can destroy a filesystem.
pub fn repair_hint(vm_name: &str) -> String {
    format!("Repair in place with:  azlin disk repair {}", vm_name)
}

// ---------------------------------------------------------------------------
// Which disks a VM is supposed to have
// ---------------------------------------------------------------------------

/// The disk configuration implied by the data disks Azure has attached.
///
/// Derived from the disk *names* `azlin new` gives them, not from LUN order:
/// the name is what says which role a disk was created for, and a VM whose
/// disks were attached in an unexpected order should be reported honestly
/// rather than probed at the wrong LUN.
fn attached_disk_config(rg: &str, vm_name: &str) -> Result<(DiskConfig, Vec<(String, u32)>)> {
    let out = std::process::Command::new("az")
        .args([
            "vm",
            "show",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--query",
            "storageProfile.dataDisks[].{name:name,lun:lun}",
            "-o",
            "json",
        ])
        .output()
        .context("failed to run `az vm show`")?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        anyhow::bail!(
            "could not read the data disks of '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let parsed: serde_json::Value =
        serde_json::from_slice(&out.stdout).context("`az vm show` returned invalid JSON")?;
    let mut attached: Vec<(String, u32)> = Vec::new();
    for entry in parsed.as_array().cloned().unwrap_or_default() {
        let name = entry
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string();
        let lun = entry.get("lun").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
        attached.push((name, lun));
    }

    let has = |suffix: &str| {
        attached
            .iter()
            .any(|(name, _)| name == &format!("{}{}", vm_name, suffix))
    };
    Ok((
        DiskConfig {
            home_disk: has("_home"),
            tmp_disk: has("_tmp"),
        },
        attached,
    ))
}

/// Whether Azure's LUN assignment matches the layout the probe will use.
///
/// A mismatch means the probe would look at the wrong LUN and report a healthy
/// disk as `absent`. That is an unknown, not a verdict — see
/// `docs-site/storage/data-disk-layout.md`.
fn lun_assignment_matches(
    config: &DiskConfig,
    vm_name: &str,
    attached: &[(String, u32)],
) -> Option<String> {
    for role in roles(config) {
        let expected_name = format!("{}_{}", vm_name, role.name);
        let actual = attached
            .iter()
            .find(|(name, _)| name == &expected_name)
            .map(|(_, lun)| *lun);
        if actual != Some(role.lun) {
            return Some(format!(
                "disk '{}' is attached at LUN {:?}, but azlin's layout puts the {} \
                 disk at LUN {}. Probing it would report the wrong disk, so no \
                 verdict is given.",
                expected_name, actual, role.name, role.lun
            ));
        }
    }
    None
}

/// Run the read-only probe against one VM and turn its output into a verdict.
///
/// Every failure mode here — no data disks, SSH down, garbled output — resolves
/// to a [`DiskReport`], never to an error that a caller might render as a pass.
pub(crate) async fn probe_vm_storage(
    vm_name: &str,
    resource_group: Option<String>,
) -> Result<(DiskReport, DiskConfig, String)> {
    let rg = resolve_resource_group(resource_group.clone())?;
    let (config, attached) = attached_disk_config(&rg, vm_name)?;

    if !config.home_disk && !config.tmp_disk {
        return Ok((
            DiskReport {
                status: StorageStatus::NoDisks,
                disks: Vec::new(),
                provisioning: None,
            },
            config,
            rg,
        ));
    }

    if let Some(reason) = lun_assignment_matches(&config, vm_name, &attached) {
        eprintln!("{}", reason);
        return Ok((
            DiskReport {
                status: StorageStatus::Unknown,
                disks: Vec::new(),
                provisioning: None,
            },
            config,
            rg,
        ));
    }

    let target = resolve_vm_ssh_target(vm_name, None, resource_group).await?;
    let script = build_disk_probe_script(&config, &target.user)
        .map_err(|e| anyhow::anyhow!("could not build the storage probe: {}", e))?;
    let (code, stdout, stderr) = target.exec(&script)?;
    if code != 0 && stdout.trim().is_empty() {
        eprintln!(
            "storage probe on '{}' failed: {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok((parse_disk_probe(&stdout, &config), config, rg))
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

fn size_cell(size_bytes: Option<u64>) -> String {
    match size_bytes {
        // Azure disks are sold in GB, so that is the unit an operator can
        // compare against the size they asked for.
        Some(bytes) => format!("{}G", bytes / 1_000_000_000),
        None => crate::health_render::UNKNOWN_CELL.to_string(),
    }
}

fn render_report_table(vm_name: &str, rg: &str, report: &DiskReport) {
    println!("VM: {}  (rg: {})", vm_name, rg);
    println!("Storage: {}", report.status);

    if !report.disks.is_empty() {
        println!();
        println!("  ROLE  LUN  DEVICE      SIZE     STAGE");
        for disk in &report.disks {
            println!(
                "  {:<5} {:<4} {:<11} {:<8} {}",
                disk.role,
                disk.lun,
                disk.device.as_deref().unwrap_or("--"),
                size_cell(disk.size_bytes),
                disk.stage
            );
            if disk.stage != DiskStage::Healthy {
                println!("        {}", disk.detail);
            }
        }
    }

    println!();
    match &report.provisioning {
        Some(p) if p.ledger_present => {
            println!(
                "Provisioning: {}, status={}",
                if p.complete { "complete" } else { "incomplete" },
                p.status
            );
            if !p.failed_sections.is_empty() {
                println!("  failed sections: {}", p.failed_sections.join(", "));
            }
        }
        Some(p) => println!(
            "Provisioning: {}, status unknown (no ledger — VM predates it)",
            if p.complete { "complete" } else { "incomplete" }
        ),
        None => println!("Provisioning: not reported"),
    }

    if report.status == StorageStatus::Degraded {
        println!();
        println!("{}", repair_hint(vm_name));
    }
}

fn report_json(vm_name: &str, rg: &str, report: &DiskReport) -> serde_json::Value {
    serde_json::json!({
        "vm": vm_name,
        "resource_group": rg,
        "status": report.status.as_str(),
        "disks": report.disks.iter().map(|d| serde_json::json!({
            "role": d.role,
            "lun": d.lun,
            "device": d.device,
            // `null`, not `0`: a disk with no device has no size, and a zero
            // here would be read as a measurement.
            "size_gb": d.size_bytes.map(|b| b / 1_000_000_000),
            "stage": d.stage.as_str(),
            "detail": d.detail,
        })).collect::<Vec<_>>(),
        "provisioning": report.provisioning.as_ref().map(|p| serde_json::json!({
            "complete": p.complete,
            "status": p.status,
            "ledger_present": p.ledger_present,
            "failed_sections": p.failed_sections,
        })),
    })
}

// ---------------------------------------------------------------------------
// azlin disk check
// ---------------------------------------------------------------------------

pub(crate) async fn handle_disk_check(
    vm_name: &str,
    resource_group: Option<String>,
    json: bool,
) -> Result<()> {
    let (report, _config, rg) = probe_vm_storage(vm_name, resource_group).await?;

    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&report_json(vm_name, &rg, &report))?
        );
    } else {
        render_report_table(vm_name, &rg, &report);
    }

    let code = check_exit_code(report.status);
    if code != 0 {
        std::process::exit(code);
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// azlin disk repair
// ---------------------------------------------------------------------------

fn plan_line(disk: &DiskFinding) -> String {
    format!(
        "  {:<5} LUN {}  {:<11} {:<8} {} -> healthy",
        disk.role,
        disk.lun,
        disk.device.as_deref().unwrap_or("--"),
        size_cell(disk.size_bytes),
        disk.stage
    )
}

pub(crate) async fn handle_disk_repair(
    vm_name: &str,
    resource_group: Option<String>,
    dry_run: bool,
    force: bool,
) -> Result<()> {
    let (report, _config, rg) = probe_vm_storage(vm_name, resource_group.clone()).await?;
    println!("VM: {}  (rg: {})", vm_name, rg);

    match report.status {
        StorageStatus::NoDisks => {
            println!("No azlin data disks are attached — nothing to repair.");
            return Ok(());
        }
        // A repair driven by a verdict that could not be reached would be a
        // `mkfs` decided by a parse failure.
        StorageStatus::Unknown => {
            anyhow::bail!(
                "could not determine the storage state of '{}', so there is nothing safe \
                 to repair. Run `azlin disk check {}` to see what the probe returned.",
                vm_name,
                vm_name
            );
        }
        StorageStatus::Ok => {
            println!("Storage: ok — nothing to repair.");
            for disk in &report.disks {
                println!("  {:<5} LUN {}  {}", disk.role, disk.lun, disk.stage);
            }
            return Ok(());
        }
        StorageStatus::Degraded => {}
    }

    let target = resolve_vm_ssh_target(vm_name, None, resource_group).await?;

    // Every script is built before anything runs, so a refusal on the second
    // disk does not leave the first half-repaired.
    let mut plan: Vec<(&DiskFinding, String)> = Vec::new();
    let mut refusals: Vec<String> = Vec::new();
    for disk in &report.disks {
        if disk.stage == DiskStage::Healthy {
            continue;
        }
        match build_disk_repair_script(disk, &target.user, force) {
            Ok(script) if script.trim().is_empty() => {}
            Ok(script) => plan.push((disk, script)),
            Err(reason) => refusals.push(format!("  {}: {}", disk.role, reason)),
        }
    }

    if !refusals.is_empty() {
        println!();
        for refusal in &refusals {
            println!("{}", refusal);
        }
    }
    if plan.is_empty() {
        anyhow::bail!("nothing could be repaired on '{}'", vm_name);
    }

    println!();
    println!("Plan:");
    for (disk, _) in &plan {
        println!("{}", plan_line(disk));
    }

    if dry_run {
        for (disk, script) in &plan {
            println!();
            println!("# ---- {} ----", disk.role);
            print!("{}", script);
        }
        println!();
        println!("--dry-run: nothing was executed on the VM.");
        return Ok(());
    }

    println!();
    let mut failed = false;
    for (disk, script) in &plan {
        let (code, stdout, stderr) = target.exec(script)?;
        for line in stdout.lines().filter(|l| !l.trim().is_empty()) {
            println!("  {:<5} {}", disk.role, line.trim_start_matches("azlin: "));
        }
        if code != 0 {
            failed = true;
            eprintln!(
                "  {:<5} repair failed (exit {}): {}",
                disk.role,
                code,
                azlin_core::sanitizer::sanitize(stderr.trim())
            );
        }
    }

    // Re-probed rather than assumed: the whole point of this command is that
    // "it printed success" is not the same claim as "the disk is mounted".
    let (after, _config, _rg) = probe_vm_storage(vm_name, Some(rg)).await?;
    println!();
    println!("Storage: {}", after.status);
    if failed || after.status != StorageStatus::Ok {
        anyhow::bail!(
            "'{}' is still not fully repaired. Run `azlin disk check {}` for the detail.",
            vm_name,
            vm_name
        );
    }

    println!();
    println!(
        "Note: open shells and tmux sessions still hold the old directories. Reconnect\n      \
         to see the new mounts:  azlin connect {}",
        vm_name
    );
    println!(
        "Note: the previous contents of the repaired home directory were kept alongside\n      \
         it as `<path>.old` and still occupy the OS disk. Remove them once you have\n      \
         confirmed the new mount."
    );
    Ok(())
}
