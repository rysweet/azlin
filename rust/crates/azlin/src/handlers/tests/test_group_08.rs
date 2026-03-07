use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── Costs handler tests ─────────────────────────────────────────────

#[test]
fn test_format_cost_history_header() {
    let out = format_cost_history_header("my-rg", 30);
    assert!(out.contains("my-rg"));
    assert!(out.contains("30 days"));
}

#[test]
fn test_format_no_recommendations() {
    let out = format_no_recommendations("my-rg", "High");
    assert!(out.contains("my-rg"));
    assert!(out.contains("High"));
}

#[test]
fn test_format_no_budgets() {
    let out = format_no_budgets("my-rg");
    assert!(out.contains("No budgets"));
    assert!(out.contains("my-rg"));
}

#[test]
fn test_format_budget_deleted_msg() {
    let out = format_budget_deleted("my-rg");
    assert!(out.contains("Budget deleted"));
}

#[test]
fn test_format_cost_actions_header_dry_run() {
    let out = format_cost_actions_header("apply", "my-rg", true);
    assert!(out.contains("Would apply"));
}

#[test]
fn test_format_cost_actions_header_live() {
    let out = format_cost_actions_header("apply", "my-rg", false);
    assert!(out.contains("Cost actions (apply)"));
}

#[test]
fn test_build_advisor_args_no_priority() {
    let args = build_advisor_args("my-rg", None);
    assert!(args.contains(&"my-rg".to_string()));
    assert!(!args.contains(&"--query".to_string()));
}

#[test]
fn test_build_advisor_args_with_priority() {
    let args = build_advisor_args("my-rg", Some("High"));
    assert!(args.contains(&"--query".to_string()));
    let query_idx = args.iter().position(|a| a == "--query").unwrap();
    assert!(args[query_idx + 1].contains("High"));
}

// ── Cleanup/orphan tests ────────────────────────────────────────────

#[test]
fn test_find_orphaned_nics_mixed() {
    let nics = vec![
        serde_json::json!({
            "name": "orphan-nic",
            "resourceGroup": "rg1",
            "virtualMachine": null
        }),
        serde_json::json!({
            "name": "attached-nic",
            "resourceGroup": "rg1",
            "virtualMachine": {"id": "/some/vm"}
        }),
    ];
    let orphans = find_orphaned_nics(&nics);
    assert_eq!(orphans.len(), 1);
    assert_eq!(orphans[0].name, "orphan-nic");
    assert_eq!(orphans[0].resource_type, "NetworkInterface");
}

#[test]
fn test_find_orphaned_nics_empty() {
    let orphans = find_orphaned_nics(&[]);
    assert!(orphans.is_empty());
}

#[test]
fn test_find_orphaned_public_ips() {
    let ips = vec![
        serde_json::json!({
            "name": "orphan-ip",
            "resourceGroup": "rg1",
            "ipConfiguration": null
        }),
        serde_json::json!({
            "name": "used-ip",
            "resourceGroup": "rg1",
            "ipConfiguration": {"id": "/some/config"}
        }),
    ];
    let orphans = find_orphaned_public_ips(&ips, 3.65);
    assert_eq!(orphans.len(), 1);
    assert_eq!(orphans[0].name, "orphan-ip");
    assert_eq!(orphans[0].estimated_monthly_cost, 3.65);
}

#[test]
fn test_find_orphaned_nsgs() {
    let nsgs = vec![
        serde_json::json!({
            "name": "orphan-nsg",
            "resourceGroup": "rg1",
            "networkInterfaces": [],
            "subnets": []
        }),
        serde_json::json!({
            "name": "used-nsg",
            "resourceGroup": "rg1",
            "networkInterfaces": [{"id": "/some/nic"}],
            "subnets": []
        }),
    ];
    let orphans = find_orphaned_nsgs(&nsgs);
    assert_eq!(orphans.len(), 1);
    assert_eq!(orphans[0].name, "orphan-nsg");
    assert_eq!(orphans[0].resource_type, "NetworkSecurityGroup");
}

#[test]
fn test_find_orphaned_nsgs_with_subnets() {
    let nsgs = vec![serde_json::json!({
        "name": "subnet-nsg",
        "resourceGroup": "rg1",
        "networkInterfaces": [],
        "subnets": [{"id": "/some/subnet"}]
    })];
    let orphans = find_orphaned_nsgs(&nsgs);
    assert!(orphans.is_empty());
}

