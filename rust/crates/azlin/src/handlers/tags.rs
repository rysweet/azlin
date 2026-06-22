//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use anyhow::Result;
use azlin_azure::AzureOps;
use std::collections::HashMap;

// ── Tag handlers ────────────────────────────────────────────────────────

/// Add tags to a VM. Returns a list of success messages.
pub fn handle_tag_add(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: &str,
    tags: &[(String, String)],
) -> Result<Vec<String>> {
    let mut messages = Vec::new();
    for (key, value) in tags {
        ops.add_tag(resource_group, vm_name, key, value)?;
        messages.push(format!("Added tag {}={} to VM '{}'", key, value, vm_name));
    }
    Ok(messages)
}

/// Remove tags from a VM. Returns a list of success messages.
pub fn handle_tag_remove(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: &str,
    tag_keys: &[String],
) -> Result<Vec<String>> {
    let mut messages = Vec::new();
    for key in tag_keys {
        ops.remove_tag(resource_group, vm_name, key)?;
        messages.push(format!("Removed tag '{}' from VM '{}'", key, vm_name));
    }
    Ok(messages)
}

/// List tags on a VM.
pub fn handle_tag_list(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: &str,
) -> Result<HashMap<String, String>> {
    ops.list_tags(resource_group, vm_name)
}

// ── Status handler ──────────────────────────────────────────────────────

/// A summary row for the status command.
pub struct StatusRow {
    pub name: String,
    pub power_state: String,
    pub public_ip: String,
    pub private_ip: String,
    pub vm_size: String,
    pub location: String,
}

/// Execute the status command: list VMs and return summary rows.
pub fn handle_status(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: Option<&str>,
) -> Result<Vec<StatusRow>> {
    let vms = if let Some(name) = vm_name {
        vec![ops.get_vm(resource_group, name)?]
    } else {
        ops.list_vms(resource_group)?
    };

    Ok(vms
        .into_iter()
        .map(|vm| StatusRow {
            name: vm.name,
            power_state: vm.power_state.to_string(),
            public_ip: vm.public_ip.unwrap_or_default(),
            private_ip: vm.private_ip.unwrap_or_default(),
            vm_size: vm.vm_size,
            location: vm.location,
        })
        .collect())
}
