use crate::*;
use std::fs;
use tempfile::TempDir;

// ── Security & business-logic tests ─────────────────────────────

// 1. Config path traversal
#[test]
fn test_config_path_traversal_blocked() {
    let result = crate::config_path_helpers::validate_config_path("../../etc/passwd");
    assert!(result.is_err(), "path traversal must be rejected");
    assert!(result.unwrap_err().contains("traversal"));
}

#[test]
fn test_config_path_traversal_deep() {
    let result = crate::config_path_helpers::validate_config_path("foo/../../../etc/shadow");
    assert!(result.is_err());
}

#[test]
fn test_config_path_safe_relative() {
    let result = crate::config_path_helpers::validate_config_path("config.toml");
    assert!(result.is_ok());
}

#[test]
fn test_config_path_safe_nested() {
    let result = crate::config_path_helpers::validate_config_path("subdir/config.toml");
    assert!(result.is_ok());
}

// 2. VM name validation
#[test]
fn test_vm_name_no_leading_hyphen() {
    let result = crate::vm_validation::validate_vm_name("-bad-name");
    assert!(result.is_err(), "leading hyphen must be rejected");
    assert!(result.unwrap_err().contains("hyphen"));
}

#[test]
fn test_vm_name_no_trailing_hyphen() {
    let result = crate::vm_validation::validate_vm_name("bad-name-");
    assert!(result.is_err(), "trailing hyphen must be rejected");
}

#[test]
fn test_vm_name_max_length() {
    let long_name = "a".repeat(65);
    let result = crate::vm_validation::validate_vm_name(&long_name);
    assert!(result.is_err(), "names > 64 chars must be rejected");
    assert!(result.unwrap_err().contains("64"));
}

#[test]
fn test_vm_name_exactly_64_chars() {
    let name = "a".repeat(64);
    let result = crate::vm_validation::validate_vm_name(&name);
    assert!(result.is_ok(), "exactly 64 chars should be allowed");
}

#[test]
fn test_vm_name_empty() {
    let result = crate::vm_validation::validate_vm_name("");
    assert!(result.is_err());
}

#[test]
fn test_vm_name_no_shell_metacharacters() {
    for bad in &["vm;rm", "vm$(whoami)", "vm`id`", "vm|cat", "vm&bg"] {
        let result = crate::vm_validation::validate_vm_name(bad);
        assert!(result.is_err(), "'{}' must be rejected", bad);
    }
}

#[test]
fn test_vm_name_valid() {
    assert!(crate::vm_validation::validate_vm_name("my-dev-vm-01").is_ok());
    assert!(crate::vm_validation::validate_vm_name("VM1").is_ok());
}

// 3. Env variable security
#[test]
fn test_env_key_no_command_injection() {
    let result = crate::env_helpers::validate_env_key("MY_VAR;rm -rf /");
    assert!(result.is_err(), "semicolons in key must be rejected");
}

#[test]
fn test_env_key_no_spaces() {
    let result = crate::env_helpers::validate_env_key("MY VAR");
    assert!(result.is_err(), "spaces in key must be rejected");
}

#[test]
fn test_env_key_no_equals() {
    let result = crate::env_helpers::validate_env_key("MY=VAR");
    assert!(result.is_err(), "equals in key must be rejected");
}

#[test]
fn test_env_key_no_dollar() {
    let result = crate::env_helpers::validate_env_key("$HOME");
    assert!(result.is_err(), "dollar sign in key must be rejected");
}

#[test]
fn test_env_key_no_leading_digit() {
    let result = crate::env_helpers::validate_env_key("9VAR");
    assert!(result.is_err(), "leading digit must be rejected");
}

#[test]
fn test_env_key_valid() {
    assert!(crate::env_helpers::validate_env_key("MY_VAR").is_ok());
    assert!(crate::env_helpers::validate_env_key("PATH").is_ok());
    assert!(crate::env_helpers::validate_env_key("_PRIVATE").is_ok());
}

#[test]
fn test_env_value_no_command_injection() {
    let escaped = crate::shell_escape("$(whoami)");
    // shell_escape wraps in single quotes, neutralizing $()
    assert!(escaped.starts_with('\''), "value must be single-quoted");
    assert!(escaped.ends_with('\''), "value must be single-quoted");
    // The $(whoami) is inside single quotes so won't execute
    let cmd = crate::env_helpers::build_env_set_cmd("MY_VAR", &escaped);
    assert!(cmd.contains("'$(whoami)'"), "injection must be quoted");
}

#[test]
fn test_env_value_semicolon_injection() {
    let escaped = crate::shell_escape("value; rm -rf /");
    let cmd = crate::env_helpers::build_env_set_cmd("VAR", &escaped);
    // The semicolon must be inside quotes, not acting as a command separator
    assert!(
        cmd.contains("'value; rm -rf /'"),
        "semicolon must be quoted, got: {}",
        cmd
    );
}

