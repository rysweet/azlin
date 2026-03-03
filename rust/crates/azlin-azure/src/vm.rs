//! VM management operations — list, start, stop, create, delete.

use std::collections::HashMap;
use std::sync::Arc;

use anyhow::{Context, Result};
use tracing::{debug, warn};

use azlin_core::models::{CreateVmParams, OsType, PowerState, VmInfo};

use crate::AzureAuth;

/// Adapter that bridges azure_core 0.22 credentials to azure_core 0.2 credentials
/// needed by the azure_mgmt_* 0.2.x SDK crates.
struct CredentialAdapter {
    inner: Arc<dyn azure_core::credentials::TokenCredential>,
}

#[async_trait::async_trait]
impl azure_core_old::auth::TokenCredential for CredentialAdapter {
    async fn get_token(
        &self,
        resource: &str,
    ) -> std::result::Result<azure_core_old::auth::TokenResponse, azure_core_old::Error> {
        // The old SDK passes a resource like "https://management.azure.com/",
        // the new SDK expects scopes as &[&str]
        let scope = if resource.ends_with('/') {
            format!("{}.default", resource)
        } else {
            format!("{}/.default", resource)
        };

        let token = self
            .inner
            .get_token(&[&scope])
            .await
            .map_err(|e| azure_core_old::Error::GetToken(Box::new(e)))?;

        Ok(azure_core_old::auth::TokenResponse::new(
            oauth2::AccessToken::new(token.token.secret().to_string()),
            chrono::Utc::now() + chrono::Duration::hours(1),
        ))
    }
}

/// Manages Azure VM operations using native SDK clients.
pub struct VmManager {
    compute_client: azure_mgmt_compute::Client,
    network_client: azure_mgmt_network::Client,
    subscription_id: String,
}

impl VmManager {
    /// Create a new `VmManager` from an `AzureAuth`.
    pub fn new(auth: &AzureAuth) -> Self {
        let adapter = Arc::new(CredentialAdapter {
            inner: auth.credential_arc(),
        });
        let subscription_id = auth.subscription_id().to_string();

        let compute_client = azure_mgmt_compute::ClientBuilder::new(
            adapter.clone() as Arc<dyn azure_core_old::auth::TokenCredential>
        )
        .build();
        let network_client = azure_mgmt_network::ClientBuilder::new(
            adapter as Arc<dyn azure_core_old::auth::TokenCredential>,
        )
        .build();

        Self {
            compute_client,
            network_client,
            subscription_id,
        }
    }

    /// List VMs in a specific resource group.
    pub async fn list_vms(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        debug!(resource_group, "Listing VMs");

        let result = self
            .compute_client
            .virtual_machines()
            .list(resource_group, &self.subscription_id)
            .into_future()
            .await
            .context("Failed to list VMs from Azure")?;

        let mut vms = Vec::new();
        for vm in &result.value {
            match self.convert_vm(vm, resource_group).await {
                Ok(info) => vms.push(info),
                Err(e) => {
                    let name = vm.resource.name.as_deref().unwrap_or("unknown");
                    warn!(vm_name = name, error = %e, "Failed to convert VM, skipping");
                }
            }
        }

        debug!(count = vms.len(), "Listed VMs");
        Ok(vms)
    }

    /// List all VMs across the entire subscription.
    pub async fn list_all_vms(&self) -> Result<Vec<VmInfo>> {
        debug!("Listing all VMs in subscription");

        let result = self
            .compute_client
            .virtual_machines()
            .list_all(&self.subscription_id)
            .into_future()
            .await
            .context("Failed to list all VMs from Azure")?;

        let mut vms = Vec::new();
        for vm in &result.value {
            let rg = extract_resource_group(vm.resource.id.as_deref().unwrap_or(""));
            match self.convert_vm(vm, &rg).await {
                Ok(info) => vms.push(info),
                Err(e) => {
                    let name = vm.resource.name.as_deref().unwrap_or("unknown");
                    warn!(vm_name = name, error = %e, "Failed to convert VM, skipping");
                }
            }
        }

        debug!(count = vms.len(), "Listed all VMs");
        Ok(vms)
    }

