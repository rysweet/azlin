// ── NEW: auth_helpers additional tests ───────────────────────

#[test]
fn test_mask_profile_string_no_secret() {
    let v = serde_json::json!("my-tenant-id");
    assert_eq!(
        crate::auth_helpers::mask_profile_value("tenant_id", &v),
        "my-tenant-id"
    );
}

#[test]
fn test_mask_profile_secret_key() {
    let v = serde_json::json!("s3cr3t-value");
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_secret", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_password_key() {
    let v = serde_json::json!("pa$$word");
    assert_eq!(
        crate::auth_helpers::mask_profile_value("admin_password", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_number_value() {
    let v = serde_json::json!(42);
    assert_eq!(crate::auth_helpers::mask_profile_value("count", &v), "42");
}

#[test]
fn test_mask_profile_bool_value() {
    let v = serde_json::json!(true);
    assert_eq!(
        crate::auth_helpers::mask_profile_value("enabled", &v),
        "true"
    );
}

#[test]
fn test_mask_profile_null_value() {
    let v = serde_json::json!(null);
    assert_eq!(crate::auth_helpers::mask_profile_value("field", &v), "null");
}

#[test]
fn test_mask_profile_secret_in_key_substring() {
    let v = serde_json::json!("value123");
    assert_eq!(
        crate::auth_helpers::mask_profile_value("my_secret_key", &v),
        "********"
    );
}

// ── NEW: cp_helpers additional tests ─────────────────────────

#[test]
fn test_is_remote_path_standard() {
    assert!(crate::cp_helpers::is_remote_path("vm-name:/path/to/file"));
}

#[test]
fn test_is_remote_path_short_colon() {
    // Two chars with colon at pos 1 like "C:" should NOT be remote
    assert!(!crate::cp_helpers::is_remote_path("C:"));
}

#[test]
fn test_is_remote_path_absolute() {
    assert!(!crate::cp_helpers::is_remote_path("/home/user/file.txt"));
}

#[test]
fn test_is_remote_path_windows_drive() {
    assert!(!crate::cp_helpers::is_remote_path("C:\\Users\\file"));
}

#[test]
fn test_is_remote_path_no_colon() {
    assert!(!crate::cp_helpers::is_remote_path("localfile.txt"));
}

#[test]
fn test_is_remote_path_empty() {
    assert!(!crate::cp_helpers::is_remote_path(""));
}

#[test]
fn test_classify_transfer_local_to_remote() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("file.txt", "vm:/path"),
        "local→remote"
    );
}

#[test]
fn test_classify_transfer_remote_to_local() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("vm:/path", "file.txt"),
        "remote→local"
    );
}

#[test]
fn test_classify_transfer_both_local() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("file1.txt", "file2.txt"),
        "local→local"
    );
}

#[test]
fn test_resolve_scp_path_rewrite() {
    let result =
        crate::cp_helpers::resolve_scp_path("vm-1:/data/file.txt", "vm-1", "admin", "10.0.0.5");
    assert_eq!(result, "admin@10.0.0.5:/data/file.txt");
}

#[test]
fn test_resolve_scp_path_no_match_passthrough() {
    let result = crate::cp_helpers::resolve_scp_path("other-vm:/file", "vm-1", "u", "1.2.3.4");
    assert_eq!(result, "other-vm:/file");
}

// ── NEW: bastion_helpers additional tests ────────────────────

#[test]
fn test_bastion_summary_full_json() {
    let b = serde_json::json!({
        "name": "bastion-prod",
        "resourceGroup": "rg-prod",
        "location": "eastus",
        "sku": {"name": "Premium"},
        "provisioningState": "Succeeded"
    });
    let (name, rg, loc, sku, state) = crate::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "bastion-prod");
    assert_eq!(rg, "rg-prod");
    assert_eq!(loc, "eastus");
    assert_eq!(sku, "Premium");
    assert_eq!(state, "Succeeded");
}

#[test]
fn test_bastion_summary_missing_all() {
    let b = serde_json::json!({});
    let (name, rg, loc, sku, state) = crate::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "unknown");
    assert_eq!(rg, "unknown");
    assert_eq!(loc, "unknown");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "unknown");
}

#[test]
fn test_shorten_resource_id_long() {
    let id = "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/bastionHosts/my-bastion";
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id(id),
        "my-bastion"
    );
}

#[test]
fn test_shorten_resource_id_single_segment() {
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id("just-a-name"),
        "just-a-name"
    );
}

#[test]
fn test_shorten_resource_id_empty() {
    assert_eq!(crate::bastion_helpers::shorten_resource_id(""), "");
}

#[test]
fn test_extract_ip_configs_multiple() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": {"id": "/subs/x/subnets/sn-1"},
                "publicIPAddress": {"id": "/subs/x/publicIPAddresses/pip-1"}
            },
            {
                "subnet": {"id": "/subs/x/subnets/sn-2"},
                "publicIPAddress": {"id": "/subs/x/publicIPAddresses/pip-2"}
            }
        ]
    });
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(configs[0], ("sn-1".to_string(), "pip-1".to_string()));
    assert_eq!(configs[1], ("sn-2".to_string(), "pip-2".to_string()));
}

#[test]
fn test_extract_ip_configs_missing_ids() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {"subnet": {}, "publicIPAddress": {}}
        ]
    });
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 1);
    assert_eq!(configs[0], ("N/A".to_string(), "N/A".to_string()));
}

#[test]
fn test_extract_ip_configs_no_array() {
    let b = serde_json::json!({"name": "no-configs"});
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

// ── NEW: log_helpers additional tests ────────────────────────

#[test]
fn test_tail_start_index_large_total() {
    assert_eq!(crate::log_helpers::tail_start_index(1000, 50), 950);
}

#[test]
fn test_tail_start_index_count_larger_than_total() {
    assert_eq!(crate::log_helpers::tail_start_index(5, 100), 0);
}

#[test]
fn test_tail_start_index_both_zero() {
    assert_eq!(crate::log_helpers::tail_start_index(0, 0), 0);
}

#[test]
fn test_tail_start_index_count_one() {
    assert_eq!(crate::log_helpers::tail_start_index(10, 1), 9);
}
