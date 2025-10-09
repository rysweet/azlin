"""Unit tests for remote_exec module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from azlin.remote_exec import RemoteExecutor, RemoteResult, WCommandExecutor, RemoteExecError
from azlin.modules.ssh_connector import SSHConfig


class TestRemoteResult:
    """Tests for RemoteResult dataclass."""

    def test_get_output_both(self):
        """Test getting combined output."""
        result = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="stdout text",
            stderr="stderr text",
            exit_code=0
        )
        output = result.get_output()
        assert "stdout text" in output
        assert "stderr text" in output

    def test_get_output_stdout_only(self):
        """Test getting stdout only."""
        result = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="stdout text",
            stderr="",
            exit_code=0
        )
        output = result.get_output()
        assert output == "stdout text"

    def test_get_output_stderr_only(self):
        """Test getting stderr only."""
        result = RemoteResult(
            vm_name="test-vm",
            success=False,
            stdout="",
            stderr="error message",
            exit_code=1
        )
        output = result.get_output()
        assert output == "error message"


class TestRemoteExecutor:
    """Tests for RemoteExecutor class."""

    @patch('azlin.remote_exec.subprocess.run')
    def test_execute_command_success(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="command output",
            stderr=""
        )

        ssh_config = SSHConfig(
            host="1.2.3.4",
            user="azureuser",
            key_path=Path("/tmp/key")
        )

        result = RemoteExecutor.execute_command(ssh_config, "ls -la", timeout=30)

        assert result.success is True
        assert result.stdout == "command output"
        assert result.exit_code == 0

    @patch('azlin.remote_exec.subprocess.run')
    def test_execute_command_failure(self, mock_run):
        """Test failed command execution."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="command not found"
        )

        ssh_config = SSHConfig(
            host="1.2.3.4",
            user="azureuser",
            key_path=Path("/tmp/key")
        )

        result = RemoteExecutor.execute_command(ssh_config, "badcommand", timeout=30)

        assert result.success is False
        assert result.stderr == "command not found"
        assert result.exit_code == 1

    def test_parse_command_from_args(self):
        """Test parsing command from args."""
        args = ["azlin", "--name", "vm", "--", "python", "script.py", "--arg"]
        command = RemoteExecutor.parse_command_from_args(args)
        assert command == "python script.py --arg"

    def test_parse_command_from_args_no_delimiter(self):
        """Test parsing when no delimiter."""
        args = ["azlin", "--name", "vm"]
        command = RemoteExecutor.parse_command_from_args(args)
        assert command is None

    def test_parse_command_from_args_empty_command(self):
        """Test parsing with delimiter but no command."""
        args = ["azlin", "--name", "vm", "--"]
        command = RemoteExecutor.parse_command_from_args(args)
        assert command is None

    def test_extract_command_slug(self):
        """Test extracting command slug."""
        slug = RemoteExecutor.extract_command_slug("python train.py --epochs 100")
        assert slug == "python-train-py"

        slug2 = RemoteExecutor.extract_command_slug("ls -la /tmp/file")
        assert slug2 == "ls-la-tmp"

    def test_extract_command_slug_max_length(self):
        """Test slug truncation."""
        slug = RemoteExecutor.extract_command_slug("very-long-command-name-that-exceeds-limit", max_length=10)
        assert len(slug) <= 10

    def test_format_parallel_output(self):
        """Test formatting parallel execution output."""
        results = [
            RemoteResult("vm-1", True, "output 1", "", 0),
            RemoteResult("vm-2", True, "output 2", "", 0),
            RemoteResult("vm-3", False, "", "error", 1),
        ]

        output = RemoteExecutor.format_parallel_output(results, show_vm_name=True)

        assert "[vm-1] output 1" in output
        assert "[vm-2] output 2" in output
        assert "[vm-3] ERROR: error" in output

    def test_format_parallel_output_no_vm_name(self):
        """Test formatting without VM names."""
        results = [
            RemoteResult("vm-1", True, "output 1", "", 0),
        ]

        output = RemoteExecutor.format_parallel_output(results, show_vm_name=False)

        assert "[vm-1]" not in output
        assert "output 1" in output


class TestWCommandExecutor:
    """Tests for WCommandExecutor class."""

    @patch('azlin.remote_exec.RemoteExecutor.execute_parallel')
    def test_execute_w_on_vms(self, mock_execute):
        """Test executing 'w' command on VMs."""
        mock_execute.return_value = [
            RemoteResult("vm-1", True, "w output 1", "", 0),
            RemoteResult("vm-2", True, "w output 2", "", 0),
        ]

        ssh_configs = [
            SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="5.6.7.8", user="azureuser", key_path=Path("/tmp/key")),
        ]

        results = WCommandExecutor.execute_w_on_vms(ssh_configs)

        assert len(results) == 2
        mock_execute.assert_called_once()

    def test_format_w_output(self):
        """Test formatting 'w' command output."""
        results = [
            RemoteResult("vm-1", True, "w output 1", "", 0),
            RemoteResult("vm-2", False, "", "connection failed", 1),
        ]

        output = WCommandExecutor.format_w_output(results)

        assert "VM: vm-1" in output
        assert "w output 1" in output
        assert "VM: vm-2" in output
        assert "ERROR: connection failed" in output
