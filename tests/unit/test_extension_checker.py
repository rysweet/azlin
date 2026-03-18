"""Unit tests for ExtensionChecker module.

Tests Azure CLI extension checking and installation logic.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.extension_checker import (
    ExtensionChecker,
    ExtensionResult,
    ExtensionStatus,
)


# --- Unit Tests (60%) ---


class TestCheckExtension:
    """Test individual extension checking."""

    def test_extension_installed(self):
        """Installed extension returns INSTALLED with version."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"name": "ssh", "version": "2.0.6"}',
                stderr="",
            )

            checker = ExtensionChecker()
            result = checker.check_extension("ssh")

            assert result.status == ExtensionStatus.INSTALLED
            assert result.extension_name == "ssh"
            assert result.version == "2.0.6"
            mock_run.assert_called_once_with(
                ["az", "extension", "show", "--name", "ssh"],
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_extension_not_installed(self):
        """Missing extension returns NOT_INSTALLED."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="The extension ssh is not installed.",
            )

            checker = ExtensionChecker()
            result = checker.check_extension("ssh")

            assert result.status == ExtensionStatus.NOT_INSTALLED
            assert result.extension_name == "ssh"

    def test_check_timeout(self):
        """Timeout returns NOT_INSTALLED with error message."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=10)

            checker = ExtensionChecker()
            result = checker.check_extension("ssh")

            assert result.status == ExtensionStatus.NOT_INSTALLED
            assert result.error_message == "Check timed out"

    def test_cli_not_found(self):
        """Missing az binary returns NOT_INSTALLED with error."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("az not found")

            checker = ExtensionChecker()
            result = checker.check_extension("ssh")

            assert result.status == ExtensionStatus.NOT_INSTALLED
            assert "not found" in result.error_message

    def test_custom_cli_path(self):
        """Custom CLI path is used in subprocess calls."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"version": "2.0.6"}',
                stderr="",
            )

            checker = ExtensionChecker(cli_path=Path("/usr/bin/az"))
            checker.check_extension("ssh")

            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "/usr/bin/az"

    def test_version_extraction_malformed_json(self):
        """Malformed JSON returns None version but still INSTALLED."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="not json",
                stderr="",
            )

            checker = ExtensionChecker()
            result = checker.check_extension("ssh")

            assert result.status == ExtensionStatus.INSTALLED
            assert result.version is None


class TestInstallExtension:
    """Test extension installation."""

    def test_install_success(self):
        """Successful install returns INSTALL_SUCCESS."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            checker = ExtensionChecker()
            result = checker.install_extension("ssh")

            assert result.status == ExtensionStatus.INSTALL_SUCCESS
            mock_run.assert_called_once_with(
                ["az", "extension", "add", "--name", "ssh", "--yes"],
                capture_output=True,
                text=True,
                timeout=120,
            )

    def test_install_failure(self):
        """Failed install returns INSTALL_FAILED with error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Permission denied",
            )

            checker = ExtensionChecker()
            result = checker.install_extension("ssh")

            assert result.status == ExtensionStatus.INSTALL_FAILED
            assert "Permission denied" in result.error_message

    def test_install_timeout(self):
        """Install timeout returns INSTALL_FAILED."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=120)

            checker = ExtensionChecker()
            result = checker.install_extension("ssh")

            assert result.status == ExtensionStatus.INSTALL_FAILED
            assert "timed out" in result.error_message


class TestExtractVersion:
    """Test version extraction from az output."""

    def test_valid_json(self):
        assert ExtensionChecker._extract_version('{"version": "1.2.3"}') == "1.2.3"

    def test_missing_version_key(self):
        assert ExtensionChecker._extract_version('{"name": "ssh"}') is None

    def test_invalid_json(self):
        assert ExtensionChecker._extract_version("not json") is None

    def test_empty_string(self):
        assert ExtensionChecker._extract_version("") is None

    def test_none_input(self):
        assert ExtensionChecker._extract_version(None) is None


