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

/// Resolve a tag filter to a user-facing display string.
/// Returns `"all"` when no tag filter is provided.
pub fn resolve_filter_display(tag: Option<&str>) -> &str {
    tag.unwrap_or("all")
}

/// Build the confirmation prompt for a batch action.
/// `action` is the verb shown to the user (e.g. "Stop", "Start").
pub fn build_confirmation_prompt(action: &str, filter_display: &str, rg: &str) -> String {
    format!("{} VMs matching '{}' in {}?", action, filter_display, rg)
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

/// Format the "no running VMs found" message for a resource group.
pub fn format_no_running_vms_message(rg: &str) -> String {
    format!("No running VMs found in resource group '{}'", rg)
}

/// Format the fleet execution start message.
pub fn format_fleet_run_message(command: &str, vm_count: usize) -> String {
    format!("Running '{}' on {} VM(s)...", command, vm_count)
}

/// Format the fleet execution start message for `fleet run`.
pub fn format_fleet_across_message(command: &str, vm_count: usize) -> String {
    format!("Running '{}' across {} VM(s)...", command, vm_count)
}
