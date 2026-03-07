#[test]
fn test_snapshot_schedule_deserialization_from_raw_toml() {
    let raw = r#"
vm_name = "from-raw"
resource_group = "raw-rg"
every_hours = 1
keep_count = 100
enabled = true
created = "2025-12-31T23:59:59Z"
"#;
    let schedule: crate::snapshot_helpers::SnapshotSchedule = toml::from_str(raw).unwrap();
    assert_eq!(schedule.vm_name, "from-raw");
    assert_eq!(schedule.every_hours, 1);
    assert_eq!(schedule.keep_count, 100);
}

// ════════════════════════════════════════════════════════════════
// NEW COVERAGE BOOST: main.rs inline helper modules
// ════════════════════════════════════════════════════════════════

// ── stop_helpers ────────────────────────────────────────────────

#[test]
fn test_stop_action_labels_returns_correct_pairs() {
    let (ing, ed) = crate::stop_helpers::stop_action_labels(true);
    assert_eq!(ing, "Deallocating");
    assert_eq!(ed, "Deallocated");

    let (ing, ed) = crate::stop_helpers::stop_action_labels(false);
    assert_eq!(ing, "Stopping");
    assert_eq!(ed, "Stopped");
}

// ── bastion_helpers ─────────────────────────────────────────────

#[test]
fn test_bastion_summary_partial_fields() {
    let b = serde_json::json!({
        "name": "my-bastion",
        "location": "eastus"
    });
    let (name, rg, loc, sku, state) = crate::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "my-bastion");
    assert_eq!(rg, "unknown");
    assert_eq!(loc, "eastus");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "unknown");
}

#[test]
fn test_shorten_resource_id_empty_string() {
    assert_eq!(crate::bastion_helpers::shorten_resource_id(""), "");
}

#[test]
fn test_shorten_resource_id_no_slash() {
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id("just-a-name"),
        "just-a-name"
    );
}

#[test]
fn test_extract_ip_configs_missing_ip_configurations_key() {
    let b = serde_json::json!({"name": "test"});
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

// ── auth_helpers ────────────────────────────────────────────────

#[test]
fn test_mask_profile_value_client_secret() {
    let val = serde_json::json!("super-secret-123");
    let masked = crate::auth_helpers::mask_profile_value("client_secret", &val);
    assert_eq!(masked, "********");
}

#[test]
fn test_mask_profile_value_normal_key() {
    let val = serde_json::json!("visible-value");
    let masked = crate::auth_helpers::mask_profile_value("tenant_id", &val);
    assert_eq!(masked, "visible-value");
}

#[test]
fn test_mask_profile_value_array() {
    let val = serde_json::json!([1, 2, 3]);
    let masked = crate::auth_helpers::mask_profile_value("data", &val);
    assert_eq!(masked, "[1,2,3]");
}

// ── log_helpers ─────────────────────────────────────────────────

#[test]
fn test_tail_start_index_large_count() {
    assert_eq!(crate::log_helpers::tail_start_index(1000, 500), 500);
}

#[test]
fn test_tail_start_index_count_exceeds_total() {
    assert_eq!(crate::log_helpers::tail_start_index(10, 100), 0);
}

// ── config_path_helpers ─────────────────────────────────────────

#[test]
fn test_validate_config_path_empty_string_ok() {
    assert!(crate::config_path_helpers::validate_config_path("").is_ok());
}

#[test]
fn test_validate_config_path_absolute_linux() {
    assert!(crate::config_path_helpers::validate_config_path("/etc/azlin/config.toml").is_ok());
}

#[test]
fn test_validate_config_path_parent_at_start() {
    assert!(crate::config_path_helpers::validate_config_path("../evil.toml").is_err());
}

#[test]
fn test_validate_config_path_parent_in_middle() {
    assert!(crate::config_path_helpers::validate_config_path("foo/../bar.toml").is_err());
}

// ── disk_helpers ────────────────────────────────────────────────

#[test]
fn test_build_data_disk_name_zero_lun() {
    assert_eq!(
        crate::disk_helpers::build_data_disk_name("myvm", 0),
        "myvm_datadisk_0"
    );
}

#[test]
fn test_build_data_disk_name_high_lun() {
    assert_eq!(
        crate::disk_helpers::build_data_disk_name("prod-db", 63),
        "prod-db_datadisk_63"
    );
}

#[test]
fn test_restored_disk_name_construction() {
    assert_eq!(
        crate::disk_helpers::build_restored_disk_name("web-server"),
        "web-server_OsDisk_restored"
    );
}

// ── command_helpers ─────────────────────────────────────────────

#[test]
fn test_is_allowed_command_az_vm() {
    assert!(crate::command_helpers::is_allowed_command("az vm list"));
}

#[test]
fn test_is_allowed_command_az_with_leading_space() {
    assert!(crate::command_helpers::is_allowed_command("  az vm list"));
}

#[test]
fn test_is_allowed_command_rm_rejected() {
    assert!(!crate::command_helpers::is_allowed_command("rm -rf /"));
}

#[test]
fn test_is_allowed_command_empty() {
    assert!(!crate::command_helpers::is_allowed_command(""));
}

#[test]
fn test_skip_reason_az_command_none() {
    assert!(crate::command_helpers::skip_reason("az vm list").is_none());
}

#[test]
fn test_skip_reason_empty_returns_message() {
    let reason = crate::command_helpers::skip_reason("").unwrap();
    assert!(reason.contains("empty"));
}

#[test]
fn test_skip_reason_non_az_returns_message() {
    let reason = crate::command_helpers::skip_reason("docker ps").unwrap();
    assert!(reason.contains("non-Azure"));
}

// ── mount_helpers ───────────────────────────────────────────────

#[test]
fn test_mount_path_empty_rejected() {
    assert!(crate::mount_helpers::validate_mount_path("").is_err());
}

#[test]
fn test_mount_path_valid_data() {
    assert!(crate::mount_helpers::validate_mount_path("/data").is_ok());
}

#[test]
fn test_mount_path_valid_deep_nested() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data/vol/1").is_ok());
}

#[test]
fn test_mount_path_traversal_dotdot() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/../etc/shadow").is_err());
}

#[test]
fn test_mount_path_shell_injection_semicolon() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt; rm -rf /").is_err());
}

// ── vm_validation ───────────────────────────────────────────────

#[test]
fn test_validate_vm_name_numeric_only() {
    assert!(crate::vm_validation::validate_vm_name("12345").is_ok());
}

#[test]
fn test_validate_vm_name_with_hyphens() {
    assert!(crate::vm_validation::validate_vm_name("my-dev-vm-01").is_ok());
}

#[test]
fn test_validate_vm_name_underscore_rejected() {
    assert!(crate::vm_validation::validate_vm_name("my_vm").is_err());
}

#[test]
fn test_validate_vm_name_dot_rejected() {
    assert!(crate::vm_validation::validate_vm_name("my.vm").is_err());
}

#[test]
fn test_validate_vm_name_exactly_64_chars() {
    let name = "a".repeat(64);
    assert!(crate::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_validate_vm_name_exactly_65_chars() {
    let name = "a".repeat(65);
    assert!(crate::vm_validation::validate_vm_name(&name).is_err());
}
