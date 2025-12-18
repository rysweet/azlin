"""Azure resource conflict error detection and transformation.

This module detects Azure resource conflict errors and transforms them into
clear, actionable user-friendly messages with specific resolution commands.

Philosophy:
- Standard library only (no external dependencies)
- Flexible parsing (JSON and plain text errors)
- Actionable suggestions (specific commands, not generic advice)
- Debug preservation (full error details in debug logs)
- Self-contained and regeneratable

Public API:
    is_resource_conflict: Detect if error message indicates resource conflict
    parse_conflict_error: Extract conflict details from error message
    format_conflict_error: Transform into user-friendly message
    ResourceConflictInfo: Dataclass containing conflict details

Example:
    >>> from azlin.resource_conflict_error_handler import (
    ...     is_resource_conflict,
    ...     parse_conflict_error,
    ...     format_conflict_error,
    ... )
    >>>
    >>> azure_error = "ERROR: The resource 'my-vm' already exists in location 'eastus'."
    >>>
    >>> if is_resource_conflict(azure_error):
    ...     conflict_info = parse_conflict_error(azure_error)
    ...     user_message = format_conflict_error(conflict_info)
    ...     print(user_message)  # Clear, actionable guidance
"""

import contextlib
import json
import re
from dataclasses import dataclass

__all__ = [
    "ResourceConflictInfo",
    "format_conflict_error",
    "is_resource_conflict",
    "parse_conflict_error",
]


@dataclass
class ResourceConflictInfo:
    """Details extracted from Azure resource conflict error.

    Attributes:
        resource_name: Name of the conflicting resource
        resource_type: Type of resource (e.g., "Microsoft.Compute/virtualMachines")
        existing_location: Location where resource currently exists
        attempted_location: Location where user attempted to create resource
        resource_group: Resource group containing the resource
        original_error: Full original error message (for debug logs)
    """

    resource_name: str | None = None
    resource_type: str | None = None
    existing_location: str | None = None
    attempted_location: str | None = None
    resource_group: str | None = None
    original_error: str | None = None


def is_resource_conflict(error_message: str | None) -> bool:
    """Detect if error message indicates an Azure resource conflict.

    Recognizes various conflict error patterns:
    - "already exists"
    - "conflicts with existing"
    - "ResourceExists" / "ConflictError"
    - Location mismatch errors

    Args:
        error_message: Error message from Azure CLI or SDK

    Returns:
        True if error indicates resource conflict, False otherwise

    Example:
        >>> is_resource_conflict("The resource 'test-vm' already exists")
        True
        >>> is_resource_conflict("Authentication failed")
        False
    """
    if not error_message:
        return False

    # Convert to lowercase for case-insensitive matching
    msg_lower = error_message.lower()

    # Common conflict patterns
    conflict_patterns = [
        "already exists",
        "conflicts with existing",
        "resourceexists",
        "conflicterror",
        "resource exists",
        "conflict",
    ]

    return any(pattern in msg_lower for pattern in conflict_patterns)


def parse_conflict_error(
    error_message: str,
    resource_name: str | None = None,
    attempted_location: str | None = None,
) -> ResourceConflictInfo | None:
    """Extract resource conflict details from Azure error message.

    Parses both JSON and plain text error formats to extract:
    - Resource name
    - Resource type
    - Existing location
    - Attempted location (if mismatch)
    - Resource group

    Args:
        error_message: Error message from Azure CLI or SDK
        resource_name: Optional hint for resource name (used if not in error)
        attempted_location: Optional hint for attempted location

    Returns:
        ResourceConflictInfo with extracted details, or None if not a conflict

    Example:
        >>> error = "ERROR: Resource 'my-vm' already exists in 'eastus'"
        >>> info = parse_conflict_error(error)
        >>> print(info.resource_name)
        my-vm
        >>> print(info.existing_location)
        eastus
    """
    if not is_resource_conflict(error_message):
        return None

    conflict_info = ResourceConflictInfo(original_error=error_message)

    # Try JSON parsing first (suppress errors and fall back to plain text)
    with contextlib.suppress(json.JSONDecodeError, KeyError):
        _parse_json_error(error_message, conflict_info)

    # Always try plain text parsing (may extract additional details)
    _parse_plain_text_error(error_message, conflict_info)

    # Apply hints if values still missing
    if not conflict_info.resource_name and resource_name:
        conflict_info.resource_name = resource_name
    if not conflict_info.attempted_location and attempted_location:
        conflict_info.attempted_location = attempted_location

    return conflict_info