#[test]
fn test_format_cleanup_complete() {
    let out = format_cleanup_complete(3, 5);
    assert!(out.contains("3/5"));
}

#[test]
fn test_format_cleanup_scan_header_dry_run() {
    let out = format_cleanup_scan_header("rg1", 30, true);
    assert!(out.contains("Dry run"));
    assert!(out.contains("rg1"));
    assert!(out.contains("30 days"));
}

#[test]
fn test_format_cleanup_scan_header_live() {
    let out = format_cleanup_scan_header("rg1", 30, false);
    assert!(!out.contains("Dry run"));
}

// ── Autopilot handler tests ─────────────────────────────────────────

#[test]
fn test_build_autopilot_config() {
    let val = build_autopilot_config(Some(100), "conservative", 30, 10, "2026-01-01T00:00:00Z");
    let t = val.as_table().unwrap();
    assert_eq!(t["enabled"].as_bool(), Some(true));
    assert_eq!(t["budget"].as_integer(), Some(100));
    assert_eq!(t["strategy"].as_str(), Some("conservative"));
    assert_eq!(t["idle_threshold_minutes"].as_integer(), Some(30));
    assert_eq!(t["cpu_threshold_percent"].as_integer(), Some(10));
}

#[test]
fn test_build_autopilot_config_no_budget() {
    let val = build_autopilot_config(None, "aggressive", 60, 5, "2026-01-01T00:00:00Z");
    let t = val.as_table().unwrap();
    assert!(!t.contains_key("budget"));
}

#[test]
fn test_format_autopilot_enabled_with_budget() {
    let out = format_autopilot_enabled(Some(200), "conservative", 30, 10);
    assert!(out.contains("$200/month"));
    assert!(out.contains("conservative"));
    assert!(out.contains("30 min"));
    assert!(out.contains("10%"));
}

#[test]
fn test_format_autopilot_enabled_no_budget() {
    let out = format_autopilot_enabled(None, "aggressive", 60, 5);
    assert!(!out.contains("Budget"));
}

#[test]
fn test_format_autopilot_status_enabled() {
    let val: toml::Value = toml::from_str(
        r#"
        enabled = true
        strategy = "conservative"
        idle_threshold_minutes = 30
        "#,
    )
    .unwrap();
    let out = format_autopilot_status(Some(&val));
    assert!(out.contains("ENABLED"));
    assert!(out.contains("conservative"));
}

#[test]
fn test_format_autopilot_status_disabled() {
    let val: toml::Value = toml::from_str("enabled = false").unwrap();
    let out = format_autopilot_status(Some(&val));
    assert!(out.contains("DISABLED"));
}

#[test]
fn test_format_autopilot_status_none() {
    let out = format_autopilot_status(None);
    assert!(out.contains("not configured"));
}

#[test]
fn test_parse_autopilot_thresholds_with_config() {
    let val: toml::Value = toml::from_str(
        r#"
        idle_threshold_minutes = 45
        cost_limit_usd = 50.0
        "#,
    )
    .unwrap();
    let (thresh, limit) = parse_autopilot_thresholds(Some(&val));
    assert_eq!(thresh, 45);
    assert!((limit - 50.0).abs() < f64::EPSILON);
}

#[test]
fn test_parse_autopilot_thresholds_defaults() {
    let (thresh, limit) = parse_autopilot_thresholds(None);
    assert_eq!(thresh, 30);
    assert!((limit - 0.0).abs() < f64::EPSILON);
}

#[test]
fn test_classify_autopilot_vm_idle() {
    let action = classify_autopilot_vm(2.0, 3600.0, 30);
    assert_eq!(action, Some("deallocate".to_string()));
}

#[test]
fn test_classify_autopilot_vm_active() {
    let action = classify_autopilot_vm(50.0, 3600.0, 30);
    assert!(action.is_none());
}

#[test]
fn test_classify_autopilot_vm_low_cpu_short_uptime() {
    // Low CPU but uptime below threshold — should NOT recommend action
    let action = classify_autopilot_vm(2.0, 60.0, 30);
    assert!(action.is_none());
}

#[test]
fn test_format_autopilot_dry_run() {
    let actions = vec![
        ("vm1".to_string(), "deallocate".to_string()),
        ("vm2".to_string(), "deallocate".to_string()),
    ];
    let out = format_autopilot_dry_run(&actions);
    assert!(out.contains("2 action(s)"));
    assert!(out.contains("vm1"));
    assert!(out.contains("vm2"));
}
