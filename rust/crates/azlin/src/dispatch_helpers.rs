use std::io::IsTerminal;

use anyhow::{Context, Result};

use super::*;

/// Prompt the user for confirmation, handling non-TTY stdin gracefully.
///
/// - If `force` is true, returns `Ok(true)` immediately (skip prompt).
/// - If stdin is a TTY, shows a dialoguer confirmation prompt.
/// - If stdin is NOT a TTY (piped, cron, CI), returns an error advising
///   the caller to use `--yes` or `--force`.
pub(crate) fn safe_confirm(prompt: &str, force: bool) -> Result<bool> {
    if force {
        return Ok(true);
    }
    if !std::io::stdin().is_terminal() {
        anyhow::bail!(
            "Confirmation required but stdin is not a terminal. \
             Use --yes or --force to skip."
        );
    }
    Ok(dialoguer::Confirm::new()
        .with_prompt(prompt)
        .default(false)
        .interact()?)
}

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

/// Look up a VM's OS disk resource ID and location via `az vm show`.
/// Returns `(disk_id, location)` for use in snapshot/clone operations.
pub(crate) fn lookup_vm_disk_info(rg: &str, vm_name: &str) -> Result<(String, String)> {
    let output = std::process::Command::new("az")
        .args([
            "vm",
            "show",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--query",
            "[storageProfile.osDisk.managedDisk.id, location]",
            "--output",
            "tsv",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to get OS disk for VM '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let raw = String::from_utf8_lossy(&output.stdout);
    let parts: Vec<&str> = raw.trim().lines().collect();
    if parts.len() < 2 || parts[0].is_empty() {
        anyhow::bail!("No OS disk found for VM '{}'", vm_name);
    }
    Ok((parts[0].to_string(), parts[1].to_string()))
}

/// Look up a VM's public IP address. Returns `Ok(None)` if the VM has no public IP
/// (bastion-only), `Ok(Some(ip))` if it has one.
pub(crate) fn lookup_vm_public_ip(rg: &str, vm_name: &str) -> Result<Option<String>> {
    let output = std::process::Command::new("az")
        .args([
            "vm",
            "list-ip-addresses",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--query",
            "[0].virtualMachine.network.publicIpAddresses[0].ipAddress",
            "--output",
            "tsv",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to get public IP for VM '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let ip = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if ip.is_empty() || ip == "None" {
        Ok(None)
    } else {
        Ok(Some(ip))
    }
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_confirm_force_true_returns_ok_true() {
        // When force=true, should always return Ok(true) regardless of TTY state
        assert_eq!(safe_confirm("Delete everything?", true).unwrap(), true);
    }

    #[test]
    fn safe_confirm_force_true_ignores_prompt() {
        // Even with an empty prompt, force=true should succeed
        assert_eq!(safe_confirm("", true).unwrap(), true);
    }

    #[test]
    fn safe_confirm_non_tty_returns_error() {
        // In test environment, stdin is not a real TTY, so force=false should error.
        // Two possible error paths:
        //   1. is_terminal() == false → our bail with "stdin is not a terminal"
        //   2. is_terminal() == true (pseudo-TTY) → dialoguer IO error
        let result = safe_confirm("Proceed?", false);
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(
            err_msg.contains("not a terminal") || err_msg.contains("IO error"),
            "Expected terminal-related error, got: {}",
            err_msg
        );
    }

    #[test]
    fn safe_confirm_non_tty_error_suggests_flags() {
        let result = safe_confirm("Proceed?", false);
        let err_msg = result.unwrap_err().to_string();
        // When is_terminal() returns false we get our custom message with flag hints.
        // When is_terminal() returns true (pseudo-TTY) dialoguer fails with an IO
        // error — that's acceptable; the flag hints only appear in our own bail path.
        assert!(
            err_msg.contains("--yes")
                || err_msg.contains("--force")
                || err_msg.contains("not a terminal"),
            "Error should suggest --yes/--force or be a terminal error, got: {}",
            err_msg
        );
    }
}
