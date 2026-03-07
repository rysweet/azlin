use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── List CSV format tests ───────────────────────────────────────

#[test]
fn test_format_list_csv_minimal() {
    let config = ListColumnConfig {
        show_tmux: false,
        wide: false,
        with_latency: false,
        with_health: false,
        show_procs: false,
    };
    let headers = build_list_headers(&config);
    let vm = make_test_vm("vm-1", PowerState::Running);
    let rows = vec![build_list_row(&vm, None, None, None, None)];
    let csv = format_list_csv(&headers, &rows, &config);
    assert!(csv.starts_with("Session,OS,Status,IP,Region,CPU,Mem\n"));
    assert!(csv.contains("Running"));
    assert!(csv.contains("20.1.2.3"));
}

#[test]
fn test_format_list_csv_wide() {
    let config = ListColumnConfig {
        show_tmux: true,
        wide: true,
        with_latency: false,
        with_health: false,
        show_procs: false,
    };
    let headers = build_list_headers(&config);
    let vm = make_test_vm("vm-1", PowerState::Running);
    let rows = vec![build_list_row(&vm, None, None, None, None)];
    let csv = format_list_csv(&headers, &rows, &config);
    assert!(csv.contains("vm-1"));
    assert!(csv.contains("Standard_D4s_v3"));
}

#[test]
fn test_format_list_csv_empty() {
    let config = ListColumnConfig {
        show_tmux: false,
        wide: false,
        with_latency: false,
        with_health: false,
        show_procs: false,
    };
    let headers = build_list_headers(&config);
    let csv = format_list_csv(&headers, &[], &config);
    let lines: Vec<&str> = csv.lines().collect();
    assert_eq!(lines.len(), 1); // Only header
}

// ── Env output parsing tests ────────────────────────────────────

#[test]
fn test_parse_env_output_basic() {
    let output = "HOME=/home/user\nPATH=/usr/bin\nSHELL=/bin/bash";
    let pairs = parse_env_output(output);
    assert_eq!(pairs.len(), 3);
    assert_eq!(pairs[0], ("HOME".to_string(), "/home/user".to_string()));
    assert_eq!(pairs[1], ("PATH".to_string(), "/usr/bin".to_string()));
}

#[test]
fn test_parse_env_output_with_equals_in_value() {
    let output = "OPTS=--key=value";
    let pairs = parse_env_output(output);
    assert_eq!(pairs.len(), 1);
    assert_eq!(pairs[0].0, "OPTS");
    assert_eq!(pairs[0].1, "--key=value");
}

#[test]
fn test_parse_env_output_empty() {
    let pairs = parse_env_output("");
    assert_eq!(pairs.len(), 0);
}

#[test]
fn test_parse_env_output_invalid_lines_skipped() {
    let output = "VALID=yes\ninvalid line\nALSO_VALID=true";
    let pairs = parse_env_output(output);
    assert_eq!(pairs.len(), 2);
}

// ── Tmux session format tests ───────────────────────────────────

#[test]
fn test_format_tmux_session_list_empty() {
    assert_eq!(format_tmux_session_list(&[], 3), "-");
}

#[test]
fn test_format_tmux_session_list_under_max() {
    let sessions = vec!["main".to_string(), "debug".to_string()];
    assert_eq!(format_tmux_session_list(&sessions, 3), "main, debug");
}

#[test]
fn test_format_tmux_session_list_over_max() {
    let sessions = vec![
        "s1".to_string(),
        "s2".to_string(),
        "s3".to_string(),
        "s4".to_string(),
    ];
    let result = format_tmux_session_list(&sessions, 2);
    assert!(result.contains("s1, s2"));
    assert!(result.contains("+2 more"));
}

#[test]
fn test_format_tmux_session_list_exact_max() {
    let sessions = vec!["a".to_string(), "b".to_string()];
    assert_eq!(format_tmux_session_list(&sessions, 2), "a, b");
}

// ── Batch filter tests ──────────────────────────────────────────

