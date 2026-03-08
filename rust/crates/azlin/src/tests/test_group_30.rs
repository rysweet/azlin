#[allow(unused_imports)]
use crate::*;
use std::fs;
use tempfile::TempDir;

// ── NEW: session file persistence tests ──────────────────────

#[test]
fn test_session_save_then_list() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path().join("sessions");
    fs::create_dir_all(&dir).unwrap();
    for name in &["alpha", "beta", "gamma"] {
        let s = crate::sessions::build_session_toml(name, "rg", &[]);
        let content = toml::to_string_pretty(&s).unwrap();
        fs::write(dir.join(format!("{}.toml", name)), content).unwrap();
    }
    let names = crate::sessions::list_session_names(&dir).unwrap();
    assert_eq!(names.len(), 3);
    for expected in &["alpha", "beta", "gamma"] {
        assert!(names.contains(&expected.to_string()));
    }
}

#[test]
fn test_session_parse_with_many_vms() {
    let vms: Vec<String> = (0..20).map(|i| format!("vm-{:03}", i)).collect();
    let built = crate::sessions::build_session_toml("big", "rg-big", &vms);
    let serialized = toml::to_string_pretty(&built).unwrap();
    let (rg, parsed_vms, _) = crate::sessions::parse_session_toml(&serialized).unwrap();
    assert_eq!(rg, "rg-big");
    assert_eq!(parsed_vms.len(), 20);
    assert_eq!(parsed_vms[0], "vm-000");
    assert_eq!(parsed_vms[19], "vm-019");
}

// ── NEW: context file persistence tests ──────────────────────

#[test]
fn test_context_rename_preserves_other_fields() {
    let tmp = TempDir::new().unwrap();
    let content = crate::contexts::build_context_toml(
        "old",
        Some("sub-1"),
        Some("tenant-1"),
        Some("rg-1"),
        Some("westus2"),
        Some("kv-1"),
    )
    .unwrap();
    fs::write(tmp.path().join("old.toml"), content).unwrap();
    crate::contexts::rename_context_file(tmp.path(), "old", "new").unwrap();
    let loaded: toml::Value = fs::read_to_string(tmp.path().join("new.toml"))
        .unwrap()
        .parse()
        .unwrap();
    let t = loaded.as_table().unwrap();
    assert_eq!(t["name"].as_str().unwrap(), "new");
    assert_eq!(t["subscription_id"].as_str().unwrap(), "sub-1");
    assert_eq!(t["tenant_id"].as_str().unwrap(), "tenant-1");
    assert_eq!(t["resource_group"].as_str().unwrap(), "rg-1");
    assert_eq!(t["region"].as_str().unwrap(), "westus2");
    assert_eq!(t["key_vault_name"].as_str().unwrap(), "kv-1");
}

#[test]
fn test_context_list_sorted() {
    let tmp = TempDir::new().unwrap();
    for name in &["charlie", "alpha", "bravo"] {
        fs::write(
            tmp.path().join(format!("{}.toml", name)),
            format!("name = \"{}\"\n", name),
        )
        .unwrap();
    }
    let list = crate::contexts::list_contexts(tmp.path(), "bravo").unwrap();
    assert_eq!(list[0].0, "alpha");
    assert_eq!(list[1].0, "bravo");
    assert!(list[1].1);
    assert_eq!(list[2].0, "charlie");
}

// ── NEW: comprehensive validate_env_key tests ───────────────

#[test]
fn test_validate_env_key_all_digits() {
    assert!(crate::env_helpers::validate_env_key("123").is_err());
}

#[test]
fn test_validate_env_key_underscore_start() {
    assert!(crate::env_helpers::validate_env_key("_VAR").is_ok());
}

#[test]
fn test_validate_env_key_long_valid() {
    let key = "A".repeat(256);
    assert!(crate::env_helpers::validate_env_key(&key).is_ok());
}

#[test]
fn test_validate_env_key_tab() {
    assert!(crate::env_helpers::validate_env_key("A\tB").is_err());
}

#[test]
fn test_validate_env_key_newline() {
    assert!(crate::env_helpers::validate_env_key("A\nB").is_err());
}

// ── NEW: cp_helpers edge cases ──────────────────────────────

#[test]
fn test_is_remote_path_colon_at_end() {
    assert!(crate::cp_helpers::is_remote_path("vm:"));
}

#[test]
fn test_is_remote_path_long_vm_name() {
    assert!(crate::cp_helpers::is_remote_path(
        "my-long-vm-name-123:/data/dir"
    ));
}

