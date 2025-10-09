"""Unit tests for vm_manager module."""

import pytest
import json
from unittest.mock import patch, MagicMock
from azlin.vm_manager import VMManager, VMInfo, VMManagerError


class TestVMInfo:
    """Tests for VMInfo dataclass."""

    def test_is_running(self):
        """Test is_running check."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running"
        )
        assert vm.is_running() is True

    def test_is_stopped(self):
        """Test is_stopped check."""
        vm1 = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped"
        )
        assert vm1.is_stopped() is True

        vm2 = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated"
        )
        assert vm2.is_stopped() is True

    def test_get_status_display(self):
        """Test status display formatting."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running"
        )
        assert vm.get_status_display() == "Running"

        vm2 = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped"
        )
        assert vm2.get_status_display() == "Stopped"


class TestVMManager:
    """Tests for VMManager class."""

    @patch('azlin.vm_manager.subprocess.run')
    def test_list_vms_success(self, mock_run):
        """Test successful VM listing."""
        mock_output = json.dumps([
            {
                "name": "azlin-test-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "powerState": "VM running",
                "publicIps": "1.2.3.4",
                "privateIps": "10.0.0.4",
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
                "provisioningState": "Succeeded"
            }
        ])

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )

        vms = VMManager.list_vms("test-rg")

        assert len(vms) == 1
        assert vms[0].name == "azlin-test-1"
        assert vms[0].public_ip == "1.2.3.4"
        assert vms[0].power_state == "VM running"

    @patch('azlin.vm_manager.subprocess.run')
    def test_list_vms_resource_group_not_found(self, mock_run):
        """Test VM listing when resource group doesn't exist."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ResourceGroupNotFound"
        )

        vms = VMManager.list_vms("missing-rg")
        assert vms == []

    @patch('azlin.vm_manager.subprocess.run')
    def test_get_vm_success(self, mock_run):
        """Test getting specific VM."""
        mock_output = json.dumps({
            "name": "azlin-test-1",
            "resourceGroup": "test-rg",
            "location": "eastus",
            "powerState": "VM running",
            "publicIps": "1.2.3.4"
        })

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )

        vm = VMManager.get_vm("azlin-test-1", "test-rg")

        assert vm is not None
        assert vm.name == "azlin-test-1"
        assert vm.public_ip == "1.2.3.4"

    @patch('azlin.vm_manager.subprocess.run')
    def test_get_vm_not_found(self, mock_run):
        """Test getting VM that doesn't exist."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ResourceNotFound"
        )

        vm = VMManager.get_vm("missing-vm", "test-rg")
        assert vm is None

    def test_filter_by_prefix(self):
        """Test filtering VMs by name prefix."""
        vms = [
            VMInfo("azlin-vm-1", "rg", "eastus", "VM running"),
            VMInfo("azlin-vm-2", "rg", "eastus", "VM running"),
            VMInfo("other-vm", "rg", "eastus", "VM running"),
        ]

        filtered = VMManager.filter_by_prefix(vms, "azlin")
        assert len(filtered) == 2
        assert all(vm.name.startswith("azlin") for vm in filtered)

    def test_sort_by_created_time(self):
        """Test sorting VMs by creation time."""
        vms = [
            VMInfo("vm-1", "rg", "eastus", "VM running", created_time="2024-10-01T10:00:00Z"),
            VMInfo("vm-2", "rg", "eastus", "VM running", created_time="2024-10-02T10:00:00Z"),
            VMInfo("vm-3", "rg", "eastus", "VM running", created_time="2024-10-01T12:00:00Z"),
        ]

        sorted_vms = VMManager.sort_by_created_time(vms, reverse=True)
        assert sorted_vms[0].name == "vm-2"  # Newest first
        assert sorted_vms[2].name == "vm-1"  # Oldest last

    @patch('azlin.vm_manager.subprocess.run')
    def test_list_resource_groups(self, mock_run):
        """Test listing resource groups."""
        mock_output = json.dumps(["rg-1", "rg-2", "rg-3"])

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )

        groups = VMManager.list_resource_groups()
        assert len(groups) == 3
        assert "rg-1" in groups

    @patch('azlin.vm_manager.subprocess.run')
    def test_get_vm_ip(self, mock_run):
        """Test getting VM public IP."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1.2.3.4\n",
            stderr=""
        )

        ip = VMManager.get_vm_ip("test-vm", "test-rg")
        assert ip == "1.2.3.4"

    @patch('azlin.vm_manager.subprocess.run')
    def test_get_vm_ip_not_found(self, mock_run):
        """Test getting IP for non-existent VM."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ResourceNotFound"
        )

        ip = VMManager.get_vm_ip("missing-vm", "test-rg")
        assert ip is None
