"""Integration tests for multi-VM commands with bastion routing.

Tests commands like `azlin w`, `azlin top`, `azlin ps` with VMs that
require bastion connectivity (no public IP).

Following TDD approach - these tests should FAIL initially and PASS
after implementing bastion routing support.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from azlin.vm_manager import VMInfo


class TestWCommandWithBastion:
    """Test 'w' command with bastion-only VMs."""

    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.WCommandExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_w_command_includes_private_vms(
        self,
        mock_config_mgr,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_w_executor,
        mock_bastion_mgr,
    ):
        """Test w command includes VMs without public IPs using bastion."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Mix of public and private VMs
        vms = [
            VMInfo(
                name="azlin-public-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
                private_ip="10.0.0.1",
            ),
            VMInfo(
                name="azlin-private-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock bastion tunnel
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel
        mock_bastion_mgr.return_value = mock_bastion

        # Mock w command results
        mock_w_executor.execute_w_on_vms.return_value = [
            {"vm": "20.1.2.3", "output": "user1 logged in"},
            {"vm": "127.0.0.1:50022", "output": "user2 logged in"},
        ]
        mock_w_executor.format_w_output.return_value = "Formatted output"

        # Import and run command
        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should succeed
        assert result.exit_code == 0

        # Should execute w on BOTH VMs (not just the public one)
        call_args = mock_w_executor.execute_w_on_vms.call_args
        ssh_configs = call_args[0][0]
        assert len(ssh_configs) == 2

        # First config should be direct
        assert ssh_configs[0].host == "20.1.2.3"
        assert ssh_configs[0].port == 22

        # Second config should use bastion tunnel
        assert ssh_configs[1].host == "127.0.0.1"
        assert ssh_configs[1].port == 50022

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_w_command_skips_stopped_vms(self, mock_config_mgr, mock_vm_mgr):
        """Test w command skips stopped VMs."""
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        vms = [
            VMInfo(
                name="azlin-running-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
            ),
            VMInfo(
                name="azlin-stopped-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM stopped",
                public_ip="20.1.2.4",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should only process running VM
        # (Implementation detail - verify in actual test execution)

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_w_command_fails_gracefully_no_reachable_vms(self, mock_config_mgr, mock_vm_mgr):
        """Test w command handles case with no reachable VMs."""
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        # Only stopped or unreachable VMs
        vms = [
            VMInfo(
                name="azlin-stopped-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM stopped",
                public_ip="20.1.2.4",
            ),
            VMInfo(
                name="azlin-no-ip-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip=None,
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should exit gracefully with message
        assert "No reachable VMs found" in result.output or "No running VMs" in result.output


class TestTopCommandWithBastion:
    """Test 'top' command with bastion-only VMs."""

    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.DistributedTopExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_top_command_includes_private_vms(
        self,
        mock_config_mgr,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_top_executor,
        mock_bastion_mgr,
    ):
        """Test top command includes VMs without public IPs using bastion."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Mix of public and private VMs
        vms = [
            VMInfo(
                name="azlin-public-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
                private_ip="10.0.0.1",
            ),
            VMInfo(
                name="azlin-private-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock bastion tunnel
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel
        mock_bastion_mgr.return_value = mock_bastion

        # Mock top executor
        mock_executor_instance = MagicMock()
        mock_top_executor.return_value = mock_executor_instance

        # Import and run command
        from click.testing import CliRunner

        from azlin.cli import top

        runner = CliRunner()
        # Use iterations=1 to prevent infinite loop
        result = runner.invoke(top, ["--interval", "10"])

        # Should create executor with BOTH VMs
        call_args = mock_top_executor.call_args
        ssh_configs = call_args.kwargs["ssh_configs"]
        assert len(ssh_configs) == 2

        # First config should be direct
        assert ssh_configs[0].host == "20.1.2.3"
        assert ssh_configs[0].port == 22

        # Second config should use bastion tunnel
        assert ssh_configs[1].host == "127.0.0.1"
        assert ssh_configs[1].port == 50022


class TestPsCommandWithBastion:
    """Test 'ps' command with bastion-only VMs."""

    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.PSCommandExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_ps_command_includes_private_vms(
        self,
        mock_config_mgr,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_ps_executor,
        mock_bastion_mgr,
    ):
        """Test ps command includes VMs without public IPs using bastion."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Mix of public and private VMs
        vms = [
            VMInfo(
                name="azlin-public-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
                private_ip="10.0.0.1",
            ),
            VMInfo(
                name="azlin-private-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock bastion tunnel
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel
        mock_bastion_mgr.return_value = mock_bastion

        # Mock ps command results
        mock_ps_executor.execute_ps_on_vms.return_value = [
            {"vm": "20.1.2.3", "output": "process1"},
            {"vm": "127.0.0.1:50022", "output": "process2"},
        ]
        mock_ps_executor.format_ps_output.return_value = "Formatted output"

        # Import and run command
        from click.testing import CliRunner

        from azlin.cli import ps

        runner = CliRunner()
        result = runner.invoke(ps, [])

        # Should succeed
        assert result.exit_code == 0

        # Should execute ps on BOTH VMs
        call_args = mock_ps_executor.execute_ps_on_vms.call_args
        ssh_configs = call_args[0][0]
        assert len(ssh_configs) == 2

        # Verify configs use appropriate routing
        assert ssh_configs[0].host == "20.1.2.3"
        assert ssh_configs[1].host == "127.0.0.1"
        assert ssh_configs[1].port == 50022


class TestBastionTunnelReuse:
    """Test bastion tunnel reuse across multiple SSH connections."""

    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.WCommandExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_single_tunnel_for_multiple_private_vms(
        self,
        mock_config_mgr,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_w_executor,
        mock_bastion_mgr,
    ):
        """Test single bastion can serve multiple private VMs."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Multiple private VMs in same VNet
        vms = [
            VMInfo(
                name="azlin-private-vm-1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
            VMInfo(
                name="azlin-private-vm-2",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.3",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock bastion manager
        mock_bastion = MagicMock()
        mock_tunnel1 = Mock()
        mock_tunnel1.local_port = 50022
        mock_tunnel2 = Mock()
        mock_tunnel2.local_port = 50023
        mock_bastion.create_tunnel.side_effect = [mock_tunnel1, mock_tunnel2]
        mock_bastion_mgr.return_value = mock_bastion

        mock_w_executor.execute_w_on_vms.return_value = []
        mock_w_executor.format_w_output.return_value = ""

        # Run command
        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should create separate tunnels for each VM
        # (Each VM needs its own tunnel to its specific resource ID)
        assert mock_bastion.create_tunnel.call_count == 2


class TestErrorHandling:
    """Test error handling for bastion connectivity issues."""

    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_command_handles_bastion_not_available(
        self, mock_config_mgr, mock_vm_mgr, mock_bastion_mgr
    ):
        """Test graceful failure when bastion not available for private VM."""
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        vms = [
            VMInfo(
                name="azlin-private-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock bastion manager to fail
        mock_bastion_mgr.side_effect = Exception("No bastion found")

        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should fail with helpful error
        assert result.exit_code != 0
        assert "bastion" in result.output.lower() or "connectivity" in result.output.lower()

    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.WCommandExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_command_continues_with_mixed_success(
        self,
        mock_config_mgr,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_w_executor,
        mock_bastion_mgr,
    ):
        """Test command continues when some VMs fail but others succeed."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        vms = [
            VMInfo(
                name="azlin-public-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
            ),
            VMInfo(
                name="azlin-private-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock bastion to fail for private VM
        mock_bastion = MagicMock()
        mock_bastion.create_tunnel.side_effect = Exception("Tunnel failed")
        mock_bastion_mgr.return_value = mock_bastion

        # Mock w executor to return partial results
        mock_w_executor.execute_w_on_vms.return_value = [
            {"vm": "20.1.2.3", "output": "user1 logged in", "success": True},
        ]
        mock_w_executor.format_w_output.return_value = "Partial output"

        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should show results from successful VM
        # and indicate failure for private VM
        # (exact behavior depends on implementation)
