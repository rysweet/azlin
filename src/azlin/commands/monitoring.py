"""Monitoring and operations commands for azlin.

This module contains monitoring-related CLI commands extracted from cli.py.
Part of Issue #423 - cli.py decomposition.

Commands:
    - status: Show VM status information
    - list_command: List VMs in resource group (most complex command)
    - session_command: Set or view session name for a VM
    - w: Run 'w' command on all VMs
    - top: Live distributed metrics dashboard
    - ps: Process listing on all VMs
    - os_update: Update OS packages on a VM
    - cost: Show cost estimates for VMs
"""

import logging
import os
import random
import sys
import time
from datetime import datetime
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.context_selector import ContextSelector, ContextSelectorError
from azlin.cost_tracker import CostTracker, CostTrackerError
from azlin.distributed_top import DistributedTopError, DistributedTopExecutor
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.multi_context_display import MultiContextDisplay
from azlin.multi_context_list import MultiContextQueryError
from azlin.multi_context_list_async import query_all_contexts_parallel
from azlin.network_security.bastion_connection_pool import (
    BastionConnectionPool,
    PooledTunnel,
    SecurityError,
)
from azlin.quota_manager import QuotaInfo, QuotaManager
from azlin.remote_exec import (
    OSUpdateExecutor,
    PSCommandExecutor,
    RemoteExecError,
    TmuxSession,
    TmuxSessionExecutor,
    WCommandExecutor,
)
from azlin.tag_manager import TagManager
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

if TYPE_CHECKING:
    from azlin.ssh.latency import LatencyResult

logger = logging.getLogger(__name__)

__all__ = [
    "cost",
    "list_command",
    "os_update",
    "ps",
    "session_command",
    "status",
    "top",
    "w",
]


# ============================================================================
# TMUX SESSION COLLECTION CONSTANTS
# ============================================================================
# These values are based on empirical observation and conservative estimates:
# - Direct SSH: 95th percentile ~3s, buffer to 5s for network variability
# - Bastion: Routing through Azure Bastion adds ~5-7s latency, plus VM SSH startup ~3-5s, buffer to 15s
DIRECT_SSH_TMUX_TIMEOUT = 5  # Seconds - Direct SSH connections (public IP)
BASTION_TUNNEL_TMUX_TIMEOUT = 15  # Seconds - Bastion tunnels (routing latency + VM SSH startup)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _get_config_int(env_var: str, default: int) -> int:
    """Get integer config from environment with safe fallback.

    Args:
        env_var: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Integer value from environment or default
    """
    try:
        return int(os.getenv(env_var, default))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {env_var}, using default: {default}")
        return default


def _get_config_float(env_var: str, default: float) -> float:
    """Get float config from environment with safe fallback.

    Args:
        env_var: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Float value from environment or default
    """
    try:
        return float(os.getenv(env_var, default))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {env_var}, using default: {default}")
        return default


def _create_tunnel_with_retry(
    pool: BastionConnectionPool,
    vm: "VMInfo",
    bastion_info: dict[str, str],
    vm_resource_id: str,
    max_attempts: int = 3,
) -> PooledTunnel:
    """Create Bastion tunnel with retry logic using connection pool.

    Combines:
    - Connection pool for reuse (BastionConnectionPool)
    - Retry with exponential backoff for resilience
    - Clear error messages for debugging

    Args:
        pool: BastionConnectionPool instance
        vm: VM information
        bastion_info: Bastion host details (name, resource_group)
        vm_resource_id: Full Azure VM resource ID
        max_attempts: Maximum retry attempts (default: 3)

    Returns:
        PooledTunnel ready for use

    Raises:
        BastionManagerError: If tunnel creation fails after all retries
    """
    last_error: Exception | None = None
    initial_delay = 1.0  # Start with 1 second delay

    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(
                f"Attempting tunnel creation for VM {vm.name} (attempt {attempt}/{max_attempts})"
            )
            pooled_tunnel = pool.get_or_create_tunnel(
                bastion_name=bastion_info["name"],
                resource_group=bastion_info["resource_group"],
                target_vm_id=vm_resource_id,
                remote_port=22,
            )
            if attempt > 1:
                logger.info(
                    f"Tunnel created successfully for VM {vm.name} (attempt {attempt}/{max_attempts})"
                )
            return pooled_tunnel

        except SecurityError:
            # Security violations should fail-fast, no retry
            logger.error(
                f"Security violation during tunnel creation for VM {vm.name} - "
                f"tunnel not bound to localhost"
            )
            raise

        except (BastionManagerError, TimeoutError, ConnectionError) as e:
            last_error = e
            if attempt < max_attempts:
                # Exponential backoff with jitter
                delay = initial_delay * (2 ** (attempt - 1))
                # Add small jitter (up to 20%) - S311 safe, not used for crypto
                delay *= 1 + random.uniform(-0.2, 0.2)  # noqa: S311
                logger.warning(
                    f"Failed to create tunnel for VM {vm.name} (attempt {attempt}/{max_attempts}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"Failed to create Bastion tunnel for VM {vm.name} "
                    f"after {max_attempts} attempts: {e}"
                )

    # All retries exhausted
    raise BastionManagerError(
        f"Failed to create Bastion tunnel for VM {vm.name} after {max_attempts} attempts"
    ) from last_error


