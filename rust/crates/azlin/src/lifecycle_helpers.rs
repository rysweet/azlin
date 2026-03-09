/// Pure helper functions for lifecycle commands (start/stop/delete/kill/destroy/killall/os-update).
/// Extracted from cmd_lifecycle.rs for testability.
/// Build the confirmation prompt for deleting a single VM.
pub fn delete_confirm_prompt(vm_name: &str) -> String {
    format!("Delete VM '{}'? This cannot be undone.", vm_name)
}

/// Build the confirmation prompt for destroying a single VM.
pub fn destroy_confirm_prompt(vm_name: &str) -> String {
    format!("Destroy VM '{}'? This cannot be undone.", vm_name)
}

/// Build the confirmation prompt for killall (batch delete).
pub fn killall_confirm_prompt(prefix: &str, resource_group: &str) -> String {
    format!(
        "Delete ALL VMs with prefix '{}' in '{}'? This cannot be undone.",
        prefix, resource_group
    )
}

/// Build a spinner progress message for a lifecycle action on a VM.
pub fn progress_message(action: &str, vm_name: &str) -> String {
    format!("{} {}...", action, vm_name)
}

/// Build the JMESPath query to filter VMs by name prefix.
pub fn killall_jmespath_query(prefix: &str) -> String {
    format!("[?starts_with(name, '{}')].id", prefix)
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

/// Parse the TSV output from `az vm list` into a list of non-empty VM IDs.
pub fn parse_vm_ids(tsv_output: &str) -> Vec<&str> {
    tsv_output.lines().filter(|l| !l.is_empty()).collect()
}

/// Format the success message after batch-deleting VMs.
pub fn killall_success_message(count: usize, prefix: &str) -> String {
    format!("Deleted {} VMs with prefix '{}'", count, prefix)
}

/// Format the "no VMs found" message for killall.
pub fn killall_empty_message(prefix: &str) -> String {
    format!("No VMs found with prefix '{}'", prefix)
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
        assert_eq!(
            killall_confirm_prompt("test-", "my-rg"),
            "Delete ALL VMs with prefix 'test-' in 'my-rg'? This cannot be undone."
        );
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
        assert_eq!(
            killall_jmespath_query("dev-"),
            "[?starts_with(name, 'dev-')].id"
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
    fn test_killall_empty_message() {
        assert_eq!(
            killall_empty_message("nope-"),
            "No VMs found with prefix 'nope-'"
        );
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
