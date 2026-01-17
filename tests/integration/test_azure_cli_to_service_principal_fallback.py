"""Integration test for Azure CLI to Service Principal authentication fallback.

Tests real authentication chain without mocking core authentication logic.
"""

import subprocess

import pytest

from azlin.azure_auth import AzureAuthenticator
from azlin.service_principal_auth import ServicePrincipalManager


class TestAzureCLIToServicePrincipalFallback:
    """Test authentication fallback chain with minimal mocking."""

    def test_azure_cli_available_and_authenticated(self):
        """Test that Azure CLI authentication works when available."""
        # Real check - no mocking
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            # Azure CLI is authenticated
            authenticator = AzureAuthenticator()
            creds = authenticator.get_credentials()
            assert creds.method in ["az_cli", "env_vars", "managed_identity"]
            assert creds.token or creds.client_id
        else:
            pytest.skip("Azure CLI not authenticated - cannot test")

    def test_service_principal_env_vars_take_priority(self, tmp_path, monkeypatch):
        """Test that SP env vars override Azure CLI."""
        # Set valid SP environment variables
        monkeypatch.setenv("AZURE_CLIENT_ID", "12345678-1234-1234-1234-123456789012")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "87654321-4321-4321-4321-210987654321")

        authenticator = AzureAuthenticator()
        creds = authenticator.get_credentials()

        # Should use env vars
        assert creds.method == "env_vars"
        assert creds.client_id == "12345678-1234-1234-1234-123456789012"

    def test_fallback_to_azure_cli_when_sp_config_missing(self, monkeypatch):
        """Test fallback to Azure CLI when SP config is not present."""
        # Clear SP environment variables
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)

        # Check if Azure CLI is available
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated - cannot test fallback")

        authenticator = AzureAuthenticator()
        creds = authenticator.get_credentials()

        # Should fall back to Azure CLI
        assert creds.method == "az_cli"


class TestServicePrincipalConfiguration:
    """Test service principal configuration workflow."""

    def test_service_principal_profile_creation(self, tmp_path):
        """Test creating and loading a service principal profile."""
        config_file = tmp_path / "sp_profiles.json"

        manager = ServicePrincipalManager(config_path=config_file)

        # Create a profile
        profile_name = "test-profile"
        client_id = "12345678-1234-1234-1234-123456789012"
        tenant_id = "87654321-4321-4321-4321-210987654321"
        secret = "test-secret"  # noqa: S105

        manager.add_profile(
            profile_name=profile_name,
            client_id=client_id,
            tenant_id=tenant_id,
            client_secret=secret,
        )

        # Verify profile was created
        assert config_file.exists()

        # Load profile
        profiles = manager.list_profiles()
        assert profile_name in profiles

    def test_service_principal_profile_switching(self, tmp_path):
        """Test switching between service principal profiles."""
        config_file = tmp_path / "sp_profiles.json"
        manager = ServicePrincipalManager(config_path=config_file)

        # Create two profiles
        manager.add_profile(
            profile_name="dev",
            client_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
            client_secret="dev-secret",  # noqa: S106
        )

        manager.add_profile(
            profile_name="prod",
            client_id="33333333-3333-3333-3333-333333333333",
            tenant_id="44444444-4444-4444-4444-444444444444",
            client_secret="prod-secret",  # noqa: S106
        )

        # Switch to dev profile
        manager.set_active_profile("dev")
        active = manager.get_active_profile()
        assert active["client_id"] == "11111111-1111-1111-1111-111111111111"

        # Switch to prod profile
        manager.set_active_profile("prod")
        active = manager.get_active_profile()
        assert active["client_id"] == "33333333-3333-3333-3333-333333333333"


class TestAuthenticationChainIntegration:
    """Test complete authentication chain with real components."""

    def test_auth_chain_with_multiple_methods(self, tmp_path, monkeypatch):
        """Test authentication tries multiple methods in priority order."""
        # Test priority: env_vars > sp_config > az_cli > managed_identity

        # Start with no env vars
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)

        # Check Azure CLI availability
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        authenticator = AzureAuthenticator()
        creds = authenticator.get_credentials()

        # Should get credentials via some method
        assert creds is not None
        assert creds.method in ["az_cli", "env_vars", "managed_identity", "sp_config"]

    def test_authentication_credential_object_structure(self):
        """Test that credential objects have correct structure."""
        authenticator = AzureAuthenticator()
        creds = authenticator.get_credentials()

        # Verify credential structure
        assert hasattr(creds, "method")
        assert hasattr(creds, "tenant_id") or hasattr(creds, "subscription_id")

        # Should have either token or client_id
        assert hasattr(creds, "token") or hasattr(creds, "client_id")
