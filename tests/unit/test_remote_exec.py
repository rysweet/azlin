"""Unit tests for remote_exec module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_routing_resolver import SSHRoute
from azlin.remote_exec import (
    RemoteExecutor,
    RemoteResult,
    TmuxSession,
    TmuxSessionExecutor,
    WCommandExecutor,
)
from azlin.vm_manager import VMInfo


class TestRemoteResult:
    """Tests for RemoteResult dataclass."""

    def test_get_output_both(self):
        """Test getting combined output."""
        result = RemoteResult(
            vm_name="test-vm", success=True, stdout="stdout text", stderr="stderr text", exit_code=0
        )
        output = result.get_output()
        assert "stdout text" in output
        assert "stderr text" in output

    def test_get_output_stdout_only(self):
        """Test getting stdout only."""
        result = RemoteResult(
            vm_name="test-vm", success=True, stdout="stdout text", stderr="", exit_code=0
        )
        output = result.get_output()
        assert output == "stdout text"

    def test_get_output_stderr_only(self):
        """Test getting stderr only."""
        result = RemoteResult(
            vm_name="test-vm", success=False, stdout="", stderr="error message", exit_code=1
        )
        output = result.get_output()
        assert output == "error message"


class TestRemoteExecutor:
    """Tests for RemoteExecutor class."""

    @patch("azlin.remote_exec.subprocess.run")
    def test_execute_command_success(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="command output", stderr="")

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        result = RemoteExecutor.execute_command(ssh_config, "ls -la", timeout=30)

        assert result.success is True
        assert result.stdout == "command output"
        assert result.exit_code == 0

    @patch("azlin.remote_exec.subprocess.run")
    def test_execute_command_failure(self, mock_run):
        """Test failed command execution."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="command not found")

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

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
        assert slug == "python-train-py-epoc"  # 3 words, truncated to 20 chars

        slug2 = RemoteExecutor.extract_command_slug("ls -la /tmp/file")
        assert slug2 == "ls-la-tmp-file"  # 3 words

    def test_extract_command_slug_max_length(self):
        """Test slug truncation."""
        slug = RemoteExecutor.extract_command_slug(
            "very-long-command-name-that-exceeds-limit", max_length=10
        )
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

    @patch("azlin.remote_exec.RemoteExecutor.execute_parallel")
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


