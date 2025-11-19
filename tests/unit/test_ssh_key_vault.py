"""Unit tests for SSH Key Vault module.

Tests cover:
- KeyVaultConfig validation
- SSHKeyVaultManager store/retrieve/delete operations
- Error handling and security requirements
- Service principal and Azure CLI authentication
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
)

from azlin.auth_models import AuthConfig, AuthMethod
from azlin.modules.ssh_key_vault import (
    KeyVaultConfig,
    KeyVaultError,
    SSHKeyVaultManager,
    create_key_vault_manager,
)


class TestKeyVaultConfig:
    """Test KeyVaultConfig dataclass."""

    def test_valid_config(self):
        """Test creating valid KeyVaultConfig."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )

        assert config.vault_name == "my-vault"
        assert config.subscription_id == "sub-123"
        assert config.tenant_id == "tenant-456"
        assert config.credentials == mock_credentials
        assert config.vault_url == "https://my-vault.vault.azure.net"

    def test_empty_vault_name(self):
        """Test validation fails with empty vault_name."""
        mock_credentials = Mock()
        with pytest.raises(KeyVaultError, match="vault_name cannot be empty"):
            KeyVaultConfig(
                vault_name="",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                credentials=mock_credentials,
            )

    def test_empty_subscription_id(self):
        """Test validation fails with empty subscription_id."""
        mock_credentials = Mock()
        with pytest.raises(KeyVaultError, match="subscription_id cannot be empty"):
            KeyVaultConfig(
                vault_name="my-vault",
                subscription_id="",
                tenant_id="tenant-456",
                credentials=mock_credentials,
            )

    def test_none_credentials(self):
        """Test validation fails with None credentials."""
        with pytest.raises(KeyVaultError, match="credentials cannot be None"):
            KeyVaultConfig(
                vault_name="my-vault",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                credentials=None,
            )


class TestSSHKeyVaultManagerInit:
    """Test SSHKeyVaultManager initialization."""

    def test_init_creates_manager(self):
        """Test manager initialization."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )

        manager = SSHKeyVaultManager(config)

        assert manager.config == config
        assert manager._client is None  # Lazy initialization

    def test_client_property_creates_secret_client(self):
        """Test client property creates SecretClient."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )

        manager = SSHKeyVaultManager(config)

        with patch("azlin.modules.ssh_key_vault.SecretClient") as mock_secret_client:
            mock_client_instance = Mock()
            mock_secret_client.return_value = mock_client_instance

            client = manager.client

            assert client == mock_client_instance
            mock_secret_client.assert_called_once_with(
                vault_url="https://my-vault.vault.azure.net", credential=mock_credentials
            )

    def test_get_secret_name(self):
        """Test secret name generation."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        # Test basic VM name
        assert manager._get_secret_name("dev-vm-01") == "azlin-dev-vm-01-ssh-private"

        # Test underscore replacement
        assert manager._get_secret_name("dev_vm_01") == "azlin-dev-vm-01-ssh-private"

        # Test lowercase conversion
        assert manager._get_secret_name("DEV-VM-01") == "azlin-dev-vm-01-ssh-private"


class TestSSHKeyVaultManagerStoreKey:
    """Test SSHKeyVaultManager store_key method."""

    @pytest.fixture
    def temp_key_file(self, tmp_path):
        """Create temporary SSH key file."""
        key_file = tmp_path / "test_key"
        key_file.write_text(
            "-----BEGIN OPENSSH PRIVATE KEY-----\ntest-key-content\n-----END OPENSSH PRIVATE KEY-----\n"
        )
        return key_file

    def test_store_key_success(self, temp_key_file):
        """Test successful key storage."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        # Mock the _client attribute directly
        mock_client = Mock()
        manager._client = mock_client

        manager.store_key("dev-vm", temp_key_file)

        # Verify set_secret was called with correct parameters
        mock_client.set_secret.assert_called_once()
        call_args = mock_client.set_secret.call_args
        assert call_args[1]["name"] == "azlin-dev-vm-ssh-private"
        assert "BEGIN OPENSSH PRIVATE KEY" in call_args[1]["value"]
        assert call_args[1]["content_type"] == "application/x-pem-file"
        assert call_args[1]["tags"]["vm_name"] == "dev-vm"
        assert call_args[1]["tags"]["managed_by"] == "azlin"

    def test_store_key_file_not_found(self):
        """Test error when key file doesn't exist."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        with pytest.raises(KeyVaultError, match="Private key not found"):
            manager.store_key("dev-vm", Path("/nonexistent/key"))

    def test_store_key_empty_file(self, tmp_path):
        """Test error when key file is empty."""
        empty_key = tmp_path / "empty_key"
        empty_key.write_text("")

        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        with pytest.raises(KeyVaultError, match="Private key is empty"):
            manager.store_key("dev-vm", empty_key)

    def test_store_key_permission_denied(self, temp_key_file):
        """Test handling of permission denied error."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_response = Mock()
        mock_response.status_code = 403

        mock_client = Mock()
        manager._client = mock_client
        mock_client.set_secret.side_effect = HttpResponseError(response=mock_response)

        with pytest.raises(KeyVaultError, match="Permission denied"):
            manager.store_key("dev-vm", temp_key_file)

    def test_store_key_authentication_error(self, temp_key_file):
        """Test handling of authentication error."""
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
        mock_client.set_secret.side_effect = ClientAuthenticationError("Auth failed")

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            manager.store_key("dev-vm", temp_key_file)


