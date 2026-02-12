"""Unit tests for Executor tmux functionality."""

import os
import unittest
from unittest.mock import Mock, patch

import pytest

from ..errors import ExecutionError
from ..executor import Executor
from ..orchestrator import VM


class TestExecutorTmux(unittest.TestCase):
    """Test cases for Executor tmux methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.vm = VM(name="test-vm", size="Standard_D2s_v3", region="eastus")
        self.executor = Executor(vm=self.vm, timeout_minutes=60)
        self.test_session_id = "test-session-123"
        self.test_command = "auto"
        self.test_prompt = "Fix the bug in main.py"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})  # pragma: allowlist secret
    @patch("subprocess.run")
    def test_execute_remote_tmux_success(self, mock_run):
        """Test successful tmux session creation."""
        mock_run.return_value = Mock(
            returncode=0, stdout="Tmux session test-session-123 started successfully\n", stderr=""
        )

        result = self.executor.execute_remote_tmux(
            session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
        )

        assert result
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "azlin"
        assert call_args[1] == "connect"
        assert call_args[2] == "test-vm"

        # Verify tmux commands in script
        script = call_args[3]
        assert "tmux new-session -d -s test-session-123" in script
        assert "tmux send-keys -t test-session-123" in script
        assert "amplihack claude --auto --max-turns 10" in script
        # Prompt is base64 encoded for security
        assert "Rml4IHRoZSBidWcgaW4gbWFpbi5weQ==" in script

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_with_max_turns(self, mock_run):
        """Test tmux session with custom max_turns."""
        mock_run.return_value = Mock(returncode=0, stdout="Session started\n", stderr="")

        self.executor.execute_remote_tmux(
            session_id=self.test_session_id,
            command="ultrathink",
            prompt=self.test_prompt,
            max_turns=20,
        )

        script = mock_run.call_args[0][0][3]
        assert "--ultrathink --max-turns 20" in script

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_with_api_key_param(self, mock_run):
        """Test tmux session with API key parameter."""
        mock_run.return_value = Mock(returncode=0, stdout="Session started\n", stderr="")

        self.executor.execute_remote_tmux(
            session_id=self.test_session_id,
            command=self.test_command,
            prompt=self.test_prompt,
            api_key="custom-key",  # pragma: allowlist secret
        )

        script = mock_run.call_args[0][0][3]
        # API key is base64 encoded for security
        assert "Y3VzdG9tLWtleQ==" in script

    @patch.dict(os.environ, {}, clear=True)
    def test_execute_remote_tmux_no_api_key(self):
        """Test error when API key not provided."""
        with pytest.raises(ExecutionError) as ctx:
            self.executor.execute_remote_tmux(
                session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
            )

        assert "ANTHROPIC_API_KEY not found" in str(ctx.value)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})  # pragma: allowlist secret
    def test_execute_remote_tmux_invalid_session_id(self):
        """Test error with invalid session ID."""
        invalid_ids = [
            "",  # Empty
            "session with spaces",  # Spaces
            "session/with/slashes",  # Slashes
            "session;dangerous",  # Semicolon
            "session$var",  # Shell variable
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ExecutionError) as ctx:
                self.executor.execute_remote_tmux(
                    session_id=invalid_id, command=self.test_command, prompt=self.test_prompt
                )
            assert "Invalid session_id" in str(ctx.value)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_execute_remote_tmux_valid_session_ids(self):
        """Test various valid session ID formats."""
        valid_ids = [
            "session123",
            "test-session",
            "session-with-many-dashes",
            "SessionWithCaps",
            "s123",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="Started\n", stderr="")

            for valid_id in valid_ids:
                result = self.executor.execute_remote_tmux(
                    session_id=valid_id, command=self.test_command, prompt=self.test_prompt
                )
                assert result

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_setup_failure(self, mock_run):
        """Test error when tmux setup fails."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="tmux: command not found\n")

        with pytest.raises(ExecutionError) as ctx:
            self.executor.execute_remote_tmux(
                session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
            )

        assert "Failed to start tmux session" in str(ctx.value)
        assert "tmux: command not found" in str(ctx.value)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_timeout(self, mock_run):
        """Test timeout during tmux setup."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("azlin connect", 600)

        with pytest.raises(ExecutionError) as ctx:
            self.executor.execute_remote_tmux(
                session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
            )

        assert "Tmux session setup timed out" in str(ctx.value)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_prompt_escaping(self, mock_run):
        """Test prompt with special characters is properly escaped."""
        mock_run.return_value = Mock(returncode=0, stdout="Started\n", stderr="")

        dangerous_prompt = "Fix the 'bug' with `command` and $variable"
        self.executor.execute_remote_tmux(
            session_id=self.test_session_id, command=self.test_command, prompt=dangerous_prompt
        )

        script = mock_run.call_args[0][0][3]
        # Prompt is base64 encoded, so special characters don't need escaping
        # Base64 encoding of: Fix the 'bug' with `command` and $variable
        assert (
            "Rml4IHRoZSAnYnVnJyB3aXRoIGBjb21tYW5kYCBhbmQgJHZhcmlhYmxl" in script
        )  # pragma: allowlist secret

    @patch("subprocess.run")
    def test_check_tmux_status_running(self, mock_run):
        """Test checking status of running tmux session."""
        mock_run.return_value = Mock(returncode=0, stdout="running\n", stderr="")

        status = self.executor.check_tmux_status(self.test_session_id)

        assert status == "running"
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "tmux has-session -t test-session-123" in call_args[3]

    @patch("subprocess.run")
    def test_check_tmux_status_completed(self, mock_run):
        """Test checking status of completed tmux session."""
        mock_run.return_value = Mock(returncode=0, stdout="completed\n", stderr="")

        status = self.executor.check_tmux_status(self.test_session_id)

        assert status == "completed"

    @patch("subprocess.run")
    def test_check_tmux_status_unexpected_output(self, mock_run):
        """Test handling unexpected output from status check."""
        mock_run.return_value = Mock(returncode=0, stdout="unknown\n", stderr="")

        status = self.executor.check_tmux_status(self.test_session_id)

        # Unexpected output should be treated as completed
        assert status == "completed"

    def test_check_tmux_status_invalid_session_id(self):
        """Test error with invalid session ID in status check."""
        invalid_ids = ["", "session with spaces", "session/path", "session;cmd"]

        for invalid_id in invalid_ids:
            with pytest.raises(ExecutionError) as ctx:
                self.executor.check_tmux_status(invalid_id)
            assert "Invalid session_id" in str(ctx.value)

    @patch("subprocess.run")
    def test_check_tmux_status_timeout(self, mock_run):
        """Test timeout during status check."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("azlin connect", 30)

        with pytest.raises(ExecutionError) as ctx:
            self.executor.check_tmux_status(self.test_session_id)

        assert "Tmux status check timed out" in str(ctx.value)

    @patch("subprocess.run")
    def test_check_tmux_status_connection_error(self, mock_run):
        """Test error during status check connection."""
        mock_run.side_effect = Exception("Connection failed")

        with pytest.raises(ExecutionError) as ctx:
            self.executor.check_tmux_status(self.test_session_id)

        assert "Failed to check tmux status" in str(ctx.value)
        assert "Connection failed" in str(ctx.value)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_includes_tmux_installation(self, mock_run):
        """Test that setup script includes tmux installation."""
        mock_run.return_value = Mock(returncode=0, stdout="Started\n", stderr="")

        self.executor.execute_remote_tmux(
            session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
        )

        script = mock_run.call_args[0][0][3]
        assert "if ! command -v tmux" in script
        assert "sudo apt-get install -y -qq tmux" in script

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_workspace_setup(self, mock_run):
        """Test that workspace setup is included in tmux script."""
        mock_run.return_value = Mock(returncode=0, stdout="Started\n", stderr="")

        self.executor.execute_remote_tmux(
            session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
        )

        script = mock_run.call_args[0][0][3]
        # Verify workspace setup
        assert "mkdir -p ~/workspace" in script
        assert "git clone ~/repo.bundle" in script
        assert "cp -r ~/.claude ." in script
        # Verify venv setup
        assert "python3.11 -m venv ~/.amplihack-venv" in script
        assert "pip install . --quiet" in script

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_execute_remote_tmux_environment_variables(self, mock_run):
        """Test that environment variables are properly set in tmux."""
        mock_run.return_value = Mock(returncode=0, stdout="Started\n", stderr="")

        self.executor.execute_remote_tmux(
            session_id=self.test_session_id, command=self.test_command, prompt=self.test_prompt
        )

        script = mock_run.call_args[0][0][3]
        # Verify tmux sends environment variables
        assert "tmux send-keys -t test-session-123" in script
        assert "source ~/.amplihack-venv/bin/activate" in script
        assert "export ANTHROPIC_API_KEY=" in script


class TestExecutorTmuxIntegration(unittest.TestCase):
    """Integration tests for tmux functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.vm = VM(name="test-vm", size="Standard_D2s_v3", region="eastus")
        self.executor = Executor(vm=self.vm, timeout_minutes=60)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("subprocess.run")
    def test_tmux_workflow_start_then_check(self, mock_run):
        """Test complete workflow: start session then check status."""
        # First call: start tmux session
        mock_run.return_value = Mock(returncode=0, stdout="Started\n", stderr="")

        session_id = "workflow-test-123"
        started = self.executor.execute_remote_tmux(
            session_id=session_id, command="auto", prompt="Test task"
        )
        assert started

        # Second call: check status (running)
        mock_run.return_value = Mock(returncode=0, stdout="running\n", stderr="")
        status = self.executor.check_tmux_status(session_id)
        assert status == "running"

        # Third call: check status (completed)
        mock_run.return_value = Mock(returncode=0, stdout="completed\n", stderr="")
        status = self.executor.check_tmux_status(session_id)
        assert status == "completed"

        # Verify all calls were made
        assert mock_run.call_count == 3


if __name__ == "__main__":
    unittest.main()
