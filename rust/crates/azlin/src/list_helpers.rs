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

    /// `az` writes a blank line before its error often enough that taking the
    /// literally-first line dropped this warning entirely: empty after
    /// trimming, so nothing printed, so every bastion-only VM in the group
    /// reported zero sessions with no visible cause -- the silent degradation
    /// this path exists to end.
    #[test]
    fn a_leading_blank_line_cannot_suppress_the_bastion_warning() {
        assert_eq!(
            first_reportable_line("\n\nERROR: (AuthorizationFailed) no access\n"),
            "ERROR: (AuthorizationFailed) no access"
        );
    }

    /// `az` prefixes stderr with its own advisories. Reporting one of those as
    /// the cause sends the operator after a missing extension when the real
    /// failure was authorization.
    #[test]
    fn az_advisory_banners_are_not_reported_as_the_cause() {
        let stderr = "WARNING: The command requires the extension bastion.\n\
                      WARNING: Extension is experimental.\n\
                      ERROR: (SubscriptionNotFound) not found\n";
        assert_eq!(
            first_reportable_line(stderr),
            "ERROR: (SubscriptionNotFound) not found"
        );
    }

    /// When the banner is all `az` said, an imprecise cause still beats
    /// printing nothing: nothing reads as "this group has no bastion".
    #[test]
    fn a_banner_only_stderr_still_reports_something() {
        assert_eq!(
            first_reportable_line("\nWARNING: The command requires the extension bastion.\n"),
            "WARNING: The command requires the extension bastion."
        );
    }

    #[test]
    fn empty_stderr_reports_nothing() {
        assert_eq!(first_reportable_line("\n  \n\t\n"), "");
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

/// Pick the one line of an `az` stderr blob worth showing an operator.
///
/// Skips blank lines and `az`'s own advisory banners (`WARNING: ...`, which is
/// how it announces a missing extension or a deprecated argument) to reach the
/// line that names the failure. Falls back to the first non-blank line when the
/// banners are all there is, so the warning is never silently dropped -- an
/// imprecise cause still tells the operator the lookup failed, whereas printing
/// nothing tells them the group has no bastion.
fn first_reportable_line(stderr: &str) -> &str {
    let mut lines = stderr.lines().map(str::trim).filter(|l| !l.is_empty());
    let Some(first) = lines.next() else {
        return "";
    };
    if first.starts_with("WARNING:") {
        lines.find(|l| !l.starts_with("WARNING:")).unwrap_or(first)
    } else {
        first
    }
}

/// Detect Azure Bastion hosts for a resource group.
/// Returns Vec of (name, location, sku).
///
/// On `az` CLI failure, returns an empty list rather than an error (bastion
/// support is optional), but prints a diagnostic to stderr so a transient
/// failure (auth, throttling, network) isn't silently indistinguishable from
/// "no bastion configured" -- this was previously swallowed entirely, which
/// caused `azlin list`/`connect` to intermittently and silently drop tmux
/// session data for bastion-only (private) VMs with no visible cause.
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
        let stderr = String::from_utf8_lossy(&output.stderr);
        // This is the warning an operator actually sees when a bastion lookup
        // fails: `az` exiting non-zero is the common case, and the `Err` arm
        // callers sanitize is only taken when the process cannot be spawned at
        // all. Both halves are text this machine did not author -- the group
        // name is chosen by whoever created it and `az` quotes it back into its
        // own error -- so an escape sequence in either would rewrite the line
        // that reports the failure. One line only, for the same reason
        // `bastion_lookup_failure_warning` takes one: a multi-line error must
        // not be able to fabricate a second warning.
        //
        // Which line matters. `az` writes a leading blank line and an advisory
        // banner ("WARNING: The command requires the extension ...") ahead of
        // the actual error often enough that taking literally the first line
        // either suppressed this warning entirely -- blank first line, empty
        // after trimming, no warning, silent `Ok(vec![])` -- or reported the
        // extension notice as the cause. Suppressing it is the worse half:
        // every bastion-only VM in the group then shows no tmux, health or
        // process data with nothing on screen explaining why, which is the
        // silent degradation this whole path exists to end.
        let stderr = crate::cmd_list_data::sanitize_remote_text(first_reportable_line(&stderr));
        if !stderr.is_empty() {
            eprintln!(
                "Warning: 'az network bastion list' failed for resource group '{}': {}",
                crate::cmd_list_data::sanitize_remote_text(resource_group),
                stderr
            );
        }
        return Ok(Vec::new()); // Bastion not available, not a fatal error
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
