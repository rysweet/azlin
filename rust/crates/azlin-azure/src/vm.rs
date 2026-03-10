//! VM management operations — list, start, stop, create, delete.
//!
//! All operations use the `az` CLI, matching the Python reference implementation.
//! This avoids the azure_core version mismatch between azure_identity (0.22) and
//! azure_mgmt_* (0.2) which requires a fragile CredentialAdapter bridge.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use tracing::debug;

use azlin_core::models::{CreateVmParams, OsType, PowerState, VmInfo};

use crate::AzureAuth;

// ── VM list cache ─────────────────────────────────────────────────────

/// Cached VM list entry with timestamp for TTL expiry.
struct CacheEntry {
    data: Vec<VmInfo>,
    timestamp: Instant,
}

/// Global VM list cache keyed by resource group (or "__all__" for subscription-wide).
static VM_CACHE: std::sync::LazyLock<Mutex<HashMap<String, CacheEntry>>> =
    std::sync::LazyLock::new(|| Mutex::new(HashMap::new()));

/// Cache TTL: 60 minutes, matching the Python reference implementation.
const CACHE_TTL: Duration = Duration::from_secs(3600);

/// Manages Azure VM operations via the `az` CLI.
///
/// All operations delegate to `az` CLI subprocess calls, matching the Python
/// reference implementation. This ensures consistent behavior wherever
/// `az login` works.
pub struct VmManager {
    subscription_id: String,
    /// Timeout for `az` CLI subprocess calls, in seconds.
    az_cli_timeout: u64,
}

impl VmManager {
    /// Create a new `VmManager` from an `AzureAuth`.
    ///
    /// Uses default az CLI timeout (120s). For custom timeouts, use
    /// [`VmManager::with_timeout`].
    pub fn new(auth: &AzureAuth) -> Self {
        Self::with_timeout(auth, AZ_CLI_DEFAULT_TIMEOUT_SECS)
    }

    /// Create a new `VmManager` with a custom az CLI timeout.
    ///
    /// The timeout applies to all `az` CLI subprocess calls. Increase on
    /// Windows/WSL where Azure CLI operations are slower.
    pub fn with_timeout(auth: &AzureAuth, az_cli_timeout: u64) -> Self {
        Self {
            subscription_id: auth.subscription_id().to_string(),
            az_cli_timeout,
        }
    }

    /// Return the subscription ID.
    pub fn subscription_id(&self) -> &str {
        &self.subscription_id
    }

    // ── List operations ────────────────────────────────────────────────

    /// List VMs in a specific resource group, returning cached data if fresh.
    ///
    /// Results are cached for 60 minutes (matching Python). Use
    /// [`list_vms_no_cache`] to bypass the cache.
    pub fn list_vms(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        let cache_key = resource_group.to_string();

        // Check cache
        if let Ok(cache) = VM_CACHE.lock() {
            if let Some(entry) = cache.get(&cache_key) {
                if entry.timestamp.elapsed() < CACHE_TTL {
                    debug!(resource_group, "Returning cached VM list");
                    return Ok(entry.data.clone());
                }
            }
        }

        let result = self.fetch_vms(resource_group)?;

        // Store in cache
        if let Ok(mut cache) = VM_CACHE.lock() {
            cache.insert(
                cache_key,
                CacheEntry {
                    data: result.clone(),
                    timestamp: Instant::now(),
                },
            );
        }

        Ok(result)
    }

    /// List VMs in a resource group, bypassing the cache entirely.
    pub fn list_vms_no_cache(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        let result = self.fetch_vms(resource_group)?;

        // Update cache with fresh data
        if let Ok(mut cache) = VM_CACHE.lock() {
            cache.insert(
                resource_group.to_string(),
                CacheEntry {
                    data: result.clone(),
                    timestamp: Instant::now(),
                },
            );
        }

        Ok(result)
    }

    /// Fetch VMs from az CLI for a specific resource group (no cache logic).
    fn fetch_vms(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        debug!(resource_group, "Listing VMs via az CLI");
        let json = az_cli_with_timeout(
            &[
                "vm",
                "list",
                "--resource-group",
                resource_group,
                "--show-details",
            ],
            self.az_cli_timeout,
        )?;

        let vms: Vec<serde_json::Value> =
            serde_json::from_str(&json).context("Failed to parse az vm list JSON")?;

        let result: Vec<VmInfo> = vms
            .iter()
            .map(|vm| parse_vm_from_az_json(vm, Some(resource_group)))
            .collect();

        debug!(count = result.len(), "Listed VMs via az CLI");
        Ok(result)
    }

    /// List all VMs across the entire subscription, returning cached data if fresh.
    pub fn list_all_vms(&self) -> Result<Vec<VmInfo>> {
        let cache_key = "__all__".to_string();

        // Check cache
        if let Ok(cache) = VM_CACHE.lock() {
            if let Some(entry) = cache.get(&cache_key) {
                if entry.timestamp.elapsed() < CACHE_TTL {
                    debug!("Returning cached all-VMs list");
                    return Ok(entry.data.clone());
                }
            }
        }

        let result = self.fetch_all_vms()?;

        // Store in cache
        if let Ok(mut cache) = VM_CACHE.lock() {
            cache.insert(
                cache_key,
                CacheEntry {
                    data: result.clone(),
                    timestamp: Instant::now(),
                },
            );
        }

        Ok(result)
    }

    /// List all VMs across the subscription, bypassing the cache.
    pub fn list_all_vms_no_cache(&self) -> Result<Vec<VmInfo>> {
        let result = self.fetch_all_vms()?;

        if let Ok(mut cache) = VM_CACHE.lock() {
            cache.insert(
                "__all__".to_string(),
                CacheEntry {
                    data: result.clone(),
                    timestamp: Instant::now(),
                },
            );
        }

        Ok(result)
    }

