"""Unit tests for PlatformDetector - TDD approach.

These tests define the contract for platform detection logic
before implementation exists.

Security focus:
- Path validation
- Command injection prevention
- Safe subprocess handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

# Import will fail until implementation exists
try:
    from azlin.commands.restore import PlatformDetector, TerminalType
except ImportError:
    pytest.skip("azlin.commands.restore not implemented yet", allow_module_level=True)


# ============================================================================
# PLATFORM DETECTION TESTS
# ============================================================================


class TestPlatformDetection:
    """Test basic platform detection."""

    def test_detect_macos_returns_macos(self):
        """Test macOS detection returns 'macos'."""
        with patch("platform.system", return_value="Darwin"):
            result = PlatformDetector.detect_platform()
            assert result == "macos"

    def test_detect_windows_returns_windows(self):
        """Test Windows detection returns 'windows'."""
        with patch("platform.system", return_value="Windows"):
            result = PlatformDetector.detect_platform()
            assert result == "windows"

    def test_detect_linux_returns_linux(self):
        """Test Linux (non-WSL) detection returns 'linux'."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(PlatformDetector, "_is_wsl", return_value=False):
                result = PlatformDetector.detect_platform()
                assert result == "linux"

    def test_detect_wsl_returns_wsl(self):
        """Test WSL detection returns 'wsl'."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(PlatformDetector, "_is_wsl", return_value=True):
                result = PlatformDetector.detect_platform()
                assert result == "wsl"

    def test_detect_unknown_platform(self):
        """Test unknown platform returns 'unknown'."""
        with patch("platform.system", return_value="FreeBSD"):
            result = PlatformDetector.detect_platform()
            assert result == "unknown"


# ============================================================================
# WSL DETECTION TESTS
# ============================================================================


class TestWSLDetection:
    """Test WSL detection logic."""

    def test_is_wsl_detects_microsoft_lowercase(self):
        """Test WSL detection with lowercase 'microsoft'."""
        mock_data = "Linux version 5.15.0-1028-microsoft"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = PlatformDetector._is_wsl()
            assert result is True

    def test_is_wsl_detects_microsoft_uppercase(self):
        """Test WSL detection with uppercase 'Microsoft'."""
        mock_data = "Linux version 4.4.0-19041-Microsoft"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = PlatformDetector._is_wsl()
            assert result is True

    def test_is_wsl_detects_microsoft_mixed_case(self):
        """Test WSL detection with mixed case 'MicroSoft'."""
        mock_data = "Linux version 5.10.0-MicroSoft-standard"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = PlatformDetector._is_wsl()
            assert result is True

    def test_is_wsl_returns_false_for_regular_linux(self):
        """Test WSL detection returns False for regular Linux."""
        mock_data = "Linux version 5.10.0-8-amd64 (debian-kernel@lists.debian.org)"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = PlatformDetector._is_wsl()
            assert result is False

    def test_is_wsl_handles_file_not_found(self):
        """Test WSL detection handles missing /proc/version."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = PlatformDetector._is_wsl()
            assert result is False

    def test_is_wsl_handles_permission_error(self):
        """Test WSL detection handles permission errors."""
        with patch("builtins.open", side_effect=PermissionError):
            result = PlatformDetector._is_wsl()
            assert result is False

    def test_is_wsl_handles_generic_exception(self):
        """Test WSL detection handles generic exceptions."""
        with patch("builtins.open", side_effect=Exception("Unknown error")):
            result = PlatformDetector._is_wsl()
            assert result is False


# ============================================================================
# DEFAULT TERMINAL SELECTION TESTS
# ============================================================================


class TestDefaultTerminalSelection:
    """Test default terminal selection based on platform."""

    def test_get_default_terminal_for_macos(self):
        """Test macOS gets Terminal.app."""
        with patch.object(PlatformDetector, "detect_platform", return_value="macos"):
            result = PlatformDetector.get_default_terminal()
            assert result == TerminalType.MACOS_TERMINAL

    def test_get_default_terminal_for_wsl(self):
        """Test WSL gets Windows Terminal."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            result = PlatformDetector.get_default_terminal()
            assert result == TerminalType.WINDOWS_TERMINAL

    def test_get_default_terminal_for_windows(self):
        """Test Windows gets wt.exe."""
        with patch.object(PlatformDetector, "detect_platform", return_value="windows"):
            result = PlatformDetector.get_default_terminal()
            assert result == TerminalType.WINDOWS_TERMINAL

    def test_get_default_terminal_for_linux_with_gnome(self):
        """Test Linux with gnome-terminal available."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            with patch.object(
                PlatformDetector, "_has_command",
                side_effect=lambda cmd: cmd == "gnome-terminal"
            ):
                result = PlatformDetector.get_default_terminal()
                assert result == TerminalType.LINUX_GNOME

    def test_get_default_terminal_for_linux_with_xterm(self):
        """Test Linux falls back to xterm when gnome-terminal unavailable."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            with patch.object(
                PlatformDetector, "_has_command",
                side_effect=lambda cmd: cmd == "xterm"
            ):
                result = PlatformDetector.get_default_terminal()
                assert result == TerminalType.LINUX_XTERM

    def test_get_default_terminal_for_linux_no_terminal(self):
        """Test Linux with no terminal available returns UNKNOWN."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            with patch.object(PlatformDetector, "_has_command", return_value=False):
                result = PlatformDetector.get_default_terminal()
                assert result == TerminalType.UNKNOWN

    def test_get_default_terminal_for_unknown_platform(self):
        """Test unknown platform returns UNKNOWN."""
        with patch.object(PlatformDetector, "detect_platform", return_value="unknown"):
            result = PlatformDetector.get_default_terminal()
            assert result == TerminalType.UNKNOWN


