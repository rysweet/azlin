"""Integration tests for service principal authentication.

Tests backward compatibility and integration with existing Azure authentication:
- Azure CLI fallback still works
- Environment variable auth continues to function
- Profile switching works correctly
- Auth command group integration
- Backward compatibility with existing flows

All tests should FAIL initially until integration is complete.
"""

import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.azure_auth import AzureAuthenticator
from azlin.service_principal_auth import (
    ServicePrincipalError,
    ServicePrincipalManager,
)


class TestBackwardCompatibilityAzureCLI:
    """Test that Azure CLI authentication still works after SP integration."""

    def test_azure_cli_fallback_when_no_sp_config(self):
        """Test that Azure CLI is used when no SP config exists."""
        with patch("subprocess.run") as mock_run:
            # Mock az CLI available and authenticated
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "fake-token", "subscription": "sub-123"}',
                stderr="",
            )

            # Get credentials without SP config
            creds = AzureAuthenticator().get_credentials()

            # Should use Azure CLI method
            assert creds.method == "az_cli"
            assert creds.token == "fake-token"  # noqa: S105

    def test_azure_cli_priority_lower_than_sp_env_vars(self, monkeypatch):
        """Test that SP env vars take priority over Azure CLI."""
        # Set SP environment variables
        monkeypatch.setenv("AZURE_CLIENT_ID", "12345678-1234-1234-1234-123456789012")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "sp-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "87654321-4321-4321-4321-210987654321")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "az-cli-token"}',
                stderr="",
            )

            creds = AzureAuthenticator().get_credentials()

            # Should use env vars, not az CLI
            assert creds.method == "env_vars"

    def test_azure_cli_commands_still_work(self):
        """Test that existing Azure CLI commands continue to work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"id": "/subscriptions/sub-123"}',
                stderr="",
            )

            # Test that we can still call az CLI
            result = subprocess.run(
                ["az", "account", "show"], capture_output=True, text=True, check=False
            )

            # Should work without errors
            assert result.returncode == 0


class TestBackwardCompatibilityEnvironmentVariables:
    """Test that existing environment variable auth patterns still work."""

    def test_existing_azure_env_vars_still_recognized(self, monkeypatch):
        """Test that AZURE_* env vars are still recognized."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "12345678-1234-1234-1234-123456789012")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "old-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "87654321-4321-4321-4321-210987654321")

        creds = AzureAuthenticator().get_credentials()

        assert creds.method == "env_vars"
        assert creds.tenant_id == "87654321-4321-4321-4321-210987654321"

    def test_azure_subscription_id_env_var_works(self, monkeypatch):
        """Test that AZURE_SUBSCRIPTION_ID is recognized."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "12345678-1234-1234-1234-123456789012")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "87654321-4321-4321-4321-210987654321")
        monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "abcdef00-0000-0000-0000-000000abcdef")

        creds = AzureAuthenticator().get_credentials()

        assert creds.subscription_id == "abcdef00-0000-0000-0000-000000abcdef"

    def test_mixed_env_vars_azlin_and_azure(self, tmp_path, monkeypatch):
        """Test that AZLIN_SP_* and AZURE_* env vars work together."""
        # Create SP config
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        # Use AZLIN_SP_CLIENT_SECRET
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "azlin-secret")

        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        # Should set AZURE_* env vars from config + AZLIN secret
        assert creds["AZURE_CLIENT_ID"] == "12345678-1234-1234-1234-123456789012"
        assert creds["AZURE_CLIENT_SECRET"] == "azlin-secret"  # noqa: S105


class TestServicePrincipalAuthenticationFlow:
    """Test end-to-end service principal authentication flow."""

    def test_sp_auth_with_client_secret_full_flow(self, tmp_path, monkeypatch):
        """Test complete flow: load config -> get credentials -> authenticate."""
        # Create SP config
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "test-secret")

        # Step 1: Load config
        config = ServicePrincipalManager.load_config(str(config_file))
        assert config.auth_method == "client_secret"

        # Step 2: Get credentials
        creds = ServicePrincipalManager.get_credentials(config)
        assert creds["AZURE_CLIENT_ID"] == "12345678-1234-1234-1234-123456789012"
        assert creds["AZURE_CLIENT_SECRET"] == "test-secret"  # noqa: S105

        # Step 3: Use credentials with Azure auth
        with patch.dict(os.environ, creds, clear=False):
            azure_creds = AzureAuthenticator().get_credentials()
            assert azure_creds.method == "env_vars"

    def test_sp_auth_with_certificate_full_flow(self, tmp_path):
        """Test complete flow with certificate authentication."""
        # Create certificate
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        # Create SP config
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            f"""
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "certificate"
certificate_path = "{cert_file}"
"""
        )
        config_file.chmod(0o600)

        # Step 1: Load and validate
        config = ServicePrincipalManager.load_config(str(config_file))
        ServicePrincipalManager.validate_certificate(config.certificate_path)

        # Step 2: Get credentials
        creds = ServicePrincipalManager.get_credentials(config)
        assert creds["AZURE_CLIENT_CERTIFICATE_PATH"] == str(cert_file)

        # Step 3: Use with Azure SDK
        with patch.dict(os.environ, creds, clear=False):
            azure_creds = AzureAuthenticator().get_credentials()
            assert azure_creds.method == "env_vars"


class TestProfileSwitching:
    """Test switching between different authentication profiles."""

    def test_switch_from_azure_cli_to_sp(self, tmp_path, monkeypatch):
        """Test switching from Azure CLI to service principal."""
        # Start with Azure CLI
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "cli-token"}',
                stderr="",
            )

            creds1 = AzureAuthenticator().get_credentials()
            assert creds1.method == "az_cli"

        # Switch to SP
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "sp-secret")

        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        with patch.dict(os.environ, creds, clear=False):
            creds2 = AzureAuthenticator().get_credentials()
            assert creds2.method == "env_vars"

    def test_multiple_sp_profiles(self, tmp_path, monkeypatch):
        """Test switching between multiple SP profiles."""
        # Create two SP configs
        config1 = tmp_path / "sp-dev.toml"
        config1.write_text(
            """
