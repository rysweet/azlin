//! Backup and disaster-recovery integration tests.
//!
//! Ported from Python E2E: test_backup_dr_e2e.py, test_disaster_recovery_e2e.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Snapshot (backup) subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_snapshot_help() {
    let (stdout, _, code) = run_azlin(&["snapshot", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("create") || stdout.contains("Create"));
}

#[test]
fn test_snapshot_create_requires_vm_name() {
    let (_, _, code) = run_azlin(&["snapshot", "create"]);
    assert_ne!(code, 0, "snapshot create requires a VM name argument");
}

#[test]
fn test_snapshot_list_requires_vm_name() {
    let (_, _, code) = run_azlin(&["snapshot", "list"]);
    assert_ne!(code, 0, "snapshot list requires a VM name argument");
}

#[test]
fn test_snapshot_delete_requires_vm_name() {
    let (_, _, code) = run_azlin(&["snapshot", "delete"]);
    assert_ne!(code, 0, "snapshot delete requires a VM name argument");
}

#[test]
fn test_snapshot_restore_requires_vm_name() {
    let (_, _, code) = run_azlin(&["snapshot", "restore"]);
    assert_ne!(code, 0, "snapshot restore requires a VM name argument");
}
