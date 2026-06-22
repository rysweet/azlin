// ── VM name validation edge cases ───────────────────────────────

#[test]
fn test_validate_vm_name_consecutive_hyphens_allowed() {
    // Azure allows consecutive hyphens
    assert!(crate::vm_validation::validate_vm_name("vm--test").is_ok());
}

#[test]
fn test_validate_vm_name_max_64_chars_ok() {
    let name = "a".repeat(64);
    assert!(crate::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_validate_vm_name_65_chars_rejected() {
    let name = "a".repeat(65);
    let err = crate::vm_validation::validate_vm_name(&name).unwrap_err();
    assert!(err.contains("exceeds 64"));
}

#[test]
fn test_validate_vm_name_special_chars_rejected() {
    assert!(crate::vm_validation::validate_vm_name("vm@test").is_err());
    assert!(crate::vm_validation::validate_vm_name("vm.test").is_err());
    assert!(crate::vm_validation::validate_vm_name("vm test").is_err());
}

// ── mount_helpers edge cases ────────────────────────────────────

#[test]
fn test_validate_mount_path_valid() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data").is_ok());
    assert!(crate::mount_helpers::validate_mount_path("/home/user/work").is_ok());
}

#[test]
fn test_validate_mount_path_empty() {
    let err = crate::mount_helpers::validate_mount_path("").unwrap_err();
    assert!(err.contains("must not be empty"));
}

#[test]
fn test_validate_mount_path_shell_metacharacters() {
    for path in &[
        "/mnt;rm -rf /",
        "/mnt|cat",
        "/mnt&bg",
        "/mnt$(cmd)",
        "/mnt`cmd`",
    ] {
        assert!(
            crate::mount_helpers::validate_mount_path(path).is_err(),
            "Expected error for path: {}",
            path,
        );
    }
}

#[test]
fn test_validate_mount_path_traversal() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/../etc").is_err());
    assert!(crate::mount_helpers::validate_mount_path("/mnt/..").is_err());
}

// ── cp_helpers ──────────────────────────────────────────────────

#[test]
fn test_is_remote_path_variants() {
    assert!(crate::cp_helpers::is_remote_path("vm-name:/path"));
    assert!(!crate::cp_helpers::is_remote_path("/local/path"));
    assert!(!crate::cp_helpers::is_remote_path("C:\\windows")); // drive letter
    assert!(!crate::cp_helpers::is_remote_path("ab")); // too short
}

#[test]
fn test_classify_transfer_direction_all_cases() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("vm:/path", "/local"),
        "remote→local"
    );
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("/local", "vm:/path"),
        "local→remote"
    );
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("/a", "/b"),
        "local→local"
    );
}

#[test]
fn test_resolve_scp_path_replaces_vm_name() {
    let result =
        crate::cp_helpers::resolve_scp_path("my-vm:/remote/path", "my-vm", "azureuser", "10.0.0.1");
    assert_eq!(result, "azureuser@10.0.0.1:/remote/path");
}

// ── bastion_helpers ─────────────────────────────────────────────

#[test]
fn test_bastion_summary_extracts_fields() {
    let b = serde_json::json!({
        "name": "my-bastion",
        "resourceGroup": "my-rg",
        "location": "eastus",
        "sku": {"name": "Standard"},
        "provisioningState": "Succeeded"
    });
    let (name, rg, loc, sku, state) = crate::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "my-bastion");
    assert_eq!(rg, "my-rg");
    assert_eq!(loc, "eastus");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "Succeeded");
}

#[test]
fn test_extract_ip_configs_multiple_entries() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": {"id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/AzureBastionSubnet"},
                "publicIPAddress": {"id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/publicIPAddresses/bastion-pip"}
            },
            {
                "subnet": {"id": "/subs/rg/vnet/subnets/OtherSubnet"},
                "publicIPAddress": {"id": "N/A"}
            }
        ]
    });
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(configs[0].0, "AzureBastionSubnet");
    assert_eq!(configs[0].1, "bastion-pip");
    assert_eq!(configs[1].1, "N/A");
}

#[test]
fn test_shorten_resource_id_long_path() {
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id(
            "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/my-pip"
        ),
        "my-pip"
    );
}

// ── fleet_helpers ───────────────────────────────────────────────

#[test]
fn test_classify_result_various_codes() {
    assert_eq!(crate::fleet_helpers::classify_result(0), ("OK", true));
    assert_eq!(crate::fleet_helpers::classify_result(1), ("FAIL", false));
    assert_eq!(crate::fleet_helpers::classify_result(127), ("FAIL", false));
    assert_eq!(crate::fleet_helpers::classify_result(-1), ("FAIL", false));
}

#[test]
fn test_finish_message_multiline_stdout() {
    let msg = crate::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert!(msg.contains("3 lines"));
}

#[test]
fn test_finish_message_error_first_line() {
    let msg =
        crate::fleet_helpers::finish_message(1, "", "Error: connection refused\ndetailed trace\n");
    assert!(msg.contains("Error: connection refused"));
    assert!(!msg.contains("detailed trace"));
}

#[test]
fn test_format_output_text_show_stdout() {
    let text = crate::fleet_helpers::format_output_text(0, "hello world", "", true);
    assert_eq!(text, "hello world");
}

#[test]
fn test_format_output_text_show_stderr_when_stdout_empty() {
    let text = crate::fleet_helpers::format_output_text(1, "", "error msg", true);
    assert_eq!(text, "error msg");
}

#[test]
fn test_format_output_text_hide_success_empty() {
    let text = crate::fleet_helpers::format_output_text(0, "output", "", false);
    assert!(text.is_empty());
}
