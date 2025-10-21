"""Cost estimation for Azure resources.

Phase 3 Implementation (not yet implemented).

Estimates Azure costs based on:
- Resource types and sizes
- Azure pricing data
- Region-specific pricing
- Usage patterns
"""

from azlin.agentic.types import CostEstimate, Intent


class CostEstimator:
    """Estimates Azure resource costs.

    Phase 3 will implement:
    - Azure pricing API integration
    - Resource type cost mapping
    - Region-specific pricing
    - Usage-based estimates

    Example (when implemented):
        >>> estimator = CostEstimator()
        >>> intent = Intent(intent="provision_vm", parameters={"vm_size": "Standard_B2s"}, ...)
        >>> cost = estimator.estimate(intent)
        >>> print(f"${cost.total_monthly}")
    """

    def estimate(self, intent: Intent, region: str = "westus2") -> CostEstimate:
        """Estimate cost for intent execution.

        TODO Phase 3:
        - Parse resource types from intent
        - Query Azure pricing API
        - Calculate monthly/hourly costs
        - Build cost breakdown by resource

        Args:
            intent: Parsed intent
            region: Azure region (affects pricing)

        Returns:
            CostEstimate with breakdown

        Raises:
            NotImplementedError: Phase 3 not yet implemented
        """
        raise NotImplementedError("Phase 3 - cost estimation not yet implemented")

    def get_vm_cost(
        self,
        vm_size: str,
        region: str = "westus2",
        storage_gb: int = 128,
    ) -> CostEstimate:
        """Get VM cost estimate.

        TODO Phase 3:
        - VM pricing by size
        - Storage costs
        - Network egress costs

        Args:
            vm_size: VM size (e.g., Standard_B2s)
            region: Azure region
            storage_gb: Storage size in GB

        Returns:
            CostEstimate

        Raises:
            NotImplementedError: Phase 3 not yet implemented
        """
        raise NotImplementedError("Phase 3 - VM cost estimation not yet implemented")

    def get_aks_cost(
        self,
        node_count: int,
        node_size: str,
        region: str = "westus2",
    ) -> CostEstimate:
        """Get AKS cluster cost estimate.

        TODO Phase 3:
        - Node pool costs
        - Control plane costs (free tier vs standard)
        - Load balancer costs

        Args:
            node_count: Number of nodes
            node_size: Node VM size
            region: Azure region

        Returns:
            CostEstimate

        Raises:
            NotImplementedError: Phase 3 not yet implemented
        """
        raise NotImplementedError("Phase 3 - AKS cost estimation not yet implemented")
