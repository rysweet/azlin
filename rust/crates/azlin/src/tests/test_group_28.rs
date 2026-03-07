use crate::*;
use std::fs;
use tempfile::TempDir;

// ── NEW: parse_cost_history_rows additional tests ────────────

#[test]
fn test_parse_cost_history_rows_no_rows_key() {
    let data = serde_json::json!({"other": "data"});
    let rows = crate::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_rows_not_array() {
    let data = serde_json::json!({"rows": "not-array"});
    let rows = crate::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_multiple_entries() {
    let data = serde_json::json!({
        "rows": [
            [10.5, "2025-01-01"],
            [20.0, "2025-01-02"],
            [0.0, "2025-01-03"]
        ]
    });
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0], ("2025-01-01".to_string(), "$10.50".to_string()));
    assert_eq!(rows[1], ("2025-01-02".to_string(), "$20.00".to_string()));
    assert_eq!(rows[2], ("2025-01-03".to_string(), "$0.00".to_string()));
}

#[test]
fn test_parse_cost_history_rows_integer_date() {
    let data = serde_json::json!({"rows": [[5.0, 20250101]]});
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    // Integer dates yield empty string due to as_str().or_else(as_i64 -> "") mapping
    assert_eq!(rows[0].0, "");
    assert_eq!(rows[0].1, "$5.00");
}

#[test]
fn test_parse_cost_history_rows_null_values() {
    let data = serde_json::json!({"rows": [[null, null]]});
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "-");
    assert_eq!(rows[0].1, "-");
}

// ── NEW: parse_recommendation_rows additional tests ─────────

#[test]
fn test_parse_recommendation_rows_null_input() {
    let data = serde_json::json!(null);
    let rows = crate::parse_recommendation_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_recommendation_rows_empty_array() {
    let data = serde_json::json!([]);
    let rows = crate::parse_recommendation_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_recommendation_rows_partial_fields() {
    let data = serde_json::json!([
        {"category": "Cost"},
        {"impact": "High"},
        {"shortDescription": {"problem": "Underutilized"}}
    ]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0], ("Cost".into(), "-".into(), "-".into()));
    assert_eq!(rows[1], ("-".into(), "High".into(), "-".into()));
    assert_eq!(rows[2], ("-".into(), "-".into(), "Underutilized".into()));
}

#[test]
fn test_parse_recommendation_rows_complete() {
    let data = serde_json::json!([{
        "category": "Cost",
        "impact": "Medium",
        "shortDescription": {"problem": "Resize VM to save money"}
    }]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].1, "Medium");
    assert_eq!(rows[0].2, "Resize VM to save money");
}

// ── NEW: parse_cost_action_rows additional tests ────────────

#[test]
fn test_parse_cost_action_rows_null_input() {
    let data = serde_json::json!(null);
    let rows = crate::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_action_rows_object_not_array() {
    let data = serde_json::json!({"key": "val"});
    let rows = crate::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_action_rows_complete() {
    let data = serde_json::json!([{
        "impactedField": "Microsoft.Compute/virtualMachines",
        "impact": "High",
        "shortDescription": {"problem": "Shut down unused VMs"}
    }]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
    assert_eq!(rows[0].1, "High");
    assert_eq!(rows[0].2, "Shut down unused VMs");
}

#[test]
fn test_parse_cost_action_rows_missing_all_fields() {
    let data = serde_json::json!([{}]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0], ("-".into(), "-".into(), "-".into()));
}

#[test]
fn test_parse_cost_action_rows_multiple() {
    let data = serde_json::json!([
        {"impactedField": "F1", "impact": "Low", "shortDescription": {"problem": "P1"}},
        {"impactedField": "F2", "impact": "High", "shortDescription": {"problem": "P2"}}
    ]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "F1");
    assert_eq!(rows[1].0, "F2");
}
