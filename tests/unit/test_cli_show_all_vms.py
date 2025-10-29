"""Unit tests for CLI --show-all-vms flag - Issue #208.

These tests verify the list command behavior with the new --show-all-vms flag:
1. Default behavior (no flag) shows only managed VMs
2. Default behavior shows notification when unmanaged VMs exist
3. --show-all-vms flag shows ALL VMs (managed + unmanaged)
4. Notification format is exactly as specified
5. Works with --all, --rg, --tag flags

TDD approach: These tests will FAIL until the feature is implemented.

Test Coverage:
- list_command() default behavior (managed VMs only)
- list_command() with --show-all-vms flag
- Notification message display and format
- Flag combinations
- Edge cases
"""

from unittest.mock import patch

from click.testing import CliRunner

from azlin.cli import main
from azlin.vm_manager import VMInfo


class TestListCommandShowAllVMs:
    """Test azlin list command with --show-all-vms flag - Issue #208."""

    # =========================================================================
    # Test 1: Default behavior shows only managed VMs
    # =========================================================================

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_default_shows_only_managed_vms(self, mock_get_rg, mock_list_vms):
        """Test that default 'azlin list' shows only managed VMs.

        Without --show-all-vms flag, only azlin-managed VMs should be shown.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # Mock VMs: 2 managed, 2 unmanaged
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="1.2.3.4",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="1.2.3.5",
                tags={"managed-by": "azlin"},
            ),
        ]

        mock_list_vms.return_value = managed_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Should show only managed VMs
        assert result.exit_code == 0
        assert "azlin-vm-1" in result.output
        assert "azlin-vm-2" in result.output

    # =========================================================================
    # Test 2: Default behavior shows notification when unmanaged VMs exist
    # =========================================================================

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_shows_notification_for_unmanaged_vms(
        self, mock_get_rg, mock_list_vms, mock_list_all
    ):
        """Test that notification is shown when unmanaged VMs exist.

        Default behavior should show:
        "N additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # Mock managed VMs only
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            )
        ]

        # Mock all VMs (managed + unmanaged)
        all_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_vms.return_value = managed_vms
        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Should show notification for 2 unmanaged VMs
        assert result.exit_code == 0
        assert (
            "2 additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."
            in result.output
        )

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_notification_format_exact(
        self, mock_get_rg, mock_list_vms, mock_list_all
    ):
        """Test that notification format is exactly as specified.

        Format must be:
        "<n> additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # 1 managed, 3 unmanaged
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            )
        ]

        all_vms = managed_vms + [
            VMInfo(
                name=f"user-vm-{i}",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            )
            for i in range(1, 4)
        ]

        mock_list_vms.return_value = managed_vms
        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Exact format check
        expected_message = (
            "3 additional vms not currently managed by azlin detected. "
            "Run with --show-all-vms to show them."
        )
        assert expected_message in result.output

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_no_notification_when_all_managed(
        self, mock_get_rg, mock_list_vms, mock_list_all
    ):
        """Test that no notification is shown when all VMs are managed.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # All VMs are managed
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
        ]

        mock_list_vms.return_value = managed_vms
        mock_list_all.return_value = managed_vms  # Same list

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Should NOT show notification
        assert "additional vms not currently managed by azlin" not in result.output

    # =========================================================================
    # Test 3: --show-all-vms flag shows ALL VMs
    # =========================================================================

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_with_show_all_vms_flag(self, mock_get_rg, mock_list_all):
        """Test that --show-all-vms flag shows all VMs (managed + unmanaged).

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # Mock all VMs
        all_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="1.2.3.4",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="1.2.3.5",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="1.2.3.6",
                tags={"owner": "user"},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg", "--show-all-vms"])

        # Should show all VMs
        assert result.exit_code == 0
        assert "azlin-vm-1" in result.output
        assert "user-vm-1" in result.output
        assert "user-vm-2" in result.output

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_show_all_vms_no_notification(self, mock_get_rg, mock_list_all):
        """Test that --show-all-vms does NOT show notification.

        When showing all VMs, no notification about unmanaged VMs is needed.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        all_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg", "--show-all-vms"])

        # Should NOT show notification
        assert "additional vms not currently managed by azlin" not in result.output

    # =========================================================================
    # Test 4: Flag combinations
    # =========================================================================

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_show_all_vms_with_all_flag(self, mock_get_rg, mock_list_all):
        """Test --show-all-vms with --all flag (include stopped VMs).

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # Mix of running and stopped VMs (managed and unmanaged)
        all_vms = [
            VMInfo(
                name="azlin-vm-running",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="azlin-vm-stopped",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-running",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-stopped",
                resource_group="test-rg",
                location="eastus",
                power_state="VM stopped",
                tags={},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg", "--show-all-vms", "--all"])

        # Should show all VMs including stopped
        assert result.exit_code == 0
        assert "azlin-vm-running" in result.output
        assert "azlin-vm-stopped" in result.output
        assert "user-vm-running" in result.output
        assert "user-vm-stopped" in result.output

        # Verify list_all_user_vms was called with include_stopped=True
        mock_list_all.assert_called_once()
        call_args = mock_list_all.call_args
        assert call_args[1]["include_stopped"] is True

    @patch("azlin.cli.TagManager.filter_vms_by_tag")
    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_show_all_vms_with_tag_filter(
        self, mock_get_rg, mock_list_all, mock_filter_by_tag
    ):
        """Test --show-all-vms with --tag flag.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        all_vms = [
            VMInfo(
                name="azlin-vm-dev",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin", "env": "dev"},
            ),
            VMInfo(
                name="user-vm-dev",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "dev"},
            ),
            VMInfo(
                name="user-vm-prod",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "prod"},
            ),
        ]

        filtered_vms = [vm for vm in all_vms if vm.tags and vm.tags.get("env") == "dev"]

        mock_list_all.return_value = all_vms
        mock_filter_by_tag.return_value = filtered_vms

        runner = CliRunner()
        result = runner.invoke(
            main, ["list", "--rg", "test-rg", "--show-all-vms", "--tag", "env=dev"]
        )

        # Should show only VMs with env=dev tag (both managed and unmanaged)
        assert result.exit_code == 0
        assert "azlin-vm-dev" in result.output
        assert "user-vm-dev" in result.output

        # Tag filtering should be called
        mock_filter_by_tag.assert_called_once()

    @patch("azlin.cli.VMManager.list_all_user_vms")
    def test_list_command_show_all_vms_with_specific_rg(self, mock_list_all):
        """Test --show-all-vms with specific --rg flag.

        Expected to FAIL until implementation is complete.
        """
        all_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="custom-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-1",
                resource_group="custom-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "custom-rg", "--show-all-vms"])

        # Should list from specified resource group
        assert result.exit_code == 0
        mock_list_all.assert_called_once_with("custom-rg", include_stopped=False)

    # =========================================================================
    # Test 5: Edge cases
    # =========================================================================

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_no_vms_default_behavior(self, mock_get_rg, mock_list_vms, mock_list_all):
        """Test default behavior when no VMs exist.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = []
        mock_list_all.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Should handle empty list gracefully
        assert result.exit_code == 0
        assert "additional vms not currently managed by azlin" not in result.output

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_show_all_vms_no_vms(self, mock_get_rg, mock_list_all):
        """Test --show-all-vms when no VMs exist.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"
        mock_list_all.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg", "--show-all-vms"])

        # Should handle empty list gracefully
        assert result.exit_code == 0

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_only_unmanaged_vms_exist(self, mock_get_rg, mock_list_vms, mock_list_all):
        """Test default behavior when only unmanaged VMs exist.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # No managed VMs
        mock_list_vms.return_value = []

        # Only unmanaged VMs
        all_vms = [
            VMInfo(
                name="user-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Should show notification for 2 unmanaged VMs
        assert result.exit_code == 0
        assert (
            "2 additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."
            in result.output
        )
        # Should NOT show VM names in output (since they're not managed)
        assert "user-vm-1" not in result.output
        assert "user-vm-2" not in result.output

    # =========================================================================
    # Test 6: Notification respects include_stopped filter
    # =========================================================================

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_notification_only_counts_running_unmanaged_vms(
        self, mock_get_rg, mock_list_vms, mock_list_all
    ):
        """Test that notification only counts running unmanaged VMs (default).

        When not using --all flag, notification should only count running unmanaged VMs.

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # 1 managed running
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            )
        ]

        # 2 unmanaged running, 1 unmanaged stopped
        all_vms_running_only = [
            *managed_vms,
            VMInfo(
                name="user-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_vms.return_value = managed_vms
        mock_list_all.return_value = all_vms_running_only  # Only running VMs

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg"])

        # Should show notification for 2 running unmanaged VMs
        assert "2 additional vms not currently managed by azlin detected." in result.output

    @patch("azlin.cli.VMManager.list_all_user_vms")
    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_command_notification_counts_all_unmanaged_with_all_flag(
        self, mock_get_rg, mock_list_vms, mock_list_all
    ):
        """Test that notification counts all unmanaged VMs with --all flag.

        When using --all flag, notification should count all unmanaged VMs (including stopped).

        Expected to FAIL until implementation is complete.
        """
        mock_get_rg.return_value = "test-rg"

        # 1 managed
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            )
        ]

        # 2 unmanaged running, 1 unmanaged stopped
        all_vms = [
            *managed_vms,
            VMInfo(
                name="user-vm-1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-3",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                tags={},
            ),
        ]

        mock_list_vms.return_value = managed_vms
        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "test-rg", "--all"])

        # Should show notification for 3 unmanaged VMs (including stopped)
        assert "3 additional vms not currently managed by azlin detected." in result.output


