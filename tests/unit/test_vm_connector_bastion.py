"""Unit tests for VM Connector Bastion integration.

Tests for Bastion-aware connection routing including:
- Auto-detection of Bastion availability
- Direct vs Bastion connection routing
- User prompts for Bastion usage
- Configuration-driven routing
- Error handling

These tests follow TDD approach - they will FAIL until implementation is complete.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_manager import BastionTunnel
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_manager import VMInfo


class TestBastionAutoDetection:
    """Test auto-detection of Bastion hosts."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
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

    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_auto_detect_no_bastion(
        self, mock_get_vm, mock_ensure_keys, mock_detect, vm_info, ssh_keys
    ):
        """Test connection when no Bastion is detected."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_detect.return_value = None  # No Bastion found

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0
            result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        mock_detect.assert_called_once_with("test-vm", "test-rg")
        # Should use direct connection
        mock_reconnect.return_value.connect_with_reconnect.assert_called_once()

    @patch("azlin.vm_connector.click.confirm")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_auto_detect_bastion_found_user_accepts(
        self, mock_get_vm, mock_ensure_keys, mock_detect, mock_confirm, vm_info, ssh_keys
    ):
        """Test prompting user when Bastion is detected."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_detect.return_value = {"name": "my-bastion", "resource_group": "bastion-rg"}
        mock_confirm.return_value = True  # User accepts Bastion

        # Act
        with patch("azlin.vm_connector.BastionManager") as mock_bastion_mgr:
            mock_tunnel = Mock(spec=BastionTunnel)
            mock_tunnel.local_port = 50022
            mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

            with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
                mock_reconnect.return_value.connect_with_reconnect.return_value = 0
                result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        mock_confirm.assert_called_once()
        # Should use Bastion tunnel
        mock_bastion_mgr.return_value.create_tunnel.assert_called_once()

    @patch("azlin.vm_connector.click.confirm")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_auto_detect_bastion_found_user_declines(
        self, mock_get_vm, mock_ensure_keys, mock_detect, mock_confirm, vm_info, ssh_keys
    ):
        """Test user declining Bastion connection."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_detect.return_value = {"name": "my-bastion", "resource_group": "bastion-rg"}
        mock_confirm.return_value = False  # User declines Bastion

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0
            result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        # Should use direct connection
        mock_reconnect.return_value.connect_with_reconnect.assert_called_once()

    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_auto_detect_disabled_in_config(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, vm_info, ssh_keys
    ):
        """Test auto-detection respects config setting."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys

        config = BastionConfig()
        config.auto_detect = False
        mock_load_config.return_value = config

        # Act
        with patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm") as mock_detect:
            with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
                mock_reconnect.return_value.connect_with_reconnect.return_value = 0
                result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        mock_detect.assert_not_called()  # Detection should be skipped


class TestBastionConnectionRouting:
    """Test routing connections through Bastion."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="10.0.1.5",  # Private IP (no direct access)
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

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_use_bastion_from_config(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_bastion_mgr, vm_info, ssh_keys
    ):
        """Test using Bastion based on config mapping."""
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

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50022
        mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0
            result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        mock_bastion_mgr.return_value.create_tunnel.assert_called_once()

        # Verify tunnel was created with correct parameters
        call_kwargs = mock_bastion_mgr.return_value.create_tunnel.call_args.kwargs
        assert call_kwargs["bastion_name"] == "my-bastion"
        assert call_kwargs["resource_group"] == "bastion-rg"

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_bastion_connection_via_localhost(
        self, mock_get_vm, mock_ensure_keys, mock_bastion_mgr, vm_info, ssh_keys
    ):
        """Test SSH connection goes through localhost tunnel."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50022
        mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

        # Act
        with patch("azlin.vm_connector.BastionConfig.load") as mock_load_config:
            config = BastionConfig()
            config.add_mapping(
                vm_name="test-vm",
                vm_resource_group="test-rg",
                bastion_name="my-bastion",
                bastion_resource_group="bastion-rg",
            )
            mock_load_config.return_value = config

            with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
                mock_reconnect.return_value.connect_with_reconnect.return_value = 0
                result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        # Verify SSH connects to localhost:50022, not VM IP
        call_kwargs = mock_reconnect.return_value.connect_with_reconnect.call_args.kwargs
        assert call_kwargs["config"].host == "localhost"
        assert call_kwargs["config"].port == 50022

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_bastion_tunnel_cleanup_on_error(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_bastion_mgr, vm_info, ssh_keys
    ):
        """Test tunnel is cleaned up if SSH connection fails."""
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

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50022
        mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.side_effect = Exception("SSH failed")

            with pytest.raises(Exception, match="SSH failed"):
                VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert - tunnel should be closed
        mock_bastion_mgr.return_value.close_tunnel.assert_called_once_with(mock_tunnel)

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_force_bastion_flag(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_bastion_mgr, vm_info, ssh_keys
    ):
        """Test forcing Bastion connection via flag."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_load_config.return_value = BastionConfig()

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50022
        mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

        # Act
        with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
            mock_reconnect.return_value.connect_with_reconnect.return_value = 0
            result = VMConnector.connect(
                vm_identifier="test-vm",
                resource_group="test-rg",
                force_bastion=True,
                bastion_name="my-bastion",
                bastion_resource_group="bastion-rg",
            )

        # Assert
        assert result is True
        mock_bastion_mgr.return_value.create_tunnel.assert_called_once()

    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_force_direct_connection(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, vm_info, ssh_keys
    ):
        """Test forcing direct connection (bypass Bastion)."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys

        # Config has Bastion mapping
        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        mock_load_config.return_value = config

        # Act
        with patch("azlin.vm_connector.BastionManager") as mock_bastion_mgr:
            with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
                mock_reconnect.return_value.connect_with_reconnect.return_value = 0
                result = VMConnector.connect(
                    vm_identifier="test-vm", resource_group="test-rg", force_direct=True
                )

        # Assert
        assert result is True
        mock_bastion_mgr.return_value.create_tunnel.assert_not_called()


