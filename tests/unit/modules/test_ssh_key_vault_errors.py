"""Comprehensive error path tests for ssh_key_vault module.

Tests all error conditions including:
- Subprocess failures and timeouts
- Azure CLI errors (authentication, permissions, resource not found)
- JSON parsing failures
- File system errors
- Network errors
- Key Vault configuration errors
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from azlin.auth_models import AuthConfig, AuthMethod
from azlin.authentication_chain import AuthenticationChainError
from azlin.modules.ssh_key_vault import (
    KeyVaultConfig,
    KeyVaultError,
    SSHKeyVaultManager,
    create_key_vault_manager,
    create_key_vault_manager_with_auto_setup,
    generate_key_vault_name,
    get_current_user_principal_id,
)


class TestGetCurrentUserPrincipalIdErrors:
    """Error tests for get_current_user_principal_id function."""

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_get_principal_id_timeout(self, mock_run):
        """Test timeout during get principal ID."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["az", "ad", "signed-in-user", "show"], timeout=30
        )

        with pytest.raises(KeyVaultError, match="Azure CLI command timed out"):
            get_current_user_principal_id()

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_get_principal_id_empty_response(self, mock_run):
        """Test empty response from Azure CLI."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["az"], returncode=0, stdout="", stderr=""
        )

        with pytest.raises(KeyVaultError, match="Failed to get principal ID: empty response"):
            get_current_user_principal_id()

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_get_principal_id_not_logged_in(self, mock_run):
        """Test error when user not logged in to Azure CLI."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["az"], stderr="Please run 'az login'"
        )

        with pytest.raises(KeyVaultError, match="Failed to get current user principal ID"):
            get_current_user_principal_id()

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_get_principal_id_service_principal_timeout(self, mock_run):
        """Test timeout when getting service principal info."""
        # First call fails (signed-in user)
        # Second call times out (service principal)
        mock_run.side_effect = [
            subprocess.CalledProcessError(returncode=1, cmd=["az"], stderr="No user signed in"),
            subprocess.TimeoutExpired(cmd=["az", "account", "show"], timeout=30),
        ]

        with pytest.raises(KeyVaultError, match="Failed to get current user principal ID"):
            get_current_user_principal_id()

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_get_principal_id_unexpected_error(self, mock_run):
        """Test unexpected error during get principal ID."""
        mock_run.side_effect = RuntimeError("Unexpected runtime error")

        with pytest.raises(KeyVaultError, match="Unexpected error getting principal ID"):
            get_current_user_principal_id()


class TestGenerateKeyVaultName:
    """Tests for generate_key_vault_name function."""

    def test_generate_vault_name_consistent(self):
        """Test that vault name generation is consistent for same subscription."""
        subscription_id = "12345678-1234-1234-1234-123456789abc"
        name1 = generate_key_vault_name(subscription_id)
        name2 = generate_key_vault_name(subscription_id)

        assert name1 == name2
        assert name1.startswith("azlin-kv-")
        assert len(name1) == 15  # azlin-kv-{6 chars}


class TestKeyVaultConfigErrors:
    """Additional error tests for KeyVaultConfig."""

    def test_empty_tenant_id(self):
        """Test validation fails with empty tenant_id."""
        mock_credentials = Mock()
        with pytest.raises(KeyVaultError, match="tenant_id cannot be empty"):
            KeyVaultConfig(
                vault_name="my-vault",
                subscription_id="sub-123",
                tenant_id="",
                credentials=mock_credentials,
            )


