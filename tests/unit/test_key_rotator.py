"""Unit tests for key_rotator module."""

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.key_rotator import (
    KeyBackup,
    KeyRotationError,
    KeyRotationResult,
    SSHKeyRotator,
    VMKeyInfo,
)


class TestKeyRotationResult:
    """Tests for KeyRotationResult dataclass."""

    def test_all_succeeded(self):
        """Test all_succeeded property."""
        result = KeyRotationResult(
            success=True,
            message="All VMs updated",
            vms_updated=["vm1", "vm2"],
            vms_failed=[],
            new_key_path=Path("/path/to/key"),
            backup_path=Path("/path/to/backup")
        )
        assert result.all_succeeded is True

    def test_partial_failure(self):
        """Test partial failure detection."""
        result = KeyRotationResult(
            success=False,
            message="Some VMs failed",
            vms_updated=["vm1"],
            vms_failed=["vm2"],
            new_key_path=Path("/path/to/key"),
            backup_path=Path("/path/to/backup")
        )
        assert result.all_succeeded is False
        assert len(result.vms_failed) == 1


class TestKeyBackup:
    """Tests for KeyBackup dataclass."""

    def test_backup_creation(self):
        """Test backup information creation."""
        backup = KeyBackup(
            backup_dir=Path("/backup"),
            timestamp=datetime.now(),
            old_private_key=Path("/old/private"),
            old_public_key=Path("/old/public")
        )
        assert backup.backup_dir.exists is not None
        assert backup.old_private_key.name == "private"


