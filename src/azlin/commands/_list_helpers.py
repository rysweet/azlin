"""Helper functions for list_command decomposition.

This module contains focused helper functions extracted from the monolithic list_command
to reduce cyclomatic complexity and improve maintainability.

Part of Issue #423 - monitoring.py decomposition.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from azlin.config_manager import ConfigManager
from azlin.context_manager import ContextManager
from azlin.lifecycle.health_monitor import HealthMonitor, HealthStatus
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.quota_manager import QuotaInfo, QuotaManager
from azlin.remote_exec import PSCommandExecutor, TmuxSession
from azlin.ssh.latency import LatencyResult, SSHLatencyMeasurer
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMInfo, VMManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "build_vm_table",
    "configure_logging",
    "display_quota_and_bastions",
    "display_summary_and_hints",
    "enrich_vm_data",
    "resolve_vms_to_list",
    "validate_list_options",
]


def _metric_rich(value: float | None, warn: float = 70.0, crit: float = 90.0) -> str:
    """Format a metric percentage with Rich color markup.

    Args:
        value: Percentage value (0-100) or None
        warn: Yellow threshold (default 70%)
        crit: Red threshold (default 90%)

    Returns:
        Rich-markup formatted string
    """
    if value is None:
        return "[dim]-[/dim]"
    if value >= crit:
        return f"[red]{value:.0f}%[/red]"
    if value >= warn:
        return f"[yellow]{value:.0f}%[/yellow]"
    return f"[green]{value:.0f}%[/green]"


def validate_list_options(
    compact_mode: bool,
    wide_mode: bool,
    all_contexts: bool,
    contexts_pattern: str | None,
    show_all_vms: bool,
) -> None:
    """Validate mutually exclusive display modes and multi-context flags.

    Args:
        compact_mode: Compact display mode flag
        wide_mode: Wide display mode flag
        all_contexts: All contexts flag
        contexts_pattern: Context pattern filter
        show_all_vms: Show all VMs flag

    Raises:
        SystemExit: If validation fails with error message
    """
    # Validate mutually exclusive display modes
    if compact_mode and wide_mode:
        click.echo(
            "Error: --compact and --wide are mutually exclusive.\nUse one or the other, not both.",
            err=True,
        )
        sys.exit(1)

    # Validate multi-context vs all-VMs modes
    if (all_contexts or contexts_pattern) and show_all_vms:
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


def configure_logging(verbose: bool) -> None:
    """Configure logging levels based on verbose flag.

    Args:
        verbose: If False, suppress INFO logs from bastion/tunnel operations
    """
    if not verbose:
        # Suppress INFO logs for bastion/tunnel operations (show only warnings+)
        logging.getLogger("azlin.modules.bastion_manager").setLevel(logging.WARNING)
        logging.getLogger("azlin.modules.bastion_detector").setLevel(logging.WARNING)
        logging.getLogger("azlin.modules.ssh_keys").setLevel(logging.WARNING)
        logging.getLogger("azlin.network_security.bastion_connection_pool").setLevel(
            logging.WARNING
        )


def resolve_vms_to_list(
    resource_group: str | None,
    config: str | None,
    show_all: bool,
    tag: str | None,
    show_all_vms: bool,
    no_cache: bool,
) -> tuple[list[VMInfo], bool, str | None]:
    """Resolve which VMs to list based on flags and configuration.

    Args:
        resource_group: Resource group override
        config: Config file path
        show_all: Include stopped VMs
        tag: Tag filter (e.g., "env=prod")
        show_all_vms: Cross-RG discovery mode
        no_cache: Skip cache

    Returns:
        Tuple of (vms list, was_cached flag, current_context_name)

    Raises:
        SystemExit: If resource group resolution fails
    """
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

    current_ctx_name = current_ctx.name if current_ctx else None
    return vms, was_cached, current_ctx_name


def enrich_vm_data(
    vms: list[VMInfo],
    was_cached: bool,
    show_quota: bool,
    show_tmux: bool,
    with_latency: bool,
    show_procs: bool,
    resource_group: str | None,
    verbose: bool,
    console: Console,
    _collect_tmux_sessions_fn,  # type: ignore[no-untyped-def]
    _cache_tmux_sessions_fn,  # type: ignore[no-untyped-def]
    with_health: bool = False,
) -> tuple[
    dict[str, list[QuotaInfo]],
    dict[str, list[TmuxSession]],
    dict[str, LatencyResult],
    dict[str, list[str]],
    dict[str, HealthStatus],
]:
    """Enrich VM data with quota, tmux sessions, latency, processes, and health signals.

    Args:
        vms: List of VMs to enrich
        was_cached: Whether VMs came from cache
        show_quota: Show quota information
        show_tmux: Show tmux sessions
        with_latency: Measure SSH latency
        show_procs: Show active processes
        resource_group: Resource group (for tmux caching and health checks)
        verbose: Verbose output
        console: Rich console for status display
        _collect_tmux_sessions_fn: Function to collect tmux sessions
        _cache_tmux_sessions_fn: Function to cache tmux sessions
        with_health: Collect VM health signals (agent status, CPU/mem/disk)

    Returns:
        Tuple of (quota_by_region, tmux_by_vm, latency_by_vm, active_procs_by_vm, health_by_vm)
    """
    quota_by_region: dict[str, list[QuotaInfo]] = {}
    tmux_by_vm: dict[str, list[TmuxSession]] = {}
    latency_by_vm: dict[str, LatencyResult] = {}
    active_procs_by_vm: dict[str, list[str]] = {}
    health_by_vm: dict[str, HealthStatus] = {}

    # Collect quota information if enabled
    if show_quota:
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

    # Collect tmux session information if enabled
    if show_tmux:
        from azlin.cache.vm_list_cache import VMListCache

        cache = VMListCache()

        # Check if we can use cached tmux sessions (on cache hit with fresh tmux data)
        if was_cached:
            # Try to use cached tmux sessions
            tmux_from_cache = {}
            all_fresh = True
            for vm in vms:
                entry = cache.get(vm.name, vm.resource_group)
                if entry and not entry.is_tmux_expired():
                    # Cached tmux data is fresh
                    tmux_from_cache[vm.name] = [
                        TmuxSession.from_dict(s) for s in entry.tmux_sessions
                    ]
                else:
                    all_fresh = False
                    break

            if all_fresh and tmux_from_cache:
                # All tmux data is fresh - use cache
                tmux_by_vm = tmux_from_cache
                if verbose:
                    click.echo("[TMUX CACHE HIT] Using cached tmux sessions")
            else:
                # Some stale - collect fresh
                if verbose:
                    click.echo(f"Collecting tmux sessions from {len(vms)} VMs...")
                tmux_by_vm = _collect_tmux_sessions_fn(vms)
                if resource_group:
                    _cache_tmux_sessions_fn(tmux_by_vm, resource_group, cache)
        else:
            # Cache miss - collect and cache tmux sessions
            running_count = len([vm for vm in vms if vm.is_running()])
            if running_count > 0 and not verbose:
                with console.status(
                    f"[dim]Collecting tmux sessions from {running_count} VMs...[/dim]"
                ):
                    tmux_by_vm = _collect_tmux_sessions_fn(vms)
            else:
                if verbose:
                    click.echo(f"Collecting tmux sessions from {running_count} VMs...")
                tmux_by_vm = _collect_tmux_sessions_fn(vms)

            # Cache the collected sessions
            if resource_group:
                _cache_tmux_sessions_fn(tmux_by_vm, resource_group, cache)

    # Measure SSH latency if enabled (always fresh — latency is ephemeral)
    if with_latency:
        try:
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

    # Collect active user processes if enabled (always fresh — processes are ephemeral)
    if show_procs:
        try:
            # Ensure SSH key is available
            ssh_key_pair = SSHKeyManager.ensure_key_exists()
            ssh_key_path = ssh_key_pair.private_path

            # Build SSH configs for running VMs with public IPs
            running_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

            if running_vms:
                ssh_configs = []
                vm_name_map = {}  # Map IP to VM name

                for vm in running_vms:
                    assert vm.public_ip is not None
                    ssh_config = SSHConfig(
                        host=vm.public_ip, user="azureuser", key_path=ssh_key_path
                    )
                    ssh_configs.append(ssh_config)
                    vm_name_map[vm.public_ip] = vm.name

                # Execute ps aux on all VMs in parallel
                if ssh_configs:
                    ps_results = PSCommandExecutor.execute_ps_on_vms(
                        ssh_configs, timeout=30, use_forest=False
                    )

                    # Filter to user processes only
                    for result in ps_results:
                        if result.success:
                            procs = PSCommandExecutor.filter_user_processes(result.stdout)
                            if procs and result.vm_name in vm_name_map:
                                # Map from IP back to VM name
                                vm_name = vm_name_map[result.vm_name]
                                active_procs_by_vm[vm_name] = procs[:5]
        except SSHKeyError as e:
            logger.warning(f"Cannot collect processes: SSH key validation failed: {e}")
        except Exception as e:
            click.echo(f"Warning: Failed to collect active processes: {e}", err=True)

    # Collect VM health signals if enabled (uses Azure management plane - works for all VM types)
    if with_health and resource_group:
        try:
            console.print("[dim]Checking VM health signals...[/dim]")
            monitor = HealthMonitor(resource_group=resource_group)
            vm_names = [vm.name for vm in vms]
            health_results = monitor.check_all_vms_health(vm_names)
            for vm_name, status, _error in health_results:
                if status is not None:
                    health_by_vm[vm_name] = status
        except Exception as e:
            click.echo(f"Warning: Failed to collect health data: {e}", err=True)

    return quota_by_region, tmux_by_vm, latency_by_vm, active_procs_by_vm, health_by_vm


def display_quota_and_bastions(
    console: Console,
    show_quota: bool,
    quota_by_region: dict[str, list[QuotaInfo]],
    resource_group: str | None,
) -> None:
    """Display quota summary and bastion hosts.

    Args:
        console: Rich console for output
        show_quota: Whether to display quota
        quota_by_region: Quota information by region
        resource_group: Resource group for bastion listing
    """
    # Display quota summary header if enabled
    if show_quota and quota_by_region:
        quota_table = Table(title="Azure vCPU Quota Summary", show_header=True, header_style="bold")
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

    # List Bastion hosts BEFORE VMs table (moved from end)
    if resource_group:
        try:
            from azlin.modules.bastion_detector import BastionDetector

            bastions = BastionDetector.list_bastions(resource_group)
            if bastions:
                bastion_table = Table(
                    title="Azure Bastion Hosts", show_header=True, header_style="bold"
                )
                bastion_table.add_column("Name", style="cyan")
                bastion_table.add_column("Location")
                bastion_table.add_column("SKU")

                for bastion in bastions:
                    bastion_table.add_row(
                        bastion.get("name", "Unknown"),
                        bastion.get("location", "N/A"),
                        bastion.get("sku", {}).get("name", "N/A"),
                    )

                console.print(bastion_table)
                console.print()  # Spacing before VM table
        except Exception as e:
            logger.debug(f"Bastion listing skipped: {e}")


def get_os_display_info(os_offer: str | None, os_type: str | None) -> tuple[str, str]:
    """Map Azure image offer to OS icon and friendly name.

    Args:
        os_offer: Azure image reference offer (e.g., "ubuntu-25_10")
        os_type: Azure OS type (e.g., "Linux", "Windows")

    Returns:
        Tuple of (icon, friendly_name) e.g., ("\U0001f7e0", "Ubuntu 25.10")
    """
    # Icons: 🐧 Linux/all distros (Tux), 🪟 Windows
    penguin = "\U0001f427"
    window = "\U0001fa9f"

    if not os_offer:
        if os_type == "Windows":
            return (window, "Windows")
        if os_type == "Linux":
            return (penguin, "Linux")
        return ("", "")

    offer_lower = os_offer.lower()

    # Ubuntu: newer format "ubuntu-25_10", "ubuntu-24_04-lts"
    m = re.match(r"ubuntu-(\d+)_(\d+)(?:-lts)?$", offer_lower)
    if m:
        ver = f"{m.group(1)}.{m.group(2)}"
        suffix = " LTS" if "-lts" in offer_lower else ""
        return (penguin, f"Ubuntu {ver}{suffix}")

    # Ubuntu: older format "0001-com-ubuntu-server-jammy", "0001-com-ubuntu-server-focal"
    codename_map = {
        "plucky": "25.04",
        "oracular": "24.10",
        "noble": "24.04 LTS",
        "jammy": "22.04 LTS",
        "focal": "20.04 LTS",
        "bionic": "18.04 LTS",
    }
    for codename, version in codename_map.items():
        if codename in offer_lower:
            return (penguin, f"Ubuntu {version}")

    if "ubuntu" in offer_lower:
        return (penguin, "Ubuntu")

    # Debian
    m = re.match(r"debian-(\d+)", offer_lower)
    if m:
        return (penguin, f"Debian {m.group(1)}")
    if "debian" in offer_lower:
        return (penguin, "Debian")

    # Windows Server
    if "windowsserver" in offer_lower or "windows" in offer_lower:
        return (window, "Windows Server")

    # RHEL
    m = re.match(r"rhel[-_]?(\d+)", offer_lower)
    if m:
        return (penguin, f"RHEL {m.group(1)}")
    if "rhel" in offer_lower:
        return (penguin, "RHEL")

    # CentOS
    if "centos" in offer_lower:
        return (penguin, "CentOS")

    # SUSE
    if "sles" in offer_lower or "suse" in offer_lower:
        return (penguin, "SUSE")

    # AlmaLinux / Rocky
    if "alma" in offer_lower:
        return (penguin, "AlmaLinux")
    if "rocky" in offer_lower:
        return (penguin, "Rocky Linux")

    # Fallback
    if os_type == "Windows":
        return (window, os_offer)
    return (penguin, os_offer)


def build_vm_table(
    vms: list[VMInfo],
    wide_mode: bool,
    compact_mode: bool,
    show_tmux: bool,
    show_procs: bool,
    with_latency: bool,
    tmux_by_vm: dict[str, list[TmuxSession]],
    active_procs_by_vm: dict[str, list[str]],
    latency_by_vm: dict[str, LatencyResult],
    with_health: bool = False,
    health_by_vm: dict[str, HealthStatus] | None = None,
) -> Table:
    """Build Rich table for VM display.

    Args:
        vms: List of VMs to display
        wide_mode: Wide display mode
        compact_mode: Compact display mode
        show_tmux: Show tmux sessions
        show_procs: Show active processes
        with_latency: Show latency
        tmux_by_vm: Tmux sessions by VM name
        active_procs_by_vm: Active processes by VM name
        latency_by_vm: Latency results by VM name
        with_health: Show health signals (agent, CPU, mem, disk)
        health_by_vm: Health status by VM name

    Returns:
        Configured Rich table with VM data
    """
    if health_by_vm is None:
        health_by_vm = {}
    table = Table(title="Azure VMs", show_header=True, header_style="bold")

    # Session Name column
    if wide_mode:
        table.add_column("Session", style="cyan", no_wrap=True)
    elif compact_mode:
        table.add_column("Session", style="cyan", width=12)
    else:
        table.add_column("Session", style="cyan", width=14)

    # Tmux Sessions column (moved to 2nd position)
    if show_tmux:
        if compact_mode:
            table.add_column("Tmux", style="magenta", width=20)
        elif wide_mode:
            table.add_column("Tmux Sessions", style="magenta", width=30)
        else:
            table.add_column("Tmux Sessions", style="magenta", width=25)

    # VM Name column (only in wide mode)
    if wide_mode:
        table.add_column("VM Name", style="white", no_wrap=True)

    # OS column (before Status)
    if wide_mode:
        table.add_column("OS", no_wrap=True)
    elif compact_mode:
        table.add_column("OS", width=12)
    else:
        table.add_column("OS", width=18)

    # Status column
    if compact_mode:
        table.add_column("Status", width=6)
    else:
        table.add_column("Status", width=8)

    # IP column (dim to reduce visual weight)
    if compact_mode:
        table.add_column("IP", style="dim yellow", width=15)
    else:
        table.add_column("IP", style="dim yellow", width=18)

    # Region column (dim)
    if compact_mode:
        table.add_column("Rgn", style="dim", width=6)
    else:
        table.add_column("Region", style="dim", width=8)

    # SKU column (only in wide mode, dim)
    if wide_mode:
        table.add_column("SKU", style="dim", width=15)

    # vCPUs column (dim)
    table.add_column("CPU", style="dim", justify="right", width=3)

    # Memory column (dim)
    table.add_column("Mem", style="dim", justify="right", width=5)

    # Active Processes column (if requested)
    if show_procs:
        table.add_column("Active Processes", style="green", width=30)

    if with_latency:
        table.add_column("Latency", justify="right", width=8)

    if with_health:
        table.add_column("Agent", width=6)
        table.add_column("CPU", justify="right", width=6)
        table.add_column("Mem", justify="right", width=6)
        table.add_column("Disk", justify="right", width=6)

    # Add rows
    for vm in vms:
        # Get OS name for the OS column
        _os_icon, os_name = get_os_display_info(vm.os_offer, vm.os_type)

        session_display = escape(vm.session_name) if vm.session_name else "-"

        status = vm.get_status_display()

        # Color code status
        if vm.is_running():
            status_display = f"[green]{status}[/green]"
        elif vm.is_stopped():
            status_display = f"[red]{status}[/red]"
        else:
            status_display = f"[yellow]{status}[/yellow]"

        # Display IP with type indicator (Issue #492)
        ip = (
            f"{vm.public_ip} (Public)"
            if vm.public_ip
            else f"{vm.private_ip} (Bast)"
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

        # Build row data (order must match column order above)
        row_data = [session_display]

        # Tmux sessions (if enabled, comes 2nd)
        if show_tmux:
            if vm.name in tmux_by_vm:
                sessions = tmux_by_vm[vm.name]
                formatted_sessions = []
                for s in sessions[:3]:  # Show max 3
                    if s.attached:
                        formatted_sessions.append(
                            f"[white bold]{escape(s.session_name)}[/white bold]"
                        )
                    else:
                        formatted_sessions.append(
                            f"[bright_black]{escape(s.session_name)}[/bright_black]"
                        )
                session_names = ", ".join(formatted_sessions)
                if len(sessions) > 3:
                    session_names += f" (+{len(sessions) - 3} more)"
                row_data.append(session_names)
            elif vm.is_running():
                row_data.append("[dim]No sessions[/dim]")
            else:
                row_data.append("-")

        # VM Name (only in wide mode)
        if wide_mode:
            row_data.append(vm.name)

        # OS name
        row_data.append(os_name or "-")

        # Status, IP, Region
        row_data.extend([status_display, ip, vm.location or "N/A"])

        # SKU (only in wide mode)
        if wide_mode:
            row_data.append(size)

        # vCPUs and Memory
        row_data.extend([vcpu_display, memory_display])

        # Active Processes (if enabled)
        if show_procs:
            if vm.name in active_procs_by_vm:
                row_data.append(", ".join(active_procs_by_vm[vm.name]))
            else:
                row_data.append("-")

        # Latency (if enabled)
        if with_latency:
            if vm.name in latency_by_vm:
                result = latency_by_vm[vm.name]
                row_data.append(result.display_value())
            else:
                row_data.append("-")

        # Health signals (if enabled)
        if with_health:
            if vm.name in health_by_vm:
                h = health_by_vm[vm.name]
                # Agent health
                if not vm.is_running():
                    row_data.append("[dim]-[/dim]")
                elif h.ssh_reachable:
                    row_data.append("[green]OK[/green]")
                else:
                    row_data.append("[red]FAIL[/red]")
                # Resource metrics
                cpu = h.metrics.cpu_percent if h.metrics else None
                mem = h.metrics.memory_percent if h.metrics else None
                disk = h.metrics.disk_percent if h.metrics else None
                row_data.extend([_metric_rich(cpu), _metric_rich(mem), _metric_rich(disk)])
            else:
                row_data.extend(["[dim]-[/dim]", "[dim]-[/dim]", "[dim]-[/dim]", "[dim]-[/dim]"])

        table.add_row(*row_data)

    return table


def display_summary_and_hints(
    console: Console,
    vms: list[VMInfo],
    show_quota: bool,
    show_tmux: bool,
    show_all_vms: bool,
    tmux_by_vm: dict[str, list[TmuxSession]],
) -> None:
    """Display summary statistics and helpful hints.

    Args:
        console: Rich console for output
        vms: List of VMs
        show_quota: Whether quota was displayed
        show_tmux: Whether tmux was displayed
        show_all_vms: Whether all-VMs mode was used
        tmux_by_vm: Tmux sessions by VM name
    """
    # Summary
    total_vcpus = sum(
        QuotaManager.get_vm_size_vcpus(vm.vm_size) for vm in vms if vm.vm_size and vm.is_running()
    )

    total_memory = sum(
        QuotaManager.get_vm_size_memory(vm.vm_size) for vm in vms if vm.vm_size and vm.is_running()
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

    # Show helpful hints
    if not show_all_vms:
        hints = []
        hints.append("[dim]Hints:[/dim]")
        hints.append(
            "[cyan]  azlin list -a[/cyan]        [dim]Show all VMs across all resource groups[/dim]"
        )
        hints.append(
            "[cyan]  azlin list -w[/cyan]        [dim]Wide mode (show VM Name, SKU columns)[/dim]"
        )
        hints.append(
            "[cyan]  azlin list -r[/cyan]        "
            "[dim]Restore all tmux sessions in new terminal window[/dim]"
        )
        hints.append("[cyan]  azlin list -q[/cyan]        [dim]Show quota usage (slower)[/dim]")
        hints.append(
            "[cyan]  azlin list -v[/cyan]        [dim]Verbose mode (show tunnel/SSH details)[/dim]"
        )
        console.print("\n".join(hints))
