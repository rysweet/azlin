"""
SSH Key Rotator Module

Rotate SSH keys across Azure VMs with backup and rollback support.

Features:
- Generate new SSH key pairs
- Update all VMs with new public key via Azure API
- Backup old keys before rotation
- Graceful rollback on failure
- List VM keys
- Export public keys

Security:
- Backup directory: 0700 permissions
- Atomic operations with rollback
- Parallel VM updates with error tracking
"""

import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from azlin.azure_auth import AzureAuthenticator
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)


class KeyRotationError(Exception):
    """Raised when key rotation operations fail."""

    pass


@dataclass
class KeyBackup:
    """Information about backed up SSH keys."""

    backup_dir: Path
    timestamp: datetime
    old_private_key: Path
    old_public_key: Path


@dataclass
class KeyRotationResult:
    """Result of SSH key rotation operation."""

    success: bool
    message: str
    vms_updated: list[str]
    vms_failed: list[str]
    new_key_path: Path | None = None
    backup_path: Path | None = None

    @property
    def all_succeeded(self) -> bool:
        """Check if all VMs were updated successfully."""
        return self.success and len(self.vms_failed) == 0


@dataclass
class VMKeyInfo:
    """Information about a VM's SSH key."""

    vm_name: str
    resource_group: str
    public_key: str | None = None
    key_fingerprint: str | None = None


