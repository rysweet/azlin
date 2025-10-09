"""CLI entry point for azlin v2.0.

This module provides the enhanced command-line interface with:
- Config storage and resource group management
- VM listing and status
- Interactive session selection
- Parallel VM provisioning (pools)
- Remote command execution
- Enhanced help

Commands:
    azlin                    # Interactive menu or provision new VM
    azlin list               # List VMs in resource group
    azlin w                  # Run 'w' command on all VMs
    azlin -- <command>       # Execute command on VM(s)
"""

import sys
import os
import logging
import time
import click
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from azlin import __version__
from azlin.azure_auth import AzureAuthenticator, AuthenticationError
from azlin.vm_provisioning import VMProvisioner, VMConfig, VMDetails, ProvisioningError
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError
from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyError
from azlin.modules.ssh_connector import SSHConnector, SSHConfig, SSHConnectionError
from azlin.modules.github_setup import GitHubSetupHandler, GitHubSetupError
from azlin.modules.progress import ProgressDisplay, ProgressStage
from azlin.modules.notifications import NotificationHandler

# New modules for v2.0
from azlin.config_manager import ConfigManager, AzlinConfig, ConfigError
from azlin.vm_manager import VMManager, VMInfo, VMManagerError
from azlin.remote_exec import RemoteExecutor, WCommandExecutor, RemoteExecError
from azlin.terminal_launcher import TerminalLauncher, TerminalConfig

logger = logging.getLogger(__name__)


class AzlinError(Exception):
    """Base exception for azlin errors."""
    exit_code = 1


def show_interactive_menu(
    vms: List[VMInfo],
    ssh_key_path: Path
) -> Optional[int]:
    """Show interactive VM selection menu.

    Args:
        vms: List of available VMs
        ssh_key_path: Path to SSH private key

    Returns:
        Exit code or None to continue
    """
    if not vms:
        click.echo("No VMs found. Create a new one? [Y/n]: ", nl=False)
        response = input().lower()
        if response in ['', 'y', 'yes']:
            return None  # Continue to provisioning
        return 0

    # Auto-connect if only 1 VM
    if len(vms) == 1:
        vm = vms[0]
        click.echo(f"\nFound 1 VM: {vm.name}")
        click.echo(f"Status: {vm.get_status_display()}")
        click.echo(f"IP: {vm.public_ip}")
        click.echo("\nConnecting...")

        if vm.is_running() and vm.public_ip:
            ssh_config = SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_path
            )
            exit_code = SSHConnector.connect(
                ssh_config,
                tmux_session="azlin",
                auto_tmux=True
            )
            return exit_code
        else:
            click.echo("VM is not running or has no public IP")
            return 1

    # Multiple VMs - show menu
    click.echo("\n" + "=" * 60)
    click.echo("Available VMs:")
    click.echo("=" * 60)

    for idx, vm in enumerate(vms, 1):
        status = vm.get_status_display()
        ip = vm.public_ip or "No IP"
        click.echo(f"  {idx}. {vm.name} - {status} - {ip}")

    click.echo(f"  n. Create new VM")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == 'n':
        return None  # Continue to provisioning

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            vm = vms[idx]

            if not vm.is_running():
                click.echo(f"\nVM '{vm.name}' is not running.")
                click.echo("Start it with: az vm start --name {} --resource-group {}".format(
                    vm.name, vm.resource_group
                ))
                return 1

            if not vm.public_ip:
                click.echo(f"\nVM '{vm.name}' has no public IP.")
                return 1

            click.echo(f"\nConnecting to {vm.name}...")
            ssh_config = SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_path
            )
            exit_code = SSHConnector.connect(
                ssh_config,
                tmux_session="azlin",
                auto_tmux=True
            )
            return exit_code
        else:
            click.echo("Invalid selection")
            return 1
    except ValueError:
        click.echo("Invalid input")
        return 1


def generate_vm_name(
    custom_name: Optional[str] = None,
    command: Optional[str] = None
) -> str:
    """Generate VM name.

    Args:
        custom_name: Custom name from --name flag
        command: Command string for slug extraction

    Returns:
        VM name
    """
    if custom_name:
        return custom_name

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if command:
        slug = RemoteExecutor.extract_command_slug(command)
        return f"azlin-{timestamp}-{slug}"

    return f"azlin-{timestamp}"


