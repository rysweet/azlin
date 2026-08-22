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

/// How many VMs each filter stage removed.
///
/// `azlin list` defaults to running-only, which is the right default. What it
/// did wrong was drop the other rows without saying so: six VMs in the pool,
/// two on the screen, and ~11.7 TB of Premium SSD billing against machines the
/// listing had decided not to mention (#1142). These counters exist so every
/// renderer can say what it left out.
///
/// The counts are **stage-local and order-dependent**. [`apply_filters`] runs
/// running -> tag -> pattern, and each field records what *that* stage removed
/// from whatever survived the stages before it. They are not independent
/// "would have been excluded" figures: a deallocated VM that also fails the tag
/// filter is counted once, under `hidden_not_running`, because that is the
/// stage that actually removed it. So the three fields sum to the number of
/// rows that vanished, and never double-count.
///
/// A stage that does not run reports `0` — with `--all`, `hidden_not_running`
/// is always `0` because the running filter never executed.
///
/// # This is not derivable from `total - running`
///
/// It is tempting to compute the hidden count from the summary footer and
/// delete this struct. That is wrong in both directions:
///
/// - [`filter_running`] keeps `Running` **and** `Starting`, while the
///   `Total: N VMs | M running` footer counts `Running` only. A VM mid-boot
///   makes `M < N` with nothing hidden at all.
/// - With `--all`, nothing was filtered, so `total - running` counts VMs that
///   are present in the output.
///
/// Only the filter knows what the filter removed.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct FilterCounts {
    /// Removed by the default running-only filter (stopped, deallocated, ...).
    pub hidden_not_running: usize,
    /// Removed by `--tag`, from what survived the running filter.
    pub dropped_by_tag: usize,
    /// Removed by `--vm-pattern`, from what survived the tag filter.
    pub dropped_by_pattern: usize,
}

impl FilterCounts {
    /// Total rows removed across all stages.
    pub fn total_dropped(&self) -> usize {
        self.hidden_not_running + self.dropped_by_tag + self.dropped_by_pattern
    }

    /// Whether any stage removed anything, i.e. whether there is something to
    /// disclose. When this is false the human-facing surfaces must stay
    /// completely silent: a warning that fires on every run teaches people to
    /// skip the footer, which is how the original defect stayed invisible.
    pub fn any(&self) -> bool {
        self.total_dropped() > 0
    }
}

