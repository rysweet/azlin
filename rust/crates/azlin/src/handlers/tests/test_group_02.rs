use super::super::*;
use super::common::*;
use azlin_core::models::PowerState;

// ── Code target tests ───────────────────────────────────────────────

#[test]
fn test_resolve_code_target() {
    let mock = MockAzureOps::new(vec![make_test_vm("code-vm", PowerState::Running)]);
    let (ip, user) = resolve_code_target(&mock, "test-rg", "code-vm", "azureuser").unwrap();
    assert_eq!(ip, "20.1.2.3");
    assert_eq!(user, "azureuser");
}

#[test]
fn test_resolve_code_target_private_ip() {
    let mock = MockAzureOps::new(vec![make_test_vm_private("priv-vm")]);
    let (ip, _user) = resolve_code_target(&mock, "test-rg", "priv-vm", "azureuser").unwrap();
    assert_eq!(ip, "10.0.0.4");
}

#[test]
fn test_resolve_code_target_no_ip() {
    let mut vm = make_test_vm("no-ip", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let mock = MockAzureOps::new(vec![vm]);
    let err = resolve_code_target(&mock, "test-rg", "no-ip", "azureuser").unwrap_err();
    assert!(err.to_string().contains("No IP address"));
}

#[test]
fn test_resolve_code_target_default_user() {
    let mut vm = make_test_vm("vm", PowerState::Running);
    vm.admin_username = None;
    let mock = MockAzureOps::new(vec![vm]);
    let (_ip, user) = resolve_code_target(&mock, "test-rg", "vm", "defaultuser").unwrap();
    assert_eq!(user, "defaultuser");
}

// ── Batch operation tests ───────────────────────────────────────────

#[test]
fn test_handle_batch_stop_deallocate() {
    let mock = MockAzureOps::new(vec![]);
    let names = vec!["vm-1".to_string(), "vm-2".to_string(), "vm-3".to_string()];
    let results = handle_batch_stop(&mock, "test-rg", &names, true);
    assert_eq!(results.len(), 3);
    for (i, r) in results.iter().enumerate() {
        let msg = r.as_ref().unwrap();
        assert!(msg.starts_with("Deallocated"));
        assert!(msg.contains(&names[i]));
    }
    let log = mock.call_log();
    assert_eq!(log.len(), 3);
    assert!(log[0].contains("stop_vm:vm-1:dealloc=true"));
}

#[test]
fn test_handle_batch_stop_no_deallocate() {
    let mock = MockAzureOps::new(vec![]);
    let names = vec!["vm-1".to_string()];
    let results = handle_batch_stop(&mock, "test-rg", &names, false);
    assert!(results[0].as_ref().unwrap().starts_with("Stopped"));
}

#[test]
fn test_handle_batch_start() {
    let mock = MockAzureOps::new(vec![]);
    let names = vec!["vm-a".to_string(), "vm-b".to_string()];
    let results = handle_batch_start(&mock, "test-rg", &names);
    assert_eq!(results.len(), 2);
    assert!(results[0].as_ref().unwrap().contains("vm-a"));
    assert!(results[1].as_ref().unwrap().contains("vm-b"));
}

#[test]
fn test_handle_batch_delete() {
    let mock = MockAzureOps::new(vec![]);
    let names = vec!["old-vm".to_string()];
    let results = handle_batch_delete(&mock, "test-rg", &names);
    assert_eq!(results.len(), 1);
    assert!(results[0].as_ref().unwrap().contains("old-vm"));
}

#[test]
fn test_handle_batch_empty() {
    let mock = MockAzureOps::new(vec![]);
    let names: Vec<String> = vec![];
    let results = handle_batch_stop(&mock, "test-rg", &names, true);
    assert_eq!(results.len(), 0);
}

// ── Count by state tests ────────────────────────────────────────────

#[test]
fn test_count_by_state() {
    let vms = vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm("vm-2", PowerState::Running),
        make_test_vm_stopped("vm-3"),
        make_test_vm("vm-4", PowerState::Starting),
    ];
    let counts = count_by_state(&vms);
    assert_eq!(counts.get("Running"), Some(&2));
    assert_eq!(counts.get("Deallocated"), Some(&1));
    assert_eq!(counts.get("Starting"), Some(&1));
}

#[test]
fn test_count_by_state_empty() {
    let counts = count_by_state(&[]);
    assert!(counts.is_empty());
}

// ── List summary tests ──────────────────────────────────────────────

#[test]
fn test_format_list_summary_no_tmux() {
    let s = format_list_summary(5, 0, false);
    assert_eq!(s, "Total: 5 VMs");
}

#[test]
fn test_format_list_summary_with_tmux() {
    let s = format_list_summary(3, 7, false);
    assert!(s.contains("3 VMs"));
    assert!(s.contains("7 tmux sessions"));
}

#[test]
fn test_format_list_summary_with_hints() {
    let s = format_list_summary(5, 0, true);
    assert!(s.contains("Hints:"));
    assert!(s.contains("azlin list -a"));
}
