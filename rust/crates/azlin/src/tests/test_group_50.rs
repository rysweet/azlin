use crate::*;
use std::fs;
use tempfile::TempDir;

// ── repo_helpers ────────────────────────────────────────────────

#[test]
fn test_validate_repo_url_https_valid() {
    assert!(crate::repo_helpers::validate_repo_url("https://github.com/user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_git_ssh_valid() {
    assert!(crate::repo_helpers::validate_repo_url("git@github.com:user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_ssh_scheme_valid() {
    assert!(crate::repo_helpers::validate_repo_url("ssh://git@github.com/user/repo").is_ok());
}

#[test]
fn test_validate_repo_url_http_valid() {
    assert!(crate::repo_helpers::validate_repo_url("http://github.com/user/repo").is_ok());
}

#[test]
fn test_validate_repo_url_ftp_rejected() {
    assert!(crate::repo_helpers::validate_repo_url("ftp://example.com/repo").is_err());
}

#[test]
fn test_validate_repo_url_space_rejected() {
    assert!(crate::repo_helpers::validate_repo_url("https://example.com/my repo").is_err());
}

#[test]
fn test_validate_repo_url_quotes_rejected() {
    assert!(crate::repo_helpers::validate_repo_url("https://example.com/repo'").is_err());
    assert!(crate::repo_helpers::validate_repo_url("https://example.com/repo\"").is_err());
}

// ── cp_helpers ──────────────────────────────────────────────────

#[test]
fn test_is_remote_path_vm_with_path() {
    assert!(crate::cp_helpers::is_remote_path(
        "myvm:/home/user/file.txt"
    ));
}

#[test]
fn test_is_remote_path_local_absolute() {
    assert!(!crate::cp_helpers::is_remote_path("/home/user/file.txt"));
}

#[test]
fn test_remote_path_empty_string_false() {
    assert!(!crate::cp_helpers::is_remote_path(""));
}

#[test]
fn test_is_remote_path_single_char_before_colon() {
    // "a:" has len 2, so should be false (too short: len > 2 check)
    assert!(!crate::cp_helpers::is_remote_path("a:"));
}

#[test]
fn test_classify_transfer_local_to_local_both_paths() {
    assert_eq!(
        crate::cp_helpers::classify_transfer_direction("/tmp/a.txt", "/tmp/b.txt"),
        "local\u{2192}local"
    );
}

#[test]
fn test_resolve_scp_path_replaces_first_occurrence() {
    let result = crate::cp_helpers::resolve_scp_path("myvm:/path", "myvm", "admin", "10.0.0.1");
    assert_eq!(result, "admin@10.0.0.1:/path");
}

// ── key_helpers ─────────────────────────────────────────────────

#[test]
fn test_detect_key_type_ed25519_pub() {
    assert_eq!(
        crate::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
}

#[test]
fn test_detect_key_type_rsa_private() {
    assert_eq!(crate::key_helpers::detect_key_type("id_rsa"), "rsa");
}

#[test]
fn test_detect_key_type_random() {
    assert_eq!(
        crate::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_ed25519_pub() {
    assert!(crate::key_helpers::is_known_key_name("id_ed25519.pub"));
}

#[test]
fn test_is_known_key_name_id_rsa() {
    assert!(crate::key_helpers::is_known_key_name("id_rsa"));
}

#[test]
fn test_is_known_key_name_config() {
    assert!(!crate::key_helpers::is_known_key_name("config"));
}

#[test]
fn test_is_known_key_name_known_hosts() {
    assert!(!crate::key_helpers::is_known_key_name("known_hosts"));
}

// ── auth_test_helpers ───────────────────────────────────────────

#[test]
fn test_extract_account_info_complete() {
    let acct = serde_json::json!({
        "name": "My Subscription",
        "tenantId": "tenant-abc",
        "user": {"name": "user@example.com"}
    });
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "My Subscription");
    assert_eq!(tenant, "tenant-abc");
    assert_eq!(user, "user@example.com");
}

#[test]
fn test_extract_account_info_all_missing() {
    let acct = serde_json::json!({});
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── storage_helpers ─────────────────────────────────────────────

#[test]
fn test_storage_sku_from_tier_premium_lrs() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_standard_lrs() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_mixed_case() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("PREMIUM"),
        "Premium_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("StAnDaRd"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_unknown_tier_defaults() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("hot"),
        "Premium_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier(""),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_complete_json() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "westus2",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(
        row,
        vec![
            "mystorage",
            "westus2",
            "StorageV2",
            "Standard_LRS",
            "Succeeded"
        ]
    );
}

#[test]
fn test_storage_account_row_all_missing() {
    let acct = serde_json::json!({});
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(row, vec!["-", "-", "-", "-", "-"]);
}

// ── compose_helpers ─────────────────────────────────────────────

#[test]
fn test_resolve_compose_file_default_value() {
    assert_eq!(
        crate::compose_helpers::resolve_compose_file(None),
        "docker-compose.yml"
    );
}

#[test]
fn test_resolve_compose_file_custom_value() {
    assert_eq!(
        crate::compose_helpers::resolve_compose_file(Some("custom.yml")),
        "custom.yml"
    );
}

#[test]
fn test_build_compose_cmd_ps() {
    assert_eq!(
        crate::compose_helpers::build_compose_cmd("ps", "docker-compose.yml"),
        "docker compose -f docker-compose.yml ps"
    );
}

#[test]
fn test_build_compose_cmd_logs() {
    assert_eq!(
        crate::compose_helpers::build_compose_cmd("logs", "custom.yml"),
        "docker compose -f custom.yml logs"
    );
}
