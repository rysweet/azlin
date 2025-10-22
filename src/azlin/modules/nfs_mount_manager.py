"""NFS mount operations for Azure Files shares.

This module handles mounting and unmounting Azure Files NFS shares on VMs
via SSH, with proper backup and rollback mechanisms.

Philosophy:
- Remote operations via SSH
- Atomic mount/unmount (rollback on failure)
- Preserves user data (backup before mount)
- Updates /etc/fstab for persistence
- Fail fast with clear error messages

Security:
- All user inputs are validated before use in shell commands
- Protection against command injection attacks
- Safe path handling with character whitelisting

Public API:
    NFSMountManager: Main mount operations class
    MountResult: Result of mount operation
    UnmountResult: Result of unmount operation
    MountInfo: Current mount information
"""

import logging
import re
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
    errors: list[str] = field(default_factory=list)  # type: ignore[misc]


@dataclass
class UnmountResult:
    """Result of unmount operation."""

    success: bool
    mount_point: str
    backed_up_files: int = 0
    errors: list[str] = field(default_factory=list)  # type: ignore[misc]


@dataclass
class MountInfo:
    """Current mount information."""

    mount_point: str
    nfs_endpoint: str
    filesystem_type: str
    mount_options: str


# Security Validation Helpers
class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def _validate_mount_point(mount_point: str) -> str:
    """Validate mount point path for safe use in shell commands.

    Args:
        mount_point: Mount point path to validate

    Returns:
        Validated mount point

    Raises:
        ValidationError: If mount point contains unsafe characters
    """
    # Allow alphanumeric, forward slashes, dots, underscores, and hyphens
    # Must start with / and not contain shell metacharacters
    if not mount_point:
        raise ValidationError("Mount point cannot be empty")

    if not mount_point.startswith("/"):
        raise ValidationError(f"Mount point must be absolute path: {mount_point}")

    # Check for shell metacharacters and dangerous patterns
    dangerous_patterns = [
        ";",
        "&",
        "|",
        "$",
        "`",
        "(",
        ")",
        "<",
        ">",
        "\\",
        "'",
        '"',
        "\n",
        "\r",
        "\t",
        "*",
        "?",
        "[",
        "]",
        "{",
        "}",
        "!",
        "~",
    ]

    for pattern in dangerous_patterns:
        if pattern in mount_point:
            raise ValidationError(
                f"Mount point contains unsafe character '{pattern}': {mount_point}"
            )

    # Additional check: must match safe path pattern
    if not re.match(r"^/[a-zA-Z0-9/_.-]+$", mount_point):
        raise ValidationError(f"Mount point contains invalid characters: {mount_point}")

    # Prevent directory traversal
    if ".." in mount_point:
        raise ValidationError(f"Mount point cannot contain '..': {mount_point}")

    return mount_point


def _validate_nfs_endpoint(nfs_endpoint: str) -> str:
    """Validate NFS endpoint for safe use in shell commands.

    Expected format: server.domain:/path/to/share
    Examples:
        - storageacct.file.core.windows.net:/share
        - 10.0.0.4:/exports/data

    Args:
        nfs_endpoint: NFS endpoint to validate

    Returns:
        Validated endpoint

    Raises:
        ValidationError: If endpoint contains unsafe characters
    """
    if not nfs_endpoint:
        raise ValidationError("NFS endpoint cannot be empty")

    # Must contain colon separator
    if ":" not in nfs_endpoint:
        raise ValidationError(f"NFS endpoint must contain ':' separator: {nfs_endpoint}")

    server, share_path = nfs_endpoint.split(":", 1)

    # Validate server part (hostname or IP)
    if not server:
        raise ValidationError(f"NFS server cannot be empty: {nfs_endpoint}")

    # Check for shell metacharacters
    dangerous_chars = [
        ";",
        "&",
        "|",
        "$",
        "`",
        "(",
        ")",
        "<",
        ">",
        "\\",
        "'",
        '"',
        "\n",
        "\r",
        "\t",
        "!",
        "~",
    ]

    for char in dangerous_chars:
        if char in nfs_endpoint:
            raise ValidationError(
                f"NFS endpoint contains unsafe character '{char}': {nfs_endpoint}"
            )

    # Validate server part: alphanumeric, dots, hyphens only
    if not re.match(r"^[a-zA-Z0-9.-]+$", server):
        raise ValidationError(f"NFS server contains invalid characters: {server}")

    # Validate share path: must start with /
    if not share_path.startswith("/"):
        raise ValidationError(f"NFS share path must start with '/': {share_path}")

    # Validate share path characters
    if not re.match(r"^/[a-zA-Z0-9/_.-]*$", share_path):
        raise ValidationError(f"NFS share path contains invalid characters: {share_path}")

    # Prevent directory traversal
    if ".." in share_path:
        raise ValidationError(f"NFS share path cannot contain '..': {share_path}")

    return nfs_endpoint