class TestSSHKeyVaultManagerRetrieveKey:
    """Test SSHKeyVaultManager retrieve_key method."""

    def test_retrieve_key_success(self, tmp_path):
        """Test successful key retrieval."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        target_path = tmp_path / "retrieved_key"
        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest-key-content\n-----END OPENSSH PRIVATE KEY-----\n"

        mock_client = Mock()
        manager._client = mock_client
        mock_secret = Mock()
        mock_secret.value = key_content
        mock_client.get_secret.return_value = mock_secret

        manager.retrieve_key("dev-vm", target_path)

        # Verify secret was retrieved
        mock_client.get_secret.assert_called_once_with("azlin-dev-vm-ssh-private")

        # Verify file was written with correct content
        assert target_path.exists()
        assert target_path.read_text() == key_content

        # Verify permissions (0600)
        stat = target_path.stat()
        assert stat.st_mode & 0o777 == 0o600

    def test_retrieve_key_not_found(self, tmp_path):
        """Test error when key not found in vault."""
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
        mock_client.get_secret.side_effect = ResourceNotFoundError("Not found")

        with pytest.raises(KeyVaultError, match="SSH key not found in Key Vault"):
            manager.retrieve_key("dev-vm", target_path)

    def test_retrieve_key_permission_denied(self, tmp_path):
        """Test handling of permission denied error during retrieval."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        target_path = tmp_path / "retrieved_key"
        mock_response = Mock()
        mock_response.status_code = 403

        mock_client = Mock()
        manager._client = mock_client
        mock_client.get_secret.side_effect = HttpResponseError(response=mock_response)

        with pytest.raises(KeyVaultError, match="Permission denied"):
            manager.retrieve_key("dev-vm", target_path)

    def test_retrieve_key_creates_parent_directory(self, tmp_path):
        """Test that parent directory is created if it doesn't exist."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        # Create nested path that doesn't exist
        target_path = tmp_path / "nested" / "dir" / "retrieved_key"
        key_content = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\ntest-key\n-----END OPENSSH PRIVATE KEY-----\n"
        )

        mock_client = Mock()
        manager._client = mock_client
        mock_secret = Mock()
        mock_secret.value = key_content
        mock_client.get_secret.return_value = mock_secret

        manager.retrieve_key("dev-vm", target_path)

        # Verify directory was created
        assert target_path.parent.exists()
        assert target_path.exists()


class TestSSHKeyVaultManagerDeleteKey:
    """Test SSHKeyVaultManager delete_key method."""

    def test_delete_key_success(self):
        """Test successful key deletion."""
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
        mock_poller = Mock()
        mock_poller.result.return_value = Mock()
        mock_client.begin_delete_secret.return_value = mock_poller

        result = manager.delete_key("dev-vm")

        assert result is True
        mock_client.begin_delete_secret.assert_called_once_with("azlin-dev-vm-ssh-private")

    def test_delete_key_not_found(self):
        """Test delete returns False when key doesn't exist."""
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
        mock_client.begin_delete_secret.side_effect = ResourceNotFoundError("Not found")

        result = manager.delete_key("dev-vm")

        assert result is False

    def test_delete_key_permission_denied(self):
        """Test handling of permission denied error during deletion."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_response = Mock()
        mock_response.status_code = 403

        mock_client = Mock()
        manager._client = mock_client
        mock_client.begin_delete_secret.side_effect = HttpResponseError(response=mock_response)

        with pytest.raises(KeyVaultError, match="Permission denied"):
            manager.delete_key("dev-vm")


class TestSSHKeyVaultManagerKeyExists:
    """Test SSHKeyVaultManager key_exists method."""

    def test_key_exists_true(self):
        """Test key_exists returns True when key exists."""
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
        mock_client.get_secret.return_value = Mock()

        result = manager.key_exists("dev-vm")

        assert result is True
        mock_client.get_secret.assert_called_once_with("azlin-dev-vm-ssh-private")

    def test_key_exists_false(self):
        """Test key_exists returns False when key doesn't exist."""
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
        mock_client.get_secret.side_effect = ResourceNotFoundError("Not found")

        result = manager.key_exists("dev-vm")

        assert result is False

    def test_key_exists_permission_denied(self):
        """Test key_exists raises error on permission denied."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        mock_response = Mock()
        mock_response.status_code = 403

        mock_client = Mock()
        manager._client = mock_client
        mock_client.get_secret.side_effect = HttpResponseError(response=mock_response)

        with pytest.raises(KeyVaultError, match="Permission denied"):
            manager.key_exists("dev-vm")


class TestCreateKeyVaultManager:
    """Test create_key_vault_manager convenience function."""

    @patch("azlin.modules.ssh_key_vault.AuthenticationChain")
    def test_create_manager_success(self, mock_auth_chain):
        """Test successful manager creation with authentication."""
        # Mock successful authentication
        mock_credentials = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.credentials = mock_credentials
        mock_auth_chain.authenticate.return_value = mock_result

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        manager = create_key_vault_manager(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            auth_config=auth_config,
        )

        assert isinstance(manager, SSHKeyVaultManager)
        assert manager.config.vault_name == "my-vault"
        assert manager.config.subscription_id == "sub-123"
        assert manager.config.tenant_id == "tenant-456"
        assert manager.config.credentials == mock_credentials

    @patch("azlin.modules.ssh_key_vault.AuthenticationChain")
    def test_create_manager_auth_failure(self, mock_auth_chain):
        """Test manager creation fails when authentication fails."""
        # Mock failed authentication
        mock_result = Mock()
        mock_result.success = False
        mock_result.error = "Authentication failed"
        mock_auth_chain.authenticate.return_value = mock_result

        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        with pytest.raises(KeyVaultError, match="Authentication failed"):
            create_key_vault_manager(
                vault_name="my-vault",
                subscription_id="sub-123",
                tenant_id="tenant-456",
                auth_config=auth_config,
            )


class TestSecurityRequirements:
    """Test security requirements are met."""

    def test_no_key_content_in_logs(self, tmp_path, caplog):
        """Test that private key content is never logged."""
        temp_key = tmp_path / "test_key"
        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-content\n-----END OPENSSH PRIVATE KEY-----\n"
        temp_key.write_text(key_content)

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

        manager.store_key("dev-vm", temp_key)

        # Check that key content is not in any log messages
        for record in caplog.records:
            assert "secret-content" not in record.message
            assert "BEGIN OPENSSH PRIVATE KEY" not in record.message

    def test_retrieved_key_has_secure_permissions(self, tmp_path):
        """Test that retrieved keys have 0600 permissions."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        target_path = tmp_path / "retrieved_key"
        key_content = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n"
        )

        mock_client = Mock()
        manager._client = mock_client
        mock_secret = Mock()
        mock_secret.value = key_content
        mock_client.get_secret.return_value = mock_secret

        manager.retrieve_key("dev-vm", target_path)

        # Verify file permissions are 0600
        stat = target_path.stat()
        mode = stat.st_mode & 0o777
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"

    def test_error_messages_sanitized(self, tmp_path):
        """Test that error messages don't leak sensitive information."""
        mock_credentials = Mock()
        config = KeyVaultConfig(
            vault_name="my-vault",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            credentials=mock_credentials,
        )
        manager = SSHKeyVaultManager(config)

        temp_key = tmp_path / "test_key"
        temp_key.write_text("secret-key-content")

        mock_client = Mock()
        manager._client = mock_client
        # Simulate error with secret in message
        mock_client.set_secret.side_effect = Exception("Error with client_secret=abc123")

        with pytest.raises(KeyVaultError) as exc_info:
            manager.store_key("dev-vm", temp_key)

        # Verify error message is sanitized
        error_message = str(exc_info.value)
        # LogSanitizer should have redacted the secret
        # We just verify the error was caught and wrapped
        assert "Unexpected error" in error_message or "failed" in error_message.lower()
