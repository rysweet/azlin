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
    if ssh_key_path is None:
        from azlin.ssh_key_manager import SSHKeyManager

        ssh_keys = SSHKeyManager.ensure_key_exists()
        ssh_key_path = ssh_keys.private_path

    # Resolve routing for all VMs
    routes = SSHRoutingResolver.resolve_routes_batch(
        vms=vms,
        ssh_key_path=ssh_key_path,
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