def format_conflict_error(conflict_info: ResourceConflictInfo) -> str:
    """Format resource conflict into user-friendly message with actionable steps.

    Generates clear error message with:
    - Description of what exists and where
    - Explanation of the problem
    - Specific resolution commands

    Args:
        conflict_info: Parsed conflict details

    Returns:
        Formatted user-friendly error message

    Example:
        >>> info = ResourceConflictInfo(
        ...     resource_name="my-vm",
        ...     existing_location="eastus",
        ...     resource_group="my-rg"
        ... )
        >>> message = format_conflict_error(info)
        >>> print(message)
        ERROR: Resource 'my-vm' already exists in location 'eastus'
        ...
    """
    name = conflict_info.resource_name or "unknown"
    location = conflict_info.existing_location or "unknown location"
    rg = conflict_info.resource_group

    # Start with basic error message
    lines = [f"ERROR: Resource '{name}' already exists in location '{location}'"]
    lines.append("")

    # Add location mismatch explanation if applicable
    if (
        conflict_info.attempted_location
        and conflict_info.attempted_location != conflict_info.existing_location
    ):
        lines.append(
            f"You attempted to create this resource in '{conflict_info.attempted_location}', "
            f"but it already exists in '{location}'. Azure resources cannot be moved between locations."
        )
        lines.append("")

    # Add resource type context if available
    if conflict_info.resource_type:
        resource_type_friendly = _get_friendly_resource_type(conflict_info.resource_type)
        lines.append(f"A {resource_type_friendly} with this name already exists.")
        lines.append("")

    # Add resolution steps
    lines.append("To resolve:")

    # Option 1: Use different name / rename / choose different
    lines.append("  # Choose a different name (rename):")
    if rg:
        lines.append(f"  azlin vm create {name}-2 --resource-group {rg}")
    else:
        lines.append(f"  azlin vm create {name}-2")
    lines.append("")

    # Option 2: Delete existing (if we have enough info)
    if rg:
        lines.append("  # Or delete the existing resource:")
        lines.append(f"  az vm delete --name {name} --resource-group {rg} --yes")
        lines.append("")

    # Option 3: Use existing
    lines.append("  # Or use existing resource if it meets your needs")

    return "\n".join(lines)


# Private helper functions


def _parse_json_error(error_message: str, conflict_info: ResourceConflictInfo) -> None:
    """Extract conflict details from JSON error structure.

    Args:
        error_message: Error message (potentially JSON)
        conflict_info: ResourceConflictInfo to populate (modified in place)
    """
    # Try to parse as JSON
    try:
        error_data = json.loads(error_message)
    except json.JSONDecodeError:
        # Not JSON, return without modification
        return

    # Navigate nested error structure
    if "error" in error_data:
        error_obj = error_data["error"]

        # Extract from message field
        if "message" in error_obj:
            _parse_plain_text_error(error_obj["message"], conflict_info)

        # Extract from details field
        if "details" in error_obj:
            details = error_obj["details"]
            if isinstance(details, dict):
                conflict_info.resource_name = details.get(
                    "resourceName", conflict_info.resource_name
                )
                conflict_info.resource_type = details.get(
                    "resourceType", conflict_info.resource_type
                )
                conflict_info.existing_location = details.get(
                    "existingLocation", conflict_info.existing_location
                )
                conflict_info.resource_group = details.get(
                    "resourceGroup", conflict_info.resource_group
                )

        # Extract from additionalInfo field
        if "additionalInfo" in error_obj:
            for info_item in error_obj["additionalInfo"]:
                if isinstance(info_item, dict) and "info" in info_item:
                    info = info_item["info"]
                    conflict_info.resource_name = info.get(
                        "resourceName", conflict_info.resource_name
                    )
                    conflict_info.resource_type = info.get(
                        "resourceType", conflict_info.resource_type
                    )


