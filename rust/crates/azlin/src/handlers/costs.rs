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
/// The impact levels Azure Advisor actually returns.
///
/// `azlin costs actions --priority` promised "Filter by priority" and was
/// discarded (#1089), so every recommendation was listed *and applied*
/// whatever the user asked for — `--priority high apply` deallocated VMs the
/// filter existed to exclude. Advisor calls the field `impact`; the flag calls
/// it priority. They are the same thing.
pub const KNOWN_PRIORITIES: [&str; 3] = ["High", "Medium", "Low"];

/// The spelling Advisor uses, from whatever the user typed, or `None` if it is
/// not a level Advisor reports.
///
/// JMESPath's `==` is case-sensitive, so `--priority high` passed through
/// unchanged would match nothing and report "no recommendations" — a filter
/// that silently excludes everything is the failure this issue is about.
pub fn canonical_priority(priority: &str) -> Option<&'static str> {
    KNOWN_PRIORITIES
        .iter()
        .find(|k| k.eq_ignore_ascii_case(priority.trim()))
        .copied()
}

/// Reject a priority Azure Advisor will never report.
///
/// Called by [`build_advisor_args`], and again by the handlers *before* they
/// check the resource group — because that check is a network call, and a
/// typo in `--priority` should not cost a round-trip or arrive disguised as
/// somebody else's authorisation error.
pub fn validate_priority(priority: Option<&str>) -> Result<(), String> {
    let Some(value) = priority else {
        return Ok(());
    };
    if canonical_priority(value).is_some() {
        return Ok(());
    }
    Err(format!(
        "Unknown --priority '{}'. Azure Advisor reports impact as one of: {}.",
        value,
        KNOWN_PRIORITIES.join(", ")
    ))
}

/// What to ask before `costs actions apply` deallocates anything.
///
/// Names the count and the filter, because "apply 12 recommendations" and
/// "apply the 2 High-impact ones" are different decisions and the user has
/// only the prompt to tell them apart.
pub fn confirm_apply_prompt(count: usize, priority: Option<&str>, resource_group: &str) -> String {
    match priority {
        Some(pri) => format!(
            "Apply {} {} cost recommendation(s) in '{}'? This deallocates the VMs listed above.",
            count,
            canonical_priority(pri).unwrap_or(pri),
            resource_group
        ),
        None => format!(
            "Apply {} cost recommendation(s) in '{}'? This deallocates the VMs listed above.",
            count, resource_group
        ),
    }
}

/// What to say when a valid priority matched nothing.
///
/// Distinct from "this resource group has no cost recommendations", because
/// the two send the user to different places.
pub fn no_actions_at_priority(resource_group: &str, priority: &str) -> String {
    format!(
        "No {} cost recommendations for '{}'. Drop --priority to see the other levels.",
        canonical_priority(priority).unwrap_or(priority),
        resource_group
    )
}

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

/// Build advisor recommendation query args, optionally for one impact level.
///
/// The category filter is not optional: `azlin costs actions` is about cost,
/// and this builder previously *replaced* the whole query when a priority was
/// given — so wiring `--priority` through it unchanged would have widened the
/// command from cost recommendations to every recommendation Advisor has,
/// security ones included, and then offered to apply them.
///
/// Filtering server-side means the table and the apply loop read the same
/// list. A client-side filter over the table alone would have left
/// `--priority high apply` deallocating Low-impact VMs while showing only the
/// High ones — the worst of both.
///
/// An unrecognised priority is an error rather than an empty table: Advisor
/// would match nothing and the command would exit 0 saying there was nothing
/// to do. Validating here rather than at the call site also means the value
/// interpolated into JMESPath is always one of [`KNOWN_PRIORITIES`].
pub fn build_advisor_args(
    resource_group: &str,
    priority: Option<&str>,
) -> Result<Vec<String>, String> {
    validate_priority(priority)?;
    let query = match priority {
        Some(pri) => format!(
            "[?category=='Cost' && impact=='{}']",
            canonical_priority(pri).unwrap_or_default()
        ),
        None => "[?category=='Cost']".to_string(),
    };
    Ok(vec![
        "advisor".to_string(),
        "recommendation".to_string(),
        "list".to_string(),
        "--resource-group".to_string(),
        resource_group.to_string(),
        "--query".to_string(),
        query,
        "-o".to_string(),
        "json".to_string(),
    ])
}

#[cfg(test)]
mod priority_tests {
    use super::*;

    #[test]
    fn the_category_filter_survives_a_priority() {
        let args = build_advisor_args("rg", Some("high")).unwrap();
        let query = args.iter().find(|a| a.contains("category")).unwrap();
        assert!(query.contains("category=='Cost'"), "{}", query);
        assert!(query.contains("impact=='High'"), "{}", query);
    }

    #[test]
    fn without_a_priority_the_query_is_still_scoped_to_cost() {
        let args = build_advisor_args("rg", None).unwrap();
        let query = args.iter().find(|a| a.contains("category")).unwrap();
        assert_eq!(query, "[?category=='Cost']");
    }

    #[test]
    fn the_users_spelling_is_translated_to_advisors() {
        // JMESPath `==` is case-sensitive; a passthrough matches nothing.
        for typed in ["high", "HIGH", "  High  "] {
            let args = build_advisor_args("rg", Some(typed)).unwrap();
            assert!(
                args.iter().any(|a| a.contains("impact=='High'")),
                "{} did not reach Advisor's spelling",
                typed
            );
        }
    }

    #[test]
    fn an_unknown_priority_is_an_error_not_an_empty_table() {
        let err = build_advisor_args("rg", Some("urgent")).unwrap_err();
        assert!(err.contains("urgent"), "{}", err);
        assert!(err.contains("High, Medium, Low"), "{}", err);
    }

    #[test]
    fn a_quote_cannot_reach_the_query() {
        // The value is interpolated into JMESPath, so nothing but the three
        // known levels may get through.
        assert!(build_advisor_args("rg", Some("high' || 'x")).is_err());
        assert_eq!(canonical_priority("high' || 'x"), None);
    }

    #[test]
    fn the_apply_prompt_names_the_count_and_the_filter() {
        let filtered = confirm_apply_prompt(2, Some("high"), "rg");
        assert!(filtered.contains("2 High"), "{}", filtered);
        assert!(filtered.contains("deallocates"), "{}", filtered);

        // "apply 12" and "apply the 2 High ones" are different decisions.
        let all = confirm_apply_prompt(12, None, "rg");
        assert!(all.contains("12 cost recommendation"), "{}", all);
        assert!(!all.contains("High"), "{}", all);
    }

    #[test]
    fn an_empty_result_at_a_priority_says_which_one() {
        let msg = no_actions_at_priority("rg", "high");
        assert!(msg.contains("No High"), "{}", msg);
        assert!(msg.contains("Drop --priority"), "{}", msg);
    }
}
