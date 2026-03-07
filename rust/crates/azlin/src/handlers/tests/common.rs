use anyhow::Result;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;
use std::sync::Mutex;

/// Mock implementation of AzureOps for testing.
pub(super) struct MockAzureOps {
    subscription_id: String,
    pub(super) vms: Vec<VmInfo>,
    /// Track calls for verification.
    calls: Mutex<Vec<String>>,
}

impl MockAzureOps {
    pub(super) fn new(vms: Vec<VmInfo>) -> Self {
        Self {
            subscription_id: "test-sub-12345".to_string(),
            vms,
            calls: Mutex::new(Vec::new()),
        }
    }

    fn record(&self, call: &str) {
        self.calls.lock().unwrap().push(call.to_string());
    }

    pub(super) fn call_log(&self) -> Vec<String> {
        self.calls.lock().unwrap().clone()
    }
}

impl AzureOps for MockAzureOps {
    fn subscription_id(&self) -> &str {
        &self.subscription_id
    }

    fn list_vms(&self, _resource_group: &str) -> Result<Vec<VmInfo>> {
        self.record("list_vms");
        Ok(self.vms.clone())
    }

    fn list_vms_no_cache(&self, _resource_group: &str) -> Result<Vec<VmInfo>> {
        self.record("list_vms_no_cache");
        Ok(self.vms.clone())
    }

    fn list_all_vms(&self) -> Result<Vec<VmInfo>> {
        self.record("list_all_vms");
        Ok(self.vms.clone())
    }

    fn list_all_vms_no_cache(&self) -> Result<Vec<VmInfo>> {
        self.record("list_all_vms_no_cache");
        Ok(self.vms.clone())
    }

    fn get_vm(&self, _resource_group: &str, name: &str) -> Result<VmInfo> {
        self.record(&format!("get_vm:{}", name));
        self.vms
            .iter()
            .find(|v| v.name == name)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("VM '{}' not found", name))
    }

    fn start_vm(&self, _resource_group: &str, name: &str) -> Result<()> {
        self.record(&format!("start_vm:{}", name));
        Ok(())
    }

    fn stop_vm(&self, _resource_group: &str, name: &str, deallocate: bool) -> Result<()> {
        self.record(&format!("stop_vm:{}:dealloc={}", name, deallocate));
        Ok(())
    }

    fn delete_vm(&self, _resource_group: &str, name: &str) -> Result<()> {
        self.record(&format!("delete_vm:{}", name));
        Ok(())
    }

    fn add_tag(&self, _resource_group: &str, name: &str, key: &str, value: &str) -> Result<()> {
        self.record(&format!("add_tag:{}:{}={}", name, key, value));
        Ok(())
    }

    fn remove_tag(&self, _resource_group: &str, name: &str, key: &str) -> Result<()> {
        self.record(&format!("remove_tag:{}:{}", name, key));
        Ok(())
    }

    fn list_tags(&self, _resource_group: &str, name: &str) -> Result<HashMap<String, String>> {
        self.record(&format!("list_tags:{}", name));
        self.vms
            .iter()
            .find(|v| v.name == name)
            .map(|v| v.tags.clone())
            .ok_or_else(|| anyhow::anyhow!("VM '{}' not found", name))
    }

    fn create_vm(&self, params: &azlin_core::models::CreateVmParams) -> Result<VmInfo> {
        self.record(&format!("create_vm:{}", params.name));
        Ok(make_test_vm(&params.name, PowerState::Running))
    }
}

/// Create a test VmInfo with sensible defaults.
pub(super) fn make_test_vm(name: &str, power_state: PowerState) -> VmInfo {
    VmInfo {
        name: name.to_string(),
        resource_group: "test-rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state,
        provisioning_state: ProvisioningState::Succeeded,
        os_type: OsType::Linux,
        os_offer: Some("UbuntuServer".to_string()),
        public_ip: Some("20.1.2.3".to_string()),
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: Some("azureuser".to_string()),
        tags: HashMap::from([
            ("env".to_string(), "dev".to_string()),
            ("azlin-session".to_string(), "main".to_string()),
        ]),
        created_time: None,
    }
}

pub(super) fn make_test_vm_stopped(name: &str) -> VmInfo {
    let mut vm = make_test_vm(name, PowerState::Deallocated);
    vm.public_ip = None;
    vm
}

pub(super) fn make_test_vm_private(name: &str) -> VmInfo {
    let mut vm = make_test_vm(name, PowerState::Running);
    vm.public_ip = None;
    vm
}
