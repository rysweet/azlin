"""Unit tests for vm_lifecycle_control module."""

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

    def test_lifecycle_result_success(self):
        """Test LifecycleResult with success."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=True,
            message="VM deallocated successfully",
            operation="deallocate",
            cost_impact="Saves ~$0.096/hour",
        )

        assert result.vm_name == "test-vm"
        assert result.success is True
        assert result.message == "VM deallocated successfully"
        assert result.operation == "deallocate"
        assert result.cost_impact == "Saves ~$0.096/hour"

    def test_lifecycle_result_failure(self):
        """Test LifecycleResult with failure."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=False,
            message="VM not found",
            operation="start",
        )

        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.message == "VM not found"
        assert result.operation == "start"
        assert result.cost_impact is None

    def test_lifecycle_result_repr_success(self):
        """Test LifecycleResult __repr__ with success."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=True,
            message="VM started",
            operation="start",
            cost_impact="~$0.100/hour while running",
        )

        repr_str = repr(result)
        assert "[SUCCESS]" in repr_str
        assert "test-vm" in repr_str
        assert "VM started" in repr_str
        assert "~$0.100/hour while running" in repr_str

    def test_lifecycle_result_repr_failure(self):
        """Test LifecycleResult __repr__ with failure."""
        result = LifecycleResult(
            vm_name="test-vm",
            success=False,
            message="Failed to start: timeout",
            operation="start",
        )

        repr_str = repr(result)
        assert "[FAILED]" in repr_str
        assert "test-vm" in repr_str
        assert "Failed to start: timeout" in repr_str


class TestLifecycleSummary:
    """Test LifecycleSummary dataclass."""

    def test_lifecycle_summary_all_succeeded(self):
        """Test LifecycleSummary when all operations succeeded."""
        results = [
            LifecycleResult("vm1", True, "success", "stop"),
            LifecycleResult("vm2", True, "success", "stop"),
            LifecycleResult("vm3", True, "success", "stop"),
        ]
        summary = LifecycleSummary(
            total=3,
            succeeded=3,
            failed=0,
            results=results,
            operation="stop",
        )

        assert summary.all_succeeded is True
        assert summary.get_failed_vms() == []
        assert summary.get_succeeded_vms() == ["vm1", "vm2", "vm3"]

    def test_lifecycle_summary_some_failed(self):
        """Test LifecycleSummary when some operations failed."""
        results = [
            LifecycleResult("vm1", True, "success", "start"),
            LifecycleResult("vm2", False, "failed", "start"),
            LifecycleResult("vm3", True, "success", "start"),
        ]
        summary = LifecycleSummary(
            total=3,
            succeeded=2,
            failed=1,
            results=results,
            operation="start",
        )

        assert summary.all_succeeded is False
        assert summary.get_failed_vms() == ["vm2"]
        assert summary.get_succeeded_vms() == ["vm1", "vm3"]

    def test_lifecycle_summary_get_failed_vms(self):
        """Test getting list of failed VMs."""
        results = [
            LifecycleResult("vm1", True, "success", "stop"),
            LifecycleResult("vm2", False, "timeout", "stop"),
            LifecycleResult("vm3", False, "not found", "stop"),
        ]
        summary = LifecycleSummary(
            total=3,
            succeeded=1,
            failed=2,
            results=results,
            operation="stop",
        )

        assert summary.get_failed_vms() == ["vm2", "vm3"]


class TestVMLifecycleController:
    """Test VMLifecycleController class."""

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_success_deallocate(self, mock_run):
        """Test successful VM deallocate operation."""
        # Mock VM details response
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "statuses": [{"code": "PowerState/running"}],
        }

        # Mock subprocess calls
        mock_run.side_effect = [
            # First call: get-instance-view
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            # Second call: deallocate
            MagicMock(stdout="", returncode=0),
        ]

        result = VMLifecycleController.stop_vm("test-vm", "test-rg", deallocate=True)

        assert result.success is True
        assert result.vm_name == "test-vm"
        assert result.message == "VM deallocated successfully"
        assert result.operation == "deallocate"
        assert "Saves ~$0.096/hour" in result.cost_impact

        # Verify subprocess calls
        assert mock_run.call_count == 2
        # Verify deallocate command
        dealloc_call = mock_run.call_args_list[1]
        assert "deallocate" in dealloc_call[0][0]
        assert "--name" in dealloc_call[0][0]
        assert "test-vm" in dealloc_call[0][0]

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_success_stop_only(self, mock_run):
        """Test successful VM stop (without deallocate) operation."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_B2s"},
            "statuses": [{"code": "PowerState/running"}],
        }

        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            MagicMock(stdout="", returncode=0),
        ]

        result = VMLifecycleController.stop_vm("test-vm", "test-rg", deallocate=False)

        assert result.success is True
        assert result.message == "VM stopped successfully"
        assert result.operation == "stop"
        assert result.cost_impact == "Still incurs compute costs"

        # Verify stop command (not deallocate)
        stop_call = mock_run.call_args_list[1]
        assert "stop" in stop_call[0][0]
        assert "deallocate" not in stop_call[0][0]

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_already_stopped(self, mock_run):
        """Test stopping VM that is already stopped."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_B2s"},
            "statuses": [{"code": "PowerState/stopped"}],
        }

        mock_run.return_value = MagicMock(stdout=json.dumps(vm_info), returncode=0)

        result = VMLifecycleController.stop_vm("test-vm", "test-rg")

        assert result.success is True
        assert result.message == "VM already vm stopped"
        # Should not call deallocate command
        assert mock_run.call_count == 1

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_already_deallocated(self, mock_run):
        """Test stopping VM that is already deallocated."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_D4s_v3"},
            "statuses": [{"code": "PowerState/deallocated"}],
        }

        mock_run.return_value = MagicMock(stdout=json.dumps(vm_info), returncode=0)

        result = VMLifecycleController.stop_vm("test-vm", "test-rg", deallocate=True)

        assert result.success is True
        assert result.message == "VM already vm deallocated"
        # Should not call deallocate command
        assert mock_run.call_count == 1

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_not_found(self, mock_run):
        """Test stopping VM that doesn't exist."""
        # Mock ResourceNotFound error
        error = subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound")
        mock_run.side_effect = error

        result = VMLifecycleController.stop_vm("nonexistent-vm", "test-rg")

        assert result.success is False
        assert result.message == "VM not found"
        assert result.vm_name == "nonexistent-vm"

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_timeout(self, mock_run):
        """Test stopping VM when operation times out."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_B1s"},
            "statuses": [{"code": "PowerState/running"}],
        }

        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            subprocess.TimeoutExpired("az", 180),
        ]

        result = VMLifecycleController.stop_vm("test-vm", "test-rg")

        assert result.success is False
        assert "timeout" in result.message.lower()
        assert result.operation == "deallocate"

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_cost_impact_calculation(self, mock_run):
        """Test cost impact calculation for different VM sizes."""
        test_cases = [
            ("Standard_D2s_v3", "Saves ~$0.096/hour"),
            ("Standard_D4s_v3", "Saves ~$0.192/hour"),
            ("Standard_B1s", "Saves ~$0.010/hour"),
            ("UnknownSize", "Saves ~$0.100/hour"),  # Default cost
        ]

        for vm_size, expected_cost in test_cases:
            vm_info = {
                "hardwareProfile": {"vmSize": vm_size},
                "statuses": [{"code": "PowerState/running"}],
            }

            mock_run.side_effect = [
                MagicMock(stdout=json.dumps(vm_info), returncode=0),
                MagicMock(stdout="", returncode=0),
            ]

            result = VMLifecycleController.stop_vm("test-vm", "test-rg", deallocate=True)

            assert result.success is True
            assert expected_cost in result.cost_impact

            mock_run.reset_mock()

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_stop_vm_subprocess_error(self, mock_run):
        """Test handling subprocess CalledProcessError."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_B2s"},
            "statuses": [{"code": "PowerState/running"}],
        }

        error = subprocess.CalledProcessError(1, "az", stderr="Operation failed")
        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            error,
        ]

        result = VMLifecycleController.stop_vm("test-vm", "test-rg")

        assert result.success is False
        assert "Failed to deallocate" in result.message
        assert "Operation failed" in result.message

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_start_vm_success(self, mock_run):
        """Test successful VM start operation."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_D8s_v3"},
            "statuses": [{"code": "PowerState/deallocated"}],
        }

        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            MagicMock(stdout="", returncode=0),
        ]

        result = VMLifecycleController.start_vm("test-vm", "test-rg")

        assert result.success is True
        assert result.message == "VM started successfully"
        assert result.operation == "start"
        assert "~$0.384/hour while running" in result.cost_impact

        # Verify start command
        start_call = mock_run.call_args_list[1]
        assert "start" in start_call[0][0]
        assert "test-vm" in start_call[0][0]

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_start_vm_already_running(self, mock_run):
        """Test starting VM that is already running."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_B4ms"},
            "statuses": [{"code": "PowerState/running"}],
        }

        mock_run.return_value = MagicMock(stdout=json.dumps(vm_info), returncode=0)

        result = VMLifecycleController.start_vm("test-vm", "test-rg")

        assert result.success is True
        assert result.message == "VM already running"
        # Should not call start command
        assert mock_run.call_count == 1

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_start_vm_not_found(self, mock_run):
        """Test starting VM that doesn't exist."""
        error = subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound")
        mock_run.side_effect = error

        result = VMLifecycleController.start_vm("nonexistent-vm", "test-rg")

        assert result.success is False
        assert result.message == "VM not found"
        assert result.vm_name == "nonexistent-vm"

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_start_vm_timeout(self, mock_run):
        """Test starting VM when operation times out."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "statuses": [{"code": "PowerState/stopped"}],
        }

        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            subprocess.TimeoutExpired("az", 180),
        ]

        result = VMLifecycleController.start_vm("test-vm", "test-rg")

        assert result.success is False
        assert "timeout" in result.message.lower()
        assert result.operation == "start"

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_start_vm_cost_impact_display(self, mock_run):
        """Test cost impact display for start operation."""
        test_cases = [
            ("Standard_D2s_v3", "~$0.096/hour while running"),
            ("Standard_B1s", "~$0.010/hour while running"),
            ("UnknownSize", "~$0.100/hour while running"),
        ]

        for vm_size, expected_cost in test_cases:
            vm_info = {
                "hardwareProfile": {"vmSize": vm_size},
                "statuses": [{"code": "PowerState/stopped"}],
            }

            mock_run.side_effect = [
                MagicMock(stdout=json.dumps(vm_info), returncode=0),
                MagicMock(stdout="", returncode=0),
            ]

            result = VMLifecycleController.start_vm("test-vm", "test-rg")

            assert result.success is True
            assert expected_cost in result.cost_impact

            mock_run.reset_mock()

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_start_vm_subprocess_error(self, mock_run):
        """Test handling subprocess CalledProcessError on start."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_B2s"},
            "statuses": [{"code": "PowerState/stopped"}],
        }

        error = subprocess.CalledProcessError(1, "az", stderr="Start failed")
        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(vm_info), returncode=0),
            error,
        ]

        result = VMLifecycleController.start_vm("test-vm", "test-rg")

        assert result.success is False
        assert "Failed to start" in result.message
        assert "Start failed" in result.message

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    @patch("azlin.vm_lifecycle_control.VMLifecycleController.stop_vm")
    def test_stop_vms_batch_with_pattern(self, mock_stop_vm, mock_list_vms):
        """Test batch stop with pattern matching."""
        # Mock VM list
        mock_list_vms.return_value = ["azlin-dev-1", "azlin-dev-2", "azlin-prod-1", "other-vm"]

        # Mock stop results
        mock_stop_vm.side_effect = [
            LifecycleResult("azlin-dev-1", True, "stopped", "stop"),
            LifecycleResult("azlin-dev-2", True, "stopped", "stop"),
        ]

        summary = VMLifecycleController.stop_vms(
            resource_group="test-rg",
            vm_pattern="azlin-dev-*",
            deallocate=True,
        )

        assert summary.total == 2
        assert summary.succeeded == 2
        assert summary.failed == 0
        assert summary.operation == "stop"
        # Only azlin-dev-* VMs should be stopped
        assert mock_stop_vm.call_count == 2

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    @patch("azlin.vm_lifecycle_control.VMLifecycleController.stop_vm")
    def test_stop_vms_batch_all_vms(self, mock_stop_vm, mock_list_vms):
        """Test batch stop with all_vms flag."""
        mock_list_vms.return_value = ["vm1", "vm2", "vm3"]

        mock_stop_vm.side_effect = [
            LifecycleResult("vm1", True, "stopped", "stop"),
            LifecycleResult("vm2", True, "stopped", "stop"),
            LifecycleResult("vm3", True, "stopped", "stop"),
        ]

        summary = VMLifecycleController.stop_vms(
            resource_group="test-rg",
            all_vms=True,
        )

        assert summary.total == 3
        assert summary.succeeded == 3
        assert mock_stop_vm.call_count == 3

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    def test_stop_vms_batch_empty_result(self, mock_list_vms):
        """Test batch stop with no matching VMs."""
        mock_list_vms.return_value = ["vm1", "vm2"]

        summary = VMLifecycleController.stop_vms(
            resource_group="test-rg",
            vm_pattern="nonexistent-*",
        )

        assert summary.total == 0
        assert summary.succeeded == 0
        assert summary.failed == 0

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    def test_stop_vms_batch_no_vms_in_group(self, mock_list_vms):
        """Test batch stop when resource group has no VMs."""
        mock_list_vms.return_value = []

        summary = VMLifecycleController.stop_vms(
            resource_group="empty-rg",
            all_vms=True,
        )

        assert summary.total == 0
        assert summary.succeeded == 0
        assert summary.failed == 0

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    @patch("azlin.vm_lifecycle_control.VMLifecycleController.stop_vm")
    def test_stop_vms_batch_parallel_execution(self, mock_stop_vm, mock_list_vms):
        """Test batch stop executes in parallel."""
        mock_list_vms.return_value = ["vm1", "vm2", "vm3", "vm4", "vm5"]

        # Mock results with some failures
        mock_stop_vm.side_effect = [
            LifecycleResult("vm1", True, "stopped", "stop", "Saves ~$0.096/hour"),
            LifecycleResult("vm2", False, "timeout", "stop"),
            LifecycleResult("vm3", True, "stopped", "stop", "Saves ~$0.100/hour"),
            LifecycleResult("vm4", True, "stopped", "stop", "Saves ~$0.050/hour"),
            LifecycleResult("vm5", False, "not found", "stop"),
        ]

        summary = VMLifecycleController.stop_vms(
            resource_group="test-rg",
            all_vms=True,
            max_workers=3,
        )

        assert summary.total == 5
        assert summary.succeeded == 3
        assert summary.failed == 2
        assert len(summary.get_succeeded_vms()) == 3
        assert len(summary.get_failed_vms()) == 2

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    @patch("azlin.vm_lifecycle_control.VMLifecycleController.start_vm")
    def test_start_vms_batch_with_pattern(self, mock_start_vm, mock_list_vms):
        """Test batch start with pattern matching."""
        mock_list_vms.return_value = ["azlin-dev-1", "azlin-dev-2", "azlin-prod-1"]

        mock_start_vm.side_effect = [
            LifecycleResult("azlin-dev-1", True, "started", "start"),
            LifecycleResult("azlin-dev-2", True, "started", "start"),
        ]

        summary = VMLifecycleController.start_vms(
            resource_group="test-rg",
            vm_pattern="azlin-dev-*",
        )

        assert summary.total == 2
        assert summary.succeeded == 2
        assert summary.operation == "start"
        assert mock_start_vm.call_count == 2

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    @patch("azlin.vm_lifecycle_control.VMLifecycleController.start_vm")
    def test_start_vms_batch_parallel_execution(self, mock_start_vm, mock_list_vms):
        """Test batch start executes in parallel."""
        mock_list_vms.return_value = ["vm1", "vm2", "vm3"]

        mock_start_vm.side_effect = [
            LifecycleResult("vm1", True, "started", "start"),
            LifecycleResult("vm2", True, "started", "start"),
            LifecycleResult("vm3", False, "failed", "start"),
        ]

        summary = VMLifecycleController.start_vms(
            resource_group="test-rg",
            all_vms=True,
            max_workers=2,
        )

        assert summary.total == 3
        assert summary.succeeded == 2
        assert summary.failed == 1

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_get_vm_details_with_instance_view(self, mock_run):
        """Test _get_vm_details returns proper VM info."""
        vm_info = {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/running"},
            ],
        }

        mock_run.return_value = MagicMock(stdout=json.dumps(vm_info), returncode=0)

        result = VMLifecycleController._get_vm_details("test-vm", "test-rg")

        assert result == vm_info
        # Verify get-instance-view was called
        assert mock_run.call_args[0][0][2] == "get-instance-view"

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_get_vm_details_not_found(self, mock_run):
        """Test _get_vm_details returns None for non-existent VM."""
        error = subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound")
        mock_run.side_effect = error

        result = VMLifecycleController._get_vm_details("nonexistent-vm", "test-rg")

        assert result is None

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_get_vm_details_timeout(self, mock_run):
        """Test _get_vm_details raises error on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(VMLifecycleControlError, match="timeout"):
            VMLifecycleController._get_vm_details("test-vm", "test-rg")

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_get_vm_details_invalid_json(self, mock_run):
        """Test _get_vm_details raises error on invalid JSON."""
        mock_run.return_value = MagicMock(stdout="invalid json", returncode=0)

        with pytest.raises(VMLifecycleControlError, match="Failed to parse"):
            VMLifecycleController._get_vm_details("test-vm", "test-rg")

    def test_get_power_state_running(self):
        """Test _get_power_state extracts running state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/running"},
            ],
        }

        state = VMLifecycleController._get_power_state(vm_info)

        assert state == "VM running"

    def test_get_power_state_stopped(self):
        """Test _get_power_state extracts stopped state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/stopped"},
            ],
        }

        state = VMLifecycleController._get_power_state(vm_info)

        assert state == "VM stopped"

    def test_get_power_state_deallocated(self):
        """Test _get_power_state extracts deallocated state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/deallocated"},
            ],
        }

        state = VMLifecycleController._get_power_state(vm_info)

        assert state == "VM deallocated"

    def test_get_power_state_unknown(self):
        """Test _get_power_state returns Unknown for missing state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
            ],
        }

        state = VMLifecycleController._get_power_state(vm_info)

        assert state == "Unknown"

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_list_vms_in_group(self, mock_run):
        """Test _list_vms_in_group returns VM names."""
        vm_names = ["vm1", "vm2", "vm3"]
        mock_run.return_value = MagicMock(stdout=json.dumps(vm_names), returncode=0)

        result = VMLifecycleController._list_vms_in_group("test-rg")

        assert result == vm_names

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_list_vms_in_group_not_found(self, mock_run):
        """Test _list_vms_in_group returns empty list for non-existent RG."""
        error = subprocess.CalledProcessError(1, "az", stderr="ResourceGroupNotFound")
        mock_run.side_effect = error

        result = VMLifecycleController._list_vms_in_group("nonexistent-rg")

        assert result == []

    @patch("azlin.vm_lifecycle_control.subprocess.run")
    def test_list_vms_timeout(self, mock_run):
        """Test _list_vms_in_group raises error on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(VMLifecycleControlError, match="timeout"):
            VMLifecycleController._list_vms_in_group("test-rg")

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    def test_stop_vms_list_error(self, mock_list_vms):
        """Test stop_vms raises error when listing VMs fails."""
        mock_list_vms.side_effect = VMLifecycleControlError("Failed to list VMs")

        with pytest.raises(VMLifecycleControlError, match="Failed to stop VMs"):
            VMLifecycleController.stop_vms(resource_group="test-rg", all_vms=True)

    @patch("azlin.vm_lifecycle_control.VMLifecycleController._list_vms_in_group")
    def test_start_vms_list_error(self, mock_list_vms):
        """Test start_vms raises error when listing VMs fails."""
        mock_list_vms.side_effect = VMLifecycleControlError("Failed to list VMs")

        with pytest.raises(VMLifecycleControlError, match="Failed to start VMs"):
            VMLifecycleController.start_vms(resource_group="test-rg", all_vms=True)
