//! Bastion integration tests.
//!
//! Ported from Python E2E: test_bastion_e2e.py, test_bastion_default_e2e.py,
//! test_bastion_routing_e2e.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Bastion subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_bastion_help() {
    let (stdout, _, code) = run_azlin(&["bastion", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("list") || stdout.contains("List"));
}

#[test]
fn test_bastion_list_help() {
    let (_, _, code) = run_azlin(&["bastion", "list", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_bastion_status_help() {
    let (_, _, code) = run_azlin(&["bastion", "status", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_bastion_configure_help() {
    let (_, _, code) = run_azlin(&["bastion", "configure", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Bastion without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_bastion_list_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["bastion", "list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "bastion list should not panic without auth"
    );
}
