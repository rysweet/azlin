//! Storage management integration tests.
//!
//! Ported from Python E2E: test_storage_management_workflows.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Storage subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_storage_help() {
    let (stdout, _, code) = run_azlin(&["storage", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("create") || stdout.contains("Create"));
}

#[test]
fn test_storage_create_help() {
    let (_, _, code) = run_azlin(&["storage", "create", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_storage_list_help() {
    let (_, _, code) = run_azlin(&["storage", "list", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_storage_status_help() {
    let (_, _, code) = run_azlin(&["storage", "status", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Storage without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_storage_list_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["storage", "list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "storage list should not panic without auth"
    );
}
