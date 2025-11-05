"""SSH Routing Resolver Module.

This module resolves how to SSH to VMs - either directly via public IP
or through Azure Bastion tunnels for private IPs.

Fixes Issue #281: Commands like 'azlin w' now work with bastion-only VMs.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click

from azlin.modules.bastion_detector import BastionDetector, BastionInfo
from azlin.modules.bastion_manager import BastionManager, BastionTunnel
from azlin.modules.ssh_connector import SSHConfig
from azlin.vm_manager import VMInfo

logger = logging.getLogger(__name__)


@dataclass
class SSHRoute:
    """Result of SSH routing resolution for a VM.

    Attributes:
        vm_name: Name of the VM
        vm_info: Full VM information
        ssh_config: SSH configuration (None if VM is unreachable)
        routing_method: How the VM is accessed
        bastion_tunnel: Bastion tunnel info if using bastion
        bastion_manager: Manager for tunnel lifecycle
        skip_reason: Why VM was skipped (if unreachable)
    """

    vm_name: str
    vm_info: VMInfo
    ssh_config: SSHConfig | None
    routing_method: Literal["direct", "bastion", "unreachable"]
    bastion_tunnel: BastionTunnel | None = None
    bastion_manager: BastionManager | None = None
    skip_reason: str | None = None


class SSHRoutingResolver:
    """Resolve SSH routing for VMs (direct, bastion, or unreachable).

    This class determines how to access each VM and creates appropriate
    SSH configurations. It handles:
    - Direct SSH for VMs with public IPs
    - Bastion tunnels for VMs with only private IPs
    - Graceful skipping of unreachable VMs
    """

    @classmethod
    def resolve_route(
        cls,
        vm: VMInfo,
        ssh_key_path: Path,
        auto_bastion: bool = True,
        skip_interactive: bool = False,
    ) -> SSHRoute:
        """Resolve SSH routing for a single VM.

        Args:
            vm: VM information
            ssh_key_path: Path to SSH private key
            auto_bastion: Automatically detect and use bastion (default: True)
            skip_interactive: Skip interactive prompts (default: False)

        Returns:
            SSHRoute with routing decision and SSH config

        Example:
            >>> route = SSHRoutingResolver.resolve_route(vm, key_path)
            >>> if route.ssh_config:
            ...     result = RemoteExecutor.execute_command(route.ssh_config, "w")
        """
        # Check if VM has public IP - prefer direct connection
        if vm.public_ip:
            logger.debug(f"VM {vm.name} has public IP {vm.public_ip} - using direct SSH")
            return SSHRoute(
                vm_name=vm.name,
                vm_info=vm,
                ssh_config=SSHConfig(
                    host=vm.public_ip,
                    user="azureuser",
                    key_path=ssh_key_path,
                ),
                routing_method="direct",
            )

        # No public IP - check for bastion if auto-detection enabled
        if auto_bastion and vm.private_ip:
            logger.debug(f"VM {vm.name} has no public IP, checking for bastion...")

            try:
                bastion_info = BastionDetector.detect_bastion_for_vm(
                    vm.name, vm.resource_group, vm.location
                )

                if bastion_info:
                    logger.info(f"Found bastion {bastion_info['name']} for VM {vm.name}")

                    # Ask user for consent if not in batch mode
                    if not skip_interactive and not click.confirm(
                        f"Use Azure Bastion ({bastion_info['name']}) to connect to {vm.name}?"
                    ):
                        return SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=None,
                            routing_method="unreachable",
                            skip_reason="User declined bastion connection",
                        )

                    # Create bastion tunnel
                    try:
                        bastion_manager, tunnel = cls._create_bastion_tunnel(
                            vm, bastion_info, ssh_key_path
                        )

                        return SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=SSHConfig(
                                host="127.0.0.1",
                                user="azureuser",
                                key_path=ssh_key_path,
                                port=tunnel.local_port,
                            ),
                            routing_method="bastion",
                            bastion_tunnel=tunnel,
                            bastion_manager=bastion_manager,
                        )
                    except Exception as e:
                        logger.error(f"Failed to create bastion tunnel for {vm.name}: {e}")
                        return SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=None,
                            routing_method="unreachable",
                            skip_reason=f"Bastion tunnel creation failed: {e}",
                        )
            except Exception as e:
                logger.debug(f"Bastion detection failed for {vm.name}: {e}")

        # No public IP and no bastion available
        return SSHRoute(
            vm_name=vm.name,
            vm_info=vm,
            ssh_config=None,
            routing_method="unreachable",
            skip_reason="No public IP and no bastion available",
        )

    @classmethod
    def resolve_routes_batch(
        cls,
        vms: list[VMInfo],
        ssh_key_path: Path,
        auto_bastion: bool = True,
        skip_interactive: bool = True,  # Default to skip in batch mode
    ) -> list[SSHRoute]:
        """Resolve SSH routing for multiple VMs in batch.

        In batch mode, bastion prompts are aggregated:
        - Single prompt per unique bastion
        - Applies decision to all VMs using that bastion

        Args:
            vms: List of VM information
            ssh_key_path: Path to SSH private key
            auto_bastion: Automatically detect and use bastion (default: True)
            skip_interactive: Skip interactive prompts (default: True for batch)

        Returns:
            List of SSHRoute objects

        Example:
            >>> routes = SSHRoutingResolver.resolve_routes_batch(vms, key_path)
            >>> configs = [r.ssh_config for r in routes if r.ssh_config]
            >>> results = RemoteExecutor.execute_parallel(configs, "w")
        """
        if not vms:
            return []

        routes: list[SSHRoute] = []
        bastion_decisions: dict[str, bool] = {}  # Cache bastion approval decisions

        for vm in vms:
            # VMs with public IPs - direct connection
            if vm.public_ip:
                routes.append(
                    SSHRoute(
                        vm_name=vm.name,
                        vm_info=vm,
                        ssh_config=SSHConfig(
                            host=vm.public_ip,
                            user="azureuser",
                            key_path=ssh_key_path,
                        ),
                        routing_method="direct",
                    )
                )
                continue

            # No public IP - check for bastion
            if not auto_bastion or not vm.private_ip:
                routes.append(
                    SSHRoute(
                        vm_name=vm.name,
                        vm_info=vm,
                        ssh_config=None,
                        routing_method="unreachable",
                        skip_reason="No public IP and bastion disabled or no private IP",
                    )
                )
                continue

            # Detect bastion
            try:
                bastion_info = BastionDetector.detect_bastion_for_vm(
                    vm.name, vm.resource_group, vm.location
                )

                if not bastion_info:
                    routes.append(
                        SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=None,
                            routing_method="unreachable",
                            skip_reason="No public IP and no bastion found",
                        )
                    )
                    continue

                bastion_key = f"{bastion_info['resource_group']}/{bastion_info['name']}"

                # Check if we've already asked about this bastion
                if bastion_key not in bastion_decisions and not skip_interactive:
                    answer = click.confirm(
                        f"Use Azure Bastion ({bastion_info['name']}) for VMs without public IPs?"
                    )
                    bastion_decisions[bastion_key] = answer
                elif bastion_key not in bastion_decisions:
                    # In batch/non-interactive mode, auto-approve
                    bastion_decisions[bastion_key] = True

                if not bastion_decisions[bastion_key]:
                    routes.append(
                        SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=None,
                            routing_method="unreachable",
                            skip_reason="User declined bastion connection",
                        )
                    )
                    continue

                # Create tunnel
                try:
                    bastion_manager, tunnel = cls._create_bastion_tunnel(
                        vm, bastion_info, ssh_key_path
                    )

                    routes.append(
                        SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=SSHConfig(
                                host="127.0.0.1",
                                user="azureuser",
                                key_path=ssh_key_path,
                                port=tunnel.local_port,
                            ),
                            routing_method="bastion",
                            bastion_tunnel=tunnel,
                            bastion_manager=bastion_manager,
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to create bastion tunnel for {vm.name}: {e}")
                    routes.append(
                        SSHRoute(
                            vm_name=vm.name,
                            vm_info=vm,
                            ssh_config=None,
                            routing_method="unreachable",
                            skip_reason=f"Bastion tunnel creation failed: {e}",
                        )
                    )

            except Exception as e:
                logger.debug(f"Bastion detection failed for {vm.name}: {e}")
                routes.append(
                    SSHRoute(
                        vm_name=vm.name,
                        vm_info=vm,
                        ssh_config=None,
                        routing_method="unreachable",
                        skip_reason=f"Bastion detection error: {e}",
                    )
                )

        return routes

    @classmethod
    def _create_bastion_tunnel(
        cls, vm: VMInfo, bastion_info: BastionInfo, ssh_key_path: Path
    ) -> tuple[BastionManager, BastionTunnel]:
        """Create a bastion tunnel for a VM.

        Args:
            vm: VM information
            bastion_info: Bastion information from detector
            ssh_key_path: Path to SSH private key

        Returns:
            Tuple of (BastionManager, BastionTunnel)

        Raises:
            Exception: If tunnel creation fails
        """
        from azlin.vm_manager import VMManager

        # Get VM resource ID
        vm_resource_id = VMManager.get_vm_resource_id(vm.name, vm.resource_group)

        if not vm_resource_id:
            raise ValueError(
                f"Cannot get VM resource ID for {vm.name}. Ensure Azure CLI is authenticated."
            )

        bastion_manager = BastionManager()

        # Find available port
        local_port = bastion_manager.get_available_port()

        # Create tunnel
        tunnel = bastion_manager.create_tunnel(
            bastion_name=bastion_info["name"],
            resource_group=bastion_info["resource_group"],
            target_vm_id=vm_resource_id,
            local_port=local_port,
            remote_port=22,
        )

        logger.info(
            f"Created bastion tunnel for {vm.name}: 127.0.0.1:{tunnel.local_port} -> {vm.name}:22"
        )

        return bastion_manager, tunnel