# --- Integration Tests (30%) ---


class TestCheckAllRequired:
    """Test checking multiple extensions."""

    def test_all_installed(self):
        """All extensions installed returns all INSTALLED."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"version": "2.0.0"}',
                stderr="",
            )

            checker = ExtensionChecker()
            results = checker.check_all_required()

            assert len(results) == 2
            assert results["ssh"].status == ExtensionStatus.INSTALLED
            assert results["bastion"].status == ExtensionStatus.INSTALLED

    def test_one_missing(self):
        """One missing extension detected correctly."""
        with patch("subprocess.run") as mock_run:
            # ssh installed, bastion not
            def side_effect(cmd, **kwargs):
                if "ssh" in cmd:
                    return Mock(returncode=0, stdout='{"version": "2.0.0"}', stderr="")
                return Mock(returncode=1, stdout="", stderr="not installed")

            mock_run.side_effect = side_effect

            checker = ExtensionChecker()
            results = checker.check_all_required()

            assert results["ssh"].status == ExtensionStatus.INSTALLED
            assert results["bastion"].status == ExtensionStatus.NOT_INSTALLED


class TestCheckAndInstallMissing:
    """Test the combined check-and-install workflow."""

    def test_nothing_missing(self):
        """No installation when all extensions present."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"version": "2.0.0"}',
                stderr="",
            )

            checker = ExtensionChecker()
            results = checker.check_and_install_missing()

            # Only check calls, no install calls
            for call in mock_run.call_args_list:
                assert "add" not in call[0][0]

    def test_install_when_missing_user_accepts(self):
        """Missing extensions get installed when user accepts."""
        call_count = 0

        def subprocess_side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "show" in cmd:
                return Mock(returncode=1, stdout="", stderr="not installed")
            if "add" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        with (
            patch("subprocess.run", side_effect=subprocess_side_effect),
            patch("builtins.input", return_value="y"),
        ):
            checker = ExtensionChecker()
            results = checker.check_and_install_missing()

            assert results["ssh"].status == ExtensionStatus.INSTALL_SUCCESS
            assert results["bastion"].status == ExtensionStatus.INSTALL_SUCCESS

    def test_no_install_when_user_declines(self):
        """No installation when user declines prompt."""
        with (
            patch("subprocess.run") as mock_run,
            patch("builtins.input", return_value="n"),
        ):
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="not installed")

            checker = ExtensionChecker()
            results = checker.check_and_install_missing()

            # Should still show NOT_INSTALLED (not attempted)
            assert results["ssh"].status == ExtensionStatus.NOT_INSTALLED
            assert results["bastion"].status == ExtensionStatus.NOT_INSTALLED

    def test_keyboard_interrupt_during_prompt(self):
        """KeyboardInterrupt during prompt skips installation gracefully."""
        with (
            patch("subprocess.run") as mock_run,
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="not installed")

            checker = ExtensionChecker()
            results = checker.check_and_install_missing()

            assert results["ssh"].status == ExtensionStatus.NOT_INSTALLED


# --- E2E Test (10%) ---


class TestBastionManagerErrorSanitization:
    """Test the safety net in bastion_manager error handling."""

    def test_extension_not_installed_error_detected(self):
        """Extension error pattern produces actionable message."""
        from azlin.modules.bastion_manager import BastionManager

        stderr = (
            "The extension ssh is not installed. "
            "Please install the extension via `az extension add -n ssh`."
        )
        result = BastionManager._sanitize_tunnel_error(stderr)

        assert "extension" in result.lower()
        assert "az extension add" in result

    def test_generic_error_still_works(self):
        """Other errors still get generic message."""
        from azlin.modules.bastion_manager import BastionManager

        result = BastionManager._sanitize_tunnel_error("some unknown error")
        assert result == "Tunnel creation failed"
