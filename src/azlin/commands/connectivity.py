"""Connectivity commands for azlin.

This module contains SSH connectivity and file transfer CLI commands extracted from cli.py.
Part of Issue #423 - cli.py decomposition.

Commands:
    - connect: SSH connection with tmux support and auto-reconnect
    - code_command: Launch VS Code with Remote-SSH
    - update: Update development tools on a VM
    - sync: Sync ~/.azlin/home/ to VM home directory
    - sync_keys: Manually sync SSH keys to VM authorized_keys
    - cp: Copy files between local machine and VMs
"""

import logging
import sys
import time
from pathlib import Path

import click
from rich.console import Console

from azlin.auth_models import AuthConfig, AuthMethod
from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextManager
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.file_transfer import (
    FileTransfer,
    FileTransferError,
    PathParser,
    SessionManager,
    TransferEndpoint,
)
from azlin.modules.home_sync import (
    HomeSyncError,
    HomeSyncManager,
)
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_key_vault import (
    KeyVaultError,
    create_key_vault_manager,
)
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager, SSHKeyPair
from azlin.modules.vscode_launcher import (
    VSCodeLauncher,
    VSCodeLauncherError,
    VSCodeNotFoundError,
)
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

__all__ = [
    # Helper functions (for use by other modules)
    "_auto_sync_home_directory",
    "_execute_sync",
    "_get_sync_vm_by_name",
    "_interactive_vm_selection",
    "_perform_sync",
    "_resolve_tmux_session",
    "_resolve_vm_identifier",
    "_select_sync_vm_interactive",
    "_try_fetch_key_from_vault",
    "_verify_vm_exists",
    # Commands
    "code_command",
    "connect",
    "cp",
    "sync",
    "sync_keys",
    "update",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def _auto_sync_home_directory(ssh_config: SSHConfig) -> None:
    """Auto-sync home directory before SSH connection (silent).

    Args:
        ssh_config: SSH configuration for target VM

    Note:
        Sync failures are silently ignored to not disrupt connection flow.
    """
    try:
        result = HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)
        if result.success and result.files_synced > 0:
            logger.info(f"Auto-synced {result.files_synced} files")
    except Exception as e:
        # Silent failure - log but don't interrupt connection
        logger.debug(f"Auto-sync failed: {e}")


def _is_valid_vm_name(vm_name: str, config: str | None) -> bool:
    """Check if a string is a valid VM name (exists in the configured resource group).

    Args:
        vm_name: Potential VM name to check
        config: Config file path (optional)

    Returns:
        True if a VM with this name exists, False otherwise
    """
    try:
        rg = ConfigManager.get_resource_group(None, config)
        if not rg:
            return False
        vm_info = VMManager.get_vm(vm_name, rg)
        return vm_info is not None
    except Exception:
        return False


def _interactive_vm_selection(
    rg: str, config: str | None, no_tmux: bool, tmux_session: str | None
) -> str:
    """Show interactive VM selection menu and return selected VM name.

    Note: This function references the 'new' command from the main CLI.
    When creating a new VM is selected, it invokes that command.
    """
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
            # Import here to avoid circular imports
            from click import Context

            from azlin.cli import new_command

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
                # Import here to avoid circular imports
                from click import Context

                from azlin.cli import new_command

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


def _resolve_vm_identifier(vm_identifier: str, config: str | None) -> tuple[str, str]:
    """Resolve session name to VM name and return both.

    Only resolves session names to VM names if the identifier is NOT already
    a valid VM name. This prevents accidental redirection when a VM name
    happens to match a session name configured for a different VM.

    Resolution is SKIPPED when:
    - The identifier is a valid IP address
    - The identifier is already a valid VM name
    - The identifier equals the resolved VM name (self-referential)

    Returns:
        Tuple of (resolved_identifier, original_identifier)
    """
    original_identifier = vm_identifier
    if not VMConnector.is_valid_ip(vm_identifier):
        # First check if this is already a valid VM name - if so, don't resolve
        # This prevents: User types "amplifier" (a VM) but session "amplifier"
        # exists on VM "atg-dev" -> should connect to VM "amplifier", not "atg-dev"
        if _is_valid_vm_name(vm_identifier, config):
            logger.debug(f"'{vm_identifier}' is a valid VM name, skipping session resolution")
            return vm_identifier, original_identifier

        # Not a VM name, try to resolve as session name
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
        if resolved_vm_name and resolved_vm_name != vm_identifier:
            click.echo(f"Resolved session '{vm_identifier}' to VM '{resolved_vm_name}'")
            vm_identifier = resolved_vm_name
    return vm_identifier, original_identifier


