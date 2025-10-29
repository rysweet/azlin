"""Integration tests for azlin list command with quota and tmux features.

This module tests the enhanced list command functionality:
- Display VM quota information
- Display tmux sessions across VMs
- Flag handling (--no-quota, --no-tmux)
- Backward compatibility
- Integration with existing list features

All tests should FAIL initially (TDD approach).
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from azlin.cli import main
from azlin.quota_manager import QuotaInfo
from azlin.remote_exec import TmuxSessionInfo
from azlin.vm_manager import VMInfo


@pytest.fixture
def cli_runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_vms():
    """Sample VM list for testing."""
    return [
        VMInfo(
            name="azlin-vm-001",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            private_ip="10.0.0.4",
            vm_size="Standard_D2s_v3",
            os_type="Linux",
            provisioning_state="Succeeded",
            session_name="dev-session",
        ),
        VMInfo(
            name="azlin-vm-002",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="5.6.7.8",
            private_ip="10.0.0.5",
            vm_size="Standard_D4s_v3",
            os_type="Linux",
            provisioning_state="Succeeded",
            session_name="prod-session",
        ),
        VMInfo(
            name="azlin-vm-003",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped",
            public_ip=None,
            private_ip="10.0.0.6",
            vm_size="Standard_B2s",
            os_type="Linux",
            provisioning_state="Succeeded",
            session_name=None,
        ),
    ]


@pytest.fixture
def sample_quota():
    """Sample quota information for testing."""
    return QuotaInfo(
        region="eastus",
        quota_name="standardDSv3Family",
        current_usage=12,
        limit=20,
    )


@pytest.fixture
def sample_tmux_sessions():
    """Sample tmux sessions for testing."""
    return [
        TmuxSessionInfo(
            vm_name="azlin-vm-001",
            session_name="dev",
            windows=3,
            created_time="Thu Oct 10 10:00:00 2024",
        ),
        TmuxSessionInfo(
            vm_name="azlin-vm-002",
            session_name="prod",
            windows=1,
            created_time="Thu Oct 10 11:00:00 2024",
        ),
        TmuxSessionInfo(
            vm_name="azlin-vm-002",
            session_name="backup",
            windows=2,
            created_time="Thu Oct 10 12:00:00 2024",
        ),
    ]


@pytest.mark.integration
class TestListCommandWithQuota:
    """Integration tests for list command with quota display."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_with_quota_enabled(
        self, mock_get_rg, mock_get_quota, mock_list_vms, cli_runner, sample_vms, sample_quota
    ):
        """Test list command displays quota information by default."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = sample_quota

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should display quota information
        assert "quota" in result.output.lower() or "12/20" in result.output
        # Should display VMs
        assert "azlin-vm-001" in result.output
        assert "azlin-vm-002" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_with_no_quota_flag(
        self, mock_get_rg, mock_get_quota, mock_list_vms, cli_runner, sample_vms
    ):
        """Test --no-quota flag suppresses quota display."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms

        result = cli_runner.invoke(main, ["list", "--no-quota"])

        assert result.exit_code == 0
        # Should not call quota manager
        mock_get_quota.assert_not_called()
        # Should still display VMs
        assert "azlin-vm-001" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_quota_api_failure_graceful(
        self, mock_get_rg, mock_get_quota, mock_list_vms, cli_runner, sample_vms
    ):
        """Test graceful handling when quota API fails."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.side_effect = Exception("Quota API unavailable")

        result = cli_runner.invoke(main, ["list"])

        # Should still succeed and show VMs
        assert result.exit_code == 0
        assert "azlin-vm-001" in result.output
        # May show warning about quota
        assert "warning" in result.output.lower() or "quota" not in result.output.lower()

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_quota_at_limit(
        self, mock_get_rg, mock_get_quota, mock_list_vms, cli_runner, sample_vms
    ):
        """Test quota display when at limit."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=20,
            limit=20,
        )

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should show quota at 100%
        assert "20/20" in result.output or "100%" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_quota_none_returned(
        self, mock_get_rg, mock_get_quota, mock_list_vms, cli_runner, sample_vms
    ):
        """Test handling when quota returns None (not found)."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = None

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should still display VMs
        assert "azlin-vm-001" in result.output


@pytest.mark.integration
class TestListCommandWithTmux:
    """Integration tests for list command with tmux session display."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_with_tmux_enabled(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_tmux_sessions,
    ):
        """Test list command displays tmux sessions by default."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should display tmux sessions
        assert "tmux" in result.output.lower() or "dev" in result.output
        assert "prod" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_with_no_tmux_flag(
        self, mock_get_rg, mock_get_sessions, mock_list_vms, cli_runner, sample_vms
    ):
        """Test --no-tmux flag suppresses tmux session display."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms

        result = cli_runner.invoke(main, ["list", "--no-tmux"])

        assert result.exit_code == 0
        # Should not call tmux executor
        mock_get_sessions.assert_not_called()
        # Should still display VMs
        assert "azlin-vm-001" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_tmux_no_sessions(
        self, mock_get_ssh, mock_get_rg, mock_get_sessions, mock_list_vms, cli_runner, sample_vms
    ):
        """Test display when no tmux sessions exist."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_sessions.return_value = []
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should show no sessions message or omit tmux section
        assert "azlin-vm-001" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_tmux_connection_timeout(
        self, mock_get_ssh, mock_get_rg, mock_get_sessions, mock_list_vms, cli_runner, sample_vms
    ):
        """Test graceful handling when tmux query times out."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_sessions.side_effect = TimeoutError("Connection timeout")
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        # Should still succeed and show VMs
        assert result.exit_code == 0
        assert "azlin-vm-001" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_tmux_stopped_vms_excluded(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_tmux_sessions,
    ):
        """Test tmux queries only run on running VMs."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms  # Includes stopped VM
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # SSH config should only be created for running VMs
        # (azlin-vm-001 and azlin-vm-002, not azlin-vm-003)
        assert mock_get_ssh.call_count == 2


@pytest.mark.integration
class TestListCommandWithBothFeatures:
    """Integration tests with both quota and tmux enabled."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_with_quota_and_tmux(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_get_quota,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_quota,
        sample_tmux_sessions,
    ):
        """Test list command with both quota and tmux enabled."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = sample_quota
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should display both quota and tmux
        assert "12/20" in result.output or "quota" in result.output.lower()
        assert "dev" in result.output or "tmux" in result.output.lower()
        # Should display VMs
        assert "azlin-vm-001" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_with_both_disabled(self, mock_get_rg, mock_list_vms, cli_runner, sample_vms):
        """Test list command with both quota and tmux disabled."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms

        result = cli_runner.invoke(main, ["list", "--no-quota", "--no-tmux"])

        assert result.exit_code == 0
        # Should only display basic VM table
        assert "azlin-vm-001" in result.output
        assert "azlin-vm-002" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_quota_fails_tmux_succeeds(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_get_quota,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_tmux_sessions,
    ):
        """Test when quota fails but tmux succeeds."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.side_effect = Exception("Quota API error")
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        # Should still succeed and show VMs and tmux
        assert result.exit_code == 0
        assert "azlin-vm-001" in result.output
        assert "dev" in result.output or "tmux" in result.output.lower()

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_tmux_fails_quota_succeeds(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_get_quota,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_quota,
    ):
        """Test when tmux fails but quota succeeds."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = sample_quota
        mock_get_sessions.side_effect = Exception("SSH connection failed")
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        # Should still succeed and show VMs and quota
        assert result.exit_code == 0
        assert "azlin-vm-001" in result.output
        assert "12/20" in result.output or "quota" in result.output.lower()


