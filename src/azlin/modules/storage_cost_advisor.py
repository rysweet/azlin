"""Storage Cost Advisor Module.

Provide cost analysis and optimization recommendations across all storage resources.

Philosophy:
- Self-contained module following brick architecture
- Aggregates data from other modules
- Evidence-based recommendations
- Clear prioritization

Public API:
    StorageCostAdvisor: Main cost analysis class
    CostAnalysis: Complete cost analysis
    CostBreakdown: Cost breakdown by resource type
    CostTrends: Cost trend analysis
    CostRecommendation: Cost optimization recommendation
    SavingsEstimate: Total savings potential
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime

# Import existing modules
try:
    from azlin.modules.storage_manager import StorageManager
except ImportError:
    StorageManager = None

try:
    from azlin.modules.orphaned_resource_detector import OrphanedResourceDetector
except ImportError:
    OrphanedResourceDetector = None

try:
    from azlin.modules.storage_tier_optimizer import StorageTierOptimizer
except ImportError:
    StorageTierOptimizer = None


__all__ = [
    "CostAnalysis",
    "CostBreakdown",
    "CostRecommendation",
    "CostTrends",
    "SavingsEstimate",
    "StorageCostAdvisor",
]


# Cost constants
PREMIUM_DISK_COST = 0.1536
STANDARD_DISK_COST = 0.04
SNAPSHOT_COST = 0.05


@dataclass
class CostBreakdown:
    """Cost breakdown by resource type.

    Attributes:
        storage_accounts: Monthly cost of storage accounts
        managed_disks: Monthly cost of managed disks
        snapshots: Monthly cost of snapshots
        orphaned_resources: Monthly cost of orphaned resources
    """

    storage_accounts: float
    managed_disks: float
    snapshots: float
    orphaned_resources: float

    def total(self) -> float:
        """Calculate total cost."""
        return self.storage_accounts + self.managed_disks + self.snapshots + self.orphaned_resources


@dataclass
class CostTrends:
    """Cost trend analysis.

    Attributes:
        daily_average: Average daily cost
        monthly_projection: Projected monthly cost
        month_over_month_change_percent: Month-over-month change percentage
    """

    daily_average: float
    monthly_projection: float
    month_over_month_change_percent: float | None


@dataclass
class CostRecommendation:
    """Cost optimization recommendation.

    Attributes:
        category: "tier", "orphaned", "snapshot-retention", "resize"
        resource_name: Name of resource
        resource_type: Type of resource
        action: Recommended action
        current_cost_per_month: Current monthly cost
        potential_cost_per_month: Potential monthly cost after action
        monthly_savings: Monthly savings
        annual_savings: Annual savings
        effort: "low", "medium", "high"
        risk: "low", "medium", "high"
        priority: 1-5 (1=highest)
    """

    category: str
    resource_name: str
    resource_type: str
    action: str
    current_cost_per_month: float
    potential_cost_per_month: float
    monthly_savings: float
    annual_savings: float
    effort: str
    risk: str
    priority: int

    def __post_init__(self):
        """Validate priority."""
        if not 1 <= self.priority <= 5:
            raise ValueError(f"Priority must be 1-5, got: {self.priority}")


@dataclass
class SavingsEstimate:
    """Total savings potential.

    Attributes:
        total_monthly_savings: Total monthly savings
        total_annual_savings: Total annual savings
        recommendations_count: Number of recommendations
        savings_by_category: Savings broken down by category
        confidence: "high", "medium", "low"
    """

    total_monthly_savings: float
    total_annual_savings: float
    recommendations_count: int
    savings_by_category: dict[str, float]
    confidence: str


@dataclass
class CostAnalysis:
    """Complete storage cost analysis.

    Attributes:
        resource_group: Resource group analyzed
        period_days: Analysis period in days
        total_cost: Total monthly cost
        cost_breakdown: Cost breakdown by resource type
        trends: Cost trends
        analysis_date: When analysis was performed
    """

    resource_group: str
    period_days: int
    total_cost: float
    cost_breakdown: CostBreakdown
    trends: CostTrends
    analysis_date: datetime


class StorageCostAdvisor:
    """Provide cost analysis and optimization recommendations.

    Usage:
        # Analyze costs
        analysis = StorageCostAdvisor.analyze_costs(
            resource_group="test-rg"
        )

        # Get recommendations
        recs = StorageCostAdvisor.get_recommendations(
            resource_group="test-rg"
        )

        # Estimate savings
        savings = StorageCostAdvisor.estimate_savings(
            resource_group="test-rg"
        )
    """

    @classmethod
    def analyze_costs(cls, resource_group: str, period_days: int = 30) -> CostAnalysis:
        """Analyze storage costs across all resource types.

        Args:
            resource_group: Resource group to analyze
            period_days: Analysis period in days (default: 30)

        Returns:
            CostAnalysis: Complete cost analysis
        """
        # Calculate costs for each resource type
        storage_cost = cls._calculate_storage_costs(resource_group)
        disk_cost = cls._calculate_disk_costs(resource_group)
        snapshot_cost = cls._calculate_snapshot_costs(resource_group)
        orphaned_cost = cls._calculate_orphaned_costs(resource_group)

        # Create breakdown
        breakdown = CostBreakdown(
            storage_accounts=storage_cost,
            managed_disks=disk_cost,
            snapshots=snapshot_cost,
            orphaned_resources=orphaned_cost,
        )

        total_cost = breakdown.total()

        # Calculate trends
        daily_average = total_cost / 30
        monthly_projection = total_cost
        trends = CostTrends(
            daily_average=daily_average,
            monthly_projection=monthly_projection,
            month_over_month_change_percent=None,  # Would need historical data
        )

        return CostAnalysis(
            resource_group=resource_group,
            period_days=period_days,
            total_cost=total_cost,
            cost_breakdown=breakdown,
            trends=trends,
            analysis_date=datetime.now(),
        )

    @classmethod
    def get_recommendations(cls, resource_group: str) -> list[CostRecommendation]:
        """Get cost optimization recommendations.

        Args:
            resource_group: Resource group to analyze

        Returns:
            List of cost recommendations, prioritized by impact
        """
        recommendations = []

        # 1. Orphaned resource cleanup recommendations
        if OrphanedResourceDetector:
            try:
                report = OrphanedResourceDetector.scan_all(resource_group=resource_group)

                if report.total_cost_per_month > 10:  # Only if significant savings
                    recommendations.append(
                        CostRecommendation(
                            category="orphaned",
                            resource_name="All orphaned resources",
                            resource_type="multiple",
                            action="Clean up orphaned resources",
                            current_cost_per_month=report.total_cost_per_month,
                            potential_cost_per_month=0.0,
                            monthly_savings=report.total_cost_per_month,
                            annual_savings=report.total_cost_per_month * 12,
                            effort="low",
                            risk="low",
                            priority=1,
                        )
                    )
            except Exception:
                pass

        # 2. Tier optimization recommendations
        if StorageTierOptimizer:
            try:
                tier_recs = StorageTierOptimizer.audit_all_storage(resource_group=resource_group)

                for tier_rec in tier_recs:
                    if tier_rec.annual_savings > 100:  # Only significant savings
                        recommendations.append(
                            CostRecommendation(
                                category="tier",
                                resource_name=tier_rec.storage_name,
                                resource_type="storage_account",
                                action=f"Migrate to {tier_rec.recommended_tier} tier",
                                current_cost_per_month=tier_rec.current_cost_per_month,
                                potential_cost_per_month=tier_rec.potential_cost_per_month,
                                monthly_savings=tier_rec.annual_savings / 12,
                                annual_savings=tier_rec.annual_savings,
                                effort="medium",
                                risk="low",
                                priority=2,
                            )
                        )
            except Exception:
                pass

        # Sort by annual savings (highest first)
        recommendations.sort(key=lambda r: r.annual_savings, reverse=True)

        return recommendations

    @classmethod
    def estimate_savings(
        cls, resource_group: str, recommendations: list[CostRecommendation] | None = None
    ) -> SavingsEstimate:
        """Estimate total savings from recommendations.

        Args:
            resource_group: Resource group to analyze
            recommendations: Optional pre-computed recommendations

        Returns:
            SavingsEstimate: Total savings potential
        """
        if recommendations is None:
            recommendations = cls.get_recommendations(resource_group=resource_group)

        # Calculate totals
        total_monthly = sum(r.monthly_savings for r in recommendations)
        total_annual = sum(r.annual_savings for r in recommendations)

        # Break down by category
        savings_by_category = {}
        for rec in recommendations:
            category = rec.category
            if category not in savings_by_category:
                savings_by_category[category] = 0.0
            savings_by_category[category] += rec.annual_savings

        # Determine confidence
        if len(recommendations) >= 3 and total_annual > 500:
            confidence = "high"
        elif len(recommendations) >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return SavingsEstimate(
            total_monthly_savings=total_monthly,
            total_annual_savings=total_annual,
            recommendations_count=len(recommendations),
            savings_by_category=savings_by_category,
            confidence=confidence,
        )

    @classmethod
    def generate_report(cls, resource_group: str, output_format: str = "text") -> str:
        """Generate cost analysis report.

        Args:
            resource_group: Resource group to analyze
            output_format: "text", "json", or "csv"

        Returns:
            Formatted report string
        """
        analysis = cls.analyze_costs(resource_group=resource_group)
        recommendations = cls.get_recommendations(resource_group=resource_group)

        if output_format == "json":
            return json.dumps(
                {
                    "analysis": {
                        "total_cost": analysis.total_cost,
                        "breakdown": {
                            "storage": analysis.cost_breakdown.storage_accounts,
                            "disks": analysis.cost_breakdown.managed_disks,
                            "snapshots": analysis.cost_breakdown.snapshots,
                            "orphaned": analysis.cost_breakdown.orphaned_resources,
                        },
                    },
                    "recommendations": [
                        {
                            "category": r.category,
                            "resource": r.resource_name,
                            "action": r.action,
                            "savings": r.annual_savings,
                        }
                        for r in recommendations
                    ],
                },
                indent=2,
            )

        if output_format == "csv":
            lines = ["Category,Resource,Action,Monthly Savings,Annual Savings,Priority"]
            for r in recommendations:
                lines.append(
                    f"{r.category},{r.resource_name},{r.action},{r.monthly_savings:.2f},{r.annual_savings:.2f},{r.priority}"
                )
            return "\n".join(lines)

        # text
        lines = [
            f"Storage Cost Analysis: {resource_group}",
            "=" * 50,
            f"Total Monthly Cost: ${analysis.total_cost:.2f}",
            "",
            "Recommendations:",
        ]

        for i, rec in enumerate(recommendations[:5], 1):
            lines.append(f"{i}. {rec.action} - ${rec.annual_savings:.2f}/year")

        return "\n".join(lines)

    # Private helper methods

    @classmethod
    def _calculate_storage_costs(cls, resource_group: str) -> float:
        """Calculate total storage account costs."""
        if not StorageManager:
            return 0.0

        try:
            storage_list = StorageManager.list_storage(resource_group=resource_group)
            return sum(getattr(s, "monthly_cost", 0.0) for s in storage_list)
        except Exception:
            return 0.0

    @classmethod
    def _calculate_disk_costs(cls, resource_group: str) -> float:
        """Calculate total managed disk costs."""
        try:
            cmd = ["az", "disk", "list", "--resource-group", resource_group, "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                disks = json.loads(result.stdout)
                total = 0.0

                for disk in disks:
                    size_gb = disk.get("diskSizeGb", 0)
                    tier = disk.get("sku", {}).get("tier", "Standard")

                    if tier == "Premium":
                        total += size_gb * PREMIUM_DISK_COST
                    else:
                        total += size_gb * STANDARD_DISK_COST

                return total
        except Exception:
            return 0.0

    @classmethod
    def _calculate_snapshot_costs(cls, resource_group: str) -> float:
        """Calculate total snapshot costs."""
        try:
            cmd = ["az", "snapshot", "list", "--resource-group", resource_group, "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                snapshots = json.loads(result.stdout)
                total = sum(snap.get("diskSizeGb", 0) * SNAPSHOT_COST for snap in snapshots)
                return total
        except Exception:
            return 0.0

    @classmethod
    def _calculate_orphaned_costs(cls, resource_group: str) -> float:
        """Calculate total orphaned resource costs."""
        if not OrphanedResourceDetector:
            return 0.0

        try:
            report = OrphanedResourceDetector.scan_all(resource_group=resource_group)
            return report.total_cost_per_month
        except Exception:
            return 0.0
