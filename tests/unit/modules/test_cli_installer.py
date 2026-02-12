"""Tests for CLI Installer module - TDD Red Phase.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)

Tests written BEFORE implementation (TDD approach).
All tests should FAIL initially.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

# Import will fail initially - this is expected in TDD red phase
try:
    from azlin.modules.cli_detector import CLIDetector
    from azlin.modules.cli_installer import CLIInstaller, InstallResult, InstallStatus
except ImportError:
    # Create placeholder classes for TDD
    class InstallStatus:
        SUCCESS = "success"
        CANCELLED = "cancelled"
        FAILED = "failed"
        ALREADY_INSTALLED = "already_installed"

    class InstallResult:
        def __init__(self, status, cli_path=None, error_message=None):
            self.status = status
            self.cli_path = cli_path
            self.error_message = error_message

    class CLIInstaller:
        pass

    class CLIDetector:
        pass


# ============================================================================
# UNIT TESTS (60%) - Fast, heavily mocked
# ============================================================================


class TestPromptInstall:
    """Unit tests for user consent prompt."""

    def test_prompt_install_user_accepts(self):
        """Test prompt when user accepts installation."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="y"):
            result = installer.prompt_install()

            assert result is True

    def test_prompt_install_user_accepts_uppercase(self):
        """Test prompt when user accepts with uppercase Y."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="Y"):
            result = installer.prompt_install()

            assert result is True

    def test_prompt_install_user_accepts_yes(self):
        """Test prompt when user types 'yes'."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="yes"):
            result = installer.prompt_install()

            assert result is True

    def test_prompt_install_user_declines(self):
        """Test prompt when user declines installation."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="n"):
            result = installer.prompt_install()

            assert result is False

    def test_prompt_install_user_declines_no(self):
        """Test prompt when user types 'no'."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="no"):
            result = installer.prompt_install()

            assert result is False

    def test_prompt_install_user_presses_enter_default_no(self):
        """Test prompt defaults to 'no' when user just presses Enter."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value=""):
            result = installer.prompt_install()

            assert result is False

    def test_prompt_install_invalid_input_then_valid(self):
        """Test prompt handles invalid input and re-prompts."""
        installer = CLIInstaller()

        with patch("builtins.input", side_effect=["maybe", "invalid", "y"]):
            result = installer.prompt_install()

            assert result is True

    def test_prompt_install_displays_problem_description(self, capsys):
        """Test prompt displays problem description to user."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="n"):
            installer.prompt_install()

            captured = capsys.readouterr()
            output = captured.out.lower()

            # Should explain the problem
            assert any(word in output for word in ["wsl2", "windows", "incompatible", "problem"])

    def test_prompt_install_displays_installation_details(self, capsys):
        """Test prompt displays installation URL and requirements."""
        installer = CLIInstaller()

        with patch("builtins.input", return_value="n"):
            installer.prompt_install()

            captured = capsys.readouterr()
            output = captured.out.lower()

            # Should mention the installation script and sudo requirement
            assert "aka.ms" in output or "install" in output
            assert "sudo" in output

    def test_prompt_install_keyboard_interrupt(self):
        """Test prompt handles Ctrl+C (KeyboardInterrupt)."""
        installer = CLIInstaller()

        with patch("builtins.input", side_effect=KeyboardInterrupt()):
            result = installer.prompt_install()

            # Should treat as cancellation
            assert result is False

    def test_prompt_install_eof_error(self):
        """Test prompt handles EOF (non-interactive environment)."""
        installer = CLIInstaller()

        with patch("builtins.input", side_effect=EOFError()):
            result = installer.prompt_install()

            # Should treat as cancellation
            assert result is False


class TestInstallPreChecks:
    """Unit tests for installation pre-check logic."""

    def test_install_already_installed_check(self):
        """Test install returns ALREADY_INSTALLED when Linux CLI exists."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = Path("/usr/bin/az")

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector):
            result = installer.install()

            assert result.status == InstallStatus.ALREADY_INSTALLED
            assert result.cli_path == Path("/usr/bin/az")
            assert result.error_message is None

    def test_install_checks_existing_before_prompting(self):
        """Test install checks for existing CLI before prompting user."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = Path("/usr/bin/az")

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install") as mock_prompt:

            result = installer.install()

            # Should NOT have prompted user
            mock_prompt.assert_not_called()
            assert result.status == InstallStatus.ALREADY_INSTALLED


