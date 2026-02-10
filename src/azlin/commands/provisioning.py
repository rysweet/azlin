"""VM provisioning commands (new, vm, create, clone).

This module contains commands for creating and cloning VMs with their
configuration, validation, and orchestration logic.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig
from azlin.exceptions import (
    ProvisioningError,
    VMManagerError,
)
from azlin.remote_exec import RemoteExecutor
from azlin.modules.ssh_connector import SSHConfig, SSHConnector
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.vm_lifecycle import VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager
from azlin.vm_provisioning import PoolProvisioningResult, VMConfig, VMProvisioner
from azlin.vm_size_tiers import VMSizeTierError, VMSizeTiers

if TYPE_CHECKING:
    from azlin.cli import CLIOrchestrator
    from azlin.modules.vm_details import VMDetails

__all__ = ["clone", "create", "new", "vm"]

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def generate_vm_name(custom_name: str | None = None, command: str | None = None) -> str:
    """Generate VM name.

    Args:
        custom_name: Custom name from --name flag
        command: Command string for slug extraction

    Returns:
        VM name
    """
    if custom_name:
        return custom_name

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if command:
        slug = RemoteExecutor.extract_command_slug(command)
        return f"azlin-{timestamp}-{slug}"

    return f"azlin-{timestamp}"


def execute_command_on_vm(vm: VMInfo, command: str, ssh_key_path: Path) -> int:
    """Execute a command on a VM and display output.

    Args:
        vm: VM to execute command on
        command: Command to execute
        ssh_key_path: Path to SSH private key

    Returns:
        Exit code from command execution
    """
    if not vm.is_running():
        click.echo(
            f"Error: VM '{vm.name}' is not running (status: {vm.get_status_display()})", err=True
        )
        return 1

    if not vm.public_ip:
        click.echo(f"Error: VM '{vm.name}' has no public IP", err=True)
        return 1

    click.echo(f"\nExecuting on {vm.name} ({vm.public_ip}): {command}")
    click.echo("=" * 60)

    ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

    try:
        # Build SSH command with the remote command
        args = SSHConnector.build_ssh_command(ssh_config, command)

        # Execute and stream output
        result = subprocess.run(args)

        click.echo("=" * 60)
        if result.returncode == 0:
            click.echo(f"Command completed successfully on {vm.name}")
        else:
            click.echo(f"Command failed on {vm.name} with exit code {result.returncode}", err=True)

        return result.returncode

    except Exception as e:
        click.echo(f"Error executing command on {vm.name}: {e}", err=True)
        return 1


def _load_config_and_template(
    config: str | None, template: str | None
) -> tuple[AzlinConfig, VMTemplateConfig | None]:
    """Load configuration and template.

    Returns:
        Tuple of (azlin_config, template_config)
    """
    try:
        azlin_config = ConfigManager.load_config(config)
    except ConfigError:
        azlin_config = AzlinConfig()

    template_config = None
    if template:
        try:
            template_config = TemplateManager.get_template(template)
            click.echo(f"Using template: {template}")
        except TemplateError as e:
            click.echo(f"Error loading template: {e}", err=True)
            sys.exit(1)

    return azlin_config, template_config


def _resolve_vm_settings(
    resource_group: str | None,
    region: str | None,
    size_tier: str | None,
    vm_size: str | None,
    azlin_config: AzlinConfig,
    template_config: VMTemplateConfig | None,
) -> tuple[str | None, str, str]:
    """Resolve VM settings with precedence: CLI > config > template > defaults.

    Args:
        resource_group: Resource group from CLI
        region: Region from CLI
        size_tier: Size tier (s/m/l/xl) from CLI
        vm_size: Explicit VM size from CLI
        azlin_config: Loaded config
        template_config: Template config if provided

    Returns:
        Tuple of (final_rg, final_region, final_vm_size)
    """
    # Resolve VM size from tier or explicit size
    try:
        resolved_vm_size = VMSizeTiers.resolve_vm_size(size_tier, vm_size)
    except VMSizeTierError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if template_config:
        final_rg = resource_group or azlin_config.default_resource_group
        final_region = region or template_config.region
        final_vm_size = resolved_vm_size or template_config.vm_size
    else:
        final_rg = resource_group or azlin_config.default_resource_group
        final_region = region or azlin_config.default_region
        final_vm_size = resolved_vm_size or azlin_config.default_vm_size

    return final_rg, final_region, final_vm_size


def _validate_inputs(pool: int | None, repo: str | None) -> None:
    """Validate pool size and repo URL."""
    if pool and pool > 10:
        estimated_cost = pool * 0.10
        click.echo(f"\nWARNING: Creating {pool} VMs")
        click.echo(f"Estimated cost: ~${estimated_cost:.2f}/hour")
        click.echo("Continue? [y/N]: ", nl=False)
        response = input().lower()
        if response not in ["y", "yes"]:
            click.echo("Cancelled.")
            sys.exit(0)

    if repo and not repo.startswith("https://github.com/"):
        click.echo("Error: Invalid GitHub URL. Must start with https://github.com/", err=True)
        sys.exit(1)


def _execute_command_mode(
    orchestrator: CLIOrchestrator,
    command: str,
    session_name: str | None = None,
    config: str | None = None,
) -> None:
    """Execute VM provisioning and command execution."""
    click.echo(f"\nCommand to execute: {command}")
    click.echo("Provisioning VM first...\n")

    orchestrator.auto_connect = False
    exit_code = orchestrator.run()

    # Save session name mapping if provided
    if session_name and orchestrator.vm_details:
        try:
            ConfigManager.set_session_name(orchestrator.vm_details.name, session_name, config)
            logger.debug(
                f"Saved session name mapping: {orchestrator.vm_details.name} -> {session_name}"
            )
        except ConfigError as e:
            logger.warning(f"Failed to save session name: {e}")

    if exit_code == 0 and orchestrator.vm_details:
        vm_info = VMInfo(
            name=orchestrator.vm_details.name,
            resource_group=orchestrator.vm_details.resource_group,
            location=orchestrator.vm_details.location,
            power_state="VM running",
            public_ip=orchestrator.vm_details.public_ip,
            vm_size=orchestrator.vm_details.size,
        )
        if orchestrator.ssh_keys is None:
            click.echo("Error: SSH keys not initialized", err=True)
            sys.exit(1)
        cmd_exit_code = execute_command_on_vm(vm_info, command, orchestrator.ssh_keys)
        sys.exit(cmd_exit_code)
    else:
        click.echo(f"\nProvisioning failed with exit code {exit_code}", err=True)
        sys.exit(exit_code)


def _provision_pool(
    orchestrator: CLIOrchestrator,
    pool: int,
    vm_name: str,
    final_rg: str | None,
    final_region: str,
    final_vm_size: str,
    session_name: str | None = None,
    config: str | None = None,
) -> None:
    """Provision pool of VMs in parallel."""
    click.echo(f"\nProvisioning pool of {pool} VMs in parallel...")

    ssh_key_pair = SSHKeyManager.ensure_key_exists()

    # Check bastion availability once for the entire pool
    # This ensures consistent behavior with single VM provisioning
    rg_for_bastion_check = final_rg or f"azlin-rg-{int(time.time())}"
    use_bastion, bastion_info = orchestrator._check_bastion_availability(
        rg_for_bastion_check, f"{vm_name} (pool)"
    )
    orchestrator.bastion_info = bastion_info  # Store for later use

    # Determine if public IP should be created
    # Public IP is disabled when using bastion
    public_ip_enabled = not use_bastion

    configs: list[VMConfig] = []
    for i in range(pool):
        vm_name_pool = f"{vm_name}-{i + 1:02d}"
        config_item = orchestrator.provisioner.create_vm_config(
            name=vm_name_pool,
            resource_group=rg_for_bastion_check,
            location=final_region,
            size=final_vm_size,
            ssh_public_key=ssh_key_pair.public_key_content,
            session_name=f"{session_name}-{i + 1:02d}" if session_name else None,
            public_ip_enabled=public_ip_enabled,
        )
        configs.append(config_item)

    try:
        result = orchestrator.provisioner.provision_vm_pool(
            configs,
            progress_callback=lambda msg: click.echo(f"  {msg}"),
            max_workers=min(10, pool),
        )

        # Save session names for successfully provisioned VMs in pool
        if session_name and result.successful:
            for i, vm_details in enumerate(result.successful, 1):
                pool_session_name = f"{session_name}-{i:02d}"
                try:
                    ConfigManager.set_session_name(vm_details.name, pool_session_name, config)
                    logger.debug(f"Saved session name: {vm_details.name} -> {pool_session_name}")
                except ConfigError as e:
                    logger.warning(f"Failed to save session name for {vm_details.name}: {e}")

        _display_pool_results(result)
        sys.exit(0 if result.any_succeeded else 1)
    except ProvisioningError as e:
        click.echo(f"\nPool provisioning failed completely: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        sys.exit(1)


def _display_pool_results(result: PoolProvisioningResult) -> None:
    """Display pool provisioning results."""
    click.echo(f"\n{result.get_summary()}")

    if result.successful:
        click.echo("\nSuccessfully Provisioned VMs:")
        click.echo("=" * 80)
        for vm in result.successful:
            # Display 'Bastion' instead of empty string when no public IP
            ip_display = vm.public_ip if vm.public_ip else "(Bastion)"
            click.echo(f"  {vm.name:<30} {ip_display:<15} {vm.location}")
        click.echo("=" * 80)

    if result.failed:
        click.echo("\nFailed VMs:")
        click.echo("=" * 80)
        for failure in result.failed:
            click.echo(f"  {failure.config.name:<30} {failure.error_type:<20} {failure.error[:40]}")
        click.echo("=" * 80)

    if result.rg_failures:
        click.echo("\nResource Group Failures:")
        for rg_fail in result.rg_failures:
            click.echo(f"  {rg_fail.rg_name}: {rg_fail.error}")


def _validate_config_path(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Validate that config file parent directory exists.

    Args:
        ctx: Click context
        param: Click parameter
        value: Config file path value

    Returns:
        The config path value if valid

    Raises:
        click.BadParameter: If parent directory doesn't exist
    """
    if value is None:
        return value

    config_path = Path(value)
    parent_dir = config_path.parent

    # Check if parent directory exists
    if not parent_dir.exists():
        raise click.BadParameter(
            f"Parent directory does not exist: {parent_dir}",
            ctx=ctx,
            param=param,
        )

    return value


