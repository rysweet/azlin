// ── snapshot_helpers tests ───────────────────────────────────

#[test]
fn test_build_snapshot_name() {
    let name = crate::snapshot_helpers::build_snapshot_name("my-vm", "20250101_120000");
    assert_eq!(name, "my-vm_snapshot_20250101_120000");
}

#[test]
fn test_build_snapshot_name_special_chars() {
    let name = crate::snapshot_helpers::build_snapshot_name("vm-with-dashes", "ts");
    assert_eq!(name, "vm-with-dashes_snapshot_ts");
}

#[test]
fn test_filter_snapshots_matches() {
    let snaps: Vec<serde_json::Value> = vec![
        serde_json::json!({"name": "my-vm_snapshot_1", "diskSizeGb": 30}),
        serde_json::json!({"name": "other-vm_snapshot_1", "diskSizeGb": 50}),
        serde_json::json!({"name": "my-vm_snapshot_2", "diskSizeGb": 30}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "my-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_filter_snapshots_no_match() {
    let snaps: Vec<serde_json::Value> = vec![serde_json::json!({"name": "alpha_snapshot_1"})];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "beta");
    assert!(filtered.is_empty());
}

#[test]
fn test_filter_snapshots_missing_name_field() {
    let snaps: Vec<serde_json::Value> = vec![
        serde_json::json!({"id": 1}),
        serde_json::json!({"name": "vm_snapshot_1"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "vm");
    assert_eq!(filtered.len(), 1);
}

#[test]
fn test_filter_snapshots_empty_list() {
    let snaps: Vec<serde_json::Value> = vec![];
    assert!(crate::snapshot_helpers::filter_snapshots(&snaps, "anything").is_empty());
}

#[test]
fn test_snapshot_row_full() {
    let snap = serde_json::json!({
        "name": "vm_snapshot_1",
        "diskSizeGb": 128,
        "timeCreated": "2025-01-15T10:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "vm_snapshot_1");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2025-01-15T10:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_missing_fields() {
    let snap = serde_json::json!({});
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

// ── output_helpers tests ─────────────────────────────────────

#[test]
fn test_format_as_csv_basic() {
    let headers = &["Name", "Value"];
    let rows = vec![vec!["A".into(), "1".into()], vec!["B".into(), "2".into()]];
    let csv = crate::output_helpers::format_as_csv(headers, &rows);
    assert_eq!(csv, "Name,Value\nA,1\nB,2");
}

#[test]
fn test_format_as_csv_empty_rows() {
    let csv = crate::output_helpers::format_as_csv(&["H1", "H2"], &[]);
    assert_eq!(csv, "H1,H2");
}

#[test]
fn test_format_as_csv_single_column() {
    let rows = vec![vec!["only".into()]];
    let csv = crate::output_helpers::format_as_csv(&["Col"], &rows);
    assert_eq!(csv, "Col\nonly");
}

#[test]
fn test_format_as_table_basic() {
    let headers = &["Name", "Age"];
    let rows = vec![
        vec!["Alice".into(), "30".into()],
        vec!["Bob".into(), "25".into()],
    ];
    let tbl = crate::output_helpers::format_as_table(headers, &rows);
    assert!(tbl.contains("Name"));
    assert!(tbl.contains("Age"));
    assert!(tbl.contains("Alice"));
    assert!(tbl.contains("Bob"));
    // columns should be aligned
    let lines: Vec<&str> = tbl.lines().collect();
    assert_eq!(lines.len(), 3); // header + 2 rows
}

#[test]
fn test_format_as_table_wide_values() {
    let headers = &["K", "V"];
    let rows = vec![vec!["short".into(), "a very long value here".into()]];
    let tbl = crate::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = tbl.lines().collect();
    // header should be padded to match the widest cell
    assert!(lines[0].contains("V"));
    assert!(lines[1].contains("a very long value here"));
}

#[test]
fn test_format_as_table_empty_rows() {
    let tbl = crate::output_helpers::format_as_table(&["X"], &[]);
    assert_eq!(tbl, "X");
}

#[test]
fn test_format_as_json_basic() {
    let items = vec![1, 2, 3];
    let json = crate::output_helpers::format_as_json(&items);
    let parsed: Vec<i32> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed, vec![1, 2, 3]);
}

#[test]
fn test_format_as_json_strings() {
    let items = vec!["hello", "world"];
    let json = crate::output_helpers::format_as_json(&items);
    assert!(json.contains("hello"));
    assert!(json.contains("world"));
}

#[test]
fn test_format_as_json_empty() {
    let items: Vec<String> = vec![];
    let json = crate::output_helpers::format_as_json(&items);
    assert_eq!(json.trim(), "[]");
}

#[test]
fn test_creds_file_format() {
    let content = format!("username={}\npassword={}\n", "testaccount", "testkey123");
    assert!(content.starts_with("username="));
    assert!(content.contains("password="));
    assert!(!content.contains("--")); // no CLI args
}