def _collect_tmux_sessions(vms: list[VMInfo]) -> dict[str, list[TmuxSession]]:
    """Collect tmux sessions from running VMs.

    Supports both direct SSH (VMs with public IPs) and Bastion tunneling
    (VMs with only private IPs).

    Args:
        vms: List of VMInfo objects

    Returns:
        Dictionary mapping VM name to list of tmux sessions
    """
    from azlin.azure_auth import AzureAuthenticator

    tmux_by_vm: dict[str, list[TmuxSession]] = {}

    # Ensure SSH key is available for connecting to VMs
    try:
        ssh_key_pair = SSHKeyManager.ensure_key_exists()
        ssh_key_path = ssh_key_pair.private_path
    except SSHKeyError as e:
        logger.warning(
            f"Cannot collect tmux sessions: SSH key validation failed: {e}\n"
            "Tmux sessions will not be displayed.\n"
            "To fix this, ensure your SSH key is available or run 'azlin' commands "
            "to set up SSH access."
        )
        return tmux_by_vm

    # Classify VMs into direct SSH (public IP) and Bastion (private IP only)
    direct_ssh_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]
    bastion_vms = [vm for vm in vms if vm.is_running() and vm.private_ip and not vm.public_ip]

    # Handle direct SSH VMs (existing code path)
    try:
        ssh_configs = []
        vm_name_map = {}  # Map IP to VM name for result matching

        for vm in direct_ssh_vms:
            # Type assertion: vm.public_ip is guaranteed non-None by direct_ssh_vms filter
            assert vm.public_ip is not None
            ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)
            ssh_configs.append(ssh_config)
            vm_name_map[vm.public_ip] = vm.name

        # Query tmux sessions in parallel
        if ssh_configs:
            tmux_sessions = TmuxSessionExecutor.get_sessions_parallel(
                ssh_configs, timeout=DIRECT_SSH_TMUX_TIMEOUT, max_workers=10
            )

            # Map sessions to VM names
            for session in tmux_sessions:
                # Map from IP back to VM name
                if session.vm_name in vm_name_map:
                    vm_name = vm_name_map[session.vm_name]
                    if vm_name not in tmux_by_vm:
                        tmux_by_vm[vm_name] = []
                    tmux_by_vm[vm_name].append(session)

    except Exception as e:
        logger.warning(f"Failed to fetch tmux sessions from direct SSH VMs: {e}")

    # Handle Bastion VMs (with retry logic and rate limiting - Issue #588)
    if bastion_vms:
        try:
            # Get subscription ID for resource ID generation
            auth = AzureAuthenticator()
            subscription_id = auth.get_subscription_id()

            # Load configuration from environment
            max_tunnels = _get_config_int("AZLIN_BASTION_MAX_TUNNELS", 10)
            idle_timeout = _get_config_int("AZLIN_BASTION_IDLE_TIMEOUT", 300)
            rate_limit = _get_config_float("AZLIN_BASTION_RATE_LIMIT", 0.5)
            retry_attempts = _get_config_int("AZLIN_BASTION_RETRY_ATTEMPTS", 3)

            # Use context manager to ensure tunnel cleanup
            with BastionManager() as bastion_manager:
                # Initialize connection pool for tunnel reuse
                pool = BastionConnectionPool(
                    bastion_manager,
                    max_tunnels=max_tunnels,
                    idle_timeout=idle_timeout,
                )

                try:
                    for idx, vm in enumerate(bastion_vms):
                        try:
                            # Rate limiting: Add delay between tunnel creations
                            if idx > 0 and rate_limit > 0:
                                logger.debug(
                                    f"Rate limiting: waiting {rate_limit}s before next tunnel"
                                )
                                time.sleep(rate_limit)

                            # Detect Bastion host for this VM
                            bastion_info = BastionDetector.detect_bastion_for_vm(
                                vm.name, vm.resource_group, vm.location
                            )

                            if not bastion_info:
                                logger.warning(
                                    f"No Bastion host found for VM {vm.name} in {vm.resource_group}"
                                )
                                continue

                            # Get VM resource ID
                            vm_resource_id = vm.get_resource_id(subscription_id)

                            # Create tunnel with retry logic (Issue #588)
                            pooled_tunnel = _create_tunnel_with_retry(
                                pool=pool,
                                vm=vm,
                                bastion_info={
                                    "name": bastion_info["name"],
                                    "resource_group": bastion_info["resource_group"],
                                },
                                vm_resource_id=vm_resource_id,
                                max_attempts=retry_attempts,
                            )

                            # Query tmux sessions through tunnel
                            ssh_config = SSHConfig(
                                host="127.0.0.1",
                                port=pooled_tunnel.tunnel.local_port,
                                user="azureuser",
                                key_path=ssh_key_path,
                            )

                            # Get sessions for this VM (use longer timeout for Bastion tunnels)
                            tmux_sessions = TmuxSessionExecutor.get_sessions_parallel(
                                [ssh_config], timeout=BASTION_TUNNEL_TMUX_TIMEOUT, max_workers=1
                            )

                            # Add sessions to result
                            for session in tmux_sessions:
                                if vm.name not in tmux_by_vm:
                                    tmux_by_vm[vm.name] = []
                                # Update session VM name to actual VM name (not localhost)
                                session.vm_name = vm.name
                                tmux_by_vm[vm.name].append(session)

                        except BastionManagerError as e:
                            logger.warning(f"Failed to create Bastion tunnel for VM {vm.name}: {e}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch tmux sessions from Bastion VM {vm.name}: {e}"
                            )
                finally:
                    # Ensure pool tunnels are cleaned up (Issue #588 review feedback)
                    pool.close_all()

        except Exception as e:
            logger.warning(f"Failed to initialize Bastion support: {e}")

    return tmux_by_vm


