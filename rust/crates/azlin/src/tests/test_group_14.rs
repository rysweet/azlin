use crate::*;
use std::fs;
use tempfile::TempDir;

// ── Tests for extracted helper functions ─────────────────────────

#[test]
fn test_format_cost_summary_json() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 123.45,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Json,
        &None,
        &None,
        false,
        false,
    );
    assert!(result.contains("123.45"));
    assert!(result.contains("USD"));
}

#[test]
fn test_format_cost_summary_csv() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 99.99,
        currency: "EUR".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        false,
    );
    assert!(result.contains("Total Cost,Currency,Period Start,Period End"));
    assert!(result.contains("99.99"));
    assert!(result.contains("EUR"));
}

#[test]
fn test_format_cost_summary_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        false,
    );
    assert!(result.contains("Total Cost: $50.00 USD"));
    assert!(result.contains("Period:"));
}

#[test]
fn test_format_cost_summary_with_estimate() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2024-01-01".to_string()),
        &Some("2024-01-31".to_string()),
        true,
        false,
    );
    assert!(result.contains("Estimate: $200.00/month (projected)"));
    assert!(result.contains("From filter: 2024-01-01"));
    assert!(result.contains("To filter: 2024-01-31"));
}

#[test]
fn test_format_cost_summary_by_vm_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 300.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "vm-1".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "vm-2".to_string(),
                cost: 200.0,
                currency: "USD".to_string(),
            },
        ],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(result.contains("vm-1"));
    assert!(result.contains("vm-2"));
    assert!(result.contains("$100.00"));
    assert!(result.contains("$200.00"));
}

#[test]
fn test_format_cost_summary_by_vm_csv() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 150.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "test-vm".to_string(),
            cost: 150.0,
            currency: "USD".to_string(),
        }],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(result.contains("VM Name,Cost,Currency"));
    assert!(result.contains("test-vm,150.00,USD"));
}

#[test]
fn test_format_cost_summary_by_vm_empty() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 0.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(result.contains("No per-VM cost data available."));
}

#[test]
fn test_parse_cost_history_rows_empty() {
    let data = serde_json::json!({});
    let rows = crate::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_with_data() {
    let data = serde_json::json!({
        "rows": [
            [12.34, "2024-01-01"],
            [56.78, "2024-01-02"]
        ]
    });
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0], ("2024-01-01".to_string(), "$12.34".to_string()));
    assert_eq!(rows[1], ("2024-01-02".to_string(), "$56.78".to_string()));
}

#[test]
fn test_parse_cost_history_rows_with_int_date() {
    let data = serde_json::json!({
        "rows": [
            [10.0, 20240101]
        ]
    });
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    // Integer dates hit the as_i64().map(|_| "") branch, producing empty string
    assert_eq!(rows[0].0, "");
    assert_eq!(rows[0].1, "$10.00");
}

#[test]
fn test_parse_cost_history_rows_missing_values() {
    let data = serde_json::json!({
        "rows": [
            [null, null]
        ]
    });
    let rows = crate::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "-");
    assert_eq!(rows[0].1, "-");
}

#[test]
fn test_parse_recommendation_rows_empty() {
    let data = serde_json::json!([]);
    let rows = crate::parse_recommendation_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_recommendation_rows_with_data() {
    let data = serde_json::json!([
        {
            "category": "Cost",
            "impact": "High",
            "shortDescription": {"problem": "Underutilized VM"}
        },
        {
            "category": "Security",
            "impact": "Medium",
            "shortDescription": {"problem": "Open port"}
        }
    ]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(
        rows[0],
        (
            "Cost".to_string(),
            "High".to_string(),
            "Underutilized VM".to_string()
        )
    );
    assert_eq!(
        rows[1],
        (
            "Security".to_string(),
            "Medium".to_string(),
            "Open port".to_string()
        )
    );
}

#[test]
fn test_parse_recommendation_rows_missing_fields() {
    let data = serde_json::json!([{"other_field": "value"}]);
    let rows = crate::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0], ("-".to_string(), "-".to_string(), "-".to_string()));
}

#[test]
fn test_parse_cost_action_rows_empty() {
    let data = serde_json::json!([]);
    let rows = crate::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_action_rows_with_data() {
    let data = serde_json::json!([
        {
            "impactedField": "Microsoft.Compute/virtualMachines",
            "impact": "High",
            "shortDescription": {"problem": "Resize VM"}
        }
    ]);
    let rows = crate::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
    assert_eq!(rows[0].1, "High");
    assert_eq!(rows[0].2, "Resize VM");
}
