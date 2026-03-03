//! VM management operations — list, start, stop, create, delete.

use std::collections::HashMap;
use std::sync::Arc;

use anyhow::{Context, Result};
use tracing::{debug, warn};

use azlin_core::models::{OsType, PowerState, VmInfo};

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

        let compute_client =
            azure_mgmt_compute::ClientBuilder::new(adapter.clone() as Arc<dyn azure_core_old::auth::TokenCredential>)
                .build();
        let network_client =
            azure_mgmt_network::ClientBuilder::new(adapter as Arc<dyn azure_core_old::auth::TokenCredential>)
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
            .map(|s| serde_json::to_value(s).ok())
            .flatten()
            .and_then(|v| v.as_str().map(String::from))
            .unwrap_or_else(|| "unknown".to_string());

        // Extract power state from instance view statuses
        let power_state = extract_power_state(props.and_then(|p| p.instance_view.as_ref()));

        let provisioning_state = props
            .and_then(|p| p.provisioning_state.as_deref())
            .unwrap_or("Unknown")
            .to_string();

        // Detect OS type from OS profile
        let os_type = if props.and_then(|p| p.os_profile.as_ref()).and_then(|o| o.linux_configuration.as_ref()).is_some() {
            OsType::Linux
        } else if props.and_then(|p| p.os_profile.as_ref()).and_then(|o| o.windows_configuration.as_ref()).is_some() {
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

    /// Fetch public and private IPs for a VM by querying its network interfaces.
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
            let rg = if nic_rg.is_empty() { resource_group } else { &nic_rg };

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
}
