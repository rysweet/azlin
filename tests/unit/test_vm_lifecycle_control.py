"""Tests for VM lifecycle control module."""

import pytest

from azlin.vm_lifecycle_control import (
    LifecycleResult,
    LifecycleSummary,
    VMLifecycleController,
)


class TestLifecycleResult:
    """Tests for LifecycleResult dataclass."""

    def test_repr_with_cost_impact(self):
        """Test __repr__ includes cost impact when present."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=True,
            message="VM stopped successfully",
            operation="stop",
            cost_impact="Saves ~$0.096/hour",
        )
        repr_str = repr(result)
        assert "test-vm" in repr_str
        assert "SUCCESS" in repr_str
        assert "Saves ~$0.096/hour" in repr_str

    def test_repr_without_cost_impact(self):
        """Test __repr__ works without cost impact."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=False,
            message="VM not found",
            operation="stop",
        )
        repr_str = repr(result)
        assert "test-vm" in repr_str
        assert "FAILED" in repr_str


class TestLifecycleSummary:
    """Tests for LifecycleSummary dataclass."""

    def test_all_succeeded_true(self):
        """Test all_succeeded property when all operations succeed."""
        summary = LifecycleSummary(total=3, succeeded=3, failed=0, results=[], operation="stop")
        assert summary.all_succeeded is True

    def test_all_succeeded_false(self):
        """Test all_succeeded property when some operations fail."""
        summary = LifecycleSummary(total=3, succeeded=2, failed=1, results=[], operation="stop")
        assert summary.all_succeeded is False

    def test_get_failed_vms(self):
        """Test getting list of failed VMs."""
        results = [
            LifecycleResult("vm1", True, "Success", "stop"),
            LifecycleResult("vm2", False, "Failed", "stop"),
            LifecycleResult("vm3", False, "Failed", "stop"),
        ]
        summary = LifecycleSummary(
            total=3, succeeded=1, failed=2, results=results, operation="stop"
        )
        failed = summary.get_failed_vms()
        assert failed == ["vm2", "vm3"]

    def test_get_succeeded_vms(self):
        """Test getting list of succeeded VMs."""
        results = [
            LifecycleResult("vm1", True, "Success", "stop"),
            LifecycleResult("vm2", False, "Failed", "stop"),
            LifecycleResult("vm3", True, "Success", "stop"),
        ]
        summary = LifecycleSummary(
            total=3, succeeded=2, failed=1, results=results, operation="stop"
        )
        succeeded = summary.get_succeeded_vms()
        assert succeeded == ["vm1", "vm3"]

    def test_str_with_cost_savings(self):
        """Test __str__ includes cost savings when present."""
        summary = LifecycleSummary(
            total=3,
            succeeded=3,
            failed=0,
            results=[],
            operation="stop",
            total_cost_savings=0.288,
        )
        summary_str = str(summary)
        assert "Stop operation" in summary_str
        assert "3/3 succeeded" in summary_str
        assert "$0.288/hour" in summary_str

    def test_str_without_cost_savings(self):
        """Test __str__ works without cost savings."""
        summary = LifecycleSummary(total=3, succeeded=3, failed=0, results=[], operation="stop")
        summary_str = str(summary)
        assert "Stop operation" in summary_str
        assert "3/3 succeeded" in summary_str
        assert "$" not in summary_str

    def test_str_with_failures(self):
        """Test __str__ includes failure count."""
        summary = LifecycleSummary(total=3, succeeded=2, failed=1, results=[], operation="start")
        summary_str = str(summary)
        assert "Start operation" in summary_str
        assert "2/3 succeeded" in summary_str
        assert "1 failed" in summary_str

    def test_total_cost_savings_none_by_default(self):
        """Test total_cost_savings is None by default."""
        summary = LifecycleSummary(total=0, succeeded=0, failed=0, results=[], operation="stop")
        assert summary.total_cost_savings is None


