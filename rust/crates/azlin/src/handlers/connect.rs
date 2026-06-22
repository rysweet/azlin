//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use anyhow::Result;
use azlin_azure::AzureOps;
use azlin_core::models::{PowerState, VmInfo};

// ── Connect handler (resolution logic) ──────────────────────────────────

/// Resolve which VM to connect to. Returns (vm_name, ip, username).
pub fn resolve_connect_target(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_identifier: Option<&str>,
    default_user: &str,
) -> Result<ConnectTarget> {
    let name = match vm_identifier {
        Some(id) => id.to_string(),
        None => {
            let vms = ops.list_vms(resource_group)?;
            let running: Vec<_> = vms
                .iter()
                .filter(|v| v.power_state == PowerState::Running)
                .collect();
            if running.is_empty() {
                anyhow::bail!(
                    "No running VMs found in resource group '{}'",
                    resource_group
                );
            }
            if running.len() == 1 {
                running[0].name.clone()
            } else {
                // Multiple running VMs — return the list for interactive selection
                return Ok(ConnectTarget::NeedsSelection(
                    running
                        .iter()
                        .map(|v| {
                            let ip = v
                                .public_ip
                                .as_deref()
                                .or(v.private_ip.as_deref())
                                .unwrap_or("-");
                            (v.name.clone(), ip.to_string())
                        })
                        .collect(),
                ));
            }
        }
    };

    let vm = ops.get_vm(resource_group, &name)?;
    let ip = vm
        .public_ip
        .or(vm.private_ip)
        .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
    let username = vm
        .admin_username
        .unwrap_or_else(|| default_user.to_string());

    Ok(ConnectTarget::Resolved {
        vm_name: name,
        ip,
        username,
    })
}

/// Result of connect target resolution.
#[derive(Debug)]
pub enum ConnectTarget {
    /// Ready to connect.
    Resolved {
        vm_name: String,
        ip: String,
        username: String,
    },
    /// Multiple VMs available — caller must prompt user for selection.
    NeedsSelection(Vec<(String, String)>),
}

// ── Health handler (data layer) ─────────────────────────────────────────

/// Resolve VMs for health checking. Returns (vm_name, ip, user, power_state).
pub fn resolve_health_targets(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: Option<&str>,
) -> Result<Vec<(String, String, String, String)>> {
    let vms = if let Some(name) = vm_name {
        vec![ops.get_vm(resource_group, name)?]
    } else {
        ops.list_vms(resource_group)?
    };

    Ok(vms
        .into_iter()
        .filter_map(|vm| {
            let ip = vm.public_ip.or(vm.private_ip)?;
            let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());
            let state = vm.power_state.to_string();
            Some((vm.name, ip, user, state))
        })
        .collect())
}

// ── OsUpdate handler ────────────────────────────────────────────────────

/// Resolve the VM for os-update. Returns (ip, username).
pub fn resolve_os_update_target(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_identifier: &str,
) -> Result<(String, String)> {
    let vm = ops.get_vm(resource_group, vm_identifier)?;
    let ip = vm
        .public_ip
        .or(vm.private_ip)
        .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
    let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());
    Ok((ip, user))
}

// ── Destroy handler (dry-run) ───────────────────────────────────────────

/// Format the dry-run output for destroy.
pub fn format_destroy_dry_run(vm_name: &str, resource_group: &str) -> String {
    format!(
        "Dry run -- would delete:\n  VM: {}\n  Resource group: {}",
        vm_name, resource_group
    )
}

// ── Code handler (resolve target) ───────────────────────────────────────

/// Resolve the target for VS Code remote connection. Returns (ip, username).
pub fn resolve_code_target(
    ops: &dyn AzureOps,
    resource_group: &str,
    name: &str,
    default_user: &str,
) -> Result<(String, String)> {
    let vm = ops.get_vm(resource_group, name)?;
    let ip = vm
        .public_ip
        .or(vm.private_ip)
        .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
    let user = vm
        .admin_username
        .unwrap_or_else(|| default_user.to_string());
    Ok((ip, user))
}

// ── SSH args building ───────────────────────────────────────────────

/// Build SSH connection arguments for connecting to a VM.
pub fn build_ssh_connect_args(
    username: &str,
    ip: &str,
    key: Option<&str>,
    tmux_session: Option<&str>,
    remote_commands: &[String],
) -> Result<Vec<String>> {
    let mut args = vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
    ];
    if let Some(key_path) = key {
        args.push("-i".to_string());
        args.push(key_path.to_string());
    }
    args.push(format!("{}@{}", username, ip));

    if let Some(sess) = tmux_session {
        if !sess
            .chars()
            .all(|c| c.is_alphanumeric() || c == '_' || c == '-')
        {
            anyhow::bail!("Invalid tmux session name: must be alphanumeric, underscore, or hyphen");
        }
        if remote_commands.is_empty() {
            args.push("-t".to_string());
            args.push(format!("tmux new-session -A -s {}", sess));
        } else {
            args.extend(remote_commands.iter().cloned());
        }
    } else if !remote_commands.is_empty() {
        args.extend(remote_commands.iter().cloned());
    }

    Ok(args)
}

// ── VM picker formatting ────────────────────────────────────────────

/// Format the VM selection list for interactive connect.
pub fn format_vm_picker(vms: &[VmInfo]) -> String {
    let mut out = String::from("Select a VM to connect to:\n");
    for (i, vm) in vms.iter().enumerate() {
        let ip = vm
            .public_ip
            .as_deref()
            .or(vm.private_ip.as_deref())
            .unwrap_or("-");
        out.push_str(&format!("  [{}] {} ({})\n", i + 1, vm.name, ip));
    }
    out
}
