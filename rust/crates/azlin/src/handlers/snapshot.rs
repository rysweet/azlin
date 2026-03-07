//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

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
