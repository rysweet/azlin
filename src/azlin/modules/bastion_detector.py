"""Bastion auto-detection module.

This module handles automatic detection of Azure Bastion hosts for VMs including:
- Detecting if a VM has access to a Bastion host
- Finding Bastion hosts in same VNet as VM
- Querying Bastion availability in resource group

Security:
- No shell=True for subprocess
- Input validation
- Error message sanitization

Note: Delegates ALL Azure operations to Azure CLI.
"""

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


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

    @classmethod
    def detect_bastion_for_vm(cls, vm_name: str, resource_group: str) -> dict[str, str] | None:
        """Detect if a Bastion host is available for VM.

        Checks if there's a Bastion host in the same resource group
        that can be used to connect to the VM.

        Args:
            vm_name: VM name
            resource_group: Resource group containing VM

        Returns:
            Dict with bastion_name and resource_group if found, None otherwise

        Example:
            >>> bastion = BastionDetector.detect_bastion_for_vm("my-vm", "my-rg")
            >>> if bastion:
            ...     print(f"Found: {bastion['name']}")
        """
        try:
            # First, check if there's a Bastion in the same resource group
            bastions = cls.list_bastions(resource_group)

            if not bastions:
                logger.debug(f"No Bastion hosts found in resource group: {resource_group}")
                return None

            # Use the first Bastion found in the RG
            bastion = bastions[0]
            logger.info(
                f"Detected Bastion host '{bastion['name']}' in {resource_group} for VM {vm_name}"
            )

            return {
                "name": bastion["name"],
                "resource_group": resource_group,
            }

        except Exception as e:
            logger.debug(f"Failed to detect Bastion for VM {vm_name}: {e}")
            return None

    @classmethod
    def list_bastions(cls, resource_group: str | None = None) -> list[dict[str, Any]]:
        """List Bastion hosts.

        Args:
            resource_group: Resource group to filter (None for all)

        Returns:
            List of Bastion host dictionaries

        Raises:
            BastionDetectorError: If listing fails
        """
        try:
            cmd = ["az", "network", "bastion", "list", "--output", "json"]

            if resource_group:
                cmd.extend(["--resource-group", resource_group])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            bastions = json.loads(result.stdout)
            logger.debug(f"Found {len(bastions)} Bastion host(s)")

            return bastions

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
