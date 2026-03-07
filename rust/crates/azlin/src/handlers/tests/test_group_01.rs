use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── List filter tests ───────────────────────────────────────────────

#[test]
fn test_filter_removes_stopped_by_default() {
    let mut vms = vec![
        make_test_vm("running-vm", PowerState::Running),
        make_test_vm_stopped("stopped-vm"),
    ];
    filter_list_vms(&mut vms, false, None, None);
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "running-vm");
}

#[test]
fn test_filter_includes_stopped_when_all() {
    let mut vms = vec![
        make_test_vm("running-vm", PowerState::Running),
        make_test_vm_stopped("stopped-vm"),
    ];
    filter_list_vms(&mut vms, true, None, None);
    assert_eq!(vms.len(), 2);
}

#[test]
fn test_filter_by_tag_key_value() {
    let mut vms = vec![make_test_vm("vm-1", PowerState::Running), {
        let mut vm = make_test_vm("vm-2", PowerState::Running);
        vm.tags.insert("env".to_string(), "prod".to_string());
        vm
    }];
    filter_list_vms(&mut vms, true, Some("env=prod"), None);
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm-2");
}

#[test]
fn test_filter_by_tag_key_only() {
    let mut vms = vec![make_test_vm("vm-1", PowerState::Running), {
        let mut vm = make_test_vm("vm-2", PowerState::Running);
        vm.tags.clear();
        vm
    }];
    filter_list_vms(&mut vms, true, Some("env"), None);
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm-1");
}

#[test]
fn test_filter_by_pattern() {
    let mut vms = vec![
        make_test_vm("dev-vm-1", PowerState::Running),
        make_test_vm("prod-vm-1", PowerState::Running),
    ];
    filter_list_vms(&mut vms, true, None, Some("dev"));
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "dev-vm-1");
}

#[test]
fn test_filter_by_pattern_case_insensitive() {
    let mut vms = vec![
        make_test_vm("DEV-VM-1", PowerState::Running),
        make_test_vm("prod-vm-1", PowerState::Running),
    ];
    filter_list_vms(&mut vms, true, None, Some("dev"));
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "DEV-VM-1");
}

#[test]
fn test_filter_combined() {
    let mut vms = vec![
        make_test_vm("dev-vm-1", PowerState::Running),
        make_test_vm("dev-vm-2", PowerState::Running),
        make_test_vm("prod-vm-1", PowerState::Running),
        make_test_vm_stopped("dev-vm-3"),
    ];
    // Only running + name contains "dev"
    filter_list_vms(&mut vms, false, None, Some("dev"));
    assert_eq!(vms.len(), 2);
    assert!(vms.iter().all(|v| v.name.contains("dev")));
}

// ── List JSON format tests ──────────────────────────────────────────

#[test]
fn test_format_list_json_basic() {
    let vms = vec![make_test_vm("vm-1", PowerState::Running)];
    let tmux = HashMap::new();
    let json_str = format_list_json(&vms, &tmux).unwrap();
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
    assert_eq!(parsed.len(), 1);
    assert_eq!(parsed[0]["name"], "vm-1");
    assert_eq!(parsed[0]["power_state"], "Running");
    assert_eq!(parsed[0]["ip"], "20.1.2.3");
}

#[test]
fn test_format_list_json_with_tmux() {
    let vms = vec![make_test_vm("vm-1", PowerState::Running)];
    let mut tmux = HashMap::new();
    tmux.insert(
        "vm-1".to_string(),
        vec!["main".to_string(), "debug".to_string()],
    );
    let json_str = format_list_json(&vms, &tmux).unwrap();
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
    let sessions = parsed[0]["tmux_sessions"].as_array().unwrap();
    assert_eq!(sessions.len(), 2);
}

// ── IP display tests ────────────────────────────────────────────────

#[test]
fn test_format_ip_display_public() {
    assert_eq!(
        format_ip_display(Some("1.2.3.4"), Some("10.0.0.1")),
        "1.2.3.4"
    );
}

#[test]
fn test_format_ip_display_private_only() {
    assert_eq!(format_ip_display(None, Some("10.0.0.1")), "(10.0.0.1)");
}

#[test]
fn test_format_ip_display_none() {
    assert_eq!(format_ip_display(None, None), "-");
}

// ── Connect tests ───────────────────────────────────────────────────

