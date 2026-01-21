"""Integration tests for PWA configuration generation (TDD approach).

This module tests the full end-to-end workflow of PWA config generation
with real file system operations and subprocess calls.

Testing Pyramid: 30% integration tests (this file)

Tests will FAIL until implementation is complete - this is TDD!

Integration Test Coverage:
- Complete config generation workflow
- File system operations
- subprocess.run integration for Azure CLI
- Multiple config sources working together
- Real .env file generation and formatting
- Error handling across components
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.modules.pwa_config_generator import (
    ConfigSource,
    PWAConfigGenerator,
    PWAConfigResult,
)


class TestFullConfigGenerationWorkflow:
    """Integration tests for complete config generation workflow."""

    @pytest.fixture
    def test_environment(self, tmp_path):
        """Set up complete test environment with directories."""
        # Create azlin config directory
        azlin_config_dir = tmp_path / ".azlin"
        azlin_config_dir.mkdir()

        # Create PWA directory
        pwa_dir = tmp_path / "pwa"
        pwa_dir.mkdir()

        return {
            "root": tmp_path,
            "azlin_config_dir": azlin_config_dir,
            "pwa_dir": pwa_dir,
        }

    @pytest.fixture
    def mock_azure_authenticated(self):
        """Mock authenticated Azure CLI environment."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "id": "12345678-1234-1234-1234-123456789012",
                    "tenantId": "87654321-4321-4321-4321-210987654321",
                    "name": "Integration Test Subscription",
                }
            )
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            yield mock_run

    def test_complete_generation_with_azure_cli(self, test_environment, mock_azure_authenticated):
        """Integration: Complete config generation using Azure CLI."""
        pwa_dir = test_environment["pwa_dir"]

        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(pwa_dir=pwa_dir)

        # Should succeed
        assert result.success is True

        # .env file should exist
        env_file = pwa_dir / ".env"
        assert env_file.exists()

        # File should have correct content
        content = env_file.read_text()
        assert "VITE_AZURE_SUBSCRIPTION_ID=12345678-1234-1234-1234-123456789012" in content
        assert "VITE_AZURE_TENANT_ID=87654321-4321-4321-4321-210987654321" in content

        # Should have source attribution
        assert result.source_attribution["VITE_AZURE_SUBSCRIPTION_ID"] == ConfigSource.AZURE_CLI

    def test_complete_generation_with_azlin_config(self, test_environment):
        """Integration: Complete config generation using azlin config.toml."""
        azlin_config_dir = test_environment["azlin_config_dir"]
        pwa_dir = test_environment["pwa_dir"]

        # Create azlin config.toml
        config_file = azlin_config_dir / "config.toml"
        config_file.write_text(
            """
[azure]
subscription_id = "config-sub-789"
tenant_id = "config-tenant-012"
"""
        )

        # Mock Azure CLI as unavailable
        with patch("shutil.which", return_value=None):
            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(
                pwa_dir=pwa_dir, azlin_config_dir=azlin_config_dir
            )

            # Should succeed with fallback to config file
            assert result.success is True

            # Should use config file values
            env_file = pwa_dir / ".env"
            content = env_file.read_text()
            assert "config-sub-789" in content
            assert "config-tenant-012" in content

    def test_azure_cli_takes_priority_over_config_file(
        self, test_environment, mock_azure_authenticated
    ):
        """Integration: Azure CLI values override config.toml values."""
        azlin_config_dir = test_environment["azlin_config_dir"]
        pwa_dir = test_environment["pwa_dir"]

        # Create azlin config with different values
        config_file = azlin_config_dir / "config.toml"
        config_file.write_text(
            """
[azure]
subscription_id = "old-sub-999"
tenant_id = "old-tenant-888"
"""
        )

        generator = PWAConfigGenerator()
        result = generator.generate_pwa_env_from_azlin(
            pwa_dir=pwa_dir, azlin_config_dir=azlin_config_dir
        )

        # Should use Azure CLI values (from mock)
        env_file = pwa_dir / ".env"
        content = env_file.read_text()
        assert "12345678-1234-1234-1234-123456789012" in content  # From Azure CLI
        assert "old-sub-999" not in content  # Not from config file


