"""TDD tests for NSG deletion feature in VM lifecycle.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)

This test suite follows the architect's specification for NSG deletion:
1. _get_nsg_from_nic(nic_name, resource_group) - discovers NSG from NIC
2. _delete_nsg(nsg_name, resource_group) - deletes NSG
3. _collect_vm_resources() - now includes NSGs in resource list
4. delete_vm() deletion loop - handles NSG resource type

These tests will FAIL until implementation is complete (TDD approach).
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.vm_lifecycle import VMLifecycleManager

# ============================================================================
# UNIT TESTS (60%) - Fast, heavily mocked
# ============================================================================


class TestNSGDiscovery:
    """Unit tests for NSG discovery from NIC."""

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_success(self, mock_run: Mock) -> None:
        """Test successful NSG discovery from NIC."""
        # Mock Azure CLI response with NSG attached
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"networkSecurityGroup": {"id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Network/networkSecurityGroups/test-nsg"}}',
            stderr="",
        )

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # Verify NSG name extracted correctly
        assert nsg_name == "test-nsg"

        # Verify correct Azure CLI command
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0:3] == ["az", "network", "nic"]
        assert "show" in call_args
        assert "--name" in call_args
        assert "test-nic" in call_args
        assert "--resource-group" in call_args
        assert "test-rg" in call_args

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_no_nsg_attached(self, mock_run: Mock) -> None:
        """Test NSG discovery when no NSG is attached to NIC."""
        # Mock Azure CLI response with no NSG
        mock_run.return_value = Mock(
            returncode=0, stdout='{"networkSecurityGroup": null}', stderr=""
        )

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # No NSG attached should return None
        assert nsg_name is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_empty_response(self, mock_run: Mock) -> None:
        """Test NSG discovery with empty networkSecurityGroup field."""
        # Mock Azure CLI response with empty NSG field
        mock_run.return_value = Mock(returncode=0, stdout="{}", stderr="")

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # Empty response should return None
        assert nsg_name is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_timeout(self, mock_run: Mock) -> None:
        """Test NSG discovery handles timeout gracefully."""
        # Mock timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=10)

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # Timeout should return None (graceful degradation)
        assert nsg_name is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_azure_cli_error(self, mock_run: Mock) -> None:
        """Test NSG discovery handles Azure CLI errors gracefully."""
        # Mock Azure CLI error (e.g., NIC not found)
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=3, cmd="az", stderr="ResourceNotFound"
        )

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # Errors should return None (graceful degradation)
        assert nsg_name is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_parse_error(self, mock_run: Mock) -> None:
        """Test NSG discovery handles JSON parse errors gracefully."""
        # Mock invalid JSON response
        mock_run.return_value = Mock(returncode=0, stdout="invalid json", stderr="")

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # Parse errors should return None (graceful degradation)
        assert nsg_name is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_nsg_from_nic_malformed_id(self, mock_run: Mock) -> None:
        """Test NSG discovery handles malformed NSG IDs gracefully."""
        # Mock response with malformed NSG ID (no slashes)
        mock_run.return_value = Mock(
            returncode=0, stdout='{"networkSecurityGroup": {"id": "malformed-id"}}', stderr=""
        )

        nsg_name = VMLifecycleManager._get_nsg_from_nic("test-nic", "test-rg")

        # Malformed ID should still extract last part
        assert nsg_name == "malformed-id"


class TestNSGDeletion:
    """Unit tests for NSG deletion."""

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_nsg_success(self, mock_run: Mock) -> None:
        """Test successful NSG deletion."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Should not raise exception
        VMLifecycleManager._delete_nsg("test-nsg", "test-rg")

        # Verify correct Azure CLI command
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "az",
            "network",
            "nsg",
            "delete",
            "--name",
            "test-nsg",
            "--resource-group",
            "test-rg",
        ]

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_nsg_timeout(self, mock_run: Mock) -> None:
        """Test NSG deletion timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=60)

        # Should raise exception for timeout
        with pytest.raises(subprocess.TimeoutExpired):
            VMLifecycleManager._delete_nsg("test-nsg", "test-rg")

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_nsg_azure_cli_error(self, mock_run: Mock) -> None:
        """Test NSG deletion Azure CLI error handling."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=3, cmd="az", stderr="NSGNotFound"
        )

        # Should raise exception for CLI errors
        with pytest.raises(subprocess.CalledProcessError):
            VMLifecycleManager._delete_nsg("test-nsg", "test-rg")


