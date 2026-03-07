use crate::*;
use std::fs;
use tempfile::TempDir;

// ── runner_helpers ──────────────────────────────────────────────

#[test]
fn test_build_runner_vm_name_zero_index() {
    assert_eq!(
        crate::runner_helpers::build_runner_vm_name("dev", 0),
        "azlin-runner-dev-1"
    );
}

#[test]
fn test_build_runner_vm_name_multiple_index() {
    assert_eq!(
        crate::runner_helpers::build_runner_vm_name("ci", 4),
        "azlin-runner-ci-5"
    );
}

#[test]
fn test_runner_tags_contains_all_parts() {
    let tags = crate::runner_helpers::build_runner_tags("ci-pool", "org/repo");
    assert!(tags.contains("azlin-runner=true"));
    assert!(tags.contains("pool=ci-pool"));
    assert!(tags.contains("repo=org/repo"));
}

#[test]
fn test_build_runner_config_structure() {
    let config = crate::runner_helpers::build_runner_config(
        "my-pool",
        "org/repo",
        3,
        "self-hosted,linux",
        "my-rg",
        "Standard_D2s_v3",
        "2025-01-01",
    );
    let map: std::collections::HashMap<String, toml::Value> = config.into_iter().collect();
    assert_eq!(
        map.get("pool").unwrap(),
        &toml::Value::String("my-pool".to_string())
    );
    assert_eq!(map.get("count").unwrap(), &toml::Value::Integer(3));
    assert_eq!(map.get("enabled").unwrap(), &toml::Value::Boolean(true));
}

#[test]
fn test_pool_config_filename_toml_extension() {
    assert_eq!(
        crate::runner_helpers::pool_config_filename("dev"),
        "dev.toml"
    );
    assert_eq!(
        crate::runner_helpers::pool_config_filename("ci-pool"),
        "ci-pool.toml"
    );
}

// ── autopilot_helpers ───────────────────────────────────────────

#[test]
fn test_autopilot_config_budget_present_and_fields() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        Some(500),
        "conservative",
        30,
        10,
        "2025-01-01T00:00:00Z",
    );
    let table = config.as_table().unwrap();
    assert_eq!(table["budget"].as_integer().unwrap(), 500);
    assert_eq!(table["strategy"].as_str().unwrap(), "conservative");
    assert_eq!(table["idle_threshold_minutes"].as_integer().unwrap(), 30);
    assert_eq!(table["cpu_threshold_percent"].as_integer().unwrap(), 10);
    assert!(table["enabled"].as_bool().unwrap());
}

#[test]
fn test_autopilot_config_no_budget_omits_key() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        None,
        "aggressive",
        15,
        5,
        "2025-06-01T00:00:00Z",
    );
    let table = config.as_table().unwrap();
    assert!(!table.contains_key("budget"));
    assert_eq!(table["strategy"].as_str().unwrap(), "aggressive");
}

#[test]
fn test_build_budget_name_format() {
    assert_eq!(
        crate::autopilot_helpers::build_budget_name("prod-rg"),
        "azlin-budget-prod-rg"
    );
}

#[test]
fn test_build_prefix_filter_query_format() {
    assert_eq!(
        crate::autopilot_helpers::build_prefix_filter_query("dev-"),
        "[?starts_with(name, 'dev-')].id"
    );
}

#[test]
fn test_build_cost_scope_format() {
    assert_eq!(
        crate::autopilot_helpers::build_cost_scope("sub-123", "my-rg"),
        "/subscriptions/sub-123/resourceGroups/my-rg"
    );
}

// ── autopilot_parse_helpers ─────────────────────────────────────

#[test]
fn test_parse_idle_check_valid_input() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("2.5\n3600.0");
    assert!((cpu - 2.5).abs() < f64::EPSILON);
    assert!((uptime - 3600.0).abs() < f64::EPSILON);
}

#[test]
fn test_parse_idle_check_empty_input() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("");
    assert!((cpu - 100.0).abs() < f64::EPSILON); // defaults to 100
    assert!((uptime - 0.0).abs() < f64::EPSILON);
}

#[test]
fn test_idle_parse_single_line_only() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("50.0");
    assert!((cpu - 50.0).abs() < f64::EPSILON);
    assert!((uptime - 0.0).abs() < f64::EPSILON);
}

#[test]
fn test_is_idle_low_cpu_long_uptime() {
    assert!(crate::autopilot_parse_helpers::is_idle(1.0, 7200.0, 60));
}

#[test]
fn test_idle_check_high_cpu_not_idle() {
    assert!(!crate::autopilot_parse_helpers::is_idle(50.0, 7200.0, 60));
}

#[test]
fn test_idle_check_short_uptime_not_idle() {
    assert!(!crate::autopilot_parse_helpers::is_idle(1.0, 100.0, 60));
}

#[test]
fn test_is_idle_boundary_cpu_exactly_5() {
    // cpu_pct < 5.0 is the check, so 5.0 should NOT be idle
    assert!(!crate::autopilot_parse_helpers::is_idle(5.0, 7200.0, 60));
}

#[test]
fn test_is_idle_boundary_uptime_exactly_threshold() {
    // uptime must be > threshold * 60, so exactly equal should NOT be idle
    assert!(!crate::autopilot_parse_helpers::is_idle(1.0, 3600.0, 60));
}

// ── batch_helpers ───────────────────────────────────────────────

#[test]
fn test_parse_vm_ids_normal_input() {
    let ids = crate::batch_helpers::parse_vm_ids("/sub/rg/vm1\n/sub/rg/vm2\n");
    assert_eq!(ids, vec!["/sub/rg/vm1", "/sub/rg/vm2"]);
}

#[test]
fn test_parse_vm_ids_empty_string() {
    let ids = crate::batch_helpers::parse_vm_ids("");
    assert!(ids.is_empty());
}

#[test]
fn test_parse_vm_ids_blank_lines_filtered() {
    let ids = crate::batch_helpers::parse_vm_ids("/sub/rg/vm1\n\n\n/sub/rg/vm2\n");
    assert_eq!(ids.len(), 2);
}

#[test]
fn test_batch_args_start_format() {
    let ids = vec!["/sub/rg/vm1", "/sub/rg/vm2"];
    let args = crate::batch_helpers::build_batch_args("start", &ids);
    assert_eq!(
        args,
        vec!["vm", "start", "--ids", "/sub/rg/vm1", "/sub/rg/vm2"]
    );
}

#[test]
fn test_build_vm_list_query_no_tag_returns_all() {
    assert_eq!(
        crate::batch_helpers::build_vm_list_query(None).unwrap(),
        "[].id"
    );
}

#[test]
fn test_build_vm_list_query_with_valid_tag() {
    assert_eq!(
        crate::batch_helpers::build_vm_list_query(Some("env=prod")).unwrap(),
        "[?tags.env=='prod'].id"
    );
}

#[test]
fn test_build_vm_list_query_injection_rejected() {
    assert!(crate::batch_helpers::build_vm_list_query(Some("env=prod';--")).is_err());
}

#[test]
fn test_summarise_batch_success_message() {
    let msg = crate::batch_helpers::summarise_batch("deallocate", "my-rg", true);
    assert!(msg.contains("deallocate"));
    assert!(msg.contains("my-rg"));
    assert!(msg.contains("completed"));
}

#[test]
fn test_summarise_batch_failure_message() {
    let msg = crate::batch_helpers::summarise_batch("start", "prod-rg", false);
    assert!(msg.contains("failed"));
}
