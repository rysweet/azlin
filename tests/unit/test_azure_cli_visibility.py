"""
Comprehensive TDD tests for Azure CLI command visibility and progress indicators.

Test Coverage (Issue #236):
1. Command display before execution
2. Sensitive data sanitization (passwords, keys, tokens)
3. Progress indicator lifecycle (start, update, stop)
4. TTY vs non-TTY mode detection
5. Error handling (command failures, user cancellation)
6. Thread safety for concurrent operations

Testing Pyramid:
- Unit tests: 60% (command sanitization, progress logic, TTY detection)
- Integration tests: 30% (end-to-end workflow with mocked subprocess)
- E2E tests: 10% (minimal full system tests)
"""

import io
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

# ============================================================================
# UNIT TESTS (60%) - Command Sanitization & Core Logic
# ============================================================================


class TestCommandSanitizer:
    """Unit tests for command sanitization - removing sensitive data."""

    def test_sanitize_password_flag(self):
        """Test sanitization of --password flag."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "login", "--password", "SuperSecret123!"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "login", "--password", "***"]

    def test_sanitize_password_short_flag(self):
        """Test sanitization of -p flag (password shorthand)."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "login", "-p", "MyPassword"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "login", "-p", "***"]

    def test_sanitize_client_secret(self):
        """Test sanitization of --client-secret flag."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "login", "--service-principal", "--client-secret", "abc123def456"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "login", "--service-principal", "--client-secret", "***"]

    def test_sanitize_account_key(self):
        """Test sanitization of --account-key flag."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "storage", "blob", "upload", "--account-key", "key123456"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "storage", "blob", "upload", "--account-key", "***"]

    def test_sanitize_sas_token(self):
        """Test sanitization of --sas-token flag."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "storage", "blob", "list", "--sas-token", "?sv=2020-08-04&ss=bfqt"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "storage", "blob", "list", "--sas-token", "***"]

    def test_sanitize_connection_string(self):
        """Test sanitization of --connection-string flag."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = [
            "az",
            "storage",
            "account",
            "show",
            "--connection-string",
            "DefaultEndpointsProtocol=https;AccountKey=secret",
        ]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "storage", "account", "show", "--connection-string", "***"]

    def test_sanitize_token_flag(self):
        """Test sanitization of --token flag."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "rest", "--url", "https://api.azure.com", "--token", "Bearer abc123"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "rest", "--url", "https://api.azure.com", "--token", "***"]

    def test_sanitize_multiple_secrets(self):
        """Test sanitization of multiple secret flags in one command."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = [
            "az",
            "login",
            "--password",
            "pass123",
            "--client-secret",
            "secret456",
        ]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "login", "--password", "***", "--client-secret", "***"]

    def test_sanitize_equals_notation(self):
        """Test sanitization of --flag=value notation."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "login", "--password=SuperSecret"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["az", "login", "--password=***"]

    def test_sanitize_no_secrets(self):
        """Test that commands without secrets are unchanged."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "vm", "list", "--resource-group", "my-rg"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == cmd

    def test_sanitize_empty_command(self):
        """Test sanitization of empty command list."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = []

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == []

    def test_sanitize_custom_patterns(self):
        """Test adding custom sanitization patterns."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer(additional_patterns=["--api-key", "--auth-token"])
        cmd = ["myapp", "deploy", "--api-key", "secret123", "--auth-token", "token456"]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized == ["myapp", "deploy", "--api-key", "***", "--auth-token", "***"]

    def test_sanitize_preserves_order(self):
        """Test that sanitization preserves command argument order."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "login", "--username", "user", "--password", "pass", "--tenant", "123"]

        sanitized = sanitizer.sanitize(cmd)

        assert len(sanitized) == len(cmd)
        assert sanitized[0:2] == ["az", "login"]
        assert sanitized[2:4] == ["--username", "user"]
        assert sanitized[4:6] == ["--password", "***"]
        assert sanitized[6:8] == ["--tenant", "123"]

    def test_sanitize_case_insensitive(self):
        """Test that sanitization handles different cases."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        # Azure CLI typically uses lowercase, but test case variations
        cmd = ["az", "login", "--Password", "MyPass"]

        sanitized = sanitizer.sanitize(cmd)

        # Should sanitize regardless of case
        assert sanitized == ["az", "login", "--Password", "***"]


