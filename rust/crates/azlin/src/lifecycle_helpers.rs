// Pure helper functions for lifecycle commands (start/stop/delete/kill/destroy/killall/os-update).
// Extracted from cmd_lifecycle.rs for testability.

/// Build the confirmation prompt for deleting a single VM.
pub fn delete_confirm_prompt(vm_name: &str) -> String {
    format!("Delete VM '{}'? This cannot be undone.", vm_name)
}

/// Build the confirmation prompt for destroying a single VM.
pub fn destroy_confirm_prompt(vm_name: &str) -> String {
    format!("Destroy VM '{}'? This cannot be undone.", vm_name)
}

/// Maximum number of VM names listed inline before the list is truncated.
const NAME_LIST_LIMIT: usize = 10;

/// Format a list of VM names as indented lines, truncated to `NAME_LIST_LIMIT`.
fn format_name_list(names: &[String]) -> String {
    let mut out = String::new();
    for name in names.iter().take(NAME_LIST_LIMIT) {
        out.push_str(&format!("  {}\n", name));
    }
    if names.len() > NAME_LIST_LIMIT {
        out.push_str(&format!(
            "  ... and {} more\n",
            names.len() - NAME_LIST_LIMIT
        ));
    }
    out
}

/// Build the confirmation prompt for killall.
///
/// Lists the VM names that are actually about to be deleted so the user can
/// see the real blast radius before confirming an irreversible action.
pub fn killall_confirm_prompt(prefix: &str, resource_group: &str, names: &[String]) -> String {
    format!(
        "Delete these {} VM(s) with prefix '{}' in '{}'? This cannot be undone.\n{}",
        names.len(),
        prefix,
        resource_group,
        format_name_list(names)
    )
}

/// Split VM names into (matching prefix, not matching prefix).
pub fn partition_by_prefix(names: &[String], prefix: &str) -> (Vec<String>, Vec<String>) {
    names
        .iter()
        .cloned()
        .partition(|name| name.starts_with(prefix))
}

/// Narrow a freshly listed set of VM names to those the user actually
/// confirmed.
///
/// The confirmation prompt names specific VMs, so the delete set may only
/// shrink (VMs removed elsewhere in the meantime) and never grow (VMs created
/// during the prompt must not be deleted unannounced).
pub fn narrow_to_confirmed<'a>(listed: &[&'a str], confirmed: &[String]) -> Vec<&'a str> {
    listed
        .iter()
        .copied()
        .filter(|n| confirmed.iter().any(|c| c == n))
        .collect()
}

/// Build a spinner progress message for a lifecycle action on a VM.
pub fn progress_message(action: &str, vm_name: &str) -> String {
    format!("{} {}...", action, vm_name)
}

/// Build the JMESPath query to filter VMs by name prefix.
///
/// Returns names rather than resource IDs: `killall` tears each VM down
/// individually via the shared teardown path, which needs a VM name to look up
/// the session's public IP and NSG.
pub fn killall_jmespath_query(prefix: &str) -> String {
    format!("[?starts_with(name, '{}')].name", prefix)
}

/// JMESPath query listing every VM name in the resource group (read-only).
pub fn killall_all_names_query() -> &'static str {
    "[].name"
}

/// Build the az CLI args for listing VMs filtered by prefix in a resource group.
pub fn killall_list_args<'a>(resource_group: &'a str, query: &'a str) -> Vec<&'a str> {
    vec![
        "vm",
        "list",
        "--resource-group",
        resource_group,
        "--query",
        query,
        "--output",
        "tsv",
    ]
}

/// Parse the TSV output from `az vm list` into a list of non-empty VM names.
///
/// Used for both the full-resource-group enumeration (`[].name`) and the
/// prefix-filtered query; both select names, because per-VM teardown looks a
/// session's disks/NIC/IP/NSG up by VM name.
pub fn parse_vm_ids(tsv_output: &str) -> Vec<&str> {
    tsv_output.lines().filter(|l| !l.is_empty()).collect()
}

/// Explain why `--delete-rg` is refused.
///
/// The flag was previously declared but never read, so it silently did
/// nothing. Actually implementing it would be worse than useless: resource
/// groups routinely contain hand-made VMs, VNets and public IPs alongside
/// azlin sessions, and deleting the group would destroy that unrelated data
/// irrecoverably. Refusing loudly is the safe behaviour.
pub fn delete_rg_rejected_message(resource_group: &str) -> String {
    format!(
        "--delete-rg is not supported: deleting resource group '{resource_group}' would \
         destroy every resource in it, including any VMs, VNets or IPs not managed by \
         azlin.\n\
         Destroy removes the VM and its own disks, NIC, public IP and NSG. To reclaim \
         other leftovers, run 'azlin cleanup --resource-group {resource_group}'.\n\
         If you really intend to delete the whole group, run \
         'az group delete --name {resource_group}' explicitly."
    )
}