class TestResourceCollection:
    """Unit tests for resource collection including NSGs."""

    @patch.object(VMLifecycleManager, "_get_public_ip_from_nic")
    @patch.object(VMLifecycleManager, "_get_nsg_from_nic")
    def test_collect_vm_resources_includes_nsg(
        self, mock_get_nsg: Mock, mock_get_public_ip: Mock
    ) -> None:
        """Test that resource collection includes NSGs."""
        # Mock NSG discovery
        mock_get_nsg.return_value = "test-nsg"
        mock_get_public_ip.return_value = "test-public-ip"

        # Mock VM info with one NIC
        vm_info = {
            "resourceGroup": "test-rg",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {"osDisk": {"name": "test-os-disk"}, "dataDisks": []},
        }

        resources = VMLifecycleManager._collect_vm_resources(vm_info)

        # Verify NSG is in the resource list
        assert ("nsg", "test-nsg") in resources
        # Verify NIC and public IP also present
        assert ("nic", "test-nic") in resources
        assert ("public-ip", "test-public-ip") in resources
        # Verify _get_nsg_from_nic was called
        mock_get_nsg.assert_called_once_with("test-nic", "test-rg")

    @patch.object(VMLifecycleManager, "_get_public_ip_from_nic")
    @patch.object(VMLifecycleManager, "_get_nsg_from_nic")
    def test_collect_vm_resources_no_nsg_attached(
        self, mock_get_nsg: Mock, mock_get_public_ip: Mock
    ) -> None:
        """Test resource collection when no NSG is attached."""
        # Mock no NSG attached
        mock_get_nsg.return_value = None
        mock_get_public_ip.return_value = None

        vm_info = {
            "resourceGroup": "test-rg",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {"osDisk": {"name": "test-os-disk"}, "dataDisks": []},
        }

        resources = VMLifecycleManager._collect_vm_resources(vm_info)

        # Verify no NSG in resource list
        assert not any(r[0] == "nsg" for r in resources)
        # Verify NIC is still present
        assert ("nic", "test-nic") in resources

    @patch.object(VMLifecycleManager, "_get_public_ip_from_nic")
    @patch.object(VMLifecycleManager, "_get_nsg_from_nic")
    def test_collect_vm_resources_nsg_lookup_fails(
        self, mock_get_nsg: Mock, mock_get_public_ip: Mock
    ) -> None:
        """Test resource collection handles NSG lookup failures gracefully."""
        # Mock NSG lookup failure (returns None)
        mock_get_nsg.side_effect = Exception("Lookup failed")
        mock_get_public_ip.return_value = None

        vm_info = {
            "resourceGroup": "test-rg",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {"osDisk": {"name": "test-os-disk"}, "dataDisks": []},
        }

        # Should not raise exception - graceful degradation
        resources = VMLifecycleManager._collect_vm_resources(vm_info)

        # Verify NIC is still collected despite NSG lookup failure
        assert ("nic", "test-nic") in resources


# ============================================================================
# INTEGRATION TESTS (30%) - Multiple components
# ============================================================================


