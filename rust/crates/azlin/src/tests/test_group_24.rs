use crate::*;
use std::fs;
use tempfile::TempDir;

// ── NEW: contexts edge-case tests ────────────────────────────

#[test]
fn test_context_build_toml_minimal() {
    let toml_str =
        crate::contexts::build_context_toml("dev", None, None, None, None, None).unwrap();
    assert!(toml_str.contains("name = \"dev\""));
    assert!(!toml_str.contains("subscription_id"));
}

#[test]
fn test_context_build_toml_all_fields() {
    let toml_str = crate::contexts::build_context_toml(
        "prod",
        Some("sub-123"),
        Some("tenant-456"),
        Some("rg-prod"),
        Some("eastus2"),
        Some("kv-prod"),
    )
    .unwrap();
    assert!(toml_str.contains("name = \"prod\""));
    assert!(toml_str.contains("subscription_id = \"sub-123\""));
    assert!(toml_str.contains("tenant_id = \"tenant-456\""));
    assert!(toml_str.contains("resource_group = \"rg-prod\""));
    assert!(toml_str.contains("region = \"eastus2\""));
    assert!(toml_str.contains("key_vault_name = \"kv-prod\""));
}

#[test]
fn test_context_build_toml_partial_fields() {
    let toml_str = crate::contexts::build_context_toml(
        "staging",
        Some("sub-789"),
        None,
        Some("rg-staging"),
        None,
        None,
    )
    .unwrap();
    assert!(toml_str.contains("name = \"staging\""));
    assert!(toml_str.contains("subscription_id = \"sub-789\""));
    assert!(toml_str.contains("resource_group = \"rg-staging\""));
    assert!(!toml_str.contains("tenant_id"));
    assert!(!toml_str.contains("region"));
    assert!(!toml_str.contains("key_vault_name"));
}

#[test]
fn test_context_list_empty_dir() {
    let tmp = TempDir::new().unwrap();
    let list = crate::contexts::list_contexts(tmp.path(), "").unwrap();
    assert!(list.is_empty());
}

#[test]
fn test_context_list_marks_active_correctly() {
    let tmp = TempDir::new().unwrap();
    for name in &["dev", "staging", "prod"] {
        let content =
            crate::contexts::build_context_toml(name, None, None, None, None, None).unwrap();
        fs::write(tmp.path().join(format!("{}.toml", name)), content).unwrap();
    }
    let list = crate::contexts::list_contexts(tmp.path(), "staging").unwrap();
    assert_eq!(list.len(), 3);
    for (name, active) in &list {
        if name == "staging" {
            assert!(active, "staging should be active");
        } else {
            assert!(!active, "{} should not be active", name);
        }
    }
}

#[test]
fn test_context_list_ignores_non_toml() {
    let tmp = TempDir::new().unwrap();
    fs::write(tmp.path().join("dev.toml"), "name = \"dev\"\n").unwrap();
    fs::write(tmp.path().join("notes.txt"), "ignore").unwrap();
    let list = crate::contexts::list_contexts(tmp.path(), "").unwrap();
    assert_eq!(list.len(), 1);
    assert_eq!(list[0].0, "dev");
}

#[test]
fn test_context_rename_success() {
    let tmp = TempDir::new().unwrap();
    let content = crate::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
    fs::write(tmp.path().join("old.toml"), content).unwrap();
    crate::contexts::rename_context_file(tmp.path(), "old", "new").unwrap();
    assert!(!tmp.path().join("old.toml").exists());
    assert!(tmp.path().join("new.toml").exists());
    let loaded: toml::Value = fs::read_to_string(tmp.path().join("new.toml"))
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(loaded["name"].as_str().unwrap(), "new");
}

#[test]
fn test_context_rename_not_found() {
    let tmp = TempDir::new().unwrap();
    let err = crate::contexts::rename_context_file(tmp.path(), "ghost", "new").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

// ── NEW: env_helpers additional edge cases ───────────────────

#[test]
fn test_split_env_var_equals_in_value() {
    let result = crate::env_helpers::split_env_var("DB_URL=postgres://host:5432/db?opt=val");
    assert_eq!(result, Some(("DB_URL", "postgres://host:5432/db?opt=val")));
}

#[test]
fn test_split_env_var_empty_string() {
    assert_eq!(crate::env_helpers::split_env_var(""), None);
}

#[test]
fn test_split_env_var_just_equals() {
    assert_eq!(crate::env_helpers::split_env_var("="), None);
}

#[test]
fn test_validate_env_key_underscores() {
    assert!(crate::env_helpers::validate_env_key("MY_VAR_123").is_ok());
}

#[test]
fn test_validate_env_key_single_char() {
    assert!(crate::env_helpers::validate_env_key("X").is_ok());
}

#[test]
fn test_validate_env_key_with_dash() {
    assert!(crate::env_helpers::validate_env_key("MY-VAR").is_err());
}

#[test]
fn test_validate_env_key_with_dot() {
    assert!(crate::env_helpers::validate_env_key("my.var").is_err());
}

#[test]
fn test_validate_env_key_unicode() {
    assert!(crate::env_helpers::validate_env_key("café").is_err());
}

#[test]
fn test_build_env_set_cmd_valid_key() {
    let cmd = crate::env_helpers::build_env_set_cmd("FOO", "'bar'");
    assert!(cmd.contains("FOO"));
    assert!(cmd.contains("'bar'"));
    assert!(cmd.contains("grep"));
}

#[test]
fn test_build_env_set_cmd_invalid_key_returns_noop() {
    let cmd = crate::env_helpers::build_env_set_cmd("BAD;KEY", "'val'");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_delete_cmd_format() {
    let cmd = crate::env_helpers::build_env_delete_cmd("MY_VAR");
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("MY_VAR"));
}

#[test]
fn test_env_list_cmd_value() {
    assert_eq!(crate::env_helpers::env_list_cmd(), "env | sort");
}

#[test]
fn test_env_clear_cmd_value() {
    let cmd = crate::env_helpers::env_clear_cmd();
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("export"));
}

