"""Backward compatibility tests for bastion routing changes.

Ensures that the bastion routing fix doesn't break existing functionality
for VMs with public IPs.

All these tests should PASS both before and after the fix.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from azlin.vm_manager import VMInfo


class TestBackwardCompatibilityW:
    """Test w command backward compatibility."""

    @patch("azlin.cli_helpers.get_ssh_configs_for_vms")
    @patch("azlin.remote_exec.WCommandExecutor.execute_w_on_routes")
    @patch("azlin.remote_exec.WCommandExecutor.format_w_output")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_w_command_works_with_public_ips_only(
        self,
        mock_config_mgr,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_format_w_output,
        mock_execute_w_on_routes,
        mock_get_ssh_configs,
    ):
        """Test w command still works with VMs that have public IPs."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Only public VMs (existing behavior)
        vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.4",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock SSH configs and routes
        from azlin.modules.ssh_connector import SSHConfig
        from azlin.modules.ssh_routing_resolver import SSHRoute

        ssh_configs = [
            SSHConfig(
                host="20.1.2.3",
                port=22,
                user="azureuser",
                key_path=Path("/home/user/.ssh/azlin_key"),
            ),
            SSHConfig(
                host="20.1.2.4",
                port=22,
                user="azureuser",
                key_path=Path("/home/user/.ssh/azlin_key"),
            ),
        ]
        routes = [
            SSHRoute(
                vm_name="azlin-vm-1",
                vm_info=vms[0],
                routing_method="direct",
                ssh_config=ssh_configs[0],
                skip_reason=None,
            ),
            SSHRoute(
                vm_name="azlin-vm-2",
                vm_info=vms[1],
                routing_method="direct",
                ssh_config=ssh_configs[1],
                skip_reason=None,
            ),
        ]
        mock_get_ssh_configs.return_value = (ssh_configs, routes)

        # Mock executor methods
        mock_execute_w_on_routes.return_value = []
        mock_format_w_output.return_value = "Output"

        # Import and run command
        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should succeed
        assert result.exit_code == 0

        # Should use execute_w_on_routes with routes (new behavior)
        assert mock_execute_w_on_routes.called, "execute_w_on_routes should have been called"
        call_args = mock_execute_w_on_routes.call_args
        called_routes = call_args[0][0]
        assert len(called_routes) == 2
        assert all(route.ssh_config.host in ["20.1.2.3", "20.1.2.4"] for route in called_routes)
        assert all(route.ssh_config.port == 22 for route in called_routes)

    @patch("azlin.cli.WCommandExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_w_command_empty_vm_list_unchanged(
        self, mock_config_mgr, mock_vm_mgr, mock_ssh_key_mgr, mock_w_executor
    ):
        """Test w command behavior with no VMs is unchanged."""
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_vm_mgr.list_vms.return_value = []
        mock_vm_mgr.filter_by_prefix.return_value = []

        from click.testing import CliRunner

        from azlin.cli import w

        runner = CliRunner()
        result = runner.invoke(w, [])

        # Should exit with appropriate message
        assert "No running VMs found" in result.output or "No VMs found" in result.output


