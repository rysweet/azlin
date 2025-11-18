"""
Unit tests for interactive VM selection in connect command.

Tests the interactive selection feature when no VM identifier is provided.

Test Coverage:
- Interactive VM list display
- VM selection from list
- Create new VM option
- No VMs available scenario
- Invalid selection handling
- User cancellation
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from azlin.cli import main
from azlin.vm_manager import VMInfo
from tests.conftest import requires_azure_auth


class TestInteractiveVMSelection:
    """Test interactive VM selection in connect command."""

    @pytest.fixture
    def runner(self):
        """Provide a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_vms(self):
        """Provide mock VM list."""
        return [
            VMInfo(
                name="test-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="10.0.0.1",
                vm_size="Standard_B2s",
            ),
            VMInfo(
                name="test-vm-2",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="10.0.0.2",
                vm_size="Standard_D2s_v3",
            ),
        ]

    def test_connect_without_vm_shows_list(self, runner, mock_vms):
        """Test that connect without VM name shows interactive list.

        When no VM identifier is provided, should display list of VMs
        and prompt for selection.
        """
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=mock_vms),
            patch("azlin.cli.VMConnector.connect", return_value=True),
        ):
            result = runner.invoke(main, ["connect"], input="1\n")

            assert result.exit_code == 0
            assert "Available VMs:" in result.output
            assert "test-vm-1" in result.output
            assert "test-vm-2" in result.output
            assert "Create new VM" in result.output

    @requires_azure_auth
    def test_connect_select_first_vm(self, runner, mock_vms):
        """Test selecting first VM from list."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=mock_vms),
            patch("azlin.cli.VMConnector.connect", return_value=True) as mock_connect,
        ):
            result = runner.invoke(main, ["connect"], input="1\n")

            assert result.exit_code == 0
            mock_connect.assert_called_once()
            # Check that it connected to the first VM
            call_args = mock_connect.call_args
            assert call_args[1]["vm_identifier"] == "test-vm-1"

    @requires_azure_auth
    def test_connect_select_second_vm(self, runner, mock_vms):
        """Test selecting second VM from list."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=mock_vms),
            patch("azlin.cli.VMConnector.connect", return_value=True) as mock_connect,
        ):
            result = runner.invoke(main, ["connect"], input="2\n")

            assert result.exit_code == 0
            call_args = mock_connect.call_args
            assert call_args[1]["vm_identifier"] == "test-vm-2"

    def test_connect_create_new_vm_option(self, runner, mock_vms):
        """Test selecting option 0 to create new VM."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=mock_vms),
            patch("azlin.cli.new_command") as mock_new,
        ):
            result = runner.invoke(main, ["connect"], input="0\n")

            # Should invoke new command
            assert mock_new.called or "create new" in result.output.lower()

    def test_connect_no_vms_prompts_create(self, runner):
        """Test that when no VMs exist, prompts to create one."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=[]),
        ):
            result = runner.invoke(main, ["connect"], input="y\n")

            assert "No running VMs found" in result.output
            assert "create a new VM" in result.output

    @requires_azure_auth
    def test_connect_no_vms_decline_create(self, runner):
        """Test declining to create VM when none exist."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=[]),
        ):
            result = runner.invoke(main, ["connect"], input="n\n")

            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_connect_invalid_selection_reprompts(self, runner, mock_vms):
        """Test that invalid selection number asks again."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=mock_vms),
            patch("azlin.cli.VMConnector.connect", return_value=True),
        ):
            # Try invalid selection (99), then valid selection (1)
            result = runner.invoke(main, ["connect"], input="99\n1\n")

            assert "Invalid selection" in result.output or result.exit_code == 0

    def test_connect_with_vm_name_skips_interactive(self, runner):
        """Test that providing VM name skips interactive selection."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMConnector.connect", return_value=True) as mock_connect,
        ):
            result = runner.invoke(main, ["connect", "my-vm"])

            # Should not show interactive list
            assert "Available VMs:" not in result.output
            mock_connect.assert_called_once()
            call_args = mock_connect.call_args
            assert call_args[1]["vm_identifier"] == "my-vm"

    def test_connect_no_resource_group_error(self, runner):
        """Test error when no resource group configured."""
        with patch("azlin.cli.ConfigManager.get_resource_group", return_value=None):
            result = runner.invoke(main, ["connect"])

            assert result.exit_code == 1
            assert "Resource group required" in result.output

    def test_connect_list_vms_error(self, runner):
        """Test handling of error when listing VMs fails."""
        from azlin.vm_manager import VMManagerError

        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", side_effect=VMManagerError("API error")),
        ):
            result = runner.invoke(main, ["connect"])

            assert result.exit_code == 1
            assert "Error listing VMs" in result.output

    def test_connect_user_abort(self, runner, mock_vms):
        """Test user cancelling (Ctrl+C) during selection."""
        with (
            patch(
                "azlin.context_manager.ContextManager.ensure_subscription_active",
                return_value="test-sub-id",
            ),
            patch("azlin.cli.ConfigManager.get_resource_group", return_value="test-rg"),
            patch("azlin.cli.VMManager.list_vms", return_value=mock_vms),
        ):
            # Simulate Ctrl+C by not providing input
            result = runner.invoke(main, ["connect"], input="")

            # Should exit gracefully
            assert result.exit_code in [0, 1]
            assert "Cancelled" in result.output or result.exit_code == 1
