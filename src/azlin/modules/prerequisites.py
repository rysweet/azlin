"""
Prerequisites Checker Module

Verifies all required external tools are installed before operations.

Security Requirements:
- No credential storage
- All inputs validated
- Secure logging
- Read-only system checks
- No shell=True in subprocess calls
"""

import logging
import platform
import shutil
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class PrerequisiteResult:
    """Result of prerequisite checks."""

    all_available: bool
    missing: list[str]
    available: list[str]
    platform_name: str


class PrerequisiteError(Exception):
    """Raised when prerequisites are missing."""

    pass


class PrerequisiteChecker:
    """
    Check required external tools are installed.

    Required tools:
    - az (Azure CLI)
    - gh (GitHub CLI)
    - git
    - ssh
    - tmux (optional but recommended)
    """

    REQUIRED_TOOLS: ClassVar[list[str]] = ["az", "gh", "git", "ssh"]
    OPTIONAL_TOOLS: ClassVar[list[str]] = ["tmux"]

    @classmethod
    def check_tool(cls, tool_name: str) -> bool:
        """
        Check if a single tool is available in PATH.

        Args:
            tool_name: Name of the tool to check

        Returns:
            bool: True if tool is available

        Security: Uses shutil.which (safe, no subprocess)
        """
        result = shutil.which(tool_name)
        if result:
            logger.debug(f"Found {tool_name} at {result}")
            return True
        logger.debug(f"Tool not found: {tool_name}")
        return False

    @classmethod
    def check_all(cls) -> PrerequisiteResult:
        """
        Check all prerequisites and return comprehensive result.

        Returns:
            PrerequisiteResult: Detailed check results

        Example:
            >>> result = PrerequisiteChecker.check_all()
            >>> if not result.all_available:
            ...     print(f"Missing: {result.missing}")
        """
        missing: list[str] = []
        available: list[str] = []

        # Check required tools
        for tool in cls.REQUIRED_TOOLS:
            if cls.check_tool(tool):
                available.append(tool)
            else:
                missing.append(tool)

        # Check optional tools (don't fail, just warn)
        for tool in cls.OPTIONAL_TOOLS:
            if cls.check_tool(tool):
                available.append(tool)
            else:
                logger.warning(f"Optional tool not found: {tool}")

        # Detect platform
        platform_name = cls.detect_platform()

        result = PrerequisiteResult(
            all_available=(len(missing) == 0),
            missing=missing,
            available=available,
            platform_name=platform_name,
        )

        if result.all_available:
            logger.info(f"All prerequisites available ({platform_name})")
        else:
            logger.error(f"Missing prerequisites: {', '.join(missing)}")

        return result

    @classmethod
    def detect_platform(cls) -> str:
        """
        Detect the operating system platform.

        Returns:
            str: Platform name (macos, linux, wsl, windows, unknown)

        Security: Uses platform.system() (safe)
        """
        system = platform.system().lower()

        if system == "darwin":
            return "macos"
        if system == "linux":
            # Check if WSL
            if cls._is_wsl():
                return "wsl"
            return "linux"
        if system == "windows":
            return "windows"
        return "unknown"

    @classmethod
    def _is_wsl(cls) -> bool:
        """
        Check if running in Windows Subsystem for Linux.

        Returns:
            bool: True if WSL detected
        """
        try:
            with open("/proc/version") as f:
                version = f.read().lower()
                return "microsoft" in version or "wsl" in version
        except (FileNotFoundError, PermissionError) as e:
            logger.debug(f"Failed to check for WSL: {e}")
            return False

    @classmethod
    def format_missing_message(cls, missing: list[str], platform_name: str) -> str:
        """
        Format user-friendly installation instructions for missing tools.

        Args:
            missing: List of missing tool names
            platform_name: Platform name from detect_platform()

        Returns:
            str: Formatted installation instructions

        Example:
            >>> msg = PrerequisiteChecker.format_missing_message(
            ...     ["az", "gh"], "macos"
            ... )
            >>> print(msg)
        """
        if not missing:
            return "All prerequisites are installed."

        lines: list[str] = ["Missing required tools:", ""]
        lines.extend(f"  - {tool}" for tool in missing)
        lines.append("")
        lines.append(f"Platform: {platform_name}")
        lines.append("")
        lines.append("Installation instructions:")
        lines.append("")

        # Platform-specific installation instructions
        if platform_name == "macos":
            lines.extend(cls._format_macos_instructions(missing))
        elif platform_name == "linux":
            lines.extend(cls._format_linux_instructions(missing))
        elif platform_name == "wsl":
            lines.extend(cls._format_wsl_instructions(missing))
        elif platform_name == "windows":
            lines.extend(cls._format_windows_instructions(missing))
        else:
            lines.extend(cls._format_generic_instructions(missing))

        return "\n".join(lines)

    @classmethod
    def _format_macos_instructions(cls, missing: list[str]) -> list[str]:
        """Format installation instructions for macOS."""
        instructions: list[str] = []

        if "az" in missing:
            instructions.extend(["Install Azure CLI:", "  brew install azure-cli", ""])

        if "gh" in missing:
            instructions.extend(["Install GitHub CLI:", "  brew install gh", ""])

        if "git" in missing:
            instructions.extend(["Install Git:", "  brew install git", ""])

        if "ssh" in missing:
            instructions.extend(["Install OpenSSH:", "  brew install openssh", ""])

        if "tmux" in missing:
            instructions.extend(["Install tmux (optional):", "  brew install tmux", ""])

        instructions.append("After installing, run 'azlin' again.")
        return instructions

    @classmethod
    def _format_linux_instructions(cls, missing: list[str]) -> list[str]:
        """Format installation instructions for Linux."""
        instructions: list[str] = []

        if "az" in missing:
            instructions.extend(
                [
                    "Install Azure CLI:",
                    "  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash",
                    "",
                ]
            )

        if "gh" in missing:
            instructions.extend(
                [
                    "Install GitHub CLI:",
                    "  See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md",
                    "",
                ]
            )

        if "git" in missing:
            instructions.extend(
                ["Install Git:", "  sudo apt-get update && sudo apt-get install git", ""]
            )

        if "ssh" in missing:
            instructions.extend(["Install OpenSSH:", "  sudo apt-get install openssh-client", ""])

        if "tmux" in missing:
            instructions.extend(["Install tmux (optional):", "  sudo apt-get install tmux", ""])

        instructions.append("After installing, run 'azlin' again.")
        return instructions

    @classmethod
    def _format_wsl_instructions(cls, missing: list[str]) -> list[str]:
        """Format installation instructions for WSL."""
        # WSL uses same package manager as Linux
        return cls._format_linux_instructions(missing)

    @classmethod
    def _format_windows_instructions(cls, missing: list[str]) -> list[str]:
        """Format installation instructions for Windows."""
        instructions: list[str] = []

        if "az" in missing:
            instructions.extend(
                ["Install Azure CLI:", "  Download from: https://aka.ms/installazurecliwindows", ""]
            )

        if "gh" in missing:
            instructions.extend(["Install GitHub CLI:", "  winget install GitHub.cli", ""])

        if "git" in missing:
            instructions.extend(
                ["Install Git:", "  Download from: https://git-scm.com/download/win", ""]
            )

        if "ssh" in missing:
            instructions.extend(
                ["Install OpenSSH:", "  Already included in Windows 10+. Check: ssh -V", ""]
            )

        if "tmux" in missing:
            instructions.extend(
                [
                    "Note: tmux is not natively available on Windows.",
                    "  Consider using WSL for full Linux compatibility.",
                    "",
                ]
            )

        instructions.append("After installing, run 'azlin' again.")
        return instructions

    @classmethod
    def _format_generic_instructions(cls, missing: list[str]) -> list[str]:
        """Format generic installation instructions for unknown platforms."""
        instructions: list[str] = ["Please install the following tools:", ""]

        for tool in missing:
            if tool == "az":
                instructions.append(
                    "  - Azure CLI: https://docs.microsoft.com/cli/azure/install-azure-cli"
                )
            elif tool == "gh":
                instructions.append("  - GitHub CLI: https://cli.github.com/")
            elif tool == "git":
                instructions.append("  - Git: https://git-scm.com/downloads")
            elif tool == "ssh":
                instructions.append("  - OpenSSH: https://www.openssh.com/")
            elif tool == "tmux":
                instructions.append("  - tmux: https://github.com/tmux/tmux")

        instructions.append("")
        instructions.append("After installing, run 'azlin' again.")
        return instructions


# Convenience function for CLI use
def check_prerequisites() -> PrerequisiteResult:
    """
    Check all prerequisites (convenience function).

    Returns:
        PrerequisiteResult: Check results

    Example:
        >>> from azlin.modules.prerequisites import check_prerequisites
        >>> result = check_prerequisites()
        >>> if not result.all_available:
        ...     print(f"Missing: {result.missing}")
    """
    return PrerequisiteChecker.check_all()
