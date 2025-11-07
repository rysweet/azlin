"""CLI Helper Functions.

Helper functions to simplify CLI command implementation,
especially for SSH routing with bastion support.

Fixes Issue #281: Provides easy integration for commands to support bastion routing.
"""

import logging
from pathlib import Path

import click

from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_routing_resolver import SSHRoute, SSHRoutingResolver
from azlin.vm_manager import VMInfo

logger = logging.getLogger(__name__)


class SSHConfigBuilder:
    """Builder for SSH configurations with bastion awareness.

    This class provides static methods for creating SSH configurations
    with automatic bastion routing support.
    """

    @staticmethod
    def build_for_vm(
        vm: VMInfo,
        ssh_key_path: Path,
        bastion_manager=None,
        auto_bastion: bool = True,
        skip_interactive: bool = True,
    ) -> SSHConfig:
        """Build SSH config for a single VM.

        Args:
            vm: VM information
            ssh_key_path: Path to SSH private key
            bastion_manager: Optional bastion manager instance
            auto_bastion: Automatically detect and use bastion (default: True)
            skip_interactive: Skip interactive prompts (default: True)

        Returns:
            SSHConfig instance

        Raises:
            ValueError: If VM requires bastion but no bastion manager provided
            ValueError: If VM has no IP addresses
        """
        # Check if VM is reachable
        if not SSHConfigBuilder.is_reachable(vm):
            if vm.power_state != "VM running":
                raise ValueError(f"VM {vm.name} is not running")
            raise ValueError(f"VM {vm.name} has no IP addresses")

        # Direct SSH if VM has public IP
        if SSHConfigBuilder.has_direct_connectivity(vm):
            # Type assertion: has_direct_connectivity ensures public_ip is not None
            assert vm.public_ip is not None
            return SSHConfig(
                host=vm.public_ip,
                port=22,
                user="azureuser",
                key_path=ssh_key_path,
            )

        # Bastion required for private-only VM
        if not auto_bastion or bastion_manager is None:
            raise ValueError(f"Bastion manager required for VM {vm.name} without public IP")

        # Create bastion tunnel
        tunnel = bastion_manager.create_tunnel(
            vm_name=vm.name,
            resource_group=vm.resource_group,
            private_ip=vm.private_ip,
            skip_interactive=skip_interactive,
        )

        return SSHConfig(
            host="127.0.0.1",
            port=tunnel.local_port,
            user="azureuser",
            key_path=ssh_key_path,
        )

    @staticmethod
    def build_for_vms(
        vms: list[VMInfo],
        ssh_key_path: Path,
        bastion_manager=None,
        auto_bastion: bool = True,
        skip_interactive: bool = True,
    ) -> list[SSHConfig]:
        """Build SSH configs for multiple VMs.

        Args:
            vms: List of VM information
            ssh_key_path: Path to SSH private key
            bastion_manager: Optional bastion manager instance
            auto_bastion: Automatically detect and use bastion (default: True)
            skip_interactive: Skip interactive prompts (default: True)

        Returns:
            List of SSHConfig instances for reachable VMs
        """
        configs = []
        for vm in vms:
            try:
                config = SSHConfigBuilder.build_for_vm(
                    vm=vm,
                    ssh_key_path=ssh_key_path,
                    bastion_manager=bastion_manager,
                    auto_bastion=auto_bastion,
                    skip_interactive=skip_interactive,
                )
                configs.append(config)
            except (ValueError, Exception) as e:
                logger.debug(f"Skipping VM {vm.name}: {e}")
                continue
        return configs

    @staticmethod
    def has_direct_connectivity(vm: VMInfo) -> bool:
        """Check if VM has direct SSH connectivity (public IP).

        Args:
            vm: VM information

        Returns:
            True if VM has a public IP, False otherwise
        """
        return bool(vm.public_ip and vm.public_ip.strip())

    @staticmethod
    def is_reachable(vm: VMInfo) -> bool:
        """Check if VM is reachable via SSH.

        A VM is reachable if:
        - It is running
        - It has at least one IP address (public or private)

        Args:
            vm: VM information

        Returns:
            True if VM is reachable, False otherwise
        """
        if vm.power_state != "VM running":
            return False

        has_ip = bool(
            (vm.public_ip and vm.public_ip.strip()) or (vm.private_ip and vm.private_ip.strip())
        )
        return has_ip

    @staticmethod
    def filter_reachable_vms(vms: list[VMInfo]) -> list[VMInfo]:
        """Filter list to only reachable VMs.

        Args:
            vms: List of VM information

        Returns:
            List of reachable VMs
        """
        return [vm for vm in vms if SSHConfigBuilder.is_reachable(vm)]


