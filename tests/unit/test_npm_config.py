"""Unit tests for npm user-local configuration module.

This module tests the npm configuration functionality that sets up
user-local global package installations to avoid requiring sudo.

Test Coverage (TDD - RED phase):
- npm prefix configuration in ~/.npmrc
- ~/.npm-packages directory creation
- PATH environment variable configuration
- MANPATH environment variable configuration
- Idempotency (safe to run multiple times)
- Integration with VM provisioning flow
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.modules.npm_config import NpmConfigError, NpmConfigResult, NpmConfigurator
from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteResult


class TestNpmConfigResult:
    """Tests for NpmConfigResult dataclass."""

    def test_npm_config_result_success(self):
        """Test successful npm configuration result."""
        result = NpmConfigResult(
            success=True,
            message="npm configured successfully",
            npmrc_configured=True,
            directory_created=True,
            bashrc_updated=True,
            bashrc_sourced=True,
        )

        assert result.success is True
        assert result.npmrc_configured is True
        assert result.directory_created is True
        assert result.bashrc_updated is True
        assert result.bashrc_sourced is True

    def test_npm_config_result_partial_failure(self):
        """Test partial failure in npm configuration."""
        result = NpmConfigResult(
            success=False,
            message="Failed to update bashrc",
            npmrc_configured=True,
            directory_created=True,
            bashrc_updated=False,
            bashrc_sourced=False,
        )

        assert result.success is False
        assert result.bashrc_updated is False
        assert result.bashrc_sourced is False


class TestNpmConfiguratorBasics:
    """Tests for NpmConfigurator basic functionality."""

    def test_creates_npm_configurator_with_ssh_config(self):
        """Test creating npm configurator with SSH configuration."""
        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)

        assert configurator.ssh_config == ssh_config
        assert configurator.npm_packages_dir == "${HOME}/.npm-packages"
        assert configurator.npmrc_path == "${HOME}/.npmrc"
        assert configurator.bashrc_path == "${HOME}/.bashrc"

    def test_generates_correct_npmrc_content(self):
        """Test that .npmrc content is correctly generated."""
        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        npmrc_content = configurator.get_npmrc_content()

        assert "prefix=${HOME}/.npm-packages" in npmrc_content

    def test_generates_correct_bashrc_content(self):
        """Test that .bashrc additions are correctly generated."""
        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        bashrc_content = configurator.get_bashrc_content()

        # Should contain NPM_PACKAGES variable
        assert "NPM_PACKAGES=" in bashrc_content
        assert "${HOME}/.npm-packages" in bashrc_content

        # Should update PATH (uses $NPM_PACKAGES syntax)
        assert "PATH=" in bashrc_content
        assert "$NPM_PACKAGES/bin" in bashrc_content

        # Should update MANPATH
        assert "MANPATH=" in bashrc_content
        assert "$NPM_PACKAGES/share/man" in bashrc_content


class TestNpmDirectoryCreation:
    """Tests for npm packages directory creation."""

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_creates_npm_packages_directory(self, mock_execute):
        """Test creating .npm-packages directory on VM."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.create_npm_directory()

        assert result is True
        mock_execute.assert_called_once()

        # Verify command creates directory
        call_args = mock_execute.call_args
        command = call_args[0][1]
        assert "mkdir" in command
        assert ".npm-packages" in command

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_directory_creation_is_idempotent(self, mock_execute):
        """Test that directory creation is idempotent (uses mkdir -p)."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        configurator.create_npm_directory()

        # Verify uses mkdir -p for idempotency
        call_args = mock_execute.call_args
        command = call_args[0][1]
        assert "mkdir -p" in command

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_handles_directory_creation_failure(self, mock_execute):
        """Test handling of directory creation failure."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=False, stdout="", stderr="Permission denied", exit_code=1
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)

        with pytest.raises(NpmConfigError) as exc_info:
            configurator.create_npm_directory()

        assert "Permission denied" in str(exc_info.value)


class TestNpmrcConfiguration:
    """Tests for .npmrc configuration."""

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_configures_npmrc_file(self, mock_execute):
        """Test configuring .npmrc with npm prefix."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_npmrc()

        assert result is True
        mock_execute.assert_called_once()

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_npmrc_configuration_is_idempotent(self, mock_execute):
        """Test that .npmrc configuration is idempotent."""
        # First call: file doesn't have the config
        mock_execute.side_effect = [
            # grep check - not found
            RemoteResult(vm_name="test-vm", success=False, stdout="", stderr="", exit_code=1),
            # append config
            RemoteResult(vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0),
        ]

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_npmrc()

        assert result is True

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_skips_npmrc_if_already_configured(self, mock_execute):
        """Test that .npmrc configuration is skipped if already present."""
        # grep check - found
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="prefix=${HOME}/.npm-packages",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_npmrc()

        assert result is True
        # Should only call grep, not append
        assert mock_execute.call_count == 1


class TestBashrcConfiguration:
    """Tests for .bashrc configuration."""

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_configures_bashrc_with_npm_variables(self, mock_execute):
        """Test configuring .bashrc with NPM_PACKAGES, PATH, and MANPATH."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_bashrc()

        assert result is True
        mock_execute.assert_called_once()

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_bashrc_configuration_is_idempotent(self, mock_execute):
        """Test that .bashrc configuration is idempotent."""
        # First call: grep check - not found
        mock_execute.side_effect = [
            RemoteResult(vm_name="test-vm", success=False, stdout="", stderr="", exit_code=1),
            # append config
            RemoteResult(vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0),
        ]

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_bashrc()

        assert result is True

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_skips_bashrc_if_already_configured(self, mock_execute):
        """Test that .bashrc configuration is skipped if already present."""
        # grep check - found
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="NPM_PACKAGES=", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_bashrc()

        assert result is True
        # Should only call grep, not append
        assert mock_execute.call_count == 1


