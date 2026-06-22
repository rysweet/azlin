//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Cost summary formatting ─────────────────────────────────────────

/// Format a cost summary for display. Supports JSON, CSV, and table output.
pub fn format_cost_summary(
    summary: &azlin_core::models::CostSummary,
    output_format: &str,
    from: &Option<String>,
    to: &Option<String>,
    estimate: bool,
    by_vm: bool,
) -> String {
    let mut out = String::new();
    if output_format == "json" {
        match serde_json::to_string_pretty(summary) {
            Ok(json) => out.push_str(&json),
            Err(e) => out.push_str(&format!("Failed to serialize cost data: {e}")),
        }
        return out;
    }

    let is_csv = output_format == "csv";

    if is_csv {
        out.push_str("Total Cost,Currency,Period Start,Period End\n");
        out.push_str(&format!(
            "{:.2},{},{},{}",
            summary.total_cost,
            summary.currency,
            summary.period_start.format("%Y-%m-%d"),
            summary.period_end.format("%Y-%m-%d")
        ));
    } else {
        out.push_str(&format!(
            "Total Cost: ${:.2} {}",
            summary.total_cost, summary.currency
        ));
        out.push_str(&format!(
            "\nPeriod: {} to {}",
            summary.period_start.format("%Y-%m-%d"),
            summary.period_end.format("%Y-%m-%d")
        ));

        if let Some(ref f) = from {
            out.push_str(&format!("\nFrom filter: {}", f));
        }
        if let Some(ref t) = to {
            out.push_str(&format!("\nTo filter: {}", t));
        }
        if estimate {
            out.push_str(&format!(
                "\nEstimate: ${:.2}/month (projected)",
                summary.total_cost
            ));
        }
    }

    if by_vm && !summary.by_vm.is_empty() {
        if is_csv {
            out.push_str("\nVM Name,Cost,Currency");
            for vc in &summary.by_vm {
                out.push_str(&format!("\n{},{:.2},{}", vc.vm_name, vc.cost, vc.currency));
            }
        } else {
            out.push('\n');
            for vc in &summary.by_vm {
                out.push_str(&format!(
                    "\n{:<20} ${:.2} {}",
                    vc.vm_name, vc.cost, vc.currency
                ));
            }
        }
    } else if by_vm {
        out.push_str("\n\nNo per-VM cost data available.");
    }

    out
}

// ── Cost data parsing ───────────────────────────────────────────────

/// Parse cost history rows from JSON data into (date, cost) pairs.
pub fn parse_cost_history_rows(data: &serde_json::Value) -> Vec<(String, String)> {
    let mut result = Vec::new();
    if let Some(rows) = data.get("rows").and_then(|r| r.as_array()) {
        for row in rows {
            if let Some(arr) = row.as_array() {
                let cost = arr
                    .first()
                    .and_then(|v| v.as_f64())
                    .map(|v| format!("${:.2}", v))
                    .unwrap_or_else(|| "-".to_string());
                let date = arr
                    .get(1)
                    .and_then(|v| v.as_str().or_else(|| v.as_i64().map(|_| "")))
                    .map(|s| s.to_string())
                    .or_else(|| arr.get(1).and_then(|v| v.as_i64()).map(|v| v.to_string()))
                    .unwrap_or_else(|| "-".to_string());
                result.push((date, cost));
            }
        }
    }
    result
}

/// Parse recommendation entries from JSON array.
pub fn parse_recommendation_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    let mut result = Vec::new();
    if let Some(recs) = data.as_array() {
        for rec in recs {
            let category = rec
                .get("category")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let impact = rec
                .get("impact")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let problem = rec
                .get("shortDescription")
                .and_then(|v| v.get("problem"))
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            result.push((category, impact, problem));
        }
    }
    result
}

