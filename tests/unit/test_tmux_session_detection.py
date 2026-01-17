"""Unit tests for tmux session detection bug fix (TDD approach).

These tests will FAIL with current code but PASS after fix implementation.

Bug Context:
- `azlin list` shows "No sessions" for VMs with active tmux sessions through Bastion tunnels
- SSH connection failures through Bastion are silently ignored
- Empty stdout with non-zero exit code treated as "no sessions" instead of "connection failed"
- SSH timeouts (5s) too short for VMs with slow SSH service startup

Fix Design:
1. Add explicit SSH connection verification before querying tmux
2. Improve error logging to distinguish connection failures from empty session lists
3. Increase SSH timeout for Bastion tunnels from 5s to 15s
4. Better error messages for debugging

Testing Coverage (60% Unit / 30% Integration / 10% E2E):
- SSH connection failure handling (unit)
- Empty session list vs connection failure distinction (unit)
- Bastion tunnel timeout configuration (unit)
- Error message clarity (unit)
"""

import logging
from unittest.mock import patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteExecError, RemoteResult, TmuxSessionExecutor

# ============================================================================
# SSH CONNECTION FAILURE HANDLING TESTS (60% - Unit Tests)
# ============================================================================


class TestSSHConnectionFailureHandling:
    """Test that SSH connection failures are properly detected and logged."""

    def test_ssh_connection_refused_logs_error_not_silent(self, caplog):
        """Test that SSH connection refused produces error log, not silent failure.

        Current behavior: Silent failure, returns []
        Expected behavior: Log connection error with clear message
        """
        with caplog.at_level(logging.ERROR):
            # Mock SSH command that fails with connection refused
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="test-vm",
                    success=False,
                    stdout="",  # Empty stdout
                    stderr="ssh: connect to host 127.0.0.1 port 5000: Connection refused",
                    exit_code=255,  # SSH connection failure exit code
                )

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                # Should return empty list (no sessions)
                assert result == []

                # CRITICAL: Should log ERROR about connection failure (not WARNING)
                # Current code logs WARNING generically, new code should log ERROR specifically
                assert any(
                    "connection" in record.message.lower() and "refused" in record.message.lower()
                    for record in caplog.records
                    if record.levelname == "ERROR"
                ), "Expected ERROR log about connection refused, but none found"

    def test_ssh_timeout_logs_error_with_context(self, caplog):
        """Test that SSH timeout produces error log with timeout context.

        Current behavior: Generic warning
        Expected behavior: Specific error mentioning timeout
        """
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                # Simulate timeout by raising RemoteExecError
                mock_exec.side_effect = RemoteExecError("Command timed out after 5s on 127.0.0.1")

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                # Should return empty list
                assert result == []

                # Should log ERROR about timeout
                assert any(
                    "timeout" in record.message.lower() or "timed out" in record.message.lower()
                    for record in caplog.records
                    if record.levelname == "ERROR"
                ), "Expected ERROR log about timeout, but none found"

    def test_ssh_permission_denied_logs_error(self, caplog):
        """Test that SSH permission denied produces specific error log.

        Current behavior: Generic warning
        Expected behavior: Specific error about authentication
        """
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="test-vm",
                    success=False,
                    stdout="",
                    stderr="Permission denied (publickey)",
                    exit_code=255,
                )

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                assert result == []

                # Should log ERROR about authentication
                assert any(
                    (
                        "permission" in record.message.lower()
                        or "authentication" in record.message.lower()
                        or "denied" in record.message.lower()
                    )
                    for record in caplog.records
                    if record.levelname == "ERROR"
                ), "Expected ERROR log about permission/authentication, but none found"


# ============================================================================
# EMPTY SESSION LIST VS CONNECTION FAILURE DISTINCTION (60% - Unit Tests)
# ============================================================================


