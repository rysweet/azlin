"""Shared helper functions for CLI commands.

This module contains utility functions used across multiple CLI commands,
extracted from cli.py as part of Issue #423 decomposition.

Functions in this module should be:
- Pure or side-effect minimal
- Reusable across multiple commands
- Well-tested
- Clearly documented
"""

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from azlin.config_manager import ConfigManager
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.vm_manager import VMInfo, VMManager

logger = logging.getLogger(__name__)


def generate_vm_name(custom_name: str | None = None, command: str | None = None) -> str:
    """Generate a VM name based on custom name or timestamp.

    Args:
        custom_name: Optional custom name for the VM
        command: Optional command being executed (for naming context)

    Returns:
        str: Generated VM name following Azure naming conventions

    Examples:
        >>> generate_vm_name(custom_name="my-vm")
        'my-vm'
        >>> generate_vm_name()  # doctest: +SKIP
        'azlin-vm-1702485600'
    """
    if custom_name:
        return custom_name

    timestamp = int(time.time())
    return f"azlin-vm-{timestamp}"


def select_vm_for_command(vms: list[VMInfo], command: str) -> VMInfo | None:
    """Select a VM for command execution based on available VMs.

    Interactive selection if multiple VMs available.

    Args:
        vms: List of available VMs
        command: Command to execute (for display purposes)

    Returns:
        VMInfo | None: Selected VM or None if cancelled/no VMs
    """
    if not vms:
        click.echo("No running VMs found.", err=True)
        return None

    if len(vms) == 1:
        return vms[0]

    # Multiple VMs - show selection menu
    console = Console()
    console.print(f"\n[bold]Select VM to execute: {command}[/bold]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("VM Name", style="cyan")
    table.add_column("Region", style="green")
    table.add_column("IP Address", style="yellow")
    table.add_column("Size", style="magenta")

    for idx, vm in enumerate(vms, 1):
        table.add_row(
            str(idx),
            vm.name,
            vm.location or "unknown",
            vm.public_ip or vm.private_ip or "no-ip",
            vm.size or "unknown",
        )

    console.print(table)
    console.print()

    # Get selection
    while True:
        try:
            selection = click.prompt(
                "Enter VM number (or 'q' to quit)",
                type=str,
                default="1",
            )

            if selection.lower() == 'q':
                return None

            idx = int(selection) - 1
            if 0 <= idx < len(vms):
                return vms[idx]
            else:
                click.echo(f"Invalid selection. Please enter 1-{len(vms)}", err=True)
        except (ValueError, KeyboardInterrupt):
            click.echo("\nSelection cancelled", err=True)
            return None


def execute_command_on_vm(vm: VMInfo, command: str, ssh_key_path: Path) -> int:
    """Execute a command on a VM via SSH.

    Args:
        vm: VM to execute command on
        command: Shell command to execute
        ssh_key_path: Path to SSH private key

    Returns:
        int: Exit code from command execution
    """
    if not vm.public_ip and not vm.private_ip:
        click.echo(f"Error: VM {vm.name} has no IP address", err=True)
        return 1

    ip_address = vm.public_ip or vm.private_ip
    assert ip_address is not None

    # Build SSH command
    ssh_cmd = [
        "ssh",
        "-i", str(ssh_key_path),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        f"azureuser@{ip_address}",
        command,
    ]

    try:
        result = subprocess.run(ssh_cmd, check=False)
        return result.returncode
    except Exception as e:
        click.echo(f"Error executing command: {e}", err=True)
        return 1


def show_interactive_menu(vms: list[VMInfo], ssh_key_path: Path) -> int | None:
    """Show interactive menu for VM selection and connection.

    Args:
        vms: List of available VMs
        ssh_key_path: Path to SSH private key

    Returns:
        int | None: Exit code or None if no action taken
    """
    if not vms:
        click.echo("No VMs available for selection.", err=True)
        return 1

    # Display VM menu
    console = Console()
    console.print("\n[bold cyan]Available VMs:[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("VM Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Region", style="green")
    table.add_column("IP Address", style="yellow")
    table.add_column("Size", style="magenta")

    for idx, vm in enumerate(vms, 1):
        status = "Running" if vm.is_running() else "Stopped"
        status_style = "green" if vm.is_running() else "red"

        table.add_row(
            str(idx),
            vm.name,
            f"[{status_style}]{status}[/{status_style}]",
            vm.location or "unknown",
            vm.public_ip or vm.private_ip or "no-ip",
            vm.size or "unknown",
        )

    console.print(table)
    console.print()

    # Get selection
    while True:
        try:
            selection = click.prompt(
                "Select VM to connect (or 'q' to quit)",
                type=str,
                default="1",
            )

            if selection.lower() == 'q':
                return None

            idx = int(selection) - 1
            if 0 <= idx < len(vms):
                selected_vm = vms[idx]

                if not selected_vm.is_running():
                    click.echo(f"VM {selected_vm.name} is not running", err=True)
                    start = click.confirm("Start the VM?", default=True)
                    if start:
                        # Import here to avoid circular dependency
                        from azlin.vm_lifecycle import VMLifecycleManager

                        VMLifecycleManager.start_vm(selected_vm.name, selected_vm.resource_group)
                        click.echo("VM started. Waiting for SSH...")
                        time.sleep(10)  # Give VM time to boot
                    else:
                        continue

                # Connect to VM
                ip_address = selected_vm.public_ip or selected_vm.private_ip
                if not ip_address:
                    click.echo(f"Error: VM {selected_vm.name} has no IP address", err=True)
                    continue

                click.echo(f"Connecting to {selected_vm.name} ({ip_address})...")

                ssh_cmd = [
                    "ssh",
                    "-i", str(ssh_key_path),
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    f"azureuser@{ip_address}",
                ]

                result = subprocess.run(ssh_cmd, check=False)
                return result.returncode
            else:
                click.echo(f"Invalid selection. Please enter 1-{len(vms)}", err=True)

        except (ValueError, KeyboardInterrupt):
            click.echo("\nSelection cancelled", err=True)
            return None


def load_config_and_resolve_rg(
    resource_group: str | None,
    config: str | None,
) -> str | None:
    """Load configuration and resolve resource group.

    Args:
        resource_group: Explicit resource group (takes precedence)
        config: Path to config file

    Returns:
        str | None: Resolved resource group name or None if not found
    """
    return ConfigManager.get_resource_group(resource_group, config)


def ensure_vm_is_running(vm: VMInfo) -> bool:
    """Check if VM is running, offer to start if not.

    Args:
        vm: VM to check

    Returns:
        bool: True if VM is running (or was started), False otherwise
    """
    if vm.is_running():
        return True

    click.echo(f"VM {vm.name} is not running (current state: {vm.power_state})", err=True)
    start = click.confirm("Start the VM?", default=True)

    if not start:
        return False

    # Import here to avoid circular dependency
    from azlin.vm_lifecycle import VMLifecycleManager

    try:
        VMLifecycleManager.start_vm(vm.name, vm.resource_group)
        click.echo("VM started successfully")
        return True
    except Exception as e:
        click.echo(f"Failed to start VM: {e}", err=True)
        return False


# NOTE: More helper functions will be added here as we extract commands
# Each function should be documented and focused on a single responsibility
