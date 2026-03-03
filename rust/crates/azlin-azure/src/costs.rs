//! Cost management — query Azure Cost Management for spending data.

use anyhow::Result;
use chrono::Utc;
use tracing::debug;

use azlin_core::models::CostSummary;

use crate::AzureAuth;

/// Fetch a cost summary for the given resource group.
///
/// Uses the Azure Cost Management API via `azure_mgmt_costmanagement`.
/// Currently returns stub data while the full SDK integration is completed.
pub async fn get_cost_summary(
    auth: &AzureAuth,
    resource_group: &str,
) -> Result<CostSummary> {
    debug!(
        subscription = auth.subscription_id(),
        resource_group,
        "Fetching cost summary"
    );

    // TODO: Wire up azure_mgmt_costmanagement SDK client once auth adapter
    // issues are resolved. For now, return a stub summary.
    let now = Utc::now();
    let period_start = now - chrono::Duration::days(30);

    Ok(CostSummary {
        total_cost: 0.0,
        currency: "USD".to_string(),
        period_start,
        period_end: now,
        by_vm: Vec::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use azlin_core::models::VmCost;

    #[test]
    fn test_stub_cost_summary_structure() {
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
}