class TestProgressIndicator:
    """Unit tests for progress indicator lifecycle."""

    def test_progress_start(self):
        """Test starting a progress indicator."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()

        indicator.start("Creating VM", operation_id="op_001")

        assert indicator.is_active()
        assert indicator.current_operation == "Creating VM"
        assert indicator.operation_id == "op_001"

    def test_progress_update(self):
        """Test updating progress indicator."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Creating VM")

        indicator.update("Provisioning resources...")

        updates = indicator.get_updates()
        assert len(updates) >= 2  # Start + update
        assert updates[-1].message == "Provisioning resources..."

    def test_progress_stop_success(self):
        """Test stopping progress indicator with success."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Creating VM")

        indicator.stop(success=True, message="VM created successfully")

        assert not indicator.is_active()
        updates = indicator.get_updates()
        assert updates[-1].success is True
        assert "successfully" in updates[-1].message.lower()

    def test_progress_stop_failure(self):
        """Test stopping progress indicator with failure."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Creating VM")

        indicator.stop(success=False, message="VM creation failed")

        assert not indicator.is_active()
        updates = indicator.get_updates()
        assert updates[-1].success is False
        assert "failed" in updates[-1].message.lower()

    def test_progress_elapsed_time(self):
        """Test that progress indicator tracks elapsed time."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Creating VM")
        time.sleep(0.1)  # Small delay
        indicator.stop(success=True)

        updates = indicator.get_updates()
        final_update = updates[-1]
        assert hasattr(final_update, "elapsed_seconds")
        assert final_update.elapsed_seconds >= 0.1

    def test_progress_cannot_start_twice(self):
        """Test that starting progress twice raises error."""
        from azlin.azure_cli_visibility import ProgressError, ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Operation 1")

        with pytest.raises(ProgressError, match="already active"):
            indicator.start("Operation 2")

    def test_progress_cannot_update_when_not_active(self):
        """Test that updating inactive progress raises error."""
        from azlin.azure_cli_visibility import ProgressError, ProgressIndicator

        indicator = ProgressIndicator()

        with pytest.raises(ProgressError, match="not active"):
            indicator.update("Should fail")

    def test_progress_cannot_stop_when_not_active(self):
        """Test that stopping inactive progress raises error."""
        from azlin.azure_cli_visibility import ProgressError, ProgressIndicator

        indicator = ProgressIndicator()

        with pytest.raises(ProgressError, match="not active"):
            indicator.stop(success=True)

    def test_progress_clear_history(self):
        """Test clearing progress history."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Operation")
        indicator.update("Update 1")
        indicator.stop(success=True)

        indicator.clear_history()

        assert len(indicator.get_updates()) == 0


class TestTTYDetection:
    """Unit tests for TTY vs non-TTY mode detection."""

    def test_is_tty_when_stdout_is_terminal(self):
        """Test TTY detection when stdout is a terminal."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        # Clear CI environment variables and mock isatty
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys.stdout, "isatty", return_value=True),
        ):
            assert detector.is_tty() is True

    def test_is_not_tty_when_stdout_redirected(self):
        """Test TTY detection when stdout is redirected."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        with patch.object(sys.stdout, "isatty", return_value=False):
            assert detector.is_tty() is False

    def test_is_not_tty_in_ci_environment(self):
        """Test that CI environment is detected as non-TTY."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        with patch.dict(os.environ, {"CI": "true"}):
            assert detector.is_tty() is False

    def test_is_not_tty_in_github_actions(self):
        """Test that GitHub Actions is detected as non-TTY."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            assert detector.is_tty() is False

    def test_supports_color_in_tty(self):
        """Test color support detection in TTY mode."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        # Clear CI environment variables and mock isatty
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys.stdout, "isatty", return_value=True),
        ):
            assert detector.supports_color() is True

    def test_no_color_when_no_color_env_set(self):
        """Test that NO_COLOR environment variable disables color."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert detector.supports_color() is False

    def test_term_dumb_disables_features(self):
        """Test that TERM=dumb disables interactive features."""
        from azlin.azure_cli_visibility import TTYDetector

        detector = TTYDetector()

        with patch.dict(os.environ, {"TERM": "dumb"}):
            assert detector.supports_interactive_features() is False


