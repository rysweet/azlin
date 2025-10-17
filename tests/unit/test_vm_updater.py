"""Unit tests for VM updater module.

Tests the VMUpdater class that handles updating development tools on VMs.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteResult
from azlin.vm_updater import UpdateResult, VMUpdater, VMUpdateSummary


@pytest.fixture
def ssh_config():
    """Create test SSH config."""
    return SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/id_rsa"))


@pytest.fixture
def mock_executor():
    """Mock RemoteExecutor for testing."""
    with patch("azlin.vm_updater.RemoteExecutor") as mock:
        yield mock


class TestUpdateResult:
    """Test UpdateResult dataclass."""

    def test_create_success_result(self):
        """Test creating successful update result."""
        result = UpdateResult(
            tool_name="npm", success=True, message="Updated successfully", duration=10.5
        )

        assert result.tool_name == "npm"
        assert result.success is True
        assert result.message == "Updated successfully"
        assert result.duration == 10.5

    def test_create_failure_result(self):
        """Test creating failed update result."""
        result = UpdateResult(
            tool_name="rust",
            success=False,
            message="Update failed: connection timeout",
            duration=5.0,
        )

        assert result.tool_name == "rust"
        assert result.success is False
        assert "connection timeout" in result.message


class TestVMUpdateSummary:
    """Test VMUpdateSummary dataclass."""

    def test_all_succeeded(self):
        """Test summary when all updates succeed."""
        successful = [UpdateResult("npm", True, "OK", 10.0), UpdateResult("rust", True, "OK", 15.0)]

        summary = VMUpdateSummary(
            vm_name="test-vm",
            total_updates=2,
            successful=successful,
            failed=[],
            total_duration=25.0,
        )

        assert summary.success_count == 2
        assert summary.failure_count == 0
        assert summary.all_succeeded is True
        assert summary.any_failed is False

    def test_partial_success(self):
        """Test summary with partial success."""
        successful = [UpdateResult("npm", True, "OK", 10.0)]
        failed = [UpdateResult("rust", False, "Failed", 5.0)]

        summary = VMUpdateSummary(
            vm_name="test-vm",
            total_updates=2,
            successful=successful,
            failed=failed,
            total_duration=15.0,
        )

        assert summary.success_count == 1
        assert summary.failure_count == 1
        assert summary.all_succeeded is False
        assert summary.any_failed is True

    def test_all_failed(self):
        """Test summary when all updates fail."""
        failed = [
            UpdateResult("npm", False, "Failed", 5.0),
            UpdateResult("rust", False, "Failed", 5.0),
        ]

        summary = VMUpdateSummary(
            vm_name="test-vm", total_updates=2, successful=[], failed=failed, total_duration=10.0
        )

        assert summary.success_count == 0
        assert summary.failure_count == 2
        assert summary.all_succeeded is False
        assert summary.any_failed is True


class TestVMUpdaterSystemPackages:
    """Test system package updates."""

    def test_update_system_packages_success(self, ssh_config, mock_executor):
        """Test successful system package update."""
        # Mock successful apt update
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="Reading package lists...\nAll packages updated",
            stderr="",
            exit_code=0,
            duration=30.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_system_packages()

        assert result.success is True
        assert result.tool_name == "system-packages"
        assert "updated" in result.message.lower()
        mock_executor.execute_command.assert_called_once()

    def test_update_system_packages_failure(self, ssh_config, mock_executor):
        """Test failed system package update."""
        # Mock failed apt update
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=False,
            stdout="",
            stderr="E: Could not get lock /var/lib/apt/lists/lock",
            exit_code=100,
            duration=5.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_system_packages()

        assert result.success is False
        assert result.tool_name == "system-packages"
        assert "lock" in result.message.lower()


class TestVMUpdaterAzureCLI:
    """Test Azure CLI updates."""

    def test_update_azure_cli_success(self, ssh_config, mock_executor):
        """Test successful Azure CLI update."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="Azure CLI updated to version 2.50.0",
            stderr="",
            exit_code=0,
            duration=45.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_azure_cli()

        assert result.success is True
        assert result.tool_name == "azure-cli"
        assert "updated" in result.message.lower()

    def test_update_azure_cli_no_upgrade_needed(self, ssh_config, mock_executor):
        """Test Azure CLI when no upgrade is needed."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="You already have the latest Azure CLI version",
            stderr="",
            exit_code=0,
            duration=5.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_azure_cli()

        assert result.success is True
        assert result.tool_name == "azure-cli"


class TestVMUpdaterNPM:
    """Test NPM and NPM packages updates."""

    def test_update_npm_success(self, ssh_config, mock_executor):
        """Test successful npm update."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="updated 1 package in 5s",
            stderr="",
            exit_code=0,
            duration=5.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_npm()

        assert result.success is True
        assert result.tool_name == "npm"

    def test_update_npm_packages_success(self, ssh_config, mock_executor):
        """Test successful npm packages update."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="updated 3 packages in 10s",
            stderr="",
            exit_code=0,
            duration=10.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_npm_packages()

        assert result.success is True
        assert result.tool_name == "npm-packages"


class TestVMUpdaterRust:
    """Test Rust toolchain updates."""

    def test_update_rust_success(self, ssh_config, mock_executor):
        """Test successful Rust update."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="info: syncing channel updates for 'stable'\ninfo: updated",
            stderr="",
            exit_code=0,
            duration=20.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_rust()

        assert result.success is True
        assert result.tool_name == "rust"

    def test_update_rust_already_current(self, ssh_config, mock_executor):
        """Test Rust update when already current."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="info: checking for self-updates\ninfo: unchanged",
            stderr="",
            exit_code=0,
            duration=3.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_rust()

        assert result.success is True
        assert result.tool_name == "rust"


class TestVMUpdaterGitHubCLI:
    """Test GitHub CLI updates."""

    def test_update_github_cli_success(self, ssh_config, mock_executor):
        """Test successful GitHub CLI extension update."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="✓ Successfully upgraded extension copilot",
            stderr="",
            exit_code=0,
            duration=10.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_github_cli()

        assert result.success is True
        assert result.tool_name == "github-cli"