class TestShowAllVMsFlagDefinition:
    """Test that --show-all-vms flag is properly defined."""

    def test_show_all_vms_flag_exists_in_list_command(self):
        """Test that --show-all-vms flag is defined in list command.

        Expected to FAIL until implementation is complete.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--help"])

        # Flag should be in help output
        assert "--show-all-vms" in result.output
        assert result.exit_code == 0

    def test_show_all_vms_flag_help_text(self):
        """Test that --show-all-vms flag has appropriate help text.

        Expected to FAIL until implementation is complete.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--help"])

        # Help text should mention showing all VMs
        output_lower = result.output.lower()
        assert "--show-all-vms" in result.output
        # Should mention both managed and unmanaged
        assert "all" in output_lower or "unmanaged" in output_lower


class TestCrossRGNotification:
    """Test cross-RG mode unmanaged VM notification - Issue #208 Bug Fix."""

    # =========================================================================
    # Test 7: Cross-RG mode notification (the actual bug being fixed)
    # =========================================================================

    @patch("azlin.cli.TagManager.list_all_vms_cross_rg")
    @patch("azlin.cli.TagManager.list_managed_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_cross_rg_mode_shows_notification_for_unmanaged_vms(
        self, mock_get_rg, mock_list_managed, mock_list_all
    ):
        """Test that cross-RG mode shows notification when unmanaged VMs exist.

        This is the actual bug being fixed in Issue #208.
        Without --rg flag, the notification should still work.

        Expected to PASS after fix is implemented.
        """
        # Mock no default resource group to trigger cross-RG mode
        mock_get_rg.return_value = None

        # Mock managed VMs only (1 managed)
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            )
        ]

        # Mock all VMs (1 managed + 2 unmanaged)
        all_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="rg2",
                location="westus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_managed.return_value = managed_vms
        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list"])

        # Should show notification for 2 unmanaged VMs
        assert result.exit_code == 0
        assert (
            "2 additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."
            in result.output
        )

        # Verify both methods were called
        mock_list_managed.assert_called_once_with(resource_group=None)
        mock_list_all.assert_called_once()

    @patch("azlin.cli.TagManager.list_all_vms_cross_rg")
    @patch("azlin.cli.TagManager.list_managed_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_cross_rg_mode_no_notification_when_all_managed(
        self, mock_get_rg, mock_list_managed, mock_list_all
    ):
        """Test that cross-RG mode shows no notification when all VMs are managed.

        Expected to PASS after fix is implemented.
        """
        # Mock no default resource group to trigger cross-RG mode
        mock_get_rg.return_value = None

        # All VMs are managed
        managed_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="rg2",
                location="westus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
        ]

        mock_list_managed.return_value = managed_vms
        mock_list_all.return_value = managed_vms  # Same list

        runner = CliRunner()
        result = runner.invoke(main, ["list"])

        # Should NOT show notification
        assert result.exit_code == 0
        assert "additional vms not currently managed by azlin" not in result.output

    @patch("azlin.cli.TagManager.list_all_vms_cross_rg")
    @patch("azlin.cli.TagManager.list_managed_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_cross_rg_mode_only_unmanaged_vms_exist(
        self, mock_get_rg, mock_list_managed, mock_list_all
    ):
        """Test cross-RG mode when only unmanaged VMs exist.

        Expected to PASS after fix is implemented.
        """
        # Mock no default resource group to trigger cross-RG mode
        mock_get_rg.return_value = None

        # No managed VMs
        mock_list_managed.return_value = []

        # Only unmanaged VMs
        all_vms = [
            VMInfo(
                name="user-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="rg2",
                location="westus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list"])

        # Should show notification for 2 unmanaged VMs
        assert result.exit_code == 0
        assert (
            "2 additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."
            in result.output
        )

    @patch("azlin.cli.TagManager.list_all_vms_cross_rg")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_cross_rg_mode_with_show_all_vms_flag(self, mock_get_rg, mock_list_all):
        """Test cross-RG mode with --show-all-vms flag.

        Expected to PASS after fix is implemented.
        """
        # Mock no default resource group to trigger cross-RG mode
        mock_get_rg.return_value = None

        # Mix of managed and unmanaged VMs
        all_vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            ),
            VMInfo(
                name="user-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
            VMInfo(
                name="user-vm-2",
                resource_group="rg2",
                location="westus",
                power_state="VM running",
                tags={},
            ),
        ]

        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-all-vms"])

        # Should show all VMs
        assert result.exit_code == 0
        assert "azlin-vm-1" in result.output
        assert "user-vm-1" in result.output
        assert "user-vm-2" in result.output

        # Should NOT show notification when using --show-all-vms
        assert "additional vms not currently managed by azlin" not in result.output

        # Verify list_all_vms_cross_rg was called
        mock_list_all.assert_called_once()

    @patch("azlin.cli.TagManager.list_all_vms_cross_rg")
    @patch("azlin.cli.TagManager.list_managed_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_cross_rg_mode_notification_with_59_unmanaged_vms(
        self, mock_get_rg, mock_list_managed, mock_list_all
    ):
        """Test cross-RG mode notification with 59 unmanaged VMs (the reported bug case).

        This tests the exact scenario reported in Issue #208.

        Expected to PASS after fix is implemented.
        """
        # Mock no default resource group to trigger cross-RG mode
        mock_get_rg.return_value = None

        # 3 managed VMs
        managed_vms = [
            VMInfo(
                name=f"azlin-vm-{i}",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                tags={"managed-by": "azlin"},
            )
            for i in range(1, 4)
        ]

        # 3 managed + 59 unmanaged = 62 total
        all_vms = managed_vms + [
            VMInfo(
                name=f"user-vm-{i}",
                resource_group=f"rg{i % 5}",
                location="eastus",
                power_state="VM running",
                tags={},
            )
            for i in range(1, 60)
        ]

        mock_list_managed.return_value = managed_vms
        mock_list_all.return_value = all_vms

        runner = CliRunner()
        result = runner.invoke(main, ["list"])

        # Should show notification for 59 unmanaged VMs
        assert result.exit_code == 0
        assert (
            "59 additional vms not currently managed by azlin detected. Run with --show-all-vms to show them."
            in result.output
        )
