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

    let pb = penguin_spinner(&format!("Creating storage account {}...", name));

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
            let mut table = crate::table_render::SimpleTable::new(
                &["Name", "Location", "Kind", "SKU", "State"],
                &[24, 12, 14, 20, 12],
            );
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

pub(crate) async fn handle_storage_mount(
    storage_name: &str,
    vm: &str,
    mount_point: Option<String>,
    resource_group: Option<String>,
) -> Result<()> {
    crate::handlers::validate_storage_name(storage_name)?;

    let mp = mount_point.unwrap_or_else(|| crate::handlers::default_nfs_mount_point(storage_name));
    crate::mount_helpers::validate_mount_path(&mp)
        .map_err(|e| anyhow::anyhow!("Invalid mount path: {}", e))?;

    let pb = penguin_spinner(&format!("Looking up VM {}...", vm));
    let target = resolve_vm_ssh_target(vm, None, resource_group).await?;
    pb.finish_and_clear();

    let mount_cmd = crate::handlers::build_nfs_mount_command(storage_name, &mp);
    let (exit_code, _stdout, stderr) = target.exec(&mount_cmd)?;

    if exit_code == 0 {
        println!(
            "{}",
            crate::handlers::format_storage_mounted(storage_name, vm, &mp)
        );
    } else {
        anyhow::bail!(
            "Failed to mount storage on VM: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

pub(crate) async fn handle_storage_unmount(vm: &str, resource_group: Option<String>) -> Result<()> {
    let pb = penguin_spinner(&format!("Looking up VM {}...", vm));
    let target = resolve_vm_ssh_target(vm, None, resource_group).await?;
    pb.finish_and_clear();

    let (exit_code, _stdout, stderr) = target.exec("sudo umount /mnt/* 2>/dev/null; echo done")?;

    if exit_code == 0 {
        println!("{}", crate::handlers::format_storage_unmounted(vm));
    } else {
        anyhow::bail!(
            "Failed to unmount storage from VM: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}
