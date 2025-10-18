"""Unit tests for cost_tracker module."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from azlin.cost_tracker import CostSummary, CostTracker, CostTrackerError, VMCostEstimate
from azlin.vm_manager import VMInfo, VMManagerError


class TestVMCostEstimate:
    """Tests for VMCostEstimate dataclass."""

    def test_is_running(self):
        """Test is_running check."""
        estimate = VMCostEstimate(
            vm_name="test-vm",
            vm_size="Standard_D2s_v3",
            power_state="VM running",
            hourly_rate=Decimal("0.096"),
            hours_running=Decimal("10"),
            estimated_cost=Decimal("0.96"),
            region="eastus",
        )
        assert estimate.is_running() is True

    def test_is_not_running(self):
        """Test stopped VM."""
        estimate = VMCostEstimate(
            vm_name="test-vm",
            vm_size="Standard_D2s_v3",
            power_state="VM stopped",
            hourly_rate=Decimal("0.096"),
            hours_running=Decimal("0"),
            estimated_cost=Decimal("0"),
            region="eastus",
        )
        assert estimate.is_running() is False


class TestCostSummary:
    """Tests for CostSummary dataclass."""

    def test_get_monthly_estimate(self):
        """Test monthly cost estimation."""
        estimates = [
            VMCostEstimate(
                vm_name="vm-1",
                vm_size="Standard_D2s_v3",
                power_state="VM running",
                hourly_rate=Decimal("0.096"),
                hours_running=Decimal("10"),
                estimated_cost=Decimal("0.96"),
                region="eastus",
            ),
            VMCostEstimate(
                vm_name="vm-2",
                vm_size="Standard_B2s",
                power_state="VM running",
                hourly_rate=Decimal("0.0416"),
                hours_running=Decimal("5"),
                estimated_cost=Decimal("0.208"),
                region="eastus",
            ),
            VMCostEstimate(
                vm_name="vm-3",
                vm_size="Standard_D2s_v3",
                power_state="VM stopped",
                hourly_rate=Decimal("0.096"),
                hours_running=Decimal("0"),
                estimated_cost=Decimal("0"),
                region="eastus",
            ),
        ]

        summary = CostSummary(
            total_cost=Decimal("1.168"),
            total_vms=3,
            running_vms=2,
            stopped_vms=1,
            estimates=estimates,
        )

        # Monthly estimate should only include running VMs
        # (0.096 + 0.0416) * 730 = 100.368
        monthly = summary.get_monthly_estimate()
        assert monthly == Decimal("0.096") * 730 + Decimal("0.0416") * 730

    def test_get_monthly_estimate_no_running_vms(self):
        """Test monthly estimate with no running VMs."""
        estimates = [
            VMCostEstimate(
                vm_name="vm-1",
                vm_size="Standard_D2s_v3",
                power_state="VM stopped",
                hourly_rate=Decimal("0.096"),
                hours_running=Decimal("0"),
                estimated_cost=Decimal("0"),
                region="eastus",
            )
        ]

        summary = CostSummary(
            total_cost=Decimal("0"), total_vms=1, running_vms=0, stopped_vms=1, estimates=estimates
        )

        monthly = summary.get_monthly_estimate()
        assert monthly == Decimal("0")


class TestCostTracker:
    """Tests for CostTracker class."""

    def test_get_hourly_rate_known_sizes(self):
        """Test hourly rate retrieval for known VM sizes."""
        assert CostTracker._get_hourly_rate("Standard_D2s_v3") == Decimal("0.096")
        assert CostTracker._get_hourly_rate("Standard_B2s") == Decimal("0.0416")
        assert CostTracker._get_hourly_rate("Standard_F2s_v2") == Decimal("0.085")

    def test_get_hourly_rate_estimated_sizes(self):
        """Test hourly rate estimation for unknown VM sizes."""
        # Should estimate based on naming patterns
        rate = CostTracker._get_hourly_rate("Standard_D2_unknown")
        assert rate == Decimal("0.10")  # D2 pattern

        rate = CostTracker._get_hourly_rate("Standard_B4_custom")
        assert rate == Decimal("0.16")  # B4 pattern

    def test_get_hourly_rate_unknown_size(self):
        """Test hourly rate for completely unknown VM size."""
        rate = CostTracker._get_hourly_rate("Unknown_VM_Size")
        assert rate == Decimal("0.10")  # Default rate

    def test_calculate_hours_running_with_dates(self):
        """Test hours calculation with explicit dates."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            created_time="2024-10-01T10:00:00Z",
        )

        from_date = datetime(2024, 10, 1, 10, 0, 0)
        to_date = datetime(2024, 10, 1, 20, 0, 0)

        hours = CostTracker._calculate_hours_running(vm, from_date, to_date)
        assert hours == Decimal("10")

    def test_calculate_hours_running_from_creation(self):
        """Test hours calculation from VM creation time."""
        # Create a timestamp 24 hours ago
        created_time = datetime.now() - timedelta(hours=24)
        created_time_str = created_time.isoformat() + "Z"

        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            created_time=created_time_str,
        )

        hours = CostTracker._calculate_hours_running(vm, None, None)
        # Should be approximately 24 hours (allow some variation)
        assert 23.9 < float(hours) < 24.1

    def test_calculate_hours_running_no_creation_time(self):
        """Test hours calculation when creation time is unavailable."""
        vm = VMInfo(
            name="test-vm", resource_group="test-rg", location="eastus", power_state="VM running"
        )

        hours = CostTracker._calculate_hours_running(vm, None, None)
        # Should default to 1 hour
        assert hours == Decimal("1")

    def test_estimate_vm_cost(self):
        """Test cost estimation for a single VM."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_D2s_v3",
            created_time="2024-10-01T10:00:00Z",
        )

        from_date = datetime(2024, 10, 1, 10, 0, 0)
        to_date = datetime(2024, 10, 1, 20, 0, 0)

        estimate = CostTracker.estimate_vm_cost(vm, from_date, to_date)

        assert estimate.vm_name == "test-vm"
        assert estimate.vm_size == "Standard_D2s_v3"
        assert estimate.power_state == "VM running"
        assert estimate.hourly_rate == Decimal("0.096")
        assert estimate.hours_running == Decimal("10")
        assert estimate.estimated_cost == Decimal("0.96")

    @patch("azlin.cost_tracker.VMManager.list_vms")
    @patch("azlin.cost_tracker.VMManager.filter_by_prefix")
    def test_estimate_costs_success(self, mock_filter, mock_list):
        """Test cost estimation for all VMs in a resource group."""
        # Create test VMs
        now = datetime.now()
        created_time = (now - timedelta(hours=10)).isoformat() + "Z"

        vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                vm_size="Standard_D2s_v3",
                created_time=created_time,
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM stopped",
                vm_size="Standard_B2s",
                created_time=created_time,
            ),
        ]

        mock_list.return_value = vms
        mock_filter.return_value = vms

        summary = CostTracker.estimate_costs("test-rg")

        assert summary.total_vms == 2
        assert summary.running_vms == 1
        assert summary.stopped_vms == 1
        assert len(summary.estimates) == 2
        assert summary.total_cost > 0

        # Verify mocks were called correctly
        mock_list.assert_called_once_with("test-rg", include_stopped=True)
        mock_filter.assert_called_once_with(vms, "azlin")

    @patch("azlin.cost_tracker.VMManager.list_vms")
    @patch("azlin.cost_tracker.VMManager.filter_by_prefix")
    def test_estimate_costs_no_vms(self, mock_filter, mock_list):
        """Test cost estimation when no VMs exist."""
        mock_list.return_value = []
        mock_filter.return_value = []

        summary = CostTracker.estimate_costs("test-rg")

        assert summary.total_vms == 0
        assert summary.running_vms == 0
        assert summary.stopped_vms == 0
        assert len(summary.estimates) == 0
        assert summary.total_cost == Decimal("0")

    @patch("azlin.cost_tracker.VMManager.list_vms")
    def test_estimate_costs_vm_manager_error(self, mock_list):
        """Test cost estimation when VMManager raises an error."""
        mock_list.side_effect = VMManagerError("Failed to list VMs")

        with pytest.raises(CostTrackerError) as exc_info:
            CostTracker.estimate_costs("test-rg")

        assert "Failed to estimate costs" in str(exc_info.value)

    def test_format_cost_table_summary_only(self):
        """Test formatting cost table without per-VM breakdown."""
        estimates = [
            VMCostEstimate(
                vm_name="vm-1",
                vm_size="Standard_D2s_v3",
                power_state="VM running",
                hourly_rate=Decimal("0.096"),
                hours_running=Decimal("10"),
                estimated_cost=Decimal("0.96"),
                region="eastus",
            )
        ]

        summary = CostSummary(
            total_cost=Decimal("0.96"),
            total_vms=1,
            running_vms=1,
            stopped_vms=0,
            estimates=estimates,
        )

        output = CostTracker.format_cost_table(summary, by_vm=False)

        assert "Azure VM Cost Estimate" in output
        assert "Total VMs:        1" in output
        assert "Running VMs:      1" in output
        assert "Stopped VMs:      0" in output
        assert "Total Cost:       $0.96" in output
        assert "Monthly Estimate:" in output
        assert "Per-VM Breakdown" not in output

    def test_format_cost_table_with_breakdown(self):
        """Test formatting cost table with per-VM breakdown."""
        estimates = [
            VMCostEstimate(
                vm_name="vm-1",
                vm_size="Standard_D2s_v3",
                power_state="VM running",
                hourly_rate=Decimal("0.096"),
                hours_running=Decimal("10"),
                estimated_cost=Decimal("0.96"),
                region="eastus",
            ),
            VMCostEstimate(
                vm_name="vm-2",
                vm_size="Standard_B2s",
                power_state="VM stopped",
                hourly_rate=Decimal("0.0416"),
                hours_running=Decimal("5"),
                estimated_cost=Decimal("0.208"),
                region="eastus",
            ),
        ]

        summary = CostSummary(
            total_cost=Decimal("1.168"),
            total_vms=2,
            running_vms=1,
            stopped_vms=1,
            estimates=estimates,
        )

        output = CostTracker.format_cost_table(summary, by_vm=True)

        assert "Per-VM Breakdown" in output
        assert "VM NAME" in output
        assert "SIZE" in output
        assert "STATUS" in output
        assert "RATE/HR" in output
        assert "HOURS" in output
        assert "COST" in output
        assert "vm-1" in output
        assert "vm-2" in output
        assert "Running" in output
        assert "Stopped" in output

    def test_format_cost_table_with_date_range(self):
        """Test formatting cost table with date range."""
        estimates = [
            VMCostEstimate(
                vm_name="vm-1",
                vm_size="Standard_D2s_v3",
                power_state="VM running",
                hourly_rate=Decimal("0.096"),
                hours_running=Decimal("10"),
                estimated_cost=Decimal("0.96"),
                region="eastus",
            )
        ]

        from_date = datetime(2024, 10, 1)
        to_date = datetime(2024, 10, 31)

        summary = CostSummary(
            total_cost=Decimal("0.96"),
            total_vms=1,
            running_vms=1,
            stopped_vms=0,
            estimates=estimates,
            date_range=(from_date, to_date),
        )

        output = CostTracker.format_cost_table(summary, by_vm=False)

        assert "Period: 2024-10-01 to 2024-10-31" in output

    def test_estimate_costs_with_date_range(self):
        """Test cost estimation with specific date range."""
        # This tests the integration of date filtering
        vm = VMInfo(
            name="azlin-vm-1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_D2s_v3",
            created_time="2024-10-01T00:00:00Z",
        )

        with (
            patch("azlin.cost_tracker.VMManager.list_vms") as mock_list,
            patch("azlin.cost_tracker.VMManager.filter_by_prefix") as mock_filter,
        ):
            mock_list.return_value = [vm]
            mock_filter.return_value = [vm]

            from_date = datetime(2024, 10, 1, 0, 0, 0)
            to_date = datetime(2024, 10, 1, 12, 0, 0)

            summary = CostTracker.estimate_costs("test-rg", from_date=from_date, to_date=to_date)

            assert summary.date_range == (from_date, to_date)
            # Should calculate 12 hours
            assert summary.estimates[0].hours_running == Decimal("12")

    def test_vm_pricing_coverage(self):
        """Test that common VM sizes have defined pricing."""
        # Ensure we have pricing for common VM sizes
        common_sizes = ["Standard_B2s", "Standard_D2s_v3", "Standard_E2s_v3", "Standard_F2s_v2"]

        for size in common_sizes:
            rate = CostTracker._get_hourly_rate(size)
            assert rate > 0
            assert rate in CostTracker.VM_PRICING.values()