#[test]
fn test_classify_both_remote() {
    // Both paths have colons and look remote, so neither condition
    // (remote+!remote or !remote+remote) matches — returns local→local
    let dir = crate::cp_helpers::classify_transfer_direction("vm1:/a", "vm2:/b");
    assert_eq!(dir, "local→local");
}

#[test]
fn test_resolve_scp_path_multiple_colons() {
    let result = crate::cp_helpers::resolve_scp_path("vm:path:with:colons", "vm", "u", "1.1.1.1");
    assert_eq!(result, "u@1.1.1.1:path:with:colons");
}

// ── NEW: output formatting with unicode ─────────────────────

#[test]
fn test_format_as_csv_unicode_content() {
    let rows = vec![vec!["名前".into(), "東京".into()]];
    let csv = crate::output_helpers::format_as_csv(&["Name", "City"], &rows);
    assert!(csv.contains("名前,東京"));
}

#[test]
fn test_format_as_table_unicode_alignment() {
    let rows = vec![vec!["日本語".into(), "データ".into()]];
    let table = crate::output_helpers::format_as_table(&["Label", "Value"], &rows);
    assert!(table.contains("日本語"));
    assert!(table.contains("データ"));
}

#[test]
fn test_format_as_csv_commas_in_values() {
    let rows = vec![vec!["a,b".into(), "c".into()]];
    let csv = crate::output_helpers::format_as_csv(&["X", "Y"], &rows);
    // Note: no escaping is done - this tests current behavior
    assert!(csv.contains("a,b,c"));
}

// ── NEW: snapshot filter edge cases ──────────────────────────

#[test]
fn test_filter_snapshots_substring_match() {
    let snaps = vec![
        serde_json::json!({"name": "vm1_snap"}),
        serde_json::json!({"name": "vm10_snap"}),
        serde_json::json!({"name": "vm1-extra_snap"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "vm1");
    // "vm1" is a substring of all three
    assert_eq!(filtered.len(), 3);
}

#[test]
fn test_filter_snapshots_case_sensitive() {
    let snaps = vec![
        serde_json::json!({"name": "VM1_snap"}),
        serde_json::json!({"name": "vm1_snap"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "vm1");
    assert_eq!(filtered.len(), 1);
}

// ── NEW: validate_mount_path traversal cases ────────────────

#[test]
fn test_mount_path_traversal_in_middle() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/a/../b").is_err());
}

#[test]
fn test_mount_path_traversal_at_end() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/..").is_err());
}

#[test]
fn test_mount_path_with_spaces_ok() {
    assert!(crate::mount_helpers::validate_mount_path("/mnt/my data").is_ok());
}

#[test]
fn test_mount_path_deeply_nested() {
    assert!(crate::mount_helpers::validate_mount_path("/a/b/c/d/e/f/g/h").is_ok());
}

// ── Additional shell_escape tests ───────────────────────────
#[test]
fn test_shell_escape_empty_v2() {
    assert_eq!(crate::shell_escape(""), "''");
}

#[test]
fn test_shell_escape_special_chars() {
    assert_eq!(crate::shell_escape("a b;c&d|e"), "'a b;c&d|e'");
}

#[test]
fn test_shell_escape_with_newlines_v2() {
    assert_eq!(crate::shell_escape("line1\nline2"), "'line1\nline2'");
}

// ── Additional parse tests ──────────────────────────────────
#[test]
fn test_parse_recommendation_rows_only_category() {
    let data = serde_json::json!([{
        "category": "Cost"
    }]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].1, "-");
}

#[test]
fn test_parse_recommendation_rows_two_entries() {
    let data = serde_json::json!([
        {"category": "Cost", "impact": "High", "shortDescription": {"problem": "idle VM"}},
        {"category": "Security", "impact": "Low", "shortDescription": {"problem": "no NSG"}}
    ]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[1].0, "Security");
}

#[test]
fn test_parse_cost_action_rows_missing_solution_field() {
    let data = serde_json::json!([{
        "category": "Cost",
        "impact": "Medium",
        "shortDescription": {}
    }]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].2, "-");
}

#[test]
fn test_parse_cost_action_rows_two_items() {
    let data = serde_json::json!([
        {"impactedField": "VM/compute", "impact": "High", "shortDescription": {"problem": "idle VM"}},
        {"impactedField": "Storage", "impact": "Low", "shortDescription": {"problem": "unattached disk"}}
    ]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "VM/compute");
    assert_eq!(rows[0].2, "idle VM");
    assert_eq!(rows[1].0, "Storage");
}
