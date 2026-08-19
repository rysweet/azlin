/// Parse VM resource IDs from the TSV output of
/// `az vm list -g <rg> --query "[].id" -o tsv`.
pub fn parse_vm_ids(tsv_output: &str) -> Vec<&str> {
    tsv_output.lines().filter(|l| !l.is_empty()).collect()
}

/// Build the `az` argument list for a batch VM operation.
/// `action` is e.g. `"deallocate"` or `"start"`.
pub fn build_batch_args<'a>(action: &'a str, ids: &[&'a str]) -> Vec<&'a str> {
    let mut args = vec!["vm", action, "--ids"];
    args.extend(ids);
    args
}

/// Build the JMESPath query for `az vm list`.
///
/// If `tag` is `Some("key=value")`, returns a filter like
/// `[?tags.KEY=='VALUE'].id`.  Otherwise returns `[].id`.
pub fn build_vm_list_query(tag: Option<&str>) -> Result<String, String> {
    match tag {
        Some(t) => {
            let (key, value) = super::tag_helpers::parse_tag(t)
                .ok_or_else(|| format!("Invalid tag format '{}'. Use key=value.", t))?;
            // Reject characters that could break JMESPath / shell quoting
            for ch in ['\'', '"', '\\', '`', '$', ';', '|', '&', '\n', '\r'] {
                if key.contains(ch) || value.contains(ch) {
                    return Err(format!(
                        "Tag key or value contains disallowed character '{}'",
                        ch.escape_default()
                    ));
                }
            }
            Ok(format!("[?tags.{}=='{}'].id", key, value))
        }
        None => Ok("[].id".to_string()),
    }
}

/// Summarise the result of a batch operation as a user-facing message.
pub fn summarise_batch(action: &str, rg: &str, success: bool) -> String {
    if success {
        format!("Batch {} completed for resource group '{}'", action, rg)
    } else {
        format!("Batch {} failed. Run commands individually.", action)
    }
}

/// Match a VM name against a glob pattern supporting `*` (any run of
/// characters, possibly empty) and `?` (exactly one character).
///
/// The match is *anchored*: the whole name must be consumed, so `scratch-*`
/// matches `scratch-01` but not `prod-scratch-01`. Anchoring is deliberate —
/// batch operations are destructive, and a pattern that quietly matches more
/// than the user meant is the failure mode that costs money. Comparison is
/// case-insensitive, matching `azlin list --vm-pattern`.
pub fn glob_match(pattern: &str, name: &str) -> bool {
    let p: Vec<char> = pattern.to_lowercase().chars().collect();
    let n: Vec<char> = name.to_lowercase().chars().collect();
    let (mut pi, mut ni) = (0usize, 0usize);
    let mut star: Option<usize> = None;
    let mut resume = 0usize;
    while ni < n.len() {
        if pi < p.len() && (p[pi] == '?' || p[pi] == n[ni]) {
            pi += 1;
            ni += 1;
        } else if pi < p.len() && p[pi] == '*' {
            star = Some(pi);
            resume = ni;
            pi += 1;
        } else if let Some(s) = star {
            resume += 1;
            ni = resume;
            pi = s + 1;
        } else {
            return false;
        }
    }
    while pi < p.len() && p[pi] == '*' {
        pi += 1;
    }
    pi == p.len()
}

/// Keep only the VM ids whose name matches `pattern`.
///
/// `names` maps resource id to VM name, as returned by the batch VM listing.
/// An id with no known name is dropped rather than kept: acting on a VM we
/// cannot even name is exactly what the filter was asked to prevent.
pub fn filter_ids_by_pattern(
    ids: &[String],
    names: &std::collections::HashMap<String, String>,
    pattern: &str,
) -> Vec<String> {
    ids.iter()
        .filter(|id| names.get(*id).is_some_and(|name| glob_match(pattern, name)))
        .cloned()
        .collect()
}

/// Validate the VM-selection flags of a batch command.
///
/// `--all` means "every VM in the resource group", so combining it with a
/// narrowing filter is ambiguous; rather than silently picking a winner (the
/// exact shape of issue #1089) it is rejected. An empty `--vm-pattern` is
/// rejected too — it would select nothing while reading like a real filter.
pub fn validate_selection(
    all: bool,
    tag: Option<&str>,
    vm_pattern: Option<&str>,
) -> Result<(), String> {
    if let Some(p) = vm_pattern {
        if p.trim().is_empty() {
            return Err(
                "--vm-pattern must not be empty. Use --all to select every VM.".to_string(),
            );
        }
    }
    if all && (tag.is_some() || vm_pattern.is_some()) {
        return Err(
            "--all cannot be combined with --tag or --vm-pattern. Drop --all to use the filter."
                .to_string(),
        );
    }
    Ok(())
}

/// Describe, for a confirmation prompt, which VMs a batch command will touch.
///
/// With no filter at all the description says so in as many words. It must
/// never render as an innocuous-sounding word: the old wording ("VMs matching
/// 'all'") read as "all the matching ones" and hid the fact that no filter was
/// in effect — or, worse, that the user's filter had been discarded.
pub fn describe_selection(tag: Option<&str>, vm_pattern: Option<&str>) -> String {
    match (tag, vm_pattern) {
        (Some(t), Some(p)) => format!("VMs with tag '{}' AND name matching '{}'", t, p),
        (Some(t), None) => format!("VMs with tag '{}'", t),
        (None, Some(p)) => format!("VMs with name matching '{}'", p),
        (None, None) => "EVERY VM (no filter)".to_string(),
    }
}

/// Build the confirmation prompt for a batch action.
/// `action` is the verb shown to the user (e.g. "Stop", "Start");
/// `selection` comes from [`describe_selection`].
pub fn build_confirmation_prompt(action: &str, selection: &str, rg: &str) -> String {
    format!("{} {} in {}?", action, selection, rg)
}

/// The `az vm` subcommand a batch stop should run.
///
/// Mirrors the single-VM path (`azlin stop`): `--no-deallocate` stops the VM
/// but keeps it allocated, preserving its dynamic public IP and ephemeral disks
/// (and its bill). Without the flag the VM is deallocated.
pub fn batch_stop_action(no_deallocate: bool) -> &'static str {
    if no_deallocate {
        "stop"
    } else {
        "deallocate"
    }
}

