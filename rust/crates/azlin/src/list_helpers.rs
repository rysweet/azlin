use azlin_core::models::{PowerState, VmInfo};

/// Filter out stopped/deallocated VMs, keeping only Running and Starting.
pub fn filter_running(vms: &mut Vec<VmInfo>) {
    vms.retain(|vm| {
        vm.power_state == PowerState::Running || vm.power_state == PowerState::Starting
    });
}

/// Filter VMs by a tag expression.
/// If `tag_filter` is `"key=value"`, keeps VMs where `tags[key] == value`.
/// If `tag_filter` is just `"key"`, keeps VMs that have the key present.
pub fn filter_by_tag(vms: &mut Vec<VmInfo>, tag_filter: &str) {
    if let Some((key, val)) = tag_filter.split_once('=') {
        vms.retain(|vm| vm.tags.get(key).is_some_and(|v| v == val));
    } else {
        vms.retain(|vm| vm.tags.contains_key(tag_filter));
    }
}

/// Filter VMs by a glob-like name pattern (supports `*` as a wildcard).
pub fn filter_by_pattern(vms: &mut Vec<VmInfo>, pattern: &str) {
    let pat = pattern.replace('*', "");
    vms.retain(|vm| vm.name.contains(&pat));
}

/// Apply all three optional filters in order: stopped, tag, pattern.
pub fn apply_filters(
    vms: &mut Vec<VmInfo>,
    include_all: bool,
    tag: Option<&str>,
    pattern: Option<&str>,
) {
    if !include_all {
        filter_running(vms);
    }
    if let Some(t) = tag {
        filter_by_tag(vms, t);
    }
    if let Some(p) = pattern {
        filter_by_pattern(vms, p);
    }
}

/// Detect Azure Bastion hosts for a resource group.
/// Returns Vec of (name, location, sku).
pub fn detect_bastion_hosts(resource_group: &str) -> anyhow::Result<Vec<(String, String, String)>> {
    let output = std::process::Command::new("az")
        .args([
            "network",
            "bastion",
            "list",
            "--resource-group",
            resource_group,
            "--output",
            "json",
        ])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()?;

    if !output.status.success() {
        return Ok(Vec::new()); // Bastion not available, not an error
    }

    let bastions: Vec<serde_json::Value> =
        serde_json::from_slice(&output.stdout).unwrap_or_default();

    Ok(bastions
        .iter()
        .map(|b| {
            let name = b["name"].as_str().unwrap_or("").to_string();
            let location = b["location"].as_str().unwrap_or("").to_string();
            let sku = b["sku"]["name"].as_str().unwrap_or("Basic").to_string();
            (name, location, sku)
        })
        .collect())
}
