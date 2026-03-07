use crate::*;
use std::fs;
use tempfile::TempDir;

// ── runner_helpers tests ────────────────────────────────────────

#[test]
fn test_build_runner_vm_name() {
    assert_eq!(
        crate::runner_helpers::build_runner_vm_name("ci-pool", 0),
        "azlin-runner-ci-pool-1"
    );
    assert_eq!(
        crate::runner_helpers::build_runner_vm_name("ci-pool", 2),
        "azlin-runner-ci-pool-3"
    );
}

#[test]
fn test_build_runner_tags() {
    let tags = crate::runner_helpers::build_runner_tags("ci-pool", "user/repo");
    assert!(tags.contains("azlin-runner=true"));
    assert!(tags.contains("pool=ci-pool"));
    assert!(tags.contains("repo=user/repo"));
}

#[test]
fn test_build_runner_config_fields() {
    let config = crate::runner_helpers::build_runner_config(
        "ci-pool",
        "user/repo",
        3,
        "self-hosted,linux",
        "my-rg",
        "Standard_D4s_v3",
        "2024-03-15T00:00:00Z",
    );
    let keys: Vec<&str> = config.iter().map(|(k, _)| k.as_str()).collect();
    assert!(keys.contains(&"pool"));
    assert!(keys.contains(&"repo"));
    assert!(keys.contains(&"count"));
    assert!(keys.contains(&"labels"));
    assert!(keys.contains(&"resource_group"));
    assert!(keys.contains(&"vm_size"));
    assert!(keys.contains(&"enabled"));
    assert!(keys.contains(&"created"));

    let count = config
        .iter()
        .find(|(k, _)| k == "count")
        .map(|(_, v)| v.as_integer().unwrap())
        .unwrap();
    assert_eq!(count, 3);
}

#[test]
fn test_pool_config_filename() {
    assert_eq!(
        crate::runner_helpers::pool_config_filename("ci-pool"),
        "ci-pool.toml"
    );
}

// ── autopilot_helpers tests ─────────────────────────────────────

#[test]
fn test_build_autopilot_config_with_budget() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        Some(500),
        "aggressive",
        30,
        80,
        "2024-03-15T00:00:00Z",
    );
    let tbl = config.as_table().unwrap();
    assert_eq!(tbl["enabled"].as_bool(), Some(true));
    assert_eq!(tbl["budget"].as_integer(), Some(500));
    assert_eq!(tbl["strategy"].as_str(), Some("aggressive"));
    assert_eq!(tbl["idle_threshold_minutes"].as_integer(), Some(30));
    assert_eq!(tbl["cpu_threshold_percent"].as_integer(), Some(80));
}

#[test]
fn test_build_autopilot_config_without_budget() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        None,
        "conservative",
        60,
        50,
        "2024-03-15T00:00:00Z",
    );
    let tbl = config.as_table().unwrap();
    assert!(tbl.get("budget").is_none());
    assert_eq!(tbl["strategy"].as_str(), Some("conservative"));
}

#[test]
fn test_build_budget_name() {
    assert_eq!(
        crate::autopilot_helpers::build_budget_name("my-rg"),
        "azlin-budget-my-rg"
    );
}

#[test]
fn test_build_prefix_filter_query() {
    let q = crate::autopilot_helpers::build_prefix_filter_query("azlin-vm");
    assert_eq!(q, "[?starts_with(name, 'azlin-vm')].id");
}

#[test]
fn test_build_cost_scope() {
    let scope = crate::autopilot_helpers::build_cost_scope("sub-123", "my-rg");
    assert_eq!(scope, "/subscriptions/sub-123/resourceGroups/my-rg");
}

// ── config_path_helpers tests ───────────────────────────────────

#[test]
fn test_validate_config_path_safe() {
    assert!(crate::config_path_helpers::validate_config_path("config.toml").is_ok());
    assert!(crate::config_path_helpers::validate_config_path("subdir/config.toml").is_ok());
}

