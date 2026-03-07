#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use dialoguer::Confirm;
pub(crate) fn handle_storage_delete(
    name: &str,
    resource_group: Option<String>,
    force: bool,
) -> Result<()> {
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
            name,
            "--resource-group",
            &rg,
            "--yes",
        ])
        .output()?;

    pb.finish_and_clear();
    if output.status.success() {
        println!("{}", crate::handlers::format_storage_deleted(name));
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to delete storage account: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

pub(crate) fn handle_storage_mount_file(
    account: &str,
    share: &str,
    mount_point: Option<std::path::PathBuf>,
    resource_group: Option<String>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let mount_dir =
        mount_point.unwrap_or_else(|| std::path::PathBuf::from(format!("/mnt/{}", account)));

    let key_output = std::process::Command::new("az")
        .args([
            "storage",
            "account",
            "keys",
            "list",
            "--account-name",
            account,
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
    let unc = crate::handlers::build_azure_files_unc(account, share);
    let mount_str = mount_dir.display().to_string();

    let mkdir_status = std::process::Command::new("sudo")
        .args(["mkdir", "-p", &mount_str])
        .status()?;
    if !mkdir_status.success() {
        eprintln!("Warning: failed to create mount point {}", mount_str);
    }

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
            &crate::handlers::build_cifs_mount_options(&creds_path.display().to_string()),
        ])
        .status()?;

    if let Err(e) = std::fs::remove_file(&creds_path) {
        eprintln!(
            "Warning: could not remove credentials file {}: {e}",
            creds_path.display()
        );
        eprintln!("  Please remove it manually (contains storage account key).");
    }

    if status.success() {
        println!("Mounted '{}' at {}", share, mount_str);
    } else {
        anyhow::bail!("Failed to mount Azure Files share.");
    }
    Ok(())
}

pub(crate) fn handle_storage_unmount_file(mount_point: Option<std::path::PathBuf>) -> Result<()> {
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
    Ok(())
}