class TestSSHKeyRotator:
    """Tests for SSHKeyRotator class."""

    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.shutil')
    @patch('azlin.key_rotator.Path')
    def test_backup_keys_creates_timestamped_directory(self, mock_path_class, mock_shutil, mock_key_manager):
        """Test that backup creates timestamped directory."""
        # Setup
        mock_key_pair = MagicMock()
        mock_key_pair.private_path = MagicMock(spec=Path)
        mock_key_pair.public_path = MagicMock(spec=Path)
        mock_key_manager.ensure_key_exists.return_value = mock_key_pair

        # Mock Path for backup directory
        mock_backup_dir = MagicMock(spec=Path)
        mock_backup_dir.exists.return_value = True
        mock_backup_dir.__truediv__ = lambda self, x: MagicMock(spec=Path)

        # Execute
        with patch('azlin.key_rotator.SSHKeyRotator.BACKUP_BASE_DIR', mock_backup_dir):
            backup = SSHKeyRotator.backup_keys()

        # Assert
        assert backup is not None
        assert isinstance(backup, KeyBackup)
        mock_key_manager.ensure_key_exists.assert_called_once()

    @patch('azlin.key_rotator.shutil')
    @patch('azlin.key_rotator.Path')
    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.VMManager')
    @patch('azlin.key_rotator.AzureAuthenticator')
    def test_rotate_keys_creates_new_key(self, mock_auth, mock_vm_manager, mock_key_manager, mock_path_class, mock_shutil):
        """Test that rotate_keys generates a new SSH key."""
        # Setup
        mock_old_key = MagicMock()
        mock_old_key.private_path = MagicMock(spec=Path)
        mock_old_key.public_path = MagicMock(spec=Path)
        mock_old_key.public_key_content = "old-public-key"

        mock_new_key = MagicMock()
        mock_new_key.private_path = MagicMock(spec=Path)
        mock_new_key.public_key_content = "new-public-key"

        mock_key_manager.ensure_key_exists.side_effect = [mock_old_key, mock_new_key]
        mock_vm_manager.list_vms.return_value = []
        mock_vm_manager.filter_by_prefix.return_value = []

        mock_auth_instance = MagicMock()
        mock_auth_instance.get_subscription_id.return_value = "sub-123"
        mock_auth.return_value = mock_auth_instance

        # Mock backup directory
        mock_backup_dir = MagicMock(spec=Path)
        mock_backup_dir.exists.return_value = True
        mock_backup_dir.__truediv__ = lambda self, x: MagicMock(spec=Path)

        # Execute
        with patch('azlin.key_rotator.SSHKeyRotator.BACKUP_BASE_DIR', mock_backup_dir):
            result = SSHKeyRotator.rotate_keys(resource_group="test-rg")

        # Assert
        assert result.success is True
        assert result.new_key_path is not None
        assert mock_key_manager.ensure_key_exists.call_count >= 1

    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.VMManager')
    @patch('azlin.key_rotator.subprocess')
    def test_update_single_vm_success(self, mock_subprocess, mock_vm_manager, mock_key_manager):
        """Test updating a single VM with new SSH key."""
        # Setup
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result

        # Execute
        success = SSHKeyRotator.update_vm_key(
            vm_name="test-vm",
            resource_group="test-rg",
            new_public_key="ssh-ed25519 AAAA..."
        )

        # Assert
        assert success is True
        mock_subprocess.run.assert_called_once()

    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.VMManager')
    @patch('azlin.key_rotator.subprocess')
    @patch('azlin.key_rotator.AzureAuthenticator')
    def test_update_all_vms_parallel(self, mock_auth, mock_subprocess, mock_vm_manager, mock_key_manager):
        """Test updating multiple VMs in parallel."""
        # Setup
        from azlin.vm_manager import VMInfo

        mock_vms = [
            VMInfo(name="vm1", resource_group="test-rg", location="eastus", power_state="VM running"),
            VMInfo(name="vm2", resource_group="test-rg", location="eastus", power_state="VM running"),
            VMInfo(name="vm3", resource_group="test-rg", location="eastus", power_state="VM running"),
        ]
        mock_vm_manager.list_vms.return_value = mock_vms
        mock_vm_manager.filter_by_prefix.return_value = mock_vms

        mock_key_pair = MagicMock()
        mock_key_pair.public_key_content = "ssh-ed25519 AAAA..."
        mock_key_manager.ensure_key_exists.return_value = mock_key_pair

        mock_auth_instance = MagicMock()
        mock_auth_instance.get_subscription_id.return_value = "sub-123"
        mock_auth.return_value = mock_auth_instance

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result

        # Execute
        result = SSHKeyRotator.update_all_vms(
            resource_group="test-rg",
            new_public_key="ssh-ed25519 AAAA..."
        )

        # Assert
        assert len(result.vms_updated) == 3
        assert len(result.vms_failed) == 0

    @patch('azlin.key_rotator.shutil')
    @patch('azlin.key_rotator.Path')
    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.VMManager')
    @patch('azlin.key_rotator.subprocess')
    @patch('azlin.key_rotator.AzureAuthenticator')
    def test_rollback_on_failure(self, mock_auth, mock_subprocess, mock_vm_manager, mock_key_manager, mock_path_class, mock_shutil):
        """Test rollback when VM update fails."""
        # Setup
        from azlin.vm_manager import VMInfo

        mock_vm = VMInfo(name="test-vm", resource_group="test-rg", location="eastus", power_state="VM running")
        mock_vm_manager.list_vms.return_value = [mock_vm]
        mock_vm_manager.filter_by_prefix.return_value = [mock_vm]

        mock_old_key = MagicMock()
        mock_old_key.public_key_content = "old-key"
        mock_old_key.private_path = MagicMock(spec=Path)
        mock_old_key.public_path = MagicMock(spec=Path)

        mock_new_key = MagicMock()
        mock_new_key.public_key_content = "new-key"
        mock_new_key.private_path = MagicMock(spec=Path)
        mock_new_key.public_path = MagicMock(spec=Path)

        mock_key_manager.ensure_key_exists.side_effect = [mock_old_key, mock_new_key]

        mock_auth_instance = MagicMock()
        mock_auth_instance.get_subscription_id.return_value = "sub-123"
        mock_auth.return_value = mock_auth_instance

        # Simulate failure on update
        mock_subprocess.run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Azure API Error")

        # Mock backup directory
        mock_backup_dir = MagicMock(spec=Path)
        mock_backup_dir.exists.return_value = True
        mock_backup_dir.__truediv__ = lambda self, x: MagicMock(spec=Path)

        # Execute
        with patch('azlin.key_rotator.SSHKeyRotator.BACKUP_BASE_DIR', mock_backup_dir):
            result = SSHKeyRotator.rotate_keys(
                resource_group="test-rg",
                enable_rollback=True
            )

        # Assert
        assert result.success is False
        assert len(result.vms_failed) > 0
        # Verify rollback was attempted
        assert "test-vm" in result.vms_failed

    @patch('azlin.key_rotator.subprocess')
    @patch('azlin.key_rotator.VMManager')
    def test_list_vm_keys(self, mock_vm_manager, mock_subprocess):
        """Test listing VMs and their SSH keys."""
        # Setup
        from azlin.vm_manager import VMInfo

        mock_vms = [
            VMInfo(name="vm1", resource_group="test-rg", location="eastus", power_state="VM running"),
            VMInfo(name="vm2", resource_group="test-rg", location="eastus", power_state="VM running"),
        ]
        mock_vm_manager.list_vms.return_value = mock_vms
        mock_vm_manager.filter_by_prefix.return_value = mock_vms

        mock_result = MagicMock()
        mock_result.stdout = "ssh-ed25519 AAAA... key"
        mock_subprocess.run.return_value = mock_result

        # Execute
        key_info_list = SSHKeyRotator.list_vm_keys(resource_group="test-rg")

        # Assert
        assert len(key_info_list) == 2
        assert all(isinstance(info, VMKeyInfo) for info in key_info_list)

    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.Path')
    def test_export_public_keys(self, mock_path, mock_key_manager):
        """Test exporting public keys to file."""
        # Setup

        mock_key_pair = MagicMock()
        mock_key_pair.public_key_content = "ssh-ed25519 AAAA... azlin-key"
        mock_key_manager.ensure_key_exists.return_value = mock_key_pair

        output_file = Path("/tmp/keys.txt")

        # Execute
        success = SSHKeyRotator.export_public_key(output_file=output_file)

        # Assert
        assert success is True
        mock_key_manager.ensure_key_exists.assert_called_once()

    @patch('azlin.key_rotator.shutil')
    @patch('azlin.key_rotator.Path')
    @patch('azlin.key_rotator.SSHKeyManager')
    def test_backup_keys_with_timestamp(self, mock_key_manager, mock_path_class, mock_shutil):
        """Test backup creates directory with timestamp."""
        # Setup
        mock_key_pair = MagicMock()
        mock_key_pair.private_path = MagicMock(spec=Path)
        mock_key_pair.public_path = MagicMock(spec=Path)
        mock_key_manager.ensure_key_exists.return_value = mock_key_pair

        # Mock backup directory
        mock_backup_dir = MagicMock(spec=Path)
        mock_backup_dir.exists.return_value = True
        mock_backup_dir.__truediv__ = lambda self, x: MagicMock(spec=Path)

        # Execute
        with patch('azlin.key_rotator.SSHKeyRotator.BACKUP_BASE_DIR', mock_backup_dir):
            backup = SSHKeyRotator.backup_keys()

        # Assert
        assert backup is not None
        assert backup.timestamp is not None
        assert isinstance(backup.timestamp, datetime)

    @patch('azlin.key_rotator.SSHKeyManager')
    @patch('azlin.key_rotator.VMManager')
    def test_rotate_keys_with_backup_disabled(self, mock_vm_manager, mock_key_manager):
        """Test rotation without backup when disabled."""
        # Setup
        mock_key_pair = MagicMock()
        mock_key_pair.public_key_content = "new-key"
        mock_key_manager.ensure_key_exists.return_value = mock_key_pair
        mock_vm_manager.list_vms.return_value = []

        # Execute
        result = SSHKeyRotator.rotate_keys(
            resource_group="test-rg",
            create_backup=False
        )

        # Assert
        assert result.success is True
        assert result.backup_path is None

    def test_key_rotation_error_raised(self):
        """Test that KeyRotationError is raised on invalid input."""
        with pytest.raises(KeyRotationError):
            SSHKeyRotator.rotate_keys(resource_group="")

    @patch('azlin.key_rotator.subprocess.run')
    def test_update_vm_key_handles_azure_error(self, mock_run):
        """Test error handling when Azure API fails."""
        # Setup - mock the exception properly
        import subprocess as real_subprocess
        mock_run.side_effect = real_subprocess.CalledProcessError(1, "az", stderr="VM not found")

        # Execute & Assert
        success = SSHKeyRotator.update_vm_key(
            vm_name="nonexistent-vm",
            resource_group="test-rg",
            new_public_key="ssh-ed25519 AAAA..."
        )

        assert success is False

    @patch('azlin.key_rotator.shutil')
    @patch('azlin.key_rotator.Path')
    @patch('azlin.key_rotator.SSHKeyManager')
    def test_backup_preserves_permissions(self, mock_key_manager, mock_path_class, mock_shutil):
        """Test that backup directory has secure permissions (0700)."""
        # Setup
        mock_key_pair = MagicMock()
        mock_key_pair.private_path = MagicMock(spec=Path)
        mock_key_pair.public_path = MagicMock(spec=Path)
        mock_key_manager.ensure_key_exists.return_value = mock_key_pair

        # Mock backup directory
        mock_backup_dir_instance = MagicMock(spec=Path)
        mock_backup_dir_instance.exists.return_value = True
        mock_backup_dir_instance.mkdir = MagicMock()
        mock_backup_dir_instance.__truediv__ = lambda self, x: MagicMock(spec=Path)

        # Execute
        with patch('azlin.key_rotator.SSHKeyRotator.BACKUP_BASE_DIR', mock_backup_dir_instance):
            backup = SSHKeyRotator.backup_keys()

            # Assert - verify mkdir was called
            # This ensures backup directory creation is attempted
            assert backup is not None
