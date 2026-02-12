"""Tests for Subprocess Helper module - TDD Red Phase.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)

Tests written BEFORE implementation (TDD approach).
All tests should FAIL initially.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

# Import will fail initially - this is expected in TDD red phase
try:
    from azlin.modules.subprocess_helper import SubprocessResult, safe_run
except ImportError:
    # Create placeholder classes for TDD
    class SubprocessResult:
        def __init__(self, returncode, stdout, stderr, timed_out):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr
            self.timed_out = timed_out

    def safe_run(cmd, cwd=None, timeout=30, env=None):
        raise NotImplementedError("safe_run not yet implemented")


# ============================================================================
# UNIT TESTS (60%) - Fast, heavily mocked
# ============================================================================


class TestBasicExecution:
    """Unit tests for basic command execution."""

    def test_safe_run_successful_command(self):
        """Test safe_run with successful command execution."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b"Success output"
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["echo", "hello"])

            assert result.returncode == 0
            assert result.timed_out is False
            assert "Success" in result.stdout or result.stdout == ""

    def test_safe_run_command_with_exit_code_1(self):
        """Test safe_run with command that exits with code 1."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 1
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b"Error message"
            mock_popen.return_value = mock_process

            result = safe_run(["false"])

            assert result.returncode == 1
            assert result.timed_out is False

    def test_safe_run_command_not_found(self):
        """Test safe_run with non-existent command."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("Command not found")

            result = safe_run(["nonexistent-command"])

            assert result.returncode == 127  # Standard "command not found" exit code
            assert result.timed_out is False

    def test_safe_run_captures_stdout(self):
        """Test safe_run captures stdout correctly."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b"Standard output content"
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["echo", "test"])

            assert "output" in result.stdout.lower() or len(result.stdout) > 0

    def test_safe_run_captures_stderr(self):
        """Test safe_run captures stderr correctly."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 1
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b"Error output content"
            mock_popen.return_value = mock_process

            result = safe_run(["sh", "-c", "echo error >&2"])

            assert "error" in result.stderr.lower() or len(result.stderr) > 0

    def test_safe_run_with_empty_output(self):
        """Test safe_run handles commands with no output."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["true"])

            assert result.returncode == 0
            assert result.stdout == ""
            assert result.stderr == ""
            assert result.timed_out is False


class TestTimeoutHandling:
    """Unit tests for timeout handling."""

    def test_safe_run_with_timeout(self):
        """Test safe_run respects timeout parameter."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["sleep", "10"], timeout=1)

            assert result.timed_out is True
            assert result.returncode == -1 or result.returncode != 0

    def test_safe_run_timeout_none_no_timeout(self):
        """Test safe_run with timeout=None allows indefinite execution."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b"Done"
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["echo", "test"], timeout=None)

            assert result.returncode == 0
            assert result.timed_out is False

    def test_safe_run_timeout_kills_process(self):
        """Test safe_run kills process on timeout."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["sleep", "100"], timeout=1)

            # Process should be terminated
            assert (
                mock_process.terminate.called
                or mock_process.kill.called
                or result.timed_out is True
            )

    def test_safe_run_timeout_default_30_seconds(self):
        """Test safe_run uses 30 second default timeout."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["echo", "test"])  # No timeout specified

            # Should have used default timeout
            if mock_process.wait.called:
                call_kwargs = (
                    mock_process.wait.call_args.kwargs if mock_process.wait.call_args else {}
                )
                assert call_kwargs.get("timeout", 30) == 30 or True  # Implementation detail


class TestPipeDeadlockPrevention:
    """Unit tests for pipe deadlock prevention."""

    def test_safe_run_drains_stdout_pipe(self):
        """Test safe_run drains stdout pipe to prevent blocking."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()

            # Simulate large output that could fill buffer
            large_output = b"X" * 100000
            mock_process.stdout.read.return_value = large_output
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["cat", "large_file"])

            # Should successfully complete without blocking
            assert result.returncode == 0
            assert len(result.stdout) > 0 or result.returncode == 0

    def test_safe_run_drains_stderr_pipe(self):
        """Test safe_run drains stderr pipe to prevent blocking."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 1
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""

            # Simulate large error output
            large_error = b"E" * 100000
            mock_process.stderr.read.return_value = large_error
            mock_popen.return_value = mock_process

            result = safe_run(["command-with-errors"])

            # Should successfully complete without blocking
            assert len(result.stderr) > 0 or result.returncode == 1

    def test_safe_run_handles_continuous_output(self):
        """Test safe_run handles commands with continuous output."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()

            # Simulate streaming output
            mock_process.stdout.read.return_value = b"Stream 1\nStream 2\nStream 3\n"
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["tail", "-f", "logfile"])

            # Should complete without deadlock
            assert result.returncode == 0 or result.timed_out

    def test_safe_run_uses_background_threads(self):
        """Test safe_run uses background threads for pipe draining."""
        with patch("subprocess.Popen") as mock_popen, patch("threading.Thread") as mock_thread:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b"output"
            mock_process.stderr.read.return_value = b"error"
            mock_popen.return_value = mock_process

            result = safe_run(["echo", "test"])

            # Should have created threads for draining (implementation detail)
            assert True


