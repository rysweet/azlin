"""Unit tests for cost_estimator module.

Tests all pricing calculations, input validation, and edge cases.
"""

import pytest

from azlin.modules.cost_estimator import CostEstimator


class TestBastionCostEstimation:
    """Test Azure Bastion cost estimation."""

    def test_basic_sku_cost(self):
        """Basic SKU should return correct cost including public IP."""
        cost = CostEstimator.estimate_bastion_cost("Basic")
        assert cost == 143.65  # 140.00 + 3.65

    def test_standard_sku_cost(self):
        """Standard SKU should return correct cost including public IP."""
        cost = CostEstimator.estimate_bastion_cost("Standard")
        assert cost == 292.65  # 289.00 + 3.65

    def test_basic_sku_lowercase(self):
        """SKU name should be case-insensitive."""
        cost = CostEstimator.estimate_bastion_cost("basic")
        assert cost == 143.65

    def test_standard_sku_mixed_case(self):
        """SKU name should handle mixed case."""
        cost = CostEstimator.estimate_bastion_cost("StAnDaRd")
        assert cost == 292.65

    def test_basic_sku_with_whitespace(self):
        """SKU name should handle whitespace."""
        cost = CostEstimator.estimate_bastion_cost("  Basic  ")
        assert cost == 143.65

    def test_invalid_sku_raises_error(self):
        """Invalid SKU should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid Bastion SKU"):
            CostEstimator.estimate_bastion_cost("Premium")

    def test_empty_sku_raises_error(self):
        """Empty SKU should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid Bastion SKU"):
            CostEstimator.estimate_bastion_cost("")

    def test_none_sku_raises_error(self):
        """None SKU should raise error."""
        with pytest.raises(AttributeError):
            CostEstimator.estimate_bastion_cost(None)  # type: ignore


class TestPrivateEndpointCostEstimation:
    """Test private endpoint cost estimation."""

    def test_default_data_transfer(self):
        """Default 100GB data transfer should return correct cost."""
        cost = CostEstimator.estimate_private_endpoint_cost()
        assert cost == 8.30  # 7.30 + (100 * 0.01)

    def test_zero_data_transfer(self):
        """Zero data transfer should return base cost only."""
        cost = CostEstimator.estimate_private_endpoint_cost(0)
        assert cost == 7.30

    def test_small_data_transfer(self):
        """Small data transfer should calculate correctly."""
        cost = CostEstimator.estimate_private_endpoint_cost(10)
        assert cost == pytest.approx(7.40)  # 7.30 + (10 * 0.01)

    def test_large_data_transfer(self):
        """Large data transfer (1TB) should calculate correctly."""
        cost = CostEstimator.estimate_private_endpoint_cost(1024)
        assert cost == 17.54  # 7.30 + (1024 * 0.01)

    def test_float_data_transfer(self):
        """Fractional GB should be handled correctly."""
        cost = CostEstimator.estimate_private_endpoint_cost(50.5)
        assert cost == 7.805  # 7.30 + (50.5 * 0.01)

    def test_negative_data_transfer_raises_error(self):
        """Negative data transfer should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            CostEstimator.estimate_private_endpoint_cost(-100)

    def test_negative_fractional_raises_error(self):
        """Negative fractional value should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            CostEstimator.estimate_private_endpoint_cost(-0.1)


class TestNFSCostEstimation:
    """Test NFS storage cost estimation."""

    def test_premium_100gb(self):
        """100GB Premium NFS should calculate correctly."""
        cost = CostEstimator.estimate_nfs_cost(100, "Premium")
        assert cost == 20.00  # 100 * 0.20

    def test_premium_500gb(self):
        """500GB Premium NFS should calculate correctly."""
        cost = CostEstimator.estimate_nfs_cost(500, "Premium")
        assert cost == 100.00  # 500 * 0.20

    def test_standard_100gb(self):
        """100GB Standard NFS should calculate correctly."""
        cost = CostEstimator.estimate_nfs_cost(100, "Standard")
        assert cost == 6.00  # 100 * 0.06

    def test_standard_500gb(self):
        """500GB Standard NFS should calculate correctly."""
        cost = CostEstimator.estimate_nfs_cost(500, "Standard")
        assert cost == 30.00  # 500 * 0.06

    def test_premium_1tb(self):
        """1TB Premium NFS should calculate correctly."""
        cost = CostEstimator.estimate_nfs_cost(1024, "Premium")
        assert cost == 204.80  # 1024 * 0.20

    def test_tier_case_insensitive(self):
        """Tier should be case-insensitive."""
        cost1 = CostEstimator.estimate_nfs_cost(100, "premium")
        cost2 = CostEstimator.estimate_nfs_cost(100, "PREMIUM")
        assert cost1 == cost2 == 20.00

    def test_tier_with_whitespace(self):
        """Tier should handle whitespace."""
        cost = CostEstimator.estimate_nfs_cost(100, "  Premium  ")
        assert cost == 20.00

    def test_zero_size_raises_error(self):
        """Zero size should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            CostEstimator.estimate_nfs_cost(0, "Premium")

    def test_negative_size_raises_error(self):
        """Negative size should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            CostEstimator.estimate_nfs_cost(-100, "Premium")

    def test_invalid_tier_raises_error(self):
        """Invalid tier should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            CostEstimator.estimate_nfs_cost(100, "Basic")

    def test_empty_tier_raises_error(self):
        """Empty tier should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            CostEstimator.estimate_nfs_cost(100, "")


