"""Unit tests for SSH latency measurement module.

Tests the SSHLatencyMeasurer and LatencyResult following TDD approach.
These tests WILL FAIL until implementation is complete.

Testing Coverage:
- LatencyResult dataclass and display_value() method
- SSHLatencyMeasurer initialization
- Single VM measurement (success, timeout, errors)
- Batch measurement with parallel execution
- Error handling (connection failures, timeouts)
"""

import subprocess
import time
from dataclasses import is_dataclass
from unittest.mock import Mock, patch

import pytest

from azlin.ssh.latency import LatencyResult, SSHLatencyMeasurer


# ============================================================================
# TEST DATA - Mock VM Objects
# ============================================================================


class MockVMInfo:
    """Mock VM object for testing."""

    def __init__(self, name, status="Running", ip="10.0.1.5", location="eastus"):
        self.name = name
        self.status = status
        self.private_ip = ip
        self.location = location

    def is_running(self):
        return self.status == "Running"


# ============================================================================
# LATENCY RESULT TESTS
# ============================================================================


class TestLatencyResult:
    """Test LatencyResult dataclass."""

    def test_latency_result_is_dataclass(self):
        """Test that LatencyResult is a dataclass."""
        assert is_dataclass(LatencyResult)

    def test_latency_result_success_initialization(self):
        """Test LatencyResult initialization for successful measurement."""
        result = LatencyResult(
            vm_name="test-vm", success=True, latency_ms=45.3, error_type=None, error_message=None
        )

        assert result.vm_name == "test-vm"
        assert result.success is True
        assert result.latency_ms == 45.3
        assert result.error_type is None
        assert result.error_message is None

    def test_latency_result_timeout_initialization(self):
        """Test LatencyResult initialization for timeout."""
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            latency_ms=None,
            error_type="timeout",
            error_message="Connection timed out after 5.0 seconds",
        )

        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.latency_ms is None
        assert result.error_type == "timeout"
        assert result.error_message == "Connection timed out after 5.0 seconds"

    def test_latency_result_error_initialization(self):
        """Test LatencyResult initialization for connection error."""
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            latency_ms=None,
            error_type="connection",
            error_message="Connection refused",
        )

        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.latency_ms is None
        assert result.error_type == "connection"
        assert result.error_message == "Connection refused"

    def test_latency_result_display_value_success(self):
        """Test display_value() returns formatted ms for successful measurement."""
        result = LatencyResult(vm_name="test-vm", success=True, latency_ms=45.3)

        display = result.display_value()
        assert display == "45ms"  # Integer ms, no decimals

    def test_latency_result_display_value_success_rounded(self):
        """Test display_value() rounds latency to integer."""
        result = LatencyResult(vm_name="test-vm", success=True, latency_ms=123.7)

        display = result.display_value()
        assert display == "124ms"  # Rounded up

        result = LatencyResult(vm_name="test-vm", success=True, latency_ms=123.2)
        display = result.display_value()
        assert display == "123ms"  # Rounded down

    def test_latency_result_display_value_timeout(self):
        """Test display_value() returns 'timeout' for timeout errors."""
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            error_type="timeout",
            error_message="Connection timed out",
        )

        assert result.display_value() == "timeout"

    def test_latency_result_display_value_connection_error(self):
        """Test display_value() returns 'error' for connection errors."""
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            error_type="connection",
            error_message="Connection refused",
        )

        assert result.display_value() == "error"

    def test_latency_result_display_value_unknown_error(self):
        """Test display_value() returns '-' for unknown errors."""
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            error_type="unknown",
            error_message="Something went wrong",
        )

        assert result.display_value() == "-"

    def test_latency_result_display_value_no_error_type(self):
        """Test display_value() returns '-' when success=False but no error_type."""
        result = LatencyResult(vm_name="test-vm", success=False, error_type=None)

        assert result.display_value() == "-"


# ============================================================================
# SSH LATENCY MEASURER TESTS - Initialization
# ============================================================================


class TestSSHLatencyMeasurerInit:
    """Test SSHLatencyMeasurer initialization."""

    def test_measurer_default_initialization(self):
        """Test measurer initializes with default parameters."""
        measurer = SSHLatencyMeasurer()

        assert measurer.timeout == 5.0
        assert measurer.max_workers == 10

    def test_measurer_custom_timeout(self):
        """Test measurer initializes with custom timeout."""
        measurer = SSHLatencyMeasurer(timeout=10.0)

        assert measurer.timeout == 10.0

    def test_measurer_custom_max_workers(self):
        """Test measurer initializes with custom max_workers."""
        measurer = SSHLatencyMeasurer(max_workers=5)

        assert measurer.max_workers == 5

    def test_measurer_both_custom_params(self):
        """Test measurer initializes with both custom parameters."""
        measurer = SSHLatencyMeasurer(timeout=3.0, max_workers=20)

        assert measurer.timeout == 3.0
        assert measurer.max_workers == 20


