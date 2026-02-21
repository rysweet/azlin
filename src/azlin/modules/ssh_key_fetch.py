"""SSH key fetching from Key Vault and auto-sync logic.

Extracted from vm_connector.py (Issue #597) to reduce module size.
Handles Key Vault SSH key retrieval and automatic key synchronization
to VM authorized_keys.

Public API:
    try_fetch_key_from_vault: Try to fetch SSH key from Key Vault
    auto_sync_key_to_vm: Auto-sync SSH key to VM if enabled in config
"""

import logging
from pathlib import Path

from azlin.auth_models import AuthConfig, AuthMethod
from azlin.config_manager import ConfigManager
from azlin.context_manager import ContextManager
from azlin.modules.connection_sanitizer import sanitize_for_logging
from azlin.modules.ssh_key_vault import KeyVaultError, create_key_vault_manager
from azlin.modules.ssh_keys import SSHKeyManager

logger = logging.getLogger(__name__)


def try_fetch_key_from_vault(vm_name: str, key_path: Path, resource_group: str) -> bool:
    """Try to fetch SSH key from Key Vault.

    Always queries Key Vault for the VM-specific key, regardless of local key existence.
    This ensures correct key retrieval when connecting to different VMs.

    Args:
        vm_name: VM name (used to construct Key Vault secret name)
        key_path: Path where key should be stored
        resource_group: Resource group containing the VM

    Returns:
        True if key was fetched successfully, False otherwise

    Note:
        - Key Vault is the source of truth for VM-specific keys
        - Local key is overwritten with Key Vault key if found
        - Returns False on any error (doesn't raise)

    Issue #417: Previously skipped Key Vault when local key existed,
    breaking multi-VM connection scenarios.
    """
    try:
        logger.info(f"Checking Key Vault for SSH key: {sanitize_for_logging(vm_name)}")

        # Load context to get subscription/tenant info
        try:
            context_config = ContextManager.load()
            current_context = context_config.get_current_context()
            if not current_context:
                logger.info("No current context set, skipping Key Vault fetch")
                return False
        except Exception as e:
            logger.info(f"Failed to load context: {e}")
            return False

        # Build auth config
        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        # Try to find Key Vault in resource group
        from azlin.modules.ssh_key_vault import SSHKeyVaultManager

        vault_name = SSHKeyVaultManager.find_key_vault_in_resource_group(
            resource_group=resource_group,
            subscription_id=current_context.subscription_id,
        )

        if not vault_name:
            logger.info(f"No Key Vault found in resource group: {resource_group}")
            return False

        # Create manager and try to retrieve key
        manager = create_key_vault_manager(
            vault_name=vault_name,
            subscription_id=current_context.subscription_id,
            tenant_id=current_context.tenant_id,
            auth_config=auth_config,
        )

        manager.retrieve_key(vm_name=vm_name, target_path=key_path)
        logger.info(f"SSH key retrieved from Key Vault: {vault_name}")
        return True

    except KeyVaultError as e:
        # Check if it's a "not found" vs auth error
        error_str = str(e).lower()
        if "not found" in error_str or "does not exist" in error_str:
            logger.info(f"SSH key not found in Key Vault for VM: {sanitize_for_logging(vm_name)}")
        else:
            logger.warning(f"Could not access Key Vault: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error fetching from Key Vault: {e}")
        return False


def auto_sync_key_to_vm(
    conn_info_vm_name: str, conn_info_resource_group: str, conn_info_ssh_key_path: Path | None
) -> None:
    """Auto-sync SSH key to VM authorized_keys if enabled in config.

    Args:
        conn_info_vm_name: VM name
        conn_info_resource_group: Resource group
        conn_info_ssh_key_path: Path to SSH private key
    """
    try:
        config = ConfigManager.load_config()

        # Only attempt auto-sync if enabled in config
        if not config.ssh_auto_sync_keys:
            return

        # Check if we should skip auto-sync for new VMs
        should_skip = False
        if config.ssh_auto_sync_skip_new_vms:
            from azlin.modules.vm_age_checker import VMAgeChecker

            try:
                is_ready = VMAgeChecker.is_vm_ready_for_auto_sync(
                    vm_name=conn_info_vm_name,
                    resource_group=conn_info_resource_group,
                    threshold_seconds=config.ssh_auto_sync_age_threshold,
                )
                should_skip = not is_ready
            except Exception as e:
                # Log warning but don't block connection on age check failure
                logger.warning(
                    f"Failed to check VM age for {sanitize_for_logging(conn_info_vm_name)}: {e}. "
                    f"Proceeding with auto-sync (fail-safe behavior)."
                )
                should_skip = False  # Fail-safe: proceed with auto-sync

            if should_skip:
                safe_vm_name = sanitize_for_logging(conn_info_vm_name)
                logger.info(
                    f"Skipping auto-sync for new VM {safe_vm_name} "
                    f"(younger than {config.ssh_auto_sync_age_threshold}s threshold). "
                    f"SSH key will be used directly for connection. "
                    f"Use 'azlin sync-keys {safe_vm_name}' to manually sync after VM initialization completes."
                )

        # Proceed with auto-sync if not skipped
        if not should_skip:
            from azlin.modules.vm_key_sync import DEFAULT_TIMEOUT, VMKeySync

            logger.info(
                f"Auto-syncing SSH key to VM authorized_keys: {sanitize_for_logging(conn_info_vm_name)}"
            )

            # Derive public key from private key
            public_key = SSHKeyManager.get_public_key(conn_info_ssh_key_path)

            # Instantiate VMKeySync with config dict
            sync_manager = VMKeySync(config.to_dict())

            # Use DEFAULT_TIMEOUT (60s) for WSL compatibility (Issue #578)
            # Previous 5s timeout was insufficient for Azure Run Command API in WSL
            result = sync_manager.ensure_key_authorized(
                vm_name=conn_info_vm_name,
                resource_group=conn_info_resource_group,
                public_key=public_key,
                timeout=DEFAULT_TIMEOUT,
            )

            # Log accurate status based on actual result (Issue #578)
            if result.synced:
                print(f"SSH key synced to VM authorized_keys in {result.duration_ms}ms")
                logger.info(f"SSH key synced to VM authorized_keys in {result.duration_ms}ms")
            elif result.already_present:
                print("SSH key already present in VM authorized_keys")
                logger.debug("SSH key already present in VM authorized_keys")
            elif result.error:
                print(f"SSH key auto-sync failed: {result.error}")
                logger.warning(
                    f"SSH key auto-sync failed: {result.error}. "
                    f"Connection may fail if key not already on VM. "
                    f"Use 'azlin sync-keys {sanitize_for_logging(conn_info_vm_name)}' to manually sync."
                )
    except Exception as e:
        # Log warning but don't block connection
        print(f"Auto-sync exception: {e}")
        logger.warning(f"Auto-sync SSH key failed: {e}, attempting connection anyway")


__all__ = ["auto_sync_key_to_vm", "try_fetch_key_from_vault"]
