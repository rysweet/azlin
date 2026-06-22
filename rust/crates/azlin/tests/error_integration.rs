//! Error-handling integration tests.
//!
//! Verifies that the binary handles bad input gracefully (no panics).
//! Ported from Python E2E error-path tests, test_cli_errors.py,
//! and test_config_manager_errors.py.

mod integration;

use integration::{run_azlin, run_azlin_with_env};

// ---------------------------------------------------------------------------
// Missing required arguments
// ---------------------------------------------------------------------------

#[test]
fn test_missing_vm_name_for_start() {
    let (_, _, code) = run_azlin(&["start"]);
    assert_ne!(code, 0, "start without VM name should exit non-zero");
}

#[test]
fn test_missing_vm_name_for_stop() {
    let (_, _, code) = run_azlin(&["stop"]);
    assert_ne!(code, 0, "stop without VM name should exit non-zero");
}

#[test]
fn test_missing_vm_name_for_connect() {
    let (_, _, code) = run_azlin(&["connect"]);
    assert_ne!(code, 0, "connect without VM name should exit non-zero");
}

#[test]
fn test_missing_vm_name_for_delete() {
    let (_, _, code) = run_azlin(&["delete"]);
    assert_ne!(code, 0, "delete without VM name should exit non-zero");
}

// ---------------------------------------------------------------------------
// No Azure auth — graceful degradation
// ---------------------------------------------------------------------------

#[test]
fn test_no_azure_auth_graceful_error() {
    let (stdout, stderr, _) = run_azlin(&["list", "--resource-group", "test-rg"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "should not panic without Azure auth"
    );
}

#[test]
fn test_azure_error_shows_login_suggestion() {
    let (stdout, stderr, code) = run_azlin(&["list", "--resource-group", "test-rg"]);
    let combined = format!("{}{}", stdout, stderr);
    // When auth fails, must show a clear error (not silently succeed with empty data).
    // When auth succeeds (az CLI logged in), exit 0 is fine.
    if code != 0 {
        assert!(
            combined.contains("az login")
                || combined.contains("error")
                || combined.contains("Error")
                || combined.contains("Failed"),
            "should show a clear error when auth fails, got: {combined}"
        );
    }
    assert!(
        !combined.contains("panicked"),
        "should not panic: {combined}"
    );
}

#[test]
fn test_status_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["status", "fake-vm"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "status without auth should not panic"
    );
}

// ---------------------------------------------------------------------------
// Bad flag combinations
// ---------------------------------------------------------------------------

#[test]
fn test_unknown_flag_rejected() {
    let (_, _, code) = run_azlin(&["list", "--nonexistent-flag"]);
    assert_ne!(code, 0, "unknown flag should be rejected");
}

// ---------------------------------------------------------------------------
// Empty string arguments — should not panic
// Ported from Python: TestInputValidationErrors.test_invalid_vm_name_empty
// ---------------------------------------------------------------------------

#[test]
fn test_empty_vm_name_no_panic() {
    let (stdout, stderr, code) = run_azlin(&["start", ""]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "empty VM name should not panic"
    );
    assert_ne!(code, 0, "empty VM name should fail with non-zero exit");
}

#[test]
fn test_empty_template_name_no_panic() {
    let (stdout, stderr, code) = run_azlin(&["template", "show", ""]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "empty template name should not panic"
    );
    assert_ne!(
        code, 0,
        "empty template name should fail with non-zero exit"
    );
}

#[test]
fn test_empty_session_name_no_panic() {
    let (stdout, stderr, code) = run_azlin(&["sessions", "load", ""]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "empty session name should not panic"
    );
    assert_ne!(code, 0, "empty session name should fail with non-zero exit");
}

// ---------------------------------------------------------------------------
// Very long arguments — should not panic
// Ported from Python: TestInputValidationErrors.test_invalid_vm_name_too_long
// ---------------------------------------------------------------------------

#[test]
fn test_long_vm_name_no_panic() {
    let long_name = "a".repeat(300);
    let (stdout, stderr, code) = run_azlin(&["start", &long_name]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "very long VM name should not panic"
    );
    assert_ne!(code, 0, "very long VM name should fail with non-zero exit");
}

#[test]
fn test_long_config_key_no_panic() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];
    let long_key = "k".repeat(500);

    let (stdout, stderr, _) = run_azlin_with_env(&["config", "get", &long_key], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "very long config key should not panic"
    );
}

// ---------------------------------------------------------------------------
// Special characters — should not panic
// Ported from Python: TestInputValidationErrors.test_invalid_vm_name_invalid_chars
// ---------------------------------------------------------------------------

#[test]
fn test_special_chars_vm_name_no_panic() {
    let (stdout, stderr, code) = run_azlin(&["start", "test@#$%^&*!"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "special chars in VM name should not panic"
    );
    assert_ne!(
        code, 0,
        "special chars in VM name should fail with non-zero exit"
    );
}

#[test]
fn test_special_chars_template_name_no_panic() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, _) =
        run_azlin_with_env(&["template", "show", "../../../etc/passwd"], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "path traversal in template name should not panic"
    );
}

// ---------------------------------------------------------------------------
// Multiple unknown flags
// ---------------------------------------------------------------------------

#[test]
fn test_multiple_unknown_flags_rejected() {
    let (_, _, code) = run_azlin(&["list", "--bad1", "--bad2", "--bad3"]);
    assert_ne!(code, 0, "multiple unknown flags should be rejected");
}

// ---------------------------------------------------------------------------
// Double-dash handling
// ---------------------------------------------------------------------------

#[test]
fn test_double_dash_stops_flag_parsing() {
    // After --, arguments should be treated as positional
    let (stdout, stderr, _) = run_azlin(&["start", "--", "--help"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "double-dash arg should not panic"
    );
}

// ---------------------------------------------------------------------------
// Missing subcommand for grouped commands
// Ported from Python: TestPrerequisiteErrors
// ---------------------------------------------------------------------------

#[test]
fn test_config_no_subcommand() {
    let (_, _, code) = run_azlin(&["config"]);
    assert_ne!(code, 0, "config without subcommand should fail");
}

#[test]
fn test_sessions_no_subcommand() {
    let (_, _, code) = run_azlin(&["sessions"]);
    assert_ne!(code, 0, "sessions without subcommand should fail");
}

// ---------------------------------------------------------------------------
// No panic on every command without Azure auth
// Ported from Python: TestAuthenticationErrors — no-auth graceful handling
// ---------------------------------------------------------------------------

#[test]
fn test_no_panic_on_commands_without_auth() {
    let commands: Vec<&[&str]> = vec![
        &["show", "test-vm"],
        &["start", "test-vm"],
        &["stop", "test-vm"],
        &["connect", "test-vm"],
        &["delete", "test-vm"],
        &["snapshot", "create", "test-vm"],
        &["env", "list", "test-vm"],
    ];

    for args in &commands {
        let (stdout, stderr, _) = run_azlin(args);
        let combined = format!("{}{}", stdout, stderr);
        assert!(
            !combined.contains("panicked"),
            "panicked for: azlin {}",
            args.join(" "),
        );
    }
}
