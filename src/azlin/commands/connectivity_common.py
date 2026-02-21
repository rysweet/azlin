"""Common helpers shared across connectivity commands.

This module provides shared utilities for SSH connection, file transfer,
and IDE commands. Extracted from connectivity.py for better modularity.
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from azlin.compound_identifier import (
    AmbiguousIdentifierError,
    CompoundIdentifierError,
    parse_identifier,
    resolve_to_vm,
)
from azlin.config_manager import ConfigManager
from azlin.context_manager import ContextManager
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)


def resolve_vm_identifier(vm_identifier: str, config: str | None) -> tuple[str, str]:
    """Resolve compound identifier or session name to VM name and return both.

    Supports compound identifiers (vm:session) and legacy session resolution.
    Resolution order:
    1. If IP address, skip resolution
    2. Try parse_identifier() for compound format (vm:session or :session)
    3. If compound format with VM name, resolve using resolve_to_vm()
    4. If simple format, fall back to legacy session resolution

    Resolution is SKIPPED when:
    - The identifier is a valid IP address
    - The identifier is already a valid VM name (legacy behavior)
    - The identifier equals the resolved VM name (self-referential)

    Returns:
        Tuple of (resolved_identifier, original_identifier)

    Raises:
        SystemExit: On CompoundIdentifierError or AmbiguousIdentifierError
    """
    original_identifier = vm_identifier

    # Skip resolution for IP addresses
    if VMConnector.is_valid_ip(vm_identifier):
        return vm_identifier, original_identifier

    # Try parsing as compound identifier
    try:
        vm_name, session_name = parse_identifier(vm_identifier)

        # Compound format detected (has colon)
        if ":" in vm_identifier:
            # Get resource group for VM lookup
            rg = ConfigManager.get_resource_group(None, config)
            if not rg:
                click.echo(
                    "Error: Resource group required for compound identifier resolution.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)

            # Get available VMs
            try:
                vms = VMManager.list_vms(resource_group=rg, include_stopped=False)
            except VMManagerError as e:
                click.echo(f"Error listing VMs: {e}", err=True)
                sys.exit(1)

            # Resolve using compound identifier module
            try:
                resolved_vm = resolve_to_vm(vm_identifier, vms, config)
                click.echo(f"Resolved '{vm_identifier}' to VM '{resolved_vm.name}'")
                return resolved_vm.name, original_identifier
            except (CompoundIdentifierError, AmbiguousIdentifierError) as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)

    except CompoundIdentifierError as e:
        # Invalid format (e.g., multiple colons)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Simple format (no colon) - use legacy resolution
    # First check if this is already a valid VM name - if so, don't resolve
    # This prevents: User types "amplifier" (a VM) but session "amplifier"
    # exists on VM "atg-dev" -> should connect to VM "amplifier", not "atg-dev"
    if _is_valid_vm_name(vm_identifier, config):
        logger.debug(f"'{vm_identifier}' is a valid VM name, skipping session resolution")
        return vm_identifier, original_identifier

    # Not a VM name, try to resolve as session name using config
    resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
    if resolved_vm_name and resolved_vm_name != vm_identifier:
        click.echo(f"Resolved session '{vm_identifier}' to VM '{resolved_vm_name}'")
        vm_identifier = resolved_vm_name

    return vm_identifier, original_identifier


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


def verify_vm_exists(vm_identifier: str, original_identifier: str, rg: str) -> None:
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


def try_fetch_key_from_vault(vm_name: str, key_path: Path, config: str | None) -> bool:
    """Try to fetch SSH key from Azure Key Vault if local key is missing.

    Args:
        vm_name: VM name (used to lookup secret)
        key_path: Target path for private key
        config: Config file path

    Returns:
        True if key was fetched successfully, False otherwise
    """
    try:
        from azlin.auth_models import AuthConfig, AuthMethod
        from azlin.modules.ssh_key_vault import create_key_vault_manager

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

        # Try to fetch key
        secret_name = SSHKeyManager.get_secret_name(vm_name)  # type: ignore[attr-defined]
        result = manager.get_ssh_key_pair(secret_name)  # type: ignore[attr-defined]

        if result and result.private_key and result.public_key:
            # Save keys locally
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_text(result.private_key)
            key_path.chmod(0o600)

            pub_key_path = Path(str(key_path) + ".pub")
            pub_key_path.write_text(result.public_key)
            pub_key_path.chmod(0o644)

            console.print(f"[green]✓ Fetched SSH key from Key Vault: {secret_name}[/green]")
            return True

        logger.debug(f"SSH key not found in Key Vault: {secret_name}")
        return False

    except Exception as e:
        logger.debug(f"Failed to fetch SSH key from Key Vault: {e}")
        return False


def get_ssh_config_for_vm(vm_identifier: str, resource_group: str | None, config: str | None):
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
    from azlin.modules.ssh_connector import SSHConfig

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


__all__ = [
    "get_ssh_config_for_vm",
    "resolve_vm_identifier",
    "try_fetch_key_from_vault",
    "verify_vm_exists",
]
