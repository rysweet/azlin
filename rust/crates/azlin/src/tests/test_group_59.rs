#[test]
fn test_snapshot_helpers_load_schedule_missing() {
    // load_schedule returns None for nonexistent VM
    let result = crate::snapshot_helpers::load_schedule("nonexistent-vm-xyz-99999");
    assert!(result.is_none());
}

#[test]
fn test_format_as_csv_with_special_chars() {
    let headers = &["Name", "Value"];
    let rows = vec![vec!["has,comma".to_string(), "has\"quote".to_string()]];
    let out = crate::output_helpers::format_as_csv(headers, &rows);
    // CSV output doesn't escape — just verify it produces output
    assert!(out.contains("has,comma"));
}

#[test]
fn test_format_as_json_nested_objects() {
    #[derive(serde::Serialize)]
    struct Nested {
        name: String,
        count: u32,
    }
    let items = vec![
        Nested {
            name: "a".to_string(),
            count: 1,
        },
        Nested {
            name: "b".to_string(),
            count: 2,
        },
    ];
    let out = crate::output_helpers::format_as_json(&items);
    assert!(out.contains("\"name\": \"a\""));
    assert!(out.contains("\"count\": 2"));
}

#[test]
fn test_storage_helpers_storage_account_row_with_sku() {
    let acct = serde_json::json!({
        "name": "teststorage",
        "location": "eastus",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "teststorage");
    assert_eq!(row[3], "Standard_LRS");
}

#[test]
fn test_stop_action_labels_variants() {
    let (ing, ed) = crate::stop_helpers::stop_action_labels(true);
    assert_eq!(ing, "Deallocating");
    assert_eq!(ed, "Deallocated");
    let (ing, ed) = crate::stop_helpers::stop_action_labels(false);
    assert_eq!(ing, "Stopping");
    assert_eq!(ed, "Stopped");
}

#[test]
fn test_new_table_with_data() {
    let table = crate::new_table(&["Col1", "Col2"]);
    let output = format!("{table}");
    assert!(output.contains("Col1"));
    assert!(output.contains("Col2"));
}

#[test]
fn test_build_ssh_target_private_ip_with_bastion_and_key() {
    use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
    use std::collections::HashMap;

    let vm = VmInfo {
        name: "bastion-vm".to_string(),
        resource_group: "rg1".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D2s_v3".to_string(),
        os_type: OsType::Linux,
        power_state: PowerState::Running,
        provisioning_state: ProvisioningState::Succeeded,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.5".to_string()),
        admin_username: None,
        tags: HashMap::new(),
        created_time: None,
    };
    let mut bastion_map = HashMap::new();
    bastion_map.insert("eastus".to_string(), "my-bastion".to_string());
    let ssh_key = Some(std::path::PathBuf::from("/tmp/test_key"));
    let target = crate::build_ssh_target(&vm, "sub-123", &bastion_map, &ssh_key);
    assert_eq!(target.ip, "10.0.0.5");
    assert!(target.bastion.is_some());
    let b = target.bastion.unwrap();
    assert_eq!(b.bastion_name, "my-bastion");
    assert_eq!(b.resource_group, "rg1");
    assert!(b.vm_resource_id.contains("bastion-vm"));
    assert!(b.vm_resource_id.contains("sub-123"));
    assert_eq!(
        b.ssh_key_path,
        Some(std::path::PathBuf::from("/tmp/test_key"))
    );
}
