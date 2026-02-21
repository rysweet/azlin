"""File transfer commands for azlin CLI.

This module provides file copy, dotfile sync, and SSH key sync commands.
Extracted from connectivity.py for better modularity (Issue #1799).
"""

import logging
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigError, ConfigManager
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.file_transfer import FileTransfer, FileTransferError, TransferEndpoint
from azlin.modules.file_transfer.path_parser import PathParser
from azlin.modules.file_transfer.session_manager import SessionManager
from azlin.modules.home_sync import HomeSyncError, HomeSyncManager
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager, SSHKeyPair
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


# =============================================================================
# Sync Helper Functions
# =============================================================================


def _get_sync_vm_by_name(vm_name: str, rg: str):
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


def _select_sync_vm_interactive(rg: str):
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


def _perform_sync(ssh_config, dry_run: bool) -> None:
    """Perform the actual sync operation.

    Args:
        ssh_config: SSH configuration for connection
        dry_run: Whether to perform dry run

    Raises:
        SystemExit: On sync errors
    """

    def progress_callback(msg: str):
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


# =============================================================================
# Sync Command
# =============================================================================


@click.command(name="sync")
@click.option("--vm-name", help="VM name to sync to", type=str)
@click.option("--dry-run", help="Show what would be synced", is_flag=True)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def sync(vm_name: str | None, dry_run: bool, resource_group: str | None, config: str | None):
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
# Sync-Keys Command
# =============================================================================


@click.command(name="sync-keys")
@click.argument("vm_name")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--ssh-user", default="azureuser", help="SSH username (default: azureuser)")
@click.option("--timeout", default=60, help="Timeout in seconds (default: 60)")
@click.option("--config", help="Config file path", type=click.Path())
def sync_keys(
    vm_name: str, resource_group: str | None, ssh_user: str, timeout: int, config: str | None
):
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
# Copy Command (cp)
# =============================================================================


@click.command(name="cp")
@click.argument("args", nargs=-1, required=True)
@click.option("--dry-run", is_flag=True, help="Show what would be transferred")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def cp(
    args: tuple[str, ...],
    dry_run: bool,
    resource_group: str | None,
    config: str | None,
):
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


__all__ = ["cp", "sync", "sync_keys"]