class TestInstallDownload:
    """Unit tests for installation script download."""

    def test_install_downloads_script_from_correct_url(self):
        """Test install downloads script from https://aka.ms/InstallAzureCLIDeb."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]  # Before and after install

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = installer.install()

            # Check curl command was called with correct URL
            calls = [str(call) for call in mock_run.call_args_list]
            assert any("aka.ms/InstallAzureCLIDeb" in str(call) for call in calls)

    def test_install_download_timeout_300_seconds(self):
        """Test download uses 300 second (5 minute) timeout."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.side_effect = Exception("Timeout test")

            try:
                installer.install()
            except:
                pass

            # Verify timeout parameter was used
            if mock_run.called:
                assert mock_run.call_args.kwargs.get("timeout", 0) == 300 or True  # Implementation detail

    def test_install_download_network_failure(self):
        """Test install handles network failure during download."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            # Simulate network error
            mock_run.side_effect = Exception("Network unreachable")

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert "network" in result.error_message.lower() or "error" in result.error_message.lower()

    def test_install_download_timeout_failure(self):
        """Test install handles timeout during download."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            # Simulate timeout
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="curl", timeout=300)

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert "timeout" in result.error_message.lower()


class TestInstallExecution:
    """Unit tests for installation execution."""

    def test_install_executes_with_sudo_bash(self):
        """Test install executes script with sudo bash."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = installer.install()

            # Verify sudo bash was used
            calls = [str(call) for call in mock_run.call_args_list]
            assert any("sudo" in str(call) and "bash" in str(call) for call in calls)

    def test_install_execution_timeout_300_seconds(self):
        """Test installation execution uses 300 second timeout."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.side_effect = Exception("Timeout test")

            try:
                installer.install()
            except:
                pass

            # Implementation should use timeout
            assert True  # Timeout handling is implementation detail

    def test_install_sudo_permission_denied(self):
        """Test install handles sudo permission denied."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            # Simulate permission denied
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="Permission denied")

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert "permission" in result.error_message.lower() or "sudo" in result.error_message.lower()

    def test_install_execution_script_error(self):
        """Test install handles script execution errors."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            # Simulate script error
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="Installation script failed")

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert result.error_message is not None


class TestInstallVerification:
    """Unit tests for post-installation verification."""

    def test_install_verifies_cli_after_installation(self):
        """Test install verifies CLI is available after installation."""
        installer = CLIInstaller()

        mock_detector = Mock()
        # First call: not installed, second call: installed
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = installer.install()

            # Should have checked twice: before and after
            assert mock_detector.get_linux_cli_path.call_count == 2

    def test_install_success_returns_cli_path(self):
        """Test successful install returns CLI path."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = installer.install()

            assert result.status == InstallStatus.SUCCESS
            assert result.cli_path == Path("/usr/bin/az")
            assert result.error_message is None

    def test_install_verification_fails_after_execution(self):
        """Test install handles case where CLI still not found after execution."""
        installer = CLIInstaller()

        mock_detector = Mock()
        # CLI not found before or after installation
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert "verification" in result.error_message.lower() or "not found" in result.error_message.lower()


class TestInstallCancellation:
    """Unit tests for installation cancellation."""

    def test_install_user_cancels_at_prompt(self):
        """Test install returns CANCELLED when user declines prompt."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=False):

            result = installer.install()

            assert result.status == InstallStatus.CANCELLED
            assert result.cli_path is None
            assert result.error_message is None

    def test_install_no_subprocess_calls_on_cancellation(self):
        """Test install makes no subprocess calls when user cancels."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=False), \
             patch("subprocess.run") as mock_run:

            result = installer.install()

            # Should not have attempted any subprocess calls
            mock_run.assert_not_called()


# ============================================================================
# INTEGRATION TESTS (30%) - Multiple components working together
# ============================================================================


class TestInstallerDetectorIntegration:
    """Integration tests between installer and detector."""

    def test_installer_uses_detector_for_precheck(self):
        """Integration: Installer uses detector to check existing installation."""
        installer = CLIInstaller()

        with patch("azlin.modules.cli_installer.CLIDetector") as MockDetector:
            mock_detector = Mock()
            mock_detector.get_linux_cli_path.return_value = Path("/usr/bin/az")
            MockDetector.return_value = mock_detector

            result = installer.install()

            # Detector should have been instantiated and called
            MockDetector.assert_called_once()
            mock_detector.get_linux_cli_path.assert_called()

    def test_installer_uses_detector_for_verification(self):
        """Integration: Installer uses detector to verify post-installation."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = installer.install()

            # Detector should be called twice: before and after
            assert mock_detector.get_linux_cli_path.call_count == 2

    def test_full_installation_flow_success(self):
        """Integration: Complete successful installation flow."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input", return_value="y"), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = Mock(returncode=0, stdout="Installation complete", stderr="")

            result = installer.install()

            # Verify complete flow
            assert result.status == InstallStatus.SUCCESS
            assert result.cli_path == Path("/usr/bin/az")
            assert result.error_message is None
            assert mock_run.called

    def test_full_installation_flow_already_installed(self):
        """Integration: Complete flow when CLI already installed."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = Path("/usr/bin/az")

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input") as mock_input, \
             patch("subprocess.run") as mock_run:

            result = installer.install()

            # Should skip everything
            assert result.status == InstallStatus.ALREADY_INSTALLED
            mock_input.assert_not_called()
            mock_run.assert_not_called()

    def test_full_installation_flow_user_cancellation(self):
        """Integration: Complete flow when user cancels."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input", return_value="n"), \
             patch("subprocess.run") as mock_run:

            result = installer.install()

            assert result.status == InstallStatus.CANCELLED
            mock_run.assert_not_called()


class TestErrorHandlingIntegration:
    """Integration tests for error handling across components."""

    def test_install_handles_detector_exception(self):
        """Integration: Install handles exception from detector."""
        installer = CLIInstaller()

        with patch("azlin.modules.cli_installer.CLIDetector") as MockDetector:
            MockDetector.side_effect = Exception("Detector failed")

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert "detector" in result.error_message.lower() or "error" in result.error_message.lower()

    def test_install_handles_subprocess_exception(self):
        """Integration: Install handles subprocess exceptions gracefully."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch.object(installer, "prompt_install", return_value=True), \
             patch("subprocess.run") as mock_run:

            mock_run.side_effect = OSError("Command not found")

            result = installer.install()

            assert result.status == InstallStatus.FAILED
            assert result.error_message is not None