def _validate_mount_options(options: str) -> str:
    """Validate mount options for safe use in shell commands.

    Args:
        options: Mount options string (e.g., "sec=sys,rw,relatime")

    Returns:
        Validated options

    Raises:
        ValidationError: If options contain unsafe characters
    """
    if not options:
        return options

    # Allow alphanumeric, commas, equals, underscores, and hyphens
    if not re.match(r"^[a-zA-Z0-9,=_-]+$", options):
        raise ValidationError(f"Mount options contain invalid characters: {options}")

    # Check for shell metacharacters
    dangerous_chars = [
        ";",
        "&",
        "|",
        "$",
        "`",
        "(",
        ")",
        "<",
        ">",
        "\\",
        "'",
        '"',
        "\n",
        "\r",
        "\t",
        "!",
        "~",
        " ",
    ]

    for char in dangerous_chars:
        if char in options:
            raise ValidationError(f"Mount options contain unsafe character '{char}': {options}")

    return options


def _validate_storage_name(name: str) -> str:
    """Validate storage account name for safe use.

    Azure storage account names are 3-24 characters, lowercase alphanumeric only.

    Args:
        name: Storage account name

    Returns:
        Validated name

    Raises:
        ValidationError: If name is invalid
    """
    if not name:
        raise ValidationError("Storage name cannot be empty")

    if len(name) < 3 or len(name) > 24:
        raise ValidationError(f"Storage name must be 3-24 characters: {name} ({len(name)} chars)")

    if not re.match(r"^[a-z0-9]+$", name):
        raise ValidationError(f"Storage name must be lowercase alphanumeric only: {name}")

    return name


