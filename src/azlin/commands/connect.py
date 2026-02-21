"""SSH connection command for azlin CLI.

This module provides SSH connectivity with tmux/bastion support.
Extracted from connectivity.py for better modularity (Issue #1799).
"""

import logging
import sys
from pathlib import Path

import click

from azlin.compound_identifier import CompoundIdentifierError, parse_identifier
from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.modules.nfs_quota_manager import NFSQuotaManager
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_manager import VMManager, VMManagerError

from .connectivity_common import resolve_vm_identifier, try_fetch_key_from_vault, verify_vm_exists

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def _interactive_vm_selection(
    rg: str, config: str | None, no_tmux: bool, tmux_session: str | None
) -> str:
    """Show interactive VM selection menu and return selected VM name."""
    try:
        vms = VMManager.list_vms(resource_group=rg, include_stopped=False)
    except VMManagerError as e:
        click.echo(f"Error listing VMs: {e}", err=True)
        sys.exit(1)

    if not vms:
        click.echo("No running VMs found in resource group.")
        response = click.prompt(
            "\nWould you like to create a new VM?",
            type=click.Choice(["y", "n"], case_sensitive=False),
            default="y",
        )
        if response.lower() == "y":
            from click import Context

            from azlin.commands.provisioning import new as new_command

            ctx = Context(new_command)
            ctx.invoke(
                new_command,
                resource_group=rg,
                config=config,
                no_tmux=no_tmux,
                tmux_session=tmux_session,
            )
        click.echo("Cancelled.")
        sys.exit(0)

    click.echo("\nAvailable VMs:")
    click.echo("─" * 60)
    for i, vm in enumerate(vms, 1):
        status_emoji = "🟢" if vm.is_running() else "🔴"
        click.echo(
            f"{i:2}. {status_emoji} {vm.name:<30} {vm.location:<15} {vm.vm_size or 'unknown'}"
        )
    click.echo("─" * 60)
    click.echo(" 0. Create new VM")
    click.echo()

    while True:
        try:
            selection = click.prompt(
                "Select a VM to connect to (0 to create new)",
                type=int,
                default=1 if vms else 0,
            )

            if selection == 0:
                from click import Context

                from azlin.commands.provisioning import new as new_command

                ctx = Context(new_command)
                ctx.invoke(
                    new_command,
                    resource_group=rg,
                    config=config,
                    no_tmux=no_tmux,
                    tmux_session=tmux_session,
                )
                sys.exit(0)
            if 1 <= selection <= len(vms):
                selected_vm = vms[selection - 1]  # type: ignore[misc]
                return str(selected_vm.name)  # type: ignore[union-attr]
            click.echo(f"Invalid selection. Please choose 0-{len(vms)}", err=True)
        except (ValueError, click.Abort):
            click.echo("\nCancelled.")
            sys.exit(0)


def _resolve_tmux_session(
    identifier: str, tmux_session: str | None, no_tmux: bool, config: str | None
) -> str | None:
    """Resolve tmux session name from provided value.

    Returns the explicit --tmux-session value if provided.
    If identifier is compound format (vm:session), extracts session name.
    Otherwise defaults to 'azlin' to provide consistent tmux session naming.

    Note: Session name (from config) is used to identify the VM, NOT as the tmux session name.
    """
    if no_tmux:
        return None

    # Explicit --tmux-session flag takes precedence
    if tmux_session:
        return tmux_session

    # Extract session from compound identifier
    if ":" in identifier:
        try:
            _, session_name = parse_identifier(identifier)
            if session_name:
                return session_name
        except CompoundIdentifierError:
            pass  # Fall through to default

    return "azlin"


# =============================================================================
# Connect Command
# =============================================================================


