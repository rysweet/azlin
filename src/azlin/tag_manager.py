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
    - Session name management via tags (azlin-session)
    - Cross-resource-group VM discovery (managed-by=azlin)
    """

    # Standard azlin tag keys
    TAG_MANAGED_BY = "managed-by"
    TAG_SESSION = "azlin-session"
    TAG_CREATED = "azlin-created"
    TAG_OWNER = "azlin-owner"

    # Tag values
    MANAGED_BY_VALUE = "azlin"

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
                cmd, capture_output=True, text=True, timeout=120, check=True
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
                cmd, capture_output=True, text=True, timeout=120, check=True
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
                cmd, capture_output=True, text=True, timeout=120, check=True
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

    # Session management methods

    @classmethod
    def get_session_name(cls, vm_name: str, resource_group: str) -> str | None:
        """Get session name from VM tags.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            Session name or None if not set
        """
        try:
            tags = cls.get_tags(vm_name, resource_group)
            return tags.get(cls.TAG_SESSION)
        except TagManagerError:
            logger.debug(f"Failed to get session name for {vm_name}")
            return None

    @classmethod
    def set_session_name(cls, vm_name: str, resource_group: str, session_name: str) -> bool:
        """Set session name in VM tags.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            session_name: Session name to set

        Returns:
            True if successful

        Raises:
            TagManagerError: If tag update fails
            ValueError: If session name invalid
        """
        if not cls.validate_session_name(session_name):
            msg = f"Invalid session name: {session_name}. Must match [a-zA-Z0-9_-]+"
            raise ValueError(msg)

        # Update session tag
        cls.add_tags(vm_name, resource_group, {cls.TAG_SESSION: session_name})
        return True

    @classmethod
    def delete_session_name(cls, vm_name: str, resource_group: str) -> bool:
        """Remove session name from VM tags.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            True if session name was removed
        """
        try:
            cls.remove_tags(vm_name, resource_group, [cls.TAG_SESSION])
            return True
        except TagManagerError:
            logger.debug(f"Failed to delete session name for {vm_name}")
            return False

    @classmethod
    def get_vm_by_session(
        cls, session_name: str, resource_group: str | None = None
    ) -> VMInfo | None:
        """Find VM by session name.

        Args:
            session_name: Session name to search for
            resource_group: Optional RG to limit search (None = search all RGs)

        Returns:
            VMInfo if found, None otherwise
        """
        try:
            vms = cls.list_managed_vms(resource_group)

            # Find VM with matching session tag
            for vm in vms:
                vm_session = cls.get_session_name(vm.name, vm.resource_group)
                if vm_session == session_name:
                    return vm

            return None
        except Exception as e:
            logger.warning(f"Failed to find VM by session '{session_name}': {e}")
            return None

    @classmethod
    def list_managed_vms(cls, resource_group: str | None = None) -> list[VMInfo]:
        """List all azlin-managed VMs.

        Args:
            resource_group: Optional RG to filter (None = all RGs)

        Returns:
            List of VMInfo objects for managed VMs

        Raises:
            TagManagerError: If list operation fails
        """
        from azlin.vm_manager import VMManager

        try:
            # Build Azure CLI command
            cmd = ["az", "vm", "list", "--output", "json"]

            if resource_group:
                cmd.extend(["--resource-group", resource_group])

            # Query for VMs with managed-by=azlin tag
            cmd.extend(
                [
                    "--query",
                    f"[?tags.\"{cls.TAG_MANAGED_BY}\"=='{cls.MANAGED_BY_VALUE}']",
                ]
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

            vms_data = json.loads(result.stdout)

            # Convert to VMInfo objects using VMManager's parser
            vms = []
            for vm_data in vms_data:
                try:
                    # Extract resource group from VM ID
                    vm_id = vm_data.get("id", "")
                    rg_parts = vm_id.split("/")
                    rg = None
                    for i, part in enumerate(rg_parts):
                        if part == "resourceGroups" and i + 1 < len(rg_parts):
                            rg = rg_parts[i + 1]
                            break

                    if not rg:
                        rg = vm_data.get("resourceGroup")

                    if rg:
                        # Use VMManager to get full VM info
                        vm_info = VMManager.get_vm(vm_data["name"], rg)
                        if vm_info:
                            vms.append(vm_info)
                except Exception as e:
                    logger.warning(f"Failed to parse VM data: {e}")
                    continue

            return vms

        except subprocess.TimeoutExpired as e:
            msg = "Azure CLI timeout while listing VMs"
            raise TagManagerError(msg) from e
        except subprocess.CalledProcessError as e:
            msg = f"Failed to list VMs: {e.stderr}"
            raise TagManagerError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Failed to parse VM list response: {e}"
            raise TagManagerError(msg) from e

    @classmethod
    def set_managed_tags(
        cls,
        vm_name: str,
        resource_group: str,
        owner: str | None = None,
        session_name: str | None = None,
    ) -> bool:
        """Set standard azlin management tags on VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            owner: Optional owner username
            session_name: Optional session name

        Returns:
            True if successful

        Raises:
            TagManagerError: If tag update fails
        """
        from datetime import UTC, datetime

        tags = {
            cls.TAG_MANAGED_BY: cls.MANAGED_BY_VALUE,
            cls.TAG_CREATED: datetime.now(UTC).isoformat(),
        }

        if owner:
            tags[cls.TAG_OWNER] = owner

        if session_name:
            if not cls.validate_session_name(session_name):
                msg = f"Invalid session name: {session_name}"
                raise ValueError(msg)
            tags[cls.TAG_SESSION] = session_name

        cls.add_tags(vm_name, resource_group, tags)
        return True

    @classmethod
    def validate_session_name(cls, session_name: str) -> bool:
        """Validate session name format.

        Args:
            session_name: Session name to validate

        Returns:
            True if valid
        """
        if not session_name:
            return False

        if len(session_name) > 64:  # Reasonable limit
            return False

        # Must match: letters, numbers, hyphens, underscores
        pattern = r"^[a-zA-Z0-9_-]+$"
        return bool(re.match(pattern, session_name))

    @classmethod
    def list_all_vms_cross_rg(cls) -> list[VMInfo]:
        """List ALL VMs across all resource groups (managed + unmanaged).

        Similar to list_managed_vms() but WITHOUT tag filtering.
        Returns all VMs accessible to the authenticated user.

        This is used in cross-RG mode to detect unmanaged VMs for notification purposes.

        Returns:
            List of VMInfo objects for all VMs across all RGs

        Raises:
            TagManagerError: If listing fails
        """
        from azlin.vm_manager import VMManager

        try:
            # Build Azure CLI command - list ALL VMs without tag filter
            cmd = ["az", "vm", "list", "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

            vms_data = json.loads(result.stdout)

            # Convert to VMInfo objects using VMManager's parser
            vms = []
            for vm_data in vms_data:
                try:
                    # Extract resource group from VM ID
                    vm_id = vm_data.get("id", "")
                    rg_parts = vm_id.split("/")
                    rg = None
                    for i, part in enumerate(rg_parts):
                        if part == "resourceGroups" and i + 1 < len(rg_parts):
                            rg = rg_parts[i + 1]
                            break

                    if not rg:
                        rg = vm_data.get("resourceGroup")

                    if rg:
                        # Use VMManager to get full VM info
                        vm_info = VMManager.get_vm(vm_data["name"], rg)
                        if vm_info:
                            vms.append(vm_info)
                except Exception as e:
                    logger.warning(f"Failed to parse VM data: {e}")
                    continue

            return vms

        except subprocess.TimeoutExpired as e:
            msg = "Azure CLI timeout while listing VMs"
            raise TagManagerError(msg) from e
        except subprocess.CalledProcessError as e:
            msg = f"Failed to list VMs: {e.stderr}"
            raise TagManagerError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Failed to parse VM list response: {e}"
            raise TagManagerError(msg) from e
