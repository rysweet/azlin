#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use console::Style;
pub(crate) async fn handle_vm_update(
    vm_identifier: &str,
    resource_group: Option<String>,
) -> Result<()> {
    let pb = penguin_spinner(&format!("Looking up {}...", vm_identifier));
    let target = resolve_vm_ssh_target(vm_identifier, None, resource_group).await?;
    pb.finish_and_clear();

    println!("Updating development tools on '{}'...", vm_identifier);
    let update_script = crate::update_helpers::build_dev_update_script();
    let (code, stdout, stderr) = target.exec(update_script)?;
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
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let snapshot_name = format!(
        "{}_clone_snap_{}",
        source_vm,
        chrono::Utc::now().format("%Y%m%d_%H%M%S")
    );

    println!(
        "Cloning VM '{}' ({} replica(s))...",
        source_vm, num_replicas
    );

    let (disk_id, location) = crate::dispatch_helpers::lookup_vm_disk_info(&rg, source_vm)?;

    let pb = penguin_spinner(&format!("Snapshotting {}...", source_vm));

    let snap_out = std::process::Command::new("az")
        .args([
            "snapshot",
            "create",
            "--resource-group",
            &rg,
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

    if !snap_out.status.success() {
        let stderr = String::from_utf8_lossy(&snap_out.stderr);
        anyhow::bail!(
            "Failed to snapshot source VM: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    println!("Created snapshot '{}'", snapshot_name);

    for i in 0..num_replicas {
        let clone_name = format!("{}-clone-{}", source_vm, i + 1);
        println!("Creating clone '{}'...", clone_name);
        let disk_name = format!("{}_OsDisk", clone_name);

        let disk_out = std::process::Command::new("az")
            .args([
                "disk",
                "create",
                "--resource-group",
                &rg,
                "--name",
                &disk_name,
                "--source",
                &snapshot_name,
                "--output",
                "json",
            ])
            .output()?;

        if disk_out.status.success() {
            println!("  Created disk '{}' from snapshot", disk_name);
            let pb = penguin_spinner(&format!("Creating VM '{}'...", clone_name));

            let mut clone_args = vec![
                "vm".to_string(),
                "create".to_string(),
                "--resource-group".to_string(),
                rg.clone(),
                "--name".to_string(),
                clone_name.clone(),
                "--attach-os-disk".to_string(),
                disk_name.clone(),
                "--os-type".to_string(),
                "Linux".to_string(),
                "--location".to_string(),
                location.clone(),
                "--output".to_string(),
                "json".to_string(),
            ];

            // For bastion VMs (no public IP on source), route through bastion VNet
            // and disable public IP on the clone too.
            let is_bastion = match crate::dispatch_helpers::lookup_vm_public_ip(&rg, source_vm) {
                Ok(None) => true,
                Ok(Some(ref ip)) if ip.is_empty() => true,
                _ => false,
            };
            if is_bastion {
                clone_args.push("--public-ip-address".to_string());
                clone_args.push(String::new());
                let vnet_name = format!("azlin-bastion-{}-vnet", location);
                clone_args.push("--subnet".to_string());
                clone_args.push("default".to_string());
                clone_args.push("--vnet-name".to_string());
                clone_args.push(vnet_name);
            }

            let vm_out = std::process::Command::new("az")
                .args(&clone_args)
                .output()?;
            pb.finish_and_clear();

            if vm_out.status.success() {
                println!("  Created VM '{}'", clone_name);
            } else {
                let stderr = String::from_utf8_lossy(&vm_out.stderr);
                eprintln!(
                    "  Failed to create VM '{}': {}",
                    clone_name,
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
        } else {
            let stderr = String::from_utf8_lossy(&disk_out.stderr);
            eprintln!(
                "  Failed to create disk for clone '{}': {}",
                clone_name,
                azlin_core::sanitizer::sanitize(stderr.trim())
            );
        }
    }
    Ok(())
}
