//! Complete VM lifecycle integration tests.
//!
//! Ported from Python E2E: test_complete_vm_lifecycle_e2e.py,
//! test_complete_workflow.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// VM lifecycle commands — help verification
// ---------------------------------------------------------------------------

#[test]
fn test_new_vm_help() {
    let (stdout, _, code) = run_azlin(&["new", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("repo") || stdout.contains("Repo"));
}

#[test]
fn test_list_help() {
    let (_, _, code) = run_azlin(&["list", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_start_help() {
    let (_, _, code) = run_azlin(&["start", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_stop_help() {
    let (_, _, code) = run_azlin(&["stop", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_connect_help() {
    let (_, _, code) = run_azlin(&["connect", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_delete_help() {
    let (_, _, code) = run_azlin(&["delete", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// VM aliases resolve correctly
// ---------------------------------------------------------------------------

#[test]
fn test_vm_alias_help() {
    let (_, _, code) = run_azlin(&["vm", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_create_alias_help() {
    let (_, _, code) = run_azlin(&["create", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// VM lifecycle without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_list_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(!combined.contains("panicked"));
}

#[test]
fn test_new_dry_run_no_panic() {
    // new without any Azure auth should fail gracefully
    let (stdout, stderr, _) = run_azlin(&["new", "--name", "test-lifecycle-vm"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(!combined.contains("panicked"));
}
