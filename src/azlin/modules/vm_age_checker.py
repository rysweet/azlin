"""VM Age Detection Module.

This module provides functionality to determine VM age based on creation time.
Used to skip auto-sync operations for newly created VMs that haven't completed
SSH initialization.

Security:
- Input validation for VM names and resource groups
- No shell=True for subprocess
- Sanitized logging
"""

import json
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _sanitize_for_logging(value: str) -> str:
    """Sanitize string for safe logging.

    Prevents log injection by removing control characters and newlines.

    Args:
        value: String to sanitize

    Returns:
        Sanitized string safe for logging
    """
    return value.encode("ascii", "replace").decode("ascii").replace("\n", " ").replace("\r", " ")


@dataclass
class VMAgeInfo:
    """VM age information."""

    vm_name: str
    age_seconds: float
    created_time: datetime
    is_new: bool
    cache_timestamp: float = 0.0  # Time when this entry was cached


class VMAgeChecker:
    """Check VM age to determine if SSH auto-sync should be skipped.

    Newly created VMs may not have SSH fully initialized, causing
    auto-sync operations to timeout. This checker identifies VMs
    younger than a threshold and allows skipping auto-sync for them.
    """

    # Cache to avoid repeated Azure CLI calls
    _cache: dict[str, VMAgeInfo] = {}
    _cache_ttl: int = 300  # 5 minutes
    _cache_lock = threading.Lock()  # Thread safety for cache operations

    @staticmethod
    def _validate_inputs(vm_name: str, resource_group: str) -> None:
        """Validate VM name and resource group format.

        Args:
            vm_name: VM name to validate
            resource_group: Resource group to validate

        Raises:
            ValueError: If inputs are invalid
        """
        if not vm_name or not vm_name.strip():
            raise ValueError("VM name cannot be empty")

        if not resource_group or not resource_group.strip():
            raise ValueError("Resource group cannot be empty")

        # Azure naming rules: 1-64 chars, alphanumeric + hyphen/underscore
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", vm_name):
            raise ValueError(f"Invalid VM name format: {vm_name}")

        if not re.match(r"^[a-zA-Z0-9_\-\.()]{1,90}$", resource_group):
            raise ValueError(f"Invalid resource group format: {resource_group}")

    @classmethod
    def get_vm_age(cls, vm_name: str, resource_group: str, timeout: int = 10) -> VMAgeInfo | None:
        """Get VM age information.

        Args:
            vm_name: VM name
            resource_group: Resource group containing the VM
            timeout: Azure CLI command timeout in seconds (default: 10)

        Returns:
            VMAgeInfo object with age details, or None if age cannot be determined

        Example:
            >>> age_info = VMAgeChecker.get_vm_age("my-vm", "my-rg")
            >>> if age_info and age_info.is_new:
            ...     print(f"VM is {age_info.age_seconds} seconds old")
        """
        # Validate inputs
        try:
            cls._validate_inputs(vm_name, resource_group)
        except ValueError as e:
            logger.warning(f"Invalid input: {e}")
            return None

        # Check cache first (with thread safety)
        cache_key = f"{resource_group}/{vm_name}"
        with cls._cache_lock:
            if cache_key in cls._cache:
                cached = cls._cache[cache_key]
                now_timestamp = time.time()
                # Check if cache entry is still valid (within TTL)
                if now_timestamp - cached.cache_timestamp < cls._cache_ttl:
                    logger.debug(f"Using cached VM age for {_sanitize_for_logging(vm_name)}")
                    # Update age_seconds to current time
                    age_now = (datetime.now(UTC) - cached.created_time).total_seconds()
                    return VMAgeInfo(
                        vm_name=cached.vm_name,
                        age_seconds=age_now,
                        created_time=cached.created_time,
                        is_new=cached.is_new,
                        cache_timestamp=cached.cache_timestamp,
                    )

        # Query Azure for VM creation time
        try:
            result = subprocess.run(
                [
                    "az",
                    "vm",
                    "show",
                    "--name",
                    vm_name,
                    "--resource-group",
                    resource_group,
                    "--query",
                    "timeCreated",
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            if result.returncode != 0:
                logger.debug(
                    f"Could not get VM creation time for {_sanitize_for_logging(vm_name)}: {result.stderr.strip()}"
                )
                return None

            # Parse creation time
            time_created_str = json.loads(result.stdout.strip())
            if not time_created_str:
                logger.debug(f"VM {_sanitize_for_logging(vm_name)} has no timeCreated field")
                return None

            # Parse ISO 8601 timestamp
            created_time = datetime.fromisoformat(time_created_str.replace("Z", "+00:00"))

            # Calculate age
            now = datetime.now(UTC)
            age_seconds = (now - created_time).total_seconds()

            # Create age info (is_new will be determined by caller's threshold)
            age_info = VMAgeInfo(
                vm_name=vm_name,
                age_seconds=age_seconds,
                created_time=created_time,
                is_new=False,  # Will be set by is_vm_ready_for_auto_sync
                cache_timestamp=time.time(),
            )

            # Cache result (with thread safety)
            with cls._cache_lock:
                cls._cache[cache_key] = age_info

            logger.debug(f"VM {_sanitize_for_logging(vm_name)} is {age_seconds:.1f} seconds old")
            return age_info

        except subprocess.TimeoutExpired:
            logger.warning(
                f"Timeout querying VM age for {_sanitize_for_logging(vm_name)} (>{timeout}s)"
            )
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"Failed to parse VM creation time for {_sanitize_for_logging(vm_name)}: {e}"
            )
            return None
        except Exception as e:
            logger.warning(
                f"Unexpected error getting VM age for {_sanitize_for_logging(vm_name)}: {e}"
            )
            return None

    @classmethod
    def is_vm_ready_for_auto_sync(
        cls, vm_name: str, resource_group: str, threshold_seconds: int = 600
    ) -> bool:
        """Check if VM is ready for auto-sync operations.

        VMs younger than threshold are considered "not ready" for auto-sync
        as SSH may not be fully initialized.

        Args:
            vm_name: VM name
            resource_group: Resource group containing the VM
            threshold_seconds: Age threshold in seconds (default: 600 = 10 minutes)

        Returns:
            True if VM is ready for auto-sync (older than threshold or age unknown),
            False if VM is too new for auto-sync

        Fail-safe behavior:
            - If age cannot be determined, returns True (assume ready)
            - This prevents blocking connections to existing VMs

        Example:
            >>> if VMAgeChecker.is_vm_ready_for_auto_sync("my-vm", "my-rg"):
            ...     print("VM is ready for auto-sync")
            ... else:
            ...     print("VM is too new, skipping auto-sync")
        """
        age_info = cls.get_vm_age(vm_name, resource_group)

        if age_info is None:
            # Fail-safe: If we can't determine age, assume VM is old enough
            logger.debug(
                f"Could not determine age for {_sanitize_for_logging(vm_name)}, assuming ready for auto-sync"
            )
            return True

        is_ready = age_info.age_seconds >= threshold_seconds

        if not is_ready:
            logger.info(
                f"VM {_sanitize_for_logging(vm_name)} is too new for auto-sync "
                f"({age_info.age_seconds:.1f}s old, threshold: {threshold_seconds}s)"
            )
        else:
            logger.debug(
                f"VM {_sanitize_for_logging(vm_name)} is ready for auto-sync ({age_info.age_seconds:.1f}s old)"
            )

        return is_ready

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the age information cache.

        Useful for testing or when VM recreation occurs.
        """
        with cls._cache_lock:
            cls._cache.clear()
        logger.debug("VM age cache cleared")


__all__ = ["VMAgeChecker", "VMAgeInfo"]
