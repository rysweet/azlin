"""Unit tests for VM lifecycle control module.

Tests cover:
- Stop/start single VMs
- Batch stop/start operations
- Cost calculation and tracking
- Error handling
- Edge cases
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from azlin.vm_lifecycle_control import (
    LifecycleResult,
    LifecycleSummary,
    VMLifecycleControlError,
    VMLifecycleController,
)


class TestLifecycleResult:
    """Test LifecycleResult dataclass."""

    def test_success_repr_without_cost(self):
        """Test repr for successful operation without cost impact."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=True,
            message="VM stopped successfully",
            operation="stop",
        )
        assert "[SUCCESS]" in str(result)
        assert "test-vm" in str(result)
        assert "VM stopped successfully" in str(result)

    def test_success_repr_with_cost(self):
        """Test repr for successful operation with cost impact."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=True,
            message="VM stopped successfully",
            operation="stop",
            cost_impact="Saves ~$0.096/hour",
        )
        assert "[SUCCESS]" in str(result)
        assert "Saves ~$0.096/hour" in str(result)

    def test_failure_repr(self):
        """Test repr for failed operation."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=False,
            message="VM not found",
            operation="stop",
        )
        assert "[FAILED]" in str(result)
        assert "VM not found" in str(result)


class TestLifecycleSummary:
    """Test LifecycleSummary dataclass."""

    def test_all_succeeded_true(self):
        """Test all_succeeded property when all operations succeed."""
        summary = LifecycleSummary(
            total=2,
            succeeded=2,
            failed=0,
            results=[],
            operation="stop",
            total_cost_savings=0.192,
        )
        assert summary.all_succeeded is True

    def test_all_succeeded_false(self):
        """Test all_succeeded property when some operations fail."""
        summary = LifecycleSummary(
            total=2,
            succeeded=1,
            failed=1,
            results=[],
            operation="stop",
            total_cost_savings=0.096,
        )
        assert summary.all_succeeded is False

    def test_get_failed_vms(self):
        """Test getting list of failed VMs."""
        results = [
            LifecycleResult("vm1", True, "Success", "stop"),
            LifecycleResult("vm2", False, "Failed", "stop"),
            LifecycleResult("vm3", False, "Failed", "stop"),
        ]
        summary = LifecycleSummary(
            total=3,
            succeeded=1,
            failed=2,
            results=results,
            operation="stop",
            total_cost_savings=0.096,
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
            total=3,
            succeeded=2,
            failed=1,
            results=results,
            operation="stop",
            total_cost_savings=0.192,
        )
        succeeded = summary.get_succeeded_vms()
        assert succeeded == ["vm1", "vm3"]

    def test_total_cost_savings_field_exists(self):
        """Test that total_cost_savings field exists and is accessible."""
        summary = LifecycleSummary(
            total=1,
            succeeded=1,
            failed=0,
            results=[],
            operation="stop",
            total_cost_savings=0.096,
        )
        assert hasattr(summary, "total_cost_savings")
        assert summary.total_cost_savings == 0.096

    def test_total_cost_savings_defaults_to_zero(self):
        """Test that total_cost_savings defaults to 0.0."""
        summary = LifecycleSummary(
            total=0,
            succeeded=0,
            failed=0,
            results=[],
            operation="start",
        )
        assert summary.total_cost_savings == 0.0


