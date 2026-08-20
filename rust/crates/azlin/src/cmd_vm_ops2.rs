#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use console::Style;
pub(crate) async fn handle_vm_update(
    vm_identifier: &str,
    resource_group: Option<String>,
    timeout: u32,
) -> Result<()> {
    let pb = penguin_spinner(&format!("Looking up {}...", vm_identifier));
    let target = resolve_vm_ssh_target(vm_identifier, None, resource_group).await?;
    pb.finish_and_clear();

    let steps = crate::update_helpers::dev_update_step_count();
    println!(
        "Updating development tools on '{}' ({}s per update, {} updates)...",
        vm_identifier, timeout, steps
    );
    // `--timeout` says "Timeout **per update** in seconds", so the bound goes
    // around each step rather than around the script: one stuck download used
    // to hold the command open forever, and a single whole-script budget would
    // have failed a slow-but-working run instead.
    let update_script = crate::update_helpers::build_dev_update_script(timeout);
    // The outer bound is the sum of the per-step ones, so the transport never
    // gives up before the steps do.
    let (code, stdout, stderr) =
        match crate::exec_under_timeout(&target, &update_script, timeout.saturating_mul(steps))? {
            crate::TimedExec::Finished {
                code,
                stdout,
                stderr,
            } => (code, stdout, stderr),
            crate::TimedExec::TimedOut(note) => {
                anyhow::bail!("Tool update on '{}' {}", vm_identifier, note)
            }
        };
    if code == crate::fleet_select::TIMEOUT_EXIT_CODE {
        anyhow::bail!(
            "Tool update on '{}': one update exceeded {}s (--timeout) and the script stopped \
             there. The output above says which.",
            vm_identifier,
            timeout
        );
    }
    if code == 0 {
        let green = Style::new().green();
        println!(
            "{}",
            green.apply_to(format!("Update completed on '{}'", vm_identifier))
        );
        if !stdout.trim().is_empty() {
            println!("{}", stdout.trim());
        }
    } else {
        let detail = if stderr.trim().is_empty() {
            String::new()
        } else {
            format!(": {}", azlin_core::sanitizer::sanitize(stderr.trim()))
        };
        anyhow::bail!("Update failed on '{}'{}", vm_identifier, detail);
    }
    Ok(())
}

pub(crate) fn handle_vm_clone(
    source_vm: &str,
    num_replicas: u32,
    resource_group: Option<String>,
    session_prefix: Option<String>,
    vm_size: Option<String>,
    region: Option<String>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let snapshot_name = format!(
        "{}_clone_snap_{}",
        source_vm,
        chrono::Utc::now().format("%Y%m%d_%H%M%S")
    );

    // All three of these were accepted and discarded (#1089). Two of them
    // documented a default the code did not implement either: `--vm-size` and
    // `--region` both say "same as source", and only the region actually was.
    let (disk_id, source_location, source_size) =
        crate::dispatch_helpers::lookup_vm_clone_source(&rg, source_vm)?;
    let location = region.unwrap_or_else(|| source_location.clone());
    let size = vm_size.unwrap_or(source_size);

    println!(
        "Cloning VM '{}' ({} replica(s), size {}, region {})...",
        source_vm, num_replicas, size, location
    );
    if let Some(note) = crate::clone_helpers::cross_region_note(&source_location, &location) {
        eprintln!("{}", note);
    }

    let cross_region = crate::clone_helpers::is_cross_region(&source_location, &location);
    let pb = penguin_spinner(&format!("Snapshotting {}...", source_vm));

    let snap_out = std::process::Command::new("az")
        .args(crate::clone_helpers::build_snapshot_args(
            &rg,
            &snapshot_name,
            &disk_id,
            &source_location,
            cross_region,
        ))
        .output()?;
    pb.finish_and_clear();

    if !snap_out.status.success() {
        let stderr = String::from_utf8_lossy(&snap_out.stderr);
        anyhow::bail!(
            "Failed to snapshot source VM: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    // The resource id, not the name: `az disk create --source` accepts a bare
    // snapshot name only within one region, so falling back to the name would
    // work in-region and fail across one — the harder failure to diagnose.
    let snapshot_source = crate::clone_helpers::snapshot_id_from_create(&snap_out.stdout)
        .unwrap_or_else(|| snapshot_name.clone());
    println!("Created snapshot '{}'", snapshot_name);

    // Every clone that did not come up. The loop used to report each failure
    // and return success, so three failed clones exited 0 having created a
    // snapshot that bills (#1089-adjacent, same shape as #1105 and #1110).
    let mut failed: Vec<String> = Vec::new();

    for i in 0..num_replicas {
        let clone_name = crate::clone_helpers::clone_name(source_vm, i);
        println!("Creating clone '{}'...", clone_name);
        let disk_name = format!("{}_OsDisk", clone_name);

        let disk_out = std::process::Command::new("az")
            .args(crate::clone_helpers::build_clone_disk_args(
                &rg,
                &disk_name,
                &snapshot_source,
                &location,
            ))
            .output()?;

        if disk_out.status.success() {
            println!("  Created disk '{}' from snapshot", disk_name);
            let pb = penguin_spinner(&format!("Creating VM '{}'...", clone_name));

            // For bastion VMs (no public IP on source), route through bastion VNet
            // and disable public IP on the clone too.
            let is_bastion = match crate::dispatch_helpers::lookup_vm_public_ip(&rg, source_vm) {
                Ok(None) => true,
                Ok(Some(ref ip)) if ip.is_empty() => true,
                _ => false,
            };
            // `--session-prefix` set nothing, so clones carried no
            // `azlin-session` tag at all and did not appear as a session in
            // `azlin list` (#1089).
            let session_tag = crate::clone_helpers::clone_session_tag(
                session_prefix.as_deref(),
                source_vm,
                i,
                num_replicas,
            );
            let clone_args = crate::clone_helpers::build_clone_vm_args(
                &rg,
                &clone_name,
                &disk_name,
                &location,
                &size,
                &session_tag,
                is_bastion,
            );

            let vm_out = std::process::Command::new("az")
                .args(&clone_args)
                .output()?;
            pb.finish_and_clear();

            if vm_out.status.success() {
                println!("  Created VM '{}' (session '{}')", clone_name, session_tag);
            } else {
                let stderr = String::from_utf8_lossy(&vm_out.stderr);
                eprintln!(
                    "  Failed to create VM '{}': {}",
                    clone_name,
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
                failed.push(clone_name.clone());
            }
        } else {
            let stderr = String::from_utf8_lossy(&disk_out.stderr);
            eprintln!(
                "  Failed to create disk for clone '{}': {}",
                clone_name,
                azlin_core::sanitizer::sanitize(stderr.trim())
            );
            failed.push(clone_name.clone());
        }
    }

    // Every clone's name and error has been printed by now, so it is safe to
    // exit non-zero — the same ordering `azlin new` uses for degraded VMs.
    if let Some(message) =
        crate::clone_helpers::clone_failure_message(&failed, num_replicas, &snapshot_name, &rg)
    {
        anyhow::bail!("{}", message);
    }
    Ok(())
}
