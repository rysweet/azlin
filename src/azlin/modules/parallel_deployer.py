"""Parallel multi-region VM deployment.

Philosophy:
- Async-first: Python asyncio for true parallelism
- Fail-fast: Each region reports success/failure independently
- Standard library only (asyncio, subprocess)
- Self-contained and regeneratable

Public API (the "studs"):
    ParallelDeployer: Main deployment orchestrator
    DeploymentResult: Result for single region
    DeploymentStatus: Status enum
    MultiRegionResult: Aggregated results across regions
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azlin.config_manager import ConfigManager
    from azlin.models import VMConfig


class DeploymentStatus(Enum):
    """Status of a single region deployment."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class DeploymentResult:
    """Result of deploying to a single region."""

    region: str
    status: DeploymentStatus
    vm_name: str
    public_ip: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class MultiRegionResult:
    """Aggregated results from multi-region deployment."""

    total_regions: int
    successful: list[DeploymentResult]
    failed: list[DeploymentResult]
    total_duration_seconds: float

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0-1.0)."""
        if self.total_regions == 0:
            return 0.0
        return len(self.successful) / self.total_regions


class ParallelDeployer:
    """Deploy VMs to multiple regions concurrently.

    Uses asyncio to provision VMs in parallel, respecting Azure
    subscription limits (typically 20 concurrent operations).

    Example:
        deployer = ParallelDeployer(config_manager=config_mgr)
        result = await deployer.deploy_to_regions(
            regions=["eastus", "westus2", "westeurope"],
            vm_config=vm_config
        )
        print(f"Success rate: {result.success_rate:.1%}")
    """

    def __init__(self, config_manager: "ConfigManager", max_concurrent: int = 10):
        """Initialize parallel deployer.

        Args:
            config_manager: Config manager for storing region metadata
            max_concurrent: Max concurrent deployments (default: 10)

        Raises:
            ValueError: If max_concurrent is not positive
        """
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive")

        self.config_manager = config_manager
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def deploy_to_regions(
        self, regions: list[str], vm_config: "VMConfig"
    ) -> MultiRegionResult:
        """Deploy VMs to multiple regions in parallel.

        Args:
            regions: List of Azure regions (e.g., ["eastus", "westus2"])
            vm_config: VM configuration (size, image, keys, etc.)

        Returns:
            MultiRegionResult with success/failure per region

        Raises:
            ValueError: If regions list is empty or invalid
            TypeError: If regions or vm_config is None
            Exception: If ALL regions fail (partial failure OK)
        """
        # Input validation
        if regions is None:
            raise TypeError("regions cannot be None")
        if vm_config is None:
            raise TypeError("vm_config cannot be None")
        if len(regions) == 0:
            raise ValueError("regions list cannot be empty")

        # Validate region names (basic check)
        valid_regions = [
            "eastus",
            "eastus2",
            "westus",
            "westus2",
            "westus3",
            "centralus",
            "northcentralus",
            "southcentralus",
            "northeurope",
            "westeurope",
            "uksouth",
            "ukwest",
            "southeastasia",
            "eastasia",
            "australiaeast",
            "australiasoutheast",
            "japaneast",
            "japanwest",
            "koreacentral",
            "koreasouth",
            "canadacentral",
            "canadaeast",
            "brazilsouth",
            "southafricanorth",
            "southafricawest",
            "switzerlandnorth",
            "germanywestcentral",
            "norwayeast",
            "westcentralus",
            "francecentral",
            "uaenorth",
            "indiacentral",
        ]

        invalid_regions = [r for r in regions if r not in valid_regions]
        if invalid_regions:
            raise ValueError(f"Invalid region names: {invalid_regions}")

        # Track start time
        start_time = time.time()

        # Deploy to all regions in parallel
        tasks = []
        for region in regions:
            task = self._deploy_single_region(region, vm_config)
            tasks.append(task)

        # Wait for all deployments to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Separate successful and failed deployments
        successful = []
        failed = []

        for result in results:
            if isinstance(result, Exception):
                # Handle unexpected exceptions
                failed.append(
                    DeploymentResult(
                        region="unknown",
                        status=DeploymentStatus.FAILED,
                        vm_name="unknown",
                        error=f"Unexpected error: {result!s}",
                        duration_seconds=0.0,
                    )
                )
            elif result.status == DeploymentStatus.SUCCESS:
                successful.append(result)
            else:
                failed.append(result)

        # Calculate total duration
        total_duration = time.time() - start_time

        # Create aggregate result
        multi_result = MultiRegionResult(
            total_regions=len(regions),
            successful=successful,
            failed=failed,
            total_duration_seconds=total_duration,
        )

        # Raise error if ALL regions failed
        if len(failed) == len(regions):
            raise Exception(f"All regions failed deployment: {[f.error for f in failed]}")

        return multi_result

    async def _deploy_single_region(self, region: str, vm_config: "VMConfig") -> DeploymentResult:
        """Deploy VM to a single region (internal method).

        Delegates to existing vm_provisioning.py module via subprocess.
        Captures output and errors for detailed reporting.

        Args:
            region: Azure region name
            vm_config: VM configuration

        Returns:
            DeploymentResult with status and details
        """
        start_time = time.time()

        # Acquire semaphore to limit concurrent deployments
        async with self._semaphore:
            try:
                # Generate unique VM name
                timestamp = int(time.time())
                vm_name = f"azlin-{region}-{timestamp}"

                # Get resource group from vm_config or use default
                resource_group = getattr(vm_config, "resource_group", None)
                if not resource_group:
                    # Try to get from config_manager
                    resource_group = self.config_manager.get_resource_group()

                if not resource_group:
                    raise ValueError(f"No resource group specified for region {region}")

                # Build az vm create command
                cmd = [
                    "az",
                    "vm",
                    "create",
                    "--resource-group",
                    resource_group,
                    "--name",
                    vm_name,
                    "--location",
                    region,
                    "--image",
                    getattr(vm_config, "image", "Ubuntu2204"),
                    "--size",
                    getattr(vm_config, "size", "Standard_D2s_v3"),
                    "--admin-username",
                    getattr(vm_config, "admin_username", "azureuser"),
                    "--generate-ssh-keys",
                    "--output",
                    "json",
                ]

                # Add SSH public key if provided
                if hasattr(vm_config, "ssh_public_key") and vm_config.ssh_public_key:
                    cmd.extend(["--ssh-key-values", vm_config.ssh_public_key])

                # Add tags for tracking
                cmd.extend(
                    [
                        "--tags",
                        f"azlin:region={region}",
                        f"azlin:created={datetime.now().isoformat()}",
                    ]
                )

                # Execute az vm create asynchronously
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                duration = time.time() - start_time

                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    return DeploymentResult(
                        region=region,
                        status=DeploymentStatus.FAILED,
                        vm_name=vm_name,
                        error=f"az vm create failed: {error_msg}",
                        duration_seconds=duration,
                    )

                # Parse JSON output to get public IP
                vm_info = json.loads(stdout.decode())
                public_ip = vm_info.get("publicIpAddress", None)

                return DeploymentResult(
                    region=region,
                    status=DeploymentStatus.SUCCESS,
                    vm_name=vm_name,
                    public_ip=public_ip,
                    duration_seconds=duration,
                )

            except TimeoutError:
                duration = time.time() - start_time
                return DeploymentResult(
                    region=region,
                    status=DeploymentStatus.FAILED,
                    vm_name=f"vm-{region}-failed",
                    error="Deployment timed out",
                    duration_seconds=duration,
                )
            except Exception as e:
                duration = time.time() - start_time
                return DeploymentResult(
                    region=region,
                    status=DeploymentStatus.FAILED,
                    vm_name=f"vm-{region}-failed",
                    error=str(e),
                    duration_seconds=duration,
                )


__all__ = ["DeploymentResult", "DeploymentStatus", "MultiRegionResult", "ParallelDeployer"]