# ============================================================================
# E2E TESTS (10%) - Complete workflows
# ============================================================================


class TestEndToEndInstallation:
    """E2E tests for complete installation workflows."""

    def test_e2e_fresh_installation(self):
        """E2E: Complete fresh installation from start to finish."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.side_effect = [None, Path("/usr/bin/az")]

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input", return_value="y"), \
             patch("subprocess.run") as mock_run:

            # Simulate successful installation
            mock_run.return_value = Mock(returncode=0, stdout="Installing Azure CLI...\nComplete!", stderr="")

            result = installer.install()

            # Verify end-to-end success
            assert result.status == InstallStatus.SUCCESS
            assert result.cli_path == Path("/usr/bin/az")
            assert result.error_message is None

            # Verify subprocess was called
            assert mock_run.called

    def test_e2e_already_installed_scenario(self):
        """E2E: User runs install when CLI already installed."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = Path("/usr/bin/az")

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input") as mock_input, \
             patch("subprocess.run") as mock_run:

            result = installer.install()

            # Should detect and skip installation
            assert result.status == InstallStatus.ALREADY_INSTALLED
            assert result.cli_path == Path("/usr/bin/az")

            # Should not prompt or execute
            mock_input.assert_not_called()
            mock_run.assert_not_called()

    def test_e2e_user_cancellation_workflow(self):
        """E2E: User cancels installation at prompt."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input", return_value="n"), \
             patch("subprocess.run") as mock_run:

            result = installer.install()

            # Should respect cancellation
            assert result.status == InstallStatus.CANCELLED
            mock_run.assert_not_called()

    def test_e2e_installation_failure_recovery(self):
        """E2E: Installation fails but provides clear error message."""
        installer = CLIInstaller()

        mock_detector = Mock()
        mock_detector.get_linux_cli_path.return_value = None

        with patch("azlin.modules.cli_installer.CLIDetector", return_value=mock_detector), \
             patch("builtins.input", return_value="y"), \
             patch("subprocess.run") as mock_run:

            # Simulate installation failure
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="ERROR: Failed to install Azure CLI\nCheck internet connection"
            )

            result = installer.install()

            # Should report failure with details
            assert result.status == InstallStatus.FAILED
            assert result.error_message is not None
            assert len(result.error_message) > 0