def _handle_multi_context_list(
    all_contexts: bool,
    contexts_pattern: str | None,
    resource_group: str | None,
    config: str | None,
    show_all: bool,
    tag: str | None,
    show_quota: bool,
    show_tmux: bool,
    wide_mode: bool = False,
    compact_mode: bool = False,
    no_cache: bool = False,
) -> None:
    """Handle multi-context VM listing.

    This function orchestrates VM listing across multiple Azure contexts using
    the context_selector, multi_context_list, and multi_context_display modules.

    Args:
        all_contexts: Query all configured contexts
        contexts_pattern: Glob pattern for context selection
        resource_group: Resource group to query (required for multi-context)
        config: Config file path
        show_all: Include stopped VMs
        tag: Tag filter (format: key or key=value)
        show_quota: Show quota information (not supported in multi-context)
        show_tmux: Show tmux sessions (not supported in multi-context)
        wide_mode: Prevent VM name truncation in table output
        compact_mode: Use compact column widths
        no_cache: Bypass cache and fetch fresh data

    Raises:
        SystemExit: On validation or execution errors
    """
    # Validate: Cannot use both flags
    if all_contexts and contexts_pattern:
        click.echo(
            "Error: Cannot use both --all-contexts and --contexts. Choose one.",
            err=True,
        )
        sys.exit(1)

    # Validate: Resource group is required for multi-context queries
    # Unlike single-context mode, we can't query "all RGs" across multiple subscriptions
    rg = ConfigManager.get_resource_group(resource_group, config)
    if not rg:
        click.echo(
            "Error: Multi-context queries require a resource group.\n"
            "Use --resource-group or set default in ~/.azlin/config.toml",
            err=True,
        )
        sys.exit(1)

    # Feature limitation warnings
    if show_quota:
        click.echo(
            "Warning: --show-quota is not yet supported for multi-context queries. "
            "Quota information will be omitted.\n",
            err=True,
        )
        show_quota = False  # Disable for now

    if show_tmux:
        click.echo(
            "Warning: --show-tmux is not yet supported for multi-context queries. "
            "Tmux session information will be omitted.\n",
            err=True,
        )
        show_tmux = False  # Disable for now

    # Step 1: Select contexts based on pattern or all flag
    try:
        selector = ContextSelector(config_path=config)

        if all_contexts:
            click.echo("Selecting all configured contexts...\n")
            contexts = selector.select_contexts(all_contexts=True)
        else:
            click.echo(f"Selecting contexts matching pattern: {contexts_pattern}\n")
            contexts = selector.select_contexts(pattern=contexts_pattern)

        click.echo(f"Selected {len(contexts)} context(s): {', '.join(c.name for c in contexts)}\n")

    except ContextSelectorError as e:
        click.echo(f"Error selecting contexts: {e}", err=True)
        sys.exit(1)

    # Step 2: Query VMs across all selected contexts in parallel
    try:
        click.echo(f"Querying VMs in resource group '{rg}' across {len(contexts)} contexts...\n")

        # Check if cache exists before query

        from azlin.cache.vm_list_cache import VMListCache

        cache = VMListCache()
        cache_file = cache.cache_path
        cache_exists_before = cache_file.exists()

        # Note: Cache debug info available via logger.debug() if needed

        result = query_all_contexts_parallel(
            contexts=contexts,
            resource_group=rg,
            include_stopped=show_all,
            filter_prefix="azlin",  # Always filter to azlin VMs like single-context mode
            cache=cache,  # Pass explicit cache instance
        )

    except MultiContextQueryError as e:
        click.echo(f"Error querying contexts: {e}", err=True)
        sys.exit(1)

    # Step 3: Apply tag filter if specified (post-query filtering)
    if tag:
        try:
            # Filter VMs in each successful context result
            for ctx_result in result.context_results:
                if ctx_result.success and ctx_result.vms:
                    ctx_result.vms = TagManager.filter_vms_by_tag(ctx_result.vms, tag)

            click.echo(f"Applied tag filter: {tag}\n")
        except Exception as e:
            click.echo(f"Error filtering by tag: {e}", err=True)
            sys.exit(1)

    # Step 4: Display results using Rich tables
    display = MultiContextDisplay()
    display.display_results(
        result, show_errors=True, show_summary=True, wide_mode=wide_mode, compact_mode=compact_mode
    )

    # Trigger background cache refresh to keep cache warm (non-blocking)
    try:
        from azlin.cache.background_refresh import trigger_background_refresh

        trigger_background_refresh(contexts=contexts)
    except Exception:
        pass  # Never fail user operation due to background refresh

    # Step 5: Check if any contexts failed and set appropriate exit code
    if result.failed_contexts > 0:
        click.echo(
            f"\nWarning: {result.failed_contexts} context(s) failed to query. "
            "See error details above.",
            err=True,
        )
        # Don't exit with error - partial success is still useful
        # User can see which contexts failed and why


def _get_ssh_config_for_vm(
    vm_identifier: str, resource_group: str | None, config: str | None
) -> SSHConfig:
    """Helper to get SSH config for VM identifier.

    Args:
        vm_identifier: VM name, session name, or IP address
        resource_group: Resource group (required for VM name)
        config: Config file path

    Returns:
        SSHConfig object

    Raises:
        SystemExit on error
    """
    # Get SSH key
    ssh_key_pair = SSHKeyManager.ensure_key_exists()

    # Check if VM identifier is IP address
    if VMConnector.is_valid_ip(vm_identifier):
        # Direct IP connection
        return SSHConfig(host=vm_identifier, user="azureuser", key_path=ssh_key_pair.private_path)

    # Resolve session name to VM name if applicable
    resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
    if resolved_vm_name:
        vm_identifier = resolved_vm_name

    # VM name - need resource group
    rg = ConfigManager.get_resource_group(resource_group, config)
    if not rg:
        click.echo(
            "Error: Resource group required for VM name.\n"
            "Use --resource-group or set default in ~/.azlin/config.toml",
            err=True,
        )
        sys.exit(1)

    # Get VM
    vm = VMManager.get_vm(vm_identifier, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_identifier}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not vm.is_running():
        click.echo(f"Error: VM '{vm_identifier}' is not running.", err=True)
        sys.exit(1)

    if not vm.public_ip:
        click.echo(f"Error: VM '{vm_identifier}' has no public IP.", err=True)
        sys.exit(1)

    return SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path)


