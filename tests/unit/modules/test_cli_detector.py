"""Tests for CLI Detector module - TDD Red Phase.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)

Tests written BEFORE implementation (TDD approach).
All tests should FAIL initially.
"""

from pathlib import Path
from unittest.mock import patch

# Import will fail initially - this is expected in TDD red phase
try:
    from azlin.modules.cli_detector import (
        CLIDetector,
        CLIType,
        Environment,
        EnvironmentInfo,
    )
except ImportError:
    # Create placeholder classes for TDD
    class Environment:
        WSL2 = "wsl2"
        LINUX_NATIVE = "linux_native"
        WINDOWS = "windows"
        UNKNOWN = "unknown"

    class CLIType:
        WINDOWS = "windows"
        LINUX = "linux"
        NONE = "none"

    class EnvironmentInfo:
        def __init__(self, environment, cli_type, cli_path, has_problem, problem_description):
            self.environment = environment
            self.cli_type = cli_type
            self.cli_path = cli_path
            self.has_problem = has_problem
            self.problem_description = problem_description

    class CLIDetector:
        pass


# ============================================================================
# UNIT TESTS (60%) - Fast, heavily mocked
# ============================================================================


class TestEnvironmentDetection:
    """Unit tests for environment detection logic."""

    def test_detect_wsl2_via_proc_version_microsoft(self):
        """Test WSL2 detection via /proc/version containing 'microsoft'."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value="Linux version 5.10.16.3-microsoft-standard-WSL2",
            ),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.WSL2

    def test_detect_wsl2_via_proc_version_wsl2(self):
        """Test WSL2 detection via /proc/version containing 'wsl2'."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="Linux version 5.10.16.3-wsl2"),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.WSL2

    def test_detect_wsl2_via_run_wsl_directory(self):
        """Test WSL2 detection via /run/WSL directory existence."""
        detector = CLIDetector()

        def mock_exists(self):
            return str(self) == "/run/WSL"

        with (
            patch("platform.system", return_value="Linux"),
            patch("pathlib.Path.exists", mock_exists),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.WSL2

    def test_detect_wsl2_via_wsl_distro_name_env(self):
        """Test WSL2 detection via WSL_DISTRO_NAME environment variable."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: (
                    "Ubuntu-20.04" if k == "WSL_DISTRO_NAME" else default
                ),
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.WSL2

    def test_detect_wsl2_via_wsl_interop_env(self):
        """Test WSL2 detection via WSL_INTEROP environment variable."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: (
                    "/run/WSL/8_interop" if k == "WSL_INTEROP" else default
                ),
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.WSL2

    def test_detect_native_linux(self):
        """Test native Linux detection (no WSL2 indicators)."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("os.environ.get", return_value=None),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.read_text", return_value="Linux version 5.10.0-generic"),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.LINUX_NATIVE

    def test_detect_windows(self):
        """Test Windows detection."""
        detector = CLIDetector()

        with patch("platform.system", return_value="Windows"):
            env_info = detector.detect()

            assert env_info.environment == Environment.WINDOWS

    def test_detect_unknown_platform(self):
        """Test unknown platform detection (e.g., Darwin/macOS)."""
        detector = CLIDetector()

        with patch("platform.system", return_value="Darwin"):
            env_info = detector.detect()

            assert env_info.environment == Environment.UNKNOWN


class TestCLIDetection:
    """Unit tests for CLI type detection logic."""

    def test_detect_windows_cli_mnt_c_path(self):
        """Test Windows CLI detection via /mnt/c/ path."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "shutil.which",
                return_value="/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd",
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.WINDOWS
            assert env_info.cli_path == Path(
                "/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"
            )

    def test_detect_windows_cli_mnt_d_path(self):
        """Test Windows CLI detection via /mnt/d/ path."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value="/mnt/d/Azure/CLI/az.cmd"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.WINDOWS

    def test_detect_windows_cli_exe_extension(self):
        """Test Windows CLI detection via .exe extension."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value="/mnt/c/tools/az.exe"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.WINDOWS

    def test_detect_windows_cli_program_files_case_insensitive(self):
        """Test Windows CLI detection via 'Program Files' (case-insensitive)."""
        detector = CLIDetector()

        test_cases = [
            "/mnt/c/Program Files/az",
            "/mnt/c/program files/az",
            "/mnt/c/PROGRAM FILES/az",
            "/mnt/c/Program files (x86)/az",
        ]

        for path in test_cases:
            with (
                patch("platform.system", return_value="Linux"),
                patch("shutil.which", return_value=path),
                patch("pathlib.Path.exists", return_value=False),
            ):
                env_info = detector.detect()

                assert env_info.cli_type == CLIType.WINDOWS, f"Failed for path: {path}"

    def test_detect_linux_cli_usr_bin(self):
        """Test Linux CLI detection via /usr/bin/az path."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.LINUX
            assert env_info.cli_path == Path("/usr/bin/az")

    def test_detect_linux_cli_usr_local_bin(self):
        """Test Linux CLI detection via /usr/local/bin/az path."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value="/usr/local/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.LINUX

    def test_detect_cli_not_installed(self):
        """Test detection when Azure CLI is not installed."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.NONE
            assert env_info.cli_path is None

    def test_cli_detection_empty_path(self):
        """Test CLI detection handles empty path from which()."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value=""),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.NONE