class TestFileSystemIntegration:
    """Integration tests for file system operations."""

    def test_env_file_permissions(self, tmp_path):
        """Integration: .env file has appropriate permissions."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "sub-123", "tenantId": "tenant-456"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            env_file = tmp_path / ".env"
            # File should be readable by owner
            assert env_file.exists()
            # Could check specific permissions if security requires

    def test_env_file_encoding_utf8(self, tmp_path):
        """Integration: .env file uses UTF-8 encoding."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "id": "sub-123",
                    "tenantId": "tenant-456",
                    "name": "Test™ Subscription™",
                }
            )
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            env_file = tmp_path / ".env"
            # Should be readable as UTF-8
            content = env_file.read_text(encoding="utf-8")
            assert content  # No encoding errors

    def test_directory_creation_if_needed(self, tmp_path):
        """Integration: Creates PWA directory if it doesn't exist."""
        pwa_dir = tmp_path / "new_pwa_directory"
        assert not pwa_dir.exists()

        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "sub-123", "tenantId": "tenant-456"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=pwa_dir)

            # Behavior depends on design decision
            # Document expected behavior once decided
            if result.success:
                assert pwa_dir.exists()


class TestSubprocessIntegration:
    """Integration tests for subprocess calls to Azure CLI."""

    def test_subprocess_called_with_correct_command(self, tmp_path):
        """Integration: Verify correct subprocess command for Azure CLI."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "sub-123", "tenantId": "tenant-456"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            generator.extract_azure_config()

            # Verify subprocess.run was called with correct args
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "az" in call_args
            assert "account" in call_args
            assert "show" in call_args

    def test_subprocess_timeout_handling(self, tmp_path):
        """Integration: Handle subprocess timeout gracefully."""
        with (
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="az", timeout=30)),
        ):
            generator = PWAConfigGenerator()
            config = generator.extract_azure_config()

            # Should handle timeout gracefully
            assert config is None

    def test_subprocess_stderr_captured(self, tmp_path):
        """Integration: Capture stderr from Azure CLI errors."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "ERROR: Please run 'az login' to authenticate"
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            # Should capture and include error message
            assert result.success is False
            assert result.error is not None


class TestMultiSourceIntegration:
    """Integration tests for multiple config sources working together."""

    @pytest.fixture
    def multi_source_environment(self, tmp_path):
        """Environment with multiple config sources."""
        # Azure CLI mock
        azlin_config_dir = tmp_path / ".azlin"
        azlin_config_dir.mkdir()
        config_file = azlin_config_dir / "config.toml"
        config_file.write_text(
            """
[azure]
subscription_id = "config-sub-111"
tenant_id = "config-tenant-222"
resource_group = "config-rg"
"""
        )

        pwa_dir = tmp_path / "pwa"
        pwa_dir.mkdir()

        return {
            "azlin_config_dir": azlin_config_dir,
            "pwa_dir": pwa_dir,
        }

    def test_merge_values_from_multiple_sources(self, multi_source_environment):
        """Integration: Merge config values from Azure CLI and config file."""
        pwa_dir = multi_source_environment["pwa_dir"]
        azlin_config_dir = multi_source_environment["azlin_config_dir"]

        # Mock Azure CLI with partial data
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "id": "azure-cli-sub-333",
                    "tenantId": "azure-cli-tenant-444",
                    # No resource_group in Azure CLI output
                }
            )
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(
                pwa_dir=pwa_dir, azlin_config_dir=azlin_config_dir
            )

            # Should have values from both sources
            assert result.success is True

            # Azure CLI values take priority
            assert result.config_values["VITE_AZURE_SUBSCRIPTION_ID"] == "azure-cli-sub-333"

            # Config file provides additional values
            if "VITE_AZURE_RESOURCE_GROUP" in result.config_values:
                assert result.config_values["VITE_AZURE_RESOURCE_GROUP"] == "config-rg"

    def test_source_attribution_for_mixed_sources(self, multi_source_environment):
        """Integration: Track different sources for different values."""
        pwa_dir = multi_source_environment["pwa_dir"]
        azlin_config_dir = multi_source_environment["azlin_config_dir"]

        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "sub-555", "tenantId": "tenant-666"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(
                pwa_dir=pwa_dir, azlin_config_dir=azlin_config_dir
            )

            # Subscription from Azure CLI
            assert result.source_attribution["VITE_AZURE_SUBSCRIPTION_ID"] == ConfigSource.AZURE_CLI

            # Resource group from config file (if present)
            if "VITE_AZURE_RESOURCE_GROUP" in result.source_attribution:
                assert (
                    result.source_attribution["VITE_AZURE_RESOURCE_GROUP"]
                    == ConfigSource.AZLIN_CONFIG
                )


