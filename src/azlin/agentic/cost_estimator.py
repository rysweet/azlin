"""Cost estimation for Azure resources.

Estimates costs based on resource types, sizes, and Azure pricing.
"""

import logging
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar

from azlin.agentic.types import CostEstimate

logger = logging.getLogger(__name__)


class PricingRegion(str, Enum):
    """Azure pricing regions."""

    US_EAST = "eastus"
    US_WEST = "westus"
    US_CENTRAL = "centralus"
    EUROPE_WEST = "westeurope"
    EUROPE_NORTH = "northeurope"
    ASIA_SOUTHEAST = "southeastasia"


class CostEstimator:
    """Estimates Azure resource costs.

    Uses simplified Azure pricing data for common resource types.
    Actual costs may vary based on:
    - Specific Azure region
    - Reserved instance discounts
    - Spot pricing
    - Actual usage patterns

    Example:
        >>> estimator = CostEstimator(region=PricingRegion.US_EAST)
        >>> factors = {"vm_count": 1, "vm_size": "Standard_B2s"}
        >>> estimate = estimator.estimate(factors)
        >>> print(f"Monthly cost: ${estimate.monthly_cost:.2f}")
    """

    # Simplified Azure pricing (USD/hour) - US East region baseline
    # Source: Azure pricing calculator (as of 2024)
    VM_PRICING: ClassVar[dict[str, float]] = {
        # B-series (Burstable)
        "Standard_B1s": 0.0104,
        "Standard_B1ms": 0.0207,
        "Standard_B2s": 0.0416,
        "Standard_B2ms": 0.0832,
        "Standard_B4ms": 0.166,
        # D-series (General Purpose)
        "Standard_D2s_v3": 0.096,
        "Standard_D4s_v3": 0.192,
        "Standard_D8s_v3": 0.384,
        "Standard_D16s_v3": 0.768,
        # E-series (Memory Optimized)
        "Standard_E2s_v3": 0.126,
        "Standard_E4s_v3": 0.252,
        "Standard_E8s_v3": 0.504,
        # F-series (Compute Optimized)
        "Standard_F2s_v2": 0.085,
        "Standard_F4s_v2": 0.169,
        "Standard_F8s_v2": 0.338,
        # N-series (GPU)
        "Standard_NC6": 0.90,
        "Standard_NC12": 1.80,
        "Standard_NC24": 3.60,
    }

    # Storage pricing (USD/GB/month)
    STORAGE_PRICING: ClassVar[dict[str, float]] = {
        "standard_hdd": 0.04,  # Standard HDD
        "standard_ssd": 0.15,  # Standard SSD
        "premium_ssd": 0.20,  # Premium SSD
    }

    # Network egress pricing (USD/GB) - first 5GB free
    NETWORK_EGRESS_PRICING: ClassVar[dict[str, float]] = {
        "first_10tb": 0.087,  # 5GB-10TB
        "next_40tb": 0.083,  # 10TB-50TB
        "next_100tb": 0.07,  # 50TB-150TB
        "over_150tb": 0.05,  # 150TB+
    }

    # Regional multipliers (relative to US East)
    REGIONAL_MULTIPLIERS: ClassVar[dict[PricingRegion, float]] = {
        PricingRegion.US_EAST: 1.0,
        PricingRegion.US_WEST: 1.0,
        PricingRegion.US_CENTRAL: 0.95,
        PricingRegion.EUROPE_WEST: 1.10,
        PricingRegion.EUROPE_NORTH: 1.05,
        PricingRegion.ASIA_SOUTHEAST: 1.15,
    }

    def __init__(self, region: PricingRegion = PricingRegion.US_EAST):
        """Initialize cost estimator.

        Args:
            region: Azure region for pricing
        """
        self.region = region
        self.regional_multiplier = self.REGIONAL_MULTIPLIERS.get(region, 1.0)

    def estimate(self, factors: dict[str, Any]) -> CostEstimate:
        """Estimate costs from resource factors.

        Args:
            factors: Dictionary of cost factors from execution strategy

        Returns:
            CostEstimate with hourly and monthly costs

        Example:
            >>> factors = {
            ...     "vm_count": 2,
            ...     "vm_size": "Standard_B2s",
            ...     "storage_gb": 256,
            ...     "storage_type": "standard_ssd"
            ... }
            >>> estimate = estimator.estimate(factors)
        """
        breakdown = {}
        notes = []
        confidence_score = 1.0

        # Estimate VM costs
        if "vm_count" in factors:
            vm_cost, vm_notes = self._estimate_vm_cost(
                count=factors.get("vm_count", 1),
                size=factors.get("vm_size", "Standard_B2s"),
            )
            breakdown["compute"] = vm_cost
            notes.extend(vm_notes)

        # Estimate storage costs
        if "storage_gb" in factors:
            storage_cost, storage_notes = self._estimate_storage_cost(
                size_gb=factors.get("storage_gb", 128),
                storage_type=factors.get("storage_type", "standard_ssd"),
            )
            breakdown["storage"] = storage_cost
            notes.extend(storage_notes)

        # Estimate network costs (simplified - assume minimal egress)
        if "network_egress_gb" in factors:
            network_cost = self._estimate_network_cost(factors["network_egress_gb"])
            breakdown["network"] = network_cost
            notes.append(f"Network egress: {factors['network_egress_gb']}GB/month")

        # AKS cluster costs (includes control plane + nodes)
        if "aks_node_count" in factors:
            aks_cost, aks_notes = self._estimate_aks_cost(
                node_count=factors.get("aks_node_count", 3),
                node_size=factors.get("aks_node_size", "Standard_D2s_v3"),
            )
            breakdown["aks"] = aks_cost
            notes.extend(aks_notes)
            # Lower confidence for AKS (more variables)
            confidence_score = 0.8

        # If we couldn't estimate anything, return zero cost with low confidence
        if not breakdown:
            notes.append("No cost factors recognized - unable to estimate")
            return CostEstimate(
                total_monthly=Decimal("0"),
                total_hourly=Decimal("0"),
                breakdown={},
                confidence="low",
            )

        # Calculate totals
        hourly_cost = sum(breakdown.values())
        monthly_cost = hourly_cost * 730  # Average hours per month

        # Add regional pricing note
        if self.regional_multiplier != 1.0:
            notes.append(
                f"Prices adjusted for {self.region.value} region (x{self.regional_multiplier:.2f})"
            )

        # Determine confidence string
        if confidence_score >= 0.8:
            confidence_str = "high"
        elif confidence_score >= 0.5:
            confidence_str = "medium"
        else:
            confidence_str = "low"

        # Convert breakdown to monthly costs (Decimal)
        breakdown_monthly = {k: Decimal(str(v * 730)) for k, v in breakdown.items()}

        return CostEstimate(
            total_monthly=Decimal(str(monthly_cost)),
            total_hourly=Decimal(str(hourly_cost)),
            breakdown=breakdown_monthly,
            confidence=confidence_str,
        )

    def _estimate_vm_cost(self, count: int, size: str) -> tuple[float, list[str]]:
        """Estimate VM compute costs.

        Args:
            count: Number of VMs
            size: VM size (e.g., "Standard_B2s")

        Returns:
            Tuple of (hourly_cost, notes)
        """
        notes = []

        # Get base price
        base_price = self.VM_PRICING.get(size)
        if base_price is None:
            # Unknown size - use B2s as fallback
            base_price = self.VM_PRICING["Standard_B2s"]
            notes.append(f"Unknown VM size '{size}', using Standard_B2s pricing as estimate")
            confidence_note = "low confidence"
        else:
            confidence_note = "high confidence"

        # Apply regional multiplier
        hourly_cost = base_price * count * self.regional_multiplier

        notes.append(f"{count}x {size} VM(s) at ${base_price:.4f}/hour ({confidence_note})")

        return hourly_cost, notes

    def _estimate_storage_cost(self, size_gb: int, storage_type: str) -> tuple[float, list[str]]:
        """Estimate storage costs.

        Args:
            size_gb: Storage size in GB
            storage_type: Type of storage (standard_hdd, standard_ssd, premium_ssd)

        Returns:
            Tuple of (monthly_cost_as_hourly, notes)
        """
        notes = []

        # Get storage price per GB per month
        monthly_per_gb = self.STORAGE_PRICING.get(
            storage_type, self.STORAGE_PRICING["standard_ssd"]
        )

        # Convert to hourly equivalent
        hourly_cost = (size_gb * monthly_per_gb * self.regional_multiplier) / 730

        notes.append(f"{size_gb}GB {storage_type} storage at ${monthly_per_gb:.4f}/GB/month")

        return hourly_cost, notes

    def _estimate_network_cost(self, egress_gb_monthly: int) -> float:
        """Estimate network egress costs.

        Args:
            egress_gb_monthly: Monthly egress in GB

        Returns:
            Hourly cost equivalent
        """
        # First 5GB free
        if egress_gb_monthly <= 5:
            return 0.0

        billable_gb = egress_gb_monthly - 5

        # Simplified: use first tier pricing
        monthly_cost = billable_gb * self.NETWORK_EGRESS_PRICING["first_10tb"]

        return monthly_cost / 730  # Convert to hourly

    def _estimate_aks_cost(self, node_count: int, node_size: str) -> tuple[float, list[str]]:
        """Estimate AKS cluster costs.

        Args:
            node_count: Number of nodes
            node_size: Node VM size

        Returns:
            Tuple of (hourly_cost, notes)
        """
        notes = []

        # AKS control plane is free for basic tier
        # Cost is just the node VMs
        vm_cost, vm_notes = self._estimate_vm_cost(node_count, node_size)

        notes.append(f"AKS cluster: {node_count} nodes")
        notes.extend(vm_notes)
        notes.append("Note: Control plane is free (standard tier)")

        return vm_cost, notes

    def format_estimate(self, estimate: CostEstimate, show_breakdown: bool = True) -> str:
        """Format cost estimate for display.

        Args:
            estimate: Cost estimate to format
            show_breakdown: Whether to show cost breakdown

        Returns:
            Formatted string
        """
        lines = []

        # Header
        lines.append("Cost Estimate:")
        lines.append("-" * 40)

        # Main costs
        lines.append(f"  Hourly:  ${float(estimate.total_hourly):.4f} USD")
        lines.append(f"  Monthly: ${float(estimate.total_monthly):.2f} USD (730 hours)")

        # Convert confidence string to display format
        confidence_map = {"high": "High (>80%)", "medium": "Medium (50-80%)", "low": "Low (<50%)"}
        confidence_display = confidence_map.get(estimate.confidence, estimate.confidence)
        lines.append(f"  Confidence: {confidence_display}")

        # Breakdown (already in monthly costs)
        if show_breakdown and estimate.breakdown:
            lines.append("\nBreakdown:")
            for category, monthly_cost in estimate.breakdown.items():
                hourly = float(monthly_cost) / 730
                lines.append(
                    f"  {category.title()}: ${float(monthly_cost):.2f}/month (${hourly:.4f}/hour)"
                )

        return "\n".join(lines)