class TestBastionErrorHandling:
    """Test error handling for Bastion connections."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="10.0.1.5",
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

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_bastion_tunnel_creation_fails(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_bastion_mgr, vm_info, ssh_keys
    ):
        """Test error when Bastion tunnel creation fails."""
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

        mock_bastion_mgr.return_value.create_tunnel.side_effect = Exception("Bastion not found")

        # Act & Assert
        with pytest.raises(VMConnectorError, match="Failed to create Bastion tunnel"):
            VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_bastion_not_in_same_vnet(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_bastion_mgr, vm_info, ssh_keys
    ):
        """Test error when Bastion is not in same VNet as VM."""
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

        mock_bastion_mgr.return_value.create_tunnel.side_effect = Exception(
            "Bastion must be in same VNet as target VM"
        )

        # Act & Assert
        with pytest.raises(VMConnectorError, match="same VNet"):
            VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_missing_bastion_in_force_mode(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, vm_info, ssh_keys
    ):
        """Test error when forcing Bastion but not specifying which one."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_load_config.return_value = BastionConfig()

        # Act & Assert
        with pytest.raises(VMConnectorError, match="Bastion name required"):
            VMConnector.connect(
                vm_identifier="test-vm",
                resource_group="test-rg",
                force_bastion=True,
                # Missing bastion_name and bastion_resource_group
            )


class TestBastionFileTransfer:
    """Test file transfer through Bastion tunnel."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="10.0.1.5",
        )

    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_file_transfer_via_bastion(
        self, mock_get_vm, mock_ensure_keys, mock_load_config, mock_bastion_mgr, vm_info
    ):
        """Test SCP/SFTP works through Bastion tunnel."""
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

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50022
        mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

        # Act
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0

            from azlin.modules.file_transfer import FileTransfer

            FileTransfer.upload_file(
                vm_name="test-vm",
                resource_group="test-rg",
                local_path="/tmp/test.txt",
                remote_path="/home/user/test.txt",
            )

        # Assert - should use localhost:50022
        call_args = mock_subprocess.call_args[0][0]
        assert "localhost" in " ".join(call_args)
        assert "50022" in " ".join(call_args)


class TestBastionPreferences:
    """Test Bastion preference settings."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
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

    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionConfig.load")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_prefer_bastion_setting(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_load_config,
        mock_bastion_mgr,
        mock_detect,
        vm_info,
        ssh_keys,
    ):
        """Test prefer_bastion setting auto-uses Bastion without prompting."""
        # Arrange
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_detect.return_value = {"name": "my-bastion", "resource_group": "bastion-rg"}

        config = BastionConfig()
        config.prefer_bastion = True
        mock_load_config.return_value = config

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50022
        mock_bastion_mgr.return_value.create_tunnel.return_value = mock_tunnel

        # Act
        with patch("azlin.vm_connector.click.confirm") as mock_confirm:
            with patch("azlin.vm_connector.SSHReconnectHandler") as mock_reconnect:
                mock_reconnect.return_value.connect_with_reconnect.return_value = 0
                result = VMConnector.connect(vm_identifier="test-vm", resource_group="test-rg")

        # Assert
        assert result is True
        mock_confirm.assert_not_called()  # No prompt with prefer_bastion=True
        mock_bastion_mgr.return_value.create_tunnel.assert_called_once()