@pytest.mark.integration
class TestListCommandBackwardCompatibility:
    """Test backward compatibility of list command."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_basic_functionality_unchanged(
        self, mock_get_rg, mock_list_vms, cli_runner, sample_vms
    ):
        """Test that basic list functionality remains unchanged."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should display VM table with all expected columns
        assert "SESSION NAME" in result.output or "VM NAME" in result.output
        assert "azlin-vm-001" in result.output
        assert "1.2.3.4" in result.output
        assert "eastus" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_with_all_flag(self, mock_get_rg, mock_list_vms, cli_runner, sample_vms):
        """Test --all flag still works (include stopped VMs)."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms

        result = cli_runner.invoke(main, ["list", "--all"])

        assert result.exit_code == 0
        # Should call with include_stopped=True
        mock_list_vms.assert_called_once()
        call_args = mock_list_vms.call_args
        assert call_args[1]["include_stopped"] is True

    @patch("azlin.cli.TagManager.list_managed_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_cross_rg_discovery_still_works(
        self, mock_get_rg, mock_list_managed, cli_runner, sample_vms
    ):
        """Test cross-RG discovery still works."""
        mock_get_rg.return_value = None  # No default RG
        mock_list_managed.return_value = sample_vms

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should use tag-based discovery
        mock_list_managed.assert_called_once()
        assert "azlin-vm-001" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TagManager.filter_vms_by_tag")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_with_tag_filter(
        self, mock_get_rg, mock_filter, mock_list_vms, cli_runner, sample_vms
    ):
        """Test --tag filter still works."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_filter.return_value = [sample_vms[0]]  # Return filtered result

        result = cli_runner.invoke(main, ["list", "--tag", "env=dev"])

        assert result.exit_code == 0
        mock_filter.assert_called_once()
        # Should display filtered VMs
        assert "azlin-vm-001" in result.output


