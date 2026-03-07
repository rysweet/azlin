//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use anyhow::Result;
use azlin_azure::AzureOps;
use azlin_core::models::{PowerState, VmInfo};
use std::collections::HashMap;

// ── List handler (data layer) ───────────────────────────────────────────

/// Fetch VMs for the list command, applying cache preference.
pub fn fetch_list_vms(
    ops: &dyn AzureOps,
    resource_group: Option<&str>,
    show_all: bool,
    no_cache: bool,
    default_rg: Option<&str>,
) -> Result<Vec<VmInfo>> {
    if show_all {
        if no_cache {
            ops.list_all_vms_no_cache()
        } else {
            ops.list_all_vms()
        }
    } else {
        let rg = resource_group.or(default_rg).ok_or_else(|| {
            anyhow::anyhow!("No resource group specified. Use --resource-group or set in config.")
        })?;
        if no_cache {
            ops.list_vms_no_cache(rg)
        } else {
            ops.list_vms(rg)
        }
    }
}

/// Filter VMs for the list command: remove stopped unless include_all,
/// filter by tag, filter by name pattern.
pub fn filter_list_vms(
    vms: &mut Vec<VmInfo>,
    include_all: bool,
    tag_filter: Option<&str>,
    vm_pattern: Option<&str>,
) {
    if !include_all {
        vms.retain(|vm| vm.power_state == PowerState::Running);
    }

    if let Some(tag) = tag_filter {
        let parts: Vec<&str> = tag.splitn(2, '=').collect();
        match parts.len() {
            2 => {
                let (key, val) = (parts[0], parts[1]);
                vms.retain(|vm| vm.tags.get(key).is_some_and(|v| v == val));
            }
            1 => {
                vms.retain(|vm| vm.tags.contains_key(parts[0]));
            }
            _ => {}
        }
    }

    if let Some(pattern) = vm_pattern {
        let pat = pattern.to_lowercase();
        vms.retain(|vm| vm.name.to_lowercase().contains(&pat));
    }
}

/// Build JSON output for the list command.
pub fn format_list_json(
    vms: &[VmInfo],
    tmux_sessions: &HashMap<String, Vec<String>>,
) -> Result<String> {
    let json_vms: Vec<serde_json::Value> = vms
        .iter()
        .map(|vm| {
            let ip_display = format_ip_display(vm.public_ip.as_deref(), vm.private_ip.as_deref());
            serde_json::json!({
                "name": vm.name,
                "resource_group": vm.resource_group,
                "power_state": vm.power_state.to_string(),
                "ip": ip_display,
                "public_ip": vm.public_ip,
                "private_ip": vm.private_ip,
                "location": vm.location,
                "vm_size": vm.vm_size,
                "session": vm.tags.get("azlin-session").unwrap_or(&"-".to_string()),
                "tmux_sessions": tmux_sessions.get(&vm.name).cloned().unwrap_or_default(),
            })
        })
        .collect();
    Ok(serde_json::to_string_pretty(&json_vms)?)
}

/// Format IP display, preferring public over private.
pub fn format_ip_display(public: Option<&str>, private: Option<&str>) -> String {
    match (public, private) {
        (Some(pub_ip), _) => pub_ip.to_string(),
        (None, Some(priv_ip)) => format!("({})", priv_ip),
        _ => "-".to_string(),
    }
}

// ── List summary stats ──────────────────────────────────────────────────

/// Count VMs by power state for summary display.
pub fn count_by_state(vms: &[VmInfo]) -> HashMap<String, usize> {
    let mut counts = HashMap::new();
    for vm in vms {
        *counts.entry(vm.power_state.to_string()).or_insert(0) += 1;
    }
    counts
}

/// Calculate a list summary string.
pub fn format_list_summary(total: usize, tmux_count: usize, show_all_hint: bool) -> String {
    let mut out = String::new();
    if tmux_count > 0 {
        out.push_str(&format!(
            "Total: {} VMs | {} tmux sessions",
            total, tmux_count
        ));
    } else {
        out.push_str(&format!("Total: {} VMs", total));
    }

    if show_all_hint {
        out.push_str("\n\nHints:");
        out.push_str("\n  azlin list -a        Show all VMs across all resource groups");
        out.push_str("\n  azlin list -w        Wide mode (show VM Name, SKU columns)");
        out.push_str("\n  azlin list -r        Restore all tmux sessions in new terminal window");
        out.push_str("\n  azlin list -q        Show quota usage (slower)");
        out.push_str("\n  azlin list -v        Verbose mode (show tunnel/SSH details)");
    }
    out
}

// ── List header builder ─────────────────────────────────────────────────

/// Column configuration for list display.
pub struct ListColumnConfig {
    pub show_tmux: bool,
    pub wide: bool,
    pub with_latency: bool,
    pub with_health: bool,
    pub show_procs: bool,
}

