// ── Auth helpers tests ──────────────────────────────────────────

#[test]
fn test_mask_profile_value_plain_string() {
    let v = serde_json::Value::String("my-tenant".into());
    assert_eq!(
        crate::auth_helpers::mask_profile_value("tenant_id", &v),
        "my-tenant"
    );
}

#[test]
fn test_mask_profile_value_secret_masked() {
    let v = serde_json::Value::String("super-secret-123".into());
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_secret", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_value_password_masked() {
    let v = serde_json::Value::String("p@ssw0rd".into());
    assert_eq!(
        crate::auth_helpers::mask_profile_value("db_password", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_value_non_string() {
    let v = serde_json::json!(42);
    assert_eq!(crate::auth_helpers::mask_profile_value("count", &v), "42");
}

#[test]
fn test_mask_profile_value_boolean() {
    let v = serde_json::json!(true);
    assert_eq!(
        crate::auth_helpers::mask_profile_value("enabled", &v),
        "true"
    );
}

// ── CP helpers tests ────────────────────────────────────────────

#[test]
fn test_is_remote_path_positive() {
    assert!(crate::cp_helpers::is_remote_path(
        "myvm:/home/user/file.txt"
    ));
    assert!(crate::cp_helpers::is_remote_path("dev-vm-1:/tmp/data"));
}

#[test]
fn test_is_remote_path_local() {
    assert!(!crate::cp_helpers::is_remote_path("/tmp/local.txt"));
    assert!(!crate::cp_helpers::is_remote_path("./relative/path"));
    assert!(!crate::cp_helpers::is_remote_path("file.txt"));
}

#[test]
fn test_is_remote_path_windows_drive_excluded() {
    assert!(!crate::cp_helpers::is_remote_path("C:\\Users\\file"));
}

#[test]
fn test_is_remote_path_too_short() {
    assert!(!crate::cp_helpers::is_remote_path("a:"));
}

#[test]
fn test_classify_transfer_direction_remote_to_local() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("vm:/path", "/local"),
        "remote→local"
    );
}

#[test]
fn test_classify_transfer_direction_local_to_remote() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("/local", "vm:/path"),
        "local→remote"
    );
}

#[test]
fn test_classify_transfer_direction_local_to_local() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("/a", "/b"),
        "local→local"
    );
}

#[test]
fn test_resolve_scp_path_rewrites() {
    let result =
        crate::cp_helpers::resolve_scp_path("myvm:/home/data", "myvm", "azureuser", "10.0.0.5");
    assert_eq!(result, "azureuser@10.0.0.5:/home/data");
}

#[test]
fn test_resolve_scp_path_no_match() {
    let result = crate::cp_helpers::resolve_scp_path("/local/path", "myvm", "user", "10.0.0.1");
    assert_eq!(result, "/local/path");
}

// ── Bastion helpers tests ───────────────────────────────────────

#[test]
fn test_bastion_summary_full() {
    let b = serde_json::json!({
        "name": "my-bastion",
        "resourceGroup": "my-rg",
        "location": "eastus2",
        "sku": { "name": "Standard" },
        "provisioningState": "Succeeded"
    });
    let (name, rg, loc, sku, state) = crate::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "my-bastion");
    assert_eq!(rg, "my-rg");
    assert_eq!(loc, "eastus2");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "Succeeded");
}

#[test]
fn test_bastion_summary_defaults() {
    let b = serde_json::json!({});
    let (name, rg, loc, sku, state) = crate::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "unknown");
    assert_eq!(rg, "unknown");
    assert_eq!(loc, "unknown");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "unknown");
}

#[test]
fn test_shorten_resource_id_full_path() {
    let id =
        "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/my-pip";
    assert_eq!(crate::bastion_helpers::shorten_resource_id(id), "my-pip");
}

#[test]
fn test_shorten_resource_id_na() {
    assert_eq!(crate::bastion_helpers::shorten_resource_id("N/A"), "N/A");
}

#[test]
fn test_shorten_resource_id_simple() {
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id("just-a-name"),
        "just-a-name"
    );
}

#[test]
fn test_extract_ip_configs_with_configs() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": { "id": "/sub/rg/subnets/AzureBastionSubnet" },
                "publicIPAddress": { "id": "/sub/rg/publicIPAddresses/bastion-pip" }
            },
            {
                "subnet": { "id": "N/A" },
                "publicIPAddress": { "id": "N/A" }
            }
        ]
    });
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(
        configs[0],
        ("AzureBastionSubnet".to_string(), "bastion-pip".to_string())
    );
    assert_eq!(configs[1], ("N/A".to_string(), "N/A".to_string()));
}

#[test]
fn test_extract_ip_configs_empty() {
    let b = serde_json::json!({});
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

// ── Log helpers tests ───────────────────────────────────────────

#[test]
fn test_tail_start_index_more_than_count() {
    assert_eq!(crate::log_helpers::tail_start_index(100, 20), 80);
}

#[test]
fn test_tail_start_index_less_than_count() {
    assert_eq!(crate::log_helpers::tail_start_index(5, 20), 0);
}

#[test]
fn test_tail_start_index_equal() {
    assert_eq!(crate::log_helpers::tail_start_index(20, 20), 0);
}

#[test]
fn test_tail_start_index_zero() {
    assert_eq!(crate::log_helpers::tail_start_index(0, 20), 0);
}

// ── Auth test helpers tests ─────────────────────────────────────

#[test]
fn test_extract_account_info_full() {
    let acct = serde_json::json!({
        "name": "My Subscription",
        "tenantId": "tenant-123",
        "user": { "name": "user@example.com" }
    });
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "My Subscription");
    assert_eq!(tenant, "tenant-123");
    assert_eq!(user, "user@example.com");
}

#[test]
fn test_extract_account_info_missing_fields() {
    let acct = serde_json::json!({});
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

#[test]
fn test_extract_account_info_partial() {
    let acct = serde_json::json!({
        "name": "Sub Only",
        "user": {}
    });
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "Sub Only");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}