class TestCostFormatting:
    """Test cost formatting for display."""

    def test_format_basic_cost(self):
        """Basic cost should format with 2 decimals."""
        formatted = CostEstimator.format_cost(143.65)
        assert formatted == "$143.65/month"

    def test_format_zero_cost(self):
        """Zero cost should format correctly."""
        formatted = CostEstimator.format_cost(0)
        assert formatted == "$0.00/month"

    def test_format_large_cost(self):
        """Large cost should format correctly."""
        formatted = CostEstimator.format_cost(1234.5)
        assert formatted == "$1234.50/month"

    def test_format_rounds_correctly(self):
        """Cost should round to 2 decimals."""
        formatted = CostEstimator.format_cost(123.456789)
        assert formatted == "$123.46/month"

    def test_format_fractional_cent(self):
        """Fractional cents should round correctly."""
        formatted = CostEstimator.format_cost(10.005)
        assert formatted == "$10.01/month"  # Banker's rounding

    def test_format_negative_cost(self):
        """Negative cost should format with minus sign."""
        formatted = CostEstimator.format_cost(-50.00)
        assert formatted == "$-50.00/month"


class TestCostConstants:
    """Test that cost constants are correctly defined."""

    def test_bastion_basic_constant(self):
        """BASTION_BASIC constant should be defined."""
        assert CostEstimator.BASTION_BASIC == 140.00

    def test_bastion_standard_constant(self):
        """BASTION_STANDARD constant should be defined."""
        assert CostEstimator.BASTION_STANDARD == 289.00

    def test_public_ip_static_constant(self):
        """PUBLIC_IP_STATIC constant should be defined."""
        assert CostEstimator.PUBLIC_IP_STATIC == 3.65

    def test_private_endpoint_constant(self):
        """PRIVATE_ENDPOINT constant should be defined."""
        assert CostEstimator.PRIVATE_ENDPOINT == 7.30

    def test_vnet_peering_gb_constant(self):
        """VNET_PEERING_GB constant should be defined."""
        assert CostEstimator.VNET_PEERING_GB == 0.01

    def test_nfs_premium_gb_constant(self):
        """NFS_PREMIUM_GB constant should be defined."""
        assert CostEstimator.NFS_PREMIUM_GB == 0.20

    def test_nfs_standard_gb_constant(self):
        """NFS_STANDARD_GB constant should be defined."""
        assert CostEstimator.NFS_STANDARD_GB == 0.06


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_data_transfer(self):
        """Very small data transfer should work."""
        cost = CostEstimator.estimate_private_endpoint_cost(0.001)
        assert cost == pytest.approx(7.30001)

    def test_very_large_storage(self):
        """Very large storage (100TB) should calculate correctly."""
        cost = CostEstimator.estimate_nfs_cost(102400, "Premium")  # 100TB
        assert cost == 20480.00

    def test_minimum_valid_storage(self):
        """Minimum valid storage (1GB) should work."""
        cost = CostEstimator.estimate_nfs_cost(1, "Premium")
        assert cost == 0.20

    def test_bastion_cost_breakdown(self):
        """Verify Bastion cost includes host + IP."""
        basic_cost = CostEstimator.estimate_bastion_cost("Basic")
        expected = CostEstimator.BASTION_BASIC + CostEstimator.PUBLIC_IP_STATIC
        assert basic_cost == expected
