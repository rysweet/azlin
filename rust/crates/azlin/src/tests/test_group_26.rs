// ── NEW: vm_validation additional tests ──────────────────────

#[test]
fn test_vm_name_valid_simple() {
    assert!(crate::vm_validation::validate_vm_name("myvm").is_ok());
}

#[test]
fn test_vm_name_valid_with_numbers() {
    assert!(crate::vm_validation::validate_vm_name("vm-01-prod").is_ok());
}

#[test]
fn test_vm_name_single_char() {
    assert!(crate::vm_validation::validate_vm_name("a").is_ok());
}

#[test]
fn test_vm_name_underscores_rejected() {
    assert!(crate::vm_validation::validate_vm_name("my_vm").is_err());
}

#[test]
fn test_vm_name_spaces_rejected() {
    assert!(crate::vm_validation::validate_vm_name("my vm").is_err());
}

#[test]
fn test_vm_name_dots_rejected() {
    assert!(crate::vm_validation::validate_vm_name("vm.prod").is_err());
}

#[test]
fn test_vm_name_double_hyphen_ok() {
    assert!(crate::vm_validation::validate_vm_name("vm--test").is_ok());
}

#[test]
fn test_vm_name_63_chars() {
    let name = "a".repeat(63);
    assert!(crate::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_vm_name_64_chars() {
    let name = "b".repeat(64);
    assert!(crate::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_vm_name_65_chars() {
    let name = "c".repeat(65);
    assert!(crate::vm_validation::validate_vm_name(&name).is_err());
}

// ── NEW: mount_helpers additional tests ──────────────────────

#[test]
fn test_mount_path_valid_nested() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data/disk1").is_ok());
}

#[test]
fn test_mount_path_root() {
    assert!(crate::mount_helpers::validate_mount_path("/").is_ok());
}

#[test]
fn test_mount_path_ampersand() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/a&b").is_err());
}

#[test]
fn test_mount_path_dollar() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/$HOME").is_err());
}

#[test]
fn test_mount_path_newline() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/a\nb").is_err());
}

#[test]
fn test_mount_path_null_byte() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/a\0b").is_err());
}

#[test]
fn test_mount_path_relative_rejected() {
    assert!(crate::mount_helpers::validate_mount_path("mnt/data").is_err());
}

#[test]
fn test_mount_path_exclamation() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/test!").is_err());
}

#[test]
fn test_mount_path_parentheses() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/(test)").is_err());
}

#[test]
fn test_mount_path_curly_braces() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/{test}").is_err());
}

#[test]
fn test_mount_path_angle_brackets() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/<test>").is_err());
}

// ── NEW: config_path_helpers additional tests ────────────────

#[test]
fn test_config_path_simple_relative() {
    assert!(crate::config_path_helpers::validate_config_path("config.toml").is_ok());
}

#[test]
fn test_config_path_nested() {
    assert!(crate::config_path_helpers::validate_config_path("a/b/c.toml").is_ok());
}

#[test]
fn test_config_path_dot_prefix() {
    assert!(crate::config_path_helpers::validate_config_path("./config.toml").is_ok());
}

#[test]
fn test_config_path_parent_traversal() {
    assert!(crate::config_path_helpers::validate_config_path("../etc/passwd").is_err());
}

#[test]
fn test_config_path_middle_traversal() {
    assert!(crate::config_path_helpers::validate_config_path("a/../../etc").is_err());
}

#[test]
fn test_config_path_absolute_allowed() {
    assert!(crate::config_path_helpers::validate_config_path("/home/user/config.toml").is_ok());
}

// ── NEW: storage_helpers additional tests ────────────────────

#[test]
fn test_storage_sku_premium() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_sku_standard() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_mixed_case() {
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
fn test_storage_sku_unknown() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("unknown"),
        "Premium_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier(""),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_complete() {
    let acct = serde_json::json!({
        "name": "mystorageacct",
        "location": "westus2",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(
        row,
        vec![
            "mystorageacct",
            "westus2",
            "StorageV2",
            "Standard_LRS",
            "Succeeded"
        ]
    );
}

#[test]
fn test_storage_account_row_partial() {
    let acct = serde_json::json!({"name": "partial"});
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "partial");
    assert_eq!(row[1], "-");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
    assert_eq!(row[4], "-");
}

#[test]
fn test_storage_account_row_empty() {
    let acct = serde_json::json!({});
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert!(row.iter().all(|c| c == "-"));
}

// ── NEW: key_helpers additional tests ────────────────────────

#[test]
fn test_detect_key_type_filename_prefix() {
    assert_eq!(
        crate::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
    assert_eq!(crate::key_helpers::detect_key_type("id_ecdsa.pub"), "ecdsa");
    assert_eq!(crate::key_helpers::detect_key_type("id_rsa.pub"), "rsa");
    assert_eq!(crate::key_helpers::detect_key_type("id_dsa.pub"), "dsa");
}

#[test]
fn test_detect_key_type_custom_name() {
    assert_eq!(
        crate::key_helpers::detect_key_type("my_ed25519_key"),
        "ed25519"
    );
    assert_eq!(crate::key_helpers::detect_key_type("backup_rsa"), "rsa");
}

#[test]
fn test_detect_key_type_random_file() {
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
fn test_is_known_key_name_standard_private() {
    assert!(crate::key_helpers::is_known_key_name("id_rsa"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519"));
    assert!(crate::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(crate::key_helpers::is_known_key_name("id_dsa"));
}

#[test]
fn test_is_known_key_name_pub_extension() {
    assert!(crate::key_helpers::is_known_key_name("custom.pub"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519.pub"));
}

#[test]
fn test_is_known_key_name_non_key_files() {
    assert!(!crate::key_helpers::is_known_key_name("known_hosts"));
    assert!(!crate::key_helpers::is_known_key_name("config"));
    assert!(!crate::key_helpers::is_known_key_name("authorized_keys"));
}
