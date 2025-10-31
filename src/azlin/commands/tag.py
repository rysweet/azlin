"""Tag management CLI commands for Azure VMs.

This module provides commands for managing VM tags:
- Add tags to VMs
- Remove tags from VMs
- List VM tags
"""

import logging
import sys

import click

from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager
from azlin.tag_manager import TagManager, TagManagerError
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)


@click.group(name="tag", cls=AzlinGroup)
def tag_group():
    """Manage Azure VM tags.

    Add, remove, and list tags on Azure VMs. Tags help organize
    and categorize VMs for easier management and cost tracking.

    \b
    COMMANDS:
        add        Add tags to a VM
        remove     Remove tags from a VM
        list       List VM tags

    \b
    EXAMPLES:
        # Add single tag
        $ azlin tag add my-vm environment=production

        # Add multiple tags
        $ azlin tag add my-vm project=web team=backend

        # List VM tags
        $ azlin tag list my-vm

        # Remove tags
        $ azlin tag remove my-vm environment project
    """
    pass


@tag_group.command(name="add")
@click.argument("vm_name", type=str)
@click.argument("tags", nargs=-1, required=True)
@click.option("--resource-group", "--rg", help="Azure resource group")
def add_tags(vm_name: str, tags: tuple[str, ...], resource_group: str | None):
    """Add tags to a VM.

    Adds one or more tags to the specified VM. Tags must be in
    key=value format.

    \b
    VM_NAME is the name of the VM to tag.
    TAGS are one or more key=value pairs to add.

    \b
    Tag format:
      - Keys: alphanumeric, underscore, hyphen, period
      - Values: any characters including spaces (quote if needed)

    \b
    Examples:
      $ azlin tag add my-vm environment=production
      $ azlin tag add my-vm project=web team=backend cost-center=eng
      $ azlin tag add my-vm description="Web server for API"
    """
    try:
        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo(
                "Error: Resource group required. Use --resource-group or set in config.", err=True
            )
            sys.exit(1)

        # Verify VM exists
        try:
            vm = VMManager.get_vm(vm_name, rg)
            if not vm:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'", err=True)
                sys.exit(1)
        except VMManagerError as e:
            click.echo(f"Error: Failed to get VM '{vm_name}': {e}", err=True)
            sys.exit(1)

        # Parse tags
        tag_dict = {}
        try:
            for tag in tags:
                key, value = TagManager.parse_tag_assignment(tag)
                tag_dict[key] = value
        except TagManagerError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Add tags
        click.echo(f"Adding tags to VM '{vm_name}'...")
        for key, value in tag_dict.items():
            click.echo(f"  {key}={value}")

        try:
            TagManager.add_tags(vm_name, rg, tag_dict)
            click.echo(f"\n✓ Successfully added {len(tag_dict)} tag(s) to VM '{vm_name}'")
        except TagManagerError as e:
            click.echo(f"\nError: Failed to add tags: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tag_group.command(name="remove")
@click.argument("vm_name", type=str)
@click.argument("tag_keys", nargs=-1, required=True)
@click.option("--resource-group", "--rg", help="Azure resource group")
def remove_tags(vm_name: str, tag_keys: tuple[str, ...], resource_group: str | None):
    """Remove tags from a VM.

    Removes one or more tags from the specified VM by tag key.

    \b
    VM_NAME is the name of the VM.
    TAG_KEYS are one or more tag keys to remove.

    \b
    Examples:
      $ azlin tag remove my-vm environment
      $ azlin tag remove my-vm project team cost-center
    """
    try:
        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo(
                "Error: Resource group required. Use --resource-group or set in config.", err=True
            )
            sys.exit(1)

        # Verify VM exists
        try:
            vm = VMManager.get_vm(vm_name, rg)
            if not vm:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'", err=True)
                sys.exit(1)
        except VMManagerError as e:
            click.echo(f"Error: Failed to get VM '{vm_name}': {e}", err=True)
            sys.exit(1)

        # Remove tags
        click.echo(f"Removing tags from VM '{vm_name}'...")
        for key in tag_keys:
            click.echo(f"  {key}")

        try:
            TagManager.remove_tags(vm_name, rg, list(tag_keys))
            click.echo(f"\n✓ Successfully removed {len(tag_keys)} tag(s) from VM '{vm_name}'")
        except TagManagerError as e:
            click.echo(f"\nError: Failed to remove tags: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tag_group.command(name="list")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group")
def list_tags(vm_name: str, resource_group: str | None):
    """List all tags on a VM.

    Shows all tags currently set on the specified VM with their
    key-value pairs.

    \b
    VM_NAME is the name of the VM.

    \b
    Examples:
      $ azlin tag list my-vm
      $ azlin tag list my-vm --resource-group azlin-rg
    """
    try:
        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo(
                "Error: Resource group required. Use --resource-group or set in config.", err=True
            )
            sys.exit(1)

        # Verify VM exists
        try:
            vm = VMManager.get_vm(vm_name, rg)
            if not vm:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'", err=True)
                sys.exit(1)
        except VMManagerError as e:
            click.echo(f"Error: Failed to get VM '{vm_name}': {e}", err=True)
            sys.exit(1)

        # Get tags
        try:
            tags = TagManager.get_tags(vm_name, rg)

            if not tags:
                click.echo(f"\nVM '{vm_name}' has no tags")
                return

            click.echo(f"\nTags for VM '{vm_name}':")
            click.echo("=" * 80)

            # Sort tags by key for consistent output
            for key in sorted(tags.keys()):
                click.echo(f"  {key}={tags[key]}")

            click.echo(f"\nTotal: {len(tags)} tag(s)")

        except TagManagerError as e:
            click.echo(f"\nError: Failed to get tags: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


__all__ = ["tag_group"]