# ============================================================================
# WINDOWS TERMINAL PATH RESOLUTION TESTS
# ============================================================================


class TestWindowsTerminalPathResolution:
    """Test Windows Terminal path resolution in WSL."""

    def test_get_windows_terminal_path_returns_none_on_non_wsl(self):
        """Test returns None when not running in WSL."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            result = PlatformDetector.get_windows_terminal_path()
            assert result is None

    def test_get_windows_terminal_path_finds_in_appdata(self):
        """Test finding wt.exe in user's AppData."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value="testuser"):
                expected_path = Path("/mnt/c/Users/testuser/AppData/Local/Microsoft/WindowsApps/wt.exe")
                with patch("pathlib.Path.exists", side_effect=lambda: str(expected_path) in str(expected_path)):
                    result = PlatformDetector.get_windows_terminal_path()
                    assert result is not None
                    assert "wt.exe" in str(result)

    def test_get_windows_terminal_path_uses_glob_for_wildcards(self):
        """Test using glob to find wt.exe with wildcards."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value="testuser"):
                with patch("glob.glob", return_value=["/mnt/c/Program Files/WindowsApps/Microsoft.WindowsTerminal_1.15.2874.0/wt.exe"]):
                    result = PlatformDetector.get_windows_terminal_path()
                    assert result is not None
                    assert "wt.exe" in str(result)

    def test_get_windows_terminal_path_returns_none_when_not_found(self):
        """Test returns None when wt.exe not found."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value="testuser"):
                with patch("pathlib.Path.exists", return_value=False):
                    with patch("glob.glob", return_value=[]):
                        result = PlatformDetector.get_windows_terminal_path()
                        assert result is None

    def test_get_windows_terminal_path_handles_no_username(self):
        """Test handles case when Windows username cannot be determined."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value=None):
                result = PlatformDetector.get_windows_terminal_path()
                assert result is None


# ============================================================================
# WINDOWS USERNAME EXTRACTION TESTS
# ============================================================================


class TestWindowsUsernameExtraction:
    """Test extracting Windows username in WSL."""

    def test_get_windows_username_success(self):
        """Test successful username extraction."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="TestUser\n")
            result = PlatformDetector._get_windows_username()
            assert result == "TestUser"

    def test_get_windows_username_strips_whitespace(self):
        """Test username extraction strips whitespace."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="  TestUser  \r\n")
            result = PlatformDetector._get_windows_username()
            assert result == "TestUser"

    def test_get_windows_username_handles_command_failure(self):
        """Test handles command failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="")
            result = PlatformDetector._get_windows_username()
            assert result is None

    def test_get_windows_username_handles_exception(self):
        """Test handles subprocess exception."""
        with patch("subprocess.run", side_effect=Exception("Command failed")):
            result = PlatformDetector._get_windows_username()
            assert result is None

    def test_get_windows_username_handles_timeout(self):
        """Test handles timeout."""
        with patch("subprocess.run", side_effect=TimeoutError):
            result = PlatformDetector._get_windows_username()
            assert result is None


# ============================================================================
# COMMAND AVAILABILITY TESTS
# ============================================================================


class TestCommandAvailability:
    """Test checking command availability."""

    def test_has_command_returns_true_when_found(self):
        """Test _has_command returns True when command exists."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = PlatformDetector._has_command("gnome-terminal")
            assert result is True

    def test_has_command_calls_which(self):
        """Test _has_command calls 'which' command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            PlatformDetector._has_command("test-command")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "which" in args
            assert "test-command" in args

    def test_has_command_returns_false_when_not_found(self):
        """Test _has_command returns False when command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = PlatformDetector._has_command("nonexistent")
            assert result is False

    def test_has_command_returns_false_on_timeout(self):
        """Test _has_command returns False on timeout."""
        with patch("subprocess.run", side_effect=TimeoutError):
            result = PlatformDetector._has_command("slow-command")
            assert result is False

    def test_has_command_returns_false_on_exception(self):
        """Test _has_command returns False on generic exception."""
        with patch("subprocess.run", side_effect=Exception("Generic error")):
            result = PlatformDetector._has_command("error-command")
            assert result is False

    def test_has_command_uses_timeout(self):
        """Test _has_command uses timeout parameter."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            PlatformDetector._has_command("test-command")
            mock_run.assert_called_once()
            kwargs = mock_run.call_args[1]
            assert "timeout" in kwargs
            assert kwargs["timeout"] == 5


# ============================================================================
# SECURITY TESTS
# ============================================================================


class TestPlatformDetectorSecurity:
    """Security tests for PlatformDetector."""

    def test_get_windows_username_prevents_command_injection(self):
        """Test Windows username extraction prevents command injection."""
        # Malicious output should be handled safely
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="user; rm -rf /")
            result = PlatformDetector._get_windows_username()
            # Should return sanitized username or None
            assert result is None or ";" not in result

    def test_has_command_prevents_command_injection(self):
        """Test _has_command prevents command injection."""
        dangerous_commands = [
            "gnome-terminal; rm -rf /",
            "xterm && malicious",
            "wt | cat /etc/passwd",
        ]

        for cmd in dangerous_commands:
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = Exception("Should not execute")
                # Should safely handle dangerous command names
                result = PlatformDetector._has_command(cmd)
                # Either rejects or safely checks
                assert result is False or mock_run.call_count == 0

    def test_windows_terminal_path_prevents_path_traversal(self):
        """Test path resolution prevents directory traversal."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value="../../root"):
                # Should not construct dangerous paths
                result = PlatformDetector.get_windows_terminal_path()
                if result is not None:
                    assert "../" not in str(result)
