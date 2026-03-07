#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Table};

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
            let (start_date, end_date) = crate::handlers::build_cost_history_dates(days);

            // Get subscription ID first
            let sub_output = std::process::Command::new("az")
                .args(["account", "show", "--query", "id", "-o", "tsv"])
                .output()?;
            let sub_id = String::from_utf8_lossy(&sub_output.stdout)
                .trim()
                .to_string();
            if sub_id.is_empty() {
                anyhow::bail!("Could not determine subscription ID. Run 'az login' first.");
            }

            let scope = crate::handlers::build_cost_management_scope(&sub_id, &resource_group);
            let output = std::process::Command::new("az")
                .args([
                    "costmanagement",
                    "query",
                    "--type",
                    "ActualCost",
                    "--scope",
                    &scope,
                    "--timeframe",
                    "Custom",
                    "--time-period",
                    &format!("start={}&end={}", start_date, end_date),
                    "-o",
                    "json",
                ])
                .output()?;

            if output.status.success() {
                let json_str = String::from_utf8_lossy(&output.stdout);
                match serde_json::from_str::<serde_json::Value>(&json_str) {
                    Ok(data) => {
                        let mut table = Table::new();
                        table
                            .load_preset(UTF8_FULL)
                            .apply_modifier(UTF8_ROUND_CORNERS)
                            .set_header(vec![
                                Cell::new("Date").add_attribute(Attribute::Bold),
                                Cell::new("Cost (USD)").add_attribute(Attribute::Bold),
                            ]);

                        for (date, cost) in crate::handlers::parse_cost_history_rows(&data) {
                            table.add_row(vec![Cell::new(&date), Cell::new(&cost)]);
                        }
                        println!(
                            "{}",
                            crate::handlers::format_cost_history_header(&resource_group, days)
                        );
                        println!("{table}");
                    }
                    Err(e) => {
                        eprintln!("Failed to parse cost data: {}", e);
                        println!("{}", json_str);
                    }
                }
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                anyhow::bail!(
                    "Failed to query cost history: {}",
                    azlin_core::sanitizer::sanitize(stderr.trim())
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
