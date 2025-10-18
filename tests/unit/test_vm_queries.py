"""Unit tests for vm_queries module."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from azlin.vm_queries import VMQueryError, VMQueryService


class TestVMQueryService:
    """Tests for VMQueryService class."""

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vms_success(self, mock_run):
        """Test successful VM listing."""
        mock_output = json.dumps(
            [
                {
                    "name": "azlin-test-1",
                    "resourceGroup": "test-rg",
                    "location": "eastus",
                    "powerState": "VM running",
                    "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                },
                {
                    "name": "azlin-test-2",
                    "resourceGroup": "test-rg",
                    "location": "westus",
                    "powerState": "VM stopped",
                    "hardwareProfile": {"vmSize": "Standard_B1s"},
                },
            ]
        )

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        vms = VMQueryService.list_vms("test-rg")

        assert len(vms) == 2
        assert vms[0]["name"] == "azlin-test-1"
        assert vms[1]["name"] == "azlin-test-2"
        assert mock_run.call_count == 1

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vms_resource_group_not_found(self, mock_run):
        """Test VM listing when resource group doesn't exist."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ResourceGroupNotFound"
        )

        vms = VMQueryService.list_vms("missing-rg")
        assert vms == []

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vms_timeout(self, mock_run):
        """Test VM listing timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(VMQueryError, match="VM list operation timed out"):
            VMQueryService.list_vms("test-rg")

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vms_invalid_json(self, mock_run):
        """Test VM listing with invalid JSON response."""
        mock_run.return_value = MagicMock(returncode=0, stdout="invalid json", stderr="")

        with pytest.raises(VMQueryError, match="Failed to parse VM list response"):
            VMQueryService.list_vms("test-rg")

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vm_names_success(self, mock_run):
        """Test successful VM name listing."""
        mock_output = json.dumps(["azlin-test-1", "azlin-test-2", "azlin-test-3"])

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        vm_names = VMQueryService.list_vm_names("test-rg")

        assert len(vm_names) == 3
        assert vm_names == ["azlin-test-1", "azlin-test-2", "azlin-test-3"]
        assert mock_run.call_count == 1

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vm_names_empty_resource_group(self, mock_run):
        """Test VM name listing with empty resource group."""
        mock_output = json.dumps([])

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        vm_names = VMQueryService.list_vm_names("empty-rg")
        assert vm_names == []

    @patch("azlin.vm_queries.subprocess.run")
    def test_list_vm_names_resource_group_not_found(self, mock_run):
        """Test VM name listing when resource group doesn't exist."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ResourceGroupNotFound"
        )

        vm_names = VMQueryService.list_vm_names("missing-rg")
        assert vm_names == []

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_vm_details_success(self, mock_run):
        """Test getting VM details."""
        mock_output = json.dumps(
            {
                "name": "azlin-test-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
                "networkProfile": {"networkInterfaces": [{"id": "/subscriptions/.../nic1"}]},
            }
        )

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        vm_details = VMQueryService.get_vm_details("azlin-test-1", "test-rg")

        assert vm_details is not None
        assert vm_details["name"] == "azlin-test-1"
        assert vm_details["hardwareProfile"]["vmSize"] == "Standard_D2s_v3"

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_vm_details_not_found(self, mock_run):
        """Test getting VM details for non-existent VM."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound")

        vm_details = VMQueryService.get_vm_details("missing-vm", "test-rg")
        assert vm_details is None

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_vm_details_timeout(self, mock_run):
        """Test VM details query timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(VMQueryError, match="VM details query timed out"):
            VMQueryService.get_vm_details("azlin-test-1", "test-rg")

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_vm_instance_view_success(self, mock_run):
        """Test getting VM instance view with power state."""
        mock_output = json.dumps(
            {
                "name": "azlin-test-1",
                "resourceGroup": "test-rg",
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "statuses": [
                    {
                        "code": "ProvisioningState/succeeded",
                        "displayStatus": "Provisioning succeeded",
                    },
                    {"code": "PowerState/running", "displayStatus": "VM running"},
                ],
            }
        )

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        instance_view = VMQueryService.get_vm_instance_view("azlin-test-1", "test-rg")

        assert instance_view is not None
        assert instance_view["name"] == "azlin-test-1"
        assert len(instance_view["statuses"]) == 2

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_vm_instance_view_not_found(self, mock_run):
        """Test getting instance view for non-existent VM."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound")

        instance_view = VMQueryService.get_vm_instance_view("missing-vm", "test-rg")
        assert instance_view is None

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_vm_instance_view_timeout(self, mock_run):
        """Test instance view query timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(VMQueryError, match="VM instance view query timed out"):
            VMQueryService.get_vm_instance_view("azlin-test-1", "test-rg")

    def test_get_power_state_running(self):
        """Test extracting running power state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/running", "displayStatus": "VM running"},
            ]
        }

        power_state = VMQueryService.get_power_state(vm_info)
        assert power_state == "VM running"

    def test_get_power_state_stopped(self):
        """Test extracting stopped power state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/stopped", "displayStatus": "VM stopped"},
            ]
        }

        power_state = VMQueryService.get_power_state(vm_info)
        assert power_state == "VM stopped"

    def test_get_power_state_deallocated(self):
        """Test extracting deallocated power state."""
        vm_info = {
            "statuses": [
                {"code": "ProvisioningState/succeeded"},
                {"code": "PowerState/deallocated", "displayStatus": "VM deallocated"},
            ]
        }

        power_state = VMQueryService.get_power_state(vm_info)
        assert power_state == "VM deallocated"

    def test_get_power_state_no_statuses(self):
        """Test extracting power state with no statuses."""
        vm_info = {"statuses": []}

        power_state = VMQueryService.get_power_state(vm_info)
        assert power_state == "Unknown"

    def test_get_power_state_missing_statuses(self):
        """Test extracting power state with missing statuses field."""
        vm_info = {}

        power_state = VMQueryService.get_power_state(vm_info)
        assert power_state == "Unknown"

    def test_get_power_state_no_power_state_code(self):
        """Test extracting power state when PowerState code is missing."""
        vm_info = {"statuses": [{"code": "ProvisioningState/succeeded"}]}

        power_state = VMQueryService.get_power_state(vm_info)
        assert power_state == "Unknown"

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_all_public_ips_success(self, mock_run):
        """Test getting all public IPs in resource group."""
        mock_output = json.dumps(
            [
                {"name": "azlin-test-1PublicIP", "ip": "1.2.3.4"},
                {"name": "azlin-test-2PublicIP", "ip": "5.6.7.8"},
                {"name": "azlin-test-3PublicIP", "ip": None},  # No IP assigned yet
            ]
        )

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        public_ips = VMQueryService.get_all_public_ips("test-rg")

        assert len(public_ips) == 2  # Should exclude None IP
        assert public_ips["azlin-test-1PublicIP"] == "1.2.3.4"
        assert public_ips["azlin-test-2PublicIP"] == "5.6.7.8"
        assert "azlin-test-3PublicIP" not in public_ips

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_all_public_ips_empty(self, mock_run):
        """Test getting public IPs when none exist."""
        mock_output = json.dumps([])

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        public_ips = VMQueryService.get_all_public_ips("test-rg")
        assert public_ips == {}

    @patch("azlin.vm_queries.subprocess.run")
    def test_get_all_public_ips_failure(self, mock_run):
        """Test handling failure when getting public IPs."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Error")

        public_ips = VMQueryService.get_all_public_ips("test-rg")
        assert public_ips == {}  # Should return empty dict on failure, not raise
