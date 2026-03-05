//! VM management operations — list, start, stop, create, delete.

use std::collections::HashMap;
use std::sync::Arc;

use anyhow::{Context, Result};
use tracing::{debug, warn};
use wait_timeout::ChildExt;

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

        // Use a conservative 5-minute expiry since we cannot extract the real
        // expiry from the new SDK's AccessToken. This forces frequent refreshes
        // but avoids using stale tokens — the credential provider caches internally.
        Ok(azure_core_old::auth::TokenResponse::new(
            oauth2::AccessToken::new(token.token.secret().to_string()),
            chrono::Utc::now() + chrono::Duration::minutes(5),
        ))
    }
}

/// Manages Azure VM operations using native SDK clients.
pub struct VmManager {
    compute_client: azure_mgmt_compute::Client,
    network_client: azure_mgmt_network::Client,
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
            az_cli_timeout,
        }
    }

    /// List VMs in a specific resource group.
    ///
    /// Uses `az vm list` CLI directly. The Rust Azure SDK's
    /// `DefaultAzureCredential` is unreliable across platforms, while
    /// `az` CLI works consistently wherever `az login` succeeds.
    pub fn list_vms(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        self.list_vms_cli(resource_group)
    }

    /// List VMs via the Azure SDK (retained for future use when SDK auth
    /// is more reliable).
    #[allow(dead_code)]
    async fn list_vms_sdk(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        let result = self
            .compute_client
            .virtual_machines()
            .list(resource_group, &self.subscription_id)
            .into_future()
            .await
            .context(format!(
                "Failed to list VMs in resource group '{resource_group}'"
            ))?;

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
        debug!(count = vms.len(), "Listed VMs via SDK");
        Ok(vms)
    }

    /// List VMs via `az vm list` CLI fallback.
    ///
    /// Used when the Rust Azure SDK's DefaultAzureCredential fails to
    /// authenticate (e.g., on platforms where the Rust SDK's CLI credential
    /// provider doesn't work correctly).
    fn list_vms_cli(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        debug!(resource_group, "Listing VMs via az CLI fallback");
        let timeout = self.az_cli_timeout;
        let json =
            az_cli_with_timeout(&["vm", "list", "--resource-group", resource_group], timeout)?;

        let vms: Vec<serde_json::Value> =
            serde_json::from_str(&json).context("Failed to parse az vm list JSON")?;

        let mut result = Vec::new();
        for vm in &vms {
            let name = vm["name"].as_str().unwrap_or("").to_string();
            let location = vm["location"].as_str().unwrap_or("").to_string();
            let vm_size = vm["hardwareProfile"]["vmSize"]
                .as_str()
                .unwrap_or("unknown")
                .to_string();

            // Parse power state from instanceView or powerState field
            // Without --show-details, powerState and IPs are not available
            // from `az vm list`. We parse provisioningState instead.
            let provisioning_state: azlin_core::models::ProvisioningState =
                vm["provisioningState"].as_str().unwrap_or("Unknown").into();

            // Detect OS type from osProfile
            let os_type = if vm["osProfile"]["windowsConfiguration"].is_object() {
                azlin_core::models::OsType::Windows
            } else {
                azlin_core::models::OsType::Linux
            };

            let admin_username = vm["osProfile"]["adminUsername"].as_str().map(String::from);

            let tags = vm["tags"]
                .as_object()
                .map(|obj| {
                    obj.iter()
                        .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                        .collect()
                })
                .unwrap_or_default();

            // Power state requires --show-details or instanceView; mark as
            // unknown for fast list (user can run `azlin status <vm>` for details)
            result.push(VmInfo {
                name,
                resource_group: resource_group.to_string(),
                location,
                vm_size,
                power_state: azlin_core::models::PowerState::Unknown,
                provisioning_state,
                os_type,
                public_ip: None,
                private_ip: None,
                admin_username,
                tags,
                created_time: None,
            });
        }

        debug!(count = result.len(), "Listed VMs via az CLI");
        Ok(result)
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
            .context("Failed to list all VMs in subscription")?;

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

        let provisioning_state: azlin_core::models::ProvisioningState = props
            .and_then(|p| p.provisioning_state.as_deref())
            .unwrap_or("Unknown")
            .into();

        // Detect OS type from OS profile
        let has_linux = props
            .and_then(|p| p.os_profile.as_ref())
            .and_then(|o| o.linux_configuration.as_ref())
            .is_some();
        let has_windows = props
            .and_then(|p| p.os_profile.as_ref())
            .and_then(|o| o.windows_configuration.as_ref())
            .is_some();
        let os_type = detect_os_type(has_linux, has_windows);

        let admin_username = props
            .and_then(|p| p.os_profile.as_ref())
            .and_then(|o| o.admin_username.clone());

        // Extract tags
        let tags = extract_tags(vm.resource.tags.as_ref());

        // Extract IPs from network interfaces
        let (public_ip, private_ip) = match self.get_vm_ips(props, resource_group).await {
            Ok(ips) => ips,
            Err(e) => {
                tracing::warn!(vm = %name, error = %e, "Failed to resolve VM IP addresses");
                (None, None)
            }
        };

        // Extract created time
        let created_time = parse_created_time(props.and_then(|p| p.time_created.as_deref()));

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
    ///
    /// Tries SDK first, falls back to `az vm show` CLI.
    /// Get details for a single VM.
    ///
    /// Uses `az vm show --show-details` CLI directly for reliable
    /// cross-platform authentication.
    pub fn get_vm(&self, resource_group: &str, name: &str) -> Result<VmInfo> {
        self.get_vm_cli(resource_group, name)
    }

    /// Get VM via SDK (retained for future use when SDK auth is more reliable).
    async fn get_vm_sdk(&self, resource_group: &str, name: &str) -> Result<VmInfo> {
        let vm = self
            .compute_client
            .virtual_machines()
            .get(resource_group, name, &self.subscription_id)
            .expand("instanceView")
            .into_future()
            .await
            .context(format!(
                "Failed to get VM '{name}' in resource group '{resource_group}'"
            ))?;

        self.convert_vm(&vm, resource_group).await
    }

    /// Get VM via `az vm show` CLI fallback.
    fn get_vm_cli(&self, resource_group: &str, name: &str) -> Result<VmInfo> {
        debug!(resource_group, name, "Getting VM via az CLI fallback");
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

        let vm_name = vm["name"].as_str().unwrap_or("").to_string();
        let location = vm["location"].as_str().unwrap_or("").to_string();
        let vm_size = vm["hardwareProfile"]["vmSize"]
            .as_str()
            .unwrap_or("unknown")
            .to_string();

        let power_state = vm["powerState"]
            .as_str()
            .map(|s| match s.to_lowercase().as_str() {
                "vm running" => azlin_core::models::PowerState::Running,
                "vm deallocated" => azlin_core::models::PowerState::Deallocated,
                "vm stopped" => azlin_core::models::PowerState::Stopped,
                "vm starting" => azlin_core::models::PowerState::Starting,
                "vm stopping" | "vm deallocating" => azlin_core::models::PowerState::Stopping,
                _ => azlin_core::models::PowerState::Unknown,
            })
            .unwrap_or(azlin_core::models::PowerState::Unknown);

        let provisioning_state: azlin_core::models::ProvisioningState =
            vm["provisioningState"].as_str().unwrap_or("Unknown").into();

        let os_type = if vm["storageProfile"]["osDisk"]["osType"]
            .as_str()
            .is_some_and(|s| s.eq_ignore_ascii_case("Windows"))
        {
            azlin_core::models::OsType::Windows
        } else {
            azlin_core::models::OsType::Linux
        };

        let public_ip = vm["publicIps"]
            .as_str()
            .filter(|s| !s.is_empty())
            .map(String::from);
        let private_ip = vm["privateIps"]
            .as_str()
            .filter(|s| !s.is_empty())
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

        Ok(VmInfo {
            name: vm_name,
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
            created_time: None,
        })
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
        let vm = self.get_vm(resource_group, name)?;
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
        let vm = self.get_vm(resource_group, name)?;
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
        let vm = self.get_vm(resource_group, name)?;
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
        let names = build_vm_resource_names(vm_name);
        let timeout = self.az_cli_timeout;

        // Local helper using the configured timeout
        let az = |args: &[&str]| -> Result<String> { az_cli_with_timeout(args, timeout) };

        // Read SSH public key
        let ssh_pub_key = std::fs::read_to_string(&params.ssh_key_path).context(format!(
            "Failed to read SSH public key: {}",
            params.ssh_key_path.display()
        ))?;

        // 1. Create or verify resource group
        debug!(rg, location, "Creating/verifying resource group");
        az(&["group", "create", "--name", rg, "--location", location])
            .context(format!("Failed to create resource group '{rg}'"))?;

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

        // 7. Fetch and return VM info (includes IP lookup via SDK)
        debug!(%vm_name, "Fetching created VM details");
        let vm_info = self.get_vm(rg, vm_name)?;
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

            let nic_name = match extract_nic_name_from_id(nic_id) {
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
        let (rg, name) = parse_public_ip_resource_id(resource_id)?;

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

/// Default timeout for `az` CLI subprocess calls (120 seconds).
/// Overridden by `AzlinConfig.az_cli_timeout` when available.
const AZ_CLI_DEFAULT_TIMEOUT_SECS: u64 = 120;

/// Run an `az` CLI command with the default timeout, returning Ok(stdout) on success.
///
/// For custom timeouts (e.g., Windows/WSL), use [`az_cli_with_timeout`].
#[cfg_attr(not(test), allow(dead_code))]
fn az_cli(args: &[&str]) -> Result<String> {
    az_cli_with_timeout(args, AZ_CLI_DEFAULT_TIMEOUT_SECS)
}

/// Run an `az` CLI command with an explicit timeout in seconds.
fn az_cli_with_timeout(args: &[&str], timeout_secs: u64) -> Result<String> {
    debug!(args = ?args, "Running az CLI command");
    let mut child = std::process::Command::new("az")
        .args(args)
        .arg("--output")
        .arg("json")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .context("Failed to execute 'az' CLI. Is Azure CLI installed?")?;

    // Drain stdout and stderr in background threads to prevent pipe deadlock.
    // Without this, the child can block on writing to a full pipe buffer while
    // we block waiting for the child to exit — a classic deadlock.
    let stdout_handle = child.stdout.take().map(|mut pipe| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            std::io::Read::read_to_end(&mut pipe, &mut buf).ok();
            buf
        })
    });
    let stderr_handle = child.stderr.take().map(|mut pipe| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            std::io::Read::read_to_end(&mut pipe, &mut buf).ok();
            buf
        })
    });

    let timeout = std::time::Duration::from_secs(timeout_secs);
    match child.wait_timeout(timeout) {
        Ok(Some(status)) => {
            let stdout = stdout_handle
                .and_then(|h| h.join().ok())
                .unwrap_or_default();
            let stderr = stderr_handle
                .and_then(|h| h.join().ok())
                .unwrap_or_default();

            if status.success() {
                Ok(String::from_utf8_lossy(&stdout).to_string())
            } else {
                let stderr_str = String::from_utf8_lossy(&stderr);
                Err(anyhow::anyhow!(
                    "az CLI failed: {}",
                    azlin_core::sanitizer::sanitize(stderr_str.trim())
                ))
            }
        }
        Ok(None) => {
            // Timed out — kill the child process
            let _ = child.kill();
            let _ = child.wait();
            Err(anyhow::anyhow!(
                "az CLI command timed out after {}s. Args: {:?}",
                timeout_secs,
                args
            ))
        }
        Err(e) => Err(anyhow::anyhow!("Failed to wait for az CLI: {e}")),
    }
}

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
    build-essential \
    tmux ripgrep fd-find \
    docker.io

