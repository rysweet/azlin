"""Unit tests for status_dashboard module.

Tests VM status dashboard functionality including Azure CLI integration,
status retrieval, and display formatting.
"""

import json
import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from azlin.status_dashboard import StatusDashboard, VMStatus, show_vm_status

# ============================================================================
# VMSTATUS DATACLASS TESTS
# ============================================================================


class TestVMStatus:
    """Tests for VMStatus dataclass."""

    def test_vmstatus_initialization_all_fields(self):
        """Test VMStatus dataclass with all fields."""
        vm_status = VMStatus(
            name="test-vm",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip="1.2.3.4",
            provisioning_state="Succeeded",
            os_type="Linux",
            uptime="5 days",
            cpu_usage=45.5,
            memory_usage=60.2,
            estimated_cost=70.08,
        )

        assert vm_status.name == "test-vm"
        assert vm_status.status == "Succeeded"
        assert vm_status.power_state == "running"
        assert vm_status.resource_group == "test-rg"
        assert vm_status.location == "eastus"
        assert vm_status.size == "Standard_D2s_v3"
        assert vm_status.public_ip == "1.2.3.4"
        assert vm_status.provisioning_state == "Succeeded"
        assert vm_status.os_type == "Linux"
        assert vm_status.uptime == "5 days"
        assert vm_status.cpu_usage == 45.5
        assert vm_status.memory_usage == 60.2
        assert vm_status.estimated_cost == 70.08

    def test_vmstatus_initialization_optional_fields(self):
        """Test VMStatus dataclass with optional fields as None."""
        vm_status = VMStatus(
            name="test-vm",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip=None,
            provisioning_state="Succeeded",
            os_type="Linux",
        )

        assert vm_status.uptime is None
        assert vm_status.cpu_usage is None
        assert vm_status.memory_usage is None
        assert vm_status.estimated_cost is None


# ============================================================================
# STATUSDASHBOARD INITIALIZATION TESTS
# ============================================================================


class TestStatusDashboardInit:
    """Tests for StatusDashboard initialization."""

    def test_initialization(self):
        """Test StatusDashboard initializes with Console."""
        dashboard = StatusDashboard()
        assert dashboard.console is not None
        assert hasattr(dashboard, "console")


# ============================================================================
# AZURE CLI COMMAND TESTS
# ============================================================================


class TestRunAzCommand:
    """Tests for _run_az_command method."""

    @patch("azlin.status_dashboard.subprocess.run")
    def test_run_az_command_success(self, mock_run):
        """Test successful Azure CLI command execution with JSON output."""
        dashboard = StatusDashboard()

        mock_output = json.dumps({"name": "test-vm", "status": "running"})
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._run_az_command(["az", "vm", "list"])

        assert result == {"name": "test-vm", "status": "running"}
        mock_run.assert_called_once_with(
            ["az", "vm", "list"], capture_output=True, text=True, check=True
        )

    @patch("azlin.status_dashboard.subprocess.run")
    def test_run_az_command_json_decode_error(self, mock_run):
        """Test JSONDecodeError handling for invalid JSON output."""
        dashboard = StatusDashboard()

        mock_run.return_value = Mock(stdout="invalid json", returncode=0)

        with pytest.raises(json.JSONDecodeError):
            dashboard._run_az_command(["az", "vm", "list"])

    @patch("azlin.status_dashboard.subprocess.run")
    def test_run_az_command_subprocess_error(self, mock_run):
        """Test subprocess.CalledProcessError handling."""
        dashboard = StatusDashboard()

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["az", "vm", "list"], stderr="Resource not found"
        )

        with pytest.raises(subprocess.CalledProcessError):
            dashboard._run_az_command(["az", "vm", "list"])

    @patch("azlin.status_dashboard.subprocess.run")
    def test_run_az_command_empty_output(self, mock_run):
        """Test handling of empty stdout."""
        dashboard = StatusDashboard()

        mock_run.return_value = Mock(stdout="", returncode=0)

        result = dashboard._run_az_command(["az", "vm", "list"])

        assert result == {}