#[test]
fn test_resolve_connect_explicit_vm() {
    let mock = MockAzureOps::new(vec![make_test_vm("my-vm", PowerState::Running)]);
    let target = resolve_connect_target(&mock, "test-rg", Some("my-vm"), "azureuser").unwrap();
    match target {
        ConnectTarget::Resolved {
            vm_name,
            ip,
            username,
        } => {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(ip, "20.1.2.3");
            assert_eq!(username, "azureuser");
        }
        _ => panic!("Expected Resolved"),
    }
}

#[test]
fn test_resolve_connect_single_running() {
    let mock = MockAzureOps::new(vec![make_test_vm("only-vm", PowerState::Running)]);
    let target = resolve_connect_target(&mock, "test-rg", None, "azureuser").unwrap();
    match target {
        ConnectTarget::Resolved { vm_name, .. } => assert_eq!(vm_name, "only-vm"),
        _ => panic!("Expected Resolved"),
    }
}

#[test]
fn test_resolve_connect_multiple_running_needs_selection() {
    let mock = MockAzureOps::new(vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm("vm-2", PowerState::Running),
    ]);
    let target = resolve_connect_target(&mock, "test-rg", None, "azureuser").unwrap();
    match target {
        ConnectTarget::NeedsSelection(choices) => {
            assert_eq!(choices.len(), 2);
            assert_eq!(choices[0].0, "vm-1");
            assert_eq!(choices[1].0, "vm-2");
        }
        _ => panic!("Expected NeedsSelection"),
    }
}

#[test]
fn test_resolve_connect_no_running_vms() {
    let mock = MockAzureOps::new(vec![make_test_vm_stopped("stopped-vm")]);
    let err = resolve_connect_target(&mock, "test-rg", None, "azureuser").unwrap_err();
    assert!(err.to_string().contains("No running VMs"));
}

#[test]
fn test_resolve_connect_private_ip_fallback() {
    let mock = MockAzureOps::new(vec![make_test_vm_private("priv-vm")]);
    let target = resolve_connect_target(&mock, "test-rg", Some("priv-vm"), "azureuser").unwrap();
    match target {
        ConnectTarget::Resolved { ip, .. } => assert_eq!(ip, "10.0.0.4"),
        _ => panic!("Expected Resolved"),
    }
}

#[test]
fn test_resolve_connect_no_ip() {
    let mut vm = make_test_vm("no-ip-vm", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let mock = MockAzureOps::new(vec![vm]);
    let err = resolve_connect_target(&mock, "test-rg", Some("no-ip-vm"), "azureuser").unwrap_err();
    assert!(err.to_string().contains("No IP address"));
}

// ── Health target tests ─────────────────────────────────────────────

#[test]
fn test_resolve_health_targets_all() {
    let mock = MockAzureOps::new(vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm_stopped("vm-2"),
    ]);
    let targets = resolve_health_targets(&mock, "test-rg", None).unwrap();
    // vm-2 has no IP after make_test_vm_stopped sets public_ip = None,
    // but still has private_ip, so it will be included
    assert!(targets.len() >= 1);
    assert_eq!(targets[0].0, "vm-1");
}

#[test]
fn test_resolve_health_targets_single() {
    let mock = MockAzureOps::new(vec![make_test_vm("health-vm", PowerState::Running)]);
    let targets = resolve_health_targets(&mock, "test-rg", Some("health-vm")).unwrap();
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0].0, "health-vm");
    assert_eq!(targets[0].1, "20.1.2.3"); // public IP
    assert_eq!(targets[0].2, "azureuser");
}

// ── OsUpdate target tests ───────────────────────────────────────────

#[test]
fn test_resolve_os_update_target() {
    let mock = MockAzureOps::new(vec![make_test_vm("update-vm", PowerState::Running)]);
    let (ip, user) = resolve_os_update_target(&mock, "test-rg", "update-vm").unwrap();
    assert_eq!(ip, "20.1.2.3");
    assert_eq!(user, "azureuser");
}

#[test]
fn test_resolve_os_update_target_no_ip() {
    let mut vm = make_test_vm("no-ip", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let mock = MockAzureOps::new(vec![vm]);
    let err = resolve_os_update_target(&mock, "test-rg", "no-ip").unwrap_err();
    assert!(err.to_string().contains("No IP found"));
}

// ── Destroy dry-run tests ───────────────────────────────────────────

#[test]
fn test_format_destroy_dry_run() {
    let output = format_destroy_dry_run("my-vm", "my-rg");
    assert!(output.contains("my-vm"));
    assert!(output.contains("my-rg"));
    assert!(output.contains("Dry run"));
}
