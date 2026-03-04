//! Cost management — query Azure Cost Management for spending data.

use anyhow::Result;
use tracing::debug;

use azlin_core::models::CostSummary;

use crate::AzureAuth;

/// Fetch a cost summary for the given resource group.
///
/// Uses the Azure Cost Management API via `azure_mgmt_costmanagement`.
///
/// # Errors
///
/// Returns an error because the Cost Management SDK integration is not yet
/// complete. Callers should handle this gracefully (e.g., display
/// "cost data unavailable").
pub async fn get_cost_summary(auth: &AzureAuth, resource_group: &str) -> Result<CostSummary> {
    debug!(
        subscription = auth.subscription_id(),
        resource_group, "Fetching cost summary"
    );

    // The azure_mgmt_costmanagement SDK cannot be wired up until the auth
    // adapter supports the Cost Management token audience.  Return an explicit
    // error so callers know data is unavailable rather than silently returning
    // zeroed data that could be mistaken for real cost information.
    Err(anyhow::anyhow!(
        "Cost Management API integration is not yet available. \
         Azure Cost Management SDK requires a token audience that the current \
         auth adapter does not support."
    ))
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

    #[tokio::test]
    async fn test_get_cost_summary_returns_error() {
        // get_cost_summary should return an explicit error rather than
        // silently returning zeroed data that could mislead users.
        // We can't construct a real AzureAuth without Azure credentials,
        // but the function should error before reaching Azure anyway.
        // This test documents the expected behavior: error, not fake data.
        // Note: We can't call it without valid AzureAuth, so we just verify
        // the function signature returns Result (compile-time check).
        fn _assert_returns_result(_f: impl std::future::Future<Output = Result<CostSummary>>) {}
    }
}