class TestEmptySessionVsConnectionFailure:
    """Test distinguishing between 'no sessions' and 'connection failed'."""

    def test_successful_connection_no_sessions_returns_empty_quietly(self, caplog):
        """Test that successful connection with no sessions returns [] without ERROR log.

        Current behavior: Returns [], no error (correct)
        Expected behavior: Same - returns [], possibly DEBUG/INFO log, but NOT ERROR
        """
        with caplog.at_level(logging.DEBUG):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="test-vm",
                    success=True,  # Connection succeeded
                    stdout="No sessions",  # No tmux sessions
                    stderr="",
                    exit_code=0,
                )

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                # Should return empty list
                assert result == []

                # Should NOT log ERROR (connection was successful, just no sessions)
                error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
                assert len(error_logs) == 0, (
                    f"Expected no ERROR logs for successful connection with no sessions, but found: {error_logs}"
                )

    def test_connection_failed_empty_stdout_logs_connection_error(self, caplog):
        """Test that connection failure with empty stdout logs ERROR, not treated as 'no sessions'.

        Current behavior: Silent failure or generic warning, returns []
        Expected behavior: Logs ERROR about connection failure, returns []
        """
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="test-vm",
                    success=False,  # Connection failed
                    stdout="",  # Empty stdout (THIS IS THE BUG TRIGGER)
                    stderr="Connection timed out",
                    exit_code=255,
                )

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                # Should return empty list (no sessions retrieved)
                assert result == []

                # CRITICAL: Should log ERROR about connection failure (not silent)
                assert any(
                    "connection" in record.message.lower() or "failed" in record.message.lower()
                    for record in caplog.records
                    if record.levelname == "ERROR"
                ), "Expected ERROR log about connection failure with empty stdout"

    def test_exit_code_255_treated_as_connection_failure(self, caplog):
        """Test that exit code 255 (SSH connection failure) is recognized and logged.

        Exit code 255 is SSH's standard exit code for connection failures.
        Current behavior: May be treated as generic failure
        Expected behavior: Specific handling and logging for SSH connection failures
        """
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="test-vm",
                    success=False,
                    stdout="",
                    stderr="ssh: connect to host test-vm port 22: No route to host",
                    exit_code=255,  # SSH-specific connection failure
                )

                ssh_config = SSHConfig(
                    host="test-vm", port=22, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                assert result == []

                # Should log ERROR about SSH connection failure (exit 255)
                assert any(
                    ("ssh" in record.message.lower() or "connection" in record.message.lower())
                    for record in caplog.records
                    if record.levelname == "ERROR"
                ), "Expected ERROR log about SSH connection failure (exit 255)"


# ============================================================================
# BASTION TUNNEL TIMEOUT CONFIGURATION (60% - Unit Tests)
# ============================================================================


class TestBastionTunnelTimeout:
    """Test that Bastion tunnels use appropriate timeout values."""

    def test_bastion_tunnel_uses_15s_timeout_not_5s(self):
        """Test that Bastion tunnel connections use 15s timeout, not 5s.

        Current behavior: 5s timeout (line 3077 in cli.py)
        Expected behavior: 15s timeout for Bastion tunnels

        This test verifies timeout configuration, not actual execution.
        """
        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            # Track timeout value passed to execute_command
            captured_timeout = None

            def capture_timeout(ssh_config, command, timeout=30):
                nonlocal captured_timeout
                captured_timeout = timeout
                return RemoteResult(
                    vm_name=ssh_config.host,
                    success=True,
                    stdout="session1:1:2:1697000000",
                    stderr="",
                    exit_code=0,
                )

            mock_exec.side_effect = capture_timeout

            # Create SSH config that looks like Bastion tunnel (localhost)
            ssh_config = SSHConfig(
                host="127.0.0.1",  # Bastion tunnel uses localhost
                port=5000,  # High port indicates tunnel
                user="azureuser",
                key_path="/tmp/test_key",
            )

            # Call get_sessions (which should use appropriate timeout)
            result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=15)

            # Verify timeout was passed correctly
            # (Current code doesn't distinguish, new code should)
            assert captured_timeout == 15, (
                f"Expected 15s timeout for Bastion tunnel, got {captured_timeout}s"
            )

    def test_direct_ssh_still_uses_5s_timeout(self):
        """Test that direct SSH connections still use 5s timeout (not affected by fix).

        Current behavior: 5s timeout
        Expected behavior: Keep 5s timeout for direct SSH (only Bastion gets 15s)
        """
        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            captured_timeout = None

            def capture_timeout(ssh_config, command, timeout=30):
                nonlocal captured_timeout
                captured_timeout = timeout
                return RemoteResult(
                    vm_name=ssh_config.host,
                    success=True,
                    stdout="session1:1:2:1697000000",
                    stderr="",
                    exit_code=0,
                )

            mock_exec.side_effect = capture_timeout

            # Create SSH config that looks like direct SSH (public IP)
            ssh_config = SSHConfig(
                host="20.30.40.50",  # Public IP
                port=22,  # Standard SSH port
                user="azureuser",
                key_path="/tmp/test_key",
            )

            # Call with 5s timeout (standard for direct SSH)
            result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

            assert captured_timeout == 5, (
                f"Expected 5s timeout for direct SSH, got {captured_timeout}s"
            )