def get_ssh_configs_for_vms(
    vms: list[VMInfo],
    ssh_key_path: Path | None = None,
    auto_bastion: bool = True,
    skip_interactive: bool = True,
    show_summary: bool = True,
) -> tuple[list[SSHConfig], list[SSHRoute]]:
    """Get SSH configs for VMs with automatic bastion routing.

    This helper function:
    1. Resolves SSH routing for each VM (direct or bastion)
    2. Creates bastion tunnels where needed
    3. Returns SSH configs and routes

    Args:
        vms: List of VM information
        ssh_key_path: Path to SSH private key (uses default if None)
        auto_bastion: Automatically detect and use bastion (default: True)
        skip_interactive: Skip interactive prompts (default: True for batch)
        show_summary: Print summary of routing decisions (default: True)

    Returns:
        Tuple of (ssh_configs, routes)
        Routes contain bastion manager references for automatic cleanup via atexit

    Example:
        >>> configs, routes = get_ssh_configs_for_vms(running_vms, key_path)
        >>> if not configs:
        ...     click.echo("No reachable VMs found.")
        ...     return
        >>> results = RemoteExecutor.execute_parallel(configs, "w")

    Note:
        VMs without connectivity are skipped gracefully.
        Bastion tunnels are automatically cleaned up via BastionManager's atexit handler.
    """
    if not vms:
        return [], []

    # Ensure ssh_key_path is provided
    resolved_key_path: Path
    if ssh_key_path is None:
        from azlin.modules.ssh_keys import SSHKeyManager

        ssh_keys = SSHKeyManager.ensure_key_exists()
        resolved_key_path = ssh_keys.private_path
    else:
        resolved_key_path = ssh_key_path

    # Resolve routing for all VMs
    routes = SSHRoutingResolver.resolve_routes_batch(
        vms=vms,
        ssh_key_path=resolved_key_path,
        auto_bastion=auto_bastion,
        skip_interactive=skip_interactive,
    )

    # Separate reachable from unreachable
    reachable = [r for r in routes if r.ssh_config is not None]
    unreachable = [r for r in routes if r.ssh_config is None]

    # Show summary if requested
    if show_summary and (reachable or unreachable):
        _print_routing_summary(reachable, unreachable)

    # Extract SSH configs
    ssh_configs = [r.ssh_config for r in reachable if r.ssh_config]

    return ssh_configs, routes


def _print_routing_summary(reachable: list, unreachable: list) -> None:
    """Print summary of routing decisions.

    Args:
        reachable: List of reachable SSH routes
        unreachable: List of unreachable SSH routes
    """
    total = len(reachable) + len(unreachable)

    if not reachable and not unreachable:
        return

    # Count routing methods
    direct_count = sum(1 for r in reachable if r.routing_method == "direct")
    bastion_count = sum(1 for r in reachable if r.routing_method == "bastion")

    # Build summary message
    summary_parts = []

    if reachable:
        methods = []
        if direct_count:
            methods.append(f"{direct_count} direct")
        if bastion_count:
            methods.append(f"{bastion_count} via bastion")

        summary_parts.append(f"✓ {len(reachable)} reachable ({', '.join(methods)})")

    if unreachable:
        summary_parts.append(f"⊘ {len(unreachable)} unreachable")

    click.echo(f"Found {total} VMs: {', '.join(summary_parts)}\n")

    # Show details for unreachable VMs
    if unreachable:
        click.echo("Unreachable VMs:")
        for route in unreachable:
            reason = route.skip_reason or "Unknown reason"
            click.echo(f"  - {route.vm_name}: {reason}")
        click.echo()
