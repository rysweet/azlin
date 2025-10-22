"""Unit tests for vm_manager module - Issue #165: VM list power state fix.

These tests verify that list_vms correctly filters VMs based on power state
when include_stopped parameter is used.

TDD approach: These tests will FAIL until the fix is implemented.
"""

import json
from unittest.mock import Mock, patch

from azlin.vm_manager import VMInfo, VMManager


class TestVMManagerPowerStateFiltering:
    """Test VM power state filtering - Issue #165."""

    # =========================================================================
    # Test 1: list_vms with include_stopped=False filters out stopped VMs
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_exclude_stopped_filters_deallocated_vms(self, mock_run):
        """Test that include_stopped=False filters out deallocated VMs.

        This test verifies that when include_stopped=False, VMs with power state
        "VM deallocated" are NOT included in the returned list.

        Expected to FAIL until fix is implemented.
        """
        # Mock Azure response with mixed power states
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-deallocated",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM deallocated",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
            {
                "name": "azlin-vm-running2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.6",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            # Mock public IPs list (empty for simplicity)
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify only running VMs are returned
        assert len(result) == 2, "Should return only 2 running VMs"
        assert all(vm.is_running() for vm in result), "All returned VMs should be running"
        vm_names = [vm.name for vm in result]
        assert "azlin-vm-running" in vm_names
        assert "azlin-vm-running2" in vm_names
        assert "azlin-vm-deallocated" not in vm_names, "Deallocated VM should be filtered out"

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_exclude_stopped_filters_stopped_vms(self, mock_run):
        """Test that include_stopped=False filters out stopped VMs.

        This test verifies that when include_stopped=False, VMs with power state
        "VM stopped" are NOT included in the returned list.

        Expected to FAIL until fix is implemented.
        """
        # Mock Azure response with stopped VM
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-stopped",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM stopped",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify only running VMs are returned
        assert len(result) == 1, "Should return only 1 running VM"
        assert result[0].name == "azlin-vm-running"
        assert result[0].is_running()
        assert "azlin-vm-stopped" not in [vm.name for vm in result]

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_include_stopped_returns_all_vms(self, mock_run):
        """Test that include_stopped=True returns all VMs regardless of power state.

        This test verifies that when include_stopped=True (default), all VMs
        are returned including stopped and deallocated ones.
        """
        # Mock Azure response with mixed power states
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-deallocated",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM deallocated",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
            {
                "name": "azlin-vm-stopped",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM stopped",
                "publicIps": None,
                "privateIps": "10.0.0.6",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=True (default)
        result = VMManager.list_vms("test-rg", include_stopped=True)

        # Verify all VMs are returned
        assert len(result) == 3, "Should return all 3 VMs"
        vm_names = [vm.name for vm in result]
        assert "azlin-vm-running" in vm_names
        assert "azlin-vm-deallocated" in vm_names
        assert "azlin-vm-stopped" in vm_names

    # =========================================================================
    # Test 2: VMs with "Unknown" power state are handled correctly
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_handles_unknown_power_state_with_exclude_stopped(self, mock_run):
        """Test that VMs with 'Unknown' power state are excluded when include_stopped=False.

        This test verifies that VMs with power state "Unknown" are treated as
        potentially stopped and excluded when include_stopped=False.

        Expected to FAIL until fix is implemented.
        """
        # Mock Azure response with Unknown power state
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-unknown",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "Unknown",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify only running VMs are returned (Unknown is excluded)
        assert len(result) == 1, "Should return only 1 VM with known running state"
        assert result[0].name == "azlin-vm-running"
        assert result[0].is_running()
        assert "azlin-vm-unknown" not in [vm.name for vm in result]

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_includes_unknown_power_state_with_include_stopped(self, mock_run):
        """Test that VMs with 'Unknown' power state are included when include_stopped=True.

        This test verifies that VMs with power state "Unknown" are included
        when include_stopped=True.
        """
        # Mock Azure response with Unknown power state
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-unknown",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "Unknown",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=True
        result = VMManager.list_vms("test-rg", include_stopped=True)

        # Verify all VMs are returned including Unknown
        assert len(result) == 2, "Should return both VMs"
        vm_names = [vm.name for vm in result]
        assert "azlin-vm-running" in vm_names
        assert "azlin-vm-unknown" in vm_names

    # =========================================================================
    # Test 3: azlin top finds running VMs
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_for_top_command_only_returns_running_vms(self, mock_run):
        """Test that 'azlin top' gets only running VMs from list_vms.

        This simulates the behavior expected by the 'azlin top' command which
        calls list_vms with include_stopped=False and expects only running VMs.

        Expected to FAIL until fix is implemented.
        """
        # Mock Azure response - simulate scenario for 'top' command
        vms_data = [
            {
                "name": "azlin-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM deallocated",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
            {
                "name": "azlin-vm-3",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.6",
                "privateIps": "10.0.0.6",
            },
            {
                "name": "azlin-vm-4",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "Unknown",
                "publicIps": None,
                "privateIps": "10.0.0.7",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Simulate what 'azlin top' does
        vms = VMManager.list_vms("test-rg", include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")
        running_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

        # Verify only running VMs with IPs are available for 'top'
        assert len(running_vms) == 2, "Should return 2 running VMs with public IPs"
        assert all(vm.is_running() for vm in running_vms)
        assert all(vm.public_ip is not None for vm in running_vms)
        vm_names = [vm.name for vm in running_vms]
        assert "azlin-vm-1" in vm_names
        assert "azlin-vm-3" in vm_names
        assert "azlin-vm-2" not in vm_names  # deallocated
        assert "azlin-vm-4" not in vm_names  # unknown

    # =========================================================================
    # Test 4: azlin w finds running VMs
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_for_w_command_only_returns_running_vms(self, mock_run):
        """Test that 'azlin w' gets only running VMs from list_vms.

        This simulates the behavior expected by the 'azlin w' command which
        calls list_vms with include_stopped=False and expects only running VMs.

        Expected to FAIL until fix is implemented.
        """
        # Mock Azure response - simulate scenario for 'w' command
        vms_data = [
            {
                "name": "azlin-vm-active",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-stopped",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM stopped",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
            {
                "name": "azlin-vm-active2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.6",
                "privateIps": "10.0.0.6",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Simulate what 'azlin w' does
        vms = VMManager.list_vms("test-rg", include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")
        running_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

        # Verify only running VMs with IPs are available for 'w'
        assert len(running_vms) == 2, "Should return 2 running VMs with public IPs"
        assert all(vm.is_running() for vm in running_vms)
        assert all(vm.public_ip is not None for vm in running_vms)
        vm_names = [vm.name for vm in running_vms]
        assert "azlin-vm-active" in vm_names
        assert "azlin-vm-active2" in vm_names
        assert "azlin-vm-stopped" not in vm_names

    # =========================================================================
    # Edge Cases and Boundary Tests
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_with_empty_result_and_exclude_stopped(self, mock_run):
        """Test that empty VM list is handled correctly with include_stopped=False."""
        # Mock empty Azure response
        vms_data = []

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify empty list is returned
        assert result == [], "Should return empty list"

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_with_all_stopped_vms_and_exclude_stopped(self, mock_run):
        """Test that all stopped VMs result in empty list when include_stopped=False."""
        # Mock Azure response with only stopped VMs
        vms_data = [
            {
                "name": "azlin-vm-stopped1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM stopped",
                "publicIps": None,
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-deallocated1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM deallocated",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify empty list is returned (all VMs are stopped)
        assert len(result) == 0, "Should return empty list when all VMs are stopped"

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_with_starting_vm_state(self, mock_run):
        """Test handling of VM in 'starting' state with include_stopped=False.

        VMs in transitional states like 'VM starting' should be treated carefully.
        This test verifies that 'VM starting' is NOT considered a running state
        and is filtered out when include_stopped=False.
        """
        # Mock Azure response with starting VM
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-starting",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM starting",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify only fully running VM is returned
        assert len(result) == 1, "Should return only the running VM"
        assert result[0].name == "azlin-vm-running"
        assert result[0].is_running()

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_vms_with_deallocating_vm_state(self, mock_run):
        """Test handling of VM in 'deallocating' state with include_stopped=False.

        VMs in transitional states like 'VM deallocating' should be excluded
        when include_stopped=False.
        """
        # Mock Azure response with deallocating VM
        vms_data = [
            {
                "name": "azlin-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
            },
            {
                "name": "azlin-vm-deallocating",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM deallocating",
                "publicIps": None,
                "privateIps": "10.0.0.5",
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call list_vms with include_stopped=False
        result = VMManager.list_vms("test-rg", include_stopped=False)

        # Verify only fully running VM is returned
        assert len(result) == 1, "Should return only the running VM"
        assert result[0].name == "azlin-vm-running"
        assert result[0].is_running()


class TestVMInfoPowerStateMethods:
    """Test VMInfo power state checking methods."""

    def test_is_running_with_running_state(self):
        """Test is_running() returns True for 'VM running' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
        )
        assert vm.is_running() is True

    def test_is_running_with_stopped_state(self):
        """Test is_running() returns False for 'VM stopped' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped",
        )
        assert vm.is_running() is False

    def test_is_running_with_unknown_state(self):
        """Test is_running() returns False for 'Unknown' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="Unknown",
        )
        assert vm.is_running() is False

    def test_is_stopped_with_stopped_state(self):
        """Test is_stopped() returns True for 'VM stopped' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped",
        )
        assert vm.is_stopped() is True

    def test_is_stopped_with_deallocated_state(self):
        """Test is_stopped() returns True for 'VM deallocated' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
        )
        assert vm.is_stopped() is True

    def test_is_stopped_with_running_state(self):
        """Test is_stopped() returns False for 'VM running' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
        )
        assert vm.is_stopped() is False

    def test_is_stopped_with_unknown_state(self):
        """Test is_stopped() returns False for 'Unknown' state."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="Unknown",
        )
        assert vm.is_stopped() is False