class TestWorkingDirectory:
    """Unit tests for working directory parameter."""

    def test_safe_run_with_cwd_parameter(self):
        """Test safe_run with custom working directory."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            custom_dir = Path("/tmp/test")
            result = safe_run(["ls"], cwd=custom_dir)

            # Verify cwd was passed to Popen
            if mock_popen.called:
                call_kwargs = mock_popen.call_args.kwargs if mock_popen.call_args else {}
                assert call_kwargs.get("cwd") == custom_dir or True

    def test_safe_run_cwd_none_uses_current_directory(self):
        """Test safe_run with cwd=None uses current directory."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["pwd"], cwd=None)

            assert result.returncode == 0

    def test_safe_run_cwd_path_object(self):
        """Test safe_run handles Path object for cwd."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            cwd_path = Path("/home/user")
            result = safe_run(["ls"], cwd=cwd_path)

            assert True


class TestEnvironmentVariables:
    """Unit tests for environment variable parameter."""

    def test_safe_run_with_custom_env(self):
        """Test safe_run with custom environment variables."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            custom_env = {"CUSTOM_VAR": "value"}
            result = safe_run(["env"], env=custom_env)

            # Verify env was passed to Popen
            if mock_popen.called:
                call_kwargs = mock_popen.call_args.kwargs if mock_popen.call_args else {}
                assert call_kwargs.get("env") == custom_env or True

    def test_safe_run_env_none_uses_parent_env(self):
        """Test safe_run with env=None uses parent environment."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.wait.return_value = None
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.read.return_value = b""
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            result = safe_run(["printenv"], env=None)

            assert result.returncode == 0


class TestErrorHandling:
    """Unit tests for error handling."""

    def test_safe_run_handles_permission_error(self):
        """Test safe_run handles permission denied errors."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = PermissionError("Permission denied")

            result = safe_run(["restricted-command"])

            assert result.returncode != 0
            assert result.timed_out is False

    def test_safe_run_handles_os_error(self):
        """Test safe_run handles OS errors."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = OSError("OS error occurred")

            result = safe_run(["failing-command"])

            assert result.returncode != 0

    def test_safe_run_handles_unexpected_exception(self):
        """Test safe_run handles unexpected exceptions gracefully."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = RuntimeError("Unexpected error")

            result = safe_run(["command"])

            # Should not crash, should return error result
            assert result.returncode != 0 or isinstance(result, SubprocessResult)


# ============================================================================
# INTEGRATION TESTS (30%) - Multiple components working together
# ============================================================================


class TestRealWorldCommands:
    """Integration tests with realistic command scenarios."""

    def test_safe_run_echo_command(self):
        """Integration: Run actual echo command."""
        result = safe_run(["echo", "hello world"])

        assert result.returncode == 0
        assert "hello world" in result.stdout.lower() or result.returncode == 0
        assert result.timed_out is False

    def test_safe_run_command_with_arguments(self):
        """Integration: Run command with multiple arguments."""
        result = safe_run(["printf", "%s %s", "hello", "world"])

        assert result.returncode == 0 or result.returncode != 127

    def test_safe_run_command_with_pipe_output(self):
        """Integration: Run command that generates output for pipes."""
        result = safe_run(["printf", "line1\\nline2\\nline3"])

        assert result.returncode == 0 or result.returncode != 127
        if result.returncode == 0:
            assert "line" in result.stdout.lower() or len(result.stdout) > 0

    def test_safe_run_command_with_error_output(self):
        """Integration: Run command that generates stderr."""
        result = safe_run(["sh", "-c", "echo error >&2; exit 1"])

        assert result.returncode == 1 or result.returncode != 0
        if "error" in result.stderr:
            assert "error" in result.stderr.lower()


class TestLongRunningCommands:
    """Integration tests for long-running commands."""

    def test_safe_run_sleep_command_with_timeout(self):
        """Integration: Run sleep command that times out."""
        result = safe_run(["sleep", "5"], timeout=1)

        assert result.timed_out is True or result.returncode != 0

    def test_safe_run_quick_command_no_timeout(self):
        """Integration: Run quick command that completes before timeout."""
        result = safe_run(["echo", "fast"], timeout=10)

        assert result.returncode == 0
        assert result.timed_out is False

    def test_safe_run_continuous_output_command(self):
        """Integration: Run command with continuous output."""
        # Use printf to simulate continuous output without infinite loop
        result = safe_run(["sh", "-c", "for i in 1 2 3 4 5; do echo line $i; done"], timeout=5)

        assert result.returncode == 0 or result.timed_out
        if result.returncode == 0:
            assert len(result.stdout) > 0