# ============================================================================
# STATUS COMMAND (Original from Issue #423)
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", help="Show status for specific VM only", type=str)
def status(resource_group: str | None, config: str | None, vm: str | None):
    """Show status of VMs in resource group.

    Displays detailed status information including power state and IP addresses.

    \b
    Examples:
        azlin status
        azlin status --rg my-resource-group
        azlin status --vm my-vm
    """
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List VMs - use TagManager to filter by managed-by=azlin tag
        vms, was_cached = TagManager.list_managed_vms(resource_group=rg)

        # Filter out stopped VMs by default (consistent with list command behavior)
        # Note: list command doesn't filter by default but shows all,
        # keeping include_stopped=True behavior for status

        if vm:
            # Filter to specific VM
            vms = [v for v in vms if v.name == vm]
            if not vms:
                click.echo(f"Error: VM '{vm}' not found in resource group '{rg}'.", err=True)
                sys.exit(1)

        vms = VMManager.sort_by_created_time(vms)

        if not vms:
            click.echo("No VMs found.")
            return

        # Display status table
        click.echo(f"\nVM Status in resource group: {rg}")
        click.echo("=" * 100)
        click.echo(f"{'NAME':<35} {'POWER STATE':<18} {'IP':<16} {'REGION':<15} {'SIZE':<15}")
        click.echo("=" * 100)

        for v in vms:
            power_state = v.power_state if v.power_state else "Unknown"
            # Display IP with type indicator (Issue #492)
            ip = (
                f"{v.public_ip} (Public)"
                if v.public_ip
                else f"{v.private_ip} (Private)"
                if v.private_ip
                else "N/A"
            )
            size = v.vm_size or "N/A"
            location = v.location or "N/A"
            click.echo(f"{v.name:<35} {power_state:<18} {ip:<16} {location:<15} {size:<15}")

        click.echo("=" * 100)
        click.echo(f"\nTotal: {len(vms)} VMs")

        # Summary stats
        running = sum(1 for v in vms if v.is_running())
        stopped = len(vms) - running
        click.echo(f"Running: {running}, Stopped/Deallocated: {stopped}\n")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# LIST COMMAND (Most Complex - Issue #423)
# ============================================================================