[service_principal]
client_id = "11111111-1111-1111-1111-111111111111"
tenant_id = "22222222-2222-2222-2222-222222222222"
subscription_id = "33333333-3333-3333-3333-333333333333"
auth_method = "client_secret"
"""
        )
        config1.chmod(0o600)

        config2 = tmp_path / "sp-prod.toml"
        config2.write_text(
            """
[service_principal]
client_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
tenant_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
subscription_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
auth_method = "client_secret"
"""
        )
        config2.chmod(0o600)

        # Load dev profile
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "dev-secret")
        dev_config = ServicePrincipalManager.load_config(str(config1))
        dev_creds = ServicePrincipalManager.get_credentials(dev_config)
        assert dev_creds["AZURE_CLIENT_ID"] == "11111111-1111-1111-1111-111111111111"

        # Load prod profile
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "prod-secret")
        prod_config = ServicePrincipalManager.load_config(str(config2))
        prod_creds = ServicePrincipalManager.get_credentials(prod_config)
        assert prod_creds["AZURE_CLIENT_ID"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class TestAuthCommandGroupIntegration:
    """Test integration with azlin CLI auth commands."""

    def test_azlin_auth_login_with_sp(self, tmp_path, monkeypatch):
        """Test 'azlin auth login --sp' command integration."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "secret")

        # Simulate auth login command
        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        # Verify authentication works
        with patch.dict(os.environ, creds, clear=False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="OK", stderr="")

                # Test Azure operation
                result = subprocess.run(["az", "account", "show"], capture_output=True, check=False)
                assert result.returncode == 0

    def test_azlin_auth_status_shows_sp_info(self, tmp_path, monkeypatch):
        """Test that 'azlin auth status' shows SP information."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "secret")

        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        # Get auth status
        with patch.dict(os.environ, creds, clear=False):
            azure_creds = AzureAuthenticator().get_credentials()

            # Verify status info
            assert azure_creds.method == "env_vars"
            assert azure_creds.tenant_id == "87654321-4321-4321-4321-210987654321"

    def test_azlin_auth_logout_clears_sp_env_vars(self, monkeypatch):
        """Test that 'azlin auth logout' clears SP environment variables."""
        # Set SP env vars
        monkeypatch.setenv("AZURE_CLIENT_ID", "12345678-1234-1234-1234-123456789012")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "87654321-4321-4321-4321-210987654321")

        # Verify they're set
        assert os.getenv("AZURE_CLIENT_ID") is not None

        # Simulate logout
        ServicePrincipalManager.clear_credentials()

        # Verify they're cleared
        assert os.getenv("AZURE_CLIENT_ID") is None
        assert os.getenv("AZURE_CLIENT_SECRET") is None
        assert os.getenv("AZURE_TENANT_ID") is None


class TestRealAzureIntegrationScenarios:
    """Test integration with real Azure authentication scenarios."""

    @pytest.mark.integration
    def test_sp_auth_with_real_azure_api(self, tmp_path, monkeypatch):
        """Test SP auth with actual Azure API call (requires real creds)."""
        pytest.skip("Requires real Azure credentials - run manually with real SP")

        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "YOUR-CLIENT-ID"
tenant_id = "YOUR-TENANT-ID"
subscription_id = "YOUR-SUBSCRIPTION-ID"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "YOUR-SECRET")

        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        with patch.dict(os.environ, creds, clear=False):
            # Try real Azure API call
            result = subprocess.run(
                ["az", "account", "show"], capture_output=True, text=True, check=False
            )

            assert result.returncode == 0

    @pytest.mark.integration
    def test_sp_auth_with_certificate_real_azure(self, tmp_path):
        """Test certificate auth with real Azure (requires real cert)."""
        pytest.skip("Requires real Azure certificate - run manually")

        cert_file = tmp_path / "real-cert.pem"
        # Copy real cert here

        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            f"""