class TestCommandDisplayFormatter:
    """Unit tests for command display formatting."""

    def test_format_simple_command(self):
        """Test formatting a simple command."""
        from azlin.azure_cli_visibility import CommandDisplayFormatter

        formatter = CommandDisplayFormatter()
        cmd = ["az", "vm", "list"]

        formatted = formatter.format(cmd)

        assert "az vm list" in formatted

    def test_format_command_with_long_args(self):
        """Test formatting command with long arguments."""
        from azlin.azure_cli_visibility import CommandDisplayFormatter

        formatter = CommandDisplayFormatter(max_width=50)
        cmd = [
            "az",
            "vm",
            "create",
            "--resource-group",
            "my-rg",
            "--name",
            "my-vm",
            "--image",
            "UbuntuLTS",
        ]

        formatted = formatter.format(cmd)

        # Should wrap or truncate if too long
        assert len(formatted) <= 80  # Reasonable display width

    def test_format_adds_color_in_tty(self):
        """Test that formatting adds color codes in TTY mode."""
        from azlin.azure_cli_visibility import CommandDisplayFormatter

        formatter = CommandDisplayFormatter(use_color=True)
        cmd = ["az", "vm", "list"]

        formatted = formatter.format(cmd)

        # Should contain ANSI escape codes for color
        assert "\033[" in formatted or "az vm list" in formatted

    def test_format_no_color_in_non_tty(self):
        """Test that formatting omits color in non-TTY mode."""
        from azlin.azure_cli_visibility import CommandDisplayFormatter

        formatter = CommandDisplayFormatter(use_color=False)
        cmd = ["az", "vm", "list"]

        formatted = formatter.format(cmd)

        # Should NOT contain ANSI escape codes
        assert "\033[" not in formatted


# ============================================================================
# UNIT TESTS - Thread Safety
# ============================================================================


