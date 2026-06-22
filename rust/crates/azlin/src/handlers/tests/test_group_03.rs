use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::PowerState;
use std::collections::HashMap;

// ── Additional edge case tests ──────────────────────────────────────

#[test]
fn test_format_show_json_null_fields() {
    let mut vm = make_test_vm("null-fields", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    vm.admin_username = None;
    let json_str = format_show_json(&vm).unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
    assert!(parsed["public_ip"].is_null());
    assert!(parsed["private_ip"].is_null());
    assert!(parsed["admin_username"].is_null());
}

#[test]
fn test_format_show_csv_missing_ips() {
    let mut vm = make_test_vm("csv-null", PowerState::Stopped);
    vm.public_ip = None;
    vm.private_ip = None;
    vm.admin_username = None;
    let csv = format_show_csv(&vm);
    assert!(csv.contains("public_ip,\n"));
    assert!(csv.contains("private_ip,\n"));
    assert!(csv.contains("admin_username,\n"));
}

#[test]
fn test_filter_empty_pattern() {
    let mut vms = vec![
        make_test_vm("vm-1", PowerState::Running),
        make_test_vm("vm-2", PowerState::Running),
    ];
    // Empty pattern should match everything
    filter_list_vms(&mut vms, true, None, Some(""));
    assert_eq!(vms.len(), 2);
}

#[test]
fn test_filter_tag_key_value_no_match() {
    let mut vms = vec![make_test_vm("vm-1", PowerState::Running)];
    filter_list_vms(&mut vms, true, Some("env=prod"), None);
    assert_eq!(vms.len(), 0);
}

#[test]
fn test_filter_tag_key_no_match() {
    let mut vms = vec![make_test_vm("vm-1", PowerState::Running)];
    filter_list_vms(&mut vms, true, Some("nonexistent"), None);
    assert_eq!(vms.len(), 0);
}

#[test]
fn test_format_ip_display_empty_strings() {
    // Public IP takes precedence even if private is available
    assert_eq!(format_ip_display(Some("1.1.1.1"), None), "1.1.1.1");
}

#[test]
fn test_handle_tag_list_not_found() {
    let mock = MockAzureOps::new(vec![]);
    let err = handle_tag_list(&mock, "test-rg", "nonexistent").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_handle_status_empty_rg() {
    let mock = MockAzureOps::new(vec![]);
    let rows = handle_status(&mock, "empty-rg", None).unwrap();
    assert_eq!(rows.len(), 0);
}

#[test]
fn test_handle_status_row_fields() {
    let mock = MockAzureOps::new(vec![make_test_vm("detail-vm", PowerState::Running)]);
    let rows = handle_status(&mock, "test-rg", Some("detail-vm")).unwrap();
    assert_eq!(rows[0].public_ip, "20.1.2.3");
    assert_eq!(rows[0].private_ip, "10.0.0.4");
    assert_eq!(rows[0].vm_size, "Standard_D4s_v3");
    assert_eq!(rows[0].location, "eastus");
}

#[test]
fn test_format_list_json_empty() {
    let json_str = format_list_json(&[], &HashMap::new()).unwrap();
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
    assert!(parsed.is_empty());
}

#[test]
fn test_format_list_json_private_ip_only() {
    let vms = vec![make_test_vm_private("priv-vm")];
    let json_str = format_list_json(&vms, &HashMap::new()).unwrap();
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
    assert_eq!(parsed[0]["ip"], "(10.0.0.4)");
}

#[test]
fn test_format_list_json_no_ip() {
    let mut vm = make_test_vm("no-ip", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let json_str = format_list_json(&[vm], &HashMap::new()).unwrap();
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json_str).unwrap();
    assert_eq!(parsed[0]["ip"], "-");
}

#[test]
fn test_resolve_connect_vm_not_found() {
    let mock = MockAzureOps::new(vec![]);
    let err = resolve_connect_target(&mock, "test-rg", Some("missing"), "azureuser").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_resolve_health_targets_no_ip_skipped() {
    let mut vm = make_test_vm("no-ip", PowerState::Running);
    vm.public_ip = None;
    vm.private_ip = None;
    let mock = MockAzureOps::new(vec![vm]);
    let targets = resolve_health_targets(&mock, "test-rg", None).unwrap();
    assert_eq!(targets.len(), 0); // Skipped because no IP
}

#[test]
fn test_mock_tracks_multiple_operations() {
    let mock = MockAzureOps::new(vec![make_test_vm("vm-1", PowerState::Running)]);
    let _ = handle_start(&mock, "test-rg", "vm-1");
    let _ = handle_stop(&mock, "test-rg", "vm-1", false);
    let _ = handle_show(&mock, "test-rg", "vm-1");
    let log = mock.call_log();
    assert_eq!(log.len(), 3);
    assert!(log[0].contains("start_vm"));
    assert!(log[1].contains("stop_vm"));
    assert!(log[2].contains("get_vm"));
}

#[test]
fn test_subscription_id_from_mock() {
    let mock = MockAzureOps::new(vec![]);
    assert_eq!(mock.subscription_id(), "test-sub-12345");
}

#[test]
fn test_create_vm_via_mock() {
    use azlin_core::models::CreateVmParams;
    use std::path::PathBuf;

    let mock = MockAzureOps::new(vec![]);
    let params = CreateVmParams {
        name: "new-vm".to_string(),
        resource_group: "test-rg".to_string(),
        region: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        image: azlin_core::models::VmImage {
            publisher: "Canonical".to_string(),
            offer: "0001-com-ubuntu-server-jammy".to_string(),
            sku: "22_04-lts-gen2".to_string(),
            version: "latest".to_string(),
        },
        admin_username: "azureuser".to_string(),
        ssh_key_path: PathBuf::from("/tmp/fake-key.pub"),
        tags: HashMap::new(),
        public_ip_enabled: true,
        disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
    };
    let vm = mock.create_vm(&params).unwrap();
    assert_eq!(vm.name, "new-vm");
    assert!(mock.call_log().contains(&"create_vm:new-vm".to_string()));
}

// ── List header tests ───────────────────────────────────────────

#[test]
fn test_build_list_headers_minimal() {
    let config = ListColumnConfig {
        show_tmux: false,
        wide: false,
        with_latency: false,
        with_health: false,
        show_procs: false,
    };
    let headers = build_list_headers(&config);
    assert_eq!(
        headers,
        vec!["Session", "OS", "Status", "IP", "Region", "CPU", "Mem"]
    );
}

#[test]
fn test_build_list_headers_all_columns() {
    let config = ListColumnConfig {
        show_tmux: true,
        wide: true,
        with_latency: true,
        with_health: true,
        show_procs: true,
    };
    let headers = build_list_headers(&config);
    assert!(headers.contains(&"Tmux"));
    assert!(headers.contains(&"VM Name"));
    assert!(headers.contains(&"SKU"));
    assert!(headers.contains(&"Latency"));
    assert!(headers.contains(&"Health"));
    assert!(headers.contains(&"Top Procs"));
}

#[test]
fn test_build_list_headers_wide_only() {
    let config = ListColumnConfig {
        show_tmux: false,
        wide: true,
        with_latency: false,
        with_health: false,
        show_procs: false,
    };
    let headers = build_list_headers(&config);
    assert!(headers.contains(&"VM Name"));
    assert!(headers.contains(&"SKU"));
    assert!(!headers.contains(&"Tmux"));
}

// ── List row tests ──────────────────────────────────────────────

#[test]
fn test_build_list_row_basic() {
    let vm = make_test_vm("vm-1", PowerState::Running);
    let row = build_list_row(&vm, None, None, None, None);
    assert_eq!(row.session, "main");
    assert_eq!(row.tmux, "-");
    assert_eq!(row.vm_name, "vm-1");
    assert_eq!(row.power_state, "Running");
    assert_eq!(row.ip_display, "20.1.2.3");
    assert!(row.latency.is_none());
}

#[test]
fn test_build_list_row_with_tmux() {
    let vm = make_test_vm("vm-1", PowerState::Running);
    let sessions = vec!["main".to_string(), "debug".to_string()];
    let row = build_list_row(&vm, Some(&sessions), None, None, None);
    assert_eq!(row.tmux, "main, debug");
}

#[test]
fn test_build_list_row_with_latency() {
    let vm = make_test_vm("vm-1", PowerState::Running);
    let row = build_list_row(&vm, None, Some(42), None, None);
    assert_eq!(row.latency, Some("42ms".to_string()));
}

#[test]
fn test_build_list_row_with_health() {
    let vm = make_test_vm("vm-1", PowerState::Running);
    let row = build_list_row(&vm, None, None, Some("CPU:10% MEM:50%"), None);
    assert_eq!(row.health, Some("CPU:10% MEM:50%".to_string()));
}

#[test]
fn test_build_list_row_no_session_tag() {
    let mut vm = make_test_vm("vm-1", PowerState::Running);
    vm.tags.remove("azlin-session");
    let row = build_list_row(&vm, None, None, None, None);
    assert_eq!(row.session, "-");
}
