use crate::*;
use std::fs;
use tempfile::TempDir;

// ── format_cost_summary comprehensive ───────────────────────────

#[test]
fn test_format_cost_summary_table_with_from_and_to() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 123.45,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2024-01-01".to_string()),
        &Some("2024-01-31".to_string()),
        false,
        false,
    );
    assert!(output.contains("$123.45"));
    assert!(output.contains("USD"));
    assert!(output.contains("From filter: 2024-01-01"));
    assert!(output.contains("To filter: 2024-01-31"));
}

#[test]
fn test_format_cost_summary_csv_format() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "EUR".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 6, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 6, 30, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        false,
    );
    assert!(output.contains("Total Cost,Currency,Period Start,Period End"));
    assert!(output.contains("50.00,EUR"));
}

#[test]
fn test_format_cost_summary_with_estimate_flag() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        true,
        false,
    );
    assert!(output.contains("Estimate"));
    assert!(output.contains("$200.00/month"));
}

#[test]
fn test_format_cost_summary_by_vm_table_output() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 300.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "dev-vm".to_string(),
                cost: 150.0,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "prod-vm".to_string(),
                cost: 150.0,
                currency: "USD".to_string(),
            },
        ],
    };
    let output = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(output.contains("dev-vm"));
    assert!(output.contains("prod-vm"));
    assert!(output.contains("$150.00"));
}

#[test]
fn test_format_cost_summary_by_vm_empty_shows_message() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(output.contains("No per-VM cost data"));
}

#[test]
fn test_format_cost_summary_by_vm_csv_format() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "test-vm".to_string(),
            cost: 100.0,
            currency: "USD".to_string(),
        }],
    };
    let output = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(output.contains("VM Name,Cost,Currency"));
    assert!(output.contains("test-vm,100.00,USD"));
}

// ── config_path_helpers ─────────────────────────────────────────

#[test]
fn test_validate_config_path_safe_paths() {
    assert!(crate::config_path_helpers::validate_config_path("config.toml").is_ok());
    assert!(crate::config_path_helpers::validate_config_path("subdir/config.toml").is_ok());
}

#[test]
fn test_validate_config_path_traversal_variants() {
    assert!(crate::config_path_helpers::validate_config_path("../evil.toml").is_err());
    assert!(crate::config_path_helpers::validate_config_path("sub/../../etc/passwd").is_err());
}

// ── stop_helpers ────────────────────────────────────────────────

#[test]
fn test_stop_action_labels_both_modes() {
    let (ing, ed) = crate::stop_helpers::stop_action_labels(true);
    assert_eq!(ing, "Deallocating");
    assert_eq!(ed, "Deallocated");

    let (ing2, ed2) = crate::stop_helpers::stop_action_labels(false);
    assert_eq!(ing2, "Stopping");
    assert_eq!(ed2, "Stopped");
}

// ── snapshot_helpers snapshot_row ────────────────────────────────

#[test]
fn test_snapshot_row_complete_data() {
    let snap = serde_json::json!({
        "name": "vm1_snapshot_20240115",
        "diskSizeGb": 128,
        "timeCreated": "2024-01-15T10:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "vm1_snapshot_20240115");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2024-01-15T10:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_empty_json_defaults() {
    let snap = serde_json::json!({});
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

// ── create_helpers edge cases ───────────────────────────────────

#[test]
fn test_build_clone_cmd_format() {
    let cmd = crate::create_helpers::build_clone_cmd("https://github.com/user/repo.git").unwrap();
    assert!(cmd.contains("git clone"));
    assert!(cmd.contains("https://github.com/user/repo.git"));
    assert!(cmd.contains("~/src/$(basename"));
}

#[test]
fn test_build_clone_name_format() {
    assert_eq!(
        crate::create_helpers::build_clone_name("myvm", 0),
        "myvm-clone-1"
    );
    assert_eq!(
        crate::create_helpers::build_clone_name("myvm", 2),
        "myvm-clone-3"
    );
}

#[test]
fn test_build_disk_name_format() {
    assert_eq!(
        crate::create_helpers::build_disk_name("myvm"),
        "myvm_OsDisk"
    );
}

#[test]
fn test_build_ssh_connect_args_format() {
    let args = crate::create_helpers::build_ssh_connect_args("user", "10.0.0.1");
    assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
    assert!(args.contains(&"user@10.0.0.1".to_string()));
}

// ═══════════════════════════════════════════════════════════════
// Security fix tests
// ═══════════════════════════════════════════════════════════════
