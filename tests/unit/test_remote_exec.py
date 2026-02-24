"""Unit tests for remote_exec module.

Tests the SSH command execution backbone with mocked subprocess calls.
Covers RemoteExecutor, TmuxSessionExecutor, PSCommandExecutor,
WCommandExecutor, and OSUpdateExecutor.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import (
    OSUpdateExecutor,
    PSCommandExecutor,
    RemoteExecError,
    RemoteExecutor,
    RemoteResult,
    TmuxSessionExecutor,
    WCommandExecutor,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ssh_config():
    """Standard SSH config for tests."""
    return SSHConfig(
        host="10.0.0.1",
        user="azureuser",
        key_path=Path("/home/azureuser/.ssh/id_rsa"),
        port=22,
    )


@pytest.fixture
def ssh_configs(ssh_config):
    """Multiple SSH configs for parallel execution tests."""
    return [
        ssh_config,
        SSHConfig(host="10.0.0.2", user="azureuser", key_path=Path("/home/azureuser/.ssh/id_rsa")),
        SSHConfig(host="10.0.0.3", user="azureuser", key_path=Path("/home/azureuser/.ssh/id_rsa")),
    ]


# ---------------------------------------------------------------------------
# RemoteResult
# ---------------------------------------------------------------------------


class TestRemoteResult:
    """Tests for the RemoteResult dataclass."""

    def test_get_output_stdout_only(self):
        r = RemoteResult(vm_name="vm1", success=True, stdout="hello", stderr="", exit_code=0)
        assert r.get_output() == "hello"

    def test_get_output_stderr_only(self):
        r = RemoteResult(vm_name="vm1", success=False, stdout="", stderr="err", exit_code=1)
        assert r.get_output() == "err"

    def test_get_output_both(self):
        r = RemoteResult(vm_name="vm1", success=True, stdout="out", stderr="warn", exit_code=0)
        assert r.get_output() == "out\nwarn"

    def test_get_output_empty(self):
        r = RemoteResult(vm_name="vm1", success=True, stdout="", stderr="", exit_code=0)
        assert r.get_output() == ""


# ---------------------------------------------------------------------------
# RemoteExecutor.execute_command
# ---------------------------------------------------------------------------


class TestRemoteExecutorCommand:
    """Tests for single-VM command execution."""

    @patch("azlin.remote_exec.subprocess.run")
    def test_successful_command(self, mock_run, ssh_config):
        mock_run.return_value = MagicMock(returncode=0, stdout="output line\n", stderr="")

        result = RemoteExecutor.execute_command(ssh_config, "echo hello", timeout=10)

        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output line\n"
        assert result.vm_name == "10.0.0.1"
        assert result.duration > 0

        # Verify SSH command structure
        args = mock_run.call_args[0][0]
        assert args[0] == "ssh"
        assert "-i" in args
        assert "azureuser@10.0.0.1" in args
        assert args[-1] == "echo hello"

    @patch("azlin.remote_exec.subprocess.run")
    def test_failed_command_nonzero_exit(self, mock_run, ssh_config):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="command not found")

        result = RemoteExecutor.execute_command(ssh_config, "bad_cmd")

        assert result.success is False
        assert result.exit_code == 1
        assert "command not found" in result.stderr

    @patch("azlin.remote_exec.subprocess.run")
    def test_timeout_raises_remote_exec_error(self, mock_run, ssh_config):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=5)

        with pytest.raises(RemoteExecError, match="timed out"):
            RemoteExecutor.execute_command(ssh_config, "sleep 100", timeout=5)

    @patch("azlin.remote_exec.subprocess.run")
    def test_connection_error_raises_remote_exec_error(self, mock_run, ssh_config):
        mock_run.side_effect = OSError("Connection refused")

        with pytest.raises(RemoteExecError, match="Failed to execute"):
            RemoteExecutor.execute_command(ssh_config, "echo hello")

    @patch("azlin.remote_exec.subprocess.run")
    def test_connect_timeout_capped_at_10(self, mock_run, ssh_config):
        """ConnectTimeout should be min(timeout, 10)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        RemoteExecutor.execute_command(ssh_config, "echo test", timeout=60)

        args = mock_run.call_args[0][0]
        assert "ConnectTimeout=10" in " ".join(args)

    @patch("azlin.remote_exec.subprocess.run")
    def test_connect_timeout_uses_smaller_value(self, mock_run, ssh_config):
        """ConnectTimeout should be min(timeout, 10) when timeout < 10."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        RemoteExecutor.execute_command(ssh_config, "echo test", timeout=3)

        args = mock_run.call_args[0][0]
        assert "ConnectTimeout=3" in " ".join(args)


# ---------------------------------------------------------------------------
# RemoteExecutor.execute_parallel
# ---------------------------------------------------------------------------


class TestRemoteExecutorParallel:
    """Tests for parallel command execution across multiple VMs."""

    @patch.object(RemoteExecutor, "execute_command")
    def test_parallel_all_succeed(self, mock_exec, ssh_configs):
        mock_exec.side_effect = [
            RemoteResult(vm_name=c.host, success=True, stdout="ok", stderr="", exit_code=0)
            for c in ssh_configs
        ]

        results = RemoteExecutor.execute_parallel(ssh_configs, "echo test")

        assert len(results) == 3
        assert all(r.success for r in results)

    @patch.object(RemoteExecutor, "execute_command")
    def test_parallel_one_failure_others_continue(self, mock_exec, ssh_configs):
        """If one VM fails, the others should still produce results."""
        mock_exec.side_effect = [
            RemoteResult(vm_name="10.0.0.1", success=True, stdout="ok", stderr="", exit_code=0),
            RemoteExecError("Connection refused"),
            RemoteResult(vm_name="10.0.0.3", success=True, stdout="ok", stderr="", exit_code=0),
        ]

        results = RemoteExecutor.execute_parallel(ssh_configs, "echo test")

        assert len(results) == 3
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert len(failures) == 1
        assert failures[0].exit_code == -1

    def test_parallel_empty_list(self):
        results = RemoteExecutor.execute_parallel([], "echo test")
        assert results == []

    @patch.object(RemoteExecutor, "execute_command")
    def test_parallel_respects_max_workers(self, mock_exec, ssh_configs):
        mock_exec.return_value = RemoteResult(
            vm_name="vm", success=True, stdout="", stderr="", exit_code=0
        )

        # max_workers=1 should still work, just sequentially
        results = RemoteExecutor.execute_parallel(ssh_configs, "echo test", max_workers=1)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# RemoteExecutor.format_parallel_output
# ---------------------------------------------------------------------------


class TestFormatParallelOutput:
    def test_format_with_vm_names(self):
        results = [
            RemoteResult(
                vm_name="vm1", success=True, stdout="line1\nline2", stderr="", exit_code=0
            ),
            RemoteResult(vm_name="vm2", success=False, stdout="", stderr="oops", exit_code=1),
        ]

        output = RemoteExecutor.format_parallel_output(results, show_vm_name=True)

        assert "[vm1] line1" in output
        assert "[vm1] line2" in output
        assert "[vm2] ERROR: oops" in output

    def test_format_without_vm_names(self):
        results = [
            RemoteResult(vm_name="vm1", success=True, stdout="hello", stderr="", exit_code=0),
        ]

        output = RemoteExecutor.format_parallel_output(results, show_vm_name=False)
        assert "[vm1]" not in output
        assert "hello" in output


# ---------------------------------------------------------------------------
# RemoteExecutor.parse_command_from_args / extract_command_slug
# ---------------------------------------------------------------------------


class TestCommandParsing:
    def test_parse_command_from_args_with_delimiter(self):
        args = ["azlin", "run", "--", "echo", "hello", "world"]
        result = RemoteExecutor.parse_command_from_args(args)
        assert result == "echo hello world"

    def test_parse_command_from_args_no_delimiter(self):
        args = ["azlin", "run", "echo"]
        assert RemoteExecutor.parse_command_from_args(args) is None

    def test_parse_command_from_args_empty_after_delimiter(self):
        args = ["azlin", "--"]
        assert RemoteExecutor.parse_command_from_args(args) is None

    def test_extract_command_slug_basic(self):
        slug = RemoteExecutor.extract_command_slug("python script.py --arg")
        # Takes first 3 words, cleans special chars to dashes, strips leading/trailing dashes
        assert slug == "python-script-py-arg"

    def test_extract_command_slug_truncation(self):
        slug = RemoteExecutor.extract_command_slug(
            "a_very_long_command with many arguments", max_length=10
        )
        assert len(slug) <= 10

    def test_extract_command_slug_empty(self):
        slug = RemoteExecutor.extract_command_slug("")
        assert slug == "cmd"


# ---------------------------------------------------------------------------
# TmuxSessionExecutor
# ---------------------------------------------------------------------------


class TestTmuxSessionExecutor:
    @patch.object(RemoteExecutor, "execute_command")
    def test_get_sessions_new_format(self, mock_exec, ssh_config):
        """Parse new tmux format: name:attached:windows:created."""
        mock_exec.return_value = RemoteResult(
            vm_name="10.0.0.1",
            success=True,
            stdout="dev:1:3:1696932000\nwork:0:2:1696932100\n",
            stderr="",
            exit_code=0,
        )

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="myvm")

        assert len(sessions) == 2
        assert sessions[0].session_name == "dev"
        assert sessions[0].attached is True
        assert sessions[0].windows == 3
        assert sessions[1].session_name == "work"
        assert sessions[1].attached is False

    @patch.object(RemoteExecutor, "execute_command")
    def test_get_sessions_old_format(self, mock_exec, ssh_config):
        """Parse old tmux format: name: X windows (created date)."""
        mock_exec.return_value = RemoteResult(
            vm_name="10.0.0.1",
            success=True,
            stdout="dev: 3 windows (created Thu Oct 10 10:00:00 2024) (attached)\n",
            stderr="",
            exit_code=0,
        )

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="myvm")

        assert len(sessions) == 1
        assert sessions[0].session_name == "dev"
        assert sessions[0].windows == 3
        assert sessions[0].attached is True

    @patch.object(RemoteExecutor, "execute_command")
    def test_get_sessions_no_sessions(self, mock_exec, ssh_config):
        mock_exec.return_value = RemoteResult(
            vm_name="10.0.0.1", success=True, stdout="No sessions\n", stderr="", exit_code=0
        )

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config)
        assert sessions == []

    @patch.object(RemoteExecutor, "execute_command")
    def test_get_sessions_ssh_failure(self, mock_exec, ssh_config):
        mock_exec.return_value = RemoteResult(
            vm_name="10.0.0.1", success=False, stdout="", stderr="Connection refused", exit_code=255
        )

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config)
        assert sessions == []

    def test_format_sessions_display_empty(self):
        assert TmuxSessionExecutor.format_sessions_display([]) == "No sessions"

    @patch.object(RemoteExecutor, "execute_parallel")
    def test_get_sessions_parallel(self, mock_parallel, ssh_configs):
        mock_parallel.return_value = [
            RemoteResult(
                vm_name="vm1", success=True, stdout="s1:0:1:123\n", stderr="", exit_code=0
            ),
            RemoteResult(
                vm_name="vm2", success=True, stdout="No sessions\n", stderr="", exit_code=0
            ),
            RemoteResult(vm_name="vm3", success=False, stdout="", stderr="err", exit_code=1),
        ]

        sessions = TmuxSessionExecutor.get_sessions_parallel(ssh_configs)

        assert len(sessions) == 1
        assert sessions[0].session_name == "s1"


# ---------------------------------------------------------------------------
# PSCommandExecutor
# ---------------------------------------------------------------------------


class TestPSCommandExecutor:
    def test_is_ssh_process_sshd(self):
        assert PSCommandExecutor._is_ssh_process("root 1234 0.0 sshd: azureuser@notty") is True

    def test_is_ssh_process_regular(self):
        assert PSCommandExecutor._is_ssh_process("azureuser 1234 0.0 python3 script.py") is False

    def test_is_ssh_process_header(self):
        assert PSCommandExecutor._is_ssh_process("USER PID %CPU") is False

    def test_filter_user_processes_basic(self):
        ps_output = (
            "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
            "azureuser  1234  0.0  0.1  12345  6789 pts/0   S+   12:00   0:00 python3 script.py\n"
            "azureuser  5678  0.0  0.2  23456  7890 pts/1   S+   12:01   0:00 node server.js\n"
            "root       9012  0.0  0.0   1234   567 ?       Ss   11:00   0:00 [kworker/0:0]\n"
            "azureuser  3456  0.0  0.0   1234   567 ?       Ss   11:00   0:00 sshd: azureuser@notty\n"
        )

        procs = PSCommandExecutor.filter_user_processes(ps_output)

        assert "python3" in procs
        assert "node" in procs
        assert len(procs) == 2

    def test_filter_user_processes_truncated_username(self):
        """ps aux truncates usernames to 8 chars + '+' (azureus+)."""
        ps_output = (
            "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
            "azureus+ 1234  0.0  0.1  12345  6789 pts/0   S+   12:00   0:00 python3 app.py\n"
        )

        procs = PSCommandExecutor.filter_user_processes(ps_output)
        assert "python3" in procs

    def test_filter_user_processes_max_five(self):
        lines = ["USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"]
        for i in range(10):
            lines.append(
                f"azureuser  {1000 + i}  0.0  0.1  12345  6789 pts/0   S+   12:00   0:00 proc{i} arg\n"
            )
        ps_output = "".join(lines)

        procs = PSCommandExecutor.filter_user_processes(ps_output)
        assert len(procs) == 5

    def test_format_ps_output_filters_ssh(self):
        results = [
            RemoteResult(
                vm_name="vm1",
                success=True,
                stdout="USER PID CMD\nazureuser 123 python3\nroot 456 sshd: azureuser@notty\n",
                stderr="",
                exit_code=0,
            )
        ]

        output = PSCommandExecutor.format_ps_output(results, filter_ssh=True)
        assert "python3" in output
        assert "sshd:" not in output


# ---------------------------------------------------------------------------
# WCommandExecutor
# ---------------------------------------------------------------------------


class TestWCommandExecutor:
    def test_format_w_output_with_session(self):
        results = [
            RemoteResult(
                vm_name="vm1",
                success=True,
                stdout="12:00 up 1 day",
                stderr="",
                exit_code=0,
                session_name="dev",
            ),
        ]

        output = WCommandExecutor.format_w_output(results)
        assert "vm1" in output
        assert "Session: dev" in output
        assert "12:00 up 1 day" in output

    def test_format_w_output_error(self):
        results = [
            RemoteResult(
                vm_name="vm2",
                success=False,
                stdout="",
                stderr="Connection refused",
                exit_code=255,
            ),
        ]

        output = WCommandExecutor.format_w_output(results)
        assert "ERROR: Connection refused" in output


# ---------------------------------------------------------------------------
# OSUpdateExecutor
# ---------------------------------------------------------------------------


class TestOSUpdateExecutor:
    @patch.object(RemoteExecutor, "execute_command")
    def test_execute_os_update_success(self, mock_exec, ssh_config):
        mock_exec.return_value = RemoteResult(
            vm_name="10.0.0.1",
            success=True,
            stdout="0 upgraded, 0 newly installed",
            stderr="",
            exit_code=0,
            duration=45.0,
        )

        result = OSUpdateExecutor.execute_os_update(ssh_config, timeout=300)
        assert result.success is True

        # Verify the command used
        mock_exec.assert_called_once_with(
            ssh_config, "sudo apt update && sudo apt upgrade -y", timeout=300
        )

    def test_format_output_success(self):
        r = RemoteResult(
            vm_name="vm1",
            success=True,
            stdout="5 upgraded, 2 newly installed",
            stderr="",
            exit_code=0,
            duration=120.5,
        )

        output = OSUpdateExecutor.format_output(r)
        assert "SUCCESS" in output
        assert "120.5s" in output
        assert "Update completed successfully" in output

    def test_format_output_failure(self):
        r = RemoteResult(
            vm_name="vm1",
            success=False,
            stdout="",
            stderr="E: Unable to lock",
            exit_code=100,
            duration=5.0,
        )

        output = OSUpdateExecutor.format_output(r)
        assert "FAILED" in output
        assert "E: Unable to lock" in output
