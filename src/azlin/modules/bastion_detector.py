"""Bastion auto-detection module.

This module handles automatic detection of Azure Bastion hosts for VMs including:
- Detecting if a VM has access to a Bastion host
- Finding Bastion hosts in same VNet as VM
- Querying Bastion availability in resource group

Security:
- No shell=True for subprocess
- Input validation
- Error message sanitization

Thread Safety:
- Module-level cache (_bastion_cache) is NOT thread-safe
- Designed for CLI single-threaded execution
- Concurrent access may cause cache inconsistencies (non-critical)

Note: Delegates ALL Azure operations to Azure CLI.
"""

import json
import logging
import subprocess
import time
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# Module-level cache for Bastion listings to avoid repeated slow Azure CLI calls
# Cache key: resource_group (None for all resource groups)
# Cache value: tuple of (bastions list, timestamp)
_bastion_cache: dict[str | None, tuple[list[dict[str, Any]], float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


class BastionInfo(TypedDict):
    """Type definition for Bastion information dictionary."""

    name: str
    resource_group: str
    location: str | None


class BastionDetectorError(Exception):
    """Raised when Bastion detection operations fail."""

    pass


class BastionDetector:
    """Detect Azure Bastion hosts for VMs.

    This class provides operations for:
    - Auto-detecting Bastion availability for a VM
    - Finding Bastion hosts in resource group
    - Checking VNet connectivity

    All Azure operations delegate to Azure CLI.
    """

    @staticmethod
    def _sanitize_azure_error(stderr: str) -> str:
        """Sanitize Azure CLI error output to prevent information leakage.

        Args:
            stderr: Raw stderr from Azure CLI

        Returns:
            Sanitized error message safe for user display
        """
        # Check for known safe error patterns
        if "ResourceNotFound" in stderr:
            return "Resource not found"
        if "InvalidAuthenticationToken" in stderr or "AuthenticationFailed" in stderr:
            return "Authentication failed"
        if "AuthorizationFailed" in stderr or "Forbidden" in stderr:
            return "Insufficient permissions"
        if "SubscriptionNotFound" in stderr:
            return "Subscription not accessible"
        if "NetworkNotFound" in stderr:
            return "Network resource not found"
        # Generic message for unknown errors - log full details for debugging
        logger.debug(f"Azure CLI error details: {stderr}")
        return "Azure operation failed"

    @staticmethod
    def _check_azure_cli_responsive(timeout: int = 10) -> bool:
        """Check if Azure CLI is responsive before making actual calls.

        Pre-flight check to avoid hanging on slow Azure CLI responses.
        Uses a fast command (az account show) to test responsiveness.

        Args:
            timeout: Maximum seconds to wait for response

        Returns:
            True if Azure CLI responds within timeout, False otherwise
        """
        try:
            result = subprocess.run(
                ["az", "account", "show", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            # Any response (success or error) means CLI is responsive
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"Azure CLI pre-flight check timed out after {timeout}s")
            return False
        except FileNotFoundError:
            # Azure CLI not installed
            logger.debug("Azure CLI not found in PATH")
            return False
        except (OSError, subprocess.SubprocessError) as e:
            # CLI execution issues (permissions, broken installation, etc.)
            logger.debug(f"Azure CLI pre-flight check failed: {e}")
            return False
        except Exception as e:
            # Other errors (e.g., JSON parse) - CLI responded but with error
            # Treat as responsive since timeout didn't occur
            logger.debug(f"Azure CLI pre-flight check error (non-blocking): {e}")
            return True

    @classmethod
    def _get_cached_bastions(cls, resource_group: str | None) -> list[dict[str, Any]] | None:
        """Get cached Bastion listing if available and fresh.

        Args:
            resource_group: Resource group filter (None for all)

        Returns:
            Cached bastions list if available and fresh, None otherwise
        """
        if resource_group not in _bastion_cache:
            return None

        bastions, cached_at = _bastion_cache[resource_group]
        age = time.time() - cached_at

        if age > CACHE_TTL_SECONDS:
            # Cache expired
            logger.debug(f"Bastion cache expired (age: {age:.1f}s)")
            del _bastion_cache[resource_group]
            return None

        logger.debug(f"Using cached Bastion list (age: {age:.1f}s)")
        return bastions

    @classmethod
    def _cache_bastions(cls, resource_group: str | None, bastions: list[dict[str, Any]]) -> None:
        """Cache Bastion listing results.

        Args:
            resource_group: Resource group filter (None for all)
            bastions: List of Bastion hosts to cache
        """
        _bastion_cache[resource_group] = (bastions, time.time())
        logger.debug(f"Cached {len(bastions)} Bastion host(s) for resource_group={resource_group}")

    @classmethod
    def detect_bastion_for_vm(
        cls, vm_name: str, resource_group: str, vm_location: str | None = None
    ) -> BastionInfo | None:
        """Detect if a Bastion host is available for VM.

        Checks if there's a Bastion host in the same resource group
        and region that can be used to connect to the VM.

        Args:
            vm_name: VM name
            resource_group: Resource group containing VM
            vm_location: VM region/location (optional, for region validation)

        Returns:
            Dict with bastion_name and resource_group if found, None otherwise

        Example:
            >>> bastion = BastionDetector.detect_bastion_for_vm("my-vm", "my-rg", "westus")
            >>> if bastion:
            ...     print(f"Found: {bastion['name']}")
        """
        try:
            # First, check if there's a Bastion in the same resource group
            bastions = cls.list_bastions(resource_group)

            if not bastions:
                logger.debug(f"No Bastion hosts found in resource group: {resource_group}")
                return None

            # Filter out failed bastions - only use successfully provisioned ones
            successful_bastions = [
                b for b in bastions if b.get("provisioningState", "").lower() == "succeeded"
            ]

            if not successful_bastions:
                logger.debug(
                    f"No successfully provisioned Bastion hosts in resource group: {resource_group}"
                )
                return None

            # If VM location provided, filter Bastions by matching region
            if vm_location:
                matching_bastions = [
                    b
                    for b in successful_bastions
                    if b.get("location", "").lower() == vm_location.lower()
                ]

                if not matching_bastions:
                    logger.warning(
                        f"Found {len(successful_bastions)} successfully provisioned Bastion(s) in {resource_group}, "
                        f"but none in VM region '{vm_location}'. "
                        f"Bastion locations: {[b.get('location') for b in successful_bastions]}"
                    )
                    return None

                bastion = matching_bastions[0]
            else:
                # No location filtering - use first successfully provisioned Bastion found
                bastion = successful_bastions[0]
            logger.info(
                f"Detected Bastion host '{bastion['name']}' "
                f"(region: {bastion.get('location', 'unknown')}) in {resource_group} for VM {vm_name}"
            )

            # Always return location for consistency (may be None if not available)
            return {
                "name": bastion["name"],
                "resource_group": resource_group,
                "location": bastion.get("location"),
            }

        except Exception as e:
            logger.debug(f"Failed to detect Bastion for VM {vm_name}: {e}")
            return None

    @classmethod
    def list_bastions(cls, resource_group: str | None = None) -> list[dict[str, Any]]:
        """List Bastion hosts with caching and timeout protection.

        First checks cache for recent results (5 min TTL). If cache miss,
        performs pre-flight check to verify Azure CLI is responsive before
        making the actual Bastion list call. Returns empty list on timeout
        rather than raising exception (graceful degradation).

        Args:
            resource_group: Resource group to filter (None for all)

        Returns:
            List of Bastion host dictionaries (empty list on timeout)

        Raises:
            BastionDetectorError: If listing fails (non-timeout errors)
        """
        # Check cache first
        cached = cls._get_cached_bastions(resource_group)
        if cached is not None:
            return cached

        # Pre-flight check: verify Azure CLI is responsive
        if not cls._check_azure_cli_responsive(timeout=10):
            logger.warning("Azure CLI not responsive, skipping Bastion detection")
            return []

        try:
            cmd = ["az", "network", "bastion", "list", "--output", "json"]

            if resource_group:
                cmd.extend(["--resource-group", resource_group])

            # Reduced timeout from 30s to 10s based on pre-flight check
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            bastions = json.loads(result.stdout)
            logger.debug(f"Found {len(bastions)} Bastion host(s)")

            # Cache successful results
            cls._cache_bastions(resource_group, bastions)

            return bastions

        except subprocess.TimeoutExpired:
            # Graceful degradation: return empty list instead of raising
            logger.warning("Bastion detection timed out after 10 seconds, skipping auto-detection")
            return []
        except subprocess.CalledProcessError as e:
            safe_error = cls._sanitize_azure_error(e.stderr)
            logger.error(f"Failed to list Bastion hosts: {safe_error}")
            raise BastionDetectorError(f"Failed to list Bastion hosts: {safe_error}") from e
        except json.JSONDecodeError as e:
            raise BastionDetectorError(f"Failed to parse Bastion list: {e}") from e
        except Exception as e:
            raise BastionDetectorError(f"Unexpected error listing Bastions: {e}") from e

    @classmethod
    def get_bastion(cls, bastion_name: str, resource_group: str) -> dict[str, Any] | None:
        """Get Bastion host details.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group

        Returns:
            Bastion details dict or None if not found

        Raises:
            BastionDetectorError: If query fails
        """
        try:
            cmd = [
                "az",
                "network",
                "bastion",
                "show",
                "--name",
                bastion_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,  # Don't raise on error
                timeout=10,  # Reduced from 30s for consistency
            )

            if result.returncode != 0:
                if "ResourceNotFound" in result.stderr:
                    logger.debug(f"Bastion not found: {bastion_name} in {resource_group}")
                    return None
                safe_error = cls._sanitize_azure_error(result.stderr)
                logger.error(f"Failed to get Bastion: {safe_error}")
                raise BastionDetectorError(f"Failed to get Bastion: {safe_error}")

            bastion = json.loads(result.stdout)
            logger.debug(f"Found Bastion: {bastion_name}")

            return bastion

        except subprocess.TimeoutExpired:
            logger.warning(f"Bastion query timed out after 10 seconds for {bastion_name}, skipping")
            return None
        except json.JSONDecodeError as e:
            raise BastionDetectorError(f"Failed to parse Bastion details: {e}") from e
        except Exception as e:
            raise BastionDetectorError(f"Unexpected error getting Bastion: {e}") from e

    @classmethod
    def check_bastion_exists(cls, bastion_name: str, resource_group: str) -> bool:
        """Check if Bastion host exists.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group

        Returns:
            True if exists, False otherwise
        """
        try:
            bastion = cls.get_bastion(bastion_name, resource_group)
            return bastion is not None
        except BastionDetectorError:
            return False


__all__ = ["BastionDetector", "BastionDetectorError"]