class TestVMLifecycleController:
    """Tests for VMLifecycleController class."""

    def test_extract_cost_from_impact_valid(self):
        """Test extracting cost from valid cost_impact string."""
        cost = VMLifecycleController._extract_cost_from_impact("Saves ~$0.096/hour")
        assert cost == 0.096

    def test_extract_cost_from_impact_different_format(self):
        """Test extracting cost from different format."""
        cost = VMLifecycleController._extract_cost_from_impact("~$0.192/hour while running")
        assert cost == 0.192

    def test_extract_cost_from_impact_no_dollar_sign(self):
        """Test extracting cost when no dollar sign present."""
        cost = VMLifecycleController._extract_cost_from_impact("Still incurs compute costs")
        assert cost == 0.0

    def test_extract_cost_from_impact_none(self):
        """Test extracting cost from None."""
        cost = VMLifecycleController._extract_cost_from_impact(None)
        assert cost == 0.0

    def test_extract_cost_from_impact_invalid_format(self):
        """Test extracting cost from invalid format."""
        cost = VMLifecycleController._extract_cost_from_impact("$invalid/format")
        assert cost == 0.0

    def test_extract_cost_from_impact_multiple_decimals(self):
        """Test extracting cost with multiple decimal places."""
        cost = VMLifecycleController._extract_cost_from_impact("Saves ~$0.0104/hour")
        assert cost == 0.0104

    def test_vm_costs_dict_defined(self):
        """Test that VM_COSTS dictionary is properly defined."""
        assert "Standard_D2s_v3" in VMLifecycleController.VM_COSTS
        assert VMLifecycleController.VM_COSTS["Standard_D2s_v3"] == 0.096
        assert VMLifecycleController.DEFAULT_COST == 0.10


class TestCostCalculationIntegration:
    """Integration tests for cost calculation in lifecycle summaries."""

    def test_lifecycle_summary_with_cost_calculation(self):
        """Test that LifecycleSummary properly stores calculated costs."""
        # Simulate results from stop operations
        results = [
            LifecycleResult("vm1", True, "Stopped", "stop", cost_impact="Saves ~$0.096/hour"),
            LifecycleResult("vm2", True, "Stopped", "stop", cost_impact="Saves ~$0.192/hour"),
            LifecycleResult("vm3", False, "Failed", "stop", cost_impact=None),
        ]

        # Calculate total cost savings as the code would
        total_cost_savings = sum(
            VMLifecycleController._extract_cost_from_impact(r.cost_impact)
            for r in results
            if r.success
        )

        # Create summary
        summary = LifecycleSummary(
            total=3,
            succeeded=2,
            failed=1,
            results=results,
            operation="stop",
            total_cost_savings=total_cost_savings if total_cost_savings > 0 else None,
        )

        # Verify cost calculation
        assert summary.total_cost_savings is not None
        assert summary.total_cost_savings == pytest.approx(0.288)
        assert "0.288" in str(summary)

    def test_lifecycle_summary_no_cost_data(self):
        """Test LifecycleSummary when no cost data available."""
        results = [
            LifecycleResult("vm1", True, "Stopped", "stop", cost_impact=None),
            LifecycleResult(
                "vm2", True, "Stopped", "stop", cost_impact="Still incurs compute costs"
            ),
        ]

        total_cost_savings = sum(
            VMLifecycleController._extract_cost_from_impact(r.cost_impact)
            for r in results
            if r.success
        )

        summary = LifecycleSummary(
            total=2,
            succeeded=2,
            failed=0,
            results=results,
            operation="stop",
            total_cost_savings=total_cost_savings if total_cost_savings > 0 else None,
        )

        assert summary.total_cost_savings is None
        assert "$" not in str(summary)

    def test_lifecycle_summary_mixed_results(self):
        """Test LifecycleSummary with mix of successful and failed operations."""
        results = [
            LifecycleResult(
                "vm1", True, "Started", "start", cost_impact="~$0.096/hour while running"
            ),
            LifecycleResult("vm2", False, "Failed to start", "start", cost_impact=None),
            LifecycleResult(
                "vm3", True, "Started", "start", cost_impact="~$0.384/hour while running"
            ),
        ]

        total_cost_savings = sum(
            VMLifecycleController._extract_cost_from_impact(r.cost_impact)
            for r in results
            if r.success
        )

        summary = LifecycleSummary(
            total=3,
            succeeded=2,
            failed=1,
            results=results,
            operation="start",
            total_cost_savings=total_cost_savings if total_cost_savings > 0 else None,
        )

        # Only successful operations contribute to cost
        assert summary.total_cost_savings == pytest.approx(0.480)
        assert "2 failed" not in str(summary)  # Only 1 failed
        assert "1 failed" in str(summary)
