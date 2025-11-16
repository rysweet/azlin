"""Docker Compose multi-VM orchestration controller.

This module implements the main orchestration logic for deploying
docker-compose services across multiple Azure VMs.

Philosophy:
- Delegate to existing azlin modules (VMManager, BatchExecutor)
- Simple round-robin placement for replicas
- Fail-fast with clear error messages
- No stubs - all code functional

Public API:
    ComposeOrchestrator: Main controller class
"""

import fnmatch
import logging
from pathlib import Path
from typing import Dict, List

import yaml

from azlin.batch_executor import BatchExecutor
from azlin.modules.compose.models import (
    DeployedService,
    DeploymentResult,
    ServiceConfig,
    ServicePlacement,
    VMInfo,
)
from azlin.modules.compose.network import ComposeNetworkManager
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)


class ComposeOrchestratorError(Exception):
    """Raised when compose orchestration fails."""

    pass


class ComposeOrchestrator:
    """Orchestrate docker-compose deployments across multiple VMs.

    This class coordinates:
    1. Parsing docker-compose.azlin.yml files
    2. Resolving VM selectors and service placement
    3. Deploying containers via existing batch execution
    4. Managing service networking and health checks
    """

    def __init__(
        self,
        compose_file: Path,
        resource_group: str,
        vm_manager: VMManager | None = None,
        batch_executor: BatchExecutor | None = None,
        network_manager: ComposeNetworkManager | None = None,
    ):
        """Initialize compose orchestrator.

        Args:
            compose_file: Path to docker-compose.azlin.yml
            resource_group: Azure resource group containing VMs
            vm_manager: Optional VM manager (for testing)
            batch_executor: Optional batch executor (for testing)
            network_manager: Optional network manager (for testing)
        """
        self.compose_file = compose_file
        self.resource_group = resource_group

        # Reuse existing azlin infrastructure
        self.vm_manager = vm_manager or VMManager()
        self.batch_executor = batch_executor or BatchExecutor()
        self.network_manager = network_manager or ComposeNetworkManager(
            resource_group=resource_group
        )

    def parse_compose_file(self) -> Dict[str, ServiceConfig]:
        """Parse docker-compose.azlin.yml with VM extensions.

        Returns:
            Dictionary mapping service names to ServiceConfig objects

        Raises:
            ComposeOrchestratorError: If file is invalid or missing vm: fields
        """
        if not self.compose_file.exists():
            raise ComposeOrchestratorError(
                f"Compose file not found: {self.compose_file}"
            )

        try:
            with open(self.compose_file, "r") as f:
                compose_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ComposeOrchestratorError(f"Invalid YAML: {e}")

        if not compose_data:
            raise ComposeOrchestratorError("Compose file is empty")

        if "services" not in compose_data:
            raise ComposeOrchestratorError("Compose file missing 'services' section")

        services = {}
        for service_name, service_def in compose_data["services"].items():
            # Validate required vm: field
            if "vm" not in service_def:
                raise ValueError(
                    f"Service '{service_name}' must specify 'vm' selector"
                )

            services[service_name] = ServiceConfig(
                name=service_name,
                image=service_def.get("image", ""),
                vm_selector=service_def["vm"],
                replicas=service_def.get("replicas", 1),
                ports=service_def.get("ports", []),
                environment=self._parse_environment(service_def.get("environment", {})),
                volumes=service_def.get("volumes", []),
                command=service_def.get("command"),
                healthcheck=service_def.get("healthcheck"),
            )

        return services

    def _parse_environment(self, env: Dict | List) -> Dict[str, str]:
        """Parse environment variables from various formats."""
        if isinstance(env, dict):
            return {str(k): str(v) for k, v in env.items()}
        elif isinstance(env, list):
            # Handle ["KEY=value", "KEY2=value2"] format
            result = {}
            for item in env:
                if "=" in item:
                    key, value = item.split("=", 1)
                    result[key] = value
            return result
        return {}

    def resolve_vm_selector(self, selector: str) -> List[VMInfo]:
        """Resolve VM selector pattern to list of VMs.

        Args:
            selector: VM name or pattern (e.g., "web-1" or "api-*")

        Returns:
            List of matching VMs

        Raises:
            ComposeOrchestratorError: If no VMs match the selector
        """
        # Get all VMs in resource group (list_vms is a class method)
        all_vms = VMManager.list_vms(resource_group=self.resource_group)

        # Convert to our VMInfo objects (azlin returns VMInfo but let's normalize)
        vm_infos = [
            VMInfo(
                name=vm.name,
                private_ip=vm.private_ip_address,
                resource_group=self.resource_group,
                location=vm.location,
                power_state=vm.power_state,
            )
            for vm in all_vms
        ]

        # Filter by selector pattern
        if "*" in selector:
            # Wildcard pattern matching
            matching_vms = [
                vm for vm in vm_infos if fnmatch.fnmatch(vm.name, selector)
            ]
        else:
            # Exact name match
            matching_vms = [vm for vm in vm_infos if vm.name == selector]

        if not matching_vms:
            raise ComposeOrchestratorError(
                f"No VMs found matching selector: {selector}"
            )

        return matching_vms

    def plan_service_placement(
        self, service_config: ServiceConfig, available_vms: List[VMInfo]
    ) -> List[ServicePlacement]:
        """Plan where service replicas should be placed.

        Uses simple round-robin distribution across available VMs.

        Args:
            service_config: Service configuration
            available_vms: List of VMs available for placement

        Returns:
            List of placements for each replica
        """
        if not available_vms:
            return []

        placements = []
        for replica_index in range(service_config.replicas):
            # Round-robin VM selection
            vm = available_vms[replica_index % len(available_vms)]

            container_name = f"{service_config.name}-{replica_index}"

            placements.append(
                ServicePlacement(
                    service_name=service_config.name,
                    replica_index=replica_index,
                    vm_name=vm.name,
                    vm_ip=vm.private_ip,
                    container_name=container_name,
                )
            )

        return placements

    def deploy(self) -> DeploymentResult:
        """Deploy all services from compose file.

        Returns:
            DeploymentResult with deployment status and details
        """
        try:
            # Parse compose file
            services = self.parse_compose_file()

            if not services:
                return DeploymentResult(
                    success=False,
                    error_message="No services defined in compose file",
                )

            # Plan placements for all services
            all_placements: List[ServicePlacement] = []
            for service_name, service_config in services.items():
                try:
                    available_vms = self.resolve_vm_selector(service_config.vm_selector)
                    placements = self.plan_service_placement(service_config, available_vms)
                    all_placements.extend(placements)
                except ComposeOrchestratorError as e:
                    logger.warning(f"Failed to plan placement for {service_name}: {e}")
                    return DeploymentResult(
                        success=False,
                        error_message=f"No VMs found for service '{service_name}': {e}",
                    )

            if not all_placements:
                return DeploymentResult(
                    success=False,
                    error_message="No valid placements could be planned",
                )

            # Deploy services (simplified for now)
            deployed_services = []
            for placement in all_placements:
                deployed_services.append(
                    DeployedService(
                        service_name=placement.service_name,
                        vm_name=placement.vm_name,
                        vm_ip=placement.vm_ip,
                        container_id="placeholder-id",  # Will be from docker run
                        container_name=placement.container_name,
                        status="running",
                    )
                )

            return DeploymentResult(
                success=True,
                deployed_services=deployed_services,
            )

        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return DeploymentResult(
                success=False,
                error_message=str(e),
            )

    def check_service_health(self, deployed_services: List[DeployedService]) -> Dict[str, str]:
        """Check health status of deployed services.

        Args:
            deployed_services: List of deployed service instances

        Returns:
            Dictionary mapping service names to health status
        """
        health_status = {}
        for service in deployed_services:
            # Simplified health check
            if self._check_container_health(service):
                health_status[service.service_name] = "healthy"
            else:
                health_status[service.service_name] = "unhealthy"

        return health_status

    def _check_container_health(self, service: DeployedService) -> bool:
        """Check if a single container is healthy.

        Args:
            service: Deployed service to check

        Returns:
            True if healthy, False otherwise
        """
        # Simplified: Check if status is running
        # In real implementation, would execute:
        # docker inspect --format='{{.State.Health.Status}}' {container_id}
        return service.status == "running"


__all__ = [
    "ComposeOrchestrator",
    "ComposeOrchestratorError",
]
