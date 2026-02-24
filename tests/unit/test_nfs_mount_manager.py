"""Unit tests for nfs_mount_manager module.

TDD Approach: Write these tests FIRST, then implement to make them pass.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from azlin.modules.nfs_mount_manager import (
    MountInfo,
    MountResult,
    NFSMountManager,
    UnmountResult,
)


class TestMountStorage:
    """Test NFS mount operations."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_installs_nfs_common(self, mock_run):
        """Mount should install nfs-common if not present."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.mount_storage(
            "1.2.3.4", Path("/fake/key"), "endpoint.file.core.windows.net:/share"
        )

        # Check that apt-get install was called
        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any(
            "apt-get install" in str(cmd) and "nfs-common" in str(cmd) for cmd in ssh_commands
        )

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_backs_up_existing_data(self, mock_run):
        """Mount should backup existing home directory when files exist."""
        # Simulate: file count check returns 5 files, then all other commands succeed
        mock_run.return_value = MagicMock(returncode=0, stdout="5")

        NFSMountManager.mount_storage(
            "1.2.3.4",
            Path("/fake/key"),
            "teststorage.file.core.windows.net:/teststorage/share",
        )

        ssh_commands = [str(call[0][0]) for call in mock_run.call_args_list]
        # Implementation uses "sudo mv {mount_point} {backup_dir}"
        assert any("sudo mv /home/azureuser /home/azureuser.backup" in cmd for cmd in ssh_commands)

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_creates_mount_point(self, mock_run):
        """Mount should create mount point directory."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.mount_storage(
            "1.2.3.4", Path("/fake/key"), "teststorage.file.core.windows.net:/teststorage/share"
        )

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any("mkdir -p /home/azureuser" in str(cmd) for cmd in ssh_commands)

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_mounts_nfs_share(self, mock_run):
        """Mount should execute NFS mount command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.mount_storage(
            "1.2.3.4", Path("/fake/key"), "endpoint.file.core.windows.net:/share"
        )

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any(
            "mount -t nfs" in str(cmd) and "endpoint.file.core.windows.net:/share" in str(cmd)
            for cmd in ssh_commands
        )

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_updates_fstab(self, mock_run):
        """Mount should add entry to /etc/fstab for persistence."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.mount_storage(
            "1.2.3.4", Path("/fake/key"), "teststorage.file.core.windows.net:/teststorage/share"
        )

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any("/etc/fstab" in str(cmd) for cmd in ssh_commands)

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_copies_backup_if_share_empty(self, mock_run):
        """Mount should copy backed up files to empty share."""

        # Return "5" for initial file count (triggers backup), then "0" for share file count
        # (triggers copy). Other calls return empty stdout.
        def side_effect(*args, **kwargs):
            cmd_str = str(args[0])
            if "ls -A /home/azureuser | wc -l" in cmd_str:
                # First call checks existing files, second checks share files
                if not hasattr(side_effect, "_share_check_done"):
                    side_effect._share_check_done = False
                if "sudo" not in cmd_str and not side_effect._share_check_done:
                    side_effect._share_check_done = True
                    return MagicMock(returncode=0, stdout="0")
                return MagicMock(returncode=0, stdout="0")
            if "wc -l" in cmd_str and "ls -A" in cmd_str:
                return MagicMock(returncode=0, stdout="5")
            return MagicMock(returncode=0, stdout="")

        # Simpler approach: all commands return "5" for file counts (backup triggers),
        # then "0" for share count (copy triggers)
        call_count = {"n": 0}

        def ordered_side_effect(*args, **kwargs):
            call_count["n"] += 1
            cmd_str = str(args[0])
            # The file count check for existing mount point
            if "wc -l" in cmd_str and call_count["n"] <= 5:
                return MagicMock(returncode=0, stdout="5")
            # The share files count check (should be 0 to trigger copy)
            if "wc -l" in cmd_str:
                return MagicMock(returncode=0, stdout="0")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = ordered_side_effect

        NFSMountManager.mount_storage(
            "1.2.3.4",
            Path("/fake/key"),
            "teststorage.file.core.windows.net:/teststorage/share",
        )

        # Should copy backup files using "sudo cp -a {backup_dir}/* {mount_point}/"
        ssh_commands = [str(call[0][0]) for call in mock_run.call_args_list]
        assert any("cp -a" in cmd and ".backup" in cmd for cmd in ssh_commands)

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_returns_mount_result(self, mock_run):
        """Mount should return MountResult with status."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = NFSMountManager.mount_storage(
            "1.2.3.4", Path("/fake/key"), "teststorage.file.core.windows.net:/teststorage/share"
        )

        assert isinstance(result, MountResult)
        assert result.success is True
        assert result.mount_point == "/home/azureuser"

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_mount_rollback_on_failure(self, mock_run):
        """Mount should rollback on failure and return unsuccessful result."""
        import subprocess

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cmd_str = str(args[0])
            # Let dpkg wait, nfs-common install, file count check, backup, mkdir succeed
            # Then fail on mount command (contains "mount -t nfs")
            if "mount -t nfs" in cmd_str:
                raise subprocess.CalledProcessError(1, args[0], stderr="Mount failed")
            # File count check returns "5" to trigger backup path
            if "wc -l" in cmd_str:
                return MagicMock(returncode=0, stdout="5")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect

        result = NFSMountManager.mount_storage(
            "1.2.3.4",
            Path("/fake/key"),
            "teststorage.file.core.windows.net:/teststorage/share",
        )

        assert result.success is False
        assert len(result.errors) > 0


class TestUnmountStorage:
    """Test NFS unmount operations."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_unmount_copies_data_to_local(self, mock_run):
        """Unmount should copy shared data to local backup."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.unmount_storage("1.2.3.4", Path("/fake/key"))

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any(
            "cp -a /home/azureuser" in str(cmd) and ".local" in str(cmd) for cmd in ssh_commands
        )

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_unmount_unmounts_nfs_share(self, mock_run):
        """Unmount should execute umount command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.unmount_storage("1.2.3.4", Path("/fake/key"))

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any("umount /home/azureuser" in str(cmd) for cmd in ssh_commands)

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_unmount_removes_fstab_entry(self, mock_run):
        """Unmount should remove entry from /etc/fstab."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.unmount_storage("1.2.3.4", Path("/fake/key"))

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any(
            "/etc/fstab" in str(cmd) and ("sed" in str(cmd) or "grep -v" in str(cmd))
            for cmd in ssh_commands
        )

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_unmount_restores_local_copy(self, mock_run):
        """Unmount should move local copy back to home."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        NFSMountManager.unmount_storage("1.2.3.4", Path("/fake/key"))

        ssh_commands = [call[0][0] for call in mock_run.call_args_list]
        assert any(
            "mv" in str(cmd) and ".local" in str(cmd) and "/home/azureuser" in str(cmd)
            for cmd in ssh_commands
        )

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_unmount_returns_unmount_result(self, mock_run):
        """Unmount should return UnmountResult."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = NFSMountManager.unmount_storage("1.2.3.4", Path("/fake/key"))

        assert isinstance(result, UnmountResult)
        assert result.success is True


class TestVerifyMount:
    """Test mount verification."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_verify_mount_nfs_mounted(self, mock_run):
        """Verify should return True if NFS mounted."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="endpoint:/share on /home/azureuser type nfs4"
        )

        result = NFSMountManager.verify_mount("1.2.3.4", Path("/fake/key"))

        assert result is True

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_verify_mount_not_mounted(self, mock_run):
        """Verify should return False if not mounted."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = NFSMountManager.verify_mount("1.2.3.4", Path("/fake/key"))

        assert result is False