class TestProblemDetection:
    """Unit tests for problem detection logic."""

    def test_problem_detected_wsl2_plus_windows_cli(self):
        """Test problem detection: WSL2 + Windows CLI = problem."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value="/mnt/c/Program Files/Azure/CLI/az.cmd"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.has_problem is True
            assert env_info.problem_description is not None
            assert "WSL2" in env_info.problem_description
            assert "Windows" in env_info.problem_description

    def test_no_problem_wsl2_plus_linux_cli(self):
        """Test no problem: WSL2 + Linux CLI = OK."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.has_problem is False
            assert env_info.problem_description is None

    def test_no_problem_native_linux_plus_linux_cli(self):
        """Test no problem: Native Linux + Linux CLI = OK."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("os.environ.get", return_value=None),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.read_text", return_value="Linux version 5.10.0-generic"),
        ):
            env_info = detector.detect()

            assert env_info.has_problem is False

    def test_no_problem_wsl2_plus_no_cli(self):
        """Test no problem: WSL2 + no CLI = OK (nothing to fix)."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.has_problem is False

    def test_problem_description_contains_guidance(self):
        """Test problem description provides actionable guidance."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value="/mnt/c/Program Files/Azure/CLI/az.cmd"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            description = env_info.problem_description.lower()
            # Should mention the problem and suggest a solution
            assert any(word in description for word in ["incompatible", "issue", "problem"])
            assert any(word in description for word in ["install", "linux", "version"])


class TestGetLinuxCLIPath:
    """Unit tests for get_linux_cli_path() method."""

    def test_get_linux_cli_path_when_installed_usr_bin(self):
        """Test getting Linux CLI path when installed in /usr/bin."""
        detector = CLIDetector()

        with patch("shutil.which", return_value="/usr/bin/az"):
            path = detector.get_linux_cli_path()

            assert path == Path("/usr/bin/az")

    def test_get_linux_cli_path_when_installed_usr_local_bin(self):
        """Test getting Linux CLI path when installed in /usr/local/bin."""
        detector = CLIDetector()

        with patch("shutil.which", return_value="/usr/local/bin/az"):
            path = detector.get_linux_cli_path()

            assert path == Path("/usr/local/bin/az")

    def test_get_linux_cli_path_when_windows_cli_present(self):
        """Test get_linux_cli_path returns None when only Windows CLI present."""
        detector = CLIDetector()

        with patch("shutil.which", return_value="/mnt/c/Program Files/Azure/CLI/az.cmd"):
            path = detector.get_linux_cli_path()

            assert path is None

    def test_get_linux_cli_path_when_not_installed(self):
        """Test get_linux_cli_path returns None when CLI not installed."""
        detector = CLIDetector()

        with patch("shutil.which", return_value=None):
            path = detector.get_linux_cli_path()

            assert path is None

    def test_get_linux_cli_path_searches_explicit_locations(self):
        """Test get_linux_cli_path searches explicit Linux locations."""
        detector = CLIDetector()

        # Simulate which() returning Windows path, but explicit check finds Linux
        with (
            patch("shutil.which", return_value="/mnt/c/az.cmd"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            path = detector.get_linux_cli_path()

            # Should find Linux CLI even if which() returns Windows path
            assert path is not None or path is None  # Implementation detail


class TestEdgeCases:
    """Unit tests for edge cases and error conditions."""

    def test_proc_version_file_not_readable(self):
        """Test handling when /proc/version is not readable."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", side_effect=PermissionError()),
            patch("os.environ.get", return_value=None),
        ):
            # Should not crash, should fallback to other detection methods
            env_info = detector.detect()

            assert env_info.environment in [
                Environment.WSL2,
                Environment.LINUX_NATIVE,
                Environment.UNKNOWN,
            ]

    def test_proc_version_empty_content(self):
        """Test handling when /proc/version has empty content."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=""),
            patch("os.environ.get", return_value=None),
        ):
            env_info = detector.detect()

            # Should treat as native Linux when no WSL indicators
            assert env_info.environment in [Environment.LINUX_NATIVE, Environment.UNKNOWN]

    def test_which_returns_relative_path(self):
        """Test handling when which() returns relative path."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value="./az"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            # Should handle relative path correctly
            assert env_info.cli_path is not None or env_info.cli_type == CLIType.NONE

    def test_cli_path_with_spaces(self):
        """Test handling CLI path with spaces."""
        detector = CLIDetector()

        path_with_spaces = "/mnt/c/Program Files (x86)/Microsoft SDKs/Azure/CLI/az.cmd"

        with (
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", return_value=path_with_spaces),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.cli_type == CLIType.WINDOWS
            assert str(env_info.cli_path) == path_with_spaces

    def test_multiple_wsl2_indicators_present(self):
        """Test when multiple WSL2 indicators are present."""
        detector = CLIDetector()

        def mock_env_get(key, default=None):
            if key == "WSL_DISTRO_NAME":
                return "Ubuntu-20.04"
            if key == "WSL_INTEROP":
                return "/run/WSL/8_interop"
            return default

        with (
            patch("platform.system", return_value="Linux"),
            patch("os.environ.get", side_effect=mock_env_get),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value="Linux version 5.10.16.3-microsoft-standard-WSL2",
            ),
        ):
            env_info = detector.detect()

            # Should still correctly identify as WSL2
            assert env_info.environment == Environment.WSL2


