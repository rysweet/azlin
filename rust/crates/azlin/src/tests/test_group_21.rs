// ── Command-specific validation ─────────────────────────────────

#[test]
fn test_env_set_requires_args() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "set"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_env_delete_requires_args() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "delete"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_env_list_requires_vm() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "list"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_snapshot_create_requires_vm() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "create"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_tag_add_requires_vm_and_tags() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "add"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_start_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["start"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_stop_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["stop"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_delete_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["delete"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_destroy_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["destroy"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_kill_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["kill"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_fleet_run_requires_command() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "run"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

// ── Additional help flag coverage ──────────────────────────────

#[test]
fn test_sessions_help_output() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "--help"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("session") || stdout.contains("Session"));
}

#[test]
fn test_context_help_output() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "--help"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("context") || stdout.contains("Context"));
}

#[test]
fn test_template_help_output() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "--help"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("template") || stdout.contains("Template"));
}

// ── Storage helpers tests ───────────────────────────────────────

#[test]
fn test_storage_sku_from_tier_premium() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_standard() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_case_insensitive() {
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("Premium"),
        "Premium_LRS"
    );
    assert_eq!(
        crate::storage_helpers::storage_sku_from_tier("STANDARD"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_unknown_defaults_premium() {
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
fn test_storage_account_row_full() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "eastus2",
        "kind": "FileStorage",
        "sku": { "name": "Premium_LRS" },
        "provisioningState": "Succeeded"
    });
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(
        row,
        vec![
            "mystorage",
            "eastus2",
            "FileStorage",
            "Premium_LRS",
            "Succeeded"
        ]
    );
}

#[test]
fn test_storage_account_row_missing_fields() {
    let acct = serde_json::json!({});
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(row, vec!["-", "-", "-", "-", "-"]);
}

// ── Key helpers tests ───────────────────────────────────────────

#[test]
fn test_detect_key_type_ed25519() {
    assert_eq!(crate::key_helpers::detect_key_type("id_ed25519"), "ed25519");
    assert_eq!(
        crate::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
}

#[test]
fn test_detect_key_type_ecdsa() {
    assert_eq!(crate::key_helpers::detect_key_type("id_ecdsa"), "ecdsa");
}

#[test]
fn test_detect_key_type_rsa() {
    assert_eq!(crate::key_helpers::detect_key_type("id_rsa"), "rsa");
    assert_eq!(crate::key_helpers::detect_key_type("id_rsa.pub"), "rsa");
}

#[test]
fn test_detect_key_type_dsa() {
    assert_eq!(crate::key_helpers::detect_key_type("id_dsa"), "dsa");
}

#[test]
fn test_detect_key_type_unknown() {
    assert_eq!(
        crate::key_helpers::detect_key_type("my_custom_key"),
        "unknown"
    );
    assert_eq!(
        crate::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_pub() {
    assert!(crate::key_helpers::is_known_key_name("id_rsa.pub"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519.pub"));
    assert!(crate::key_helpers::is_known_key_name("custom.pub"));
}

#[test]
fn test_is_known_key_name_private() {
    assert!(crate::key_helpers::is_known_key_name("id_rsa"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519"));
    assert!(crate::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(crate::key_helpers::is_known_key_name("id_dsa"));
}

#[test]
fn test_is_known_key_name_not_key() {
    assert!(!crate::key_helpers::is_known_key_name("known_hosts"));
    assert!(!crate::key_helpers::is_known_key_name("config"));
    assert!(!crate::key_helpers::is_known_key_name("authorized_keys"));
}