@click.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group to list VMs from", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "show_all", help="Show all VMs (including stopped)", is_flag=True)
@click.option("--tag", help="Filter VMs by tag (format: key or key=value)", type=str)
@click.option("--show-quota/--no-quota", default=True, help="Show Azure vCPU quota information")
@click.option("--show-tmux/--no-tmux", default=True, help="Show active tmux sessions")
@click.option(
    "--show-all-vms",
    "-a",
    "show_all_vms",
    help="List all VMs across all resource groups (expensive operation)",
    is_flag=True,
)
@click.option(
    "--all-contexts",
    "all_contexts",
    help="List VMs across all configured contexts (requires context configuration)",
    is_flag=True,
)
@click.option(
    "--contexts",
    "contexts_pattern",
    help="List VMs from contexts matching glob pattern (e.g., 'prod*', 'dev-*')",
    type=str,
)
@click.option(
    "--wide",
    "-w",
    "wide_mode",
    help="Prevent VM name truncation in table output",
    is_flag=True,
)
@click.option(
    "--compact",
    "-c",
    "compact_mode",
    help="Use compact column widths for table output",
    is_flag=True,
)
@click.option(
    "--with-latency",
    is_flag=True,
    default=False,
    help="Measure SSH latency for running VMs (adds ~5s per VM, parallel)",
)
@click.option(
    "--no-cache",
    "no_cache",
    is_flag=True,
    default=False,
    help="Bypass cache and fetch fresh data from Azure (used by background refresh)",
)
def list_command(
    resource_group: str | None,
    config: str | None,
    show_all: bool,
    tag: str | None,
    show_quota: bool,
    show_tmux: bool,
    show_all_vms: bool,
    all_contexts: bool,
    contexts_pattern: str | None,
    wide_mode: bool = False,
    compact_mode: bool = False,
    with_latency: bool = False,
    no_cache: bool = False,
):
    """List VMs in a resource group.

    By default, lists azlin-managed VMs in the configured resource group.
    Use --show-all-vms (-a) to scan all VMs across all resource groups (expensive).

    Shows VM name, status, IP address, region, size, vCPUs, memory (GB), and optionally quota/tmux/latency info.

    \b
    Examples:
        azlin list                    # VMs in default RG with quota & tmux
        azlin list --rg my-rg         # VMs in specific RG
        azlin list --all              # Include stopped VMs
        azlin list --tag env=dev      # Filter by tag
        azlin list --with-latency     # Include SSH latency measurements
        azlin list --show-all-vms     # All VMs across all RGs (expensive)
        azlin list -a                 # Same as --show-all-vms
        azlin list --no-quota         # Skip quota information
        azlin list --no-tmux          # Skip tmux session info
        azlin list --all-contexts     # VMs across all configured contexts
        azlin list --contexts "prod*" # VMs from production contexts
        azlin list --contexts "*-dev" --all  # All VMs (including stopped) in dev contexts
    """
    # Validate mutually exclusive display modes
    if compact_mode and wide_mode:
        click.echo(
            "Error: --compact and --wide are mutually exclusive.\nUse one or the other, not both.",
            err=True,
        )
        sys.exit(1)

    console = Console()
    try:
        # NEW: Multi-context query mode (Issue #350)
        # Check for multi-context flags first, before single-context logic
        # Multi-context mode has its own subscription switching per context
        if all_contexts or contexts_pattern:
            # Validate mutually exclusive flags
            if show_all_vms:
                click.echo(
                    "Error: Cannot use --all-contexts or --contexts with --show-all-vms.\n"
                    "These are mutually exclusive modes:\n"
                    "  - Multi-context mode: Query specific RG across multiple contexts\n"
                    "  - All-VMs mode: Query all RGs in single context\n\n"
                    "Use one or the other, not both.",
                    err=True,
                )
                sys.exit(1)

            # Validate empty pattern
            if contexts_pattern and not contexts_pattern.strip():
                click.echo(
                    "Error: --contexts pattern cannot be empty.\n"
                    "Provide a glob pattern (e.g., 'prod*', '*-dev') or use --all-contexts.",
                    err=True,
                )
                sys.exit(1)

            _handle_multi_context_list(
                all_contexts=all_contexts,
                contexts_pattern=contexts_pattern,
                resource_group=resource_group,
                config=config,
                show_all=show_all,
                tag=tag,
                show_quota=show_quota,
                show_tmux=show_tmux,
                wide_mode=wide_mode,
                compact_mode=compact_mode,
                no_cache=no_cache,
            )
            return  # Exit early - multi-context mode handled completely

        # EXISTING: Single-context query mode continues below...
        # Ensure Azure CLI subscription matches current context for single-context queries
        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Get resource group from config or CLI
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Try to get current context (for background refresh later)
        current_ctx = None
        try:
            context_config = ContextManager.load(config)
            current_ctx = context_config.get_current_context()
        except Exception:
            pass  # Silently skip if context unavailable

        # Cross-RG discovery: ONLY if --show-all-vms flag is set
        if not rg and show_all_vms:
            click.echo("Listing all azlin-managed VMs across resource groups...\n")
            try:
                vms, was_cached = TagManager.list_managed_vms(
                    resource_group=None, use_cache=not no_cache
                )
                if not show_all:
                    vms = [vm for vm in vms if vm.is_running()]
            except Exception as e:
                click.echo(
                    f"Error: Failed to list VMs across resource groups: {e}\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
        elif not rg and not show_all_vms:
            # No RG and no --show-all-vms flag: require RG or show help
            click.echo("Error: No resource group specified and no default configured.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml\n", err=True)
            click.echo(
                "To show all VMs accessible by this subscription, run:\n"
                "  azlin list --show-all-vms\n"
                "  (or use the short form: azlin list -a)"
            )
            sys.exit(1)
        else:
            # Single RG listing (rg is guaranteed to be str here)
            assert rg is not None, "Resource group must be set in this branch"

            # Show current context name if available
            if current_ctx:
                click.echo(f"Context: {current_ctx.name}")

            click.echo(f"Listing VMs in resource group: {rg}\n")
            # Use tag-based query to include custom-named VMs (Issue #385 support)
            vms, was_cached = TagManager.list_managed_vms(resource_group=rg, use_cache=not no_cache)
            if not show_all:
                vms = [vm for vm in vms if vm.is_running()]

        # Filter by tag if specified
        if tag:
            try:
                vms = TagManager.filter_vms_by_tag(vms, tag)
            except Exception as e:
                click.echo(f"Error filtering by tag: {e}", err=True)
                sys.exit(1)

        vms = VMManager.sort_by_created_time(vms)

        # Trigger background cache refresh to keep cache warm (non-blocking)
        try:
            from azlin.cache.background_refresh import trigger_background_refresh

            # Create Context object from current context for refresh
            if current_ctx:
                trigger_background_refresh(contexts=[current_ctx])
        except Exception:
            pass  # Never fail user operation due to background refresh

        # Populate session names from tags (hybrid resolution: tags first, config fallback)
        for vm in vms:
            # Use tags already in memory instead of making N API calls (fixes Issue #219)
            if vm.tags and TagManager.TAG_SESSION in vm.tags:
                vm.session_name = vm.tags[TagManager.TAG_SESSION]
            else:
                # Fall back to config file
                vm.session_name = ConfigManager.get_session_name(vm.name, config)

        # Display results
        if not vms:
            click.echo("No VMs found.")
            return

        # Collect quota information if enabled (skip if cached)
        quota_by_region: dict[str, list[QuotaInfo]] = {}
        if show_quota and not was_cached:
            try:
                # Get unique regions from VMs
                regions = list({vm.location for vm in vms if vm.location})
                if regions:
                    # Fetch quota for all regions in parallel
                    regional_quotas = QuotaManager.get_regional_quotas(regions)

                    # Filter to relevant quota types (cores and VM families)
                    for region, quotas in regional_quotas.items():
                        relevant_quotas = [
                            q
                            for q in quotas
                            if "cores" in q.quota_name.lower() or "family" in q.quota_name.lower()
                        ]
                        if relevant_quotas:
                            quota_by_region[region] = relevant_quotas
            except Exception as e:
                click.echo(f"Warning: Failed to fetch quota information: {e}", err=True)

        # Collect tmux session information if enabled (skip if cached)
        tmux_by_vm: dict[str, list[TmuxSession]] = {}
        if show_tmux and not was_cached:
            tmux_by_vm = _collect_tmux_sessions(vms)

        # Measure SSH latency if enabled (skip if cached)
        latency_by_vm: dict[str, LatencyResult] = {}
        if with_latency and not was_cached:
            try:
                from azlin.ssh.latency import SSHLatencyMeasurer

                # Use default SSH key path
                ssh_key_path = "~/.ssh/id_rsa"

                # Measure latencies in parallel
                console_temp = Console()
                console_temp.print("[dim]Measuring SSH latency for running VMs...[/dim]")

                measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=10)
                latency_by_vm = measurer.measure_batch(
                    vms=vms, ssh_user="azureuser", ssh_key_path=ssh_key_path
                )

            except Exception as e:
                click.echo(f"Warning: Failed to measure latencies: {e}", err=True)

        # Display quota summary header if enabled
        if show_quota and quota_by_region:
            console = Console()
            quota_table = Table(
                title="Azure vCPU Quota Summary", show_header=True, header_style="bold"
            )
            quota_table.add_column("Region", style="cyan")
            quota_table.add_column("Quota Type", style="white")
            quota_table.add_column("Used / Total", justify="right")
            quota_table.add_column("Available", justify="right", style="green")
            quota_table.add_column("Usage %", justify="right")

            for region in sorted(quota_by_region.keys()):
                quotas = quota_by_region[region]
                # Show only the most relevant quotas (total cores and specific families in use)
                for quota in quotas:
                    if quota.quota_name.lower() == "cores" or quota.current_usage > 0:
                        usage_pct = quota.usage_percentage()
                        usage_style = (
                            "red" if usage_pct > 80 else "yellow" if usage_pct > 60 else "green"
                        )

                        quota_table.add_row(
                            region,
                            quota.quota_name,
                            f"{quota.current_usage} / {quota.limit if quota.limit >= 0 else '∞'}",
                            str(quota.available()) if quota.limit >= 0 else "∞",
                            f"[{usage_style}]{usage_pct:.0f}%[/{usage_style}]"
                            if quota.limit > 0
                            else "N/A",
                        )

            console.print(quota_table)
            console.print()  # Add spacing

        # Create Rich table for VMs
        console = Console()
        table = Table(title="Azure VMs", show_header=True, header_style="bold")

        # Add columns
        if wide_mode:
            table.add_column("Session Name", style="cyan", no_wrap=True)
            table.add_column("VM Name", style="white", no_wrap=True)
        elif compact_mode:
            table.add_column("Session Name", style="cyan", width=12)
            table.add_column("VM Name", style="white", width=18)
        else:
            table.add_column("Session Name", style="cyan", width=14)
            table.add_column("VM Name", style="white", width=22)

        if compact_mode:
            table.add_column("Status", width=8)
            table.add_column("IP", style="yellow", width=13)
            table.add_column("Region", width=8)
            table.add_column("SKU", width=12)
            table.add_column("vCPUs", justify="right", width=5)
        else:
            table.add_column("Status", width=10)
            table.add_column("IP", style="yellow", width=15)
            table.add_column("Region", width=10)
            table.add_column("SKU", width=15)
            table.add_column("vCPUs", justify="right", width=6)
        table.add_column("Memory", justify="right", width=8)

        if with_latency:
            table.add_column("Latency", justify="right", width=10)

        if show_tmux:
            table.add_column("Tmux Sessions", style="magenta", width=45)

        # Add rows
        for vm in vms:
            session_display = escape(vm.session_name) if vm.session_name else "-"
            vm_status = vm.get_status_display()

            # Color code status
            if vm.is_running():
                status_display = f"[green]{vm_status}[/green]"
            elif vm.is_stopped():
                status_display = f"[red]{vm_status}[/red]"
            else:
                status_display = f"[yellow]{vm_status}[/yellow]"

            # Display IP with type indicator (Issue #492)
            ip = (
                f"{vm.public_ip} (Public)"
                if vm.public_ip
                else f"{vm.private_ip} (Private)"
                if vm.private_ip
                else "N/A"
            )
            size = vm.vm_size or "N/A"

            # Get vCPU count for the VM
            vcpus = QuotaManager.get_vm_size_vcpus(size) if size != "N/A" else 0
            vcpu_display = str(vcpus) if vcpus > 0 else "-"

            # Get memory for the VM
            memory_gb = QuotaManager.get_vm_size_memory(size) if size != "N/A" else 0
            memory_display = f"{memory_gb} GB" if memory_gb > 0 else "-"

            # Build row data
            row_data = [
                session_display,
                vm.name,
                status_display,
                ip,
                vm.location,
                size,
                vcpu_display,
                memory_display,
            ]

            # Add latency if enabled
            if with_latency:
                if vm.name in latency_by_vm:
                    result = latency_by_vm[vm.name]
                    row_data.append(result.display_value())
                else:
                    # VM is stopped (not measured)
                    row_data.append("-")

            # Add tmux sessions if enabled
            if show_tmux:
                if vm.name in tmux_by_vm:
                    sessions = tmux_by_vm[vm.name]
                    # Format sessions with bold (connected) or dim (disconnected) markup (Issue #499)
                    formatted_sessions = []
                    for s in sessions[:3]:  # Show max 3
                        if s.attached:
                            formatted_sessions.append(f"[bold]{escape(s.session_name)}[/bold]")
                        else:
                            formatted_sessions.append(f"[dim]{escape(s.session_name)}[/dim]")

                    session_names = ", ".join(formatted_sessions)
                    if len(sessions) > 3:
                        session_names += f" (+{len(sessions) - 3} more)"
                    row_data.append(session_names)
                elif vm.is_running():
                    row_data.append("[dim]No sessions[/dim]")
                else:
                    row_data.append("-")

            table.add_row(*row_data)

        # Display the table
        console.print(table)

        # Summary
        total_vcpus = sum(
            QuotaManager.get_vm_size_vcpus(vm.vm_size)
            for vm in vms
            if vm.vm_size and vm.is_running()
        )

        total_memory = sum(
            QuotaManager.get_vm_size_memory(vm.vm_size)
            for vm in vms
            if vm.vm_size and vm.is_running()
        )

        summary_parts = [f"Total: {len(vms)} VMs"]
        if show_quota:
            running_vms = sum(1 for vm in vms if vm.is_running())
            summary_parts.append(f"{running_vms} running")
            summary_parts.append(f"{total_vcpus} vCPUs in use")
            summary_parts.append(f"{total_memory} GB memory in use")

        # Add tmux session count if tmux display is enabled
        if show_tmux and tmux_by_vm:
            total_tmux_sessions = sum(len(sessions) for sessions in tmux_by_vm.values())
            summary_parts.append(f"{total_tmux_sessions} tmux sessions")

        console.print(f"\n[bold]{' | '.join(summary_parts)}[/bold]")

        # Show helpful message if not already showing all VMs
        if not show_all_vms:
            console.print(
                "\n[dim]To show all VMs accessible by this subscription, run:[/dim]\n"
                "[cyan]  azlin list --show-all-vms[/cyan] (or: [cyan]azlin list -a[/cyan])\n\n"
                "[dim]To show VMs across multiple contexts, run:[/dim]\n"
                "[cyan]  azlin list --all-contexts --rg <resource-group>[/cyan]\n"
                '[cyan]  azlin list --contexts "pattern*" --rg <resource-group>[/cyan]'
            )

        # List Bastion hosts in the same resource group
        if rg:
            try:
                bastions = BastionDetector.list_bastions(rg)
                if bastions:
                    console.print("\n[bold cyan]Azure Bastion Hosts[/bold cyan]")
                    bastion_table = Table(show_header=True, header_style="bold magenta")
                    bastion_table.add_column("Name", style="cyan")
                    bastion_table.add_column("Location", style="blue")
                    bastion_table.add_column("SKU", style="green")
                    bastion_table.add_column("State", style="yellow")

                    for bastion in bastions:
                        bastion_table.add_row(
                            bastion.get("name", "Unknown"),
                            bastion.get("location", "N/A"),
                            bastion.get("sku", {}).get("name", "N/A"),
                            bastion.get("provisioningState", "N/A"),
                        )

                    console.print(bastion_table)
                    console.print(f"\n[bold]Total: {len(bastions)} Bastion host(s)[/bold]")
            except Exception as e:
                # Silently skip if Bastion listing fails
                logger.debug(f"Bastion listing skipped: {e}")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# SESSION COMMAND (Issue #423)
