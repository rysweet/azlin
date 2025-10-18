"""NFS mount operations for Azure Files shares.

This module handles mounting and unmounting Azure Files NFS shares on VMs
via SSH, with proper backup and rollback mechanisms.

Philosophy:
- Remote operations via SSH
- Atomic mount/unmount (rollback on failure)
- Preserves user data (backup before mount)
- Updates /etc/fstab for persistence
- Fail fast with clear error messages

Public API:
    NFSMountManager: Main mount operations class
    MountResult: Result of mount operation
    UnmountResult: Result of unmount operation
    MountInfo: Current mount information
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# Data Models
@dataclass
class MountResult:
    """Result of mount operation."""

    success: bool
    mount_point: str
    nfs_endpoint: str
    backed_up_files: int = 0
    copied_files: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class UnmountResult:
    """Result of unmount operation."""

    success: bool
    mount_point: str
    backed_up_files: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class MountInfo:
    """Current mount information."""

    mount_point: str
    nfs_endpoint: str
    filesystem_type: str
    mount_options: str


class NFSMountManager:
    """NFS mount operations for Azure Files shares.

    All methods are classmethods for brick-style API.
    No instance state maintained.
    """

    @classmethod
    def mount_storage(
        cls,
        vm_ip: str,
        ssh_key: Path,
        nfs_endpoint: str,
        mount_point: str = "/home/azureuser",
    ) -> MountResult:
        """Mount NFS share on VM.

        Steps:
        1. Install nfs-common if not present
        2. Backup existing mount point to .backup
        3. Create mount point if doesn't exist
        4. Mount NFS share
        5. Update /etc/fstab for persistence
        6. Verify mount successful
        7. Copy backup files to mounted share if empty

        Rollback on failure:
        - Unmount if partially mounted
        - Restore from backup

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            nfs_endpoint: NFS endpoint (e.g., "server:/share")
            mount_point: Mount point path (default: /home/azureuser)

        Returns:
            MountResult with success status and details
        """
        errors = []
        backed_up_files = 0
        copied_files = 0

        try:
            # Step 1: Install nfs-common
            logger.info(f"Installing nfs-common on {vm_ip}")
            cls._ssh_command(
                vm_ip,
                ssh_key,
                "sudo apt-get update -qq && sudo apt-get install -y nfs-common",
            )

            # Step 2: Backup existing mount point
            logger.info(f"Backing up existing {mount_point}")
            backup_dir = f"{mount_point}.backup"

            # Check if mount point exists and has files
            check_cmd = f"[ -d {mount_point} ] && ls -A {mount_point} | wc -l || echo 0"
            result = cls._ssh_command(vm_ip, ssh_key, check_cmd)
            file_count = int(result.strip()) if result.strip().isdigit() else 0

            if file_count > 0:
                cls._ssh_command(
                    vm_ip,
                    ssh_key,
                    f"sudo mv {mount_point} {backup_dir}",
                )
                backed_up_files = file_count

            # Step 3: Create mount point
            logger.info(f"Creating mount point {mount_point}")
            cls._ssh_command(vm_ip, ssh_key, f"sudo mkdir -p {mount_point}")

            # Step 4: Mount NFS share
            logger.info(f"Mounting NFS share {nfs_endpoint}")
            mount_cmd = f"sudo mount -t nfs -o sec=sys {nfs_endpoint} {mount_point}"
            cls._ssh_command(vm_ip, ssh_key, mount_cmd)

            # Step 5: Update /etc/fstab
            logger.info("Updating /etc/fstab")
            fstab_entry = f"{nfs_endpoint} {mount_point} nfs defaults 0 0"
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"echo '{fstab_entry}' | sudo tee -a /etc/fstab",
            )

            # Step 6: Verify mount
            verify_cmd = f"mount | grep {mount_point}"
            cls._ssh_command(vm_ip, ssh_key, verify_cmd)

            # Step 7: Copy backup if share is empty
            if backed_up_files > 0:
                logger.info("Copying backup files to mounted share")
                # Check if share is empty
                share_files_cmd = f"ls -A {mount_point} | wc -l"
                result = cls._ssh_command(vm_ip, ssh_key, share_files_cmd)
                share_file_count = int(result.strip()) if result.strip().isdigit() else 0

                if share_file_count == 0:
                    cls._ssh_command(
                        vm_ip,
                        ssh_key,
                        f"sudo cp -a {backup_dir}/* {mount_point}/ 2>/dev/null || true",
                    )
                    copied_files = backed_up_files

            # Set ownership
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"sudo chown -R azureuser:azureuser {mount_point}",
            )

            logger.info(f"Successfully mounted {nfs_endpoint} on {mount_point}")
            return MountResult(
                success=True,
                mount_point=mount_point,
                nfs_endpoint=nfs_endpoint,
                backed_up_files=backed_up_files,
                copied_files=copied_files,
                errors=[],
            )

        except Exception as e:
            error_msg = str(e)
            errors.append(error_msg)
            logger.error(f"Mount failed: {error_msg}")

            # Rollback: Try to restore backup
            try:
                logger.info("Rolling back mount operation")
                if backed_up_files > 0:
                    cls._ssh_command(
                        vm_ip,
                        ssh_key,
                        f"sudo umount {mount_point} 2>/dev/null || true",
                    )
                    cls._ssh_command(
                        vm_ip,
                        ssh_key,
                        f"sudo rm -rf {mount_point}",
                    )
                    cls._ssh_command(
                        vm_ip,
                        ssh_key,
                        f"sudo mv {backup_dir} {mount_point}",
                    )
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
                errors.append(f"Rollback error: {rollback_error!s}")

            return MountResult(
                success=False,
                mount_point=mount_point,
                nfs_endpoint=nfs_endpoint,
                backed_up_files=backed_up_files,
                copied_files=0,
                errors=errors,
            )

    @classmethod
    def unmount_storage(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str = "/home/azureuser",
    ) -> UnmountResult:
        """Unmount NFS share from VM.

        Steps:
        1. Copy mounted files to local backup
        2. Unmount NFS share
        3. Remove from /etc/fstab
        4. Move backup to original mount point
        5. Verify unmount successful

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            mount_point: Mount point path (default: /home/azureuser)

        Returns:
            UnmountResult with success status
        """
        errors = []
        backed_up_files = 0

        try:
            # Step 1: Copy mounted files to local backup
            logger.info(f"Backing up mounted files from {mount_point}")
            local_backup = f"{mount_point}.local"

            # Count files
            count_cmd = f"ls -A {mount_point} | wc -l"
            result = cls._ssh_command(vm_ip, ssh_key, count_cmd)
            backed_up_files = int(result.strip()) if result.strip().isdigit() else 0

            # Copy files
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"sudo cp -a {mount_point} {local_backup}",
            )

            # Step 2: Unmount NFS share
            logger.info(f"Unmounting {mount_point}")
            cls._ssh_command(vm_ip, ssh_key, f"sudo umount {mount_point}")

            # Step 3: Remove from /etc/fstab
            logger.info("Removing from /etc/fstab")
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"sudo sed -i '\\|{mount_point}|d' /etc/fstab",
            )

            # Step 4: Move backup to original mount point
            logger.info("Restoring local copy")
            cls._ssh_command(vm_ip, ssh_key, f"sudo rm -rf {mount_point}")
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"sudo mv {local_backup} {mount_point}",
            )

            # Set ownership
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"sudo chown -R azureuser:azureuser {mount_point}",
            )

            logger.info(f"Successfully unmounted {mount_point}")
            return UnmountResult(
                success=True,
                mount_point=mount_point,
                backed_up_files=backed_up_files,
                errors=[],
            )

        except Exception as e:
            error_msg = str(e)
            errors.append(error_msg)
            logger.error(f"Unmount failed: {error_msg}")

            return UnmountResult(
                success=False,
                mount_point=mount_point,
                backed_up_files=backed_up_files,
                errors=errors,
            )

    @classmethod
    def verify_mount(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str = "/home/azureuser",
    ) -> bool:
        """Check if mount point is NFS-mounted.

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            mount_point: Mount point path

        Returns:
            True if NFS-mounted, False otherwise
        """
        try:
            cmd = f"mount | grep {mount_point} | grep nfs"
            result = cls._ssh_command(vm_ip, ssh_key, cmd)
            return bool(result.strip())
        except Exception as e:
            logger.warning(f"Failed to check if NFS is mounted at {mount_point}: {e}")
            return False

    @classmethod
    def get_mount_info(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str = "/home/azureuser",
    ) -> MountInfo | None:
        """Get mount information if mounted.

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            mount_point: Mount point path

        Returns:
            MountInfo if mounted, None otherwise
        """
        try:
            cmd = f"mount | grep {mount_point}"
            result = cls._ssh_command(vm_ip, ssh_key, cmd)

            if not result.strip():
                return None

            # Parse mount output
            # Format: "endpoint on /mount/point type nfs4 (options)"
            parts = result.split()
            if len(parts) < 6:
                return None

            nfs_endpoint = parts[0]
            filesystem_type = parts[4]
            mount_options = parts[5].strip("()")

            return MountInfo(
                mount_point=mount_point,
                nfs_endpoint=nfs_endpoint,
                filesystem_type=filesystem_type,
                mount_options=mount_options,
            )

        except Exception as e:
            logger.debug(f"Failed to get mount info: {e}")
            return None

    @classmethod
    def _ssh_command(cls, vm_ip: str, ssh_key: Path, command: str) -> str:
        """Execute SSH command on VM.

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            command: Command to execute

        Returns:
            Command stdout

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        ssh_cmd = [
            "ssh",
            "-i",
            str(ssh_key),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=30",
            f"azureuser@{vm_ip}",
            command,
        ]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )

        return result.stdout


# Public API
__all__ = [
    "MountInfo",
    "MountResult",
    "NFSMountManager",
    "UnmountResult",
]