#[test]
fn test_filter_vms_by_tag_no_filter() {
    let vms = vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm("vm-2", PowerState::Running),
    ];
    let filtered = filter_vms_by_tag(&vms, None);
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_filter_vms_by_tag_key_value() {
    let mut vm2 = make_test_vm("vm-2", PowerState::Running);
    vm2.tags.insert("env".to_string(), "prod".to_string());
    let vms = vec![make_test_vm("vm-1", PowerState::Running), vm2];
    let filtered = filter_vms_by_tag(&vms, Some("env=prod"));
    assert_eq!(filtered.len(), 1);
    assert_eq!(filtered[0].name, "vm-2");
}

#[test]
fn test_filter_vms_by_tag_key_only() {
    let mut vm2 = make_test_vm("vm-2", PowerState::Running);
    vm2.tags.clear();
    let vms = vec![make_test_vm("vm-1", PowerState::Running), vm2];
    let filtered = filter_vms_by_tag(&vms, Some("env"));
    assert_eq!(filtered.len(), 1);
    assert_eq!(filtered[0].name, "vm-1");
}

#[test]
fn test_filter_vms_by_tag_no_match() {
    let vms = vec![make_test_vm("vm-1", PowerState::Running)];
    let filtered = filter_vms_by_tag(&vms, Some("nonexistent=value"));
    assert_eq!(filtered.len(), 0);
}

// ── Orphan cost tests ───────────────────────────────────────────

#[test]
fn test_estimate_orphan_costs_zero() {
    let msg = estimate_orphan_costs(0, 3.65);
    assert!(msg.contains("0 orphaned"));
    assert!(msg.contains("$0.00"));
}

#[test]
fn test_estimate_orphan_costs_multiple() {
    let msg = estimate_orphan_costs(5, 3.65);
    assert!(msg.contains("5 orphaned"));
    assert!(msg.contains("$18.25"));
}

// ── Health metric classification tests ──────────────────────────

#[test]
fn test_classify_percent_ok() {
    assert_eq!(classify_percent_metric(50.0, 70.0, 90.0), Severity::Ok);
}

#[test]
fn test_classify_percent_warning() {
    assert_eq!(classify_percent_metric(75.0, 70.0, 90.0), Severity::Warning);
}

#[test]
fn test_classify_percent_critical() {
    assert_eq!(
        classify_percent_metric(95.0, 70.0, 90.0),
        Severity::Critical
    );
}

#[test]
fn test_classify_error_count_levels() {
    assert_eq!(classify_error_count(0), Severity::Ok);
    assert_eq!(classify_error_count(5), Severity::Warning);
    assert_eq!(classify_error_count(15), Severity::Critical);
}

#[test]
fn test_classify_power_state_levels() {
    assert_eq!(classify_power_state("running"), Severity::Ok);
    assert_eq!(classify_power_state("stopped"), Severity::Critical);
    assert_eq!(classify_power_state("starting"), Severity::Warning);
}

#[test]
fn test_classify_agent_status_levels() {
    assert_eq!(classify_agent_status("OK"), Severity::Ok);
    assert_eq!(classify_agent_status("Down"), Severity::Critical);
    assert_eq!(classify_agent_status("N/A"), Severity::Warning);
}

// ── Snapshot schedule formatting tests ──────────────────────────

#[test]
fn test_format_snapshot_status_output() {
    let info = SnapshotScheduleInfo {
        vm_name: "my-vm".to_string(),
        resource_group: "my-rg".to_string(),
        every_hours: 6,
        keep_count: 10,
        enabled: true,
        created: "2026-01-01".to_string(),
    };
    let out = format_snapshot_status(&info);
    assert!(out.contains("my-vm"));
    assert!(out.contains("every 6 hours"));
}

#[test]
fn test_format_snapshot_no_schedule_output() {
    let out = format_snapshot_no_schedule("missing-vm");
    assert!(out.contains("no schedule configured"));
}