# ============================================================================


@click.command(name="session")
@click.argument("vm_name", type=str)
@click.argument("session_name", type=str, required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--clear", is_flag=True, help="Clear session name")
def session_command(
    vm_name: str,
    session_name: str | None,
    resource_group: str | None,
    config: str | None,
    clear: bool,
):
    """Set or view session name for a VM.

    Session names are labels that help you identify what you're working on.
    They appear in the 'azlin list' output alongside the VM name.

    \b
    Examples:
        # Set session name
        azlin session azlin-vm-12345 my-project

        # View current session name
        azlin session azlin-vm-12345

        # Clear session name
        azlin session azlin-vm-12345 --clear
    """
    try:
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified and no default configured.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        # Verify VM exists
        vm = VMManager.get_vm(vm_name, rg)

        if not vm:
            click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
            sys.exit(1)

        # Clear session name
        if clear:
            cleared_tag = False
            cleared_config = False

            # Clear from tags
            try:
                cleared_tag = TagManager.delete_session_name(vm_name, rg)
            except Exception as e:
                logger.warning(f"Failed to clear session from tags: {e}")

            # Clear from config
            cleared_config = ConfigManager.delete_session_name(vm_name, config)

            if cleared_tag or cleared_config:
                locations = []
                if cleared_tag:
                    locations.append("VM tags")
                if cleared_config:
                    locations.append("local config")
                click.echo(
                    f"Cleared session name for VM '{vm_name}' from {' and '.join(locations)}"
                )
            else:
                click.echo(f"No session name set for VM '{vm_name}'")
            return

        # View current session name (hybrid: tags first, config fallback)
        if not session_name:
            # Try tags first
            current_name = TagManager.get_session_name(vm_name, rg)
            source = "VM tags" if current_name else None

            # Fall back to config
            if not current_name:
                current_name = ConfigManager.get_session_name(vm_name, config)
                source = "local config" if current_name else None

            if current_name:
                click.echo(f"Session name for '{vm_name}': {current_name} (from {source})")
            else:
                click.echo(f"No session name set for VM '{vm_name}'")
                click.echo(f"\nSet one with: azlin session {vm_name} <session_name>")
            return

        # Set session name (write to both tags and config)
        success_tag = False
        success_config = False

        # Set in tags (primary)
        try:
            TagManager.set_session_name(vm_name, rg, session_name)
            success_tag = True
        except Exception as e:
            logger.warning(f"Failed to set session in tags: {e}")
            click.echo(f"Warning: Could not set session name in VM tags: {e}", err=True)

        # Set in config (backward compatibility)
        try:
            ConfigManager.set_session_name(vm_name, session_name, config)
            success_config = True
        except Exception as e:
            logger.warning(f"Failed to set session in config: {e}")

        if success_tag or success_config:
            locations = []
            if success_tag:
                locations.append("VM tags")
            if success_config:
                locations.append("local config")
            click.echo(
                f"Set session name for '{vm_name}' to '{session_name}' in {' and '.join(locations)}"
            )
        else:
            click.echo("Error: Failed to set session name", err=True)
            sys.exit(1)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# W COMMAND (Issue #423)
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def w(resource_group: str | None, config: str | None):
    """Run 'w' command on all VMs.

    Shows who is logged in and what they are doing on each VM.

    \b
    Examples:
        azlin w
        azlin w --rg my-resource-group
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # List running VMs
        vms = VMManager.list_vms(rg, include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")

        # Populate session names from tags (same logic as list command)
        for vm in vms:
            # Use tags already in memory instead of making N API calls
            if vm.tags and TagManager.TAG_SESSION in vm.tags:
                vm.session_name = vm.tags[TagManager.TAG_SESSION]
            else:
                # Fall back to config file
                vm.session_name = ConfigManager.get_session_name(vm.name, config)

        if not vms:
            click.echo("No running VMs found.")
            return

        running_vms = [vm for vm in vms if vm.is_running()]

        if not running_vms:
            click.echo("No running VMs found.")
            return

        # Get SSH configs with bastion support (Issue #281 fix)
        from azlin.cli_helpers import get_ssh_configs_for_vms

        ssh_configs, routes = get_ssh_configs_for_vms(
            vms=running_vms,
            ssh_key_path=ssh_key_pair.private_path,
            skip_interactive=True,  # Batch operation
            show_summary=True,
        )

        if not ssh_configs:
            click.echo("No reachable VMs found.")
            return

        click.echo(f"Running 'w' on {len(ssh_configs)} VMs...\n")

        # Execute in parallel (bastion tunnels cleaned up automatically via atexit)
        results = WCommandExecutor.execute_w_on_routes(routes, timeout=30)

        # Display output
        output = WCommandExecutor.format_w_output(results)
        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# TOP COMMAND (Issue #423)
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--interval",
    "-i",
    help="Refresh interval in seconds (default 10)",
    type=int,
    default=10,
)
@click.option(
    "--timeout",
    "-t",
    help="SSH timeout per VM in seconds (default 5)",
    type=int,
    default=5,
)
def top(
    resource_group: str | None,
    config: str | None,
    interval: int,
    timeout: int,
):
    """Run distributed top command on all VMs.

    Shows real-time CPU, memory, load, and top processes across all VMs
    in a unified dashboard that updates every N seconds.

    \b
    Examples:
        azlin top                    # Default: 10s refresh
        azlin top -i 5               # 5 second refresh
        azlin top --rg my-rg         # Specific resource group
        azlin top -i 15 -t 10        # 15s refresh, 10s timeout

    \b
    Press Ctrl+C to exit the dashboard.
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # List running VMs
        vms = VMManager.list_vms(rg, include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")

        if not vms:
            click.echo("No running VMs found.")
            return

        running_vms = [vm for vm in vms if vm.is_running()]

        if not running_vms:
            click.echo("No running VMs found.")
            return

        # Get SSH configs with bastion support (Issue #281 fix)
        from azlin.cli_helpers import get_ssh_configs_for_vms

        ssh_configs, _routes = get_ssh_configs_for_vms(
            vms=running_vms,
            ssh_key_path=ssh_key_pair.private_path,
            skip_interactive=True,  # Batch operation
            show_summary=True,
        )

        if not ssh_configs:
            click.echo("No reachable VMs found.")
            return

        click.echo(
            f"Starting distributed top for {len(ssh_configs)} VMs "
            f"(refresh: {interval}s, timeout: {timeout}s)..."
        )
        click.echo("Press Ctrl+C to exit.\n")

        # Create and run executor (bastion tunnels cleaned up automatically via atexit)
        executor = DistributedTopExecutor(
            ssh_configs=ssh_configs,
            interval=interval,
            timeout=timeout,
        )
        executor.run_dashboard()

    except VMManagerError as e:
        # VMManagerError is already user-friendly
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except DistributedTopError as e:
        # DistributedTopError is already user-friendly
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nDashboard stopped by user.")
        sys.exit(0)
    except Exception as e:
        # Log detailed error for debugging, show generic error to user
        logger.debug(f"Unexpected error in distributed top: {e}", exc_info=True)
        click.echo("Error: An unexpected error occurred. Run with --verbose for details.", err=True)
        sys.exit(1)


# ============================================================================
# OS-UPDATE COMMAND (Issue #423)
# ============================================================================


@click.command(name="os-update")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--timeout", help="Timeout in seconds (default 300)", type=int, default=300)
def os_update(vm_identifier: str, resource_group: str | None, config: str | None, timeout: int):
    """Update OS packages on a VM.

    Runs 'apt update && apt upgrade -y' on Ubuntu VMs to update all packages.

    VM_IDENTIFIER can be:
    - Session name (resolved to VM)
    - VM name (requires --resource-group or default config)
    - IP address (direct connection)

    \b
    Examples:
        azlin os-update my-session
        azlin os-update azlin-myvm --rg my-resource-group
        azlin os-update 20.1.2.3
        azlin os-update my-vm --timeout 600  # 10 minute timeout
    """
    try:
        # Get SSH config for VM
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        click.echo(f"Updating OS packages on {vm_identifier}...")
        click.echo("This may take several minutes...\n")

        # Execute OS update
        result = OSUpdateExecutor.execute_os_update(ssh_config, timeout=timeout)

        # Format and display output
        output = OSUpdateExecutor.format_output(result)
        click.echo(output)

        # Exit with appropriate code
        if not result.success:
            sys.exit(1)

    except RemoteExecError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except SSHKeyError as e:
        click.echo(f"SSH key error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# PS COMMAND (Issue #423)
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--grouped", is_flag=True, help="Group output by VM instead of prefixing")
def ps(resource_group: str | None, config: str | None, grouped: bool):
    """Run 'ps aux' command on all VMs.

    Shows running processes on each VM. Output is prefixed with [vm-name].
    SSH processes are automatically filtered out.

    \b
    Examples:
        azlin ps
        azlin ps --rg my-resource-group
        azlin ps --grouped
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # List running VMs
        vms = VMManager.list_vms(rg, include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")

        if not vms:
            click.echo("No running VMs found.")
            return

        running_vms = [vm for vm in vms if vm.is_running()]

        if not running_vms:
            click.echo("No running VMs found.")
            return

        # Get SSH configs with bastion support (Issue #281 fix)
        from azlin.cli_helpers import get_ssh_configs_for_vms

        ssh_configs, _routes = get_ssh_configs_for_vms(
            vms=running_vms,
            ssh_key_path=ssh_key_pair.private_path,
            skip_interactive=True,  # Batch operation
            show_summary=True,
        )

        if not ssh_configs:
            click.echo("No reachable VMs found.")
            return

        click.echo(f"Running 'ps aux' on {len(ssh_configs)} VMs...\n")

        # Execute in parallel (bastion tunnels cleaned up automatically via atexit)
        results = PSCommandExecutor.execute_ps_on_vms(ssh_configs, timeout=30)

        # Display output
        if grouped:
            output = PSCommandExecutor.format_ps_output_grouped(results, filter_ssh=True)
        else:
            output = PSCommandExecutor.format_ps_output(results, filter_ssh=True)

        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except RemoteExecError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# COST COMMAND (Issue #423)
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--by-vm", is_flag=True, help="Show per-VM breakdown")
@click.option("--from", "from_date", help="Start date (YYYY-MM-DD)", type=str)
@click.option("--to", "to_date", help="End date (YYYY-MM-DD)", type=str)
@click.option("--estimate", is_flag=True, help="Show monthly cost estimate")
def cost(
    resource_group: str | None,
    config: str | None,
    by_vm: bool,
    from_date: str | None,
    to_date: str | None,
    estimate: bool,
):
    """Show cost estimates for VMs.

    Displays cost estimates based on VM size and uptime.
    Costs are approximate based on Azure pay-as-you-go pricing.

    \b
    Examples:
        azlin cost
        azlin cost --by-vm
        azlin cost --from 2025-01-01 --to 2025-01-31
        azlin cost --estimate
        azlin cost --rg my-resource-group --by-vm
    """
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Parse dates if provided
        start_date = None
        end_date = None

        if from_date:
            try:
                start_date = datetime.strptime(from_date, "%Y-%m-%d")
            except ValueError:
                click.echo("Error: Invalid from date format. Use YYYY-MM-DD", err=True)
                sys.exit(1)

        if to_date:
            try:
                end_date = datetime.strptime(to_date, "%Y-%m-%d")
            except ValueError:
                click.echo("Error: Invalid to date format. Use YYYY-MM-DD", err=True)
                sys.exit(1)

        # Get cost estimates
        click.echo(f"Calculating costs for resource group: {rg}\n")

        summary = CostTracker.estimate_costs(
            resource_group=rg, from_date=start_date, to_date=end_date, include_stopped=True
        )

        # Display formatted table
        output = CostTracker.format_cost_table(summary, by_vm=by_vm)
        click.echo(output)

        # Show estimate if requested
        if estimate and summary.running_vms > 0:
            monthly = summary.get_monthly_estimate()
            click.echo(f"Monthly estimate for running VMs: ${monthly:.2f}")
            click.echo("")

    except CostTrackerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)
