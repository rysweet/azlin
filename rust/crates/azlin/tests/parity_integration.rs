//! Integration tests for Python CLI parity — exercises the azlin binary.
//!
//! These tests verify that --help output includes the new flags/subcommands
//! and that argument parsing works end-to-end via the compiled binary.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Code command parity
// ---------------------------------------------------------------------------

#[test]
fn test_code_help_shows_parity_flags() {
    let (stdout, _, code) = run_azlin(&["code", "--help"]);
    assert_eq!(code, 0, "code --help should exit 0");
    assert!(stdout.contains("--user"), "code --help missing --user");
    assert!(stdout.contains("--key"), "code --help missing --key");
    assert!(
        stdout.contains("--no-extensions"),
        "code --help missing --no-extensions"
    );
    assert!(
        stdout.contains("--workspace"),
        "code --help missing --workspace"
    );
}

#[test]
fn test_code_requires_vm_identifier() {
    let (_, stderr, code) = run_azlin(&["code"]);
    assert_ne!(
        code, 0,
        "code without vm_identifier should fail (required arg)"
    );
    assert!(
        stderr.contains("required") || stderr.contains("VM_IDENTIFIER"),
        "error should mention the missing required argument"
    );
}

// ---------------------------------------------------------------------------
// List command parity
// ---------------------------------------------------------------------------

#[test]
fn test_list_help_shows_verbose() {
    let (stdout, _, code) = run_azlin(&["list", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("--verbose"),
        "list --help missing --verbose"
    );
}

// ---------------------------------------------------------------------------
// Batch stop parity
// ---------------------------------------------------------------------------

#[test]
fn test_batch_stop_help_shows_no_deallocate() {
    let (stdout, _, code) = run_azlin(&["batch", "stop", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("--no-deallocate"),
        "batch stop --help missing --no-deallocate"
    );
}

// ---------------------------------------------------------------------------
// Disk add parity
// ---------------------------------------------------------------------------

#[test]
fn test_disk_add_help_shows_mount() {
    let (stdout, _, code) = run_azlin(&["disk", "add", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("--mount"),
        "disk add --help missing --mount"
    );
}

// ---------------------------------------------------------------------------
// Fleet run parity
// ---------------------------------------------------------------------------

#[test]
fn test_fleet_run_help_shows_if_mem_below() {
    let (stdout, _, code) = run_azlin(&["fleet", "run", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("--if-mem-below"),
        "fleet run --help missing --if-mem-below"
    );
}

// ---------------------------------------------------------------------------
// Restore parity
// ---------------------------------------------------------------------------

#[test]
fn test_restore_help_shows_parity_flags() {
    let (stdout, _, code) = run_azlin(&["restore", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("--dry-run"),
        "restore --help missing --dry-run"
    );
    assert!(
        stdout.contains("--no-multi-tab"),
        "restore --help missing --no-multi-tab"
    );
    assert!(
        stdout.contains("--verbose"),
        "restore --help missing --verbose"
    );
}

// ---------------------------------------------------------------------------
// Doit destroy & delete parity
// ---------------------------------------------------------------------------

#[test]
fn test_doit_help_lists_destroy_and_delete() {
    let (stdout, _, code) = run_azlin(&["doit", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("destroy"),
        "doit --help should list 'destroy' subcommand"
    );
    assert!(
        stdout.contains("delete"),
        "doit --help should list 'delete' subcommand"
    );
}

#[test]
fn test_doit_destroy_help() {
    let (_, _, code) = run_azlin(&["doit", "destroy", "--help"]);
    assert_eq!(code, 0, "doit destroy --help should exit 0");
}

#[test]
fn test_doit_delete_help() {
    let (_, _, code) = run_azlin(&["doit", "delete", "--help"]);
    assert_eq!(code, 0, "doit delete --help should exit 0");
}

// ---------------------------------------------------------------------------
// Default value regression tests
// ---------------------------------------------------------------------------

#[test]
fn test_disk_add_help_shows_standard_lrs_default() {
    let (stdout, _, code) = run_azlin(&["disk", "add", "--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Standard_LRS"),
        "disk add --help should show Standard_LRS as default SKU"
    );
}

#[test]
fn test_autopilot_enable_help_shows_correct_defaults() {
    let (stdout, _, code) = run_azlin(&["autopilot", "enable", "--help"]);
    assert_eq!(code, 0);
    // idle_threshold default should be 120, not 30
    assert!(
        stdout.contains("120"),
        "autopilot enable --help should show 120 as idle-threshold default"
    );
    // cpu_threshold default should be 20, not 10
    assert!(
        stdout.contains("20"),
        "autopilot enable --help should show 20 as cpu-threshold default"
    );
}