def _parse_plain_text_error(error_message: str, conflict_info: ResourceConflictInfo) -> None:
    """Extract conflict details from plain text error message using regex.

    Args:
        error_message: Plain text error message
        conflict_info: ResourceConflictInfo to populate (modified in place)
    """
    # Extract resource name (various quote styles)
    # Order matters - try specific patterns first, then general patterns
    if not conflict_info.resource_name:
        name_patterns = [
            r"[Rr]esource ['\"`]([^'\"`]+)['\"`] of type",  # "Resource 'name' of type" - must come before general patterns
            r"[Vv]irtual [Mm]achine ['\"`]([^'\"`]+)['\"`]",  # "Virtual Machine 'name'"
            r"[Vv][Mm] ['\"`]([^'\"`]+)['\"`]",  # "VM 'name'"
            r"[Rr]esource [Nn]ame: ([^\s]+)",  # "Resource Name: name"
            r"['\"`]([^'\"`]+)['\"`] already exists",  # "'name' already exists"
            # Try ConflictError pattern (match name before "in resource group")
            r"ConflictError:.*?['\"`]([^'\"`]+)['\"`] in resource group",  # Match VM name, not RG
            r"[Rr]esource ['\"`]([^'\"`]+)['\"`]",  # "Resource 'name'" - general, last resort
        ]
        for pattern in name_patterns:
            match = re.search(pattern, error_message)
            if match:
                name = match.group(1)
                # Skip if this looks like a resource group (contains "rg" suffix) or a resource type path
                if not re.match(r".*-rg$", name) and not re.match(r"[A-Z][a-z]+\.[A-Z]", name):
                    conflict_info.resource_name = name
                    break

    # Extract resource group
    if not conflict_info.resource_group:
        rg_patterns = [
            r"resource group ['\"`]([^'\"`]+)['\"`]",
            r"[Rr]esource [Gg]roup: ([^\s]+)",
        ]
        for pattern in rg_patterns:
            match = re.search(pattern, error_message)
            if match:
                conflict_info.resource_group = match.group(1)
                break

    # Extract existing location
    if not conflict_info.existing_location:
        location_patterns = [
            r"in location ['\"`]([^'\"`]+)['\"`]",
            r"exists in ['\"`]([^'\"`]+)['\"`]",
            r"[Ll]ocation: ([^\s]+)",
        ]
        for pattern in location_patterns:
            match = re.search(pattern, error_message)
            if match:
                conflict_info.existing_location = match.group(1)
                break

    # Extract attempted location (for mismatch errors)
    if not conflict_info.attempted_location:
        attempted_patterns = [
            r"attempted to create (?:it )?in (?:location )?['\"`]([^'\"`]+)['\"`]",
            r"you attempted.*?['\"`]([^'\"`]+)['\"`]",
        ]
        for pattern in attempted_patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                conflict_info.attempted_location = match.group(1)
                break

    # Extract resource type
    if not conflict_info.resource_type:
        type_patterns = [
            r"(Microsoft\.[A-Za-z]+/[A-Za-z]+)",
            r"[Tt]ype ['\"`]([^'\"`]+)['\"`]",
        ]
        for pattern in type_patterns:
            match = re.search(pattern, error_message)
            if match:
                conflict_info.resource_type = match.group(1)
                break

        # Infer type from context (preserve exact casing when found)
        if not conflict_info.resource_type:
            # Try to find exact match with proper casing
            for keyword in ["Virtual Machine", "VM", "Storage Account"]:
                if keyword in error_message:
                    conflict_info.resource_type = keyword
                    break

            # Fall back to case-insensitive matching
            if not conflict_info.resource_type:
                msg_lower = error_message.lower()
                if "virtual machine" in msg_lower:
                    conflict_info.resource_type = "Virtual Machine"
                elif "vm" in msg_lower:
                    conflict_info.resource_type = "VM"
                elif "storage account" in msg_lower:
                    conflict_info.resource_type = "Storage Account"


def _get_friendly_resource_type(resource_type: str) -> str:
    """Convert Azure resource type to user-friendly name.

    Args:
        resource_type: Azure resource type (e.g., "Microsoft.Compute/virtualMachines")

    Returns:
        Friendly name (e.g., "Virtual Machine")
    """
    # Map full type names to friendly names
    type_map = {
        "Microsoft.Compute/virtualMachines": "Virtual Machine",
        "Microsoft.Storage/storageAccounts": "Storage Account",
        "Microsoft.Network/networkInterfaces": "Network Interface",
        "Microsoft.Network/publicIPAddresses": "Public IP Address",
        "Microsoft.Network/virtualNetworks": "Virtual Network",
        "Microsoft.Network/networkSecurityGroups": "Network Security Group",
    }

    # Check direct mapping
    if resource_type in type_map:
        return type_map[resource_type]

    # Try to extract friendly name from type path
    if "/" in resource_type:
        simple_name = resource_type.split("/")[-1]
        # Convert camelCase to Title Case with spaces
        friendly = re.sub(r"([A-Z])", r" \1", simple_name).strip()
        return friendly

    # Return as-is if no conversion possible
    return resource_type