@click.group(invoke_without_command=True)
@click.pass_context
@click.option('--repo', help='GitHub repository URL to clone', type=str)
@click.option('--vm-size', help='Azure VM size', type=str)
@click.option('--region', help='Azure region', type=str)
@click.option('--resource-group', '--rg', help='Azure resource group', type=str)
@click.option('--name', help='Custom VM name', type=str)
@click.option('--pool', help='Number of VMs to create in parallel', type=int)
@click.option('--no-auto-connect', help='Do not auto-connect via SSH', is_flag=True)
@click.option('--config', help='Config file path', type=click.Path())
@click.version_option(version=__version__)
def cli(
    ctx,
    repo: Optional[str],
    vm_size: Optional[str],
    region: Optional[str],
    resource_group: Optional[str],
    name: Optional[str],
    pool: Optional[int],
    no_auto_connect: bool,
    config: Optional[str]
):
    """azlin - Azure Ubuntu VM provisioning and management.

    Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
    and executes commands remotely.

    \b
    Examples:
        # Interactive menu (if VMs exist) or provision new VM
        azlin

        # List VMs in resource group
        azlin list

        # Run 'w' on all VMs
        azlin w

        # Provision VM with custom name
        azlin --name my-dev-vm

        # Provision 5 VMs in parallel
        azlin --pool 5

        # Execute command on VM
        azlin -- python train.py

        # Provision VM and clone repo
        azlin --repo https://github.com/owner/repo

    For detailed help on any command, use: azlin <command> --help
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

    # If no subcommand and no explicit provision flags, check for interactive mode
    if ctx.invoked_subcommand is None:
        # Check for command after --
        has_command = '--' in sys.argv

        # If no special args, try interactive mode
        if not any([repo, pool, name, has_command]):
            try:
                # Load config to get resource group
                azlin_config = ConfigManager.load_config(config)
                rg = resource_group or azlin_config.default_resource_group

                if rg:
                    # List VMs and show menu
                    ssh_key_pair = SSHKeyManager.ensure_key_exists()
                    vms = VMManager.list_vms(rg, include_stopped=False)
                    vms = VMManager.filter_by_prefix(vms, "azlin")
                    vms = VMManager.sort_by_created_time(vms)

                    if vms:
                        exit_code = show_interactive_menu(vms, ssh_key_pair.private_path)
                        if exit_code is not None:
                            sys.exit(exit_code)
                        # If None, continue to provisioning

            except Exception as e:
                logger.debug(f"Interactive mode failed: {e}")
                # Continue to provisioning

        # Continue to provision command
        ctx.invoke(provision, repo=repo, vm_size=vm_size, region=region,
                   resource_group=resource_group, name=name, pool=pool,
                   no_auto_connect=no_auto_connect, config=config)


@cli.command()
@click.option('--resource-group', '--rg', help='Resource group to list VMs from', type=str)
@click.option('--config', help='Config file path', type=click.Path())
@click.option('--all', 'show_all', help='Show all VMs (including stopped)', is_flag=True)
def list_vms(resource_group: Optional[str], config: Optional[str], show_all: bool):
    """List VMs in resource group.

    Shows VM name, status, IP address, region, and size.

    \b
    Examples:
        azlin list
        azlin list --rg my-resource-group
        azlin list --all
    """
    try:
        # Get resource group from config or CLI
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified and no default configured.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        click.echo(f"Listing VMs in resource group: {rg}\n")

        # List VMs
        vms = VMManager.list_vms(rg, include_stopped=show_all)

        # Filter to azlin VMs
        vms = VMManager.filter_by_prefix(vms, "azlin")
        vms = VMManager.sort_by_created_time(vms)

        if not vms:
            click.echo("No VMs found.")
            return

        # Display table
        click.echo("=" * 80)
        click.echo(f"{'NAME':<30} {'STATUS':<15} {'IP':<15} {'REGION':<15}")
        click.echo("=" * 80)

        for vm in vms:
            status = vm.get_status_display()
            ip = vm.public_ip or "N/A"
            click.echo(f"{vm.name:<30} {status:<15} {ip:<15} {vm.location:<15}")

        click.echo("=" * 80)
        click.echo(f"\nTotal: {len(vms)} VMs")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--config', help='Config file path', type=click.Path())
def w(resource_group: Optional[str], config: Optional[str]):
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

        if not vms:
            click.echo("No running VMs found.")
            return

        running_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

        if not running_vms:
            click.echo("No running VMs with public IPs found.")
            return

        click.echo(f"Running 'w' on {len(running_vms)} VMs...\n")

        # Build SSH configs
        ssh_configs = [
            SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_pair.private_path
            )
            for vm in running_vms
        ]

        # Execute in parallel
        results = WCommandExecutor.execute_w_on_vms(ssh_configs, timeout=30)

        # Display output
        output = WCommandExecutor.format_w_output(results)
        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--repo', help='GitHub repository URL', type=str)
@click.option('--vm-size', help='Azure VM size', type=str)
@click.option('--region', help='Azure region', type=str)
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--name', help='Custom VM name', type=str)
@click.option('--pool', help='Number of VMs in parallel', type=int)
@click.option('--no-auto-connect', help='Do not auto-connect', is_flag=True)
@click.option('--config', help='Config file path', type=click.Path())
def provision(
    repo: Optional[str],
    vm_size: Optional[str],
    region: Optional[str],
    resource_group: Optional[str],
    name: Optional[str],
    pool: Optional[int],
    no_auto_connect: bool,
    config: Optional[str]
):
    """Provision new Azure VM(s).

    \b
    Examples:
        azlin provision --name my-vm
        azlin provision --pool 3
        azlin provision --repo https://github.com/owner/repo
    """
    # Check for command after --
    command = None
    if '--' in sys.argv:
        delimiter_idx = sys.argv.index('--')
        command = ' '.join(sys.argv[delimiter_idx + 1:])

    # Load config
    try:
        azlin_config = ConfigManager.load_config(config)
    except ConfigError:
        azlin_config = AzlinConfig()

    # Get settings with CLI override
    final_rg = resource_group or azlin_config.default_resource_group
    final_region = region or azlin_config.default_region
    final_vm_size = vm_size or azlin_config.default_vm_size

    # Generate VM name
    vm_name = generate_vm_name(name, command)

    # Warn if pool > 10
    if pool and pool > 10:
        estimated_cost = pool * 0.10  # Rough estimate
        click.echo(f"\nWARNING: Creating {pool} VMs")
        click.echo(f"Estimated cost: ~${estimated_cost:.2f}/hour")
        click.echo("Continue? [y/N]: ", nl=False)
        response = input().lower()
        if response not in ['y', 'yes']:
            click.echo("Cancelled.")
            sys.exit(0)

    # Create orchestrator
    from azlin.cli import CLIOrchestrator

    orchestrator = CLIOrchestrator(
        repo=repo,
        vm_size=final_vm_size,
        region=final_region,
        resource_group=final_rg,
        auto_connect=not no_auto_connect,
        config_file=config
    )

    # Update config with used resource group
    if final_rg:
        try:
            ConfigManager.update_config(
                config,
                default_resource_group=final_rg,
                last_vm_name=vm_name
            )
        except ConfigError as e:
            logger.debug(f"Failed to update config: {e}")

    # Execute command if specified
    if command and not pool:
        click.echo(f"\nCommand: {command}")
        click.echo("Opening in new terminal window...\n")

        # Provision VM first
        exit_code = orchestrator.run()

        if exit_code == 0 and orchestrator.vm_details:
            # Launch terminal with command
            terminal_config = TerminalConfig(
                ssh_host=orchestrator.vm_details.public_ip,
                ssh_user="azureuser",
                ssh_key_path=orchestrator.ssh_keys,
                command=command,
                title=f"azlin - {command}"
            )
            TerminalLauncher.launch(terminal_config)

        sys.exit(exit_code)

    # Pool provisioning
    if pool and pool > 1:
        click.echo(f"\nProvisioning {pool} VMs in parallel...")
        click.echo("This feature requires additional implementation.")
        click.echo("For now, provision VMs one at a time.")
        sys.exit(1)

    # Standard single VM provisioning
    exit_code = orchestrator.run()
    sys.exit(exit_code)


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()


__all__ = ['cli', 'main']
