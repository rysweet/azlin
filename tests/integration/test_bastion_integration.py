"""Integration tests for Azure Bastion feature.

Tests end-to-end workflows including:
- Bastion deployment and configuration
- Connection through Bastion tunnel
- File transfer through Bastion
- Configuration persistence
- Auto-detection and user experience

These tests follow TDD approach - they will FAIL until implementation is complete.
Integration tests use mocked Azure CLI but test full component interaction.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_manager import BastionManager
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMInfo


class TestBastionDeploymentWorkflow:
    """Test complete Bastion deployment workflow."""

    @pytest.fixture
    def mock_az_cli(self):
        """Mock Azure CLI calls."""
        with patch("subprocess.run") as mock_run:

            def az_side_effect(cmd, *args, **kwargs):
                if "bastion" in cmd and "create" in cmd:
                    return Mock(
                        returncode=0,
                        stdout='{"provisioningState": "Succeeded", "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/bastionHosts/my-bastion"}',
                    )
                if "bastion" in cmd and "list" in cmd:
                    return Mock(
                        returncode=0,
                        stdout='[{"name": "my-bastion", "resourceGroup": "bastion-rg", "provisioningState": "Succeeded"}]',
                    )
                if "bastion" in cmd and "show" in cmd:
                    return Mock(
                        returncode=0,
                        stdout='{"name": "my-bastion", "provisioningState": "Succeeded", "ipConfigurations": [{"subnet": {"id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/AzureBastionSubnet"}}]}',
                    )
                if "bastion" in cmd and "delete" in cmd:
                    return Mock(returncode=0, stdout="")
                return Mock(returncode=0, stdout="")

            mock_run.side_effect = az_side_effect
            yield mock_run

    def test_deploy_bastion_host(self, mock_az_cli):
        """Test deploying new Bastion host."""
        # Arrange
        from azlin.modules.bastion_deployment import BastionDeployment

        # Act
        bastion_info = BastionDeployment.create_bastion(
            bastion_name="my-bastion",
            resource_group="bastion-rg",
            vnet_name="my-vnet",
            location="westus2",
        )

        # Assert
        assert bastion_info is not None
        assert bastion_info["name"] == "my-bastion"
        assert bastion_info["provisioningState"] == "Succeeded"

        # Verify az command was called
        mock_az_cli.assert_called()
        call_args = " ".join(mock_az_cli.call_args[0][0])
        assert "az network bastion create" in call_args
        assert "AzureBastionSubnet" in call_args

    def test_list_bastion_hosts(self, mock_az_cli):
        """Test listing Bastion hosts in resource group."""
        # Arrange
        from azlin.modules.bastion_deployment import BastionDeployment

        # Act
        bastions = BastionDeployment.list_bastions(resource_group="bastion-rg")

        # Assert
        assert len(bastions) > 0
        assert bastions[0]["name"] == "my-bastion"

    def test_get_bastion_status(self, mock_az_cli):
        """Test getting Bastion host status."""
        # Arrange
        from azlin.modules.bastion_deployment import BastionDeployment

        # Act
        status = BastionDeployment.get_bastion_status(
            bastion_name="my-bastion", resource_group="bastion-rg"
        )

        # Assert
        assert status["provisioningState"] == "Succeeded"

    def test_delete_bastion_host(self, mock_az_cli):
        """Test deleting Bastion host."""
        # Arrange
        from azlin.modules.bastion_deployment import BastionDeployment

        # Act
        result = BastionDeployment.delete_bastion(
            bastion_name="my-bastion", resource_group="bastion-rg"
        )

        # Assert
        assert result is True

        # Verify delete command was called
        mock_az_cli.assert_called()
        call_args = " ".join(mock_az_cli.call_args[0][0])
        assert "az network bastion delete" in call_args


class TestBastionConnectionWorkflow:
    """Test complete connection workflow through Bastion."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create temporary config directory."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        return config_dir

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="10.0.1.5",
            vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        )

    @pytest.fixture
    def ssh_keys(self, tmp_path):
        """Create test SSH keys."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHKeyPair(
            private_path=key_file,
            public_path=tmp_path / "test_key.pub",
            public_key_content="ssh-ed25519 AAAA...",
        )

    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_end_to_end_bastion_connection(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_load_config,
        mock_popen,
        vm_info,
        ssh_keys,
        temp_config_dir,
    ):
        """Test complete workflow: config -> tunnel -> SSH connection."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys

        # Create config with Bastion mapping
        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        mock_load_config.return_value = config

        # Mock tunnel process
        mock_tunnel_process = Mock()
        mock_tunnel_process.poll.return_value = None
        mock_tunnel_process.pid = 12345
        mock_popen.return_value = mock_tunnel_process

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0

            result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True

        # Verify tunnel was created
        assert mock_popen.called
        tunnel_cmd = mock_popen.call_args[0][0]
        assert "az" in tunnel_cmd
        assert "bastion" in tunnel_cmd
        assert "tunnel" in tunnel_cmd

        # Verify SSH used localhost tunnel
        ssh_call = mock_reconnect.return_value.connect_with_reconnect.call_args.kwargs
        assert ssh_call["config"].host == "localhost"

    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.click.confirm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_auto_detect_and_prompt_workflow(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_confirm,
        mock_detect,
        mock_popen,
        vm_info,
        ssh_keys,
    ):
        """Test workflow: auto-detect Bastion -> prompt user -> create tunnel -> connect."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_detect.return_value = {"name": "detected-bastion", "resource_group": "bastion-rg"}
        mock_confirm.return_value = True  # User accepts

        # Mock tunnel process
        mock_tunnel_process = Mock()
        mock_tunnel_process.poll.return_value = None
        mock_popen.return_value = mock_tunnel_process

        # Act
        with patch("azlin.vm_connector.BastionConfig.load") as mock_load_config:
            mock_load_config.return_value = BastionConfig()  # No existing mapping

            with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
                mock_reconnect.return_value.connect_with_reconnect.return_value = 0

                result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        mock_detect.assert_called_once()
        mock_confirm.assert_called_once()

        # Verify prompt message contains Bastion info
        prompt_msg = mock_confirm.call_args[0][0]
        assert "detected-bastion" in prompt_msg

    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_config_persistence_workflow(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, vm_info, ssh_keys, temp_config_dir
    ):
        """Test saving and loading Bastion configuration."""
        # Arrange
        config_file = temp_config_dir / "bastion_config.toml"

        # Act - Create and save config
        config1 = BastionConfig()
        config1.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        config1.set_default_bastion("default-bastion", "default-rg")
        config1.save(config_file)

        # Load config in new instance
        config2 = BastionConfig.load(config_file)

        # Assert
        assert "test-vm" in config2.mappings
        assert config2.mappings["test-vm"].bastion_name == "my-bastion"
        assert config2.default_bastion == ("default-bastion", "default-rg")

    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_tunnel_reuse_same_vm(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_popen, vm_info, ssh_keys
    ):
        """Test reusing existing tunnel for multiple connections to same VM."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys

        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        mock_load_config.return_value = config

        # Mock tunnel process
        mock_tunnel_process = Mock()
        mock_tunnel_process.poll.return_value = None
        mock_popen.return_value = mock_tunnel_process

        manager = BastionManager()

        # Act - Create first tunnel
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0
            tunnel1 = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="bastion-rg",
                target_vm_id=vm_info.vm_id,
                local_port=50022,
                remote_port=22,
            )

            # Try to connect again - should reuse tunnel
            existing_tunnel = manager.get_tunnel_by_port(50022)

        # Assert
        assert existing_tunnel == tunnel1
        assert mock_popen.call_count == 1  # Tunnel created only once


