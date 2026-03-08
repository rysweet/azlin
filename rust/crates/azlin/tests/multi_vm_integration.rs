//! Multi-VM orchestration integration tests.
//!
//! Ported from Python E2E: test_multi_vm_orchestration_e2e.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Batch subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_batch_help() {
    let (stdout, _, code) = run_azlin(&["batch", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("stop") || stdout.contains("Stop"));
}

#[test]
fn test_batch_stop_help() {
    let (_, _, code) = run_azlin(&["batch", "stop", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_batch_start_help() {
    let (_, _, code) = run_azlin(&["batch", "start", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Fleet subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_fleet_help() {
    let (stdout, _, code) = run_azlin(&["fleet", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("run") || stdout.contains("Run"));
}

#[test]
fn test_fleet_run_help() {
    let (_, _, code) = run_azlin(&["fleet", "run", "--help"]);
    assert_eq!(code, 0);
}
