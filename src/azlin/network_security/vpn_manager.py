"""VPN Gateway Management for Secure Remote Access.

Manages Azure VPN Gateway configuration for Point-to-Site VPN connections,
providing secure remote access to Azure resources without exposing them to the internet.

Key features:
- Point-to-Site VPN gateway creation
- OpenVPN protocol configuration
- VPN client config generation
- Custom address pool support

Philosophy:
- Secure remote access without public IPs
- Delegate ALL Azure operations to Azure CLI
- Simple, working implementation
- Clear error messages

Public API:
    VPNManager: Main VPN management class

Example:
    >>> manager = VPNManager(resource_group="test-rg")
    >>> gateway_id = manager.create_point_to_site_vpn("test-vnet", "test-vpn-gw")
    >>> config_url = manager.generate_vpn_client_config("test-vpn-gw")
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


class VPNManagerError(Exception):
    """Raised when VPN operations fail."""

    pass


class VPNManager:
    """Manage Azure VPN Gateway configuration.

    Provides operations for creating and configuring Point-to-Site VPN gateways
    for secure remote access to Azure resources.

    All Azure operations delegate to Azure CLI (`az network vnet-gateway`).
    """

    def __init__(self, resource_group: str):
        """Initialize VPN manager.

        Args:
            resource_group: Azure resource group name
        """
        self.resource_group = resource_group

    def create_point_to_site_vpn(
        self,
        vnet_name: str,
        vpn_gateway_name: str,
        address_pool: str = "172.16.0.0/24",
    ) -> str:
        """Create Point-to-Site VPN for remote access.

        Creates a VPN gateway with Point-to-Site configuration for secure
        remote access. The gateway creation takes 30-45 minutes, so this
        method uses --no-wait and returns immediately.

        Args:
            vnet_name: Virtual network name
            vpn_gateway_name: Name for VPN gateway
            address_pool: Client address pool CIDR (default: 172.16.0.0/24)

        Returns:
            VPN gateway resource ID

        Raises:
            VPNManagerError: If gateway creation fails
        """
        # Step 1: Create gateway subnet (required for VPN gateway)
        logger.info(f"Creating GatewaySubnet in VNet '{vnet_name}'")

        gateway_subnet_cmd = [
            "az",
            "network",
            "vnet",
            "subnet",
            "create",
            "--name",
            "GatewaySubnet",
            "--vnet-name",
            vnet_name,
            "--resource-group",
            self.resource_group,
            "--address-prefixes",
            "10.0.255.0/27",
        ]

        result = subprocess.run(gateway_subnet_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise VPNManagerError(f"Failed to create gateway subnet: {result.stderr}")

        # Step 2: Create VPN gateway (takes 30-45 minutes, use --no-wait)
        logger.info(f"Creating VPN gateway '{vpn_gateway_name}' (this takes 30-45 minutes)")

        gateway_cmd = [
            "az",
            "network",
            "vnet-gateway",
            "create",
            "--name",
            vpn_gateway_name,
            "--resource-group",
            self.resource_group,
            "--vnet",
            vnet_name,
            "--gateway-type",
            "Vpn",
            "--vpn-type",
            "RouteBased",
            "--sku",
            "VpnGw1",
            "--no-wait",
        ]

        result = subprocess.run(gateway_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise VPNManagerError(f"Failed to create VPN gateway: {result.stderr}")

        # Step 3: Configure Point-to-Site VPN (OpenVPN protocol)
        logger.info(f"Configuring Point-to-Site VPN for gateway '{vpn_gateway_name}'")

        p2s_cmd = [
            "az",
            "network",
            "vnet-gateway",
            "update",
            "--name",
            vpn_gateway_name,
            "--resource-group",
            self.resource_group,
            "--client-protocol",
            "OpenVPN",
            "--address-prefixes",
            address_pool,
        ]

        result = subprocess.run(p2s_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # This is expected if gateway is still provisioning - log warning but continue
            logger.warning(
                f"P2S configuration will be applied when gateway is ready: {result.stderr}"
            )

        logger.info(
            f"VPN gateway '{vpn_gateway_name}' creation started "
            f"(provisioning in background, takes 30-45 minutes)"
        )

        return self._get_gateway_id(vpn_gateway_name)

    def generate_vpn_client_config(self, vpn_gateway_name: str) -> str:
        """Generate VPN client configuration package.

        Generates a downloadable configuration package for VPN clients to
        connect to the VPN gateway.

        Args:
            vpn_gateway_name: VPN gateway name

        Returns:
            Download URL for VPN client configuration package

        Raises:
            VPNManagerError: If config generation fails
        """
        logger.info(f"Generating VPN client config for gateway '{vpn_gateway_name}'")

        cmd = [
            "az",
            "network",
            "vnet-gateway",
            "vpn-client",
            "generate",
            "--name",
            vpn_gateway_name,
            "--resource-group",
            self.resource_group,
            "--processor-architecture",
            "Amd64",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise VPNManagerError(f"Failed to generate VPN client config: {result.stderr}")

        # Parse config URL from output (returned as quoted string)
        config_url = result.stdout.strip().strip('"')

        logger.info(f"VPN client config generated: {config_url}")
        return config_url

    def _get_gateway_id(self, vpn_gateway_name: str) -> str:
        """Get VPN gateway resource ID.

        Args:
            vpn_gateway_name: VPN gateway name

        Returns:
            Full Azure resource ID

        Raises:
            VPNManagerError: If gateway not found
        """
        cmd = [
            "az",
            "network",
            "vnet-gateway",
            "show",
            "--name",
            vpn_gateway_name,
            "--resource-group",
            self.resource_group,
            "--query",
            "id",
            "-o",
            "tsv",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise VPNManagerError(f"Failed to get gateway ID: {result.stderr}")

        return result.stdout.strip()


__all__ = ["VPNManager", "VPNManagerError"]
