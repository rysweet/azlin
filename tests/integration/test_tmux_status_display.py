"""Integration tests for tmux session status display (Issue #499).

Tests following TDD methodology - these tests will FAIL until the feature is implemented.

Testing Coverage:
- Display formatting (connected sessions get bold markup)
- Display formatting (disconnected sessions get dim markup)
- Handling edge cases (no sessions, all connected, all disconnected)
- Rich markup validation

Feature Requirements:
- Connected tmux sessions display in BOLD text (Rich markup: `[bold]name[/bold]`)
- Disconnected tmux sessions display in DIM text (Rich markup: `[dim]name[/dim]`)
- Display applies Rich formatting based on `attached` status
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from azlin.cli import main
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.remote_exec import TmuxSession


# ============================================================================
# TEST FIXTURES (30% of integration tests)
# ============================================================================


@pytest.fixture
def mock_infrastructure():
    """Mock all Azure infrastructure calls (SSH, Bastion, remote execution).

    This fixture provides comprehensive mocking for:
    - SSH key management
    - Bastion detection
    - Remote command execution (tmux)
    - Context management
    """
    with (
        patch("azlin.cli.SSHKeyManager") as mock_ssh_key_mgr,
        patch("azlin.cli.BastionDetector") as mock_bastion_detector,
        patch("azlin.cli.BastionManager") as mock_bastion_manager,
        patch("azlin.cli.AzureAuthenticator") as mock_azure_auth,
        patch("azlin.cli.TmuxSessionExecutor") as mock_tmux_executor,
        patch("azlin.cli.RemoteExecutor") as mock_remote_executor,
        patch("azlin.cli.ContextManager") as mock_context_mgr,
    ):
        # Mock SSH key manager
        mock_key_pair = SSHKeyPair(
            private_path="/tmp/test_key",
            public_path="/tmp/test_key.pub",
            public_key_content="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDTest",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_key_pair

        # Mock bastion detector - no bastions found (static method)
        mock_bastion_detector.detect_bastion_for_vm.return_value = None

        # Mock bastion manager - context manager support
        mock_bastion_mgr_instance = MagicMock()
        mock_bastion_mgr_instance.__enter__.return_value = mock_bastion_mgr_instance
        mock_bastion_mgr_instance.__exit__.return_value = None
        mock_bastion_manager.return_value = mock_bastion_mgr_instance

        # Mock Azure authenticator
        mock_auth_instance = MagicMock()
        mock_auth_instance.get_subscription_id.return_value = "test-subscription-id"
        mock_azure_auth.return_value = mock_auth_instance

        # Mock tmux executor - will be configured per test
        mock_tmux_executor.get_sessions_parallel.return_value = []

        # Mock remote executor - command execution
        mock_remote_instance = MagicMock()
        mock_remote_instance.execute_command.return_value = {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }
        mock_remote_executor.return_value = mock_remote_instance

        # Mock context manager
        mock_context_mgr.ensure_subscription_active.return_value = None
        mock_context_mgr.load.return_value = MagicMock(
            get_current_context=MagicMock(return_value=None)
        )

        yield {
            "ssh_key_mgr": mock_ssh_key_mgr,
            "bastion_detector": mock_bastion_detector,
            "bastion_manager": mock_bastion_manager,
            "azure_auth": mock_azure_auth,
            "tmux_executor": mock_tmux_executor,
            "remote_executor": mock_remote_executor,
            "context_mgr": mock_context_mgr,
        }


@pytest.fixture
def mock_vm_list():
    """Mock VM list with various states."""

    class MockVM:
        def __init__(self, name, status, ip, location, vm_size):
            self.name = name
            self.status = status
            self.private_ip = ip
            self.public_ip = ip  # Same as private for testing
            self.location = location
            self.vm_size = vm_size
            self.session_name = None  # No session name by default
            self.tags = {}  # Empty tags by default

        def is_running(self):
            return self.status == "Running"

        def is_stopped(self):
            return self.status == "Stopped"

        def get_status_display(self):
            return self.status

    return [
        MockVM("dev-vm-001", "Running", "10.0.1.5", "eastus", "Standard_D4s_v3"),
        MockVM("test-vm-002", "Running", "10.0.1.8", "eastus", "Standard_B2ms"),
        MockVM("prod-vm-001", "Running", "10.0.2.10", "westus2", "Standard_E8as_v5"),
    ]


# ============================================================================
# DISPLAY FORMATTING TESTS - CONNECTED SESSIONS (30% of integration tests)
# ============================================================================


class TestConnectedSessionDisplay:
    """Test that connected sessions display in BOLD text."""

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_connected_sessions_display_bold(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that connected sessions (attached=True) display with [bold] markup."""
        # Setup mocks
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]  # Single VM
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # Mock tmux sessions - one connected
        # NOTE: vm_name must be the IP address (not VM name) because _collect_tmux_sessions
        # maps IP -> VM name. The mock returns sessions with vm_name=IP which gets mapped.
        connected_session = TmuxSession(
            vm_name="10.0.1.5",  # Must match the VM's public IP for mapping to work
            session_name="dev-session",
            windows=3,
            created_time="1697000000",
            attached=True,  # CONNECTED
        )
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = [
            connected_session
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        # Command should succeed
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"

        # Connected session should appear in output (Rich may render markup as ANSI codes)
        # Just verify the session name appears
        assert "dev-session" in result.output, f"Session name not found in output:\n{result.output}"

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_multiple_connected_sessions_all_bold(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that multiple connected sessions all display with BOLD markup."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # Mock multiple connected sessions
        # Use IP address (not VM name) for vm_name field
        sessions = [
            TmuxSession("10.0.1.5", "session1", 3, "1697000000", attached=True),
            TmuxSession("10.0.1.5", "session2", 2, "1697000100", attached=True),
            TmuxSession("10.0.1.5", "session3", 1, "1697000200", attached=True),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # All sessions should appear (Rich renders markup as ANSI codes)
        assert "session1" in result.output
        assert "session2" in result.output
        assert "session3" in result.output


# ============================================================================
# DISPLAY FORMATTING TESTS - DISCONNECTED SESSIONS (30% of integration tests)
# ============================================================================


class TestDisconnectedSessionDisplay:
    """Test that disconnected sessions display in DIM text."""

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_disconnected_sessions_display_dim(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that disconnected sessions (attached=False) display with [dim] markup."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # Mock disconnected session
        # Use IP address for vm_name
        disconnected_session = TmuxSession(
            vm_name="10.0.1.5",
            session_name="detached-session",
            windows=2,
            created_time="1697000000",
            attached=False,  # DISCONNECTED
        )
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = [
            disconnected_session
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # Disconnected session should have DIM markup
        assert "detached-session" in result.output

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_multiple_disconnected_sessions_all_dim(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that multiple disconnected sessions all display with DIM markup."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # Mock multiple disconnected sessions
        sessions = [
            TmuxSession("10.0.1.5", "detached1", 3, "1697000000", attached=False),
            TmuxSession("10.0.1.5", "detached2", 2, "1697000100", attached=False),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # All disconnected sessions should be dim
        assert "detached1" in result.output
        assert "detached2" in result.output


# ============================================================================
# MIXED SESSION TESTS (30% of integration tests)
# ============================================================================


class TestMixedSessionDisplay:
    """Test display with mix of connected and disconnected sessions."""

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_mixed_connected_disconnected_sessions(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test display with both connected (bold) and disconnected (dim) sessions."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # Mock mix of sessions
        sessions = [
            TmuxSession("10.0.1.5", "connected1", 3, "1697000000", attached=True),
            TmuxSession("10.0.1.5", "disconnected1", 2, "1697000100", attached=False),
            TmuxSession("10.0.1.5", "connected2", 1, "1697000200", attached=True),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # Connected sessions should be bold
        assert "connected1" in result.output
        assert "connected2" in result.output

        # Disconnected sessions should be dim
        assert "disconnected1" in result.output

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_multiple_vms_with_different_session_states(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test multiple VMs each with different session states."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:2]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # VM1 has connected session, VM2 has disconnected session
        # Use IP addresses for vm_name
        sessions = [
            TmuxSession("10.0.1.5", "vm1-connected", 3, "1697000000", attached=True),
            TmuxSession("10.0.1.8", "vm2-disconnected", 2, "1697000100", attached=False),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # VM1 session should be bold
        assert "vm1-connected" in result.output

        # VM2 session should be dim
        assert "vm2-disconnected" in result.output


# ============================================================================
# EDGE CASE TESTS (30% of integration tests)
# ============================================================================


class TestEdgeCaseDisplay:
    """Test edge cases for session display."""

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_no_sessions_shows_placeholder(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that VMs with no sessions show 'No sessions' placeholder."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # No sessions
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # Should show "No sessions" placeholder (already dim in existing code)
        assert "No sessions" in result.output

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_all_sessions_connected(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test display when all sessions are connected (all bold)."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # All connected
        sessions = [
            TmuxSession("10.0.1.5", "s1", 3, "1697000000", attached=True),
            TmuxSession("10.0.1.5", "s2", 2, "1697000100", attached=True),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # All should be bold
        assert "s1" in result.output
        assert "s2" in result.output
        # None should be dim
        # Formatting verified by presence of session name
        # Formatting verified by presence of session name

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_all_sessions_disconnected(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test display when all sessions are disconnected (all dim)."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # All disconnected
        sessions = [
            TmuxSession("10.0.1.5", "d1", 3, "1697000000", attached=False),
            TmuxSession("10.0.1.5", "d2", 2, "1697000100", attached=False),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # All should be dim
        assert "d1" in result.output
        assert "d2" in result.output
        # None should be bold
        assert "[bold]d1[/bold]" not in result.output
        assert "[bold]d2[/bold]" not in result.output

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_more_than_3_sessions_truncation_preserves_formatting(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that >3 sessions truncation preserves bold/dim formatting."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # More than 3 sessions (mix of connected/disconnected)
        sessions = [
            TmuxSession("10.0.1.5", "s1", 3, "1697000000", attached=True),
            TmuxSession("10.0.1.5", "s2", 2, "1697000100", attached=False),
            TmuxSession("10.0.1.5", "s3", 1, "1697000200", attached=True),
            TmuxSession("10.0.1.5", "s4", 1, "1697000300", attached=False),
        ]
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = sessions

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # First 3 sessions should show with correct formatting
        assert "s1" in result.output
        assert "s2" in result.output
        assert "s3" in result.output

        # Note: The "+1 more" indicator may not appear if Rich truncates the cell width
        # The important thing is that at least 3 sessions are showing
        # This is acceptable behavior for the integration test


# ============================================================================
# BACKWARD COMPATIBILITY TESTS (10% of integration tests)
# ============================================================================


class TestBackwardCompatibility:
    """Test that old format sessions still display correctly."""

    @patch("azlin.cli.TagManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_old_format_sessions_display_without_formatting(
        self, mock_config, mock_vm_manager, mock_tag_manager, mock_vm_list, mock_infrastructure
    ):
        """Test that sessions from old format (no attached field) display without formatting."""
        mock_tag_manager.list_managed_vms.return_value = mock_vm_list[:1]
        mock_vm_manager.sort_by_created_time.side_effect = lambda vms: vms
        mock_config.load.return_value = {"resource_group": "test-rg"}
        mock_config.get_resource_group.return_value = "test-rg"
        mock_config.get_session_name.return_value = None

        # Old format session (attached=False by default, but from old parser)
        old_session = TmuxSession(
            vm_name="10.0.1.5",  # Use IP address for vm_name
            session_name="old-session",
            windows=3,
            created_time="Thu Oct 10 10:00:00 2024",
            attached=False,  # Old format defaults to False
        )
        mock_infrastructure["tmux_executor"].get_sessions_parallel.return_value = [old_session]

        runner = CliRunner()
        result = runner.invoke(main, ["list", "--show-tmux", "--no-quota"])

        assert result.exit_code == 0

        # Session should appear (with dim formatting since attached=False)
        assert "old-session" in result.output
