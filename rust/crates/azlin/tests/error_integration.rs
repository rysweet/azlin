//! Error-handling integration tests.
//!
//! Verifies that the binary handles bad input gracefully (no panics).
//! Ported from Python E2E error-path tests.

mod integration;

use integration::run_azlin;

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
    assert_ne!(code, 0, "should fail without Azure auth");
    assert!(
        combined.contains("az login"),
        "should suggest 'az login' when auth fails, got: {combined}"
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
