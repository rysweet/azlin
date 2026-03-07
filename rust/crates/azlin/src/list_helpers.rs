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

#[cfg(test)]
mod tests {
    use super::*;
    use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
    use std::collections::HashMap;

    fn make_vm(name: &str, state: PowerState) -> VmInfo {
        VmInfo {
            name: name.to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "Standard_D4s_v3".to_string(),
            power_state: state,
            provisioning_state: ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: Some("1.2.3.4".to_string()),
            private_ip: Some("10.0.0.1".to_string()),
            admin_username: Some("azureuser".to_string()),
            tags: HashMap::from([("env".to_string(), "dev".to_string())]),
            created_time: None,
        }
    }

    #[test]
    fn test_filter_running_keeps_running() {
        let mut vms = vec![
            make_vm("a", PowerState::Running),
            make_vm("b", PowerState::Deallocated),
            make_vm("c", PowerState::Starting),
        ];
        filter_running(&mut vms);
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].name, "a");
        assert_eq!(vms[1].name, "c");
    }

    #[test]
    fn test_filter_running_empty() {
        let mut vms: Vec<VmInfo> = vec![];
        filter_running(&mut vms);
        assert!(vms.is_empty());
    }

    #[test]
    fn test_filter_by_tag_key_value() {
        let mut vms = vec![make_vm("a", PowerState::Running)];
        filter_by_tag(&mut vms, "env=dev");
        assert_eq!(vms.len(), 1);
    }

    #[test]
    fn test_filter_by_tag_key_value_no_match() {
        let mut vms = vec![make_vm("a", PowerState::Running)];
        filter_by_tag(&mut vms, "env=prod");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_filter_by_tag_key_only() {
        let mut vms = vec![make_vm("a", PowerState::Running)];
        filter_by_tag(&mut vms, "env");
        assert_eq!(vms.len(), 1);
    }

    #[test]
    fn test_filter_by_tag_key_only_missing() {
        let mut vms = vec![make_vm("a", PowerState::Running)];
        filter_by_tag(&mut vms, "missing");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_filter_by_pattern_match() {
        let mut vms = vec![
            make_vm("dev-vm-1", PowerState::Running),
            make_vm("prod-vm-1", PowerState::Running),
        ];
        filter_by_pattern(&mut vms, "dev*");
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "dev-vm-1");
    }

    #[test]
    fn test_filter_by_pattern_no_match() {
        let mut vms = vec![make_vm("dev-vm-1", PowerState::Running)];
        filter_by_pattern(&mut vms, "staging*");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_apply_filters_all_off() {
        let mut vms = vec![
            make_vm("a", PowerState::Running),
            make_vm("b", PowerState::Deallocated),
        ];
        apply_filters(&mut vms, false, None, None);
        assert_eq!(vms.len(), 1); // Only running kept
    }

    #[test]
    fn test_apply_filters_include_all() {
        let mut vms = vec![
            make_vm("a", PowerState::Running),
            make_vm("b", PowerState::Deallocated),
        ];
        apply_filters(&mut vms, true, None, None);
        assert_eq!(vms.len(), 2);
    }

    #[test]
    fn test_apply_filters_combined() {
        let mut vms = vec![
            make_vm("dev-1", PowerState::Running),
            make_vm("prod-1", PowerState::Running),
        ];
        apply_filters(&mut vms, true, Some("env=dev"), Some("dev*"));
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "dev-1");
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
