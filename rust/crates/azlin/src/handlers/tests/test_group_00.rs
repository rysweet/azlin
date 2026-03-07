use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── Show tests ──────────────────────────────────────────────────────

#[test]
fn test_handle_show_returns_vm() {
    let mock = MockAzureOps::new(vec![make_test_vm("dev-vm-1", PowerState::Running)]);
    let vm = handle_show(&mock, "test-rg", "dev-vm-1").unwrap();
    assert_eq!(vm.name, "dev-vm-1");
    assert_eq!(vm.power_state, PowerState::Running);
    assert!(mock.call_log().contains(&"get_vm:dev-vm-1".to_string()));
}

#[test]
fn test_handle_show_not_found() {
    let mock = MockAzureOps::new(vec![]);
    let err = handle_show(&mock, "test-rg", "nonexistent").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_format_show_table_includes_all_fields() {
    let vm = make_test_vm("dev-vm-1", PowerState::Running);
    let output = format_show_table(&vm);
    assert!(output.contains("dev-vm-1"));
    assert!(output.contains("test-rg"));
    assert!(output.contains("eastus"));
    assert!(output.contains("Standard_D4s_v3"));
    assert!(output.contains("Running"));
    assert!(output.contains("20.1.2.3"));
    assert!(output.contains("10.0.0.4"));
    assert!(output.contains("azureuser"));
    assert!(output.contains("env: dev"));
}

#[test]
fn test_format_show_table_no_optional_fields() {
    let mut vm = make_test_vm("minimal", PowerState::Stopped);
    vm.public_ip = None;
    vm.private_ip = None;
    vm.admin_username = None;
    vm.tags.clear();
    let output = format_show_table(&vm);
    assert!(output.contains("minimal"));
    assert!(!output.contains("Public IP:"));
    assert!(!output.contains("Private IP:"));
    assert!(!output.contains("Admin User:"));
    assert!(!output.contains("Tags:"));
}

#[test]
fn test_format_show_json_valid() {
    let vm = make_test_vm("json-vm", PowerState::Running);
    let json_str = format_show_json(&vm).unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
    assert_eq!(parsed["name"], "json-vm");
    assert_eq!(parsed["power_state"], "Running");
    assert_eq!(parsed["public_ip"], "20.1.2.3");
}

#[test]
fn test_format_show_csv_has_header_and_fields() {
    let vm = make_test_vm("csv-vm", PowerState::Running);
    let csv = format_show_csv(&vm);
    assert!(csv.starts_with("Field,Value\n"));
    assert!(csv.contains("name,csv-vm"));
    assert!(csv.contains("power_state,Running"));
    assert!(csv.contains("public_ip,20.1.2.3"));
}

// ── Start tests ─────────────────────────────────────────────────────

#[test]
fn test_handle_start() {
    let mock = MockAzureOps::new(vec![]);
    let msg = handle_start(&mock, "test-rg", "my-vm").unwrap();
    assert_eq!(msg, "Started my-vm");
    assert!(mock.call_log().contains(&"start_vm:my-vm".to_string()));
}

// ── Stop tests ──────────────────────────────────────────────────────

#[test]
fn test_handle_stop_no_deallocate() {
    let mock = MockAzureOps::new(vec![]);
    let msg = handle_stop(&mock, "test-rg", "my-vm", false).unwrap();
    assert_eq!(msg, "Stopped my-vm");
    assert!(mock
        .call_log()
        .contains(&"stop_vm:my-vm:dealloc=false".to_string()));
}

#[test]
fn test_handle_stop_deallocate() {
    let mock = MockAzureOps::new(vec![]);
    let msg = handle_stop(&mock, "test-rg", "my-vm", true).unwrap();
    assert_eq!(msg, "Deallocated my-vm");
    assert!(mock
        .call_log()
        .contains(&"stop_vm:my-vm:dealloc=true".to_string()));
}

// ── Delete tests ────────────────────────────────────────────────────

#[test]
fn test_handle_delete() {
    let mock = MockAzureOps::new(vec![]);
    let msg = handle_delete(&mock, "test-rg", "doomed-vm").unwrap();
    assert_eq!(msg, "Deleted doomed-vm");
    assert!(mock.call_log().contains(&"delete_vm:doomed-vm".to_string()));
}

// ── Tag tests ───────────────────────────────────────────────────────

#[test]
fn test_handle_tag_add_single() {
    let mock = MockAzureOps::new(vec![]);
    let tags = vec![("env".to_string(), "prod".to_string())];
    let msgs = handle_tag_add(&mock, "test-rg", "my-vm", &tags).unwrap();
    assert_eq!(msgs.len(), 1);
    assert!(msgs[0].contains("env=prod"));
    assert!(mock
        .call_log()
        .contains(&"add_tag:my-vm:env=prod".to_string()));
}

#[test]
fn test_handle_tag_add_multiple() {
    let mock = MockAzureOps::new(vec![]);
    let tags = vec![
        ("env".to_string(), "prod".to_string()),
        ("team".to_string(), "infra".to_string()),
    ];
    let msgs = handle_tag_add(&mock, "test-rg", "my-vm", &tags).unwrap();
    assert_eq!(msgs.len(), 2);
}

#[test]
fn test_handle_tag_remove() {
    let mock = MockAzureOps::new(vec![]);
    let keys = vec!["env".to_string(), "team".to_string()];
    let msgs = handle_tag_remove(&mock, "test-rg", "my-vm", &keys).unwrap();
    assert_eq!(msgs.len(), 2);
    assert!(msgs[0].contains("env"));
    assert!(msgs[1].contains("team"));
}

#[test]
fn test_handle_tag_list() {
    let mock = MockAzureOps::new(vec![make_test_vm("tagged-vm", PowerState::Running)]);
    let tags = handle_tag_list(&mock, "test-rg", "tagged-vm").unwrap();
    assert_eq!(tags.get("env").unwrap(), "dev");
}

// ── Status tests ────────────────────────────────────────────────────

#[test]
fn test_handle_status_all_vms() {
    let mock = MockAzureOps::new(vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm_stopped("vm-2"),
    ]);
    let rows = handle_status(&mock, "test-rg", None).unwrap();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].name, "vm-1");
    assert_eq!(rows[0].power_state, "Running");
    assert_eq!(rows[1].name, "vm-2");
    assert_eq!(rows[1].power_state, "Deallocated");
}