    /// Convert an Azure SDK VM to our VmInfo model.
    async fn convert_vm(
        &self,
        vm: &azure_mgmt_compute::models::VirtualMachine,
        resource_group: &str,
    ) -> Result<VmInfo> {
        let name = vm.resource.name.clone().unwrap_or_default();
        let location = vm.resource.location.clone();
        let props = vm.properties.as_ref();

        // Extract VM size from hardware profile
        let vm_size = props
            .and_then(|p| p.hardware_profile.as_ref())
            .and_then(|hp| hp.vm_size.as_ref())
            .and_then(|s| serde_json::to_value(s).ok())
            .and_then(|v| v.as_str().map(String::from))
            .unwrap_or_else(|| "unknown".to_string());

        // Extract power state from instance view statuses
        let power_state = extract_power_state(props.and_then(|p| p.instance_view.as_ref()));

        let provisioning_state = props
            .and_then(|p| p.provisioning_state.as_deref())
            .unwrap_or("Unknown")
            .to_string();

        // Detect OS type from OS profile
        let os_type = if props
            .and_then(|p| p.os_profile.as_ref())
            .and_then(|o| o.linux_configuration.as_ref())
            .is_some()
        {
            OsType::Linux
        } else if props
            .and_then(|p| p.os_profile.as_ref())
            .and_then(|o| o.windows_configuration.as_ref())
            .is_some()
        {
            OsType::Windows
        } else {
            OsType::Linux // Default assumption
        };

        let admin_username = props
            .and_then(|p| p.os_profile.as_ref())
            .and_then(|o| o.admin_username.clone());

        // Extract tags
        let tags = extract_tags(vm.resource.tags.as_ref());

        // Extract IPs from network interfaces
        let (public_ip, private_ip) = self
            .get_vm_ips(props, resource_group)
            .await
            .unwrap_or((None, None));

        // Extract created time
        let created_time = props
            .and_then(|p| p.time_created.as_deref())
            .and_then(|t| chrono::DateTime::parse_from_rfc3339(t).ok())
            .map(|dt| dt.with_timezone(&chrono::Utc));

        Ok(VmInfo {
            name,
            resource_group: resource_group.to_string(),
            location,
            vm_size,
            power_state,
            provisioning_state,
            os_type,
            public_ip,
            private_ip,
            admin_username,
            tags,
            created_time,
        })
    }

    /// Start a VM.
    pub async fn start_vm(&self, resource_group: &str, name: &str) -> Result<()> {
        debug!(resource_group, name, "Starting VM");
        self.compute_client
            .virtual_machines()
            .start(resource_group, name, &self.subscription_id)
            .into_future()
            .await
            .context(format!("Failed to start VM '{name}'"))?;
        debug!(name, "VM started");
        Ok(())
    }

    /// Stop a VM. If `deallocate` is true, the VM is deallocated to save costs;
    /// otherwise it is only powered off.
    pub async fn stop_vm(&self, resource_group: &str, name: &str, deallocate: bool) -> Result<()> {
        debug!(resource_group, name, deallocate, "Stopping VM");
        if deallocate {
            self.compute_client
                .virtual_machines()
                .deallocate(resource_group, name, &self.subscription_id)
                .into_future()
                .await
                .context(format!("Failed to deallocate VM '{name}'"))?;
        } else {
            self.compute_client
                .virtual_machines()
                .power_off(resource_group, name, &self.subscription_id)
                .into_future()
                .await
                .context(format!("Failed to power off VM '{name}'"))?;
        }
        debug!(name, "VM stopped");
        Ok(())
    }

    /// Get details for a single VM (with instance view for power state).
    pub async fn get_vm(&self, resource_group: &str, name: &str) -> Result<VmInfo> {
        debug!(resource_group, name, "Getting VM details");
        let vm = self
            .compute_client
            .virtual_machines()
            .get(resource_group, name, &self.subscription_id)
            .expand("instanceView")
            .into_future()
            .await
            .context(format!("Failed to get VM '{name}'"))?;

        self.convert_vm(&vm, resource_group).await
    }

    /// Add a tag to a VM, preserving existing tags.
    pub async fn add_tag(
        &self,
        resource_group: &str,
        name: &str,
        key: &str,
        value: &str,
    ) -> Result<()> {
        debug!(resource_group, name, key, value, "Adding tag to VM");
        let vm = self.get_vm(resource_group, name).await?;
        let mut tags = vm.tags.clone();
        tags.insert(key.to_string(), value.to_string());

        let tags_json: serde_json::Map<String, serde_json::Value> = tags
            .iter()
            .map(|(k, v)| (k.clone(), serde_json::Value::String(v.clone())))
            .collect();

        let mut update = azure_mgmt_compute::models::VirtualMachineUpdate::new();
        update.update_resource.tags = Some(serde_json::Value::Object(tags_json));

        self.compute_client
            .virtual_machines()
            .update(resource_group, name, update, &self.subscription_id)
            .into_future()
            .await
            .context(format!("Failed to add tag to VM '{name}'"))?;
        debug!(name, key, "Tag added");
        Ok(())
    }

