#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use console::Style;
use dialoguer::Confirm;
use indicatif::{ProgressBar, ProgressStyle};

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Storage { action } => match action {
            azlin_cli::StorageAction::Create {
                name,
                size,
                tier,
                resource_group,
                region,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let loc = region.unwrap_or_else(|| "westus2".to_string());

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Creating storage account {}...", name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let sku = crate::storage_helpers::storage_sku_from_tier(&tier);

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "create",
                        "--name",
                        &name,
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
                        crate::handlers::format_storage_created(&name, size, &tier)
                    );
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to create storage account: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            azlin_cli::StorageAction::List { resource_group } => {
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
                    let accounts: Vec<serde_json::Value> =
                        serde_json::from_slice(&output.stdout)
                            .context("Failed to parse storage account list JSON")?;

                    if accounts.is_empty() {
                        println!("No storage accounts found.");
                    } else {
                        let mut table = Table::new();
                        table
                            .load_preset(UTF8_FULL)
                            .apply_modifier(UTF8_ROUND_CORNERS)
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
            }
            azlin_cli::StorageAction::Status {
                name,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "show",
                        "--name",
                        &name,
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
            }
            azlin_cli::StorageAction::Mount {
                storage_name,
                vm,
                mount_point,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Looking up VM {}...", vm));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm_info = vm_manager.get_vm(&rg, &vm)?;
                pb.finish_and_clear();

                let ip = vm_info
                    .public_ip
                    .or(vm_info.private_ip)
                    .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

                crate::handlers::validate_storage_name(&storage_name)?;

                let mp = mount_point
                    .unwrap_or_else(|| crate::handlers::default_nfs_mount_point(&storage_name));

                // Validate mount path to prevent command injection
                crate::mount_helpers::validate_mount_path(&mp)
                    .map_err(|e| anyhow::anyhow!("Invalid mount path: {}", e))?;

                let mount_cmd = crate::handlers::build_nfs_mount_command(&storage_name, &mp);
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
                        crate::handlers::format_storage_mounted(&storage_name, &vm, &mp)
                    );
                } else {
                    anyhow::bail!("Failed to mount storage on VM.");
                }
            }
            azlin_cli::StorageAction::Unmount { vm, resource_group } => {
                let rg = resolve_resource_group(resource_group)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Looking up VM {}...", vm));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm_info = vm_manager.get_vm(&rg, &vm)?;
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
                    println!("{}", crate::handlers::format_storage_unmounted(&vm));
                } else {
                    anyhow::bail!("Failed to unmount storage from VM.");
                }
            }
            azlin_cli::StorageAction::Delete {
                name,
                resource_group,
                force,
            } => {
                let rg = resolve_resource_group(resource_group)?;

                if !force {
                    let confirmed = Confirm::new()
                        .with_prompt(format!(
                            "Delete storage account '{}'? This cannot be undone.",
                            name
                        ))
                        .default(false)
                        .interact()?;
                    if !confirmed {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Deleting storage account {}...", name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "delete",
                        "--name",
                        &name,
                        "--resource-group",
                        &rg,
                        "--yes",
                    ])
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    println!("{}", crate::handlers::format_storage_deleted(&name));
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to delete storage account: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            azlin_cli::StorageAction::MountFile {
                account,
                share,
                mount_point,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let mount_dir = mount_point
                    .unwrap_or_else(|| std::path::PathBuf::from(format!("/mnt/{}", account)));

                // Get storage account key
                let key_output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "keys",
                        "list",
                        "--account-name",
                        &account,
                        "--resource-group",
                        &rg,
                        "--query",
                        "[0].value",
                        "-o",
                        "tsv",
                    ])
                    .output()?;

                if !key_output.status.success() {
                    let stderr = String::from_utf8_lossy(&key_output.stderr);
                    anyhow::bail!(
                        "Failed to get storage account key: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }

                let key = String::from_utf8_lossy(&key_output.stdout)
                    .trim()
                    .to_string();
                let unc = crate::handlers::build_azure_files_unc(&account, &share);
                let mount_str = mount_dir.display().to_string();

                // Create mount point (best-effort; mount will fail if this fails)
                let mkdir_status = std::process::Command::new("sudo")
                    .args(["mkdir", "-p", &mount_str])
                    .status()?;
                if !mkdir_status.success() {
                    eprintln!("Warning: failed to create mount point {}", mount_str);
                }

                // Write credentials to a temp file instead of passing on CLI
                // to avoid exposing the storage key in process listings.
                use std::os::unix::fs::PermissionsExt;
                let creds_dir = home_dir()?.join(".azlin");
                std::fs::create_dir_all(&creds_dir)?;
                let creds_path = creds_dir.join(format!(".mount_creds_{}", account));
                std::fs::write(
                    &creds_path,
                    format!("username={}\npassword={}\n", account, key),
                )?;
                std::fs::set_permissions(&creds_path, std::fs::Permissions::from_mode(0o600))?;

                let status = std::process::Command::new("sudo")
                    .args([
                        "mount",
                        "-t",
                        "cifs",
                        &unc,
                        &mount_str,
                        "-o",
                        &crate::handlers::build_cifs_mount_options(
                            &creds_path.display().to_string(),
                        ),
                    ])
                    .status()?;

                // Clean up credentials file after mount — warn if cleanup fails
                // since the file contains a storage account key in plaintext
                if let Err(e) = std::fs::remove_file(&creds_path) {
                    eprintln!(
                        "⚠ Warning: could not remove credentials file {}: {e}",
                        creds_path.display()
                    );
                    eprintln!("  Please remove it manually (contains storage account key).");
                }

                if status.success() {
                    println!("Mounted '{}' at {}", share, mount_str);
                } else {
                    anyhow::bail!("Failed to mount Azure Files share.");
                }
            }
            azlin_cli::StorageAction::UnmountFile { mount_point } => {
                let mount_str = mount_point
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "/mnt".to_string());

                let status = std::process::Command::new("sudo")
                    .args(["umount", &mount_str])
                    .status()?;

                if status.success() {
                    println!("Unmounted '{}'", mount_str);
                } else {
                    anyhow::bail!("Failed to unmount '{}'.", mount_str);
                }
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}
