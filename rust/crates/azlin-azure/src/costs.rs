//! Cost management — query Azure Cost Management for spending data via az CLI.

use anyhow::{Context, Result};
use tracing::debug;

use azlin_core::models::CostSummary;

use crate::AzureAuth;

/// Fetch a cost summary for the given resource group using `az consumption usage list`.
///
/// Uses the az CLI to query Azure Cost Management, matching the Python
/// reference implementation. `timeout_secs` controls the subprocess timeout
/// (pass the configured `az_cli_timeout` from `AzlinConfig`).
pub fn get_cost_summary(
    auth: &AzureAuth,
    resource_group: &str,
    timeout_secs: u64,
) -> Result<CostSummary> {
    debug!(
        subscription = auth.subscription_id(),
        resource_group, "Fetching cost summary via az CLI"
    );

    let end_date = chrono::Utc::now();
    let start_date = end_date - chrono::Duration::days(30);
    let start_str = start_date.format("%Y-%m-%d").to_string();
    let end_str = end_date.format("%Y-%m-%d").to_string();

    // Use the shared az_cli_with_timeout to prevent pipe deadlocks and hangs
    let json = match crate::vm::az_cli_with_timeout(
        &[
            "consumption",
            "usage",
            "list",
            "--start-date",
            &start_str,
            "--end-date",
            &end_str,
        ],
        timeout_secs,
    ) {
        Ok(json) => json,
        Err(e) => {
            return Err(anyhow::anyhow!("Cost data unavailable: {}", e));
        }
    };

    let entries: Vec<serde_json::Value> =
        serde_json::from_str(&json).context("Failed to parse cost data JSON")?;

    // Aggregate costs by VM name
    let mut total_cost = 0.0;
    let mut currency = "USD".to_string();
    let mut by_vm: std::collections::HashMap<String, f64> = std::collections::HashMap::new();

    for entry in &entries {
        let cost = entry["pretaxCost"].as_f64().unwrap_or(0.0);
        if let Some(c) = entry["currency"].as_str() {
            currency = c.to_string();
        }

        // Filter by resource group if the entry has one
        let entry_rg = entry["instanceId"].as_str().and_then(|id| {
            let parts: Vec<&str> = id.split('/').collect();
            if parts.len() >= 5 {
                Some(parts[4])
            } else {
                None
            }
        });

        match entry_rg {
            Some(rg) if rg.eq_ignore_ascii_case(resource_group) => {
                // Matches the target resource group — include it.
            }
            Some(_) => {
                // Different resource group — skip.
                continue;
            }
            None => {
                // No resource group on entry — skip when filtering by RG.
                continue;
            }
        }

        total_cost += cost;

        // Try to extract VM name from instance ID
        if let Some(instance_name) = entry["instanceName"].as_str() {
            *by_vm.entry(instance_name.to_string()).or_insert(0.0) += cost;
        }
    }

    let vm_costs: Vec<azlin_core::models::VmCost> = by_vm
        .into_iter()
        .map(|(vm_name, cost)| azlin_core::models::VmCost {
            vm_name,
            cost,
            currency: currency.clone(),
        })
        .collect();

    Ok(CostSummary {
        total_cost,
        currency,
        period_start: start_date,
        period_end: end_date,
        by_vm: vm_costs,
    })
}

#[cfg(test)]
mod tests {
    use azlin_core::models::{CostSummary, VmCost};
    use chrono::Utc;

    #[test]
    fn test_cost_summary_structure() {
        let summary = CostSummary {
            total_cost: 123.45,
            currency: "USD".to_string(),
            period_start: Utc::now(),
            period_end: Utc::now(),
            by_vm: vec![VmCost {
                vm_name: "test-vm".to_string(),
                cost: 123.45,
                currency: "USD".to_string(),
            }],
        };
        assert_eq!(summary.total_cost, 123.45);
        assert_eq!(summary.by_vm.len(), 1);
        assert_eq!(summary.by_vm[0].vm_name, "test-vm");
    }

    #[test]
    fn test_cost_summary_period_ordering() {
        let start = Utc::now() - chrono::Duration::days(30);
        let end = Utc::now();
        let summary = CostSummary {
            total_cost: 0.0,
            currency: "USD".to_string(),
            period_start: start,
            period_end: end,
            by_vm: vec![],
        };
        assert!(summary.period_start < summary.period_end);
    }

    #[test]
    fn test_cost_summary_zero_cost() {
        let summary = CostSummary {
            total_cost: 0.0,
            currency: "USD".to_string(),
            period_start: Utc::now(),
            period_end: Utc::now(),
            by_vm: vec![],
        };
        assert_eq!(summary.total_cost, 0.0);
        assert!(summary.by_vm.is_empty());
    }
}
