use crate::*;
use std::fs;
use tempfile::TempDir;

// ── storage_helpers ─────────────────────────────────────────────

#[test]
fn test_storage_sku_from_tier_all_variants() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("PREMIUM"),
        "Premium_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("STANDARD"),
        "Standard_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("anything"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_partial_data() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "eastus"
        // Missing kind, sku, provisioningState
    });
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "mystorage");
    assert_eq!(row[1], "eastus");
    assert_eq!(row[2], "-"); // missing kind
    assert_eq!(row[3], "-"); // missing sku.name
    assert_eq!(row[4], "-"); // missing provisioningState
}

// ── key_helpers ─────────────────────────────────────────────────

#[test]
fn test_detect_key_type_comprehensive() {
    assert_eq!(crate::key_helpers::detect_key_type("id_ed25519"), "ed25519");
    assert_eq!(
        crate::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
    assert_eq!(crate::key_helpers::detect_key_type("id_ecdsa"), "ecdsa");
    assert_eq!(crate::key_helpers::detect_key_type("id_rsa"), "rsa");
    assert_eq!(crate::key_helpers::detect_key_type("id_dsa"), "dsa");
    assert_eq!(
        crate::key_helpers::detect_key_type("known_hosts"),
        "unknown"
    );
    assert_eq!(
        crate::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_comprehensive() {
    assert!(crate::key_helpers::is_known_key_name("id_rsa.pub"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519.pub"));
    assert!(crate::key_helpers::is_known_key_name("id_rsa"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519"));
    assert!(crate::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(crate::key_helpers::is_known_key_name("id_dsa"));
    assert!(!crate::key_helpers::is_known_key_name("known_hosts"));
    assert!(!crate::key_helpers::is_known_key_name("config"));
}

// ── auth_helpers ────────────────────────────────────────────────

#[test]
fn test_mask_profile_value_secret_variants() {
    let secret_val = serde_json::json!("my-actual-secret");
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_secret", &secret_val),
        "********"
    );
    assert_eq!(
        crate::auth_helpers::mask_profile_value("db_password", &secret_val),
        "********"
    );
    // Non-secret field
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_id", &secret_val),
        "my-actual-secret"
    );
}

#[test]
fn test_mask_profile_value_non_string_types() {
    assert_eq!(
        crate::auth_helpers::mask_profile_value("count", &serde_json::json!(42)),
        "42"
    );
    assert_eq!(
        crate::auth_helpers::mask_profile_value("enabled", &serde_json::json!(true)),
        "true"
    );
    assert_eq!(
        crate::auth_helpers::mask_profile_value("data", &serde_json::json!(null)),
        "null"
    );
}

// ── log_helpers ─────────────────────────────────────────────────

#[test]
fn test_tail_start_index_various() {
    assert_eq!(crate::log_helpers::tail_start_index(100, 20), 80);
    assert_eq!(crate::log_helpers::tail_start_index(10, 20), 0); // can't go negative
    assert_eq!(crate::log_helpers::tail_start_index(0, 0), 0);
    assert_eq!(crate::log_helpers::tail_start_index(50, 50), 0);
}

// ── auth_test_helpers ───────────────────────────────────────────

#[test]
fn test_extract_account_info_full_json() {
    let acct = serde_json::json!({
        "name": "My Subscription",
        "tenantId": "tenant-123",
        "user": {"name": "user@example.com", "type": "user"}
    });
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "My Subscription");
    assert_eq!(tenant, "tenant-123");
    assert_eq!(user, "user@example.com");
}

#[test]
fn test_extract_account_info_empty_json() {
    let acct = serde_json::json!({});
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── cost helpers ────────────────────────────────────────────────

#[test]
fn test_parse_cost_history_rows_with_only_cost() {
    let data = serde_json::json!({
        "rows": [[42.5]]
    });
    let result = crate::parse_cost_history_rows(&data);
    assert_eq!(result.len(), 1);
    assert_eq!(result[0].1, "$42.50");
    assert_eq!(result[0].0, "-"); // no date column
}

#[test]
fn test_parse_recommendation_rows_with_nested_fields() {
    let data = serde_json::json!([
        {
            "category": "Cost",
            "impact": "High",
            "shortDescription": {"problem": "VM is oversized"}
        }
    ]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].1, "High");
    assert_eq!(rows[0].2, "VM is oversized");
}

#[test]
fn test_parse_cost_action_rows_complete_entry() {
    let data = serde_json::json!([
        {
            "impactedField": "Microsoft.Compute/virtualMachines",
            "impact": "Medium",
            "shortDescription": {"problem": "Rightsize your VM"}
        }
    ]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
    assert_eq!(rows[0].1, "Medium");
    assert_eq!(rows[0].2, "Rightsize your VM");
}