class TestVMDeletionWithNSG:
    """Integration tests for VM deletion with NSG cleanup."""

    @patch.object(VMLifecycleManager, "_delete_nsg")
    @patch.object(VMLifecycleManager, "_delete_disk")
    @patch.object(VMLifecycleManager, "_delete_public_ip")
    @patch.object(VMLifecycleManager, "_delete_nic")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_collect_vm_resources")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    @patch("azlin.vm_lifecycle.ConnectionTracker.remove_connection")
    @patch("azlin.vm_lifecycle.ConfigManager.delete_session_name")
    def test_delete_vm_calls_nsg_deletion(
        self,
        mock_delete_session: Mock,
        mock_remove_connection: Mock,
        mock_get_vm_details: Mock,
        mock_collect_resources: Mock,
        mock_delete_vm: Mock,
        mock_delete_nic: Mock,
        mock_delete_public_ip: Mock,
        mock_delete_disk: Mock,
        mock_delete_nsg: Mock,
    ) -> None:
        """Test that VM deletion calls NSG deletion method."""
        # Mock VM details
        mock_get_vm_details.return_value = {"name": "test-vm", "resourceGroup": "test-rg"}

        # Mock resources including NSG
        mock_collect_resources.return_value = [
            ("nic", "test-nic"),
            ("nsg", "test-nsg"),
            ("public-ip", "test-ip"),
        ]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Verify NSG deletion was called
        mock_delete_nsg.assert_called_once_with("test-nsg", "test-rg")

        # Verify other deletions also called
        mock_delete_nic.assert_called_once()
        mock_delete_public_ip.assert_called_once()

        # Verify result is successful
        assert result.success is True
        assert "NSG: test-nsg" in result.resources_deleted

    @patch.object(VMLifecycleManager, "_delete_nsg")
    @patch.object(VMLifecycleManager, "_delete_nic")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_collect_vm_resources")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    @patch("azlin.vm_lifecycle.ConnectionTracker.remove_connection")
    @patch("azlin.vm_lifecycle.ConfigManager.delete_session_name")
    def test_delete_vm_continues_on_nsg_deletion_failure(
        self,
        mock_delete_session: Mock,
        mock_remove_connection: Mock,
        mock_get_vm_details: Mock,
        mock_collect_resources: Mock,
        mock_delete_vm: Mock,
        mock_delete_nic: Mock,
        mock_delete_nsg: Mock,
    ) -> None:
        """Test that VM deletion continues if NSG deletion fails."""
        # Mock VM details
        mock_get_vm_details.return_value = {"name": "test-vm", "resourceGroup": "test-rg"}

        # Mock resources including NSG
        mock_collect_resources.return_value = [("nsg", "test-nsg"), ("nic", "test-nic")]

        # Mock NSG deletion failure
        mock_delete_nsg.side_effect = Exception("NSG deletion failed")

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Verify NSG deletion was attempted
        mock_delete_nsg.assert_called_once()

        # Verify NIC deletion still proceeded
        mock_delete_nic.assert_called_once()

        # Verify overall result is still successful
        assert result.success is True

    @patch.object(VMLifecycleManager, "_delete_nsg")
    @patch.object(VMLifecycleManager, "_delete_nic")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_collect_vm_resources")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    @patch("azlin.vm_lifecycle.ConnectionTracker.remove_connection")
    @patch("azlin.vm_lifecycle.ConfigManager.delete_session_name")
    def test_delete_vm_no_nsg_to_delete(
        self,
        mock_delete_session: Mock,
        mock_remove_connection: Mock,
        mock_get_vm_details: Mock,
        mock_collect_resources: Mock,
        mock_delete_vm: Mock,
        mock_delete_nic: Mock,
        mock_delete_nsg: Mock,
    ) -> None:
        """Test VM deletion when no NSG is present."""
        # Mock VM details
        mock_get_vm_details.return_value = {"name": "test-vm", "resourceGroup": "test-rg"}

        # Mock resources WITHOUT NSG
        mock_collect_resources.return_value = [("nic", "test-nic")]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Verify NSG deletion was NOT called
        mock_delete_nsg.assert_not_called()

        # Verify NIC deletion was called
        mock_delete_nic.assert_called_once()

        # Verify result is successful
        assert result.success is True


# ============================================================================
# E2E TESTS (10%) - Complete workflows (if needed)
# ============================================================================


class TestNSGDeletionE2E:
    """End-to-end tests for NSG deletion feature (minimal, high-value only)."""

    @patch("azlin.vm_lifecycle.subprocess.run")
    @patch("azlin.vm_lifecycle.ConnectionTracker.remove_connection")
    @patch("azlin.vm_lifecycle.ConfigManager.delete_session_name")
    def test_complete_vm_deletion_with_nsg(
        self, mock_delete_session: Mock, mock_remove_connection: Mock, mock_subprocess: Mock
    ) -> None:
        """Test complete VM deletion workflow including NSG discovery and deletion."""
        # Mock sequence of subprocess calls for:
        # 1. Get VM details
        # 2. Get NSG from NIC
        # 3. Delete VM
        # 4. Delete NSG
        # 5. Delete NIC

        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]

            # VM show command
            if "vm" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "name": "test-vm",
                            "resourceGroup": "test-rg",
                            "networkProfile": {
                                "networkInterfaces": [
                                    {
                                        "id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                                    }
                                ]
                            },
                            "storageProfile": {"osDisk": {"name": "test-disk"}, "dataDisks": []},
                        }
                    ),
                    stderr="",
                )

            # NIC show command (for NSG)
            if "nic" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "networkSecurityGroup": {
                                "id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Network/networkSecurityGroups/test-nsg"
                            }
                        }
                    ),
                    stderr="",
                )

            # All delete commands
            if "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")

            return Mock(returncode=0, stdout="", stderr="")

        mock_subprocess.side_effect = subprocess_side_effect

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Verify successful deletion
        assert result.success is True

        # Verify NSG was discovered and deleted
        delete_calls = [call for call in mock_subprocess.call_args_list if "delete" in call[0][0]]

        # Should have delete calls for: VM, NSG, NIC
        assert len(delete_calls) >= 3

        # Verify NSG delete was called
        nsg_delete_calls = [
            call for call in delete_calls if "nsg" in call[0][0] and "delete" in call[0][0]
        ]
        assert len(nsg_delete_calls) == 1
