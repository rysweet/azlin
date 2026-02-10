"""Environment variable management commands.

This module provides commands for setting, listing, deleting, importing,
exporting, and clearing environment variables on remote VMs.
"""

from __future__ import annotations

import sys

import click

from azlin.config_manager import ConfigManager
from azlin.env_manager import EnvManager, EnvManagerError
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMManager

__all__ = ["_get_ssh_config_for_vm", "env"]


@click.group(name="env")
def env():
    """Manage environment variables on VMs.

    Commands to set, list, delete, and export environment variables
    stored in ~/.bashrc on remote VMs.

    \b
    Examples:
        azlin env set my-vm DATABASE_URL="postgres://localhost/db"
        azlin env list my-vm
        azlin env delete my-vm API_KEY
        azlin env export my-vm prod.env
    """
    pass


@env.command(name="set")
@click.argument("vm_identifier", type=str)
@click.argument("env_var", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip secret detection warnings")
def env_set(
    vm_identifier: str, env_var: str, resource_group: str | None, config: str | None, force: bool
):
    """Set environment variable on VM.

    ENV_VAR should be in format KEY=VALUE.

    \b
    Examples:
        azlin env set my-vm DATABASE_URL="postgres://localhost/db"
        azlin env set my-vm API_KEY=secret123 --force
        azlin env set 20.1.2.3 NODE_ENV=production
    """
    try:
        # Parse KEY=VALUE
        if "=" not in env_var:
            click.echo("Error: ENV_VAR must be in format KEY=VALUE", err=True)
            sys.exit(1)

        key, value = env_var.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Remove quotes if present
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Detect secrets and warn
        if not force:
            warnings = EnvManager.detect_secrets(value)
            if warnings:
                click.echo("WARNING: Potential secret detected!", err=True)
                for warning in warnings:
                    click.echo(f"  - {warning}", err=True)
                click.echo("\nAre you sure you want to set this value? [y/N]: ", nl=False)
                response = input().lower()
                if response not in ["y", "yes"]:
                    click.echo("Cancelled.")
                    return

        # Set the variable
        EnvManager.set_env_var(ssh_config, key, value)

        click.echo(f"Set {key} on {vm_identifier}")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="list")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--show-values", is_flag=True, help="Show full values (default: masked)")
def env_list(vm_identifier: str, resource_group: str | None, config: str | None, show_values: bool):
    """List environment variables on VM.

    \b
    Examples:
        azlin env list my-vm
        azlin env list my-vm --show-values
        azlin env list 20.1.2.3
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # List variables
        env_vars = EnvManager.list_env_vars(ssh_config)

        if not env_vars:
            click.echo(f"No environment variables set on {vm_identifier}")
            return

        click.echo(f"\nEnvironment variables on {vm_identifier}:")
        click.echo("=" * 80)

        for key, value in sorted(env_vars.items()):
            if show_values:
                click.echo(f"  {key}={value}")
            else:
                # Mask values that might be secrets
                warnings = EnvManager.detect_secrets(value)
                if warnings or len(value) > 20:
                    masked = "***" if warnings else value[:20] + "..."
                    click.echo(f"  {key}={masked}")
                else:
                    click.echo(f"  {key}={value}")

        click.echo("=" * 80)
        click.echo(f"\nTotal: {len(env_vars)} variables")
        if not show_values:
            click.echo("Use --show-values to display full values\n")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="delete")
@click.argument("vm_identifier", type=str)
@click.argument("key", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def env_delete(vm_identifier: str, key: str, resource_group: str | None, config: str | None):
    """Delete environment variable from VM.

    \b
    Examples:
        azlin env delete my-vm API_KEY
        azlin env delete 20.1.2.3 DATABASE_URL
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Delete the variable
        result = EnvManager.delete_env_var(ssh_config, key)

        if result:
            click.echo(f"Deleted {key} from {vm_identifier}")
        else:
            click.echo(f"Variable {key} not found on {vm_identifier}", err=True)
            sys.exit(1)

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="export")
@click.argument("vm_identifier", type=str)
@click.argument("output_file", type=str, required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def env_export(
    vm_identifier: str, output_file: str | None, resource_group: str | None, config: str | None
):
    """Export environment variables to .env file format.

    \b
    Examples:
        azlin env export my-vm prod.env
        azlin env export my-vm  # Print to stdout
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Export variables
        result = EnvManager.export_env_vars(ssh_config, output_file)

        if output_file:
            click.echo(f"Exported environment variables to {output_file}")
        else:
            click.echo(result)

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="import")
@click.argument("vm_identifier", type=str)
@click.argument("env_file", type=click.Path(exists=True))
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def env_import(vm_identifier: str, env_file: str, resource_group: str | None, config: str | None):
    """Import environment variables from .env file.

    \b
    Examples:
        azlin env import my-vm .env
        azlin env import my-vm prod.env
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Import variables
        count = EnvManager.import_env_file(ssh_config, env_file)

        click.echo(f"Imported {count} variables to {vm_identifier}")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="clear")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def env_clear(vm_identifier: str, resource_group: str | None, config: str | None, force: bool):
    """Clear all environment variables from VM.

    \b
    Examples:
        azlin env clear my-vm
        azlin env clear my-vm --force
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Confirm unless --force
        if not force:
            env_vars = EnvManager.list_env_vars(ssh_config)
            if not env_vars:
                click.echo(f"No environment variables set on {vm_identifier}")
                return

            click.echo(
                f"This will delete {len(env_vars)} environment variable(s) from {vm_identifier}"
            )
            click.echo("Are you sure? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Clear all variables
        EnvManager.clear_all_env_vars(ssh_config)

        click.echo(f"Cleared all environment variables from {vm_identifier}")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


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