# ============================================================================
# CLONE COMMAND HELPERS
# ============================================================================


def _validate_and_resolve_source_vm(source_vm: str, rg: str, config: str | None) -> VMInfo:
    """Validate and resolve source VM, showing error if not found."""
    click.echo(f"Resolving source VM: {source_vm}")
    source_vm_info = _resolve_source_vm(source_vm, rg, config)

    if not source_vm_info:
        click.echo(f"Error: Source VM '{source_vm}' not found", err=True)
        # Show available VMs
        vms = VMManager.list_vms(rg)
        if vms:
            click.echo("\nAvailable VMs:", err=True)
            for vm in vms:
                display_name = vm.session_name or vm.name
                click.echo(f"  - {display_name} ({vm.name})", err=True)
        sys.exit(1)

    click.echo(f"Source VM: {source_vm_info.name} ({source_vm_info.public_ip})")
    click.echo(f"VM size: {source_vm_info.vm_size}")
    click.echo(f"Region: {source_vm_info.location}")
    return source_vm_info


def _ensure_source_vm_running(source_vm_info: VMInfo, rg: str) -> VMInfo:
    """Ensure source VM is running, start if needed."""
    if not source_vm_info.is_running():
        click.echo(f"Warning: Source VM is not running (state: {source_vm_info.power_state})")
        click.echo("Starting source VM...")
        controller = VMLifecycleController()
        controller.start_vm(source_vm_info.name, rg)
        click.echo("Source VM started successfully")
        # Refresh VM info
        refreshed_vm = VMManager.get_vm(source_vm_info.name, rg)
        if refreshed_vm is None:
            click.echo("Error: Failed to refresh VM info after starting", err=True)
            sys.exit(1)
        return refreshed_vm
    return source_vm_info


