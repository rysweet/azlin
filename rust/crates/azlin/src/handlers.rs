//! Extracted command handler logic for testability.
//!
//! Each handler function accepts `&dyn AzureOps` instead of `&VmManager`,
//! enabling mock-based testing without live Azure credentials.
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
}
