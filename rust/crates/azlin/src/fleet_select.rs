//! Pure helpers for the `azlin fleet run` / `azlin fleet workflow` flags.
//!
//! Every function here exists because the matching flag was accepted by clap,
//! printed in `--help`, and then dropped by the handler (issue #1089). The
//! logic is kept free of Azure and SSH so each promise `--help` makes can be
//! asserted in a unit test.

use std::collections::HashMap;

/// A VM's measured load, as sampled by [`probe_command`].
///
/// Both fields are `Option` because a probe can fail — an unreachable VM, a
/// missing `top`, a truncated SSH session. A failed probe is *not* zero load:
/// treating it as zero is precisely the silent-success bug this work removes,
/// so the gates below refuse rather than assume.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct VmLoad {
    pub cpu_percent: Option<f32>,
    pub mem_percent: Option<f32>,
}

impl VmLoad {
    /// A load sample is usable for gating only when both figures parsed.
    pub fn is_complete(&self) -> bool {
        self.cpu_percent.is_some() && self.mem_percent.is_some()
    }

    /// Ranking key for `--smart-route`: the busier of the two percentages.
    ///
    /// A VM pinned on memory is as poor a target as one pinned on CPU, so the
    /// worse figure decides. An incomplete sample sorts last (`f32::MAX`)
    /// rather than first, so an unmeasurable VM is never called "least loaded".
    pub fn pressure(&self) -> f32 {
        match (self.cpu_percent, self.mem_percent) {
            (Some(c), Some(m)) => c.max(m),
            _ => f32::MAX,
        }
    }
}

/// CPU percentage at or below which a VM counts as idle for `--if-idle`.
pub const IDLE_CPU_PERCENT: f32 = 5.0;

/// One shell command that prints `<cpu-percent> <mem-percent>` on one line.
///
/// Reuses the same two expressions `azlin health` samples, so `--if-cpu-below`
/// and `azlin health` cannot disagree about what a VM's CPU load is.
pub fn probe_command() -> &'static str {
    "cpu=$(top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'); \
     mem=$(free | awk '/Mem:/{printf \"%.1f\", $3/$2 * 100}'); \
     echo \"$cpu $mem\""
}

/// Parse the output of [`probe_command`].
///
/// Anything other than two parsable numbers yields an incomplete [`VmLoad`],
/// which the gates reject rather than round to zero.
pub fn parse_probe(exit_code: i32, stdout: &str) -> VmLoad {
    if exit_code != 0 {
        return VmLoad::default();
    }
    let mut parts = stdout.split_whitespace();
    let cpu = parts.next().and_then(|s| s.parse::<f32>().ok());
    let mem = parts.next().and_then(|s| s.parse::<f32>().ok());
    VmLoad {
        cpu_percent: cpu,
        mem_percent: mem,
    }
}

/// Why a VM was dropped from a fleet run, for a message the user can act on.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Skipped {
    /// The load probe did not return usable numbers.
    Unmeasurable,
    /// A `--if-*` threshold excluded it. Carries the rendered reason.
    Threshold(String),
}

impl Skipped {
    pub fn reason(&self) -> String {
        match self {
            Skipped::Unmeasurable => {
                "load could not be measured (--if-* gates require a reading)".to_string()
            }
            Skipped::Threshold(t) => t.clone(),
        }
    }
}

/// Decide whether a VM passes the `--if-idle` / `--if-cpu-below` /
/// `--if-mem-below` gates.
///
/// Returns `Ok(())` to run, `Err(reason)` to skip. When no gate is requested
/// the load is never consulted, so an unprobed VM still runs.
pub fn load_gate(
    load: &VmLoad,
    if_idle: bool,
    if_cpu_below: Option<u32>,
    if_mem_below: Option<f64>,
) -> Result<(), Skipped> {
    if !gates_requested(if_idle, if_cpu_below, if_mem_below) {
        return Ok(());
    }
    if !load.is_complete() {
        return Err(Skipped::Unmeasurable);
    }
    let cpu = load.cpu_percent.unwrap_or_default();
    let mem = load.mem_percent.unwrap_or_default();
    if if_idle && cpu > IDLE_CPU_PERCENT {
        return Err(Skipped::Threshold(format!(
            "not idle: CPU {:.1}% > {:.1}% (--if-idle)",
            cpu, IDLE_CPU_PERCENT
        )));
    }
    if let Some(limit) = if_cpu_below {
        if cpu >= limit as f32 {
            return Err(Skipped::Threshold(format!(
                "CPU {:.1}% >= {}% (--if-cpu-below)",
                cpu, limit
            )));
        }
    }
    if let Some(limit) = if_mem_below {
        if mem as f64 >= limit {
            return Err(Skipped::Threshold(format!(
                "memory {:.1}% >= {}% (--if-mem-below)",
                mem, limit
            )));
        }
    }
    Ok(())
}

