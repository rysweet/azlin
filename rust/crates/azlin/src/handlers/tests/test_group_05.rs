use super::super::*;
use super::common::*;
use azlin_core::models::PowerState;

// ── Cost summary formatting tests ───────────────────────────────

fn make_cost_summary() -> azlin_core::models::CostSummary {
    azlin_core::models::CostSummary {
        total_cost: 123.45,
        currency: "USD".to_string(),
        period_start: chrono::NaiveDate::from_ymd_opt(2026, 1, 1)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        period_end: chrono::NaiveDate::from_ymd_opt(2026, 1, 31)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        by_vm: vec![],
    }
}

#[test]
fn test_cost_summary_table() {
    let s = make_cost_summary();
    let out = format_cost_summary(&s, "table", &None, &None, false, false);
    assert!(out.contains("$123.45"));
    assert!(out.contains("USD"));
}

#[test]
fn test_cost_summary_json() {
    let s = make_cost_summary();
    let out = format_cost_summary(&s, "json", &None, &None, false, false);
    let _parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
}

#[test]
fn test_cost_summary_csv() {
    let s = make_cost_summary();
    let out = format_cost_summary(&s, "csv", &None, &None, false, false);
    assert!(out.starts_with("Total Cost,Currency"));
}

#[test]
fn test_cost_summary_with_estimate() {
    let s = make_cost_summary();
    let out = format_cost_summary(&s, "table", &None, &None, true, false);
    assert!(out.contains("Estimate:"));
}

#[test]
fn test_cost_summary_with_filters() {
    let s = make_cost_summary();
    let out = format_cost_summary(
        &s,
        "table",
        &Some("2026-01-01".to_string()),
        &Some("2026-01-15".to_string()),
        false,
        false,
    );
    assert!(out.contains("From filter:"));
    assert!(out.contains("To filter:"));
}

#[test]
fn test_cost_summary_by_vm() {
    let mut s = make_cost_summary();
    s.by_vm = vec![azlin_core::models::VmCost {
        vm_name: "vm-1".to_string(),
        cost: 50.0,
        currency: "USD".to_string(),
    }];
    let out = format_cost_summary(&s, "table", &None, &None, false, true);
    assert!(out.contains("vm-1"));
    assert!(out.contains("$50.00"));
}

#[test]
fn test_cost_summary_by_vm_empty() {
    let s = make_cost_summary();
    let out = format_cost_summary(&s, "table", &None, &None, false, true);
    assert!(out.contains("No per-VM cost data"));
}

// ── Cost data parsing tests ─────────────────────────────────────

#[test]
fn test_parse_cost_history_rows_basic() {
    let data = serde_json::json!({"rows": [[42.5, "2026-01-01"]]});
    let rows = parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].1, "$42.50");
}

#[test]
fn test_parse_cost_history_rows_empty() {
    let data = serde_json::json!({"rows": []});
    assert!(parse_cost_history_rows(&data).is_empty());
}

#[test]
fn test_parse_recommendation_rows_basic() {
    let data = serde_json::json!([{
        "category": "Cost",
        "impact": "High",
        "shortDescription": {"problem": "Unused VM"}
    }]);
    let rows = parse_recommendation_rows(&data);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].2, "Unused VM");
}

#[test]
fn test_parse_recommendation_rows_empty() {
    assert!(parse_recommendation_rows(&serde_json::json!([])).is_empty());
}

#[test]
fn test_parse_cost_action_rows_basic() {
    let data = serde_json::json!([{
        "impactedField": "VMs",
        "impact": "Medium",
        "shortDescription": {"problem": "Resize"}
    }]);
    let rows = parse_cost_action_rows(&data);
    assert_eq!(rows[0].0, "VMs");
}

// ── Create VM result formatting tests ───────────────────────────

#[test]
fn test_build_create_vm_rows_basic() {
    let vm = make_test_vm("new-vm", PowerState::Running);
    let rows = build_create_vm_rows(&vm, "rg", "Standard_D4s_v3", "eastus");
    assert!(rows.iter().any(|(k, v)| k == "Name" && v == "new-vm"));
    assert!(rows.iter().any(|(k, _)| k == "Public IP"));
}

