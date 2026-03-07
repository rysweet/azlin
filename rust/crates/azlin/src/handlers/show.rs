//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use anyhow::Result;
use azlin_azure::AzureOps;
use azlin_core::models::VmInfo;

// ── Show handler ────────────────────────────────────────────────────────

/// Structured output from the `show` command.
pub struct ShowOutput {
    pub vm: VmInfo,
}

/// Format a VmInfo as a key-value table (plain text).
pub fn format_show_table(vm: &VmInfo) -> String {
    let mut out = String::new();
    out.push_str(&format!("Name:               {}\n", vm.name));
    out.push_str(&format!("Resource Group:     {}\n", vm.resource_group));
    out.push_str(&format!("Location:           {}\n", vm.location));
    out.push_str(&format!("VM Size:            {}\n", vm.vm_size));
    out.push_str(&format!("OS Type:            {:?}\n", vm.os_type));
    out.push_str(&format!("Power State:        {}\n", vm.power_state));
    out.push_str(&format!("Provisioning State: {}\n", vm.provisioning_state));
    if let Some(ip) = &vm.public_ip {
        out.push_str(&format!("Public IP:          {}\n", ip));
    }
    if let Some(ip) = &vm.private_ip {
        out.push_str(&format!("Private IP:         {}\n", ip));
    }
    if let Some(user) = &vm.admin_username {
        out.push_str(&format!("Admin User:         {}\n", user));
    }
    if !vm.tags.is_empty() {
        out.push_str("Tags:\n");
        for (k, v) in &vm.tags {
            out.push_str(&format!("  {}: {}\n", k, v));
        }
    }
    if let Some(t) = &vm.created_time {
        out.push_str(&format!(
            "Created:            {}\n",
            t.format("%Y-%m-%d %H:%M:%S UTC")
        ));
    }
    out
}

/// Format a VmInfo as JSON.
pub fn format_show_json(vm: &VmInfo) -> Result<String> {
    let json = serde_json::json!({
        "name": vm.name,
        "resource_group": vm.resource_group,
        "location": vm.location,
        "vm_size": vm.vm_size,
        "os_type": format!("{:?}", vm.os_type),
        "power_state": vm.power_state.to_string(),
        "provisioning_state": vm.provisioning_state,
        "public_ip": vm.public_ip,
        "private_ip": vm.private_ip,
        "admin_username": vm.admin_username,
        "tags": vm.tags,
        "created_time": vm.created_time.map(|t| t.format("%Y-%m-%d %H:%M:%S UTC").to_string()),
    });
    Ok(serde_json::to_string_pretty(&json)?)
}

/// Format a VmInfo as CSV.
pub fn format_show_csv(vm: &VmInfo) -> String {
    let mut out = String::from("Field,Value\n");
    out.push_str(&format!("name,{}\n", vm.name));
    out.push_str(&format!("resource_group,{}\n", vm.resource_group));
    out.push_str(&format!("location,{}\n", vm.location));
    out.push_str(&format!("vm_size,{}\n", vm.vm_size));
    out.push_str(&format!("os_type,{:?}\n", vm.os_type));
    out.push_str(&format!("power_state,{}\n", vm.power_state));
    out.push_str(&format!("provisioning_state,{}\n", vm.provisioning_state));
    out.push_str(&format!(
        "public_ip,{}\n",
        vm.public_ip.as_deref().unwrap_or("")
    ));
    out.push_str(&format!(
        "private_ip,{}\n",
        vm.private_ip.as_deref().unwrap_or("")
    ));
    out.push_str(&format!(
        "admin_username,{}\n",
        vm.admin_username.as_deref().unwrap_or("")
    ));
    out
}

/// Execute the show command: fetch a VM and return its info.
pub fn handle_show(ops: &dyn AzureOps, resource_group: &str, name: &str) -> Result<VmInfo> {
    ops.get_vm(resource_group, name)
}

// ── Start handler ───────────────────────────────────────────────────────

/// Execute the start command.
pub fn handle_start(ops: &dyn AzureOps, resource_group: &str, vm_name: &str) -> Result<String> {
    ops.start_vm(resource_group, vm_name)?;
    Ok(format!("Started {}", vm_name))
}

// ── Stop handler ────────────────────────────────────────────────────────

/// Execute the stop command.
pub fn handle_stop(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: &str,
    deallocate: bool,
) -> Result<String> {
    ops.stop_vm(resource_group, vm_name, deallocate)?;
    let action = if deallocate { "Deallocated" } else { "Stopped" };
    Ok(format!("{} {}", action, vm_name))
}

// ── Delete handler ──────────────────────────────────────────────────────

/// Execute the delete command (after confirmation has been obtained).
pub fn handle_delete(ops: &dyn AzureOps, resource_group: &str, vm_name: &str) -> Result<String> {
    ops.delete_vm(resource_group, vm_name)?;
    Ok(format!("Deleted {}", vm_name))
}
