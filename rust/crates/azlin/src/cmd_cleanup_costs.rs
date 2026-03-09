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
            match azlin_azure::get_cost_summary(&auth, &resource_group, cost_timeout) {
                Ok(summary) => {
                    println!(
                        "{}",
                        crate::handlers::format_cost_dashboard(
                            &resource_group,
                            summary.total_cost,
                            &summary.currency,
                            &summary.period_start.format("%Y-%m-%d").to_string(),
                            &summary.period_end.format("%Y-%m-%d").to_string(),
                        )
                    );
                }
                Err(e) => {
                    eprintln!("⚠ Cost data unavailable: {e}");
                    eprintln!("  Run 'az consumption usage list' for cost data via Azure CLI.");
                }
            }
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
                    eprintln!(
                        "⚠ Cost history unavailable: {}",
                        azlin_core::sanitizer::sanitize(&e.to_string())
                    );
                    eprintln!(
                        "  Run 'az consumption usage list' for cost data via Azure CLI."
                    );
                    return Ok(());
                }
            };

            let entries: Vec<serde_json::Value> =
                serde_json::from_str(&json).context("Failed to parse cost data JSON")?;

            // Aggregate costs by date
            let mut date_costs: std::collections::BTreeMap<String, f64> =
                std::collections::BTreeMap::new();
            for entry in &entries {
                let date = entry
                    .get("usageStart")
                    .and_then(|v| v.as_str())
                    .and_then(|s| s.get(..10))
                    .unwrap_or("unknown");
                let cost = entry
                    .get("pretaxCost")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                *date_costs.entry(date.to_string()).or_insert(0.0) += cost;
            }

            println!(
                "{}",
                crate::handlers::format_cost_history_header(&resource_group, days)
            );

            if date_costs.is_empty() {
                println!("No cost data available for the last {} days.", days);
            } else {
                let mut table = crate::table_render::SimpleTable::new(
                    &["Date", "Cost (USD)"],
                    &[12, 14],
                );
                let mut total = 0.0;
                for (date, cost) in &date_costs {
                    table.add_row(vec![date.clone(), format!("${:.2}", cost)]);
                    total += cost;
                }
                println!("{table}");
                println!(
                    "Total: ${:.2} ({} days with data)",
                    total,
                    date_costs.len()
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