#[test]
fn test_build_create_vm_rows_no_ips() {
    let mut vm = make_test_vm("bare", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let rows = build_create_vm_rows(&vm, "rg", "D2s", "westus");
    assert_eq!(rows.len(), 5);
}

// ── Doit VM filter tests ────────────────────────────────────────

#[test]
fn test_filter_doit_vms_with_tag() {
    let mut vm1 = make_test_vm("doit-vm", PowerState::Running);
    vm1.tags
        .insert("created_by".to_string(), "azlin-doit".to_string());
    let vm2 = make_test_vm("regular-vm", PowerState::Running);
    let vms = vec![vm1, vm2];
    let filtered = filter_doit_vms(&vms, None);
    assert_eq!(filtered.len(), 1);
    assert_eq!(filtered[0].name, "doit-vm");
}

#[test]
fn test_filter_doit_vms_by_username() {
    let mut vm1 = make_test_vm("doit-1", PowerState::Running);
    vm1.tags
        .insert("created_by".to_string(), "azlin-doit".to_string());
    vm1.admin_username = Some("alice".to_string());
    let mut vm2 = make_test_vm("doit-2", PowerState::Running);
    vm2.tags
        .insert("created_by".to_string(), "azlin-doit".to_string());
    vm2.admin_username = Some("bob".to_string());
    let vms = vec![vm1, vm2];
    let filtered = filter_doit_vms(&vms, Some("alice"));
    assert_eq!(filtered.len(), 1);
}

#[test]
fn test_filter_doit_vms_none_match() {
    let vms = vec![make_test_vm("regular-vm", PowerState::Running)];
    let filtered = filter_doit_vms(&vms, None);
    assert!(filtered.is_empty());
}

// ── SSH args building tests ─────────────────────────────────────

#[test]
fn test_ssh_connect_args_basic() {
    let args = build_ssh_connect_args("user", "1.2.3.4", None, None, &[]).unwrap();
    assert!(args.contains(&"user@1.2.3.4".to_string()));
}

#[test]
fn test_ssh_connect_args_with_key() {
    let args = build_ssh_connect_args("user", "1.2.3.4", Some("/tmp/key"), None, &[]).unwrap();
    assert!(args.contains(&"-i".to_string()));
}

#[test]
fn test_ssh_connect_args_with_tmux() {
    let args = build_ssh_connect_args("user", "1.2.3.4", None, Some("azlin"), &[]).unwrap();
    assert!(args.contains(&"-t".to_string()));
}

#[test]
fn test_ssh_connect_args_invalid_tmux() {
    let err = build_ssh_connect_args("user", "1.2.3.4", None, Some("bad;name"), &[]).unwrap_err();
    assert!(err.to_string().contains("Invalid tmux"));
}

// ── VM picker formatting tests ──────────────────────────────────

#[test]
fn test_format_vm_picker_basic() {
    let vms = vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm("vm-2", PowerState::Running),
    ];
    let out = format_vm_picker(&vms);
    assert!(out.contains("[1] vm-1"));
    assert!(out.contains("[2] vm-2"));
}

#[test]
fn test_format_vm_picker_no_ip() {
    let mut vm = make_test_vm("no-ip", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let out = format_vm_picker(&[vm]);
    assert!(out.contains("no-ip (-)"));
}

// ── Help handler tests ──────────────────────────────────────────

#[test]
fn test_build_extended_help_with_command() {
    let out = build_extended_help(Some("list"));
    assert!(out.contains("azlin list"));
    assert!(out.contains("Extended help"));
    assert!(out.contains("--help"));
}

#[test]
fn test_build_extended_help_general() {
    let out = build_extended_help(None);
    assert!(out.contains("azlin"));
    assert!(out.contains("Azure VM fleet management CLI"));
    assert!(out.contains("<command> --help"));
    assert!(out.contains("completions bash"));
    assert!(out.contains("completions zsh"));
    assert!(out.contains("completions fish"));
}