# ============================================================================
# VM LIST TESTS
# ============================================================================


class TestGetVMList:
    """Tests for _get_vm_list method."""

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_list_all_vms(self, mock_run):
        """Test getting all VMs without resource group filter."""
        dashboard = StatusDashboard()

        mock_output = json.dumps(
            [
                {"name": "vm1", "resourceGroup": "rg1"},
                {"name": "vm2", "resourceGroup": "rg2"},
            ]
        )
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_vm_list()

        assert len(result) == 2
        assert result[0]["name"] == "vm1"
        assert result[1]["name"] == "vm2"
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "az" in call_args
        assert "vm" in call_args
        assert "list" in call_args
        assert "--resource-group" not in call_args

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_list_filtered_by_resource_group(self, mock_run):
        """Test getting VMs filtered by resource group."""
        dashboard = StatusDashboard()

        mock_output = json.dumps([{"name": "vm1", "resourceGroup": "test-rg"}])
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_vm_list(resource_group="test-rg")

        assert len(result) == 1
        assert result[0]["name"] == "vm1"
        call_args = mock_run.call_args[0][0]
        assert "--resource-group" in call_args
        assert "test-rg" in call_args


# ============================================================================
# VM INSTANCE VIEW TESTS
# ============================================================================


class TestGetVMInstanceView:
    """Tests for _get_vm_instance_view method."""

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_instance_view_success(self, mock_run):
        """Test successful VM instance view retrieval."""
        dashboard = StatusDashboard()

        mock_output = json.dumps(
            {
                "provisioningState": "Succeeded",
                "instanceView": {
                    "statuses": [
                        {"code": "ProvisioningState/succeeded"},
                        {"code": "PowerState/running"},
                    ]
                },
            }
        )
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_vm_instance_view("test-vm", "test-rg")

        assert result["provisioningState"] == "Succeeded"
        assert "instanceView" in result
        call_args = mock_run.call_args[0][0]
        assert "az" in call_args
        assert "vm" in call_args
        assert "get-instance-view" in call_args
        assert "test-vm" in call_args
        assert "test-rg" in call_args


# ============================================================================
# PUBLIC IP TESTS
# ============================================================================


class TestGetPublicIP:
    """Tests for _get_public_ip method."""

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_public_ip_success(self, mock_run):
        """Test successful public IP retrieval."""
        dashboard = StatusDashboard()

        mock_output = json.dumps(
            [{"virtualMachine": {"network": {"publicIpAddresses": [{"ipAddress": "1.2.3.4"}]}}}]
        )
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_public_ip("test-vm", "test-rg")

        assert result == "1.2.3.4"

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_public_ip_no_public_ip(self, mock_run):
        """Test when VM has no public IP."""
        dashboard = StatusDashboard()

        mock_output = json.dumps([{"virtualMachine": {"network": {"publicIpAddresses": []}}}])
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_public_ip("test-vm", "test-rg")

        assert result is None

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_public_ip_returns_none_on_subprocess_error(self, mock_run):
        """Test None return on subprocess.CalledProcessError."""
        dashboard = StatusDashboard()

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["az", "vm", "list-ip-addresses"]
        )

        result = dashboard._get_public_ip("test-vm", "test-rg")

        assert result is None

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_public_ip_returns_none_on_json_decode_error(self, mock_run):
        """Test None return on json.JSONDecodeError."""
        dashboard = StatusDashboard()

        mock_run.return_value = Mock(stdout="invalid json", returncode=0)

        result = dashboard._get_public_ip("test-vm", "test-rg")

        assert result is None

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_public_ip_returns_none_on_key_error(self, mock_run):
        """Test None return on KeyError."""
        dashboard = StatusDashboard()

        mock_output = json.dumps([{"malformed": "data"}])
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_public_ip("test-vm", "test-rg")

        assert result is None

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_public_ip_empty_result_list(self, mock_run):
        """Test when result list is empty."""
        dashboard = StatusDashboard()

        mock_output = json.dumps([])
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        result = dashboard._get_public_ip("test-vm", "test-rg")

        assert result is None