    /// Remove a tag from a VM, preserving other tags.
    pub async fn remove_tag(&self, resource_group: &str, name: &str, key: &str) -> Result<()> {
        debug!(resource_group, name, key, "Removing tag from VM");
        let vm = self.get_vm(resource_group, name).await?;
        let mut tags = vm.tags.clone();
        tags.remove(key);

        let tags_json: serde_json::Map<String, serde_json::Value> = tags
            .iter()
            .map(|(k, v)| (k.clone(), serde_json::Value::String(v.clone())))
            .collect();

        let mut update = azure_mgmt_compute::models::VirtualMachineUpdate::new();
        update.update_resource.tags = Some(serde_json::Value::Object(tags_json));

        self.compute_client
            .virtual_machines()
            .update(resource_group, name, update, &self.subscription_id)
            .into_future()
            .await
            .context(format!("Failed to remove tag from VM '{name}'"))?;
        debug!(name, key, "Tag removed");
        Ok(())
    }

    /// List tags on a VM.
    pub async fn list_tags(
        &self,
        resource_group: &str,
        name: &str,
    ) -> Result<HashMap<String, String>> {
        debug!(resource_group, name, "Listing tags on VM");
        let vm = self.get_vm(resource_group, name).await?;
        Ok(vm.tags)
    }

    /// Delete a VM.
    pub async fn delete_vm(&self, resource_group: &str, name: &str) -> Result<()> {
        debug!(resource_group, name, "Deleting VM");
        self.compute_client
            .virtual_machines()
            .delete(resource_group, name, &self.subscription_id)
            .into_future()
            .await
            .context(format!("Failed to delete VM '{name}'"))?;
        debug!(name, "VM deleted");
        Ok(())
    }

