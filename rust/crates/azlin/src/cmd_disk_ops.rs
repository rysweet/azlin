//! `azlin disk check` and `azlin disk repair` (issue #1131).
//!
//! The defect was not only that cloud-init left the data disks unformatted. It
//! was that nothing said so: `azlin list` reported the VM Running and healthy
//! for weeks while 1.2 TB of attached, billed Premium SSD sat unused and `/`
//! ran at 98%. These two commands make the condition askable and fixable
//! without reprovisioning.
//!
//! The layout they compare against lives in `azlin_azure::disk_layout`, under
//! that module's drift rule.

use super::*;
use anyhow::{Context, Result};
use azlin_azure::cloud_init::DiskConfig;
use azlin_azure::disk_layout::{
    build_disk_probe_script, build_disk_repair_script, config_from_attached_disks,
    parse_disk_probe, reformats_existing_filesystem, DiskFinding, DiskReport, DiskStage,
    StorageStatus,
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

/// How long a single disk's repair may take.
///
/// A repair formats a disk and copies a home directory across it. Two hours is
/// not a prediction of how long that takes; it is a bound loose enough that
/// hitting it means something is wrong rather than merely large.
const REPAIR_EXEC_TIMEOUT_SECS: u64 = 2 * 60 * 60;

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

/// The data disks Azure reports attached to this VM, as `(name, lun)`.
///
/// `subscription_id` is explicit rather than ambient. This query used to run
/// before `create_auth()` — which is where an azlin context becomes real — so a
/// bare `az vm show` read whatever subscription the Azure CLI happened to be
/// pointed at. For anyone using `azlin context`, that is the wrong one: the VM
/// is not found there, `check` and `repair` fail outright, and on the unlucky
/// path where a same-named VM *does* exist in the CLI's subscription, the disk
/// layout of one machine decides the repair plan for another.
fn attached_disks(subscription_id: &str, rg: &str, vm_name: &str) -> Result<Vec<(String, u32)>> {
    let out = std::process::Command::new("az")
        .args([
            "vm",
            "show",
            "--subscription",
            subscription_id,
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
    Ok(disks_from_json(Some(&parsed)))
}

/// An `az` `[{name, lun}]` array as the `(name, lun)` pairs
/// [`config_from_attached_disks`] takes.
///
/// `azlin disk check` reads one VM's disks and the `Storage` column reads a
/// whole resource group's, from two different `az` queries that nest the same
/// array differently. Only the extraction is shared -- but it is the half that
/// decides which disks the layout is matched against, so a second copy that
/// defaulted a missing `lun` differently would make the two surfaces disagree
/// about the same VM.
pub(crate) fn disks_from_json(value: Option<&serde_json::Value>) -> Vec<(String, u32)> {
    value
        .and_then(|v| v.as_array())
        .map(|entries| {
            entries
                .iter()
                .map(|entry| {
                    (
                        entry
                            .get("name")
                            .and_then(|v| v.as_str())
                            .unwrap_or_default()
                            .to_string(),
                        entry.get("lun").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

/// Run the read-only probe against one VM and turn its output into a verdict.
///
/// Every failure mode here — no data disks, SSH down, garbled output — resolves
/// to a [`DiskReport`], never to an error that a caller might render as a pass.
pub(crate) async fn probe_vm_storage(
    vm_name: &str,
    resource_group: Option<String>,
) -> Result<ProbedVm> {
    let rg = resolve_resource_group(resource_group.clone())?;
    let verdict_only = |status| {
        Ok(ProbedVm {
            report: DiskReport {
                status,
                disks: Vec::new(),
                provisioning: None,
            },
            resource_group: rg.clone(),
            route: None,
        })
    };

    // Before the disk query, not after it: `create_auth` is the chokepoint that
    // switches the Azure CLI to the active context's subscription, and every
    // `az` call this function makes has to run on the far side of it.
    let auth = crate::dispatch_helpers::create_auth()?;
    let subscription_id = auth.subscription_id().to_string();

    let attached = attached_disks(&subscription_id, &rg, vm_name)?;
    let config = match config_from_attached_disks(vm_name, &attached) {
        Ok(config) => config,
        Err(reason) => {
            eprintln!("{}", reason);
            return verdict_only(StorageStatus::Unknown);
        }
    };
    if !config.home_disk && !config.tmp_disk {
        return verdict_only(StorageStatus::NoDisks);
    }

    let target =
        crate::dispatch_helpers::resolve_vm_ssh_target_with_auth(&auth, vm_name, resource_group)
            .await?;
    let report = run_probe(vm_name, &config, &target)?;
    Ok(ProbedVm {
        report,
        resource_group: rg,
        route: Some(ProbeRoute { target, config }),
    })
}

/// One VM's storage verdict, together with the route and the layout used to
/// reach it.
pub(crate) struct ProbedVm {
    pub(crate) report: DiskReport,
    pub(crate) resource_group: String,
    /// `None` when the verdict was reached without SSH — no data disks, or a
    /// LUN layout that does not match what the VM was created with.
    pub(crate) route: Option<ProbeRoute>,
}

/// An open route to a VM and the disk layout to interpret it against.
pub(crate) struct ProbeRoute {
    pub(crate) target: crate::VmSshTarget,
    pub(crate) config: DiskConfig,
}

impl ProbedVm {
    /// Ask the same VM the same question again, over the route already open.
    ///
    /// A repair does not attach disks, change subscription, or move the
    /// bastion, so re-running [`probe_vm_storage`] would spend four `az`
    /// invocations — `az vm show` twice, `az account show`, `az network
    /// bastion list` — re-deriving answers that cannot have changed, and on a
    /// context-pinned subscription an `az account set` as well. Only the disk
    /// state can have changed, and that is exactly what the probe reads.
    pub(crate) fn reprobe(&self, vm_name: &str) -> Result<DiskReport> {
        let Some(route) = self.route.as_ref() else {
            // No route means the verdict never needed one; it still does not.
            return Ok(DiskReport {
                status: self.report.status,
                disks: Vec::new(),
                provisioning: None,
            });
        };
        run_probe(vm_name, &route.config, &route.target)
    }
}

/// Send the read-only probe over an established route and parse the answer.
/// What [`run_probe`] prints when the probe came back with nothing usable.
///
/// Built by a pure function rather than inline at the `eprintln!` because this
/// is the only part of a network-bound call a test can reach, and it is the
/// part carrying the rule: both fields are remote text, so both get both
/// inbound sanitizers.
///
/// Redact first, then strip. The order is not cosmetic -- the redaction
/// patterns in [`azlin_core::sanitizer::sanitize`] are written against ordinary
/// text, and an escape planted mid-token is enough to split a secret out of a
/// match. Stripping second would leave the secret reassembled and unredacted.
///
/// `stdout` gets the same treatment at `disk_layout`'s parse boundary. stderr
/// had only the redaction half, which is the asymmetry this closes: it is the
/// channel a VM shapes most easily, and this message is printed once per VM in
/// a fleet-wide sweep, immediately above the next VM's row.
pub(crate) fn probe_failure_note(vm_name: &str, stderr: &str) -> String {
    let clean = |s: &str| {
        azlin_core::sanitizer::printable(&azlin_core::sanitizer::sanitize(s.trim()))
            .trim()
            .to_string()
    };
    let vm = clean(vm_name);
    let reason = clean(stderr);
    if reason.is_empty() {
        // A dangling "failed: " reads as a bug in azlin rather than as silence
        // from the VM, and silence is the actual finding worth reporting.
        format!("storage probe on '{vm}' failed, with no output to explain why")
    } else {
        format!("storage probe on '{vm}' failed: {reason}")
    }
}

fn run_probe(
    vm_name: &str,
    config: &DiskConfig,
    target: &crate::VmSshTarget,
) -> Result<DiskReport> {
    let script = build_disk_probe_script(config, &target.user)
        .map_err(|e| anyhow::anyhow!("could not build the storage probe: {}", e))?;
    let (code, stdout, stderr) = target.exec(&script)?;
    if code != 0 && stdout.trim().is_empty() {
        eprintln!("{}", probe_failure_note(vm_name, &stderr));
    }
    Ok(parse_disk_probe(&stdout, config))
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/// Bytes in one GiB.
///
/// `az disk create --size-gb 100` provisions 100 **GiB**, and `lsblk -bdno
/// SIZE` reports the byte count, so dividing by 10^9 rendered every disk about
/// 7% larger than the size the operator asked for: a `--home-disk-size 100`
/// disk read as `107G`. The point of this column is to be comparable with the
/// request.
const BYTES_PER_GIB: u64 = 1024 * 1024 * 1024;

fn size_cell(size_bytes: Option<u64>) -> String {
    match size_bytes {
        Some(bytes) => format!("{}G", bytes / BYTES_PER_GIB),
        None => crate::health_render::UNKNOWN_CELL.to_string(),
    }
}

fn render_report_table(vm_name: &str, rg: &str, report: &DiskReport) {
    println!("VM: {}  (rg: {})", vm_name, rg);
    println!("Storage: {}", report.status);

    if !report.disks.is_empty() {
        println!();
        // Widths from content, not hand-spaced: a header string and a row
        // format kept in character-level agreement by hand misaligns the first
        // time either changes, and a device path longer than the guessed width
        // truncates differently here than in the repair plan.
        for (i, line) in crate::output_helpers::format_as_table(
            &["ROLE", "LUN", "DEVICE", "SIZE", "STAGE"],
            &report.disks.iter().map(disk_row).collect::<Vec<_>>(),
        )
        .lines()
        .enumerate()
        {
            println!("  {}", line.trim_end());
            // The header occupies line 0, so disk `n` is line `n + 1`.
            if let Some(disk) = i.checked_sub(1).and_then(|n| report.disks.get(n)) {
                if disk.stage != DiskStage::Healthy {
                    println!("        {}", disk.detail);
                }
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
            "size_gb": d.size_bytes.map(|b| b / BYTES_PER_GIB),
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
    // A failure before the probe — no `az` login, VM deallocated, no route — is
    // "the check could not be completed", which the exit-code contract spells
    // `2`. Letting it propagate would surface it as azlin's generic `1`, the
    // code that means *degraded*: a cron sweep would record a storage failure
    // on a VM whose storage was never inspected.
    let probe = match probe_vm_storage(vm_name, resource_group).await {
        Ok(probe) => probe,
        Err(e) => {
            eprintln!("Error: {:#}", e);
            std::process::exit(check_exit_code(StorageStatus::Unknown));
        }
    };
    let (report, rg) = (probe.report, probe.resource_group);

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

/// One disk as a table row: role, LUN, device, size, stage.
///
/// Shared by the `check` table and the `repair` plan so a long device path
/// cannot be padded one way in one and truncated another way in the other.
fn disk_row(disk: &DiskFinding) -> Vec<String> {
    vec![
        disk.role.clone(),
        disk.lun.to_string(),
        disk.device
            .clone()
            .unwrap_or_else(|| crate::health_render::UNKNOWN_CELL.to_string()),
        size_cell(disk.size_bytes),
        disk.stage.to_string(),
    ]
}

pub(crate) async fn handle_disk_repair(
    vm_name: &str,
    resource_group: Option<String>,
    dry_run: bool,
    force: bool,
    yes: bool,
) -> Result<()> {
    let probed = probe_vm_storage(vm_name, resource_group).await?;
    let (report, rg) = (&probed.report, probed.resource_group.clone());
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

    // Resolved once, by the probe. Re-resolving costs three `az` calls per
    // repair for an answer that cannot have changed.
    let Some(target) = probed.route.as_ref().map(|r| &r.target) else {
        anyhow::bail!("could not reach '{}' to repair it", vm_name);
    };

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
    let rows: Vec<Vec<String>> = plan
        .iter()
        .map(|(disk, _)| {
            let mut row = disk_row(disk);
            row.push("-> healthy".to_string());
            row
        })
        .collect();
    for line in crate::output_helpers::format_as_table(
        &["ROLE", "LUN", "DEVICE", "SIZE", "STAGE", ""],
        &rows,
    )
    .lines()
    .skip(1)
    {
        println!("  {}", line.trim_end());
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

    // The one irreversible thing this command can do gets the one prompt.
    //
    // `--dry-run` protects the careful operator; it does not protect the one
    // who mistyped the VM name. Nineteen other azlin commands confirm before
    // something destructive, and the only command in the tool that can run
    // `mkfs` over a filesystem holding data azlin cannot see had no
    // confirmation at all — because `--force` here reads like the
    // skip-the-prompt flag it is everywhere else and is not one. The plan is
    // printed above, so this asks after the operator has seen exactly which
    // disks are involved.
    let reformats: Vec<&&DiskFinding> = plan
        .iter()
        .map(|(disk, _)| disk)
        .filter(|disk| reformats_existing_filesystem(disk, force))
        .collect();
    if !reformats.is_empty() {
        println!();
        for disk in &reformats {
            println!(
                "  --force will run mkfs.ext4 over the existing filesystem on the {} disk \
                 at LUN {} ({}).",
                disk.role,
                disk.lun,
                disk.device
                    .as_deref()
                    .unwrap_or(crate::health_render::UNKNOWN_CELL),
            );
        }
        println!("  Anything on it that is not already on another disk is lost.");
        if !crate::dispatch_helpers::safe_confirm_with_flag("Reformat and continue?", yes, "--yes")?
        {
            println!("Nothing was executed on the VM.");
            return Ok(());
        }
    }

    println!();
    let mut failed = false;
    for (disk, script) in &plan {
        // Not `exec`: that caps a bastion-routed command at
        // BASTION_EXEC_TIMEOUT_SECS (60s), and this one copies an entire home
        // directory. Bastion-only VMs are the population #1131 was reported
        // against, so the default cap would have killed the copy mid-flight on
        // exactly the machines this command exists for.
        //
        // A transport failure is recorded and the loop continues rather than
        // propagating: `?` here would abandon the remaining disks *and* skip
        // the closing notes — including the only place the command says where
        // the previous home directory went.
        match target.exec_with_local_timeout(script, REPAIR_EXEC_TIMEOUT_SECS) {
            Ok((code, stdout, stderr)) => {
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
            Err(e) => {
                failed = true;
                eprintln!(
                    "  {:<5} the connection failed mid-repair, so what was applied is \
                     unknown: {:#}",
                    disk.role, e
                );
            }
        }
    }

    // Printed before the verdict, and on every path: a repair that failed
    // halfway still moved a home directory, and where it went is the first
    // thing the operator needs to know.
    println!();
    println!(
        "Note: open shells and tmux sessions still hold the old directories. Reconnect\n      \
         to see the new mounts:  azlin connect {}",
        vm_name
    );
    println!(
        "Note: if the home directory was moved, its previous contents were kept\n      \
         alongside it as `<path>.old` and still occupy the OS disk. Remove them\n      \
         once you have confirmed the new mount."
    );

    // Re-probed rather than assumed: the whole point of this command is that
    // "it printed success" is not the same claim as "the disk is mounted".
    // Over the route already open — see `ProbedVm::reprobe`.
    let after = probed.reprobe(vm_name)?;
    println!();
    println!("Storage: {}", after.status);
    if failed || after.status != StorageStatus::Ok {
        anyhow::bail!(
            "'{}' is still not fully repaired. Run `azlin disk check {}` for the detail.",
            vm_name,
            vm_name
        );
    }
    Ok(())
}