#[test]
fn test_handle_status_single_vm() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let rows = handle_status(&mock, "test-rg", Some("vm-1")).unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].name, "vm-1");
}

// ── List fetch tests ────────────────────────────────────────────────

#[test]
fn test_fetch_list_vms_with_rg() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let vms = fetch_list_vms(&mock, Some("test-rg"), false, false, None).unwrap();
    assert_eq!(vms.len(), 1);
    assert!(mock.call_log().contains(&"list_vms".to_string()));
}

#[test]
fn test_fetch_list_vms_no_cache() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let _vms = fetch_list_vms(&mock, Some("test-rg"), false, true, None).unwrap();
    assert!(mock.call_log().contains(&"list_vms_no_cache".to_string()));
}

#[test]
fn test_fetch_list_vms_show_all() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let _vms = fetch_list_vms(&mock, None, true, false, None).unwrap();
    assert!(mock.call_log().contains(&"list_all_vms".to_string()));
}

#[test]
fn test_fetch_list_vms_show_all_no_cache() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let _vms = fetch_list_vms(&mock, None, true, true, None).unwrap();
    assert!(mock
        .call_log()
        .contains(&"list_all_vms_no_cache".to_string()));
}

#[test]
fn test_fetch_list_vms_default_rg() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let vms = fetch_list_vms(&mock, None, false, false, Some("default-rg")).unwrap();
    assert_eq!(vms.len(), 1);
}

#[test]
fn test_fetch_list_vms_no_rg_errors() {
    let mock = MockAzureOps::new(vec![]);
    let err = fetch_list_vms(&mock, None, false, false, None).unwrap_err();
    assert!(err.to_string().contains("No resource group"));
}