class TestVMUpdaterAstralUV:
    """Test astral-uv snap updates."""

    def test_update_astral_uv_success(self, ssh_config, mock_executor):
        """Test successful astral-uv update."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="astral-uv refreshed",
            stderr="",
            exit_code=0,
            duration=15.0,
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_astral_uv()

        assert result.success is True
        assert result.tool_name == "astral-uv"


class TestVMUpdaterFullUpdate:
    """Test full VM update process."""

    def test_update_vm_all_success(self, ssh_config, mock_executor):
        """Test successful update of all tools."""
        # Mock all updates as successful
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="Success", stderr="", exit_code=0, duration=10.0
        )

        updater = VMUpdater(ssh_config)
        summary = updater.update_vm()

        assert summary.vm_name == "20.1.2.3"
        assert summary.all_succeeded is True
        assert summary.failure_count == 0
        # Should update: system, az, gh, npm, npm-packages, rust, astral-uv
        assert summary.success_count >= 7

    def test_update_vm_partial_failure(self, ssh_config, mock_executor):
        """Test update with some failures."""
        # Mock responses: some succeed, some fail
        responses = [
            RemoteResult("test-vm", True, "OK", "", 0, 10.0),  # system
            RemoteResult("test-vm", True, "OK", "", 0, 10.0),  # az
            RemoteResult("test-vm", False, "", "Error", 1, 5.0),  # gh - fails
            RemoteResult("test-vm", True, "OK", "", 0, 10.0),  # npm
            RemoteResult("test-vm", True, "OK", "", 0, 10.0),  # npm-packages
            RemoteResult("test-vm", True, "OK", "", 0, 10.0),  # rust
            RemoteResult("test-vm", True, "OK", "", 0, 10.0),  # astral-uv
        ]
        mock_executor.execute_command.side_effect = responses

        updater = VMUpdater(ssh_config)
        summary = updater.update_vm()

        assert summary.any_failed is True
        assert summary.all_succeeded is False
        assert summary.success_count >= 6
        assert summary.failure_count >= 1

    def test_update_vm_timeout_handling(self, ssh_config, mock_executor):
        """Test handling of timeout during update."""
        from azlin.remote_exec import RemoteExecError

        # Mock timeout error
        mock_executor.execute_command.side_effect = RemoteExecError("Command timed out after 300s")

        updater = VMUpdater(ssh_config)
        summary = updater.update_vm()

        # Should have failure results for each attempted update
        assert summary.any_failed is True
        assert all(
            "timeout" in r.message.lower() or "failed" in r.message.lower() for r in summary.failed
        )


class TestVMUpdaterEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_ssh_config(self):
        """Test with invalid SSH config."""
        invalid_config = SSHConfig(host="", user="azureuser", key_path=Path("/nonexistent/key"))

        updater = VMUpdater(invalid_config)
        summary = updater.update_vm()

        # Should fail gracefully
        assert summary.any_failed is True

    def test_update_with_progress_callback(self, ssh_config, mock_executor):
        """Test update with progress callback."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="OK", stderr="", exit_code=0, duration=10.0
        )

        progress_messages = []

        def callback(msg: str):
            progress_messages.append(msg)

        updater = VMUpdater(ssh_config, progress_callback=callback)
        updater.update_vm()

        # Should have received progress updates
        assert len(progress_messages) > 0
        assert any("updating" in msg.lower() for msg in progress_messages)

    def test_update_result_duration_tracked(self, ssh_config, mock_executor):
        """Test that update duration is properly tracked."""
        mock_executor.execute_command.return_value = RemoteResult(
            vm_name="test-vm", success=True, stdout="OK", stderr="", exit_code=0, duration=25.5
        )

        updater = VMUpdater(ssh_config)
        result = updater._update_npm()

        # Duration is tracked internally by VMUpdater, not from RemoteResult
        assert result.duration > 0
        assert result.duration < 1.0  # Should be very fast for a mock