#[test]
fn test_validate_config_path_traversal_rejected() {
    assert!(crate::config_path_helpers::validate_config_path("../etc/passwd").is_err());
    assert!(crate::config_path_helpers::validate_config_path("subdir/../../etc/shadow").is_err());
}

// ── snapshot_helpers additional tests ────────────────────────────

#[test]
fn test_snapshot_row_full_data() {
    let snap = serde_json::json!({
        "name": "vm1_snapshot_20240315",
        "diskSizeGb": 128,
        "timeCreated": "2024-03-15T12:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "vm1_snapshot_20240315");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2024-03-15T12:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_defaults_for_empty_json() {
    let snap = serde_json::json!({});
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

#[test]
fn test_snapshot_schedule_path_format() {
    let path = crate::snapshot_helpers::schedule_path("my-vm");
    assert!(path.to_string_lossy().contains("my-vm.toml"));
    assert!(path.to_string_lossy().contains("schedules"));
}

// ── output_helpers edge case tests ──────────────────────────────

#[test]
fn test_format_as_table_header_only_no_rows() {
    let out = crate::output_helpers::format_as_table(&["Name", "Value"], &[]);
    assert_eq!(out, "Name  Value");
}

#[test]
fn test_format_as_table_renders_single_col() {
    let rows = vec![vec!["alpha".to_string()], vec!["beta".to_string()]];
    let out = crate::output_helpers::format_as_table(&["Items"], &rows);
    assert!(out.contains("Items"));
    assert!(out.contains("alpha"));
    assert!(out.contains("beta"));
}

#[test]
fn test_format_as_csv_header_only() {
    let out = crate::output_helpers::format_as_csv(&["Name", "Size"], &[]);
    assert_eq!(out, "Name,Size");
}

#[test]
fn test_format_as_json_empty_slice() {
    let items: Vec<String> = vec![];
    let out = crate::output_helpers::format_as_json(&items);
    assert_eq!(out, "[]");
}

#[test]
fn test_format_as_json_with_data() {
    let items = vec!["hello", "world"];
    let out = crate::output_helpers::format_as_json(&items);
    assert!(out.contains("hello"));
    assert!(out.contains("world"));
}

// ── parse_cost_history_rows tests ───────────────────────────────

#[test]
fn test_parse_cost_history_no_rows_key() {
    let data = serde_json::json!({});
    let rows = crate::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_valid() {
    let data = serde_json::json!({
        "rows": [
            [12.50, "2024-03-01"],
            [8.75, "2024-03-02"]
        ]
    });
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "2024-03-01");
    assert_eq!(rows[0].1, "$12.50");
    assert_eq!(rows[1].0, "2024-03-02");
    assert_eq!(rows[1].1, "$8.75");
}

#[test]
fn test_parse_cost_history_numeric_date() {
    // When date is an integer, the parser maps it to empty string via the
    // `as_str().or_else(|| as_i64().map(|_| ""))` branch.
    let data = serde_json::json!({
        "rows": [
            [5.00, 20240301]
        ]
    });
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].1, "$5.00");
    // Integer dates produce an empty string via the current parser logic
    assert_eq!(rows[0].0, "");
}

#[test]
fn test_parse_cost_history_rows_empty_array() {
    let data = serde_json::json!({ "rows": [] });
    let rows = crate::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

// ── storage_helpers additional tests ─────────────────────────────

#[test]
fn test_storage_account_row_all_fields() {
    let acct = serde_json::json!({
        "name": "mystorageacct",
        "location": "westus2",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "mystorageacct");
    assert_eq!(row[1], "westus2");
    assert_eq!(row[2], "StorageV2");
    assert_eq!(row[3], "Standard_LRS");
    assert_eq!(row[4], "Succeeded");
}

#[test]
fn test_storage_account_row_missing() {
    let acct = serde_json::json!({});
    let row = crate::storage_helpers::storage_account_row(&acct);
    assert!(row.iter().all(|c| c == "-"));
}