/// Format the success message after batch-deleting VMs.
pub fn killall_success_message(count: usize, prefix: &str) -> String {
    format!("Deleted {} VMs with prefix '{}'", count, prefix)
}

/// Format the message shown when no VM matched the killall prefix.
///
/// `unmatched` are the VMs that exist in the resource group but do not start
/// with `prefix`. Reporting them prevents the silent no-op that makes an empty
/// resource group indistinguishable from a prefix mismatch.
pub fn killall_no_match_message(prefix: &str, resource_group: &str, unmatched: &[String]) -> String {
    if unmatched.is_empty() {
        return format!(
            "No VMs found in resource group '{}'. Nothing was deleted.",
            resource_group
        );
    }
    format!(
        "No VMs matched prefix '{}' in '{}'. Nothing was deleted.\n\
         {} VM(s) exist in this resource group but do not start with '{}':\n\
         {}\
         Target them with --prefix, for example:\n  \
         azlin killall --prefix '{}'\n  \
         azlin killall --prefix ''   # every VM in the resource group",
        prefix,
        resource_group,
        unmatched.len(),
        prefix,
        format_name_list(unmatched),
        unmatched[0]
    )
}

/// Format the OS update error detail from stderr.
/// Returns an empty string if stderr is blank; otherwise `: <sanitized_stderr>`.
pub fn os_update_error_detail(stderr: &str) -> String {
    let trimmed = stderr.trim();
    if trimmed.is_empty() {
        String::new()
    } else {
        format!(": {}", azlin_core::sanitizer::sanitize(trimmed))
    }
}

/// Build the full error message for a failed OS update.
pub fn os_update_failure_message(vm_identifier: &str, stderr: &str) -> String {
    let detail = os_update_error_detail(stderr);
    format!("OS update failed on '{}'{}", vm_identifier, detail)
}

/// Format the OS update success banner text.
pub fn os_update_success_message(vm_identifier: &str) -> String {
    format!("OS update completed on '{}'", vm_identifier)
}

/// Format a spinner completion message with a check mark.
pub fn finished_ok(msg: &str) -> String {
    format!("\u{2713} {}", msg)
}

/// Format a "Killed" completion message.
pub fn killed_message(vm_name: &str) -> String {
    format!("\u{2713} Killed {}", vm_name)
}

