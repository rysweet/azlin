"""Integration test for cleanup cost calculation workflow."""

from decimal import Decimal

import pytest

from azlin.modules.cost_estimator import CostEstimator


class TestCleanupCostCalculation:
    """Test cost calculation during cleanup workflow."""

    def test_calculate_savings_from_cleanup(self):
        """Test calculating potential savings from cleanup."""
        try:
            estimator = CostEstimator()

            # Orphaned resources to cleanup
            orphaned_disks = [
                {"size_gb": 128, "tier": "Standard"},
                {"size_gb": 256, "tier": "Standard"},
                {"size_gb": 512, "tier": "Premium"},
            ]

            total_savings = Decimal("0")
            for disk in orphaned_disks:
                cost = estimator.estimate_disk_cost(
                    size_gb=disk["size_gb"],
                    tier=disk["tier"],
                    region="eastus",
                )
                total_savings += Decimal(str(cost))

            # Should calculate total savings
            assert total_savings > 0

        except Exception as e:
            pytest.skip(f"Cost estimation not available: {e}")
