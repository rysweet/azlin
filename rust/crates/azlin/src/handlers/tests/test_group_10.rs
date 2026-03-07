use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── Cost summary formatting tests ───────────────────────────────────

#[test]
fn test_format_cost_summary_json() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let out = format_cost_summary(&summary, "json", &None, &None, false, false);
    let parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
    assert_eq!(parsed["total_cost"], 100.0);
}

#[test]
fn test_format_cost_summary_csv() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let out = format_cost_summary(&summary, "csv", &None, &None, false, false);
    assert!(out.contains("Total Cost,Currency"));
    assert!(out.contains("50.00"));
}

#[test]
fn test_format_cost_summary_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 75.50,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let out = format_cost_summary(&summary, "table", &None, &None, false, false);
    assert!(out.contains("$75.50"));
    assert!(out.contains("USD"));
}

#[test]
fn test_format_cost_summary_with_estimate() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let out = format_cost_summary(&summary, "table", &None, &None, true, false);
    assert!(out.contains("Estimate"));
    assert!(out.contains("projected"));
}

#[test]
fn test_format_cost_summary_with_filters() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let from = Some("2026-01-01".to_string());
    let to = Some("2026-01-31".to_string());
    let out = format_cost_summary(&summary, "table", &from, &to, false, false);
    assert!(out.contains("From filter: 2026-01-01"));
    assert!(out.contains("To filter: 2026-01-31"));
}

#[test]
fn test_format_cost_summary_by_vm() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "my-vm".to_string(),
            cost: 75.0,
            currency: "USD".to_string(),
        }],
    };
    let out = format_cost_summary(&summary, "table", &None, &None, false, true);
    assert!(out.contains("my-vm"));
    assert!(out.contains("$75.00"));
}

#[test]
fn test_format_cost_summary_by_vm_csv() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "my-vm".to_string(),
            cost: 75.0,
            currency: "USD".to_string(),
        }],
    };
    let out = format_cost_summary(&summary, "csv", &None, &None, false, true);
    assert!(out.contains("VM Name,Cost,Currency"));
    assert!(out.contains("my-vm,75.00,USD"));
}

#[test]
fn test_format_cost_summary_by_vm_empty() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let out = format_cost_summary(&summary, "table", &None, &None, false, true);
    assert!(out.contains("No per-VM cost data"));
}

// ── Create VM rows ──────────────────────────────────────────────────

#[test]
fn test_build_create_vm_rows() {
    let vm = make_test_vm("new-vm", PowerState::Running);
    let rows = build_create_vm_rows(&vm, "rg", "Standard_D4s_v3", "eastus");
    assert!(rows.iter().any(|(k, _)| k == "Name"));
    assert!(rows.iter().any(|(k, _)| k == "Public IP"));
}

#[test]
fn test_build_create_vm_rows_no_ip() {
    let mut vm = make_test_vm("new-vm", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let rows = build_create_vm_rows(&vm, "rg", "Standard_D4s_v3", "eastus");
    assert!(!rows.iter().any(|(k, _)| k == "Public IP"));
    assert!(!rows.iter().any(|(k, _)| k == "Private IP"));
}

// ── Doit VM filtering ───────────────────────────────────────────────

#[test]
fn test_filter_doit_vms() {
    let mut vm = make_test_vm("doit-vm", PowerState::Running);
    vm.tags
        .insert("created_by".to_string(), "azlin-doit".to_string());
    let vms = vec![vm, make_test_vm("regular-vm", PowerState::Running)];
    let filtered = filter_doit_vms(&vms, None);
    assert_eq!(filtered.len(), 1);
    assert_eq!(filtered[0].name, "doit-vm");
}

#[test]
fn test_filter_doit_vms_by_user() {
    let mut vm = make_test_vm("doit-vm", PowerState::Running);
    vm.tags
        .insert("created_by".to_string(), "azlin-doit".to_string());
    vm.admin_username = Some("testuser".to_string());
    let vms = vec![vm];
    let filtered = filter_doit_vms(&vms, Some("testuser"));
    assert_eq!(filtered.len(), 1);
    let filtered_wrong = filter_doit_vms(&vms, Some("otheruser"));
    assert!(filtered_wrong.is_empty());
}

// ── SSH connect args ────────────────────────────────────────────────

#[test]
fn test_build_ssh_connect_args_basic() {
    let args = build_ssh_connect_args("azureuser", "1.2.3.4", None, None, &[]).unwrap();
    assert!(args.contains(&"azureuser@1.2.3.4".to_string()));
    assert!(args.contains(&"-o".to_string()));
}

#[test]
fn test_build_ssh_connect_args_with_key() {
    let args = build_ssh_connect_args("azureuser", "1.2.3.4", Some("/tmp/key"), None, &[]).unwrap();
    assert!(args.contains(&"-i".to_string()));
    assert!(args.contains(&"/tmp/key".to_string()));
}

#[test]
fn test_build_ssh_connect_args_with_tmux() {
    let args = build_ssh_connect_args("azureuser", "1.2.3.4", None, Some("main"), &[]).unwrap();
    assert!(args.contains(&"-t".to_string()));
    let tmux_arg = args.iter().find(|a| a.contains("tmux")).unwrap();
    assert!(tmux_arg.contains("main"));
}

#[test]
fn test_build_ssh_connect_args_invalid_tmux() {
    let result = build_ssh_connect_args("azureuser", "1.2.3.4", None, Some("bad;name"), &[]);
    assert!(result.is_err());
}

// ── VM picker ───────────────────────────────────────────────────────

#[test]
fn test_format_vm_picker() {
    let vms = vec![
        make_test_vm("vm-a", PowerState::Running),
        make_test_vm("vm-b", PowerState::Running),
    ];
    let out = format_vm_picker(&vms);
    assert!(out.contains("[1] vm-a"));
    assert!(out.contains("[2] vm-b"));
}

// ── Extended help ───────────────────────────────────────────────────

// ── Build list JSON ─────────────────────────────────────────────────

#[test]
fn test_build_list_json() {
    let vms = vec![make_test_vm("vm1", PowerState::Running)];
    let sessions = HashMap::new();
    let json = build_list_json(&vms, &sessions);
    let arr = json.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["name"], "vm1");
}

#[test]
fn test_build_list_json_with_tmux() {
    let vms = vec![make_test_vm("vm1", PowerState::Running)];
    let mut sessions = HashMap::new();
    sessions.insert(
        "vm1".to_string(),
        vec!["main".to_string(), "dev".to_string()],
    );
    let json = build_list_json(&vms, &sessions);
    let arr = json.as_array().unwrap();
    let tmux = arr[0]["tmux_sessions"].as_array().unwrap();
    assert_eq!(tmux.len(), 2);
}

// ── Key rotation ────────────────────────────────────────────────────

#[test]
fn test_format_key_rotation_complete_msg() {
    assert!(format_key_rotation_complete().contains("complete"));
}

#[test]
fn test_format_no_contexts_msg() {
    assert!(format_no_contexts().contains("No contexts"));
}
