"""Integration test for storage tier optimization workflow."""


class TestStorageTierOptimization:
    """Test storage tier optimization workflow."""

    def test_tier_recommendation_based_on_usage(self):
        """Test recommending tier based on usage patterns."""
        # Usage scenarios
        high_iops_usage = {"iops": 5000, "throughput_mbps": 200}
        low_iops_usage = {"iops": 100, "throughput_mbps": 10}

        # Recommend tier
        def recommend_tier(usage):
            if usage["iops"] > 1000:
                return "Premium"
            return "Standard"

        assert recommend_tier(high_iops_usage) == "Premium"
        assert recommend_tier(low_iops_usage) == "Standard"
