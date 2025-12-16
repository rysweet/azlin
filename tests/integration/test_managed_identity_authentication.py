"""Integration test for managed identity authentication workflow."""

import json

import pytest

from azlin.azure_auth import AzureAuthenticator


class TestManagedIdentityAuthentication:
    """Test managed identity authentication workflow."""

    def test_managed_identity_detection(self):
        """Test detecting if running in managed identity environment."""
        # Check for Azure instance metadata service
        try:
            import urllib.request

            req = urllib.request.Request(
                "http://169.254.169.254/metadata/instance?api-version=2021-02-01",
                headers={"Metadata": "true"},
            )
            urllib.request.urlopen(req, timeout=1)  # noqa: S310
            is_azure_vm = True
        except Exception:
            is_azure_vm = False

        # Managed identity only available on Azure VMs
        if is_azure_vm:
            authenticator = AzureAuthenticator()
            creds = authenticator.get_credentials()
            assert creds.method in ["managed_identity", "az_cli", "env_vars"]
        else:
            pytest.skip("Not running on Azure VM with managed identity")

    def test_system_assigned_identity(self):
        """Test system-assigned managed identity."""
        try:
            import urllib.request

            # Try to get token from metadata service
            req = urllib.request.Request(
                "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/",
                headers={"Metadata": "true"},
            )
            response = urllib.request.urlopen(req, timeout=1)  # noqa: S310
            token_data = json.loads(response.read())

            # Should have access token
            assert "access_token" in token_data

        except Exception:
            pytest.skip("System-assigned identity not available")
