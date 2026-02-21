"""CLI Helper Functions.

Helper functions extracted from cli.py to reduce its size and improve maintainability.

This module contains:
- VM operations helpers
- Configuration and validation helpers
- Display and UI helpers
- Sync operation helpers
- Deletion operation helpers
- Clone operation helpers
- NLP/AI operation helpers
- SSH and key management helpers
- Batch operation helpers

Public API exported via __all__.
"""

import contextlib
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from azlin.agentic import (
    ClarificationResult,
    CommandExecutionError,
    CommandExecutor,
    IntentParseError,
    IntentParser,
    RequestClarificationError,
    RequestClarifier,
    ResultValidator,
)
from azlin.auth_models import AuthConfig, AuthMethod
from azlin.batch_executor import BatchResult, BatchSelector
from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.context_manager import ContextManager
from azlin.key_rotator import KeyRotationError, SSHKeyRotator
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.cli_detector import CLIDetector
from azlin.modules.cli_installer import CLIInstaller, InstallStatus
from azlin.modules.home_sync import HomeSyncManager
from azlin.modules.interaction_handler import CLIInteractionHandler
from azlin.modules.snapshot_manager import SnapshotError, SnapshotManager
from azlin.modules.ssh_connector import SSHConfig, SSHConnector
from azlin.modules.ssh_key_vault import KeyVaultError, create_key_vault_manager
from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyPair
from azlin.modules.ssh_routing_resolver import SSHRoute, SSHRoutingResolver
from azlin.orchestrator import CLIOrchestrator
from azlin.remote_exec import (
    RemoteExecutor,
)
from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig
from azlin.vm_connector import VMConnector
from azlin.vm_lifecycle import DeletionSummary, VMLifecycleManager
from azlin.vm_lifecycle_control import VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
from azlin.vm_provisioning import (
    PoolProvisioningResult,
    ProvisioningError,
    VMConfig,
    VMDetails,
    VMProvisioner,
)
from azlin.vm_size_tiers import VMSizeTierError, VMSizeTiers

logger = logging.getLogger(__name__)


class SSHConfigBuilder:
    """Builder for SSH configurations with bastion awareness.

    This class provides static methods for creating SSH configurations
    with automatic bastion routing support.
    """

    @staticmethod
    def build_for_vm(
        vm: VMInfo,
        ssh_key_path: Path,
        bastion_manager=None,
        auto_bastion: bool = True,
        skip_interactive: bool = True,
    ) -> SSHConfig:
        """Build SSH config for a single VM.

        Args:
            vm: VM information
            ssh_key_path: Path to SSH private key
            bastion_manager: Optional bastion manager instance
            auto_bastion: Automatically detect and use bastion (default: True)
            skip_interactive: Skip interactive prompts (default: True)

        Returns:
            SSHConfig instance

        Raises:
            ValueError: If VM requires bastion but no bastion manager provided
            ValueError: If VM has no IP addresses
        """
        # Check if VM is reachable
        if not SSHConfigBuilder.is_reachable(vm):
            if vm.power_state != "VM running":
                raise ValueError(f"VM {vm.name} is not running")
            raise ValueError(f"VM {vm.name} has no IP addresses")

        # Direct SSH if VM has public IP
        if SSHConfigBuilder.has_direct_connectivity(vm):
            # Type assertion: has_direct_connectivity ensures public_ip is not None
            assert vm.public_ip is not None
            return SSHConfig(
                host=vm.public_ip,
                port=22,
                user="azureuser",
                key_path=ssh_key_path,
            )

        # Bastion required for private-only VM
        if not auto_bastion or bastion_manager is None:
            raise ValueError(f"Bastion manager required for VM {vm.name} without public IP")

        # Create bastion tunnel
        tunnel = bastion_manager.create_tunnel(
            vm_name=vm.name,
            resource_group=vm.resource_group,
            private_ip=vm.private_ip,
            skip_interactive=skip_interactive,
        )

        return SSHConfig(
            host="127.0.0.1",
            port=tunnel.local_port,
            user="azureuser",
            key_path=ssh_key_path,
        )

    @staticmethod
    def build_for_vms(
        vms: list[VMInfo],
        ssh_key_path: Path,
        bastion_manager=None,
        auto_bastion: bool = True,
        skip_interactive: bool = True,
    ) -> list[SSHConfig]:
        """Build SSH configs for multiple VMs.

        Args:
            vms: List of VM information
            ssh_key_path: Path to SSH private key
            bastion_manager: Optional bastion manager instance
            auto_bastion: Automatically detect and use bastion (default: True)
            skip_interactive: Skip interactive prompts (default: True)

        Returns:
            List of SSHConfig instances for reachable VMs
        """
        configs = []
        for vm in vms:
            try:
                config = SSHConfigBuilder.build_for_vm(
                    vm=vm,
                    ssh_key_path=ssh_key_path,
                    bastion_manager=bastion_manager,
                    auto_bastion=auto_bastion,
                    skip_interactive=skip_interactive,
                )
                configs.append(config)
            except (ValueError, Exception) as e:
                logger.debug(f"Skipping VM {vm.name}: {e}")
                continue
        return configs

    @staticmethod
    def has_direct_connectivity(vm: VMInfo) -> bool:
        """Check if VM has direct SSH connectivity (public IP).

        Args:
            vm: VM information

        Returns:
            True if VM has a public IP, False otherwise
        """
        return bool(vm.public_ip and vm.public_ip.strip())

    @staticmethod
    def is_reachable(vm: VMInfo) -> bool:
        """Check if VM is reachable via SSH.

        A VM is reachable if:
        - It is running
        - It has at least one IP address (public or private)

        Args:
            vm: VM information

        Returns:
            True if VM is reachable, False otherwise
        """
        if vm.power_state != "VM running":
            return False

        has_ip = bool(
            (vm.public_ip and vm.public_ip.strip()) or (vm.private_ip and vm.private_ip.strip())
        )
        return has_ip

    @staticmethod
    def filter_reachable_vms(vms: list[VMInfo]) -> list[VMInfo]:
        """Filter list to only reachable VMs.

        Args:
            vms: List of VM information

        Returns:
            List of reachable VMs
        """
        return [vm for vm in vms if SSHConfigBuilder.is_reachable(vm)]