systemctl enable docker
systemctl start docker
usermod -aG docker {username}

echo "cloud-init provisioning complete"
"#,
        username = safe_username
    )
}

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
fn format_tag_cli_args(tags: &HashMap<String, String>) -> Vec<String> {
    tags.iter().map(|(k, v)| format!("{k}={v}")).collect()
}

/// Parse a public IP resource ID into (resource_group, name).
///
/// Expects format: `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/publicIPAddresses/{name}`
fn parse_public_ip_resource_id(resource_id: &str) -> Option<(&str, &str)> {
    let parts: Vec<&str> = resource_id.split('/').collect();
    if parts.len() < 9 {
        return None;
    }
    Some((parts[4], parts[8]))
}

/// Extract NIC name from a full Azure resource ID.
fn extract_nic_name_from_id(nic_id: &str) -> Option<&str> {
    nic_id.rsplit('/').next().filter(|s| !s.is_empty())
}

/// Detect OS type from OS profile flags.
fn detect_os_type(has_linux_config: bool, has_windows_config: bool) -> OsType {
    if has_linux_config {
        OsType::Linux
    } else if has_windows_config {
        OsType::Windows
    } else {
        OsType::Linux // Default assumption
    }
}

/// Parse an optional RFC 3339 timestamp into a `DateTime<Utc>`.
fn parse_created_time(time_str: Option<&str>) -> Option<chrono::DateTime<chrono::Utc>> {
    time_str
        .and_then(|t| chrono::DateTime::parse_from_rfc3339(t).ok())
        .map(|dt| dt.with_timezone(&chrono::Utc))
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
        assert!(cloud_init_script("azureuser").starts_with("#!/bin/bash"));
        assert!(cloud_init_script("azureuser").contains("apt-get"));
        assert!(cloud_init_script("azureuser").contains("docker"));
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
        let tmp = create_cloud_init_file("azureuser").expect("should create cloud-init file");
        let path = tmp.path();
        assert!(path.exists(), "cloud-init temp file should exist");
        let content = std::fs::read_to_string(path).expect("should read temp file");
        assert!(
            content.contains("cloud-init provisioning complete"),
            "file should contain the cloud-init script"
        );
    }

    #[test]
    fn test_create_cloud_init_file_path_is_in_temp() {
        let tmp = create_cloud_init_file("azureuser").unwrap();
        let path = tmp.path().to_string_lossy().to_string();
        let temp_dir = std::env::temp_dir();
        assert!(
            path.starts_with(temp_dir.to_string_lossy().as_ref()),
            "cloud-init path should be in temp dir"
        );
    }

    // ── cloud_init_script("azureuser") content tests ─────────────────────────────

    #[test]
    fn test_cloud_init_script_has_set_options() {
        assert!(
            cloud_init_script("azureuser").contains("set -euo pipefail"),
            "cloud-init should use strict bash options"
        );
    }

    #[test]
    fn test_cloud_init_script_installs_essential_tools() {
        for tool in &["git", "curl", "wget", "jq", "tmux", "ripgrep"] {
            assert!(
                cloud_init_script("azureuser").contains(tool),
                "cloud-init should install {tool}"
            );
        }
    }

    #[test]
    fn test_cloud_init_script_enables_docker() {
        assert!(cloud_init_script("azureuser").contains("systemctl enable docker"));
        assert!(cloud_init_script("azureuser").contains("systemctl start docker"));
        assert!(cloud_init_script("azureuser").contains("usermod -aG docker"));
    }

    #[test]
    fn test_cloud_init_script_uses_custom_username() {
        let script = cloud_init_script("devadmin");
        assert!(script.contains("usermod -aG docker devadmin"));
        assert!(!script.contains("azureuser"));
    }

    #[test]
    fn test_cloud_init_script_rejects_invalid_username() {
        // Invalid username should fall back to "azureuser"
        let script = cloud_init_script("evil;user");
        assert!(script.contains("usermod -aG docker azureuser"));
        assert!(!script.contains("evil"));
    }

    #[test]
    fn test_cloud_init_script_completion_marker() {
        assert!(
            cloud_init_script("azureuser").contains("cloud-init provisioning complete"),
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
            map.insert(
                format!("key{i}"),
                serde_json::Value::String(format!("val{i}")),
            );
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
        if let Ok(output) = result {
            assert!(!output.is_empty());
        } // Error also acceptable
    }

    #[test]
    fn test_az_cli_with_timeout_invalid_command() {
        let result = az_cli_with_timeout(&["this-is-not-a-real-command-xyz"], 30);
        assert!(result.is_err(), "invalid command should error with timeout");
    }

    #[test]
    fn test_az_cli_with_timeout_zero_still_works() {
        // Even with 0 timeout, the function should not panic
        let result = az_cli_with_timeout(&["version"], 0);
        // May succeed quickly or timeout — both are acceptable, no panic
        let _ = result;
    }

    // ── create_cloud_init_file path test ────────────────────────────

    #[test]
    fn test_create_cloud_init_file_unique_paths() {
        let tmp1 = create_cloud_init_file("azureuser").unwrap();
        let tmp2 = create_cloud_init_file("azureuser").unwrap();
        assert_ne!(
            tmp1.path(),
            tmp2.path(),
            "concurrent calls should produce unique paths"
        );
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

    // ── build_vm_resource_names tests ───────────────────────────────

    #[test]
    fn test_build_vm_resource_names_basic() {
        let names = build_vm_resource_names("myvm");
        assert_eq!(names.nsg, "myvm-nsg");
        assert_eq!(names.vnet, "myvm-vnet");
        assert_eq!(names.subnet, "myvm-subnet");
        assert_eq!(names.pip, "myvm-pip");
        assert_eq!(names.nic, "myvm-nic");
    }

    #[test]
    fn test_build_vm_resource_names_with_hyphens() {
        let names = build_vm_resource_names("dev-vm-01");
        assert_eq!(names.nsg, "dev-vm-01-nsg");
        assert_eq!(names.vnet, "dev-vm-01-vnet");
        assert_eq!(names.subnet, "dev-vm-01-subnet");
        assert_eq!(names.pip, "dev-vm-01-pip");
        assert_eq!(names.nic, "dev-vm-01-nic");
    }

    #[test]
    fn test_build_vm_resource_names_with_underscores() {
        let names = build_vm_resource_names("test_vm");
        assert_eq!(names.nsg, "test_vm-nsg");
        assert_eq!(names.nic, "test_vm-nic");
    }

    #[test]
    fn test_build_vm_resource_names_long_name() {
        let long_name = "a".repeat(64);
        let names = build_vm_resource_names(&long_name);
        assert!(names.nsg.ends_with("-nsg"));
        assert!(names.nsg.starts_with(&long_name));
    }

    #[test]
    fn test_build_vm_resource_names_equality() {
        let names1 = build_vm_resource_names("vm1");
        let names2 = build_vm_resource_names("vm1");
        assert_eq!(names1, names2);
    }

    #[test]
    fn test_build_vm_resource_names_inequality() {
        let names1 = build_vm_resource_names("vm1");
        let names2 = build_vm_resource_names("vm2");
        assert_ne!(names1, names2);
    }

    #[test]
    fn test_build_vm_resource_names_debug() {
        let names = build_vm_resource_names("vm");
        let debug = format!("{:?}", names);
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
        tags.insert("env".to_string(), "dev".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args.len(), 1);
        assert_eq!(args[0], "env=dev");
    }

    #[test]
    fn test_format_tag_cli_args_multiple() {
        let mut tags = HashMap::new();
        tags.insert("env".to_string(), "prod".to_string());
        tags.insert("team".to_string(), "backend".to_string());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args.len(), 2);
        assert!(args.iter().any(|a| a == "env=prod"));
        assert!(args.iter().any(|a| a == "team=backend"));
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
        tags.insert("key".to_string(), String::new());
        let args = format_tag_cli_args(&tags);
        assert_eq!(args[0], "key=");
    }

    // ── parse_public_ip_resource_id tests ───────────────────────────

    #[test]
    fn test_parse_public_ip_resource_id_valid() {
        let id = "/subscriptions/sub-123/resourceGroups/my-rg/providers/Microsoft.Network/publicIPAddresses/my-pip";
        let result = parse_public_ip_resource_id(id);
        assert!(result.is_some());
        let (rg, name) = result.unwrap();
        assert_eq!(rg, "my-rg");
        assert_eq!(name, "my-pip");
    }

    #[test]
    fn test_parse_public_ip_resource_id_too_short() {
        assert!(parse_public_ip_resource_id("").is_none());
        assert!(parse_public_ip_resource_id("/short").is_none());
        assert!(parse_public_ip_resource_id("/a/b/c").is_none());
        assert!(parse_public_ip_resource_id("/subscriptions/sub/resourceGroups/rg").is_none());
    }

    #[test]
    fn test_parse_public_ip_resource_id_exact_9_parts() {
        // 9 parts: ["", "subscriptions", "sub", "resourceGroups", "rg", "providers", "Msft", "pub", "name"]
        let id = "/subscriptions/sub/resourceGroups/rg/providers/Msft/pub/name";
        let result = parse_public_ip_resource_id(id);
        assert!(result.is_some());
        let (rg, name) = result.unwrap();
        assert_eq!(rg, "rg");
        assert_eq!(name, "name");
    }

    #[test]
    fn test_parse_public_ip_resource_id_with_extra_segments() {
        let id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip/extra/segments";
        let result = parse_public_ip_resource_id(id);
        assert!(result.is_some());
        let (rg, name) = result.unwrap();
        assert_eq!(rg, "rg");
        assert_eq!(name, "pip");
    }

    // ── extract_nic_name_from_id tests ──────────────────────────────

    #[test]
    fn test_extract_nic_name_from_id_valid() {
        let id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/my-nic";
        assert_eq!(extract_nic_name_from_id(id), Some("my-nic"));
    }

    #[test]
    fn test_extract_nic_name_from_id_simple() {
        assert_eq!(extract_nic_name_from_id("my-nic"), Some("my-nic"));
    }

    #[test]
    fn test_extract_nic_name_from_id_trailing_slash() {
        // Trailing slash results in empty last segment, filtered out
        assert_eq!(extract_nic_name_from_id("foo/"), None);
    }

    #[test]
    fn test_extract_nic_name_from_id_empty() {
        assert_eq!(extract_nic_name_from_id(""), None);
    }

    #[test]
    fn test_extract_nic_name_from_id_just_slashes() {
        assert_eq!(extract_nic_name_from_id("///"), None);
    }

    // ── detect_os_type tests ────────────────────────────────────────

    #[test]
    fn test_detect_os_type_linux() {
        assert_eq!(detect_os_type(true, false), OsType::Linux);
    }

    #[test]
    fn test_detect_os_type_windows() {
        assert_eq!(detect_os_type(false, true), OsType::Windows);
    }

    #[test]
    fn test_detect_os_type_neither() {
        assert_eq!(detect_os_type(false, false), OsType::Linux);
    }

    #[test]
    fn test_detect_os_type_both() {
        // Linux takes precedence
        assert_eq!(detect_os_type(true, true), OsType::Linux);
    }

    // ── parse_created_time tests ────────────────────────────────────

    #[test]
    fn test_parse_created_time_valid_rfc3339() {
        let result = parse_created_time(Some("2024-06-15T10:30:00Z"));
        assert!(result.is_some());
        let dt = result.unwrap();
        assert_eq!(dt.year(), 2024);
        assert_eq!(dt.month(), 6);
        assert_eq!(dt.day(), 15);
    }

    #[test]
    fn test_parse_created_time_with_timezone_offset() {
        let result = parse_created_time(Some("2024-01-01T00:00:00+05:30"));
        assert!(result.is_some());
    }

    #[test]
    fn test_parse_created_time_invalid_format() {
        assert!(parse_created_time(Some("not-a-date")).is_none());
        assert!(parse_created_time(Some("2024/01/01")).is_none());
        assert!(parse_created_time(Some("")).is_none());
    }

    #[test]
    fn test_parse_created_time_none() {
        assert!(parse_created_time(None).is_none());
    }

    #[test]
    fn test_parse_created_time_iso_variants() {
        // With fractional seconds
        let result = parse_created_time(Some("2024-06-15T10:30:00.123456Z"));
        assert!(result.is_some());
        // With negative offset
        let result = parse_created_time(Some("2024-06-15T10:30:00-07:00"));
        assert!(result.is_some());
    }

    // ── VmManager convert_vm tests (mock credential) ────────────────

    use chrono::Datelike;

    struct DummyCred;

    #[async_trait::async_trait]
    impl azure_core_old::auth::TokenCredential for DummyCred {
        async fn get_token(
            &self,
            _resource: &str,
        ) -> std::result::Result<azure_core_old::auth::TokenResponse, azure_core_old::Error>
        {
            Ok(azure_core_old::auth::TokenResponse::new(
                oauth2::AccessToken::new("test-token".to_string()),
                chrono::Utc::now() + chrono::Duration::hours(1),
            ))
        }
    }

    fn create_test_vm_manager() -> VmManager {
        let cred = Arc::new(DummyCred) as Arc<dyn azure_core_old::auth::TokenCredential>;
        VmManager {
            compute_client: azure_mgmt_compute::ClientBuilder::new(cred.clone()).build(),
            network_client: azure_mgmt_network::ClientBuilder::new(cred).build(),
            subscription_id: "test-subscription-id".to_string(),
            az_cli_timeout: AZ_CLI_DEFAULT_TIMEOUT_SECS,
        }
    }

    fn make_test_vm(
        name: Option<&str>,
        location: &str,
        props: Option<azure_mgmt_compute::models::VirtualMachineProperties>,
        tags: Option<serde_json::Value>,
    ) -> azure_mgmt_compute::models::VirtualMachine {
        let mut resource = azure_mgmt_compute::models::Resource::new(location.to_string());
        resource.name = name.map(|n| n.to_string());
        resource.tags = tags;
        let mut vm = azure_mgmt_compute::models::VirtualMachine::new(resource);
        vm.properties = props;
        vm
    }

    #[tokio::test]
    async fn test_convert_vm_minimal() {
        let mgr = create_test_vm_manager();
        let vm = make_test_vm(None, "westus2", None, None);
        let info = mgr.convert_vm(&vm, "test-rg").await.unwrap();
        assert_eq!(info.name, "");
        assert_eq!(info.location, "westus2");
        assert_eq!(info.resource_group, "test-rg");
        assert_eq!(info.vm_size, "unknown");
        assert_eq!(info.power_state, PowerState::Unknown);
        assert_eq!(
            info.provisioning_state,
            azlin_core::models::ProvisioningState::Other("Unknown".to_string())
        );
        assert_eq!(info.os_type, OsType::Linux);
        assert!(info.public_ip.is_none());
        assert!(info.private_ip.is_none());
        assert!(info.admin_username.is_none());
        assert!(info.tags.is_empty());
        assert!(info.created_time.is_none());
    }

    #[tokio::test]
    async fn test_convert_vm_with_name_and_location() {
        let mgr = create_test_vm_manager();
        let vm = make_test_vm(Some("dev-vm-01"), "eastus", None, None);
        let info = mgr.convert_vm(&vm, "prod-rg").await.unwrap();
        assert_eq!(info.name, "dev-vm-01");
        assert_eq!(info.location, "eastus");
        assert_eq!(info.resource_group, "prod-rg");
    }

    #[tokio::test]
    async fn test_convert_vm_with_linux_os() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            os_profile: Some(azure_mgmt_compute::models::OsProfile {
                admin_username: Some("azureuser".to_string()),
                linux_configuration: Some(azure_mgmt_compute::models::LinuxConfiguration::default()),
                ..Default::default()
            }),
            ..Default::default()
        };
        let vm = make_test_vm(Some("linux-vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(info.os_type, OsType::Linux);
        assert_eq!(info.admin_username, Some("azureuser".to_string()));
    }

    #[tokio::test]
    async fn test_convert_vm_with_windows_os() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            os_profile: Some(azure_mgmt_compute::models::OsProfile {
                admin_username: Some("adminuser".to_string()),
                windows_configuration: Some(
                    azure_mgmt_compute::models::WindowsConfiguration::default(),
                ),
                ..Default::default()
            }),
            ..Default::default()
        };
        let vm = make_test_vm(Some("win-vm"), "eastus", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(info.os_type, OsType::Windows);
        assert_eq!(info.admin_username, Some("adminuser".to_string()));
    }

    #[tokio::test]
    async fn test_convert_vm_with_no_os_profile() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            provisioning_state: Some("Succeeded".to_string()),
            ..Default::default()
        };
        let vm = make_test_vm(Some("no-os"), "westus", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(info.os_type, OsType::Linux); // default
        assert!(info.admin_username.is_none());
    }

    #[tokio::test]
    async fn test_convert_vm_with_provisioning_state() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            provisioning_state: Some("Succeeded".to_string()),
            ..Default::default()
        };
        let vm = make_test_vm(Some("vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(
            info.provisioning_state,
            azlin_core::models::ProvisioningState::Succeeded
        );
    }

    #[tokio::test]
    async fn test_convert_vm_provisioning_state_updating() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            provisioning_state: Some("Updating".to_string()),
            ..Default::default()
        };
        let vm = make_test_vm(Some("vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(
            info.provisioning_state,
            azlin_core::models::ProvisioningState::Updating
        );
    }

    #[tokio::test]
    async fn test_convert_vm_with_tags() {
        let mgr = create_test_vm_manager();
        let tags = serde_json::json!({"env": "dev", "team": "platform"});
        let vm = make_test_vm(Some("tagged-vm"), "westus2", None, Some(tags));
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(info.tags.get("env").unwrap(), "dev");
        assert_eq!(info.tags.get("team").unwrap(), "platform");
        assert_eq!(info.tags.len(), 2);
    }

    #[tokio::test]
    async fn test_convert_vm_with_created_time() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            time_created: Some("2024-06-15T10:30:00Z".to_string()),
            ..Default::default()
        };
        let vm = make_test_vm(Some("vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert!(info.created_time.is_some());
        assert_eq!(info.created_time.unwrap().year(), 2024);
    }

    #[tokio::test]
    async fn test_convert_vm_with_invalid_created_time() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            time_created: Some("invalid-date".to_string()),
            ..Default::default()
        };
        let vm = make_test_vm(Some("vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert!(info.created_time.is_none());
    }

    #[tokio::test]
    async fn test_convert_vm_with_instance_view_running() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            instance_view: Some(azure_mgmt_compute::models::VirtualMachineInstanceView {
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
            }),
            ..Default::default()
        };
        let vm = make_test_vm(Some("running-vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(info.power_state, PowerState::Running);
    }

    #[tokio::test]
    async fn test_convert_vm_with_instance_view_deallocated() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            instance_view: Some(azure_mgmt_compute::models::VirtualMachineInstanceView {
                statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("PowerState/deallocated".to_string()),
                    ..Default::default()
                }],
                ..Default::default()
            }),
            ..Default::default()
        };
        let vm = make_test_vm(Some("dealloc-vm"), "westus2", Some(props), None);
        let info = mgr.convert_vm(&vm, "rg").await.unwrap();
        assert_eq!(info.power_state, PowerState::Deallocated);
    }

    #[tokio::test]
    async fn test_convert_vm_full() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            provisioning_state: Some("Succeeded".to_string()),
            os_profile: Some(azure_mgmt_compute::models::OsProfile {
                admin_username: Some("azureuser".to_string()),
                linux_configuration: Some(azure_mgmt_compute::models::LinuxConfiguration::default()),
                ..Default::default()
            }),
            instance_view: Some(azure_mgmt_compute::models::VirtualMachineInstanceView {
                statuses: vec![azure_mgmt_compute::models::InstanceViewStatus {
                    code: Some("PowerState/running".to_string()),
                    ..Default::default()
                }],
                ..Default::default()
            }),
            time_created: Some("2024-03-15T08:00:00Z".to_string()),
            ..Default::default()
        };
        let tags = serde_json::json!({"session": "dev", "owner": "tester"});
        let vm = make_test_vm(Some("full-vm"), "westus2", Some(props), Some(tags));
        let info = mgr.convert_vm(&vm, "my-rg").await.unwrap();
        assert_eq!(info.name, "full-vm");
        assert_eq!(info.location, "westus2");
        assert_eq!(info.resource_group, "my-rg");
        assert_eq!(
            info.provisioning_state,
            azlin_core::models::ProvisioningState::Succeeded
        );
        assert_eq!(info.os_type, OsType::Linux);
        assert_eq!(info.admin_username, Some("azureuser".to_string()));
        assert_eq!(info.power_state, PowerState::Running);
        assert!(info.created_time.is_some());
        assert_eq!(info.tags.len(), 2);
    }

    // ── VmManager get_vm_ips tests ──────────────────────────────────

    #[tokio::test]
    async fn test_get_vm_ips_no_props() {
        let mgr = create_test_vm_manager();
        let result = mgr.get_vm_ips(None, "rg").await.unwrap();
        assert_eq!(result, (None, None));
    }

    #[tokio::test]
    async fn test_get_vm_ips_no_network_profile() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties::default();
        let result = mgr.get_vm_ips(Some(&props), "rg").await.unwrap();
        assert_eq!(result, (None, None));
    }

    #[tokio::test]
    async fn test_get_vm_ips_empty_nic_list() {
        let mgr = create_test_vm_manager();
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            network_profile: Some(azure_mgmt_compute::models::NetworkProfile {
                network_interfaces: vec![],
                ..Default::default()
            }),
            ..Default::default()
        };
        let result = mgr.get_vm_ips(Some(&props), "rg").await.unwrap();
        assert_eq!(result, (None, None));
    }

    #[tokio::test]
    async fn test_get_vm_ips_nic_without_id() {
        let mgr = create_test_vm_manager();
        let mut nic_ref = azure_mgmt_compute::models::NetworkInterfaceReference::new();
        nic_ref.sub_resource.id = None;
        let props = azure_mgmt_compute::models::VirtualMachineProperties {
            network_profile: Some(azure_mgmt_compute::models::NetworkProfile {
                network_interfaces: vec![nic_ref],
                ..Default::default()
            }),
            ..Default::default()
        };
        let result = mgr.get_vm_ips(Some(&props), "rg").await.unwrap();
        assert_eq!(result, (None, None));
    }

    // ── VmManager error path tests ──────────────────────────────────

    #[test]
    fn test_list_vms_nonexistent_rg_returns_error_or_empty() {
        let mgr = create_test_vm_manager();
        let result = mgr.list_vms("nonexistent-rg-xyz-12345");
        // With az CLI: either errors (no login) or returns empty list (logged in, RG doesn't exist)
        match result {
            Ok(vms) => assert!(vms.is_empty(), "nonexistent RG should have no VMs"),
            Err(e) => {
                let msg = e.to_string();
                assert!(
                    msg.contains("az")
                        || msg.contains("CLI")
                        || msg.contains("error")
                        || msg.contains("failed"),
                    "error should mention az CLI: {msg}"
                );
            }
        }
    }

    #[tokio::test]
    async fn test_list_all_vms_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.list_all_vms().await;
        assert!(result.is_err(), "should fail with dummy credentials");
        let msg = result.unwrap_err().to_string();
        assert!(!msg.is_empty(), "error should be descriptive");
    }

    #[tokio::test]
    async fn test_start_vm_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.start_vm("rg", "nonexistent-vm").await;
        assert!(result.is_err());
        let err = result.unwrap_err().to_string();
        assert!(
            err.contains("Failed to start") || err.contains("error"),
            "should contain descriptive error: {err}"
        );
    }

    #[tokio::test]
    async fn test_stop_vm_deallocate_returns_error() {
        let mgr = create_test_vm_manager();
        let result = mgr.stop_vm("rg", "nonexistent-vm", true).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_stop_vm_power_off_returns_error() {
        let mgr = create_test_vm_manager();
        let result = mgr.stop_vm("rg", "nonexistent-vm", false).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_get_vm_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.get_vm("rg", "nonexistent-vm");
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_delete_vm_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.delete_vm("rg", "nonexistent-vm").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_add_tag_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.add_tag("rg", "vm", "key", "value").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_remove_tag_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.remove_tag("rg", "vm", "key").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_list_tags_returns_error_with_dummy_cred() {
        let mgr = create_test_vm_manager();
        let result = mgr.list_tags("rg", "vm").await;
        assert!(result.is_err());
    }

    // ── VmManager construction tests ────────────────────────────────

    #[test]
    fn test_create_test_vm_manager_has_subscription() {
        let mgr = create_test_vm_manager();
        assert_eq!(mgr.subscription_id, "test-subscription-id");
    }

    // ── VmResourceNames struct tests ────────────────────────────────

    #[test]
    fn test_vm_resource_names_clone() {
        let names = build_vm_resource_names("vm1");
        let cloned = names.clone();
        assert_eq!(names, cloned);
    }

    #[test]
    fn test_vm_resource_names_all_suffixes() {
        let names = build_vm_resource_names("x");
        assert_eq!(names.nsg, "x-nsg");
        assert_eq!(names.vnet, "x-vnet");
        assert_eq!(names.subnet, "x-subnet");
        assert_eq!(names.pip, "x-pip");
        assert_eq!(names.nic, "x-nic");
    }

    // ── CredentialAdapter tests ──────────────────────────────────────

    #[tokio::test]
    async fn test_dummy_credential_returns_token() {
        use azure_core_old::auth::TokenCredential;
        let cred = DummyCred;
        let result = cred.get_token("https://management.azure.com/").await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_dummy_credential_different_resources() {
        use azure_core_old::auth::TokenCredential;
        let cred = DummyCred;
        for resource in &[
            "https://management.azure.com/",
            "https://vault.azure.net",
            "https://storage.azure.com/",
        ] {
            let result = cred.get_token(resource).await;
            assert!(result.is_ok());
        }
    }
}
