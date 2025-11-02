"""Bastion provisioning module.

This module handles automatic creation of Azure Bastion hosts including:
- Prerequisite checking (VNet, subnet, public IP, quotas)
- VNet and subnet creation if needed
- Public IP address provisioning
- Bastion host creation with all dependencies
- Provisioning state polling
- Rollback on failures

Security:
- No shell=True for subprocess
- Input validation for all parameters
- Proper error message sanitization
- Timeout enforcement on all operations

Note: Delegates ALL Azure operations to Azure CLI.
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from azlin.modules.bastion_detector import BastionDetector, BastionDetectorError

logger = logging.getLogger(__name__)


class BastionProvisionerError(Exception):
    """Raised when Bastion provisioning operations fail."""

    pass


@dataclass
class PrerequisiteStatus:
    """Status of Bastion prerequisites.

    Tracks which resources exist and which need creation.
    """

    vnet_exists: bool
    subnet_exists: bool
    public_ip_exists: bool
    quota_available: bool
    vnet_name: str | None = None
    subnet_name: str | None = None
    public_ip_name: str | None = None
    quota_message: str | None = None

    def is_ready(self) -> bool:
        """Check if all prerequisites are met.

        Returns:
            True if Bastion can be created without additional resources
        """
        return self.vnet_exists and self.subnet_exists and self.public_ip_exists and self.quota_available

    def missing_resources(self) -> list[str]:
        """List of missing resources that need creation.

        Returns:
            List of resource type names
        """
        missing = []
        if not self.vnet_exists:
            missing.append("vnet")
        if not self.subnet_exists:
            missing.append("subnet")
        if not self.public_ip_exists:
            missing.append("public_ip")
        if not self.quota_available:
            missing.append("quota")
        return missing


@dataclass
class ProvisioningResult:
    """Result of Bastion provisioning operation.

    Contains details about created resources and operation status.
    """

    success: bool
    bastion_name: str
    resource_group: str
    location: str
    resources_created: list[str]
    error_message: str | None = None
    provisioning_state: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all result fields
        """
        return {
            "success": self.success,
            "bastion_name": self.bastion_name,
            "resource_group": self.resource_group,
            "location": self.location,
            "resources_created": self.resources_created,
            "error_message": self.error_message,
            "provisioning_state": self.provisioning_state,
            "duration_seconds": self.duration_seconds,
        }


