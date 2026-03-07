use crate::*;
use std::fs;
use tempfile::TempDir;

// ── format_cost_summary additional tests ────────────────────
#[test]
fn test_format_cost_summary_with_from_to_filters() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::NaiveDate::from_ymd_opt(2025, 1, 1)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        period_end: chrono::NaiveDate::from_ymd_opt(2025, 1, 31)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        by_vm: vec![],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2025-01-01".to_string()),
        &Some("2025-01-31".to_string()),
        false,
        false,
    );
    assert!(out.contains("From filter: 2025-01-01"));
    assert!(out.contains("To filter: 2025-01-31"));
}

#[test]
fn test_format_cost_summary_by_vm_csv_output() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::NaiveDate::from_ymd_opt(2025, 1, 1)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        period_end: chrono::NaiveDate::from_ymd_opt(2025, 1, 31)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "vm-1".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "vm-2".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            },
        ],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("VM Name,Cost,Currency"));
    assert!(out.contains("vm-1,100.00,USD"));
    assert!(out.contains("vm-2,100.00,USD"));
}

// ── fleet_spinner_style test ────────────────────────────────
#[test]
fn test_fleet_spinner_style_creation() {
    let style = crate::fleet_spinner_style();
    let _ = style;
}

// ── HealthMetrics test ──────────────────────────────────────
#[test]
fn test_health_metrics_struct() {
    let m = crate::HealthMetrics {
        vm_name: "test-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 45.0,
        mem_percent: 60.0,
        disk_percent: 30.0,
    };
    assert_eq!(m.vm_name, "test-vm");
    assert_eq!(m.power_state, "running");
    assert!(m.cpu_percent > 0.0);
}

// ── health_parse_helpers tests ──────────────────────────────

#[test]
fn test_parse_cpu_stdout_valid() {
    assert_eq!(
        crate::health_parse_helpers::parse_cpu_stdout(0, "  23.4\n"),
        Some(23.4)
    );
}

#[test]
fn test_parse_cpu_stdout_non_zero_exit() {
    assert_eq!(
        crate::health_parse_helpers::parse_cpu_stdout(1, "23.4"),
        None
    );
}

#[test]
fn test_parse_cpu_stdout_garbage() {
    assert_eq!(
        crate::health_parse_helpers::parse_cpu_stdout(0, "not a number"),
        None
    );
}

#[test]
fn test_parse_cpu_stdout_empty() {
    assert_eq!(crate::health_parse_helpers::parse_cpu_stdout(0, ""), None);
}

#[test]
fn test_parse_cpu_stdout_whitespace_only() {
    assert_eq!(
        crate::health_parse_helpers::parse_cpu_stdout(0, "   \n  "),
        None
    );
}

#[test]
fn test_parse_mem_stdout_valid() {
    assert_eq!(
        crate::health_parse_helpers::parse_mem_stdout(0, "67.3\n"),
        Some(67.3)
    );
}

#[test]
fn test_parse_mem_stdout_failure() {
    assert_eq!(
        crate::health_parse_helpers::parse_mem_stdout(127, "67.3"),
        None
    );
}

#[test]
fn test_parse_mem_stdout_zero() {
    assert_eq!(
        crate::health_parse_helpers::parse_mem_stdout(0, "0.0"),
        Some(0.0)
    );
}

#[test]
fn test_parse_disk_stdout_valid() {
    assert_eq!(
        crate::health_parse_helpers::parse_disk_stdout(0, " 42 \n"),
        Some(42.0)
    );
}

#[test]
fn test_parse_disk_stdout_failure() {
    assert_eq!(
        crate::health_parse_helpers::parse_disk_stdout(255, "42"),
        None
    );
}

#[test]
fn test_parse_disk_stdout_not_numeric() {
    assert_eq!(
        crate::health_parse_helpers::parse_disk_stdout(0, "N/A"),
        None
    );
}

#[test]
fn test_default_metrics() {
    let m = crate::health_parse_helpers::default_metrics("my-vm", "deallocated");
    assert_eq!(m.vm_name, "my-vm");
    assert_eq!(m.power_state, "deallocated");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

// ── fleet_helpers tests ─────────────────────────────────────

#[test]
fn test_classify_result_success() {
    let (status, ok) = crate::fleet_helpers::classify_result(0);
    assert_eq!(status, "OK");
    assert!(ok);
}

#[test]
fn test_classify_result_failure() {
    let (status, ok) = crate::fleet_helpers::classify_result(1);
    assert_eq!(status, "FAIL");
    assert!(!ok);
}

#[test]
fn test_classify_result_negative() {
    let (status, ok) = crate::fleet_helpers::classify_result(-1);
    assert_eq!(status, "FAIL");
    assert!(!ok);
}

#[test]
fn test_finish_message_success() {
    let msg = crate::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert_eq!(msg, "✓ done (3 lines)");
}

#[test]
fn test_finish_message_success_empty_stdout() {
    let msg = crate::fleet_helpers::finish_message(0, "", "");
    assert_eq!(msg, "✓ done (0 lines)");
}

#[test]
fn test_finish_message_failure() {
    let msg = crate::fleet_helpers::finish_message(1, "", "Permission denied\nfatal error");
    assert_eq!(msg, "✗ Permission denied");
}

#[test]
fn test_finish_message_failure_empty_stderr() {
    let msg = crate::fleet_helpers::finish_message(1, "", "");
    assert_eq!(msg, "✗ error");
}

#[test]
fn test_format_output_text_show_output_with_stdout() {
    let text = crate::fleet_helpers::format_output_text(0, "hello world\n", "some warning", true);
    assert_eq!(text, "hello world");
}

#[test]
fn test_format_output_text_show_output_empty_stdout() {
    let text = crate::fleet_helpers::format_output_text(0, "  \n", "stderr output", true);
    assert_eq!(text, "stderr output");
}

#[test]
fn test_format_output_text_no_show_failure() {
    let text = crate::fleet_helpers::format_output_text(
        1,
        "",
        "error: connection refused\nmore details",
        false,
    );
    assert_eq!(text, "error: connection refused");
}

#[test]
fn test_format_output_text_no_show_success() {
    let text = crate::fleet_helpers::format_output_text(0, "data", "warning", false);
    assert_eq!(text, "");
}

#[test]
fn test_format_output_text_no_show_failure_empty_stderr() {
    let text = crate::fleet_helpers::format_output_text(1, "", "", false);
    assert_eq!(text, "");
}