def _provision_clone_vms(
    clone_configs: list[VMConfig], num_replicas: int
) -> PoolProvisioningResult:
    """Provision clone VMs in parallel."""
    click.echo(f"\nProvisioning {num_replicas} VM(s)...")
    provisioner = VMProvisioner()

    def progress_callback(msg: str):
        click.echo(f"  {msg}")

    result = provisioner.provision_vm_pool(
        configs=clone_configs,
        progress_callback=progress_callback,
        max_workers=min(10, num_replicas),
    )

    # Check provisioning results
    if not result.any_succeeded:
        click.echo("\nError: All VM provisioning failed", err=True)
        for failure in result.failed[:3]:  # Show first 3 failures
            click.echo(f"  {failure.config.name}: {failure.error}", err=True)
        sys.exit(1)

    if result.partial_success:
        click.echo(
            f"\nWarning: Partial success - {result.success_count}/{result.total_requested} VMs provisioned"
        )

    click.echo(f"\nSuccessfully provisioned {result.success_count} VM(s)")
    return result


def _display_clone_results(
    result: PoolProvisioningResult,
    copy_results: dict[str, bool],
    session_prefix: str | None,
    config: str | None,
) -> None:
    """Display final clone operation results."""
    successful_copies = sum(1 for success in copy_results.values() if success)

    click.echo("\n" + "=" * 70)
    click.echo(f"Clone operation complete: {successful_copies}/{len(result.successful)} successful")
    click.echo("=" * 70)
    click.echo("\nCloned VMs:")
    for vm in result.successful:
        session_name = ConfigManager.get_session_name(vm.name, config) if session_prefix else None
        copy_status = "✓" if copy_results.get(vm.name, False) else "✗"
        display_name = f"{session_name} ({vm.name})" if session_name else vm.name
        click.echo(f"  {copy_status} {display_name}")
        click.echo(f"     IP: {vm.public_ip}")
        click.echo(f"     Size: {vm.size}, Region: {vm.location}")

    if result.failed:
        click.echo("\nFailed provisioning:")
        for failure in result.failed:
            click.echo(f"  ✗ {failure.config.name}: {failure.error}")

    # Show connection instructions
    if result.successful:
        first_clone = result.successful[0]
        first_session = (
            ConfigManager.get_session_name(first_clone.name, config) if session_prefix else None
        )
        connect_target = first_session or first_clone.name
        click.echo("\nTo connect to first clone:")
        click.echo(f"  azlin connect {connect_target}")