/// Whether any flag needs a load reading, which is what decides if the extra
/// probe round-trip is worth paying for.
pub fn needs_load_probe(
    if_idle: bool,
    if_cpu_below: Option<u32>,
    if_mem_below: Option<f64>,
    smart_route: bool,
) -> bool {
    smart_route || gates_requested(if_idle, if_cpu_below, if_mem_below)
}

fn gates_requested(if_idle: bool, if_cpu_below: Option<u32>, if_mem_below: Option<f64>) -> bool {
    if_idle || if_cpu_below.is_some() || if_mem_below.is_some()
}

/// Order VM indices least-loaded-first for `--smart-route`.
///
/// The sort is stable on pressure, so VMs with equal load keep the order the
/// resource group listed them in and the command stays reproducible.
pub fn smart_route_order(loads: &[VmLoad]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..loads.len()).collect();
    order.sort_by(|a, b| {
        loads[*a]
            .pressure()
            .partial_cmp(&loads[*b].pressure())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    order
}

/// Apply `--count`, which limits execution to the first N targets.
///
/// `--count 0` selects nothing; that is what the user typed, and running
/// everywhere instead would be the #1089 failure mode in reverse.
pub fn apply_count<T>(mut targets: Vec<T>, count: Option<u32>) -> Vec<T> {
    if let Some(n) = count {
        targets.truncate(n as usize);
    }
    targets
}

/// Validate the VM-selection flags of a fleet command.
///
/// Mirrors [`crate::batch_helpers::validate_selection`], with `--pattern`
/// wording: `--all` means "every VM", so pairing it with a narrowing filter is
/// ambiguous and is rejected rather than silently resolved.
pub fn validate_selection(
    all: bool,
    tag: Option<&str>,
    pattern: Option<&str>,
) -> Result<(), String> {
    if let Some(p) = pattern {
        if p.trim().is_empty() {
            return Err("--pattern must not be empty. Use --all to select every VM.".to_string());
        }
    }
    if let Some(t) = tag {
        if crate::tag_helpers::parse_tag(t).is_none() {
            return Err(format!("Invalid tag format '{}'. Use key=value.", t));
        }
    }
    if all && (tag.is_some() || pattern.is_some()) {
        return Err(
            "--all cannot be combined with --tag or --pattern. Drop --all to use the filter."
                .to_string(),
        );
    }
    Ok(())
}

/// Does one VM pass the `--tag` and `--pattern` filters?
///
/// `tag` is `key=value`; the caller has already validated its shape. Both
/// filters narrow, so a VM must satisfy every filter that was supplied.
pub fn matches_filters(
    vm_name: &str,
    vm_tags: &HashMap<String, String>,
    tag: Option<&str>,
    pattern: Option<&str>,
) -> bool {
    if let Some(t) = tag {
        match crate::tag_helpers::parse_tag(t) {
            Some((key, value)) => {
                if vm_tags.get(key).map(String::as_str) != Some(value) {
                    return false;
                }
            }
            None => return false,
        }
    }
    if let Some(p) = pattern {
        if !crate::batch_helpers::glob_match(p, vm_name) {
            return false;
        }
    }
    true
}

/// Describe the fleet selection for the run banner, naming an absent filter
/// in as many words so "no filter" never reads as a narrow one.
pub fn describe_selection(tag: Option<&str>, pattern: Option<&str>) -> String {
    match (tag, pattern) {
        (Some(t), Some(p)) => format!("VMs with tag '{}' AND name matching '{}'", t, p),
        (Some(t), None) => format!("VMs with tag '{}'", t),
        (None, Some(p)) => format!("VMs with name matching '{}'", p),
        (None, None) => "EVERY running VM (no filter)".to_string(),
    }
}

/// Report an empty fleet, naming the filter that emptied it.
///
/// "No running VMs found in 'rg'" after a `--tag` that matched nothing reads as
/// an empty resource group and sends the user looking in the wrong place.
pub fn format_no_match_message(rg: &str, tag: Option<&str>, pattern: Option<&str>) -> String {
    if tag.is_none() && pattern.is_none() {
        return crate::batch_helpers::format_no_running_vms_message(rg);
    }
    format!(
        "No running VMs in resource group '{}' matched {}",
        rg,
        describe_selection(tag, pattern)
    )
}

/// Exit status the GNU `timeout` utility uses when it kills the command.
pub const TIMEOUT_EXIT_CODE: i32 = 124;

/// Wrap a user command so the remote side kills it after `secs` seconds.
///
/// `--timeout` promised "Command timeout in seconds" and enforced nothing: a
/// command that hung held the whole fleet run open forever. Enforcing it on
/// the remote host rather than locally means the runaway process dies too,
/// instead of being orphaned when the SSH session is torn down.
///
/// `secs == 0` disables the wrapper, matching `timeout(1)`'s own reading of 0
/// as "no limit".
pub fn wrap_with_timeout(command: &str, secs: u32) -> String {
    if secs == 0 {
        return command.to_string();
    }
    format!("timeout {} bash -c {}", secs, shell_quote(command))
}

/// Single-quote a string for POSIX `sh`.
fn shell_quote(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}

/// Seconds the *local* side may spend on one `fleet run` command.
///
/// The remote `timeout` wrapper is the real limit; this is the transport's
/// backstop, kept above it so the remote kill wins and the user sees
/// "timed out after Ns" rather than an opaque transport failure. Without it
/// the bastion path's fixed 60-second cap silently overrode any longer
/// `--timeout` the user asked for.
pub fn local_timeout_secs(timeout: u32) -> u64 {
    /// Grace period for the SSH/bastion round-trip around the remote command.
    const TRANSPORT_GRACE_SECS: u64 = 30;
    /// `--timeout 0` disables the remote limit; the transport still needs a
    /// finite bound, so it gets a day rather than forever.
    const NO_LIMIT_SECS: u64 = 24 * 60 * 60;
    if timeout == 0 {
        NO_LIMIT_SECS
    } else {
        timeout as u64 + TRANSPORT_GRACE_SECS
    }
}

/// Turn a timed-out exit code into a message that says so.
///
/// Without this the user sees a bare "exit 124" and no hint that *their*
/// `--timeout` produced it.
pub fn timeout_note(exit_code: i32, secs: u32) -> Option<String> {
    if secs > 0 && exit_code == TIMEOUT_EXIT_CODE {
        Some(format!("timed out after {}s (--timeout)", secs))
    } else {
        None
    }
}

/// Render `--show-diff`: group VMs by identical output and name the outliers.
///
/// The interesting question a fleet run answers is "which host disagrees",
/// and the per-VM tab view buries it. Groups are ordered largest first, so the
/// majority answer is on top and the divergent hosts are named right after it.
pub fn format_output_diff(results: &[(String, String)]) -> String {
    if results.is_empty() {
        return "No output to compare.".to_string();
    }
    let mut groups: Vec<(String, Vec<String>)> = Vec::new();
    for (name, out) in results {
        let normalised = out.trim_end().to_string();
        match groups.iter_mut().find(|(o, _)| *o == normalised) {
            Some((_, names)) => names.push(name.clone()),
            None => groups.push((normalised, vec![name.clone()])),
        }
    }
    // Largest group first; ties keep discovery order so output is stable.
    groups.sort_by_key(|g| std::cmp::Reverse(g.1.len()));

    if groups.len() == 1 {
        return format!("All {} VM(s) produced identical output.", results.len());
    }
    let mut out = format!(
        "Output differs across {} VM(s): {} distinct result(s).\n",
        results.len(),
        groups.len()
    );
    for (i, (body, names)) in groups.iter().enumerate() {
        out.push_str(&format!(
            "\n── Group {} ({} VM(s): {}) ──\n{}\n",
            i + 1,
            names.len(),
            names.join(", "),
            if body.is_empty() { "(no output)" } else { body }
        ));
    }
    out
}

/// Summarise a retry pass so `--retry-failed` reports what it changed.
pub fn format_retry_summary(retried: usize, recovered: usize) -> String {
    if retried == 0 {
        return "No failures to retry.".to_string();
    }
    format!(
        "Retried {} failed VM(s); {} succeeded on the second attempt, {} still failing.",
        retried,
        recovered,
        retried - recovered
    )
}

/// Clamp `--parallel` to at least one worker.
///
/// `--parallel 0` would otherwise mean "run on nothing" while reading as
/// "no limit".
pub fn worker_count(parallel: u32) -> usize {
    (parallel as usize).max(1)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tags(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn probe_parses_two_numbers() {
        let load = parse_probe(0, "12.5 43.0\n");
        assert_eq!(load.cpu_percent, Some(12.5));
        assert_eq!(load.mem_percent, Some(43.0));
        assert!(load.is_complete());
    }

    #[test]
    fn probe_failure_is_not_zero_load() {
        let load = parse_probe(1, "12.5 43.0");
        assert!(!load.is_complete());
        assert_eq!(load.cpu_percent, None);
        let partial = parse_probe(0, "12.5");
        assert!(!partial.is_complete());
    }

    #[test]
    fn unmeasurable_vm_is_skipped_not_assumed_idle() {
        let load = VmLoad::default();
        assert_eq!(
            load_gate(&load, true, None, None),
            Err(Skipped::Unmeasurable)
        );
    }

    #[test]
    fn unmeasurable_vm_still_runs_when_no_gate_asked() {
        assert_eq!(load_gate(&VmLoad::default(), false, None, None), Ok(()));
    }

    #[test]
    fn if_idle_excludes_a_busy_vm() {
        let busy = VmLoad {
            cpu_percent: Some(80.0),
            mem_percent: Some(10.0),
        };
        assert!(load_gate(&busy, true, None, None).is_err());
        let quiet = VmLoad {
            cpu_percent: Some(1.0),
            mem_percent: Some(10.0),
        };
        assert_eq!(load_gate(&quiet, true, None, None), Ok(()));
    }

    #[test]
    fn if_cpu_below_is_a_strict_threshold() {
        let at_limit = VmLoad {
            cpu_percent: Some(50.0),
            mem_percent: Some(1.0),
        };
        assert!(load_gate(&at_limit, false, Some(50), None).is_err());
        let under = VmLoad {
            cpu_percent: Some(49.9),
            mem_percent: Some(1.0),
        };
        assert_eq!(load_gate(&under, false, Some(50), None), Ok(()));
    }

    #[test]
    fn if_mem_below_is_a_strict_threshold() {
        let at_limit = VmLoad {
            cpu_percent: Some(1.0),
            mem_percent: Some(75.0),
        };
        assert!(load_gate(&at_limit, false, None, Some(75.0)).is_err());
        let under = VmLoad {
            cpu_percent: Some(1.0),
            mem_percent: Some(74.9),
        };
        assert_eq!(load_gate(&under, false, None, Some(75.0)), Ok(()));
    }

    #[test]
    fn probe_is_only_paid_for_when_a_flag_needs_it() {
        assert!(!needs_load_probe(false, None, None, false));
        assert!(needs_load_probe(true, None, None, false));
        assert!(needs_load_probe(false, Some(10), None, false));
        assert!(needs_load_probe(false, None, Some(10.0), false));
        assert!(needs_load_probe(false, None, None, true));
    }

    #[test]
    fn smart_route_puts_the_quietest_vm_first() {
        let loads = vec![
            VmLoad {
                cpu_percent: Some(90.0),
                mem_percent: Some(10.0),
            },
            VmLoad {
                cpu_percent: Some(5.0),
                mem_percent: Some(5.0),
            },
            VmLoad {
                cpu_percent: Some(10.0),
                mem_percent: Some(80.0),
            },
        ];
        assert_eq!(smart_route_order(&loads), vec![1, 2, 0]);
    }

    #[test]
    fn smart_route_sorts_unmeasurable_vms_last() {
        let loads = vec![
            VmLoad::default(),
            VmLoad {
                cpu_percent: Some(99.0),
                mem_percent: Some(99.0),
            },
        ];
        assert_eq!(smart_route_order(&loads), vec![1, 0]);
    }

    #[test]
    fn count_limits_the_target_list() {
        let targets = vec!["a", "b", "c"];
        assert_eq!(apply_count(targets.clone(), Some(2)), vec!["a", "b"]);
        assert_eq!(apply_count(targets.clone(), None), vec!["a", "b", "c"]);
        assert_eq!(apply_count(targets.clone(), Some(9)), vec!["a", "b", "c"]);
        assert!(apply_count(targets, Some(0)).is_empty());
    }

    #[test]
    fn all_cannot_be_combined_with_a_filter() {
        assert!(validate_selection(true, Some("env=dev"), None).is_err());
        assert!(validate_selection(true, None, Some("web-*")).is_err());
        assert_eq!(validate_selection(true, None, None), Ok(()));
        assert_eq!(validate_selection(false, Some("env=dev"), None), Ok(()));
    }

    #[test]
    fn empty_pattern_is_rejected_rather_than_matching_nothing() {
        assert!(validate_selection(false, None, Some("  ")).is_err());
    }

    #[test]
    fn malformed_tag_is_rejected_up_front() {
        let err = validate_selection(false, Some("env"), None).unwrap_err();
        assert!(err.contains("key=value"), "{err}");
    }

    #[test]
    fn tag_filter_selects_only_matching_vms() {
        let dev = tags(&[("env", "dev")]);
        let prod = tags(&[("env", "prod")]);
        assert!(matches_filters("vm1", &dev, Some("env=dev"), None));
        assert!(!matches_filters("vm1", &prod, Some("env=dev"), None));
        assert!(!matches_filters(
            "vm1",
            &HashMap::new(),
            Some("env=dev"),
            None
        ));
    }

    #[test]
    fn pattern_filter_selects_only_matching_names() {
        let none = HashMap::new();
        assert!(matches_filters("web-01", &none, None, Some("web-*")));
        assert!(!matches_filters("db-01", &none, None, Some("web-*")));
    }

    #[test]
    fn tag_and_pattern_both_have_to_match() {
        let dev = tags(&[("env", "dev")]);
        assert!(matches_filters(
            "web-01",
            &dev,
            Some("env=dev"),
            Some("web-*")
        ));
        assert!(!matches_filters(
            "db-01",
            &dev,
            Some("env=dev"),
            Some("web-*")
        ));
    }

    #[test]
    fn no_filter_is_described_as_no_filter() {
        assert!(describe_selection(None, None).contains("no filter"));
    }

    #[test]
    fn empty_result_names_the_filter_that_emptied_it() {
        let filtered = format_no_match_message("rg", Some("env=dev"), None);
        assert!(filtered.contains("env=dev"), "{filtered}");
        let unfiltered = format_no_match_message("rg", None, None);
        assert!(unfiltered.contains("No running VMs"), "{unfiltered}");
        assert!(!unfiltered.contains("matched"), "{unfiltered}");
    }

    #[test]
    fn timeout_wraps_the_command_and_quotes_it() {
        let wrapped = wrap_with_timeout("echo 'hi there'", 30);
        assert!(wrapped.starts_with("timeout 30 bash -c "), "{wrapped}");
        assert!(wrapped.contains("'\\''hi there'\\''"), "{wrapped}");
    }

    #[test]
    fn timeout_zero_leaves_the_command_alone() {
        assert_eq!(wrap_with_timeout("uptime", 0), "uptime");
    }

    #[test]
    fn local_timeout_outlives_the_remote_one() {
        // The remote kill has to land first, or the user sees a transport
        // error instead of "timed out after Ns".
        assert!(local_timeout_secs(300) > 300);
        // And it must not be capped at the bastion default of 60s.
        assert!(local_timeout_secs(600) > 60);
        assert!(local_timeout_secs(0) >= 24 * 60 * 60);
    }

    #[test]
    fn timeout_exit_code_is_reported_as_a_timeout() {
        assert!(timeout_note(124, 30).unwrap().contains("30s"));
        assert_eq!(timeout_note(1, 30), None);
        assert_eq!(timeout_note(124, 0), None);
    }

    #[test]
    fn diff_reports_identical_output_as_identical() {
        let results = vec![
            ("a".to_string(), "same\n".to_string()),
            ("b".to_string(), "same".to_string()),
        ];
        assert!(format_output_diff(&results).contains("identical"));
    }

    #[test]
    fn diff_names_the_outlier_vm() {
        let results = vec![
            ("a".to_string(), "6.8.0".to_string()),
            ("b".to_string(), "6.8.0".to_string()),
            ("odd".to_string(), "5.15.0".to_string()),
        ];
        let out = format_output_diff(&results);
        assert!(out.contains("2 distinct result(s)"), "{out}");
        // The majority answer leads; the single outlier is named after it.
        let majority = out.find("6.8.0").unwrap();
        let outlier = out.find("5.15.0").unwrap();
        assert!(majority < outlier, "{out}");
        assert!(out.contains("odd"), "{out}");
    }

    #[test]
    fn diff_of_nothing_says_so() {
        assert!(format_output_diff(&[]).contains("No output"));
    }

    #[test]
    fn retry_summary_counts_recoveries() {
        assert!(format_retry_summary(0, 0).contains("No failures"));
        let s = format_retry_summary(3, 1);
        assert!(s.contains("Retried 3"), "{s}");
        assert!(s.contains("1 succeeded"), "{s}");
        assert!(s.contains("2 still failing"), "{s}");
    }

    #[test]
    fn parallel_zero_still_runs_one_worker() {
        assert_eq!(worker_count(0), 1);
        assert_eq!(worker_count(10), 10);
    }
}