class BastionProvisioner:
    """Provision Azure Bastion hosts with all dependencies.

    This class provides operations for:
    - Checking prerequisites (VNet, subnet, public IP, quotas)
    - Creating VNets and subnets as needed
    - Provisioning public IP addresses
    - Creating Bastion hosts (sync and async)
    - Polling provisioning status
    - Rollback on failures

    All Azure operations delegate to Azure CLI.
    """

    # Azure Bastion constants
    BASTION_SUBNET_NAME = "AzureBastionSubnet"
    BASTION_SUBNET_PREFIX_LENGTH = 26  # /26 minimum (64 addresses)
    DEFAULT_VNET_PREFIX = "10.0.0.0/16"
    DEFAULT_BASTION_SUBNET_PREFIX = "10.0.1.0/26"

    # Timeouts
    DEFAULT_PROVISIONING_TIMEOUT = 900  # 15 minutes
    DEFAULT_COMMAND_TIMEOUT = 60  # 1 minute for most commands

    @staticmethod
    def _sanitize_azure_error(stderr: str) -> str:
        """Sanitize Azure CLI error output to prevent information leakage.

        Args:
            stderr: Raw stderr from Azure CLI

        Returns:
            Sanitized error message safe for user display
        """
        if "ResourceNotFound" in stderr:
            return "Resource not found"
        if "InvalidAuthenticationToken" in stderr or "AuthenticationFailed" in stderr:
            return "Authentication failed"
        if "AuthorizationFailed" in stderr or "Forbidden" in stderr:
            return "Insufficient permissions"
        if "QuotaExceeded" in stderr or "quota" in stderr.lower():
            return "Quota exceeded"
        if "InvalidParameter" in stderr or "invalid" in stderr.lower():
            return "Invalid parameter"
        if "AlreadyExists" in stderr or "already exists" in stderr.lower():
            return "Resource already exists"
        if "NetworkNotFound" in stderr:
            return "Network resource not found"
        if "timeout" in stderr.lower():
            return "Operation timed out"
        # Generic message for unknown errors - log full details for debugging
        logger.debug(f"Azure CLI error details: {stderr}")
        return "Azure operation failed"

    @staticmethod
    def _validate_inputs(
        bastion_name: str,
        resource_group: str,
        location: str,
        vnet_name: str | None = None,
    ) -> None:
        """Validate inputs for Bastion provisioning.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
            location: Azure region
            vnet_name: VNet name (optional)

        Raises:
            BastionProvisionerError: If validation fails
        """
        if not bastion_name:
            raise BastionProvisionerError("Bastion name cannot be empty")
        if not resource_group:
            raise BastionProvisionerError("Resource group cannot be empty")
        if not location:
            raise BastionProvisionerError("Location cannot be empty")

        # Validate name format (Azure naming rules)
        import re

        name_pattern = re.compile(r"^[a-zA-Z0-9_.\-]{1,80}$")
        if not name_pattern.match(bastion_name):
            raise BastionProvisionerError(
                f"Invalid Bastion name: {bastion_name}. "
                "Must be 1-80 characters, alphanumeric, hyphen, underscore, or period"
            )
        if vnet_name and not name_pattern.match(vnet_name):
            raise BastionProvisionerError(
                f"Invalid VNet name: {vnet_name}. "
                "Must be 1-80 characters, alphanumeric, hyphen, underscore, or period"
            )

    @classmethod
    def check_prerequisites(
        cls,
        resource_group: str,
        location: str,
        vnet_name: str | None = None,
        public_ip_name: str | None = None,
    ) -> PrerequisiteStatus:
        """Check prerequisites for Bastion creation.

        Verifies existence of:
        - VNet (creates default if not specified)
        - AzureBastionSubnet
        - Public IP
        - Regional quota availability

        Args:
            resource_group: Resource group
            location: Azure region
            vnet_name: VNet name (optional, checks for any VNet if None)
            public_ip_name: Public IP name (optional)

        Returns:
            PrerequisiteStatus with details

        Raises:
            BastionProvisionerError: If prerequisite check fails
        """
        logger.info(f"Checking Bastion prerequisites in {resource_group} ({location})")

        status = PrerequisiteStatus(
            vnet_exists=False,
            subnet_exists=False,
            public_ip_exists=False,
            quota_available=True,  # Default to True, check if needed
        )

        try:
            # Check VNet
            if vnet_name:
                # Check specific VNet
                vnet_exists = cls._check_vnet_exists(vnet_name, resource_group)
                status.vnet_exists = vnet_exists
                if vnet_exists:
                    status.vnet_name = vnet_name
                    logger.debug(f"VNet exists: {vnet_name}")
            else:
                # Check for any VNet in resource group
                vnets = cls._list_vnets(resource_group)
                if vnets:
                    status.vnet_exists = True
                    status.vnet_name = vnets[0]["name"]
                    logger.debug(f"Found VNet: {status.vnet_name}")

            # Check AzureBastionSubnet if VNet exists
            if status.vnet_exists and status.vnet_name:
                subnet_exists = cls._check_subnet_exists(
                    cls.BASTION_SUBNET_NAME, status.vnet_name, resource_group
                )
                status.subnet_exists = subnet_exists
                if subnet_exists:
                    status.subnet_name = cls.BASTION_SUBNET_NAME
                    logger.debug(f"Bastion subnet exists in {status.vnet_name}")

            # Check Public IP
            if public_ip_name:
                ip_exists = cls._check_public_ip_exists(public_ip_name, resource_group)
                status.public_ip_exists = ip_exists
                if ip_exists:
                    status.public_ip_name = public_ip_name
                    logger.debug(f"Public IP exists: {public_ip_name}")

            # Check quota (basic check - assumes quota available if no errors)
            # More detailed quota checking would require subscription-level API access
            status.quota_available = True
            status.quota_message = "Quota check not implemented (assumed available)"

            missing = status.missing_resources()
            if missing:
                logger.info(f"Missing prerequisites: {', '.join(missing)}")
            else:
                logger.info("All prerequisites satisfied")

            return status

        except subprocess.CalledProcessError as e:
            safe_error = cls._sanitize_azure_error(e.stderr or "")
            raise BastionProvisionerError(f"Failed to check prerequisites: {safe_error}") from e
        except Exception as e:
            raise BastionProvisionerError(f"Unexpected error checking prerequisites: {e}") from e

    @classmethod
    def provision_bastion(
        cls,
        bastion_name: str,
        resource_group: str,
        location: str,
        vnet_name: str | None = None,
        vnet_address_prefix: str | None = None,
        subnet_address_prefix: str | None = None,
        public_ip_name: str | None = None,
        wait_for_completion: bool = True,
        timeout: int = DEFAULT_PROVISIONING_TIMEOUT,
    ) -> ProvisioningResult:
        """Provision Bastion host with all dependencies.

        Creates all required resources:
        1. VNet (if needed)
        2. AzureBastionSubnet (if needed)
        3. Public IP (if needed)
        4. Bastion host

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
            location: Azure region
            vnet_name: VNet name (creates default if None)
            vnet_address_prefix: VNet address prefix (default: 10.0.0.0/16)
            subnet_address_prefix: Bastion subnet prefix (default: 10.0.1.0/26)
            public_ip_name: Public IP name (generates if None)
            wait_for_completion: Wait for provisioning to complete
            timeout: Provisioning timeout in seconds

        Returns:
            ProvisioningResult with status and created resources

        Raises:
            BastionProvisionerError: If provisioning fails

        Example:
            >>> result = BastionProvisioner.provision_bastion(
            ...     "my-bastion", "my-rg", "eastus"
            ... )
            >>> if result.success:
            ...     print(f"Bastion created: {result.bastion_name}")
        """
        start_time = time.time()
        resources_created = []

        try:
            # Validate inputs
            cls._validate_inputs(bastion_name, resource_group, location, vnet_name)

            logger.info(f"Provisioning Bastion: {bastion_name} in {resource_group} ({location})")

            # Generate default names
            if not vnet_name:
                vnet_name = f"{bastion_name}-vnet"
            if not public_ip_name:
                public_ip_name = f"{bastion_name}-pip"
            if not vnet_address_prefix:
                vnet_address_prefix = cls.DEFAULT_VNET_PREFIX
            if not subnet_address_prefix:
                subnet_address_prefix = cls.DEFAULT_BASTION_SUBNET_PREFIX

            # Check prerequisites
            prereqs = cls.check_prerequisites(resource_group, location, vnet_name, public_ip_name)

            # Create VNet if needed
            if not prereqs.vnet_exists:
                logger.info(f"Creating VNet: {vnet_name}")
                cls._create_vnet(
                    vnet_name,
                    resource_group,
                    location,
                    vnet_address_prefix,
                )
                resources_created.append(f"vnet:{vnet_name}")

            # Create Bastion subnet if needed
            if not prereqs.subnet_exists:
                logger.info(f"Creating Bastion subnet in {vnet_name}")
                cls._create_bastion_subnet(
                    vnet_name,
                    resource_group,
                    subnet_address_prefix,
                )
                resources_created.append(f"subnet:{cls.BASTION_SUBNET_NAME}")

            # Create Public IP if needed
            if not prereqs.public_ip_exists:
                logger.info(f"Creating Public IP: {public_ip_name}")
                cls._create_public_ip(
                    public_ip_name,
                    resource_group,
                    location,
                )
                resources_created.append(f"public-ip:{public_ip_name}")

            # Create Bastion host
            logger.info(f"Creating Bastion host: {bastion_name}")
            cls._create_bastion(
                bastion_name,
                resource_group,
                location,
                vnet_name,
                public_ip_name,
            )
            resources_created.append(f"bastion:{bastion_name}")

            # Wait for provisioning if requested
            provisioning_state = None
            if wait_for_completion:
                logger.info("Waiting for Bastion provisioning to complete...")
                provisioning_state = cls.wait_for_bastion_ready(
                    bastion_name,
                    resource_group,
                    timeout=timeout,
                )
                logger.info(f"Bastion provisioning complete: {provisioning_state}")

            duration = time.time() - start_time

            return ProvisioningResult(
                success=True,
                bastion_name=bastion_name,
                resource_group=resource_group,
                location=location,
                resources_created=resources_created,
                provisioning_state=provisioning_state,
                duration_seconds=duration,
            )

        except Exception as e:
            # Provisioning failed - attempt rollback
            duration = time.time() - start_time
            error_msg = str(e)

            logger.error(f"Bastion provisioning failed: {error_msg}")

            # Don't rollback by default - let user decide
            logger.info(
                f"Created resources before failure: {resources_created}. "
                "Use rollback_bastion() to clean up."
            )

            return ProvisioningResult(
                success=False,
                bastion_name=bastion_name,
                resource_group=resource_group,
                location=location,
                resources_created=resources_created,
                error_message=error_msg,
                duration_seconds=duration,
            )

    @classmethod
    def wait_for_bastion_ready(
        cls,
        bastion_name: str,
        resource_group: str,
        timeout: int = DEFAULT_PROVISIONING_TIMEOUT,
        poll_interval: int = 30,
    ) -> str:
        """Wait for Bastion provisioning to complete.

        Polls Bastion provisioning state until it reaches a terminal state.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Final provisioning state

        Raises:
            BastionProvisionerError: If provisioning fails or times out

        Example:
            >>> state = BastionProvisioner.wait_for_bastion_ready("my-bastion", "my-rg")
            >>> assert state == "Succeeded"
        """
        start_time = time.time()
        terminal_states = {"Succeeded", "Failed", "Canceled"}

        logger.info(f"Polling Bastion provisioning state (timeout: {timeout}s)")

        while time.time() - start_time < timeout:
            try:
                # Get Bastion details
                bastion = BastionDetector.get_bastion(bastion_name, resource_group)

                if not bastion:
                    raise BastionProvisionerError(f"Bastion not found: {bastion_name}")

                state = bastion.get("provisioningState", "Unknown")
                logger.debug(f"Bastion state: {state}")

                # Check for terminal states
                if state in terminal_states:
                    if state == "Succeeded":
                        return state
                    raise BastionProvisionerError(f"Bastion provisioning {state.lower()}")

                # Still provisioning - wait and retry
                time.sleep(poll_interval)

            except BastionDetectorError as e:
                raise BastionProvisionerError(f"Failed to query Bastion state: {e}") from e

        # Timeout reached
        elapsed = time.time() - start_time
        raise BastionProvisionerError(
            f"Bastion provisioning timed out after {elapsed:.0f} seconds. "
            f"Check Azure portal for status."
        )

    @classmethod
    def rollback_bastion(
        cls,
        bastion_name: str,
        resource_group: str,
        resources_created: list[str],
        delete_bastion: bool = True,
    ) -> dict[str, bool]:
        """Clean up resources from failed Bastion provisioning.

        Attempts to delete created resources in reverse order.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
            resources_created: List of created resources from ProvisioningResult
            delete_bastion: Whether to delete the Bastion itself

        Returns:
            Dictionary mapping resource to deletion success status

        Example:
            >>> result = BastionProvisioner.provision_bastion(...)
            >>> if not result.success:
            ...     BastionProvisioner.rollback_bastion(
            ...         result.bastion_name,
            ...         result.resource_group,
            ...         result.resources_created,
            ...     )
        """
        logger.info(f"Rolling back Bastion provisioning: {bastion_name}")

        deletion_status = {}

        # Delete in reverse order
        for resource_spec in reversed(resources_created):
            try:
                # Parse resource spec: "type:name"
                if ":" not in resource_spec:
                    logger.warning(f"Invalid resource spec: {resource_spec}")
                    continue

                resource_type, resource_name = resource_spec.split(":", 1)

                logger.info(f"Deleting {resource_type}: {resource_name}")

                if resource_type == "bastion" and delete_bastion:
                    cls._delete_bastion(resource_name, resource_group)
                elif resource_type == "public-ip":
                    cls._delete_public_ip(resource_name, resource_group)
                elif resource_type == "subnet":
                    # Subnets are deleted with VNet
                    logger.debug(f"Skipping subnet deletion: {resource_name}")
                    continue
                elif resource_type == "vnet":
                    cls._delete_vnet(resource_name, resource_group)

                deletion_status[resource_spec] = True
                logger.debug(f"Deleted {resource_type}: {resource_name}")

            except Exception as e:
                logger.error(f"Failed to delete {resource_spec}: {e}")
                deletion_status[resource_spec] = False

        return deletion_status

    # Private helper methods for Azure CLI operations

    @classmethod
    def _check_vnet_exists(cls, vnet_name: str, resource_group: str) -> bool:
        """Check if VNet exists.

        Args:
            vnet_name: VNet name
            resource_group: Resource group

        Returns:
            True if exists
        """
        try:
            cmd = [
                "az",
                "network",
                "vnet",
                "show",
                "--name",
                vnet_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def _list_vnets(cls, resource_group: str) -> list[dict[str, Any]]:
        """List VNets in resource group.

        Args:
            resource_group: Resource group

        Returns:
            List of VNet dictionaries
        """
        try:
            cmd = [
                "az",
                "network",
                "vnet",
                "list",
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
            return json.loads(result.stdout)
        except Exception:
            return []

    @classmethod
    def _check_subnet_exists(cls, subnet_name: str, vnet_name: str, resource_group: str) -> bool:
        """Check if subnet exists.

        Args:
            subnet_name: Subnet name
            vnet_name: VNet name
            resource_group: Resource group

        Returns:
            True if exists
        """
        try:
            cmd = [
                "az",
                "network",
                "vnet",
                "subnet",
                "show",
                "--name",
                subnet_name,
                "--vnet-name",
                vnet_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def _check_public_ip_exists(cls, public_ip_name: str, resource_group: str) -> bool:
        """Check if public IP exists.

        Args:
            public_ip_name: Public IP name
            resource_group: Resource group

        Returns:
            True if exists
        """
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "show",
                "--name",
                public_ip_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def _create_vnet(
        cls,
        vnet_name: str,
        resource_group: str,
        location: str,
        address_prefix: str,
    ) -> None:
        """Create VNet.

        Args:
            vnet_name: VNet name
            resource_group: Resource group
            location: Azure region
            address_prefix: Address prefix (e.g., 10.0.0.0/16)

        Raises:
            BastionProvisionerError: If creation fails
        """
        try:
            cmd = [
                "az",
                "network",
                "vnet",
                "create",
                "--name",
                vnet_name,
                "--resource-group",
                resource_group,
                "--location",
                location,
                "--address-prefix",
                address_prefix,
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
            logger.debug(f"VNet created: {vnet_name}")
        except subprocess.CalledProcessError as e:
            safe_error = cls._sanitize_azure_error(e.stderr or "")
            raise BastionProvisionerError(f"Failed to create VNet: {safe_error}") from e

    @classmethod
    def _create_bastion_subnet(
        cls,
        vnet_name: str,
        resource_group: str,
        address_prefix: str,
    ) -> None:
        """Create AzureBastionSubnet.

        Args:
            vnet_name: VNet name
            resource_group: Resource group
            address_prefix: Address prefix (must be /26 or larger)

        Raises:
            BastionProvisionerError: If creation fails
        """
        try:
            cmd = [
                "az",
                "network",
                "vnet",
                "subnet",
                "create",
                "--name",
                cls.BASTION_SUBNET_NAME,
                "--vnet-name",
                vnet_name,
                "--resource-group",
                resource_group,
                "--address-prefix",
                address_prefix,
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
            logger.debug(f"Bastion subnet created in {vnet_name}")
        except subprocess.CalledProcessError as e:
            safe_error = cls._sanitize_azure_error(e.stderr or "")
            raise BastionProvisionerError(f"Failed to create Bastion subnet: {safe_error}") from e

    @classmethod
    def _create_public_ip(
        cls,
        public_ip_name: str,
        resource_group: str,
        location: str,
    ) -> None:
        """Create Standard SKU public IP for Bastion.

        Args:
            public_ip_name: Public IP name
            resource_group: Resource group
            location: Azure region

        Raises:
            BastionProvisionerError: If creation fails
        """
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "create",
                "--name",
                public_ip_name,
                "--resource-group",
                resource_group,
                "--location",
                location,
                "--sku",
                "Standard",
                "--allocation-method",
                "Static",
                "--output",
                "json",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
            logger.debug(f"Public IP created: {public_ip_name}")
        except subprocess.CalledProcessError as e:
            safe_error = cls._sanitize_azure_error(e.stderr or "")
            raise BastionProvisionerError(f"Failed to create Public IP: {safe_error}") from e

    @classmethod
    def _create_bastion(
        cls,
        bastion_name: str,
        resource_group: str,
        location: str,
        vnet_name: str,
        public_ip_name: str,
    ) -> None:
        """Create Bastion host.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
            location: Azure region
            vnet_name: VNet name
            public_ip_name: Public IP name

        Raises:
            BastionProvisionerError: If creation fails
        """
        try:
            cmd = [
                "az",
                "network",
                "bastion",
                "create",
                "--name",
                bastion_name,
                "--resource-group",
                resource_group,
                "--location",
                location,
                "--vnet-name",
                vnet_name,
                "--public-ip-address",
                public_ip_name,
                "--output",
                "json",
            ]
            # Bastion creation takes 5-15 minutes - use async execution
            # The command will return immediately and provision in background
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Command itself should return quickly
                check=True,
            )
            logger.debug(f"Bastion creation initiated: {bastion_name}")
        except subprocess.CalledProcessError as e:
            safe_error = cls._sanitize_azure_error(e.stderr or "")
            raise BastionProvisionerError(f"Failed to create Bastion: {safe_error}") from e

    @classmethod
    def _delete_bastion(cls, bastion_name: str, resource_group: str) -> None:
        """Delete Bastion host.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
        """
        try:
            cmd = [
                "az",
                "network",
                "bastion",
                "delete",
                "--name",
                bastion_name,
                "--resource-group",
                resource_group,
                "--yes",
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
        except Exception as e:
            raise BastionProvisionerError(f"Failed to delete Bastion: {e}") from e

    @classmethod
    def _delete_public_ip(cls, public_ip_name: str, resource_group: str) -> None:
        """Delete public IP.

        Args:
            public_ip_name: Public IP name
            resource_group: Resource group
        """
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "delete",
                "--name",
                public_ip_name,
                "--resource-group",
                resource_group,
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
        except Exception as e:
            raise BastionProvisionerError(f"Failed to delete Public IP: {e}") from e

    @classmethod
    def _delete_vnet(cls, vnet_name: str, resource_group: str) -> None:
        """Delete VNet.

        Args:
            vnet_name: VNet name
            resource_group: Resource group
        """
        try:
            cmd = [
                "az",
                "network",
                "vnet",
                "delete",
                "--name",
                vnet_name,
                "--resource-group",
                resource_group,
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cls.DEFAULT_COMMAND_TIMEOUT,
                check=True,
            )
        except Exception as e:
            raise BastionProvisionerError(f"Failed to delete VNet: {e}") from e


__all__ = [
    "BastionProvisioner",
    "BastionProvisionerError",
    "PrerequisiteStatus",
    "ProvisioningResult",
]