/// Apply all three optional filters in order: stopped, tag, pattern.
///
/// Returns what each stage removed. Filtering behaviour is unchanged; the
/// return value is new (#1142).
///
/// Deliberately **not** `#[must_use]`: several existing tests call this purely
/// for its effect on `vms` and discard the result, and CI runs
/// `clippy -D warnings`. Adding a return type on its own is source-compatible;
/// `#[must_use]` would not be.
pub fn apply_filters(
    vms: &mut Vec<VmInfo>,
    include_all: bool,
    tag: Option<&str>,
    pattern: Option<&str>,
) -> FilterCounts {
    let mut counts = FilterCounts::default();
    // `saturating_sub` rather than `-`: the subtraction is only sound while
    // every stage is a `retain`, and an underflow here would not panic in
    // release — it would wrap to 18446744073709551615 and print that at the
    // operator, and feed it to JSON consumers.
    if !include_all {
        let before = vms.len();
        filter_running(vms);
        counts.hidden_not_running = before.saturating_sub(vms.len());
    }
    if let Some(t) = tag {
        let before = vms.len();
        filter_by_tag(vms, t);
        counts.dropped_by_tag = before.saturating_sub(vms.len());
    }
    if let Some(p) = pattern {
        let before = vms.len();
        filter_by_pattern(vms, p);
        counts.dropped_by_pattern = before.saturating_sub(vms.len());
    }
    counts
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

    // ── Filter disclosure counts (#1142) ──────────────────────────────
    //
    // The filtering was never the defect; the silence was. Six VMs existed
    // in the pool, `azlin list` showed two, and the four it removed --
    // holding ~11.7 TB of Premium SSD billed at full rate -- left no trace
    // in the output at all. Every test below exists so that a row removed
    // by a filter stays *countable*, which is the precondition for any
    // renderer being able to say it out loud.

    /// A VM with a caller-chosen tag, for separating the tag filter's drops
    /// from the power-state filter's. [`make_vm`] hardcodes `env=dev`, so a
    /// tag test written against it can only ever drop nothing or everything.
    fn make_vm_tagged(name: &str, state: PowerState, key: &str, val: &str) -> VmInfo {
        let mut vm = make_vm(name, state);
        vm.tags = HashMap::from([(key.to_string(), val.to_string())]);
        vm
    }

    #[test]
    fn counts_vms_hidden_because_not_running() {
        // The live pool that exposed this: azt1 + dev running, deva2/deva3/ia2
        // deallocated, test-lifecycle-vm stopped.
        let mut vms = vec![
            make_vm("azt1", PowerState::Running),
            make_vm("dev", PowerState::Running),
            make_vm("deva2", PowerState::Deallocated),
            make_vm("deva3", PowerState::Deallocated),
            make_vm("ia2", PowerState::Deallocated),
            make_vm("test-lifecycle-vm", PowerState::Stopped),
        ];
        let counts = apply_filters(&mut vms, false, None, None);
        assert_eq!(
            vms.len(),
            2,
            "the default view still shows only running VMs"
        );
        assert_eq!(
            counts.hidden_not_running, 4,
            "all four non-running VMs must be counted, not just silently dropped"
        );
        assert_eq!(counts.dropped_by_tag, 0);
        assert_eq!(counts.dropped_by_pattern, 0);
        assert_eq!(counts.total_dropped(), 4);
        assert!(
            counts.any(),
            "something was hidden, so there is something to disclose"
        );
    }

    #[test]
    fn counts_are_zero_when_nothing_was_filtered() {
        let mut vms = vec![
            make_vm("a", PowerState::Running),
            make_vm("b", PowerState::Starting),
        ];
        let counts = apply_filters(&mut vms, false, None, None);
        assert_eq!(vms.len(), 2);
        assert_eq!(counts, FilterCounts::default());
        assert_eq!(counts.total_dropped(), 0);
        assert!(
            !counts.any(),
            "nothing was hidden: renderers must stay quiet, not print a scary zero"
        );
    }

    #[test]
    fn counts_no_hidden_vms_when_include_all_is_set() {
        let mut vms = vec![
            make_vm("a", PowerState::Running),
            make_vm("b", PowerState::Deallocated),
        ];
        let counts = apply_filters(&mut vms, true, None, None);
        assert_eq!(vms.len(), 2);
        assert_eq!(
            counts.hidden_not_running, 0,
            "--all hides nothing, so there is nothing to disclose"
        );
        assert!(!counts.any());
    }

    #[test]
    fn counts_every_non_running_state_as_hidden() {
        // Anything filter_running removes is hidden, including the states an
        // operator is least likely to expect to vanish.
        let mut vms = vec![
            make_vm("run", PowerState::Running),
            make_vm("start", PowerState::Starting),
            make_vm("stop", PowerState::Stopped),
            make_vm("dealloc", PowerState::Deallocated),
            make_vm("stopping", PowerState::Stopping),
            make_vm("unknown", PowerState::Unknown),
        ];
        let counts = apply_filters(&mut vms, false, None, None);
        assert_eq!(vms.len(), 2, "Running and Starting survive");
        assert_eq!(counts.hidden_not_running, 4);
    }

    #[test]
    fn counts_rows_dropped_by_the_tag_filter() {
        let mut vms = vec![
            make_vm_tagged("a", PowerState::Running, "env", "dev"),
            make_vm_tagged("b", PowerState::Running, "env", "prod"),
            make_vm_tagged("c", PowerState::Running, "env", "prod"),
        ];
        let counts = apply_filters(&mut vms, false, Some("env=dev"), None);
        assert_eq!(vms.len(), 1);
        assert_eq!(counts.dropped_by_tag, 2);
        assert_eq!(counts.hidden_not_running, 0);
        assert_eq!(counts.dropped_by_pattern, 0);
    }

    #[test]
    fn counts_rows_dropped_by_the_pattern_filter() {
        let mut vms = vec![
            make_vm("dev-vm-1", PowerState::Running),
            make_vm("prod-vm-1", PowerState::Running),
            make_vm("prod-vm-2", PowerState::Running),
        ];
        let counts = apply_filters(&mut vms, false, None, Some("dev*"));
        assert_eq!(vms.len(), 1);
        assert_eq!(counts.dropped_by_pattern, 2);
        assert_eq!(counts.total_dropped(), 2);
    }

    #[test]
    fn counts_a_pattern_that_matched_nothing() {
        // An empty table is the least informative thing azlin can print. The
        // count is what lets the renderer say "3 VMs did not match" instead.
        let mut vms = vec![
            make_vm("dev-vm-1", PowerState::Running),
            make_vm("dev-vm-2", PowerState::Running),
            make_vm("dev-vm-3", PowerState::Running),
        ];
        let counts = apply_filters(&mut vms, false, None, Some("staging*"));
        assert!(vms.is_empty());
        assert_eq!(counts.dropped_by_pattern, 3);
        assert!(counts.any());
    }

    #[test]
    fn counts_attribute_each_drop_to_the_filter_that_made_it() {
        // dev-2 is dropped by the power-state filter and would *also* have
        // failed the pattern; it must be counted once, against the filter
        // that actually removed it. Otherwise the disclosure over-reports and
        // the numbers stop adding up against the fetched total.
        let mut vms = vec![
            make_vm_tagged("dev-1", PowerState::Running, "env", "dev"),
            make_vm_tagged("dev-2", PowerState::Deallocated, "env", "dev"),
            make_vm_tagged("prod-1", PowerState::Running, "env", "prod"),
        ];
        let counts = apply_filters(&mut vms, false, Some("env=dev"), Some("nomatch"));
        assert!(vms.is_empty());
        assert_eq!(counts.hidden_not_running, 1, "dev-2, and only dev-2");
        assert_eq!(counts.dropped_by_tag, 1, "prod-1, from the surviving two");
        assert_eq!(
            counts.dropped_by_pattern, 1,
            "dev-1, from the surviving one"
        );
        assert_eq!(
            counts.total_dropped(),
            3,
            "the three drops must sum to the three VMs that vanished"
        );
    }

    #[test]
    fn total_dropped_sums_all_three_filters() {
        let counts = FilterCounts {
            hidden_not_running: 4,
            dropped_by_tag: 2,
            dropped_by_pattern: 1,
        };
        assert_eq!(counts.total_dropped(), 7);
        assert!(counts.any());
        assert!(!FilterCounts::default().any());
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

/// [`detect_bastion_hosts`] for callers with no better message to give than the
/// failure itself.
///
/// Degrades to an empty list, exactly as before, but says so. Without this the
/// `unwrap_or_default()` these callers used to write turned an authorization
/// failure into "this group has no bastion", and every private VM they went on
/// to build an SSH target for failed later with a cause the operator never saw.
///
/// Prints immediately, so it is only fully effective for a caller with no
/// spinner live at the time. Most have none, and `cmd_monitoring` moves its
/// lookup above the spinner for exactly this reason. Two do not: `azlin batch`
/// holds a spinner across `resolve_fleet_targets`, which reaches here, so
/// `indicatif` erases the line before it can be read. Those two are still
/// better off than the silent `unwrap_or_default()` they replaced, and fixing
/// them properly means changing how `azlin batch` reports progress rather than
/// anything here -- tracked in #1143. Do not read the absence of a warning on
/// that path as the absence of a failure.
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
                crate::cmd_list_data::strip_one_trailing_period(
                    &crate::cmd_list_data::sanitize_remote_text(&e.to_string())
                )
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
/// [`crate::cmd_list_data::discover_bastions_async_reusing`]), and a line printed from in
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

    // A zero exit whose stdout is not a JSON array is a lookup that did not
    // answer the question, and `unwrap_or_default()` turned it into "this
    // group has no bastion" -- the same silent degradation as a swallowed
    // error, reaching the operator the same way: blank tmux, health and
    // process columns with nothing on screen to explain them.
    //
    // No specific cause is claimed here. `--output json` is on the argv, so
    // `az configure`'s output default cannot override it, and `az`'s own
    // advisories go to stderr; this guards the residue -- a wrapper or shim
    // named `az` earlier in PATH, a truncated write, a future change in the
    // shape ARM returns. The point is that an answer we cannot read must not
    // be recorded as an answer of "none".
    //
    // Genuinely empty stdout stays benign: it carries no contradicting claim,
    // and reporting it would make a quiet success look like a failure.
    let bastions: Vec<serde_json::Value> = if output.stdout.iter().all(u8::is_ascii_whitespace) {
        Vec::new()
    } else {
        // `Option<Vec<_>>`, not `Vec<_>`: a JSON `null` is how several `az`
        // commands spell an empty result, and it means the same thing as `[]`
        // here. Rejecting it would turn the most ordinary case there is -- a
        // resource group with no bastion -- into a warning claiming the lookup
        // failed, which is the mirror image of the bug this arm exists to fix
        // and would train operators to ignore the line.
        //
        // Everything else still fails loudly. A table-formatted or
        // banner-prefixed stdout (`az configure --defaults output=table`, an
        // extension greeting on stdout) is a lookup that did not answer the
        // question, and reading it as "no bastion" degrades every
        // bastion-only VM in the group in silence.
        serde_json::from_slice::<Option<Vec<serde_json::Value>>>(&output.stdout)
            .map_err(|e| {
                anyhow::anyhow!("az exited successfully but its bastion list did not parse: {e}")
            })?
            .unwrap_or_default()
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
