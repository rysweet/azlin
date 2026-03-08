#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use console::Style;

pub(crate) async fn handle_storage_create(
    name: &str,
    size: u32,
    tier: &str,
    resource_group: Option<String>,
    region: Option<String>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let loc = region.unwrap_or_else(|| "westus2".to_string());

    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message(format!("Creating storage account {}...", name));
    pb.enable_steady_tick(std::time::Duration::from_millis(100));

    let sku = crate::storage_helpers::storage_sku_from_tier(tier);

    let output = std::process::Command::new("az")
        .args([
            "storage",
            "account",
            "create",
            "--name",
            name,
            "--resource-group",
            &rg,
            "--location",
            &loc,
            "--sku",
            sku,
            "--kind",
            "FileStorage",
            "--enable-nfs-v3",
            "true",
            "--output",
            "json",
        ])
        .output()?;

    pb.finish_and_clear();
    if output.status.success() {
        println!(
            "{}",
            crate::handlers::format_storage_created(name, size, tier)
        );
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to create storage account: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

pub(crate) fn handle_storage_list(resource_group: Option<String>) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;

    let output = std::process::Command::new("az")
        .args([
            "storage",
            "account",
            "list",
            "--resource-group",
            &rg,
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let accounts: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)
            .context("Failed to parse storage account list JSON")?;

        if accounts.is_empty() {
            println!("No storage accounts found.");
        } else {
            let mut table = Table::new();
            table
                .load_preset(UTF8_FULL_CONDENSED)
                .set_header(vec!["Name", "Location", "Kind", "SKU", "State"]);
            for acct in &accounts {
                table.add_row(crate::storage_helpers::storage_account_row(acct));
            }
            println!("{table}");
        }
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list storage accounts: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

pub(crate) fn handle_storage_status(name: &str, resource_group: Option<String>) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;

    let output = std::process::Command::new("az")
        .args([
            "storage",
            "account",
            "show",
            "--name",
            name,
            "--resource-group",
            &rg,
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let acct: serde_json::Value = serde_json::from_slice(&output.stdout)
            .context("Failed to parse storage account JSON")?;
        let key_style = Style::new().cyan().bold();
        for (key, value) in crate::handlers::format_storage_status(&acct) {
            println!("{}: {}", key_style.apply_to(&key), value);
        }
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to show storage account: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

pub(crate) fn handle_storage_mount(
    storage_name: &str,
    vm: &str,
    mount_point: Option<String>,
    resource_group: Option<String>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);

    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message(format!("Looking up VM {}...", vm));
    pb.enable_steady_tick(std::time::Duration::from_millis(100));
    let vm_info = vm_manager.get_vm(&rg, vm)?;
    pb.finish_and_clear();

    let ip = vm_info
        .public_ip
        .or(vm_info.private_ip)
        .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
    let user = vm_info
        .admin_username
        .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

    crate::handlers::validate_storage_name(storage_name)?;

    let mp = mount_point.unwrap_or_else(|| crate::handlers::default_nfs_mount_point(storage_name));

    crate::mount_helpers::validate_mount_path(&mp)
        .map_err(|e| anyhow::anyhow!("Invalid mount path: {}", e))?;

    let mount_cmd = crate::handlers::build_nfs_mount_command(storage_name, &mp);
    let status = std::process::Command::new("ssh")
        .args([
            "-o",
            "StrictHostKeyChecking=accept-new",
            &format!("{}@{}", user, ip),
            &mount_cmd,
        ])
        .status()?;

    if status.success() {
        println!(
            "{}",
            crate::handlers::format_storage_mounted(storage_name, vm, &mp)
        );
    } else {
        anyhow::bail!("Failed to mount storage on VM.");
    }
    Ok(())
}

pub(crate) fn handle_storage_unmount(vm: &str, resource_group: Option<String>) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);

    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message(format!("Looking up VM {}...", vm));
    pb.enable_steady_tick(std::time::Duration::from_millis(100));
    let vm_info = vm_manager.get_vm(&rg, vm)?;
    pb.finish_and_clear();

    let ip = vm_info
        .public_ip
        .or(vm_info.private_ip)
        .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
    let user = vm_info
        .admin_username
        .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

    let status = std::process::Command::new("ssh")
        .args([
            "-o",
            "StrictHostKeyChecking=accept-new",
            &format!("{}@{}", user, ip),
            "sudo umount /mnt/* 2>/dev/null; echo done",
        ])
        .status()?;

    if status.success() {
        println!("{}", crate::handlers::format_storage_unmounted(vm));
    } else {
        anyhow::bail!("Failed to unmount storage from VM.");
    }
    Ok(())
}
