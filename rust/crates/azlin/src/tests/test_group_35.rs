// ── vm_validation edge cases ────────────────────────────────────

#[test]
fn test_validate_vm_name_max_length() {
    let name = "a".repeat(64);
    assert!(crate::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_validate_vm_name_exceeds_max() {
    let name = "a".repeat(65);
    assert!(crate::vm_validation::validate_vm_name(&name).is_err());
}

#[test]
fn test_validate_vm_name_with_underscores_rejected() {
    assert!(crate::vm_validation::validate_vm_name("my_vm").is_err());
}

// ── env_helpers edge case tests ─────────────────────────────────

#[test]
fn test_split_env_var_missing_equals() {
    assert!(crate::env_helpers::split_env_var("NOVALUE").is_none());
}

#[test]
fn test_split_env_var_empty_key() {
    assert!(crate::env_helpers::split_env_var("=value").is_none());
}

#[test]
fn test_split_env_var_blank_value() {
    let result = crate::env_helpers::split_env_var("KEY=");
    assert_eq!(result, Some(("KEY", "")));
}

#[test]
fn test_split_env_var_embedded_equals() {
    let result = crate::env_helpers::split_env_var("KEY=val=ue");
    assert_eq!(result, Some(("KEY", "val=ue")));
}

#[test]
fn test_parse_env_output_blank_input() {
    let result = crate::env_helpers::parse_env_output("");
    assert!(result.is_empty());
}

#[test]
fn test_parse_env_output_multiple() {
    let result =
        crate::env_helpers::parse_env_output("HOME=/home/user\nPATH=/usr/bin\nSHELL=/bin/bash");
    assert_eq!(result.len(), 3);
    assert_eq!(result[0], ("HOME".to_string(), "/home/user".to_string()));
    assert_eq!(result[1], ("PATH".to_string(), "/usr/bin".to_string()));
}

// ── sync_helpers edge case tests ────────────────────────────────

#[test]
fn test_validate_sync_source_var_rejected() {
    assert!(crate::sync_helpers::validate_sync_source("/var/log/syslog").is_err());
}

#[test]
fn test_validate_sync_source_root_rejected() {
    assert!(crate::sync_helpers::validate_sync_source("/root/.bashrc").is_err());
}

#[test]
fn test_validate_sync_source_safe_path() {
    assert!(crate::sync_helpers::validate_sync_source("my-dotfiles/.bashrc").is_ok());
}

#[test]
fn test_validate_sync_source_dotdot_only() {
    assert!(crate::sync_helpers::validate_sync_source("..").is_err());
}

// ── mount_helpers additional edge case tests ────────────────────

#[test]
fn test_mount_path_null_char() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data\0bad").is_err());
}

#[test]
fn test_mount_path_pipe_char() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data|bad").is_err());
}

#[test]
fn test_mount_path_newline_injection() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data\nbad").is_err());
}

#[test]
fn test_mount_path_not_absolute() {
    assert!(crate::mount_helpers::validate_mount_path("relative/path").is_err());
}

// ── stop_helpers tests ──────────────────────────────────────────

#[test]
fn test_stop_action_labels_deallocate() {
    let (action, done) = crate::stop_helpers::stop_action_labels(true);
    assert_eq!(action, "Deallocating");
    assert_eq!(done, "Deallocated");
}

#[test]
fn test_stop_action_labels_stop() {
    let (action, done) = crate::stop_helpers::stop_action_labels(false);
    assert_eq!(action, "Stopping");
    assert_eq!(done, "Stopped");
}

// ── display_helpers tests ───────────────────────────────────────

#[test]
fn test_config_value_display_string() {
    let v = serde_json::Value::String("hello".to_string());
    assert_eq!(crate::display_helpers::config_value_display(&v), "hello");
}

#[test]
fn test_config_value_display_null() {
    assert_eq!(
        crate::display_helpers::config_value_display(&serde_json::Value::Null),
        "null"
    );
}

#[test]
fn test_config_value_display_number() {
    let v = serde_json::json!(42);
    assert_eq!(crate::display_helpers::config_value_display(&v), "42");
}

#[test]
fn test_truncate_vm_name_short() {
    assert_eq!(
        crate::display_helpers::truncate_vm_name("my-vm", 20),
        "my-vm"
    );
}

#[test]
fn test_truncate_vm_name_long() {
    let name = "azlin-very-long-vm-name-12345";
    let result = crate::display_helpers::truncate_vm_name(name, 20);
    assert_eq!(result, "azlin-very-long-v...");
    assert_eq!(result.len(), 20);
}

#[test]
fn test_truncate_vm_name_exact_boundary() {
    let name = "exactly-twenty-chars";
    assert_eq!(name.len(), 20);
    assert_eq!(crate::display_helpers::truncate_vm_name(name, 20), name);
}

#[test]
fn test_format_tmux_sessions_empty() {
    let sessions: Vec<String> = vec![];
    assert_eq!(
        crate::display_helpers::format_tmux_sessions(&sessions, 3),
        "-"
    );
}

#[test]
fn test_format_tmux_sessions_few() {
    let sessions = vec!["main".to_string(), "dev".to_string()];
    assert_eq!(
        crate::display_helpers::format_tmux_sessions(&sessions, 3),
        "main, dev"
    );
}

#[test]
fn test_format_tmux_sessions_overflow() {
    let sessions: Vec<String> = (1..=5).map(|i| format!("s{}", i)).collect();
    let result = crate::display_helpers::format_tmux_sessions(&sessions, 3);
    assert_eq!(result, "s1, s2, s3, +2 more");
}

#[test]
fn test_reconnect_prompt_format() {
    let msg = crate::display_helpers::reconnect_prompt(2, 5);
    assert!(msg.contains("2/5"));
    assert!(msg.contains("[Y/n]"));
}

// ── tag_helpers tests ───────────────────────────────────────────

#[test]
fn test_parse_tag_key_value() {
    assert_eq!(
        crate::tag_helpers::parse_tag("env=production"),
        Some(("env", "production"))
    );
}

#[test]
fn test_parse_tag_missing_equals() {
    assert_eq!(crate::tag_helpers::parse_tag("justkey"), None);
}

#[test]
fn test_parse_tag_empty_key() {
    assert_eq!(crate::tag_helpers::parse_tag("=value"), None);
}

#[test]
fn test_parse_tag_embedded_equals() {
    assert_eq!(
        crate::tag_helpers::parse_tag("key=val=ue"),
        Some(("key", "val=ue"))
    );
}

#[test]
fn test_find_invalid_tag_all_valid() {
    let tags = vec!["a=1".to_string(), "b=2".to_string()];
    assert_eq!(crate::tag_helpers::find_invalid_tag(&tags), None);
}

#[test]
fn test_find_invalid_tag_has_bad() {
    let tags = vec!["a=1".to_string(), "bad".to_string(), "c=3".to_string()];
    assert_eq!(crate::tag_helpers::find_invalid_tag(&tags), Some("bad"));
}

// ── disk_helpers tests ──────────────────────────────────────────

#[test]
fn test_build_data_disk_name_lun0() {
    assert_eq!(
        crate::disk_helpers::build_data_disk_name("my-vm", 0),
        "my-vm_datadisk_0"
    );
}

#[test]
fn test_build_data_disk_name_lun5() {
    assert_eq!(
        crate::disk_helpers::build_data_disk_name("worker", 5),
        "worker_datadisk_5"
    );
}

#[test]
fn test_build_restored_disk_name() {
    assert_eq!(
        crate::disk_helpers::build_restored_disk_name("my-vm"),
        "my-vm_OsDisk_restored"
    );
}
