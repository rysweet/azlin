"""Azure Storage Account Key Management.

This module retrieves storage account keys from Azure using the Azure SDK.
Keys are never logged or printed to ensure security.

Philosophy:
- Uses Azure SDK (azure-mgmt-storage) for key retrieval
- No credentials in code (uses DefaultAzureCredential)
- Keys are never logged or exposed
- Validates all inputs before Azure calls
- Returns structured data
- Fail fast with clear error messages

Security:
- Storage account keys are CRITICAL secrets
- Never log, print, or expose keys in error messages
- Only return keys to callers who need them for authentication
- Validate all inputs to prevent injection attacks

Public API:
    StorageKeyManager: Main storage key operations class
    StorageKeyError: Base exception
    StorageKeyNotFoundError: Storage account not found
    ValidationError: Invalid input parameters
"""

import logging
import re
from dataclasses import dataclass

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient

logger = logging.getLogger(__name__)


# Exceptions
class StorageKeyError(Exception):
    """Base exception for storage key operations."""

    pass


class StorageKeyNotFoundError(StorageKeyError):
    """Storage account not found or keys not accessible."""

    pass


class ValidationError(StorageKeyError):
    """Invalid input parameters."""

    pass


# Data Models
@dataclass
class StorageKeys:
    """Storage account keys (CRITICAL: Never log this object)."""

    key1: str
    key2: str

    def __repr__(self) -> str:
        """Prevent accidental exposure of keys in logs."""
        return "StorageKeys(key1=***REDACTED***, key2=***REDACTED***)"

    def __str__(self) -> str:
        """Prevent accidental exposure of keys in logs."""
        return "StorageKeys(keys redacted for security)"


class StorageKeyManager:
    """Manage Azure Storage Account key retrieval.

    This class provides methods to retrieve storage account keys from Azure
    using the Azure Management SDK. All operations use DefaultAzureCredential
    for authentication.
    """

    # Validation patterns
    STORAGE_NAME_PATTERN = re.compile(r"^[a-z0-9]{3,24}$")
    RESOURCE_GROUP_PATTERN = re.compile(r"^[\w\-\.()]{1,90}$")

    @classmethod
    def _validate_storage_name(cls, name: str) -> None:
        """Validate storage account name format.

        Args:
            name: Storage account name

        Raises:
            ValidationError: If name is invalid
        """
        if not cls.STORAGE_NAME_PATTERN.match(name):
            raise ValidationError(
                f"Invalid storage account name: {name}. "
                "Must be 3-24 characters, lowercase letters and numbers only."
            )

    @classmethod
    def _validate_resource_group(cls, resource_group: str) -> None:
        """Validate resource group name format.

        Args:
            resource_group: Resource group name

        Raises:
            ValidationError: If resource group name is invalid
        """
        if not cls.RESOURCE_GROUP_PATTERN.match(resource_group):
            raise ValidationError(
                f"Invalid resource group name: {resource_group}. "
                "Must be 1-90 characters, alphanumeric, hyphens, dots, or parentheses."
            )

    @classmethod
    def get_storage_keys(
        cls, storage_account_name: str, resource_group: str, subscription_id: str
    ) -> StorageKeys:
        """Get storage account keys from Azure.

        Retrieves the storage account keys using the Azure Management SDK.
        Keys are never logged or printed.

        Args:
            storage_account_name: Name of the storage account
            resource_group: Azure resource group containing the storage account
            subscription_id: Azure subscription ID

        Returns:
            StorageKeys: Object containing key1 and key2

        Raises:
            ValidationError: If input parameters are invalid
            StorageKeyNotFoundError: If storage account not found or inaccessible
            StorageKeyError: For other errors

        Example:
            >>> keys = StorageKeyManager.get_storage_keys(
            ...     "mystorageaccount",
            ...     "my-resource-group",
            ...     "00000000-0000-0000-0000-000000000000"
            ... )
            >>> # Use keys.key1 for authentication
        """
        # Validate inputs
        cls._validate_storage_name(storage_account_name)
        cls._validate_resource_group(resource_group)

        if not subscription_id or not subscription_id.strip():
            raise ValidationError("Subscription ID cannot be empty")

        logger.info(
            f"Retrieving storage keys for account: {storage_account_name} "
            f"in resource group: {resource_group}"
        )

        try:
            # Create Azure SDK client
            credential = DefaultAzureCredential()
            storage_client = StorageManagementClient(credential, subscription_id)

            # List keys for the storage account
            # NOTE: This returns both key1 and key2
            keys_result = storage_client.storage_accounts.list_keys(
                resource_group, storage_account_name
            )

            # Extract keys from result
            if keys_result.keys is None:
                raise StorageKeyError(
                    f"No keys returned for storage account: {storage_account_name}"
                )
            keys_list = list(keys_result.keys)
            if len(keys_list) < 2:
                raise StorageKeyError(
                    f"Expected at least 2 keys, got {len(keys_list)} for "
                    f"storage account: {storage_account_name}"
                )

            key1 = keys_list[0].value
            key2 = keys_list[1].value

            if not key1 or not key2:
                raise StorageKeyError(
                    f"Retrieved invalid keys for storage account: {storage_account_name}"
                )

            # SECURITY: Log success but never log the keys themselves
            logger.info(f"Successfully retrieved storage keys for account: {storage_account_name}")

            return StorageKeys(key1=key1, key2=key2)

        except ResourceNotFoundError as e:
            # Storage account doesn't exist or not accessible
            raise StorageKeyNotFoundError(
                f"Storage account not found: {storage_account_name} "
                f"in resource group: {resource_group}"
            ) from e
        except Exception as e:
            # Catch all other errors
            # SECURITY: Don't include key values in error messages
            logger.error(
                f"Failed to retrieve storage keys for account: {storage_account_name}. "
                f"Error type: {type(e).__name__}"
            )
            raise StorageKeyError(
                f"Failed to retrieve storage keys for account: {storage_account_name}. Error: {e}"
            ) from e


__all__ = [
    "StorageKeyError",
    "StorageKeyManager",
    "StorageKeyNotFoundError",
    "StorageKeys",
    "ValidationError",
]
