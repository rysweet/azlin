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

    let (total_cost, currency, vm_costs) = aggregate_costs(&entries, resource_group);

    Ok(CostSummary {
        total_cost,
        currency,
        period_start: start_date,
        period_end: end_date,
        by_vm: vm_costs,
    })
}

/// Extract the resource group name from an Azure instance ID.
///
/// Instance IDs have the form `/subscriptions/{sub}/resourceGroups/{rg}/...`.
/// Returns `None` if the path has fewer than 5 segments.
fn extract_rg_from_instance_id(instance_id: &str) -> Option<&str> {
    let parts: Vec<&str> = instance_id.split('/').collect();
    if parts.len() >= 5 {
        Some(parts[4])
    } else {
        None
    }
}

/// Aggregate cost entries by resource group, returning (total_cost, currency, per-vm costs).
///
/// This is the pure logic extracted from `get_cost_summary` so it can be tested
/// without calling the az CLI.
fn aggregate_costs(
    entries: &[serde_json::Value],
    resource_group: &str,
) -> (f64, String, Vec<azlin_core::models::VmCost>) {
    let mut total_cost = 0.0;
    let mut currency = "USD".to_string();
    let mut by_vm: std::collections::HashMap<String, f64> = std::collections::HashMap::new();

    for entry in entries {
        let cost = entry["pretaxCost"].as_f64().unwrap_or(0.0);
        if let Some(c) = entry["currency"].as_str() {
            currency = c.to_string();
        }

        let entry_rg = entry["instanceId"]
            .as_str()
            .and_then(extract_rg_from_instance_id);

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

    (total_cost, currency, vm_costs)
}

#[cfg(test)]
mod tests {
    use super::*;
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

    // ── extract_rg_from_instance_id tests ────────────────────────────

    #[test]
    fn test_extract_rg_from_instance_id_valid() {
        let id = "/subscriptions/sub-1/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/vm1";
        assert_eq!(extract_rg_from_instance_id(id), Some("my-rg"));
    }

    #[test]
    fn test_extract_rg_from_instance_id_short_path() {
        assert_eq!(extract_rg_from_instance_id("/a/b/c"), None);
        assert_eq!(extract_rg_from_instance_id(""), None);
    }

    #[test]
    fn test_extract_rg_from_instance_id_exact_five_segments() {
        // "/a/b/c/d/THE_RG" splits to ["", "a", "b", "c", "d", "THE_RG"] — len 6, parts[4] = "d"
        // Wait — 5 slashes = 6 parts. "/subscriptions/sub/resourceGroups/rg/providers" = 6 parts.
        let id = "/subscriptions/sub/resourceGroups/rg/providers";
        assert_eq!(extract_rg_from_instance_id(id), Some("rg"));
    }

    // ── aggregate_costs tests ────────────────────────────────────────

    #[test]
    fn test_aggregate_costs_empty_entries() {
        let entries: Vec<serde_json::Value> = vec![];
        let (total, currency, by_vm) = aggregate_costs(&entries, "my-rg");
        assert_eq!(total, 0.0);
        assert_eq!(currency, "USD"); // default
        assert!(by_vm.is_empty());
    }

    #[test]
    fn test_aggregate_costs_matching_rg() {
        let entries = vec![
            serde_json::json!({
                "pretaxCost": 10.50,
                "currency": "USD",
                "instanceId": "/subscriptions/sub/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/vm1",
                "instanceName": "vm1"
            }),
            serde_json::json!({
                "pretaxCost": 5.25,
                "currency": "USD",
                "instanceId": "/subscriptions/sub/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/vm2",
                "instanceName": "vm2"
            }),
        ];

        let (total, currency, by_vm) = aggregate_costs(&entries, "my-rg");
        assert!((total - 15.75).abs() < 0.001);
        assert_eq!(currency, "USD");
        assert_eq!(by_vm.len(), 2);
    }

    #[test]
    fn test_aggregate_costs_non_matching_rg_filtered() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 10.0,
            "currency": "USD",
            "instanceId": "/subscriptions/sub/resourceGroups/other-rg/providers/Microsoft.Compute/virtualMachines/vm1",
            "instanceName": "vm1"
        })];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "my-rg");
        assert_eq!(total, 0.0);
        assert!(by_vm.is_empty());
    }

    #[test]
    fn test_aggregate_costs_rg_case_insensitive() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 7.0,
            "currency": "EUR",
            "instanceId": "/subscriptions/sub/resourceGroups/My-RG/providers/Microsoft.Compute/virtualMachines/vm1",
            "instanceName": "vm1"
        })];

        let (total, currency, by_vm) = aggregate_costs(&entries, "my-rg");
        assert!((total - 7.0).abs() < 0.001);
        assert_eq!(currency, "EUR");
        assert_eq!(by_vm.len(), 1);
        assert_eq!(by_vm[0].vm_name, "vm1");
    }

    #[test]
    fn test_aggregate_costs_no_instance_id_skipped() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 99.0,
            "currency": "GBP",
        })];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "my-rg");
        assert_eq!(total, 0.0);
        assert!(by_vm.is_empty());
    }

    #[test]
    fn test_aggregate_costs_short_instance_id_skipped() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 5.0,
            "currency": "USD",
            "instanceId": "/short/path"
        })];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "my-rg");
        assert_eq!(total, 0.0);
        assert!(by_vm.is_empty());
    }

    #[test]
    fn test_aggregate_costs_currency_extraction() {
        let entries = vec![
            serde_json::json!({
                "pretaxCost": 1.0,
                "currency": "EUR",
                "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
                "instanceName": "vm1"
            }),
            serde_json::json!({
                "pretaxCost": 2.0,
                "currency": "GBP",
                "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
                "instanceName": "vm2"
            }),
        ];

        let (_total, currency, _by_vm) = aggregate_costs(&entries, "rg");
        // Last currency wins
        assert_eq!(currency, "GBP");
    }

    #[test]
    fn test_aggregate_costs_zero_cost_entries_included() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 0.0,
            "currency": "USD",
            "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
            "instanceName": "vm-free"
        })];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "rg");
        assert_eq!(total, 0.0);
        assert_eq!(by_vm.len(), 1);
        assert_eq!(by_vm[0].vm_name, "vm-free");
        assert_eq!(by_vm[0].cost, 0.0);
    }

    #[test]
    fn test_aggregate_costs_missing_pretax_cost_defaults_zero() {
        let entries = vec![serde_json::json!({
            "currency": "USD",
            "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
            "instanceName": "vm1"
        })];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "rg");
        assert_eq!(total, 0.0);
        assert_eq!(by_vm.len(), 1);
        assert_eq!(by_vm[0].cost, 0.0);
    }

    #[test]
    fn test_aggregate_costs_no_instance_name_not_in_by_vm() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 50.0,
            "currency": "USD",
            "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p"
        })];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "rg");
        assert!((total - 50.0).abs() < 0.001);
        // Cost is counted in total but not attributed to any VM
        assert!(by_vm.is_empty());
    }

    #[test]
    fn test_aggregate_costs_same_vm_costs_aggregated() {
        let entries = vec![
            serde_json::json!({
                "pretaxCost": 10.0,
                "currency": "USD",
                "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
                "instanceName": "vm1"
            }),
            serde_json::json!({
                "pretaxCost": 20.0,
                "currency": "USD",
                "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
                "instanceName": "vm1"
            }),
        ];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "rg");
        assert!((total - 30.0).abs() < 0.001);
        assert_eq!(by_vm.len(), 1);
        assert!((by_vm[0].cost - 30.0).abs() < 0.001);
    }

    #[test]
    fn test_aggregate_costs_mixed_matching_and_non_matching() {
        let entries = vec![
            serde_json::json!({
                "pretaxCost": 10.0,
                "currency": "USD",
                "instanceId": "/subscriptions/s/resourceGroups/target-rg/providers/p",
                "instanceName": "vm1"
            }),
            serde_json::json!({
                "pretaxCost": 999.0,
                "currency": "USD",
                "instanceId": "/subscriptions/s/resourceGroups/other-rg/providers/p",
                "instanceName": "vm-other"
            }),
            serde_json::json!({
                "pretaxCost": 5.0,
                "currency": "USD",
                "instanceId": "/subscriptions/s/resourceGroups/target-rg/providers/p",
                "instanceName": "vm2"
            }),
        ];

        let (total, _currency, by_vm) = aggregate_costs(&entries, "target-rg");
        assert!((total - 15.0).abs() < 0.001);
        assert_eq!(by_vm.len(), 2);
        // vm-other should not be present
        assert!(by_vm.iter().all(|v| v.vm_name != "vm-other"));
    }

    #[test]
    fn test_aggregate_costs_no_currency_field_defaults_usd() {
        let entries = vec![serde_json::json!({
            "pretaxCost": 1.0,
            "instanceId": "/subscriptions/s/resourceGroups/rg/providers/p",
            "instanceName": "vm1"
        })];

        let (_total, currency, _by_vm) = aggregate_costs(&entries, "rg");
        assert_eq!(currency, "USD");
    }
}