def _verify_vm_exists(vm_identifier: str, original_identifier: str, rg: str) -> None:
    """Verify VM exists and clean up stale session mappings."""
    if original_identifier != vm_identifier:
        try:
            vm_info = VMManager.get_vm(vm_identifier, rg)
            if vm_info is None:
                click.echo(
                    f"Error: Session '{original_identifier}' points to VM '{vm_identifier}' "
                    f"which no longer exists.",
                    err=True,
                )
                ConfigManager.delete_session_name(vm_identifier)
                click.echo(f"Removed stale session mapping for '{vm_identifier}'")
                sys.exit(1)
        except VMManagerError as e:
            click.echo(f"Error: Failed to verify VM exists: {e}", err=True)
            sys.exit(1)


def _resolve_tmux_session(
    identifier: str, tmux_session: str | None, no_tmux: bool, config: str | None
) -> str | None:
    """Resolve tmux session name from provided value.

    Returns the explicit --tmux-session value if provided.
    Otherwise defaults to 'azlin' to provide consistent tmux session naming.

    Note: Session name (from config) is used to identify the VM, NOT as the tmux session name.
    """
    if no_tmux:
        return None
    return tmux_session if tmux_session else "azlin"


def _try_fetch_key_from_vault(vm_name: str, key_path: Path, config: str | None) -> bool:
    """Try to fetch SSH key from Azure Key Vault if local key is missing.

    Args:
        vm_name: VM name (used to lookup secret)
        key_path: Target path for private key
        config: Config file path

    Returns:
        True if key was fetched successfully, False otherwise
    """
    try:
        # Load context to get key_vault_name
        context_config = ContextManager.load(config)
        current_context = context_config.get_current_context()

        if not current_context or not current_context.key_vault_name:
            logger.debug("No Key Vault configured, skipping auto-fetch")
            return False

        console = Console()
        console.print("[yellow]SSH key not found locally, checking Key Vault...[/yellow]")

        # Build auth config from context
        # Note: Currently only supports Azure CLI authentication
        # Service Principal support would require storing credentials in context
        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        # Create Key Vault manager
        manager = create_key_vault_manager(
            vault_name=current_context.key_vault_name,
            subscription_id=current_context.subscription_id,
            tenant_id=current_context.tenant_id,
            auth_config=auth_config,
        )

        # Check if key exists in vault
        if not manager.key_exists(vm_name):
            logger.debug(f"SSH key not found in Key Vault for VM: {vm_name}")
            return False

        # Retrieve key
        manager.retrieve_key(vm_name, key_path)
        console.print(
            f"[green]SSH key retrieved from Key Vault: {current_context.key_vault_name}[/green]"
        )
        return True

    except KeyVaultError as e:
        logger.warning(f"Failed to fetch SSH key from Key Vault: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error fetching SSH key: {e}")
        return False


