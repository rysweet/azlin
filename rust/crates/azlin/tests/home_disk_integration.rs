//! Home disk integration tests.
//!
//! Ported from Python E2E: test_home_disk_e2e.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Disk subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_disk_help() {
    let (stdout, _, code) = run_azlin(&["disk", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("disk") || stdout.contains("Disk"),
        "disk help should describe disk management"
    );
}

// ---------------------------------------------------------------------------
// Disk without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_disk_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["disk", "list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "disk list should not panic without auth"
    );
}
