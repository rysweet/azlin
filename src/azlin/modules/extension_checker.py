"""Azure CLI extension checker module.

Verifies required Azure CLI extensions are installed and offers
to install missing ones. Required for Bastion operations which
depend on both 'ssh' and 'bastion' extensions.

Philosophy:
- Single responsibility: Check and install Azure CLI extensions
- Standard library only (no external dependencies)
- Self-contained and regeneratable

Public API (the "studs"):
    ExtensionStatus: Extension status enum
    ExtensionResult: Check result dataclass
    ExtensionChecker: Main checker class
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


class ExtensionStatus(Enum):
    """Extension installation status."""

    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    INSTALL_SUCCESS = "install_success"
    INSTALL_FAILED = "install_failed"


@dataclass
class ExtensionResult:
    """Result of extension check or installation."""

    extension_name: str
    status: ExtensionStatus
    version: str | None = None
    error_message: str | None = None


class ExtensionChecker:
    """Check and install required Azure CLI extensions.

    Required extensions for azlin Bastion operations:
    - ssh: SSH connectivity through Azure Bastion
    - bastion: Azure Bastion tunnel management

    Args:
        cli_path: Explicit path to Azure CLI binary (for WSL2 compatibility).
                  If None, uses 'az' from PATH.

    Example:
        >>> checker = ExtensionChecker()
        >>> results = checker.check_all_required()
        >>> missing = [n for n, r in results.items()
        ...           if r.status == ExtensionStatus.NOT_INSTALLED]
    """

    REQUIRED_EXTENSIONS: ClassVar[list[str]] = ["ssh", "bastion"]

    # Timeouts
    CHECK_TIMEOUT = 10  # seconds
    INSTALL_TIMEOUT = 120  # seconds

    def __init__(self, cli_path: Path | None = None):
        self._cli_cmd = str(cli_path) if cli_path else "az"

    def check_extension(self, extension_name: str) -> ExtensionResult:
        """Check if a single Azure CLI extension is installed.

        Args:
            extension_name: Extension name (e.g., 'ssh', 'bastion')

        Returns:
            ExtensionResult with status and optional version

        Security: No shell=True, validated timeout
        """
        try:
            result = subprocess.run(
                [self._cli_cmd, "extension", "show", "--name", extension_name],
                capture_output=True,
                text=True,
                timeout=self.CHECK_TIMEOUT,
            )

            if result.returncode == 0:
                version = self._extract_version(result.stdout)
                logger.debug(
                    "Extension '%s' installed (version: %s)",
                    extension_name,
                    version or "unknown",
                )
                return ExtensionResult(
                    extension_name=extension_name,
                    status=ExtensionStatus.INSTALLED,
                    version=version,
                )

            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.NOT_INSTALLED,
            )

        except subprocess.TimeoutExpired:
            logger.debug("Timeout checking extension '%s'", extension_name)
            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.NOT_INSTALLED,
                error_message="Check timed out",
            )
        except FileNotFoundError:
            logger.debug("Azure CLI not found at '%s'", self._cli_cmd)
            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.NOT_INSTALLED,
                error_message=f"Azure CLI not found: {self._cli_cmd}",
            )
        except Exception as e:
            logger.debug("Error checking extension '%s': %s", extension_name, e)
            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.NOT_INSTALLED,
                error_message=str(e),
            )

    def check_all_required(self) -> dict[str, ExtensionResult]:
        """Check all required extensions.

        Returns:
            Dict mapping extension name to ExtensionResult
        """
        results = {}
        for ext_name in self.REQUIRED_EXTENSIONS:
            results[ext_name] = self.check_extension(ext_name)
        return results

    def install_extension(self, extension_name: str) -> ExtensionResult:
        """Install a single Azure CLI extension.

        Args:
            extension_name: Extension to install

        Returns:
            ExtensionResult with installation outcome
        """
        logger.info("Installing Azure CLI extension: %s", extension_name)

        try:
            result = subprocess.run(
                [self._cli_cmd, "extension", "add", "--name", extension_name, "--yes"],
                capture_output=True,
                text=True,
                timeout=self.INSTALL_TIMEOUT,
            )

            if result.returncode == 0:
                logger.info("Extension '%s' installed successfully", extension_name)
                return ExtensionResult(
                    extension_name=extension_name,
                    status=ExtensionStatus.INSTALL_SUCCESS,
                )

            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(
                "Failed to install extension '%s': %s", extension_name, error_msg
            )
            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.INSTALL_FAILED,
                error_message=error_msg,
            )

        except subprocess.TimeoutExpired:
            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.INSTALL_FAILED,
                error_message="Installation timed out after 120 seconds",
            )
        except Exception as e:
            return ExtensionResult(
                extension_name=extension_name,
                status=ExtensionStatus.INSTALL_FAILED,
                error_message=str(e),
            )

    def check_and_install_missing(self) -> dict[str, ExtensionResult]:
        """Check all required extensions and install any that are missing.

        Prompts the user once if any extensions are missing, then installs
        all missing extensions.

        Returns:
            Dict mapping extension name to final ExtensionResult
        """
        results = self.check_all_required()

        missing = [
            name
            for name, result in results.items()
            if result.status == ExtensionStatus.NOT_INSTALLED
        ]

        if not missing:
            return results

        # Prompt user once for all missing extensions
        if not self._prompt_install(missing):
            logger.info("Extension installation skipped by user")
            return results

        # Install all missing
        for ext_name in missing:
            install_result = self.install_extension(ext_name)
            results[ext_name] = install_result

        return results

    def _prompt_install(self, missing_extensions: list[str]) -> bool:
        """Prompt user to install missing extensions.

        Args:
            missing_extensions: List of missing extension names

        Returns:
            True if user accepts, False otherwise
        """
        ext_list = ", ".join(missing_extensions)
        print(
            f"\nAzure CLI extensions required for Bastion operations: {ext_list}"
        )
        print(f"Install command: az extension add --name <ext> --yes")

        try:
            response = input(f"\nInstall missing extensions now? [Y/n]: ").strip().lower()
            return response in ("y", "yes", "")
        except (KeyboardInterrupt, EOFError):
            print()
            return False

    @staticmethod
    def _extract_version(show_output: str) -> str | None:
        """Extract version from 'az extension show' JSON output."""
        try:
            data = json.loads(show_output)
            return data.get("version")
        except (json.JSONDecodeError, KeyError, TypeError):
            return None


__all__ = ["ExtensionChecker", "ExtensionResult", "ExtensionStatus"]