class TestSSHKeyVaultManagerEnsureKeyVaultExists:
    """Error tests for ensure_key_vault_exists static method."""

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group")
    def test_ensure_vault_create_timeout(self, mock_find, mock_run):
        """Test timeout during Key Vault creation."""
        mock_find.return_value = None  # No existing vault

        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["az", "keyvault", "create"], timeout=30
        )

        with pytest.raises(KeyVaultError, match="Azure CLI command timed out"):
            SSHKeyVaultManager.ensure_key_vault_exists(
                resource_group="rg", location="eastus", subscription_id="sub-123"
            )

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group")
    def test_ensure_vault_create_already_exists_race(self, mock_find, mock_run):
        """Test race condition where vault is created between check and create."""
        mock_find.return_value = None  # No existing vault

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["az"], stderr="vault already exists"
        )

        # Should return vault name, not raise error
        vault_name = SSHKeyVaultManager.ensure_key_vault_exists(
            resource_group="rg", location="eastus", subscription_id="sub-123"
        )

        assert vault_name.startswith("azlin-kv-")

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group")
    def test_ensure_vault_create_quota_exceeded(self, mock_find, mock_run):
        """Test quota exceeded error during vault creation."""
        mock_find.return_value = None

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["az"], stderr="Quota exceeded for Key Vaults"
        )

        with pytest.raises(KeyVaultError, match="Failed to create Key Vault"):
            SSHKeyVaultManager.ensure_key_vault_exists(
                resource_group="rg", location="eastus", subscription_id="sub-123"
            )

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group")
    def test_ensure_vault_create_unexpected_error(self, mock_find, mock_run):
        """Test unexpected error during vault creation."""
        mock_find.return_value = None

        mock_run.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(KeyVaultError, match="Unexpected error creating Key Vault"):
            SSHKeyVaultManager.ensure_key_vault_exists(
                resource_group="rg", location="eastus", subscription_id="sub-123"
            )


class TestSSHKeyVaultManagerFindKeyVault:
    """Error tests for find_key_vault_in_resource_group static method."""

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_find_vault_timeout(self, mock_run):
        """Test timeout during vault search."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["az", "keyvault", "list"], timeout=30
        )

        result = SSHKeyVaultManager.find_key_vault_in_resource_group(
            resource_group="rg", subscription_id="sub-123"
        )

        assert result is None  # Should return None, not raise

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_find_vault_invalid_json(self, mock_run):
        """Test invalid JSON response from Azure CLI."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["az"], returncode=0, stdout="not valid json{", stderr=""
        )

        result = SSHKeyVaultManager.find_key_vault_in_resource_group(
            resource_group="rg", subscription_id="sub-123"
        )

        assert result is None  # Should handle gracefully

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_find_vault_resource_group_not_found(self, mock_run):
        """Test resource group not found error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["az"], stderr="ResourceGroupNotFound"
        )

        result = SSHKeyVaultManager.find_key_vault_in_resource_group(
            resource_group="nonexistent-rg", subscription_id="sub-123"
        )

        assert result is None


class TestSSHKeyVaultManagerEnsureRBACPermissions:
    """Error tests for ensure_rbac_permissions static method."""

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_ensure_rbac_get_vault_scope_timeout(self, mock_run):
        """Test timeout when getting vault scope."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["az", "keyvault", "show"], timeout=30
        )

        with pytest.raises(KeyVaultError, match="Azure CLI command timed out"):
            SSHKeyVaultManager.ensure_rbac_permissions(
                vault_name="vault",
                resource_group="rg",
                subscription_id="sub-123",
                principal_id="principal-123",
            )

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_ensure_rbac_list_assignments_timeout(self, mock_run):
        """Test timeout when listing role assignments."""
        # First call succeeds (get vault scope)
        # Second call times out (list assignments)
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["az"], returncode=0, stdout="/subscriptions/sub/vaults/vault\n", stderr=""
            ),
            subprocess.TimeoutExpired(cmd=["az", "role", "assignment", "list"], timeout=30),
        ]

        with pytest.raises(KeyVaultError, match="Azure CLI command timed out"):
            SSHKeyVaultManager.ensure_rbac_permissions(
                vault_name="vault",
                resource_group="rg",
                subscription_id="sub-123",
                principal_id="principal-123",
            )

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_ensure_rbac_assignment_create_race_condition(self, mock_run):
        """Test race condition where role is assigned between check and create."""
        # Get vault scope
        # List assignments (empty)
        # Create assignment (already exists error)
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["az"], returncode=0, stdout="/subscriptions/sub/vaults/vault\n", stderr=""
            ),
            subprocess.CompletedProcess(args=["az"], returncode=0, stdout="[]\n", stderr=""),
            subprocess.CalledProcessError(
                returncode=1, cmd=["az"], stderr="role assignment already exists"
            ),
        ]

        # Should not raise error
        SSHKeyVaultManager.ensure_rbac_permissions(
            vault_name="vault",
            resource_group="rg",
            subscription_id="sub-123",
            principal_id="principal-123",
        )

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_ensure_rbac_insufficient_permissions(self, mock_run):
        """Test error when user lacks permissions to assign roles."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["az"], returncode=0, stdout="/subscriptions/sub/vaults/vault\n", stderr=""
            ),
            subprocess.CompletedProcess(args=["az"], returncode=0, stdout="[]\n", stderr=""),
            subprocess.CalledProcessError(
                returncode=1,
                cmd=["az"],
                stderr="The client 'user@example.com' does not have authorization",
            ),
        ]

        with pytest.raises(KeyVaultError, match="Failed to assign RBAC permissions"):
            SSHKeyVaultManager.ensure_rbac_permissions(
                vault_name="vault",
                resource_group="rg",
                subscription_id="sub-123",
                principal_id="principal-123",
            )

    @patch("azlin.modules.ssh_key_vault.subprocess.run")
    def test_ensure_rbac_unexpected_error(self, mock_run):
        """Test unexpected error during RBAC operations."""
        mock_run.side_effect = RuntimeError("Unexpected runtime error")

        with pytest.raises(KeyVaultError, match="Unexpected error assigning RBAC permissions"):
            SSHKeyVaultManager.ensure_rbac_permissions(
                vault_name="vault",
                resource_group="rg",
                subscription_id="sub-123",
                principal_id="principal-123",
            )


class TestSSHKeyVaultManagerClientErrors:
    """Error tests for SecretClient creation."""

    def test_client_creation_failure(self):
        """Test error when SecretClient creation fails."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        with patch("azlin.modules.ssh_key_vault.SecretClient") as mock_secret_client:
            mock_secret_client.side_effect = Exception("Network error creating client")

            with pytest.raises(KeyVaultError, match="Failed to create SecretClient"):
                _ = manager.client


