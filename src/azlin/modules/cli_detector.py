"""Azure CLI and environment detection.

Philosophy:
- Single responsibility: Detect environment and CLI type
- Standard library only (no external dependencies)
- Self-contained and regeneratable
- Zero-BS: No stubs or placeholders

Public API (the "studs"):
    Environment: Environment type enum
    CLIType: CLI type enum
    EnvironmentInfo: Detection result dataclass
    CLIDetector: Main detector class
"""

import os
import platform
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Environment(Enum):
    """Environment types."""

    WSL2 = "wsl2"
    LINUX_NATIVE = "linux_native"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


class CLIType(Enum):
    """Azure CLI types."""

    WINDOWS = "windows"
    LINUX = "linux"
    NONE = "none"


@dataclass
class EnvironmentInfo:
    """Complete environment detection result."""

    environment: Environment
    cli_type: CLIType
    cli_path: Path | None
    has_problem: bool
    problem_description: str | None


class CLIDetector:
    """Detects runtime environment and Azure CLI installation."""

    # Standard Linux CLI installation locations
    LINUX_CLI_LOCATIONS = [
        Path("/usr/bin/az"),
        Path("/usr/local/bin/az"),
    ]

    def detect(self) -> EnvironmentInfo:
        """
        Perform complete detection of environment and CLI.

        Returns:
            EnvironmentInfo with all detection results

        Example:
            >>> detector = CLIDetector()
            >>> env_info = detector.detect()
            >>> print(env_info.environment)
        """
        # Detect environment
        environment = self._detect_environment()

        # Detect CLI type and path
        cli_type, cli_path = self._detect_cli()

        # Determine if there's a problem
        has_problem = environment == Environment.WSL2 and cli_type == CLIType.WINDOWS

        # Generate problem description if needed
        problem_description = None
        if has_problem:
            problem_description = (
                "WSL2 detected with Windows Azure CLI installation. "
                "The Windows CLI version is incompatible with WSL2 for certain operations "
                "(like 'az network bastion tunnel'). "
                "Installing the Linux version of Azure CLI is recommended for full compatibility."
            )

        return EnvironmentInfo(
            environment=environment,
            cli_type=cli_type,
            cli_path=cli_path,
            has_problem=has_problem,
            problem_description=problem_description,
        )

    def get_linux_cli_path(self) -> Path | None:
        """
        Get explicit path to Linux Azure CLI if installed.

        Returns:
            Path to Linux CLI binary, or None if not found

        Example:
            >>> detector = CLIDetector()
            >>> linux_cli = detector.get_linux_cli_path()
            >>> if linux_cli:
            ...     print(f"Linux CLI at: {linux_cli}")
        """
        # Try to find az command
        az_path = shutil.which("az")

        if not az_path:
            # Not found via PATH, try explicit locations
            for location in self.LINUX_CLI_LOCATIONS:
                if location.exists() and location.is_file():
                    return location
            return None

        # Check if it's a Linux installation
        if self._is_windows_cli_path(az_path):
            # It's a Windows CLI, check explicit Linux locations
            for location in self.LINUX_CLI_LOCATIONS:
                if location.exists() and location.is_file():
                    return location
            return None

        # It's a Linux CLI
        return Path(az_path)

    def _detect_environment(self) -> Environment:
        """Detect the runtime environment."""
        system = platform.system()

        if system == "Windows":
            return Environment.WINDOWS

        if system == "Linux":
            # Check for WSL2 indicators
            if self._is_wsl2():
                return Environment.WSL2
            return Environment.LINUX_NATIVE

        # Darwin (macOS), FreeBSD, etc.
        return Environment.UNKNOWN

    def _is_wsl2(self) -> bool:
        """Check if running in WSL2."""
        # Method 1: Check /proc/version for "microsoft" or "wsl2"
        try:
            proc_version_path = Path("/proc/version")
            if proc_version_path.exists():
                content = proc_version_path.read_text().lower()
                if content and ("microsoft" in content or "wsl2" in content):
                    return True
                # If proc_version exists but has no WSL indicators, check env vars only
                if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
                    return True
                return False
        except (PermissionError, OSError):
            # Can't read /proc/version, continue to other methods
            pass

        # Method 2: Check for /run/WSL directory
        if Path("/run/WSL").exists():
            return True

        # Method 3: Check environment variables
        if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
            return True

        return False

    def _detect_cli(self) -> tuple[CLIType, Path | None]:
        """Detect Azure CLI type and path."""
        az_path = shutil.which("az")

        if not az_path or az_path == "":
            return CLIType.NONE, None

        # Check if it's a Windows CLI
        if self._is_windows_cli_path(az_path):
            return CLIType.WINDOWS, Path(az_path)

        # It's a Linux CLI
        return CLIType.LINUX, Path(az_path)

    def _is_windows_cli_path(self, path: str) -> bool:
        """Check if path indicates Windows Azure CLI."""
        path_lower = path.lower()

        # Check for /mnt/c/, /mnt/d/, etc.
        if path_lower.startswith("/mnt/"):
            return True

        # Check for .exe extension
        if path_lower.endswith(".exe"):
            return True

        # Check for "program files" (case-insensitive)
        if "program files" in path_lower:
            return True

        return False


__all__ = ["CLIDetector", "CLIType", "Environment", "EnvironmentInfo"]