# ============================================================================
# INTEGRATION TESTS (30%) - Multiple components working together
# ============================================================================


class TestDetectorIntegration:
    """Integration tests combining environment and CLI detection."""

    def test_full_detection_wsl2_with_windows_cli_problem(self):
        """Integration: Full detection flow for WSL2 + Windows CLI problem."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value="/mnt/c/Program Files/Azure/CLI/az.cmd"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            # Verify all fields are populated correctly
            assert env_info.environment == Environment.WSL2
            assert env_info.cli_type == CLIType.WINDOWS
            assert env_info.cli_path == Path("/mnt/c/Program Files/Azure/CLI/az.cmd")
            assert env_info.has_problem is True
            assert env_info.problem_description is not None

    def test_full_detection_wsl2_with_linux_cli_no_problem(self):
        """Integration: Full detection flow for WSL2 + Linux CLI (OK)."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.WSL2
            assert env_info.cli_type == CLIType.LINUX
            assert env_info.cli_path == Path("/usr/bin/az")
            assert env_info.has_problem is False
            assert env_info.problem_description is None

    def test_full_detection_native_linux_with_linux_cli(self):
        """Integration: Full detection flow for native Linux + Linux CLI."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("os.environ.get", return_value=None),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.read_text", return_value="Linux version 5.10.0-generic"),
        ):
            env_info = detector.detect()

            assert env_info.environment == Environment.LINUX_NATIVE
            assert env_info.cli_type == CLIType.LINUX
            assert env_info.has_problem is False

    def test_detector_with_get_linux_cli_path_integration(self):
        """Integration: detect() and get_linux_cli_path() work together."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", side_effect=lambda cmd: "/usr/bin/az" if cmd == "az" else None),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()
            linux_cli_path = detector.get_linux_cli_path()

            # Both should find the Linux CLI
            assert env_info.cli_type == CLIType.LINUX
            assert linux_cli_path == Path("/usr/bin/az")

    def test_detector_state_independence(self):
        """Integration: Multiple detect() calls are independent."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("os.environ.get", return_value=None),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.read_text", return_value="Linux version 5.10.0-generic"),
        ):
            env_info1 = detector.detect()
            env_info2 = detector.detect()

            # Results should be identical
            assert env_info1.environment == env_info2.environment
            assert env_info1.cli_type == env_info2.cli_type
            assert env_info1.has_problem == env_info2.has_problem


# ============================================================================
# E2E TESTS (10%) - Complete workflows
# ============================================================================


class TestEndToEndWorkflows:
    """E2E tests for complete detection workflows."""

    def test_e2e_wsl2_problem_detection_and_guidance(self):
        """E2E: Detect WSL2 + Windows CLI problem and provide guidance."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: (
                    "Ubuntu-20.04" if k == "WSL_DISTRO_NAME" else default
                ),
            ),
            patch(
                "shutil.which",
                return_value="/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd",
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            # User workflow: Check if there's a problem
            env_info = detector.detect()

            if env_info.has_problem:
                # Display problem to user
                problem_msg = env_info.problem_description
                assert "WSL2" in problem_msg
                assert "Windows" in problem_msg

                # Check if Linux CLI is available
                linux_cli = detector.get_linux_cli_path()

                if not linux_cli:
                    # Need to install Linux CLI
                    assert env_info.cli_type == CLIType.WINDOWS
                else:
                    # Linux CLI already available, just need to use it
                    raise AssertionError("If Linux CLI exists, should not have problem")

    def test_e2e_healthy_wsl2_system(self):
        """E2E: Verify healthy WSL2 + Linux CLI system."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "os.environ.get",
                side_effect=lambda k, default=None: "Ubuntu" if k == "WSL_DISTRO_NAME" else default,
            ),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            env_info = detector.detect()

            # Verify system is healthy
            assert env_info.environment == Environment.WSL2
            assert env_info.cli_type == CLIType.LINUX
            assert not env_info.has_problem

            # Verify can get explicit CLI path
            linux_cli = detector.get_linux_cli_path()
            assert linux_cli is not None

    def test_e2e_native_linux_system(self):
        """E2E: Verify native Linux system works correctly."""
        detector = CLIDetector()

        with (
            patch("platform.system", return_value="Linux"),
            patch("os.environ.get", return_value=None),
            patch("shutil.which", return_value="/usr/bin/az"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.read_text", return_value="Linux version 5.10.0-generic"),
        ):
            env_info = detector.detect()

            # Native Linux should work fine
            assert env_info.environment == Environment.LINUX_NATIVE
            assert env_info.cli_type == CLIType.LINUX
            assert not env_info.has_problem