class TestSSHKeyVaultManagerStoreKeyErrors:
    """Additional error tests for store_key method."""

    @pytest.fixture
    def temp_key_file(self, tmp_path):
        """Create temporary SSH key file."""
        key_file = tmp_path / "test_key"
        key_file.write_text(
            "-----BEGIN OPENSSH PRIVATE KEY-----\ntest-key-content\n-----END OPENSSH PRIVATE KEY-----\n"
        )
        return key_file

    def test_store_key_read_permission_denied(self, tmp_path):
        """Test error when unable to read key file due to permissions."""
        key_file = tmp_path / "unreadable_key"
        key_file.write_text("key content")
        key_file.chmod(0o000)  # Remove all permissions

        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        try:
            with pytest.raises(KeyVaultError, match="Failed to read private key"):
                manager.store_key("dev-vm", key_file)
        finally:
            key_file.chmod(0o600)  # Restore permissions for cleanup

    def test_store_key_whitespace_only(self, tmp_path):
        """Test error when key file contains only whitespace."""
        key_file = tmp_path / "whitespace_key"
        key_file.write_text("   \n\t\n  ")

        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        with pytest.raises(KeyVaultError, match="Private key is empty"):
            manager.store_key("dev-vm", key_file)

    def test_store_key_http_error_other_status(self, temp_key_file):
        """Test handling of HTTP errors with non-403 status codes."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_response = Mock()
        mock_response.status_code = 500

        mock_client = Mock()
        manager._client = mock_client
        mock_client.set_secret.side_effect = HttpResponseError(response=mock_response)

        with pytest.raises(KeyVaultError, match="Failed to storing key"):
            manager.store_key("dev-vm", temp_key_file)

    def test_store_key_generic_exception(self, temp_key_file):
        """Test handling of generic exceptions during storage."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_client = Mock()
        manager._client = mock_client
        mock_client.set_secret.side_effect = RuntimeError("Unexpected runtime error")

        with pytest.raises(KeyVaultError, match="Unexpected error storing key"):
            manager.store_key("dev-vm", temp_key_file)


