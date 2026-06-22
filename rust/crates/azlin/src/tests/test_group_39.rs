use std::fs;
use tempfile::TempDir;

// ── env_helpers edge cases ──────────────────────────────────────

#[test]
fn test_validate_env_key_empty_is_error() {
    assert!(crate::env_helpers::validate_env_key("").is_err());
    let err = crate::env_helpers::validate_env_key("").unwrap_err();
    assert!(err.contains("must not be empty"));
}

#[test]
fn test_validate_env_key_starting_with_digit_is_error() {
    let err = crate::env_helpers::validate_env_key("1ABC").unwrap_err();
    assert!(err.contains("must not start with a digit"));
}

#[test]
fn test_validate_env_key_special_chars_rejected() {
    assert!(crate::env_helpers::validate_env_key("MY-VAR").is_err());
    assert!(crate::env_helpers::validate_env_key("MY.VAR").is_err());
    assert!(crate::env_helpers::validate_env_key("MY VAR").is_err());
    assert!(crate::env_helpers::validate_env_key("MY$VAR").is_err());
}

#[test]
fn test_build_env_set_cmd_with_invalid_key_returns_noop() {
    let cmd = crate::env_helpers::build_env_set_cmd("BAD-KEY!", "'value'");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_set_cmd_valid_contains_grep_and_sed() {
    let cmd = crate::env_helpers::build_env_set_cmd("MY_VAR", "'hello'");
    assert!(cmd.contains("grep"));
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("MY_VAR"));
    assert!(cmd.contains("'hello'"));
}

#[test]
fn test_parse_env_file_skips_comments_and_blanks() {
    let content = "# comment\n\nFOO=bar\n  # another comment\nBAZ=qux\n\n";
    let result = crate::env_helpers::parse_env_file(content);
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], ("FOO".to_string(), "bar".to_string()));
    assert_eq!(result[1], ("BAZ".to_string(), "qux".to_string()));
}

#[test]
fn test_build_env_file_and_parse_roundtrip() {
    let vars = vec![
        ("PATH".to_string(), "/usr/bin".to_string()),
        ("HOME".to_string(), "/home/user".to_string()),
        ("LANG".to_string(), "en_US.UTF-8".to_string()),
    ];
    let file_content = crate::env_helpers::build_env_file(&vars);
    let parsed = crate::env_helpers::parse_env_file(&file_content);
    assert_eq!(parsed, vars);
}

#[test]
fn test_split_env_var_normal() {
    let result = crate::env_helpers::split_env_var("KEY=VALUE");
    assert_eq!(result, Some(("KEY", "VALUE")));
}

#[test]
fn test_split_env_var_embedded_equals_sign() {
    let result = crate::env_helpers::split_env_var("KEY=VAL=UE");
    assert_eq!(result, Some(("KEY", "VAL=UE")));
}

#[test]
fn test_split_env_var_no_equals_returns_none() {
    assert!(crate::env_helpers::split_env_var("NOEQUALS").is_none());
}

// ── sync_helpers ────────────────────────────────────────────────

#[test]
fn test_validate_sync_source_traversal_variants() {
    // "/../" in the middle
    assert!(crate::sync_helpers::validate_sync_source("foo/../bar").is_err());
    // Ends with "/.."
    assert!(crate::sync_helpers::validate_sync_source("foo/..").is_err());
    // Just ".."
    assert!(crate::sync_helpers::validate_sync_source("..").is_err());
    // Safe relative path is OK
    assert!(crate::sync_helpers::validate_sync_source("mydir/file").is_ok());
}

#[test]
fn test_validate_sync_source_forbidden_prefixes() {
    for prefix in &[
        "/etc/passwd",
        "/var/log",
        "/root/.ssh",
        "/proc/cpuinfo",
        "/sys/devices",
    ] {
        let result = crate::sync_helpers::validate_sync_source(prefix);
        assert!(result.is_err(), "Expected error for prefix: {}", prefix);
    }
}

#[test]
fn test_build_rsync_args_correct_format() {
    let args = crate::sync_helpers::build_rsync_args(".bashrc", "azureuser", "10.0.0.1", ".bashrc");
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert!(args[2].contains("StrictHostKeyChecking=accept-new"));
    assert_eq!(args[3], ".bashrc");
    assert_eq!(args[4], "azureuser@10.0.0.1:~/.bashrc");
}

#[test]
fn test_default_dotfiles_contains_expected() {
    let dotfiles = crate::sync_helpers::default_dotfiles();
    assert!(dotfiles.contains(&".bashrc"));
    assert!(dotfiles.contains(&".profile"));
    assert!(dotfiles.contains(&".gitconfig"));
    assert!(dotfiles.len() >= 4);
}

// ── health_helpers edge cases ───────────────────────────────────

