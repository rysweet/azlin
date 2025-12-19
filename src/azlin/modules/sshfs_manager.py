"""SSHFS mount manager for local NFS directory access.

Philosophy:
- Mount VM's NFS home directory locally via sshfs
- Reuse existing bastion SSH tunnels (no additional complexity)
- Simple one-command mount through existing infrastructure
- Graceful degradation if sshfs not installed

Public API:
    SSHFSManager: Main SSHFS operations class
    MountInfo: Mount point information
    MountResult: Result of mount operation
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class MountInfo:
    """Information about a mount point."""

    mount_point: Path
    is_mounted: bool
    mount_source: str | None = None  # e.g., "azureuser@localhost:/home/azureuser"


@dataclass
class MountResult:
    """Result of mount operation."""

    success: bool
    mount_point: Path
    message: str
    errors: list[str] = field(default_factory=list)


class SSHFSManager:
    """SSHFS mount manager for VM home directories.

    Mounts VM's /home/azureuser directory locally via sshfs,
    reusing existing bastion SSH tunnels.

    All methods are classmethods for brick-style API.
    """

    DEFAULT_MOUNT_POINT: ClassVar[Path] = Path.home() / "azlinhome"

    @classmethod
    def check_sshfs_installed(cls) -> bool:
        """Check if sshfs command is available.

        Returns:
            True if sshfs is installed and in PATH
        """
        return shutil.which("sshfs") is not None

    @classmethod
    def get_install_instructions(cls) -> str:
        """Get platform-specific install instructions for sshfs.

        Returns:
            Installation instructions string
        """
        return (
            "SSHFS not installed. Install with:\n\n"
            "  brew install macfuse sshfs\n\n"
            "Then:\n"
            "  1. Go to System Settings → Privacy & Security\n"
            "  2. Allow 'macFUSE' kernel extension\n"
            "  3. Restart your terminal\n"
        )

    @classmethod
    def check_mount_status(cls, mount_point: Path | None = None) -> MountInfo:
        """Check if directory is currently mounted.

        Args:
            mount_point: Mount point to check (default: DEFAULT_MOUNT_POINT)

        Returns:
            MountInfo with mount status
        """
        if mount_point is None:
            mount_point = cls.DEFAULT_MOUNT_POINT

        try:
            result = subprocess.run(["mount"], capture_output=True, text=True, timeout=5)

            mount_point_str = str(mount_point.resolve())

            # Check if mount_point appears in mount output
            for line in result.stdout.splitlines():
                if mount_point_str in line:
                    # Parse mount source (e.g., "user@host:/path on /mount/point type fuse...")
                    parts = line.split(" on ")
                    if len(parts) >= 2:
                        source = parts[0].strip()
                        return MountInfo(
                            mount_point=mount_point,
                            is_mounted=True,
                            mount_source=source,
                        )

            return MountInfo(mount_point=mount_point, is_mounted=False)

        except Exception as e:
            logger.debug(f"Failed to check mount status: {e}")
            return MountInfo(mount_point=mount_point, is_mounted=False)

    @classmethod
    def mount_via_tunnel(
        cls,
        tunnel_host: str,
        tunnel_port: int,
        remote_path: str,
        mount_point: Path,
        ssh_key: Path,
        ssh_user: str = "azureuser",
    ) -> MountResult:
        """Mount remote directory via sshfs through SSH tunnel.

        Args:
            tunnel_host: Tunnel hostname (usually "localhost")
            tunnel_port: Tunnel local port
            remote_path: Remote path to mount (e.g., "/home/azureuser")
            mount_point: Local mount point
            ssh_key: SSH private key path
            ssh_user: SSH username

        Returns:
            MountResult with success status and message
        """
        # Verify sshfs installed
        if not cls.check_sshfs_installed():
            return MountResult(
                success=False,
                mount_point=mount_point,
                message="sshfs not installed",
                errors=[cls.get_install_instructions()],
            )

        # Create mount point if it doesn't exist
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return MountResult(
                success=False,
                mount_point=mount_point,
                message="Failed to create mount point",
                errors=[str(e)],
            )

        # Build sshfs command
        cmd = [
            "sshfs",
            f"{ssh_user}@{tunnel_host}:{remote_path}",
            str(mount_point),
            "-p",
            str(tunnel_port),
            "-o",
            f"IdentityFile={ssh_key}",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "reconnect",
            "-o",
            "volname=azlin-nfs",
        ]

        # Execute mount
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            logger.info(f"Mounted {remote_path} to {mount_point} via sshfs")

            return MountResult(
                success=True,
                mount_point=mount_point,
                message=f"Successfully mounted at {mount_point}",
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return MountResult(
                success=False,
                mount_point=mount_point,
                message="sshfs mount failed",
                errors=[error_msg],
            )
        except subprocess.TimeoutExpired:
            return MountResult(
                success=False,
                mount_point=mount_point,
                message="sshfs mount timed out",
                errors=["Mount operation took longer than 30 seconds"],
            )

    @classmethod
    def prompt_and_mount(
        cls,
        vm_name: str,
        storage_name: str,
        tunnel_host: str,
        tunnel_port: int,
        ssh_key: Path,
        mount_point: Path | None = None,
        skip_prompt: bool = False,
    ) -> MountResult:
        """Prompt user and mount VM's NFS directory via sshfs.

        Args:
            vm_name: VM name (for display)
            storage_name: NFS storage account name (for display)
            tunnel_host: SSH tunnel hostname
            tunnel_port: SSH tunnel port
            ssh_key: SSH private key path
            mount_point: Local mount point (default: DEFAULT_MOUNT_POINT)
            skip_prompt: Skip interactive prompt (auto-mount)

        Returns:
            MountResult with mount status
        """
        import click

        if mount_point is None:
            mount_point = cls.DEFAULT_MOUNT_POINT

        # Check if already mounted
        mount_info = cls.check_mount_status(mount_point)
        if mount_info.is_mounted:
            click.echo(f"✅ NFS already mounted at {mount_point}")
            return MountResult(
                success=True,
                mount_point=mount_point,
                message=f"Already mounted: {mount_info.mount_source}",
            )

        # Check if sshfs installed
        if not cls.check_sshfs_installed():
            click.echo("\n⚠️  " + cls.get_install_instructions())
            return MountResult(
                success=False,
                mount_point=mount_point,
                message="sshfs not installed",
                errors=["Install sshfs to enable local mounting"],
            )

        # Prompt user
        click.echo(f"\n📁 This VM uses NFS shared storage: {storage_name}")

        if not skip_prompt and not click.confirm(
            f"Mount /home/azureuser locally to {mount_point}?", default=True
        ):
            return MountResult(
                success=False,
                mount_point=mount_point,
                message="User declined mount",
            )

        # Perform mount
        result = cls.mount_via_tunnel(
            tunnel_host=tunnel_host,
            tunnel_port=tunnel_port,
            remote_path="/home/azureuser",
            mount_point=mount_point,
            ssh_key=ssh_key,
        )

        # Show result
        if result.success:
            click.echo(f"\n✅ Mounted at {mount_point}")
            click.echo(f"   Browse files: ls {mount_point}/src")
            click.echo(f"   Edit locally: code {mount_point}/src/myproject")
            click.echo(f"   Unmount: umount {mount_point}\n")
        else:
            click.echo(f"\n❌ Mount failed: {result.message}")
            if result.errors:
                for error in result.errors:
                    click.echo(f"   {error}")

        return result

    @classmethod
    def unmount(cls, mount_point: Path | None = None) -> bool:
        """Unmount sshfs mount point.

        Args:
            mount_point: Mount point to unmount (default: DEFAULT_MOUNT_POINT)

        Returns:
            True if unmounted successfully
        """
        if mount_point is None:
            mount_point = cls.DEFAULT_MOUNT_POINT

        # Check if mounted
        mount_info = cls.check_mount_status(mount_point)
        if not mount_info.is_mounted:
            logger.debug(f"{mount_point} is not mounted")
            return True

        # Unmount
        try:
            subprocess.run(
                ["umount", str(mount_point)],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            logger.info(f"Unmounted {mount_point}")
            return True

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to unmount {mount_point}: {e.stderr}")
            return False


# Public API
__all__ = [
    "MountInfo",
    "MountResult",
    "SSHFSManager",
]
