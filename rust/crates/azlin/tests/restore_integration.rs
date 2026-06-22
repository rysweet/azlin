//! Restore integration tests.
//!
//! Ported from Python E2E: test_restore_e2e.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Restore command help
// ---------------------------------------------------------------------------

#[test]
fn test_restore_help() {
    let (_, _, code) = run_azlin(&["restore", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Restore without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_restore_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["restore", "fake-vm"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "restore should not panic without auth"
    );
}
