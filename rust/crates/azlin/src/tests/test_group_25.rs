// ── NEW: health_helpers boundary tests ───────────────────────

#[test]
fn test_metric_color_exact_50() {
    assert_eq!(crate::health_helpers::metric_color(50.0), "green");
}

#[test]
fn test_metric_color_exact_80() {
    assert_eq!(crate::health_helpers::metric_color(80.0), "yellow");
}

#[test]
fn test_metric_color_just_above_80() {
    assert_eq!(crate::health_helpers::metric_color(80.1), "red");
}

#[test]
fn test_metric_color_just_above_50() {
    assert_eq!(crate::health_helpers::metric_color(50.1), "yellow");
}

#[test]
fn test_metric_color_zero() {
    assert_eq!(crate::health_helpers::metric_color(0.0), "green");
}

#[test]
fn test_metric_color_100() {
    assert_eq!(crate::health_helpers::metric_color(100.0), "red");
}

#[test]
fn test_state_color_deallocated() {
    assert_eq!(crate::health_helpers::state_color("deallocated"), "red");
}

#[test]
fn test_state_color_starting() {
    assert_eq!(crate::health_helpers::state_color("starting"), "yellow");
}

#[test]
fn test_state_color_empty_string() {
    assert_eq!(crate::health_helpers::state_color(""), "yellow");
}

#[test]
fn test_format_percentage_large() {
    assert_eq!(crate::health_helpers::format_percentage(99.99), "100.0%");
}

#[test]
fn test_format_percentage_very_negative() {
    assert_eq!(crate::health_helpers::format_percentage(-100.0), "0.0%");
}

#[test]
fn test_format_percentage_exactly_zero() {
    assert_eq!(crate::health_helpers::format_percentage(0.0), "0.0%");
}

#[test]
fn test_status_emoji_all_low() {
    assert_eq!(crate::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
}

#[test]
fn test_status_emoji_cpu_critical() {
    assert_eq!(crate::health_helpers::status_emoji(91.0, 10.0, 10.0), "🔴");
}

#[test]
fn test_status_emoji_mem_critical() {
    assert_eq!(crate::health_helpers::status_emoji(10.0, 95.0, 10.0), "🔴");
}

#[test]
fn test_status_emoji_disk_critical() {
    assert_eq!(crate::health_helpers::status_emoji(10.0, 10.0, 91.0), "🔴");
}

#[test]
fn test_status_emoji_cpu_warning() {
    assert_eq!(crate::health_helpers::status_emoji(75.0, 10.0, 10.0), "🟡");
}

#[test]
fn test_status_emoji_exact_boundary_70() {
    assert_eq!(crate::health_helpers::status_emoji(70.0, 70.0, 70.0), "🟢");
}

#[test]
fn test_status_emoji_exact_boundary_90() {
    assert_eq!(crate::health_helpers::status_emoji(90.0, 90.0, 90.0), "🟡");
}

// ── NEW: snapshot_helpers additional tests ───────────────────

#[test]
fn test_build_snapshot_name_format() {
    let name = crate::snapshot_helpers::build_snapshot_name("my-vm", "20250101_120000");
    assert_eq!(name, "my-vm_snapshot_20250101_120000");
}

#[test]
fn test_build_snapshot_name_with_dashes() {
    let name = crate::snapshot_helpers::build_snapshot_name("vm-with-dashes", "ts");
    assert_eq!(name, "vm-with-dashes_snapshot_ts");
}

#[test]
fn test_filter_snapshots_partial_match() {
    let snaps = vec![
        serde_json::json!({"name": "dev-vm_snapshot_123"}),
        serde_json::json!({"name": "prod-vm_snapshot_456"}),
        serde_json::json!({"name": "dev-vm_snapshot_789"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "dev-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_snapshot_row_complete() {
    let snap = serde_json::json!({
        "name": "snap-1",
        "diskSizeGb": 128,
        "timeCreated": "2025-01-01T00:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "snap-1");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2025-01-01T00:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_null_fields() {
    let snap = serde_json::json!({});
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

// ── NEW: output_helpers additional tests ─────────────────────

#[test]
fn test_format_as_csv_multiple_rows() {
    let headers = &["Name", "Age", "City"];
    let rows = vec![
        vec!["Alice".into(), "30".into(), "NYC".into()],
        vec!["Bob".into(), "25".into(), "LA".into()],
    ];
    let csv = crate::output_helpers::format_as_csv(headers, &rows);
    let lines: Vec<&str> = csv.lines().collect();
    assert_eq!(lines[0], "Name,Age,City");
    assert_eq!(lines[1], "Alice,30,NYC");
    assert_eq!(lines[2], "Bob,25,LA");
}

#[test]
fn test_format_as_csv_single_row() {
    let csv = crate::output_helpers::format_as_csv(&["X"], &[vec!["1".into()]]);
    assert_eq!(csv, "X\n1");
}

#[test]
fn test_format_as_table_alignment() {
    let headers = &["Short", "LongerHeader"];
    let rows = vec![vec!["a".into(), "b".into()], vec!["ccc".into(), "d".into()]];
    let table = crate::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = table.lines().collect();
    assert_eq!(lines.len(), 3);
    // Header line should have both column names
    assert!(lines[0].contains("Short"));
    assert!(lines[0].contains("LongerHeader"));
}

#[test]
fn test_format_as_table_single_column() {
    let table = crate::output_helpers::format_as_table(
        &["Items"],
        &[vec!["one".into()], vec!["two".into()]],
    );
    assert!(table.contains("Items"));
    assert!(table.contains("one"));
    assert!(table.contains("two"));
}

#[test]
fn test_format_as_table_no_rows() {
    let table = crate::output_helpers::format_as_table(&["A", "B"], &[]);
    assert!(table.contains("A"));
    assert!(table.contains("B"));
    assert_eq!(table.lines().count(), 1);
}

#[test]
fn test_format_as_table_wide_cell_expands_column() {
    let headers = &["H"];
    let rows = vec![vec!["very long cell content".into()]];
    let table = crate::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = table.lines().collect();
    // The header line should be padded to at least the width of the cell
    assert!(lines[0].len() >= "very long cell content".len());
}

#[test]
fn test_format_as_json_numbers() {
    let items: Vec<i32> = vec![1, 2, 3];
    let json = crate::output_helpers::format_as_json(&items);
    let parsed: Vec<i32> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed, vec![1, 2, 3]);
}

#[test]
fn test_format_as_json_empty_vec() {
    let items: Vec<String> = vec![];
    let json = crate::output_helpers::format_as_json(&items);
    assert_eq!(json.trim(), "[]");
}

#[test]
fn test_format_as_json_structs() {
    let items = vec![
        serde_json::json!({"name": "a"}),
        serde_json::json!({"name": "b"}),
    ];
    let json = crate::output_helpers::format_as_json(&items);
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed.len(), 2);
}
