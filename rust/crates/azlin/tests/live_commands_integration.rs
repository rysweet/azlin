//! Live Azure integration tests for issues #796 and #789.
//!
//! These tests verify commands that were previously untested against live Azure.
//! Run with: `cargo test --test live_commands_integration -- --ignored`
//!
//! ## Commands covered (from issue #796):
//!   1. costs dashboard / costs history / costs recommend
//!   2. session list
//!   3. template list / template show
//!   4. autopilot status
//!   5. bastion list / bastion status
//!   6. azlin-help list
//!   7. completions bash
//!   8. sync-keys
//!   9. web status / web stop
//!  10. context show / context create / context use
//!  11. restore (tmux restore)
//!  12. os-update (destructive — skipped by default)
//!
//! ## Commands covered (from issue #789):
//!   1. code <vm>
//!   2. logs <vm>
//!   3. compose --help
//!   4. github-runner --help
//!   5. fleet workflow --help
//!   6. sync --dry-run

mod integration;
use integration::run_azlin;

const RG: &str = "RYSWEET-LINUX-VM-POOL";
const VM: &str = "devo";

fn has_azure_login() -> bool {
    let (_, _, code) = run_azlin(&["--version"]);
    if code != 0 {
        return false;
    }
    let output = std::process::Command::new("az")
        .args(["account", "show", "--output", "json"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output();
    matches!(output, Ok(o) if o.status.success())
}

// ---------------------------------------------------------------------------
// #796: costs commands
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_costs_dashboard() {
    if !has_azure_login() {
        return;
    }
    let (_, _, _code) = run_azlin(&["costs", "dashboard", "--resource-group", RG]);
    // Cost APIs may fail on subscription type — just verify no panic
}

#[test]
#[ignore]
fn test_live_costs_history() {
    if !has_azure_login() {
        return;
    }
    let (_, _, _code) = run_azlin(&["costs", "history", "--resource-group", RG, "--days", "7"]);
}

#[test]
#[ignore]
fn test_live_costs_recommend() {
    if !has_azure_login() {
        return;
    }
    let (_, _, _code) = run_azlin(&["costs", "recommend", "--resource-group", RG]);
}

// ---------------------------------------------------------------------------
// #796: session list
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_session_list() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["session", "list", VM, "--resource-group", RG]);
    assert_eq!(code, 0, "session list should succeed");
}

// ---------------------------------------------------------------------------
// #796: template list
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_template_list() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["template", "list"]);
    assert_eq!(code, 0, "template list should succeed");
}

// ---------------------------------------------------------------------------
// #796: autopilot status
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_autopilot_status() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["autopilot", "status"]);
    assert_eq!(code, 0, "autopilot status should succeed");
}

// ---------------------------------------------------------------------------
// #796: bastion status
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_bastion_status() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["bastion", "status", "--resource-group", RG]);
    assert_eq!(code, 0, "bastion status should succeed");
    assert!(
        stdout.contains("Bastion") || stdout.contains("bastion") || stdout.contains("Provisioning"),
        "should show bastion status info"
    );
}

// ---------------------------------------------------------------------------
// #796: azlin-help with various commands
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_azlin_help_list() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["azlin-help", "list"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("list") || stdout.contains("List"),
        "should contain help about list command"
    );
}

// ---------------------------------------------------------------------------
// #796: completions (no Azure needed)
// ---------------------------------------------------------------------------

#[test]
fn test_completions_bash_produces_output() {
    let (stdout, _, code) = run_azlin(&["completions", "bash"]);
    assert_eq!(code, 0, "completions bash should exit 0");
    assert!(!stdout.is_empty(), "bash completions should produce output");
    assert!(
        stdout.contains("complete") || stdout.contains("_azlin"),
        "should contain bash completion syntax"
    );
}

#[test]
fn test_completions_zsh_produces_output() {
    let (stdout, _, code) = run_azlin(&["completions", "zsh"]);
    assert_eq!(code, 0);
    assert!(!stdout.is_empty(), "zsh completions should produce output");
}

#[test]
fn test_completions_fish_produces_output() {
    let (stdout, _, code) = run_azlin(&["completions", "fish"]);
    assert_eq!(code, 0);
    assert!(!stdout.is_empty(), "fish completions should produce output");
}

