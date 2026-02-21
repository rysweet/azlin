"""SESSION command for azlin monitoring.

This module contains the 'session' command extracted from monitoring.py.
Part of Issue #423 - monitoring.py decomposition.

Command:
    - session: Set or view session name for a VM
"""

from __future__ import annotations

import logging
import sys

import click

from azlin.config_manager import ConfigError, ConfigManager
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)

__all__ = ["session_command"]


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