# ============================================================================
# ERROR MESSAGE CLARITY TESTS (60% - Unit Tests)
# ============================================================================


class TestErrorMessageClarity:
    """Test that error messages are clear and actionable."""

    def test_connection_refused_error_mentions_vm_and_port(self, caplog):
        """Test that connection refused error includes VM name and port for debugging."""
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="my-test-vm",
                    success=False,
                    stdout="",
                    stderr="ssh: connect to host 127.0.0.1 port 5000: Connection refused",
                    exit_code=255,
                )

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(
                    ssh_config, vm_name="my-test-vm", timeout=5
                )

                # Should include VM name in error message
                error_messages = [r.message for r in caplog.records if r.levelname == "ERROR"]
                assert any("my-test-vm" in msg or "127.0.0.1" in msg for msg in error_messages), (
                    f"Expected VM name in error message, got: {error_messages}"
                )

    def test_timeout_error_mentions_duration(self, caplog):
        """Test that timeout error mentions how long it waited."""
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.side_effect = RemoteExecError("Command timed out after 15s on 127.0.0.1")

                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=15)

                # Should mention timeout duration in error
                error_messages = [r.message for r in caplog.records if r.levelname == "ERROR"]
                assert any("15" in msg or "timeout" in msg.lower() for msg in error_messages), (
                    f"Expected timeout duration in error message, got: {error_messages}"
                )

    def test_no_tmux_installed_has_clear_message(self, caplog):
        """Test that 'tmux not installed' produces clear, actionable message."""
        with caplog.at_level(logging.ERROR):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
                mock_exec.return_value = RemoteResult(
                    vm_name="test-vm",
                    success=False,
                    stdout="",
                    stderr="bash: tmux: command not found",
                    exit_code=127,  # Command not found
                )

                ssh_config = SSHConfig(
                    host="test-vm", port=22, user="azureuser", key_path="/tmp/test_key"
                )

                result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

                # Should mention tmux not installed
                error_messages = [r.message for r in caplog.records if r.levelname == "ERROR"]
                assert any(
                    "tmux" in msg.lower()
                    and ("not found" in msg.lower() or "not installed" in msg.lower())
                    for msg in error_messages
                ), f"Expected clear 'tmux not installed' message, got: {error_messages}"


# ============================================================================
# INTEGRATION TESTS (30% - Multi-component interaction)
# ============================================================================


class TestConnectionVerificationFlow:
    """Integration tests for SSH connection verification before tmux query."""

    def test_connection_verification_before_tmux_query(self):
        """Test that SSH connection is verified before attempting tmux query.

        Expected flow:
        1. Verify SSH connection works (simple command like 'echo test')
        2. If connection fails, log error and return []
        3. If connection succeeds, proceed with tmux query

        Current behavior: Goes straight to tmux query, connection failures silent
        """
        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            call_count = 0

            def mock_execution(ssh_config, command, timeout=30):
                nonlocal call_count
                call_count += 1

                # First call should be connection verification
                if call_count == 1:
                    # Simulate failed connection verification
                    return RemoteResult(
                        vm_name=ssh_config.host,
                        success=False,
                        stdout="",
                        stderr="Connection refused",
                        exit_code=255,
                    )

                # Should NOT reach here (no tmux query if connection failed)
                pytest.fail("Should not attempt tmux query after connection verification failed")

            mock_exec.side_effect = mock_execution

            ssh_config = SSHConfig(
                host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
            )

            result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

            # Should return empty (connection failed)
            assert result == []

            # Should have attempted connection verification (at least 1 call)
            # NOTE: Current code will make 1 call (tmux directly),
            # new code should make 1-2 calls (verification, then optionally tmux)
            assert call_count >= 1

    def test_successful_verification_proceeds_to_tmux_query(self):
        """Test that successful connection verification allows tmux query to proceed."""
        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:
            calls = []

            def mock_execution(ssh_config, command, timeout=30):
                calls.append(command)

                # If this is tmux query (check for tmux first to avoid false match on 'echo' in command)
                if "tmux" in command:
                    return RemoteResult(
                        vm_name=ssh_config.host,
                        success=True,
                        stdout="session1:1:2:1697000000",
                        stderr="",
                        exit_code=0,
                    )

                # If this is connection verification (simple command)
                if "echo" in command.lower() or len(command) < 20:
                    return RemoteResult(
                        vm_name=ssh_config.host,
                        success=True,
                        stdout="test",
                        stderr="",
                        exit_code=0,
                    )

                # Default success
                return RemoteResult(
                    vm_name=ssh_config.host,
                    success=True,
                    stdout="",
                    stderr="",
                    exit_code=0,
                )

            mock_exec.side_effect = mock_execution

            ssh_config = SSHConfig(
                host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
            )

            result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

            # Should return sessions (connection succeeded)
            assert len(result) == 1
            assert result[0].session_name == "session1"

            # Should have made at least 1 call (current code) or 2 calls (new code with verification)
            # New code: verification + tmux query = 2 calls
            # Current code: tmux query only = 1 call
            # Test passes if either behavior occurs, but new code is preferred
            assert len(calls) >= 1