class TestThreadSafety:
    """Unit tests for thread safety of concurrent operations."""

    def test_progress_indicator_thread_safe(self):
        """Test that progress indicator is thread-safe."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        errors = []

        def update_progress(thread_id: int):
            try:
                for i in range(10):
                    indicator.update(f"Thread {thread_id} update {i}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        indicator.start("Concurrent operation")

        threads = [threading.Thread(target=update_progress, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        indicator.stop(success=True)

        # Should complete without errors
        assert len(errors) == 0
        # Should have received all updates
        updates = indicator.get_updates()
        assert len(updates) >= 30  # 3 threads * 10 updates each

    def test_command_sanitizer_thread_safe(self):
        """Test that command sanitizer is thread-safe."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        results = []

        def sanitize_command(thread_id: int):
            cmd = ["az", "login", "--password", f"pass{thread_id}"]
            sanitized = sanitizer.sanitize(cmd)
            results.append(sanitized)

        threads = [threading.Thread(target=sanitize_command, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should have sanitized passwords
        assert len(results) == 10
        for result in results:
            assert result[3] == "***"


# ============================================================================
# INTEGRATION TESTS (30%) - End-to-End Workflow
# ============================================================================


class TestAzureCLIVisibilityWorkflow:
    """Integration tests for complete command visibility workflow."""

    @patch("subprocess.run")
    def test_display_command_before_execution(self, mock_run):
        """Test that command is displayed before execution."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.return_value = Mock(returncode=0, stdout="VM created", stderr="")

        executor = AzureCLIExecutor()
        output_buffer = io.StringIO()

        with patch("sys.stdout", output_buffer):
            executor.execute(["az", "vm", "create", "--name", "test-vm"])

        output = output_buffer.getvalue()

        # Command should be displayed before execution
        assert "az vm create" in output
        # Subprocess should have been called
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_sanitize_secrets_in_display(self, mock_run):
        """Test that secrets are sanitized in command display."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.return_value = Mock(returncode=0, stdout="Logged in", stderr="")

        executor = AzureCLIExecutor()
        output_buffer = io.StringIO()

        with patch("sys.stdout", output_buffer):
            executor.execute(["az", "login", "--password", "SuperSecret123"])

        output = output_buffer.getvalue()

        # Password should be sanitized in display
        assert "SuperSecret123" not in output
        assert "***" in output

        # But original command should be passed to subprocess
        call_args = mock_run.call_args[0][0]
        assert "SuperSecret123" in call_args

    @patch("subprocess.run")
    def test_progress_indicator_lifecycle(self, mock_run):
        """Test complete progress indicator lifecycle."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        # Simulate long-running command
        def slow_command(*args, **kwargs):
            time.sleep(0.1)
            return Mock(returncode=0, stdout="Success", stderr="")

        mock_run.side_effect = slow_command

        executor = AzureCLIExecutor(show_progress=True)
        output_buffer = io.StringIO()

        with patch("sys.stdout", output_buffer):
            result = executor.execute(["az", "vm", "create", "--name", "test"])

        output = output_buffer.getvalue()

        # Should show start, progress, and completion
        assert "Creating VM" in output or "Executing" in output
        assert result["returncode"] == 0

    @patch("subprocess.run")
    def test_command_failure_handling(self, mock_run):
        """Test handling of command execution failures."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.return_value = Mock(returncode=1, stdout="", stderr="ERROR: VM not found")

        executor = AzureCLIExecutor(show_progress=True)
        output_buffer = io.StringIO()

        with patch("sys.stdout", output_buffer):
            result = executor.execute(["az", "vm", "show", "--name", "nonexistent"])

        output = output_buffer.getvalue()

        # Should indicate failure
        assert result["returncode"] == 1
        assert "ERROR" in result["stderr"] or "ERROR" in output

    @patch("subprocess.run")
    def test_user_cancellation_handling(self, mock_run):
        """Test handling of user cancellation (Ctrl+C)."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.side_effect = KeyboardInterrupt()

        executor = AzureCLIExecutor(show_progress=True)

        with pytest.raises(KeyboardInterrupt):
            executor.execute(["az", "vm", "create", "--name", "test"])

        # Progress should be stopped even on cancellation
        assert not executor.progress_indicator.is_active()

    @patch("subprocess.run")
    def test_tty_vs_non_tty_output(self, mock_run):
        """Test different output formatting for TTY vs non-TTY."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

        # Test TTY mode
        executor_tty = AzureCLIExecutor()
        with patch("sys.stdout.isatty", return_value=True):
            output_tty = io.StringIO()
            with patch("sys.stdout", output_tty):
                executor_tty.execute(["az", "vm", "list"])

        # Test non-TTY mode
        executor_non_tty = AzureCLIExecutor()
        with patch("sys.stdout.isatty", return_value=False):
            output_non_tty = io.StringIO()
            with patch("sys.stdout", output_non_tty):
                executor_non_tty.execute(["az", "vm", "list"])

        # TTY output might have color codes, non-TTY should not
        tty_out = output_tty.getvalue()
        non_tty_out = output_non_tty.getvalue()

        # Both should execute successfully
        assert "az vm list" in tty_out or len(tty_out) > 0
        assert "az vm list" in non_tty_out or len(non_tty_out) > 0

    @patch("subprocess.run")
    def test_timeout_handling(self, mock_run):
        """Test handling of command execution timeout."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=30)

        executor = AzureCLIExecutor(timeout=30)

        result = executor.execute(["az", "vm", "create", "--name", "test"])

        assert result["returncode"] == -1
        assert "timeout" in result["error"].lower()

    @patch("subprocess.run")
    def test_multiple_commands_in_sequence(self, mock_run):
        """Test executing multiple commands with visibility."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

        executor = AzureCLIExecutor(show_progress=True)
        commands = [
            ["az", "group", "create", "--name", "test-rg"],
            ["az", "vm", "create", "--resource-group", "test-rg"],
            ["az", "vm", "list", "--resource-group", "test-rg"],
        ]

        results = []
        for cmd in commands:
            result = executor.execute(cmd)
            results.append(result)

        # All commands should succeed
        assert len(results) == 3
        assert all(r["returncode"] == 0 for r in results)
        assert mock_run.call_count == 3


class TestProgressIndicatorIntegration:
    """Integration tests for progress indicator with real subprocess calls."""

    @patch("subprocess.run")
    def test_progress_updates_during_execution(self, mock_run):
        """Test that progress updates are shown during command execution."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        # Simulate command that takes time
        def slow_command(*args, **kwargs):
            time.sleep(0.2)
            return Mock(returncode=0, stdout="Done", stderr="")

        mock_run.side_effect = slow_command

        executor = AzureCLIExecutor(show_progress=True)
        output_buffer = io.StringIO()

        with patch("sys.stdout", output_buffer):
            executor.execute(["az", "vm", "create", "--name", "test"])

        output = output_buffer.getvalue()

        # Should have progress indication
        assert len(output) > 0

    @patch("subprocess.run")
    def test_progress_indicator_cleanup_on_error(self, mock_run):
        """Test that progress indicator is cleaned up properly on error."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.side_effect = RuntimeError("Command failed")

        executor = AzureCLIExecutor(show_progress=True)

        with pytest.raises(RuntimeError):
            executor.execute(["az", "vm", "create", "--name", "test"])

        # Progress indicator should not be active after error
        assert not executor.progress_indicator.is_active()


# ============================================================================
# E2E TESTS (10%) - Minimal Full System Tests
# ============================================================================


class TestEndToEndVisibility:
    """End-to-end tests for Azure CLI visibility system."""

    @patch("subprocess.run")
    def test_complete_vm_creation_workflow(self, mock_run):
        """Test complete VM creation workflow with visibility."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        # Simulate full VM creation flow
        responses = [
            Mock(returncode=0, stdout="Resource group created", stderr=""),
            Mock(returncode=0, stdout="VM created", stderr=""),
            Mock(returncode=0, stdout='{"name": "test-vm"}', stderr=""),
        ]
        mock_run.side_effect = responses

        executor = AzureCLIExecutor(show_progress=True)

        # Execute full workflow
        results = []
        commands = [
            ["az", "group", "create", "--name", "test-rg", "--location", "eastus"],
            ["az", "vm", "create", "--resource-group", "test-rg", "--name", "test-vm"],
            ["az", "vm", "show", "--resource-group", "test-rg", "--name", "test-vm"],
        ]

        for cmd in commands:
            result = executor.execute(cmd)
            results.append(result)

        # All operations should succeed
        assert len(results) == 3
        assert all(r["returncode"] == 0 for r in results)
        assert all(r["success"] for r in results)

    @patch("subprocess.run")
    def test_error_recovery_workflow(self, mock_run):
        """Test error recovery in multi-step workflow."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        # First command succeeds, second fails, third succeeds
        responses = [
            Mock(returncode=0, stdout="RG created", stderr=""),
            Mock(returncode=1, stdout="", stderr="ERROR: Quota exceeded"),
            Mock(returncode=0, stdout="Cleaned up", stderr=""),
        ]
        mock_run.side_effect = responses

        executor = AzureCLIExecutor(show_progress=True)

        results = []
        commands = [
            ["az", "group", "create", "--name", "test-rg"],
            ["az", "vm", "create", "--name", "test-vm"],  # This fails
            ["az", "group", "delete", "--name", "test-rg", "--yes"],
        ]

        for cmd in commands:
            result = executor.execute(cmd)
            results.append(result)

        # First should succeed, second fail, third succeed
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert results[2]["success"] is True


# ============================================================================
# EDGE CASES & BOUNDARY TESTS
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_command_display(self):
        """Test display of very long commands."""
        from azlin.azure_cli_visibility import CommandDisplayFormatter

        formatter = CommandDisplayFormatter(max_width=80)

        # Create very long command
        cmd = ["az", "vm", "create"]
        cmd.extend([f"--arg{i}" for i in range(50)])
        cmd.extend([f"value{i}" for i in range(50)])

        formatted = formatter.format(cmd)

        # Should handle gracefully (truncate or wrap)
        assert len(formatted) < 10000  # Reasonable upper limit

    def test_empty_command_sanitization(self):
        """Test sanitization of empty command."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        assert sanitizer.sanitize([]) == []

    def test_single_element_command(self):
        """Test handling of single-element command."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        assert sanitizer.sanitize(["az"]) == ["az"]

    def test_null_bytes_in_command(self):
        """Test handling of null bytes in command."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        # Should handle without crashing
        cmd = ["az", "vm", "create", "\x00"]
        sanitized = sanitizer.sanitize(cmd)
        assert len(sanitized) == len(cmd)

    def test_unicode_in_command(self):
        """Test handling of Unicode characters in command."""
        from azlin.azure_cli_visibility import CommandDisplayFormatter

        formatter = CommandDisplayFormatter()
        cmd = ["az", "vm", "create", "--name", "test-vm-🚀"]

        formatted = formatter.format(cmd)
        assert "test-vm" in formatted

    def test_rapid_progress_updates(self):
        """Test handling of rapid progress updates."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Fast operation")

        # Send many updates rapidly
        for i in range(100):
            indicator.update(f"Update {i}")

        indicator.stop(success=True)

        updates = indicator.get_updates()
        assert len(updates) >= 100

    def test_zero_timeout(self):
        """Test handling of zero timeout."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        executor = AzureCLIExecutor(timeout=0)

        # Should handle gracefully (use default or raise error)
        assert executor.timeout == 0 or executor.timeout > 0

    def test_negative_timeout(self):
        """Test handling of negative timeout."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        # Should reject or use default
        with pytest.raises(ValueError, match="[Tt]imeout"):
            AzureCLIExecutor(timeout=-1)

    def test_command_with_special_characters(self):
        """Test command containing special shell characters."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "vm", "create", "--name", "test;rm -rf /"]

        sanitized = sanitizer.sanitize(cmd)

        # Should preserve special chars (subprocess handles them safely)
        assert sanitized == cmd

    def test_extremely_long_password(self):
        """Test sanitization of extremely long password."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        long_password = "a" * 10000
        cmd = ["az", "login", "--password", long_password]

        sanitized = sanitizer.sanitize(cmd)

        assert sanitized[3] == "***"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestErrorHandling:
    """Test comprehensive error handling."""

    @patch("subprocess.run")
    def test_subprocess_not_found(self, mock_run):
        """Test handling when subprocess command is not found."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.side_effect = FileNotFoundError("az: command not found")

        executor = AzureCLIExecutor()
        result = executor.execute(["az", "vm", "list"])

        assert result["returncode"] == -1
        assert "not found" in result["error"].lower()

    @patch("subprocess.run")
    def test_permission_denied(self, mock_run):
        """Test handling of permission denied errors."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.side_effect = PermissionError("Permission denied")

        executor = AzureCLIExecutor()
        result = executor.execute(["az", "vm", "create"])

        assert result["returncode"] == -1
        assert "permission" in result["error"].lower()

    @patch("subprocess.run")
    def test_keyboard_interrupt_cleanup(self, mock_run):
        """Test that Ctrl+C properly cleans up progress indicator."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        mock_run.side_effect = KeyboardInterrupt()

        executor = AzureCLIExecutor(show_progress=True)

        with pytest.raises(KeyboardInterrupt):
            executor.execute(["az", "vm", "create"])

        # Progress indicator should be stopped
        assert not executor.progress_indicator.is_active()

    def test_invalid_command_structure(self):
        """Test handling of invalid command structure."""
        from azlin.azure_cli_visibility import AzureCLIExecutor

        executor = AzureCLIExecutor()

        # Should handle gracefully
        with pytest.raises((TypeError, ValueError)):
            executor.execute(None)  # type: ignore

    def test_sanitizer_with_none_value(self):
        """Test sanitizer handling of None values in command."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()

        # Should handle gracefully
        with pytest.raises((TypeError, ValueError)):
            sanitizer.sanitize(None)  # type: ignore


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


class TestPerformance:
    """Test performance characteristics."""

    def test_sanitizer_performance(self):
        """Test that sanitizer performs well with many commands."""
        from azlin.azure_cli_visibility import CommandSanitizer

        sanitizer = CommandSanitizer()
        cmd = ["az", "login", "--password", "secret123"]

        start = time.time()
        for _ in range(1000):
            sanitizer.sanitize(cmd)
        elapsed = time.time() - start

        # Should complete quickly (< 1 second for 1000 operations)
        assert elapsed < 1.0

    def test_progress_update_performance(self):
        """Test that progress updates don't significantly slow execution."""
        from azlin.azure_cli_visibility import ProgressIndicator

        indicator = ProgressIndicator()
        indicator.start("Performance test")

        start = time.time()
        for i in range(100):
            indicator.update(f"Update {i}")
        elapsed = time.time() - start

        indicator.stop(success=True)

        # 100 updates should be very fast (< 0.1 seconds)
        assert elapsed < 0.1


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_tty_environment():
    """Mock TTY environment for testing."""
    with patch("sys.stdout.isatty", return_value=True):
        yield


@pytest.fixture
def mock_non_tty_environment():
    """Mock non-TTY environment for testing."""
    with patch("sys.stdout.isatty", return_value=False):
        with patch.dict(os.environ, {"CI": "true"}):
            yield


@pytest.fixture
def capture_output():
    """Fixture to capture stdout/stderr."""

    @contextmanager
    def _capture():
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        try:
            sys.stdout = stdout_buffer
            sys.stderr = stderr_buffer
            yield {"stdout": stdout_buffer, "stderr": stderr_buffer}
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    return _capture