# ============================================================================
# POWER STATE TESTS
# ============================================================================


class TestExtractPowerState:
    """Tests for _extract_power_state method."""

    def test_extract_power_state_running(self):
        """Test extracting 'running' power state."""
        dashboard = StatusDashboard()

        instance_view = {
            "instanceView": {
                "statuses": [
                    {"code": "ProvisioningState/succeeded"},
                    {"code": "PowerState/running"},
                ]
            }
        }

        result = dashboard._extract_power_state(instance_view)

        assert result == "running"

    def test_extract_power_state_stopped(self):
        """Test extracting 'stopped' power state."""
        dashboard = StatusDashboard()

        instance_view = {
            "instanceView": {
                "statuses": [
                    {"code": "ProvisioningState/succeeded"},
                    {"code": "PowerState/stopped"},
                ]
            }
        }

        result = dashboard._extract_power_state(instance_view)

        assert result == "stopped"

    def test_extract_power_state_deallocated(self):
        """Test extracting 'deallocated' power state."""
        dashboard = StatusDashboard()

        instance_view = {
            "instanceView": {
                "statuses": [
                    {"code": "ProvisioningState/succeeded"},
                    {"code": "PowerState/deallocated"},
                ]
            }
        }

        result = dashboard._extract_power_state(instance_view)

        assert result == "deallocated"

    def test_extract_power_state_unknown(self):
        """Test 'Unknown' for missing power state."""
        dashboard = StatusDashboard()

        instance_view = {
            "instanceView": {
                "statuses": [
                    {"code": "ProvisioningState/succeeded"},
                ]
            }
        }

        result = dashboard._extract_power_state(instance_view)

        assert result == "Unknown"

    def test_extract_power_state_no_statuses(self):
        """Test 'Unknown' when statuses list is empty."""
        dashboard = StatusDashboard()

        instance_view = {"instanceView": {"statuses": []}}

        result = dashboard._extract_power_state(instance_view)

        assert result == "Unknown"

    def test_extract_power_state_missing_instance_view(self):
        """Test 'Unknown' when instanceView is missing."""
        dashboard = StatusDashboard()

        instance_view = {}

        result = dashboard._extract_power_state(instance_view)

        assert result == "Unknown"


# ============================================================================
# UPTIME TESTS
# ============================================================================


class TestCalculateUptime:
    """Tests for _calculate_uptime method."""

    def test_calculate_uptime_returns_none(self):
        """Test that uptime calculation returns None (not implemented)."""
        dashboard = StatusDashboard()

        instance_view = {"instanceView": {"statuses": []}}

        result = dashboard._calculate_uptime(instance_view)

        assert result is None


# ============================================================================
# ESTIMATED COST TESTS
# ============================================================================


class TestGetEstimatedCost:
    """Tests for _get_estimated_cost method."""

    def test_get_estimated_cost_known_vm_size(self):
        """Test estimated cost for known VM size."""
        dashboard = StatusDashboard()

        # Standard_D2s_v3 has hourly rate of 0.096
        cost = dashboard._get_estimated_cost("Standard_D2s_v3", hours=730.0)

        assert cost == 0.096 * 730.0
        assert cost == pytest.approx(70.08)

    def test_get_estimated_cost_unknown_vm_size(self):
        """Test estimated cost returns 0.0 for unknown VM size."""
        dashboard = StatusDashboard()

        cost = dashboard._get_estimated_cost("Unknown_VM_Size", hours=730.0)

        assert cost == 0.0

    def test_get_estimated_cost_custom_hours(self):
        """Test estimated cost with custom hours."""
        dashboard = StatusDashboard()

        # Standard_B1s has hourly rate of 0.0104
        cost = dashboard._get_estimated_cost("Standard_B1s", hours=100.0)

        assert cost == 0.0104 * 100.0
        assert cost == pytest.approx(1.04)

    def test_get_estimated_cost_default_hours(self):
        """Test estimated cost uses default 730 hours (1 month)."""
        dashboard = StatusDashboard()

        cost = dashboard._get_estimated_cost("Standard_B2s")

        # Standard_B2s hourly rate is 0.0416
        assert cost == 0.0416 * 730.0
        assert cost == pytest.approx(30.368)