class TestBashrcSourceing:
    """Tests for sourcing .bashrc to apply changes."""

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_sources_bashrc_to_apply_changes(self, mock_execute):
        """Test sourcing .bashrc after configuration."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.source_bashrc()

        assert result is True
        mock_execute.assert_called_once()

        # Verify command sources bashrc
        call_args = mock_execute.call_args
        command = call_args[0][1]
        assert "source" in command or "." in command
        assert ".bashrc" in command


class TestNpmConfigurationEndToEnd:
    """Tests for end-to-end npm configuration."""

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_configure_npm_runs_all_steps(self, mock_execute):
        """Test that configure_npm runs all configuration steps."""
        # Mock all successful responses
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_npm()

        assert result.success is True
        assert result.directory_created is True
        assert result.npmrc_configured is True
        assert result.bashrc_updated is True
        assert result.bashrc_sourced is True

        # Should have called execute_command multiple times
        assert mock_execute.call_count >= 4

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_configure_npm_handles_partial_failure(self, mock_execute):
        """Test that configure_npm handles partial failures gracefully."""
        # Mock mixed responses - bashrc update fails
        mock_execute.side_effect = [
            # create directory - success
            RemoteResult(vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0),
            # configure npmrc - check
            RemoteResult(vm_name="test-vm", success=False, stdout="", stderr="", exit_code=1),
            # configure npmrc - append
            RemoteResult(vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0),
            # configure bashrc - check
            RemoteResult(vm_name="test-vm", success=False, stdout="", stderr="", exit_code=1),
            # configure bashrc - append (FAILS)
            RemoteResult(
                vm_name="test-vm", success=False, stdout="", stderr="Write error", exit_code=1
            ),
        ]

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)

        with pytest.raises(NpmConfigError) as exc_info:
            configurator.configure_npm()

        assert "Write error" in str(exc_info.value)

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_configure_npm_is_idempotent(self, mock_execute):
        """Test that configure_npm can be run multiple times safely."""
        # Mock all checks return "already configured"
        mock_execute.side_effect = [
            # create directory - already exists
            RemoteResult(vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0),
            # check npmrc - found
            RemoteResult(vm_name="test-vm", success=True, stdout="prefix=", stderr="", exit_code=0),
            # check bashrc - found
            RemoteResult(
                vm_name="test-vm", success=True, stdout="NPM_PACKAGES=", stderr="", exit_code=0
            ),
            # source bashrc
            RemoteResult(vm_name="test-vm", success=True, stdout="", stderr="", exit_code=0),
        ]

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_npm()

        assert result.success is True
        # Should not have appended anything, just checked
        assert mock_execute.call_count == 4


class TestNpmConfigIntegrationWithProvisioning:
    """Tests for integration with VM provisioning flow."""

    @patch("azlin.modules.npm_config.NpmConfigurator.configure_npm")
    def test_can_be_called_after_vm_provisioning(self, mock_configure):
        """Test that npm configuration can be called after VM provisioning."""
        mock_configure.return_value = NpmConfigResult(
            success=True,
            message="npm configured",
            npmrc_configured=True,
            directory_created=True,
            bashrc_updated=True,
            bashrc_sourced=True,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)
        result = configurator.configure_npm()

        assert result.success is True
        mock_configure.assert_called_once()

    def test_npm_configurator_has_vm_name_attribute(self):
        """Test that npm configurator tracks VM name for logging."""
        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)

        # Should use host as VM identifier
        assert configurator.vm_name == "1.2.3.4"


class TestNpmConfigErrorHandling:
    """Tests for npm configuration error handling."""

    def test_npm_config_error_has_message(self):
        """Test that NpmConfigError includes error message."""
        error = NpmConfigError("Configuration failed")
        assert str(error) == "Configuration failed"

    @patch("azlin.modules.npm_config.RemoteExecutor.execute_command")
    def test_raises_error_on_directory_creation_failure(self, mock_execute):
        """Test that error is raised on directory creation failure."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm", success=False, stdout="", stderr="Disk full", exit_code=1
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))  # noqa: S108

        configurator = NpmConfigurator(ssh_config)

        with pytest.raises(NpmConfigError) as exc_info:
            configurator.create_npm_directory()

        assert "Disk full" in str(exc_info.value)
