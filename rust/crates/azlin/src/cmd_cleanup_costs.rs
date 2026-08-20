#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) fn dispatch_costs(action: azlin_cli::CostsAction) -> Result<()> {
    match action {
        azlin_cli::CostsAction::Dashboard { resource_group, .. } => {
            let auth = create_auth()?;
            let cost_timeout = azlin_core::AzlinConfig::load()
                .map(|c| c.az_cli_timeout)
                .unwrap_or(120);
            // Every fetch below can fail, and every failure used to be
            // swallowed into an empty vector. The dashboard then summed
            // nothing and printed `$-0.00` with exit 0 — a spend report
            // produced entirely from data it never obtained. Failures are
            // collected here and reported alongside whatever did arrive.
            let mut unavailable: Vec<String> = Vec::new();
            // Fetch cost summary for budget info
            let budget_info =
                match azlin_azure::get_cost_summary(&auth, &resource_group, cost_timeout) {
                    Ok(summary) => Some(crate::cost_dashboard::BudgetInfo {
                        // Filled in below if a budget is actually configured.
                        limit: None,
                        current_spend: summary.total_cost,
                        currency: summary.currency.clone(),
                    }),
                    Err(e) => {
                        unavailable.push(format!(
                            "Cost summary unavailable: {}",
                            azlin_core::sanitizer::sanitize(&e.to_string())
                        ));
                        None
                    }
                };
            let end_date = chrono::Utc::now();
            let start_date = end_date - chrono::Duration::days(30);
            let start_str = start_date.format("%Y-%m-%d").to_string();
            let end_str = end_date.format("%Y-%m-%d").to_string();
            let (daily_costs, vm_costs) = match azlin_azure::vm::az_cli_with_timeout(
                &[
                    "consumption",
                    "usage",
                    "list",
                    "--start-date",
                    &start_str,
                    "--end-date",
                    &end_str,
                ],
                cost_timeout,
            ) {
                Ok(json) => match serde_json::from_str::<Vec<serde_json::Value>>(&json) {
                    Ok(entries) => {
                        let unreadable = crate::cost_dashboard::count_unreadable_costs(&entries);
                        if unreadable > 0 {
                            // Folded in as 0.0 by the parsers below, which
                            // would show up as a cheaper month rather than as
                            // a problem.
                            unavailable.push(format!(
                                "{} of {} usage rows had no readable cost and are missing \
                                 from the figures below.",
                                unreadable,
                                entries.len()
                            ));
                        }
                        (
                            Some(crate::cost_dashboard::parse_daily_costs(&entries)),
                            Some(crate::cost_dashboard::parse_vm_costs(&entries)),
                        )
                    }
                    Err(e) => {
                        // A parse failure is not "no usage". Before this, a
                        // schema change in `az consumption` would have read
                        // as a month that cost nothing.
                        unavailable.push(format!("Usage data could not be parsed: {}", e));
                        (None, None)
                    }
                },
                Err(e) => {
                    unavailable.push(format!(
                        "Usage data unavailable: {}",
                        azlin_core::sanitizer::sanitize(&e.to_string())
                    ));
                    (None, None)
                }
            };
            let budget = {
                let budget_name = crate::handlers::build_budget_name(&resource_group);
                match std::process::Command::new("az")
                    .args([
                        "consumption",
                        "budget",
                        "show",
                        "--budget-name",
                        &budget_name,
                        "--resource-group",
                        &resource_group,
                        "-o",
                        "json",
                    ])
                    .output()
                {
                    Ok(o) if o.status.success() => {
                        let json_str = String::from_utf8_lossy(&o.stdout);
                        // `amount` missing or unparsable leaves the limit
                        // unknown rather than zero: a ceiling of 0 made
                        // `usage_pct()` answer 0% and painted the gauge green.
                        let limit = serde_json::from_str::<serde_json::Value>(&json_str)
                            .ok()
                            .and_then(|parsed| parsed.get("amount").and_then(|v| v.as_f64()));
                        if limit.is_none() {
                            unavailable.push(format!(
                                "Budget '{}' returned no usable 'amount'; \
                                 spend is shown without a limit.",
                                budget_name
                            ));
                        }
                        budget_info.map(|mut b| {
                            b.limit = limit;
                            b
                        })
                    }
                    // No budget configured is the common case and not an
                    // error; the spend is still shown, just without a
                    // ceiling to measure it against.
                    _ => budget_info,
                }
            };
            let data = crate::cost_dashboard::CostDashboardData {
                resource_group: resource_group.clone(),
                daily_costs,
                vm_costs,
                budget,
                period_label: "Last 30 days".to_string(),
                unavailable,
            };
            // Nothing arrived at all: there is no dashboard to draw, and
            // drawing an empty one that reports a total of zero is the
            // failure this change exists to remove.
            if data.is_empty_of_data() {
                anyhow::bail!(
                    "No cost data could be retrieved for '{}':\n  {}\n\
                     Hint: cost queries need the Cost Management Reader role \
                     on the subscription; check with \
                     `az consumption usage list --start-date {} --end-date {}`.",
                    resource_group,
                    data.unavailable.join("\n  "),
                    start_str,
                    end_str
                );
            }
            crate::cost_dashboard::run_cost_dashboard(&data)?;
        }
        azlin_cli::CostsAction::History {
            resource_group,
            days,
        } => {
            let cost_timeout = azlin_core::AzlinConfig::load()
                .map(|c| c.az_cli_timeout)
                .unwrap_or(120);

            let end_date = chrono::Utc::now();
            let start_date = end_date - chrono::Duration::days(days as i64);
            let start_str = start_date.format("%Y-%m-%d").to_string();
            let end_str = end_date.format("%Y-%m-%d").to_string();

            // Use az consumption usage list — same API as costs dashboard
            let json = match azlin_azure::vm::az_cli_with_timeout(
                &[
                    "consumption",
                    "usage",
                    "list",
                    "--start-date",
                    &start_str,
                    "--end-date",
                    &end_str,
                ],
                cost_timeout,
            ) {
                Ok(j) => j,
                Err(e) => {
                    // Not `return Ok(())`. Printing a warning and exiting 0
                    // meant a scheduled cost check went green having fetched
                    // nothing at all.
                    anyhow::bail!(
                        "Cost history unavailable for '{}': {}\n\
                         Hint: cost queries need the Cost Management Reader role on the \
                         subscription; check with `az consumption usage list --start-date \
                         {} --end-date {}`.",
                        resource_group,
                        azlin_core::sanitizer::sanitize(&e.to_string()),
                        start_str,
                        end_str
                    );
                }
            };

            let entries: Vec<serde_json::Value> =
                serde_json::from_str(&json).context("Failed to parse cost data JSON")?;

            // Aggregate costs by date
            let mut date_costs: std::collections::BTreeMap<String, f64> =
                std::collections::BTreeMap::new();
            // Rows whose cost will not parse are counted, not silently
            // added as zero: a schema change would otherwise show up as a
            // cheaper month rather than as a problem.
            let mut unparsable_rows = 0usize;
            for entry in &entries {
                let date = entry
                    .get("usageStart")
                    .and_then(|v| v.as_str())
                    .and_then(|s| s.get(..10))
                    .unwrap_or("unknown");
                match entry.get("pretaxCost").and_then(|v| v.as_f64()) {
                    Some(cost) => *date_costs.entry(date.to_string()).or_insert(0.0) += cost,
                    None => unparsable_rows += 1,
                }
            }

            println!(
                "{}",
                crate::handlers::format_cost_history_header(&resource_group, days)
            );

            if date_costs.is_empty() {
                println!("No cost data available for the last {} days.", days);
            } else {
                let mut table =
                    crate::table_render::SimpleTable::new(&["Date", "Cost (USD)"], &[12, 14]);
                let mut total = 0.0;
                for (date, cost) in &date_costs {
                    table.add_row(vec![date.clone(), format!("${:.2}", cost)]);
                    total += cost;
                }
                println!("{table}");
                println!("Total: ${:.2} ({} days with data)", total, date_costs.len());
            }
            if unparsable_rows > 0 {
                eprintln!(
                    "⚠ {} of {} usage rows had no readable cost and are missing from the \
                     total above.",
                    unparsable_rows,
                    entries.len()
                );
            }
        }
        azlin_cli::CostsAction::Budget {
            action,
            resource_group,
            amount,
            threshold,
        } => match action.as_str() {
            "create" | "set" => {
                let budget_amount = amount.unwrap_or(100.0);
                let alert_threshold = threshold.unwrap_or(80);
                let budget_name = crate::handlers::build_budget_name(&resource_group);
                let output = std::process::Command::new("az")
                    .args([
                        "consumption",
                        "budget",
                        "create",
                        "--budget-name",
                        &budget_name,
                        "--amount",
                        &format!("{:.2}", budget_amount),
                        "--time-grain",
                        "Monthly",
                        "--resource-group",
                        &resource_group,
                        "--category",
                        "Cost",
                        "--output",
                        "json",
                    ])
                    .output()?;
                if output.status.success() {
                    println!(
                        "{}",
                        crate::handlers::format_budget_created(
                            budget_amount,
                            &resource_group,
                            alert_threshold,
                        )
                    );
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to create budget: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            "show" | "list" => {
                let output = std::process::Command::new("az")
                    .args([
                        "consumption",
                        "budget",
                        "list",
                        "--resource-group",
                        &resource_group,
                        "--output",
                        "table",
                    ])
                    .output()?;
                if output.status.success() {
                    let text = String::from_utf8_lossy(&output.stdout);
                    if text.trim().is_empty() {
                        println!("{}", crate::handlers::format_no_budgets(&resource_group));
                    } else {
                        print!("{}", text);
                    }
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    eprintln!(
                        "Failed to list budgets: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            "delete" => {
                let budget_name = crate::handlers::build_budget_name(&resource_group);
                let output = std::process::Command::new("az")
                    .args([
                        "consumption",
                        "budget",
                        "delete",
                        "--budget-name",
                        &budget_name,
                        "--resource-group",
                        &resource_group,
                    ])
                    .output()?;
                if output.status.success() {
                    println!(
                        "{}",
                        crate::handlers::format_budget_deleted(&resource_group)
                    );
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    eprintln!(
                        "Failed to delete budget: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            _ => {
                anyhow::bail!(
                    "Unknown budget action '{}'. Use: create, show, delete",
                    action
                );
            }
        },
        azlin_cli::CostsAction::Recommend { .. } | azlin_cli::CostsAction::Actions { .. } => {
            crate::cmd_cleanup_costs2::dispatch_costs_extended(action)?;
        }
    }
    Ok(())
}