class TestBastionFileTransferWorkflow:
    """Test file transfer through Bastion workflow."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="10.0.1.5",
            vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        )

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create temporary file for upload."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, Bastion!")
        return test_file

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_file_upload_via_bastion(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_load_config,
        mock_popen,
        mock_run,
        vm_info,
        temp_file,
    ):
        """Test uploading file through Bastion tunnel."""
        # Arrange
        mock_get_vm.return_value = vm_info
        key_file = Path("/tmp/test_key")
        ssh_keys = SSHKeyPair(
            private_path=key_file,
            public_path=Path("/tmp/test_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ensure_keys.return_value = ssh_keys

        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        mock_load_config.return_value = config

        # Mock tunnel
        mock_tunnel_process = Mock()
        mock_tunnel_process.poll.return_value = None
        mock_popen.return_value = mock_tunnel_process

        # Mock scp
        mock_run.return_value = Mock(returncode=0)

        # Act
        from azlin.modules.file_transfer import FileTransfer

        with patch("azlin.modules.file_transfer.BastionManager") as mock_bastion_mgr:
            mock_tunnel = Mock()
            mock_tunnel.local_port = 50022
            mock_tunnel.is_active.return_value = True
            mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

            result = FileTransfer.upload_file(
                vm_name="test-vm",
                resource_group="test-rg",
                local_path=str(temp_file),
                remote_path="/home/azureuser/test.txt",
            )

        # Assert
        assert result is True

        # Verify scp used localhost tunnel
        scp_call_args = " ".join(mock_run.call_args[0][0])
        assert "localhost" in scp_call_args
        assert "50022" in scp_call_args

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_file_download_via_bastion(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_load_config,
        mock_popen,
        mock_run,
        vm_info,
        tmp_path,
    ):
        """Test downloading file through Bastion tunnel."""
        # Arrange
        mock_get_vm.return_value = vm_info
        key_file = Path("/tmp/test_key")
        ssh_keys = SSHKeyPair(
            private_path=key_file,
            public_path=Path("/tmp/test_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ensure_keys.return_value = ssh_keys

        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        mock_load_config.return_value = config

        # Mock tunnel
        mock_tunnel_process = Mock()
        mock_tunnel_process.poll.return_value = None
        mock_popen.return_value = mock_tunnel_process

        # Mock scp
        mock_run.return_value = Mock(returncode=0)

        local_file = tmp_path / "downloaded.txt"

        # Act
        from azlin.modules.file_transfer import FileTransfer

        with patch("azlin.modules.file_transfer.BastionManager") as mock_bastion_mgr:
            mock_tunnel = Mock()
            mock_tunnel.local_port = 50022
            mock_tunnel.is_active.return_value = True
            mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

            result = FileTransfer.download_file(
                vm_name="test-vm",
                resource_group="test-rg",
                remote_path="/home/azureuser/test.txt",
                local_path=str(local_file),
            )

        # Assert
        assert result is True


class TestBastionErrorRecovery:
    """Test error recovery scenarios."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="10.0.1.5",
            vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        )

    @pytest.fixture
    def ssh_keys(self, tmp_path):
        """Create test SSH keys."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHKeyPair(
            private_path=key_file,
            public_path=tmp_path / "test_key.pub",
            public_key_content="ssh-ed25519 AAAA...",
        )

    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_tunnel_dies_during_connection(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_popen, vm_info, ssh_keys
    ):
        """Test handling when tunnel dies during SSH connection."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys

        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        mock_load_config.return_value = config

        # Mock tunnel process that dies
        mock_tunnel_process = Mock()
        mock_tunnel_process.poll.side_effect = [None, None, 1]  # Dies on third check
        mock_popen.return_value = mock_tunnel_process

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            # SSH fails because tunnel died
            mock_reconnect.return_value.connect_with_reconnect.return_value = 255

            result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is False

    @patch("subprocess.Popen")
    @patch("azlin.vm_connector.click.confirm")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_fallback_to_direct_on_bastion_failure(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_load_config,
        mock_detect,
        mock_confirm,
        mock_popen,
        vm_info,
        ssh_keys,
    ):
        """Test falling back to direct connection if Bastion fails."""
        # Arrange
        vm_info.public_ip = "20.1.2.3"  # Has public IP for direct access
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_load_config.return_value = BastionConfig()
        mock_detect.return_value = {"name": "my-bastion", "resource_group": "bastion-rg"}
        mock_confirm.return_value = True  # User wants Bastion

        # Mock tunnel creation failure
        mock_popen.side_effect = Exception("Bastion connection failed")

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            # Should fallback to direct connection
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0

            with patch("azlin.vm_connector.click.confirm") as mock_fallback_confirm:
                mock_fallback_confirm.return_value = True  # User accepts fallback

                result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        # Should have prompted about fallback
        assert mock_fallback_confirm.call_count >= 1


