//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use anyhow::Result;

// ── Storage formatting helpers ───────────────────────────────────────

/// Format a storage account's key details for display.
/// Returns a list of (key, value) pairs.
pub fn format_storage_status(acct: &serde_json::Value) -> Vec<(String, String)> {
    vec![
        (
            "Name".to_string(),
            acct["name"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "Location".to_string(),
            acct["location"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "Kind".to_string(),
            acct["kind"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "SKU".to_string(),
            acct["sku"]["name"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "State".to_string(),
            acct["provisioningState"]
                .as_str()
                .unwrap_or("-")
                .to_string(),
        ),
        (
            "Primary Endpoint".to_string(),
            acct["primaryEndpoints"]["file"]
                .as_str()
                .unwrap_or("-")
                .to_string(),
        ),
    ]
}

/// Build the NFS mount command string for a storage account.
pub fn build_nfs_mount_command(storage_name: &str, mount_point: &str) -> String {
    format!(
        "sudo mkdir -p {mp} && sudo mount -t nfs {name}.file.core.windows.net:/{name}/home {mp} -o vers=3,sec=sys",
        name = storage_name,
        mp = mount_point,
    )
}

/// Build the CIFS mount options string.
pub fn build_cifs_mount_options(credentials_path: &str) -> String {
    format!(
        "vers=3.0,credentials={},serverino,nosharesock,actimeo=30",
        credentials_path
    )
}

/// Build the UNC path for an Azure Files share.
pub fn build_azure_files_unc(account: &str, share: &str) -> String {
    format!("//{}.file.core.windows.net/{}", account, share)
}

// ── Storage formatting handlers ─────────────────────────────────────────

/// Format the output message for a successful storage account creation.
pub fn format_storage_created(name: &str, size: u32, tier: &str) -> String {
    format!("Created storage account '{}' ({} GB, {})", name, size, tier)
}

/// Format the output message for a successful storage account deletion.
pub fn format_storage_deleted(name: &str) -> String {
    format!("Deleted storage account '{}'", name)
}

/// Format the mount success message.
pub fn format_storage_mounted(storage_name: &str, vm: &str, mount_point: &str) -> String {
    format!(
        "Mounted '{}' on VM '{}' at {}",
        storage_name, vm, mount_point
    )
}

/// Format the unmount success message.
pub fn format_storage_unmounted(vm: &str) -> String {
    format!("Unmounted NFS storage from VM '{}'", vm)
}

/// Validate a storage account name (Azure allows only [a-zA-Z0-9-]).
pub fn validate_storage_name(name: &str) -> Result<()> {
    if !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        anyhow::bail!("Invalid storage name: contains disallowed characters");
    }
    Ok(())
}

/// Determine the default mount point for NFS storage.
pub fn default_nfs_mount_point(storage_name: &str) -> String {
    format!("/mnt/{}", storage_name)
}
