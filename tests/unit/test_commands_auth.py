"""Unit tests for auth command group (Brick 6).

Tests cover all auth commands:
- azlin auth setup
- azlin auth test
- azlin auth list
- azlin auth delete
- azlin auth show

Target coverage: >90%
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from azlin.auth_resolver import AuthResolverError, AzureCredentials
from azlin.commands.auth import auth_group
from azlin.config_auth import AuthConfig
from azlin.profile_manager import ProfileError, ProfileInfo


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_profile_manager():
    """Mock ProfileManager for testing."""
    with patch("azlin.commands.auth.ProfileManager") as mock:
        yield mock.return_value


@pytest.fixture
def mock_auth_resolver():
    """Mock AuthResolver for testing."""
    with patch("azlin.commands.auth.AuthResolver") as mock:
        yield mock


@pytest.fixture
def sample_profile_info():
    """Sample ProfileInfo for testing."""
    return ProfileInfo(
        name="test-profile",
        auth_method="service_principal_cert",
        tenant_id="12345678-1234-1234-1234-123456789abc",
        client_id="87654321-4321-4321-4321-cba987654321",
        subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        last_used=None,
    )


@pytest.fixture
def sample_auth_config():
    """Sample AuthConfig for testing."""
    return AuthConfig(
        auth_method="service_principal_cert",
        tenant_id="12345678-1234-1234-1234-123456789abc",
        client_id="87654321-4321-4321-4321-cba987654321",
        subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
        client_certificate_path="/path/to/cert.pem",
    )


# ============================================================================
# Tests for: azlin auth setup
# ============================================================================


class TestAuthSetup:
    """Tests for 'azlin auth setup' command."""

    def test_setup_azure_cli_method(self, runner, mock_profile_manager):
        """Test setup with Azure CLI method (default)."""
        mock_profile_manager.create_profile.return_value = ProfileInfo(
            name="default",
            auth_method="az_cli",
            tenant_id=None,
            client_id=None,
            subscription_id=None,
            created_at=datetime.now(UTC),
            last_used=None,
        )

        result = runner.invoke(
            auth_group,
            ["setup"],
            input="1\ndefault\n",  # 1=Azure CLI, profile name=default
        )

        assert result.exit_code == 0
        assert "Profile 'default' created" in result.output
        mock_profile_manager.create_profile.assert_called_once()

    def test_setup_service_principal_secret(self, runner, mock_profile_manager):
        """Test setup with service principal + client secret."""
        mock_profile_manager.create_profile.return_value = ProfileInfo(
            name="production",
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
            created_at=datetime.now(UTC),
            last_used=None,
        )

        result = runner.invoke(
            auth_group,
            ["setup"],
            input=(
                "2\n"  # 2=Service principal with secret
                "12345678-1234-1234-1234-123456789abc\n"  # tenant_id
                "87654321-4321-4321-4321-cba987654321\n"  # client_id
                "abcdef01-2345-6789-abcd-ef0123456789\n"  # subscription_id
                "production\n"  # profile name
            ),
        )

        assert result.exit_code == 0
        assert "Profile 'production' created" in result.output
        assert "Set AZURE_CLIENT_SECRET environment variable" in result.output

    def test_setup_service_principal_cert(self, runner, mock_profile_manager):
        """Test setup with service principal + certificate."""
        mock_profile_manager.create_profile.return_value = ProfileInfo(
            name="cert-profile",
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
            created_at=datetime.now(UTC),
            last_used=None,
        )

        result = runner.invoke(
            auth_group,
            ["setup"],
            input=(
                "3\n"  # 3=Service principal with certificate
                "12345678-1234-1234-1234-123456789abc\n"  # tenant_id
                "87654321-4321-4321-4321-cba987654321\n"  # client_id
                "/path/to/cert.pem\n"  # certificate path
                "abcdef01-2345-6789-abcd-ef0123456789\n"  # subscription_id
                "cert-profile\n"  # profile name
            ),
        )

        assert result.exit_code == 0
        assert "Profile 'cert-profile' created" in result.output

    def test_setup_managed_identity(self, runner, mock_profile_manager):
        """Test setup with managed identity."""
        mock_profile_manager.create_profile.return_value = ProfileInfo(
            name="mi-profile",
            auth_method="managed_identity",
            tenant_id=None,
            client_id=None,
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
            created_at=datetime.now(UTC),
            last_used=None,
        )

        result = runner.invoke(
            auth_group,
            ["setup"],
            input=(
                "4\n"  # 4=Managed identity
                "\n"  # No client_id (system-assigned)
                "abcdef01-2345-6789-abcd-ef0123456789\n"  # subscription_id
                "mi-profile\n"  # profile name
            ),
        )

        assert result.exit_code == 0
        assert "Profile 'mi-profile' created" in result.output

    def test_setup_with_profile_flag(self, runner, mock_profile_manager):
        """Test setup with --profile flag (skips profile name prompt)."""
        mock_profile_manager.create_profile.return_value = ProfileInfo(
            name="custom",
            auth_method="az_cli",
            tenant_id=None,
            client_id=None,
            subscription_id=None,
            created_at=datetime.now(UTC),
            last_used=None,
        )

        result = runner.invoke(
            auth_group,
            ["setup", "--profile", "custom"],
            input="1\n",  # 1=Azure CLI
        )

        assert result.exit_code == 0
        assert "Profile 'custom' created" in result.output

    def test_setup_profile_already_exists(self, runner, mock_profile_manager):
        """Test setup fails when profile already exists."""
        mock_profile_manager.create_profile.side_effect = ProfileError(
            "Profile 'existing' already exists"
        )

        result = runner.invoke(
            auth_group,
            ["setup"],
            input="1\nexisting\n",
        )

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_setup_invalid_uuid_format(self, runner, mock_profile_manager):
        """Test setup validates UUID format."""
        mock_profile_manager.create_profile.side_effect = ProfileError("Invalid tenant_id format")

        result = runner.invoke(
            auth_group,
            ["setup"],
            input=(
                "2\n"  # Service principal with secret
                "not-a-uuid\n"  # Invalid tenant_id
                "87654321-4321-4321-4321-cba987654321\n"
                "abcdef01-2345-6789-abcd-ef0123456789\n"
                "test\n"
            ),
        )

        assert result.exit_code == 1
        assert "Invalid" in result.output or "format" in result.output

    def test_setup_invalid_method_selection(self, runner, mock_profile_manager):
        """Test setup handles invalid method selection."""
        result = runner.invoke(
            auth_group,
            ["setup"],
            input="99\n1\ndefault\n",  # 99=invalid, retry with 1
        )

        # Should still succeed after retry
        assert result.exit_code == 0 or "Invalid" in result.output


# ============================================================================
# Tests for: azlin auth test
# ============================================================================


class TestAuthTest:
    """Tests for 'azlin auth test' command."""

    def test_test_default_config_success(self, runner, mock_auth_resolver):
        """Test authentication with default config (success)."""
        mock_resolver_instance = Mock()
        mock_resolver_instance.resolve_credentials.return_value = AzureCredentials(
            method="az_cli",
            token="mock-token",
            subscription_id="sub123",
            tenant_id="tenant123",
        )
        mock_auth_resolver.return_value = mock_resolver_instance

        with patch("azlin.commands.auth.load_auth_config") as mock_load:
            mock_load.return_value = AuthConfig(auth_method="az_cli")
            result = runner.invoke(auth_group, ["test"])

        assert result.exit_code == 0
        assert "Authentication successful" in result.output
        assert "Method: az_cli" in result.output

    def test_test_with_profile_success(self, runner, mock_profile_manager, mock_auth_resolver):
        """Test authentication with specific profile (success)."""
        mock_profile_manager.get_profile.return_value = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
        )

        mock_resolver_instance = Mock()
        mock_resolver_instance.resolve_credentials.return_value = AzureCredentials(
            method="service_principal_cert",
            token="mock-token",
            subscription_id="sub123",
            tenant_id="12345678-1234-1234-1234-123456789abc",
        )
        mock_auth_resolver.return_value = mock_resolver_instance

        result = runner.invoke(auth_group, ["test", "--profile", "test-profile"])

        assert result.exit_code == 0
        assert "Authentication successful" in result.output
        assert "service_principal_cert" in result.output

    def test_test_authentication_failure(self, runner, mock_auth_resolver):
        """Test authentication failure."""
        mock_resolver_instance = Mock()
        mock_resolver_instance.resolve_credentials.side_effect = AuthResolverError(
            "Authentication failed: invalid credentials"
        )
        mock_auth_resolver.return_value = mock_resolver_instance

        with patch("azlin.commands.auth.load_auth_config") as mock_load:
            mock_load.return_value = AuthConfig(auth_method="az_cli")
            result = runner.invoke(auth_group, ["test"])

        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    def test_test_profile_not_found(self, runner, mock_profile_manager):
        """Test with non-existent profile."""
        mock_profile_manager.get_profile.side_effect = ProfileError(
            "Profile 'nonexistent' not found"
        )

        result = runner.invoke(auth_group, ["test", "--profile", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_test_displays_tenant_and_subscription(self, runner, mock_auth_resolver):
        """Test displays tenant and subscription info."""
        mock_resolver_instance = Mock()
        mock_resolver_instance.resolve_credentials.return_value = AzureCredentials(
            method="az_cli",
            token="mock-token",
            subscription_id="sub-12345",
            tenant_id="tenant-67890",
        )
        mock_auth_resolver.return_value = mock_resolver_instance

        with patch("azlin.commands.auth.load_auth_config") as mock_load:
            mock_load.return_value = AuthConfig(auth_method="az_cli")
            result = runner.invoke(auth_group, ["test"])

        assert result.exit_code == 0
        assert "sub-12345" in result.output
        assert "tenant-67890" in result.output


# ============================================================================
# Tests for: azlin auth list
# ============================================================================


class TestAuthList:
    """Tests for 'azlin auth list' command."""

    def test_list_multiple_profiles(self, runner, mock_profile_manager):
        """Test listing multiple profiles."""
        mock_profile_manager.list_profiles.return_value = [
            ProfileInfo(
                name="profile1",
                auth_method="az_cli",
                tenant_id=None,
                client_id=None,
                subscription_id=None,
                created_at=datetime(2025, 1, 1, tzinfo=UTC),
                last_used=datetime(2025, 1, 15, tzinfo=UTC),
            ),
            ProfileInfo(
                name="profile2",
                auth_method="service_principal_cert",
                tenant_id="12345678-1234-1234-1234-123456789abc",
                client_id="87654321-4321-4321-4321-cba987654321",
                subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
                created_at=datetime(2025, 1, 10, tzinfo=UTC),
                last_used=None,
            ),
        ]

        result = runner.invoke(auth_group, ["list"])

        assert result.exit_code == 0
        assert "profile1" in result.output
        assert "profile2" in result.output
        assert "az_cli" in result.output
        assert "service_principal_cert" in result.output

    def test_list_no_profiles(self, runner, mock_profile_manager):
        """Test listing when no profiles exist."""
        mock_profile_manager.list_profiles.return_value = []

        result = runner.invoke(auth_group, ["list"])

        assert result.exit_code == 0
        assert "No authentication profiles found" in result.output

    def test_list_shows_timestamps(self, runner, mock_profile_manager):
        """Test list shows created_at and last_used timestamps."""
        mock_profile_manager.list_profiles.return_value = [
            ProfileInfo(
                name="test",
                auth_method="az_cli",
                tenant_id=None,
                client_id=None,
                subscription_id=None,
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                last_used=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            ),
        ]

        result = runner.invoke(auth_group, ["list"])

        assert result.exit_code == 0
        assert "2025-01-01" in result.output
        assert "2025-01-15" in result.output

    def test_list_shows_never_used(self, runner, mock_profile_manager):
        """Test list shows 'Never' for profiles never used."""
        mock_profile_manager.list_profiles.return_value = [
            ProfileInfo(
                name="test",
                auth_method="az_cli",
                tenant_id=None,
                client_id=None,
                subscription_id=None,
                created_at=datetime(2025, 1, 1, tzinfo=UTC),
                last_used=None,
            ),
        ]

        result = runner.invoke(auth_group, ["list"])

        assert result.exit_code == 0
        assert "Never" in result.output


# ============================================================================
# Tests for: azlin auth delete
# ============================================================================


class TestAuthDelete:
    """Tests for 'azlin auth delete' command."""

    def test_delete_with_confirmation(self, runner, mock_profile_manager):
        """Test delete with user confirmation."""
        mock_profile_manager.delete_profile.return_value = True

        result = runner.invoke(
            auth_group,
            ["delete", "test-profile"],
            input="y\n",  # Confirm deletion
        )

        assert result.exit_code == 0
        assert "deleted successfully" in result.output
        mock_profile_manager.delete_profile.assert_called_once_with("test-profile")

    def test_delete_cancelled(self, runner, mock_profile_manager):
        """Test delete cancelled by user."""
        result = runner.invoke(
            auth_group,
            ["delete", "test-profile"],
            input="n\n",  # Cancel deletion
        )

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        mock_profile_manager.delete_profile.assert_not_called()

    def test_delete_with_force_flag(self, runner, mock_profile_manager):
        """Test delete with --force flag (skips confirmation)."""
        mock_profile_manager.delete_profile.return_value = True

        result = runner.invoke(auth_group, ["delete", "test-profile", "--force"])

        assert result.exit_code == 0
        assert "deleted successfully" in result.output
        mock_profile_manager.delete_profile.assert_called_once()

    def test_delete_profile_not_found(self, runner, mock_profile_manager):
        """Test delete when profile doesn't exist."""
        mock_profile_manager.delete_profile.return_value = False

        result = runner.invoke(auth_group, ["delete", "nonexistent", "--force"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_delete_invalid_profile_name(self, runner, mock_profile_manager):
        """Test delete with invalid profile name."""
        mock_profile_manager.delete_profile.side_effect = ProfileError("Invalid profile name")

        result = runner.invoke(auth_group, ["delete", "../invalid", "--force"])

        assert result.exit_code == 1
        assert "Invalid" in result.output or "Error" in result.output


# ============================================================================
# Tests for: azlin auth show
# ============================================================================


class TestAuthShow:
    """Tests for 'azlin auth show' command."""

    def test_show_profile_details(self, runner, mock_profile_manager):
        """Test show displays profile details."""
        mock_profile_manager.get_profile.return_value = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
            client_certificate_path="/path/to/cert.pem",
        )

        result = runner.invoke(auth_group, ["show", "--profile", "test-profile"])

        assert result.exit_code == 0
        assert "test-profile" in result.output
        assert "service_principal_cert" in result.output
        assert "12345678-1234-1234-1234-123456789abc" in result.output
        assert "87654321-4321-4321-4321-cba987654321" in result.output
        assert "/path/to/cert.pem" in result.output

    def test_show_redacts_secrets(self, runner, mock_profile_manager):
        """Test show redacts any secrets (defense in depth)."""
        # Even though profiles shouldn't have secrets, test redaction
        mock_profile_manager.get_profile.return_value = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="this-should-not-appear",
        )

        result = runner.invoke(auth_group, ["show", "--profile", "test-profile"])

        assert result.exit_code == 0
        assert "this-should-not-appear" not in result.output
        # Secrets should be marked as "from environment"
        assert "environment" in result.output.lower() or "REDACTED" in result.output

    def test_show_default_profile(self, runner, mock_profile_manager):
        """Test show with no profile uses default."""
        mock_profile_manager.get_profile.return_value = AuthConfig(
            auth_method="az_cli",
        )

        result = runner.invoke(auth_group, ["show"])

        assert result.exit_code == 0
        assert "az_cli" in result.output

    def test_show_profile_not_found(self, runner, mock_profile_manager):
        """Test show when profile doesn't exist."""
        mock_profile_manager.get_profile.side_effect = ProfileError(
            "Profile 'nonexistent' not found"
        )

        result = runner.invoke(auth_group, ["show", "--profile", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_show_displays_all_fields(self, runner, mock_profile_manager):
        """Test show displays all configuration fields."""
        mock_profile_manager.get_profile.return_value = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
            client_certificate_path="/path/to/cert.pem",
        )

        result = runner.invoke(auth_group, ["show", "--profile", "test"])

        assert result.exit_code == 0
        # Check all fields are displayed
        assert "Method" in result.output or "method" in result.output
        assert "Tenant" in result.output or "tenant" in result.output
        assert "Client" in result.output or "client" in result.output
        assert "Subscription" in result.output or "subscription" in result.output


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestAuthGroupIntegration:
    """Integration tests for auth command group."""

    def test_auth_group_has_all_commands(self):
        """Test auth group includes all expected commands."""
        command_names = list(auth_group.commands.keys())

        assert "setup" in command_names
        assert "test" in command_names
        assert "list" in command_names
        assert "delete" in command_names
        assert "show" in command_names

    def test_auth_group_name(self):
        """Test auth group has correct name."""
        assert auth_group.name == "auth"

    def test_commands_have_help_text(self):
        """Test all commands have help text."""
        for cmd_name, cmd in auth_group.commands.items():
            assert cmd.help is not None
            assert len(cmd.help) > 0

    def test_setup_command_options(self):
        """Test setup command has expected options."""
        setup_cmd = auth_group.commands["setup"]
        param_names = [p.name for p in setup_cmd.params]

        assert "profile" in param_names

    def test_test_command_options(self):
        """Test test command has expected options."""
        test_cmd = auth_group.commands["test"]
        param_names = [p.name for p in test_cmd.params]

        assert "profile" in param_names

    def test_show_command_options(self):
        """Test show command has expected options."""
        show_cmd = auth_group.commands["show"]
        param_names = [p.name for p in show_cmd.params]

        assert "profile" in param_names

    def test_delete_command_arguments(self):
        """Test delete command has profile_name argument."""
        delete_cmd = auth_group.commands["delete"]
        param_names = [p.name for p in delete_cmd.params]

        assert "profile_name" in param_names
        assert "force" in param_names


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in auth commands."""

    def test_setup_handles_unexpected_error(self, runner, mock_profile_manager):
        """Test setup handles unexpected errors gracefully."""
        mock_profile_manager.create_profile.side_effect = Exception("Unexpected error")

        result = runner.invoke(
            auth_group,
            ["setup"],
            input="1\ntest\n",
        )

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_test_handles_unexpected_error(self, runner, mock_auth_resolver):
        """Test test handles unexpected errors gracefully."""
        mock_auth_resolver.side_effect = Exception("Unexpected error")

        with patch("azlin.commands.auth.load_auth_config") as mock_load:
            mock_load.return_value = AuthConfig(auth_method="az_cli")
            result = runner.invoke(auth_group, ["test"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_list_handles_unexpected_error(self, runner, mock_profile_manager):
        """Test list handles unexpected errors gracefully."""
        mock_profile_manager.list_profiles.side_effect = Exception("Unexpected error")

        result = runner.invoke(auth_group, ["list"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_delete_handles_unexpected_error(self, runner, mock_profile_manager):
        """Test delete handles unexpected errors gracefully."""
        mock_profile_manager.delete_profile.side_effect = Exception("Unexpected error")

        result = runner.invoke(auth_group, ["delete", "test", "--force"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_show_handles_unexpected_error(self, runner, mock_profile_manager):
        """Test show handles unexpected errors gracefully."""
        mock_profile_manager.get_profile.side_effect = Exception("Unexpected error")

        result = runner.invoke(auth_group, ["show", "--profile", "test"])

        assert result.exit_code == 1
        assert "Error" in result.output