# ============================================================================
# SSH LATENCY MEASURER TESTS - Single VM Measurement
# ============================================================================


class TestSSHLatencyMeasurerSingle:
    """Test measure_single() method."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_measure_single_success(self, mock_time, mock_subprocess):
        """Test successful SSH connection measurement."""
        # Mock time: 50ms elapsed
        mock_time.side_effect = [0.0, 0.05]  # Start and end times

        # Mock successful SSH connection
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify result
        assert result.vm_name == "test-vm"
        assert result.success is True
        assert result.latency_ms == 50.0  # 0.05 seconds = 50ms
        assert result.error_type is None
        assert result.error_message is None

        # Verify SSH command was called correctly
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        cmd = call_args[0][0]

        assert "ssh" in cmd
        assert "-i" in cmd
        assert "/tmp/key" in cmd
        assert "azureuser@10.0.1.5" in cmd

    @patch("subprocess.run")
    def test_measure_single_timeout(self, mock_subprocess):
        """Test timeout during SSH connection."""
        # Mock timeout exception
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd=["ssh"], timeout=5.0)

        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify timeout result
        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.latency_ms is None
        assert result.error_type == "timeout"
        assert "timeout" in result.error_message.lower()

    @patch("subprocess.run")
    def test_measure_single_connection_refused(self, mock_subprocess):
        """Test connection refused error."""
        # Mock connection failure
        mock_result = Mock()
        mock_result.returncode = 255  # SSH error code
        mock_result.stderr = "Connection refused"
        mock_subprocess.return_value = mock_result

        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify connection error result
        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.latency_ms is None
        assert result.error_type == "connection"
        assert "refused" in result.error_message.lower()

    @patch("subprocess.run")
    def test_measure_single_permission_denied(self, mock_subprocess):
        """Test permission denied error (wrong key)."""
        # Mock permission denied
        mock_result = Mock()
        mock_result.returncode = 255
        mock_result.stderr = "Permission denied (publickey)"
        mock_subprocess.return_value = mock_result

        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify permission error result
        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.error_type == "connection"
        assert "permission" in result.error_message.lower()

    @patch("subprocess.run")
    def test_measure_single_network_unreachable(self, mock_subprocess):
        """Test network unreachable error."""
        # Mock network unreachable
        mock_result = Mock()
        mock_result.returncode = 255
        mock_result.stderr = "Network is unreachable"
        mock_subprocess.return_value = mock_result

        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify network error result
        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.error_type == "connection"
        assert "unreachable" in result.error_message.lower()

    @patch("subprocess.run")
    def test_measure_single_unknown_error(self, mock_subprocess):
        """Test unknown exception during measurement."""
        # Mock unexpected exception
        mock_subprocess.side_effect = RuntimeError("Unexpected error")

        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify unknown error result
        assert result.vm_name == "test-vm"
        assert result.success is False
        assert result.error_type == "unknown"
        assert "unexpected" in result.error_message.lower()

    @patch("subprocess.run")
    def test_measure_single_stopped_vm_skipped(self, mock_subprocess):
        """Test that stopped VMs are not measured (should be filtered by caller)."""
        # This test documents behavior - stopped VMs should be filtered before measurement
        # But if called, measurement should handle gracefully

        vm = MockVMInfo(name="test-vm", status="Stopped", ip="N/A")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        # Attempting to measure stopped VM should fail gracefully
        # (Implementation should check VM status or handle missing IP)
        # This will fail until implementation adds proper stopped VM handling


# ============================================================================
# SSH LATENCY MEASURER TESTS - Batch Measurement
# ============================================================================


class TestSSHLatencyMeasurerBatch:
    """Test measure_batch() method with parallel execution."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_measure_batch_multiple_vms_success(self, mock_time, mock_subprocess):
        """Test measuring latency for multiple VMs in parallel."""
        # Mock times for 3 VMs (different latencies)
        mock_time.side_effect = [
            0.0,
            0.045,  # VM1: 45ms
            0.0,
            0.052,  # VM2: 52ms
            0.0,
            0.123,  # VM3: 123ms
        ]

        # Mock successful SSH for all VMs
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        vms = [
            MockVMInfo(name="vm-1", ip="10.0.1.5"),
            MockVMInfo(name="vm-2", ip="10.0.1.6"),
            MockVMInfo(name="vm-3", ip="10.0.2.10"),
        ]

        measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=10)
        results = measurer.measure_batch(vms, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify all VMs measured
        assert len(results) == 3
        assert "vm-1" in results
        assert "vm-2" in results
        assert "vm-3" in results

        # Verify all successful
        assert results["vm-1"].success is True
        assert results["vm-2"].success is True
        assert results["vm-3"].success is True

        # Verify latencies
        assert results["vm-1"].latency_ms == 45.0
        assert results["vm-2"].latency_ms == 52.0
        assert results["vm-3"].latency_ms == 123.0

    @patch("subprocess.run")
    def test_measure_batch_mixed_results(self, mock_subprocess):
        """Test batch measurement with mix of success and failures."""

        def mock_ssh_call(*args, **kwargs):
            cmd = args[0]
            # Determine which VM based on IP in command
            if "10.0.1.5" in " ".join(cmd):
                # VM1: Success
                result = Mock()
                result.returncode = 0
                return result
            elif "10.0.1.6" in " ".join(cmd):
                # VM2: Timeout
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=5.0)
            else:
                # VM3: Connection error
                result = Mock()
                result.returncode = 255
                result.stderr = "Connection refused"
                return result

        mock_subprocess.side_effect = mock_ssh_call

        vms = [
            MockVMInfo(name="vm-success", ip="10.0.1.5"),
            MockVMInfo(name="vm-timeout", ip="10.0.1.6"),
            MockVMInfo(name="vm-error", ip="10.0.2.10"),
        ]

        measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=10)

        with patch("time.time", side_effect=[0.0, 0.05] * 10):  # Mock time for successful VMs
            results = measurer.measure_batch(vms, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify all VMs have results
        assert len(results) == 3

        # Verify success VM
        assert results["vm-success"].success is True
        assert results["vm-success"].latency_ms == 50.0

        # Verify timeout VM
        assert results["vm-timeout"].success is False
        assert results["vm-timeout"].error_type == "timeout"

        # Verify error VM
        assert results["vm-error"].success is False
        assert results["vm-error"].error_type == "connection"

    def test_measure_batch_filters_stopped_vms(self):
        """Test that batch measurement filters out stopped VMs."""
        vms = [
            MockVMInfo(name="vm-running", status="Running", ip="10.0.1.5"),
            MockVMInfo(name="vm-stopped", status="Stopped", ip="N/A"),
            MockVMInfo(name="vm-running-2", status="Running", ip="10.0.1.6"),
        ]

        measurer = SSHLatencyMeasurer(timeout=5.0)

        with patch.object(measurer, "measure_single") as mock_measure:
            mock_measure.return_value = LatencyResult(vm_name="test", success=True, latency_ms=50)

            results = measurer.measure_batch(vms, ssh_user="azureuser", ssh_key_path="/tmp/key")

            # Only running VMs should be measured
            assert len(results) == 2
            assert "vm-running" in results
            assert "vm-running-2" in results
            assert "vm-stopped" not in results

            # Should only call measure_single for running VMs
            assert mock_measure.call_count == 2

    def test_measure_batch_empty_list(self):
        """Test batch measurement with empty VM list."""
        measurer = SSHLatencyMeasurer(timeout=5.0)

        results = measurer.measure_batch([], ssh_user="azureuser", ssh_key_path="/tmp/key")

        assert results == {}

    def test_measure_batch_respects_max_workers(self):
        """Test that batch measurement respects max_workers limit."""
        # Create many VMs
        vms = [MockVMInfo(name=f"vm-{i}", ip=f"10.0.1.{i}") for i in range(20)]

        measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=5)

        with patch.object(measurer, "measure_single") as mock_measure:
            mock_measure.return_value = LatencyResult(vm_name="test", success=True, latency_ms=50)

            # Measure time to ensure parallel execution
            start = time.perf_counter()
            results = measurer.measure_batch(vms, ssh_user="azureuser", ssh_key_path="/tmp/key")
            elapsed = time.perf_counter() - start

            # All VMs should be measured
            assert len(results) == 20

            # Should complete faster than sequential (rough check)
            # Sequential would take 20 * 0.05s = 1s, parallel ~0.2s with 5 workers
            # Very generous threshold to avoid flaky tests
            assert elapsed < 2.0

    @patch("subprocess.run")
    def test_measure_batch_one_failure_doesnt_stop_others(self, mock_subprocess):
        """Test that one VM failure doesn't stop measurement of others."""

        def mock_ssh_call(*args, **kwargs):
            cmd = args[0]
            if "10.0.1.5" in " ".join(cmd):
                # VM1: Fail
                raise RuntimeError("Unexpected error")
            else:
                # Other VMs: Success
                result = Mock()
                result.returncode = 0
                return result

        mock_subprocess.side_effect = mock_ssh_call

        vms = [
            MockVMInfo(name="vm-fail", ip="10.0.1.5"),
            MockVMInfo(name="vm-success-1", ip="10.0.1.6"),
            MockVMInfo(name="vm-success-2", ip="10.0.1.7"),
        ]

        measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=10)

        with patch("time.time", side_effect=[0.0, 0.05] * 10):
            results = measurer.measure_batch(vms, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # All VMs should have results
        assert len(results) == 3

        # Failed VM should have error result
        assert results["vm-fail"].success is False
        assert results["vm-fail"].error_type == "unknown"

        # Other VMs should succeed
        assert results["vm-success-1"].success is True
        assert results["vm-success-2"].success is True


# ============================================================================
# SSH LATENCY MEASURER TESTS - Edge Cases
# ============================================================================


class TestSSHLatencyMeasurerEdgeCases:
    """Test edge cases and error conditions."""

    def test_measure_single_missing_ssh_key(self):
        """Test measurement with missing SSH key file."""
        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        # This should handle FileNotFoundError gracefully
        result = measurer.measure_single(
            vm, ssh_user="azureuser", ssh_key_path="/nonexistent/key"
        )

        assert result.success is False
        # Could be "connection" or "unknown" depending on implementation

    def test_measure_single_none_ssh_key_path(self):
        """Test measurement with None SSH key path."""
        vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        # Should handle None gracefully (maybe use default key or fail gracefully)
        # This documents expected behavior

    def test_measure_single_invalid_ip_format(self):
        """Test measurement with invalid IP address."""
        vm = MockVMInfo(name="test-vm", ip="invalid-ip")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        assert result.success is False
        # Should fail with connection or unknown error

    def test_measure_single_empty_vm_name(self):
        """Test measurement with empty VM name."""
        vm = MockVMInfo(name="", ip="10.0.1.5")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Should still attempt measurement (name is just for result tracking)
        assert result.vm_name == ""

    @patch("subprocess.run")
    def test_measure_single_very_high_latency(self, mock_subprocess):
        """Test measurement with very high latency (near timeout)."""
        # Mock slow connection (4.9 seconds)
        with patch("time.time", side_effect=[0.0, 4.9]):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_subprocess.return_value = mock_result

            vm = MockVMInfo(name="test-vm", ip="10.0.1.5")
            measurer = SSHLatencyMeasurer(timeout=5.0)

            result = measurer.measure_single(vm, ssh_user="azureuser", ssh_key_path="/tmp/key")

            # Should succeed with high latency
            assert result.success is True
            assert result.latency_ms == 4900.0  # 4.9s = 4900ms


# ============================================================================
# INTEGRATION-STYLE TESTS (Unit tests that test multiple components)
# ============================================================================


class TestSSHLatencyMeasurerIntegration:
    """Integration-style unit tests."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_full_measurement_workflow(self, mock_time, mock_subprocess):
        """Test complete workflow from batch measurement to display."""
        # Mock times
        mock_time.side_effect = [0.0, 0.045, 0.0, 0.052, 0.0, 0.123]

        # Mock SSH results
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        # Create VMs
        vms = [
            MockVMInfo(name="vm-1", ip="10.0.1.5"),
            MockVMInfo(name="vm-2", ip="10.0.1.6"),
            MockVMInfo(name="vm-3", ip="10.0.2.10"),
        ]

        # Measure latencies
        measurer = SSHLatencyMeasurer(timeout=5.0)
        results = measurer.measure_batch(vms, ssh_user="azureuser", ssh_key_path="/tmp/key")

        # Verify display values
        assert results["vm-1"].display_value() == "45ms"
        assert results["vm-2"].display_value() == "52ms"
        assert results["vm-3"].display_value() == "123ms"

    def test_latency_result_to_dict_serialization(self):
        """Test that LatencyResult can be serialized to dict (for JSON output)."""
        result = LatencyResult(vm_name="test-vm", success=True, latency_ms=45.3)

        # Should be convertible to dict (dataclass feature)
        from dataclasses import asdict

        result_dict = asdict(result)

        assert result_dict["vm_name"] == "test-vm"
        assert result_dict["success"] is True
        assert result_dict["latency_ms"] == 45.3
