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
pub async fn get_cost_summary(auth: &AzureAuth, resource_group: &str) -> Result<CostSummary> {
    debug!(
        subscription = auth.subscription_id(),
        resource_group, "Fetching cost summary"
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
    use azlin_core::models::VmCost;
    use chrono::Utc;

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
    fn test_cost_summary_multiple_currencies() {
        let vm1 = VmCost {
            vm_name: "vm-us".into(),
            cost: 50.0,
            currency: "USD".into(),
        };
        let vm2 = VmCost {
            vm_name: "vm-eu".into(),
            cost: 45.0,
            currency: "EUR".into(),
        };
        // VmCost can hold different currencies per VM
        assert_eq!(vm1.currency, "USD");
        assert_eq!(vm2.currency, "EUR");
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

    #[test]
    fn test_vm_cost_large_value() {
        let vm = VmCost {
            vm_name: "expensive-vm".into(),
            cost: 999_999.99,
            currency: "USD".into(),
        };
        assert!(vm.cost > 999_000.0);
    }
}