@click.command(name="connect")
@click.argument("vm_identifier", type=str, required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--no-tmux", is_flag=True, help="Disable tmux session management")
@click.option("--tmux-session", help="Custom tmux session name (default: azlin)", type=str)
@click.option("--user", default="azureuser", help="SSH username (default: azureuser)", type=str)
@click.option("--key", help="SSH private key path", type=click.Path(exists=True))
@click.option("--no-reconnect", is_flag=True, help="Disable auto-reconnect on SSH disconnect")
@click.option(
    "--max-retries", default=3, help="Maximum reconnection attempts (default: 3)", type=int
)
@click.option("--yes", "-y", is_flag=True, help="Skip prompts (auto-accept)")
@click.option(
    "--disable-bastion-pool",
    is_flag=True,
    hidden=True,
    help="Disable bastion tunnel pool (used by restore to prevent session crossing)",
)
@click.argument("remote_command", nargs=-1, type=str)
@click.pass_context
def connect(
    ctx: click.Context,
    vm_identifier: str | None,
    resource_group: str | None,
    config: str | None,
    no_tmux: bool,
    tmux_session: str | None,
    user: str,
    key: str | None,
    no_reconnect: bool,
    max_retries: int,
    yes: bool,
    disable_bastion_pool: bool,
    remote_command: tuple[str, ...],
):
    """Connect to existing VM via SSH.

    If VM_IDENTIFIER is not provided, displays an interactive list of available
    VMs to choose from, or option to create a new VM.

    VM_IDENTIFIER can be either:
    - VM name (requires --resource-group or default config)
    - Session name (will be resolved to VM name)
    - IP address (direct connection)

    Use -- to separate remote command from options.

    By default, auto-reconnect is ENABLED. If your SSH session disconnects,
    you will be prompted to reconnect. Use --no-reconnect to disable this.

    \b
    Examples:
        # Interactive selection
        azlin connect

        # Connect to VM by name
        azlin connect my-vm

        # Connect to VM by session name
        azlin connect my-project

        # Connect to VM by name with explicit resource group
        azlin connect my-vm --rg my-resource-group

        # Connect by IP address
        azlin connect 20.1.2.3

        # Connect without tmux
        azlin connect my-vm --no-tmux

        # Connect with custom tmux session name
        azlin connect my-vm --tmux-session dev

        # Connect and run command
        azlin connect my-vm -- ls -la

        # Connect with custom SSH user
        azlin connect my-vm --user myuser

        # Connect with custom SSH key
        azlin connect my-vm --key ~/.ssh/custom_key

        # Disable auto-reconnect
        azlin connect my-vm --no-reconnect

        # Set maximum reconnection attempts
        azlin connect my-vm --max-retries 5
    """
    # Set environment variable to disable bastion pool if flag is passed
    # This is critical to prevent session crossing when called from restore (Issue #593)
    if disable_bastion_pool:
        import os

        os.environ["AZLIN_DISABLE_BASTION_POOL"] = "1"

    # Validate remote command syntax BEFORE entering try block
    # If remote_command has values but passthrough_command is not in ctx.obj,
    # it means user typed "connect my-vm ls" without "--", which is invalid
    # Use ClickException (not UsageError) to avoid showing usage help text
    if remote_command and not (ctx.obj and "passthrough_command" in ctx.obj):
        # remote_command was populated by Click's nargs=-1 without -- separator
        raise click.ClickException(
            f"Got unexpected extra argument ({remote_command[0]})\n"
            "Use -- separator to pass remote commands: azlin connect my-vm -- ls -la"
        )

    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Get passthrough command from context (if using -- syntax)
        # AzlinGroup strips -- and everything after from sys.argv and stores in ctx.obj
        if ctx.obj and "passthrough_command" in ctx.obj:
            passthrough_cmd = ctx.obj["passthrough_command"]
            # Override remote_command with the passthrough version
            remote_command = tuple(passthrough_cmd.split())

        # Interactive VM selection if no identifier provided
        if not vm_identifier:
            rg = ConfigManager.get_resource_group(resource_group, config)
            if not rg:
                click.echo(
                    "Error: Resource group required.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
            vm_identifier = _interactive_vm_selection(rg, config, no_tmux, tmux_session)

        # Parse remote command and key path
        # If using -- separator, ALL arguments after it are the remote command
        command = " ".join(remote_command) if remote_command else None

        key_path = Path(key).expanduser() if key else None

        # Resolve session name to VM name
        vm_identifier, original_identifier = resolve_vm_identifier(vm_identifier, config)

        # Get resource group for VM name (not IP)
        if not VMConnector.is_valid_ip(vm_identifier):
            rg = ConfigManager.get_resource_group(resource_group, config)

            # Auto-detect resource group if not provided and feature is enabled
            if not rg:
                from azlin.modules.resource_group_discovery import ResourceGroupDiscovery

                try:
                    azlin_config = ConfigManager.load_config(config)

                    # Only attempt auto-detection if enabled in config
                    if azlin_config.resource_group_auto_detect:
                        logger.info(f"Auto-detecting resource group for VM: {vm_identifier}")
                        discovery = ResourceGroupDiscovery(azlin_config.__dict__)
                        discovered_rg = discovery.find_vm_resource_group(vm_identifier)
                        if discovered_rg:
                            logger.info(
                                f"Auto-detected resource group: {discovered_rg.resource_group}"
                            )
                            rg = discovered_rg.resource_group
                        else:
                            logger.debug(f"Auto-detection failed for VM: {vm_identifier}")
                except Exception as e:
                    logger.warning(f"Auto-detect resource group failed: {e}")
                    # Fall through to existing error handling

            # If still no resource group, show error
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

        # Auto-fetch SSH key from Key Vault if local key is missing
        if key_path is None:
            # Use default key path
            key_path = SSHKeyManager.DEFAULT_KEY_PATH

        # Check if key exists locally, if not try to fetch from vault
        if not key_path.exists():
            logger.debug(f"SSH key not found at {key_path}, attempting Key Vault fetch")
            try_fetch_key_from_vault(vm_identifier, key_path, config)

        # Resolve tmux session name (use original_identifier so tmux session matches user input)
        tmux_session = _resolve_tmux_session(original_identifier, tmux_session, no_tmux, config)

        # Connect to VM
        display_name = (
            original_identifier if original_identifier != vm_identifier else vm_identifier
        )
        click.echo(f"Connecting to {display_name}...")

        # Check NFS quota before connecting (if VM uses NFS storage)
        if not VMConnector.is_valid_ip(vm_identifier) and rg:
            try:
                nfs_info = NFSQuotaManager.check_vm_nfs_storage(vm_identifier, rg)
                if nfs_info:
                    storage_account, share_name, _ = nfs_info
                    quota_info = NFSQuotaManager.get_nfs_quota_info(storage_account, share_name, rg)
                    warning = NFSQuotaManager.check_quota_warning(quota_info)

                    if warning.is_warning and not yes:
                        click.echo()
                        click.echo(warning.message)
                        if NFSQuotaManager.prompt_and_expand_quota(quota_info):
                            result = NFSQuotaManager.expand_nfs_quota(
                                storage_account, share_name, rg, quota_info.quota_gb + 100
                            )
                            if result.success:
                                click.echo(
                                    f"✅ Quota expanded to {result.new_quota_gb}GB "
                                    f"(+${result.cost_increase_monthly:.2f}/month)"
                                )
                            else:
                                click.echo(f"⚠️  Quota expansion failed: {result.errors}")
                        click.echo()
            except Exception as e:
                # Don't block connection if quota check fails
                logger.debug(f"NFS quota check failed: {e}")

        # Disable reconnect for remote commands (no terminal for prompts)
        should_reconnect = (not no_reconnect) and (command is None)

        success = VMConnector.connect(
            vm_identifier=vm_identifier,
            resource_group=rg,
            use_tmux=not no_tmux,
            tmux_session=tmux_session,
            remote_command=command,
            ssh_user=user,
            ssh_key_path=key_path,
            enable_reconnect=should_reconnect,
            max_reconnect_retries=max_retries,
            skip_prompts=yes,
        )

        sys.exit(0 if success else 1)

    except VMConnectorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in connect command")
        sys.exit(1)


__all__ = ["connect"]