@pytest.mark.integration
class TestListCommandErrorHandling:
    """Test error handling in list command."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_no_vms_found(self, mock_get_rg, mock_list_vms, cli_runner):
        """Test display when no VMs found."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = []

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        assert "No VMs found" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_vm_manager_error(self, mock_get_rg, mock_list_vms, cli_runner):
        """Test handling of VM manager errors."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.side_effect = Exception("Azure API error")

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code != 0
        assert "error" in result.output.lower()

    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_no_resource_group(self, mock_get_rg, cli_runner):
        """Test error when no resource group configured."""
        mock_get_rg.return_value = None

        result = cli_runner.invoke(main, ["list"])

        # Should attempt cross-RG discovery or show error
        assert "resource group" in result.output.lower() or "azlin-vm" in result.output


@pytest.mark.integration
class TestListCommandPerformance:
    """Test performance aspects of list command."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_parallel_execution(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_get_quota,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_quota,
        sample_tmux_sessions,
    ):
        """Test that quota and tmux queries run in parallel or are non-blocking."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = sample_quota
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Both should be called
        mock_get_quota.assert_called_once()
        mock_get_sessions.assert_called_once()

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_tmux_uses_parallel_executor(
        self, mock_get_ssh, mock_get_rg, mock_get_sessions, mock_list_vms, cli_runner, sample_vms
    ):
        """Test that tmux session queries use parallel execution."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_sessions.return_value = []
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should call parallel executor, not single VM executor
        mock_get_sessions.assert_called_once()


@pytest.mark.integration
class TestListCommandOutputFormatting:
    """Test output formatting of list command."""

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_output_structure(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_get_quota,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_quota,
        sample_tmux_sessions,
    ):
        """Test that output has proper structure with all sections."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = sample_quota
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should have quota section
        assert "quota" in result.output.lower() or "12" in result.output
        # Should have VM table
        assert "VM NAME" in result.output or "azlin-vm-001" in result.output
        # Should have tmux section
        assert "tmux" in result.output.lower() or "dev" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.QuotaManager.get_quota")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    def test_list_quota_formatting(
        self, mock_get_rg, mock_get_quota, mock_list_vms, cli_runner, sample_vms, sample_quota
    ):
        """Test quota display formatting."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_quota.return_value = sample_quota

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should show usage in readable format
        # Format: "12 / 20" or "12/20 (60%)" or similar
        output_lower = result.output.lower()
        assert "12" in result.output
        assert "20" in result.output

    @patch("azlin.cli.VMManager.list_vms")
    @patch("azlin.cli.TmuxSessionExecutor.get_sessions_parallel")
    @patch("azlin.cli.ConfigManager.get_resource_group")
    @patch("azlin.cli.SSHConnector.get_ssh_config")
    def test_list_tmux_formatting(
        self,
        mock_get_ssh,
        mock_get_rg,
        mock_get_sessions,
        mock_list_vms,
        cli_runner,
        sample_vms,
        sample_tmux_sessions,
    ):
        """Test tmux session display formatting."""
        mock_get_rg.return_value = "test-rg"
        mock_list_vms.return_value = sample_vms
        mock_get_sessions.return_value = sample_tmux_sessions
        mock_get_ssh.return_value = Mock()

        result = cli_runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Should group sessions by VM or show VM association
        assert "azlin-vm-001" in result.output
        assert "dev" in result.output
        # Should show window count
        assert "3" in result.output or "windows" in result.output.lower()