/// Parse cost action entries from JSON array.
pub fn parse_cost_action_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    let mut result = Vec::new();
    if let Some(recs) = data.as_array() {
        for rec in recs {
            let resource = rec
                .get("impactedField")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let impact = rec
                .get("impact")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let problem = rec
                .get("shortDescription")
                .and_then(|v| v.get("problem"))
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            result.push((resource, impact, problem));
        }
    }
    result
}

// ── Cost dashboard formatting ────────────────────────────────────────

/// Format the cost dashboard output for a resource group.
pub fn format_cost_dashboard(
    resource_group: &str,
    total_cost: f64,
    currency: &str,
    period_start: &str,
    period_end: &str,
) -> String {
    let mut out = format!("Cost Dashboard for '{}':\n", resource_group);
    out.push_str(&format!("  Total: ${:.2} {}\n", total_cost, currency));
    out.push_str(&format!("  Period: {} to {}", period_start, period_end));
    out
}

/// Build the scope string for Azure Cost Management queries.
pub fn build_cost_management_scope(subscription_id: &str, resource_group: &str) -> String {
    format!(
        "/subscriptions/{}/resourceGroups/{}",
        subscription_id, resource_group
    )
}

/// Build the budget name for a resource group.
pub fn build_budget_name(resource_group: &str) -> String {
    format!("azlin-budget-{}", resource_group)
}

/// Format the budget creation result message.
pub fn format_budget_created(amount: f64, resource_group: &str, threshold: u32) -> String {
    format!(
        "Budget set: ${:.2}/month for '{}' (alert at {}%)",
        amount, resource_group, threshold
    )
}

/// Determine the date range for cost history queries.
pub fn build_cost_history_dates(days: u32) -> (String, String) {
    let now = chrono::Utc::now();
    let start = (now - chrono::Duration::days(days as i64))
        .format("%Y-%m-%dT00:00:00+00:00")
        .to_string();
    let end = now.format("%Y-%m-%dT23:59:59+00:00").to_string();
    (start, end)
}

// ── Costs formatting handlers ───────────────────────────────────────────

/// Format cost history table header text.
pub fn format_cost_history_header(resource_group: &str, days: u32) -> String {
    format!(
        "Cost history for '{}' (last {} days):",
        resource_group, days
    )
}

/// Format recommendation display header.
pub fn format_recommendations_header(resource_group: &str) -> String {
    format!("Cost recommendations for '{}':", resource_group)
}

/// Format the "no recommendations" message.
pub fn format_no_recommendations(resource_group: &str, priority: &str) -> String {
    format!(
        "No cost recommendations found for '{}' (priority: {})",
        resource_group, priority
    )
}

/// Format the budget list empty message.
pub fn format_no_budgets(resource_group: &str) -> String {
    format!("No budgets found for '{}'.", resource_group)
}

/// Format the budget deleted message.
pub fn format_budget_deleted(resource_group: &str) -> String {
    format!("Budget deleted for '{}'.", resource_group)
}

/// Format "no pending cost actions" message.
pub fn format_no_cost_actions(resource_group: &str) -> String {
    format!("No pending cost actions in '{}'", resource_group)
}

/// Format cost actions header (with or without dry_run).
pub fn format_cost_actions_header(action: &str, resource_group: &str, dry_run: bool) -> String {
    if dry_run {
        format!(
            "Would {} the following cost actions in '{}':",
            action, resource_group
        )
    } else {
        format!("Cost actions ({}) in '{}':", action, resource_group)
    }
}

/// Build advisor recommendation query args with optional priority filter.
pub fn build_advisor_args(resource_group: &str, priority: Option<&str>) -> Vec<String> {
    let mut args = vec![
        "advisor".to_string(),
        "recommendation".to_string(),
        "list".to_string(),
        "--resource-group".to_string(),
        resource_group.to_string(),
        "-o".to_string(),
        "json".to_string(),
    ];
    if let Some(pri) = priority {
        args.push("--query".to_string());
        args.push(format!("[?impact=='{}']", pri));
    }
    args
}