class TestVMLifecycleController:
    """Test VMLifecycleController class."""

    @pytest.fixture
    def mock_vm_info(self):
        """Mock VM info response."""
        return {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/running"},
            ],
        }

    @pytest.fixture
    def mock_stopped_vm_info(self):
        """Mock stopped VM info response."""
        return {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/deallocated"},
            ],
        }

    def test_stop_vm_success(self, mock_vm_info):
        """Test successful VM stop operation."""
        with (
            patch.object(VMLifecycleController, "_get_vm_details", return_value=mock_vm_info),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

                result = VMLifecycleController.stop_vm("test-vm", "test-rg")

                assert result.success is True
                assert result.vm_name == "test-vm"
                assert "deallocated" in result.message.lower()
                assert result.cost_impact is not None
                assert "$0.096" in result.cost_impact

    def test_stop_vm_already_stopped(self, mock_stopped_vm_info):
        """Test stopping an already stopped VM."""
        with patch.object(
            VMLifecycleController, "_get_vm_details", return_value=mock_stopped_vm_info
        ):
            result = VMLifecycleController.stop_vm("test-vm", "test-rg")

            assert result.success is True
            assert "already" in result.message.lower()

    def test_stop_vm_not_found(self):
        """Test stopping a non-existent VM."""
        with patch.object(VMLifecycleController, "_get_vm_details", return_value=None):
            result = VMLifecycleController.stop_vm("test-vm", "test-rg")

            assert result.success is False
            assert "not found" in result.message.lower()

    def test_stop_vm_with_unknown_size(self):
        """Test stopping VM with unknown size uses default cost."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Unknown_Size"},
            "statuses": [{"code": "PowerState/running"}],
        }
        with (
            patch.object(VMLifecycleController, "_get_vm_details", return_value=vm_info),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

                result = VMLifecycleController.stop_vm("test-vm", "test-rg")

                assert result.success is True
                # Should use DEFAULT_COST (0.10)
                assert "$0.100" in result.cost_impact

    def test_start_vm_success(self, mock_stopped_vm_info):
        """Test successful VM start operation."""
        with patch.object(
            VMLifecycleController, "_get_vm_details", return_value=mock_stopped_vm_info
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = VMLifecycleController.start_vm("test-vm", "test-rg")

            assert result.success is True
            assert result.vm_name == "test-vm"
            assert "started" in result.message.lower()
            assert result.cost_impact is not None
            assert "$0.096" in result.cost_impact

    def test_start_vm_already_running(self, mock_vm_info):
        """Test starting an already running VM."""
        with patch.object(VMLifecycleController, "_get_vm_details", return_value=mock_vm_info):
            result = VMLifecycleController.start_vm("test-vm", "test-rg")

            assert result.success is True
            assert "already running" in result.message.lower()

    def test_stop_vms_empty_resource_group(self):
        """Test stopping VMs in an empty resource group."""
        with patch.object(VMLifecycleController, "_list_vms_in_group", return_value=[]):
            summary = VMLifecycleController.stop_vms("test-rg", all_vms=True)

            assert summary.total == 0
            assert summary.succeeded == 0
            assert summary.failed == 0
            assert summary.total_cost_savings == 0.0

    def test_stop_vms_cost_calculation(self, mock_vm_info):
        """Test that cost calculation is properly stored in summary."""
        vm_names = ["vm1", "vm2", "vm3"]

        with (
            patch.object(VMLifecycleController, "_list_vms_in_group", return_value=vm_names),
            patch.object(VMLifecycleController, "_get_vm_details", return_value=mock_vm_info),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            summary = VMLifecycleController.stop_vms("test-rg", all_vms=True)

                    # All 3 VMs succeeded
                    assert summary.total == 3
                    assert summary.succeeded == 3
                    assert summary.failed == 0

                    # Cost calculation: 3 VMs * $0.096/hour = $0.288/hour
                    assert summary.total_cost_savings == pytest.approx(0.288, rel=0.01)

    def test_stop_vms_mixed_success_cost_calculation(self, mock_vm_info):
        """Test cost calculation with mixed success/failure."""
        vm_names = ["vm1", "vm2", "vm3"]

        def mock_stop_vm(vm_name, resource_group, deallocate=True, no_wait=False):
            """Mock stop_vm with mixed results."""
            if vm_name == "vm2":
                return LifecycleResult(
                    vm_name=vm_name,
                    success=False,
                    message="Failed to stop",
                    operation="deallocate",
                )
            return LifecycleResult(
                vm_name=vm_name,
                success=True,
                message="VM deallocated successfully",
                operation="deallocate",
                cost_impact="Saves ~$0.096/hour",
            )

        with (
            patch.object(VMLifecycleController, "_list_vms_in_group", return_value=vm_names),
            patch.object(VMLifecycleController, "stop_vm", side_effect=mock_stop_vm),
        ):
            summary = VMLifecycleController.stop_vms("test-rg", all_vms=True)

            assert summary.total == 3
            assert summary.succeeded == 2
            assert summary.failed == 1

                # Only 2 successful VMs contribute to cost savings: 2 * $0.096 = $0.192
                assert summary.total_cost_savings == pytest.approx(0.192, rel=0.01)

    def test_stop_vms_no_cost_impact(self):
        """Test cost calculation when VMs have no cost impact string."""
        vm_names = ["vm1"]

        def mock_stop_vm(vm_name, resource_group, deallocate=True, no_wait=False):
            """Mock stop_vm without cost_impact."""
            return LifecycleResult(
                vm_name=vm_name,
                success=True,
                message="VM stopped (not deallocated)",
                operation="stop",
                cost_impact="Still incurs compute costs",  # No $ sign
            )

        with (
            patch.object(VMLifecycleController, "_list_vms_in_group", return_value=vm_names),
            patch.object(VMLifecycleController, "stop_vm", side_effect=mock_stop_vm),
        ):
            summary = VMLifecycleController.stop_vms("test-rg", all_vms=True, deallocate=False)

            assert summary.total == 1
            assert summary.succeeded == 1
            # No cost savings because deallocate=False
            assert summary.total_cost_savings == 0.0

    def test_stop_vms_pattern_matching(self):
        """Test VM pattern matching."""
        all_vms = ["azlin-dev-1", "azlin-dev-2", "azlin-prod-1"]

        with (
            patch.object(VMLifecycleController, "_list_vms_in_group", return_value=all_vms),
            patch.object(
                VMLifecycleController,
                "stop_vm",
                return_value=LifecycleResult("test", True, "Success", "stop"),
            ),
        ):
            # Should only match dev VMs
            summary = VMLifecycleController.stop_vms("test-rg", vm_pattern="azlin-dev-*")

            assert summary.total == 2

    def test_start_vms_success(self, mock_stopped_vm_info):
        """Test starting multiple VMs."""
        vm_names = ["vm1", "vm2"]

        with (
            patch.object(VMLifecycleController, "_list_vms_in_group", return_value=vm_names),
            patch.object(
                VMLifecycleController, "_get_vm_details", return_value=mock_stopped_vm_info
            ),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            summary = VMLifecycleController.start_vms("test-rg", all_vms=True)

                    assert summary.total == 2
                    assert summary.succeeded == 2
                    assert summary.failed == 0
                    assert summary.operation == "start"
                    # Start operations don't calculate cost savings
                    assert summary.total_cost_savings == 0.0

    def test_get_vm_details_not_found(self):
        """Test getting details for non-existent VM."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "cmd", stderr="ResourceNotFound"
            )

            result = VMLifecycleController._get_vm_details("test-vm", "test-rg")
            assert result is None

    def test_get_vm_details_timeout(self):
        """Test timeout when getting VM details."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

            with pytest.raises(VMLifecycleControlError, match="timed out"):
                VMLifecycleController._get_vm_details("test-vm", "test-rg")

    def test_list_vms_in_group_success(self):
        """Test listing VMs in resource group."""
        expected_vms = ["vm1", "vm2", "vm3"]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps(expected_vms)
            )

            vms = VMLifecycleController._list_vms_in_group("test-rg")
            assert vms == expected_vms

    def test_list_vms_resource_group_not_found(self):
        """Test listing VMs in non-existent resource group."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "cmd", stderr="ResourceGroupNotFound"
            )

            vms = VMLifecycleController._list_vms_in_group("test-rg")
            assert vms == []

    def test_get_power_state(self):
        """Test extracting power state from VM info."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/running"},
            ]
        }

        state = VMLifecycleController._get_power_state(vm_info)
        assert state == "VM running"

    def test_get_power_state_deallocated(self):
        """Test extracting deallocated power state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/deallocated"},
            ]
        }

        state = VMLifecycleController._get_power_state(vm_info)
        assert state == "VM deallocated"

    def test_get_power_state_unknown(self):
        """Test handling unknown power state."""
        vm_info = {"statuses": [{"code": "ProvisioningState/succeeded"}]}

        state = VMLifecycleController._get_power_state(vm_info)
        assert state == "Unknown"