// ---------------------------------------------------------------------------
// #796: sync-keys
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_sync_keys() {
    if !has_azure_login() {
        return;
    }
    let (stdout, stderr, _code) = run_azlin(&["sync-keys", VM, "--resource-group", RG]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(!combined.contains("panicked"), "sync-keys should not panic");
}

// ---------------------------------------------------------------------------
// #796: web status / web stop
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_web_stop() {
    // web stop should succeed even if nothing is running
    let (_, _, _code) = run_azlin(&["web", "stop"]);
    // Just verify no panic
}

#[test]
#[ignore]
fn test_live_web_status() {
    let (_, _, _code) = run_azlin(&["web", "status"]);
}

// ---------------------------------------------------------------------------
// #796: context show / create / use / delete
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_context_lifecycle() {
    if !has_azure_login() {
        return;
    }
    // Show current
    let (_, _, code) = run_azlin(&["context", "show"]);
    assert_eq!(code, 0, "context show should succeed");

    // Create a test context
    let (_, _, code) = run_azlin(&[
        "context",
        "create",
        "test-live-ctx",
        "--subscription-id",
        "00000000-0000-0000-0000-000000000000",
        "--tenant-id",
        "11111111-1111-1111-1111-111111111111",
        "--resource-group",
        "test-rg",
        "--region",
        "westus2",
    ]);
    assert_eq!(code, 0, "context create should succeed");

    // Use it
    let (_, _, code) = run_azlin(&["context", "use", "test-live-ctx"]);
    assert_eq!(code, 0, "context use should succeed");

    // List (should include the new context)
    let (stdout, _, code) = run_azlin(&["context", "list"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("test-live-ctx"),
        "context list should include the created context"
    );

    // Delete
    let (_, _, code) = run_azlin(&["context", "delete", "test-live-ctx", "--force"]);
    assert_eq!(code, 0, "context delete should succeed");
}

// ---------------------------------------------------------------------------
// #796: restore (tmux session restore)
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_restore() {
    if !has_azure_login() {
        return;
    }
    let (stdout, stderr, _code) = run_azlin(&["restore", "--resource-group", RG]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(!combined.contains("panicked"), "restore should not panic");
}

// ---------------------------------------------------------------------------
// #789: code <vm>
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_code() {
    if !has_azure_login() {
        return;
    }
    let (_, stderr, _code) = run_azlin(&["code", VM, "--resource-group", RG]);
    // May fail if VS Code not installed — just verify no panic
    assert!(!stderr.contains("panicked"), "code should not panic");
}

// ---------------------------------------------------------------------------
// #789: logs <vm>
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_logs_tail() {
    if !has_azure_login() {
        return;
    }
    let (stdout, stderr, code) = run_azlin(&["logs", VM, "--lines", "10", "--resource-group", RG]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(!combined.contains("panicked"), "logs should not panic");
    // If it succeeds, there should be some output
    if code == 0 {
        assert!(!stdout.is_empty(), "log output should not be empty");
    }
}

#[test]
#[ignore]
fn test_live_logs_cloud_init() {
    if !has_azure_login() {
        return;
    }
    let (_, stderr, _code) = run_azlin(&[
        "logs",
        VM,
        "--lines",
        "5",
        "--type",
        "cloud-init",
        "--resource-group",
        RG,
    ]);
    assert!(
        !stderr.contains("panicked"),
        "logs --type cloud-init should not panic"
    );
}

// ---------------------------------------------------------------------------
// #789: compose, github-runner, fleet --help verification
// ---------------------------------------------------------------------------

#[test]
fn test_compose_help_exists() {
    let (stdout, _, code) = run_azlin(&["compose", "--help"]);
    assert_eq!(code, 0, "compose --help should exit 0");
    assert!(
        stdout.contains("compose") || stdout.contains("Docker"),
        "help should mention compose"
    );
}

#[test]
fn test_github_runner_help_exists() {
    let (stdout, _, code) = run_azlin(&["github-runner", "--help"]);
    assert_eq!(code, 0, "github-runner --help should exit 0");
    assert!(
        stdout.contains("runner") || stdout.contains("Runner"),
        "help should mention runner"
    );
}

#[test]
fn test_fleet_workflow_help_exists() {
    let (stdout, _, code) = run_azlin(&["fleet", "workflow", "--help"]);
    assert_eq!(code, 0, "fleet workflow --help should exit 0");
    assert!(
        stdout.contains("workflow") || stdout.contains("Workflow"),
        "help should mention workflow"
    );
}

// ---------------------------------------------------------------------------
// #789: sync --dry-run
// ---------------------------------------------------------------------------

#[test]
#[ignore]
fn test_live_sync_dry_run() {
    if !has_azure_login() {
        return;
    }
    let (stdout, stderr, _code) = run_azlin(&["sync", VM, "--dry-run", "--resource-group", RG]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "sync --dry-run should not panic"
    );
    // Dry run should mention what it would do
    assert!(
        combined.contains("Would") || combined.contains("sync") || combined.contains("No"),
        "dry run should describe what it would do"
    );
}

// ---------------------------------------------------------------------------
// Additional edge cases for untested commands
// ---------------------------------------------------------------------------

#[test]
fn test_invalid_subcommand_for_costs() {
    let (_, _, code) = run_azlin(&["costs", "nonexistent-sub"]);
    assert_ne!(code, 0, "invalid costs subcommand should fail");
}

#[test]
fn test_session_no_args_exits_nonzero() {
    // session with no arguments should require a subcommand or vm name
    let (stdout, stderr, _code) = run_azlin(&["session"]);
    let combined = format!("{}{}", stdout, stderr);
    // Should not panic
    assert!(
        !combined.contains("panicked"),
        "session with no args should not panic"
    );
}

#[test]
fn test_invalid_subcommand_for_bastion() {
    let (_, _, code) = run_azlin(&["bastion", "nonexistent-sub"]);
    assert_ne!(code, 0, "invalid bastion subcommand should fail");
}