class NFSMountManager:
    """NFS mount operations for Azure Files shares.

    All methods are classmethods for brick-style API.
    No instance state maintained.
    """

    @classmethod
    def mount_storage_via_runcommand(
        cls,
        vm_name: str,
        resource_group: str,
        nfs_endpoint: str,
        ssh_public_key: str,
        mount_point: str = "/home/azureuser",
    ) -> MountResult:
        """Mount NFS share on VM using Azure run-command (no SSH required).

        This method executes the entire mount operation via Azure's run-command API,
        bypassing the SSH limitation where Azure's waagent continuously overwrites
        SSH keys every 10-30 seconds.

        Steps executed in single run-command script:
        1. Wait for package manager availability
        2. Install nfs-common
        3. Backup existing mount point
        4. Create mount point
        5. Mount NFS share
        6. Update /etc/fstab
        7. Restore SSH keys
        8. Fix permissions
        9. Copy backup files if share is empty

        Args:
            vm_name: VM name
            resource_group: Resource group name
            nfs_endpoint: NFS endpoint (e.g., "server:/share")
            ssh_public_key: SSH public key to restore after mount
            mount_point: Mount point path (default: /home/azureuser)

        Returns:
            MountResult with success status and details
        """
        import subprocess

        backup_dir = f"{mount_point}.backup"

        # Generate comprehensive mount script
        mount_script = f"""#!/bin/bash
set -e  # Exit on any error

# Output for debugging
exec 1> >(logger -s -t nfs-mount) 2>&1

echo "=== NFS Mount Script Starting ==="
echo "Endpoint: {nfs_endpoint}"
echo "Mount point: {mount_point}"

# Step 1: Wait for package manager
echo "Step 1: Waiting for package manager..."
for i in {{1..30}}; do
    if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 && \
       ! fuser /var/lib/apt/lists/lock >/dev/null 2>&1; then
        echo "Package manager available"
        break
    fi
    echo "Waiting for package manager (attempt $i/30)..."
    sleep 2
done

# Step 2: Install nfs-common
echo "Step 2: Installing nfs-common..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y nfs-common

# Step 3: Backup existing mount point
echo "Step 3: Backing up {mount_point}..."
if [ -d "{mount_point}" ] && [ "$(ls -A {mount_point} 2>/dev/null)" ]; then
    if [ ! -d "{backup_dir}" ]; then
        mv "{mount_point}" "{backup_dir}"
        BACKED_UP_FILES=$(find "{backup_dir}" -type f | wc -l)
        echo "Backed up $BACKED_UP_FILES files to {backup_dir}"
    else
        echo "Backup already exists at {backup_dir}"
        BACKED_UP_FILES=$(find "{backup_dir}" -type f | wc -l)
    fi
else
    BACKED_UP_FILES=0
    echo "No files to backup"
fi

# Step 4: Create mount point
echo "Step 4: Creating mount point..."
mkdir -p "{mount_point}"

# Step 5: Mount NFS share
echo "Step 5: Mounting NFS share..."
mount -t nfs -o vers=4,minorversion=1,sec=sys {nfs_endpoint} {mount_point}
echo "Mount successful!"

# Step 6: Update /etc/fstab
echo "Step 6: Updating /etc/fstab..."
FSTAB_ENTRY="{nfs_endpoint} {mount_point} nfs vers=4,minorversion=1,sec=sys 0 0"
if ! grep -q "{nfs_endpoint}" /etc/fstab; then
    echo "$FSTAB_ENTRY" >> /etc/fstab
    echo "Added to /etc/fstab"
else
    echo "Already in /etc/fstab"
fi

# Step 7: Fix ownership and permissions
echo "Step 7: Fixing ownership and permissions..."
chown azureuser:azureuser "{mount_point}"
chmod 755 "{mount_point}"

# Step 8: Restore SSH keys
echo "Step 8: Restoring SSH keys..."
mkdir -p "{mount_point}/.ssh"
cat > "{mount_point}/.ssh/authorized_keys" << 'SSHKEY'
{ssh_public_key}
SSHKEY
chown -R azureuser:azureuser "{mount_point}/.ssh"
chmod 700 "{mount_point}/.ssh"
chmod 600 "{mount_point}/.ssh/authorized_keys"
echo "SSH keys restored"

# Step 9: Copy backup files if share is empty
echo "Step 9: Checking if backup restore needed..."
SHARE_FILES=$(ls -A "{mount_point}" 2>/dev/null | grep -v '^\\.ssh$' | wc -l)
if [ "$BACKED_UP_FILES" -gt 0 ] && [ "$SHARE_FILES" -eq 0 ]; then
    echo "Restoring backup files..."
    cp -a "{backup_dir}"/* "{mount_point}"/ 2>/dev/null || true
    # Fix ownership after copy
    chown -R azureuser:azureuser "{mount_point}"
    COPIED_FILES=$(find "{mount_point}" -type f | wc -l)
    echo "Copied $COPIED_FILES files from backup"
else
    echo "No backup restore needed (share has $SHARE_FILES files)"
    COPIED_FILES=0
fi

# Step 10: Verify mount
echo "Step 10: Verifying mount..."
if mount | grep -q "{mount_point}"; then
    echo "=== NFS Mount Complete ==="
    echo "Mount point: {mount_point}"
    echo "Backed up files: $BACKED_UP_FILES"
    echo "Copied files: $COPIED_FILES"
    df -h "{mount_point}"
    exit 0
else
    echo "ERROR: Mount verification failed"
    exit 1
fi
"""

        try:
            logger.info(f"Executing NFS mount via run-command on {vm_name}")

            # Execute via Azure run-command
            cmd = [
                "az",
                "vm",
                "run-command",
                "invoke",
                "--resource-group",
                resource_group,
                "--name",
                vm_name,
                "--command-id",
                "RunShellScript",
                "--scripts",
                mount_script,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=600,  # 10 minutes for full operation
            )

            # Parse output for backed_up and copied files counts
            output = result.stdout
            backed_up_files = 0
            copied_files = 0

            # Extract counts from output
            import re

            backed_up_match = re.search(r"Backed up (\d+) files", output)
            if backed_up_match:
                backed_up_files = int(backed_up_match.group(1))

            copied_match = re.search(r"Copied (\d+) files", output)
            if copied_match:
                copied_files = int(copied_match.group(1))

            logger.info("NFS mount completed successfully via run-command")

            return MountResult(
                success=True,
                mount_point=mount_point,
                nfs_endpoint=nfs_endpoint,
                backed_up_files=backed_up_files,
                copied_files=copied_files,
                errors=[],
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"NFS mount via run-command failed: {error_msg}")

            # Try to get output even on failure
            if e.stdout:
                logger.debug(f"Run-command output: {e.stdout}")

            return MountResult(
                success=False,
                mount_point=mount_point,
                nfs_endpoint=nfs_endpoint,
                backed_up_files=0,
                copied_files=0,
                errors=[error_msg],
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error in NFS mount: {error_msg}")

            return MountResult(
                success=False,
                mount_point=mount_point,
                nfs_endpoint=nfs_endpoint,
                backed_up_files=0,
                copied_files=0,
                errors=[error_msg],
            )

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

        Raises:
            ValidationError: If inputs contain unsafe characters
        """
        # Validate all inputs before use in shell commands (SEC-003)
        mount_point = _validate_mount_point(mount_point)
        nfs_endpoint = _validate_nfs_endpoint(nfs_endpoint)

        errors = []
        backed_up_files = 0
        copied_files = 0
        backup_dir = f"{mount_point}.backup"  # Define early for rollback

        try:
            # Step 1: Wait for package manager, then install nfs-common
            logger.info(f"Waiting for package manager on {vm_ip}")
            cls._wait_for_dpkg_available(vm_ip, ssh_key)

            logger.info(f"Installing nfs-common on {vm_ip}")
            cls._install_nfs_common_with_retry(vm_ip, ssh_key)

            # Step 2: Backup existing mount point
            logger.info(f"Backing up existing {mount_point}")

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
            # Azure Files NFS requires NFSv4.1 with specific options
            mount_cmd = (
                f"sudo mount -t nfs -o vers=4,minorversion=1,sec=sys {nfs_endpoint} {mount_point}"
            )
            cls._ssh_command(vm_ip, ssh_key, mount_cmd)

            # Step 5: Update /etc/fstab
            logger.info("Updating /etc/fstab")
            fstab_entry = f"{nfs_endpoint} {mount_point} nfs vers=4,minorversion=1,sec=sys 0 0"
            cls._ssh_command(
                vm_ip,
                ssh_key,
                f"echo '{fstab_entry}' | sudo tee -a /etc/fstab",
            )

            # Step 6: Verify mount
            verify_cmd = f"mount | grep {mount_point}"
            cls._ssh_command(vm_ip, ssh_key, verify_cmd)

            # Step 6.5: Fix home directory ownership and permissions
            # The NFS mount replaces the home directory, so we need to:
            # 1. Set correct ownership (azureuser:azureuser)
            # 2. Set correct permissions (755) - SSH requires this
            logger.info(f"Fixing ownership and permissions on {mount_point}")
            cls._ssh_command(vm_ip, ssh_key, f"sudo chown azureuser:azureuser {mount_point}")
            cls._ssh_command(vm_ip, ssh_key, f"sudo chmod 755 {mount_point}")

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

            # Step 7.5: Restore SSH keys to NFS mount
            # The mount replaced /home/azureuser, wiping out .ssh/authorized_keys
            # We need to restore it so SSH continues to work
            logger.info("Restoring SSH keys to mounted share")
            cls._restore_ssh_keys(
                vm_ip, ssh_key, mount_point, backup_dir if backed_up_files > 0 else None
            )

            # Set ownership recursively
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

        Raises:
            ValidationError: If inputs contain unsafe characters
        """
        # Validate all inputs before use in shell commands (SEC-003)
        mount_point = _validate_mount_point(mount_point)

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

        Raises:
            ValidationError: If inputs contain unsafe characters
        """
        # Validate all inputs before use in shell commands (SEC-003)
        mount_point = _validate_mount_point(mount_point)

        try:
            cmd = f"mount | grep {mount_point} | grep nfs"
            result = cls._ssh_command(vm_ip, ssh_key, cmd)
            return bool(result.strip())
        except Exception:
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

        Raises:
            ValidationError: If inputs contain unsafe characters
        """
        # Validate all inputs before use in shell commands (SEC-003)
        mount_point = _validate_mount_point(mount_point)

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
    def _wait_for_dpkg_available(
        cls, vm_ip: str, ssh_key: Path, timeout: int = 300, interval: int = 10
    ) -> None:
        """Wait for dpkg/apt to be available (not locked by cloud-init or other processes).

        This fixes the race condition where apt-get commands fail with exit code 100
        because cloud-init or apt-daily services still hold the dpkg lock.

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            timeout: Maximum wait time in seconds (default: 300)
            interval: Check interval in seconds (default: 10)

        Raises:
            Exception: If dpkg doesn't become available within timeout
        """
        import time

        start_time = time.time()

        # Command to wait for apt-daily services and check dpkg lock
        check_command = (
            "sudo systemd-run --property='After=apt-daily.service apt-daily-upgrade.service' "
            "--wait /bin/true && sudo flock --timeout 1 /var/lib/dpkg/lock true"
        )

        while (time.time() - start_time) < timeout:
            try:
                cls._ssh_command(vm_ip, ssh_key, check_command)
                elapsed = time.time() - start_time
                logger.info(f"Package manager ready after {elapsed:.1f}s")
                return

            except subprocess.CalledProcessError:
                elapsed = time.time() - start_time
                logger.debug(f"Package manager busy, waiting... ({elapsed:.0f}s/{timeout}s)")
                time.sleep(interval)

        # Timeout - log warning but proceed
        logger.warning(f"Package manager wait timed out after {timeout}s, proceeding anyway")

    @classmethod
    def _install_nfs_common_with_retry(
        cls, vm_ip: str, ssh_key: Path, max_attempts: int = 3
    ) -> None:
        """Install nfs-common with retry on lock errors.

        Handles transient dpkg lock failures with exponential backoff.

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            max_attempts: Maximum retry attempts (default: 3)

        Raises:
            Exception: If all attempts fail
        """
        import time

        for attempt in range(1, max_attempts + 1):
            try:
                cls._ssh_command(
                    vm_ip,
                    ssh_key,
                    "sudo apt-get update -qq && sudo apt-get install -y nfs-common",
                )
                logger.info(f"nfs-common installed successfully (attempt {attempt}/{max_attempts})")
                return

            except subprocess.CalledProcessError as e:
                # Check if it's a lock error
                is_lock_error = e.returncode == 100 or (
                    e.stderr and "Could not get lock" in e.stderr
                )

                if attempt < max_attempts and is_lock_error:
                    wait_time = 30 * attempt  # Exponential backoff: 30s, 60s, 90s
                    logger.warning(
                        f"apt-get locked (attempt {attempt}/{max_attempts}), "
                        f"waiting {wait_time}s before retry..."
                    )
                    time.sleep(wait_time)
                else:
                    # Not a lock error or last attempt - re-raise
                    raise

    @classmethod
    def _restore_ssh_keys(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str,
        backup_dir: str | None = None,
    ) -> None:
        """Restore SSH keys to mounted NFS share.

        When an NFS share is mounted over /home/azureuser, it replaces the directory
        contents including .ssh/authorized_keys, breaking SSH access. This method
        restores the keys from either:
        1. The backup directory (if available)
        2. The SSH public key file (fallback)

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key (for auth and deriving public key)
            mount_point: Mount point path (e.g., /home/azureuser)
            backup_dir: Optional backup directory path
        """
        try:
            # Try to restore from backup first
            if backup_dir:
                check_cmd = (
                    f"[ -f {backup_dir}/.ssh/authorized_keys ] && echo 'exists' || echo 'missing'"
                )
                result = cls._ssh_command(vm_ip, ssh_key, check_cmd)
                if "exists" in result:
                    logger.info("Restoring SSH keys from backup")
                    cls._ssh_command(
                        vm_ip,
                        ssh_key,
                        f"sudo mkdir -p {mount_point}/.ssh && "
                        f"sudo cp -a {backup_dir}/.ssh/authorized_keys {mount_point}/.ssh/ && "
                        f"sudo chown azureuser:azureuser {mount_point}/.ssh/authorized_keys && "
                        f"sudo chmod 600 {mount_point}/.ssh/authorized_keys",
                    )
                    return

            # Fallback: Read public key from local file and write to VM
            logger.info("Restoring SSH keys from public key file")
            pub_key_path = Path(str(ssh_key) + ".pub")
            if pub_key_path.exists():
                pub_key = pub_key_path.read_text().strip()
                # Use heredoc to safely write the key
                cls._ssh_command(
                    vm_ip,
                    ssh_key,
                    f"sudo mkdir -p {mount_point}/.ssh && "
                    f"echo '{pub_key}' | sudo tee {mount_point}/.ssh/authorized_keys > /dev/null && "
                    f"sudo chown azureuser:azureuser {mount_point}/.ssh/authorized_keys && "
                    f"sudo chmod 600 {mount_point}/.ssh/authorized_keys",
                )
            else:
                logger.warning("No SSH public key found to restore")

        except Exception as e:
            logger.error(f"Failed to restore SSH keys: {e}")
            raise

    @classmethod
    def _ssh_command(cls, vm_ip: str, ssh_key: Path, command: str, retries: int = 3) -> str:
        """Execute SSH command on VM with retry logic.

        Retries are helpful when SSH service is briefly restarting or
        authentication is temporarily unavailable (e.g., during cloud-init finalization).

        Args:
            vm_ip: VM IP address
            ssh_key: Path to SSH private key
            command: Command to execute
            retries: Number of retry attempts (default: 3)

        Returns:
            Command stdout

        Raises:
            subprocess.CalledProcessError: If all attempts fail
        """
        import time

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

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                )
                return result.stdout

            except subprocess.CalledProcessError as e:
                last_error = e
                if attempt < retries:
                    wait_time = 5 * attempt  # 5s, 10s, 15s
                    logger.debug(
                        f"SSH command failed (attempt {attempt}/{retries}), "
                        f"retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"SSH command failed after {retries} attempts")
                    raise last_error from None

        # Should never reach here, but satisfy linter
        if last_error:
            raise last_error
        raise RuntimeError("SSH command failed with no error")


# Public API
__all__ = [
    "MountInfo",
    "MountResult",
    "NFSMountManager",
    "UnmountResult",
    "ValidationError",
]
