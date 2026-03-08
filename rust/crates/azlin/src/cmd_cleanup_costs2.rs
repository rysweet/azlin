#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use comfy_table::{presets::UTF8_FULL_CONDENSED, Attribute, Cell, Table};

pub(crate) fn dispatch_costs_extended(action: azlin_cli::CostsAction) -> Result<()> {
    match action {
        azlin_cli::CostsAction::Recommend {
            resource_group,
            priority,
        } => {
            let cmd_args =
                crate::handlers::build_advisor_args(&resource_group, priority.as_deref());
            let output = std::process::Command::new("az").args(&cmd_args).output()?;

            if output.status.success() {
                let json_str = String::from_utf8_lossy(&output.stdout);
                match serde_json::from_str::<serde_json::Value>(&json_str) {
                    Ok(data) => {
                        if let Some(recs) = data.as_array() {
                            if recs.is_empty() {
                                let pri = priority.unwrap_or_else(|| "all".to_string());
                                println!(
                                    "{}",
                                    crate::handlers::format_no_recommendations(
                                        &resource_group,
                                        &pri
                                    )
                                );
                            } else {
                                let mut table = Table::new();
                                table.load_preset(UTF8_FULL_CONDENSED).set_header(vec![
                                    Cell::new("Category").add_attribute(Attribute::Bold),
                                    Cell::new("Impact").add_attribute(Attribute::Bold),
                                    Cell::new("Problem").add_attribute(Attribute::Bold),
                                ]);
                                for (category, impact, problem) in
                                    crate::handlers::parse_recommendation_rows(&data)
                                {
                                    table.add_row(vec![
                                        Cell::new(&category),
                                        Cell::new(&impact),
                                        Cell::new(&problem),
                                    ]);
                                }
                                println!(
                                    "{}",
                                    crate::handlers::format_recommendations_header(&resource_group)
                                );
                                println!("{table}");
                            }
                        }
                    }
                    Err(e) => eprintln!("Failed to parse advisor data: {}", e),
                }
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                anyhow::bail!(
                    "Failed to list recommendations: {}",
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
        }
        azlin_cli::CostsAction::Actions {
            action,
            resource_group,
            dry_run,
            ..
        } => {
            let output = std::process::Command::new("az")
                .args([
                    "advisor",
                    "recommendation",
                    "list",
                    "--resource-group",
                    &resource_group,
                    "--query",
                    "[?category=='Cost']",
                    "-o",
                    "json",
                ])
                .output()?;

            if output.status.success() {
                let json_str = String::from_utf8_lossy(&output.stdout);
                match serde_json::from_str::<serde_json::Value>(&json_str) {
                    Ok(data) => {
                        if let Some(recs) = data.as_array() {
                            if recs.is_empty() {
                                println!(
                                    "{}",
                                    crate::handlers::format_no_cost_actions(&resource_group)
                                );
                            } else {
                                let mut table = Table::new();
                                table.load_preset(UTF8_FULL_CONDENSED).set_header(vec![
                                    Cell::new("Resource").add_attribute(Attribute::Bold),
                                    Cell::new("Impact").add_attribute(Attribute::Bold),
                                    Cell::new("Recommendation").add_attribute(Attribute::Bold),
                                ]);
                                for (resource, impact, problem) in
                                    crate::handlers::parse_cost_action_rows(&data)
                                {
                                    table.add_row(vec![
                                        Cell::new(&resource),
                                        Cell::new(&impact),
                                        Cell::new(&problem),
                                    ]);
                                }
                                println!(
                                    "{}",
                                    crate::handlers::format_cost_actions_header(
                                        &action,
                                        &resource_group,
                                        dry_run
                                    )
                                );
                                println!("{table}");
                                // Apply actions if not dry-run
                                if !dry_run && action == "apply" {
                                    println!("\nApplying cost recommendations...");
                                    for rec in recs {
                                        let resource_id = rec
                                            .get("resourceMetadata")
                                            .and_then(|rm| rm.get("resourceId"))
                                            .and_then(|v| v.as_str())
                                            .unwrap_or("");
                                        let impact = rec
                                            .get("impact")
                                            .and_then(|v| v.as_str())
                                            .unwrap_or("");
                                        if !resource_id.is_empty()
                                            && resource_id.contains("virtualMachines")
                                        {
                                            println!(
                                                "  Deallocating idle VM: {} (impact: {})",
                                                resource_id, impact
                                            );
                                            match std::process::Command::new("az")
                                                .args(["vm", "deallocate", "--ids", resource_id])
                                                .output()
                                            {
                                                Ok(output) if output.status.success() => {
                                                    println!("  ✓ Deallocated successfully");
                                                }
                                                Ok(output) => {
                                                    eprintln!(
                                                        "  ✗ Failed to deallocate: {}",
                                                        String::from_utf8_lossy(&output.stderr)
                                                            .trim()
                                                    );
                                                }
                                                Err(e) => {
                                                    eprintln!("  ✗ Failed to run az: {}", e);
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => eprintln!("Failed to parse advisor data: {}", e),
                }
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                anyhow::bail!(
                    "Failed to list cost actions: {}",
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
