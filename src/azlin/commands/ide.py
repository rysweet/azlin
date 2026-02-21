"""VS Code Remote launcher command for azlin CLI.

This module provides VS Code Remote-SSH integration with bastion support.
Extracted from connectivity.py for better modularity (Issue #1799).
"""

import logging
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextManager
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.modules.vscode_launcher import (
    VSCodeLauncher,
    VSCodeLauncherError,
    VSCodeNotFoundError,
)
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMManager, VMManagerError

from .connectivity_common import resolve_vm_identifier, verify_vm_exists

logger = logging.getLogger(__name__)


# =============================================================================
# Code Command (VS Code Remote)
# =============================================================================


@click.command(name="code")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group (required for VM name)", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--user", default="azureuser", help="SSH username (default: azureuser)", type=str)
@click.option("--key", help="SSH private key path", type=click.Path(exists=True))
@click.option("--no-extensions", is_flag=True, help="Skip extension installation (faster launch)")
@click.option("--workspace", help="Remote workspace path (default: /home/user)", type=str)
def code_command(
    vm_identifier: str,
    resource_group: str | None,
    config: str | None,
    user: str,
    key: str | None,
    no_extensions: bool,
    workspace: str | None,
):
    """Launch VS Code with Remote-SSH for a VM.

    One-click VS Code launch that automatically:
    - Configures SSH connection in ~/.ssh/config
    - Installs configured extensions from ~/.azlin/vscode/extensions.json
    - Sets up port forwarding from ~/.azlin/vscode/ports.json
    - Launches VS Code Remote-SSH

    VM_IDENTIFIER can be:
    - VM name (requires --resource-group or default config)
    - Session name (will be resolved to VM name)
    - IP address (direct connection)

    Configuration:
    Create ~/.azlin/vscode/ directory with optional files:
    - extensions.json: {"extensions": ["ms-python.python", ...]}
    - ports.json: {"forwards": [{"local": 3000, "remote": 3000}, ...]}
    - settings.json: VS Code workspace settings

    \b
    Examples:
        # Launch VS Code for VM
        azlin code my-dev-vm

        # Launch with explicit resource group
        azlin code my-vm --rg my-resource-group

        # Launch by session name
        azlin code my-project

        # Launch by IP address
        azlin code 20.1.2.3

        # Skip extension installation (faster)
        azlin code my-vm --no-extensions

        # Open specific remote directory
        azlin code my-vm --workspace /home/azureuser/projects

        # Custom SSH user
        azlin code my-vm --user myuser

        # Custom SSH key
        azlin code my-vm --key ~/.ssh/custom_key
    """
    try:
        # Resolve session name to VM name
        vm_identifier, original_identifier = resolve_vm_identifier(vm_identifier, config)

        # Get resource group for VM name (not IP)
        if not VMConnector.is_valid_ip(vm_identifier):
            rg = ConfigManager.get_resource_group(resource_group, config)
            if not rg:
                click.echo(
                    "Error: Resource group required for VM name.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
            verify_vm_exists(vm_identifier, original_identifier, rg)
        else:
            rg = resource_group

        # Get VM information
        click.echo(f"Setting up VS Code for {original_identifier}...")

        # Initialize bastion-related variables (may be set later)
        bastion_tunnel = None
        tunnel_host: str = ""
        tunnel_port: int = 22

        if VMConnector.is_valid_ip(vm_identifier):
            # Direct IP connection
            vm_ip = vm_identifier
            vm_name = f"vm-{vm_ip.replace('.', '-')}"
            tunnel_host = vm_ip
        else:
            # Get VM info from Azure
            if not rg:
                click.echo("Error: Resource group required", err=True)
                sys.exit(1)

            vm_info = VMManager.get_vm(vm_identifier, rg)
            if vm_info is None:
                click.echo(
                    f"Error: VM '{vm_identifier}' not found in resource group '{rg}'", err=True
                )
                sys.exit(1)

            vm_name = vm_info.name
            vm_ip = vm_info.public_ip
            private_ip = vm_info.private_ip

            # Check if VM needs bastion (no public IP)
            tunnel_host = vm_ip if vm_ip else ""

            if not vm_ip and private_ip:
                click.echo(
                    f"VM {vm_name} is private-only (no public IP), will use bastion tunnel..."
                )

                # Auto-detect bastion (same logic as azlin connect)
                bastion_info = BastionDetector.detect_bastion_for_vm(
                    vm_name=vm_name, resource_group=rg, vm_location=vm_info.location
                )

                if not bastion_info:
                    click.echo(
                        f"Error: VM {vm_name} has no public IP and no bastion found.\n"
                        f"Create a bastion: azlin bastion create --rg {rg}",
                        err=True,
                    )
                    sys.exit(1)

                click.echo(
                    f"✓ Found bastion: {bastion_info['name']} (region: {bastion_info['location']})"
                )

                # Get subscription ID and build VM resource ID
                context_config = ContextManager.load()
                current_context = context_config.get_current_context()
                if not current_context:
                    click.echo("Error: No context set, cannot create bastion tunnel", err=True)
                    sys.exit(1)

                vm_resource_id = (
                    f"/subscriptions/{current_context.subscription_id}/resourceGroups/{rg}/"
                    f"providers/Microsoft.Compute/virtualMachines/{vm_name}"
                )

                # Create bastion tunnel (matches azlin connect approach)
                click.echo(f"Creating bastion tunnel to {vm_name}...")

                # Initialize BastionManager and get available port
                bastion_manager = BastionManager()
                local_port = bastion_manager.get_available_port()

                # Create tunnel
                bastion_tunnel = bastion_manager.create_tunnel(
                    bastion_name=bastion_info["name"],
                    resource_group=bastion_info["resource_group"],
                    target_vm_id=vm_resource_id,
                    local_port=local_port,
                    remote_port=22,
                )

                # Use tunnel endpoint for VS Code
                tunnel_host = "127.0.0.1"
                tunnel_port = bastion_tunnel.local_port

                click.echo(f"✓ Bastion tunnel created on {tunnel_host}:{tunnel_port}")
                click.echo("  (Tunnel will remain open for VS Code - close VS Code to stop tunnel)")

                vm_ip = tunnel_host  # Use tunnel endpoint

            if not vm_ip and not tunnel_host:
                click.echo(f"Error: No IP address found for VM {vm_identifier}", err=True)
                sys.exit(1)

        # Determine final connection details
        final_host = tunnel_host if bastion_tunnel else (vm_ip or "")
        if not final_host:
            click.echo(f"Error: No connection endpoint available for VM {vm_identifier}", err=True)
            sys.exit(1)

        # Ensure SSH key exists
        key_path = Path(key).expanduser() if key else Path.home() / ".ssh" / "azlin_key"
        ssh_keys = SSHKeyManager.ensure_key_exists(key_path)

        # Launch VS Code
        click.echo("Configuring VS Code Remote-SSH...")

        VSCodeLauncher.launch(
            vm_name=vm_name,
            host=final_host,
            port=tunnel_port,
            user=user,
            key_path=ssh_keys.private_path,
            install_extensions=not no_extensions,
            workspace_path=workspace,
        )

        click.echo(f"\n✓ VS Code launched successfully for {original_identifier}")
        click.echo(f"  SSH Host: azlin-{vm_name}")
        if bastion_tunnel:
            click.echo(f"  Connection: via bastion tunnel at {final_host}:{tunnel_port}")
            click.echo("\n⚠️  KEEP THIS TERMINAL OPEN - Bastion tunnel is active!")
            click.echo("   The tunnel will close when you press Ctrl+C here.")
            click.echo("")

            # Keep tunnel alive until user interrupts
            try:
                click.echo("Press Ctrl+C to close the tunnel when done with VS Code...")
                import time

                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                click.echo("\n\nClosing bastion tunnel...")
        else:
            click.echo(f"  User: {user}@{final_host}")

        if not no_extensions:
            click.echo("\nExtensions will be installed in VS Code.")
            click.echo("Use --no-extensions to skip extension installation for faster launch.")

        click.echo("\nTo customize:")
        click.echo("  Extensions: ~/.azlin/vscode/extensions.json")
        click.echo("  Port forwards: ~/.azlin/vscode/ports.json")
        click.echo("  Settings: ~/.azlin/vscode/settings.json")

    except VSCodeNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VSCodeLauncherError as e:
        click.echo(f"Error launching VS Code: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except SSHKeyError as e:
        click.echo(f"SSH key error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in code command")
        sys.exit(1)


__all__ = ["code_command"]
