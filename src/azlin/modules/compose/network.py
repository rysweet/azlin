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
from typing import Dict, List, Optional

from azlin.modules.compose.models import DeployedService, VMInfo
from azlin.remote_exec import RemoteExecutor

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

    def discover_service_ips(
        self, deployments: Dict[str, DeployedService]
    ) -> Dict[str, str]:
        """Discover private IPs for all deployed services.

        For replicated services, returns comma-separated IPs for load balancing.

        Args:
            deployments: Dictionary of deployment ID to DeployedService

        Returns:
            Dictionary mapping service names to IP addresses
        """
        service_ips: Dict[str, List[str]] = {}

        for deployment_id, service in deployments.items():
            service_name = getattr(service, "service_name", service_name) if hasattr(service, "service_name") else deployment_id.split("-")[0]

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
        service_ips: Dict[str, str],
        user_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
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
        """
        try:
            remote_executor = RemoteExecutor(
                resource_group=self.resource_group
            )

            # Check if network already exists
            check_cmd = f"docker network inspect {network_name}"
            check_result = remote_executor.execute(
                vm_name=vm.name,
                command=check_cmd,
            )

            if check_result.returncode == 0:
                logger.debug(f"Docker network '{network_name}' already exists on {vm.name}")
                return

            # Create bridge network
            create_cmd = f"docker network create --driver bridge {network_name}"
            create_result = remote_executor.execute(
                vm_name=vm.name,
                command=create_cmd,
            )

            if create_result.returncode != 0:
                # Check if error is "network already exists" (race condition)
                if "already exists" not in create_result.stderr.lower():
                    raise ComposeNetworkError(
                        f"Failed to create network on {vm.name}: {create_result.stderr}"
                    )

            logger.info(f"Configured Docker network '{network_name}' on {vm.name}")

        except Exception as e:
            logger.error(f"Network configuration failed for {vm.name}: {e}")
            # Don't raise - network configuration is best-effort
            # Containers can still communicate via private IPs

    def get_service_endpoints(
        self, deployed_services: List[DeployedService]
    ) -> Dict[str, List[str]]:
        """Get all endpoints for each service.

        Useful for load balancing and service mesh configuration.

        Args:
            deployed_services: List of deployed service instances

        Returns:
            Dictionary mapping service names to list of endpoints (IP:port)
        """
        endpoints: Dict[str, List[str]] = {}

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
    "ComposeNetworkManager",
    "ComposeNetworkError",
]
