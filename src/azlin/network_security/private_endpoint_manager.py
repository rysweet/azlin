"""Private Endpoint Management for Secure Azure Service Access.

Manages Azure Private Endpoints for secure, private access to Azure services
(Storage, Key Vault, etc.) without exposing them to the public internet.

Key features:
- Private endpoint creation
- Private DNS zone configuration
- Network policy management
- VNet link configuration

Philosophy:
- Secure service access without public endpoints
- Delegate ALL Azure operations to Azure CLI
- Simple, working implementation
- Clear error messages

Public API:
    PrivateEndpointManager: Main private endpoint management class

Example:
    >>> manager = PrivateEndpointManager()
    >>> endpoint_id = manager.create_private_endpoint(
    ...     "keyvault-pe", "test-rg", "test-vnet", "default",
    ...     "/subscriptions/.../keyvault-id", "vault"
    ... )
    >>> manager.create_private_dns_zone(
    ...     "privatelink.vaultcore.azure.net", "test-rg", "test-vnet"
    ... )
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


class PrivateEndpointManagerError(Exception):
    """Raised when private endpoint operations fail."""

    pass


class PrivateEndpointManager:
    """Manage Azure Private Endpoints.

    Provides operations for creating private endpoints to Azure services,
    enabling secure private connectivity without public internet exposure.

    All Azure operations delegate to Azure CLI (`az network private-endpoint`).
    """

    def create_private_endpoint(
        self,
        endpoint_name: str,
        resource_group: str,
        vnet_name: str,
        subnet_name: str,
        service_resource_id: str,
        group_id: str,
    ) -> str:
        """Create private endpoint for Azure service.

        Creates a private endpoint that provides private IP address access
        to an Azure service (Storage, Key Vault, SQL, etc.).

        Args:
            endpoint_name: Private endpoint name
            resource_group: Resource group
            vnet_name: Virtual network name
            subnet_name: Subnet for private endpoint
            service_resource_id: Full Azure resource ID of service (Storage, Key Vault, etc.)
            group_id: Sub-resource group ID:
                - "blob" for Storage blobs
                - "file" for Storage files
                - "vault" for Key Vault
                - "sqlServer" for SQL Server

        Returns:
            Private endpoint resource ID

        Raises:
            PrivateEndpointManagerError: If creation fails
        """
        # Step 1: Disable private endpoint network policies on subnet
        logger.info(f"Disabling private endpoint network policies on subnet '{subnet_name}'")

        disable_policies_cmd = [
            "az",
            "network",
            "vnet",
            "subnet",
            "update",
            "--name",
            subnet_name,
            "--vnet-name",
            vnet_name,
            "--resource-group",
            resource_group,
            "--disable-private-endpoint-network-policies",
            "true",
        ]

        result = subprocess.run(disable_policies_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise PrivateEndpointManagerError(
                f"Failed to disable network policies: {result.stderr}"
            )

        # Step 2: Create private endpoint
        logger.info(
            f"Creating private endpoint '{endpoint_name}' for service "
            f"'{service_resource_id}' (group: {group_id})"
        )

        create_cmd = [
            "az",
            "network",
            "private-endpoint",
            "create",
            "--name",
            endpoint_name,
            "--resource-group",
            resource_group,
            "--vnet-name",
            vnet_name,
            "--subnet",
            subnet_name,
            "--private-connection-resource-id",
            service_resource_id,
            "--group-id",
            group_id,
            "--connection-name",
            f"{endpoint_name}-connection",
        ]

        result = subprocess.run(create_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise PrivateEndpointManagerError(f"Failed to create private endpoint: {result.stderr}")

        logger.info(f"Private endpoint '{endpoint_name}' created successfully")

        return self._get_endpoint_id(endpoint_name, resource_group)

    def create_private_dns_zone(self, zone_name: str, resource_group: str, vnet_name: str) -> None:
        """Create Private DNS zone for private endpoint name resolution.

        Private DNS zones provide DNS resolution for private endpoints so that
        services can be accessed by their normal DNS names but resolve to
        private IP addresses.

        Common zone names:
        - privatelink.blob.core.windows.net (Storage Blobs)
        - privatelink.file.core.windows.net (Storage Files)
        - privatelink.vaultcore.azure.net (Key Vault)
        - privatelink.database.windows.net (SQL Database)

        Args:
            zone_name: Private DNS zone name (e.g., privatelink.blob.core.windows.net)
            resource_group: Resource group
            vnet_name: Virtual network to link DNS zone to

        Raises:
            PrivateEndpointManagerError: If DNS zone creation or linking fails
        """
        # Step 1: Create Private DNS zone
        logger.info(f"Creating Private DNS zone '{zone_name}'")

        create_zone_cmd = [
            "az",
            "network",
            "private-dns",
            "zone",
            "create",
            "--name",
            zone_name,
            "--resource-group",
            resource_group,
        ]

        result = subprocess.run(create_zone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise PrivateEndpointManagerError(f"Failed to create DNS zone: {result.stderr}")

        # Step 2: Link DNS zone to VNet
        logger.info(f"Linking DNS zone '{zone_name}' to VNet '{vnet_name}'")

        link_cmd = [
            "az",
            "network",
            "private-dns",
            "link",
            "vnet",
            "create",
            "--name",
            f"{vnet_name}-link",
            "--zone-name",
            zone_name,
            "--resource-group",
            resource_group,
            "--virtual-network",
            vnet_name,
            "--registration-enabled",
            "false",
        ]

        result = subprocess.run(link_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise PrivateEndpointManagerError(f"Failed to link DNS zone to VNet: {result.stderr}")

        logger.info(f"Private DNS zone '{zone_name}' created and linked to {vnet_name}")

    def _get_endpoint_id(self, endpoint_name: str, resource_group: str) -> str:
        """Get private endpoint resource ID.

        Args:
            endpoint_name: Private endpoint name
            resource_group: Resource group

        Returns:
            Full Azure resource ID

        Raises:
            PrivateEndpointManagerError: If endpoint not found
        """
        cmd = [
            "az",
            "network",
            "private-endpoint",
            "show",
            "--name",
            endpoint_name,
            "--resource-group",
            resource_group,
            "--query",
            "id",
            "-o",
            "tsv",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise PrivateEndpointManagerError(f"Failed to get endpoint ID: {result.stderr}")

        return result.stdout.strip()


__all__ = ["PrivateEndpointManager", "PrivateEndpointManagerError"]
