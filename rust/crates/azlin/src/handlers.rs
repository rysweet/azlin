//! Extracted command handler logic for testability.
//!
//! Each handler function accepts `&dyn AzureOps` instead of `&VmManager`,
//! enabling mock-based testing without live Azure credentials.
//!
//! Some functions are only called from tests currently — they provide
//! covered logic that mirrors main.rs command handlers.
#![allow(dead_code)]
//!
//! The handlers produce structured output (strings, data) rather than directly
//! printing, so tests can assert on return values.
//!
//! Functions are being wired into dispatch_command incrementally. Those not yet
//! wired are still exercised via tests and will be integrated in follow-up PRs.

use std::collections::HashMap;

use anyhow::Result;
use azlin_azure::AzureOps;
use azlin_core::models::{PowerState, VmInfo};

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

// ── Orphan cost estimation ──────────────────────────────────────────────

/// Estimate monthly cost of orphaned public IPs.
pub fn estimate_orphan_costs(orphan_count: usize, cost_per_ip: f64) -> String {
    let total = orphan_count as f64 * cost_per_ip;
    format!(
        "{} orphaned public IP(s) estimated at ${:.2}/month",
        orphan_count, total
    )
}

// ── Health metric classification ─────────────────────────────────────

/// Severity level for metric thresholds.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Ok,
    Warning,
    Critical,
}

/// Classify a percentage metric (CPU, memory, disk) by threshold.
pub fn classify_percent_metric(value: f32, warn: f32, crit: f32) -> Severity {
    if value > crit {
        Severity::Critical
    } else if value > warn {
        Severity::Warning
    } else {
        Severity::Ok
    }
}

/// Classify an error count metric.
pub fn classify_error_count(count: u32) -> Severity {
    if count > 10 {
        Severity::Critical
    } else if count > 0 {
        Severity::Warning
    } else {
        Severity::Ok
    }
}

/// Classify a power state string.
pub fn classify_power_state(state: &str) -> Severity {
    let lower = state.to_lowercase();
    match lower.as_str() {
        "running" => Severity::Ok,
        "stopped" | "deallocated" => Severity::Critical,
        _ => Severity::Warning,
    }
}

/// Classify agent status.
pub fn classify_agent_status(status: &str) -> Severity {
    match status {
        "OK" => Severity::Ok,
        "Down" => Severity::Critical,
        _ => Severity::Warning,
    }
}

// ── Snapshot schedule formatting ────────────────────────────────────

/// Snapshot schedule info for display.
pub struct SnapshotScheduleInfo {
    pub vm_name: String,
    pub resource_group: String,
    pub every_hours: u32,
    pub keep_count: u32,
    pub enabled: bool,
    pub created: String,
}

/// Format snapshot schedule status as a string.
pub fn format_snapshot_status(info: &SnapshotScheduleInfo) -> String {
    let mut out = format!("Snapshot schedule for VM '{}':\n", info.vm_name);
    out.push_str(&format!("  Resource group: {}\n", info.resource_group));
    out.push_str(&format!(
        "  Interval:       every {} hours\n",
        info.every_hours
    ));
    out.push_str(&format!("  Keep count:     {}\n", info.keep_count));
    out.push_str(&format!("  Enabled:        {}\n", info.enabled));
    out.push_str(&format!("  Created:        {}", info.created));
    out
}

/// Format a "no schedule" status message.
pub fn format_snapshot_no_schedule(vm_name: &str) -> String {
    format!(
        "Snapshot schedule status for VM '{}': no schedule configured",
        vm_name
    )
}

// ── Cost summary formatting ─────────────────────────────────────────

/// Format a cost summary for display. Supports JSON, CSV, and table output.
pub fn format_cost_summary(
    summary: &azlin_core::models::CostSummary,
    output_format: &str,
    from: &Option<String>,
    to: &Option<String>,
    estimate: bool,
    by_vm: bool,
) -> String {
    let mut out = String::new();
    if output_format == "json" {
        match serde_json::to_string_pretty(summary) {
            Ok(json) => out.push_str(&json),
            Err(e) => out.push_str(&format!("Failed to serialize cost data: {e}")),
        }
        return out;
    }

    let is_csv = output_format == "csv";

    if is_csv {
        out.push_str("Total Cost,Currency,Period Start,Period End\n");
        out.push_str(&format!(
            "{:.2},{},{},{}",
            summary.total_cost,
            summary.currency,
            summary.period_start.format("%Y-%m-%d"),
            summary.period_end.format("%Y-%m-%d")
        ));
    } else {
        out.push_str(&format!(
            "Total Cost: ${:.2} {}",
            summary.total_cost, summary.currency
        ));
        out.push_str(&format!(
            "\nPeriod: {} to {}",
            summary.period_start.format("%Y-%m-%d"),
            summary.period_end.format("%Y-%m-%d")
        ));

        if let Some(ref f) = from {
            out.push_str(&format!("\nFrom filter: {}", f));
        }
        if let Some(ref t) = to {
            out.push_str(&format!("\nTo filter: {}", t));
        }
        if estimate {
            out.push_str(&format!(
                "\nEstimate: ${:.2}/month (projected)",
                summary.total_cost
            ));
        }
    }

    if by_vm && !summary.by_vm.is_empty() {
        if is_csv {
            out.push_str("\nVM Name,Cost,Currency");
            for vc in &summary.by_vm {
                out.push_str(&format!("\n{},{:.2},{}", vc.vm_name, vc.cost, vc.currency));
            }
        } else {
            out.push('\n');
            for vc in &summary.by_vm {
                out.push_str(&format!(
                    "\n{:<20} ${:.2} {}",
                    vc.vm_name, vc.cost, vc.currency
                ));
            }
        }
    } else if by_vm {
        out.push_str("\n\nNo per-VM cost data available.");
    }

    out
}

// ── Cost data parsing ───────────────────────────────────────────────

/// Parse cost history rows from JSON data into (date, cost) pairs.
pub fn parse_cost_history_rows(data: &serde_json::Value) -> Vec<(String, String)> {
    let mut result = Vec::new();
    if let Some(rows) = data.get("rows").and_then(|r| r.as_array()) {
        for row in rows {
            if let Some(arr) = row.as_array() {
                let cost = arr
                    .first()
                    .and_then(|v| v.as_f64())
                    .map(|v| format!("${:.2}", v))
                    .unwrap_or_else(|| "-".to_string());
                let date = arr
                    .get(1)
                    .and_then(|v| v.as_str().or_else(|| v.as_i64().map(|_| "")))
                    .map(|s| s.to_string())
                    .or_else(|| arr.get(1).and_then(|v| v.as_i64()).map(|v| v.to_string()))
                    .unwrap_or_else(|| "-".to_string());
                result.push((date, cost));
            }
        }
    }
    result
}

/// Parse recommendation entries from JSON array.
pub fn parse_recommendation_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    let mut result = Vec::new();
    if let Some(recs) = data.as_array() {
        for rec in recs {
            let category = rec
                .get("category")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let impact = rec
                .get("impact")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let problem = rec
                .get("shortDescription")
                .and_then(|v| v.get("problem"))
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            result.push((category, impact, problem));
        }
    }
    result
}

/// Parse cost action entries from JSON array.
pub fn parse_cost_action_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    let mut result = Vec::new();
    if let Some(recs) = data.as_array() {
        for rec in recs {
            let resource = rec
                .get("impactedField")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let impact = rec
                .get("impact")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let problem = rec
                .get("shortDescription")
                .and_then(|v| v.get("problem"))
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            result.push((resource, impact, problem));
        }
    }
    result
}

// ── Create VM result formatting ─────────────────────────────────────

/// Build property rows for a newly created VM (for table display).
pub fn build_create_vm_rows(
    vm: &VmInfo,
    resource_group: &str,
    vm_size: &str,
    region: &str,
) -> Vec<(String, String)> {
    let mut rows = vec![
        ("Name".to_string(), vm.name.clone()),
        ("Resource Group".to_string(), resource_group.to_string()),
        ("Size".to_string(), vm_size.to_string()),
        ("Region".to_string(), region.to_string()),
        ("State".to_string(), vm.power_state.to_string()),
    ];
    if let Some(ref ip) = vm.public_ip {
        rows.push(("Public IP".to_string(), ip.clone()));
    }
    if let Some(ref ip) = vm.private_ip {
        rows.push(("Private IP".to_string(), ip.clone()));
    }
    rows
}

// ── Doit VM filtering ───────────────────────────────────────────────

/// Filter VMs tagged as doit-created, optionally by username.
pub fn filter_doit_vms<'a>(vms: &'a [VmInfo], username: Option<&str>) -> Vec<&'a VmInfo> {
    vms.iter()
        .filter(|vm| {
            let has_tag = vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
            let user_match = username.is_none_or(|u| vm.admin_username.as_deref() == Some(u));
            has_tag && user_match
        })
        .collect()
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

// ── Help handler ──────────────────────────────────────────────────────