class TestSSHKeyVaultManagerRetrieveKeyErrors:
    """Additional error tests for retrieve_key method."""

    def test_retrieve_key_empty_value(self, tmp_path):
        """Test error when retrieved key value is empty."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        target_path = tmp_path / "retrieved_key"

        mock_client = Mock()
        manager._client = mock_client
        mock_secret = Mock()
        mock_secret.value = ""  # Empty value
        mock_client.get_secret.return_value = mock_secret

        with pytest.raises(KeyVaultError, match="Retrieved key is empty"):
            manager.retrieve_key("dev-vm", target_path)

    def test_retrieve_key_write_permission_denied(self, tmp_path):
        """Test error when unable to write key file due to permissions."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        # Create directory with no write permissions
        target_dir = tmp_path / "readonly_dir"
        target_dir.mkdir(mode=0o500)
        target_path = target_dir / "retrieved_key"

        mock_client = Mock()
        manager._client = mock_client
        mock_secret = Mock()
        mock_secret.value = "key content"
        mock_client.get_secret.return_value = mock_secret

        try:
            with pytest.raises(KeyVaultError, match="Failed to write key to file"):
                manager.retrieve_key("dev-vm", target_path)
        finally:
            target_dir.chmod(0o700)  # Restore permissions for cleanup

    def test_retrieve_key_authentication_error(self, tmp_path):
        """Test handling of authentication error during retrieval."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        target_path = tmp_path / "retrieved_key"

        mock_client = Mock()
        manager._client = mock_client
        mock_client.get_secret.side_effect = ClientAuthenticationError("Auth failed")

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            manager.retrieve_key("dev-vm", target_path)

    def test_retrieve_key_generic_exception(self, tmp_path):
        """Test handling of generic exceptions during retrieval."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        target_path = tmp_path / "retrieved_key"

        mock_client = Mock()
        manager._client = mock_client
        mock_client.get_secret.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(KeyVaultError, match="Unexpected error retrieving key"):
            manager.retrieve_key("dev-vm", target_path)


class TestSSHKeyVaultManagerDeleteKeyErrors:
    """Additional error tests for delete_key method."""

    def test_delete_key_authentication_error(self):
        """Test handling of authentication error during deletion."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_client = Mock()
        manager._client = mock_client
        mock_client.begin_delete_secret.side_effect = ClientAuthenticationError("Auth failed")

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            manager.delete_key("dev-vm")

    def test_delete_key_generic_exception(self):
        """Test handling of generic exceptions during deletion."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_client = Mock()
        manager._client = mock_client
        mock_client.begin_delete_secret.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(KeyVaultError, match="Unexpected error deleting key"):
            manager.delete_key("dev-vm")


class TestSSHKeyVaultManagerKeyExistsErrors:
    """Additional error tests for key_exists method."""

    def test_key_exists_authentication_error(self):
        """Test handling of authentication error in key_exists."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_client = Mock()
        manager._client = mock_client
        mock_client.get_secret.side_effect = ClientAuthenticationError("Auth failed")

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            manager.key_exists("dev-vm")

    def test_key_exists_generic_exception(self):
        """Test handling of generic exceptions in key_exists."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_client = Mock()
        manager._client = mock_client
        mock_client.get_secret.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(KeyVaultError, match="Unexpected error checking key"):
            manager.key_exists("dev-vm")


