//! Doit / azdoit scenario integration tests.
//!
//! Ported from Python E2E: test_doit_scenarios.py, test_azdoit_scenarios.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Doit subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_doit_help() {
    let (_, _, code) = run_azlin(&["doit", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Do subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_do_help() {
    let (_, _, code) = run_azlin(&["do", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Ask subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_ask_help() {
    let (_, _, code) = run_azlin(&["ask", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Do without API key — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_do_without_api_key_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["do", "list vms", "--dry-run"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "do should not panic without API key"
    );
}