/// Build the header row for the list command table.
pub fn build_list_headers(config: &ListColumnConfig) -> Vec<&'static str> {
    let mut headers = vec!["Session"];
    if config.show_tmux {
        headers.push("Tmux");
    }
    if config.wide {
        headers.push("VM Name");
    }
    headers.extend_from_slice(&["OS", "Status", "IP", "Region"]);
    if config.wide {
        headers.push("SKU");
    }
    headers.extend_from_slice(&["CPU", "Mem"]);
    if config.with_latency {
        headers.push("Latency");
    }
    if config.with_health {
        headers.push("Health");
    }
    if config.show_procs {
        headers.push("Top Procs");
    }
    headers
}

/// A row of data for the list command.
pub struct ListRow {
    pub session: String,
    pub tmux: String,
    pub vm_name: String,
    pub os_display: String,
    pub power_state: String,
    pub ip_display: String,
    pub location: String,
    pub vm_size: String,
    pub cpu: String,
    pub mem: String,
    pub latency: Option<String>,
    pub health: Option<String>,
    pub top_procs: Option<String>,
}

/// Build a data row for a VM in the list.
pub fn build_list_row(
    vm: &VmInfo,
    tmux_sessions: Option<&Vec<String>>,
    latency_ms: Option<u64>,
    health: Option<&str>,
    procs: Option<&str>,
) -> ListRow {
    let session = vm
        .tags
        .get("azlin-session")
        .cloned()
        .unwrap_or_else(|| "-".to_string());
    let tmux = tmux_sessions
        .map(|s| s.join(", "))
        .unwrap_or_else(|| "-".to_string());
    let ip_display = format_ip_display(vm.public_ip.as_deref(), vm.private_ip.as_deref());

    ListRow {
        session,
        tmux,
        vm_name: vm.name.clone(),
        os_display: format!("{:?}", vm.os_type),
        power_state: vm.power_state.to_string(),
        ip_display,
        location: vm.location.clone(),
        vm_size: vm.vm_size.clone(),
        cpu: String::new(),
        mem: String::new(),
        latency: latency_ms.map(|l| format!("{}ms", l)),
        health: health.map(|h| h.to_string()),
        top_procs: procs.map(|p| p.to_string()),
    }
}

/// Format list data as CSV.
pub fn format_list_csv(headers: &[&str], rows: &[ListRow], config: &ListColumnConfig) -> String {
    let mut out = headers.join(",");
    out.push('\n');
    for row in rows {
        let mut fields = vec![row.session.clone()];
        if config.show_tmux {
            fields.push(row.tmux.clone());
        }
        if config.wide {
            fields.push(row.vm_name.clone());
        }
        fields.push(row.os_display.clone());
        fields.push(row.power_state.clone());
        fields.push(row.ip_display.clone());
        fields.push(row.location.clone());
        if config.wide {
            fields.push(row.vm_size.clone());
        }
        fields.push(row.cpu.clone());
        fields.push(row.mem.clone());
        if config.with_latency {
            fields.push(row.latency.clone().unwrap_or_default());
        }
        if config.with_health {
            fields.push(row.health.clone().unwrap_or_default());
        }
        if config.show_procs {
            fields.push(row.top_procs.clone().unwrap_or_default());
        }
        out.push_str(&fields.join(","));
        out.push('\n');
    }
    out
}

// ── List footer builder ──────────────────────────────────────────────

/// Build the footer text for the list command (total + tmux count).
pub fn format_list_footer(total: usize, tmux_count: usize) -> String {
    if tmux_count > 0 {
        format!("Total: {} VMs | {} tmux sessions", total, tmux_count)
    } else {
        format!("Total: {} VMs", total)
    }
}

/// Build full JSON output for the list command (alternative to table/CSV).
pub fn build_list_json(
    vms: &[VmInfo],
    tmux_sessions: &HashMap<String, Vec<String>>,
) -> serde_json::Value {
    let json_vms: Vec<serde_json::Value> = vms
        .iter()
        .map(|vm| {
            let ip_display = format_ip_display(vm.public_ip.as_deref(), vm.private_ip.as_deref());
            serde_json::json!({
                "name": vm.name,
                "resource_group": vm.resource_group,
                "power_state": vm.power_state.to_string(),
                "ip": ip_display,
                "public_ip": vm.public_ip,
                "private_ip": vm.private_ip,
                "location": vm.location,
                "vm_size": vm.vm_size,
                "session": vm.tags.get("azlin-session").unwrap_or(&"-".to_string()),
                "tmux_sessions": tmux_sessions.get(&vm.name).cloned().unwrap_or_default(),
            })
        })
        .collect();
    serde_json::Value::Array(json_vms)
}