class TestCreateKeyVaultManagerErrors:
    """Additional error tests for create_key_vault_manager function."""

    @patch("azlin.modules.ssh_key_vault.AuthenticationChain")
    def test_create_manager_credentials_none(self, mock_auth_chain):
        """Test error when authentication returns None credentials."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.credentials = None  # Success but no credentials
        mock_auth_chain.authenticate.return_value = mock_result

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            create_key_vault_manager(
                vault_name="my-vault",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )

    @patch("azlin.modules.ssh_key_vault.AuthenticationChain")
    def test_create_manager_auth_chain_exception(self, mock_auth_chain):
        """Test error when AuthenticationChain raises exception."""
        mock_auth_chain.authenticate.side_effect = AuthenticationChainError(
            "Authentication chain failed"
        )

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            create_key_vault_manager(
                vault_name="my-vault",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )

    @patch("azlin.modules.ssh_key_vault.AuthenticationChain")
    def test_create_manager_generic_exception(self, mock_auth_chain):
        """Test generic exception during manager creation."""
        mock_auth_chain.authenticate.side_effect = RuntimeError("Unexpected error")

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Failed to create Key Vault manager"):
            create_key_vault_manager(
                vault_name="my-vault",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )


class TestCreateKeyVaultManagerWithAutoSetupErrors:
    """Error tests for create_key_vault_manager_with_auto_setup function."""

    @patch("azlin.modules.ssh_key_vault.create_key_vault_manager")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_rbac_permissions")
    @patch("azlin.modules.ssh_key_vault.get_current_user_principal_id")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_key_vault_exists")
    def test_auto_setup_vault_creation_fails(
        self, mock_ensure_vault, mock_get_principal, mock_ensure_rbac, mock_create
    ):
        """Test error when vault creation fails during auto-setup."""
        mock_ensure_vault.side_effect = KeyVaultError("Failed to create vault")

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Failed to create vault"):
            create_key_vault_manager_with_auto_setup(
                resource_group="rg",
                location="eastus",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )

    @patch("azlin.modules.ssh_key_vault.create_key_vault_manager")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_rbac_permissions")
    @patch("azlin.modules.ssh_key_vault.get_current_user_principal_id")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_key_vault_exists")
    def test_auto_setup_principal_id_fails(
        self, mock_ensure_vault, mock_get_principal, mock_ensure_rbac, mock_create
    ):
        """Test error when getting principal ID fails during auto-setup."""
        mock_ensure_vault.return_value = "azlin-kv-abc123"
        mock_get_principal.side_effect = KeyVaultError("Failed to get principal ID")

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Failed to get principal ID"):
            create_key_vault_manager_with_auto_setup(
                resource_group="rg",
                location="eastus",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )

    @patch("azlin.modules.ssh_key_vault.create_key_vault_manager")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_rbac_permissions")
    @patch("azlin.modules.ssh_key_vault.get_current_user_principal_id")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_key_vault_exists")
    def test_auto_setup_rbac_assignment_fails(
        self, mock_ensure_vault, mock_get_principal, mock_ensure_rbac, mock_create
    ):
        """Test error when RBAC assignment fails during auto-setup."""
        mock_ensure_vault.return_value = "azlin-kv-abc123"
        mock_get_principal.return_value = "principal-123"
        mock_ensure_rbac.side_effect = KeyVaultError("Failed to assign RBAC permissions")

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Failed to assign RBAC permissions"):
            create_key_vault_manager_with_auto_setup(
                resource_group="rg",
                location="eastus",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )

    @patch("azlin.modules.ssh_key_vault.create_key_vault_manager")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_rbac_permissions")
    @patch("azlin.modules.ssh_key_vault.get_current_user_principal_id")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_key_vault_exists")
    def test_auto_setup_manager_creation_fails(
        self, mock_ensure_vault, mock_get_principal, mock_ensure_rbac, mock_create
    ):
        """Test error when manager creation fails during auto-setup."""
        mock_ensure_vault.return_value = "azlin-kv-abc123"
        mock_get_principal.return_value = "principal-123"
        mock_ensure_rbac.return_value = None
        mock_create.side_effect = KeyVaultError("Failed to create manager")

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Failed to create manager"):
            create_key_vault_manager_with_auto_setup(
                resource_group="rg",
                location="eastus",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )

    @patch("azlin.modules.ssh_key_vault.create_key_vault_manager")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_rbac_permissions")
    @patch("azlin.modules.ssh_key_vault.get_current_user_principal_id")
    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.ensure_key_vault_exists")
    def test_auto_setup_generic_exception(
        self, mock_ensure_vault, mock_get_principal, mock_ensure_rbac, mock_create
    ):
        """Test generic exception during auto-setup."""
        mock_ensure_vault.side_effect = RuntimeError("Unexpected error")

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Failed to create Key Vault manager"):
            create_key_vault_manager_with_auto_setup(
                resource_group="rg",
                location="eastus",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )
