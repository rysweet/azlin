"""Local SMB mount operations for macOS.

This module handles mounting and unmounting Azure Files SMB shares on the
local macOS machine using mount_smbfs. It ensures secure password handling
and proper error reporting.

Philosophy:
- macOS-only operations (mount_smbfs)
- Secure password handling (stdin, never command-line)
- Atomic mount/unmount operations
- Path validation and sanitization
- Fail fast with clear error messages

Security (CRITICAL):
- Passwords passed via stdin, never as command-line arguments
- Never log or print passwords
- Validate all paths to prevent injection attacks
- Check platform to prevent accidental Linux/Windows usage
- Safe escaping of mount point paths

Public API:
    LocalSMBMount: Main mount operations class
    MountResult: Result of mount operation
    UnmountResult: Result of unmount operation
    MountInfo: Current mount information
    LocalSMBMountError: Base exception
    UnsupportedPlatformError: Not running on macOS
    ValidationError: Invalid input parameters
"""

import logging
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# Exceptions
class LocalSMBMountError(Exception):
    """Base exception for local SMB mount operations."""

    pass


class UnsupportedPlatformError(LocalSMBMountError):
    """Operation not supported on this platform."""

    pass


class ValidationError(LocalSMBMountError):
    """Invalid input parameters."""

    pass


class MountPointError(LocalSMBMountError):
    """Mount point error (doesn't exist, not a directory, etc)."""

    pass


# Data Models
@dataclass
class MountResult:
    """Result of mount operation."""

    success: bool
    mount_point: str
    smb_share: str
    errors: list[str] | None = None


@dataclass
class UnmountResult:
    """Result of unmount operation."""

    success: bool
    mount_point: str
    was_mounted: bool
    errors: list[str] | None = None


@dataclass
class MountInfo:
    """Information about a mounted share."""

    mount_point: str
    smb_share: str
    is_mounted: bool


class LocalSMBMount:
    """Manage local SMB mount operations on macOS.

    This class provides methods to mount and unmount Azure Files SMB shares
    on the local macOS machine. All operations use mount_smbfs for security
    and proper authentication.
    """

    # Validation patterns
    STORAGE_ACCOUNT_PATTERN = re.compile(r"^[a-z0-9]{3,24}$")
    SHARE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")

    @classmethod
    def _check_platform(cls) -> None:
        """Verify we're running on macOS.

        Raises:
            UnsupportedPlatformError: If not running on macOS
        """
        if platform.system() != "Darwin":
            raise UnsupportedPlatformError(
                f"Local SMB mount is only supported on macOS. Current platform: {platform.system()}"
            )

    @classmethod
    def _validate_storage_account(cls, storage_account: str) -> None:
        """Validate storage account name format.

        Args:
            storage_account: Storage account name

        Raises:
            ValidationError: If storage account name is invalid
        """
        if not cls.STORAGE_ACCOUNT_PATTERN.match(storage_account):
            raise ValidationError(
                f"Invalid storage account name: {storage_account}. "
                "Must be 3-24 characters, lowercase letters and numbers only."
            )

    @classmethod
    def _validate_share_name(cls, share_name: str) -> None:
        """Validate share name format.

        Args:
            share_name: Share name

        Raises:
            ValidationError: If share name is invalid
        """
        if not cls.SHARE_NAME_PATTERN.match(share_name):
            raise ValidationError(
                f"Invalid share name: {share_name}. "
                "Must be 3-63 characters, lowercase letters, numbers, and hyphens. "
                "Cannot start or end with hyphen."
            )

    @classmethod
    def _validate_mount_point(cls, mount_point: Path) -> None:
        """Validate and prepare mount point.

        Args:
            mount_point: Path to mount point directory

        Raises:
            MountPointError: If mount point is invalid or can't be created
        """
        # Expand user path (~/...)
        mount_point = mount_point.expanduser()

        # Check if parent directory exists
        if not mount_point.parent.exists():
            raise MountPointError(
                f"Parent directory does not exist: {mount_point.parent}. "
                "Create it first or use an existing location."
            )

        # Create mount point if it doesn't exist
        if not mount_point.exists():
            try:
                mount_point.mkdir(parents=False, exist_ok=True)
                logger.info(f"Created mount point directory: {mount_point}")
            except Exception as e:
                raise MountPointError(
                    f"Failed to create mount point directory: {mount_point}. Error: {e}"
                ) from e

        # Verify it's a directory
        if not mount_point.is_dir():
            raise MountPointError(f"Mount point is not a directory: {mount_point}")

    @classmethod
    def _build_smb_url(cls, storage_account: str, share_name: str, username: str) -> str:
        """Build SMB URL for Azure Files share.

        Args:
            storage_account: Storage account name
            share_name: Share name
            username: Storage account username (usually the storage account name)

        Returns:
            SMB URL in format: //username@storage.file.core.windows.net/sharename
        """
        # Azure Files SMB endpoint format
        smb_host = f"{storage_account}.file.core.windows.net"
        return f"//{username}@{smb_host}/{share_name}"

    @classmethod
    def mount(
        cls,
        storage_account: str,
        share_name: str,
        storage_key: str,
        mount_point: Path,
        username: str | None = None,
    ) -> MountResult:
        """Mount Azure Files SMB share on local macOS machine.

        Uses mount_smbfs to mount the share with the storage account key as password.
        The password is passed via stdin for security.

        Args:
            storage_account: Azure storage account name
            share_name: Azure Files share name
            storage_key: Storage account key (used as password)
            mount_point: Local directory path to mount to
            username: SMB username (defaults to storage_account if not provided)

        Returns:
            MountResult: Result of the mount operation

        Raises:
            UnsupportedPlatformError: If not running on macOS
            ValidationError: If input parameters are invalid
            MountPointError: If mount point is invalid
            LocalSMBMountError: For other mount errors

        Example:
            >>> result = LocalSMBMount.mount(
            ...     "mystorageaccount",
            ...     "myshare",
            ...     "storage-key-here",
            ...     Path("~/azure")
            ... )
            >>> if result.success:
            ...     print(f"Mounted at: {result.mount_point}")
        """
        # Verify platform
        cls._check_platform()

        # Validate inputs
        cls._validate_storage_account(storage_account)
        cls._validate_share_name(share_name)

        if not storage_key or not storage_key.strip():
            raise ValidationError("Storage key cannot be empty")

        # Expand and validate mount point
        mount_point = mount_point.expanduser().resolve()
        cls._validate_mount_point(mount_point)

        # Use storage account name as username if not provided
        if username is None:
            username = storage_account

        # Build SMB URL
        smb_url = cls._build_smb_url(storage_account, share_name, username)

        logger.info(f"Mounting SMB share to: {mount_point}")
        # SECURITY: Never log the storage_key
        logger.debug(f"SMB URL (without password): {smb_url}")

        try:
            # Build mount_smbfs command
            # Format: mount_smbfs //user@host/share /mount/point
            # Password will be provided via stdin for security
            cmd = ["mount_smbfs", "-N", smb_url, str(mount_point)]

            # Execute mount command with password via stdin
            # -N flag means "don't prompt for password" - we'll provide it via stdin
            result = subprocess.run(
                cmd,
                input=storage_key.encode(),  # Password via stdin
                capture_output=True,
                text=False,  # Use bytes for input
                check=False,
            )

            if result.returncode == 0:
                logger.info(f"Successfully mounted SMB share at: {mount_point}")
                return MountResult(success=True, mount_point=str(mount_point), smb_share=smb_url)
            # Mount failed
            error_msg = result.stderr.decode() if result.stderr else "Unknown error"
            logger.error(f"Mount failed: {error_msg}")
            return MountResult(
                success=False,
                mount_point=str(mount_point),
                smb_share=smb_url,
                errors=[f"Mount failed: {error_msg}"],
            )

        except Exception as e:
            logger.error(f"Exception during mount operation: {e}")
            return MountResult(
                success=False,
                mount_point=str(mount_point),
                smb_share=smb_url,
                errors=[f"Exception during mount: {e}"],
            )

    @classmethod
    def unmount(cls, mount_point: Path, force: bool = False) -> UnmountResult:
        """Unmount SMB share from local machine.

        Args:
            mount_point: Path to the mount point to unmount
            force: Force unmount even if busy (default: False)

        Returns:
            UnmountResult: Result of the unmount operation

        Raises:
            UnsupportedPlatformError: If not running on macOS
            ValidationError: If mount point is invalid

        Example:
            >>> result = LocalSMBMount.unmount(Path("~/azure"))
            >>> if result.success:
            ...     print("Successfully unmounted")
        """
        # Verify platform
        cls._check_platform()

        # Expand and resolve mount point
        mount_point = mount_point.expanduser().resolve()

        if not mount_point.exists():
            raise ValidationError(f"Mount point does not exist: {mount_point}")

        if not mount_point.is_dir():
            raise ValidationError(f"Mount point is not a directory: {mount_point}")

        logger.info(f"Unmounting SMB share from: {mount_point}")

        # Check if it's actually mounted
        is_mounted = cls._is_mounted(mount_point)

        if not is_mounted:
            logger.info(f"Mount point is not currently mounted: {mount_point}")
            return UnmountResult(success=True, mount_point=str(mount_point), was_mounted=False)

        try:
            # Build unmount command
            cmd = ["umount"]
            if force:
                cmd.append("-f")  # Force unmount
            cmd.append(str(mount_point))

            # Execute unmount
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                logger.info(f"Successfully unmounted: {mount_point}")
                return UnmountResult(success=True, mount_point=str(mount_point), was_mounted=True)
            error_msg = result.stderr if result.stderr else "Unknown error"
            logger.error(f"Unmount failed: {error_msg}")
            return UnmountResult(
                success=False,
                mount_point=str(mount_point),
                was_mounted=True,
                errors=[f"Unmount failed: {error_msg}"],
            )

        except Exception as e:
            logger.error(f"Exception during unmount operation: {e}")
            return UnmountResult(
                success=False,
                mount_point=str(mount_point),
                was_mounted=True,
                errors=[f"Exception during unmount: {e}"],
            )

    @classmethod
    def _is_mounted(cls, mount_point: Path) -> bool:
        """Check if a path is currently a mount point.

        Args:
            mount_point: Path to check

        Returns:
            True if the path is a mount point, False otherwise
        """
        try:
            # Use mount command to list all mounts
            result = subprocess.run(["mount"], capture_output=True, text=True, check=True)

            mount_point_str = str(mount_point.resolve())

            # Check if our mount point appears in the mount list
            return any(f" on {mount_point_str} " in line for line in result.stdout.splitlines())

        except Exception as e:
            logger.warning(f"Failed to check mount status: {e}")
            return False

    @classmethod
    def get_mount_info(cls, mount_point: Path) -> MountInfo:
        """Get information about a mount point.

        Args:
            mount_point: Path to check

        Returns:
            MountInfo: Mount information

        Raises:
            UnsupportedPlatformError: If not running on macOS
        """
        # Verify platform
        cls._check_platform()

        mount_point = mount_point.expanduser().resolve()
        is_mounted = cls._is_mounted(mount_point)

        smb_share = ""
        if is_mounted:
            # Try to get the SMB share URL from mount output
            try:
                result = subprocess.run(["mount"], capture_output=True, text=True, check=True)
                mount_point_str = str(mount_point)

                for line in result.stdout.splitlines():
                    if f" on {mount_point_str} " in line:
                        # Parse the share from mount line
                        # Format: //user@host/share on /mount/point (smbfs, ...)
                        parts = line.split(" on ")
                        if parts:
                            smb_share = parts[0].strip()
                        break
            except Exception as e:
                logger.warning(f"Failed to get mount share info: {e}")

        return MountInfo(mount_point=str(mount_point), smb_share=smb_share, is_mounted=is_mounted)


__all__ = [
    "LocalSMBMount",
    "LocalSMBMountError",
    "MountInfo",
    "MountPointError",
    "MountResult",
    "UnmountResult",
    "UnsupportedPlatformError",
    "ValidationError",
]