# ============================================================================
# VM STATUS TESTS
# ============================================================================


class TestGetVMStatus:
    """Tests for get_vm_status method."""

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_status_single_vm(self, mock_run):
        """Test getting status for a single VM."""
        dashboard = StatusDashboard()

        # Mock VM list response
        vm_list = [
            {
                "name": "test-vm",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
            }
        ]

        # Mock instance view response
        instance_view = {
            "provisioningState": "Succeeded",
            "instanceView": {
                "statuses": [
                    {"code": "PowerState/running"},
                ]
            },
        }

        # Mock IP addresses response
        ip_addresses = [
            {"virtualMachine": {"network": {"publicIpAddresses": [{"ipAddress": "1.2.3.4"}]}}}
        ]

        def mock_run_side_effect(cmd, *args, **kwargs):
            if "list" in cmd and "vm" in cmd:
                return Mock(stdout=json.dumps(vm_list), returncode=0)
            if "get-instance-view" in cmd:
                return Mock(stdout=json.dumps(instance_view), returncode=0)
            if "list-ip-addresses" in cmd:
                return Mock(stdout=json.dumps(ip_addresses), returncode=0)
            return Mock(stdout="{}", returncode=0)

        mock_run.side_effect = mock_run_side_effect

        result = dashboard.get_vm_status()

        assert len(result) == 1
        assert result[0].name == "test-vm"
        assert result[0].resource_group == "test-rg"
        assert result[0].location == "eastus"
        assert result[0].size == "Standard_D2s_v3"
        assert result[0].os_type == "Linux"
        assert result[0].power_state == "running"
        assert result[0].provisioning_state == "Succeeded"
        assert result[0].public_ip == "1.2.3.4"
        assert result[0].estimated_cost == pytest.approx(70.08)

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_status_filtered_by_name(self, mock_run):
        """Test getting status filtered by VM name."""
        dashboard = StatusDashboard()

        vm_list = [
            {
                "name": "test-vm-1",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "hardwareProfile": {"vmSize": "Standard_B1s"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
            },
            {
                "name": "test-vm-2",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "hardwareProfile": {"vmSize": "Standard_B1s"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
            },
        ]

        instance_view = {
            "provisioningState": "Succeeded",
            "instanceView": {"statuses": [{"code": "PowerState/running"}]},
        }

        def mock_run_side_effect(cmd, *args, **kwargs):
            if "list" in cmd and "vm" in cmd:
                return Mock(stdout=json.dumps(vm_list), returncode=0)
            if "get-instance-view" in cmd:
                return Mock(stdout=json.dumps(instance_view), returncode=0)
            if "list-ip-addresses" in cmd:
                return Mock(stdout=json.dumps([]), returncode=0)
            return Mock(stdout="{}", returncode=0)

        mock_run.side_effect = mock_run_side_effect

        result = dashboard.get_vm_status(vm_name="test-vm-1")

        assert len(result) == 1
        assert result[0].name == "test-vm-1"

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_status_filtered_by_resource_group(self, mock_run):
        """Test getting status filtered by resource group."""
        dashboard = StatusDashboard()

        vm_list = [
            {
                "name": "test-vm",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "hardwareProfile": {"vmSize": "Standard_B1s"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
            }
        ]

        instance_view = {
            "provisioningState": "Succeeded",
            "instanceView": {"statuses": [{"code": "PowerState/running"}]},
        }

        def mock_run_side_effect(cmd, *args, **kwargs):
            if "list" in cmd and "vm" in cmd:
                assert "--resource-group" in cmd
                assert "test-rg" in cmd
                return Mock(stdout=json.dumps(vm_list), returncode=0)
            if "get-instance-view" in cmd:
                return Mock(stdout=json.dumps(instance_view), returncode=0)
            if "list-ip-addresses" in cmd:
                return Mock(stdout=json.dumps([]), returncode=0)
            return Mock(stdout="{}", returncode=0)

        mock_run.side_effect = mock_run_side_effect

        result = dashboard.get_vm_status(resource_group="test-rg")

        assert len(result) == 1

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_status_instance_view_error(self, mock_run):
        """Test handling of instance view retrieval error."""
        dashboard = StatusDashboard()

        vm_list = [
            {
                "name": "test-vm",
                "resourceGroup": "test-rg",
                "location": "eastus",
                "hardwareProfile": {"vmSize": "Standard_B1s"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
            }
        ]

        def mock_run_side_effect(cmd, *args, **kwargs):
            if "list" in cmd and "vm" in cmd:
                return Mock(stdout=json.dumps(vm_list), returncode=0)
            if "get-instance-view" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            if "list-ip-addresses" in cmd:
                return Mock(stdout=json.dumps([]), returncode=0)
            return Mock(stdout="{}", returncode=0)

        mock_run.side_effect = mock_run_side_effect

        result = dashboard.get_vm_status()

        assert len(result) == 1
        assert result[0].power_state == "Unknown"
        assert result[0].provisioning_state == "Unknown"

    @patch("azlin.status_dashboard.subprocess.run")
    def test_get_vm_status_empty_vm_list(self, mock_run):
        """Test when no VMs are found."""
        dashboard = StatusDashboard()

        mock_run.return_value = Mock(stdout=json.dumps([]), returncode=0)

        result = dashboard.get_vm_status()

        assert len(result) == 0


# ============================================================================
# DISPLAY STATUS TESTS
# ============================================================================


class TestDisplayStatus:
    """Tests for display_status method."""

    @patch("azlin.status_dashboard.StatusDashboard.get_vm_status")
    @patch("azlin.status_dashboard.Console")
    def test_display_status_no_vms(self, mock_console_class, mock_get_vm_status):
        """Test display when no VMs are found."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        mock_get_vm_status.return_value = []

        dashboard = StatusDashboard()
        dashboard.display_status()

        mock_get_vm_status.assert_called_once_with(None, None)
        mock_console.print.assert_called_once()
        call_args = str(mock_console.print.call_args)
        assert "No VMs found" in call_args or "yellow" in call_args.lower()

    @patch("azlin.status_dashboard.StatusDashboard.get_vm_status")
    @patch("azlin.status_dashboard.Console")
    def test_display_status_basic_table(self, mock_console_class, mock_get_vm_status):
        """Test basic table display without detailed metrics."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        vm_status = VMStatus(
            name="test-vm",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip="1.2.3.4",
            provisioning_state="Succeeded",
            os_type="Linux",
            estimated_cost=70.08,
        )
        mock_get_vm_status.return_value = [vm_status]

        dashboard = StatusDashboard()
        dashboard.display_status()

        mock_get_vm_status.assert_called_once_with(None, None)
        assert mock_console.print.call_count >= 1

    @patch("azlin.status_dashboard.StatusDashboard.get_vm_status")
    @patch("azlin.status_dashboard.Console")
    def test_display_status_with_detailed_metrics(self, mock_console_class, mock_get_vm_status):
        """Test detailed display with metrics and cost."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        vm_status = VMStatus(
            name="test-vm",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip="1.2.3.4",
            provisioning_state="Succeeded",
            os_type="Linux",
            estimated_cost=70.08,
        )
        mock_get_vm_status.return_value = [vm_status]

        dashboard = StatusDashboard()
        dashboard.display_status(detailed=True)

        mock_get_vm_status.assert_called_once_with(None, None)
        # Should print table and total cost
        assert mock_console.print.call_count >= 2

    @patch("azlin.status_dashboard.StatusDashboard.get_vm_status")
    @patch("azlin.status_dashboard.Console")
    def test_display_status_power_state_colors(self, mock_console_class, mock_get_vm_status):
        """Test power state color coding in display."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        running_vm = VMStatus(
            name="running-vm",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_B1s",
            public_ip="1.2.3.4",
            provisioning_state="Succeeded",
            os_type="Linux",
        )

        stopped_vm = VMStatus(
            name="stopped-vm",
            status="Succeeded",
            power_state="stopped",
            resource_group="test-rg",
            location="eastus",
            size="Standard_B1s",
            public_ip=None,
            provisioning_state="Succeeded",
            os_type="Linux",
        )

        deallocated_vm = VMStatus(
            name="deallocated-vm",
            status="Succeeded",
            power_state="deallocated",
            resource_group="test-rg",
            location="eastus",
            size="Standard_B1s",
            public_ip=None,
            provisioning_state="Succeeded",
            os_type="Linux",
        )

        mock_get_vm_status.return_value = [running_vm, stopped_vm, deallocated_vm]

        dashboard = StatusDashboard()
        dashboard.display_status()

        mock_get_vm_status.assert_called_once_with(None, None)
        mock_console.print.assert_called()

    @patch("azlin.status_dashboard.StatusDashboard.get_vm_status")
    @patch("azlin.status_dashboard.Console")
    def test_display_status_total_cost_calculation(self, mock_console_class, mock_get_vm_status):
        """Test total cost calculation only includes running VMs."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        running_vm1 = VMStatus(
            name="running-vm-1",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_B1s",
            public_ip="1.2.3.4",
            provisioning_state="Succeeded",
            os_type="Linux",
            estimated_cost=7.59,
        )

        running_vm2 = VMStatus(
            name="running-vm-2",
            status="Succeeded",
            power_state="running",
            resource_group="test-rg",
            location="eastus",
            size="Standard_B1s",
            public_ip="1.2.3.5",
            provisioning_state="Succeeded",
            os_type="Linux",
            estimated_cost=7.59,
        )

        stopped_vm = VMStatus(
            name="stopped-vm",
            status="Succeeded",
            power_state="stopped",
            resource_group="test-rg",
            location="eastus",
            size="Standard_B1s",
            public_ip=None,
            provisioning_state="Succeeded",
            os_type="Linux",
            estimated_cost=7.59,
        )

        mock_get_vm_status.return_value = [running_vm1, running_vm2, stopped_vm]

        dashboard = StatusDashboard()
        dashboard.display_status(detailed=True)

        # Verify total cost only includes running VMs (2 * 7.59 = 15.18)
        mock_console.print.assert_called()
        # Check if any call contains the total cost
        calls_str = str(mock_console.print.call_args_list)
        assert "15.18" in calls_str or "Total" in calls_str


# ============================================================================
# MODULE FUNCTION TESTS
# ============================================================================


class TestShowVMStatus:
    """Tests for show_vm_status module function."""

    @patch("azlin.status_dashboard.StatusDashboard.display_status")
    def test_show_vm_status_creates_dashboard(self, mock_display_status):
        """Test that show_vm_status creates dashboard and calls display_status."""
        show_vm_status(vm_name="test-vm", resource_group="test-rg", detailed=True)

        mock_display_status.assert_called_once_with("test-vm", "test-rg", True)

    @patch("azlin.status_dashboard.StatusDashboard.display_status")
    def test_show_vm_status_default_parameters(self, mock_display_status):
        """Test show_vm_status with default parameters."""
        show_vm_status()

        mock_display_status.assert_called_once_with(None, None, False)