class TestCostCalculationEdgeCases:
    """Test edge cases in cost calculation."""

    def test_malformed_cost_impact_string(self):
        """Test handling of malformed cost_impact strings."""
        results = [
            LifecycleResult(
                "vm1", True, "Success", "stop", cost_impact="Malformed"
            ),  # No $ sign
            LifecycleResult(
                "vm2", True, "Success", "stop", cost_impact="Saves ~$0.096/hour"
            ),  # Valid
        ]

        # Simulate the calculation logic
        total_cost_savings = sum(
            float(r.cost_impact.split("$")[1].split("/")[0])
            for r in results
            if r.success and r.cost_impact and "$" in r.cost_impact
        )

        # Only vm2 should contribute
        assert total_cost_savings == pytest.approx(0.096, rel=0.01)

    def test_empty_results_list(self):
        """Test cost calculation with empty results."""
        results = []

        total_cost_savings = sum(
            float(r.cost_impact.split("$")[1].split("/")[0])
            for r in results
            if r.success and r.cost_impact and "$" in r.cost_impact
        )

        assert total_cost_savings == 0.0

    def test_all_failed_operations(self):
        """Test cost calculation when all operations fail."""
        results = [
            LifecycleResult("vm1", False, "Failed", "stop"),
            LifecycleResult("vm2", False, "Failed", "stop"),
        ]

        total_cost_savings = sum(
            float(r.cost_impact.split("$")[1].split("/")[0])
            for r in results
            if r.success and r.cost_impact and "$" in r.cost_impact
        )

        assert total_cost_savings == 0.0

    def test_various_vm_sizes_cost_calculation(self):
        """Test cost calculation with different VM sizes."""
        results = [
            LifecycleResult(
                "vm1", True, "Success", "stop", cost_impact="Saves ~$0.096/hour"
            ),  # D2s_v3
            LifecycleResult(
                "vm2", True, "Success", "stop", cost_impact="Saves ~$0.192/hour"
            ),  # D4s_v3
            LifecycleResult(
                "vm3", True, "Success", "stop", cost_impact="Saves ~$0.0104/hour"
            ),  # B1s
        ]

        total_cost_savings = sum(
            float(r.cost_impact.split("$")[1].split("/")[0])
            for r in results
            if r.success and r.cost_impact and "$" in r.cost_impact
        )

        # 0.096 + 0.192 + 0.0104 = 0.2984
        assert total_cost_savings == pytest.approx(0.2984, rel=0.01)