#[test]
fn test_env_set_cmd_rejects_bad_key() {
    let cmd = crate::env_helpers::build_env_set_cmd("BAD;KEY", "'safe_value'");
    // With a bad key, should return a no-op
    assert_eq!(cmd, "true", "bad key should produce no-op command");
}

// 4. Shell escape
#[test]
fn test_shell_escape_semicolons() {
    let escaped = crate::shell_escape("hello; rm -rf /");
    // Must be wrapped in single quotes
    assert!(escaped.starts_with('\''));
    assert!(escaped.ends_with('\''));
    assert!(escaped.contains("hello; rm -rf /"));
}

#[test]
fn test_shell_escape_backticks() {
    let escaped = crate::shell_escape("`whoami`");
    assert!(escaped.starts_with('\''), "backticks must be quoted");
    assert!(escaped.contains("`whoami`"));
}

#[test]
fn test_shell_escape_dollar_paren() {
    let escaped = crate::shell_escape("$(rm -rf /)");
    assert!(escaped.starts_with('\''));
    // The dangerous sequence is neutralized inside single quotes
    assert!(!escaped.starts_with("$("));
}

#[test]
fn test_shell_escape_single_quotes() {
    let escaped = crate::shell_escape("it's dangerous");
    // Single quotes within single-quoted strings need special escaping
    assert!(escaped.contains("'\\''"), "single quote must be escaped");
}

#[test]
fn test_shell_escape_empty_string_security() {
    let escaped = crate::shell_escape("");
    assert_eq!(escaped, "''");
}

#[test]
fn test_shell_escape_pipe() {
    let escaped = crate::shell_escape("data | cat /etc/passwd");
    assert!(escaped.starts_with('\''));
    assert!(escaped.ends_with('\''));
}

#[test]
fn test_shell_escape_newlines() {
    let escaped = crate::shell_escape("line1\nline2");
    assert!(escaped.starts_with('\''));
    assert!(escaped.ends_with('\''));
}

// 5. Mount path injection
#[test]
fn test_mount_path_no_semicolons() {
    let result = crate::mount_helpers::validate_mount_path("/mnt/data;rm -rf /");
    assert!(result.is_err(), "semicolons in mount path must be rejected");
}

#[test]
fn test_mount_path_no_pipe() {
    let result = crate::mount_helpers::validate_mount_path("/mnt/data|cat /etc/passwd");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_no_backticks() {
    let result = crate::mount_helpers::validate_mount_path("/mnt/`whoami`");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_no_dollar_paren() {
    let result = crate::mount_helpers::validate_mount_path("/mnt/$(id)");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_no_traversal() {
    let result = crate::mount_helpers::validate_mount_path("/mnt/../etc/shadow");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_requires_absolute() {
    let result = crate::mount_helpers::validate_mount_path("relative/path");
    assert!(result.is_err(), "relative paths must be rejected");
}

#[test]
fn test_mount_path_valid() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/data").is_ok());
    assert!(crate::mount_helpers::validate_mount_path("/mnt/azure-files").is_ok());
}

// 6. Dotfile sync security
#[test]
fn test_sync_rejects_sensitive_paths() {
    let result = crate::sync_helpers::validate_sync_source("/etc/shadow");
    assert!(result.is_err(), "sensitive system paths must be rejected");
}

#[test]
fn test_sync_rejects_var_paths() {
    let result = crate::sync_helpers::validate_sync_source("/var/log/syslog");
    assert!(result.is_err());
}

#[test]
fn test_sync_rejects_traversal() {
    let result = crate::sync_helpers::validate_sync_source("/home/user/../../../etc/passwd");
    assert!(result.is_err());
}

#[test]
fn test_sync_allows_home_dotfiles() {
    assert!(crate::sync_helpers::validate_sync_source("/home/user/.bashrc").is_ok());
    assert!(crate::sync_helpers::validate_sync_source(".bashrc").is_ok());
}

// 7. Health helpers edge cases
#[test]
fn test_health_percentage_negative() {
    assert_eq!(
        crate::health_helpers::format_percentage(-5.0),
        "0.0%",
        "negative percentages must clamp to 0"
    );
}

#[test]
fn test_health_percentage_zero() {
    assert_eq!(crate::health_helpers::format_percentage(0.0), "0.0%");
}

#[test]
fn test_health_percentage_over_100() {
    // Over-100 values are allowed (shows actual measurement)
    let result = crate::health_helpers::format_percentage(150.0);
    assert_eq!(result, "150.0%");
}
