"""Azure Key Vault SSH key storage for azlin.

Secure storage and retrieval of SSH private keys using Azure Key Vault.
Keys are stored during VM provisioning and auto-retrieved when connecting from different hosts.

Features:
- Store/retrieve/delete SSH keys in Azure Key Vault
- Service Principal and Azure CLI authentication via AuthenticationChain
- Automatic cleanup on VM deletion
- Zero plaintext key logging
- Secure file permissions (0600)
- Auto-create Key Vault if needed (transparent setup)
- Auto-assign RBAC permissions to current user
- Auto-detect existing Key Vault in resource group

Secret Naming: azlin-{vm-name}-ssh-private
RBAC Roles: Key Vault Secrets Officer (write), Secrets User (read)
Integration: azlin new (auto-stores), connect (auto-retrieves), kill, destroy
"""

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from azure.core.credentials import TokenCredential  # type: ignore[import-untyped]
from azure.core.exceptions import (  # type: ignore[import-untyped]
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
)
from azure.keyvault.secrets import SecretClient  # type: ignore[import-untyped]

from azlin.auth_models import AuthConfig
from azlin.authentication_chain import AuthenticationChain, AuthenticationChainError
from azlin.log_sanitizer import LogSanitizer
from azlin.modules.azure_cli_helper import get_az_command

logger = logging.getLogger(__name__)


class KeyVaultError(Exception):
    """Raised when Key Vault operations fail."""

    pass