#[test]
fn test_status_emoji_all_values_low() {
    assert_eq!(crate::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
}

#[test]
fn test_status_emoji_one_high() {
    assert_eq!(crate::health_helpers::status_emoji(95.0, 20.0, 30.0), "🔴");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 91.0, 30.0), "🔴");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 20.0, 95.0), "🔴");
}

#[test]
fn test_status_emoji_medium() {
    assert_eq!(crate::health_helpers::status_emoji(75.0, 20.0, 30.0), "🟡");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 80.0, 30.0), "🟡");
}

#[test]
fn test_metric_color_boundary_values() {
    assert_eq!(crate::health_helpers::metric_color(50.0), "green");
    assert_eq!(crate::health_helpers::metric_color(50.1), "yellow");
    assert_eq!(crate::health_helpers::metric_color(80.0), "yellow");
    assert_eq!(crate::health_helpers::metric_color(80.1), "red");
}

#[test]
fn test_state_color_all_variants() {
    assert_eq!(crate::health_helpers::state_color("running"), "green");
    assert_eq!(crate::health_helpers::state_color("stopped"), "red");
    assert_eq!(crate::health_helpers::state_color("deallocated"), "red");
    assert_eq!(crate::health_helpers::state_color("starting"), "yellow");
    assert_eq!(crate::health_helpers::state_color("random"), "yellow");
}

#[test]
fn test_format_percentage_large_value() {
    let result = crate::health_helpers::format_percentage(100.0);
    assert_eq!(result, "100.0%");
}

#[test]
fn test_format_percentage_zero() {
    assert_eq!(crate::health_helpers::format_percentage(0.0), "0.0%");
}

// ── snapshot_helpers ────────────────────────────────────────────

#[test]
fn test_filter_snapshots_partial_name_match() {
    let snapshots = vec![
        serde_json::json!({"name": "dev-vm_snapshot_20240101"}),
        serde_json::json!({"name": "prod-vm_snapshot_20240101"}),
        serde_json::json!({"name": "dev-vm_snapshot_20240102"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snapshots, "dev-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_snapshot_schedule_full_lifecycle() {
    let tmp = TempDir::new().unwrap();
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "test-vm".to_string(),
        resource_group: "test-rg".to_string(),
        every_hours: 6,
        keep_count: 10,
        enabled: true,
        created: "2024-01-15T10:00:00Z".to_string(),
    };

    // Serialize and write
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    let path = tmp.path().join("test-vm.toml");
    fs::write(&path, &toml_str).unwrap();

    // Read back and deserialize
    let content = fs::read_to_string(&path).unwrap();
    let loaded: crate::snapshot_helpers::SnapshotSchedule = toml::from_str(&content).unwrap();
    assert_eq!(loaded.vm_name, "test-vm");
    assert_eq!(loaded.every_hours, 6);
    assert_eq!(loaded.keep_count, 10);
    assert!(loaded.enabled);
}

// ── output_helpers ──────────────────────────────────────────────

#[test]
fn test_format_as_table_multirow() {
    let headers = &["Name", "Size", "Status"];
    let rows = vec![
        vec![
            "vm-1".to_string(),
            "Standard_B2s".to_string(),
            "Running".to_string(),
        ],
        vec![
            "vm-2-long-name".to_string(),
            "Standard_D4s_v3".to_string(),
            "Stopped".to_string(),
        ],
    ];
    let table = crate::output_helpers::format_as_table(headers, &rows);
    assert!(table.contains("Name"));
    assert!(table.contains("vm-1"));
    assert!(table.contains("vm-2-long-name"));
    // Verify alignment: wider columns expand
    let lines: Vec<&str> = table.lines().collect();
    assert_eq!(lines.len(), 3); // header + 2 rows
}

#[test]
fn test_format_as_csv_with_data() {
    let headers = &["Name", "Cost"];
    let rows = vec![
        vec!["vm-1".to_string(), "$10.50".to_string()],
        vec!["vm-2".to_string(), "$20.00".to_string()],
    ];
    let csv = crate::output_helpers::format_as_csv(headers, &rows);
    let lines: Vec<&str> = csv.lines().collect();
    assert_eq!(lines[0], "Name,Cost");
    assert_eq!(lines[1], "vm-1,$10.50");
    assert_eq!(lines[2], "vm-2,$20.00");
}

#[test]
fn test_format_as_json_custom_structs() {
    #[derive(serde::Serialize)]
    struct Item {
        name: String,
        value: i32,
    }
    let items = vec![
        Item {
            name: "a".to_string(),
            value: 1,
        },
        Item {
            name: "b".to_string(),
            value: 2,
        },
    ];
    let json = crate::output_helpers::format_as_json(&items);
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed.len(), 2);
    assert_eq!(parsed[0]["name"], "a");
    assert_eq!(parsed[1]["value"], 2);
}