/// Format a "Destroyed" completion message.
pub fn destroyed_message(vm_name: &str) -> String {
    format!("\u{2713} Destroyed {}", vm_name)
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // ── Confirmation prompts ───────────────────────────────────────────

    #[test]
    fn test_delete_confirm_prompt() {
        assert_eq!(
            delete_confirm_prompt("my-vm"),
            "Delete VM 'my-vm'? This cannot be undone."
        );
    }

    #[test]
    fn test_destroy_confirm_prompt() {
        assert_eq!(
            destroy_confirm_prompt("dev-box"),
            "Destroy VM 'dev-box'? This cannot be undone."
        );
    }

    #[test]
    fn test_killall_confirm_prompt() {
        let names = vec!["test-a".to_string(), "test-b".to_string()];
        let prompt = killall_confirm_prompt("test-", "my-rg", &names);
        assert!(prompt.starts_with(
            "Delete these 2 VM(s) with prefix 'test-' in 'my-rg'? This cannot be undone."
        ));
        assert!(prompt.contains("\n  test-a\n"));
        assert!(prompt.contains("\n  test-b\n"));
    }

    #[test]
    fn test_killall_confirm_prompt_truncates_long_lists() {
        let names: Vec<String> = (0..13).map(|i| format!("vm-{i}")).collect();
        let prompt = killall_confirm_prompt("vm-", "rg", &names);
        assert!(prompt.contains("Delete these 13 VM(s)"));
        assert!(prompt.contains("  vm-9\n"));
        assert!(!prompt.contains("  vm-10\n"));
        assert!(prompt.contains("... and 3 more"));
    }

    // ── Progress / spinner messages ────────────────────────────────────

    #[test]
    fn test_progress_message() {
        assert_eq!(progress_message("Starting", "vm1"), "Starting vm1...");
        assert_eq!(progress_message("Deleting", "vm2"), "Deleting vm2...");
    }

    // ── Killall helpers ────────────────────────────────────────────────

    #[test]
    fn test_killall_jmespath_query() {
        // Names, not IDs: teardown looks up a session's disks/NIC/IP/NSG by VM
        // name, so batching on `--ids` would re-leak the IP and NSG.
        assert_eq!(
            killall_jmespath_query("dev-"),
            "[?starts_with(name, 'dev-')].name"
        );
    }

    #[test]
    fn test_killall_list_args() {
        let query = killall_jmespath_query("x");
        let args = killall_list_args("rg1", &query);
        assert_eq!(args[0], "vm");
        assert_eq!(args[1], "list");
        assert_eq!(args[3], "rg1");
        assert_eq!(args[5], &query);
        assert_eq!(args[7], "tsv");
    }

    #[test]
    fn test_parse_vm_ids_normal() {
        let input = "/sub/rg/vm1\n/sub/rg/vm2\n";
        let ids = parse_vm_ids(input);
        assert_eq!(ids, vec!["/sub/rg/vm1", "/sub/rg/vm2"]);
    }

    #[test]
    fn test_parse_vm_ids_empty() {
        assert!(parse_vm_ids("").is_empty());
        assert!(parse_vm_ids("\n\n").is_empty());
    }

    #[test]
    fn test_killall_success_message() {
        assert_eq!(
            killall_success_message(3, "test-"),
            "Deleted 3 VMs with prefix 'test-'"
        );
    }

    #[test]
    fn test_killall_no_match_message_empty_rg() {
        assert_eq!(
            killall_no_match_message("azlin", "my-rg", &[]),
            "No VMs found in resource group 'my-rg'. Nothing was deleted."
        );
    }

    #[test]
    fn test_killall_no_match_message_reports_unmatched_vms() {
        let unmatched = vec!["smoke-test".to_string(), "other-vm".to_string()];
        let msg = killall_no_match_message("azlin", "my-rg", &unmatched);
        assert!(msg.contains("No VMs matched prefix 'azlin' in 'my-rg'. Nothing was deleted."));
        assert!(msg.contains("2 VM(s) exist in this resource group"));
        assert!(msg.contains("  smoke-test\n"));
        assert!(msg.contains("  other-vm\n"));
        assert!(msg.contains("azlin killall --prefix 'smoke-test'"));
        assert!(msg.contains("--prefix ''"));
    }

    #[test]
    fn test_killall_all_names_query() {
        assert_eq!(killall_all_names_query(), "[].name");
    }

    #[test]
    fn test_partition_by_prefix() {
        let names = vec![
            "azlin-vm-1".to_string(),
            "smoke-test".to_string(),
            "azlin-vm-2".to_string(),
        ];
        let (matched, unmatched) = partition_by_prefix(&names, "azlin");
        assert_eq!(matched, vec!["azlin-vm-1", "azlin-vm-2"]);
        assert_eq!(unmatched, vec!["smoke-test"]);
    }

    #[test]
    fn test_narrow_to_confirmed_drops_unannounced_vms() {
        // A VM created between the confirmation and the delete query must not
        // be torn down: the user never saw it in the prompt.
        let listed = vec!["azlin-a", "azlin-new", "azlin-b"];
        let confirmed = vec!["azlin-a".to_string(), "azlin-b".to_string()];
        assert_eq!(
            narrow_to_confirmed(&listed, &confirmed),
            vec!["azlin-a", "azlin-b"]
        );
    }

    #[test]
    fn test_narrow_to_confirmed_allows_shrinking() {
        // A VM deleted elsewhere in the meantime simply drops out.
        let listed = vec!["azlin-a"];
        let confirmed = vec!["azlin-a".to_string(), "azlin-gone".to_string()];
        assert_eq!(narrow_to_confirmed(&listed, &confirmed), vec!["azlin-a"]);
    }

    #[test]
    fn test_partition_by_prefix_empty_prefix_matches_all() {
        let names = vec!["a".to_string(), "b".to_string()];
        let (matched, unmatched) = partition_by_prefix(&names, "");
        assert_eq!(matched.len(), 2);
        assert!(unmatched.is_empty());
    }

    // ── OS update helpers ──────────────────────────────────────────────

    #[test]
    fn test_os_update_error_detail_empty() {
        assert_eq!(os_update_error_detail(""), "");
        assert_eq!(os_update_error_detail("   "), "");
    }

    #[test]
    fn test_os_update_error_detail_with_text() {
        let detail = os_update_error_detail("  some error  ");
        assert!(detail.starts_with(": "));
        assert!(detail.contains("some error"));
    }

    #[test]
    fn test_os_update_failure_message_no_stderr() {
        assert_eq!(
            os_update_failure_message("vm1", ""),
            "OS update failed on 'vm1'"
        );
    }

    #[test]
    fn test_os_update_failure_message_with_stderr() {
        let msg = os_update_failure_message("vm1", "  apt failed  ");
        assert!(msg.starts_with("OS update failed on 'vm1': "));
        assert!(msg.contains("apt failed"));
    }

    #[test]
    fn test_os_update_success_message() {
        assert_eq!(
            os_update_success_message("box-1"),
            "OS update completed on 'box-1'"
        );
    }

    // ── Completion messages ────────────────────────────────────────────

    #[test]
    fn test_finished_ok() {
        assert_eq!(finished_ok("Started vm1"), "\u{2713} Started vm1");
    }

    #[test]
    fn test_killed_message() {
        assert_eq!(killed_message("vm1"), "\u{2713} Killed vm1");
    }

    #[test]
    fn test_destroyed_message() {
        assert_eq!(destroyed_message("vm1"), "\u{2713} Destroyed vm1");
    }
}
