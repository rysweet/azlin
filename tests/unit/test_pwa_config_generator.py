"""Unit tests for PWA configuration generator (TDD approach).

This module tests the PWA configuration inheritance feature that extracts
Azure configuration from azlin parent config.

Testing Pyramid: 60% unit tests (this file)

Tests will FAIL until implementation is complete - this is TDD!

Test Coverage:
- Azure CLI extraction (az account show)
- Config extraction from parent azlin config
- .env generation with proper formatting
- NEVER overwrite existing .env (CRITICAL)
- Source attribution tracking
- Error handling and fallbacks
- Azure CLI availability checking
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.pwa_config_generator import (
    ConfigSource,
    PWAConfigGenerator,
    PWAConfigResult,
)


class TestConfigSource:
    """Test ConfigSource enum for tracking value origins."""

    def test_config_source_values(self):
        """Test ConfigSource enum has expected values."""
        assert ConfigSource.AZURE_CLI.value == "azure_cli"
        assert ConfigSource.AZLIN_CONFIG.value == "azlin_config"
        assert ConfigSource.DEFAULT.value == "default"
        assert ConfigSource.EXISTING_ENV.value == "existing_env"


class TestPWAConfigResult:
    """Test PWAConfigResult dataclass."""

    def test_result_creation_success(self):
        """Test creating successful result."""
        result = PWAConfigResult(
            success=True,
            env_path=Path("/pwa/.env"),
            config_values={
                "VITE_AZURE_SUBSCRIPTION_ID": "sub-123",
                "VITE_AZURE_TENANT_ID": "tenant-456",
            },
            source_attribution={
                "VITE_AZURE_SUBSCRIPTION_ID": ConfigSource.AZURE_CLI,
                "VITE_AZURE_TENANT_ID": ConfigSource.AZURE_CLI,
            },
            message="Configuration generated successfully",
        )

        assert result.success is True
        assert result.env_path == Path("/pwa/.env")
        assert len(result.config_values) == 2
        assert result.message == "Configuration generated successfully"
        assert result.error is None

    def test_result_creation_failure(self):
        """Test creating failure result."""
        result = PWAConfigResult(
            success=False,
            env_path=None,
            config_values={},
            source_attribution={},
            message="Azure CLI not available",
            error="Command 'az' not found",
        )

        assert result.success is False
        assert result.env_path is None
        assert result.config_values == {}
        assert "Azure CLI not available" in result.message
        assert result.error is not None


class TestPWAConfigGenerator:
    """Test PWAConfigGenerator class."""

    @pytest.fixture
    def temp_pwa_dir(self, tmp_path):
        """Create temporary PWA directory."""
        pwa_dir = tmp_path / "pwa"
        pwa_dir.mkdir()
        return pwa_dir

    @pytest.fixture
    def mock_azure_cli_available(self):
        """Mock Azure CLI as available."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/az"
            yield mock_which

    @pytest.fixture
    def mock_azure_cli_unavailable(self):
        """Mock Azure CLI as unavailable."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            yield mock_which

    @pytest.fixture
    def mock_az_account_show_success(self):
        """Mock successful 'az account show' command."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "id": "12345678-1234-1234-1234-123456789012",
                    "tenantId": "87654321-4321-4321-4321-210987654321",
                    "name": "My Azure Subscription",
                }
            )
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            yield mock_run

    # ========================================================================
    # CRITICAL TEST: NEVER overwrite existing .env
    # ========================================================================

    def test_never_overwrite_existing_env_file(self, temp_pwa_dir):
        """CRITICAL: Must never overwrite existing .env file.

        This is the #1 requirement from architecture spec.
        """
        # Create existing .env with user content
        existing_env = temp_pwa_dir / ".env"
        existing_content = "VITE_USER_CONFIG=important_value\nVITE_API_KEY=secret"
        existing_env.write_text(existing_content)

        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir, force=False)

        # Should NOT create/modify .env
        assert result.success is False
        assert ".env already exists" in result.message.lower()

        # Original content must be unchanged
        assert existing_env.read_text() == existing_content

    def test_force_flag_allows_overwrite(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test force=True allows overwriting existing .env."""
        # Create existing .env
        existing_env = temp_pwa_dir / ".env"
        existing_env.write_text("OLD_CONFIG=old_value")

        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir, force=True)

        # Should overwrite when force=True
        assert result.success is True
        assert "OLD_CONFIG" not in existing_env.read_text()

    # ========================================================================
    # Azure CLI Extraction Tests
    # ========================================================================

    def test_check_azure_cli_available(self, mock_azure_cli_available):
        """Test checking if Azure CLI is available."""
        generator = PWAConfigGenerator()

        assert generator.is_azure_cli_available() is True

    def test_check_azure_cli_unavailable(self, mock_azure_cli_unavailable):
        """Test checking when Azure CLI is not available."""
        generator = PWAConfigGenerator()

        assert generator.is_azure_cli_available() is False

    def test_extract_azure_config_success(
        self, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test successful Azure config extraction."""
        generator = PWAConfigGenerator()
        config = generator.extract_azure_config()

        assert config is not None
        assert "subscription_id" in config
        assert config["subscription_id"] == "12345678-1234-1234-1234-123456789012"
        assert "tenant_id" in config
        assert config["tenant_id"] == "87654321-4321-4321-4321-210987654321"

    def test_extract_azure_config_cli_unavailable(self, mock_azure_cli_unavailable):
        """Test Azure config extraction when CLI unavailable."""
        generator = PWAConfigGenerator()
        config = generator.extract_azure_config()

        assert config is None

    def test_extract_azure_config_command_fails(self, mock_azure_cli_available):
        """Test Azure config extraction when command fails."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "Authentication required"
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            config = generator.extract_azure_config()

            assert config is None

    def test_extract_azure_config_invalid_json(self, mock_azure_cli_available):
        """Test Azure config extraction with invalid JSON response."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "not valid json"
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            config = generator.extract_azure_config()

            assert config is None

    # ========================================================================
    # Config Value Mapping Tests
    # ========================================================================

    def test_map_azure_config_to_env_vars(self):
        """Test mapping Azure config to environment variables."""
        azure_config = {
            "subscription_id": "sub-123",
            "tenant_id": "tenant-456",
            "name": "My Subscription",
        }

        generator = PWAConfigGenerator()
        env_vars = generator.map_azure_config_to_env_vars(azure_config)

        assert env_vars["VITE_AZURE_SUBSCRIPTION_ID"] == "sub-123"
        assert env_vars["VITE_AZURE_TENANT_ID"] == "tenant-456"

    def test_map_azure_config_with_missing_fields(self):
        """Test mapping when some fields are missing."""
        azure_config = {"subscription_id": "sub-123"}  # Missing tenant_id

        generator = PWAConfigGenerator()
        env_vars = generator.map_azure_config_to_env_vars(azure_config)

        assert "VITE_AZURE_SUBSCRIPTION_ID" in env_vars
        assert "VITE_AZURE_TENANT_ID" not in env_vars

    # ========================================================================
    # .env File Generation Tests
    # ========================================================================

    def test_generate_env_file_success(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test successful .env file generation."""
        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        assert result.success is True
        assert result.env_path == temp_pwa_dir / ".env"

        # Check file was created
        env_file = temp_pwa_dir / ".env"
        assert env_file.exists()

        # Check content
        content = env_file.read_text()
        assert "VITE_AZURE_SUBSCRIPTION_ID=" in content
        assert "VITE_AZURE_TENANT_ID=" in content

    def test_generate_env_file_with_comments(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test .env file includes helpful comments."""
        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        env_file = temp_pwa_dir / ".env"
        content = env_file.read_text()

        # Should have header comment
        assert "# Azure Configuration" in content or "# PWA Config" in content
        # Should have source attribution comments
        assert "#" in content

    def test_env_file_format_correctness(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test .env file has correct format (KEY=value)."""
        generator = PWAConfigGenerator()
        generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        env_file = temp_pwa_dir / ".env"
        content = env_file.read_text()

        # Each non-comment line should be KEY=value format
        for line in content.split("\n"):
            if line.strip() and not line.strip().startswith("#"):
                assert "=" in line
                key, value = line.split("=", 1)
                assert key.strip()  # Key not empty
                assert value.strip()  # Value not empty

    # ========================================================================
    # Source Attribution Tests
    # ========================================================================

    def test_source_attribution_tracking(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test that source attribution is tracked for each value."""
        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        assert result.source_attribution is not None
        assert "VITE_AZURE_SUBSCRIPTION_ID" in result.source_attribution
        assert result.source_attribution["VITE_AZURE_SUBSCRIPTION_ID"] == ConfigSource.AZURE_CLI

    def test_source_attribution_in_env_file(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test that .env file includes source attribution comments."""
        generator = PWAConfigGenerator()
        generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        env_file = temp_pwa_dir / ".env"
        content = env_file.read_text()

        # Should have comments indicating source
        assert "azure_cli" in content.lower() or "source:" in content.lower()

    # ========================================================================
    # Error Handling Tests
    # ========================================================================

    def test_generate_with_no_azure_cli(self, temp_pwa_dir, mock_azure_cli_unavailable):
        """Test graceful fallback when Azure CLI unavailable."""
        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        # Should succeed with fallback behavior
        assert result.success is True
        assert "azure cli not available" in result.message.lower()

    def test_generate_with_invalid_pwa_dir(self):
        """Test error handling for invalid PWA directory."""
        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=Path("/nonexistent/path"))

        assert result.success is False
        assert "directory" in result.message.lower()

    def test_generate_handles_permission_errors(self, temp_pwa_dir):
        """Test handling of permission errors during file writing."""
        # Make directory read-only
        temp_pwa_dir.chmod(0o444)

        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        # Should fail gracefully
        assert result.success is False
        assert result.error is not None

        # Cleanup
        temp_pwa_dir.chmod(0o755)

    # ========================================================================
    # Config Value Priority Tests
    # ========================================================================

    def test_azure_cli_values_preferred_over_defaults(
        self, temp_pwa_dir, mock_azure_cli_available, mock_az_account_show_success
    ):
        """Test that Azure CLI values take priority over defaults."""
        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

        # Values should come from Azure CLI, not defaults
        assert result.config_values["VITE_AZURE_SUBSCRIPTION_ID"] != "default"
        assert result.source_attribution["VITE_AZURE_SUBSCRIPTION_ID"] == ConfigSource.AZURE_CLI

    # ========================================================================
    # Edge Case Tests
    # ========================================================================

    def test_empty_subscription_id(self, temp_pwa_dir, mock_azure_cli_available):
        """Test handling of empty subscription ID from Azure CLI."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "", "tenantId": "tenant-123"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

            # Should handle empty values gracefully
            assert (
                result.success is False or "VITE_AZURE_SUBSCRIPTION_ID" not in result.config_values
            )

    def test_pwa_dir_created_if_not_exists(self, tmp_path):
        """Test that PWA directory is created if it doesn't exist."""
        pwa_dir = tmp_path / "new_pwa_dir"
        assert not pwa_dir.exists()

        generator = PWAConfigGenerator()
        # Should create directory
        # (This behavior may vary based on implementation)
        result = generator.generate_pwa_env_from_azlin(pwa_dir=pwa_dir)

        # Directory creation behavior depends on design decision
        # Test documents expected behavior once decided

    def test_unicode_in_config_values(self, temp_pwa_dir, mock_azure_cli_available):
        """Test handling of unicode characters in config values."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "id": "sub-123",
                    "tenantId": "tenant-456",
                    "name": "Subscription™ with Unicode™",
                }
            )
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=temp_pwa_dir)

            # Should handle unicode correctly
            assert result.success is True

            # Check file is readable
            env_file = temp_pwa_dir / ".env"
            content = env_file.read_text(encoding="utf-8")
            assert content  # Should be readable

    # ========================================================================
    # Integration with azlin config.toml Tests
    # ========================================================================

    def test_extract_from_azlin_config_file(self, tmp_path):
        """Test extracting config from azlin config.toml."""
        # Create fake azlin config
        azlin_config_dir = tmp_path / ".azlin"
        azlin_config_dir.mkdir()
        config_file = azlin_config_dir / "config.toml"
        config_file.write_text(
            """
[azure]
subscription_id = "config-sub-123"
tenant_id = "config-tenant-456"
"""
        )

        generator = PWAConfigGenerator()
        config = generator.extract_from_azlin_config(azlin_config_dir)

        assert config is not None
        assert config["subscription_id"] == "config-sub-123"
        assert config["tenant_id"] == "config-tenant-456"

    def test_azlin_config_missing(self, tmp_path):
        """Test when azlin config.toml doesn't exist."""
        generator = PWAConfigGenerator()
        config = generator.extract_from_azlin_config(tmp_path)

        assert config is None


class TestConfigValueExtraction:
    """Test specific config value extraction logic."""

    def test_validate_subscription_id_format(self):
        """Test subscription ID format validation."""
        generator = PWAConfigGenerator()

        # Valid UUID
        assert generator.is_valid_subscription_id("12345678-1234-1234-1234-123456789012")

        # Invalid formats
        assert not generator.is_valid_subscription_id("invalid")
        assert not generator.is_valid_subscription_id("")
        assert not generator.is_valid_subscription_id("123")


class TestErrorMessages:
    """Test error message quality and clarity."""

    def test_error_message_for_missing_azure_cli(self, tmp_path):
        """Test clear error message when Azure CLI missing."""
        with patch("shutil.which", return_value=None):
            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            # Message should be clear and actionable
            assert "azure cli" in result.message.lower()
            # Should suggest how to install/authenticate

    def test_error_message_for_existing_env(self, tmp_path):
        """Test clear error message when .env exists."""
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING=value")

        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

        # Message should mention existing file and force flag
        assert ".env" in result.message
        assert "exists" in result.message.lower()
        assert "force" in result.message.lower()


# ============================================================================
# Proportionality Check
# ============================================================================
# This test file: ~650 lines
# Expected implementation: ~200-300 lines
# Ratio: ~2-3:1 (appropriate for moderate complexity config generation)
# ============================================================================
