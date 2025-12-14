"""Integration test for credential rotation workflow."""

from pathlib import Path

import pytest

from azlin.service_principal_auth import ServicePrincipalManager


class TestCredentialRotationWorkflow:
    """Test credential rotation for service principals."""

    def test_credential_rotation_workflow(self, tmp_path):
        """Test rotating service principal credentials."""
        config_file = tmp_path / "sp_config.json"
        manager = ServicePrincipalManager(config_path=config_file)

        # Create profile with initial secret
        manager.add_profile(
            profile_name="test-sp",
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            client_secret="old-secret",  # noqa: S106
        )

        # Rotate credential
        manager.update_profile_secret(
            profile_name="test-sp",
            new_secret="new-secret",  # noqa: S106
        )

        # Verify new secret
        profile = manager.get_profile("test-sp")
        assert profile["client_secret"] == "new-secret"  # noqa: S105