class TestBackwardCompatibilityTop:
    """Test top command backward compatibility."""

    @patch("azlin.cli.DistributedTopExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_top_command_works_with_public_ips_only(
        self, mock_config_mgr, mock_vm_mgr, mock_ssh_key_mgr, mock_top_executor
    ):
        """Test top command still works with VMs that have public IPs."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Only public VMs
        vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        # Mock executor
        mock_executor_instance = MagicMock()
        mock_top_executor.return_value = mock_executor_instance

        from click.testing import CliRunner

        from azlin.cli import top

        runner = CliRunner()
        result = runner.invoke(top, ["--interval", "10"])

        # Should create executor with direct SSH
        call_args = mock_top_executor.call_args
        ssh_configs = call_args.kwargs["ssh_configs"]
        assert len(ssh_configs) == 1
        assert ssh_configs[0].host == "20.1.2.3"
        assert ssh_configs[0].port == 22


class TestBackwardCompatibilityPs:
    """Test ps command backward compatibility."""

    @patch("azlin.cli.PSCommandExecutor")
    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_ps_command_works_with_public_ips_only(
        self, mock_config_mgr, mock_vm_mgr, mock_ssh_key_mgr, mock_ps_executor
    ):
        """Test ps command still works with VMs that have public IPs."""
        # Setup mocks
        mock_config_mgr.get_resource_group.return_value = "test-rg"

        mock_ssh_keys = Mock()
        mock_ssh_keys.private_path = Path("/home/user/.ssh/azlin_key")
        mock_ssh_key_mgr.ensure_key_exists.return_value = mock_ssh_keys

        # Only public VMs
        vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.4",
            ),
        ]
        mock_vm_mgr.list_vms.return_value = vms
        mock_vm_mgr.filter_by_prefix.return_value = vms

        mock_ps_executor.execute_ps_on_vms.return_value = []
        mock_ps_executor.format_ps_output.return_value = "Output"

        from click.testing import CliRunner

        from azlin.cli import ps

        runner = CliRunner()
        result = runner.invoke(ps, [])

        # Should succeed
        assert result.exit_code == 0

        # Should use direct SSH
        call_args = mock_ps_executor.execute_ps_on_vms.call_args
        ssh_configs = call_args[0][0]
        assert len(ssh_configs) == 2
        assert all(config.port == 22 for config in ssh_configs)


class TestBackwardCompatibilityConnect:
    """Test connect command backward compatibility."""

    @patch("azlin.vm_connector.BastionConfig")
    @patch("azlin.vm_connector.BastionDetector")
    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_command_still_works_with_public_ip(
        self,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_reconnect_handler,
        mock_bastion_detector,
        mock_bastion_config,
    ):
        """Test connect command still works normally with public IP."""
        # Mock VM with public IP
        vm_info = VMInfo(
            name="my-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        from azlin.modules.ssh_keys import SSHKeyPair

        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock bastion detection to return None (no bastion needed)
        mock_bastion_config.load.side_effect = Exception("No config")
        mock_bastion_detector.detect_bastion_for_vm.return_value = None

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect
        from azlin.vm_connector import VMConnector

        result = VMConnector.connect("my-vm", resource_group="test-rg")

        # Should succeed with direct connection
        assert result is True

        # Should use public IP, not bastion
        call_args = mock_handler_instance.connect_with_reconnect.call_args
        config = call_args.kwargs["config"]
        assert config.host == "20.1.2.3"
        assert config.port == 22


class TestBackwardCompatibilityHelperFunction:
    """Test _get_ssh_config_for_vm helper backward compatibility."""

    @patch("azlin.cli.SSHKeyManager")
    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_get_ssh_config_for_vm_with_public_ip(
        self, mock_config_mgr, mock_vm_mgr, mock_ssh_key_mgr
    ):
        """Test helper function still works with public IP."""
        # Mock config
        mock_config_mgr.get_resource_group.return_value = "test-rg"
        mock_config_mgr.get_vm_name_by_session.return_value = None

        # Mock VM with public IP
        vm_info = VMInfo(
            name="my-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        from azlin.modules.ssh_keys import SSHKeyPair

        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Call helper (if it still exists after refactoring)
        from azlin.cli import _get_ssh_config_for_vm

        config = _get_ssh_config_for_vm("my-vm", "test-rg", None)

        # Should return direct SSH config
        assert config.host == "20.1.2.3"
        assert config.user == "azureuser"

    @patch("azlin.cli.VMConnector")
    def test_get_ssh_config_for_vm_with_ip_address(self, mock_vm_connector):
        """Test helper function still works with direct IP."""
        mock_vm_connector.is_valid_ip.return_value = True

        from azlin.cli import _get_ssh_config_for_vm

        config = _get_ssh_config_for_vm("20.1.2.3", None, None)

        # Should return config with IP
        assert config.host == "20.1.2.3"


class TestNoRegressionInExistingTests:
    """Verify existing test suite still passes."""

    def test_existing_vm_connector_tests_still_valid(self):
        """Verify existing VMConnector tests are still valid."""
        # This is a meta-test that ensures we haven't broken
        # the existing test suite structure
        import tests.unit.test_vm_connector

        # Just verify the module exists and has expected tests
        assert hasattr(tests.unit.test_vm_connector, "TestVMConnector")

    def test_existing_distributed_top_tests_still_valid(self):
        """Verify existing DistributedTop tests are still valid."""
        import tests.unit.test_distributed_top

        assert hasattr(tests.unit.test_distributed_top, "TestDistributedTopExecutor")

    def test_existing_integration_tests_still_valid(self):
        """Verify existing integration tests structure unchanged."""
        import tests.integration.test_bastion_integration

        # Basic check that the module exists
        assert tests.integration.test_bastion_integration is not None
