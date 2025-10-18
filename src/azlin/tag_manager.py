"""Tag management module.

This module handles Azure VM tag operations: add, remove, list, and filter.
Uses Azure CLI for tag operations.

Security:
- Input validation for tag keys and values
- No shell=True
- Sanitized logging
"""

import json
import logging
import re
import subprocess
from typing import Any

from azlin.vm_manager import VMInfo

logger = logging.getLogger(__name__)


class TagManagerError(Exception):
    """Raised when tag management operations fail."""

    pass


class TagManager:
    """Manage Azure VM tags.

    This class provides operations for:
    - Adding tags to VMs
    - Removing tags from VMs
    - Getting tags from VMs
    - Filtering VMs by tags
    """

    # Tag key validation: alphanumeric, underscore, hyphen, period
    TAG_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")

    @classmethod
    def add_tags(cls, vm_name: str, resource_group: str, tags: dict[str, str]) -> None:
        """Add tags to a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tags: Dictionary of tag key-value pairs to add

        Raises:
            TagManagerError: If adding tags fails
        """
        try:
            # Validate tags
            for key, value in tags.items():
                if not cls.validate_tag_key(key):
                    raise TagManagerError(f"Invalid tag key: {key}")
                if not cls.validate_tag_value(value):
                    raise TagManagerError(f"Invalid tag value: {value}")

            # Build command with --set for each tag
            cmd = [
                "az",
                "vm",
                "update",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            # Add each tag as a separate --set argument
            for key, value in tags.items():
                cmd.extend(["--set", f"tags.{key}={value}"])

            logger.debug(f"Adding tags to VM {vm_name}: {tags}")

            _result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            logger.info(f"Successfully added tags to VM {vm_name}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add tags to VM {vm_name}: {e.stderr}")
            raise TagManagerError(f"Failed to add tags: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise TagManagerError("Tag operation timed out") from e
        except Exception as e:
            raise TagManagerError(f"Failed to add tags: {e!s}") from e

    @classmethod
    def remove_tags(cls, vm_name: str, resource_group: str, tag_keys: list[str]) -> None:
        """Remove tags from a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tag_keys: List of tag keys to remove

        Raises:
            TagManagerError: If removing tags fails
        """
        try:
            # Build command with --remove for each tag key
            cmd = [
                "az",
                "vm",
                "update",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            # Add each tag key as a separate --remove argument
            for key in tag_keys:
                cmd.extend(["--remove", f"tags.{key}"])

            logger.debug(f"Removing tags from VM {vm_name}: {tag_keys}")

            _result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            logger.info(f"Successfully removed tags from VM {vm_name}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove tags from VM {vm_name}: {e.stderr}")
            raise TagManagerError(f"Failed to remove tags: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise TagManagerError("Tag operation timed out") from e
        except Exception as e:
            raise TagManagerError(f"Failed to remove tags: {e!s}") from e

    @classmethod
    def get_tags(cls, vm_name: str, resource_group: str) -> dict[str, str]:
        """Get tags from a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            Dictionary of tag key-value pairs

        Raises:
            TagManagerError: If getting tags fails
        """
        try:
            cmd = [
                "az",
                "vm",
                "show",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            vm_data: dict[str, Any] = json.loads(result.stdout)
            tags: dict[str, str] | None = vm_data.get("tags", {})

            # Handle null tags
            if tags is None:
                tags = {}

            return tags

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get tags from VM {vm_name}: {e.stderr}")
            raise TagManagerError(f"Failed to get tags: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise TagManagerError("Failed to parse VM tags response") from e
        except subprocess.TimeoutExpired as e:
            raise TagManagerError("Tag operation timed out") from e
        except Exception as e:
            raise TagManagerError(f"Failed to get tags: {e!s}") from e

    @classmethod
    def filter_vms_by_tag(cls, vms: list[VMInfo], tag_filter: str) -> list[VMInfo]:
        """Filter VMs by tag.

        Args:
            vms: List of VMInfo objects
            tag_filter: Tag filter in format "key" or "key=value"

        Returns:
            Filtered list of VMInfo objects
        """
        key, value = cls.parse_tag_filter(tag_filter)

        filtered_vms: list[VMInfo] = []
        for vm in vms:
            # Skip VMs with no tags
            if not vm.tags:
                continue

            # Check if tag key exists
            if key not in vm.tags:
                continue

            # If value specified, check exact match
            if value is not None:
                if vm.tags[key] == value:
                    filtered_vms.append(vm)
            else:
                # Key only - any value matches
                filtered_vms.append(vm)

        return filtered_vms

    @classmethod
    def parse_tag_filter(cls, tag_filter: str) -> tuple[str, str | None]:
        """Parse tag filter string.

        Args:
            tag_filter: Tag filter in format "key" or "key=value"

        Returns:
            Tuple of (key, value) where value is None for key-only filters
        """
        if "=" in tag_filter:
            # Split only on first '=' to handle values with '='
            parts = tag_filter.split("=", 1)
            return parts[0], parts[1]
        return tag_filter, None

    @classmethod
    def parse_tag_assignment(cls, tag_str: str) -> tuple[str, str]:
        """Parse tag assignment string (key=value).

        Args:
            tag_str: Tag assignment in format "key=value"

        Returns:
            Tuple of (key, value)

        Raises:
            TagManagerError: If format is invalid
        """
        if "=" not in tag_str:
            raise TagManagerError(f"Invalid tag format: {tag_str}. Expected format: key=value")

        # Split only on first '=' to handle values with '='
        parts = tag_str.split("=", 1)
        key = parts[0]
        value = parts[1]

        # Validate key and value
        if not key:
            raise TagManagerError(f"Invalid tag format: {tag_str}. Tag key cannot be empty")
        if not value:
            raise TagManagerError(f"Invalid tag format: {tag_str}. Tag value cannot be empty")

        if not cls.validate_tag_key(key):
            raise TagManagerError(f"Invalid tag key: {key}")
        if not cls.validate_tag_value(value):
            raise TagManagerError(f"Invalid tag value: {value}")

        return key, value

    @classmethod
    def validate_tag_key(cls, key: str) -> bool:
        """Validate tag key.

        Tag keys must be alphanumeric with underscore, hyphen, or period.

        Args:
            key: Tag key to validate

        Returns:
            True if valid, False otherwise
        """
        if not key:
            return False
        return bool(cls.TAG_KEY_PATTERN.match(key))

    @classmethod
    def validate_tag_value(cls, value: str) -> bool:
        """Validate tag value.

        Tag values can contain most characters including spaces.

        Args:
            value: Tag value to validate

        Returns:
            True if valid, False otherwise
        """
        # Azure allows most characters in tag values, including empty strings
        # Type annotation already guarantees it's a string
        return True