def _get_sync_vm_by_name(vm_name: str, rg: str) -> VMInfo:
    """Get and validate a specific VM for syncing."""
    vm = VMManager.get_vm(vm_name, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not vm.is_running():
        click.echo(f"Error: VM '{vm_name}' is not running.", err=True)
        sys.exit(1)

    # Check that VM has at least one IP (public or private)
    if not vm.public_ip and not vm.private_ip:
        click.echo(
            f"Error: VM '{vm_name}' has no IP address (neither public nor private).", err=True
        )
        sys.exit(1)

    return vm


def _select_sync_vm_interactive(rg: str) -> VMInfo:
    """Interactively select a VM for syncing."""
    vms = VMManager.list_vms(rg, include_stopped=False)
    vms = VMManager.filter_by_prefix(vms, "azlin")
    # Include all running VMs (both public IP and Bastion-only)
    vms = [vm for vm in vms if vm.is_running()]

    if not vms:
        click.echo("No running VMs found.")
        sys.exit(1)

    if len(vms) == 1:
        selected_vm = vms[0]
        click.echo(f"Auto-selecting VM: {selected_vm.name}")
        return selected_vm

    # Show menu
    click.echo("\nSelect VM to sync to:")
    for idx, vm in enumerate(vms, 1):
        # Display public IP if available, otherwise show "(Bastion)"
        ip_display = vm.public_ip if vm.public_ip else f"{vm.private_ip} (Bastion)"
        click.echo(f"  {idx}. {vm.name} - {ip_display}")

    choice = input("\nSelect VM (number): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            return vms[idx]
        click.echo("Invalid selection", err=True)
        sys.exit(1)
    except ValueError:
        click.echo("Invalid input", err=True)
        sys.exit(1)


def _perform_sync(ssh_config: SSHConfig, dry_run: bool) -> None:
    """Perform the actual sync operation.

    Args:
        ssh_config: SSH configuration for connection
        dry_run: Whether to perform dry run

    Raises:
        SystemExit: On sync errors
    """

    def progress_callback(msg: str) -> None:
        click.echo(f"  {msg}")

    result = HomeSyncManager.sync_to_vm(
        ssh_config, dry_run=dry_run, progress_callback=progress_callback
    )

    if result.success:
        click.echo(
            f"\nSuccess! Synced {result.files_synced} files "
            f"({result.bytes_transferred / 1024:.1f} KB) "
            f"in {result.duration_seconds:.1f}s"
        )
    else:
        click.echo("\nSync completed with errors:", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)


def _execute_sync(selected_vm: VMInfo, ssh_key_pair: SSHKeyPair, dry_run: bool) -> None:
    """Execute the sync operation to the selected VM.

    Supports both direct connection (public IP) and Bastion routing (private IP only).
    """
    # Check if VM has public IP for direct connection
    if selected_vm.public_ip:
        # Direct connection path (existing behavior)
        click.echo(f"\nSyncing to {selected_vm.name} ({selected_vm.public_ip})...")

        ssh_config = SSHConfig(
            host=selected_vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
        )

        _perform_sync(ssh_config, dry_run)
        return

    # VM has no public IP - try Bastion routing
    if not selected_vm.private_ip:
        click.echo("Error: VM has no IP address (neither public nor private)", err=True)
        sys.exit(1)

    # Detect Bastion
    bastion_info = BastionDetector.detect_bastion_for_vm(
        vm_name=selected_vm.name,
        resource_group=selected_vm.resource_group,
        vm_location=selected_vm.location,
    )
    if not bastion_info:
        click.echo(
            f"Error: VM '{selected_vm.name}' has no public IP and no Bastion host was detected.\n"
            f"Please provision a Bastion host or assign a public IP to the VM.",
            err=True,
        )
        sys.exit(1)

    # Use Bastion tunnel
    click.echo(
        f"\nSyncing to {selected_vm.name} (private IP: {selected_vm.private_ip}) via Bastion..."
    )

    try:
        with BastionManager() as bastion_mgr:
            # Get VM resource ID
            vm_resource_id = VMManager.get_vm_resource_id(
                selected_vm.name, selected_vm.resource_group
            )
            if not vm_resource_id:
                raise BastionManagerError("Failed to get VM resource ID")

            # Find available port
            local_port = bastion_mgr.get_available_port()

            # Create tunnel
            click.echo(f"Creating Bastion tunnel through {bastion_info['name']}...")
            _tunnel = bastion_mgr.create_tunnel(
                bastion_name=bastion_info["name"],
                resource_group=bastion_info["resource_group"],
                target_vm_id=vm_resource_id,
                local_port=local_port,
                remote_port=22,
                wait_for_ready=True,
            )

            # Create SSH config using tunnel
            ssh_config = SSHConfig(
                host="127.0.0.1",
                port=local_port,
                user="azureuser",
                key_path=ssh_key_pair.private_path,
            )

            # Perform sync through tunnel
            _perform_sync(ssh_config, dry_run)

    except BastionManagerError as e:
        click.echo(f"\nBastion tunnel error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nSync failed: {e}", err=True)
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


# =============================================================================
# CONNECT COMMAND
# =============================================================================


@click.command()
@click.argument("vm_identifier", type=str, required=False)
@click.option("--resource-group", "--rg", help="Resource group (required for VM name)", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--no-tmux", is_flag=True, help="Skip tmux session")
@click.option("--tmux-session", help="Tmux session name (default: azlin)", type=str)
@click.option("--user", default="azureuser", help="SSH username (default: azureuser)", type=str)
@click.option("--key", help="SSH private key path", type=click.Path(exists=True))
@click.option("--no-reconnect", is_flag=True, help="Disable auto-reconnect on disconnect")
@click.option(
    "--max-retries", default=3, help="Maximum reconnection attempts (default: 3)", type=int
)
@click.option("--yes", "-y", is_flag=True, help="Skip all confirmation prompts (e.g., Bastion)")
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
    remote_command: tuple[str, ...],
) -> None:
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

    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        from azlin.context_manager import ContextError

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
        vm_identifier, original_identifier = _resolve_vm_identifier(vm_identifier, config)

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
            _verify_vm_exists(vm_identifier, original_identifier, rg)
        else:
            rg = resource_group

        # Auto-fetch SSH key from Key Vault if local key is missing
        if key_path is None:
            # Use default key path
            key_path = SSHKeyManager.DEFAULT_KEY_PATH

        # Check if key exists locally, if not try to fetch from vault
        if not key_path.exists():
            logger.debug(f"SSH key not found at {key_path}, attempting Key Vault fetch")
            _try_fetch_key_from_vault(vm_identifier, key_path, config)

        # Resolve tmux session name (use original_identifier so tmux session matches user input)
        tmux_session = _resolve_tmux_session(original_identifier, tmux_session, no_tmux, config)

        # Connect to VM
        display_name = (
            original_identifier if original_identifier != vm_identifier else vm_identifier
        )
        click.echo(f"Connecting to {display_name}...")

        # Check NFS quota before connecting (if VM uses NFS storage)
        if not VMConnector.is_valid_ip(vm_identifier) and rg:
            from azlin.modules.nfs_quota_manager import NFSQuotaManager

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


# =============================================================================
# CODE COMMAND (VS Code Remote-SSH)
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
) -> None:
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
        vm_identifier, original_identifier = _resolve_vm_identifier(vm_identifier, config)

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
            _verify_vm_exists(vm_identifier, original_identifier, rg)
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


# =============================================================================
# UPDATE COMMAND
# =============================================================================


@click.command()
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--timeout", help="Timeout per update in seconds", type=int, default=300)
def update(
    vm_identifier: str, resource_group: str | None, config: str | None, timeout: int
) -> None:
    """Update all development tools on a VM.

    Updates system packages, programming languages, CLIs, and other dev tools
    that were installed during VM provisioning.

    VM_IDENTIFIER can be:
    - VM name (requires --resource-group or default config)
    - Session name (will be resolved to VM name)
    - IP address (direct connection)

    Tools updated:
    - System packages (apt)
    - Azure CLI
    - GitHub CLI
    - npm and npm packages (Copilot, Codex, Claude Code)
    - Rust toolchain
    - astral-uv

    \b
    Examples:
        # Update VM by name
        azlin update my-vm

        # Update VM by session name
        azlin update my-project

        # Update VM by IP
        azlin update 20.1.2.3

        # Update with custom timeout (default 300s per tool)
        azlin update my-vm --timeout 600

        # Update with explicit resource group
        azlin update my-vm --rg my-resource-group
    """
    from azlin.modules.progress import ProgressDisplay
    from azlin.vm_updater import VMUpdater, VMUpdaterError

    try:
        # Resolve VM identifier to SSH config
        # Try session name first, then VM name, then IP
        original_identifier = vm_identifier

        # Try to resolve as session name
        try:
            session_vm = ConfigManager.get_vm_name_by_session(vm_identifier, config)
            if session_vm:
                vm_identifier = session_vm
                click.echo(f"Resolved session '{original_identifier}' to VM '{vm_identifier}'")
        except Exception as e:
            logger.debug(f"Not a session name, trying as VM name or IP: {e}")

        # Get SSH config for VM
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Display info
        display_name = (
            original_identifier if original_identifier != vm_identifier else vm_identifier
        )
        click.echo(f"\nUpdating tools on {display_name}...")
        click.echo("This may take several minutes.\n")

        # Create progress display
        progress = ProgressDisplay()

        # Create updater with progress callback
        def progress_callback(message: str) -> None:
            click.echo(f"  {message}")

        updater = VMUpdater(
            ssh_config=ssh_config, timeout=timeout, progress_callback=progress_callback
        )

        # Perform update
        progress.start_operation("Updating VM tools", estimated_seconds=180)
        summary = updater.update_vm()
        progress.complete(
            success=summary.all_succeeded,
            message=f"Update completed in {summary.total_duration:.1f}s",
        )

        # Display results
        click.echo("\n" + "=" * 60)
        click.echo("UPDATE SUMMARY")
        click.echo("=" * 60)

        if summary.successful:
            click.echo(f"\n✓ Successful updates ({len(summary.successful)}):")
            for result in summary.successful:
                click.echo(f"  {result.tool_name:<20} {result.duration:>6.1f}s")

        if summary.failed:
            click.echo(f"\n✗ Failed updates ({len(summary.failed)}):")
            for result in summary.failed:
                click.echo(f"  {result.tool_name:<20} {result.message[:40]}")

        click.echo(f"\nTotal time: {summary.total_duration:.1f}s")
        click.echo("=" * 60 + "\n")

        # Exit with appropriate code
        if summary.all_succeeded:
            click.echo("All updates completed successfully!")
            sys.exit(0)
        elif summary.any_failed:
            if summary.success_count > 0:
                click.echo(
                    f"Partial success: {summary.success_count}/{summary.total_updates} updates succeeded"
                )
                sys.exit(1)
            else:
                click.echo("All updates failed!")
                sys.exit(2)

    except VMUpdaterError as e:
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
        logger.exception("Unexpected error in update command")
        sys.exit(1)


# =============================================================================
# SYNC COMMAND
# =============================================================================


@click.command()
@click.option("--vm-name", help="VM name to sync to", type=str)
@click.option("--dry-run", help="Show what would be synced", is_flag=True)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def sync(
    vm_name: str | None, dry_run: bool, resource_group: str | None, config: str | None
) -> None:
    """Sync ~/.azlin/home/ to VM home directory.

    Syncs local configuration files to remote VM for consistent
    development environment.

    \b
    Examples:
        azlin sync                    # Interactive VM selection
        azlin sync --vm-name myvm     # Sync to specific VM
        azlin sync --dry-run          # Show what would be synced
    """
    try:
        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: Resource group required for VM name.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        # Resolve session name to VM name if applicable
        if vm_name:
            resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
            if resolved_vm_name:
                vm_name = resolved_vm_name

        # Get VM
        if vm_name:
            selected_vm = _get_sync_vm_by_name(vm_name, rg)
        else:
            selected_vm = _select_sync_vm_interactive(rg)

        # Execute sync
        _execute_sync(selected_vm, ssh_key_pair, dry_run)

    except HomeSyncError as e:
        click.echo(f"\nSync failed: {e}", err=True)
        sys.exit(1)

    except (VMManagerError, ConfigError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)

    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in sync command")
        sys.exit(1)


# =============================================================================
# SYNC-KEYS COMMAND
# =============================================================================


@click.command(name="sync-keys")
@click.argument("vm_name")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--ssh-user", default="azureuser", help="SSH username (default: azureuser)")
@click.option("--timeout", default=60, help="Timeout in seconds (default: 60)")
@click.option("--config", help="Config file path", type=click.Path())
def sync_keys(
    vm_name: str, resource_group: str | None, ssh_user: str, timeout: int, config: str | None
) -> None:
    """Manually sync SSH keys to VM authorized_keys.

    This command synchronizes SSH public keys from your local machine
    to the target VM's authorized_keys file. Useful for newly created
    VMs or when auto-sync was skipped.

    \b
    Examples:
        azlin sync-keys myvm                      # Sync to VM in default resource group
        azlin sync-keys myvm --rg my-rg           # Sync to VM in specific resource group
        azlin sync-keys myvm --timeout 120        # Sync with extended timeout
    """
    try:
        # Get SSH key pair
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: Resource group required.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            click.echo(f"Resolved session name '{vm_name}' to VM '{resolved_vm_name}'")
            vm_name = resolved_vm_name

        # Verify VM exists
        try:
            vm = VMManager.get_vm(vm_name, rg)
            if not vm:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'", err=True)
                sys.exit(1)

            if not vm.is_running():
                click.echo(
                    f"Warning: VM '{vm_name}' is not running (state: {vm.power_state}). "
                    "Key sync may fail.",
                    err=True,
                )
        except Exception as e:
            click.echo(f"Error: Could not verify VM status: {e}", err=True)
            sys.exit(1)

        # Get config for sync settings
        azlin_config = ConfigManager.load_config(config)

        # Import VMKeySync
        from azlin.modules.vm_key_sync import VMKeySync

        # Derive public key from private key
        public_key = SSHKeyManager.get_public_key(ssh_key_pair.private_path)

        click.echo(f"Syncing SSH key to VM '{vm_name}' in resource group '{rg}'...")

        # Instantiate VMKeySync with config dict
        sync_manager = VMKeySync(azlin_config.to_dict())

        # Sync keys
        sync_manager.ensure_key_authorized(
            vm_name=vm_name,
            resource_group=rg,
            public_key=public_key,
        )

        click.echo(f"✓ SSH keys successfully synced to VM '{vm_name}'")

    except (VMManagerError, ConfigError, SSHKeyError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)

    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in sync-keys command")
        sys.exit(1)


# =============================================================================
# CP COMMAND (File Transfer)
# =============================================================================


@click.command()
@click.argument("args", nargs=-1, required=True)
@click.option("--dry-run", is_flag=True, help="Show what would be transferred")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def cp(
    args: tuple[str, ...],
    dry_run: bool,
    resource_group: str | None,
    config: str | None,
) -> None:
    """Copy files between local machine and VMs.

    Supports bidirectional file transfer with security-hardened path validation.
    Accepts multiple source files when copying to a single destination.

    Arguments support session:path notation:
    - Local path: myfile.txt
    - Remote path: vm1:~/myfile.txt

    \b
    Examples:
        azlin cp myfile.txt vm1:~/                     # Single file to remote
        azlin cp file1.txt file2.txt file3.py vm1:~/   # Multiple files to remote
        azlin cp vm1:~/data.txt ./                     # Remote to local
        azlin cp vm1:~/src vm2:~/dest                  # Remote to remote (not supported)
        azlin cp --dry-run test.txt vm1:~/             # Show transfer plan
    """
    src_manager, dst_manager = None, None
    try:
        # Parse args: all but last are sources, last is destination
        if len(args) < 2:
            click.echo("Error: At least one source and one destination required", err=True)
            click.echo("Usage: azlin cp SOURCE... DESTINATION", err=True)
            sys.exit(1)

        sources = args[:-1]
        destination = args[-1]

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Get SSH key
        SSHKeyManager.ensure_key_exists()

        # Parse destination first (shared by all sources)
        dest_session_name, dest_path_str = SessionManager.parse_session_path(destination)

        if dest_session_name is None:
            # Local destination - resolve from cwd, allow absolute paths
            dest_path = PathParser.parse_and_validate(
                dest_path_str, allow_absolute=True, is_local=True
            )
            dest_endpoint = TransferEndpoint(path=dest_path, session=None)
        else:
            # Remote destination
            if not rg:
                click.echo("Error: Resource group required for remote sessions.", err=True)
                click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
                sys.exit(1)

            # Get session (returns tuple now)
            vm_session, dst_manager = SessionManager.get_vm_session(
                dest_session_name, rg, VMManager
            )

            # Parse remote path (allow relative to home)
            dest_path = PathParser.parse_and_validate(
                dest_path_str,
                allow_absolute=True,
                base_dir=Path("/home") / vm_session.user,
                is_local=False,  # Remote path - don't validate against local filesystem
            )

            dest_endpoint = TransferEndpoint(path=dest_path, session=vm_session)

        # Parse all sources and create endpoints
        source_endpoints: list[TransferEndpoint] = []
        for source in sources:
            source_session_name, source_path_str = SessionManager.parse_session_path(source)

            if source_session_name is None:
                # Local source - resolve from cwd, allow absolute paths
                source_path = PathParser.parse_and_validate(
                    source_path_str, allow_absolute=True, is_local=True
                )
                source_endpoint = TransferEndpoint(path=source_path, session=None)
            else:
                # Remote source
                if not rg:
                    click.echo("Error: Resource group required for remote sessions.", err=True)
                    click.echo(
                        "Use --resource-group or set default in ~/.azlin/config.toml", err=True
                    )
                    sys.exit(1)

                # Get session (returns tuple now) - reuse if same session
                if src_manager is None:
                    vm_session, src_manager = SessionManager.get_vm_session(
                        source_session_name, rg, VMManager
                    )
                else:
                    # Already have a session - verify it's the same VM
                    vm_session, _ = SessionManager.get_vm_session(
                        source_session_name, rg, VMManager
                    )

                # Parse remote path (allow relative to home)
                source_path = PathParser.parse_and_validate(
                    source_path_str,
                    allow_absolute=True,
                    base_dir=Path("/home") / vm_session.user,
                    is_local=False,  # Remote path - don't validate against local filesystem
                )

                source_endpoint = TransferEndpoint(path=source_path, session=vm_session)

            source_endpoints.append(source_endpoint)

        # Validate all sources are from the same location (all local or all same remote)
        first_source = source_endpoints[0]
        for idx, src_endpoint in enumerate(source_endpoints[1:], start=1):
            if (first_source.session is None) != (src_endpoint.session is None):
                click.echo(
                    "Error: All sources must be from the same location "
                    "(either all local or all from the same VM)",
                    err=True,
                )
                sys.exit(1)
            if (
                first_source.session
                and src_endpoint.session
                and first_source.session.name != src_endpoint.session.name
            ):
                click.echo("Error: All remote sources must be from the same VM", err=True)
                sys.exit(1)

        # Display transfer plan
        click.echo("\nTransfer Plan:")
        if len(source_endpoints) == 1:
            if source_endpoints[0].session is None:
                click.echo(f"  Source: {source_endpoints[0].path} (local)")
            else:
                click.echo(
                    f"  Source: {source_endpoints[0].session.name}:{source_endpoints[0].path}"
                )
        else:
            click.echo(f"  Sources: {len(source_endpoints)} files")
            for src_endpoint in source_endpoints:
                if src_endpoint.session is None:
                    click.echo(f"    - {src_endpoint.path} (local)")
                else:
                    click.echo(f"    - {src_endpoint.session.name}:{src_endpoint.path}")

        if dest_endpoint.session is None:
            click.echo(f"  Dest:   {dest_endpoint.path} (local)")
        else:
            click.echo(f"  Dest:   {dest_endpoint.session.name}:{dest_endpoint.path}")

        click.echo()

        if dry_run:
            click.echo("Dry run - no files transferred")
            return

        # Execute transfers
        total_files = 0
        total_bytes = 0
        total_duration = 0.0
        all_errors: list[str] = []

        for idx, source_endpoint in enumerate(source_endpoints, start=1):
            if len(source_endpoints) > 1:
                source_name = (
                    source_endpoint.path.name
                    if source_endpoint.session is None
                    else f"{source_endpoint.session.name}:{source_endpoint.path.name}"
                )
                click.echo(f"[{idx}/{len(source_endpoints)}] Transferring {source_name}...")

            result = FileTransfer.transfer(source_endpoint, dest_endpoint)

            total_files += result.files_transferred
            total_bytes += result.bytes_transferred
            total_duration += result.duration_seconds

            if result.success:
                if len(source_endpoints) > 1:
                    click.echo(
                        f"  ✓ {result.bytes_transferred / 1024:.1f} KB "
                        f"in {result.duration_seconds:.1f}s"
                    )
            else:
                all_errors.extend(result.errors)
                if len(source_endpoints) > 1:
                    click.echo(
                        f"  ✗ Failed: {result.errors[0] if result.errors else 'Unknown error'}"
                    )

        # Display summary
        if all_errors:
            click.echo("\nTransfer completed with errors:", err=True)
            click.echo(
                f"Transferred {total_files} files ({total_bytes / 1024:.1f} KB) "
                f"in {total_duration:.1f}s"
            )
            for error in all_errors:
                click.echo(f"  {error}", err=True)
            sys.exit(1)
        else:
            if len(source_endpoints) > 1:
                click.echo(
                    f"\nSuccess! Transferred {total_files} files "
                    f"({total_bytes / 1024:.1f} KB) in {total_duration:.1f}s"
                )
            else:
                click.echo(
                    f"Success! Transferred {total_files} files "
                    f"({total_bytes / 1024:.1f} KB) in {total_duration:.1f}s"
                )

    except FileTransferError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
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
        logger.exception("Unexpected error in cp command")
        sys.exit(1)
    finally:
        # Cleanup bastion tunnels
        if src_manager:
            src_manager.close_all_tunnels()
        if dst_manager:
            dst_manager.close_all_tunnels()
