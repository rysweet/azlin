//! AzureOps trait — abstraction over VM management operations.
//!
//! This trait enables mock-based testing of command handlers that would
//! otherwise require a live Azure connection. `VmManager` implements this
//! trait; test code can provide `MockAzureOps` instead.

use std::collections::HashMap;

use anyhow::Result;
use azlin_core::models::{CreateVmParams, VmInfo};

/// Trait abstracting Azure VM operations for testability.
///
/// Every method mirrors a `VmManager` public method. Command handlers accept
/// `&dyn AzureOps` so tests can substitute a mock.
pub trait AzureOps {
    /// Return the subscription ID.
    fn subscription_id(&self) -> &str;

    /// List VMs in a resource group (cached).
    fn list_vms(&self, resource_group: &str) -> Result<Vec<VmInfo>>;

    /// List VMs in a resource group (no cache).
    fn list_vms_no_cache(&self, resource_group: &str) -> Result<Vec<VmInfo>>;

    /// List all VMs across the subscription (cached).
    fn list_all_vms(&self) -> Result<Vec<VmInfo>>;

    /// List all VMs across the subscription (no cache).
    fn list_all_vms_no_cache(&self) -> Result<Vec<VmInfo>>;

    /// Get details for a single VM.
    fn get_vm(&self, resource_group: &str, name: &str) -> Result<VmInfo>;

    /// Start a VM.
    fn start_vm(&self, resource_group: &str, name: &str) -> Result<()>;

    /// Stop (or deallocate) a VM.
    fn stop_vm(&self, resource_group: &str, name: &str, deallocate: bool) -> Result<()>;

    /// Delete a VM.
    fn delete_vm(&self, resource_group: &str, name: &str) -> Result<()>;

    /// Add a tag to a VM.
    fn add_tag(&self, resource_group: &str, name: &str, key: &str, value: &str) -> Result<()>;

    /// Remove a tag from a VM.
    fn remove_tag(&self, resource_group: &str, name: &str, key: &str) -> Result<()>;

    /// List tags on a VM.
    fn list_tags(&self, resource_group: &str, name: &str) -> Result<HashMap<String, String>>;

    /// Create a new VM.
    fn create_vm(&self, params: &CreateVmParams) -> Result<VmInfo>;
}

/// Blanket implementation for `VmManager`.
impl AzureOps for super::VmManager {
    fn subscription_id(&self) -> &str {
        self.subscription_id()
    }

    fn list_vms(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        self.list_vms(resource_group)
    }

    fn list_vms_no_cache(&self, resource_group: &str) -> Result<Vec<VmInfo>> {
        self.list_vms_no_cache(resource_group)
    }

    fn list_all_vms(&self) -> Result<Vec<VmInfo>> {
        self.list_all_vms()
    }

    fn list_all_vms_no_cache(&self) -> Result<Vec<VmInfo>> {
        self.list_all_vms_no_cache()
    }

    fn get_vm(&self, resource_group: &str, name: &str) -> Result<VmInfo> {
        self.get_vm(resource_group, name)
    }

    fn start_vm(&self, resource_group: &str, name: &str) -> Result<()> {
        self.start_vm(resource_group, name)
    }

    fn stop_vm(&self, resource_group: &str, name: &str, deallocate: bool) -> Result<()> {
        self.stop_vm(resource_group, name, deallocate)
    }

    fn delete_vm(&self, resource_group: &str, name: &str) -> Result<()> {
        self.delete_vm(resource_group, name)
    }

    fn add_tag(&self, resource_group: &str, name: &str, key: &str, value: &str) -> Result<()> {
        self.add_tag(resource_group, name, key, value)
    }

    fn remove_tag(&self, resource_group: &str, name: &str, key: &str) -> Result<()> {
        self.remove_tag(resource_group, name, key)
    }

    fn list_tags(&self, resource_group: &str, name: &str) -> Result<HashMap<String, String>> {
        self.list_tags(resource_group, name)
    }

    fn create_vm(&self, params: &CreateVmParams) -> Result<VmInfo> {
        self.create_vm(params)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verify that AzureOps is object-safe (can be used as `&dyn AzureOps`).
    #[test]
    fn trait_is_object_safe() {
        fn _assert_object_safe(_: &dyn AzureOps) {}
    }
}