@pytest.mark.unit
class TestWCommandExecutorRoutes:
    """Tests for WCommandExecutor.execute_w_on_routes method."""

    def _create_vm_info(self, name: str, session_name: str | None = None) -> VMInfo:
        """Helper to create VMInfo for testing."""
        return VMInfo(
            name=name,
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            session_name=session_name,
        )

    def _create_ssh_config(self, host: str) -> SSHConfig:
        """Helper to create SSHConfig for testing."""
        return SSHConfig(host=host, user="azureuser", key_path=Path("/tmp/key"))

    def _create_route(
        self,
        vm_name: str,
        session_name: str | None = None,
        ssh_config: SSHConfig | None = None,
        routing_method: str = "direct",
    ) -> SSHRoute:
        """Helper to create SSHRoute for testing."""
        vm_info = self._create_vm_info(vm_name, session_name)
        return SSHRoute(
            vm_name=vm_name,
            vm_info=vm_info,
            ssh_config=ssh_config,
            routing_method=routing_method,  # type: ignore[arg-type]
        )

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_basic_success(self, mock_execute):
        """Test basic execution on routes with vm_name and session_name."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp-name",  # Will be overridden
            success=True,
            stdout="w output from vm",
            stderr="",
            exit_code=0,
        )

        routes = [
            self._create_route(
                vm_name="test-vm-1",
                session_name="session-a",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 1
        assert results[0].vm_name == "test-vm-1"
        assert results[0].session_name == "session-a"
        assert results[0].success is True
        assert results[0].stdout == "w output from vm"
        mock_execute.assert_called_once()

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_skip_unreachable(self, mock_execute):
        """Test that routes with ssh_config=None are skipped."""
        # Arrange
        routes = [
            self._create_route(
                vm_name="reachable-vm",
                session_name="session-1",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
            self._create_route(
                vm_name="unreachable-vm",
                session_name="session-2",
                ssh_config=None,  # Unreachable
                routing_method="unreachable",
            ),
        ]

        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 1
        assert results[0].vm_name == "reachable-vm"
        # Should only call execute_command once (not for unreachable VM)
        mock_execute.assert_called_once()

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_multiple_vms_parallel(self, mock_execute):
        """Test parallel execution on multiple VMs."""
        # Arrange
        routes = [
            self._create_route(
                vm_name=f"vm-{i}",
                session_name=f"session-{i}",
                ssh_config=self._create_ssh_config(f"10.0.0.{i}"),
            )
            for i in range(1, 4)
        ]

        def execute_side_effect(ssh_config, command, timeout):
            """Return different output based on host."""
            return RemoteResult(
                vm_name="temp",
                success=True,
                stdout=f"output from {ssh_config.host}",
                stderr="",
                exit_code=0,
            )

        mock_execute.side_effect = execute_side_effect

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 3
        assert mock_execute.call_count == 3

        # Verify all VMs got their names set correctly
        vm_names = {r.vm_name for r in results}
        assert vm_names == {"vm-1", "vm-2", "vm-3"}

        # Verify all sessions got their names set correctly
        session_names = {r.session_name for r in results}
        assert session_names == {"session-1", "session-2", "session-3"}

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_session_name_none(self, mock_execute):
        """Test handling when session_name is None."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        routes = [
            self._create_route(
                vm_name="test-vm",
                session_name=None,  # No session name
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 1
        assert results[0].vm_name == "test-vm"
        assert results[0].session_name is None

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_execution_error(self, mock_execute):
        """Test error handling when execution fails."""
        # Arrange
        mock_execute.side_effect = Exception("Connection timeout")

        routes = [
            self._create_route(
                vm_name="failing-vm",
                session_name="session-x",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].vm_name == "failing-vm"
        assert results[0].session_name == "session-x"
        assert "Connection timeout" in results[0].stderr
        assert results[0].exit_code == -1
        assert results[0].stdout == ""

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_mixed_success_failure(self, mock_execute):
        """Test handling mixed success and failure results."""
        # Arrange
        routes = [
            self._create_route(
                vm_name="success-vm",
                session_name="session-ok",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
            self._create_route(
                vm_name="failure-vm",
                session_name="session-fail",
                ssh_config=self._create_ssh_config("5.6.7.8"),
            ),
        ]

        def execute_side_effect(ssh_config, command, timeout):
            """Fail for specific host."""
            if ssh_config.host == "5.6.7.8":
                raise Exception("Connection refused")
            return RemoteResult(
                vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
            )

        mock_execute.side_effect = execute_side_effect

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 2

        success_results = [r for r in results if r.success]
        failure_results = [r for r in results if not r.success]

        assert len(success_results) == 1
        assert len(failure_results) == 1

        assert success_results[0].vm_name == "success-vm"
        assert success_results[0].session_name == "session-ok"

        assert failure_results[0].vm_name == "failure-vm"
        assert failure_results[0].session_name == "session-fail"
        assert "Connection refused" in failure_results[0].stderr

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_empty_list(self, mock_execute):
        """Test handling empty routes list."""
        # Act
        results = WCommandExecutor.execute_w_on_routes([])

        # Assert
        assert results == []
        mock_execute.assert_not_called()

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_all_unreachable(self, mock_execute):
        """Test when all routes are unreachable."""
        # Arrange
        routes = [
            self._create_route(
                vm_name="unreachable-1",
                session_name="session-1",
                ssh_config=None,
                routing_method="unreachable",
            ),
            self._create_route(
                vm_name="unreachable-2",
                session_name="session-2",
                ssh_config=None,
                routing_method="unreachable",
            ),
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert results == []
        mock_execute.assert_not_called()

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_custom_timeout(self, mock_execute):
        """Test custom timeout is passed through."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        routes = [
            self._create_route(
                vm_name="test-vm",
                session_name="session-1",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        WCommandExecutor.execute_w_on_routes(routes, timeout=60)

        # Assert
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][1] == "w"  # Command
        assert call_args[0][2] == 60  # Timeout

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_custom_max_workers(self, mock_execute):
        """Test custom max_workers parameter."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        # Create many routes to test worker limitation
        routes = [
            self._create_route(
                vm_name=f"vm-{i}",
                session_name=f"session-{i}",
                ssh_config=self._create_ssh_config(f"10.0.0.{i}"),
            )
            for i in range(1, 21)  # 20 VMs
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes, max_workers=5)

        # Assert
        assert len(results) == 20
        assert mock_execute.call_count == 20

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_preserves_route_metadata(self, mock_execute):
        """Test that route metadata is preserved in results."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="wrong-name",  # Should be overridden
            success=True,
            stdout="w output",
            stderr="",
            exit_code=0,
            session_name="wrong-session",  # Should be overridden
        )

        routes = [
            self._create_route(
                vm_name="correct-vm-name",
                session_name="correct-session-name",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        assert len(results) == 1
        # Verify route metadata overrides RemoteResult values
        assert results[0].vm_name == "correct-vm-name"
        assert results[0].session_name == "correct-session-name"

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_command_is_w(self, mock_execute):
        """Test that the 'w' command is executed."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        routes = [
            self._create_route(
                vm_name="test-vm",
                session_name="session-1",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        WCommandExecutor.execute_w_on_routes(routes)

        # Assert
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][1] == "w"  # Verify command is 'w'

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_default_timeout(self, mock_execute):
        """Test default timeout value."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        routes = [
            self._create_route(
                vm_name="test-vm",
                session_name="session-1",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        WCommandExecutor.execute_w_on_routes(routes)  # No timeout specified

        # Assert
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][2] == 30  # Default timeout

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_execute_w_on_routes_single_vm_uses_one_worker(self, mock_execute):
        """Test that single VM uses min(1, max_workers) workers."""
        # Arrange
        mock_execute.return_value = RemoteResult(
            vm_name="temp", success=True, stdout="w output", stderr="", exit_code=0
        )

        routes = [
            self._create_route(
                vm_name="test-vm",
                session_name="session-1",
                ssh_config=self._create_ssh_config("1.2.3.4"),
            ),
        ]

        # Act
        results = WCommandExecutor.execute_w_on_routes(routes, max_workers=10)

        # Assert
        assert len(results) == 1
        mock_execute.assert_called_once()


@pytest.mark.unit
class TestTmuxSessionInfo:
    """Tests for TmuxSession dataclass."""

    def test_tmux_session_info_creation(self):
        """Test creating TmuxSession with all fields."""
        session = TmuxSession(
            vm_name="test-vm",
            session_name="dev",
            windows=3,
            created_time="Thu Oct 10 10:00:00 2024",
        )

        assert session.vm_name == "test-vm"
        assert session.session_name == "dev"
        assert session.windows == 3
        assert session.created_time == "Thu Oct 10 10:00:00 2024"

    def test_tmux_session_info_minimal(self):
        """Test creating TmuxSession with minimal fields."""
        session = TmuxSession(
            vm_name="test-vm",
            session_name="dev",
            windows=1,
            created_time="",  # Required field
        )

        assert session.vm_name == "test-vm"
        assert session.session_name == "dev"
        assert session.windows == 1
        assert session.created_time == ""

    def test_tmux_session_info_zero_windows(self):
        """Test handling zero windows (edge case)."""
        session = TmuxSession(
            vm_name="test-vm",
            session_name="dev",
            windows=0,
            created_time="",  # Required field
        )

        assert session.windows == 0


@pytest.mark.unit
class TestTmuxSessionExecutorSingleVM:
    """Tests for TmuxSessionExecutor on single VM."""

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_success(self, mock_execute):
        """Test successfully getting tmux sessions from single VM."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="dev: 3 windows (created Thu Oct 10 10:00:00 2024)",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].vm_name == "test-vm"
        assert sessions[0].session_name == "dev"
        assert sessions[0].windows == 3

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_multiple_sessions(self, mock_execute):
        """Test getting multiple tmux sessions from single VM."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="dev: 3 windows (created Thu Oct 10 10:00:00 2024)\n"
            "prod: 1 window (created Thu Oct 10 11:00:00 2024)\n"
            "test: 2 windows (created Thu Oct 10 12:00:00 2024)",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 3
        assert sessions[0].session_name == "dev"
        assert sessions[1].session_name == "prod"
        assert sessions[2].session_name == "test"

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_no_sessions(self, mock_execute):
        """Test VM with no tmux sessions."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=False,
            stdout="",
            stderr="no server running",
            exit_code=1,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 0

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_tmux_not_installed(self, mock_execute):
        """Test VM without tmux installed."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=False,
            stdout="",
            stderr="command not found: tmux",
            exit_code=127,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 0

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_timeout(self, mock_execute):
        """Test handling timeout when querying tmux sessions."""
        mock_execute.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=5)

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 0

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_connection_failed(self, mock_execute):
        """Test handling connection failure."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=False,
            stdout="",
            stderr="ssh: connect to host 1.2.3.4 port 22: Connection refused",
            exit_code=255,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 0

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_single_vm_custom_timeout(self, mock_execute):
        """Test using custom timeout value."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="dev: 1 window",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm", timeout=10)

        # Verify execute_command was called with correct timeout
        mock_execute.assert_called_once()
        assert mock_execute.call_args[1]["timeout"] == 10


@pytest.mark.unit
class TestTmuxSessionExecutorParallel:
    """Tests for TmuxSessionExecutor parallel execution."""

    @patch("azlin.remote_exec.RemoteExecutor.execute_parallel")
    def test_get_sessions_parallel_multiple_vms(self, mock_execute):
        """Test getting sessions from multiple VMs in parallel."""
        mock_execute.return_value = [
            RemoteResult(
                "vm-1",
                True,
                "dev: 3 windows (created Thu Oct 10 10:00:00 2024)",
                "",
                0,
            ),
            RemoteResult(
                "vm-2",
                True,
                "prod: 1 window (created Thu Oct 10 11:00:00 2024)",
                "",
                0,
            ),
            RemoteResult(
                "vm-3",
                True,
                "test: 2 windows (created Thu Oct 10 12:00:00 2024)",
                "",
                0,
            ),
        ]

        ssh_configs = [
            SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="5.6.7.8", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="9.10.11.12", user="azureuser", key_path=Path("/tmp/key")),
        ]

        sessions = TmuxSessionExecutor.get_sessions_parallel(ssh_configs)

        assert len(sessions) == 3
        assert sessions[0].vm_name == "vm-1"
        assert sessions[0].session_name == "dev"
        assert sessions[1].vm_name == "vm-2"
        assert sessions[1].session_name == "prod"
        assert sessions[2].vm_name == "vm-3"
        assert sessions[2].session_name == "test"

    @patch("azlin.remote_exec.RemoteExecutor.execute_parallel")
    def test_get_sessions_parallel_mixed_results(self, mock_execute):
        """Test parallel execution with mixed success/failure."""
        mock_execute.return_value = [
            RemoteResult("vm-1", True, "dev: 1 window", "", 0),
            RemoteResult("vm-2", False, "", "no server running", 1),
            RemoteResult("vm-3", True, "prod: 2 windows", "", 0),
        ]

        ssh_configs = [
            SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="5.6.7.8", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="9.10.11.12", user="azureuser", key_path=Path("/tmp/key")),
        ]

        sessions = TmuxSessionExecutor.get_sessions_parallel(ssh_configs)

        # Should only return successful sessions
        assert len(sessions) == 2
        assert sessions[0].vm_name == "vm-1"
        assert sessions[1].vm_name == "vm-3"

    @patch("azlin.remote_exec.RemoteExecutor.execute_parallel")
    def test_get_sessions_parallel_all_failed(self, mock_execute):
        """Test parallel execution where all VMs fail."""
        mock_execute.return_value = [
            RemoteResult("vm-1", False, "", "connection refused", 255),
            RemoteResult("vm-2", False, "", "connection timeout", 255),
            RemoteResult("vm-3", False, "", "host unreachable", 255),
        ]

        ssh_configs = [
            SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="5.6.7.8", user="azureuser", key_path=Path("/tmp/key")),
            SSHConfig(host="9.10.11.12", user="azureuser", key_path=Path("/tmp/key")),
        ]

        sessions = TmuxSessionExecutor.get_sessions_parallel(ssh_configs)

        assert len(sessions) == 0

    @patch("azlin.remote_exec.RemoteExecutor.execute_parallel")
    def test_get_sessions_parallel_empty_configs(self, mock_execute):
        """Test parallel execution with empty SSH configs list."""
        mock_execute.return_value = []

        sessions = TmuxSessionExecutor.get_sessions_parallel([])

        assert len(sessions) == 0

    @patch("azlin.remote_exec.RemoteExecutor.execute_parallel")
    def test_get_sessions_parallel_single_config(self, mock_execute):
        """Test parallel execution with single SSH config."""
        mock_execute.return_value = [
            RemoteResult("vm-1", True, "dev: 1 window", "", 0),
        ]

        ssh_configs = [
            SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key")),
        ]

        sessions = TmuxSessionExecutor.get_sessions_parallel(ssh_configs)

        assert len(sessions) == 1
        assert sessions[0].vm_name == "vm-1"


@pytest.mark.unit
class TestTmuxSessionExecutorParsing:
    """Tests for tmux output parsing."""

    def test_parse_tmux_output_single_session(self):
        """Test parsing single tmux session."""
        output = "dev: 3 windows (created Thu Oct 10 10:00:00 2024)"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].session_name == "dev"
        assert sessions[0].windows == 3
        assert "Thu Oct 10" in sessions[0].created_time

    def test_parse_tmux_output_multiple_sessions(self):
        """Test parsing multiple tmux sessions."""
        output = (
            "dev: 3 windows (created Thu Oct 10 10:00:00 2024)\n"
            "prod: 1 window (created Thu Oct 10 11:00:00 2024)\n"
            "test: 5 windows (created Thu Oct 10 12:00:00 2024)"
        )

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        assert len(sessions) == 3
        assert sessions[0].windows == 3
        assert sessions[1].windows == 1
        assert sessions[2].windows == 5

    def test_parse_tmux_output_empty(self):
        """Test parsing empty output."""
        sessions = TmuxSessionExecutor.parse_tmux_output("", vm_name="test-vm")

        assert len(sessions) == 0

    def test_parse_tmux_output_malformed_line(self):
        """Test parsing with malformed line (should skip)."""
        output = (
            "dev: 3 windows (created Thu Oct 10 10:00:00 2024)\n"
            "malformed line without proper format\n"
            "prod: 1 window (created Thu Oct 10 11:00:00 2024)"
        )

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        # Should skip malformed line
        assert len(sessions) == 2
        assert sessions[0].session_name == "dev"
        assert sessions[1].session_name == "prod"

    def test_parse_tmux_output_single_window(self):
        """Test parsing session with 1 window (singular)."""
        output = "dev: 1 window (created Thu Oct 10 10:00:00 2024)"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].windows == 1

    def test_parse_tmux_output_no_created_time(self):
        """Test parsing output without created time."""
        output = "dev: 3 windows"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].session_name == "dev"
        assert sessions[0].windows == 3

    def test_parse_tmux_output_special_characters_in_name(self):
        """Test parsing session name with special characters."""
        output = "my-dev-session_v2: 2 windows (created Thu Oct 10 10:00:00 2024)"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].session_name == "my-dev-session_v2"

    def test_parse_tmux_output_whitespace_variations(self):
        """Test parsing with various whitespace."""
        output = "  dev:   3   windows   (created Thu Oct 10 10:00:00 2024)  "

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].session_name.strip() in ["dev", "  dev"]


@pytest.mark.unit
class TestTmuxSessionExecutorFormatting:
    """Tests for tmux session display formatting."""

    def test_format_sessions_display_single_vm(self):
        """Test formatting sessions for single VM."""
        sessions = [
            TmuxSession(
                vm_name="test-vm",
                session_name="dev",
                windows=3,
                created_time="Thu Oct 10 10:00:00 2024",
            ),
            TmuxSession(
                vm_name="test-vm",
                session_name="prod",
                windows=1,
                created_time="Thu Oct 10 11:00:00 2024",
            ),
        ]

        display = TmuxSessionExecutor.format_sessions_display(sessions)

        assert "test-vm" in display
        assert "dev" in display
        assert "prod" in display
        assert "3 windows" in display or "3" in display
        assert "1 window" in display or "1" in display

    def test_format_sessions_display_multiple_vms(self):
        """Test formatting sessions across multiple VMs."""
        sessions = [
            TmuxSession(vm_name="vm-1", session_name="dev", windows=2, created_time=""),
            TmuxSession(vm_name="vm-2", session_name="prod", windows=1, created_time=""),
            TmuxSession(vm_name="vm-3", session_name="test", windows=5, created_time=""),
        ]

        display = TmuxSessionExecutor.format_sessions_display(sessions)

        assert "vm-1" in display
        assert "vm-2" in display
        assert "vm-3" in display

    def test_format_sessions_display_empty(self):
        """Test formatting empty sessions list."""
        display = TmuxSessionExecutor.format_sessions_display([])

        assert "no sessions" in display.lower() or display == ""

    def test_format_sessions_display_no_created_time(self):
        """Test formatting sessions without created time."""
        sessions = [
            TmuxSession(vm_name="test-vm", session_name="dev", windows=1, created_time=""),
        ]

        display = TmuxSessionExecutor.format_sessions_display(sessions)

        # Should still display without error
        assert "dev" in display


@pytest.mark.unit
class TestTmuxSessionExecutorEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_with_unicode_output(self, mock_execute):
        """Test handling unicode characters in tmux output."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="dev-μπορεί: 1 window (created Thu Oct 10 10:00:00 2024)",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 1

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_very_large_window_count(self, mock_execute):
        """Test handling very large window count."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="dev: 999 windows (created Thu Oct 10 10:00:00 2024)",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        sessions = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, vm_name="test-vm")

        assert len(sessions) == 1
        assert sessions[0].windows == 999

    @patch("azlin.remote_exec.RemoteExecutor.execute_command")
    def test_get_sessions_zero_timeout(self, mock_execute):
        """Test with zero timeout (should use default)."""
        mock_execute.return_value = RemoteResult(
            vm_name="test-vm",
            success=True,
            stdout="dev: 1 window",
            stderr="",
            exit_code=0,
        )

        ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/tmp/key"))

        # Should handle gracefully
        sessions = TmuxSessionExecutor.get_sessions_single_vm(
            ssh_config, vm_name="test-vm", timeout=0
        )

        assert len(sessions) == 1

    def test_parse_tmux_output_line_with_only_colon(self):
        """Test parsing line with only colon (edge case)."""
        output = ":"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, vm_name="test-vm")

        # Should handle gracefully without crashing
        assert isinstance(sessions, list)