#[test]
fn test_parse_env_output_multiline() {
    let output = "A=1\nB=two\nC=three=3\nD=\n";
    let vars = crate::env_helpers::parse_env_output(output);
    assert_eq!(vars.len(), 4);
    assert_eq!(vars[0], ("A".into(), "1".into()));
    assert_eq!(vars[1], ("B".into(), "two".into()));
    assert_eq!(vars[2], ("C".into(), "three=3".into()));
    assert_eq!(vars[3], ("D".into(), "".into()));
}

#[test]
fn test_build_env_file_multiple() {
    let vars = vec![("K1".into(), "v1".into()), ("K2".into(), "v2".into())];
    let file = crate::env_helpers::build_env_file(&vars);
    assert_eq!(file, "K1=v1\nK2=v2");
}

#[test]
fn test_parse_env_file_mixed_content() {
    let content = "# comment\n\nFOO=bar\n  # another comment  \n  BAZ=qux  \n\n";
    let vars = crate::env_helpers::parse_env_file(content);
    assert_eq!(vars.len(), 2);
    assert_eq!(vars[0], ("FOO".into(), "bar".into()));
    assert_eq!(vars[1], ("BAZ".into(), "qux".into()));
}

#[test]
fn test_env_file_build_then_parse_roundtrip() {
    let original = vec![
        ("PATH".into(), "/usr/bin".into()),
        ("HOME".into(), "/home/user".into()),
    ];
    let file = crate::env_helpers::build_env_file(&original);
    let parsed = crate::env_helpers::parse_env_file(&file);
    assert_eq!(parsed, original);
}

// ── NEW: sync_helpers additional tests ───────────────────────

#[test]
fn test_default_dotfiles_count() {
    let df = crate::sync_helpers::default_dotfiles();
    assert!(df.len() >= 4);
    assert!(df.contains(&".bashrc"));
    assert!(df.contains(&".gitconfig"));
}

#[test]
fn test_validate_sync_source_etc() {
    assert!(crate::sync_helpers::validate_sync_source("/etc/passwd").is_err());
}

#[test]
fn test_validate_sync_source_proc() {
    assert!(crate::sync_helpers::validate_sync_source("/proc/1/status").is_err());
}

#[test]
fn test_validate_sync_source_sys() {
    assert!(crate::sync_helpers::validate_sync_source("/sys/class/net").is_err());
}

#[test]
fn test_validate_sync_source_root() {
    assert!(crate::sync_helpers::validate_sync_source("/root/secret").is_err());
}

#[test]
fn test_validate_sync_source_traversal_end() {
    assert!(crate::sync_helpers::validate_sync_source("foo/..").is_err());
}

#[test]
fn test_validate_sync_source_double_dot_bare() {
    assert!(crate::sync_helpers::validate_sync_source("..").is_err());
}

#[test]
fn test_validate_sync_source_safe_home() {
    assert!(crate::sync_helpers::validate_sync_source("/home/user/.bashrc").is_ok());
}

#[test]
fn test_validate_sync_source_relative() {
    assert!(crate::sync_helpers::validate_sync_source("src/main.rs").is_ok());
}

#[test]
fn test_build_rsync_args_format() {
    let args = crate::sync_helpers::build_rsync_args(".bashrc", "admin", "10.0.0.1", ".bashrc");
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert_eq!(args[2], "ssh -o StrictHostKeyChecking=accept-new");
    assert_eq!(args[3], ".bashrc");
    assert_eq!(args[4], "admin@10.0.0.1:~/.bashrc");
}

#[test]
fn test_build_rsync_args_with_subpath() {
    let args = crate::sync_helpers::build_rsync_args("config/", "user", "192.168.1.1", "config/");
    assert_eq!(args[4], "user@192.168.1.1:~/config/");
}