def get_ssh_configs_for_vms(
    vms: list[VMInfo],
    ssh_key_path: Path | None = None,
    auto_bastion: bool = True,
    skip_interactive: bool = True,
    show_summary: bool = True,
) -> tuple[list[SSHConfig], list[SSHRoute]]:
    """Get SSH configs for VMs with automatic bastion routing.

    This helper function:
    1. Resolves SSH routing for each VM (direct or bastion)
    2. Creates bastion tunnels where needed
    3. Returns SSH configs and routes

    Args:
        vms: List of VM information
        ssh_key_path: Path to SSH private key (uses default if None)
        auto_bastion: Automatically detect and use bastion (default: True)
        skip_interactive: Skip interactive prompts (default: True for batch)
        show_summary: Print summary of routing decisions (default: True)

    Returns:
        Tuple of (ssh_configs, routes)
        Routes contain bastion manager references for automatic cleanup via atexit

    Example:
        >>> configs, routes = get_ssh_configs_for_vms(running_vms, key_path)
        >>> if not configs:
        ...     click.echo("No reachable VMs found.")
        ...     return
        >>> results = RemoteExecutor.execute_parallel(configs, "w")

    Note:
        VMs without connectivity are skipped gracefully.
        Bastion tunnels are automatically cleaned up via BastionManager's atexit handler.
    """
    if not vms:
        return [], []

    # Ensure ssh_key_path is provided
    resolved_key_path: Path
    if ssh_key_path is None:
        from azlin.modules.ssh_keys import SSHKeyManager

        ssh_keys = SSHKeyManager.ensure_key_exists()
        resolved_key_path = ssh_keys.private_path
    else:
        resolved_key_path = ssh_key_path

    # Resolve routing for all VMs
    routes = SSHRoutingResolver.resolve_routes_batch(
        vms=vms,
        ssh_key_path=resolved_key_path,
        auto_bastion=auto_bastion,
        skip_interactive=skip_interactive,
    )

    # Separate reachable from unreachable
    reachable = [r for r in routes if r.ssh_config is not None]
    unreachable = [r for r in routes if r.ssh_config is None]

    # Show summary if requested
    if show_summary and (reachable or unreachable):
        _print_routing_summary(reachable, unreachable)

    # Extract SSH configs
    ssh_configs = [r.ssh_config for r in reachable if r.ssh_config]

    return ssh_configs, routes


def _print_routing_summary(reachable: list, unreachable: list) -> None:
    """Print summary of routing decisions.

    Args:
        reachable: List of reachable SSH routes
        unreachable: List of unreachable SSH routes
    """
    total = len(reachable) + len(unreachable)

    if not reachable and not unreachable:
        return

    # Count routing methods
    direct_count = sum(1 for r in reachable if r.routing_method == "direct")
    bastion_count = sum(1 for r in reachable if r.routing_method == "bastion")

    # Build summary message
    summary_parts = []

    if reachable:
        methods = []
        if direct_count:
            methods.append(f"{direct_count} direct")
        if bastion_count:
            methods.append(f"{bastion_count} via bastion")

        summary_parts.append(f"✓ {len(reachable)} reachable ({', '.join(methods)})")

    if unreachable:
        summary_parts.append(f"⊘ {len(unreachable)} unreachable")

    click.echo(f"Found {total} VMs: {', '.join(summary_parts)}\n")

    # Show details for unreachable VMs
    if unreachable:
        click.echo("Unreachable VMs:")
        for route in unreachable:
            reason = route.skip_reason or "Unknown reason"
            click.echo(f"  - {route.vm_name}: {reason}")
        click.echo()


# =============================================================================
# Extracted Helper Functions from cli.py
# =============================================================================


# VM Operations


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


def select_vm_for_command(vms: list[VMInfo], command: str) -> VMInfo | None:
    """Show interactive menu to select VM for command execution.

    Args:
        vms: List of available VMs
        command: Command that will be executed

    Returns:
        Selected VM or None to provision new VM
    """
    click.echo("\n" + "=" * 60)
    click.echo(f"Command to execute: {command}")
    click.echo("=" * 60)
    click.echo("\nAvailable VMs:")

    for idx, vm_info in enumerate(vms, 1):
        status = vm_info.get_status_display()
        ip = vm_info.public_ip or "No IP"
        click.echo(f"  {idx}. {vm_info.name} - {status} - {ip}")

    click.echo("  n. Create new VM and execute")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == "n":
        return None  # Signal to create new VM

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            return vms[idx]
        click.echo("Invalid selection")
        return None
    except ValueError:
        click.echo("Invalid input")
        return None


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