def _resolve_source_vm(
    source_vm: str, resource_group: str, config_path: str | None = None
) -> VMInfo | None:
    """Resolve source VM by session name or VM name.

    Args:
        source_vm: Source VM identifier (session name or VM name)
        resource_group: Resource group name
        config_path: Optional config file path

    Returns:
        VMInfo object or None if not found
    """
    # Try as VM name first
    vm_info = VMManager.get_vm(source_vm, resource_group)
    if vm_info:
        return vm_info

    # Try as session name
    vm_name = ConfigManager.get_vm_name_by_session(source_vm, config_path)
    if vm_name:
        vm_info = VMManager.get_vm(vm_name, resource_group)
        if vm_info:
            return vm_info

    # Try finding in list (case-insensitive match)
    all_vms = VMManager.list_vms(resource_group)
    for vm in all_vms:
        if vm.name.lower() == source_vm.lower():
            return vm
        if vm.session_name and vm.session_name.lower() == source_vm.lower():
            return vm

    return None


def _generate_clone_configs(
    source_vm: VMInfo,
    num_replicas: int,
    vm_size: str | None,
    region: str | None,
) -> list[VMConfig]:
    """Generate VMConfig objects for clones.

    Args:
        source_vm: Source VM information
        num_replicas: Number of clones to create
        vm_size: Custom VM size (None = use source size)
        region: Custom region (None = use source region)

    Returns:
        List of VMConfig objects
    """
    # Use custom or source attributes
    clone_size = vm_size or source_vm.vm_size or "Standard_B2s"  # Default if both are None
    clone_region = region or source_vm.location

    # Generate unique VM names with timestamp
    timestamp = int(time.time())
    configs: list[Any] = []

    for i in range(1, num_replicas + 1):
        vm_name = f"azlin-vm-{timestamp}-{i}"
        config = VMConfig(
            name=vm_name,
            resource_group=source_vm.resource_group,
            location=clone_region,
            size=clone_size,
            image="Ubuntu2204",
            ssh_public_key=None,  # Will use default SSH keys
            admin_username="azureuser",
            disable_password_auth=True,
        )
        configs.append(config)

    return configs


