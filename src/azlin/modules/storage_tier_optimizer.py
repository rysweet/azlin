"""Storage Tier Optimizer Module.

Analyze usage patterns and recommend optimal storage tiers (Premium vs Standard)
for cost vs performance optimization. Analysis-only - does not migrate tiers.

Philosophy:
- Self-contained module following brick architecture
- Standard library + subprocess for Azure CLI
- Zero-BS implementation - every function works
- Evidence-based recommendations

Public API:
    StorageTierOptimizer: Main tier optimization class
    TierAnalysis: Storage tier usage analysis
    TierRecommendation: Tier optimization recommendation
"""

from dataclasses import dataclass

# Import existing modules
try:
    from azlin.modules.storage_manager import StorageManager
except ImportError:
    StorageManager = None


__all__ = [
    "StorageTierOptimizer",
    "TierAnalysis",
    "TierRecommendation",
]


# Cost constants (per GB per month)
PREMIUM_COST = 0.1536
STANDARD_COST = 0.04


@dataclass
class TierAnalysis:
    """Storage tier usage analysis.

    Attributes:
        storage_name: Storage account name
        current_tier: Current tier (Premium/Standard)
        size_gb: Storage size in GB
        usage_pattern: "high", "medium", or "low"
        connected_vms: Number of connected VMs
        avg_operations_per_day: Estimated operations per day
        current_cost_per_month: Current monthly cost
    """

    storage_name: str
    current_tier: str
    size_gb: int
    usage_pattern: str
    connected_vms: int
    avg_operations_per_day: int
    current_cost_per_month: float


@dataclass
class TierRecommendation:
    """Tier optimization recommendation.

    Attributes:
        storage_name: Storage account name
        current_tier: Current tier
        recommended_tier: Recommended tier
        reason: Explanation for recommendation
        current_cost_per_month: Current monthly cost
        potential_cost_per_month: Potential monthly cost after migration
        annual_savings: Annual savings estimate
        performance_impact: "none", "minor", or "significant"
        confidence: "high", "medium", or "low"
    """

    storage_name: str
    current_tier: str
    recommended_tier: str
    reason: str
    current_cost_per_month: float
    potential_cost_per_month: float
    annual_savings: float
    performance_impact: str
    confidence: str


class StorageTierOptimizer:
    """Analyze and optimize storage tier selection.

    Provides analysis-only functionality - recommends optimal tiers but does not migrate.
    Azure limitation: Cannot change tier in-place, must migrate to new storage account.

    Usage:
        # Analyze storage
        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="myteam-shared",
            resource_group="test-rg"
        )

        # Get recommendation
        rec = StorageTierOptimizer.recommend_tier(
            storage_name="myteam-shared",
            resource_group="test-rg"
        )
    """

    @classmethod
    def analyze_storage(
        cls, storage_name: str, resource_group: str, days: int = 30
    ) -> TierAnalysis:
        """Analyze storage usage patterns.

        Args:
            storage_name: Storage account name
            resource_group: Resource group
            days: Analysis period in days (default: 30)

        Returns:
            TierAnalysis: Usage analysis
        """
        if not StorageManager:
            raise RuntimeError("StorageManager not available")

        # Get storage status
        status = StorageManager.get_storage_status(name=storage_name, resource_group=resource_group)

        # Determine usage pattern based on connected VMs
        connected_vms_count = len(getattr(status, "connected_vms", []))

        if connected_vms_count == 0:
            usage_pattern = "low"
        elif connected_vms_count >= 3:
            usage_pattern = "high"
        else:
            usage_pattern = "medium"

        # Estimate operations (simplified heuristic)
        avg_operations = connected_vms_count * 1000  # 1000 ops/day per VM

        # Calculate current cost
        tier = getattr(status, "tier", "Standard")
        size_gb = getattr(status, "size_gb", 0)

        if tier == "Premium":
            current_cost = size_gb * PREMIUM_COST
        else:
            current_cost = size_gb * STANDARD_COST

        return TierAnalysis(
            storage_name=storage_name,
            current_tier=tier,
            size_gb=size_gb,
            usage_pattern=usage_pattern,
            connected_vms=connected_vms_count,
            avg_operations_per_day=avg_operations,
            current_cost_per_month=current_cost,
        )

    @classmethod
    def recommend_tier(cls, storage_name: str, resource_group: str) -> TierRecommendation:
        """Recommend optimal tier based on usage.

        Args:
            storage_name: Storage account name
            resource_group: Resource group

        Returns:
            TierRecommendation: Tier recommendation
        """
        # Analyze current usage
        analysis = cls.analyze_storage(storage_name=storage_name, resource_group=resource_group)

        # Determine recommendation
        current_tier = analysis.current_tier
        size_gb = analysis.size_gb

        # Calculate costs for both tiers
        premium_cost = size_gb * PREMIUM_COST
        standard_cost = size_gb * STANDARD_COST

        # Recommendation logic
        if current_tier == "Premium" and analysis.usage_pattern == "low":
            # Recommend downgrade to Standard
            recommended_tier = "Standard"
            potential_cost = standard_cost
            savings = premium_cost - standard_cost
            reason = f"Storage is Premium tier but has only {analysis.connected_vms} connected VM(s) with low utilization. Standard tier would provide adequate performance at {((savings / premium_cost) * 100):.0f}% cost reduction."
            performance_impact = "minor"
            confidence = "high"

        elif current_tier == "Standard" and analysis.usage_pattern == "high":
            # Recommend upgrade to Premium
            recommended_tier = "Premium"
            potential_cost = premium_cost
            savings = 0  # No cost savings, this is performance upgrade
            reason = f"Storage has {analysis.connected_vms} connected VMs with high utilization. Premium tier would improve performance."
            performance_impact = "significant"
            confidence = "medium"

        else:
            # Keep current tier
            recommended_tier = current_tier
            potential_cost = analysis.current_cost_per_month
            savings = 0
            reason = f"Current {current_tier} tier is appropriate for {analysis.usage_pattern} usage pattern."
            performance_impact = "none"
            confidence = "high"

        annual_savings = savings * 12

        return TierRecommendation(
            storage_name=storage_name,
            current_tier=current_tier,
            recommended_tier=recommended_tier,
            reason=reason,
            current_cost_per_month=analysis.current_cost_per_month,
            potential_cost_per_month=potential_cost,
            annual_savings=annual_savings,
            performance_impact=performance_impact,
            confidence=confidence,
        )

    @classmethod
    def audit_all_storage(cls, resource_group: str) -> list[TierRecommendation]:
        """Audit all storage accounts in resource group.

        Args:
            resource_group: Resource group to audit

        Returns:
            List of tier recommendations for all storage accounts
        """
        if not StorageManager:
            return []

        try:
            storage_list = StorageManager.list_storage(resource_group=resource_group)
            recommendations = []

            for storage in storage_list:
                try:
                    rec = cls.recommend_tier(
                        storage_name=storage.name, resource_group=resource_group
                    )
                    recommendations.append(rec)
                except Exception:
                    continue

            return recommendations

        except Exception:
            return []