class SSHKeyRotator:
    """
    Manage SSH key rotation across Azure VMs.

    Provides functionality to:
    - Rotate SSH keys with automatic backup
    - Update multiple VMs in parallel
    - Rollback on failure
    - List and export VM keys
    """

    BACKUP_BASE_DIR = Path.home() / ".azlin" / "key_backups"
    MAX_WORKERS = 10  # Parallel VM updates

    @classmethod
    def rotate_keys(
        cls,
        resource_group: str,
        create_backup: bool = True,
        enable_rollback: bool = True,
        vm_prefix: str = "azlin",
    ) -> KeyRotationResult:
        """
        Rotate SSH keys for all VMs in resource group.

        Args:
            resource_group: Azure resource group name
            create_backup: Whether to backup old keys (default: True)
            enable_rollback: Whether to rollback on failure (default: True)
            vm_prefix: Only update VMs with this prefix (default: "azlin")

        Returns:
            KeyRotationResult: Rotation result with success status

        Raises:
            KeyRotationError: If resource group is invalid

        Example:
            >>> result = SSHKeyRotator.rotate_keys("my-rg")
            >>> if result.success:
            >>>     print(f"Updated {len(result.vms_updated)} VMs")
        """
        if not resource_group:
            raise KeyRotationError("Resource group cannot be empty")

        logger.info(f"Starting key rotation for resource group: {resource_group}")

        # Step 1: Backup old keys
        backup = None
        if create_backup:
            try:
                backup = cls.backup_keys()
                logger.info(f"Backed up keys to: {backup.backup_dir}")
            except Exception as e:
                logger.error(f"Failed to backup keys: {e}")
                return KeyRotationResult(
                    success=False, message=f"Backup failed: {e}", vms_updated=[], vms_failed=[]
                )

        # Step 2: Generate new SSH key
        try:
            # Generate new key with timestamp suffix
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            new_key_path = Path.home() / ".ssh" / f"azlin_key_{timestamp}"
            new_key_pair = SSHKeyManager.ensure_key_exists(new_key_path)
            logger.info(f"Generated new SSH key: {new_key_path}")
        except Exception as e:
            logger.error(f"Failed to generate new key: {e}")
            return KeyRotationResult(
                success=False,
                message=f"Key generation failed: {e}",
                vms_updated=[],
                vms_failed=[],
                backup_path=backup.backup_dir if backup else None,
            )

        # Step 3: Update all VMs
        try:
            update_result = cls.update_all_vms(
                resource_group=resource_group,
                new_public_key=new_key_pair.public_key_content,
                vm_prefix=vm_prefix,
            )

            # Step 4: Handle rollback if needed
            if not update_result.all_succeeded and enable_rollback and backup:
                logger.warning(f"Rolling back {len(update_result.vms_failed)} failed VMs")
                try:
                    # Read old public key from backup
                    old_public_key = backup.old_public_key.read_text().strip()

                    # Rollback: restore old key to VMs that succeeded but should revert
                    rollback_result = cls.update_all_vms(
                        resource_group=resource_group,
                        new_public_key=old_public_key,
                        vm_prefix=vm_prefix,
                    )
                    logger.info(f"Rollback completed: {rollback_result.message}")
                except Exception as e:
                    logger.error(f"Rollback failed: {e}")
                    # Continue to return partial failure result

            return KeyRotationResult(
                success=update_result.all_succeeded,
                message=update_result.message,
                vms_updated=update_result.vms_updated,
                vms_failed=update_result.vms_failed,
                new_key_path=new_key_path,
                backup_path=backup.backup_dir if backup else None,
            )

        except Exception as e:
            logger.error(f"Key rotation failed: {e}")
            return KeyRotationResult(
                success=False,
                message=f"Rotation failed: {e}",
                vms_updated=[],
                vms_failed=[],
                new_key_path=new_key_path,
                backup_path=backup.backup_dir if backup else None,
            )

    @classmethod
    def update_all_vms(
        cls, resource_group: str, new_public_key: str, vm_prefix: str = "azlin"
    ) -> KeyRotationResult:
        """
        Update all VMs in resource group with new SSH key.

        Args:
            resource_group: Azure resource group
            new_public_key: New SSH public key content
            vm_prefix: Only update VMs with this prefix

        Returns:
            KeyRotationResult: Update results

        Example:
            >>> result = SSHKeyRotator.update_all_vms("my-rg", "ssh-ed25519 AAA...")
        """
        # Get list of VMs
        try:
            vms = VMManager.list_vms(resource_group, include_stopped=True)
            vms = VMManager.filter_by_prefix(vms, vm_prefix)
        except Exception as e:
            logger.error(f"Failed to list VMs: {e}")
            return KeyRotationResult(
                success=False, message=f"Failed to list VMs: {e}", vms_updated=[], vms_failed=[]
            )

        if not vms:
            logger.info(f"No VMs found with prefix '{vm_prefix}'")
            return KeyRotationResult(
                success=True,
                message=f"No VMs found with prefix '{vm_prefix}'",
                vms_updated=[],
                vms_failed=[],
            )

        logger.info(f"Updating {len(vms)} VMs in parallel...")

        # Verify Azure CLI is authenticated
        try:
            auth = AzureAuthenticator()
            auth.get_subscription_id()
        except Exception as e:
            logger.error(f"Failed to authenticate with Azure: {e}")
            return KeyRotationResult(
                success=False,
                message=f"Azure authentication failed: {e}",
                vms_updated=[],
                vms_failed=[],
            )

        # Update VMs in parallel
        vms_updated: list[str] = []
        vms_failed: list[str] = []

        with ThreadPoolExecutor(max_workers=cls.MAX_WORKERS) as executor:
            # Submit all update tasks
            future_to_vm = {
                executor.submit(cls.update_vm_key, vm.name, resource_group, new_public_key): vm
                for vm in vms
            }

            # Collect results
            for future in as_completed(future_to_vm):
                vm = future_to_vm[future]
                try:
                    success = future.result()
                    if success:
                        vms_updated.append(vm.name)
                        logger.info(f"Updated VM: {vm.name}")
                    else:
                        vms_failed.append(vm.name)
                        logger.error(f"Failed to update VM: {vm.name}")
                except Exception as e:
                    vms_failed.append(vm.name)
                    logger.error(f"Error updating VM {vm.name}: {e}")

        # Build result message
        if vms_failed:
            message = f"Updated {len(vms_updated)}/{len(vms)} VMs. {len(vms_failed)} failed."
        else:
            message = f"Successfully updated all {len(vms_updated)} VMs"

        return KeyRotationResult(
            success=(len(vms_failed) == 0),
            message=message,
            vms_updated=vms_updated,
            vms_failed=vms_failed,
        )

    @classmethod
    def update_vm_key(cls, vm_name: str, resource_group: str, new_public_key: str) -> bool:
        """
        Update a single VM's SSH key using Azure CLI.

        Args:
            vm_name: VM name
            resource_group: Resource group
            new_public_key: New SSH public key

        Returns:
            bool: True if successful, False otherwise

        Example:
            >>> success = SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519...")
        """
        try:
            # Use Azure CLI to update VM SSH key
            # This updates the VM's OS profile with the new key
            cmd = [
                "az",
                "vm",
                "user",
                "update",
                "--resource-group",
                resource_group,
                "--name",
                vm_name,
                "--username",
                "azureuser",
                "--ssh-key-value",
                new_public_key,
            ]

            subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)

            logger.debug(f"Successfully updated SSH key for VM: {vm_name}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to update VM {vm_name}: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout updating VM {vm_name}")
            return False
        except Exception as e:
            logger.error(f"Failed to update VM {vm_name}: {e}")
            return False

    @classmethod
    def backup_keys(cls, key_path: Path | None = None) -> KeyBackup:
        """
        Backup current SSH keys to timestamped directory.

        Args:
            key_path: Path to private key (default: ~/.ssh/azlin_key)

        Returns:
            KeyBackup: Backup information

        Raises:
            KeyRotationError: If backup fails

        Example:
            >>> backup = SSHKeyRotator.backup_keys()
            >>> print(f"Backed up to: {backup.backup_dir}")
        """
        # Get current key
        try:
            key_pair = SSHKeyManager.ensure_key_exists(key_path)
        except Exception as e:
            raise KeyRotationError(f"Failed to get current key: {e}") from e

        # Create timestamped backup directory
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d-%H-%M-%S")
        backup_dir = cls.BACKUP_BASE_DIR / timestamp_str

        try:
            # Create backup directory with secure permissions
            backup_dir.mkdir(parents=True, exist_ok=False, mode=0o700)

            # Copy private key
            backup_private = backup_dir / "azlin_key"
            shutil.copy2(key_pair.private_path, backup_private)
            backup_private.chmod(0o600)

            # Copy public key
            backup_public = backup_dir / "azlin_key.pub"
            shutil.copy2(key_pair.public_path, backup_public)
            backup_public.chmod(0o644)

            logger.info(f"Backed up keys to: {backup_dir}")

            return KeyBackup(
                backup_dir=backup_dir,
                timestamp=timestamp,
                old_private_key=backup_private,
                old_public_key=backup_public,
            )

        except Exception as e:
            # Cleanup on failure
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            raise KeyRotationError(f"Failed to backup keys: {e}") from e

    @classmethod
    def list_vm_keys(cls, resource_group: str, vm_prefix: str = "azlin") -> list[VMKeyInfo]:
        """
        List VMs and their SSH public keys using Azure CLI.

        Args:
            resource_group: Azure resource group
            vm_prefix: Only list VMs with this prefix

        Returns:
            List[VMKeyInfo]: List of VM key information

        Example:
            >>> keys = SSHKeyRotator.list_vm_keys("my-rg")
            >>> for key_info in keys:
            >>>     print(f"{key_info.vm_name}: {key_info.public_key[:50]}...")
        """
        try:
            # List VMs
            vms = VMManager.list_vms(resource_group, include_stopped=True)
            vms = VMManager.filter_by_prefix(vms, vm_prefix)

            # Get key info for each VM using az CLI
            vm_keys: list[VMKeyInfo] = []
            for vm in vms:
                try:
                    # Get VM details including SSH keys
                    cmd = [
                        "az",
                        "vm",
                        "show",
                        "--resource-group",
                        resource_group,
                        "--name",
                        vm.name,
                        "--query",
                        "osProfile.linuxConfiguration.ssh.publicKeys[0].keyData",
                        "--output",
                        "tsv",
                    ]

                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30, check=True
                    )

                    public_key = result.stdout.strip() if result.stdout else None

                    vm_keys.append(
                        VMKeyInfo(
                            vm_name=vm.name,
                            resource_group=resource_group,
                            public_key=public_key,
                            key_fingerprint=None,  # Could compute SHA256 hash
                        )
                    )
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to get key for VM {vm.name}: {e.stderr}")
                    vm_keys.append(
                        VMKeyInfo(
                            vm_name=vm.name,
                            resource_group=resource_group,
                            public_key=None,
                            key_fingerprint=None,
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to get key for VM {vm.name}: {e}")
                    vm_keys.append(
                        VMKeyInfo(
                            vm_name=vm.name,
                            resource_group=resource_group,
                            public_key=None,
                            key_fingerprint=None,
                        )
                    )

            return vm_keys

        except Exception as e:
            logger.error(f"Failed to list VM keys: {e}")
            return []

    @classmethod
    def export_public_key(cls, output_file: Path, key_path: Path | None = None) -> bool:
        """
        Export public key to file.

        Args:
            output_file: Output file path
            key_path: SSH key path (default: ~/.ssh/azlin_key)

        Returns:
            bool: True if successful

        Example:
            >>> SSHKeyRotator.export_public_key(Path("~/keys/azlin.pub"))
        """
        try:
            key_pair = SSHKeyManager.ensure_key_exists(key_path)

            # Ensure output directory exists
            output_file = output_file.expanduser().resolve()
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Write public key
            output_file.write_text(key_pair.public_key_content + "\n")
            output_file.chmod(0o644)

            logger.info(f"Exported public key to: {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export public key: {e}")
            return False


__all__ = ["KeyBackup", "KeyRotationError", "KeyRotationResult", "SSHKeyRotator", "VMKeyInfo"]
