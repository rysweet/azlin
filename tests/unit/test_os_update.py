"""Unit tests for OS update functionality."""

from pathlib import Path
from unittest.mock import patch

from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import OSUpdateExecutor, RemoteResult


class TestOSUpdateExecutor:
    """Test OS update execution."""

    def test_execute_os_update_success(self):
        """Test successful OS update execution."""
        ssh_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/azlin_key")
        )

        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            mock_exec.return_value = RemoteResult(
                vm_name="20.1.2.3",
                success=True,
                stdout="Reading package lists...\nUpgrading packages...\n",
                stderr="",
                exit_code=0,
                duration=45.2,
            )

            result = OSUpdateExecutor.execute_os_update(ssh_config)

            assert result.success is True
            assert result.exit_code == 0
            assert "package" in result.stdout.lower()
            mock_exec.assert_called_once()

    def test_execute_os_update_with_timeout(self):
        """Test OS update with custom timeout."""
        ssh_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/azlin_key")
        )

        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            mock_exec.return_value = RemoteResult(
                vm_name="20.1.2.3", success=True, stdout="Update complete", stderr="", exit_code=0
            )

            result = OSUpdateExecutor.execute_os_update(ssh_config, timeout=600)

            assert result.success is True
            # Verify timeout was passed
            call_args = mock_exec.call_args
            assert call_args[1]["timeout"] == 600

    def test_execute_os_update_failure(self):
        """Test OS update execution failure."""
        ssh_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/azlin_key")
        )

        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            mock_exec.return_value = RemoteResult(
                vm_name="20.1.2.3",
                success=False,
                stdout="",
                stderr="E: Could not get lock /var/lib/dpkg/lock",
                exit_code=100,
                duration=5.0,
            )

            result = OSUpdateExecutor.execute_os_update(ssh_config)

            assert result.success is False
            assert result.exit_code == 100
            assert "lock" in result.stderr.lower()

    def test_execute_os_update_uses_correct_command(self):
        """Test that correct apt command is executed."""
        ssh_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/azlin_key")
        )

        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            mock_exec.return_value = RemoteResult(
                vm_name="20.1.2.3", success=True, stdout="Success", stderr="", exit_code=0
            )

            OSUpdateExecutor.execute_os_update(ssh_config)

            # Verify the command includes apt update and upgrade
            call_args = mock_exec.call_args
            command = call_args[0][1]  # Second argument is the command
            assert "apt update" in command
            assert "apt upgrade" in command
            assert "sudo" in command
            assert "-y" in command  # Non-interactive

    def test_format_output_success(self):
        """Test formatting successful update output."""
        result = RemoteResult(
            vm_name="azlin-test",
            success=True,
            stdout="Reading package lists... Done\n5 packages upgraded",
            stderr="",
            exit_code=0,
            duration=45.0,
        )

        output = OSUpdateExecutor.format_output(result)

        assert "azlin-test" in output
        assert "upgraded" in output.lower()
        assert "success" in output.lower() or "complete" in output.lower()

    def test_format_output_failure(self):
        """Test formatting failed update output."""
        result = RemoteResult(
            vm_name="azlin-test",
            success=False,
            stdout="",
            stderr="E: Could not get lock",
            exit_code=100,
            duration=5.0,
        )

        output = OSUpdateExecutor.format_output(result)

        assert "azlin-test" in output
        assert "error" in output.lower() or "failed" in output.lower()
        assert "lock" in output.lower()

    def test_format_output_shows_duration(self):
        """Test that output includes execution duration."""
        result = RemoteResult(
            vm_name="azlin-test",
            success=True,
            stdout="Update complete",
            stderr="",
            exit_code=0,
            duration=123.45,
        )

        output = OSUpdateExecutor.format_output(result)

        # Should show duration in some format
        assert "123" in output or "2m" in output or "2 min" in output


class TestOSUpdateCLI:
    """Test CLI integration for os-update command."""

    @patch("azlin.cli.OSUpdateExecutor")
    @patch("azlin.cli._get_ssh_config_for_vm")
    @patch("azlin.cli.click.echo")
    def test_os_update_command_exists(self, mock_echo, mock_get_config, mock_executor):
        """Test that os-update command is registered."""
        # This test will pass once we add the command to cli.py
        from azlin.cli import main

        # Check command is registered
        assert "os-update" in [cmd.name for cmd in main.commands.values()] or "os_update" in [
            cmd.name for cmd in main.commands.values()
        ]

    @patch("azlin.cli.OSUpdateExecutor")
    @patch("azlin.cli._get_ssh_config_for_vm")
    @patch("azlin.cli.click.echo")
    def test_os_update_with_session_name(self, mock_echo, mock_get_config, mock_executor):
        """Test os-update with session name."""
        mock_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/azlin_key")
        )
        mock_get_config.return_value = mock_config

        mock_result = RemoteResult(
            vm_name="20.1.2.3", success=True, stdout="Update complete", stderr="", exit_code=0
        )
        mock_executor.execute_os_update.return_value = mock_result
        mock_executor.format_output.return_value = "Update successful"

        # This will be implemented in cli.py
        from azlin.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(main, ["os-update", "my-session"])

        assert result.exit_code == 0
        mock_get_config.assert_called_once()
        mock_executor.execute_os_update.assert_called_once()

    @patch("azlin.cli.OSUpdateExecutor")
    @patch("azlin.cli._get_ssh_config_for_vm")
    @patch("azlin.cli.click.echo")
    def test_os_update_handles_errors(self, mock_echo, mock_get_config, mock_executor):
        """Test os-update handles errors gracefully."""
        mock_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/azlin_key")
        )
        mock_get_config.return_value = mock_config

        mock_result = RemoteResult(
            vm_name="20.1.2.3", success=False, stdout="", stderr="Connection refused", exit_code=255
        )
        mock_executor.execute_os_update.return_value = mock_result

        from azlin.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(main, ["os-update", "my-session"])

        # Should exit with error code
        assert result.exit_code != 0