def _handle_vm_dry_run(vm_name: str, rg: str) -> None:
    """Handle dry-run mode for VM deletion."""
    vm = VMManager.get_vm(vm_name, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    click.echo(f"\n[DRY RUN] Would delete VM: {vm_name}")
    click.echo(f"  Resource Group: {rg}")
    click.echo(f"  Status:         {vm.get_status_display()}")
    click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
    click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
    click.echo("\nResources that would be deleted:")
    click.echo(f"  - VM: {vm_name}")
    click.echo("  - Associated NICs")
    click.echo("  - Associated disks")
    click.echo("  - Associated public IPs")


def _execute_vm_deletion(vm_name: str, rg: str, force: bool, config: str | None = None) -> None:
    """Execute VM deletion and display results."""
    vm = VMManager.get_vm(vm_name, rg)

    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not force and not _confirm_vm_deletion(vm):
        click.echo("Cancelled.")
        return

    click.echo(f"\nDeleting VM '{vm_name}'...")

    result = VMLifecycleManager.delete_vm(
        vm_name=vm_name, resource_group=rg, force=True, no_wait=False
    )

    if result.success:
        click.echo(f"\nSuccess! {result.message}")
        if result.resources_deleted:
            click.echo("\nDeleted resources:")
            for resource in result.resources_deleted:
                click.echo(f"  - {resource}")

        # Clean up SSH key from Key Vault
        _cleanup_key_from_vault(vm_name, config)

        # Clean up session name mapping if it exists
        try:
            if ConfigManager.delete_session_name(vm_name, config):
                click.echo(f"Removed session name mapping for '{vm_name}'")
        except ConfigError:
            pass  # Config cleanup is non-critical

        # Check for orphaned Bastion after VM deletion
        try:
            from azlin.modules.cleanup_orchestrator import CleanupOrchestrator

            cleanup_orch = CleanupOrchestrator(
                resource_group=rg, interaction_handler=CLIInteractionHandler()
            )

            orphaned = cleanup_orch.detect_orphaned_bastions()
            if orphaned:
                click.echo(f"\n🔍 Detected {len(orphaned)} orphaned Bastion host(s)")
                cleanup_results = cleanup_orch.cleanup_orphaned_bastions()

                for cleanup_result in cleanup_results:
                    if cleanup_result.was_successful():
                        click.echo(
                            click.style(
                                f"✓ Removed {cleanup_result.bastion_name} "
                                f"(saving ${cleanup_result.estimated_monthly_savings:.2f}/month)",
                                fg="green",
                            )
                        )
        except Exception as e:
            # Bastion cleanup is optional - don't fail the entire destroy
            logger.debug(f"Bastion cleanup check failed: {e}")

    else:
        click.echo(f"\nError: {result.message}", err=True)
        sys.exit(1)


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


# Configuration & Validation


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


def _update_config_state(
    config: str | None, final_rg: str | None, vm_name: str, name: str | None
) -> None:
    """Update config with resource group and session name."""
    if final_rg:
        try:
            ConfigManager.update_config(
                config, default_resource_group=final_rg, last_vm_name=vm_name
            )
            if name:
                ConfigManager.set_session_name(vm_name, name, config)
        except ConfigError as e:
            logger.debug(f"Failed to update config: {e}")


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
            for vm_item in vms:
                display_name = vm_item.session_name or vm_item.name
                click.echo(f"  - {display_name} ({vm_item.name})", err=True)
        sys.exit(1)

    return source_vm_info

    click.echo(f"Source VM: {source_vm_info.name} ({source_vm_info.public_ip})")
    click.echo(f"VM size: {source_vm_info.vm_size}")
    click.echo(f"Region: {source_vm_info.location}")
    return source_vm_info


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
    for vm_item in all_vms:
        if vm_item.name.lower() == source_vm.lower():
            return vm_item
        if vm_item.session_name and vm_item.session_name.lower() == source_vm.lower():
            return vm_item

    return None


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


# Display & UI


def show_interactive_menu(vms: list[VMInfo], ssh_key_path: Path) -> int | None:
    """Show interactive VM selection menu.

    Args:
        vms: List of available VMs
        ssh_key_path: Path to SSH private key

    Returns:
        Exit code or None to continue to provisioning
    """
    if not vms:
        click.echo("No VMs found. Create a new one? [Y/n]: ", nl=False)
        response = input().lower()
        if response in ["", "y", "yes"]:
            return None  # Continue to provisioning
        return 0

    # Auto-connect if only 1 VM
    if len(vms) == 1:
        vm = vms[0]
        click.echo(f"\nFound 1 VM: {vm.name}")
        click.echo(f"Status: {vm.get_status_display()}")
        click.echo(f"IP: {vm.public_ip}")
        click.echo("\nConnecting...")

        if vm.is_running() and vm.public_ip:
            ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

            # Sync home directory before connection (silent)
            _auto_sync_home_directory(ssh_config)

            return SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
        click.echo("VM is not running or has no public IP")
        return 1

    # Multiple VMs - show menu
    click.echo("\n" + "=" * 60)
    click.echo("Available VMs:")
    click.echo("=" * 60)

    for idx, vm_info in enumerate(vms, 1):
        status = vm_info.get_status_display()
        ip = vm_info.public_ip or "No IP"
        click.echo(f"  {idx}. {vm_info.name} - {status} - {ip}")

    click.echo("  n. Create new VM")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == "n":
        return None  # Continue to provisioning

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            vm = vms[idx]

            if not vm.is_running():
                click.echo(f"\nVM '{vm.name}' is not running.")
                click.echo(
                    f"Start it with: az vm start --name {vm.name} --resource-group {vm.resource_group}"
                )
                return 1

            if not vm.public_ip:
                click.echo(f"\nVM '{vm.name}' has no public IP.")
                return 1

            click.echo(f"\nConnecting to {vm.name}...")
            ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

            # Sync home directory before connection (silent)
            _auto_sync_home_directory(ssh_config)

            return SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
        click.echo("Invalid selection")
        return 1
    except ValueError:
        click.echo("Invalid input")
        return 1


def _display_pool_results(result: PoolProvisioningResult) -> None:
    """Display pool provisioning results."""
    click.echo(f"\n{result.get_summary()}")

    if result.successful:
        click.echo("\nSuccessfully Provisioned VMs:")
        click.echo("=" * 80)
        for vm_item in result.successful:
            # Display 'Bastion' instead of empty string when no public IP
            ip_display = vm_item.public_ip if vm_item.public_ip else "(Bastion)"
            click.echo(f"  {vm_item.name:<30} {ip_display:<15} {vm_item.location}")
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

            from azlin.commands import new

            ctx = Context(new)
            ctx.invoke(
                new,
                resource_group=rg,
                config=config,
                no_tmux=no_tmux,
                tmux_session=tmux_session,
            )
        click.echo("Cancelled.")
        sys.exit(0)

    click.echo("\nAvailable VMs:")
    click.echo("─" * 60)
    for i, vm_info in enumerate(vms, 1):
        status_emoji = "🟢" if vm_info.is_running() else "🔴"
        click.echo(
            f"{i:2}. {status_emoji} {vm_info.name:<30} {vm_info.location:<15} {vm_info.vm_size or 'unknown'}"
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

                from azlin.commands import new

                ctx = Context(new)
                ctx.invoke(
                    new,
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
    for vm_item in result.successful:
        session_name = (
            ConfigManager.get_session_name(vm_item.name, config) if session_prefix else None
        )
        copy_status = "✓" if copy_results.get(vm_item.name, False) else "✗"
        display_name = f"{session_name} ({vm_item.name})" if session_name else vm_item.name
        click.echo(f"  {copy_status} {display_name}")
        click.echo(f"     IP: {vm_item.public_ip}")
        click.echo(f"     Size: {vm_item.size}, Region: {vm_item.location}")

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


def _display_batch_summary(batch_result: BatchResult, operation_name: str) -> None:
    """Display batch operation summary."""
    click.echo("\n" + "=" * 80)
    click.echo(f"Batch {operation_name} Summary")
    click.echo("=" * 80)
    click.echo(batch_result.format_summary())
    click.echo("=" * 80)

    if batch_result.failed > 0:
        click.echo("\nFailed VMs:")
        for failure in batch_result.get_failures():
            click.echo(f"  - {failure.vm_name}: {failure.message}")


def _display_killall_results(summary: DeletionSummary) -> None:
    """Display killall operation results."""
    click.echo("\n" + "=" * 80)
    click.echo("Deletion Summary")
    click.echo("=" * 80)
    click.echo(f"Total VMs:     {summary.total}")
    click.echo(f"Succeeded:     {summary.succeeded}")
    click.echo(f"Failed:        {summary.failed}")
    click.echo("=" * 80)

    if summary.succeeded > 0:
        click.echo("\nSuccessfully deleted:")
        for result in summary.results:
            if result.success:
                click.echo(f"  - {result.vm_name}")

    if summary.failed > 0:
        click.echo("\nFailed to delete:")
        for result in summary.results:
            if not result.success:
                click.echo(f"  - {result.vm_name}: {result.message}")


# Sync Operations


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
    for idx, vm_info in enumerate(vms, 1):
        # Display public IP if available, otherwise show "(Bastion)"
        ip_display = vm_info.public_ip if vm_info.public_ip else f"{vm_info.private_ip} (Bastion)"
        click.echo(f"  {idx}. {vm_info.name} - {ip_display}")

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


# Deletion Operations


def _handle_delete_resource_group(rg: str, vm_name: str, force: bool, dry_run: bool) -> None:
    """Handle resource group deletion."""
    if dry_run:
        click.echo(f"\n[DRY RUN] Would delete entire resource group: {rg}")
        click.echo(f"This would delete ALL resources in the group, not just '{vm_name}'")
        return

    if not force:
        click.echo(f"\nWARNING: You are about to delete the ENTIRE resource group: {rg}")
        click.echo(f"This will delete ALL resources in the group, not just the VM '{vm_name}'!")
        click.echo("\nThis action cannot be undone.\n")

        confirm = input("Type the resource group name to confirm deletion: ").strip()
        if confirm != rg:
            click.echo("Cancelled. Resource group name did not match.")
            return

    click.echo(f"\nDeleting resource group '{rg}'...")

    cmd = ["az", "group", "delete", "--name", rg, "--yes"]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
        click.echo(f"\nSuccess! Resource group '{rg}' and all resources deleted.")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nError deleting resource group: {e.stderr}", err=True)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        click.echo("\nError: Resource group deletion timed out.", err=True)
        sys.exit(1)


def _confirm_vm_deletion(vm: VMInfo) -> bool:
    """Show VM details and get confirmation for deletion."""
    click.echo("\nVM Details:")
    click.echo(f"  Name:           {vm.name}")
    click.echo(f"  Resource Group: {vm.resource_group}")
    click.echo(f"  Status:         {vm.get_status_display()}")
    click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
    click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
    click.echo("\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
    click.echo("This action cannot be undone.\n")

    confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
    return confirm in ["y", "yes"]


def _confirm_killall(vms: list[Any], rg: str) -> bool:
    """Display VMs and get confirmation for bulk deletion."""
    click.echo(f"\nFound {len(vms)} VM(s) in resource group '{rg}':")
    click.echo("=" * 80)
    for vm_item in vms:
        status = vm_item.get_status_display()
        # Display IP with type indicator (Issue #492)
        ip = (
            f"{vm_item.public_ip} (Public)"
            if vm_item.public_ip
            else f"{vm_item.private_ip} (Private)"
            if vm_item.private_ip
            else "N/A"
        )
        click.echo(f"  {vm_item.name:<35} {status:<15} {ip:<15}")
    click.echo("=" * 80)

    click.echo(f"\nThis will delete all {len(vms)} VM(s) and their associated resources.")
    click.echo("This action cannot be undone.\n")

    confirm = input(f"Are you sure you want to delete {len(vms)} VM(s)? [y/N]: ").lower()
    return confirm in ["y", "yes"]


def _confirm_batch_operation(num_vms: int, operation: str, confirm: bool) -> bool:
    """Confirm batch operation with user. Returns True if should proceed."""
    if not confirm:
        click.echo(f"\nThis will {operation} {num_vms} VM(s).")
        confirm_input = input("Continue? [y/N]: ").lower()
        if confirm_input not in ["y", "yes"]:
            click.echo("Cancelled.")
            return False
    return True


# Clone Operations


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
    from azlin.vm_provisioning import VMConfig

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
        for i, clone_vm in enumerate(clone_vms, 1):
            session_name = f"{session_prefix}-{i}"
            ConfigManager.set_session_name(clone_vm.name, session_name, config_path)
            click.echo(f"  Set session name: {session_name} -> {clone_vm.name}")


# NLP/AI Operations


def _do_impl(
    request: str,
    dry_run: bool,
    yes: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """Shared implementation for natural language command execution.

    This function contains the core logic used by both 'azlin do' and 'azdoit'
    commands to parse and execute natural language requests.

    Args:
        request: Natural language request describing desired action
        dry_run: If True, show execution plan without running commands
        yes: If True, skip confirmation prompts
        resource_group: Azure resource group name (optional)
        config: Path to config file (optional)
        verbose: If True, show detailed execution information

    Raises:
        SystemExit: On various error conditions with appropriate exit codes
    """
    logger = logging.getLogger(__name__)

    try:
        # Check for API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            click.echo("Error: ANTHROPIC_API_KEY environment variable is required", err=True)
            click.echo("\nSet your API key with:", err=True)
            click.echo("  export ANTHROPIC_API_KEY=your-key-here", err=True)
            sys.exit(1)

        # Get resource group for context
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Build context for parser
        context = {}
        if rg:
            context["resource_group"] = rg
            # Get current VMs for context
            try:
                vms = VMManager.list_vms(rg, include_stopped=True)
                context["current_vms"] = [
                    {"name": v.name, "status": v.power_state, "ip": v.public_ip} for v in vms
                ]
            except Exception:
                # Context is optional - continue without VM list
                context["current_vms"] = []

        # Phase 1: Request Clarification (for complex/ambiguous requests)
        clarification_result: ClarificationResult | None = None
        clarified_request = request  # Use original by default

        # Check if clarification is disabled via environment variable
        disable_clarification = os.getenv("AZLIN_DISABLE_CLARIFICATION", "").lower() in (
            "1",
            "true",
            "yes",
        )

        # Track whether we need to parse intent (or if we can reuse initial_intent)
        initial_intent = None
        needs_parsing = True

        if not disable_clarification:
            try:
                clarifier = RequestClarifier()

                # Quick check if clarification might be needed
                # We'll do a fast initial parse to get confidence
                parser = IntentParser()
                initial_confidence = None
                commands_empty = False

                try:
                    initial_intent = parser.parse(request, context=context)
                    initial_confidence = initial_intent.get("confidence")
                    commands_empty = not initial_intent.get("azlin_commands", [])
                except Exception:
                    # If initial parse fails, we should definitely try clarification
                    initial_confidence = 0.0
                    commands_empty = True

                # Determine if clarification is needed
                if clarifier.should_clarify(
                    request, confidence=initial_confidence, commands_empty=commands_empty
                ):
                    if verbose:
                        click.echo("Complex request detected - initiating clarification phase...")

                    # Get clarification
                    clarification_result = clarifier.clarify(
                        request, context=context, auto_confirm=yes
                    )

                    # If user didn't confirm, exit
                    if not clarification_result.user_confirmed:
                        click.echo("Cancelled.")
                        sys.exit(0)

                    # Use clarified request for parsing
                    if clarification_result.clarified_request:
                        clarified_request = clarification_result.clarified_request
                        if verbose:
                            click.echo("\nUsing clarified request for command generation...")
                else:
                    # No clarification needed - reuse initial_intent to avoid double parsing
                    if initial_intent is not None:
                        needs_parsing = False
                        if verbose:
                            click.echo("Request is clear - proceeding with direct parsing...")

            except RequestClarificationError as e:
                # Clarification failed - fall back to direct parsing with warning
                # Always inform user when fallback occurs, not just in verbose mode
                click.echo(f"Clarification unavailable: {e}", err=True)
                click.echo("Continuing with direct parsing...", err=True)
                if verbose:
                    logger.exception("Clarification error details:")

        # Phase 2: Parse natural language intent (possibly clarified)
        # Only parse if we didn't already parse successfully above
        intent: dict[str, Any]
        if needs_parsing:
            if verbose:
                click.echo(f"\nParsing request: {clarified_request}")

            parser = IntentParser()
            intent = parser.parse(clarified_request, context=context)
        else:
            # Reuse the initial intent we already parsed
            if initial_intent is None:
                # This shouldn't happen, but if it does, parse again
                parser = IntentParser()
                intent = parser.parse(clarified_request, context=context)
            else:
                intent = initial_intent

        if verbose:
            click.echo("\nParsed Intent:")
            click.echo(f"  Type: {intent['intent']}")
            click.echo(f"  Confidence: {intent['confidence']:.1%}")
            if "explanation" in intent:
                click.echo(f"  Plan: {intent['explanation']}")

        # Check confidence (only warn if we didn't already clarify)
        if not clarification_result and intent["confidence"] < 0.7:
            click.echo(
                f"\nWarning: Low confidence ({intent['confidence']:.1%}) in understanding your request.",
                err=True,
            )
            if not yes and not click.confirm("Continue anyway?"):
                sys.exit(1)

        # Show commands to be executed
        click.echo("\nCommands to execute:")
        for i, cmd in enumerate(intent["azlin_commands"], 1):
            cmd_str = f"{cmd['command']} {' '.join(cmd['args'])}"
            click.echo(f"  {i}. {cmd_str}")

        if dry_run:
            click.echo("\n[DRY RUN] Would execute the above commands.")
            sys.exit(0)

        # Confirm execution
        if not yes and not click.confirm("\nExecute these commands?"):
            click.echo("Cancelled.")
            sys.exit(0)

        # Execute commands
        click.echo("\nExecuting commands...\n")
        executor = CommandExecutor(dry_run=False)
        results = executor.execute_plan(intent["azlin_commands"])

        # Display results
        for i, result in enumerate(results, 1):
            click.echo(f"\nCommand {i}: {result['command']}")
            if result["success"]:
                click.echo("  ✓ Success")
                if verbose and result["stdout"]:
                    click.echo(f"  Output: {result['stdout'][:200]}")
            else:
                click.echo(f"  ✗ Failed: {result['stderr']}")
                break  # Stop on first failure

        # Validate results
        validator = ResultValidator()
        validation = validator.validate(intent, results)

        click.echo("\n" + "=" * 80)
        if validation["success"]:
            click.echo("✓ " + validation["message"])
        else:
            click.echo("✗ " + validation["message"], err=True)
            if "issues" in validation:
                for issue in validation["issues"]:
                    click.echo(f"  - {issue}", err=True)
            sys.exit(1)

    except IntentParseError as e:
        click.echo(f"\nFailed to parse request: {e}", err=True)
        click.echo("\nTry rephrasing your request or use specific azlin commands.", err=True)
        sys.exit(1)

    except CommandExecutionError as e:
        click.echo(f"\nCommand execution failed: {e}", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        if verbose:
            logger.exception("Unexpected error in do command")
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        sys.exit(130)


def _doit_old_impl(
    objective: str,
    dry_run: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """[DEPRECATED] Enhanced agentic Azure infrastructure management (old version).

    This command provides multi-strategy execution with state persistence
    and intelligent fallback handling. It enhances the basic 'do' command
    with objective tracking, cost estimation, and failure recovery.

    \b
    Examples:
        azlin doit "provision an AKS cluster with 3 nodes"
        azlin doit "create a VM optimized for ML workloads" --dry-run
        azlin doit "set up a complete dev environment" --verbose

    \b
    Phase 1 Features (Current):
        - Objective state persistence at ~/.azlin/objectives/<uuid>.json
        - Audit logging to ~/.azlin/audit.log
        - Secure file permissions (0600)

    \b
    Future Phases (Not Yet Implemented):
        - Multi-strategy execution (CLI, Terraform, MCP, Custom)
        - Automatic fallback on failures
        - Cost estimation and optimization
        - MS Learn documentation research
        - Intelligent failure recovery

    \b
    Requirements:
        - ANTHROPIC_API_KEY environment variable must be set
        - Active Azure authentication
    """
    try:
        # Check for API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            click.echo("Error: ANTHROPIC_API_KEY environment variable is required", err=True)
            click.echo("\nSet your API key with:", err=True)
            click.echo("  export ANTHROPIC_API_KEY=your-key-here", err=True)
            sys.exit(1)

        # Import azdoit components
        from azlin.agentic.audit_logger import AuditLogger
        from azlin.agentic.objective_manager import ObjectiveManager
        from azlin.agentic.types import Intent

        # Parse natural language intent (using existing parser)
        if verbose:
            click.echo(f"Parsing objective: {objective}")

        # Get resource group for context
        rg = ConfigManager.get_resource_group(resource_group, config)
        context = {}
        if rg:
            context["resource_group"] = rg

        # Parse intent
        parser = IntentParser()
        intent_dict = parser.parse(objective, context=context if context else None)

        # Convert to Intent dataclass
        intent = Intent(
            intent=intent_dict["intent"],
            parameters=intent_dict["parameters"],
            confidence=intent_dict["confidence"],
            azlin_commands=intent_dict["azlin_commands"],
            explanation=intent_dict.get("explanation"),
        )

        if verbose:
            click.echo("\nParsed Intent:")
            click.echo(f"  Type: {intent.intent}")
            click.echo(f"  Confidence: {intent.confidence:.1%}")
            if intent.explanation:
                click.echo(f"  Plan: {intent.explanation}")

        # Create objective state
        manager = ObjectiveManager()
        state = manager.create(
            natural_language=objective,
            intent=intent,
        )

        # Log creation
        logger_inst = AuditLogger()
        logger_inst.log(
            "OBJECTIVE_CREATED",
            objective_id=state.id,
            details={"objective": objective[:100], "confidence": f"{intent.confidence:.2f}"},
        )

        # Display objective info
        click.echo("\n" + "=" * 80)
        click.echo(f"Objective Created: {state.id}")
        click.echo("=" * 80)
        click.echo(f"\nObjective: {objective}")
        click.echo(f"Status: {state.status.value}")
        click.echo(f"State file: ~/.azlin/objectives/{state.id}.json")
        click.echo(f"Created at: {state.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

        if verbose:
            click.echo("\nIntent details:")
            click.echo(f"  Type: {intent.intent}")
            click.echo(f"  Parameters: {intent.parameters}")

        # Phase 2: Strategy Selection and Execution
        from azlin.agentic.strategies import (
            AzureCLIStrategy,
            TerraformStrategy,
        )
        from azlin.agentic.strategy_selector import StrategySelector
        from azlin.agentic.types import ExecutionContext, ObjectiveStatus, Strategy

        # Select execution strategy
        click.echo("\n" + "=" * 80)
        click.echo("Phase 2: Strategy Selection")
        click.echo("=" * 80)

        selector = StrategySelector()
        strategy_plan = selector.select_strategy(intent, resource_group=rg)

        # Update objective with strategy plan
        manager.update(
            state.id,
            strategy_plan=strategy_plan,
            selected_strategy=strategy_plan.primary_strategy,
        )

        click.echo(f"\nSelected Strategy: {strategy_plan.primary_strategy.value}")
        click.echo(f"Reasoning: {strategy_plan.reasoning}")
        if strategy_plan.fallback_strategies:
            click.echo(f"Fallback: {', '.join(s.value for s in strategy_plan.fallback_strategies)}")
        if strategy_plan.estimated_duration_seconds:
            mins = strategy_plan.estimated_duration_seconds // 60
            click.echo(f"Estimated Duration: ~{mins} minutes")

        # Check prerequisites
        if not strategy_plan.prerequisites_met:
            click.echo("\n⚠️  Prerequisites not met!", err=True)
            click.echo(f"Unable to execute: {strategy_plan.reasoning}")

            # Log prerequisite failure
            logger_inst.log(
                "PREREQUISITES_FAILED",
                objective_id=state.id,
                details={"strategy": strategy_plan.primary_strategy.value},
            )

            # Update objective as failed
            manager.update(
                state.id, status=ObjectiveStatus.FAILED, error_message=strategy_plan.reasoning
            )
            sys.exit(1)

        # Log strategy selection
        logger_inst.log(
            "STRATEGY_SELECTED",
            objective_id=state.id,
            details={
                "strategy": strategy_plan.primary_strategy.value,
                "fallbacks": [s.value for s in strategy_plan.fallback_strategies],
            },
        )

        # Phase 3: Cost Estimation
        click.echo("\n" + "=" * 80)
        click.echo("Phase 3: Cost Estimation")
        click.echo("=" * 80)

        from azlin.agentic.budget_monitor import BudgetMonitor, BudgetPeriod
        from azlin.agentic.cost_estimator import CostEstimator, PricingRegion

        # Get strategy instance to extract cost factors
        strategy_map = {
            Strategy.AZURE_CLI: AzureCLIStrategy(),
            Strategy.TERRAFORM: TerraformStrategy(),
        }
        strategy = strategy_map.get(strategy_plan.primary_strategy)

        if strategy:
            # Get cost factors from strategy
            execution_context_temp = ExecutionContext(
                objective_id=state.id,
                intent=intent,
                strategy=strategy_plan.primary_strategy,
                dry_run=True,  # Dry run for cost estimation
                resource_group=rg,
            )
            cost_factors = strategy.get_cost_factors(execution_context_temp)

            if cost_factors:
                # Estimate costs using US_EAST pricing (most common region)
                estimator = CostEstimator(region=PricingRegion.US_EAST)
                cost_estimate = estimator.estimate(cost_factors)

                # Display estimate
                if verbose:
                    click.echo("\n" + estimator.format_estimate(cost_estimate, show_breakdown=True))
                else:
                    click.echo(f"\nEstimated Cost: ${float(cost_estimate.total_monthly):.2f}/month")
                    confidence_pct = {"high": "High", "medium": "Medium", "low": "Low"}
                    click.echo(
                        f"Confidence: {confidence_pct.get(cost_estimate.confidence, cost_estimate.confidence)}"
                    )

                # Check budget
                budget_monitor = BudgetMonitor()
                budget_alert = budget_monitor.check_budget(
                    cost_estimate,
                    period=BudgetPeriod.MONTHLY,
                    resource_group=rg,
                )

                if budget_alert:
                    # Show alert
                    if budget_alert.level.value == "exceeded":
                        click.echo(f"\n🛑 {budget_alert.message}", err=True)
                        click.echo(f"   {budget_alert.recommended_action}", err=True)
                        # Block execution if budget would be exceeded
                        if not dry_run:
                            click.echo("\nExecution blocked to prevent budget overrun.", err=True)
                            click.echo("Options:", err=True)
                            click.echo("  1. Use --dry-run to preview without executing", err=True)
                            click.echo("  2. Reduce resource requirements", err=True)
                            click.echo(
                                "  3. Increase budget limit in ~/.azlin/budget.json", err=True
                            )
                            manager.update(
                                state.id,
                                status=ObjectiveStatus.FAILED,
                                error_message="Budget limit would be exceeded",
                            )
                            sys.exit(1)
                    elif budget_alert.level.value == "critical":
                        click.echo(f"\n⚠️  {budget_alert.message}", err=True)
                        click.echo(f"   {budget_alert.recommended_action}", err=True)
                    else:
                        click.echo(f"\nINFO: {budget_alert.message}")

                # Store cost estimate in objective state
                # cost_estimate is already in the correct types.CostEstimate format
                # Update the objective state with it
                manager.update(state.id, cost_estimate=cost_estimate)

                # Log cost estimation
                logger_inst.log(
                    "COST_ESTIMATED",
                    objective_id=state.id,
                    details={
                        "monthly_cost": f"${float(cost_estimate.total_monthly):.2f}",
                        "confidence": cost_estimate.confidence,
                    },
                )
            else:
                click.echo("\nNo cost factors available for estimation")
        else:
            click.echo("\nCost estimation not available for this strategy")

        # Execute strategy
        click.echo("\n" + "=" * 80)
        click.echo("Phase 3: Execution")
        click.echo("=" * 80)

        # Create execution context
        execution_context = ExecutionContext(
            objective_id=state.id,
            intent=intent,
            strategy=strategy_plan.primary_strategy,
            dry_run=dry_run,
            resource_group=rg,
        )

        # Strategy was already obtained in Phase 3
        if not strategy:
            click.echo(
                f"\n⚠️  Strategy {strategy_plan.primary_strategy.value} not yet implemented",
                err=True,
            )
            manager.update(
                state.id,
                status=ObjectiveStatus.FAILED,
                error_message=f"Strategy {strategy_plan.primary_strategy.value} not implemented",
            )
            sys.exit(1)

        # Update status to IN_PROGRESS
        manager.update(state.id, status=ObjectiveStatus.IN_PROGRESS)

        # Log execution start
        logger_inst.log(
            "EXECUTION_STARTED",
            objective_id=state.id,
            details={"strategy": strategy_plan.primary_strategy.value},
        )

        # Phase 4: Execution Orchestrator (with fallback and retry)
        from azlin.agentic.execution_orchestrator import ExecutionOrchestrator

        orchestrator = ExecutionOrchestrator(
            max_retries=3,
            retry_delay_base=2.0,
            enable_rollback=True,
        )

        if verbose:
            click.echo("\nExecuting with orchestrated fallback chain:")
            click.echo(f"  Primary: {strategy_plan.primary_strategy.value}")
            if strategy_plan.fallback_strategies:
                click.echo(
                    f"  Fallbacks: {', '.join(s.value for s in strategy_plan.fallback_strategies)}"
                )

        # Execute with orchestrator (handles retries and fallback automatically)
        result = orchestrator.execute(execution_context, strategy_plan)

        # Show execution summary in verbose mode
        if verbose:
            summary = orchestrator.get_execution_summary()
            click.echo("\nExecution Summary:")
            click.echo(f"  Total Attempts: {summary['total_attempts']}")
            click.echo(f"  Strategies Tried: {', '.join(summary['strategies_tried'])}")
            click.echo(f"  Total Duration: {summary['total_duration']:.1f}s")

        # Update objective with execution result
        manager.update(
            state.id,
            execution_results=[result],
            resources_created=result.resources_created,
        )

        # Display result
        if result.success:
            click.echo("\n✅ Execution successful!")

            # Update objective status
            manager.update(state.id, status=ObjectiveStatus.COMPLETED)

            # Log success
            logger_inst.log(
                "EXECUTION_COMPLETED",
                objective_id=state.id,
                details={
                    "strategy": result.strategy.value,
                    "duration": f"{result.duration_seconds:.1f}s"
                    if result.duration_seconds
                    else None,
                    "resources": len(result.resources_created),
                },
            )

            if result.output and verbose:
                click.echo("\nOutput:")
                click.echo(result.output)

            if result.resources_created:
                click.echo(f"\nResources Created ({len(result.resources_created)}):")
                for resource_id in result.resources_created[:10]:  # Show first 10
                    click.echo(f"  - {resource_id}")
                if len(result.resources_created) > 10:
                    click.echo(f"  ... and {len(result.resources_created) - 10} more")

            if result.duration_seconds:
                click.echo(f"\nDuration: {result.duration_seconds:.1f} seconds")

        else:
            click.echo(f"\n❌ Execution failed: {result.error}", err=True)

            # Phase 5: Failure Analysis & MS Learn Research
            click.echo("\n" + "=" * 80)
            click.echo("Phase 5: Failure Analysis")
            click.echo("=" * 80)

            from azlin.agentic.failure_analyzer import FailureAnalyzer
            from azlin.agentic.ms_learn_client import MSLearnClient

            # Analyze failure
            ms_learn = MSLearnClient()
            analyzer = FailureAnalyzer(ms_learn_client=ms_learn)
            analysis = analyzer.analyze_failure(result)

            # Display analysis
            click.echo(f"\nFailure Type: {analysis.failure_type.value}")
            if analysis.error_signature.error_code:
                click.echo(f"Error Code: {analysis.error_signature.error_code}")
            if analysis.similar_failures > 0:
                click.echo(f"Similar Past Failures: {analysis.similar_failures}")

            # Show suggested fixes
            if analysis.suggested_fixes:
                click.echo("\n📋 Suggested Fixes:")
                for i, fix in enumerate(analysis.suggested_fixes, 1):
                    click.echo(f"  {i}. {fix}")

            # Show runnable commands
            if analysis.runnable_commands:
                click.echo("\n🔧 Diagnostic Commands:")
                for cmd in analysis.runnable_commands:
                    click.echo(f"  $ {cmd}")

            # Show MS Learn documentation
            if analysis.doc_links:
                click.echo("\n📚 MS Learn Documentation:")
                for doc in analysis.doc_links:
                    click.echo(f"  • {doc.title}")
                    click.echo(f"    {doc.url}")
                    if doc.summary and verbose:
                        click.echo(f"    {doc.summary}")

            # Ask user if they want to try suggested commands
            if analysis.runnable_commands and not dry_run:
                click.echo("\n❓ Would you like to run the diagnostic commands? [y/N]: ", nl=False)
                try:
                    if sys.stdin.isatty():
                        response = input().strip().lower()
                        if response == "y":
                            click.echo("\n🔍 Running diagnostic commands...")
                            for cmd in analysis.runnable_commands:
                                click.echo(f"\n$ {cmd}")
                                try:
                                    # Security: Use shlex.split() for safe command parsing
                                    # This protects against command injection
                                    import shlex

                                    # Check if command contains pipes (need special handling)
                                    if "|" in cmd:
                                        # For piped commands, validate they're safe Az CLI commands
                                        if not cmd.strip().startswith(
                                            ("az ", "terraform ", "kubectl ")
                                        ):
                                            click.echo(
                                                "  ⚠️  Skipped: Only az/terraform/kubectl commands allowed for piped execution",
                                                err=True,
                                            )
                                            continue

                                        # Execute pipes securely without shell=True
                                        # Split by pipe and chain processes
                                        pipe_parts = [part.strip() for part in cmd.split("|")]

                                        try:
                                            # Start first process
                                            first_cmd = shlex.split(pipe_parts[0])
                                            current_proc = subprocess.Popen(
                                                first_cmd,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE,
                                                text=True,
                                            )

                                            # Chain remaining processes
                                            for pipe_cmd in pipe_parts[1:]:
                                                cmd_parts = shlex.split(pipe_cmd)
                                                next_proc = subprocess.Popen(
                                                    cmd_parts,
                                                    stdin=current_proc.stdout,
                                                    stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE,
                                                    text=True,
                                                )
                                                if current_proc.stdout:
                                                    current_proc.stdout.close()
                                                current_proc = next_proc

                                            # Get final output
                                            stdout, stderr = current_proc.communicate(timeout=30)
                                            proc_result = subprocess.CompletedProcess(
                                                args=cmd,
                                                returncode=current_proc.returncode or 0,
                                                stdout=stdout,
                                                stderr=stderr,
                                            )
                                        except Exception as pipe_error:
                                            click.echo(
                                                f"  ⚠️  Pipe execution failed: {pipe_error}",
                                                err=True,
                                            )
                                            continue

                                    elif any(
                                        char in cmd for char in [">", "<", ";", "&", "`", "$("]
                                    ):
                                        # Redirects, command chains, and substitutions are not supported
                                        click.echo(
                                            "  ⚠️  Skipped: Redirects, command chains, and substitutions not supported",
                                            err=True,
                                        )
                                        continue
                                    else:
                                        # Simple commands: use safe list-based execution
                                        cmd_parts = shlex.split(cmd)
                                        proc_result = subprocess.run(
                                            cmd_parts,
                                            shell=False,
                                            capture_output=True,
                                            text=True,
                                            timeout=30,
                                        )

                                    if proc_result.stdout:
                                        click.echo(proc_result.stdout)
                                    if proc_result.stderr:
                                        click.echo(proc_result.stderr, err=True)
                                except subprocess.TimeoutExpired:
                                    click.echo("  (command timed out)", err=True)
                                except Exception as e:
                                    click.echo(f"  Error: {e}", err=True)
                except (EOFError, KeyboardInterrupt):
                    click.echo("N")

            # Update objective as failed
            manager.update(
                state.id,
                status=ObjectiveStatus.FAILED,
                error_message=result.error,
                failure_type=result.failure_type,
            )

            # Log failure
            logger_inst.log(
                "EXECUTION_FAILED",
                objective_id=state.id,
                details={
                    "strategy": result.strategy.value,
                    "error": result.error,
                    "failure_type": result.failure_type.value if result.failure_type else None,
                },
            )

            if result.output and verbose:
                click.echo("\nOutput:")
                click.echo(result.output)

            sys.exit(1)

        # Show audit trail
        click.echo("\nAudit trail:")
        timeline = logger_inst.get_objective_timeline(state.id)
        for event in timeline:
            click.echo(f"  {event['timestamp']}: {event['event']}")

        click.echo("\nTo view objective state:")
        click.echo(f"  cat ~/.azlin/objectives/{state.id}.json")
        click.echo("\nTo view audit log:")
        click.echo("  tail ~/.azlin/audit.log")

    except IntentParseError as e:
        click.echo(f"\nFailed to parse objective: {e}", err=True)
        click.echo("\nTry rephrasing your objective or use specific azlin commands.", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        if verbose:
            logger.exception("Unexpected error in doit command")
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        sys.exit(130)


# SSH & Keys


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


def _cleanup_key_from_vault(vm_name: str, config: str | None) -> None:
    """Delete SSH key from Azure Key Vault when VM is destroyed.

    Args:
        vm_name: VM name (used to lookup secret)
        config: Config file path

    Note:
        This function logs warnings but does not raise exceptions to avoid
        blocking VM deletion if Key Vault cleanup fails.
    """
    try:
        # Load context to get key_vault_name
        context_config = ContextManager.load(config)
        current_context = context_config.get_current_context()

        if not current_context or not current_context.key_vault_name:
            logger.debug("No Key Vault configured, skipping cleanup")
            return

        logger.info(f"Cleaning up SSH key from Key Vault for VM: {vm_name}")

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

        # Delete key
        deleted = manager.delete_key(vm_name)
        if deleted:
            click.echo(f"SSH key deleted from Key Vault: {current_context.key_vault_name}")
        else:
            logger.debug(f"SSH key not found in Key Vault for VM: {vm_name}")

    except KeyVaultError as e:
        logger.warning(f"Failed to delete SSH key from Key Vault: {e}")
        # Don't block VM deletion if Key Vault cleanup fails
    except Exception as e:
        logger.warning(f"Unexpected error during Key Vault cleanup: {e}")


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


# Batch Operations


def _validate_batch_selection(tag: str | None, vm_pattern: str | None, select_all: bool):
    """Validate that exactly one batch selection option is provided."""
    selection_count = sum([bool(tag), bool(vm_pattern), select_all])
    if selection_count == 0:
        click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
        sys.exit(1)
    if selection_count > 1:
        click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
        sys.exit(1)


def _select_vms_by_criteria(
    all_vms: list[VMInfo], tag: str | None, vm_pattern: str | None, select_all: bool
) -> tuple[list[VMInfo], str]:
    """Select VMs based on criteria and return (selected_vms, selection_description)."""
    if tag:
        selected_vms = BatchSelector.select_by_tag(all_vms, tag)
        selection_desc = f"tag '{tag}'"
    elif vm_pattern:
        selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
        selection_desc = f"pattern '{vm_pattern}'"
    else:  # select_all
        selected_vms = all_vms
        selection_desc = "all VMs"
    return selected_vms, selection_desc


# Other


def _perform_startup_checks() -> None:
    """Perform Azure CLI environment checks at startup.

    Detects WSL2 + Windows Azure CLI and offers Linux CLI installation.
    Non-fatal - failures are logged but don't prevent CLI operation.
    """
    try:
        detector = CLIDetector()
        env_info = detector.detect()

        # If there's a problem, offer installation
        if env_info.has_problem:
            logger.info("Azure CLI environment check: %s", env_info.problem_description)

            installer = CLIInstaller()
            result = installer.install()

            if result.status == InstallStatus.SUCCESS:
                logger.info("Azure CLI installation successful")
            elif result.status == InstallStatus.ALREADY_INSTALLED:
                logger.debug("Linux Azure CLI already installed")
            elif result.status == InstallStatus.CANCELLED:
                logger.info("Azure CLI installation skipped")
            elif result.status == InstallStatus.FAILED and result.error_message:
                logger.warning("Azure CLI installation failed: %s", result.error_message)

    except Exception as e:
        # Non-fatal - log and continue
        logger.debug("Azure CLI environment check failed: %s", e)


def snapshot_enable(
    vm_name: str,
    resource_group: str | None,
    config: str | None,
    interval_hours: int,
    keep_count: int,
):
    """Enable scheduled snapshots for a VM.

    Configures the VM to take snapshots every N hours, keeping only the most recent snapshots.
    Schedule is stored in VM tags and triggered by `azlin snapshot sync`.

    \b
    Examples:
        azlin snapshot enable my-vm --every 24          # Daily, keep 2
        azlin snapshot enable my-vm --every 12 --keep 5 # Every 12h, keep 5
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        SnapshotManager.enable_snapshots(vm_name, rg, interval_hours, keep_count)

        click.echo(f"✓ Enabled scheduled snapshots for {vm_name}")
        click.echo(f"  Interval: every {interval_hours} hours")
        click.echo(f"  Retention: keep {keep_count} snapshots")
        click.echo("\nRun 'azlin snapshot sync' to trigger snapshot creation.")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


__all__ = [
    "SSHConfigBuilder",
    "_auto_sync_home_directory",
    "_cleanup_key_from_vault",
    "_confirm_batch_operation",
    "_confirm_killall",
    "_confirm_vm_deletion",
    "_copy_home_directories",
    "_display_batch_summary",
    "_display_clone_results",
    "_display_killall_results",
    "_display_pool_results",
    "_do_impl",
    "_doit_old_impl",
    "_ensure_source_vm_running",
    "_execute_command_mode",
    "_execute_sync",
    "_execute_vm_deletion",
    "_generate_clone_configs",
    "_get_ssh_config_for_vm",
    "_get_sync_vm_by_name",
    "_handle_delete_resource_group",
    "_handle_vm_dry_run",
    "_interactive_vm_selection",
    "_is_valid_vm_name",
    "_load_config_and_template",
    "_perform_startup_checks",
    "_perform_sync",
    "_provision_clone_vms",
    "_provision_pool",
    "_resolve_source_vm",
    "_resolve_tmux_session",
    "_resolve_vm_identifier",
    "_resolve_vm_settings",
    "_select_sync_vm_interactive",
    "_select_vms_by_criteria",
    "_set_clone_session_names",
    "_try_fetch_key_from_vault",
    "_update_config_state",
    "_validate_and_resolve_source_vm",
    "_validate_batch_selection",
    "_validate_config_path",
    "_validate_inputs",
    "_verify_vm_exists",
    "execute_command_on_vm",
    "generate_vm_name",
    "get_ssh_configs_for_vms",
    "keys_backup",
    "select_vm_for_command",
    "show_interactive_menu",
    "snapshot_enable",
]
