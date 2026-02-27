"""Health command for azlin - VM Health Dashboard with Four Golden Signals.

Displays a Rich table showing health status for all managed VMs using
the Four Golden Signals framework:
    - Latency: SSH reachability
    - Traffic: Active tmux sessions (via power state proxy)
    - Errors: SSH failure count
    - Saturation: CPU / Memory / Disk usage percentages

Command:
    - health: VM health dashboard

Public API:
    health: Click command for 'azlin health'
"""

from __future__ import annotations

import logging
import sys

import click

from azlin.config_manager import ConfigManager
from azlin.lifecycle.health_monitor import (
    HealthCheckError,
    HealthMonitor,
    HealthStatus,
    VMState,
)
from azlin.tag_manager import TagManager

logger = logging.getLogger(__name__)

__all__ = ["health"]


def _state_display(state: VMState) -> str:
    """Format VM state with color indicator."""
    state_map = {
        VMState.RUNNING: click.style("running", fg="green"),
        VMState.STOPPED: click.style("stopped", fg="yellow"),
        VMState.DEALLOCATED: click.style("deallocated", fg="red"),
        VMState.UNKNOWN: click.style("unknown", fg="white"),
    }
    return state_map.get(state, str(state))


def _ssh_display(status: HealthStatus) -> str:
    """Format SSH reachability."""
    if status.state != VMState.RUNNING:
        return click.style("-", fg="white")
    if status.ssh_reachable:
        return click.style("OK", fg="green")
    return click.style("FAIL", fg="red")


def _metric_display(value: float | None, warn: float = 70.0, crit: float = 90.0) -> str:
    """Format a metric percentage with color thresholds."""
    if value is None:
        return click.style("-", fg="white")
    if value >= crit:
        return click.style(f"{value:.0f}%", fg="red")
    if value >= warn:
        return click.style(f"{value:.0f}%", fg="yellow")
    return click.style(f"{value:.0f}%", fg="green")


def _errors_display(failures: int) -> str:
    """Format error count."""
    if failures == 0:
        return click.style("0", fg="green")
    if failures <= 2:
        return click.style(str(failures), fg="yellow")
    return click.style(str(failures), fg="red")


def _render_health_table(results: list[tuple[str, HealthStatus | None, str | None]]) -> None:
    """Render health results as a formatted table.

    Args:
        results: List of (vm_name, health_status_or_none, error_message_or_none)
    """
    # Header
    header = f"{'VM':<25} {'State':<15} {'SSH':<8} {'Errors':<8} {'CPU':<8} {'Mem':<8} {'Disk':<8}"
    click.echo()
    click.echo(click.style("VM Health Dashboard (Four Golden Signals)", bold=True))
    click.echo(click.style("-" * 70, fg="white"))
    click.echo(header)
    click.echo(click.style("-" * 70, fg="white"))

    for vm_name, status, error in results:
        if error:
            click.echo(f"{vm_name:<25} {click.style('ERROR', fg='red'):<15} {error}")
            continue

        if status is None:
            click.echo(f"{vm_name:<25} {click.style('unknown', fg='white')}")
            continue

        cpu = status.metrics.cpu_percent if status.metrics else None
        mem = status.metrics.memory_percent if status.metrics else None
        disk = status.metrics.disk_percent if status.metrics else None

        # Use raw strings for fixed-width columns, apply color
        click.echo(
            f"{vm_name:<25} "
            f"{_state_display(status.state):<24} "  # Extra width for ANSI codes
            f"{_ssh_display(status):<17} "
            f"{_errors_display(status.ssh_failures):<17} "
            f"{_metric_display(cpu):<17} "
            f"{_metric_display(mem):<17} "
            f"{_metric_display(disk)}"
        )

    click.echo(click.style("-" * 70, fg="white"))
    click.echo()

    # Legend
    click.echo(
        click.style("Signals: ", bold=True)
        + "Latency=SSH | Traffic=State | Errors=SSH fails | Saturation=CPU/Mem/Disk"
    )
    click.echo(
        click.style("Thresholds: ", bold=True)
        + click.style("<70% ", fg="green")
        + click.style("70-90% ", fg="yellow")
        + click.style(">90%", fg="red")
    )


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", help="Check a single VM by name", type=str)
def health(
    resource_group: str | None,
    config: str | None,
    vm: str | None,
):
    """Show VM health dashboard with Four Golden Signals.

    Displays health status for all managed VMs including:
    power state, SSH reachability, error counts, and
    resource saturation (CPU, memory, disk).

    \b
    Four Golden Signals:
        Latency:    SSH connection reachability
        Traffic:    VM power state (running/stopped)
        Errors:     SSH connection failure count
        Saturation: CPU / Memory / Disk usage

    \b
    Examples:
        azlin health                 # All VMs in default resource group
        azlin health --rg my-rg      # Specific resource group
        azlin health --vm my-vm      # Single VM check
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Discover VMs using tag-based discovery
        vms, _was_cached = TagManager.list_managed_vms(resource_group=rg, use_cache=False)

        if not vms:
            click.echo("No VMs found in resource group.")
            return

        # Filter to single VM if requested
        if vm:
            vms = [v for v in vms if v.name == vm]
            if not vms:
                click.echo(f"VM '{vm}' not found in resource group.", err=True)
                sys.exit(1)

        click.echo(f"Checking health for {len(vms)} VM(s) in {rg}...")

        # Run health checks
        monitor = HealthMonitor(resource_group=rg)
        results: list[tuple[str, HealthStatus | None, str | None]] = []

        for v in vms:
            try:
                status = monitor.check_vm_health(v.name)
                results.append((v.name, status, None))
            except HealthCheckError as e:
                logger.debug(f"Health check failed for {v.name}: {e}")
                results.append((v.name, None, str(e)))
            except Exception as e:
                logger.debug(f"Unexpected error checking {v.name}: {e}", exc_info=True)
                results.append((v.name, None, f"Unexpected: {e}"))

        # Display results
        _render_health_table(results)

    except KeyboardInterrupt:
        click.echo("\nHealth check cancelled.")
        sys.exit(0)
    except Exception as e:
        logger.debug(f"Unexpected error in health command: {e}", exc_info=True)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
