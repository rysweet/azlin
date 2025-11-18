"""Bastion management CLI commands for Azure Bastion.

This module provides commands for managing Azure Bastion hosts:
- List Bastion hosts
- Check Bastion status
- Configure Bastion connections
"""

import logging
import sys

import click
from rich.console import Console

from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.modules.bastion_config import BastionConfig, BastionConfigError
from azlin.modules.bastion_detector import BastionDetector, BastionDetectorError

logger = logging.getLogger(__name__)


@click.group(name="bastion", cls=AzlinGroup)
def bastion_group():
    """Manage Azure Bastion hosts for secure VM connections.

    Azure Bastion provides secure RDP/SSH connectivity to VMs
    without exposing public IPs. These commands help you list,
    configure, and use Bastion hosts with azlin.

    \b
    COMMANDS:
        list         List Bastion hosts
        status       Show Bastion host status
        configure    Configure Bastion for a VM

    \b
    EXAMPLES:
        # List all Bastion hosts
        $ azlin bastion list

        # List Bastion hosts in a resource group
        $ azlin bastion list --resource-group my-rg

        # Check status of a specific Bastion
        $ azlin bastion status my-bastion --resource-group my-rg

        # Configure VM to use Bastion
        $ azlin bastion configure my-vm --bastion-name my-bastion --resource-group my-rg
    """
    pass


@bastion_group.command(name="list")
@click.option("--resource-group", "--rg", help="Filter by resource group")
def list_bastions(resource_group: str | None):
    """List Azure Bastion hosts.

    Lists all Bastion hosts in your subscription, optionally
    filtered by resource group.

    \b
    Examples:
      $ azlin bastion list
      $ azlin bastion list --resource-group my-rg
    """
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        click.echo("Listing Bastion hosts...")

        bastions = BastionDetector.list_bastions(resource_group)

        if not bastions:
            if resource_group:
                click.echo(f"No Bastion hosts found in resource group: {resource_group}")
            else:
                click.echo("No Bastion hosts found in subscription")
            return

        click.echo(f"\nFound {len(bastions)} Bastion host(s):\n")

        for bastion in bastions:
            name = bastion.get("name", "unknown")
            rg = bastion.get("resourceGroup", "unknown")
            location = bastion.get("location", "unknown")
            sku = bastion.get("sku", {}).get("name", "Standard")
            provisioning_state = bastion.get("provisioningState", "unknown")

            click.echo(f"  {name}")
            click.echo(f"    Resource Group: {rg}")
            click.echo(f"    Location: {location}")
            click.echo(f"    SKU: {sku}")
            click.echo(f"    State: {provisioning_state}")
            click.echo()

    except BastionDetectorError as e:
        click.echo(f"Error listing Bastion hosts: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Failed to list Bastion hosts")
        sys.exit(1)


@bastion_group.command(name="status")
@click.argument("name", type=str)
@click.option("--resource-group", "--rg", required=True, help="Resource group")
def bastion_status(name: str, resource_group: str):
    """Show status of a Bastion host.

    \b
    Arguments:
      NAME    Bastion host name

    \b
    Examples:
      $ azlin bastion status my-bastion --resource-group my-rg
    """
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        click.echo(f"Checking Bastion host: {name}...")

        bastion = BastionDetector.get_bastion(name, resource_group)

        if not bastion:
            click.echo(f"Bastion host not found: {name} in {resource_group}", err=True)
            sys.exit(1)

        # Display details
        click.echo(f"\nBastion Host: {bastion.get('name')}")
        click.echo(f"Resource Group: {bastion.get('resourceGroup')}")
        click.echo(f"Location: {bastion.get('location')}")
        click.echo(f"SKU: {bastion.get('sku', {}).get('name', 'Standard')}")
        click.echo(f"Provisioning State: {bastion.get('provisioningState', 'Unknown')}")

        # DNS name
        dns_name = bastion.get("dnsName", "N/A")
        click.echo(f"DNS Name: {dns_name}")

        # IP Configuration
        ip_configs = bastion.get("ipConfigurations", [])
        if ip_configs:
            click.echo(f"\nIP Configurations: {len(ip_configs)}")
            for idx, config in enumerate(ip_configs):
                subnet_id = config.get("subnet", {}).get("id", "N/A")
                public_ip_id = config.get("publicIPAddress", {}).get("id", "N/A")
                click.echo(
                    f"  [{idx + 1}] Subnet: {subnet_id.split('/')[-1] if subnet_id != 'N/A' else 'N/A'}"
                )
                click.echo(
                    f"      Public IP: {public_ip_id.split('/')[-1] if public_ip_id != 'N/A' else 'N/A'}"
                )

    except BastionDetectorError as e:
        click.echo(f"Error getting Bastion status: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Failed to get Bastion status")
        sys.exit(1)


@bastion_group.command(name="configure")
@click.argument("vm_name", type=str)
@click.option("--bastion-name", required=True, help="Bastion host name")
@click.option("--resource-group", "--rg", help="VM resource group")
@click.option(
    "--bastion-resource-group", "--bastion-rg", help="Bastion resource group (defaults to VM RG)"
)
@click.option("--enable/--disable", default=True, help="Enable or disable mapping")
def configure_bastion(
    vm_name: str,
    bastion_name: str,
    resource_group: str | None,
    bastion_resource_group: str | None,
    enable: bool,
):
    """Configure Bastion connection for a VM.

    Creates a mapping between a VM and a Bastion host, so azlin
    will automatically use the Bastion when connecting to the VM.

    \b
    Arguments:
      VM_NAME    VM name to configure

    \b
    Examples:
      $ azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg
      $ azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --bastion-rg bastion-rg
      $ azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --disable
    """
    try:
        # Get resource group
        try:
            config = ConfigManager.load_config()
            vm_rg = resource_group or config.default_resource_group
        except ConfigError:
            vm_rg = resource_group

        if not vm_rg:
            click.echo(
                "Resource group required. Set default with:\n"
                "  azlin config set default_resource_group <name>\n"
                "Or specify with --resource-group option.",
                err=True,
            )
            sys.exit(1)

        bastion_rg = bastion_resource_group or vm_rg

        # Load Bastion config
        config_path = ConfigManager.DEFAULT_CONFIG_DIR / "bastion_config.toml"
        bastion_config = BastionConfig.load(config_path)

        if enable:
            # Add mapping
            bastion_config.add_mapping(
                vm_name=vm_name,
                vm_resource_group=vm_rg,
                bastion_name=bastion_name,
                bastion_resource_group=bastion_rg,
            )

            # Save config
            bastion_config.save(config_path)

            click.echo(f"✓ Configured {vm_name} to use Bastion: {bastion_name}")
            click.echo(f"  VM RG: {vm_rg}")
            click.echo(f"  Bastion RG: {bastion_rg}")
            click.echo("\nConnection will now route through Bastion automatically.")

        else:
            # Disable mapping
            bastion_config.disable_mapping(vm_name)
            bastion_config.save(config_path)

            click.echo(f"✓ Disabled Bastion mapping for: {vm_name}")

    except BastionConfigError as e:
        click.echo(f"Error configuring Bastion: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Failed to configure Bastion")
        sys.exit(1)


__all__ = ["bastion_group"]