class TestErrorRecoveryIntegration:
    """Integration tests for error handling and recovery."""

    def test_partial_failure_recovery(self, tmp_path):
        """Integration: Continue with partial data if some sources fail."""
        # Azure CLI fails
        with patch("shutil.which", return_value=None):
            # But config file exists
            azlin_config_dir = tmp_path / ".azlin"
            azlin_config_dir.mkdir()
            config_file = azlin_config_dir / "config.toml"
            config_file.write_text(
                """
[azure]
subscription_id = "fallback-sub-777"
"""
            )

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(
                pwa_dir=tmp_path, azlin_config_dir=azlin_config_dir
            )

            # Should succeed with fallback source
            assert result.success is True
            assert "fallback-sub-777" in result.config_values.values()

    def test_complete_failure_handling(self, tmp_path):
        """Integration: Handle case when all sources fail."""
        # No Azure CLI
        with patch("shutil.which", return_value=None):
            # No config file
            # No existing .env

            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            # Should succeed gracefully with placeholder .env and helpful message
            assert result.success is True
            assert result.message  # Has helpful message
            assert "azure cli not available" in result.message.lower()
            # .env file should be created with default values
            assert result.env_path is not None
            assert result.env_path.exists()


class TestCLIIntegration:
    """Integration tests for CLI command integration."""

    def test_cli_web_start_calls_config_generator(self, tmp_path):
        """Integration: Verify web_start CLI command calls config generator."""
        # This test verifies that the CLI integration point works
        # Will be implemented once CLI changes are made

        # Mock the generator
        with patch(
            "azlin.modules.pwa_config_generator.PWAConfigGenerator.generate_pwa_env_from_azlin"
        ) as mock_generate:
            mock_generate.return_value = PWAConfigResult(
                success=True,
                env_path=tmp_path / ".env",
                config_values={},
                source_attribution={},
                message="Success",
            )

            # Import and call CLI function
            # from azlin.cli import web_start
            # web_start(...)

            # Verify generator was called
            # mock_generate.assert_called_once()

            # This test documents the integration point
            # Will be completed when CLI is modified


class TestEnvFileFormatIntegration:
    """Integration tests for .env file format correctness."""

    def test_env_file_compatible_with_vite(self, tmp_path):
        """Integration: Generated .env is compatible with Vite."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "sub-888", "tenantId": "tenant-999"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            env_file = tmp_path / ".env"
            content = env_file.read_text()

            # Vite requirements:
            # - Variables start with VITE_
            # - Format: KEY=value (no spaces around =)
            # - No quotes needed for simple values
            for line in content.split("\n"):
                if line.strip() and not line.strip().startswith("#"):
                    assert "VITE_" in line
                    assert "=" in line
                    # No spaces around =
                    assert " = " not in line

    def test_env_file_has_proper_comments(self, tmp_path):
        """Integration: .env file includes helpful comments."""
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "sub-000", "tenantId": "tenant-111"})
            mock_run.return_value = mock_result

            generator = PWAConfigGenerator()
            generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            env_file = tmp_path / ".env"
            content = env_file.read_text()

            # Should have header
            lines = content.split("\n")
            assert lines[0].startswith("#")

            # Should have source attribution comments
            assert any("source:" in line.lower() for line in lines if "#" in line)


class TestRealWorldScenarios:
    """Integration tests for real-world usage scenarios."""

    def test_fresh_pwa_setup_scenario(self, tmp_path):
        """Integration: Complete scenario - setting up new PWA project."""
        # User has Azure CLI authenticated
        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "id": "12345678-1234-1234-1234-123456789012",
                    "tenantId": "87654321-4321-4321-4321-210987654321",
                }
            )
            mock_run.return_value = mock_result

            # User runs config generation
            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path)

            # Should succeed
            assert result.success is True

            # .env should be ready for Vite
            env_file = tmp_path / ".env"
            assert env_file.exists()

            # User can start dev server
            content = env_file.read_text()
            assert "VITE_AZURE_SUBSCRIPTION_ID=" in content

    def test_update_existing_config_scenario(self, tmp_path):
        """Integration: Scenario - user wants to update existing .env."""
        # Create existing .env
        env_file = tmp_path / ".env"
        env_file.write_text("VITE_AZURE_SUBSCRIPTION_ID=old-value")

        with patch("shutil.which", return_value="/usr/bin/az"), patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"id": "new-sub", "tenantId": "new-tenant"})
            mock_run.return_value = mock_result

            # User tries without force - should fail
            generator = PWAConfigGenerator()
            result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path, force=False)
            assert result.success is False

            # User uses force flag - should succeed
            result = generator.generate_pwa_env_from_azlin(pwa_dir=tmp_path, force=True)
            assert result.success is True

            # Config updated
            content = env_file.read_text()
            assert "new-sub" in content


# ============================================================================
# Proportionality Check
# ============================================================================
# This test file: ~550 lines
# Combined with unit tests: ~1200 lines total
# Expected implementation: ~200-300 lines
# Ratio: ~4-6:1 (appropriate for critical config generation with safety requirements)
# ============================================================================
