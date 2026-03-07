use anyhow::{Context, Result};

use super::*;

pub(crate) fn create_auth() -> Result<azlin_azure::AzureAuth> {
    azlin_azure::AzureAuth::new().map_err(|e| {
        anyhow::anyhow!(
            "Azure authentication failed: {e}\n\
             Run 'az login' to authenticate with Azure CLI."
        )
    })
}

pub(crate) fn resolve_resource_group(explicit: Option<String>) -> Result<String> {
    if let Some(rg) = explicit {
        return Ok(rg);
    }
    let config = azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
    config.default_resource_group.ok_or_else(|| {
        anyhow::anyhow!(
            "No resource group configured.\n\n\
             Quick setup:\n\
             1. azlin context create <name> --subscription-id <sub> --tenant-id <tenant>\n\
             2. azlin context use <name>\n\
             3. azlin config set default_resource_group <rg-name>\n\n\
             Or pass --resource-group <name> to any command.\n\
             Run 'az account show' to find your subscription and tenant IDs."
        )
    })
}

/// Get the user's home directory, returning a clear error on failure.
pub(crate) fn home_dir() -> Result<std::path::PathBuf> {
    dirs::home_dir().ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))
}

/// Escape a value for safe inclusion in a shell command.
pub(crate) fn shell_escape(s: &str) -> String {
    let mut escaped = String::with_capacity(s.len() + 2);
    escaped.push('\'');
    for c in s.chars() {
        if c == '\'' {
            escaped.push_str("'\\''");
        } else {
            escaped.push(c);
        }
    }
    escaped.push('\'');
    escaped
}

/// Resolve a single VM to a `VmSshTarget`, using --ip flag if provided.
/// Routes through bastion automatically for private-IP-only VMs.
pub(crate) async fn resolve_vm_ssh_target(
    vm_name: &str,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<VmSshTarget> {
    if let Some(ip) = ip_flag {
        return Ok(VmSshTarget {
            vm_name: vm_name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
            bastion: None,
        });
    }
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let vm = vm_manager.get_vm(&rg, vm_name)?;
    let bastion_map: std::collections::HashMap<String, String> =
        list_helpers::detect_bastion_hosts(&rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();
    let ssh_key = resolve_ssh_key();
    let target = build_ssh_target(&vm, vm_manager.subscription_id(), &bastion_map, &ssh_key);
    if target.ip.is_empty() {
        anyhow::bail!("No IP address found for VM '{}'", vm_name);
    }
    Ok(target)
}

/// Resolve targets for W/Ps/Top: single VM (--vm/--ip) or all VMs via Azure.
/// Returns `Vec<VmSshTarget>` with bastion routing for private-IP-only VMs.
pub(crate) async fn resolve_vm_targets(
    vm_flag: Option<&str>,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<Vec<VmSshTarget>> {
    if let Some(ip) = ip_flag {
        let name = vm_flag.unwrap_or(ip);
        return Ok(vec![VmSshTarget {
            vm_name: name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
            bastion: None,
        }]);
    }
    if let Some(vm_name) = vm_flag {
        let auth = create_auth()?;
        let vm_manager = azlin_azure::VmManager::new(&auth);
        let rg = resolve_resource_group(resource_group)?;
        let vm = vm_manager.get_vm(&rg, vm_name)?;
        let bastion_map: std::collections::HashMap<String, String> =
            list_helpers::detect_bastion_hosts(&rg)
                .unwrap_or_default()
                .into_iter()
                .map(|(name, location, _)| (location, name))
                .collect();
        let ssh_key = resolve_ssh_key();
        let target = build_ssh_target(&vm, vm_manager.subscription_id(), &bastion_map, &ssh_key);
        if target.ip.is_empty() {
            anyhow::bail!("No IP address found for VM '{}'", vm_name);
        }
        return Ok(vec![target]);
    }
    // List all running VMs
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let bastion_map: std::collections::HashMap<String, String> =
        list_helpers::detect_bastion_hosts(&rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();
    let sub_id = vm_manager.subscription_id().to_string();
    let ssh_key = resolve_ssh_key();
    let vms = vm_manager.list_vms(&rg)?;
    let mut targets = Vec::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        if vm.public_ip.is_none() && vm.private_ip.is_none() {
            continue;
        }
        targets.push(build_ssh_target(&vm, &sub_id, &bastion_map, &ssh_key));
    }
    if targets.is_empty() {
        anyhow::bail!("No running VMs found. Use --vm or --ip to target a specific VM.");
    }
    Ok(targets)
}