def _copy_home_directories(
    source_vm: VMInfo,
    clone_vms: list[VMDetails],
    ssh_key_path: str,
    max_workers: int = 5,
) -> dict[str, bool]:
    """Copy home directories from source to clones in parallel.

    Args:
        source_vm: Source VM information
        clone_vms: List of cloned VM details
        ssh_key_path: Path to SSH private key
        max_workers: Maximum parallel workers

    Returns:
        Dictionary mapping VM name to success status
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def copy_to_vm(clone_vm: VMDetails) -> tuple[str, bool]:
        """Copy home directory to a single clone.

        Uses localhost as staging area to avoid rsync remote-to-remote limitation.
        Two-stage copy: source -> localhost -> destination.
        """
        import shutil
        import tempfile

        temp_dir = None
        try:
            # Create temporary directory for staging
            temp_dir = Path(tempfile.mkdtemp(prefix="azlin_clone_"))

            click.echo(f"  Copying to {clone_vm.name}...")

            # Stage 1: Copy from source VM to localhost
            source_path = f"azureuser@{source_vm.public_ip}:/home/azureuser/"
            rsync_from_source = [
                "rsync",
                "-az",  # Archive mode, compress
                "-e",
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10",
                source_path,
                str(temp_dir) + "/",
            ]

            result1 = subprocess.run(
                rsync_from_source,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for download
            )

            if result1.returncode != 0:
                click.echo(f"  ✗ {clone_vm.name} download failed: {result1.stderr[:100]}", err=True)
                return (clone_vm.name, False)

            # Stage 2: Copy from localhost to destination VM
            dest_path = f"azureuser@{clone_vm.public_ip}:/home/azureuser/"
            rsync_to_dest = [
                "rsync",
                "-az",  # Archive mode, compress
                "-e",
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10",
                str(temp_dir) + "/",
                dest_path,
            ]

            result2 = subprocess.run(
                rsync_to_dest,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for upload
            )

            if result2.returncode == 0:
                click.echo(f"  ✓ {clone_vm.name} copy complete")
                return (clone_vm.name, True)
            click.echo(f"  ✗ {clone_vm.name} upload failed: {result2.stderr[:100]}", err=True)
            return (clone_vm.name, False)

        except subprocess.TimeoutExpired:
            click.echo(f"  ✗ {clone_vm.name} copy timeout", err=True)
            return (clone_vm.name, False)
        except Exception as e:
            click.echo(f"  ✗ {clone_vm.name} copy error: {e}", err=True)
            return (clone_vm.name, False)
        finally:
            # Clean up temporary directory
            if temp_dir and temp_dir.exists():
                with contextlib.suppress(Exception):
                    shutil.rmtree(temp_dir)

    # Execute copies in parallel
    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(copy_to_vm, clone): clone for clone in clone_vms}

        for future in as_completed(futures):
            vm_name, success = future.result()
            results[vm_name] = success

    return results


def _set_clone_session_names(
    clone_vms: list[VMDetails],
    session_prefix: str,
    config_path: str | None = None,
) -> None:
    """Set session names for cloned VMs.

    Args:
        clone_vms: List of cloned VM details
        session_prefix: Session name prefix
        config_path: Optional config file path
    """
    if len(clone_vms) == 1:
        # Single clone: use prefix without number
        ConfigManager.set_session_name(clone_vms[0].name, session_prefix, config_path)
        click.echo(f"  Set session name: {session_prefix} -> {clone_vms[0].name}")
    else:
        # Multiple clones: use numbered suffixes
        for i, vm in enumerate(clone_vms, 1):
            session_name = f"{session_prefix}-{i}"
            ConfigManager.set_session_name(vm.name, session_name, config_path)
            click.echo(f"  Set session name: {session_name} -> {vm.name}")


# ============================================================================
# COMMAND IMPLEMENTATIONS
# ============================================================================


@click.command(name="new")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option(
    "--size",
    help="VM size tier: s(mall), m(edium), l(arge), xl (default: l)",
    type=click.Choice(["s", "m", "l", "xl"], case_sensitive=False),
)
@click.option("--vm-size", help="Azure VM size (overrides --size)", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option(
    "--config", help="Config file path", type=click.Path(), callback=_validate_config_path
)
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
@click.option(
    "--no-nfs",
    is_flag=True,
    help="Skip NFS storage mounting (use local home directory only)",
)
@click.option(
    "--no-bastion", help="Skip bastion auto-detection and always create public IP", is_flag=True
)
@click.option("--bastion-name", help="Explicit bastion host name to use for private VM", type=str)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Accept all defaults and confirmations (non-interactive mode)",
)
@click.option(
    "--home-disk-size",
    type=int,
    help="Size of separate /home disk in GB (default: 100)",
)
@click.option(
    "--no-home-disk",
    is_flag=True,
    help="Disable separate /home disk (use OS disk)",
)
def new(
    ctx: click.Context,
    repo: str | None,
    size: str | None,
    vm_size: str | None,
    region: str | None,
    resource_group: str | None,
    name: str | None,
    pool: int | None,
    no_auto_connect: bool,
    config: str | None,
    template: str | None,
    nfs_storage: str | None,
    no_nfs: bool,
    no_bastion: bool,
    bastion_name: str | None,
    yes: bool,
    home_disk_size: int | None,
    no_home_disk: bool,
) -> None:
    """Provision a new Azure VM with development tools.

    SSH keys are automatically stored in Azure Key Vault for cross-system access.

    Creates a new Ubuntu VM in Azure with all development tools pre-installed.
    Optionally connects via SSH and clones a GitHub repository.

    \b
    EXAMPLES:
        # Provision basic VM (uses size 'l' = 128GB RAM)
        $ azlin new

        # Provision with size tier (s=8GB, m=64GB, l=128GB, xl=256GB)
        $ azlin new --size m     # Medium: 64GB RAM
        $ azlin new --size s     # Small: 8GB RAM (original default)
        $ azlin new --size xl    # Extra-large: 256GB RAM

        # Provision with exact VM size (overrides --size)
        $ azlin new --vm-size Standard_E8as_v5

        # Provision with custom name
        $ azlin new --name my-dev-vm --size m

        # Provision and clone repository
        $ azlin new --repo https://github.com/owner/repo

        # Provision 5 VMs in parallel
        $ azlin new --pool 5 --size l

        # Provision from template
        $ azlin new --template dev-vm

        # Provision with NFS storage for shared home directory
        $ azlin new --nfs-storage myteam-shared --name worker-1

        # Provision and execute command
        $ azlin new --size xl -- python train.py
    """
    # Lazy import to avoid circular dependency
    from azlin.cli import CLIOrchestrator

    # Check for passthrough command
    command = None
    if ctx.obj and "passthrough_command" in ctx.obj:
        command = ctx.obj["passthrough_command"]
    elif ctx.args:
        command = " ".join(ctx.args)

    # Load configuration and template
    azlin_config, template_config = _load_config_and_template(config, template)

    # Resolve VM settings
    final_rg, final_region, final_vm_size = _resolve_vm_settings(
        resource_group, region, size, vm_size, azlin_config, template_config
    )

    # Generate VM name (don't use custom name for Azure VM resource name)
    vm_name = generate_vm_name(None, command)

    # Validate inputs
    _validate_inputs(pool, repo)

    # Create orchestrator
    orchestrator = CLIOrchestrator(
        repo=repo,
        vm_size=final_vm_size,
        region=final_region,
        resource_group=final_rg,
        auto_connect=not no_auto_connect,
        config_file=config,
        nfs_storage=nfs_storage,
        no_nfs=no_nfs,
        session_name=name,
        no_bastion=no_bastion,
        bastion_name=bastion_name,
        auto_approve=yes,
        home_disk_size=home_disk_size,
        no_home_disk=no_home_disk,
    )

    # Update config state (resource group only, session name saved after VM creation)
    if final_rg:
        try:
            ConfigManager.update_config(config, default_resource_group=final_rg)
        except ConfigError as e:
            logger.debug(f"Failed to update config: {e}")

    # Handle command execution mode
    if command and not pool:
        _execute_command_mode(orchestrator, command, name, config)

    # Handle pool provisioning
    if pool and pool > 1:
        _provision_pool(
            orchestrator, pool, vm_name, final_rg, final_region, final_vm_size, name, config
        )

    # Standard single VM provisioning
    exit_code = orchestrator.run()

    # Save session name mapping AFTER VM creation (now we have actual VM name)
    if name and orchestrator.vm_details:
        try:
            actual_vm_name = orchestrator.vm_details.name
            ConfigManager.set_session_name(actual_vm_name, name, config)
            logger.debug(f"Saved session name mapping: {actual_vm_name} -> {name}")
        except ConfigError as e:
            logger.warning(f"Failed to save session name: {e}")

    sys.exit(exit_code)


@click.command(name="vm")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
@click.option(
    "--no-bastion", help="Skip bastion auto-detection and always create public IP", is_flag=True
)
@click.option("--bastion-name", help="Explicit bastion host name to use for private VM", type=str)
def vm(ctx: click.Context, **kwargs: Any) -> Any:
    """Alias for 'new' command. Provision a new Azure VM."""
    return ctx.invoke(new, **kwargs)


@click.command(name="create")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
@click.option(
    "--no-bastion", help="Skip bastion auto-detection and always create public IP", is_flag=True
)
@click.option("--bastion-name", help="Explicit bastion host name to use for private VM", type=str)
def create(ctx: click.Context, **kwargs: Any) -> Any:
    """Alias for 'new' command. Provision a new Azure VM."""
    return ctx.invoke(new, **kwargs)


@click.command()
@click.argument("source_vm", type=str)
@click.option("--num-replicas", type=int, default=1, help="Number of clones to create (default: 1)")
@click.option("--session-prefix", type=str, help="Session name prefix for clones")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--vm-size", help="VM size for clones (default: same as source)", type=str)
@click.option("--region", help="Azure region (default: same as source)", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def clone(
    source_vm: str,
    num_replicas: int,
    session_prefix: str | None,
    resource_group: str | None,
    vm_size: str | None,
    region: str | None,
    config: str | None,
):
    """Clone a VM with its home directory contents.

    Creates new VM(s) and copies the entire home directory from the source VM.
    Useful for creating development environments, parallel testing, or team onboarding.

    \b
    Examples:
        # Clone single VM
        azlin clone amplihack

        # Clone with custom session name
        azlin clone amplihack --session-prefix dev-env

        # Clone multiple replicas
        azlin clone amplihack --num-replicas 3 --session-prefix worker
        # Creates: worker-1, worker-2, worker-3

        # Clone with specific VM size
        azlin clone my-vm --vm-size Standard_D4s_v3

    The source VM can be specified by VM name or session name.
    Home directory security filters are applied (no SSH keys, credentials, etc.).
    """
    try:
        # Validate num-replicas
        if num_replicas < 1:
            click.echo("Error: num-replicas must be >= 1", err=True)
            sys.exit(1)

        # Load configuration and get resource group
        cfg = ConfigManager.load_config(config)
        rg = resource_group or cfg.default_resource_group
        if not rg:
            click.echo("Error: No resource group specified and no default configured", err=True)
            sys.exit(1)

        # Resolve and validate source VM
        source_vm_info = _validate_and_resolve_source_vm(source_vm, rg, config)

        # Ensure source VM is running
        source_vm_info = _ensure_source_vm_running(source_vm_info, rg)

        # Generate and display clone configurations
        click.echo(f"\nGenerating configurations for {num_replicas} clone(s)...")
        clone_configs = _generate_clone_configs(
            source_vm=source_vm_info,
            num_replicas=num_replicas,
            vm_size=vm_size,
            region=region,
        )

        click.echo("\nClone plan:")
        for i, clone_config in enumerate(clone_configs, 1):
            click.echo(f"  Clone {i}: {clone_config.name}")
            click.echo(f"    Size: {clone_config.size}")
            click.echo(f"    Region: {clone_config.location}")

        # Provision VMs
        result = _provision_clone_vms(clone_configs, num_replicas)

        # Copy home directories
        click.echo("\nCopying home directories from source VM...")
        ssh_key_path = Path.home() / ".ssh" / "id_rsa"
        copy_results = _copy_home_directories(
            source_vm=source_vm_info,
            clone_vms=result.successful,
            ssh_key_path=str(ssh_key_path),
            max_workers=min(5, len(result.successful)),
        )

        # Check copy results
        failed_copies = len(copy_results) - sum(1 for success in copy_results.values() if success)
        if failed_copies > 0:
            click.echo(f"\nWarning: {failed_copies} home directory copy operations failed")

        # Set session names if prefix provided
        if session_prefix:
            click.echo(f"\nSetting session names with prefix: {session_prefix}")
            _set_clone_session_names(
                clone_vms=result.successful,
                session_prefix=session_prefix,
                config_path=config,
            )

        # Display results
        _display_clone_results(result, copy_results, session_prefix, config)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ProvisioningError as e:
        click.echo(f"Provisioning error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nClone operation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in clone command")
        sys.exit(1)
