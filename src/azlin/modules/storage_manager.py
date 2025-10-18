"""Azure Files NFS storage account management.

This module provides a brick-style API for managing Azure Files NFS storage accounts
used for shared home directories across multiple VMs.

Philosophy:
- Uses Azure CLI (az storage account) for operations
- No credentials in code
- Validates all inputs before Azure calls
- Returns structured data (dataclasses)
- Fail fast with clear error messages

Public API:
    StorageManager: Main storage operations class
    StorageInfo: Storage account information
    StorageStatus: Detailed storage status with usage
    StorageError: Base exception
    StorageNotFoundError: Storage not found
    StorageInUseError: Storage has connected VMs
    ValidationError: Invalid input parameters
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

logger = logging.getLogger(__name__)


# Exceptions
class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class StorageNotFoundError(StorageError):
    """Storage account not found."""

    pass


class StorageInUseError(StorageError):
    """Storage account still has connected VMs."""

    pass


class ValidationError(StorageError):
    """Invalid input parameters."""

    pass


# Data Models
@dataclass
class StorageInfo:
    """Storage account information."""

    name: str
    resource_group: str
    region: str
    tier: str  # "Premium" or "Standard"
    size_gb: int
    nfs_endpoint: str  # e.g., "name.file.core.windows.net:/sharename"
    created: datetime


@dataclass
class StorageStatus:
    """Detailed storage status."""

    info: StorageInfo
    used_gb: float
    utilization_percent: float
    connected_vms: list[str]  # VM names
    cost_per_month: float


class StorageManager:
    """Azure Files NFS storage account management.

    All methods are classmethods for brick-style API.
    No instance state maintained.
    """

    # Storage account naming rules (Azure constraints)
    MIN_NAME_LENGTH = 3
    MAX_NAME_LENGTH = 24
    VALID_NAME_PATTERN = re.compile(r"^[a-z0-9]+$")

    # Cost constants (USD per GB per month)
    COST_PER_GB: ClassVar[dict[str, float]] = {
        "Premium": 0.1536,
        "Standard": 0.04,
    }

    # Valid tiers
    VALID_TIERS: ClassVar[list[str]] = ["Premium", "Standard"]

    @classmethod
    def create_storage(
        cls,
        name: str,
        resource_group: str,
        region: str,
        tier: str = "Premium",
        size_gb: int = 100,
    ) -> StorageInfo:
        """Create Azure Files NFS storage account.

        Idempotent: Returns existing storage if already exists.

        Args:
            name: Storage account name (3-24 chars, alphanumeric lowercase)
            resource_group: Azure resource group
            region: Azure region (e.g., westus2)
            tier: Storage tier (Premium or Standard)
            size_gb: Storage quota in GB

        Returns:
            StorageInfo with created/existing storage details

        Raises:
            ValidationError: If inputs are invalid
            StorageError: If creation fails
        """
        # Validate inputs
        cls._validate_name(name)
        cls._validate_tier(tier)
        cls._validate_size(size_gb)

        # Check if storage already exists (idempotent)
        try:
            existing = cls.get_storage(name, resource_group)
            logger.info(f"Storage account {name} already exists, returning existing")
            return existing
        except StorageNotFoundError as e:
            logger.debug(f"Storage not found during deletion: {e}")  # Doesn't exist, continue with creation

        # Create storage account
        logger.info(f"Creating storage account {name} in {resource_group}")

        try:
            # For NFS Premium, we use FileStorage with NFS file shares
            # For NFS Standard, we use StorageV2 with hierarchical namespace and blob containers
            if tier == "Premium":
                sku = "Premium_ZRS"
                kind = "FileStorage"
                enable_hns = False
            else:
                sku = "Standard_LRS"
                kind = "StorageV2"
                enable_hns = True

            # Build create command
            cmd = [
                "az",
                "storage",
                "account",
                "create",
                "--name",
                name,
                "--resource-group",
                resource_group,
                "--location",
                region,
                "--sku",
                sku,
                "--kind",
                kind,
                "--https-only",
                "false",  # NFS requires http
                "--default-action",
                "Deny",  # Required for NFS
                "--tags",
                "managed-by=azlin",
                "--output",
                "json",
            ]

            # Only add HNS and NFS-v3 flags for Standard (StorageV2)
            if enable_hns:
                cmd.extend(["--enable-hierarchical-namespace", "true"])
                cmd.extend(["--enable-nfs-v3", "true"])

            logger.info(f"Running command: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

            storage_data = json.loads(result.stdout)

            # Create appropriate storage type
            share_name = "home"
            if tier == "Premium":
                # Premium uses NFS file shares
                cls._create_nfs_file_share(name, resource_group, share_name, size_gb)
                nfs_endpoint = f"{name}.file.core.windows.net:/{name}/{share_name}"
            else:
                # Standard uses blob containers with NFS
                cls._create_nfs_container(name, resource_group, share_name)
                nfs_endpoint = f"{name}.blob.core.windows.net:/{name}/{share_name}"

            return StorageInfo(
                name=name,
                resource_group=resource_group,
                region=storage_data.get("location", region),
                tier=tier,
                size_gb=size_gb,
                nfs_endpoint=nfs_endpoint,
                created=datetime.now(),
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise StorageError(f"Failed to create storage account: {error_msg}") from e
        except subprocess.TimeoutExpired as e:
            raise StorageError("Storage account creation timed out after 5 minutes") from e
        except json.JSONDecodeError as e:
            raise StorageError(f"Failed to parse Azure CLI output: {e}") from e

    @classmethod
    def _create_nfs_container(
        cls, storage_account: str, resource_group: str, container_name: str
    ) -> None:
        """Create NFS-enabled blob container in storage account."""
        try:
            cmd = [
                "az",
                "storage",
                "container",
                "create",
                "--name",
                container_name,
                "--account-name",
                storage_account,
                "--auth-mode",
                "login",
                "--output",
                "json",
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.warning(f"Failed to create container: {error_msg}")
            # Don't fail the entire operation, container might already exist

    @classmethod
    def _create_nfs_file_share(
        cls, storage_account: str, resource_group: str, share_name: str, quota_gb: int
    ) -> None:
        """Create NFS file share in storage account."""
        try:
            cmd = [
                "az",
                "storage",
                "share-rm",
                "create",
                "--storage-account",
                storage_account,
                "--resource-group",
                resource_group,
                "--name",
                share_name,
                "--quota",
                str(quota_gb),
                "--enabled-protocols",
                "NFS",
                "--root-squash",
                "NoRootSquash",
                "--output",
                "json",
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.warning(f"Failed to create file share: {error_msg}")
            # Don't fail the entire operation, share might already exist

    @classmethod
    def _create_file_share(cls, storage_account: str, share_name: str, quota_gb: int) -> None:
        """Create NFS file share in storage account (legacy method for backwards compatibility)."""
        # This method is kept for backwards compatibility but shouldn't be used for new code
        cls._create_nfs_file_share(storage_account, "", share_name, quota_gb)

    @classmethod
    def list_storage(cls, resource_group: str) -> list[StorageInfo]:
        """List all azlin-managed storage accounts in resource group.

        Args:
            resource_group: Azure resource group

        Returns:
            List of StorageInfo objects
        """
        try:
            cmd = [
                "az",
                "storage",
                "account",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                "[?tags.\"managed-by\"=='azlin']",
                "--output",
                "json",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)

            accounts = json.loads(result.stdout)

            storage_list = []
            for account in accounts:
                # Determine tier from SKU
                sku = account.get("sku", {}).get("name", "")
                tier = "Premium" if "Premium" in sku else "Standard"

                # Get file share info for size
                size_gb = cls._get_share_quota(account["name"], resource_group)

                nfs_endpoint = f"{account['name']}.file.core.windows.net:/{account['name']}/home"

                storage_list.append(
                    StorageInfo(
                        name=account["name"],
                        resource_group=resource_group,
                        region=account["location"],
                        tier=tier,
                        size_gb=size_gb,
                        nfs_endpoint=nfs_endpoint,
                        created=datetime.fromisoformat(
                            account.get("creationTime", "").replace("Z", "+00:00")
                        )
                        if account.get("creationTime")
                        else datetime.now(),
                    )
                )

            return storage_list

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.warning(f"Failed to list storage accounts: {error_msg}")
            return []
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse storage account list: {e}")
            return []

    @classmethod
    def _get_share_quota(cls, storage_account: str, resource_group: str) -> int:
        """Get file share quota in GB."""
        try:
            cmd = [
                "az",
                "storage",
                "share-rm",
                "list",
                "--storage-account",
                storage_account,
                "--resource-group",
                resource_group,
                "--query",
                "[0].shareQuota",
                "--output",
                "tsv",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
            return 100  # Default

        except (ValueError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Failed to get storage quota for {storage_name}: {e}")
            return 100  # Default

    @classmethod
    def get_storage(cls, name: str, resource_group: str) -> StorageInfo:
        """Get storage account details.

        Args:
            name: Storage account name
            resource_group: Azure resource group

        Returns:
            StorageInfo with storage details

        Raises:
            StorageNotFoundError: If storage doesn't exist
        """
        try:
            cmd = [
                "az",
                "storage",
                "account",
                "show",
                "--name",
                name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

            account = json.loads(result.stdout)

            # Determine tier from SKU
            sku = account.get("sku", {}).get("name", "")
            tier = "Premium" if "Premium" in sku else "Standard"

            # Get file share info for size
            size_gb = cls._get_share_quota(name, resource_group)

            nfs_endpoint = f"{name}.file.core.windows.net:/{name}/home"

            return StorageInfo(
                name=name,
                resource_group=resource_group,
                region=account["location"],
                tier=tier,
                size_gb=size_gb,
                nfs_endpoint=nfs_endpoint,
                created=datetime.fromisoformat(
                    account.get("creationTime", "").replace("Z", "+00:00")
                )
                if account.get("creationTime")
                else datetime.now(),
            )

        except subprocess.CalledProcessError as e:
            if "ResourceNotFound" in (e.stderr or ""):
                raise StorageNotFoundError(f"Storage account {name} not found") from e
            error_msg = e.stderr if e.stderr else str(e)
            raise StorageError(f"Failed to get storage account: {error_msg}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise StorageError(f"Failed to parse storage account info: {e}") from e

    @classmethod
    def get_storage_status(cls, name: str, resource_group: str) -> StorageStatus:
        """Get detailed storage status including usage and connected VMs.

        Args:
            name: Storage account name
            resource_group: Azure resource group

        Returns:
            StorageStatus with detailed information
        """
        # Get basic storage info
        info = cls.get_storage(name, resource_group)

        # Get usage information
        used_gb = cls._get_storage_usage(name)
        utilization = (used_gb / info.size_gb * 100) if info.size_gb > 0 else 0

        # Get connected VMs from config
        from azlin.config_manager import ConfigManager

        connected_vms = []
        try:
            # Get all VMs that have this storage attached
            config_obj = ConfigManager.load_config()
            config_dict = config_obj.to_dict()
            vm_storage = config_dict.get("vm_storage", {})
            connected_vms = [vm for vm, storage in vm_storage.items() if storage == name]
        except Exception as e:
            logger.warning(f"Failed to get connected VMs: {e}")

        # Calculate monthly cost
        cost_per_month = info.size_gb * cls.COST_PER_GB[info.tier]

        return StorageStatus(
            info=info,
            used_gb=used_gb,
            utilization_percent=utilization,
            connected_vms=connected_vms,
            cost_per_month=cost_per_month,
        )

    @classmethod
    def _get_storage_usage(cls, storage_account: str) -> float:
        """Get storage usage in GB."""
        # For now, return 0 as usage metrics require additional setup
        # In production, would query Azure Monitor metrics
        return 0.0

    @classmethod
    def delete_storage(cls, name: str, resource_group: str, force: bool = False) -> None:
        """Delete storage account.

        Args:
            name: Storage account name
            resource_group: Azure resource group
            force: Skip connected VMs check if True

        Raises:
            StorageInUseError: If VMs still connected and not force
            StorageError: If deletion fails
        """
        # Check if VMs are connected (unless force)
        if not force:
            try:
                status = cls.get_storage_status(name, resource_group)
                if status.connected_vms:
                    vm_list = ", ".join(status.connected_vms)
                    raise StorageInUseError(
                        f"Storage {name} still has VMs connected: {vm_list}. "
                        "Detach VMs first or use --force"
                    )
            except StorageNotFoundError:
                # Storage doesn't exist, deletion is idempotent
                logger.info(f"Storage {name} doesn't exist, nothing to delete")
                return

        # Delete storage account
        try:
            cmd = [
                "az",
                "storage",
                "account",
                "delete",
                "--name",
                name,
                "--resource-group",
                resource_group,
                "--yes",
                "--output",
                "none",
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)

            logger.info(f"Deleted storage account {name}")

        except subprocess.CalledProcessError as e:
            if "ResourceNotFound" in (e.stderr or ""):
                # Already deleted, idempotent
                logger.info(f"Storage {name} already deleted")
                return
            error_msg = e.stderr if e.stderr else str(e)
            raise StorageError(f"Failed to delete storage account: {error_msg}") from e

    @classmethod
    def _validate_name(cls, name: str) -> None:
        """Validate storage account name."""
        if len(name) < cls.MIN_NAME_LENGTH:
            raise ValidationError(f"Storage name must be at least {cls.MIN_NAME_LENGTH} characters")

        if len(name) > cls.MAX_NAME_LENGTH:
            raise ValidationError(f"Storage name must be at most {cls.MAX_NAME_LENGTH} characters")

        if not cls.VALID_NAME_PATTERN.match(name):
            raise ValidationError("Storage name must be alphanumeric lowercase (a-z, 0-9)")

    @classmethod
    def _validate_tier(cls, tier: str) -> None:
        """Validate storage tier."""
        if tier not in cls.VALID_TIERS:
            raise ValidationError(
                f"Tier must be one of: {', '.join(cls.VALID_TIERS)} (got: {tier})"
            )

    @classmethod
    def _validate_size(cls, size_gb: int) -> None:
        """Validate storage size."""
        if size_gb <= 0:
            raise ValidationError("Size must be greater than zero")

        if size_gb < 0:
            raise ValidationError("Size must be positive")


# Public API
__all__ = [
    "StorageError",
    "StorageInUseError",
    "StorageInfo",
    "StorageManager",
    "StorageNotFoundError",
    "StorageStatus",
    "ValidationError",
]