def get_current_user_principal_id() -> str:
    """Get current Azure CLI user's object ID (principal ID).

    Returns:
        Object ID (principal ID) of current Azure CLI user

    Raises:
        KeyVaultError: If unable to get principal ID
    """
    try:
        result = subprocess.run(
            [get_az_command(), "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        principal_id = result.stdout.strip()
        if not principal_id:
            raise KeyVaultError("Failed to get principal ID: empty response")
        logger.debug(f"Current user principal ID: {principal_id}")
        return principal_id
    except subprocess.TimeoutExpired as e:
        logger.warning("Azure CLI command timed out after 30 seconds: get signed-in user")
        raise KeyVaultError(
            "Azure CLI command timed out while getting user principal ID. "
            "Check your network connection and Azure CLI authentication."
        ) from e
    except subprocess.CalledProcessError as e:
        # Might be service principal authentication
        try:
            # Try getting service principal info
            result = subprocess.run(
                [get_az_command(), "account", "show", "--query", "user.name", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            sp_name = result.stdout.strip()
            if sp_name:
                # Get SP object ID
                result = subprocess.run(
                    [
                        get_az_command(),
                        "ad",
                        "sp",
                        "show",
                        "--id",
                        sp_name,
                        "--query",
                        "id",
                        "-o",
                        "tsv",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                principal_id = result.stdout.strip()
                if principal_id:
                    logger.debug(f"Service principal ID: {principal_id}")
                    return principal_id
        except subprocess.TimeoutExpired:
            logger.warning(
                "Azure CLI command timed out after 30 seconds: get service principal info"
            )
            pass
        except Exception:
            pass
        raise KeyVaultError(
            f"Failed to get current user principal ID: {e.stderr if e.stderr else str(e)}\n"
            "Ensure you are logged in with 'az login'"
        ) from e
    except Exception as e:
        raise KeyVaultError(f"Unexpected error getting principal ID: {e}") from e


def generate_key_vault_name(subscription_id: str) -> str:
    """Generate consistent Key Vault name for a subscription.

    Args:
        subscription_id: Azure subscription ID

    Returns:
        Key Vault name (azlin-kv-{hash})

    Note:
        - Key Vault names must be 3-24 characters
        - Format: azlin-kv-{first 6 chars of subscription hash}
        - Total length: 15 characters
    """
    # Hash subscription ID to get consistent, short identifier
    hash_obj = hashlib.sha256(subscription_id.encode())
    hash_hex = hash_obj.hexdigest()[:6]
    vault_name = f"azlin-kv-{hash_hex}"
    logger.debug(f"Generated vault name: {vault_name} for subscription: {subscription_id}")
    return vault_name


@dataclass
class KeyVaultConfig:
    """Azure Key Vault configuration with vault name, subscription, tenant, and credentials."""

    vault_name: str
    subscription_id: str
    tenant_id: str
    credentials: TokenCredential

    def __post_init__(self):
        """Validate configuration."""
        if not self.vault_name:
            raise KeyVaultError("vault_name cannot be empty")
        if not self.subscription_id:
            raise KeyVaultError("subscription_id cannot be empty")
        if not self.tenant_id:
            raise KeyVaultError("tenant_id cannot be empty")
        if not self.credentials:
            raise KeyVaultError("credentials cannot be None")

    @property
    def vault_url(self) -> str:
        """Get full vault URL.

        Returns:
            Full vault URL (https://{vault_name}.vault.azure.net)
        """
        return f"https://{self.vault_name}.vault.azure.net"


class SSHKeyVaultManager:
    """Manage SSH keys in Azure Key Vault.

    Provides secure storage/retrieval of SSH private keys using AuthenticationChain.
    Private key content is never logged, error messages are sanitized, and files have 0600 permissions.
    Includes automatic Key Vault creation, RBAC setup, and detection.
    """

    # Secret name format: azlin-{vm-name}-ssh-private
    SECRET_NAME_PREFIX = "azlin-"  # noqa: S105
    SECRET_NAME_SUFFIX = "-ssh-private"  # noqa: S105

    def __init__(self, config: KeyVaultConfig):
        """Initialize Key Vault manager.

        Args:
            config: Key Vault configuration with credentials

        Raises:
            KeyVaultError: If configuration is invalid
        """
        self.config = config
        self._client: SecretClient | None = None

    @staticmethod
    def find_key_vault_in_resource_group(resource_group: str, subscription_id: str) -> str | None:
        """Find existing azlin Key Vault in resource group.

        Args:
            resource_group: Resource group name
            subscription_id: Azure subscription ID

        Returns:
            Vault name if found, None otherwise

        Note: Looks for vaults with name pattern 'azlin-kv-*'
        """
        try:
            logger.debug(f"Searching for Key Vault in resource group: {resource_group}")
            result = subprocess.run(
                [
                    "az",
                    "keyvault",
                    "list",
                    "--resource-group",
                    resource_group,
                    "--subscription",
                    subscription_id,
                    "--query",
                    "[?starts_with(name, 'azlin-kv-')].name",
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            vaults = json.loads(result.stdout)
            if vaults:
                vault_name = vaults[0]
                logger.debug(f"Found existing Key Vault: {vault_name}")
                return vault_name

            logger.debug("No existing azlin Key Vault found")
            return None

        except subprocess.TimeoutExpired:
            logger.warning(
                f"Azure CLI command timed out after 30 seconds: list Key Vaults in {resource_group}"
            )
            return None
        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed to list Key Vaults: {e.stderr if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.debug(f"Error finding Key Vault: {e}")
            return None

    @staticmethod
    def ensure_key_vault_exists(resource_group: str, location: str, subscription_id: str) -> str:
        """Ensure Key Vault exists, creating if needed.

        Args:
            resource_group: Resource group name
            location: Azure region
            subscription_id: Azure subscription ID

        Returns:
            Key Vault name (existing or newly created)

        Raises:
            KeyVaultError: If creation fails

        Note:
            - Creates vault with RBAC authorization enabled
            - Vault name: azlin-kv-{hash(subscription_id)[:6]}
            - Silent operation (only logs at debug level)
        """
        # First check if vault already exists
        existing_vault = SSHKeyVaultManager.find_key_vault_in_resource_group(
            resource_group, subscription_id
        )
        if existing_vault:
            logger.debug(f"Using existing Key Vault: {existing_vault}")
            return existing_vault

        # Generate vault name
        vault_name = generate_key_vault_name(subscription_id)
        logger.debug(f"Creating Key Vault: {vault_name} in {resource_group}")

        try:
            # Create Key Vault with RBAC authorization
            subprocess.run(
                [
                    "az",
                    "keyvault",
                    "create",
                    "--name",
                    vault_name,
                    "--resource-group",
                    resource_group,
                    "--location",
                    location,
                    "--subscription",
                    subscription_id,
                    "--enable-rbac-authorization",
                    "true",
                    "--no-wait",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            logger.debug(f"Key Vault creation initiated: {vault_name}")
            return vault_name

        except subprocess.TimeoutExpired as e:
            logger.warning(
                f"Azure CLI command timed out after 30 seconds: create Key Vault {vault_name}"
            )
            raise KeyVaultError(
                f"Azure CLI command timed out while creating Key Vault: {vault_name}. "
                "The vault may still be creating in the background. Try again in a few moments."
            ) from e
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            # Check if vault already exists (race condition)
            if "already exists" in error_msg.lower():
                logger.debug(f"Key Vault already exists: {vault_name}")
                return vault_name
            raise KeyVaultError(f"Failed to create Key Vault: {error_msg}") from e
        except Exception as e:
            raise KeyVaultError(f"Unexpected error creating Key Vault: {e}") from e

    @staticmethod
    def ensure_rbac_permissions(
        vault_name: str, resource_group: str, subscription_id: str, principal_id: str
    ) -> None:
        """Ensure user has RBAC permissions on Key Vault.

        Args:
            vault_name: Key Vault name
            resource_group: Resource group name
            subscription_id: Azure subscription ID
            principal_id: User/service principal object ID

        Raises:
            KeyVaultError: If permission assignment fails

        Note:
            - Assigns 'Key Vault Secrets Officer' role (write access)
            - Checks if role already assigned (idempotent)
            - Silent operation (only logs at debug level)
        """
        role = "Key Vault Secrets Officer"
        logger.debug(f"Ensuring RBAC permissions on vault: {vault_name}")

        try:
            # Get vault scope
            result = subprocess.run(
                [
                    "az",
                    "keyvault",
                    "show",
                    "--name",
                    vault_name,
                    "--resource-group",
                    resource_group,
                    "--subscription",
                    subscription_id,
                    "--query",
                    "id",
                    "-o",
                    "tsv",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            vault_scope = result.stdout.strip()

            # Check if role already assigned
            result = subprocess.run(
                [
                    "az",
                    "role",
                    "assignment",
                    "list",
                    "--assignee",
                    principal_id,
                    "--scope",
                    vault_scope,
                    "--role",
                    role,
                    "--query",
                    "[].id",
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            assignments = json.loads(result.stdout)
            if assignments:
                logger.debug(f"RBAC permissions already assigned for: {principal_id}")
                return

            # Assign role
            logger.debug(f"Assigning '{role}' role to: {principal_id}")
            subprocess.run(
                [
                    "az",
                    "role",
                    "assignment",
                    "create",
                    "--assignee",
                    principal_id,
                    "--role",
                    role,
                    "--scope",
                    vault_scope,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            logger.debug("RBAC permissions assigned successfully")

        except subprocess.TimeoutExpired as e:
            logger.warning(
                f"Azure CLI command timed out after 30 seconds: RBAC operations for {vault_name}"
            )
            raise KeyVaultError(
                f"Azure CLI command timed out while managing RBAC permissions for Key Vault: {vault_name}. "
                "Check your network connection and try again."
            ) from e
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            # Check if assignment already exists (race condition)
            if "already exists" in error_msg.lower():
                logger.debug("RBAC permissions already assigned")
                return
            raise KeyVaultError(f"Failed to assign RBAC permissions: {error_msg}") from e
        except Exception as e:
            raise KeyVaultError(f"Unexpected error assigning RBAC permissions: {e}") from e

    @property
    def client(self) -> SecretClient:
        """Get or create Key Vault SecretClient.

        Returns:
            Initialized SecretClient

        Raises:
            KeyVaultError: If client creation fails
        """
        if self._client is None:
            try:
                self._client = SecretClient(
                    vault_url=self.config.vault_url, credential=self.config.credentials
                )
                logger.debug(f"Created SecretClient for vault: {self.config.vault_name}")
            except Exception as e:
                safe_error = LogSanitizer.create_safe_error_message(
                    e, "Failed to create SecretClient"
                )
                raise KeyVaultError(safe_error) from e

        return self._client

    def _get_secret_name(self, vm_name: str) -> str:
        """Generate secret name for VM.

        Args:
            vm_name: VM name

        Returns:
            Secret name (azlin-{vm-name}-ssh-private)
        """
        safe_name = vm_name.replace("_", "-").lower()
        return f"{self.SECRET_NAME_PREFIX}{safe_name}{self.SECRET_NAME_SUFFIX}"

    def _handle_vault_exception(self, e: Exception, operation: str, secret_name: str) -> NoReturn:
        """Handle Key Vault exceptions with consistent error messages.

        Args:
            e: Exception to handle
            operation: Operation being performed (e.g., "storing", "retrieving")
            secret_name: Secret name being operated on

        Raises:
            KeyVaultError: Always raises with appropriate message
        """
        if isinstance(e, ClientAuthenticationError):
            safe_error = LogSanitizer.create_safe_error_message(
                e, f"Authentication failed {operation} key"
            )
            role = (
                "Key Vault Secrets Officer"
                if operation in ["storing", "deleting"]
                else "Key Vault Secrets User"
            )
            raise KeyVaultError(
                f"{safe_error}\n"
                f"Ensure service principal has '{role}' role on vault: {self.config.vault_name}"
            ) from e

        if isinstance(e, HttpResponseError):
            safe_error = LogSanitizer.create_safe_error_message(e, f"HTTP error {operation} key")
            if getattr(e, "status_code", None) == 403:
                role = (
                    "Key Vault Secrets Officer"
                    if operation in ["storing", "deleting"]
                    else "Key Vault Secrets User"
                )
                raise KeyVaultError(
                    f"Permission denied {operation} key in vault: {self.config.vault_name}\n"
                    f"Ensure service principal has '{role}' role.\n"
                    f"Secret name: {secret_name}\n"
                    f"Error: {safe_error}"
                ) from e
            raise KeyVaultError(f"Failed to {operation} key: {safe_error}") from e

        # Generic exception
        safe_error = LogSanitizer.create_safe_error_message(e, f"Unexpected error {operation} key")
        raise KeyVaultError(safe_error) from e

    def store_key(self, vm_name: str, private_key_path: Path) -> None:
        """Store SSH private key in Azure Key Vault.

        Args:
            vm_name: VM name (used in secret name)
            private_key_path: Path to private key file

        Raises:
            KeyVaultError: If storage fails or key unreadable

        Note: Private key content is never logged. Requires Key Vault Secrets Officer role.
        """
        # Validate private key path
        key_path = Path(private_key_path).expanduser().resolve()
        if not key_path.exists():
            raise KeyVaultError(f"Private key not found: {key_path}")

        # Read private key content (NEVER log this)
        try:
            private_key_content = key_path.read_text()
        except Exception as e:
            raise KeyVaultError(f"Failed to read private key: {e}") from e

        if not private_key_content or not private_key_content.strip():
            raise KeyVaultError(f"Private key is empty: {key_path}")

        # Generate secret name
        secret_name = self._get_secret_name(vm_name)

        # Store in Key Vault
        logger.info(f"Storing SSH key in Key Vault: {secret_name}")
        logger.debug(f"Vault: {self.config.vault_name}, VM: {vm_name}")

        try:
            self.client.set_secret(
                name=secret_name,
                value=private_key_content,
                content_type="application/x-pem-file",
                tags={
                    "vm_name": vm_name,
                    "managed_by": "azlin",
                    "type": "ssh_private_key",
                },
            )
            logger.info(f"SSH key stored successfully: {secret_name}")
        except (ClientAuthenticationError, HttpResponseError) as e:
            self._handle_vault_exception(e, "storing", secret_name)
        except Exception as e:
            safe_error = LogSanitizer.create_safe_error_message(e, "Unexpected error storing key")
            raise KeyVaultError(safe_error) from e

    def retrieve_key(self, vm_name: str, target_path: Path) -> None:
        """Retrieve SSH private key from Azure Key Vault.

        Args:
            vm_name: VM name (used in secret name)
            target_path: Path to write private key

        Raises:
            KeyVaultError: If retrieval fails or key not found

        Note: Sets file permissions to 0600. Requires Key Vault Secrets User role.
        """
        # Generate secret name
        secret_name = self._get_secret_name(vm_name)

        logger.info(f"Retrieving SSH key from Key Vault: {secret_name}")
        logger.debug(f"Vault: {self.config.vault_name}, VM: {vm_name}")

        private_key_content: str
        try:
            # Retrieve from Key Vault
            secret = self.client.get_secret(secret_name)
            key_value = secret.value

            if not key_value:
                raise KeyVaultError(f"Retrieved key is empty: {secret_name}")

            private_key_content = key_value

        except ResourceNotFoundError as e:
            raise KeyVaultError(
                f"SSH key not found in Key Vault: {secret_name}\n"
                f"Vault: {self.config.vault_name}\n"
                f"VM: {vm_name}\n"
                f"The key may not have been stored with --store-key during VM creation."
            ) from e
        except (ClientAuthenticationError, HttpResponseError) as e:
            self._handle_vault_exception(e, "retrieving", secret_name)
        except KeyVaultError:
            raise
        except Exception as e:
            safe_error = LogSanitizer.create_safe_error_message(
                e, "Unexpected error retrieving key"
            )
            raise KeyVaultError(safe_error) from e

        # Write to target path with secure permissions
        target_path = Path(target_path).expanduser().resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Write key to file (NEVER log content)
        try:
            fd = os.open(target_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            try:
                os.write(fd, private_key_content.encode("utf-8"))
            finally:
                os.close(fd)

            target_path.chmod(0o600)  # Defense in depth
            logger.info(f"SSH key retrieved and saved to: {target_path}")

            # Regenerate public key from private key to ensure they match (Issue #578)
            # Bug fix: Public key file must be updated when private key changes
            try:
                pub_key_result = subprocess.run(
                    ["ssh-keygen", "-y", "-f", str(target_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
                pub_key_content = pub_key_result.stdout.strip()
                pub_key_path = Path(str(target_path) + ".pub")
                pub_key_path.write_text(pub_key_content + "\n")
                pub_key_path.chmod(0o644)
                logger.info(f"Public key regenerated: {pub_key_path}")
            except Exception as e:
                logger.warning(f"Failed to regenerate public key (non-critical): {e}")

        except Exception as e:
            raise KeyVaultError(f"Failed to write key to file: {e}") from e

    def delete_key(self, vm_name: str) -> bool:
        """Delete SSH private key from Azure Key Vault.

        Args:
            vm_name: VM name (used in secret name)

        Returns:
            True if deleted, False if not found

        Raises:
            KeyVaultError: If deletion fails (but not if key doesn't exist)

        Note: Requires Key Vault Secrets Officer role.
        """
        secret_name = self._get_secret_name(vm_name)

        logger.info(f"Deleting SSH key from Key Vault: {secret_name}")
        logger.debug(f"Vault: {self.config.vault_name}, VM: {vm_name}")

        try:
            self.client.begin_delete_secret(secret_name).result()
            logger.info(f"SSH key deleted successfully: {secret_name}")
            return True
        except ResourceNotFoundError:
            logger.debug(f"SSH key not found (already deleted?): {secret_name}")
            return False
        except (ClientAuthenticationError, HttpResponseError) as e:
            self._handle_vault_exception(e, "deleting", secret_name)
            return False  # Unreachable, but satisfies type checker
        except Exception as e:
            safe_error = LogSanitizer.create_safe_error_message(e, "Unexpected error deleting key")
            raise KeyVaultError(safe_error) from e

    def key_exists(self, vm_name: str) -> bool:
        """Check if SSH key exists in Key Vault.

        Args:
            vm_name: VM name (used in secret name)

        Returns:
            True if key exists, False otherwise

        Raises:
            KeyVaultError: If check fails (connectivity, permissions, etc.)
        """
        secret_name = self._get_secret_name(vm_name)

        try:
            self.client.get_secret(secret_name)
            return True
        except ResourceNotFoundError:
            return False
        except (ClientAuthenticationError, HttpResponseError) as e:
            self._handle_vault_exception(e, "checking", secret_name)
            return False  # Unreachable, but satisfies type checker
        except Exception as e:
            safe_error = LogSanitizer.create_safe_error_message(e, "Unexpected error checking key")
            raise KeyVaultError(safe_error) from e


def create_key_vault_manager(
    vault_name: str, subscription_id: str, tenant_id: str, auth_config: AuthConfig
) -> SSHKeyVaultManager:
    """Create Key Vault manager with authentication.

    Args:
        vault_name: Key Vault name
        subscription_id: Azure subscription ID
        tenant_id: Azure tenant ID
        auth_config: Authentication configuration

    Returns:
        Configured SSHKeyVaultManager

    Raises:
        KeyVaultError: If authentication fails or config invalid
    """
    try:
        result = AuthenticationChain.authenticate(auth_config)

        if not result.success or result.credentials is None:
            raise KeyVaultError(f"Authentication failed: {result.error}")

        config = KeyVaultConfig(
            vault_name=vault_name,
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            credentials=result.credentials,
        )

        return SSHKeyVaultManager(config)

    except AuthenticationChainError as e:
        raise KeyVaultError(f"Authentication failed: {e}") from e
    except Exception as e:
        safe_error = LogSanitizer.create_safe_error_message(e, "Failed to create Key Vault manager")
        raise KeyVaultError(safe_error) from e


def create_key_vault_manager_with_auto_setup(
    resource_group: str,
    location: str,
    subscription_id: str,
    tenant_id: str,
    auth_config: AuthConfig,
) -> SSHKeyVaultManager:
    """Create Key Vault manager with automatic setup (vault creation + RBAC).

    This is the main entry point for transparent Key Vault usage. It will:
    1. Find or create Key Vault in the resource group
    2. Get current user principal ID
    3. Ensure RBAC permissions are assigned
    4. Return configured manager

    Args:
        resource_group: Resource group name
        location: Azure region
        subscription_id: Azure subscription ID
        tenant_id: Azure tenant ID
        auth_config: Authentication configuration

    Returns:
        Configured SSHKeyVaultManager ready to use

    Raises:
        KeyVaultError: If setup or authentication fails

    Note:
        - Silent operation (only logs at debug level)
        - Idempotent (safe to call multiple times)
        - Works with Azure CLI auth (current user) or service principal
    """
    try:
        # Step 1: Ensure Key Vault exists (find or create)
        vault_name = SSHKeyVaultManager.ensure_key_vault_exists(
            resource_group=resource_group,
            location=location,
            subscription_id=subscription_id,
        )

        # Step 2: Get current user principal ID
        principal_id = get_current_user_principal_id()

        # Step 3: Ensure RBAC permissions
        SSHKeyVaultManager.ensure_rbac_permissions(
            vault_name=vault_name,
            resource_group=resource_group,
            subscription_id=subscription_id,
            principal_id=principal_id,
        )

        # Step 4: Create manager with authentication
        manager = create_key_vault_manager(
            vault_name=vault_name,
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            auth_config=auth_config,
        )

        logger.debug(f"Key Vault manager created with auto-setup: {vault_name}")
        return manager

    except KeyVaultError:
        raise
    except Exception as e:
        safe_error = LogSanitizer.create_safe_error_message(
            e, "Failed to create Key Vault manager with auto-setup"
        )
        raise KeyVaultError(safe_error) from e


__all__ = [
    "KeyVaultConfig",
    "KeyVaultError",
    "SSHKeyVaultManager",
    "create_key_vault_manager",
    "create_key_vault_manager_with_auto_setup",
    "generate_key_vault_name",
    "get_current_user_principal_id",
]