/// Represents a single step extracted from a workflow YAML file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkflowStep {
    pub name: String,
    pub command: Option<String>,
}

/// Extract the name and command from a workflow YAML step value.
/// Falls back to `"step-N"` when no `name` field is present.
/// Looks for `command` first, then `run` for the command string.
pub fn extract_workflow_step(step: &serde_yaml::Value, index: usize) -> WorkflowStep {
    let default_name = format!("step-{}", index + 1);
    let name = step
        .get("name")
        .and_then(|n| n.as_str())
        .unwrap_or(&default_name)
        .to_string();
    let command = step
        .get("command")
        .or_else(|| step.get("run"))
        .and_then(|c| c.as_str())
        .map(|s| s.to_string());
    WorkflowStep { name, command }
}

/// Format the step header shown during workflow execution.
pub fn format_step_header(step_number: usize, step_name: &str) -> String {
    format!("\n── Step {}: {} ──", step_number, step_name)
}

/// Format the "no VMs found" message for a resource group.
pub fn format_no_vms_message(rg: &str) -> String {
    format!("No VMs found in resource group '{}'", rg)
}

/// Format the "nothing matched" message, naming the filter that was applied so
/// an empty result is never mistaken for an empty resource group.
pub fn format_no_match_message(rg: &str, tag: Option<&str>, vm_pattern: Option<&str>) -> String {
    if tag.is_none() && vm_pattern.is_none() {
        return format_no_vms_message(rg);
    }
    format!(
        "No VMs in resource group '{}' matched {}",
        rg,
        describe_selection(tag, vm_pattern)
    )
}

/// Format the "no running VMs found" message for a resource group.
pub fn format_no_running_vms_message(rg: &str) -> String {
    format!("No running VMs found in resource group '{}'", rg)
}

/// Format the "no running VMs matched" message, naming the name filter when one
/// was applied.
pub fn format_no_running_match_message(rg: &str, vm_pattern: Option<&str>) -> String {
    match vm_pattern {
        Some(p) => format!(
            "No running VMs in resource group '{}' matched name pattern '{}'",
            rg, p
        ),
        None => format_no_running_vms_message(rg),
    }
}

/// Format the fleet execution start message.
pub fn format_fleet_run_message(command: &str, vm_count: usize) -> String {
    format!("Running '{}' on {} VM(s)...", command, vm_count)
}

/// Format the fleet execution start message for `fleet run`.
pub fn format_fleet_across_message(command: &str, vm_count: usize) -> String {
    format!("Running '{}' across {} VM(s)...", command, vm_count)
}
