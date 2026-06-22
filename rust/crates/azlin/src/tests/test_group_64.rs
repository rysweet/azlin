use super::common::*;

// ── Missing graceful-error (no-auth) tests ─────────────────────────
// These exercise commands that lacked no-auth graceful-error coverage.
// Each verifies: no panic, exits non-zero or shows error message.

#[test]
fn test_gui_graceful_error_no_auth() {
    assert_graceful_auth_error(&["gui", "test-vm"]);
}

#[test]
fn test_tunnel_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tunnel", "test-vm", "--port", "8080"]);
}

#[test]
fn test_top_graceful_error_no_auth() {
    assert_graceful_auth_error(&["top", "--vm", "test-vm"]);
}

#[test]
fn test_restore_graceful_error_no_auth() {
    assert_graceful_auth_error(&["restore"]);
}

#[test]
fn test_fleet_workflow_graceful_error_no_auth() {
    assert_graceful_auth_error(&["fleet", "workflow", "run", "test.yml"]);
}

#[test]
fn test_github_runner_disable_nonexistent_pool() {
    // github-runner disable checks pool config locally first, before needing auth.
    // A nonexistent pool should produce a "not found" message and exit cleanly.
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "disable", "--pool", "nonexistent-pool-xyz"])
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        !combined.contains("panicked"),
        "should not panic: {}",
        combined
    );
    assert!(
        combined.contains("not found") || combined.contains("Not found"),
        "should mention pool not found: {}",
        combined
    );
}

#[test]
fn test_github_runner_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["github-runner", "status"]);
}

// ── Missing --help smoke tests ─────────────────────────────────────
// Verify commands not covered in earlier groups produce valid help.

#[test]
fn test_tunnel_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tunnel", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "tunnel --help should exit 0");
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("tunnel") || stdout.contains("Tunnel"),
        "help should mention tunnel"
    );
}

#[test]
fn test_gui_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["gui", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "gui --help should exit 0");
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("gui") || stdout.contains("GUI") || stdout.contains("VNC"),
        "help should mention gui/VNC"
    );
}

#[test]
fn test_top_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["top", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "top --help should exit 0");
}

#[test]
fn test_restore_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["restore", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "restore --help should exit 0");
}

// ── Additional --help tests for subcommands that lacked coverage ───

#[test]
fn test_fleet_workflow_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "workflow", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "fleet workflow --help should exit 0");
}

#[test]
fn test_web_help_exits_zero_with_subcommands() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "web --help should exit 0");
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("start") && stdout.contains("stop"),
        "web help should list start and stop subcommands"
    );
}

#[test]
fn test_github_runner_status_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "status", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "github-runner status --help should exit 0"
    );
}

#[test]
fn test_sessions_list_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "sessions list --help should exit 0");
}

#[test]
fn test_sessions_save_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "save", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "sessions save --help should exit 0");
}

#[test]
fn test_sessions_delete_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "delete", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "sessions delete --help should exit 0");
}

// ── Non-auth dispatch tests for commands that can run locally ──────

#[tokio::test]
async fn test_dispatch_completions_powershell() {
    let r = run_dispatch(&["completions", "powershell"]).await;
    assert!(r.is_ok(), "completions powershell failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_completions_elvish() {
    let r = run_dispatch(&["completions", "elvish"]).await;
    assert!(r.is_ok(), "completions elvish failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_config_get_default_region_exists() {
    // Verify default_region is a valid config key
    let r = run_dispatch(&["config", "get", "default_region"]).await;
    assert!(r.is_ok(), "config get default_region failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_config_set_invalid_key() {
    let r = run_dispatch(&["config", "set", "nonexistent_xyz", "value"]).await;
    assert!(r.is_err(), "setting unknown config key should fail");
}

#[tokio::test]
async fn test_dispatch_azlin_help_all_major_commands() {
    for cmd in &[
        "list", "connect", "new", "delete", "start", "stop", "env", "snapshot", "cost",
    ] {
        let r = run_dispatch(&["azlin-help", cmd]).await;
        assert!(r.is_ok(), "azlin-help {} failed: {:?}", cmd, r.err());
    }
}