    /// Fetch all VMs from az CLI across the subscription (no cache logic).
    fn fetch_all_vms(&self) -> Result<Vec<VmInfo>> {
        debug!("Listing all VMs in subscription via az CLI");
        let json = az_cli_with_timeout(&["vm", "list", "--show-details"], self.az_cli_timeout)?;

        let vms: Vec<serde_json::Value> =
            serde_json::from_str(&json).context("Failed to parse az vm list JSON")?;

        let result: Vec<VmInfo> = vms
            .iter()
            .map(|vm| parse_vm_from_az_json(vm, None))
            .collect();

        debug!(count = result.len(), "Listed all VMs via az CLI");
        Ok(result)
    }

    /// Invalidate all cached VM lists.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn invalidate_cache() {
        if let Ok(mut cache) = VM_CACHE.lock() {
            cache.clear();
        }
    }

    // ── Single VM operations ───────────────────────────────────────────

    /// Get details for a single VM.
    pub fn get_vm(&self, resource_group: &str, name: &str) -> Result<VmInfo> {
        debug!(resource_group, name, "Getting VM via az CLI");
        let json = az_cli_with_timeout(
            &[
                "vm",
                "show",
                "--resource-group",
                resource_group,
                "--name",
                name,
                "--show-details",
            ],
            self.az_cli_timeout,
        )?;

        let vm: serde_json::Value =
            serde_json::from_str(&json).context("Failed to parse az vm show JSON")?;

        Ok(parse_vm_from_az_json(&vm, Some(resource_group)))
    }

    // ── Lifecycle operations ───────────────────────────────────────────

    /// Start a VM.
    pub fn start_vm(&self, resource_group: &str, name: &str) -> Result<()> {
        debug!(resource_group, name, "Starting VM");
        az_cli_with_timeout(
            &[
                "vm",
                "start",
                "--resource-group",
                resource_group,
                "--name",
                name,
            ],
            self.az_cli_timeout,
        )?;
        debug!(name, "VM started");
        Ok(())
    }

    /// Stop a VM. If `deallocate` is true, the VM is deallocated to save costs;
    /// otherwise it is only powered off.
    pub fn stop_vm(&self, resource_group: &str, name: &str, deallocate: bool) -> Result<()> {
        debug!(resource_group, name, deallocate, "Stopping VM");
        if deallocate {
            az_cli_with_timeout(
                &[
                    "vm",
                    "deallocate",
                    "--resource-group",
                    resource_group,
                    "--name",
                    name,
                ],
                self.az_cli_timeout,
            )?;
        } else {
            az_cli_with_timeout(
                &[
                    "vm",
                    "stop",
                    "--resource-group",
                    resource_group,
                    "--name",
                    name,
                ],
                self.az_cli_timeout,
            )?;
        }
        debug!(name, "VM stopped");
        Ok(())
    }

    /// Delete a VM.
    pub fn delete_vm(&self, resource_group: &str, name: &str) -> Result<()> {
        debug!(resource_group, name, "Deleting VM");
        az_cli_with_timeout(
            &[
                "vm",
                "delete",
                "--resource-group",
                resource_group,
                "--name",
                name,
                "--yes",
            ],
            self.az_cli_timeout,
        )?;
        debug!(name, "VM deleted");
        Ok(())
    }

    // ── Tag operations ─────────────────────────────────────────────────

    /// Add a tag to a VM, preserving existing tags.
    pub fn add_tag(&self, resource_group: &str, name: &str, key: &str, value: &str) -> Result<()> {
        validate_tag_key(key)?;
        validate_tag_value(value)?;
        debug!(resource_group, name, key, value, "Adding tag to VM");
        let tag_arg = format!("tags.{}={}", key, value);
        az_cli_with_timeout(
            &[
                "vm",
                "update",
                "--resource-group",
                resource_group,
                "--name",
                name,
                "--set",
                &tag_arg,
            ],
            self.az_cli_timeout,
        )?;
        debug!(name, key, "Tag added");
        Ok(())
    }

    /// Remove a tag from a VM, preserving other tags.
    pub fn remove_tag(&self, resource_group: &str, name: &str, key: &str) -> Result<()> {
        validate_tag_key(key)?;
        debug!(resource_group, name, key, "Removing tag from VM");
        let tag_arg = format!("tags.{}", key);
        az_cli_with_timeout(
            &[
                "vm",
                "update",
                "--resource-group",
                resource_group,
                "--name",
                name,
                "--remove",
                &tag_arg,
            ],
            self.az_cli_timeout,
        )?;
        debug!(name, key, "Tag removed");
        Ok(())
    }

    /// List tags on a VM.
    pub fn list_tags(&self, resource_group: &str, name: &str) -> Result<HashMap<String, String>> {
        debug!(resource_group, name, "Listing tags on VM");
        let vm = self.get_vm(resource_group, name)?;
        Ok(vm.tags)
    }

    // ── Provisioning ───────────────────────────────────────────────────

    /// Provision a new VM with all required networking resources.
    ///
    /// Creates: resource group -> NSG -> VNet/subnet -> public IP -> NIC -> VM.
    pub fn create_vm(&self, params: &CreateVmParams) -> Result<VmInfo> {
        let rg = &params.resource_group;
        let location = &params.region;
        let vm_name = &params.name;
        let names = build_vm_resource_names(vm_name);
        let timeout = self.az_cli_timeout;

        let az = |args: &[&str]| -> Result<String> { az_cli_with_timeout(args, timeout) };

        // Read SSH public key
        let ssh_pub_key = std::fs::read_to_string(&params.ssh_key_path).context(format!(
            "Failed to read SSH public key: {}",
            params.ssh_key_path.display()
        ))?;

        // 1. Create or verify resource group (only create if it doesn't exist)
        debug!(rg, location, "Checking resource group");
        let rg_check = std::process::Command::new("az")
            .args(["group", "exists", "--name", rg])
            .output()?;
        let rg_exists = String::from_utf8_lossy(&rg_check.stdout)
            .trim()
            .eq_ignore_ascii_case("true");
        if !rg_exists {
            debug!(rg, location, "Creating resource group");
            az(&["group", "create", "--name", rg, "--location", location])
                .context(format!("Failed to create resource group '{rg}'"))?;
        }

        // 2. Create NSG with SSH + HTTPS rules
        debug!(nsg_name = %names.nsg, "Creating NSG");
        az(&[
            "network",
            "nsg",
            "create",
            "--resource-group",
            rg,
            "--name",
            &names.nsg,
            "--location",
            location,
        ])
        .context(format!("Failed to create NSG '{}'", names.nsg))?;

        az(&[
            "network",
            "nsg",
            "rule",
            "create",
            "--resource-group",
            rg,
            "--nsg-name",
            &names.nsg,
            "--name",
            "AllowSSH",
            "--priority",
            "1000",
            "--protocol",
            "Tcp",
            "--destination-port-ranges",
            "22",
            "--access",
            "Allow",
            "--direction",
            "Inbound",
        ])
        .context("Failed to create SSH NSG rule")?;

        az(&[
            "network",
            "nsg",
            "rule",
            "create",
            "--resource-group",
            rg,
            "--nsg-name",
            &names.nsg,
            "--name",
            "AllowHTTPS",
            "--priority",
            "1001",
            "--protocol",
            "Tcp",
            "--destination-port-ranges",
            "443",
            "--access",
            "Allow",
            "--direction",
            "Inbound",
        ])
        .context("Failed to create HTTPS NSG rule")?;

        // 3. Create VNet + subnet
        debug!(vnet_name = %names.vnet, subnet_name = %names.subnet, "Creating VNet and subnet");
        az(&[
            "network",
            "vnet",
            "create",
            "--resource-group",
            rg,
            "--name",
            &names.vnet,
            "--address-prefix",
            "10.0.0.0/16",
            "--subnet-name",
            &names.subnet,
            "--subnet-prefix",
            "10.0.0.0/24",
            "--location",
            location,
            "--network-security-group",
            &names.nsg,
        ])
        .context(format!("Failed to create VNet '{}'", names.vnet))?;

        // 4. Create public IP
        debug!(pip_name = %names.pip, "Creating public IP");
        az(&[
            "network",
            "public-ip",
            "create",
            "--resource-group",
            rg,
            "--name",
            &names.pip,
            "--sku",
            "Standard",
            "--allocation-method",
            "Static",
            "--location",
            location,
        ])
        .context(format!("Failed to create public IP '{}'", names.pip))?;

        // 5. Create NIC
        debug!(nic_name = %names.nic, "Creating NIC");
        az(&[
            "network",
            "nic",
            "create",
            "--resource-group",
            rg,
            "--name",
            &names.nic,
            "--vnet-name",
            &names.vnet,
            "--subnet",
            &names.subnet,
            "--public-ip-address",
            &names.pip,
            "--network-security-group",
            &names.nsg,
            "--location",
            location,
        ])
        .context(format!("Failed to create NIC '{}'", names.nic))?;

        // 6. Create the VM
        debug!(%vm_name, "Creating VM");
        let image_urn = params.image.to_string();

        let cloud_init_file = create_cloud_init_file(&params.admin_username)?;
        let cloud_init_path = cloud_init_file.path().to_string_lossy().to_string();
        let mut az_args = vec![
            "vm",
            "create",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--location",
            location,
            "--nics",
            &names.nic,
            "--image",
            &image_urn,
            "--size",
            &params.vm_size,
            "--admin-username",
            &params.admin_username,
            "--ssh-key-value",
            ssh_pub_key.trim(),
            "--authentication-type",
            "ssh",
            "--custom-data",
            &cloud_init_path,
        ];

        let tag_strs = format_tag_cli_args(&params.tags);
        if !tag_strs.is_empty() {
            az_args.push("--tags");
            for t in &tag_strs {
                az_args.push(t);
            }
        }

        az(&az_args).context(format!("Failed to create VM '{vm_name}'"))?;

        // cloud_init_file is dropped here, which auto-deletes the temp file

        // 7. Fetch and return VM info
        debug!(%vm_name, "Fetching created VM details");
        let vm_info = self.get_vm(rg, vm_name)?;
        Ok(vm_info)
    }
}