class TestBastionMultiVMScenarios:
    """Test scenarios with multiple VMs and Bastions."""

    @patch("subprocess.Popen")
    def test_multiple_tunnels_concurrent(self, mock_popen):
        """Test managing multiple concurrent Bastion tunnels."""
        # Arrange
        mock_process1 = Mock()
        mock_process1.poll.return_value = None
        mock_process2 = Mock()
        mock_process2.poll.return_value = None
        mock_popen.side_effect = [mock_process1, mock_process2]

        manager = BastionManager()

        # Act
        tunnel1 = manager.create_tunnel(
            bastion_name="bastion1",
            resource_group="rg1",
            target_vm_id="/subscriptions/sub/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1",
            local_port=50022,
            remote_port=22,
        )

        tunnel2 = manager.create_tunnel(
            bastion_name="bastion2",
            resource_group="rg2",
            target_vm_id="/subscriptions/sub/resourceGroups/rg2/providers/Microsoft.Compute/virtualMachines/vm2",
            local_port=50023,
            remote_port=22,
        )

        # Assert
        assert len(manager.active_tunnels) == 2
        assert tunnel1.local_port != tunnel2.local_port
        assert mock_popen.call_count == 2

    @patch("subprocess.Popen")
    def test_shared_bastion_multiple_vms(self, mock_popen):
        """Test using same Bastion for multiple VMs."""
        # Arrange
        mock_process1 = Mock()
        mock_process1.poll.return_value = None
        mock_process2 = Mock()
        mock_process2.poll.return_value = None
        mock_popen.side_effect = [mock_process1, mock_process2]

        manager = BastionManager()

        # Act - Same Bastion, different VMs
        tunnel1 = manager.create_tunnel(
            bastion_name="shared-bastion",
            resource_group="bastion-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            local_port=50022,
            remote_port=22,
        )

        tunnel2 = manager.create_tunnel(
            bastion_name="shared-bastion",
            resource_group="bastion-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm2",
            local_port=50023,
            remote_port=22,
        )

        # Assert
        assert tunnel1.bastion_name == tunnel2.bastion_name
        assert tunnel1.local_port != tunnel2.local_port
        assert len(manager.active_tunnels) == 2