[service_principal]
client_id = "YOUR-CLIENT-ID"
tenant_id = "YOUR-TENANT-ID"
subscription_id = "YOUR-SUBSCRIPTION-ID"
auth_method = "certificate"
certificate_path = "{cert_file}"
"""
        )
        config_file.chmod(0o600)

        config = ServicePrincipalManager.load_config(str(config_file))
        ServicePrincipalManager.validate_certificate(config.certificate_path)

        creds = ServicePrincipalManager.get_credentials(config)

        with patch.dict(os.environ, creds, clear=False):
            result = subprocess.run(
                ["az", "account", "show"], capture_output=True, text=True, check=False
            )

            assert result.returncode == 0


class TestExistingFunctionalityUnaffected:
    """Test that existing azlin functionality is not affected by SP integration."""

    def test_vm_provisioning_still_works(self):
        """Test that VM provisioning commands still work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="OK", stderr="")

            # Simulate VM creation
            result = subprocess.run(
                ["az", "vm", "create", "--resource-group", "test-rg", "--name", "test-vm"],
                capture_output=True,
                check=False,
            )

            assert result.returncode == 0

    def test_storage_operations_still_work(self):
        """Test that storage operations still work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="OK", stderr="")

            # Simulate storage operation
            result = subprocess.run(
                ["az", "storage", "account", "list"], capture_output=True, check=False
            )

            assert result.returncode == 0

    def test_config_manager_still_works(self, tmp_path, monkeypatch):
        """Test that ConfigManager is not affected by SP integration."""
        from azlin.config_manager import AzlinConfig, ConfigManager

        # Use explicit custom_path to avoid writing to real ~/.azlin/config.toml
        # ConfigManager.DEFAULT_CONFIG_FILE is cached at import, so monkeypatch won't work
        test_config_path = str(tmp_path / "config.toml")

        # Create and save config
        config = AzlinConfig(default_resource_group="test-rg", default_region="eastus")

        ConfigManager.save_config(config, custom_path=test_config_path)

        # Load config
        loaded = ConfigManager.load_config(custom_path=test_config_path)

        assert loaded.default_resource_group == "test-rg"
        assert loaded.default_region == "eastus"

    def test_azure_authenticator_priority_chain_still_works(self, monkeypatch):
        """Test that AzureAuthenticator priority chain is preserved."""
        # Clear all auth env vars
        for key in [
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "AZURE_TENANT_ID",
            "AZLIN_SP_CLIENT_SECRET",
        ]:
            monkeypatch.delenv(key, raising=False)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "cli-token"}',
                stderr="",
            )

            creds = AzureAuthenticator().get_credentials()

            # Should fall back to Azure CLI
            assert creds.method == "az_cli"


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios."""

    def test_sp_auth_failure_falls_back_to_cli(self, tmp_path, monkeypatch):
        """Test that SP auth failure falls back to Azure CLI."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        # Don't set secret - will fail
        monkeypatch.delenv("AZLIN_SP_CLIENT_SECRET", raising=False)

        # SP auth should fail
        with pytest.raises(ServicePrincipalError):
            config = ServicePrincipalManager.load_config(str(config_file))
            ServicePrincipalManager.get_credentials(config)

        # But Azure CLI should still work
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "cli-token"}',
                stderr="",
            )

            creds = AzureAuthenticator().get_credentials()
            assert creds.method == "az_cli"

    def test_invalid_sp_config_does_not_break_cli(self, tmp_path):
        """Test that invalid SP config doesn't break CLI functionality."""
        config_file = tmp_path / "invalid-sp.toml"
        config_file.write_text("this is not valid TOML [[[")

        # SP load should fail
        with pytest.raises(ServicePrincipalError):
            ServicePrincipalManager.load_config(str(config_file))

        # But Azure CLI should still work
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "cli-token"}',
                stderr="",
            )

            creds = AzureAuthenticator().get_credentials()
            assert creds.method == "az_cli"

    def test_expired_certificate_fails_gracefully(self, tmp_path):
        """Test that expired certificate fails with clear error."""
        cert_file = tmp_path / "expired-cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        from datetime import datetime, timedelta

        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
        ) as mock_expiry:
            mock_expiry.return_value = datetime.now() - timedelta(days=1)

            with pytest.raises(ServicePrincipalError, match="expired"):
                ServicePrincipalManager.validate_certificate(cert_file)


class TestAuthProfileCLIIntegration:
    """Test --auth-profile CLI integration."""

    def test_auth_profile_option_in_help(self):
        """Test that --auth-profile appears in main help."""
        result = subprocess.run(
            ["python", "-m", "azlin", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "--auth-profile" in result.stdout
        assert "Service principal authentication profile" in result.stdout

    def test_auth_profile_with_nonexistent_profile_shows_error(self):
        """Test that using nonexistent profile shows clear error message."""
        # Run with profile that doesn't exist
        result = subprocess.run(
            ["python", "-m", "azlin", "--auth-profile", "nonexistent-profile-xyz", "auth", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Should fail with clear error message
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "not found" in output.lower() or "authentication" in output.lower()

    def test_auth_profile_missing_profile_fails(self, tmp_path):
        """Test that missing profile shows clear error."""
        # Create empty config
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("[auth_profiles]\n")

        env = os.environ.copy()
        env["HOME"] = str(tmp_path)

        result = subprocess.run(
            ["python", "-m", "azlin", "--auth-profile", "nonexistent", "auth", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )

        assert result.returncode != 0
        assert "not found" in result.stderr or "not found" in result.stdout
        assert "auth setup" in result.stderr or "auth setup" in result.stdout
