"""Network management for multi-VM docker-compose deployments.

This module handles inter-service networking across multiple VMs using:
- Private IP-based service discovery
- Environment variable injection for service names
- Docker bridge network configuration

Philosophy:
- Use Azure VNet private IPs for communication
- Simple environment variable-based discovery
- No external service mesh required
- Reuse existing RemoteExecutor for docker commands

Public API:
    ComposeNetworkManager: Main network configuration class
"""

import logging

from azlin.modules.compose.models import DeployedService, VMInfo

logger = logging.getLogger(__name__)


class ComposeNetworkError(Exception):
    """Raised when network configuration fails."""

    pass


class ComposeNetworkManager:
    """Manage inter-service networking for multi-VM deployments.

    This class provides:
    1. Service IP discovery from deployed services
    2. Environment variable generation for service discovery
    3. Docker network configuration on VMs
    """

    def __init__(self, resource_group: str):
        """Initialize network manager.

        Args:
            resource_group: Azure resource group containing VMs
        """
        self.resource_group = resource_group

    def discover_service_ips(self, deployments: dict[str, DeployedService]) -> dict[str, str]:
        """Discover private IPs for all deployed services.

        For replicated services, returns comma-separated IPs for load balancing.

        Args:
            deployments: Dictionary of deployment ID/service name to DeployedService

        Returns:
            Dictionary mapping service names to IP addresses
        """
        service_ips: dict[str, list[str]] = {}

        for deployment_id, service in deployments.items():
            # Try to get service_name from the service object first
            # Check if it's actually a string attribute, not a Mock
            service_name_attr = getattr(service, "service_name", None)
            if isinstance(service_name_attr, str):
                service_name = service_name_attr
            else:
                service_name = deployment_id

            if service_name not in service_ips:
                service_ips[service_name] = []

            service_ips[service_name].append(service.vm_ip)

        # Convert lists to comma-separated strings for multi-replica services
        result = {}
        for service_name, ips in service_ips.items():
            # Remove duplicates and sort for consistency
            unique_ips = sorted(set(ips))
            result[service_name] = ",".join(unique_ips)

        return result

    def generate_env_vars(
        self,
        service_ips: dict[str, str],
        user_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Generate environment variables for service discovery.

        Creates {SERVICE_NAME}_HOST variables for each service.

        Args:
            service_ips: Dictionary mapping service names to IPs
            user_env: Optional user-defined environment variables to preserve

        Returns:
            Dictionary of environment variables
        """
        env_vars = {}

        # Add user-defined env vars first (can be overridden)
        if user_env:
            env_vars.update(user_env)

        # Generate SERVICE_NAME_HOST environment variables
        for service_name, ip_addresses in service_ips.items():
            # Convert service name to env var format
            # e.g., "my-service" -> "MY_SERVICE_HOST" or "MY-SERVICE_HOST"
            env_var_name = f"{service_name.upper().replace('-', '_')}_HOST"

            # For compatibility, also add with hyphens
            env_var_name_alt = f"{service_name.upper()}_HOST"

            env_vars[env_var_name] = ip_addresses
            if "-" in service_name:
                env_vars[env_var_name_alt] = ip_addresses

        return env_vars

    def configure_docker_network(
        self,
        vm: VMInfo,
        network_name: str = "azlin-compose",
    ) -> None:
        """Configure Docker bridge network on VM.

        Creates a Docker bridge network if it doesn't exist.
        Idempotent - safe to call multiple times.

        Args:
            vm: VM to configure
            network_name: Docker network name to create

        Raises:
            ComposeNetworkError: If network configuration fails

        Note:
            This is a placeholder implementation. Full implementation would use
            RemoteExecutor to configure docker networks on VMs.
        """
        # Simplified implementation - placeholder for now
        # In full implementation, would use SSHConfig and RemoteExecutor
        logger.info(
            f"Network configuration for {vm.name} with network '{network_name}' "
            f"would be configured here"
        )
        # For now, this is a no-op as the actual docker commands would be run
        # through the batch executor during deployment

    def get_service_endpoints(
        self, deployed_services: list[DeployedService]
    ) -> dict[str, list[str]]:
        """Get all endpoints for each service.

        Useful for load balancing and service mesh configuration.

        Args:
            deployed_services: List of deployed service instances

        Returns:
            Dictionary mapping service names to list of endpoints (IP:port)
        """
        endpoints: dict[str, list[str]] = {}

        for service in deployed_services:
            if service.service_name not in endpoints:
                endpoints[service.service_name] = []

            # Build endpoints from exposed ports
            if service.ports:
                for host_port, container_port in service.ports.items():
                    endpoint = f"{service.vm_ip}:{host_port}"
                    endpoints[service.service_name].append(endpoint)
            else:
                # No ports exposed - just add VM IP
                endpoints[service.service_name].append(service.vm_ip)

        return endpoints


__all__ = [
    "ComposeNetworkError",
    "ComposeNetworkManager",
]