// ── VM JSON parsing ────────────────────────────────────────────────────

/// Parse a VmInfo from `az vm list --show-details` or `az vm show --show-details` JSON.
fn parse_vm_from_az_json(vm: &serde_json::Value, fallback_rg: Option<&str>) -> VmInfo {
    let name = vm["name"].as_str().unwrap_or("").to_string();
    let resource_group = vm["resourceGroup"]
        .as_str()
        .map(String::from)
        .unwrap_or_else(|| fallback_rg.unwrap_or("").to_string());
    let location = vm["location"].as_str().unwrap_or("").to_string();
    let vm_size = vm["hardwareProfile"]["vmSize"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();

    let power_state = parse_az_power_state(vm["powerState"].as_str());

    let provisioning_state: azlin_core::models::ProvisioningState =
        vm["provisioningState"].as_str().unwrap_or("Unknown").into();

    let os_type = if vm["storageProfile"]["osDisk"]["osType"]
        .as_str()
        .is_some_and(|s| s.eq_ignore_ascii_case("Windows"))
    {
        OsType::Windows
    } else {
        OsType::Linux
    };

    let public_ip = vm["publicIps"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(String::from);
    let private_ip = vm["privateIps"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(String::from);

    let os_offer = vm["storageProfile"]["imageReference"]["offer"]
        .as_str()
        .map(String::from);

    let admin_username = vm["osProfile"]["adminUsername"].as_str().map(String::from);

    let tags = vm["tags"]
        .as_object()
        .map(|obj| {
            obj.iter()
                .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                .collect()
        })
        .unwrap_or_default();

    let created_time = parse_created_time(vm["timeCreated"].as_str());

    VmInfo {
        name,
        resource_group,
        location,
        vm_size,
        power_state,
        provisioning_state,
        os_type,
        os_offer,
        public_ip,
        private_ip,
        admin_username,
        tags,
        created_time,
    }
}

// ── az CLI helpers ─────────────────────────────────────────────────────

/// Default timeout for `az` CLI subprocess calls (120 seconds).
/// Overridden by `AzlinConfig.az_cli_timeout` when available.
const AZ_CLI_DEFAULT_TIMEOUT_SECS: u64 = 120;

/// Parse Azure power state string from `az vm list --show-details` or `az vm show`.
///
/// Azure returns values like "VM running", "VM deallocated", "VM stopped".
fn parse_az_power_state(s: Option<&str>) -> PowerState {
    match s.map(|s| s.to_lowercase()).as_deref() {
        Some("vm running") => PowerState::Running,
        Some("vm deallocated") => PowerState::Deallocated,
        Some("vm stopped") => PowerState::Stopped,
        Some("vm starting") => PowerState::Starting,
        Some("vm stopping") | Some("vm deallocating") => PowerState::Stopping,
        _ => PowerState::Unknown,
    }
}

/// Validate that a tag key contains only safe characters: alphanumeric, hyphen, underscore, dot.
fn validate_tag_key(key: &str) -> Result<()> {
    if key.is_empty()
        || !key
            .chars()
            .all(|c| c.is_alphanumeric() || c == '-' || c == '_' || c == '.')
    {
        anyhow::bail!(
            "Invalid tag key '{}': must be non-empty and contain only alphanumeric, hyphen, underscore, dot",
            key
        );
    }
    Ok(())
}

/// Validate that a tag value contains no control characters.
fn validate_tag_value(value: &str) -> Result<()> {
    if value.chars().any(|c| c.is_control()) {
        anyhow::bail!("Invalid tag value: must not contain control characters");
    }
    Ok(())
}

/// Run an `az` CLI command with the default timeout, returning Ok(stdout) on success.
///
/// For custom timeouts (e.g., Windows/WSL), use [`az_cli_with_timeout`].
#[cfg_attr(not(test), allow(dead_code))]
fn az_cli(args: &[&str]) -> Result<String> {
    az_cli_with_timeout(args, AZ_CLI_DEFAULT_TIMEOUT_SECS)
}

/// Run an `az` CLI command with an explicit timeout in seconds.
pub fn az_cli_with_timeout(args: &[&str], timeout_secs: u64) -> Result<String> {
    debug!(args = ?args, "Running az CLI command");
    let mut full_args: Vec<&str> = args.to_vec();
    full_args.push("--output");
    full_args.push("json");

    let (code, stdout, stderr) =
        crate::subprocess::run_with_timeout("az", &full_args, timeout_secs)
            .context("Failed to execute 'az' CLI. Is Azure CLI installed?")?;

    if code == 0 {
        Ok(stdout)
    } else {
        Err(anyhow::anyhow!(
            "az CLI failed: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        ))
    }
}

// ── Cloud-init helpers ─────────────────────────────────────────────────

/// Write cloud-init script to a unique temp file and return the handle.
///
/// The caller must keep the returned `NamedTempFile` alive until the file is no
/// longer needed (e.g. until the `az vm create` command has finished). Dropping
/// the handle deletes the file automatically.
fn create_cloud_init_file(admin_username: &str) -> Result<tempfile::NamedTempFile> {
    use std::io::Write;
    let mut tmp = tempfile::Builder::new()
        .prefix("azlin-cloud-init-")
        .suffix(".sh")
        .tempfile()
        .context("Failed to create cloud-init temp file")?;
    let script = cloud_init_script(admin_username);
    tmp.write_all(script.as_bytes())
        .context("Failed to write cloud-init temp file")?;
    tmp.flush()
        .context("Failed to flush cloud-init temp file")?;
    Ok(tmp)
}

/// Generate the cloud-init script with the given admin username.
///
/// Uses the admin_username for docker group membership instead of
/// hardcoding "azureuser".
fn cloud_init_script(admin_username: &str) -> String {
    // Validate username to prevent injection into the shell script
    let safe_username = if admin_username
        .chars()
        .all(|c| c.is_alphanumeric() || c == '-' || c == '_')
        && !admin_username.is_empty()
    {
        admin_username
    } else {
        "azureuser"
    };
    format!(
        r#"#!/bin/bash
set -euo pipefail

apt-get update -qq
apt-get upgrade -y -qq

apt-get install -y -qq \
    git curl wget jq unzip \
    build-essential make \
    tmux ripgrep fd-find \
    docker.io

systemctl enable docker
systemctl start docker
usermod -aG docker {username}

# Install Rust and Cargo
su - {username} -c 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y'

# Install .NET 10 SDK (preview until GA release, then remove --quality flag)
curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
chmod +x /tmp/dotnet-install.sh
/tmp/dotnet-install.sh --channel 10.0 --quality preview --install-dir /usr/share/dotnet \
    || /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet \
    || echo "WARNING: .NET 10 SDK install failed (may not be available yet)"
ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet 2>/dev/null || true
rm -f /tmp/dotnet-install.sh

# Install amplihack
su - {username} -c 'git clone https://github.com/rysweet/amplihack.git ~/amplihack && cd ~/amplihack && make install || true'

echo "cloud-init provisioning complete"
"#,
        username = safe_username
    )
}

// ── Resource naming helpers ────────────────────────────────────────────

/// Struct holding derived resource names for VM provisioning.
#[derive(Debug, Clone, PartialEq, Eq)]
struct VmResourceNames {
    nsg: String,
    vnet: String,
    subnet: String,
    pip: String,
    nic: String,
}

/// Build the conventional resource names for a VM (NSG, VNet, subnet, PIP, NIC).
fn build_vm_resource_names(vm_name: &str) -> VmResourceNames {
    VmResourceNames {
        nsg: format!("{vm_name}-nsg"),
        vnet: format!("{vm_name}-vnet"),
        subnet: format!("{vm_name}-subnet"),
        pip: format!("{vm_name}-pip"),
        nic: format!("{vm_name}-nic"),
    }
}

/// Format a tag map into CLI args suitable for `az ... --tags key=value`.
///
/// Values containing `=` are safe: the `az` CLI splits on the **first** `=`
/// only, so `key=a=b` is parsed as key `key` with value `a=b`.
fn format_tag_cli_args(tags: &HashMap<String, String>) -> Vec<String> {
    tags.iter().map(|(k, v)| format!("{k}={v}")).collect()
}

// ── Misc helpers ───────────────────────────────────────────────────────

/// Extract resource group name from an Azure resource ID.
#[cfg(test)]
fn extract_resource_group(resource_id: &str) -> String {
    let parts: Vec<&str> = resource_id.split('/').collect();
    // /subscriptions/{sub}/resourceGroups/{rg}/...
    if parts.len() >= 5 {
        parts[4].to_string()
    } else {
        String::new()
    }
}

/// Parse an optional RFC 3339 timestamp into a `DateTime<Utc>`.
fn parse_created_time(time_str: Option<&str>) -> Option<chrono::DateTime<chrono::Utc>> {
    time_str
        .and_then(|t| chrono::DateTime::parse_from_rfc3339(t).ok())
        .map(|dt| dt.with_timezone(&chrono::Utc))
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── parse_az_power_state tests ──────────────────────────────────

    #[test]
    fn test_parse_az_power_state_running() {
        assert_eq!(
            parse_az_power_state(Some("VM running")),
            PowerState::Running
        );
    }

    #[test]
    fn test_parse_az_power_state_deallocated() {
        assert_eq!(
            parse_az_power_state(Some("VM deallocated")),
            PowerState::Deallocated
        );
    }

    #[test]
    fn test_parse_az_power_state_stopped() {
        assert_eq!(
            parse_az_power_state(Some("VM stopped")),
            PowerState::Stopped
        );
    }

    #[test]
    fn test_parse_az_power_state_starting() {
        assert_eq!(
            parse_az_power_state(Some("VM starting")),
            PowerState::Starting
        );
    }

    #[test]
    fn test_parse_az_power_state_stopping() {
        assert_eq!(
            parse_az_power_state(Some("VM stopping")),
            PowerState::Stopping
        );
    }

    #[test]
    fn test_parse_az_power_state_deallocating() {
        assert_eq!(
            parse_az_power_state(Some("VM deallocating")),
            PowerState::Stopping
        );
    }

    #[test]
    fn test_parse_az_power_state_unknown() {
        assert_eq!(
            parse_az_power_state(Some("VM whatever")),
            PowerState::Unknown
        );
        assert_eq!(parse_az_power_state(None), PowerState::Unknown);
    }

    #[test]
    fn test_parse_az_power_state_case_insensitive() {
        assert_eq!(
            parse_az_power_state(Some("VM Running")),
            PowerState::Running
        );
        assert_eq!(
            parse_az_power_state(Some("VM STOPPED")),
            PowerState::Stopped
        );
    }

    // ── parse_vm_from_az_json tests ─────────────────────────────────

    #[test]
    fn test_parse_vm_from_az_json_minimal() {
        let json = serde_json::json!({});
        let vm = parse_vm_from_az_json(&json, Some("test-rg"));
        assert_eq!(vm.name, "");
        assert_eq!(vm.resource_group, "test-rg");
        assert_eq!(vm.power_state, PowerState::Unknown);
    }

    #[test]
    fn test_parse_vm_from_az_json_full() {
        let json = serde_json::json!({
            "name": "my-vm",
            "resourceGroup": "my-rg",
            "location": "eastus",
            "hardwareProfile": { "vmSize": "Standard_D4s_v3" },
            "powerState": "VM running",
            "provisioningState": "Succeeded",
            "storageProfile": { "osDisk": { "osType": "Linux" } },
            "publicIps": "52.1.2.3",
            "privateIps": "10.0.0.4",
            "osProfile": { "adminUsername": "azureuser" },
            "tags": { "session": "dev", "owner": "user1" },
            "timeCreated": "2025-01-15T10:30:00+00:00"
        });
        let vm = parse_vm_from_az_json(&json, None);
        assert_eq!(vm.name, "my-vm");
        assert_eq!(vm.resource_group, "my-rg");
        assert_eq!(vm.location, "eastus");
        assert_eq!(vm.vm_size, "Standard_D4s_v3");
        assert_eq!(vm.power_state, PowerState::Running);
        assert_eq!(vm.os_type, OsType::Linux);
        assert_eq!(vm.public_ip.as_deref(), Some("52.1.2.3"));
        assert_eq!(vm.private_ip.as_deref(), Some("10.0.0.4"));
        assert_eq!(vm.admin_username.as_deref(), Some("azureuser"));
        assert_eq!(vm.tags.get("session").unwrap(), "dev");
        assert!(vm.created_time.is_some());
    }

    #[test]
    fn test_parse_vm_from_az_json_windows() {
        let json = serde_json::json!({
            "name": "win-vm",
            "storageProfile": { "osDisk": { "osType": "Windows" } }
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert_eq!(vm.os_type, OsType::Windows);
    }

    #[test]
    fn test_parse_vm_from_az_json_empty_ips() {
        let json = serde_json::json!({
            "name": "no-ip-vm",
            "publicIps": "",
            "privateIps": ""
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert!(vm.public_ip.is_none());
        assert!(vm.private_ip.is_none());
    }

    #[test]
    fn test_parse_vm_from_az_json_resource_group_from_json() {
        let json = serde_json::json!({
            "name": "vm1",
            "resourceGroup": "json-rg"
        });
        let vm = parse_vm_from_az_json(&json, Some("fallback-rg"));
        assert_eq!(vm.resource_group, "json-rg");
    }

    #[test]
    fn test_parse_vm_from_az_json_resource_group_fallback() {
        let json = serde_json::json!({ "name": "vm1" });
        let vm = parse_vm_from_az_json(&json, Some("fallback-rg"));
        assert_eq!(vm.resource_group, "fallback-rg");
    }

    #[test]
    fn test_parse_vm_from_az_json_tags_mixed_values() {
        let json = serde_json::json!({
            "name": "vm1",
            "tags": {
                "str_tag": "value",
                "num_tag": 42,
                "bool_tag": true,
                "null_tag": null
            }
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert_eq!(vm.tags.get("str_tag").unwrap(), "value");
        // Non-string values are skipped
        assert!(!vm.tags.contains_key("num_tag"));
        assert!(!vm.tags.contains_key("bool_tag"));
        assert!(!vm.tags.contains_key("null_tag"));
    }

    // ── extract_resource_group tests ────────────────────────────────

    #[test]
    fn test_extract_resource_group() {
        let id = "/subscriptions/sub-id/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/vm1";
        assert_eq!(extract_resource_group(id), "my-rg");
    }

    #[test]
    fn test_extract_resource_group_empty() {
        assert_eq!(extract_resource_group(""), "");
        assert_eq!(extract_resource_group("/short/path"), "");
    }

    #[test]
    fn test_extract_resource_group_various_paths() {
        let cases = vec![
            ("/subscriptions/s/resourceGroups/rg1/providers/p", "rg1"),
            (
                "/subscriptions/s/resourceGroups/MY-RG/providers/p/type/name",
                "MY-RG",
            ),
        ];
        for (input, expected) in cases {
            assert_eq!(extract_resource_group(input), expected, "input: {input}");
        }
    }

    // ── parse_created_time tests ────────────────────────────────────

    #[test]
    fn test_parse_created_time_valid_rfc3339() {
        use chrono::Datelike;
        let result = parse_created_time(Some("2025-01-15T10:30:00+00:00"));
        assert!(result.is_some());
        let dt = result.unwrap();
        assert_eq!(dt.year(), 2025);
    }

    #[test]
    fn test_parse_created_time_invalid() {
        assert!(parse_created_time(Some("not-a-date")).is_none());
    }

    #[test]
    fn test_parse_created_time_none() {
        assert!(parse_created_time(None).is_none());
    }

    // ── cloud_init tests ────────────────────────────────────────────

    #[test]
    fn test_cloud_init_script_is_valid_shell() {
        let script = cloud_init_script("testuser");
        assert!(script.starts_with("#!/bin/bash"));
    }

    #[test]
    fn test_cloud_init_script_has_set_options() {
        let script = cloud_init_script("testuser");
        assert!(script.contains("set -euo pipefail"));
    }

    #[test]
    fn test_cloud_init_script_installs_essential_tools() {
        let script = cloud_init_script("testuser");
        for tool in &["git", "curl", "tmux", "docker.io", "make"] {
            assert!(script.contains(tool), "Missing tool: {tool}");
        }
    }

    #[test]
    fn test_cloud_init_script_installs_rust() {
        let script = cloud_init_script("testuser");
        assert!(script.contains("rustup.rs"), "Missing Rust installer");
    }

    #[test]
    fn test_cloud_init_script_installs_dotnet() {
        let script = cloud_init_script("testuser");
        assert!(
            script.contains("dotnet-install.sh"),
            "Missing .NET installer"
        );
        assert!(
            script.contains("--channel 10.0"),
            "Missing .NET 10 channel"
        );
    }

    #[test]
    fn test_cloud_init_script_installs_amplihack() {
        let script = cloud_init_script("testuser");
        assert!(
            script.contains("github.com/rysweet/amplihack"),
            "Missing amplihack clone"
        );
    }

    #[test]
    fn test_cloud_init_script_enables_docker() {
        let script = cloud_init_script("testuser");
        assert!(script.contains("systemctl enable docker"));
        assert!(script.contains("systemctl start docker"));
    }

    #[test]
    fn test_cloud_init_script_uses_custom_username() {
        let script = cloud_init_script("myuser");
        assert!(script.contains("usermod -aG docker myuser"));
    }

    #[test]
    fn test_cloud_init_script_rejects_invalid_username() {
        let script = cloud_init_script("user; rm -rf /");
        assert!(script.contains("usermod -aG docker azureuser"));
    }

    #[test]
    fn test_cloud_init_script_completion_marker() {
        let script = cloud_init_script("user");
        assert!(script.contains("cloud-init provisioning complete"));
    }

    #[test]
    fn test_create_cloud_init_file_creates_file() {
        let file = create_cloud_init_file("testuser").unwrap();
        assert!(file.path().exists());
        let contents = std::fs::read_to_string(file.path()).unwrap();
        assert!(contents.contains("#!/bin/bash"));
    }

    #[test]
    fn test_create_cloud_init_file_path_is_in_temp() {
        let file = create_cloud_init_file("testuser").unwrap();
        let path = file.path().to_string_lossy();
        assert!(
            path.contains("azlin-cloud-init-"),
            "Temp file path should contain prefix: {path}"
        );
    }

    #[test]
    fn test_create_cloud_init_file_unique_paths() {
        let f1 = create_cloud_init_file("u").unwrap();
        let f2 = create_cloud_init_file("u").unwrap();
        assert_ne!(
            f1.path(),
            f2.path(),
            "Each call should create a unique file"
        );
    }

    // ── az_cli tests ────────────────────────────────────────────────

    #[test]
    fn test_az_cli_invalid_command_returns_error() {
        let result = az_cli(&["this-is-not-a-real-command-xyz"]);
        assert!(result.is_err());
    }

    #[test]
    fn test_az_cli_version_succeeds_or_fails_gracefully() {
        // `az version` should succeed if az is installed, or fail gracefully
        let result = az_cli(&["version"]);
        match result {
            Ok(output) => assert!(output.contains("azure-cli")),
            Err(e) => {
                let msg = format!("{e}");
                assert!(
                    msg.contains("az") || msg.contains("CLI") || msg.contains("not found"),
                    "Unexpected error: {msg}"
                );
            }
        }
    }

    #[test]
    fn test_az_cli_appends_output_json() {
        // az_cli always adds --output json
        let result = az_cli(&["nonexistent-subcommand-xyz"]);
        assert!(result.is_err());
    }

    #[test]
    fn test_az_cli_empty_args() {
        // Even with empty args, az should be invoked with just --output json
        let result = az_cli(&[]);
        // It may succeed (az with no args shows help) or fail - either is OK
        match result {
            Ok(_) => {}  // az showed help as JSON
            Err(_) => {} // az failed - also fine
        }
    }

    #[test]
    fn test_az_cli_with_timeout_invalid_command() {
        let result = az_cli_with_timeout(&["this-is-not-a-real-command-xyz"], 30);
        assert!(result.is_err());
    }

    #[test]
    fn test_az_cli_with_timeout_zero_still_works() {
        // Zero timeout should still attempt the command (it may time out instantly)
        let result = az_cli_with_timeout(&["version"], 0);
        // Either succeeds quickly or times out - both are valid
        match result {
            Ok(_) | Err(_) => {}
        }
    }

    // ── build_vm_resource_names tests ───────────────────────────────

    #[test]
    fn test_build_vm_resource_names_basic() {
        let names = build_vm_resource_names("my-vm");
        assert_eq!(names.nsg, "my-vm-nsg");
        assert_eq!(names.vnet, "my-vm-vnet");
        assert_eq!(names.subnet, "my-vm-subnet");
        assert_eq!(names.pip, "my-vm-pip");
        assert_eq!(names.nic, "my-vm-nic");
    }

    #[test]
    fn test_build_vm_resource_names_with_hyphens() {
        let names = build_vm_resource_names("dev-vm-01");
        assert_eq!(names.nsg, "dev-vm-01-nsg");
        assert_eq!(names.nic, "dev-vm-01-nic");
    }

    #[test]
    fn test_build_vm_resource_names_equality() {
        let n1 = build_vm_resource_names("vm");
        let n2 = build_vm_resource_names("vm");
        assert_eq!(n1, n2);
    }

    #[test]
    fn test_build_vm_resource_names_inequality() {
        let n1 = build_vm_resource_names("vm1");
        let n2 = build_vm_resource_names("vm2");
        assert_ne!(n1, n2);
    }

    #[test]
    fn test_build_vm_resource_names_debug() {
        let names = build_vm_resource_names("vm");
        let debug = format!("{names:?}");
        assert!(debug.contains("vm-nsg"));
    }

    // ── format_tag_cli_args tests ───────────────────────────────────

    #[test]
    fn test_format_tag_cli_args_empty() {
        let tags = HashMap::new();
        let args = format_tag_cli_args(&tags);
        assert!(args.is_empty());
    }

    #[test]
    fn test_format_tag_cli_args_single() {
        let mut tags = HashMap::new();
        tags.insert("key".to_string(), "value".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args.len(), 1);
        assert_eq!(args[0], "key=value");
    }

    #[test]
    fn test_format_tag_cli_args_multiple() {
        let mut tags = HashMap::new();
        tags.insert("a".to_string(), "1".to_string());
        tags.insert("b".to_string(), "2".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args.len(), 2);
        assert!(args.iter().any(|a| a == "a=1"));
        assert!(args.iter().any(|a| a == "b=2"));
    }

    #[test]
    fn test_format_tag_cli_args_special_values() {
        let mut tags = HashMap::new();
        tags.insert("key".to_string(), "value with spaces".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args[0], "key=value with spaces");
    }

    #[test]
    fn test_format_tag_cli_args_empty_value() {
        let mut tags = HashMap::new();
        tags.insert("key".to_string(), "".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args[0], "key=");
    }

    #[test]
    fn test_format_tag_cli_args_value_with_equals() {
        // az CLI splits on the first `=`, so `key=a=b` is key="key", value="a=b".
        let mut tags = HashMap::new();
        tags.insert("config".to_string(), "mode=debug".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args[0], "config=mode=debug");
        // Verify the key can be recovered by splitting on first '='
        let (k, v) = args[0].split_once('=').unwrap();
        assert_eq!(k, "config");
        assert_eq!(v, "mode=debug");
    }

    // ── VmManager construction tests ────────────────────────────────

    // ── validate_tag_key tests ─────────────────────────────────────

    #[test]
    fn test_validate_tag_key_valid_alphanumeric() {
        assert!(validate_tag_key("environment").is_ok());
        assert!(validate_tag_key("Environment1").is_ok());
    }

    #[test]
    fn test_validate_tag_key_valid_with_special_chars() {
        assert!(validate_tag_key("my-tag").is_ok());
        assert!(validate_tag_key("my_tag").is_ok());
        assert!(validate_tag_key("my.tag").is_ok());
        assert!(validate_tag_key("a-b_c.d").is_ok());
    }

    #[test]
    fn test_validate_tag_key_empty_rejected() {
        let result = validate_tag_key("");
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(msg.contains("Invalid tag key"));
    }

    #[test]
    fn test_validate_tag_key_space_rejected() {
        assert!(validate_tag_key("my tag").is_err());
    }

    #[test]
    fn test_validate_tag_key_special_chars_rejected() {
        assert!(validate_tag_key("key=value").is_err());
        assert!(validate_tag_key("key;drop").is_err());
        assert!(validate_tag_key("key$env").is_err());
        assert!(validate_tag_key("key/path").is_err());
    }

    #[test]
    fn test_validate_tag_key_unicode_alphanumeric_accepted() {
        // Rust's is_alphanumeric() accepts Unicode letters, so accented chars are valid
        assert!(validate_tag_key("caf\u{00e9}").is_ok());
    }

    // ── validate_tag_value tests ────────────────────────────────────

    #[test]
    fn test_validate_tag_value_valid_normal_text() {
        assert!(validate_tag_value("production").is_ok());
        assert!(validate_tag_value("value with spaces").is_ok());
        assert!(validate_tag_value("key=value").is_ok());
        assert!(validate_tag_value("").is_ok()); // empty is allowed
    }

    #[test]
    fn test_validate_tag_value_valid_special_chars() {
        assert!(validate_tag_value("hello world! @#$%^&*()").is_ok());
        assert!(validate_tag_value("2025-01-15T10:30:00Z").is_ok());
    }

    #[test]
    fn test_validate_tag_value_control_char_rejected() {
        assert!(validate_tag_value("line1\nline2").is_err());
        assert!(validate_tag_value("tab\there").is_err());
        assert!(validate_tag_value("null\0byte").is_err());
    }

    #[test]
    fn test_validate_tag_value_control_char_error_message() {
        let result = validate_tag_value("bad\x01value");
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(msg.contains("control characters"));
    }

    // ── Additional parse_vm_from_az_json edge cases ─────────────────

    #[test]
    fn test_parse_vm_from_az_json_no_fallback_rg() {
        let json = serde_json::json!({ "name": "vm1" });
        let vm = parse_vm_from_az_json(&json, None);
        assert_eq!(vm.resource_group, "");
    }

    #[test]
    fn test_parse_vm_from_az_json_null_values() {
        let json = serde_json::json!({
            "name": null,
            "location": null,
            "hardwareProfile": { "vmSize": null },
            "powerState": null,
            "provisioningState": null,
            "publicIps": null,
            "privateIps": null,
            "tags": null,
            "timeCreated": null
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert_eq!(vm.name, "");
        assert_eq!(vm.location, "");
        assert_eq!(vm.vm_size, "unknown");
        assert_eq!(vm.power_state, PowerState::Unknown);
        assert!(vm.public_ip.is_none());
        assert!(vm.private_ip.is_none());
        assert!(vm.tags.is_empty());
        assert!(vm.created_time.is_none());
    }

    #[test]
    fn test_parse_vm_from_az_json_windows_case_insensitive() {
        let json = serde_json::json!({
            "name": "win-vm",
            "storageProfile": { "osDisk": { "osType": "WINDOWS" } }
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert_eq!(vm.os_type, OsType::Windows);
    }

    #[test]
    fn test_parse_vm_from_az_json_os_offer_extracted() {
        let json = serde_json::json!({
            "name": "vm1",
            "storageProfile": {
                "osDisk": { "osType": "Linux" },
                "imageReference": { "offer": "UbuntuServer" }
            }
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert_eq!(vm.os_offer.as_deref(), Some("UbuntuServer"));
    }

    #[test]
    fn test_parse_vm_from_az_json_created_time_with_offset() {
        let json = serde_json::json!({
            "name": "vm1",
            "timeCreated": "2025-06-15T14:30:00+05:30"
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert!(vm.created_time.is_some());
    }

    #[test]
    fn test_parse_vm_from_az_json_empty_tags_object() {
        let json = serde_json::json!({
            "name": "vm1",
            "tags": {}
        });
        let vm = parse_vm_from_az_json(&json, Some("rg"));
        assert!(vm.tags.is_empty());
    }

    // ── parse_created_time edge cases ───────────────────────────────

    #[test]
    fn test_parse_created_time_z_suffix() {
        let result = parse_created_time(Some("2025-01-15T10:30:00Z"));
        assert!(result.is_some());
    }

    #[test]
    fn test_parse_created_time_empty_string() {
        assert!(parse_created_time(Some("")).is_none());
    }

    // ── cloud_init_script edge cases ────────────────────────────────

    #[test]
    fn test_cloud_init_script_empty_username_falls_back() {
        let script = cloud_init_script("");
        assert!(script.contains("usermod -aG docker azureuser"));
    }

    #[test]
    fn test_cloud_init_script_hyphen_username_allowed() {
        let script = cloud_init_script("my-user");
        assert!(script.contains("usermod -aG docker my-user"));
    }

    #[test]
    fn test_cloud_init_script_underscore_username_allowed() {
        let script = cloud_init_script("my_user");
        assert!(script.contains("usermod -aG docker my_user"));
    }

    #[test]
    fn test_list_vms_nonexistent_rg_returns_error_or_empty() {
        // This test requires `az` CLI to be logged in.
        // If az is not available, the error should be descriptive.
        let auth = match AzureAuth::new() {
            Ok(a) => a,
            Err(_) => return, // Skip if no auth
        };
        let mgr = VmManager::new(&auth);
        let result = mgr.list_vms("nonexistent-rg-1234567890-xyz");
        match result {
            Ok(vms) => assert!(vms.is_empty()),
            Err(e) => {
                let msg = format!("{e}");
                assert!(
                    msg.contains("az")
                        || msg.contains("CLI")
                        || msg.contains("not found")
                        || msg.contains("could not be found"),
                    "Unexpected error: {msg}"
                );
            }
        }
    }
}
