use tempfile::TempDir;

// ── NEW: format_cost_summary additional tests ───────────────

#[test]
fn test_format_cost_summary_table_with_filters() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 150.75,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2025-01-01".into()),
        &Some("2025-01-31".into()),
        false,
        false,
    );
    assert!(out.contains("$150.75"));
    assert!(out.contains("From filter: 2025-01-01"));
    assert!(out.contains("To filter: 2025-01-31"));
}

#[test]
fn test_format_cost_summary_table_with_estimate() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        true,
        false,
    );
    assert!(out.contains("Estimate: $50.00/month (projected)"));
}

#[test]
fn test_format_cost_summary_by_vm_empty_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-06-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-06-30T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("No per-VM cost data available"));
}

#[test]
fn test_format_cost_summary_by_vm_csv_multi() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "vm-a".to_string(),
                cost: 120.50,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "vm-b".to_string(),
                cost: 79.50,
                currency: "USD".to_string(),
            },
        ],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("VM Name,Cost,Currency"));
    assert!(out.contains("vm-a,120.50,USD"));
    assert!(out.contains("vm-b,79.50,USD"));
}

#[test]
fn test_format_cost_summary_by_vm_table_format() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 300.0,
        currency: "EUR".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-03-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-03-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "prod-vm".to_string(),
            cost: 300.0,
            currency: "EUR".to_string(),
        }],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("$300.00 EUR"));
    assert!(out.contains("prod-vm"));
}

#[test]
fn test_format_cost_summary_json_output() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 99.99,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Json,
        &Some("ignored".into()),
        &Some("ignored".into()),
        true,
        true,
    );
    let parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
    assert_eq!(parsed["total_cost"].as_f64().unwrap(), 99.99);
    assert_eq!(parsed["currency"].as_str().unwrap(), "USD");
}

#[test]
fn test_format_cost_summary_csv_no_by_vm() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 42.0,
        currency: "GBP".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-02-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-02-28T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = crate::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        false,
    );
    assert!(out.starts_with("Total Cost,Currency,Period Start,Period End\n"));
    assert!(out.contains("42.00,GBP,2025-02-01,2025-02-28"));
}

// ── NEW: shell_escape additional tests ───────────────────────

#[test]
fn test_shell_escape_tab() {
    let result = crate::shell_escape("\t");
    assert_eq!(result, "'\t'");
}

#[test]
fn test_shell_escape_mixed_quotes() {
    let result = crate::shell_escape("it's a \"test\"");
    assert_eq!(result, "'it'\\''s a \"test\"'");
}

#[test]
fn test_shell_escape_backslash() {
    let result = crate::shell_escape("path\\to\\file");
    assert_eq!(result, "'path\\to\\file'");
}

#[test]
fn test_shell_escape_env_var_syntax() {
    let result = crate::shell_escape("${HOME}");
    assert_eq!(result, "'${HOME}'");
}

#[test]
fn test_shell_escape_command_substitution() {
    let result = crate::shell_escape("$(whoami)");
    assert_eq!(result, "'$(whoami)'");
}

#[test]
fn test_shell_escape_consecutive_single_quotes() {
    let result = crate::shell_escape("''");
    assert_eq!(result, "''\\'''\\'''");
}

// ── NEW: auth_test_helpers additional tests ─────────────────

#[test]
fn test_extract_account_info_nested_user() {
    let acct = serde_json::json!({
        "name": "Enterprise Sub",
        "tenantId": "t-abc-123",
        "user": {"name": "admin@contoso.com", "type": "servicePrincipal"}
    });
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "Enterprise Sub");
    assert_eq!(tenant, "t-abc-123");
    assert_eq!(user, "admin@contoso.com");
}

#[test]
fn test_extract_account_info_numeric_values() {
    let acct = serde_json::json!({
        "name": 123,
        "tenantId": 456,
        "user": {"name": 789}
    });
    let (sub, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── NEW: template file system edge cases ─────────────────────

#[test]
fn test_template_overwrite_existing() {
    let tmp = TempDir::new().unwrap();
    let tpl1 = crate::templates::build_template_toml("x", Some("v1"), None, None, None);
    crate::templates::save_template(tmp.path(), "x", &tpl1).unwrap();
    let tpl2 = crate::templates::build_template_toml("x", Some("v2"), None, None, None);
    crate::templates::save_template(tmp.path(), "x", &tpl2).unwrap();
    let loaded = crate::templates::load_template(tmp.path(), "x").unwrap();
    assert_eq!(loaded["description"].as_str().unwrap(), "v2");
}

#[test]
fn test_template_import_overwrites_existing() {
    let tmp = TempDir::new().unwrap();
    let tpl = crate::templates::build_template_toml("imp", Some("old"), None, None, None);
    crate::templates::save_template(tmp.path(), "imp", &tpl).unwrap();
    let content =
        "name = \"imp\"\ndescription = \"new\"\nvm_size = \"Standard_A1\"\nregion = \"westus\"\n";
    crate::templates::import_template(tmp.path(), content).unwrap();
    let loaded = crate::templates::load_template(tmp.path(), "imp").unwrap();
    assert_eq!(loaded["description"].as_str().unwrap(), "new");
}
