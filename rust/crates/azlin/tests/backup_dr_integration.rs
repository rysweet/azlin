//! Backup and disaster-recovery integration tests.
//!
//! TDD RED PHASE: Tests define the expected CLI behavior for the backup and
//! DR feature (Issue #439). Tests marked [RED] FAIL until implementation adds
//! the `backup` and `dr` subcommands. Tests marked [GREEN] exercise existing
//! snapshot functionality that already works.
//!
//! Ported from Python E2E: test_backup_dr_e2e.py, test_disaster_recovery_e2e.py.

mod integration;

use integration::run_azlin;

// ===========================================================================
// [GREEN] Existing snapshot tests — these pass today
// ===========================================================================

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

// ===========================================================================
// [RED] Backup command — help and argument validation
// ===========================================================================

#[test]
fn test_backup_help_shows_subcommands() {
    let (stdout, _, code) = run_azlin(&["backup", "--help"]);
    assert_eq!(code, 0, "backup --help should succeed");
    assert!(
        stdout.contains("configure"),
        "should list configure subcommand"
    );
    assert!(stdout.contains("trigger"), "should list trigger subcommand");
    assert!(stdout.contains("list"), "should list list subcommand");
    assert!(stdout.contains("restore"), "should list restore subcommand");
    assert!(stdout.contains("verify"), "should list verify subcommand");
    assert!(
        stdout.contains("replicate"),
        "should list replicate subcommand"
    );
}

#[test]
fn test_backup_configure_help() {
    let (stdout, _, code) = run_azlin(&["backup", "configure", "--help"]);
    assert_eq!(code, 0, "backup configure --help should succeed");
    assert!(
        stdout.contains("daily-retention"),
        "should document --daily-retention flag"
    );
    assert!(
        stdout.contains("weekly-retention"),
        "should document --weekly-retention flag"
    );
    assert!(
        stdout.contains("monthly-retention"),
        "should document --monthly-retention flag"
    );
}

#[test]
fn test_backup_configure_requires_vm_name() {
    let (_, _, code) = run_azlin(&["backup", "configure"]);
    assert_ne!(code, 0, "backup configure requires a VM name argument");
}

#[test]
fn test_backup_trigger_requires_vm_name() {
    let (_, _, code) = run_azlin(&["backup", "trigger"]);
    assert_ne!(code, 0, "backup trigger requires a VM name argument");
}

#[test]
fn test_backup_list_requires_vm_name() {
    let (_, _, code) = run_azlin(&["backup", "list"]);
    assert_ne!(code, 0, "backup list requires a VM name argument");
}

#[test]
fn test_backup_restore_requires_vm_and_backup() {
    let (_, _, code) = run_azlin(&["backup", "restore"]);
    assert_ne!(code, 0, "backup restore requires vm name");
    let (_, _, code2) = run_azlin(&["backup", "restore", "my-vm"]);
    assert_ne!(code2, 0, "backup restore requires --backup flag");
}

#[test]
fn test_backup_verify_requires_backup_name() {
    let (_, _, code) = run_azlin(&["backup", "verify"]);
    assert_ne!(code, 0, "backup verify requires a backup name argument");
}

#[test]
fn test_backup_replicate_requires_args() {
    let (_, _, code) = run_azlin(&["backup", "replicate"]);
    assert_ne!(
        code, 0,
        "backup replicate requires backup name and target region"
    );
}

#[test]
fn test_backup_config_show_requires_vm() {
    let (_, _, code) = run_azlin(&["backup", "config-show"]);
    assert_ne!(code, 0, "backup config-show requires a VM name");
}

#[test]
fn test_backup_disable_requires_vm() {
    let (_, _, code) = run_azlin(&["backup", "disable"]);
    assert_ne!(code, 0, "backup disable requires a VM name");
}

// ===========================================================================
// [RED] Backup configure — end-to-end behavior
// ===========================================================================

#[test]
fn test_backup_configure_daily_only() {
    let (stdout, _, code) = run_azlin(&["backup", "configure", "test-vm", "--daily-retention", "7"]);
    assert_eq!(code, 0, "backup configure with daily retention should succeed");
    assert!(
        stdout.contains("configured") || stdout.contains("Configured"),
        "should confirm configuration"
    );
    assert!(stdout.contains("7"), "should echo daily retention value");
}

#[test]
fn test_backup_configure_full_retention() {
    let (stdout, _, code) = run_azlin(&[
        "backup",
        "configure",
        "test-vm",
        "--daily-retention",
        "7",
        "--weekly-retention",
        "4",
        "--monthly-retention",
        "12",
    ]);
    assert_eq!(code, 0, "backup configure with full retention should succeed");
    assert!(stdout.contains("7"), "should echo daily retention");
    assert!(stdout.contains("4"), "should echo weekly retention");
    assert!(stdout.contains("12"), "should echo monthly retention");
}

