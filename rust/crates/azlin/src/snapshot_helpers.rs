use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Schedule configuration persisted to `~/.azlin/schedules/{vm_name}.toml`.
#[derive(Debug, Serialize, Deserialize)]
pub struct SnapshotSchedule {
    pub vm_name: String,
    pub resource_group: String,
    pub every_hours: u32,
    pub keep_count: u32,
    pub enabled: bool,
    pub created: String,
}

/// Return the directory that holds per-VM schedule files.
pub fn schedules_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".azlin")
        .join("schedules")
}

/// Path to the schedule file for a given VM.
pub fn schedule_path(vm_name: &str) -> PathBuf {
    schedules_dir().join(format!("{}.toml", vm_name))
}

/// Read the schedule config for a VM, if it exists.
pub fn load_schedule(vm_name: &str) -> Option<SnapshotSchedule> {
    let path = schedule_path(vm_name);
    let contents = std::fs::read_to_string(path).ok()?;
    toml::from_str(&contents).ok()
}

/// Write a schedule config for a VM.
pub fn save_schedule(schedule: &SnapshotSchedule) -> anyhow::Result<()> {
    let dir = schedules_dir();
    std::fs::create_dir_all(&dir)?;
    let path = schedule_path(&schedule.vm_name);
    let contents = toml::to_string_pretty(schedule)?;
    std::fs::write(path, contents)?;
    Ok(())
}

/// List all schedule files and load them.
pub fn load_all_schedules() -> Vec<SnapshotSchedule> {
    let dir = schedules_dir();
    let entries = match std::fs::read_dir(&dir) {
        Ok(e) => e,
        Err(_) => return Vec::new(),
    };
    entries
        .filter_map(|e| {
            let e = e.ok()?;
            let path = e.path();
            if path.extension().and_then(|x| x.to_str()) == Some("toml") {
                let contents = std::fs::read_to_string(&path).ok()?;
                toml::from_str(&contents).ok()
            } else {
                None
            }
        })
        .collect()
}

/// Generate a deterministic snapshot name from a VM name and a formatted timestamp.
pub fn build_snapshot_name(vm_name: &str, timestamp: &str) -> String {
    format!("{}_snapshot_{}", vm_name, timestamp)
}

/// Filter a list of snapshot JSON values by VM name substring match on `"name"`.
pub fn filter_snapshots<'a>(
    snapshots: &'a [serde_json::Value],
    vm_name: &str,
) -> Vec<&'a serde_json::Value> {
    snapshots
        .iter()
        .filter(|s| {
            s["name"]
                .as_str()
                .map(|n| n.contains(vm_name))
                .unwrap_or(false)
        })
        .collect()
}

/// Extract display columns from a single snapshot JSON value.
pub fn snapshot_row(snap: &serde_json::Value) -> Vec<String> {
    vec![
        snap["name"].as_str().unwrap_or("-").to_string(),
        snap["diskSizeGb"].to_string(),
        snap["timeCreated"].as_str().unwrap_or("-").to_string(),
        snap["provisioningState"]
            .as_str()
            .unwrap_or("-")
            .to_string(),
    ]
}