/// Build extended help text for a given command (or general help if None).
pub fn build_extended_help(command_name: Option<&str>) -> String {
    match command_name {
        Some(cmd) => {
            let mut out = format!("azlin {} -- Extended help\n\n", cmd);
            out.push_str(&format!("Run 'azlin {} --help' for usage details.", cmd));
            out
        }
        None => {
            let mut out = String::from("azlin -- Azure VM fleet management CLI\n\n");
            out.push_str("Run 'azlin --help' for a list of commands.\n");
            out.push_str("Run 'azlin <command> --help' for command-specific help.\n\n");
            out.push_str("Tip: Generate shell completions with:\n");
            out.push_str("  azlin completions bash >> ~/.bashrc\n");
            out.push_str("  azlin completions zsh  >> ~/.zshrc\n");
            out.push_str("  azlin completions fish >  ~/.config/fish/completions/azlin.fish\n");
            out
        }
    }
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

// ── Snapshot formatting helpers ──────────────────────────────────────

/// Format a list of snapshot JSON values as rows for table display.
/// Returns Vec of (name, disk_size, time_created, state) tuples.
pub fn format_snapshot_rows(
    snapshots: &[serde_json::Value],
) -> Vec<(String, String, String, String)> {
    snapshots
        .iter()
        .map(|snap| {
            (
                snap["name"].as_str().unwrap_or("-").to_string(),
                snap["diskSizeGb"].to_string(),
                snap["timeCreated"].as_str().unwrap_or("-").to_string(),
                snap["provisioningState"]
                    .as_str()
                    .unwrap_or("-")
                    .to_string(),
            )
        })
        .collect()
}

/// Build the snapshot name from a VM name and timestamp.
pub fn build_snapshot_name(vm_name: &str, timestamp: &str) -> String {
    format!("{}_snapshot_{}", vm_name, timestamp)
}

/// Build a snapshot schedule info struct from parameters.
pub fn build_snapshot_schedule_info(
    vm_name: &str,
    resource_group: &str,
    every_hours: u32,
    keep_count: u32,
    enabled: bool,
    created: &str,
) -> SnapshotScheduleInfo {
    SnapshotScheduleInfo {
        vm_name: vm_name.to_string(),
        resource_group: resource_group.to_string(),
        every_hours,
        keep_count,
        enabled,
        created: created.to_string(),
    }
}

// ── Storage formatting helpers ───────────────────────────────────────

/// Format a storage account's key details for display.
/// Returns a list of (key, value) pairs.
pub fn format_storage_status(acct: &serde_json::Value) -> Vec<(String, String)> {
    vec![
        (
            "Name".to_string(),
            acct["name"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "Location".to_string(),
            acct["location"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "Kind".to_string(),
            acct["kind"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "SKU".to_string(),
            acct["sku"]["name"].as_str().unwrap_or("-").to_string(),
        ),
        (
            "State".to_string(),
            acct["provisioningState"]
                .as_str()
                .unwrap_or("-")
                .to_string(),
        ),
        (
            "Primary Endpoint".to_string(),
            acct["primaryEndpoints"]["file"]
                .as_str()
                .unwrap_or("-")
                .to_string(),
        ),
    ]
}

/// Build the NFS mount command string for a storage account.
pub fn build_nfs_mount_command(storage_name: &str, mount_point: &str) -> String {
    format!(
        "sudo mkdir -p {mp} && sudo mount -t nfs {name}.file.core.windows.net:/{name}/home {mp} -o vers=3,sec=sys",
        name = storage_name,
        mp = mount_point,
    )
}

/// Build the CIFS mount options string.
pub fn build_cifs_mount_options(credentials_path: &str) -> String {
    format!(
        "vers=3.0,credentials={},serverino,nosharesock,actimeo=30",
        credentials_path
    )
}

/// Build the UNC path for an Azure Files share.
pub fn build_azure_files_unc(account: &str, share: &str) -> String {
    format!("//{}.file.core.windows.net/{}", account, share)
}

// ── Cost dashboard formatting ────────────────────────────────────────

/// Format the cost dashboard output for a resource group.
pub fn format_cost_dashboard(
    resource_group: &str,
    total_cost: f64,
    currency: &str,
    period_start: &str,
    period_end: &str,
) -> String {
    let mut out = format!("Cost Dashboard for '{}':\n", resource_group);
    out.push_str(&format!("  Total: ${:.2} {}\n", total_cost, currency));
    out.push_str(&format!("  Period: {} to {}", period_start, period_end));
    out
}

/// Build the scope string for Azure Cost Management queries.
pub fn build_cost_management_scope(subscription_id: &str, resource_group: &str) -> String {
    format!(
        "/subscriptions/{}/resourceGroups/{}",
        subscription_id, resource_group
    )
}

/// Build the budget name for a resource group.
pub fn build_budget_name(resource_group: &str) -> String {
    format!("azlin-budget-{}", resource_group)
}

/// Format the budget creation result message.
pub fn format_budget_created(amount: f64, resource_group: &str, threshold: u32) -> String {
    format!(
        "Budget set: ${:.2}/month for '{}' (alert at {}%)",
        amount, resource_group, threshold
    )
}

/// Determine the date range for cost history queries.
pub fn build_cost_history_dates(days: u32) -> (String, String) {
    let now = chrono::Utc::now();
    let start = (now - chrono::Duration::days(days as i64))
        .format("%Y-%m-%dT00:00:00+00:00")
        .to_string();
    let end = now.format("%Y-%m-%dT23:59:59+00:00").to_string();
    (start, end)
}

// ── Cleanup / orphan detection helpers ───────────────────────────────

/// Parse NIC JSON array and classify orphaned NICs (no VM attached).
pub fn classify_orphaned_nics(nics: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nics.iter()
        .filter(|nic| {
            let attached = nic
                .get("virtualMachine")
                .map(|v| !v.is_null())
                .unwrap_or(false);
            !attached
        })
        .filter_map(|nic| {
            let name = nic.get("name")?.as_str()?.to_string();
            let rg = nic
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            Some(OrphanedResourceInfo {
                name,
                resource_type: "NIC".to_string(),
                resource_group: rg,
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Parse public IP JSON array and classify orphaned IPs (no ipConfiguration).
pub fn classify_orphaned_ips(
    ips: &[serde_json::Value],
    cost_per_ip: f64,
) -> Vec<OrphanedResourceInfo> {
    ips.iter()
        .filter(|ip| {
            let attached = ip
                .get("ipConfiguration")
                .map(|v| !v.is_null())
                .unwrap_or(false);
            !attached
        })
        .filter_map(|ip| {
            let name = ip.get("name")?.as_str()?.to_string();
            let rg = ip
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            Some(OrphanedResourceInfo {
                name,
                resource_type: "Public IP".to_string(),
                resource_group: rg,
                estimated_monthly_cost: cost_per_ip,
            })
        })
        .collect()
}

/// Parse NSG JSON array and classify orphaned NSGs (no NICs or subnets attached).
pub fn classify_orphaned_nsgs(nsgs: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nsgs.iter()
        .filter(|nsg| {
            let has_nics = nsg
                .get("networkInterfaces")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            let has_subnets = nsg
                .get("subnets")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            !has_nics && !has_subnets
        })
        .filter_map(|nsg| {
            let name = nsg.get("name")?.as_str()?.to_string();
            let rg = nsg
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            Some(OrphanedResourceInfo {
                name,
                resource_type: "NSG".to_string(),
                resource_group: rg,
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Lightweight orphaned resource info for handler-level logic.
/// Uses String resource_type to avoid coupling to azlin_azure types.
#[derive(Debug, Clone, PartialEq)]
pub struct OrphanedResourceInfo {
    pub name: String,
    pub resource_type: String,
    pub resource_group: String,
    pub estimated_monthly_cost: f64,
}

/// Build a cleanup plan: list of resources to delete, with dry_run annotation.
pub fn build_cleanup_plan(resources: &[OrphanedResourceInfo], dry_run: bool) -> Vec<CleanupAction> {
    resources
        .iter()
        .map(|r| CleanupAction {
            resource_name: r.name.clone(),
            resource_type: r.resource_type.clone(),
            resource_group: r.resource_group.clone(),
            action: if dry_run {
                "would delete".to_string()
            } else {
                "delete".to_string()
            },
        })
        .collect()
}

/// A planned cleanup action.
#[derive(Debug, Clone, PartialEq)]
pub struct CleanupAction {
    pub resource_name: String,
    pub resource_type: String,
    pub resource_group: String,
    pub action: String,
}

/// Format an orphan report from a list of orphaned resources.
pub fn format_orphan_report(resources: &[OrphanedResourceInfo]) -> String {
    if resources.is_empty() {
        return "No orphaned resources found.".to_string();
    }
    let mut out = format!("Found {} orphaned resource(s):\n", resources.len());
    let total_cost: f64 = resources.iter().map(|r| r.estimated_monthly_cost).sum();
    for r in resources {
        out.push_str(&format!(
            "  {} '{}' ({}) - ${:.2}/mo\n",
            r.resource_type, r.name, r.resource_group, r.estimated_monthly_cost
        ));
    }
    out.push_str(&format!("Estimated savings: ${:.2}/month", total_cost));
    out
}

// ── Snapshot enable/disable/status handlers ─────────────────────────────

/// Build a SnapshotScheduleInfo from raw schedule parameters.
pub fn build_snapshot_enable_output(
    vm_name: &str,
    _resource_group: &str,
    every_hours: u32,
    keep_count: u32,
) -> String {
    format!(
        "Scheduled snapshots enabled for VM '{}': every {}h, keep {}",
        vm_name, every_hours, keep_count
    )
}

/// Build the disable output message based on schedule state.
pub fn build_snapshot_disable_output(vm_name: &str, had_schedule: bool) -> String {
    if had_schedule {
        format!("Scheduled snapshots disabled for VM '{}'", vm_name)
    } else {
        format!("No schedule configured for VM '{}'", vm_name)
    }
}

/// Determine whether a snapshot sync is needed based on the most recent snapshot age.
/// Returns (needs_snapshot, skip_message) where skip_message is Some if skipping.
pub fn check_snapshot_sync_needed(
    snapshots: &[&serde_json::Value],
    vm_name: &str,
    every_hours: u32,
    now: chrono::DateTime<chrono::Utc>,
) -> (bool, Option<String>) {
    let newest = snapshots
        .iter()
        .filter_map(|s| {
            s["timeCreated"]
                .as_str()
                .and_then(|t| chrono::DateTime::parse_from_rfc3339(t).ok())
        })
        .max();
    if let Some(latest) = newest {
        let age = now.signed_duration_since(latest.with_timezone(&chrono::Utc));
        if age.num_hours() < every_hours as i64 {
            return (
                false,
                Some(format!(
                    "VM '{}': latest snapshot is {}h old (interval {}h), skipping",
                    vm_name,
                    age.num_hours(),
                    every_hours
                )),
            );
        }
    }
    (true, None)
}

/// Format sync completion message.
pub fn format_snapshot_sync_complete(vm_name: Option<&str>) -> String {
    match vm_name {
        Some(name) => format!("Snapshot sync completed for VM '{}'", name),
        None => "Snapshot sync completed for all VMs".to_string(),
    }
}

// ── Storage formatting handlers ─────────────────────────────────────────

/// Format the output message for a successful storage account creation.
pub fn format_storage_created(name: &str, size: u32, tier: &str) -> String {
    format!("Created storage account '{}' ({} GB, {})", name, size, tier)
}

/// Format the output message for a successful storage account deletion.
pub fn format_storage_deleted(name: &str) -> String {
    format!("Deleted storage account '{}'", name)
}

/// Format the mount success message.
pub fn format_storage_mounted(storage_name: &str, vm: &str, mount_point: &str) -> String {
    format!(
        "Mounted '{}' on VM '{}' at {}",
        storage_name, vm, mount_point
    )
}

/// Format the unmount success message.
pub fn format_storage_unmounted(vm: &str) -> String {
    format!("Unmounted NFS storage from VM '{}'", vm)
}

/// Validate a storage account name (Azure allows only [a-zA-Z0-9-]).
pub fn validate_storage_name(name: &str) -> Result<()> {
    if !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        anyhow::bail!("Invalid storage name: contains disallowed characters");
    }
    Ok(())
}

/// Determine the default mount point for NFS storage.
pub fn default_nfs_mount_point(storage_name: &str) -> String {
    format!("/mnt/{}", storage_name)
}

// ── Costs formatting handlers ───────────────────────────────────────────

/// Format cost history table header text.
pub fn format_cost_history_header(resource_group: &str, days: u32) -> String {
    format!(
        "Cost history for '{}' (last {} days):",
        resource_group, days
    )
}

/// Format recommendation display header.
pub fn format_recommendations_header(resource_group: &str) -> String {
    format!("Cost recommendations for '{}':", resource_group)
}

/// Format the "no recommendations" message.
pub fn format_no_recommendations(resource_group: &str, priority: &str) -> String {
    format!(
        "No cost recommendations found for '{}' (priority: {})",
        resource_group, priority
    )
}

/// Format the budget list empty message.
pub fn format_no_budgets(resource_group: &str) -> String {
    format!("No budgets found for '{}'.", resource_group)
}

/// Format the budget deleted message.
pub fn format_budget_deleted(resource_group: &str) -> String {
    format!("Budget deleted for '{}'.", resource_group)
}

/// Format "no pending cost actions" message.
pub fn format_no_cost_actions(resource_group: &str) -> String {
    format!("No pending cost actions in '{}'", resource_group)
}

/// Format cost actions header (with or without dry_run).
pub fn format_cost_actions_header(action: &str, resource_group: &str, dry_run: bool) -> String {
    if dry_run {
        format!(
            "Would {} the following cost actions in '{}':",
            action, resource_group
        )
    } else {
        format!("Cost actions ({}) in '{}':", action, resource_group)
    }
}

/// Build advisor recommendation query args with optional priority filter.
pub fn build_advisor_args(resource_group: &str, priority: Option<&str>) -> Vec<String> {
    let mut args = vec![
        "advisor".to_string(),
        "recommendation".to_string(),
        "list".to_string(),
        "--resource-group".to_string(),
        resource_group.to_string(),
        "-o".to_string(),
        "json".to_string(),
    ];
    if let Some(pri) = priority {
        args.push("--query".to_string());
        args.push(format!("[?impact=='{}']", pri));
    }
    args
}

// ── Cleanup/orphan classification handlers ──────────────────────────────

/// Classify NICs as orphaned if they have no virtual machine attached.
/// Pure function over parsed JSON — no CLI calls.
pub fn find_orphaned_nics(nics: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nics.iter()
        .filter(|nic| {
            !nic.get("virtualMachine")
                .map(|v| !v.is_null())
                .unwrap_or(false)
        })
        .filter_map(|nic| {
            let name = nic.get("name")?.as_str()?;
            let rg = nic
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown");
            Some(OrphanedResourceInfo {
                name: name.to_string(),
                resource_type: "NetworkInterface".to_string(),
                resource_group: rg.to_string(),
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Classify public IPs as orphaned if they have no ipConfiguration.
pub fn find_orphaned_public_ips(
    ips: &[serde_json::Value],
    cost_per_ip: f64,
) -> Vec<OrphanedResourceInfo> {
    ips.iter()
        .filter(|ip| {
            !ip.get("ipConfiguration")
                .map(|v| !v.is_null())
                .unwrap_or(false)
        })
        .filter_map(|ip| {
            let name = ip.get("name")?.as_str()?;
            let rg = ip
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown");
            Some(OrphanedResourceInfo {
                name: name.to_string(),
                resource_type: "PublicIp".to_string(),
                resource_group: rg.to_string(),
                estimated_monthly_cost: cost_per_ip,
            })
        })
        .collect()
}

/// Classify NSGs as orphaned if they have no attached NICs or subnets.
pub fn find_orphaned_nsgs(nsgs: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nsgs.iter()
        .filter(|nsg| {
            let has_nics = nsg
                .get("networkInterfaces")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            let has_subnets = nsg
                .get("subnets")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            !has_nics && !has_subnets
        })
        .filter_map(|nsg| {
            let name = nsg.get("name")?.as_str()?;
            let rg = nsg
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown");
            Some(OrphanedResourceInfo {
                name: name.to_string(),
                resource_type: "NetworkSecurityGroup".to_string(),
                resource_group: rg.to_string(),
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Format a cleanup summary line.
pub fn format_cleanup_complete(deleted: usize, total: usize) -> String {
    format!(
        "Cleanup complete. Deleted {}/{} orphaned resources.",
        deleted, total
    )
}

/// Format the scan header for cleanup.
pub fn format_cleanup_scan_header(resource_group: &str, age_days: u32, dry_run: bool) -> String {
    format!(
        "{}Scanning for orphaned resources in '{}' (older than {} days)...",
        if dry_run { "Dry run — " } else { "" },
        resource_group,
        age_days
    )
}

// ── Autopilot handlers ──────────────────────────────────────────────────

/// Build the autopilot TOML config table.
pub fn build_autopilot_config(
    budget: Option<u32>,
    strategy: &str,
    idle_threshold: u32,
    cpu_threshold: u32,
    timestamp: &str,
) -> toml::Value {
    let mut config = toml::map::Map::new();
    config.insert("enabled".to_string(), toml::Value::Boolean(true));
    if let Some(b) = budget {
        config.insert("budget".to_string(), toml::Value::Integer(b as i64));
    }
    config.insert(
        "strategy".to_string(),
        toml::Value::String(strategy.to_string()),
    );
    config.insert(
        "idle_threshold_minutes".to_string(),
        toml::Value::Integer(idle_threshold as i64),
    );
    config.insert(
        "cpu_threshold_percent".to_string(),
        toml::Value::Integer(cpu_threshold as i64),
    );
    config.insert(
        "updated".to_string(),
        toml::Value::String(timestamp.to_string()),
    );
    toml::Value::Table(config)
}

/// Format the autopilot enable output message.
pub fn format_autopilot_enabled(
    budget: Option<u32>,
    strategy: &str,
    idle_threshold: u32,
    cpu_threshold: u32,
) -> String {
    let mut out = "Autopilot enabled:\n".to_string();
    if let Some(b) = budget {
        out.push_str(&format!("  Budget:         ${}/month\n", b));
    }
    out.push_str(&format!("  Strategy:       {}\n", strategy));
    out.push_str(&format!("  Idle threshold: {} min\n", idle_threshold));
    out.push_str(&format!("  CPU threshold:  {}%", cpu_threshold));
    out
}

/// Format the autopilot status output from a parsed TOML value.
pub fn format_autopilot_status(config: Option<&toml::Value>) -> String {
    match config {
        Some(val) => {
            if let Some(t) = val.as_table() {
                let enabled = t.get("enabled").and_then(|v| v.as_bool()).unwrap_or(false);
                let mut out = format!(
                    "Autopilot: {}",
                    if enabled { "ENABLED" } else { "DISABLED" }
                );
                for (k, v) in t {
                    if k != "enabled" {
                        out.push_str(&format!("\n  {}: {}", k, v));
                    }
                }
                out
            } else {
                "Autopilot: invalid configuration".to_string()
            }
        }
        None => "Autopilot: not configured\nEnable with: azlin autopilot enable".to_string(),
    }
}

/// Parse autopilot config to get thresholds.
pub fn parse_autopilot_thresholds(config: Option<&toml::Value>) -> (u32, f64) {
    match config {
        Some(val) => {
            let thresh = val
                .as_table()
                .and_then(|t| t.get("idle_threshold_minutes"))
                .and_then(|v| v.as_integer())
                .unwrap_or(30) as u32;
            let limit = val
                .as_table()
                .and_then(|t| t.get("cost_limit_usd"))
                .and_then(|v| v.as_float())
                .unwrap_or(0.0);
            (thresh, limit)
        }
        None => (30, 0.0),
    }
}

/// Classify a VM's CPU/uptime into an autopilot action recommendation.
/// Returns Some(action_name) if an action is recommended, None if VM is active.
pub fn classify_autopilot_vm(
    cpu_pct: f64,
    uptime_secs: f64,
    idle_threshold_minutes: u32,
) -> Option<String> {
    let idle_mins = idle_threshold_minutes as f64;
    if cpu_pct < 5.0 && uptime_secs > idle_mins * 60.0 {
        Some("deallocate".to_string())
    } else {
        None
    }
}

/// Format autopilot dry-run report.
pub fn format_autopilot_dry_run(actions: &[(String, String)]) -> String {
    let mut out = format!("\nDry run — {} action(s) would be taken:", actions.len());
    for (name, action) in actions {
        out.push_str(&format!("\n  {} -> {}", name, action));
    }
    out
}

// ── Context handlers ────────────────────────────────────────────────────

/// Format context list output for table display.
pub fn format_context_list_table(contexts: &[(String, bool)]) -> String {
    let mut out = String::new();
    for (name, is_active) in contexts {
        if *is_active {
            out.push_str(&format!("* {}\n", name));
        } else {
            out.push_str(&format!("  {}\n", name));
        }
    }
    out
}

/// Format the "no contexts" message.
pub fn format_no_contexts() -> &'static str {
    "No contexts found. Create one with: azlin context create <name>"
}

/// Format the context show output.
pub fn format_context_show(name: &str, content: Option<&str>) -> String {
    let mut out = format!("Current context: {}", name);
    if let Some(c) = content {
        out.push_str(&format!("\n{}", c.trim()));
    }
    out
}

/// Format the context switch message.
pub fn format_context_switched(name: &str) -> String {
    format!("Switched to context '{}'", name)
}

/// Format the context create message.
pub fn format_context_created(name: &str) -> String {
    format!("Created context '{}'", name)
}

/// Format the context delete message.
pub fn format_context_deleted(name: &str) -> String {
    format!("Deleted context '{}'", name)
}

/// Format the context rename message.
pub fn format_context_renamed(old_name: &str, new_name: &str) -> String {
    format!("Renamed context '{}' -> '{}'", old_name, new_name)
}

// ── Keys handlers ───────────────────────────────────────────────────────

/// Build rows for the keys list table from directory entries.
/// Each row: [filename, key_type, size_bytes, modified_date]
pub fn build_key_list_row(name: &str, size: u64, modified: &str) -> Vec<String> {
    let key_type = if name.contains("ed25519") {
        "ed25519"
    } else if name.contains("ecdsa") {
        "ecdsa"
    } else if name.contains("rsa") {
        "rsa"
    } else if name.contains("dsa") {
        "dsa"
    } else {
        "unknown"
    };
    vec![
        name.to_string(),
        key_type.to_string(),
        size.to_string(),
        modified.to_string(),
    ]
}

/// Determine if a file looks like an SSH key based on its name and
/// whether its .pub companion exists.
pub fn is_ssh_key_file(name: &str, has_pub_companion: bool) -> bool {
    name.ends_with(".pub")
        || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name)
        || (!name.starts_with('.') && !name.ends_with(".pub") && has_pub_companion)
}

/// Format the key export success message.
pub fn format_key_exported(source_name: &str, dest: &str) -> String {
    format!("Exported {} to {}", source_name, dest)
}

/// Format the key backup success message.
pub fn format_key_backup(count: u32, dest: &str) -> String {
    format!("Backed up {} key files to {}", count, dest)
}

/// Format the key rotation complete message.
pub fn format_key_rotation_complete() -> &'static str {
    "Key rotation complete."
}

#[cfg(test)]
mod tests {
    use super::*;
    use azlin_core::models::{OsType, PowerState, ProvisioningState};
    use std::collections::HashMap;
    use std::sync::Mutex;

    /// Mock implementation of AzureOps for testing.
    struct MockAzureOps {
        subscription_id: String,
        vms: Vec<VmInfo>,
        /// Track calls for verification.
        calls: Mutex<Vec<String>>,
    }

    impl MockAzureOps {
        fn new(vms: Vec<VmInfo>) -> Self {
            Self {
                subscription_id: "test-sub-12345".to_string(),
                vms,
                calls: Mutex::new(Vec::new()),
            }
        }

        fn record(&self, call: &str) {
            self.calls.lock().unwrap().push(call.to_string());
        }

        fn call_log(&self) -> Vec<String> {
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
    fn make_test_vm(name: &str, power_state: PowerState) -> VmInfo {
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

    fn make_test_vm_stopped(name: &str) -> VmInfo {
        let mut vm = make_test_vm(name, PowerState::Deallocated);
        vm.public_ip = None;
        vm
    }

    fn make_test_vm_private(name: &str) -> VmInfo {
        let mut vm = make_test_vm(name, PowerState::Running);
        vm.public_ip = None;
        vm
    }

    // ── Show tests ──────────────────────────────────────────────────────

    #[test]
    fn test_handle_show_returns_vm() {
        let mock = MockAzureOps::new(vec![make_test_vm("dev-vm-1", PowerState::Running)]);
        let vm = handle_show(&mock, "test-rg", "dev-vm-1").unwrap();
        assert_eq!(vm.name, "dev-vm-1");
        assert_eq!(vm.power_state, PowerState::Running);
        assert!(mock.call_log().contains(&"get_vm:dev-vm-1".to_string()));
    }

    #[test]
    fn test_handle_show_not_found() {
        let mock = MockAzureOps::new(vec![]);
        let err = handle_show(&mock, "test-rg", "nonexistent").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    #[test]
    fn test_format_show_table_includes_all_fields() {
        let vm = make_test_vm("dev-vm-1", PowerState::Running);
        let output = format_show_table(&vm);
        assert!(output.contains("dev-vm-1"));
        assert!(output.contains("test-rg"));
        assert!(output.contains("eastus"));
        assert!(output.contains("Standard_D4s_v3"));
        assert!(output.contains("Running"));
        assert!(output.contains("20.1.2.3"));
        assert!(output.contains("10.0.0.4"));
        assert!(output.contains("azureuser"));
        assert!(output.contains("env: dev"));
    }

    #[test]
    fn test_format_show_table_no_optional_fields() {
        let mut vm = make_test_vm("minimal", PowerState::Stopped);
        vm.public_ip = None;
        vm.private_ip = None;
        vm.admin_username = None;
        vm.tags.clear();
        let output = format_show_table(&vm);
        assert!(output.contains("minimal"));
        assert!(!output.contains("Public IP:"));
        assert!(!output.contains("Private IP:"));
        assert!(!output.contains("Admin User:"));
        assert!(!output.contains("Tags:"));
    }

    #[test]
    fn test_format_show_json_valid() {
        let vm = make_test_vm("json-vm", PowerState::Running);
        let json_str = format_show_json(&vm).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
        assert_eq!(parsed["name"], "json-vm");
        assert_eq!(parsed["power_state"], "Running");
        assert_eq!(parsed["public_ip"], "20.1.2.3");
    }

    #[test]
    fn test_format_show_csv_has_header_and_fields() {
        let vm = make_test_vm("csv-vm", PowerState::Running);
        let csv = format_show_csv(&vm);
        assert!(csv.starts_with("Field,Value\n"));
        assert!(csv.contains("name,csv-vm"));
        assert!(csv.contains("power_state,Running"));
        assert!(csv.contains("public_ip,20.1.2.3"));
    }

    // ── Start tests ─────────────────────────────────────────────────────

    #[test]
    fn test_handle_start() {
        let mock = MockAzureOps::new(vec![]);
        let msg = handle_start(&mock, "test-rg", "my-vm").unwrap();
        assert_eq!(msg, "Started my-vm");
        assert!(mock.call_log().contains(&"start_vm:my-vm".to_string()));
    }

    // ── Stop tests ──────────────────────────────────────────────────────

    #[test]
    fn test_handle_stop_no_deallocate() {
        let mock = MockAzureOps::new(vec![]);
        let msg = handle_stop(&mock, "test-rg", "my-vm", false).unwrap();
        assert_eq!(msg, "Stopped my-vm");
        assert!(mock
            .call_log()
            .contains(&"stop_vm:my-vm:dealloc=false".to_string()));
    }

    #[test]
    fn test_handle_stop_deallocate() {
        let mock = MockAzureOps::new(vec![]);
        let msg = handle_stop(&mock, "test-rg", "my-vm", true).unwrap();
        assert_eq!(msg, "Deallocated my-vm");
        assert!(mock
            .call_log()
            .contains(&"stop_vm:my-vm:dealloc=true".to_string()));
    }

    // ── Delete tests ────────────────────────────────────────────────────

    #[test]
    fn test_handle_delete() {
        let mock = MockAzureOps::new(vec![]);
        let msg = handle_delete(&mock, "test-rg", "doomed-vm").unwrap();
        assert_eq!(msg, "Deleted doomed-vm");
        assert!(mock.call_log().contains(&"delete_vm:doomed-vm".to_string()));
    }

    // ── Tag tests ───────────────────────────────────────────────────────

    #[test]
    fn test_handle_tag_add_single() {
        let mock = MockAzureOps::new(vec![]);
        let tags = vec![("env".to_string(), "prod".to_string())];
        let msgs = handle_tag_add(&mock, "test-rg", "my-vm", &tags).unwrap();
        assert_eq!(msgs.len(), 1);
        assert!(msgs[0].contains("env=prod"));
        assert!(mock
            .call_log()
            .contains(&"add_tag:my-vm:env=prod".to_string()));
    }

    #[test]
    fn test_handle_tag_add_multiple() {
        let mock = MockAzureOps::new(vec![]);
        let tags = vec![
            ("env".to_string(), "prod".to_string()),
            ("team".to_string(), "infra".to_string()),
        ];
        let msgs = handle_tag_add(&mock, "test-rg", "my-vm", &tags).unwrap();
        assert_eq!(msgs.len(), 2);
    }

    #[test]
    fn test_handle_tag_remove() {
        let mock = MockAzureOps::new(vec![]);
        let keys = vec!["env".to_string(), "team".to_string()];
        let msgs = handle_tag_remove(&mock, "test-rg", "my-vm", &keys).unwrap();
        assert_eq!(msgs.len(), 2);
        assert!(msgs[0].contains("env"));
        assert!(msgs[1].contains("team"));
    }

    #[test]
    fn test_handle_tag_list() {
        let mock = MockAzureOps::new(vec![make_test_vm("tagged-vm", PowerState::Running)]);
        let tags = handle_tag_list(&mock, "test-rg", "tagged-vm").unwrap();
        assert_eq!(tags.get("env").unwrap(), "dev");
    }

    // ── Status tests ────────────────────────────────────────────────────

    #[test]
    fn test_handle_status_all_vms() {
        let mock = MockAzureOps::new(vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm_stopped("vm-2"),
        ]);
        let rows = handle_status(&mock, "test-rg", None).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].name, "vm-1");
        assert_eq!(rows[0].power_state, "Running");
        assert_eq!(rows[1].name, "vm-2");
        assert_eq!(rows[1].power_state, "Deallocated");
    }

    #[test]
    fn test_handle_status_single_vm() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let rows = handle_status(&mock, "test-rg", Some("vm-1")).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].name, "vm-1");
    }

    // ── List fetch tests ────────────────────────────────────────────────

    #[test]
    fn test_fetch_list_vms_with_rg() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let vms = fetch_list_vms(&mock, Some("test-rg"), false, false, None).unwrap();
        assert_eq!(vms.len(), 1);
        assert!(mock.call_log().contains(&"list_vms".to_string()));
    }

    #[test]
    fn test_fetch_list_vms_no_cache() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let _vms = fetch_list_vms(&mock, Some("test-rg"), false, true, None).unwrap();
        assert!(mock.call_log().contains(&"list_vms_no_cache".to_string()));
    }

    #[test]
    fn test_fetch_list_vms_show_all() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let _vms = fetch_list_vms(&mock, None, true, false, None).unwrap();
        assert!(mock.call_log().contains(&"list_all_vms".to_string()));
    }

    #[test]
    fn test_fetch_list_vms_show_all_no_cache() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let _vms = fetch_list_vms(&mock, None, true, true, None).unwrap();
        assert!(mock
            .call_log()
            .contains(&"list_all_vms_no_cache".to_string()));
    }

    #[test]
    fn test_fetch_list_vms_default_rg() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let vms = fetch_list_vms(&mock, None, false, false, Some("default-rg")).unwrap();
        assert_eq!(vms.len(), 1);
    }

    #[test]
    fn test_fetch_list_vms_no_rg_errors() {
        let mock = MockAzureOps::new(vec![]);
        let err = fetch_list_vms(&mock, None, false, false, None).unwrap_err();
        assert!(err.to_string().contains("No resource group"));
    }

    // ── List filter tests ───────────────────────────────────────────────

    #[test]
    fn test_filter_removes_stopped_by_default() {
        let mut vms = vec![
            make_test_vm("running-vm", PowerState::Running),
            make_test_vm_stopped("stopped-vm"),
        ];
        filter_list_vms(&mut vms, false, None, None);
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "running-vm");
    }

    #[test]
    fn test_filter_includes_stopped_when_all() {
        let mut vms = vec![
            make_test_vm("running-vm", PowerState::Running),
            make_test_vm_stopped("stopped-vm"),
        ];
        filter_list_vms(&mut vms, true, None, None);
        assert_eq!(vms.len(), 2);
    }

    #[test]
    fn test_filter_by_tag_key_value() {
        let mut vms = vec![make_test_vm("vm-1", PowerState::Running), {
            let mut vm = make_test_vm("vm-2", PowerState::Running);
            vm.tags.insert("env".to_string(), "prod".to_string());
            vm
        }];
        filter_list_vms(&mut vms, true, Some("env=prod"), None);
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "vm-2");
    }

    #[test]
    fn test_filter_by_tag_key_only() {
        let mut vms = vec![make_test_vm("vm-1", PowerState::Running), {
            let mut vm = make_test_vm("vm-2", PowerState::Running);
            vm.tags.clear();
            vm
        }];
        filter_list_vms(&mut vms, true, Some("env"), None);
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "vm-1");
    }

    #[test]
    fn test_filter_by_pattern() {
        let mut vms = vec![
            make_test_vm("dev-vm-1", PowerState::Running),
            make_test_vm("prod-vm-1", PowerState::Running),
        ];
        filter_list_vms(&mut vms, true, None, Some("dev"));
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "dev-vm-1");
    }

    #[test]
    fn test_filter_by_pattern_case_insensitive() {
        let mut vms = vec![
            make_test_vm("DEV-VM-1", PowerState::Running),
            make_test_vm("prod-vm-1", PowerState::Running),
        ];
        filter_list_vms(&mut vms, true, None, Some("dev"));
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "DEV-VM-1");
    }

    #[test]
    fn test_filter_combined() {
        let mut vms = vec![
            make_test_vm("dev-vm-1", PowerState::Running),
            make_test_vm("dev-vm-2", PowerState::Running),
            make_test_vm("prod-vm-1", PowerState::Running),
            make_test_vm_stopped("dev-vm-3"),
        ];
        // Only running + name contains "dev"
        filter_list_vms(&mut vms, false, None, Some("dev"));
        assert_eq!(vms.len(), 2);
        assert!(vms.iter().all(|v| v.name.contains("dev")));
    }

    // ── List JSON format tests ──────────────────────────────────────────

    #[test]
    fn test_format_list_json_basic() {
        let vms = vec![make_test_vm("vm-1", PowerState::Running)];
        let tmux = HashMap::new();
        let json_str = format_list_json(&vms, &tmux).unwrap();
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0]["name"], "vm-1");
        assert_eq!(parsed[0]["power_state"], "Running");
        assert_eq!(parsed[0]["ip"], "20.1.2.3");
    }

    #[test]
    fn test_format_list_json_with_tmux() {
        let vms = vec![make_test_vm("vm-1", PowerState::Running)];
        let mut tmux = HashMap::new();
        tmux.insert(
            "vm-1".to_string(),
            vec!["main".to_string(), "debug".to_string()],
        );
        let json_str = format_list_json(&vms, &tmux).unwrap();
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
        let sessions = parsed[0]["tmux_sessions"].as_array().unwrap();
        assert_eq!(sessions.len(), 2);
    }

    // ── IP display tests ────────────────────────────────────────────────

    #[test]
    fn test_format_ip_display_public() {
        assert_eq!(
            format_ip_display(Some("1.2.3.4"), Some("10.0.0.1")),
            "1.2.3.4"
        );
    }

    #[test]
    fn test_format_ip_display_private_only() {
        assert_eq!(format_ip_display(None, Some("10.0.0.1")), "(10.0.0.1)");
    }

    #[test]
    fn test_format_ip_display_none() {
        assert_eq!(format_ip_display(None, None), "-");
    }

    // ── Connect tests ───────────────────────────────────────────────────

    #[test]
    fn test_resolve_connect_explicit_vm() {
        let mock = MockAzureOps::new(vec![make_test_vm("my-vm", PowerState::Running)]);
        let target = resolve_connect_target(&mock, "test-rg", Some("my-vm"), "azureuser").unwrap();
        match target {
            ConnectTarget::Resolved {
                vm_name,
                ip,
                username,
            } => {
                assert_eq!(vm_name, "my-vm");
                assert_eq!(ip, "20.1.2.3");
                assert_eq!(username, "azureuser");
            }
            _ => panic!("Expected Resolved"),
        }
    }

    #[test]
    fn test_resolve_connect_single_running() {
        let mock = MockAzureOps::new(vec![make_test_vm("only-vm", PowerState::Running)]);
        let target = resolve_connect_target(&mock, "test-rg", None, "azureuser").unwrap();
        match target {
            ConnectTarget::Resolved { vm_name, .. } => assert_eq!(vm_name, "only-vm"),
            _ => panic!("Expected Resolved"),
        }
    }

    #[test]
    fn test_resolve_connect_multiple_running_needs_selection() {
        let mock = MockAzureOps::new(vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm("vm-2", PowerState::Running),
        ]);
        let target = resolve_connect_target(&mock, "test-rg", None, "azureuser").unwrap();
        match target {
            ConnectTarget::NeedsSelection(choices) => {
                assert_eq!(choices.len(), 2);
                assert_eq!(choices[0].0, "vm-1");
                assert_eq!(choices[1].0, "vm-2");
            }
            _ => panic!("Expected NeedsSelection"),
        }
    }

    #[test]
    fn test_resolve_connect_no_running_vms() {
        let mock = MockAzureOps::new(vec![make_test_vm_stopped("stopped-vm")]);
        let err = resolve_connect_target(&mock, "test-rg", None, "azureuser").unwrap_err();
        assert!(err.to_string().contains("No running VMs"));
    }

    #[test]
    fn test_resolve_connect_private_ip_fallback() {
        let mock = MockAzureOps::new(vec![make_test_vm_private("priv-vm")]);
        let target =
            resolve_connect_target(&mock, "test-rg", Some("priv-vm"), "azureuser").unwrap();
        match target {
            ConnectTarget::Resolved { ip, .. } => assert_eq!(ip, "10.0.0.4"),
            _ => panic!("Expected Resolved"),
        }
    }

    #[test]
    fn test_resolve_connect_no_ip() {
        let mut vm = make_test_vm("no-ip-vm", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let mock = MockAzureOps::new(vec![vm]);
        let err =
            resolve_connect_target(&mock, "test-rg", Some("no-ip-vm"), "azureuser").unwrap_err();
        assert!(err.to_string().contains("No IP address"));
    }

    // ── Health target tests ─────────────────────────────────────────────

    #[test]
    fn test_resolve_health_targets_all() {
        let mock = MockAzureOps::new(vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm_stopped("vm-2"),
        ]);
        let targets = resolve_health_targets(&mock, "test-rg", None).unwrap();
        // vm-2 has no IP after make_test_vm_stopped sets public_ip = None,
        // but still has private_ip, so it will be included
        assert!(targets.len() >= 1);
        assert_eq!(targets[0].0, "vm-1");
    }

    #[test]
    fn test_resolve_health_targets_single() {
        let mock = MockAzureOps::new(vec![make_test_vm("health-vm", PowerState::Running)]);
        let targets = resolve_health_targets(&mock, "test-rg", Some("health-vm")).unwrap();
        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].0, "health-vm");
        assert_eq!(targets[0].1, "20.1.2.3"); // public IP
        assert_eq!(targets[0].2, "azureuser");
    }

    // ── OsUpdate target tests ───────────────────────────────────────────

    #[test]
    fn test_resolve_os_update_target() {
        let mock = MockAzureOps::new(vec![make_test_vm("update-vm", PowerState::Running)]);
        let (ip, user) = resolve_os_update_target(&mock, "test-rg", "update-vm").unwrap();
        assert_eq!(ip, "20.1.2.3");
        assert_eq!(user, "azureuser");
    }

    #[test]
    fn test_resolve_os_update_target_no_ip() {
        let mut vm = make_test_vm("no-ip", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let mock = MockAzureOps::new(vec![vm]);
        let err = resolve_os_update_target(&mock, "test-rg", "no-ip").unwrap_err();
        assert!(err.to_string().contains("No IP found"));
    }

    // ── Destroy dry-run tests ───────────────────────────────────────────

    #[test]
    fn test_format_destroy_dry_run() {
        let output = format_destroy_dry_run("my-vm", "my-rg");
        assert!(output.contains("my-vm"));
        assert!(output.contains("my-rg"));
        assert!(output.contains("Dry run"));
    }

    // ── Code target tests ───────────────────────────────────────────────

    #[test]
    fn test_resolve_code_target() {
        let mock = MockAzureOps::new(vec![make_test_vm("code-vm", PowerState::Running)]);
        let (ip, user) = resolve_code_target(&mock, "test-rg", "code-vm", "azureuser").unwrap();
        assert_eq!(ip, "20.1.2.3");
        assert_eq!(user, "azureuser");
    }

    #[test]
    fn test_resolve_code_target_private_ip() {
        let mock = MockAzureOps::new(vec![make_test_vm_private("priv-vm")]);
        let (ip, _user) = resolve_code_target(&mock, "test-rg", "priv-vm", "azureuser").unwrap();
        assert_eq!(ip, "10.0.0.4");
    }

    #[test]
    fn test_resolve_code_target_no_ip() {
        let mut vm = make_test_vm("no-ip", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let mock = MockAzureOps::new(vec![vm]);
        let err = resolve_code_target(&mock, "test-rg", "no-ip", "azureuser").unwrap_err();
        assert!(err.to_string().contains("No IP address"));
    }

    #[test]
    fn test_resolve_code_target_default_user() {
        let mut vm = make_test_vm("vm", PowerState::Running);
        vm.admin_username = None;
        let mock = MockAzureOps::new(vec![vm]);
        let (_ip, user) = resolve_code_target(&mock, "test-rg", "vm", "defaultuser").unwrap();
        assert_eq!(user, "defaultuser");
    }

    // ── Batch operation tests ───────────────────────────────────────────

    #[test]
    fn test_handle_batch_stop_deallocate() {
        let mock = MockAzureOps::new(vec![]);
        let names = vec!["vm-1".to_string(), "vm-2".to_string(), "vm-3".to_string()];
        let results = handle_batch_stop(&mock, "test-rg", &names, true);
        assert_eq!(results.len(), 3);
        for (i, r) in results.iter().enumerate() {
            let msg = r.as_ref().unwrap();
            assert!(msg.starts_with("Deallocated"));
            assert!(msg.contains(&names[i]));
        }
        let log = mock.call_log();
        assert_eq!(log.len(), 3);
        assert!(log[0].contains("stop_vm:vm-1:dealloc=true"));
    }

    #[test]
    fn test_handle_batch_stop_no_deallocate() {
        let mock = MockAzureOps::new(vec![]);
        let names = vec!["vm-1".to_string()];
        let results = handle_batch_stop(&mock, "test-rg", &names, false);
        assert!(results[0].as_ref().unwrap().starts_with("Stopped"));
    }

    #[test]
    fn test_handle_batch_start() {
        let mock = MockAzureOps::new(vec![]);
        let names = vec!["vm-a".to_string(), "vm-b".to_string()];
        let results = handle_batch_start(&mock, "test-rg", &names);
        assert_eq!(results.len(), 2);
        assert!(results[0].as_ref().unwrap().contains("vm-a"));
        assert!(results[1].as_ref().unwrap().contains("vm-b"));
    }

    #[test]
    fn test_handle_batch_delete() {
        let mock = MockAzureOps::new(vec![]);
        let names = vec!["old-vm".to_string()];
        let results = handle_batch_delete(&mock, "test-rg", &names);
        assert_eq!(results.len(), 1);
        assert!(results[0].as_ref().unwrap().contains("old-vm"));
    }

    #[test]
    fn test_handle_batch_empty() {
        let mock = MockAzureOps::new(vec![]);
        let names: Vec<String> = vec![];
        let results = handle_batch_stop(&mock, "test-rg", &names, true);
        assert_eq!(results.len(), 0);
    }

    // ── Count by state tests ────────────────────────────────────────────

    #[test]
    fn test_count_by_state() {
        let vms = vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm("vm-2", PowerState::Running),
            make_test_vm_stopped("vm-3"),
            make_test_vm("vm-4", PowerState::Starting),
        ];
        let counts = count_by_state(&vms);
        assert_eq!(counts.get("Running"), Some(&2));
        assert_eq!(counts.get("Deallocated"), Some(&1));
        assert_eq!(counts.get("Starting"), Some(&1));
    }

    #[test]
    fn test_count_by_state_empty() {
        let counts = count_by_state(&[]);
        assert!(counts.is_empty());
    }

    // ── List summary tests ──────────────────────────────────────────────

    #[test]
    fn test_format_list_summary_no_tmux() {
        let s = format_list_summary(5, 0, false);
        assert_eq!(s, "Total: 5 VMs");
    }

    #[test]
    fn test_format_list_summary_with_tmux() {
        let s = format_list_summary(3, 7, false);
        assert!(s.contains("3 VMs"));
        assert!(s.contains("7 tmux sessions"));
    }

    #[test]
    fn test_format_list_summary_with_hints() {
        let s = format_list_summary(5, 0, true);
        assert!(s.contains("Hints:"));
        assert!(s.contains("azlin list -a"));
    }

    // ── Additional edge case tests ──────────────────────────────────────

    #[test]
    fn test_format_show_json_null_fields() {
        let mut vm = make_test_vm("null-fields", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        vm.admin_username = None;
        let json_str = format_show_json(&vm).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
        assert!(parsed["public_ip"].is_null());
        assert!(parsed["private_ip"].is_null());
        assert!(parsed["admin_username"].is_null());
    }

    #[test]
    fn test_format_show_csv_missing_ips() {
        let mut vm = make_test_vm("csv-null", PowerState::Stopped);
        vm.public_ip = None;
        vm.private_ip = None;
        vm.admin_username = None;
        let csv = format_show_csv(&vm);
        assert!(csv.contains("public_ip,\n"));
        assert!(csv.contains("private_ip,\n"));
        assert!(csv.contains("admin_username,\n"));
    }

    #[test]
    fn test_filter_empty_pattern() {
        let mut vms = vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm("vm-2", PowerState::Running),
        ];
        // Empty pattern should match everything
        filter_list_vms(&mut vms, true, None, Some(""));
        assert_eq!(vms.len(), 2);
    }

    #[test]
    fn test_filter_tag_key_value_no_match() {
        let mut vms = vec![make_test_vm("vm-1", PowerState::Running)];
        filter_list_vms(&mut vms, true, Some("env=prod"), None);
        assert_eq!(vms.len(), 0);
    }

    #[test]
    fn test_filter_tag_key_no_match() {
        let mut vms = vec![make_test_vm("vm-1", PowerState::Running)];
        filter_list_vms(&mut vms, true, Some("nonexistent"), None);
        assert_eq!(vms.len(), 0);
    }

    #[test]
    fn test_format_ip_display_empty_strings() {
        // Public IP takes precedence even if private is available
        assert_eq!(format_ip_display(Some("1.1.1.1"), None), "1.1.1.1");
    }

    #[test]
    fn test_handle_tag_list_not_found() {
        let mock = MockAzureOps::new(vec![]);
        let err = handle_tag_list(&mock, "test-rg", "nonexistent").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    #[test]
    fn test_handle_status_empty_rg() {
        let mock = MockAzureOps::new(vec![]);
        let rows = handle_status(&mock, "empty-rg", None).unwrap();
        assert_eq!(rows.len(), 0);
    }

    #[test]
    fn test_handle_status_row_fields() {
        let mock = MockAzureOps::new(vec![make_test_vm("detail-vm", PowerState::Running)]);
        let rows = handle_status(&mock, "test-rg", Some("detail-vm")).unwrap();
        assert_eq!(rows[0].public_ip, "20.1.2.3");
        assert_eq!(rows[0].private_ip, "10.0.0.4");
        assert_eq!(rows[0].vm_size, "Standard_D4s_v3");
        assert_eq!(rows[0].location, "eastus");
    }

    #[test]
    fn test_format_list_json_empty() {
        let json_str = format_list_json(&[], &HashMap::new()).unwrap();
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
        assert!(parsed.is_empty());
    }

    #[test]
    fn test_format_list_json_private_ip_only() {
        let vms = vec![make_test_vm_private("priv-vm")];
        let json_str = format_list_json(&vms, &HashMap::new()).unwrap();
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
        assert_eq!(parsed[0]["ip"], "(10.0.0.4)");
    }

    #[test]
    fn test_format_list_json_no_ip() {
        let mut vm = make_test_vm("no-ip", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let json_str = format_list_json(&[vm], &HashMap::new()).unwrap();
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
        assert_eq!(parsed[0]["ip"], "-");
    }

    #[test]
    fn test_resolve_connect_vm_not_found() {
        let mock = MockAzureOps::new(vec![]);
        let err =
            resolve_connect_target(&mock, "test-rg", Some("missing"), "azureuser").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    #[test]
    fn test_resolve_health_targets_no_ip_skipped() {
        let mut vm = make_test_vm("no-ip", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let mock = MockAzureOps::new(vec![vm]);
        let targets = resolve_health_targets(&mock, "test-rg", None).unwrap();
        assert_eq!(targets.len(), 0); // Skipped because no IP
    }

    #[test]
    fn test_mock_tracks_multiple_operations() {
        let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
        let _ = handle_start(&mock, "test-rg", "vm-1");
        let _ = handle_stop(&mock, "test-rg", "vm-1", false);
        let _ = handle_show(&mock, "test-rg", "vm-1");
        let log = mock.call_log();
        assert_eq!(log.len(), 3);
        assert!(log[0].contains("start_vm"));
        assert!(log[1].contains("stop_vm"));
        assert!(log[2].contains("get_vm"));
    }

    #[test]
    fn test_subscription_id_from_mock() {
        let mock = MockAzureOps::new(vec![]);
        assert_eq!(mock.subscription_id(), "test-sub-12345");
    }

    #[test]
    fn test_create_vm_via_mock() {
        use azlin_core::models::CreateVmParams;
        use std::path::PathBuf;

        let mock = MockAzureOps::new(vec![]);
        let params = CreateVmParams {
            name: "new-vm".to_string(),
            resource_group: "test-rg".to_string(),
            region: "eastus".to_string(),
            vm_size: "Standard_D4s_v3".to_string(),
            image: azlin_core::models::VmImage {
                publisher: "Canonical".to_string(),
                offer: "0001-com-ubuntu-server-jammy".to_string(),
                sku: "22_04-lts-gen2".to_string(),
                version: "latest".to_string(),
            },
            admin_username: "azureuser".to_string(),
            ssh_key_path: PathBuf::from("/tmp/fake-key.pub"),
            tags: HashMap::new(),
        };
        let vm = mock.create_vm(&params).unwrap();
        assert_eq!(vm.name, "new-vm");
        assert!(mock.call_log().contains(&"create_vm:new-vm".to_string()));
    }

    // ── List header tests ───────────────────────────────────────────

    #[test]
    fn test_build_list_headers_minimal() {
        let config = ListColumnConfig {
            show_tmux: false,
            wide: false,
            with_latency: false,
            with_health: false,
            show_procs: false,
        };
        let headers = build_list_headers(&config);
        assert_eq!(
            headers,
            vec!["Session", "OS", "Status", "IP", "Region", "CPU", "Mem"]
        );
    }

    #[test]
    fn test_build_list_headers_all_columns() {
        let config = ListColumnConfig {
            show_tmux: true,
            wide: true,
            with_latency: true,
            with_health: true,
            show_procs: true,
        };
        let headers = build_list_headers(&config);
        assert!(headers.contains(&"Tmux"));
        assert!(headers.contains(&"VM Name"));
        assert!(headers.contains(&"SKU"));
        assert!(headers.contains(&"Latency"));
        assert!(headers.contains(&"Health"));
        assert!(headers.contains(&"Top Procs"));
    }

    #[test]
    fn test_build_list_headers_wide_only() {
        let config = ListColumnConfig {
            show_tmux: false,
            wide: true,
            with_latency: false,
            with_health: false,
            show_procs: false,
        };
        let headers = build_list_headers(&config);
        assert!(headers.contains(&"VM Name"));
        assert!(headers.contains(&"SKU"));
        assert!(!headers.contains(&"Tmux"));
    }

    // ── List row tests ──────────────────────────────────────────────

    #[test]
    fn test_build_list_row_basic() {
        let vm = make_test_vm("vm-1", PowerState::Running);
        let row = build_list_row(&vm, None, None, None, None);
        assert_eq!(row.session, "main");
        assert_eq!(row.tmux, "-");
        assert_eq!(row.vm_name, "vm-1");
        assert_eq!(row.power_state, "Running");
        assert_eq!(row.ip_display, "20.1.2.3");
        assert!(row.latency.is_none());
    }

    #[test]
    fn test_build_list_row_with_tmux() {
        let vm = make_test_vm("vm-1", PowerState::Running);
        let sessions = vec!["main".to_string(), "debug".to_string()];
        let row = build_list_row(&vm, Some(&sessions), None, None, None);
        assert_eq!(row.tmux, "main, debug");
    }

    #[test]
    fn test_build_list_row_with_latency() {
        let vm = make_test_vm("vm-1", PowerState::Running);
        let row = build_list_row(&vm, None, Some(42), None, None);
        assert_eq!(row.latency, Some("42ms".to_string()));
    }

    #[test]
    fn test_build_list_row_with_health() {
        let vm = make_test_vm("vm-1", PowerState::Running);
        let row = build_list_row(&vm, None, None, Some("CPU:10% MEM:50%"), None);
        assert_eq!(row.health, Some("CPU:10% MEM:50%".to_string()));
    }

    #[test]
    fn test_build_list_row_no_session_tag() {
        let mut vm = make_test_vm("vm-1", PowerState::Running);
        vm.tags.remove("azlin-session");
        let row = build_list_row(&vm, None, None, None, None);
        assert_eq!(row.session, "-");
    }

    // ── List CSV format tests ───────────────────────────────────────

    #[test]
    fn test_format_list_csv_minimal() {
        let config = ListColumnConfig {
            show_tmux: false,
            wide: false,
            with_latency: false,
            with_health: false,
            show_procs: false,
        };
        let headers = build_list_headers(&config);
        let vm = make_test_vm("vm-1", PowerState::Running);
        let rows = vec![build_list_row(&vm, None, None, None, None)];
        let csv = format_list_csv(&headers, &rows, &config);
        assert!(csv.starts_with("Session,OS,Status,IP,Region,CPU,Mem\n"));
        assert!(csv.contains("Running"));
        assert!(csv.contains("20.1.2.3"));
    }

    #[test]
    fn test_format_list_csv_wide() {
        let config = ListColumnConfig {
            show_tmux: true,
            wide: true,
            with_latency: false,
            with_health: false,
            show_procs: false,
        };
        let headers = build_list_headers(&config);
        let vm = make_test_vm("vm-1", PowerState::Running);
        let rows = vec![build_list_row(&vm, None, None, None, None)];
        let csv = format_list_csv(&headers, &rows, &config);
        assert!(csv.contains("vm-1"));
        assert!(csv.contains("Standard_D4s_v3"));
    }

    #[test]
    fn test_format_list_csv_empty() {
        let config = ListColumnConfig {
            show_tmux: false,
            wide: false,
            with_latency: false,
            with_health: false,
            show_procs: false,
        };
        let headers = build_list_headers(&config);
        let csv = format_list_csv(&headers, &[], &config);
        let lines: Vec<&str> = csv.lines().collect();
        assert_eq!(lines.len(), 1); // Only header
    }

    // ── Env output parsing tests ────────────────────────────────────

    #[test]
    fn test_parse_env_output_basic() {
        let output = "HOME=/home/user\nPATH=/usr/bin\nSHELL=/bin/bash";
        let pairs = parse_env_output(output);
        assert_eq!(pairs.len(), 3);
        assert_eq!(pairs[0], ("HOME".to_string(), "/home/user".to_string()));
        assert_eq!(pairs[1], ("PATH".to_string(), "/usr/bin".to_string()));
    }

    #[test]
    fn test_parse_env_output_with_equals_in_value() {
        let output = "OPTS=--key=value";
        let pairs = parse_env_output(output);
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].0, "OPTS");
        assert_eq!(pairs[0].1, "--key=value");
    }

    #[test]
    fn test_parse_env_output_empty() {
        let pairs = parse_env_output("");
        assert_eq!(pairs.len(), 0);
    }

    #[test]
    fn test_parse_env_output_invalid_lines_skipped() {
        let output = "VALID=yes\ninvalid line\nALSO_VALID=true";
        let pairs = parse_env_output(output);
        assert_eq!(pairs.len(), 2);
    }

    // ── Tmux session format tests ───────────────────────────────────

    #[test]
    fn test_format_tmux_session_list_empty() {
        assert_eq!(format_tmux_session_list(&[], 3), "-");
    }

    #[test]
    fn test_format_tmux_session_list_under_max() {
        let sessions = vec!["main".to_string(), "debug".to_string()];
        assert_eq!(format_tmux_session_list(&sessions, 3), "main, debug");
    }

    #[test]
    fn test_format_tmux_session_list_over_max() {
        let sessions = vec![
            "s1".to_string(),
            "s2".to_string(),
            "s3".to_string(),
            "s4".to_string(),
        ];
        let result = format_tmux_session_list(&sessions, 2);
        assert!(result.contains("s1, s2"));
        assert!(result.contains("+2 more"));
    }

    #[test]
    fn test_format_tmux_session_list_exact_max() {
        let sessions = vec!["a".to_string(), "b".to_string()];
        assert_eq!(format_tmux_session_list(&sessions, 2), "a, b");
    }

    // ── Batch filter tests ──────────────────────────────────────────

    #[test]
    fn test_filter_vms_by_tag_no_filter() {
        let vms = vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm("vm-2", PowerState::Running),
        ];
        let filtered = filter_vms_by_tag(&vms, None);
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_filter_vms_by_tag_key_value() {
        let mut vm2 = make_test_vm("vm-2", PowerState::Running);
        vm2.tags.insert("env".to_string(), "prod".to_string());
        let vms = vec![make_test_vm("vm-1", PowerState::Running), vm2];
        let filtered = filter_vms_by_tag(&vms, Some("env=prod"));
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].name, "vm-2");
    }

    #[test]
    fn test_filter_vms_by_tag_key_only() {
        let mut vm2 = make_test_vm("vm-2", PowerState::Running);
        vm2.tags.clear();
        let vms = vec![make_test_vm("vm-1", PowerState::Running), vm2];
        let filtered = filter_vms_by_tag(&vms, Some("env"));
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].name, "vm-1");
    }

    #[test]
    fn test_filter_vms_by_tag_no_match() {
        let vms = vec![make_test_vm("vm-1", PowerState::Running)];
        let filtered = filter_vms_by_tag(&vms, Some("nonexistent=value"));
        assert_eq!(filtered.len(), 0);
    }

    // ── Orphan cost tests ───────────────────────────────────────────

    #[test]
    fn test_estimate_orphan_costs_zero() {
        let msg = estimate_orphan_costs(0, 3.65);
        assert!(msg.contains("0 orphaned"));
        assert!(msg.contains("$0.00"));
    }

    #[test]
    fn test_estimate_orphan_costs_multiple() {
        let msg = estimate_orphan_costs(5, 3.65);
        assert!(msg.contains("5 orphaned"));
        assert!(msg.contains("$18.25"));
    }

    // ── Health metric classification tests ──────────────────────────

    #[test]
    fn test_classify_percent_ok() {
        assert_eq!(classify_percent_metric(50.0, 70.0, 90.0), Severity::Ok);
    }

    #[test]
    fn test_classify_percent_warning() {
        assert_eq!(classify_percent_metric(75.0, 70.0, 90.0), Severity::Warning);
    }

    #[test]
    fn test_classify_percent_critical() {
        assert_eq!(
            classify_percent_metric(95.0, 70.0, 90.0),
            Severity::Critical
        );
    }

    #[test]
    fn test_classify_error_count_levels() {
        assert_eq!(classify_error_count(0), Severity::Ok);
        assert_eq!(classify_error_count(5), Severity::Warning);
        assert_eq!(classify_error_count(15), Severity::Critical);
    }

    #[test]
    fn test_classify_power_state_levels() {
        assert_eq!(classify_power_state("running"), Severity::Ok);
        assert_eq!(classify_power_state("stopped"), Severity::Critical);
        assert_eq!(classify_power_state("starting"), Severity::Warning);
    }

    #[test]
    fn test_classify_agent_status_levels() {
        assert_eq!(classify_agent_status("OK"), Severity::Ok);
        assert_eq!(classify_agent_status("Down"), Severity::Critical);
        assert_eq!(classify_agent_status("N/A"), Severity::Warning);
    }

    // ── Snapshot schedule formatting tests ──────────────────────────

    #[test]
    fn test_format_snapshot_status_output() {
        let info = SnapshotScheduleInfo {
            vm_name: "my-vm".to_string(),
            resource_group: "my-rg".to_string(),
            every_hours: 6,
            keep_count: 10,
            enabled: true,
            created: "2026-01-01".to_string(),
        };
        let out = format_snapshot_status(&info);
        assert!(out.contains("my-vm"));
        assert!(out.contains("every 6 hours"));
    }

    #[test]
    fn test_format_snapshot_no_schedule_output() {
        let out = format_snapshot_no_schedule("missing-vm");
        assert!(out.contains("no schedule configured"));
    }

    // ── Cost summary formatting tests ───────────────────────────────

    fn make_cost_summary() -> azlin_core::models::CostSummary {
        azlin_core::models::CostSummary {
            total_cost: 123.45,
            currency: "USD".to_string(),
            period_start: chrono::NaiveDate::from_ymd_opt(2026, 1, 1)
                .unwrap()
                .and_hms_opt(0, 0, 0)
                .unwrap()
                .and_utc(),
            period_end: chrono::NaiveDate::from_ymd_opt(2026, 1, 31)
                .unwrap()
                .and_hms_opt(0, 0, 0)
                .unwrap()
                .and_utc(),
            by_vm: vec![],
        }
    }

    #[test]
    fn test_cost_summary_table() {
        let s = make_cost_summary();
        let out = format_cost_summary(&s, "table", &None, &None, false, false);
        assert!(out.contains("$123.45"));
        assert!(out.contains("USD"));
    }

    #[test]
    fn test_cost_summary_json() {
        let s = make_cost_summary();
        let out = format_cost_summary(&s, "json", &None, &None, false, false);
        let _parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
    }

    #[test]
    fn test_cost_summary_csv() {
        let s = make_cost_summary();
        let out = format_cost_summary(&s, "csv", &None, &None, false, false);
        assert!(out.starts_with("Total Cost,Currency"));
    }

    #[test]
    fn test_cost_summary_with_estimate() {
        let s = make_cost_summary();
        let out = format_cost_summary(&s, "table", &None, &None, true, false);
        assert!(out.contains("Estimate:"));
    }

    #[test]
    fn test_cost_summary_with_filters() {
        let s = make_cost_summary();
        let out = format_cost_summary(
            &s,
            "table",
            &Some("2026-01-01".to_string()),
            &Some("2026-01-15".to_string()),
            false,
            false,
        );
        assert!(out.contains("From filter:"));
        assert!(out.contains("To filter:"));
    }

    #[test]
    fn test_cost_summary_by_vm() {
        let mut s = make_cost_summary();
        s.by_vm = vec![azlin_core::models::VmCost {
            vm_name: "vm-1".to_string(),
            cost: 50.0,
            currency: "USD".to_string(),
        }];
        let out = format_cost_summary(&s, "table", &None, &None, false, true);
        assert!(out.contains("vm-1"));
        assert!(out.contains("$50.00"));
    }

    #[test]
    fn test_cost_summary_by_vm_empty() {
        let s = make_cost_summary();
        let out = format_cost_summary(&s, "table", &None, &None, false, true);
        assert!(out.contains("No per-VM cost data"));
    }

    // ── Cost data parsing tests ─────────────────────────────────────

    #[test]
    fn test_parse_cost_history_rows_basic() {
        let data = serde_json::json!({"rows": [[42.5, "2026-01-01"]]});
        let rows = parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].1, "$42.50");
    }

    #[test]
    fn test_parse_cost_history_rows_empty() {
        let data = serde_json::json!({"rows": []});
        assert!(parse_cost_history_rows(&data).is_empty());
    }

    #[test]
    fn test_parse_recommendation_rows_basic() {
        let data = serde_json::json!([{
            "category": "Cost",
            "impact": "High",
            "shortDescription": {"problem": "Unused VM"}
        }]);
        let rows = parse_recommendation_rows(&data);
        assert_eq!(rows[0].0, "Cost");
        assert_eq!(rows[0].2, "Unused VM");
    }

    #[test]
    fn test_parse_recommendation_rows_empty() {
        assert!(parse_recommendation_rows(&serde_json::json!([])).is_empty());
    }

    #[test]
    fn test_parse_cost_action_rows_basic() {
        let data = serde_json::json!([{
            "impactedField": "VMs",
            "impact": "Medium",
            "shortDescription": {"problem": "Resize"}
        }]);
        let rows = parse_cost_action_rows(&data);
        assert_eq!(rows[0].0, "VMs");
    }

    // ── Create VM result formatting tests ───────────────────────────

    #[test]
    fn test_build_create_vm_rows_basic() {
        let vm = make_test_vm("new-vm", PowerState::Running);
        let rows = build_create_vm_rows(&vm, "rg", "Standard_D4s_v3", "eastus");
        assert!(rows.iter().any(|(k, v)| k == "Name" && v == "new-vm"));
        assert!(rows.iter().any(|(k, _)| k == "Public IP"));
    }

    #[test]
    fn test_build_create_vm_rows_no_ips() {
        let mut vm = make_test_vm("bare", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let rows = build_create_vm_rows(&vm, "rg", "D2s", "westus");
        assert_eq!(rows.len(), 5);
    }

    // ── Doit VM filter tests ────────────────────────────────────────

    #[test]
    fn test_filter_doit_vms_with_tag() {
        let mut vm1 = make_test_vm("doit-vm", PowerState::Running);
        vm1.tags
            .insert("created_by".to_string(), "azlin-doit".to_string());
        let vm2 = make_test_vm("regular-vm", PowerState::Running);
        let vms = vec![vm1, vm2];
        let filtered = filter_doit_vms(&vms, None);
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].name, "doit-vm");
    }

    #[test]
    fn test_filter_doit_vms_by_username() {
        let mut vm1 = make_test_vm("doit-1", PowerState::Running);
        vm1.tags
            .insert("created_by".to_string(), "azlin-doit".to_string());
        vm1.admin_username = Some("alice".to_string());
        let mut vm2 = make_test_vm("doit-2", PowerState::Running);
        vm2.tags
            .insert("created_by".to_string(), "azlin-doit".to_string());
        vm2.admin_username = Some("bob".to_string());
        let vms = vec![vm1, vm2];
        let filtered = filter_doit_vms(&vms, Some("alice"));
        assert_eq!(filtered.len(), 1);
    }

    #[test]
    fn test_filter_doit_vms_none_match() {
        let vms = vec![make_test_vm("regular-vm", PowerState::Running)];
        let filtered = filter_doit_vms(&vms, None);
        assert!(filtered.is_empty());
    }

    // ── SSH args building tests ─────────────────────────────────────

    #[test]
    fn test_ssh_connect_args_basic() {
        let args = build_ssh_connect_args("user", "1.2.3.4", None, None, &[]).unwrap();
        assert!(args.contains(&"user@1.2.3.4".to_string()));
    }

    #[test]
    fn test_ssh_connect_args_with_key() {
        let args = build_ssh_connect_args("user", "1.2.3.4", Some("/tmp/key"), None, &[]).unwrap();
        assert!(args.contains(&"-i".to_string()));
    }

    #[test]
    fn test_ssh_connect_args_with_tmux() {
        let args = build_ssh_connect_args("user", "1.2.3.4", None, Some("azlin"), &[]).unwrap();
        assert!(args.contains(&"-t".to_string()));
    }

    #[test]
    fn test_ssh_connect_args_invalid_tmux() {
        let err =
            build_ssh_connect_args("user", "1.2.3.4", None, Some("bad;name"), &[]).unwrap_err();
        assert!(err.to_string().contains("Invalid tmux"));
    }

    // ── VM picker formatting tests ──────────────────────────────────

    #[test]
    fn test_format_vm_picker_basic() {
        let vms = vec![
            make_test_vm("vm-1", PowerState::Running),
            make_test_vm("vm-2", PowerState::Running),
        ];
        let out = format_vm_picker(&vms);
        assert!(out.contains("[1] vm-1"));
        assert!(out.contains("[2] vm-2"));
    }

    #[test]
    fn test_format_vm_picker_no_ip() {
        let mut vm = make_test_vm("no-ip", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let out = format_vm_picker(&[vm]);
        assert!(out.contains("no-ip (-)"));
    }

    // ── Help handler tests ──────────────────────────────────────────

    #[test]
    fn test_build_extended_help_with_command() {
        let out = build_extended_help(Some("list"));
        assert!(out.contains("azlin list"));
        assert!(out.contains("Extended help"));
        assert!(out.contains("--help"));
    }

    #[test]
    fn test_build_extended_help_general() {
        let out = build_extended_help(None);
        assert!(out.contains("azlin"));
        assert!(out.contains("Azure VM fleet management CLI"));
        assert!(out.contains("<command> --help"));
        assert!(out.contains("completions bash"));
        assert!(out.contains("completions zsh"));
        assert!(out.contains("completions fish"));
    }

    // ── List footer tests ───────────────────────────────────────────

    #[test]
    fn test_format_list_footer_no_tmux() {
        let out = format_list_footer(5, 0);
        assert_eq!(out, "Total: 5 VMs");
        assert!(!out.contains("tmux"));
    }

    #[test]
    fn test_format_list_footer_with_tmux() {
        let out = format_list_footer(3, 7);
        assert!(out.contains("3 VMs"));
        assert!(out.contains("7 tmux sessions"));
    }

    #[test]
    fn test_build_list_json_basic() {
        let vms = vec![make_test_vm("vm-1", PowerState::Running)];
        let tmux = HashMap::from([("vm-1".to_string(), vec!["main".to_string()])]);
        let json = build_list_json(&vms, &tmux);
        let arr = json.as_array().unwrap();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["name"], "vm-1");
        assert_eq!(arr[0]["tmux_sessions"][0], "main");
    }

    #[test]
    fn test_build_list_json_empty() {
        let json = build_list_json(&[], &HashMap::new());
        assert!(json.as_array().unwrap().is_empty());
    }

    // ── Snapshot formatting tests ───────────────────────────────────

    #[test]
    fn test_format_snapshot_rows_basic() {
        let snaps = vec![serde_json::json!({
            "name": "vm1_snapshot_20260301",
            "diskSizeGb": 128,
            "timeCreated": "2026-03-01T10:00:00Z",
            "provisioningState": "Succeeded"
        })];
        let rows = format_snapshot_rows(&snaps);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "vm1_snapshot_20260301");
        assert_eq!(rows[0].1, "128");
        assert!(rows[0].2.contains("2026-03-01"));
        assert_eq!(rows[0].3, "Succeeded");
    }

    #[test]
    fn test_format_snapshot_rows_empty() {
        assert!(format_snapshot_rows(&[]).is_empty());
    }

    #[test]
    fn test_build_snapshot_name() {
        let name = build_snapshot_name("my-vm", "20260301_120000");
        assert_eq!(name, "my-vm_snapshot_20260301_120000");
    }

    #[test]
    fn test_build_snapshot_schedule_info() {
        let info = build_snapshot_schedule_info("vm-1", "rg-1", 6, 10, true, "2026-03-01");
        assert_eq!(info.vm_name, "vm-1");
        assert_eq!(info.every_hours, 6);
        assert_eq!(info.keep_count, 10);
        assert!(info.enabled);
    }

    // ── Storage formatting tests ────────────────────────────────────

    #[test]
    fn test_format_storage_status_basic() {
        let acct = serde_json::json!({
            "name": "mystorage",
            "location": "westus2",
            "kind": "FileStorage",
            "sku": {"name": "Premium_LRS"},
            "provisioningState": "Succeeded",
            "primaryEndpoints": {"file": "https://mystorage.file.core.windows.net/"}
        });
        let rows = format_storage_status(&acct);
        assert_eq!(rows.len(), 6);
        assert_eq!(rows[0], ("Name".to_string(), "mystorage".to_string()));
        assert_eq!(rows[1], ("Location".to_string(), "westus2".to_string()));
        assert!(rows[5].1.contains("mystorage.file.core.windows.net"));
    }

    #[test]
    fn test_format_storage_status_missing_fields() {
        let acct = serde_json::json!({});
        let rows = format_storage_status(&acct);
        assert_eq!(rows.len(), 6);
        // All values should be "-"
        for (_, v) in &rows {
            assert_eq!(v, "-");
        }
    }

    #[test]
    fn test_build_nfs_mount_command() {
        let cmd = build_nfs_mount_command("mystorage", "/mnt/data");
        assert!(cmd.contains("sudo mkdir -p /mnt/data"));
        assert!(cmd.contains("mystorage.file.core.windows.net"));
        assert!(cmd.contains("mount -t nfs"));
    }

    #[test]
    fn test_build_cifs_mount_options() {
        let opts = build_cifs_mount_options("/home/user/.azlin/.mount_creds_acct");
        assert!(opts.contains("vers=3.0"));
        assert!(opts.contains("credentials=/home/user/.azlin/.mount_creds_acct"));
    }

    #[test]
    fn test_build_azure_files_unc() {
        let unc = build_azure_files_unc("mystorage", "myshare");
        assert_eq!(unc, "//mystorage.file.core.windows.net/myshare");
    }

    // ── Cost dashboard tests ────────────────────────────────────────

    #[test]
    fn test_format_cost_dashboard() {
        let out = format_cost_dashboard("my-rg", 123.45, "USD", "2026-03-01", "2026-03-07");
        assert!(out.contains("Cost Dashboard for 'my-rg':"));
        assert!(out.contains("$123.45 USD"));
        assert!(out.contains("2026-03-01 to 2026-03-07"));
    }

    #[test]
    fn test_build_cost_management_scope() {
        let scope = build_cost_management_scope("sub-123", "my-rg");
        assert_eq!(scope, "/subscriptions/sub-123/resourceGroups/my-rg");
    }

    #[test]
    fn test_build_budget_name() {
        assert_eq!(build_budget_name("my-rg"), "azlin-budget-my-rg");
    }

    #[test]
    fn test_format_budget_created() {
        let msg = format_budget_created(100.0, "my-rg", 80);
        assert!(msg.contains("$100.00/month"));
        assert!(msg.contains("my-rg"));
        assert!(msg.contains("80%"));
    }

    #[test]
    fn test_build_cost_history_dates() {
        let (start, end) = build_cost_history_dates(7);
        // Both should be valid date strings with T separator
        assert!(start.contains("T00:00:00"));
        assert!(end.contains("T23:59:59"));
    }

    // ── Cleanup / orphan classification tests ───────────────────────

    #[test]
    fn test_classify_orphaned_nics_finds_unattached() {
        let nics = vec![
            serde_json::json!({"name": "nic-orphan", "resourceGroup": "rg1", "virtualMachine": null}),
            serde_json::json!({"name": "nic-attached", "resourceGroup": "rg1", "virtualMachine": {"id": "/sub/vm"}}),
        ];
        let orphans = classify_orphaned_nics(&nics);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "nic-orphan");
        assert_eq!(orphans[0].resource_type, "NIC");
    }

    #[test]
    fn test_classify_orphaned_nics_empty() {
        assert!(classify_orphaned_nics(&[]).is_empty());
    }

    #[test]
    fn test_classify_orphaned_ips_finds_unattached() {
        let ips = vec![
            serde_json::json!({"name": "ip-orphan", "resourceGroup": "rg1", "ipConfiguration": null}),
            serde_json::json!({"name": "ip-attached", "resourceGroup": "rg1", "ipConfiguration": {"id": "/sub/nic"}}),
        ];
        let orphans = classify_orphaned_ips(&ips, 3.65);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "ip-orphan");
        assert_eq!(orphans[0].resource_type, "Public IP");
        assert!((orphans[0].estimated_monthly_cost - 3.65).abs() < 0.01);
    }

    #[test]
    fn test_classify_orphaned_ips_empty() {
        assert!(classify_orphaned_ips(&[], 3.65).is_empty());
    }

    #[test]
    fn test_classify_orphaned_nsgs_finds_unattached() {
        let nsgs = vec![
            serde_json::json!({"name": "nsg-orphan", "resourceGroup": "rg1", "networkInterfaces": [], "subnets": []}),
            serde_json::json!({"name": "nsg-used", "resourceGroup": "rg1", "networkInterfaces": [{"id": "/sub/nic"}], "subnets": []}),
        ];
        let orphans = classify_orphaned_nsgs(&nsgs);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "nsg-orphan");
        assert_eq!(orphans[0].resource_type, "NSG");
    }

    #[test]
    fn test_classify_orphaned_nsgs_with_subnets() {
        let nsgs = vec![
            serde_json::json!({"name": "nsg-subnet", "resourceGroup": "rg1", "networkInterfaces": [], "subnets": [{"id": "/sub/subnet"}]}),
        ];
        let orphans = classify_orphaned_nsgs(&nsgs);
        assert!(orphans.is_empty());
    }

    #[test]
    fn test_build_cleanup_plan_dry_run() {
        let resources = vec![OrphanedResourceInfo {
            name: "nic-1".to_string(),
            resource_type: "NIC".to_string(),
            resource_group: "rg1".to_string(),
            estimated_monthly_cost: 0.0,
        }];
        let plan = build_cleanup_plan(&resources, true);
        assert_eq!(plan.len(), 1);
        assert_eq!(plan[0].action, "would delete");
        assert_eq!(plan[0].resource_name, "nic-1");
    }

    #[test]
    fn test_build_cleanup_plan_real() {
        let resources = vec![
            OrphanedResourceInfo {
                name: "disk-1".to_string(),
                resource_type: "Disk".to_string(),
                resource_group: "rg1".to_string(),
                estimated_monthly_cost: 5.12,
            },
            OrphanedResourceInfo {
                name: "ip-1".to_string(),
                resource_type: "Public IP".to_string(),
                resource_group: "rg1".to_string(),
                estimated_monthly_cost: 3.65,
            },
        ];
        let plan = build_cleanup_plan(&resources, false);
        assert_eq!(plan.len(), 2);
        assert_eq!(plan[0].action, "delete");
        assert_eq!(plan[1].action, "delete");
    }

    #[test]
    fn test_format_orphan_report_empty() {
        let out = format_orphan_report(&[]);
        assert!(out.contains("No orphaned resources found"));
    }

    #[test]
    fn test_format_orphan_report_with_resources() {
        let resources = vec![
            OrphanedResourceInfo {
                name: "disk-old".to_string(),
                resource_type: "Disk".to_string(),
                resource_group: "rg1".to_string(),
                estimated_monthly_cost: 5.12,
            },
            OrphanedResourceInfo {
                name: "ip-old".to_string(),
                resource_type: "Public IP".to_string(),
                resource_group: "rg1".to_string(),
                estimated_monthly_cost: 3.65,
            },
        ];
        let out = format_orphan_report(&resources);
        assert!(out.contains("2 orphaned resource(s)"));
        assert!(out.contains("disk-old"));
        assert!(out.contains("ip-old"));
        assert!(out.contains("$8.77/month"));
    }

    // ── Snapshot handler tests ──────────────────────────────────────────

    #[test]
    fn test_build_snapshot_enable_output() {
        let out = build_snapshot_enable_output("dev-vm-1", "test-rg", 6, 3);
        assert!(out.contains("dev-vm-1"));
        assert!(out.contains("every 6h"));
        assert!(out.contains("keep 3"));
    }

    #[test]
    fn test_build_snapshot_disable_output_had_schedule() {
        let out = build_snapshot_disable_output("dev-vm-1", true);
        assert!(out.contains("disabled"));
        assert!(out.contains("dev-vm-1"));
    }

    #[test]
    fn test_build_snapshot_disable_output_no_schedule() {
        let out = build_snapshot_disable_output("dev-vm-1", false);
        assert!(out.contains("No schedule configured"));
    }

    #[test]
    fn test_check_snapshot_sync_needed_recent() {
        let now = chrono::Utc::now();
        let recent = now - chrono::Duration::hours(2);
        let snap = serde_json::json!({
            "timeCreated": recent.to_rfc3339(),
        });
        let snaps = vec![&snap];
        let (needs, msg) = check_snapshot_sync_needed(&snaps, "vm1", 6, now);
        assert!(!needs);
        assert!(msg.unwrap().contains("skipping"));
    }

    #[test]
    fn test_check_snapshot_sync_needed_old() {
        let now = chrono::Utc::now();
        let old = now - chrono::Duration::hours(12);
        let snap = serde_json::json!({
            "timeCreated": old.to_rfc3339(),
        });
        let snaps = vec![&snap];
        let (needs, msg) = check_snapshot_sync_needed(&snaps, "vm1", 6, now);
        assert!(needs);
        assert!(msg.is_none());
    }

    #[test]
    fn test_check_snapshot_sync_needed_empty() {
        let now = chrono::Utc::now();
        let empty: Vec<&serde_json::Value> = vec![];
        let (needs, msg) = check_snapshot_sync_needed(&empty, "vm1", 6, now);
        assert!(needs);
        assert!(msg.is_none());
    }

    #[test]
    fn test_format_snapshot_sync_complete_single() {
        let out = format_snapshot_sync_complete(Some("vm1"));
        assert!(out.contains("vm1"));
    }

    #[test]
    fn test_format_snapshot_sync_complete_all() {
        let out = format_snapshot_sync_complete(None);
        assert!(out.contains("all VMs"));
    }

    // ── Storage handler tests ───────────────────────────────────────────

    #[test]
    fn test_format_storage_created() {
        let out = format_storage_created("mystorage", 100, "premium");
        assert!(out.contains("mystorage"));
        assert!(out.contains("100 GB"));
        assert!(out.contains("premium"));
    }

    #[test]
    fn test_format_storage_deleted() {
        let out = format_storage_deleted("mystorage");
        assert!(out.contains("Deleted"));
        assert!(out.contains("mystorage"));
    }

    #[test]
    fn test_format_storage_mounted() {
        let out = format_storage_mounted("share1", "vm1", "/mnt/share1");
        assert!(out.contains("share1"));
        assert!(out.contains("vm1"));
        assert!(out.contains("/mnt/share1"));
    }

    #[test]
    fn test_validate_storage_name_valid() {
        assert!(validate_storage_name("my-storage-1").is_ok());
    }

    #[test]
    fn test_validate_storage_name_invalid() {
        assert!(validate_storage_name("my_storage!").is_err());
    }

    #[test]
    fn test_default_nfs_mount_point() {
        assert_eq!(default_nfs_mount_point("share1"), "/mnt/share1");
    }

    // ── Costs handler tests ─────────────────────────────────────────────

    #[test]
    fn test_format_cost_history_header() {
        let out = format_cost_history_header("my-rg", 30);
        assert!(out.contains("my-rg"));
        assert!(out.contains("30 days"));
    }

    #[test]
    fn test_format_no_recommendations() {
        let out = format_no_recommendations("my-rg", "High");
        assert!(out.contains("my-rg"));
        assert!(out.contains("High"));
    }

    #[test]
    fn test_format_no_budgets() {
        let out = format_no_budgets("my-rg");
        assert!(out.contains("No budgets"));
        assert!(out.contains("my-rg"));
    }

    #[test]
    fn test_format_budget_deleted_msg() {
        let out = format_budget_deleted("my-rg");
        assert!(out.contains("Budget deleted"));
    }

    #[test]
    fn test_format_cost_actions_header_dry_run() {
        let out = format_cost_actions_header("apply", "my-rg", true);
        assert!(out.contains("Would apply"));
    }

    #[test]
    fn test_format_cost_actions_header_live() {
        let out = format_cost_actions_header("apply", "my-rg", false);
        assert!(out.contains("Cost actions (apply)"));
    }

    #[test]
    fn test_build_advisor_args_no_priority() {
        let args = build_advisor_args("my-rg", None);
        assert!(args.contains(&"my-rg".to_string()));
        assert!(!args.contains(&"--query".to_string()));
    }

    #[test]
    fn test_build_advisor_args_with_priority() {
        let args = build_advisor_args("my-rg", Some("High"));
        assert!(args.contains(&"--query".to_string()));
        let query_idx = args.iter().position(|a| a == "--query").unwrap();
        assert!(args[query_idx + 1].contains("High"));
    }

    // ── Cleanup/orphan tests ────────────────────────────────────────────

    #[test]
    fn test_find_orphaned_nics_mixed() {
        let nics = vec![
            serde_json::json!({
                "name": "orphan-nic",
                "resourceGroup": "rg1",
                "virtualMachine": null
            }),
            serde_json::json!({
                "name": "attached-nic",
                "resourceGroup": "rg1",
                "virtualMachine": {"id": "/some/vm"}
            }),
        ];
        let orphans = find_orphaned_nics(&nics);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "orphan-nic");
        assert_eq!(orphans[0].resource_type, "NetworkInterface");
    }

    #[test]
    fn test_find_orphaned_nics_empty() {
        let orphans = find_orphaned_nics(&[]);
        assert!(orphans.is_empty());
    }

    #[test]
    fn test_find_orphaned_public_ips() {
        let ips = vec![
            serde_json::json!({
                "name": "orphan-ip",
                "resourceGroup": "rg1",
                "ipConfiguration": null
            }),
            serde_json::json!({
                "name": "used-ip",
                "resourceGroup": "rg1",
                "ipConfiguration": {"id": "/some/config"}
            }),
        ];
        let orphans = find_orphaned_public_ips(&ips, 3.65);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "orphan-ip");
        assert_eq!(orphans[0].estimated_monthly_cost, 3.65);
    }

    #[test]
    fn test_find_orphaned_nsgs() {
        let nsgs = vec![
            serde_json::json!({
                "name": "orphan-nsg",
                "resourceGroup": "rg1",
                "networkInterfaces": [],
                "subnets": []
            }),
            serde_json::json!({
                "name": "used-nsg",
                "resourceGroup": "rg1",
                "networkInterfaces": [{"id": "/some/nic"}],
                "subnets": []
            }),
        ];
        let orphans = find_orphaned_nsgs(&nsgs);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "orphan-nsg");
        assert_eq!(orphans[0].resource_type, "NetworkSecurityGroup");
    }

    #[test]
    fn test_find_orphaned_nsgs_with_subnets() {
        let nsgs = vec![serde_json::json!({
            "name": "subnet-nsg",
            "resourceGroup": "rg1",
            "networkInterfaces": [],
            "subnets": [{"id": "/some/subnet"}]
        })];
        let orphans = find_orphaned_nsgs(&nsgs);
        assert!(orphans.is_empty());
    }

    #[test]
    fn test_format_cleanup_complete() {
        let out = format_cleanup_complete(3, 5);
        assert!(out.contains("3/5"));
    }

    #[test]
    fn test_format_cleanup_scan_header_dry_run() {
        let out = format_cleanup_scan_header("rg1", 30, true);
        assert!(out.contains("Dry run"));
        assert!(out.contains("rg1"));
        assert!(out.contains("30 days"));
    }

    #[test]
    fn test_format_cleanup_scan_header_live() {
        let out = format_cleanup_scan_header("rg1", 30, false);
        assert!(!out.contains("Dry run"));
    }

    // ── Autopilot handler tests ─────────────────────────────────────────

    #[test]
    fn test_build_autopilot_config() {
        let val = build_autopilot_config(Some(100), "conservative", 30, 10, "2026-01-01T00:00:00Z");
        let t = val.as_table().unwrap();
        assert_eq!(t["enabled"].as_bool(), Some(true));
        assert_eq!(t["budget"].as_integer(), Some(100));
        assert_eq!(t["strategy"].as_str(), Some("conservative"));
        assert_eq!(t["idle_threshold_minutes"].as_integer(), Some(30));
        assert_eq!(t["cpu_threshold_percent"].as_integer(), Some(10));
    }

    #[test]
    fn test_build_autopilot_config_no_budget() {
        let val = build_autopilot_config(None, "aggressive", 60, 5, "2026-01-01T00:00:00Z");
        let t = val.as_table().unwrap();
        assert!(!t.contains_key("budget"));
    }

    #[test]
    fn test_format_autopilot_enabled_with_budget() {
        let out = format_autopilot_enabled(Some(200), "conservative", 30, 10);
        assert!(out.contains("$200/month"));
        assert!(out.contains("conservative"));
        assert!(out.contains("30 min"));
        assert!(out.contains("10%"));
    }

    #[test]
    fn test_format_autopilot_enabled_no_budget() {
        let out = format_autopilot_enabled(None, "aggressive", 60, 5);
        assert!(!out.contains("Budget"));
    }

    #[test]
    fn test_format_autopilot_status_enabled() {
        let val: toml::Value = toml::from_str(
            r#"
            enabled = true
            strategy = "conservative"
            idle_threshold_minutes = 30
            "#,
        )
        .unwrap();
        let out = format_autopilot_status(Some(&val));
        assert!(out.contains("ENABLED"));
        assert!(out.contains("conservative"));
    }

    #[test]
    fn test_format_autopilot_status_disabled() {
        let val: toml::Value = toml::from_str("enabled = false").unwrap();
        let out = format_autopilot_status(Some(&val));
        assert!(out.contains("DISABLED"));
    }

    #[test]
    fn test_format_autopilot_status_none() {
        let out = format_autopilot_status(None);
        assert!(out.contains("not configured"));
    }

    #[test]
    fn test_parse_autopilot_thresholds_with_config() {
        let val: toml::Value = toml::from_str(
            r#"
            idle_threshold_minutes = 45
            cost_limit_usd = 50.0
            "#,
        )
        .unwrap();
        let (thresh, limit) = parse_autopilot_thresholds(Some(&val));
        assert_eq!(thresh, 45);
        assert!((limit - 50.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_parse_autopilot_thresholds_defaults() {
        let (thresh, limit) = parse_autopilot_thresholds(None);
        assert_eq!(thresh, 30);
        assert!((limit - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_classify_autopilot_vm_idle() {
        let action = classify_autopilot_vm(2.0, 3600.0, 30);
        assert_eq!(action, Some("deallocate".to_string()));
    }

    #[test]
    fn test_classify_autopilot_vm_active() {
        let action = classify_autopilot_vm(50.0, 3600.0, 30);
        assert!(action.is_none());
    }

    #[test]
    fn test_classify_autopilot_vm_low_cpu_short_uptime() {
        // Low CPU but uptime below threshold — should NOT recommend action
        let action = classify_autopilot_vm(2.0, 60.0, 30);
        assert!(action.is_none());
    }

    #[test]
    fn test_format_autopilot_dry_run() {
        let actions = vec![
            ("vm1".to_string(), "deallocate".to_string()),
            ("vm2".to_string(), "deallocate".to_string()),
        ];
        let out = format_autopilot_dry_run(&actions);
        assert!(out.contains("2 action(s)"));
        assert!(out.contains("vm1"));
        assert!(out.contains("vm2"));
    }

    // ── Context handler tests ───────────────────────────────────────────

    #[test]
    fn test_format_context_list_table() {
        let contexts = vec![
            ("default".to_string(), true),
            ("staging".to_string(), false),
        ];
        let out = format_context_list_table(&contexts);
        assert!(out.contains("* default"));
        assert!(out.contains("  staging"));
    }

    #[test]
    fn test_format_context_show_with_content() {
        let out = format_context_show("prod", Some("subscription_id = \"abc\""));
        assert!(out.contains("Current context: prod"));
        assert!(out.contains("subscription_id"));
    }

    #[test]
    fn test_format_context_show_no_content() {
        let out = format_context_show("prod", None);
        assert!(out.contains("Current context: prod"));
        assert!(!out.contains("subscription_id"));
    }

    #[test]
    fn test_format_context_messages() {
        assert!(format_context_switched("prod").contains("prod"));
        assert!(format_context_created("staging").contains("staging"));
        assert!(format_context_deleted("old").contains("old"));
        assert!(format_context_renamed("a", "b").contains("a"));
        assert!(format_context_renamed("a", "b").contains("b"));
    }

    // ── Keys handler tests ──────────────────────────────────────────────

    #[test]
    fn test_build_key_list_row() {
        let row = build_key_list_row("id_ed25519.pub", 256, "2026-01-01 00:00");
        assert_eq!(row[0], "id_ed25519.pub");
        assert_eq!(row[1], "ed25519");
        assert_eq!(row[2], "256");
        assert_eq!(row[3], "2026-01-01 00:00");
    }

    #[test]
    fn test_build_key_list_row_rsa() {
        let row = build_key_list_row("id_rsa", 1024, "2026-01-01 00:00");
        assert_eq!(row[1], "rsa");
    }

    #[test]
    fn test_is_ssh_key_file_pub() {
        assert!(is_ssh_key_file("id_ed25519.pub", false));
    }

    #[test]
    fn test_is_ssh_key_file_private() {
        assert!(is_ssh_key_file("id_rsa", false));
    }

    #[test]
    fn test_is_ssh_key_file_with_companion() {
        assert!(is_ssh_key_file("my_custom_key", true));
    }

    #[test]
    fn test_is_ssh_key_file_hidden() {
        // Hidden files are not SSH keys
        assert!(!is_ssh_key_file(".config", true));
    }

    #[test]
    fn test_format_key_exported() {
        let out = format_key_exported("id_ed25519.pub", "/tmp/mykey.pub");
        assert!(out.contains("id_ed25519.pub"));
        assert!(out.contains("/tmp/mykey.pub"));
    }

    #[test]
    fn test_format_key_backup() {
        let out = format_key_backup(3, "/tmp/backup");
        assert!(out.contains("3 key files"));
        assert!(out.contains("/tmp/backup"));
    }

    // ── Severity/classification tests ──────────────────────────────────

    #[test]
    fn test_classify_percent_metric_ok() {
        assert_eq!(classify_percent_metric(30.0, 70.0, 90.0), Severity::Ok);
    }

    #[test]
    fn test_classify_percent_metric_warning() {
        assert_eq!(classify_percent_metric(75.0, 70.0, 90.0), Severity::Warning);
    }

    #[test]
    fn test_classify_percent_metric_critical() {
        assert_eq!(
            classify_percent_metric(95.0, 70.0, 90.0),
            Severity::Critical
        );
    }

    #[test]
    fn test_classify_error_count_zero() {
        assert_eq!(classify_error_count(0), Severity::Ok);
    }

    #[test]
    fn test_classify_error_count_low() {
        assert_eq!(classify_error_count(5), Severity::Warning);
    }

    #[test]
    fn test_classify_error_count_high() {
        assert_eq!(classify_error_count(15), Severity::Critical);
    }

    #[test]
    fn test_classify_power_state_running() {
        assert_eq!(classify_power_state("Running"), Severity::Ok);
    }

    #[test]
    fn test_classify_power_state_stopped() {
        assert_eq!(classify_power_state("stopped"), Severity::Critical);
    }

    #[test]
    fn test_classify_power_state_deallocated() {
        assert_eq!(classify_power_state("deallocated"), Severity::Critical);
    }

    #[test]
    fn test_classify_power_state_starting() {
        assert_eq!(classify_power_state("Starting"), Severity::Warning);
    }

    #[test]
    fn test_classify_agent_status_ok() {
        assert_eq!(classify_agent_status("OK"), Severity::Ok);
    }

    #[test]
    fn test_classify_agent_status_down() {
        assert_eq!(classify_agent_status("Down"), Severity::Critical);
    }

    #[test]
    fn test_classify_agent_status_unknown() {
        assert_eq!(classify_agent_status("Unknown"), Severity::Warning);
    }

    // ── Cost summary formatting tests ───────────────────────────────────

    #[test]
    fn test_format_cost_summary_json() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let out = format_cost_summary(&summary, "json", &None, &None, false, false);
        let parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
        assert_eq!(parsed["total_cost"], 100.0);
    }

    #[test]
    fn test_format_cost_summary_csv() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 50.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let out = format_cost_summary(&summary, "csv", &None, &None, false, false);
        assert!(out.contains("Total Cost,Currency"));
        assert!(out.contains("50.00"));
    }

    #[test]
    fn test_format_cost_summary_table() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 75.50,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let out = format_cost_summary(&summary, "table", &None, &None, false, false);
        assert!(out.contains("$75.50"));
        assert!(out.contains("USD"));
    }

    #[test]
    fn test_format_cost_summary_with_estimate() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let out = format_cost_summary(&summary, "table", &None, &None, true, false);
        assert!(out.contains("Estimate"));
        assert!(out.contains("projected"));
    }

    #[test]
    fn test_format_cost_summary_with_filters() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let from = Some("2026-01-01".to_string());
        let to = Some("2026-01-31".to_string());
        let out = format_cost_summary(&summary, "table", &from, &to, false, false);
        assert!(out.contains("From filter: 2026-01-01"));
        assert!(out.contains("To filter: 2026-01-31"));
    }

    #[test]
    fn test_format_cost_summary_by_vm() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![azlin_core::models::VmCost {
                vm_name: "my-vm".to_string(),
                cost: 75.0,
                currency: "USD".to_string(),
            }],
        };
        let out = format_cost_summary(&summary, "table", &None, &None, false, true);
        assert!(out.contains("my-vm"));
        assert!(out.contains("$75.00"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_csv() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![azlin_core::models::VmCost {
                vm_name: "my-vm".to_string(),
                cost: 75.0,
                currency: "USD".to_string(),
            }],
        };
        let out = format_cost_summary(&summary, "csv", &None, &None, false, true);
        assert!(out.contains("VM Name,Cost,Currency"));
        assert!(out.contains("my-vm,75.00,USD"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_empty() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let out = format_cost_summary(&summary, "table", &None, &None, false, true);
        assert!(out.contains("No per-VM cost data"));
    }

    // ── Create VM rows ──────────────────────────────────────────────────

    #[test]
    fn test_build_create_vm_rows() {
        let vm = make_test_vm("new-vm", PowerState::Running);
        let rows = build_create_vm_rows(&vm, "rg", "Standard_D4s_v3", "eastus");
        assert!(rows.iter().any(|(k, _)| k == "Name"));
        assert!(rows.iter().any(|(k, _)| k == "Public IP"));
    }

    #[test]
    fn test_build_create_vm_rows_no_ip() {
        let mut vm = make_test_vm("new-vm", PowerState::Running);
        vm.public_ip = None;
        vm.private_ip = None;
        let rows = build_create_vm_rows(&vm, "rg", "Standard_D4s_v3", "eastus");
        assert!(!rows.iter().any(|(k, _)| k == "Public IP"));
        assert!(!rows.iter().any(|(k, _)| k == "Private IP"));
    }

    // ── Doit VM filtering ───────────────────────────────────────────────

    #[test]
    fn test_filter_doit_vms() {
        let mut vm = make_test_vm("doit-vm", PowerState::Running);
        vm.tags
            .insert("created_by".to_string(), "azlin-doit".to_string());
        let vms = vec![vm, make_test_vm("regular-vm", PowerState::Running)];
        let filtered = filter_doit_vms(&vms, None);
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].name, "doit-vm");
    }

    #[test]
    fn test_filter_doit_vms_by_user() {
        let mut vm = make_test_vm("doit-vm", PowerState::Running);
        vm.tags
            .insert("created_by".to_string(), "azlin-doit".to_string());
        vm.admin_username = Some("testuser".to_string());
        let vms = vec![vm];
        let filtered = filter_doit_vms(&vms, Some("testuser"));
        assert_eq!(filtered.len(), 1);
        let filtered_wrong = filter_doit_vms(&vms, Some("otheruser"));
        assert!(filtered_wrong.is_empty());
    }

    // ── SSH connect args ────────────────────────────────────────────────

    #[test]
    fn test_build_ssh_connect_args_basic() {
        let args = build_ssh_connect_args("azureuser", "1.2.3.4", None, None, &[]).unwrap();
        assert!(args.contains(&"azureuser@1.2.3.4".to_string()));
        assert!(args.contains(&"-o".to_string()));
    }

    #[test]
    fn test_build_ssh_connect_args_with_key() {
        let args =
            build_ssh_connect_args("azureuser", "1.2.3.4", Some("/tmp/key"), None, &[]).unwrap();
        assert!(args.contains(&"-i".to_string()));
        assert!(args.contains(&"/tmp/key".to_string()));
    }

    #[test]
    fn test_build_ssh_connect_args_with_tmux() {
        let args = build_ssh_connect_args("azureuser", "1.2.3.4", None, Some("main"), &[]).unwrap();
        assert!(args.contains(&"-t".to_string()));
        let tmux_arg = args.iter().find(|a| a.contains("tmux")).unwrap();
        assert!(tmux_arg.contains("main"));
    }

    #[test]
    fn test_build_ssh_connect_args_invalid_tmux() {
        let result = build_ssh_connect_args("azureuser", "1.2.3.4", None, Some("bad;name"), &[]);
        assert!(result.is_err());
    }

    // ── VM picker ───────────────────────────────────────────────────────

    #[test]
    fn test_format_vm_picker() {
        let vms = vec![
            make_test_vm("vm-a", PowerState::Running),
            make_test_vm("vm-b", PowerState::Running),
        ];
        let out = format_vm_picker(&vms);
        assert!(out.contains("[1] vm-a"));
        assert!(out.contains("[2] vm-b"));
    }

    // ── Extended help ───────────────────────────────────────────────────

    // ── Build list JSON ─────────────────────────────────────────────────

    #[test]
    fn test_build_list_json() {
        let vms = vec![make_test_vm("vm1", PowerState::Running)];
        let sessions = HashMap::new();
        let json = build_list_json(&vms, &sessions);
        let arr = json.as_array().unwrap();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["name"], "vm1");
    }

    #[test]
    fn test_build_list_json_with_tmux() {
        let vms = vec![make_test_vm("vm1", PowerState::Running)];
        let mut sessions = HashMap::new();
        sessions.insert(
            "vm1".to_string(),
            vec!["main".to_string(), "dev".to_string()],
        );
        let json = build_list_json(&vms, &sessions);
        let arr = json.as_array().unwrap();
        let tmux = arr[0]["tmux_sessions"].as_array().unwrap();
        assert_eq!(tmux.len(), 2);
    }

    // ── Key rotation ────────────────────────────────────────────────────

    #[test]
    fn test_format_key_rotation_complete_msg() {
        assert!(format_key_rotation_complete().contains("complete"));
    }

    #[test]
    fn test_format_no_contexts_msg() {
        assert!(format_no_contexts().contains("No contexts"));
    }

    // ── Format list CSV ─────────────────────────────────────────────────

    #[test]
    fn test_format_list_csv_basic() {
        let headers = vec!["Session", "Status", "IP"];
        let rows = vec![ListRow {
            session: "main".to_string(),
            tmux: "-".to_string(),
            vm_name: "vm-1".to_string(),
            os_display: "Linux".to_string(),
            power_state: "Running".to_string(),
            ip_display: "1.2.3.4".to_string(),
            location: "eastus".to_string(),
            cpu: "4".to_string(),
            mem: "16 GB".to_string(),
            vm_size: "Standard_D4s_v3".to_string(),
            latency: None,
            health: None,
            top_procs: None,
        }];
        let config = ListColumnConfig {
            show_tmux: false,
            wide: false,
            with_latency: false,
            with_health: false,
            show_procs: false,
        };
        let csv = format_list_csv(&headers, &rows, &config);
        assert!(csv.contains("Session,Status,IP"));
        assert!(csv.contains("main"));
    }
}