#[test]
fn test_backup_configure_with_cross_region() {
    let (stdout, _, code) = run_azlin(&[
        "backup",
        "configure",
        "test-vm",
        "--daily-retention",
        "7",
        "--cross-region",
        "--target-region",
        "westus2",
    ]);
    assert_eq!(
        code, 0,
        "backup configure with cross-region should succeed"
    );
    assert!(
        stdout.contains("westus2"),
        "should confirm target region"
    );
}

// ===========================================================================
// [RED] Backup trigger — tier determination
// ===========================================================================

#[test]
fn test_backup_trigger_help_shows_tier_option() {
    let (stdout, _, code) = run_azlin(&["backup", "trigger", "--help"]);
    assert_eq!(code, 0, "backup trigger --help should succeed");
    assert!(
        stdout.contains("tier"),
        "should document --tier option for manual tier override"
    );
}

// ===========================================================================
// [RED] Backup list — filtering
// ===========================================================================

#[test]
fn test_backup_list_help_shows_filters() {
    let (stdout, _, code) = run_azlin(&["backup", "list", "--help"]);
    assert_eq!(code, 0, "backup list --help should succeed");
    assert!(
        stdout.contains("tier"),
        "should document --tier filter option"
    );
}

// ===========================================================================
// [RED] Backup replication commands
// ===========================================================================

#[test]
fn test_backup_replicate_all_requires_vm_and_region() {
    let (_, _, code) = run_azlin(&["backup", "replicate-all"]);
    assert_ne!(
        code, 0,
        "backup replicate-all requires vm name and target region"
    );
}

#[test]
fn test_backup_replication_status_requires_vm() {
    let (_, _, code) = run_azlin(&["backup", "replication-status"]);
    assert_ne!(
        code, 0,
        "backup replication-status requires a VM name"
    );
}

#[test]
fn test_backup_replication_jobs_help() {
    let (stdout, _, code) = run_azlin(&["backup", "replication-jobs", "--help"]);
    assert_eq!(code, 0, "backup replication-jobs --help should succeed");
    assert!(
        stdout.contains("status"),
        "should document --status filter"
    );
}

// ===========================================================================
// [RED] Backup verification commands
// ===========================================================================

#[test]
fn test_backup_verify_all_requires_vm() {
    let (_, _, code) = run_azlin(&["backup", "verify-all"]);
    assert_ne!(code, 0, "backup verify-all requires a VM name");
}

#[test]
fn test_backup_verification_report_help() {
    let (stdout, _, code) = run_azlin(&["backup", "verification-report", "--help"]);
    assert_eq!(
        code, 0,
        "backup verification-report --help should succeed"
    );
    assert!(stdout.contains("days"), "should document --days option");
    assert!(stdout.contains("vm"), "should document --vm option");
}

// ===========================================================================
// [RED] DR test commands
// ===========================================================================

#[test]
fn test_dr_help_shows_subcommands() {
    let (stdout, _, code) = run_azlin(&["dr", "--help"]);
    assert_eq!(code, 0, "dr --help should succeed");
    assert!(stdout.contains("test"), "should list test subcommand");
    assert!(
        stdout.contains("test-history"),
        "should list test-history subcommand"
    );
    assert!(
        stdout.contains("success-rate"),
        "should list success-rate subcommand"
    );
}

#[test]
fn test_dr_test_requires_vm_and_region() {
    let (_, _, code) = run_azlin(&["dr", "test"]);
    assert_ne!(code, 0, "dr test requires VM name");
    let (_, _, code2) = run_azlin(&["dr", "test", "my-vm"]);
    assert_ne!(code2, 0, "dr test requires --test-region");
}

#[test]
fn test_dr_test_help_shows_options() {
    let (stdout, _, code) = run_azlin(&["dr", "test", "--help"]);
    assert_eq!(code, 0, "dr test --help should succeed");
    assert!(
        stdout.contains("test-region"),
        "should document --test-region"
    );
    assert!(stdout.contains("backup"), "should document --backup option");
}

#[test]
fn test_dr_test_all_help() {
    let (stdout, _, code) = run_azlin(&["dr", "test-all", "--help"]);
    assert_eq!(code, 0, "dr test-all --help should succeed");
    assert!(
        stdout.contains("resource-group") || stdout.contains("resource_group"),
        "should document --resource-group option"
    );
}

#[test]
fn test_dr_test_history_requires_vm() {
    let (_, _, code) = run_azlin(&["dr", "test-history"]);
    assert_ne!(code, 0, "dr test-history requires VM name");
}

#[test]
fn test_dr_test_history_help_shows_days() {
    let (stdout, _, code) = run_azlin(&["dr", "test-history", "--help"]);
    assert_eq!(code, 0, "dr test-history --help should succeed");
    assert!(stdout.contains("days"), "should document --days option");
}

#[test]
fn test_dr_success_rate_help() {
    let (stdout, _, code) = run_azlin(&["dr", "success-rate", "--help"]);
    assert_eq!(code, 0, "dr success-rate --help should succeed");
    assert!(stdout.contains("vm"), "should document --vm filter");
    assert!(stdout.contains("days"), "should document --days option");
}
