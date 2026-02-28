"""LIST command for azlin monitoring.

This module contains the 'list' command (main VM listing logic) extracted from monitoring.py.
Part of Issue #423 - monitoring.py decomposition.

Command:
    - list: List VMs in a resource group
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path

import click
from rich.console import Console

from azlin.azure_auth import AzureAuthenticator
from azlin.commands._list_helpers import (
    build_vm_table,
    configure_logging,
    display_quota_and_bastions,
    display_summary_and_hints,
    enrich_vm_data,
    resolve_vms_to_list,
    validate_list_options,
)
from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.network_security.bastion_connection_pool import (
    BastionConnectionPool,
    PooledTunnel,
    SecurityError,
)
from azlin.remote_exec import RemoteExecutor, TmuxSession, TmuxSessionExecutor
from azlin.ssh.latency import LatencyResult, SSHLatencyMeasurer
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMInfo, VMManagerError

logger = logging.getLogger(__name__)

__all__ = ["get_vm_session_pairs", "list_command"]

# SSH timeout configuration for tmux session detection
# These values are based on empirical observation and conservative estimates:
# - Direct SSH: 95th percentile ~3s, buffer to 5s for network variability
# - Bastion: Routing through Azure Bastion adds ~5-7s latency, plus VM SSH startup ~3-5s, buffer to 15s
DIRECT_SSH_TMUX_TIMEOUT = 5  # Seconds - Direct SSH connections (public IP)
BASTION_TUNNEL_TMUX_TIMEOUT = 15  # Seconds - Bastion tunnels (routing latency + VM SSH startup)


# ============================================================================
# BASTION TUNNEL RETRY HELPERS (Issue #588)
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
    vm: VMInfo,
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


def get_vm_session_pairs(
    resource_group: str,
    config_path: str | None = None,
    include_stopped: bool = False,
) -> list[tuple[VMInfo, list[TmuxSession]]]:
    """Get canonical VM/session pairs - SINGLE SOURCE OF TRUTH.

    Uses tag-based discovery (TagManager) to match the behavior of 'azlin list',
    ensuring only azlin-managed VMs are included.

    Used by 'azlin list --show-tmux', 'azlin restore', and 'azlin sessions save'.
    """
    vms, _was_cached = TagManager.list_managed_vms(resource_group=resource_group, use_cache=False)
    if not vms:
        return []

    # Filter stopped VMs if requested (list_managed_vms always includes stopped)
    if not include_stopped:
        vms = [vm for vm in vms if vm.is_running()]

    if not vms:
        return []

    # Populate session names from tags (same as list_command)
    for vm in vms:
        if vm.tags and TagManager.TAG_SESSION in vm.tags:
            vm.session_name = vm.tags[TagManager.TAG_SESSION]
        else:
            vm.session_name = ConfigManager.get_session_name(vm.name, config_path)

    tmux_by_vm, _ = _collect_tmux_sessions(vms)

    # Return (VM, sessions) pairs
    return [(vm, tmux_by_vm.get(vm.name, [])) for vm in vms]


def _cache_tmux_sessions(
    tmux_by_vm: dict[str, list[TmuxSession]],
    rg: str,
    cache: object,
) -> None:
    """Cache tmux sessions with corrected vm_name (IP → VM name).

    The tmux session objects contain the SSH host (IP address) as vm_name.
    Before caching, we replace that with the actual VM name.
    """
    for vm_name, sessions in tmux_by_vm.items():
        corrected_sessions = []
        for s in sessions:
            session_dict = s.to_dict()
            session_dict["vm_name"] = vm_name  # Replace IP with actual VM name
            corrected_sessions.append(session_dict)
        cache.set_tmux(vm_name, rg, corrected_sessions)  # type: ignore[attr-defined]


def _sync_key_if_auth_failed(
    ssh_config: SSHConfig,
    vm: VMInfo,
    ssh_key_path: Path,
) -> bool:
    """Test SSH connectivity and sync key if authentication fails.

    When azlin list detects SSH "Permission denied" (exit code 255), this
    function syncs the local SSH public key to the VM via Azure Run Command
    API (which doesn't require SSH) and returns True so the caller can retry.

    Args:
        ssh_config: SSH config for the tunnel connection
        vm: VM info (name, resource_group)
        ssh_key_path: Path to private key

    Returns:
        True if key was synced (caller should retry SSH), False otherwise
    """
    from azlin.modules.ssh_keys import SSHKeyManager as _SSHKeyManager
    from azlin.modules.vm_key_sync import DEFAULT_TIMEOUT, VMKeySync

    # Quick SSH test: run 'true' to check auth
    result = RemoteExecutor.execute_command(ssh_config, "true", timeout=10)
    if result.success:
        return False  # SSH works fine, no sync needed

    # Only sync on auth failures (exit code 255 = SSH protocol/auth error)
    if result.exit_code != 255:
        return False

    stderr_lower = result.stderr.lower()
    if "permission denied" not in stderr_lower and "publickey" not in stderr_lower:
        return False

    logger.info(
        f"SSH auth failed for {vm.name} - syncing key via Azure Run Command API"
    )

    try:
        public_key = _SSHKeyManager.get_public_key(ssh_key_path)
        config = ConfigManager.load_config()
        sync_manager = VMKeySync(config.to_dict())
        sync_result = sync_manager.ensure_key_authorized(
            vm_name=vm.name,
            resource_group=vm.resource_group,
            public_key=public_key,
            timeout=DEFAULT_TIMEOUT,
        )
        if sync_result.synced:
            logger.info(f"SSH key synced to {vm.name} in {sync_result.duration_ms}ms")
            return True
        elif sync_result.already_present:
            logger.debug(f"SSH key already present on {vm.name} (auth issue may be elsewhere)")
            return False
        elif sync_result.error:
            logger.warning(f"Key sync failed for {vm.name}: {sync_result.error}")
            return False
    except Exception as e:
        logger.warning(f"Key sync attempt failed for {vm.name}: {e}")

    return False


def _collect_tmux_sessions(
    vms: list[VMInfo], with_latency: bool = False
) -> tuple[dict[str, list[TmuxSession]], dict[str, LatencyResult]]:
    """Collect tmux sessions from running VMs.

    Supports both direct SSH (VMs with public IPs) and Bastion tunneling
    (VMs with only private IPs).

    When with_latency=True, opportunistically measures SSH latency through
    Bastion tunnels while they are already open for tmux collection.
    No extra tunnel creation cost.

    Args:
        vms: List of VMInfo objects
        with_latency: If True, measure SSH latency through Bastion tunnels

    Returns:
        Tuple of (tmux_by_vm, bastion_latency_by_vm)
    """
    tmux_by_vm: dict[str, list[TmuxSession]] = {}
    bastion_latency_by_vm: dict[str, LatencyResult] = {}

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
        return tmux_by_vm, bastion_latency_by_vm

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

                            # Auto-sync SSH key if auth fails (Issue #740)
                            # Tests SSH first; if "Permission denied", syncs key
                            # via Azure Run Command API and signals caller to retry.
                            key_was_synced = _sync_key_if_auth_failed(
                                ssh_config, vm, ssh_key_path
                            )
                            if key_was_synced:
                                logger.info(
                                    f"Key synced for {vm.name}, retrying tmux query"
                                )

                            logger.debug(
                                f"Querying VM {vm.name} via tunnel port {pooled_tunnel.tunnel.local_port}"
                            )
                            tmux_sessions = TmuxSessionExecutor.get_sessions_single_vm(
                                ssh_config, vm_name=vm.name, timeout=BASTION_TUNNEL_TMUX_TIMEOUT
                            )
                            logger.debug(
                                f"VM {vm.name} returned {len(tmux_sessions)} sessions: {[s.session_name for s in tmux_sessions]}"
                            )

                            # Add sessions to result
                            if tmux_sessions:
                                logger.debug(
                                    f"Found {len(tmux_sessions)} tmux sessions on {vm.name}"
                                )
                            else:
                                logger.debug(f"No tmux sessions found on {vm.name}")

                            # Add sessions to result (vm_name already correct from get_sessions_single_vm)
                            if vm.name not in tmux_by_vm:
                                tmux_by_vm[vm.name] = []
                            tmux_by_vm[vm.name].extend(tmux_sessions)

                            # Measure SSH latency through tunnel while it's open (no extra cost)
                            if with_latency:
                                measurer = SSHLatencyMeasurer(timeout=5.0)
                                bastion_latency_by_vm[vm.name] = measurer.measure_at_port(
                                    vm_name=vm.name,
                                    host="127.0.0.1",
                                    port=pooled_tunnel.tunnel.local_port,
                                    ssh_user="azureuser",
                                    ssh_key_path=str(ssh_key_path),
                                )
                                logger.debug(
                                    f"Bastion latency for {vm.name}: "
                                    f"{bastion_latency_by_vm[vm.name].display_value()}"
                                )

                        except BastionManagerError as e:
                            logger.warning(f"Failed to create Bastion tunnel for VM {vm.name}: {e}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch tmux sessions from Bastion VM {vm.name}: {e}"
                            )

                finally:
                    # Ensure pool tunnels are cleaned up after ALL VMs processed
                    pool.close_all()

        except Exception as e:
            logger.warning(f"Failed to initialize Bastion support: {e}")

    return tmux_by_vm, bastion_latency_by_vm


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
    from azlin.context_selector import ContextSelector, ContextSelectorError

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
    from azlin.multi_context_list import MultiContextQueryError
    from azlin.multi_context_list_async import query_all_contexts_parallel

    try:
        click.echo(f"Querying VMs in resource group '{rg}' across {len(contexts)} contexts...\n")

        from azlin.cache.vm_list_cache import VMListCache

        cache = VMListCache()
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
    from azlin.multi_context_display import MultiContextDisplay

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


@click.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group to list VMs from", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "show_all", help="Show all VMs (including stopped)", is_flag=True)
@click.option("--tag", help="Filter VMs by tag (format: key or key=value)", type=str)
@click.option(
    "--quota",
    "-q",
    "show_quota",
    is_flag=True,
    default=False,
    help="Show Azure vCPU quota information (slower)",
)
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
@click.option(
    "--verbose",
    "-v",
    "verbose",
    is_flag=True,
    default=False,
    help="Show detailed output (tunnel creation, SSH commands, etc.)",
)
@click.option(
    "--restore",
    "-r",
    "run_restore",
    is_flag=True,
    default=False,
    help="After listing, restore all tmux sessions in Windows Terminal tabs",
)
@click.option(
    "--show-procs",
    "show_procs",
    is_flag=True,
    default=False,
    help="Show active user processes on each VM (top 5, public IP VMs only)",
)
@click.option(
    "--with-health",
    "with_health",
    is_flag=True,
    default=False,
    help="Show VM health signals (agent status, CPU/mem/disk) - slower, uses Azure management plane",
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
    verbose: bool = False,
    run_restore: bool = False,
    show_procs: bool = False,
    with_health: bool = False,
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
        azlin list --with-latency     # Include SSH latency measurements (public IP VMs)
        azlin list --with-health      # Include health signals (agent, CPU, mem, disk)
        azlin list --show-all-vms     # All VMs across all RGs (expensive)
        azlin list -a                 # Same as --show-all-vms
        azlin list --no-quota         # Skip quota information
        azlin list --no-tmux          # Skip tmux session info
        azlin list --all-contexts     # VMs across all configured contexts
        azlin list --contexts "prod*" # VMs from production contexts
        azlin list --contexts "*-dev" --all  # All VMs (including stopped) in dev contexts
    """
    # Step 1: Validate options
    validate_list_options(compact_mode, wide_mode, all_contexts, contexts_pattern, show_all_vms)

    # Step 2: Configure logging
    configure_logging(verbose)

    console = Console()
    try:
        # Step 3: Handle multi-context mode (early exit if applicable)
        if all_contexts or contexts_pattern:
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

        # Step 4: Ensure subscription active for single-context queries
        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Step 5: Resolve VMs to list
        vms, was_cached, current_ctx_name = resolve_vms_to_list(
            resource_group=resource_group,
            config=config,
            show_all=show_all,
            tag=tag,
            show_all_vms=show_all_vms,
            no_cache=no_cache,
        )

        # Early exit if no VMs found
        if not vms:
            click.echo("No VMs found.")
            return

        # Step 6: Enrich VMs with quota, tmux, latency, processes, health
        quota_by_region, tmux_by_vm, latency_by_vm, active_procs_by_vm, health_by_vm = (
            enrich_vm_data(
                vms=vms,
                was_cached=was_cached,
                show_quota=show_quota,
                show_tmux=show_tmux,
                with_latency=with_latency,
                show_procs=show_procs,
                resource_group=ConfigManager.get_resource_group(resource_group, config),
                verbose=verbose,
                console=console,
                _collect_tmux_sessions_fn=_collect_tmux_sessions,
                _cache_tmux_sessions_fn=_cache_tmux_sessions,
                with_health=with_health,
            )
        )

        # Step 7: Display quota summary and bastion hosts
        display_quota_and_bastions(
            console=console,
            show_quota=show_quota,
            quota_by_region=quota_by_region,
            resource_group=ConfigManager.get_resource_group(resource_group, config),
        )

        # Step 8: Build and display VM table
        table = build_vm_table(
            vms=vms,
            wide_mode=wide_mode,
            compact_mode=compact_mode,
            show_tmux=show_tmux,
            show_procs=show_procs,
            with_latency=with_latency,
            tmux_by_vm=tmux_by_vm,
            active_procs_by_vm=active_procs_by_vm,
            latency_by_vm=latency_by_vm,
            with_health=with_health,
            health_by_vm=health_by_vm,
        )
        console.print(table)

        # Step 9: Display summary and hints
        display_summary_and_hints(
            console=console,
            vms=vms,
            show_quota=show_quota,
            show_tmux=show_tmux,
            show_all_vms=show_all_vms,
            tmux_by_vm=tmux_by_vm,
        )

        # Step 10: Handle restore workflow if requested
        if run_restore and show_tmux and tmux_by_vm:
            console.print("\n[bold cyan]Restoring sessions...[/bold cyan]")
            from azlin.commands.restore import restore_command

            # Invoke restore command via Click context, passing verbose flag
            ctx = click.get_current_context()
            ctx.invoke(restore_command, verbose=verbose)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
