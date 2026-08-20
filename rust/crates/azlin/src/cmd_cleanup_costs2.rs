#[allow(unused_imports)]
use super::*;
use anyhow::Result;

/// Fail unless the resource group exists.
///
/// Azure Advisor answers `[]` for a resource group that does not exist, so
/// `azlin costs recommend --rg typo` reported "no cost recommendations found
/// for 'typo'" — a confident statement about infrastructure it had never
/// reached. An unanswerable check (not logged in, no permission) is an error
/// too: assuming "exists" or "does not exist" from a failed lookup is the same
/// mistake one step further out.
fn require_resource_group(resource_group: &str) -> Result<()> {
    let timeout = azlin_core::AzlinConfig::load()
        .map(|c| c.az_cli_timeout)
        .unwrap_or(120);
    if !azlin_azure::resource_group_exists(resource_group, timeout)? {
        anyhow::bail!(
            "Resource group '{}' does not exist. \
             Check the name, or `az account set --subscription <id>` if it \
             lives in another subscription.",
            resource_group
        );
    }
    Ok(())
}

pub(crate) fn dispatch_costs_extended(action: azlin_cli::CostsAction) -> Result<()> {
    match action {
        azlin_cli::CostsAction::Recommend {
            resource_group,
            priority,
        } => {
            require_resource_group(&resource_group)?;
            let cmd_args =
                crate::handlers::build_advisor_args(&resource_group, priority.as_deref())
                    .map_err(|e| anyhow::anyhow!("{}", e))?;
            let output = std::process::Command::new("az").args(&cmd_args).output()?;

            if output.status.success() {
                let json_str = String::from_utf8_lossy(&output.stdout);
                match serde_json::from_str::<serde_json::Value>(&json_str) {
                    Ok(data) => {
                        // A non-array answer used to fall out of the `if let`
                        // and exit 0 having printed nothing — indistinguishable
                        // from a resource group with no recommendations.
                        let recs = data.as_array().ok_or_else(|| {
                            anyhow::anyhow!(
                                "Azure Advisor returned {} rather than a list of \
                                 recommendations for '{}'",
                                if data.is_object() {
                                    "an object"
                                } else {
                                    "a scalar"
                                },
                                resource_group
                            )
                        })?;
                        {
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
                                let mut table = crate::table_render::SimpleTable::new(
                                    &["Category", "Impact", "Problem"],
                                    &[14, 10, 40],
                                );
                                for (category, impact, problem) in
                                    crate::handlers::parse_recommendation_rows(&data)
                                {
                                    table.add_row(vec![category, impact, problem]);
                                }
                                println!(
                                    "{}",
                                    crate::handlers::format_recommendations_header(&resource_group)
                                );
                                println!("{table}");
                            }
                        }
                    }
                    // Not `eprintln!` and carry on: a parse failure that
                    // exits 0 reports "nothing to do" for data that was
                    // never read.
                    Err(e) => anyhow::bail!(
                        "Could not parse Azure Advisor data for '{}': {}",
                        resource_group,
                        e
                    ),
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
            priority,
        } => {
            require_resource_group(&resource_group)?;
            // `--priority` was accepted and discarded (#1089), so every
            // recommendation was listed *and applied* whatever the user asked
            // for — `--priority high apply` deallocated the Low-impact VMs the
            // filter existed to exclude. Filtered in the fetch, so the table
            // and the apply loop below cannot disagree about what is in scope.
            let cmd_args =
                crate::handlers::build_advisor_args(&resource_group, priority.as_deref())
                    .map_err(|e| anyhow::anyhow!("{}", e))?;
            let output = std::process::Command::new("az").args(&cmd_args).output()?;

            if output.status.success() {
                let json_str = String::from_utf8_lossy(&output.stdout);
                match serde_json::from_str::<serde_json::Value>(&json_str) {
                    Ok(data) => {
                        // Same as above: a non-array answer printed nothing and
                        // exited 0.
                        let recs = data.as_array().ok_or_else(|| {
                            anyhow::anyhow!(
                                "Azure Advisor returned {} rather than a list of \
                                 recommendations for '{}'",
                                if data.is_object() {
                                    "an object"
                                } else {
                                    "a scalar"
                                },
                                resource_group
                            )
                        })?;
                        {
                            if recs.is_empty() {
                                // "No High recommendations" and "no cost
                                // recommendations at all" send the user to
                                // different places, so they say different
                                // things.
                                match priority.as_deref() {
                                    Some(pri) => println!(
                                        "{}",
                                        crate::handlers::no_actions_at_priority(
                                            &resource_group,
                                            pri
                                        )
                                    ),
                                    None => println!(
                                        "{}",
                                        crate::handlers::format_no_cost_actions(&resource_group)
                                    ),
                                }
                            } else {
                                let mut table = crate::table_render::SimpleTable::new(
                                    &["Resource", "Impact", "Recommendation"],
                                    &[25, 10, 40],
                                );
                                for (resource, impact, problem) in
                                    crate::handlers::parse_cost_action_rows(&data)
                                {
                                    table.add_row(vec![resource, impact, problem]);
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
                    // Not `eprintln!` and carry on: a parse failure that
                    // exits 0 reports "nothing to do" for data that was
                    // never read.
                    Err(e) => anyhow::bail!(
                        "Could not parse Azure Advisor data for '{}': {}",
                        resource_group,
                        e
                    ),
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
