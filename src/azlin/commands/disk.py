"""Disk management commands for azlin CLI.

This module provides commands for managing VM disks:
- disk add: Attach a new managed disk to an existing VM

Supports adding /tmp disks (or other mount points) to running VMs.
"""

from __future__ import annotations

import json
import logging
import sys

import click

from azlin.azure_cli_visibility import AzureCLIExecutor
from azlin.config_manager import ConfigError, ConfigManager

logger = logging.getLogger(__name__)

# Default mount point for the disk add command
_DEFAULT_MOUNT = "/tmp"  # noqa: S108


@click.group(name="disk")
def disk_group():
    """Manage VM disks."""
    pass


@disk_group.command(name="add")
@click.argument("vm_name", type=str)
@click.option("--size", required=True, type=int, help="Disk size in GB")
@click.option(
    "--mount",
    default=_DEFAULT_MOUNT,
    help="Mount point on the VM (default: /tmp)",
)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--sku",
    default="Standard_LRS",
    type=click.Choice(["Standard_LRS", "Premium_LRS", "StandardSSD_LRS"]),
    help="Storage SKU (default: Standard_LRS)",
)
def add_disk(
    vm_name: str,
    size: int,
    mount: str,
    resource_group: str | None,
    config: str | None,
    sku: str,
) -> None:
    """Add a managed disk to an existing VM.

    Creates a new Azure managed disk, attaches it to the VM,
    then formats and mounts it at the specified mount point.

    \b
    EXAMPLES:
    \b
    # Add a 64GB /tmp disk
    $ azlin disk add my-vm --size 64
    \b
    # Add a 128GB /tmp disk explicitly
    $ azlin disk add my-vm --size 128 --mount /tmp
    \b
    # Add a disk with custom mount point
    $ azlin disk add my-vm --size 256 --mount /data
    """
    try:
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Validate size
        if size < 1:
            click.echo("Error: Disk size must be at least 1GB.", err=True)
            sys.exit(1)
        if size > 32767:
            click.echo("Error: Disk size exceeds Azure maximum (32767GB / 32TB).", err=True)
            sys.exit(1)

        # Get VM location
        click.echo(f"Looking up VM '{vm_name}'...")
        executor = AzureCLIExecutor(show_progress=False, timeout=30)
        vm_result = executor.execute(
            ["az", "vm", "show", "--name", vm_name, "--resource-group", rg, "--output", "json"]
        )
        if not vm_result["success"]:
            click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
            sys.exit(1)

        vm_info = json.loads(vm_result["stdout"])
        location = vm_info["location"]

        # Derive mount-safe disk name suffix
        mount_suffix = mount.strip("/").replace("/", "-") or "data"
        safe_location = location.replace(" ", "-").lower()
        disk_name = f"{vm_name}-{mount_suffix}-{safe_location}"

        # Create the managed disk
        click.echo(f"Creating {size}GB managed disk '{disk_name}' ({sku})...")
        create_result = executor.execute(
            [
                "az",
                "disk",
                "create",
                "--name",
                disk_name,
                "--resource-group",
                rg,
                "--location",
                location,
                "--size-gb",
                str(size),
                "--sku",
                sku,
                "--output",
                "json",
            ]
        )
        if not create_result["success"]:
            click.echo(f"Error creating disk: {create_result['stderr']}", err=True)
            sys.exit(1)

        disk_info = json.loads(create_result["stdout"])
        disk_id = disk_info["id"]
        click.echo(f"Disk created: {disk_name}")

        # Attach disk to VM
        click.echo(f"Attaching disk to VM '{vm_name}'...")
        attach_result = executor.execute(
            [
                "az",
                "vm",
                "disk",
                "attach",
                "--vm-name",
                vm_name,
                "--resource-group",
                rg,
                "--disk",
                disk_id,
                "--output",
                "json",
            ]
        )
        if not attach_result["success"]:
            click.echo(f"Error attaching disk: {attach_result['stderr']}", err=True)
            sys.exit(1)

        click.echo("Disk attached successfully.")

        # Find the newly attached disk's LUN by querying the VM
        click.echo("Detecting disk LUN...")
        lun = 0  # Default LUN
        vm_result2 = executor.execute(
            ["az", "vm", "show", "--name", vm_name, "--resource-group", rg, "--output", "json"]
        )
        if vm_result2["success"]:
            vm_data = json.loads(vm_result2["stdout"])
            data_disks = vm_data.get("storageProfile", {}).get("dataDisks", [])
            # Find our disk by name
            for dd in data_disks:
                if dd.get("name") == disk_name:
                    lun = dd.get("lun", 0)
                    break

        click.echo(f"Disk at LUN {lun}. Formatting and mounting at {mount}...")

        # Build the formatting/mounting script
        # Use Azure VM run-command to execute on the VM (no SSH needed)
        mount_permissions = "1777" if mount == _DEFAULT_MOUNT else "755"
        format_script = (
            f"set -e && "
            f"echo 'Partitioning disk at LUN {lun}...' && "
            f"disk_dev=/dev/disk/azure/scsi1/lun{lun} && "
            f"if [ ! -b $disk_dev ]; then echo 'Disk device not found'; exit 1; fi && "
            f"sgdisk -n 1:0:0 -t 1:8300 $disk_dev || true && "
            f"partprobe $disk_dev && "
            f"sleep 2 && "
            f"part_dev=${{disk_dev}}-part1 && "
            f"mkfs.ext4 -F $part_dev && "
            f"mkdir -p {mount} && "
            f"mount $part_dev {mount} && "
            f"chmod {mount_permissions} {mount} && "
            f'echo "$part_dev {mount} ext4 defaults,nofail 0 2" >> /etc/fstab && '
            f"echo 'Disk mounted at {mount} successfully'"
        )

        run_executor = AzureCLIExecutor(show_progress=False, timeout=120)
        run_cmd_result = run_executor.execute(
            [
                "az",
                "vm",
                "run-command",
                "invoke",
                "--resource-group",
                rg,
                "--name",
                vm_name,
                "--command-id",
                "RunShellScript",
                "--scripts",
                format_script,
                "--output",
                "json",
            ]
        )

        if not run_cmd_result["success"]:
            click.echo(
                f"Warning: Disk attached but remote formatting failed: {run_cmd_result['stderr']}",
                err=True,
            )
            click.echo(
                "You may need to SSH in and manually format/mount the disk.",
                err=True,
            )
            sys.exit(1)

        # Parse run-command output for the script result
        try:
            run_output = json.loads(run_cmd_result["stdout"])
            messages = run_output.get("value", [])
            for msg in messages:
                if msg.get("code") == "ProvisioningState/succeeded":
                    stdout_msg = msg.get("message", "")
                    if stdout_msg:
                        click.echo(stdout_msg)
        except (json.JSONDecodeError, KeyError):
            pass

        click.echo(f"Done! {size}GB disk mounted at {mount} on VM '{vm_name}'.")

    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