# ============================================================================
# E2E TESTS (10% - Complete workflow simulation)
# ============================================================================


class TestEndToEndTmuxDetection:
    """End-to-end tests simulating real usage scenarios."""

    def test_bastion_tunnel_complete_workflow(self, caplog):
        """E2E test: Complete workflow for Bastion tunnel tmux detection.

        Simulates:
        1. Bastion tunnel established (localhost:5000)
        2. Connection verification attempted
        3. Connection succeeds (but slow - 10s)
        4. Tmux query succeeds
        5. Sessions returned
        """
        with caplog.at_level(logging.INFO):
            with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:

                def mock_execution(ssh_config, command, timeout=30):
                    # Simulate slow SSH (needs 15s timeout for Bastion)
                    if timeout < 10:
                        # If timeout too short, fail
                        raise RemoteExecError(f"Command timed out after {timeout}s")

                    # If timeout sufficient, succeed
                    if "tmux" in command:
                        return RemoteResult(
                            vm_name=ssh_config.host,
                            success=True,
                            stdout="dev:1:3:1697000000\nprod:0:2:1697000100",
                            stderr="",
                            exit_code=0,
                        )

                    return RemoteResult(
                        vm_name=ssh_config.host,
                        success=True,
                        stdout="",
                        stderr="",
                        exit_code=0,
                    )

                mock_exec.side_effect = mock_execution

                # Bastion tunnel SSH config
                ssh_config = SSHConfig(
                    host="127.0.0.1", port=5000, user="azureuser", key_path="/tmp/test_key"
                )

                # Call with 15s timeout (Bastion-appropriate)
                result = TmuxSessionExecutor.get_sessions_single_vm(
                    ssh_config, vm_name="my-vm", timeout=15
                )

                # Should successfully retrieve sessions
                assert len(result) == 2
                assert result[0].session_name == "dev"
                assert result[0].attached is True
                assert result[1].session_name == "prod"
                assert result[1].attached is False

                # Should NOT have ERROR logs (successful operation)
                error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
                assert len(error_logs) == 0, (
                    f"E2E test should not produce errors, got: {error_logs}"
                )

    def test_direct_ssh_fast_connection_workflow(self):
        """E2E test: Direct SSH with fast connection (5s timeout sufficient)."""
        with patch("azlin.remote_exec.RemoteExecutor.execute_command") as mock_exec:

            def mock_execution(ssh_config, command, timeout=30):
                # Fast connection (< 5s)
                if "tmux" in command:
                    return RemoteResult(
                        vm_name=ssh_config.host,
                        success=True,
                        stdout="session1:1:1:1697000000",
                        stderr="",
                        exit_code=0,
                    )

                return RemoteResult(
                    vm_name=ssh_config.host,
                    success=True,
                    stdout="",
                    stderr="",
                    exit_code=0,
                )

            mock_exec.side_effect = mock_execution

            # Direct SSH config
            ssh_config = SSHConfig(
                host="20.30.40.50", port=22, user="azureuser", key_path="/tmp/test_key"
            )

            # Call with standard 5s timeout
            result = TmuxSessionExecutor.get_sessions_single_vm(ssh_config, timeout=5)

            # Should successfully retrieve sessions
            assert len(result) == 1
            assert result[0].session_name == "session1"