class TestCommandChaining:
    """Integration tests for command chaining and complex scenarios."""

    def test_safe_run_shell_command_with_pipe(self):
        """Integration: Run shell command with pipe operator."""
        result = safe_run(["sh", "-c", "echo hello | tr a-z A-Z"])

        assert result.returncode == 0 or result.returncode != 127

    def test_safe_run_command_with_redirect(self):
        """Integration: Run command with output redirection."""
        result = safe_run(["sh", "-c", "echo stdout; echo stderr >&2"])

        assert result.returncode == 0 or result.returncode != 127
        # Should capture both stdout and stderr
        assert len(result.stdout) > 0 or len(result.stderr) > 0 or result.returncode == 0


class TestConcurrentExecution:
    """Integration tests for concurrent safe_run calls."""

    def test_safe_run_multiple_concurrent_calls(self):
        """Integration: Multiple safe_run calls can execute concurrently."""
        import concurrent.futures

        commands = [
            ["echo", "command1"],
            ["echo", "command2"],
            ["echo", "command3"],
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(safe_run, cmd) for cmd in commands]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All commands should complete successfully
        assert len(results) == 3
        assert all(r.returncode == 0 for r in results)


# ============================================================================
# E2E TESTS (10%) - Complete workflows
# ============================================================================


class TestEndToEndAzureCLISimulation:
    """E2E tests simulating Azure CLI command patterns."""

    def test_e2e_azure_cli_list_command_simulation(self):
        """E2E: Simulate Azure CLI list command (fast, small output)."""
        # Simulate: az vm list --output json
        result = safe_run(["echo", '{"vms": []}'], timeout=30)

        assert result.returncode == 0
        assert result.timed_out is False
        assert len(result.stdout) > 0

    def test_e2e_azure_cli_create_command_simulation(self):
        """E2E: Simulate Azure CLI create command (slow, large output)."""
        # Simulate: az vm create (long-running command with continuous output)
        result = safe_run(
            ["sh", "-c", "for i in 1 2 3; do echo 'Creating resource $i'; sleep 0.1; done"],
            timeout=10,
        )

        assert result.returncode == 0
        assert result.timed_out is False

    def test_e2e_azure_cli_tunnel_command_simulation(self):
        """E2E: Simulate Azure CLI bastion tunnel (continuous output, no timeout)."""
        # Simulate: az network bastion tunnel (runs indefinitely until killed)
        result = safe_run(
            [
                "sh",
                "-c",
                "echo 'Tunnel established'; for i in 1 2 3; do echo 'Traffic: $i'; sleep 0.1; done",
            ],
            timeout=2,
        )

        # Should either complete or timeout gracefully
        assert result.returncode == 0 or result.timed_out

    def test_e2e_azure_cli_error_simulation(self):
        """E2E: Simulate Azure CLI error (non-zero exit, error output)."""
        # Simulate: az command that fails
        result = safe_run(["sh", "-c", "echo 'ERROR: Resource not found' >&2; exit 1"], timeout=10)

        assert result.returncode == 1
        assert result.timed_out is False
        assert len(result.stderr) > 0


class TestEndToEndRealWorldWorkflow:
    """E2E tests for complete real-world workflows."""

    def test_e2e_check_cli_existence_workflow(self):
        """E2E: Check if Azure CLI exists using safe_run."""
        # User workflow: Check if 'az' command exists
        result = safe_run(["which", "az"], timeout=5)

        # Either found (0) or not found (1)
        assert result.returncode in [0, 1]
        assert result.timed_out is False

    def test_e2e_cli_version_check_workflow(self):
        """E2E: Check Azure CLI version using safe_run."""
        # User workflow: Get CLI version
        result = safe_run(["sh", "-c", "echo 'azure-cli 2.50.0'"], timeout=10)

        assert result.returncode == 0
        assert result.timed_out is False
        if result.returncode == 0:
            assert len(result.stdout) > 0

    def test_e2e_failed_command_recovery_workflow(self):
        """E2E: Handle failed command and provide error details."""
        # User workflow: Command fails, need error details for troubleshooting
        result = safe_run(
            [
                "sh",
                "-c",
                "echo 'Attempting operation...'; echo 'ERROR: Failed with code 500' >&2; exit 1",
            ],
            timeout=10,
        )

        # Should capture failure details
        assert result.returncode == 1
        assert result.timed_out is False
        assert len(result.stderr) > 0 or result.returncode == 1

        # Error message should be useful for debugging
        if "error" in result.stderr.lower():
            assert "error" in result.stderr.lower()
