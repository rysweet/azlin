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
pub(crate) fn first_reportable_line(stderr: &str) -> &str {
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

/// [`detect_bastion_hosts`] for callers that have no spinner to clear and no
/// better message to give than the failure itself.
///
/// Degrades to an empty list, exactly as before, but says so. Without this the
/// `unwrap_or_default()` these callers used to write turned an authorization
/// failure into "this group has no bastion", and every private VM they went on
/// to build an SSH target for failed later with a cause the operator never saw.
///
/// Both halves are sanitized: the resource group name is chosen by whoever
/// created it and `az` quotes it back into its own error text, so an escape
/// sequence in either would rewrite the line that reports the failure.
pub fn detect_bastion_hosts_or_warn(resource_group: &str) -> Vec<(String, String, String)> {
    match detect_bastion_hosts(resource_group) {
        Ok(found) => found,
        Err(e) => {
            eprintln!(
                "Warning: could not list bastion hosts in resource group '{}': {}. \
                 VMs there that are only reachable through a bastion may be unreachable.",
                crate::cmd_list_data::sanitize_remote_text(resource_group),
                crate::cmd_list_data::sanitize_remote_text(&e.to_string())
            );
            Vec::new()
        }
    }
}

/// Detect Azure Bastion hosts for a resource group.
/// Returns Vec of (name, location, sku).
///
/// Every failure is an `Err`, including `az` merely exiting non-zero. Bastion
/// support is still optional -- callers are expected to degrade rather than
/// abort, and none of them propagate this error -- but the degradation has to
/// be *narrated*, because an empty list is indistinguishable from "no bastion
/// configured" and that silence is what made `azlin list`/`connect`
/// intermittently drop tmux session data for bastion-only (private) VMs with
/// no visible cause.
///
/// Reporting is the caller's job rather than this function's: the callers that
/// run inside a spinner must print after clearing it (see
/// [`crate::cmd_list_data::discover_bastions`]), and a line printed from in
/// here would be erased before it could be read. Callers with no spinner and
/// nothing useful to add should use [`detect_bastion_hosts_or_warn`].
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
        // `az` exiting non-zero is the *common* way a bastion lookup fails --
        // no authorization on the resource, a missing extension, a subscription
        // the credential cannot see. Reporting it is this function's whole
        // contribution to the caller, so it leaves as an `Err` rather than as a
        // line printed from in here.
        //
        // Printing it here instead was the silent-degradation bug wearing a
        // different hat. Every caller runs this inside `spawn_blocking` beneath
        // an `indicatif` spinner that erases and redraws its line on each tick,
        // so the warning was overwritten before it could be read -- and because
        // the old `Ok(Vec::new())` looks exactly like "this group has no
        // bastion", the returned warning list came back empty and the caller
        // had nothing to print once its spinner cleared. Every bastion-only VM
        // in the group then showed no tmux, health or process data with nothing
        // on screen explaining why. Returning `Err` routes the common case
        // through `bastion_lookup_failure_warning`, which the caller prints
        // after `finish_and_clear()`, where it survives.
        //
        // The text is returned unsanitized on purpose: every caller sanitizes
        // at the point of printing (`bastion_lookup_failure_warning` and the
        // bastion-table sweep both do), and sanitizing twice would be the kind
        // of redundancy that rots when one side moves. One line only, so a
        // multi-line `az` error cannot fabricate a second warning; blank lines
        // and `az`'s own `WARNING:` advisory banners are skipped so the line
        // that names the failure is the line reported.
        let detail = first_reportable_line(&stderr);
        let detail = if detail.is_empty() {
            format!(
                "az exited with {} and wrote nothing to stderr",
                output.status
            )
        } else {
            detail.to_string()
        };
        return Err(anyhow::anyhow!("{detail}"));
    }

    // A zero exit whose stdout is not a JSON array is a failed lookup wearing a
    // success code: `az configure --defaults output=table` and extensions that
    // greet on stdout both produce it. `unwrap_or_default()` turned that into
    // "this group has no bastion", which is the same silent degradation as a
    // swallowed error and reaches the operator the same way -- blank tmux,
    // health and process columns with nothing on screen to explain them.
    //
    // Genuinely empty stdout stays benign: it carries no contradicting claim,
    // and reporting it would make a quiet success look like a failure.
    let bastions: Vec<serde_json::Value> = if output.stdout.iter().all(u8::is_ascii_whitespace) {
        Vec::new()
    } else {
        serde_json::from_slice(&output.stdout).map_err(|e| {
            anyhow::anyhow!("az exited successfully but its bastion list did not parse: {e}")
        })?
    };

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
