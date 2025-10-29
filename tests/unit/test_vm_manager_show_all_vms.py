"""Unit tests for --show-all-vms feature - Issue #208.

These tests verify the new functionality for showing all VMs (managed + unmanaged)
when the --show-all-vms flag is used with azlin list command.

TDD approach: These tests will FAIL until the feature is implemented.

Test Coverage:
- VMManager.list_all_user_vms() function (NEW)
- Detection and counting of unmanaged VMs
- Separation of managed vs unmanaged VMs
- Edge cases: no VMs, all managed, all unmanaged
"""

import json
from unittest.mock import Mock, patch

from azlin.vm_manager import VMInfo, VMManager


class TestListAllUserVMs:
    """Test VMManager.list_all_user_vms() - Issue #208."""

    # =========================================================================
    # Test 1: list_all_user_vms returns both managed and unmanaged VMs
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_returns_both_managed_and_unmanaged(self, mock_run):
        """Test that list_all_user_vms returns both managed and unmanaged VMs.

        This is the core functionality: when listing all user VMs, we should
        get both azlin-managed VMs and user-created VMs without azlin tags.

        Expected to FAIL until implementation is complete.
        """
        # Mock Azure response with mixed managed/unmanaged VMs
        vms_data = [
            {
                "name": "azlin-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {"managed-by": "azlin", "azlin-session": "dev"},
            },
            {
                "name": "user-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {},  # No azlin tags - unmanaged
            },
            {
                "name": "azlin-vm-2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM stopped",
                "publicIps": None,
                "privateIps": "10.0.0.6",
                "tags": {"managed-by": "azlin"},
            },
            {
                "name": "user-vm-2",
                "resourceGroup": "test-rg",
                "location": "westus",
                "powerState": "VM deallocated",
                "publicIps": None,
                "privateIps": "10.0.0.7",
                "tags": {"environment": "prod"},  # Has tags but not azlin-managed
            },
        ]

        # Mock VM list with show-details
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),  # Public IPs
        ]

        # Call the new function
        result = VMManager.list_all_user_vms("test-rg", include_stopped=True)

        # Verify all VMs are returned
        assert len(result) == 4, "Should return all 4 VMs (managed + unmanaged)"
        vm_names = [vm.name for vm in result]
        assert "azlin-vm-1" in vm_names
        assert "user-vm-1" in vm_names
        assert "azlin-vm-2" in vm_names
        assert "user-vm-2" in vm_names

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_excludes_stopped_when_include_stopped_false(self, mock_run):
        """Test that list_all_user_vms respects include_stopped=False for all VMs.

        When include_stopped=False, both managed and unmanaged stopped VMs
        should be excluded.

        Expected to FAIL until implementation is complete.
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
                "tags": {"managed-by": "azlin"},
            },
            {
                "name": "user-vm-running",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {},
            },
            {
                "name": "azlin-vm-stopped",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM deallocated",
                "publicIps": None,
                "privateIps": "10.0.0.6",
                "tags": {"managed-by": "azlin"},
            },
            {
                "name": "user-vm-stopped",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM stopped",
                "publicIps": None,
                "privateIps": "10.0.0.7",
                "tags": {},
            },
        ]

        # Mock VM list
        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        # Call with include_stopped=False
        result = VMManager.list_all_user_vms("test-rg", include_stopped=False)

        # Verify only running VMs are returned (both managed and unmanaged)
        assert len(result) == 2, "Should return only 2 running VMs"
        assert all(vm.is_running() for vm in result)
        vm_names = [vm.name for vm in result]
        assert "azlin-vm-running" in vm_names
        assert "user-vm-running" in vm_names
        assert "azlin-vm-stopped" not in vm_names
        assert "user-vm-stopped" not in vm_names

    # =========================================================================
    # Test 2: Separate managed vs unmanaged VMs
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_can_identify_managed_vms(self, mock_run):
        """Test that managed VMs can be identified by tags.

        VMs with 'managed-by: azlin' tag should be identifiable as managed.

        Expected to FAIL until implementation is complete.
        """
        # Mock Azure response
        vms_data = [
            {
                "name": "azlin-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {"managed-by": "azlin"},
            },
            {
                "name": "user-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {},
            },
        ]

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        result = VMManager.list_all_user_vms("test-rg")

        # Check tags are preserved so we can identify managed VMs
        managed_vms = [vm for vm in result if vm.tags and vm.tags.get("managed-by") == "azlin"]
        unmanaged_vms = [
            vm for vm in result if not vm.tags or vm.tags.get("managed-by") != "azlin"
        ]

        assert len(managed_vms) == 1
        assert managed_vms[0].name == "azlin-vm-1"
        assert len(unmanaged_vms) == 1
        assert unmanaged_vms[0].name == "user-vm-1"

    # =========================================================================
    # Test 3: Count unmanaged VMs
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_count_unmanaged_vms_returns_correct_count(self, mock_run):
        """Test counting unmanaged VMs separately from managed VMs.

        This is needed for the notification message that says:
        "N additional vms not currently managed by azlin detected."

        Expected to FAIL until implementation is complete.
        """
        # Mock Azure response
        vms_data = [
            {
                "name": "azlin-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {"managed-by": "azlin"},
            },
            {
                "name": "user-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {},
            },
            {
                "name": "user-vm-2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.6",
                "privateIps": "10.0.0.6",
                "tags": {"environment": "dev"},
            },
            {
                "name": "user-vm-3",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.7",
                "privateIps": "10.0.0.7",
                "tags": None,  # No tags at all
            },
        ]

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        all_vms = VMManager.list_all_user_vms("test-rg")

        # Count unmanaged VMs
        unmanaged_count = len(
            [vm for vm in all_vms if not vm.tags or vm.tags.get("managed-by") != "azlin"]
        )

        assert unmanaged_count == 3, "Should count 3 unmanaged VMs"

    # =========================================================================
    # Test 4: Edge cases
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_with_no_vms(self, mock_run):
        """Test list_all_user_vms with empty result.

        Expected to FAIL until implementation is complete.
        """
        # Mock empty response
        vms_data = []

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        result = VMManager.list_all_user_vms("test-rg")

        assert result == [], "Should return empty list when no VMs exist"

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_with_all_managed_vms(self, mock_run):
        """Test list_all_user_vms when all VMs are azlin-managed.

        Expected to FAIL until implementation is complete.
        """
        # Mock response with only managed VMs
        vms_data = [
            {
                "name": "azlin-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {"managed-by": "azlin"},
            },
            {
                "name": "azlin-vm-2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {"managed-by": "azlin"},
            },
        ]

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        all_vms = VMManager.list_all_user_vms("test-rg")
        unmanaged_count = len(
            [vm for vm in all_vms if not vm.tags or vm.tags.get("managed-by") != "azlin"]
        )

        assert len(all_vms) == 2
        assert unmanaged_count == 0, "Should have 0 unmanaged VMs"

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_with_all_unmanaged_vms(self, mock_run):
        """Test list_all_user_vms when all VMs are unmanaged.

        Expected to FAIL until implementation is complete.
        """
        # Mock response with only unmanaged VMs
        vms_data = [
            {
                "name": "user-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {},
            },
            {
                "name": "user-vm-2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {"owner": "user"},
            },
        ]

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        all_vms = VMManager.list_all_user_vms("test-rg")
        unmanaged_count = len(
            [vm for vm in all_vms if not vm.tags or vm.tags.get("managed-by") != "azlin"]
        )

        assert len(all_vms) == 2
        assert unmanaged_count == 2, "Should have 2 unmanaged VMs"

    # =========================================================================
    # Test 5: VMs with various tag scenarios
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_with_various_tag_scenarios(self, mock_run):
        """Test identification of managed/unmanaged with various tag scenarios.

        Expected to FAIL until implementation is complete.
        """
        # Mock response with various tag scenarios
        vms_data = [
            {
                "name": "vm-with-managed-by-azlin",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {"managed-by": "azlin", "env": "dev"},
            },
            {
                "name": "vm-with-no-tags",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.5",
                "privateIps": "10.0.0.5",
                "tags": {},
            },
            {
                "name": "vm-with-other-tags",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.6",
                "privateIps": "10.0.0.6",
                "tags": {"owner": "user", "project": "test"},
            },
            {
                "name": "vm-with-managed-by-other",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.7",
                "privateIps": "10.0.0.7",
                "tags": {"managed-by": "terraform"},  # Managed by something else
            },
            {
                "name": "vm-with-null-tags",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.8",
                "privateIps": "10.0.0.8",
                "tags": None,
            },
        ]

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        all_vms = VMManager.list_all_user_vms("test-rg")

        # Count managed vs unmanaged
        managed_vms = [vm for vm in all_vms if vm.tags and vm.tags.get("managed-by") == "azlin"]
        unmanaged_vms = [
            vm for vm in all_vms if not vm.tags or vm.tags.get("managed-by") != "azlin"
        ]

        assert len(managed_vms) == 1, "Only 1 VM has managed-by=azlin"
        assert managed_vms[0].name == "vm-with-managed-by-azlin"
        assert len(unmanaged_vms) == 4, "4 VMs are not managed by azlin"

        # Verify specific VMs are in unmanaged
        unmanaged_names = [vm.name for vm in unmanaged_vms]
        assert "vm-with-no-tags" in unmanaged_names
        assert "vm-with-other-tags" in unmanaged_names
        assert "vm-with-managed-by-other" in unmanaged_names
        assert "vm-with-null-tags" in unmanaged_names

    # =========================================================================
    # Test 6: Function should behave like list_vms but without filtering
    # =========================================================================

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_uses_same_azure_cli_as_list_vms(self, mock_run):
        """Test that list_all_user_vms uses same Azure CLI call structure as list_vms.

        This ensures consistency and that the function properly integrates with
        existing infrastructure.

        Expected to FAIL until implementation is complete.
        """
        # Mock response
        vms_data = [
            {
                "name": "test-vm",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "tags": {},
            }
        ]

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vms_data), stderr=""),
            Mock(returncode=0, stdout=json.dumps([]), stderr=""),
        ]

        result = VMManager.list_all_user_vms("test-rg")

        # Verify Azure CLI was called correctly
        assert mock_run.call_count == 2
        first_call = mock_run.call_args_list[0]
        cmd = first_call[0][0]

        # Should use same command structure as list_vms
        assert cmd[0] == "az"
        assert cmd[1] == "vm"
        assert cmd[2] == "list"
        assert "--resource-group" in cmd
        assert "test-rg" in cmd
        assert "--show-details" in cmd
        assert len(result) == 1

    @patch("azlin.vm_manager.subprocess.run")
    def test_list_all_user_vms_handles_resource_group_not_found(self, mock_run):
        """Test that list_all_user_vms handles non-existent resource group gracefully.

        Expected to FAIL until implementation is complete.
        """
        # Mock ResourceGroupNotFound error
        mock_run.side_effect = [
            Mock(
                returncode=1,
                stdout="",
                stderr="(ResourceGroupNotFound) Resource group 'nonexistent' could not be found.",
            )
        ]

        # Should return empty list like list_vms does
        result = VMManager.list_all_user_vms("nonexistent")
        assert result == [], "Should return empty list for non-existent resource group"


class TestVMInfoIsManaged:
    """Test VMInfo.is_managed() helper method - Issue #208."""

    def test_vm_is_managed_with_managed_by_azlin_tag(self):
        """Test that VM with managed-by=azlin tag is identified as managed.

        Expected to FAIL until implementation is complete.
        """
        vm = VMInfo(
            name="azlin-vm-1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            tags={"managed-by": "azlin"},
        )

        # Assuming we add an is_managed() method to VMInfo
        assert vm.is_managed() is True

    def test_vm_is_not_managed_without_tags(self):
        """Test that VM without tags is not identified as managed.

        Expected to FAIL until implementation is complete.
        """
        vm = VMInfo(
            name="user-vm-1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            tags={},
        )

        assert vm.is_managed() is False

    def test_vm_is_not_managed_with_other_managed_by_value(self):
        """Test that VM with managed-by != azlin is not identified as managed.

        Expected to FAIL until implementation is complete.
        """
        vm = VMInfo(
            name="terraform-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            tags={"managed-by": "terraform"},
        )

        assert vm.is_managed() is False

    def test_vm_is_not_managed_with_null_tags(self):
        """Test that VM with None tags is not identified as managed.

        Expected to FAIL until implementation is complete.
        """
        vm = VMInfo(
            name="user-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            tags=None,
        )

        assert vm.is_managed() is False
