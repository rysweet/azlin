#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) fn handle_doit_status(session: Option<String>) -> Result<()> {
    let rg = resolve_resource_group(None)?;
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let vms = vm_manager.list_vms(&rg)?;
    let doit_vms: Vec<_> = vms
        .iter()
        .filter(|vm| vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit"))
        .collect();
    if doit_vms.is_empty() {
        let session_id = session.unwrap_or_else(|| "latest".to_string());
        println!(
            "No active doit deployments for session '{}' in '{}'.",
            session_id, rg
        );
    } else {
        println!("Doit deployments in '{}':", rg);
        for vm in &doit_vms {
            println!("  {} -- {} -- {}", vm.name, vm.power_state, vm.vm_size);
        }
    }
    Ok(())
}

pub(crate) fn handle_doit_list(username: Option<String>) -> Result<()> {
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(None)?;
    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message("Listing doit-created resources...");
    pb.enable_steady_tick(std::time::Duration::from_millis(100));
    let vms = vm_manager.list_vms(&rg)?;
    pb.finish_and_clear();
    let filtered: Vec<_> = vms
        .iter()
        .filter(|vm| {
            let has_tag = vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
            let user_match = username
                .as_ref()
                .is_none_or(|u| vm.admin_username.as_deref() == Some(u.as_str()));
            has_tag && user_match
        })
        .collect();
    if filtered.is_empty() {
        println!("No doit-created resources found.");
    } else {
        for vm in &filtered {
            println!("  {} ({})", vm.name, vm.power_state);
        }
    }
    Ok(())
}

pub(crate) fn handle_doit_show(resource_id: &str) -> Result<()> {
    let output = std::process::Command::new("az")
        .args(["resource", "show", "--ids", resource_id, "-o", "json"])
        .output()?;
    if output.status.success() {
        print!("{}", String::from_utf8_lossy(&output.stdout));
    } else {
        eprintln!(
            "Failed to show resource: {}",
            azlin_core::sanitizer::sanitize(&String::from_utf8_lossy(&output.stderr))
        );
    }
    Ok(())
}

pub(crate) fn handle_doit_cleanup(
    force: bool,
    dry_run: bool,
    username: Option<String>,
) -> Result<()> {
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(None)?;

    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message("Finding doit-created resources...");
    pb.enable_steady_tick(std::time::Duration::from_millis(100));
    let vms = vm_manager.list_vms(&rg)?;
    pb.finish_and_clear();

    let to_delete: Vec<_> = vms
        .iter()
        .filter(|vm| {
            let has_tag = vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
            let user_match = username
                .as_ref()
                .is_none_or(|u| vm.admin_username.as_deref() == Some(u.as_str()));
            has_tag && user_match
        })
        .collect();

    if to_delete.is_empty() {
        println!("No doit-created resources to clean up.");
        return Ok(());
    }

    println!("Resources to delete:");
    for vm in &to_delete {
        println!("  {} ({})", vm.name, vm.power_state);
    }

    if dry_run {
        return Ok(());
    }

    if !safe_confirm("Delete these resources?", force)? {
        println!("Cancelled.");
        return Ok(());
    }

    for vm in &to_delete {
        println!("Deleting '{}'...", vm.name);
        vm_manager.delete_vm(&rg, &vm.name)?;
    }
    println!("Cleanup complete.");
    Ok(())
}

pub(crate) fn handle_doit_examples() {
    println!("Example doit requests:");
    println!("  azlin doit deploy \"Create a 2-VM cluster with Ubuntu 24.04\"");
    println!("  azlin doit deploy \"Set up a dev VM with 4 cores and 16GB RAM\"");
    println!("  azlin doit deploy \"Scale my fleet to 5 VMs in eastus2\"");
    println!("  azlin doit deploy --dry-run \"Delete all stopped VMs\"");
}
