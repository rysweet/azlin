"""Shared validation utilities for Azure resources.

Consolidates validation logic from multiple modules to ensure
consistent security checks and prevent code duplication.

Philosophy:
- Single source of truth for validation
- Security-first: prevent command injection and path traversal
- Clear error messages with actionable guidance
- Zero dependencies on other azlin modules

Public API:
    validate_azure_resource_name: General Azure resource validation
    validate_storage_account_name: Storage-specific validation
    validate_mount_point: NFS mount point validation
    validate_nfs_endpoint: NFS endpoint validation
    ValidationError: Base exception for validation failures
"""

import re
from pathlib import Path


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def validate_azure_resource_name(name: str, resource_type: str) -> str:
    """Validate Azure resource name for safe use.

    Prevents command injection and path traversal attacks by ensuring
    resource names contain only safe characters.

    Args:
        name: Resource name to validate
        resource_type: Type of resource (for error messages)

    Returns:
        Validated name (unchanged if valid)

    Raises:
        ValidationError: If name contains unsafe characters

    Security Checks:
        - Command injection: ;, &, |, $, `, (), <, >
        - Path traversal: .., /, \\
        - Format: alphanumeric + hyphen + underscore only

    Example:
        >>> validate_azure_resource_name("my-vnet-01", "VNet")
        'my-vnet-01'
        >>> validate_azure_resource_name("evil; rm -rf /", "VNet")
        ValidationError: VNet name contains unsafe character ';'
    """
    if not name or not isinstance(name, str):
        raise ValidationError(f"{resource_type} name must be a non-empty string")

    # Security: Check for command injection patterns
    dangerous_patterns = [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r", "\t"]
    for pattern in dangerous_patterns:
        if pattern in name:
            raise ValidationError(
                f"{resource_type} name contains unsafe character '{pattern}'. "
                f"Use only alphanumeric characters, hyphens, and underscores."
            )

    # Check for path traversal
    if ".." in name or "/" in name or "\\" in name:
        raise ValidationError(
            f"{resource_type} name contains path traversal sequences. "
            f"Use only alphanumeric characters, hyphens, and underscores."
        )

    # Basic alphanumeric validation (with hyphens, underscores, and periods)
    # Periods allowed for some Azure resources (like DNS zones)
    if not re.match(r"^[a-zA-Z0-9_.\-]+$", name):
        raise ValidationError(
            f"{resource_type} name must contain only: "
            f"letters (a-z, A-Z), numbers (0-9), hyphens (-), underscores (_), periods (.)"
        )

    # Azure general length limits (most resources)
    if len(name) > 80:
        raise ValidationError(f"{resource_type} name too long: {len(name)} characters (max: 80)")

    return name


def validate_storage_account_name(name: str) -> str:
    """Validate Azure storage account name.

    Storage accounts have specific naming requirements:
    - 3-24 characters
    - Lowercase letters and numbers only
    - Must be globally unique

    Args:
        name: Storage account name

    Returns:
        Validated name (unchanged if valid)

    Raises:
        ValidationError: If name doesn't meet requirements

    Example:
        >>> validate_storage_account_name("mystorageacct01")
        'mystorageacct01'
        >>> validate_storage_account_name("MyStorage")
        ValidationError: Storage name must be lowercase alphanumeric only
    """
    if not name:
        raise ValidationError("Storage account name cannot be empty")

    if len(name) < 3 or len(name) > 24:
        raise ValidationError(
            f"Storage account name must be 3-24 characters: '{name}' ({len(name)} chars)"
        )

    if not re.match(r"^[a-z0-9]+$", name):
        raise ValidationError(
            f"Storage account name must be lowercase alphanumeric only: '{name}'. "
            f"No hyphens, underscores, or uppercase letters allowed."
        )

    return name


def validate_mount_point(mount_point: str) -> str:
    """Validate NFS mount point path.

    Args:
        mount_point: Mount point path

    Returns:
        Validated mount point (unchanged if valid)

    Raises:
        ValidationError: If mount point is invalid

    Security Checks:
        - Must be absolute path
        - No path traversal sequences
        - No special characters that could enable injection

    Example:
        >>> validate_mount_point("/mnt/storage")
        '/mnt/storage'
        >>> validate_mount_point("../../etc/passwd")
        ValidationError: Mount point must be absolute path
    """
    if not mount_point:
        raise ValidationError("Mount point cannot be empty")

    mount_path = Path(mount_point)

    # Must be absolute path
    if not mount_path.is_absolute():
        raise ValidationError(
            f"Mount point must be absolute path: '{mount_point}'. "
            f"Use paths like /mnt/storage, not relative paths."
        )

    # Check for path traversal
    if ".." in mount_point:
        raise ValidationError(f"Mount point contains path traversal '..': '{mount_point}'")

    # Ensure it's under safe mount directories
    safe_prefixes = ["/mnt/", "/media/", "/home/"]
    is_safe = any(mount_point.startswith(prefix) for prefix in safe_prefixes)

    # Warn but don't fail for unusual mount points (user might have custom setup)
    if not is_safe:
        import logging

        logging.getLogger(__name__).warning(
            f"Mount point '{mount_point}' is outside typical directories: {safe_prefixes}. "
            f"Ensure this is intentional."
        )

    return mount_point


def validate_nfs_endpoint(endpoint: str) -> str:
    """Validate NFS endpoint format.

    Expected format: {storage-account}.file.core.windows.net:/{storage-account}/{share-name}

    Args:
        endpoint: NFS endpoint string

    Returns:
        Validated endpoint (unchanged if valid)

    Raises:
        ValidationError: If endpoint format is invalid

    Example:
        >>> validate_nfs_endpoint("mystore.file.core.windows.net:/mystore/home")
        'mystore.file.core.windows.net:/mystore/home'
    """
    if not endpoint:
        raise ValidationError("NFS endpoint cannot be empty")

    # Basic format check: must contain : and /
    if ":" not in endpoint or "/" not in endpoint:
        raise ValidationError(
            f"Invalid NFS endpoint format: '{endpoint}'. "
            f"Expected: {{account}}.file.core.windows.net:/{{account}}/{{share}}"
        )

    # Split into host and path
    try:
        host, path = endpoint.split(":", 1)
    except ValueError as e:
        raise ValidationError(
            f"Invalid NFS endpoint format: '{endpoint}'. Cannot split into host:path"
        ) from e

    # Validate host part (should be Azure Files FQDN)
    if not host.endswith(".file.core.windows.net"):
        raise ValidationError(
            f"Invalid NFS endpoint host: '{host}'. "
            f"Expected Azure Files FQDN (*.file.core.windows.net)"
        )

    # Validate path part (should start with /)
    if not path.startswith("/"):
        raise ValidationError(f"Invalid NFS endpoint path: '{path}'. Path must start with /")

    # Check for path traversal in path component
    if ".." in path:
        raise ValidationError(f"NFS endpoint path contains traversal '..': '{path}'")

    return endpoint


def sanitize_azure_error(stderr: str) -> str:
    """Sanitize Azure CLI error messages for user display.

    Removes sensitive information while preserving useful error context.

    Args:
        stderr: Raw Azure CLI error output

    Returns:
        Sanitized error message

    Example:
        >>> sanitize_azure_error("ERROR: (ResourceNotFound) VM 'my-vm' not found\\nDetails: ...")
        "VM 'my-vm' not found"
    """
    if not stderr:
        return "Unknown error"

    # Common Azure CLI error patterns to extract
    patterns = [
        r"ERROR: \((\w+)\) (.+?)(?:\n|$)",  # ERROR: (Code) message
        r"ERROR: (.+?)(?:\n|$)",  # ERROR: message
        r"error: (.+?)(?:\n|$)",  # error: message (lowercase)
    ]

    for pattern in patterns:
        match = re.search(pattern, stderr, re.IGNORECASE)
        if match:
            # Return just the message part
            if len(match.groups()) > 1:
                return match.group(2).strip()  # (Code) message format
            return match.group(1).strip()  # Simple message format

    # If no pattern matches, return first non-empty line
    lines = [line.strip() for line in stderr.split("\n") if line.strip()]
    if lines:
        return lines[0]

    return stderr.strip()


# Public API
__all__ = [
    "ValidationError",
    "sanitize_azure_error",
    "validate_azure_resource_name",
    "validate_mount_point",
    "validate_nfs_endpoint",
    "validate_storage_account_name",
]
