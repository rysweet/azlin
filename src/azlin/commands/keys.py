"""SSH key management and rotation commands.

This module provides commands for rotating, listing, exporting, and backing up
SSH keys across Azure VMs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from azlin.config import ConfigManager
from azlin.key_rotator import KeyRotationError, SSHKeyRotator
from azlin.logging_config import get_logger

logger = get_logger()

__all__ = ["keys_group"]


@click.group(name="keys")
def keys_group():
    """SSH key management and rotation.

    Manage SSH keys across Azure VMs with rotation, backup, and export functionality.
    """
    pass


@keys_group.command(name="rotate")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all-vms", is_flag=True, help="Rotate keys for all VMs (not just azlin prefix)")
@click.option("--no-backup", is_flag=True, help="Skip backup before rotation")
@click.option("--vm-prefix", default="azlin", help="Only update VMs with this prefix")
def keys_rotate(
    resource_group: str | None, config: str | None, all_vms: bool, no_backup: bool, vm_prefix: str
):
    """Rotate SSH keys for all VMs in resource group.

    Generates a new SSH key pair and updates all VMs to use the new key.
    Automatically backs up old keys before rotation for safety.

    \b
    Examples:
        azlin keys rotate
        azlin keys rotate --rg my-resource-group
        azlin keys rotate --all-vms
        azlin keys rotate --no-backup
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Determine VM prefix
        prefix = "" if all_vms else vm_prefix

        click.echo(f"Rotating SSH keys for VMs in resource group: {rg}")
        if prefix:
            click.echo(f"Only updating VMs with prefix: {prefix}")
        click.echo()

        # Confirm
        confirm = input("Continue with key rotation? [y/N]: ").lower()
        if confirm not in ["y", "yes"]:
            click.echo("Cancelled.")
            return

        # Rotate keys
        result = SSHKeyRotator.rotate_keys(
            resource_group=rg, create_backup=not no_backup, enable_rollback=True, vm_prefix=prefix
        )

        # Display results
        click.echo()
        if result.success:
            click.echo(f"Success! {result.message}")
            if result.new_key_path:
                click.echo(f"New key: {result.new_key_path}")
            if result.backup_path:
                click.echo(f"Backup: {result.backup_path}")
            if result.vms_updated:
                click.echo(f"\nUpdated VMs ({len(result.vms_updated)}):")
                for vm in result.vms_updated:
                    click.echo(f"  - {vm}")
            sys.exit(0)
        else:
            click.echo(f"Failed: {result.message}", err=True)
            if result.vms_failed:
                click.echo(f"\nFailed VMs ({len(result.vms_failed)}):")
                for vm in result.vms_failed:
                    click.echo(f"  - {vm}")
            sys.exit(1)

    except KeyRotationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@keys_group.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all-vms", is_flag=True, help="List all VMs (not just azlin prefix)")
@click.option("--vm-prefix", default="azlin", help="Only list VMs with this prefix")
def keys_list(resource_group: str | None, config: str | None, all_vms: bool, vm_prefix: str):
    """List VMs and their SSH public keys.

    Shows which SSH public key is configured on each VM.

    \b
    Examples:
        azlin keys list
        azlin keys list --rg my-resource-group
        azlin keys list --all-vms
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Determine VM prefix
        prefix = "" if all_vms else vm_prefix

        click.echo(f"Listing SSH keys for VMs in resource group: {rg}\n")

        # List VM keys
        vm_keys = SSHKeyRotator.list_vm_keys(resource_group=rg, vm_prefix=prefix)

        if not vm_keys:
            click.echo("No VMs found.")
            return

        # Display table
        click.echo("=" * 100)
        click.echo(f"{'VM NAME':<35} {'PUBLIC KEY (first 50 chars)':<65}")
        click.echo("=" * 100)

        for vm_key in vm_keys:
            key_display = vm_key.public_key[:50] + "..." if vm_key.public_key else "N/A"
            click.echo(f"{vm_key.vm_name:<35} {key_display:<65}")

        click.echo("=" * 100)
        click.echo(f"\nTotal: {len(vm_keys)} VMs")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.exception("Unexpected error in keys list")
        sys.exit(1)


@keys_group.command(name="export")
@click.option("--output", help="Output file path", type=click.Path(), required=True)
def keys_export(output: str):
    """Export current SSH public key to file.

    Exports the azlin SSH public key to a specified file.

    \b
    Examples:
        azlin keys export --output ~/my-keys/azlin.pub
        azlin keys export --output ./keys.txt
    """
    try:
        output_path = Path(output).expanduser().resolve()

        click.echo(f"Exporting public key to: {output_path}")

        success = SSHKeyRotator.export_public_key(output_file=output_path)

        if success:
            click.echo(f"\nSuccess! Public key exported to: {output_path}")
        else:
            click.echo("\nFailed to export public key", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.exception("Unexpected error in keys export")
        sys.exit(1)


@keys_group.command(name="backup")
@click.option(
    "--destination", help="Backup destination (default: ~/.azlin/key_backups/)", type=click.Path()
)
def keys_backup(destination: str | None):
    """Backup current SSH keys.

    Creates a timestamped backup of current SSH keys.

    \b
    Examples:
        azlin keys backup
        azlin keys backup --destination ~/backups/
    """
    try:
        click.echo("Backing up SSH keys...")

        backup = SSHKeyRotator.backup_keys()

        click.echo("\nSuccess! Keys backed up to:")
        click.echo(f"  Directory: {backup.backup_dir}")
        click.echo(f"  Timestamp: {backup.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo(f"  Private key: {backup.old_private_key}")
        click.echo(f"  Public key: {backup.old_public_key}")

    except KeyRotationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in keys backup")

        sys.exit(1)
