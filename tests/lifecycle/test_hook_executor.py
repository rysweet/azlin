"""Unit tests for HookExecutor (60% of test pyramid).

Tests hook execution with mocked subprocess calls.
"""

import subprocess
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from azlin.lifecycle.hook_executor import (
    HookExecutor,
    HookResult,
    HookType,
    HookExecutionError,
)


class TestHookExecutor:
    """Test HookExecutor hook execution logic."""

    @pytest.fixture
    def executor(self):
        """Create HookExecutor instance."""
        return HookExecutor()

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess module."""
        with patch("azlin.lifecycle.hook_executor.subprocess") as mock:
            yield mock

    @pytest.fixture
    def temp_script(self, tmp_path):
        """Create temporary executable script."""
        script = tmp_path / "test_hook.sh"
        script.write_text("#!/bin/bash\necho 'Hook executed'")
        script.chmod(0o755)
        return script

    def test_execute_hook_success(self, executor, mock_subprocess, temp_script):
        """Test successful hook execution."""
        mock_subprocess.run.return_value = Mock(returncode=0, stdout="Hook executed", stderr="")

        result = executor.execute_hook(HookType.ON_START, "test-vm", {"key": "value"}, script_path=str(temp_script))

        assert result.success is True
        assert result.hook_type == HookType.ON_START
        assert result.vm_name == "test-vm"
        assert result.exit_code == 0

    def test_execute_hook_with_environment_variables(self, executor, mock_subprocess, temp_script):
        """Test hook receives correct environment variables."""
        mock_subprocess.run.return_value = Mock(returncode=0, stdout="", stderr="")

        executor.execute_hook(HookType.ON_FAILURE, "test-vm", {"failure_count": 3}, script_path=str(temp_script))

        call_kwargs = mock_subprocess.run.call_args[1]
        env = call_kwargs["env"]

        assert "AZLIN_VM_NAME" in env
        assert env["AZLIN_VM_NAME"] == "test-vm"
        assert "AZLIN_EVENT_TYPE" in env
        assert env["AZLIN_EVENT_TYPE"] == "on_failure"
        assert "AZLIN_TIMESTAMP" in env
        assert "AZLIN_FAILURE_COUNT" in env
        assert env["AZLIN_FAILURE_COUNT"] == "3"

    def test_execute_hook_timeout(self, executor, mock_subprocess, temp_script):
        """Test hook execution respects timeout."""
        mock_subprocess.run.side_effect = subprocess.TimeoutExpired("cmd", 60)

        result = executor.execute_hook(HookType.ON_START, "test-vm", {}, script_path=str(temp_script), timeout=60)

        assert result.success is False
        assert "timeout" in result.error_message.lower()

    def test_execute_hook_nonzero_exit_code(self, executor, mock_subprocess, temp_script):
        """Test hook with non-zero exit code."""
        mock_subprocess.run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Script failed"
        )

        result = executor.execute_hook(HookType.ON_FAILURE, "test-vm", {}, script_path=str(temp_script))

        assert result.success is False
        assert result.exit_code == 1
        assert "Script failed" in result.stderr

    def test_validate_hook_script_executable(self, executor, temp_script):
        """Test validation passes for executable script."""
        is_valid = executor.validate_hook_script(str(temp_script))

        assert is_valid is True

    def test_validate_hook_script_not_executable(self, executor, tmp_path):
        """Test validation fails for non-executable script."""
        script = tmp_path / "not_executable.sh"
        script.write_text("#!/bin/bash\\necho 'test'")
        script.chmod(0o644)  # Not executable

        is_valid = executor.validate_hook_script(str(script))

        assert is_valid is False

    def test_validate_hook_script_nonexistent(self, executor):
        """Test validation fails for non-existent script."""
        is_valid = executor.validate_hook_script("/nonexistent/script.sh")

        assert is_valid is False

    def test_execute_hook_invalid_script_raises_error(self, executor):
        """Test executing invalid script raises error."""
        with pytest.raises(HookExecutionError, match="Script not found or not executable"):
            executor.execute_hook(HookType.ON_START, "test-vm", {}, script_path="/nonexistent/script.sh")

    def test_hook_types_enum(self):
        """Test all hook types defined."""
        expected_hooks = [
            "on_start",
            "on_stop",
            "on_failure",
            "on_restart",
            "on_destroy",
            "on_healthy",
        ]

        for hook_name in expected_hooks:
            assert hasattr(HookType, hook_name.upper())

    def test_execute_hook_captures_stdout_and_stderr(self, executor, mock_subprocess, temp_script):
        """Test hook execution captures stdout and stderr."""
        mock_subprocess.run.return_value = Mock(
            returncode=0,
            stdout="Output message",
            stderr="Warning message"
        )

        result = executor.execute_hook(HookType.ON_START, "test-vm", {}, script_path=str(temp_script))

        assert "Output message" in result.stdout
        assert "Warning message" in result.stderr

    def test_execute_hook_async_execution(self, executor, mock_subprocess, temp_script):
        """Test hook executes asynchronously (non-blocking)."""
        # Hook executor should not block daemon
        mock_subprocess.Popen.return_value = Mock(pid=12345)

        result = executor.execute_hook_async(HookType.ON_START, "test-vm", {}, script_path=str(temp_script))

        assert result.success is True
        assert result.pid is not None
        mock_subprocess.Popen.assert_called_once()

    def test_multiple_hooks_execute_independently(self, executor, mock_subprocess, temp_script):
        """Test multiple hooks can execute without interference."""
        mock_subprocess.run.return_value = Mock(returncode=0, stdout="", stderr="")

        result1 = executor.execute_hook(HookType.ON_START, "vm1", {}, script_path=str(temp_script))
        result2 = executor.execute_hook(HookType.ON_FAILURE, "vm2", {}, script_path=str(temp_script))

        assert result1.success is True
        assert result2.success is True
        assert mock_subprocess.run.call_count == 2
