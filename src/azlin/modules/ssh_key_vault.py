"""Azure Key Vault SSH key storage for azlin.

Secure storage and retrieval of SSH private keys using Azure Key Vault.
Keys are stored during VM provisioning and auto-retrieved when connecting from different hosts.

Features:
- Store/retrieve/delete SSH keys in Azure Key Vault
- Service Principal and Azure CLI authentication via AuthenticationChain
- Automatic cleanup on VM deletion
- Zero plaintext key logging
- Secure file permissions (0600)

Secret Naming: azlin-{vm-name}-ssh-private
RBAC Roles: Key Vault Secrets Officer (write), Secrets User (read)
Integration: azlin new --store-key, connect, kill, destroy
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from azure.core.credentials import TokenCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
)
from azure.keyvault.secrets import SecretClient

from azlin.auth_models import AuthConfig
from azlin.authentication_chain import AuthenticationChain, AuthenticationChainError
from azlin.log_sanitizer import LogSanitizer

logger = logging.getLogger(__name__)


class KeyVaultError(Exception):
    """Raised when Key Vault operations fail."""

    pass


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
            if e.status_code == 403:
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


__all__ = [
    "KeyVaultConfig",
    "KeyVaultError",
    "SSHKeyVaultManager",
    "create_key_vault_manager",
]