class TestGetMountInfo:
    """Test getting mount information."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_get_mount_info_when_mounted(self, mock_run):
        """Get mount info should return MountInfo if mounted."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="endpoint:/share on /home/azureuser type nfs4 (rw,relatime)"
        )

        result = NFSMountManager.get_mount_info("1.2.3.4", Path("/fake/key"))

        assert isinstance(result, MountInfo)
        assert result.mount_point == "/home/azureuser"
        assert "endpoint:/share" in result.nfs_endpoint
        assert result.filesystem_type == "nfs4"

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_get_mount_info_when_not_mounted(self, mock_run):
        """Get mount info should return None if not mounted."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = NFSMountManager.get_mount_info("1.2.3.4", Path("/fake/key"))

        assert result is None


class TestMountResult:
    """Test MountResult dataclass."""

    def test_mount_result_creation(self):
        """MountResult should be creatable with all fields."""
        result = MountResult(
            success=True,
            mount_point="/home/azureuser",
            nfs_endpoint="endpoint:/share",
            backed_up_files=100,
            copied_files=100,
            errors=[],
        )

        assert result.success is True
        assert result.backed_up_files == 100


class TestUnmountResult:
    """Test UnmountResult dataclass."""

    def test_unmount_result_creation(self):
        """UnmountResult should be creatable."""
        result = UnmountResult(
            success=True,
            mount_point="/home/azureuser",
            backed_up_files=100,
            errors=[],
        )

        assert result.success is True


class TestMountInfo:
    """Test MountInfo dataclass."""

    def test_mount_info_creation(self):
        """MountInfo should be creatable."""
        info = MountInfo(
            mount_point="/home/azureuser",
            nfs_endpoint="endpoint:/share",
            filesystem_type="nfs4",
            mount_options="rw,relatime",
        )

        assert info.filesystem_type == "nfs4"