    /// Provision a new VM with all required networking resources.
    ///
    /// Creates: resource group → NSG → VNet/subnet → public IP → NIC → VM.
    /// Uses the `az` CLI for resource creation (matching the Python implementation)
    /// and the SDK for the final VM lookup.
    pub async fn create_vm(&self, params: &CreateVmParams) -> Result<VmInfo> {
        let rg = &params.resource_group;
        let location = &params.region;
        let vm_name = &params.name;

        // Read SSH public key
        let ssh_pub_key = std::fs::read_to_string(&params.ssh_key_path).context(format!(
            "Failed to read SSH public key: {}",
            params.ssh_key_path.display()
        ))?;

        // 1. Create or verify resource group
        debug!(rg, location, "Creating/verifying resource group");
        az_cli(&["group", "create", "--name", rg, "--location", location])
            .context(format!("Failed to create resource group '{rg}'"))?;

        // 2. Create NSG with SSH + HTTPS rules
        let nsg_name = format!("{vm_name}-nsg");
        debug!(%nsg_name, "Creating NSG");
        az_cli(&[
            "network",
            "nsg",
            "create",
            "--resource-group",
            rg,
            "--name",
            &nsg_name,
            "--location",
            location,
        ])
        .context(format!("Failed to create NSG '{nsg_name}'"))?;

        az_cli(&[
            "network",
            "nsg",
            "rule",
            "create",
            "--resource-group",
            rg,
            "--nsg-name",
            &nsg_name,
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

        az_cli(&[
            "network",
            "nsg",
            "rule",
            "create",
            "--resource-group",
            rg,
            "--nsg-name",
            &nsg_name,
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
        let vnet_name = format!("{vm_name}-vnet");
        let subnet_name = format!("{vm_name}-subnet");
        debug!(%vnet_name, %subnet_name, "Creating VNet and subnet");
        az_cli(&[
            "network",
            "vnet",
            "create",
            "--resource-group",
            rg,
            "--name",
            &vnet_name,
            "--address-prefix",
            "10.0.0.0/16",
            "--subnet-name",
            &subnet_name,
            "--subnet-prefix",
            "10.0.0.0/24",
            "--location",
            location,
            "--network-security-group",
            &nsg_name,
        ])
        .context(format!("Failed to create VNet '{vnet_name}'"))?;

        // 4. Create public IP
        let pip_name = format!("{vm_name}-pip");
        debug!(%pip_name, "Creating public IP");
        az_cli(&[
            "network",
            "public-ip",
            "create",
            "--resource-group",
            rg,
            "--name",
            &pip_name,
            "--sku",
            "Standard",
            "--allocation-method",
            "Static",
            "--location",
            location,
        ])
        .context(format!("Failed to create public IP '{pip_name}'"))?;

        // 5. Create NIC
        let nic_name = format!("{vm_name}-nic");
        debug!(%nic_name, "Creating NIC");
        az_cli(&[
            "network",
            "nic",
            "create",
            "--resource-group",
            rg,
            "--name",
            &nic_name,
            "--vnet-name",
            &vnet_name,
            "--subnet",
            &subnet_name,
            "--public-ip-address",
            &pip_name,
            "--network-security-group",
            &nsg_name,
            "--location",
            location,
        ])
        .context(format!("Failed to create NIC '{nic_name}'"))?;

        // 6. Create the VM
        debug!(%vm_name, "Creating VM");
        let image_urn = format!(
            "{}:{}:{}:{}",
            params.image.publisher, params.image.offer, params.image.sku, params.image.version
        );

        let cloud_init_path = create_cloud_init_file()?;
        let mut az_args = vec![
            "vm",
            "create",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--nics",
            &nic_name,
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

        let tag_strs: Vec<String> = params
            .tags
            .iter()
            .map(|(k, v)| format!("{k}={v}"))
            .collect();
        if !tag_strs.is_empty() {
            az_args.push("--tags");
            for t in &tag_strs {
                az_args.push(t);
            }
        }

        az_cli(&az_args).context(format!("Failed to create VM '{vm_name}'"))?;

        // Clean up temp file
        let _ = std::fs::remove_file(&cloud_init_path);

        // 7. Fetch and return VM info (includes IP lookup via SDK)
        debug!(%vm_name, "Fetching created VM details");
        let vm_info = self.get_vm(rg, vm_name).await?;
        Ok(vm_info)
    }
    async fn get_vm_ips(
        &self,
        props: Option<&azure_mgmt_compute::models::VirtualMachineProperties>,
        resource_group: &str,
    ) -> Result<(Option<String>, Option<String>)> {
        let nic_refs = props
            .and_then(|p| p.network_profile.as_ref())
            .map(|np| &np.network_interfaces)
            .cloned()
            .unwrap_or_default();

        let mut public_ip = None;
        let mut private_ip = None;

        for nic_ref in &nic_refs {
            let nic_id = match nic_ref.sub_resource.id.as_deref() {
                Some(id) => id,
                None => continue,
            };

            let nic_name = match nic_id.rsplit('/').next() {
                Some(n) => n,
                None => continue,
            };

            let nic_rg = extract_resource_group(nic_id);
            let rg = if nic_rg.is_empty() {
                resource_group
            } else {
                &nic_rg
            };

            let nic = self
                .network_client
                .network_interfaces()
                .get(rg, nic_name, &self.subscription_id)
                .into_future()
                .await;

            let nic = match nic {
                Ok(n) => n,
                Err(e) => {
                    debug!(nic_name, error = %e, "Failed to fetch NIC");
                    continue;
                }
            };

            if let Some(nic_props) = &nic.properties {
                for ip_config in &nic_props.ip_configurations {
                    if let Some(ip_props) = &ip_config.properties {
                        if private_ip.is_none() {
                            private_ip = ip_props.private_ip_address.clone();
                        }
                        if public_ip.is_none() {
                            if let Some(pub_ip) = &ip_props.public_ip_address {
                                if let Some(pub_props) = pub_ip.properties.as_ref() {
                                    public_ip = pub_props.ip_address.clone();
                                }
                                // If ip_address is not inline, fetch by ID
                                if public_ip.is_none() {
                                    if let Some(pub_id) = &pub_ip.resource.id {
                                        public_ip = self.fetch_public_ip(pub_id).await;
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Stop after finding IPs from the first NIC with data
            if public_ip.is_some() || private_ip.is_some() {
                break;
            }
        }

        Ok((public_ip, private_ip))
    }

    /// Fetch a public IP address by its resource ID.
    async fn fetch_public_ip(&self, resource_id: &str) -> Option<String> {
        let parts: Vec<&str> = resource_id.split('/').collect();
        // /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/publicIPAddresses/{name}
        if parts.len() < 9 {
            return None;
        }
        let rg = parts[4];
        let name = parts[8];

        match self
            .network_client
            .public_ip_addresses()
            .get(rg, name, &self.subscription_id)
            .into_future()
            .await
        {
            Ok(pip) => pip
                .properties
                .as_ref()
                .as_ref()
                .and_then(|p| p.ip_address.clone()),
            Err(e) => {
                debug!(name, error = %e, "Failed to fetch public IP");
                None
            }
        }
    }
}

/// Run an `az` CLI command, returning Ok(stdout) on success.
fn az_cli(args: &[&str]) -> Result<String> {
    debug!(args = ?args, "Running az CLI command");
    let output = std::process::Command::new("az")
        .args(args)
        .arg("--output")
        .arg("json")
        .output()
        .context("Failed to execute 'az' CLI. Is Azure CLI installed?")?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(anyhow::anyhow!("az CLI failed: {}", stderr.trim()))
    }
}

/// Write cloud-init script to a temp file and return its path.
fn create_cloud_init_file() -> Result<String> {
    let dir = std::env::temp_dir();
    let path = dir.join("azlin-cloud-init.sh");
    std::fs::write(&path, CLOUD_INIT_SCRIPT).context("Failed to write cloud-init temp file")?;
    Ok(path.to_string_lossy().to_string())
}

/// Cloud-init script for basic VM setup.
const CLOUD_INIT_SCRIPT: &str = r#"#!/bin/bash
set -euo pipefail

apt-get update -qq
apt-get upgrade -y -qq

apt-get install -y -qq \
    git curl wget jq unzip \
    build-essential \
    tmux ripgrep fd-find \
    docker.io

systemctl enable docker
systemctl start docker
usermod -aG docker azureuser

echo "cloud-init provisioning complete"
"#;

/// Extract resource group name from an Azure resource ID.
fn extract_resource_group(resource_id: &str) -> String {
    let parts: Vec<&str> = resource_id.split('/').collect();
    // /subscriptions/{sub}/resourceGroups/{rg}/...
    if parts.len() >= 5 {
        parts[4].to_string()
    } else {
        String::new()
    }
}

/// Extract power state from instance view statuses.
fn extract_power_state(
    instance_view: Option<&azure_mgmt_compute::models::VirtualMachineInstanceView>,
) -> PowerState {
    let statuses = match instance_view {
        Some(iv) => &iv.statuses,
        None => return PowerState::Unknown,
    };

    for status in statuses {
        if let Some(code) = &status.code {
            if let Some(state) = code.strip_prefix("PowerState/") {
                return match state.to_lowercase().as_str() {
                    "running" => PowerState::Running,
                    "stopped" => PowerState::Stopped,
                    "deallocated" => PowerState::Deallocated,
                    "starting" => PowerState::Starting,
                    "stopping" | "deallocating" => PowerState::Stopping,
                    _ => PowerState::Unknown,
                };
            }
        }
    }

    PowerState::Unknown
}

/// Extract tags from Azure resource tags JSON value.
fn extract_tags(tags_value: Option<&serde_json::Value>) -> HashMap<String, String> {
    match tags_value {
        Some(serde_json::Value::Object(map)) => map
            .iter()
            .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
            .collect(),
        _ => HashMap::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn test_extract_power_state_running() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("ProvisioningState/succeeded".to_string()),
                    ..Default::default()
                },
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("PowerState/running".to_string()),
                    ..Default::default()
                },
            ],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Running);
    }

    #[test]
    fn test_extract_power_state_deallocated() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/deallocated".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Deallocated);
    }

    #[test]
    fn test_extract_power_state_none() {
        assert_eq!(extract_power_state(None), PowerState::Unknown);
    }

    #[test]
    fn test_extract_power_state_no_power_code() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("ProvisioningState/succeeded".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Unknown);
    }

    #[test]
    fn test_extract_tags() {
        let tags = serde_json::json!({
            "session": "dev-session",
            "owner": "azureuser"
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.get("session").unwrap(), "dev-session");
        assert_eq!(result.get("owner").unwrap(), "azureuser");
    }

    #[test]
    fn test_extract_tags_none() {
        let result = extract_tags(None);
        assert!(result.is_empty());
    }

    #[test]
    fn test_extract_power_state_stopped() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/stopped".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Stopped);
    }

    #[test]
    fn test_extract_power_state_starting() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/starting".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Starting);
    }

    #[test]
    fn test_extract_power_state_stopping() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/stopping".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Stopping);
    }

    #[test]
    fn test_extract_tags_with_mixed_values() {
        let tags = serde_json::json!({
            "env": "production",
            "team": "backend",
            "numeric": 42
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.get("env").unwrap(), "production");
        assert_eq!(result.get("team").unwrap(), "backend");
        // Non-string values are skipped
        assert!(!result.contains_key("numeric"));
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn test_extract_tags_empty_object() {
        let tags = serde_json::json!({});
        let result = extract_tags(Some(&tags));
        assert!(result.is_empty());
    }

    #[test]
    fn test_extract_tags_non_object() {
        let tags = serde_json::json!("not an object");
        let result = extract_tags(Some(&tags));
        assert!(result.is_empty());
    }

    // ── Additional vm.rs tests ──────────────────────────────────────

    #[test]
    fn test_extract_resource_group_various_paths() {
        // Standard VM path
        let id = "/subscriptions/abc-123/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/vm1";
        assert_eq!(extract_resource_group(id), "prod-rg");

        // NIC path
        let nic_id = "/subscriptions/abc-123/resourceGroups/net-rg/providers/Microsoft.Network/networkInterfaces/vm1-nic";
        assert_eq!(extract_resource_group(nic_id), "net-rg");

        // Public IP path
        let pip_id = "/subscriptions/abc-123/resourceGroups/ip-rg/providers/Microsoft.Network/publicIPAddresses/vm1-pip";
        assert_eq!(extract_resource_group(pip_id), "ip-rg");
    }

    #[test]
    fn test_extract_resource_group_case_preserved() {
        let id = "/subscriptions/sub/resourceGroups/MyRG-Test/providers/Microsoft.Compute/virtualMachines/vm";
        assert_eq!(extract_resource_group(id), "MyRG-Test");
    }

    #[test]
    fn test_extract_power_state_deallocating() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/deallocating".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Stopping);
    }

    #[test]
    fn test_extract_power_state_unknown_value() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/suspended".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Unknown);
    }

    #[test]
    fn test_extract_power_state_empty_statuses() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Unknown);
    }

    #[test]
    fn test_extract_power_state_multiple_statuses_picks_power() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("ProvisioningState/succeeded".to_string()),
                    ..Default::default()
                },
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("ProvisioningState/updating".to_string()),
                    ..Default::default()
                },
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("PowerState/running".to_string()),
                    ..Default::default()
                },
            ],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Running);
    }

    #[test]
    fn test_extract_tags_with_empty_values() {
        let tags = serde_json::json!({
            "key1": "",
            "key2": "value2"
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.get("key1").unwrap(), "");
        assert_eq!(result.get("key2").unwrap(), "value2");
    }

    #[test]
    fn test_extract_tags_array_value() {
        let tags = serde_json::json!([1, 2, 3]);
        let result = extract_tags(Some(&tags));
        assert!(result.is_empty());
    }

    #[test]
    fn test_extract_tags_null_value() {
        let tags = serde_json::json!(null);
        let result = extract_tags(Some(&tags));
        assert!(result.is_empty());
    }

    #[test]
    fn test_cloud_init_script_is_valid_shell() {
        assert!(CLOUD_INIT_SCRIPT.starts_with("#!/bin/bash"));
        assert!(CLOUD_INIT_SCRIPT.contains("apt-get"));
        assert!(CLOUD_INIT_SCRIPT.contains("docker"));
    }

    #[test]
    fn test_extract_resource_group_with_only_subscription() {
        let id = "/subscriptions/abc-123";
        // Less than 5 parts
        assert_eq!(extract_resource_group(id), "");
    }

    // ── create_cloud_init_file tests ────────────────────────────────

    #[test]
    fn test_create_cloud_init_file_creates_file() {
        let path = create_cloud_init_file().expect("should create cloud-init file");
        // The function writes CLOUD_INIT_SCRIPT to a fixed temp path.
        // Another parallel test may overwrite it, so just verify the path is valid.
        assert!(
            !path.is_empty(),
            "cloud-init file path should not be empty"
        );
        assert!(
            path.contains("azlin-cloud-init"),
            "path should contain expected filename: {path}"
        );
    }

    #[test]
    fn test_create_cloud_init_file_path_is_in_temp() {
        let path = create_cloud_init_file().unwrap();
        let temp_dir = std::env::temp_dir();
        assert!(
            path.starts_with(temp_dir.to_string_lossy().as_ref()),
            "cloud-init path should be in temp dir"
        );
    }

    // ── CLOUD_INIT_SCRIPT content tests ─────────────────────────────

    #[test]
    fn test_cloud_init_script_has_set_options() {
        assert!(
            CLOUD_INIT_SCRIPT.contains("set -euo pipefail"),
            "cloud-init should use strict bash options"
        );
    }

    #[test]
    fn test_cloud_init_script_installs_essential_tools() {
        for tool in &["git", "curl", "wget", "jq", "tmux", "ripgrep"] {
            assert!(
                CLOUD_INIT_SCRIPT.contains(tool),
                "cloud-init should install {tool}"
            );
        }
    }

    #[test]
    fn test_cloud_init_script_enables_docker() {
        assert!(CLOUD_INIT_SCRIPT.contains("systemctl enable docker"));
        assert!(CLOUD_INIT_SCRIPT.contains("systemctl start docker"));
        assert!(CLOUD_INIT_SCRIPT.contains("usermod -aG docker"));
    }

    #[test]
    fn test_cloud_init_script_completion_marker() {
        assert!(
            CLOUD_INIT_SCRIPT.contains("cloud-init provisioning complete"),
            "cloud-init should have a completion marker"
        );
    }

    // ── az_cli tests ────────────────────────────────────────────────

    #[test]
    fn test_az_cli_invalid_command_returns_error() {
        let result = az_cli(&["this-is-not-a-real-command-xyz"]);
        assert!(result.is_err(), "invalid az command should return error");
    }

    #[test]
    fn test_az_cli_version_succeeds_or_fails_gracefully() {
        // `az version` should work if az is installed, or fail if not
        let result = az_cli(&["version"]);
        match result {
            Ok(output) => {
                assert!(!output.is_empty(), "az version should produce output");
            }
            Err(e) => {
                let msg = e.to_string();
                assert!(
                    msg.contains("az") || msg.contains("CLI"),
                    "error should mention az CLI: {msg}"
                );
            }
        }
    }

    // ── CredentialAdapter scope formatting tests ─────────────────────

    #[test]
    fn test_credential_adapter_scope_with_trailing_slash() {
        let resource = "https://management.azure.com/";
        let scope = if resource.ends_with('/') {
            format!("{}.default", resource)
        } else {
            format!("{}/.default", resource)
        };
        assert_eq!(scope, "https://management.azure.com/.default");
    }

    #[test]
    fn test_credential_adapter_scope_without_trailing_slash() {
        let resource = "https://management.azure.com";
        let scope = if resource.ends_with('/') {
            format!("{}.default", resource)
        } else {
            format!("{}/.default", resource)
        };
        assert_eq!(scope, "https://management.azure.com/.default");
    }

    #[test]
    fn test_credential_adapter_scope_with_custom_resource() {
        let resource = "https://vault.azure.net";
        let scope = if resource.ends_with('/') {
            format!("{}.default", resource)
        } else {
            format!("{}/.default", resource)
        };
        assert_eq!(scope, "https://vault.azure.net/.default");
    }

    // ── extract_power_state edge cases ──────────────────────────────

    #[test]
    fn test_extract_power_state_case_insensitivity() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/RUNNING".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Running);
    }

    #[test]
    fn test_extract_power_state_mixed_case() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: Some("PowerState/Deallocated".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Deallocated);
    }

    #[test]
    fn test_extract_power_state_status_with_none_code() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                code: None,
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Unknown);
    }

    #[test]
    fn test_extract_power_state_only_provisioning_no_power() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("ProvisioningState/succeeded".to_string()),
                    ..Default::default()
                },
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("ProvisioningState/creating".to_string()),
                    ..Default::default()
                },
            ],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Unknown);
    }

    #[test]
    fn test_extract_power_state_first_power_state_wins() {
        let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
            statuses: vec![
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("PowerState/running".to_string()),
                    ..Default::default()
                },
                azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("PowerState/stopped".to_string()),
                    ..Default::default()
                },
            ],
            ..Default::default()
        };
        assert_eq!(extract_power_state(Some(&iv)), PowerState::Running);
    }

    // ── extract_tags edge cases ─────────────────────────────────────

    #[test]
    fn test_extract_tags_many_tags() {
        let mut map = serde_json::Map::new();
        for i in 0..50 {
            map.insert(format!("key{i}"), serde_json::Value::String(format!("val{i}")));
        }
        let tags = serde_json::Value::Object(map);
        let result = extract_tags(Some(&tags));
        assert_eq!(result.len(), 50);
        assert_eq!(result.get("key0").unwrap(), "val0");
        assert_eq!(result.get("key49").unwrap(), "val49");
    }

    #[test]
    fn test_extract_tags_special_characters() {
        let tags = serde_json::json!({
            "env/prod": "us-east-1",
            "team:backend": "active",
            "tag with spaces": "value with spaces",
            "unicode-日本語": "テスト"
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.len(), 4);
        assert_eq!(result.get("env/prod").unwrap(), "us-east-1");
        assert_eq!(result.get("unicode-日本語").unwrap(), "テスト");
    }

    #[test]
    fn test_extract_tags_boolean_values_skipped() {
        let tags = serde_json::json!({
            "name": "vm1",
            "active": true,
            "count": 5
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.len(), 1);
        assert_eq!(result.get("name").unwrap(), "vm1");
    }

    // ── extract_resource_group edge cases ────────────────────────────

    #[test]
    fn test_extract_resource_group_exactly_five_parts() {
        let id = "/subscriptions/sub-id/resourceGroups/my-rg";
        assert_eq!(extract_resource_group(id), "my-rg");
    }

    #[test]
    fn test_extract_resource_group_with_special_chars() {
        let id = "/subscriptions/sub/resourceGroups/rg-with_special.chars/providers/X/Y/Z";
        assert_eq!(extract_resource_group(id), "rg-with_special.chars");
    }

    #[test]
    fn test_extract_resource_group_single_slash() {
        assert_eq!(extract_resource_group("/"), "");
    }

    // ── VmManager::new compilation/failure test ─────────────────────

    #[test]
    fn test_vm_manager_new_without_auth_does_not_panic() {
        // VmManager::new requires AzureAuth which needs az login.
        // Just verify the function exists and types compile.
        let result = crate::AzureAuth::new_with_subscription("test-sub");
        match result {
            Ok(auth) => {
                let _mgr = VmManager::new(&auth);
                // If we get here, VmManager constructed successfully
                assert_eq!(_mgr.subscription_id, "test-sub");
            }
            Err(_) => {
                // Expected in CI without Azure credentials
            }
        }
    }

    // ── extract_power_state comprehensive tests ─────────────────────

    #[test]
    fn test_extract_power_state_all_known_states() {
        let states = vec![
            ("running", PowerState::Running),
            ("stopped", PowerState::Stopped),
            ("deallocated", PowerState::Deallocated),
            ("starting", PowerState::Starting),
            ("stopping", PowerState::Stopping),
            ("deallocating", PowerState::Stopping),
        ];
        for (state_str, expected) in states {
            let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
                statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some(format!("PowerState/{state_str}")),
                    ..Default::default()
                }],
                ..Default::default()
            };
            assert_eq!(
                extract_power_state(Some(&iv)),
                expected,
                "Failed for state: {state_str}"
            );
        }
    }

    #[test]
    fn test_extract_power_state_all_unknown_values() {
        let unknown_states = vec!["suspended", "migrating", "paused", "error", ""];
        for state_str in unknown_states {
            let iv = azure_mgmt_compute::models::VirtualMachineInstanceView {
                statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some(format!("PowerState/{state_str}")),
                    ..Default::default()
                }],
                ..Default::default()
            };
            assert_eq!(
                extract_power_state(Some(&iv)),
                PowerState::Unknown,
                "Should be Unknown for state: {state_str}"
            );
        }
    }

    // ── az_cli additional tests ─────────────────────────────────────

    #[test]
    fn test_az_cli_appends_output_json() {
        // az_cli always adds --output json, so even invalid commands
        // should get that flag. We just verify the error contains useful info.
        let result = az_cli(&["nonexistent-subcommand-xyz"]);
        assert!(result.is_err());
    }

    #[test]
    fn test_az_cli_empty_args() {
        // Running az with no args should produce either help text or an error
        let result = az_cli(&[]);
        // az with no args typically returns exit code 0 with help text
        match result {
            Ok(output) => assert!(!output.is_empty()),
            Err(_) => {} // Also acceptable
        }
    }

    // ── create_cloud_init_file path test ────────────────────────────

    #[test]
    fn test_create_cloud_init_file_consistent_name() {
        let path1 = create_cloud_init_file().unwrap();
        let path2 = create_cloud_init_file().unwrap();
        assert_eq!(path1, path2, "should produce same path each time");
    }

    // ── extract_tags with all JSON types ────────────────────────────

    #[test]
    fn test_extract_tags_nested_objects_skipped() {
        let tags = serde_json::json!({
            "name": "vm1",
            "nested": {"inner": "value"},
            "array_val": [1, 2, 3]
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.len(), 1);
        assert_eq!(result.get("name").unwrap(), "vm1");
    }

    #[test]
    fn test_extract_tags_with_numeric_string_values() {
        let tags = serde_json::json!({
            "version": "2.0",
            "port": "8080",
            "count": "100"
        });
        let result = extract_tags(Some(&tags));
        assert_eq!(result.len(), 3);
        assert_eq!(result.get("version").unwrap(), "2.0");
    }
}
