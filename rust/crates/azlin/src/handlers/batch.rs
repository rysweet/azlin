//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use anyhow::Result;
use azlin_azure::AzureOps;
use azlin_core::models::VmInfo;

// ── Batch stop handler (data layer) ─────────────────────────────────────

/// Execute batch stop on a list of VMs.
pub fn handle_batch_stop(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_names: &[String],
    deallocate: bool,
) -> Vec<Result<String>> {
    vm_names
        .iter()
        .map(|name| {
            ops.stop_vm(resource_group, name, deallocate)?;
            let action = if deallocate { "Deallocated" } else { "Stopped" };
            Ok(format!("{} {}", action, name))
        })
        .collect()
}

/// Execute batch start on a list of VMs.
pub fn handle_batch_start(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_names: &[String],
) -> Vec<Result<String>> {
    vm_names
        .iter()
        .map(|name| {
            ops.start_vm(resource_group, name)?;
            Ok(format!("Started {}", name))
        })
        .collect()
}

/// Execute batch delete on a list of VMs.
pub fn handle_batch_delete(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_names: &[String],
) -> Vec<Result<String>> {
    vm_names
        .iter()
        .map(|name| {
            ops.delete_vm(resource_group, name)?;
            Ok(format!("Deleted {}", name))
        })
        .collect()
}

// ── Env handler helpers ─────────────────────────────────────────────────

/// Parse env output into key-value pairs for display.
pub fn parse_env_output(output: &str) -> Vec<(String, String)> {
    output
        .lines()
        .filter_map(|line| {
            let parts: Vec<&str> = line.splitn(2, '=').collect();
            if parts.len() == 2 {
                Some((parts[0].to_string(), parts[1].to_string()))
            } else {
                None
            }
        })
        .collect()
}

// ── Session handler helpers ─────────────────────────────────────────────

/// Format a list of tmux sessions for display.
pub fn format_tmux_session_list(sessions: &[String], max_display: usize) -> String {
    if sessions.is_empty() {
        return "-".to_string();
    }
    if sessions.len() <= max_display {
        sessions.join(", ")
    } else {
        let shown: Vec<&str> = sessions
            .iter()
            .take(max_display)
            .map(|s| s.as_str())
            .collect();
        format!(
            "{} (+{} more)",
            shown.join(", "),
            sessions.len() - max_display
        )
    }
}

// ── Batch filter helper ─────────────────────────────────────────────────

/// Filter VMs by tag for batch operations.
pub fn filter_vms_by_tag(vms: &[VmInfo], tag_filter: Option<&str>) -> Vec<VmInfo> {
    match tag_filter {
        None => vms.to_vec(),
        Some(tag) => {
            let parts: Vec<&str> = tag.splitn(2, '=').collect();
            match parts.len() {
                2 => vms
                    .iter()
                    .filter(|vm| vm.tags.get(parts[0]).is_some_and(|v| v == parts[1]))
                    .cloned()
                    .collect(),
                1 => vms
                    .iter()
                    .filter(|vm| vm.tags.contains_key(parts[0]))
                    .cloned()
                    .collect(),
                _ => vms.to_vec(),
            }
        }
    }
}
