"""Interactive Azure CLI installation for WSL2.

Philosophy:
- Single responsibility: Install Linux Azure CLI
- Standard library only (no external dependencies)
- Self-contained and regeneratable
- Zero-BS: No stubs or placeholders

Public API (the "studs"):
    InstallStatus: Installation status enum
    InstallResult: Installation result dataclass
    CLIInstaller: Main installer class
"""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .cli_detector import CLIDetector


class InstallStatus(Enum):
    """Installation status."""

    SUCCESS = "success"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ALREADY_INSTALLED = "already_installed"


@dataclass
class InstallResult:
    """Result of installation attempt."""

    status: InstallStatus
    cli_path: Path | None = None
    error_message: str | None = None


class CLIInstaller:
    """Handles interactive Linux Azure CLI installation."""

    INSTALL_SCRIPT_URL = "https://aka.ms/InstallAzureCLIDeb"

    def prompt_install(self) -> bool:
        """
        Prompt user for installation consent.

        Returns:
            True if user consents, False otherwise

        Example:
            >>> installer = CLIInstaller()
            >>> if installer.prompt_install():
            ...     print("User consented")
        """
        print("\n" + "=" * 70)
        print("Azure CLI Installation")
        print("=" * 70)
        print("\nProblem:")
        print("  You're running WSL2 with the Windows version of Azure CLI.")
        print("  This is incompatible with certain operations like 'az network bastion tunnel'.")
        print("\nSolution:")
        print("  Install the Linux version of Azure CLI in WSL2.")
        print("\nDetails:")
        print(f"  - Script: {self.INSTALL_SCRIPT_URL}")
        print("  - Requires: sudo (you'll be prompted for password)")
        print("  - Time: ~2-3 minutes")
        print("\n" + "=" * 70)

        try:
            while True:
                response = input("\nInstall Linux Azure CLI now? [y/N]: ").strip().lower()

                if response in ["y", "yes"]:
                    return True
                if response in ["n", "no", ""]:
                    return False
                print("Invalid input. Please enter 'y' or 'n'.")

        except (KeyboardInterrupt, EOFError):
            # User pressed Ctrl+C or input stream closed
            print("\n\nInstallation cancelled.")
            return False

    def install(self) -> InstallResult:
        """
        Execute Linux Azure CLI installation.

        Returns:
            InstallResult with installation outcome

        Example:
            >>> installer = CLIInstaller()
            >>> result = installer.install()
            >>> if result.status == InstallStatus.SUCCESS:
            ...     print(f"Installed at: {result.cli_path}")
        """
        # Check if already installed
        try:
            detector = CLIDetector()
            linux_cli = detector.get_linux_cli_path()

            if linux_cli:
                return InstallResult(
                    status=InstallStatus.ALREADY_INSTALLED,
                    cli_path=linux_cli,
                    error_message=None,
                )
        except Exception as e:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message=f"Error checking existing installation: {e!s}",
            )

        # Prompt user
        if not self.prompt_install():
            return InstallResult(
                status=InstallStatus.CANCELLED,
                cli_path=None,
                error_message=None,
            )

        # Download and execute installation script
        print("\nDownloading installation script...")

        try:
            # Download script
            download_result = subprocess.run(
                ["curl", "-sL", self.INSTALL_SCRIPT_URL],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
            )

            if download_result.returncode != 0:
                return InstallResult(
                    status=InstallStatus.FAILED,
                    cli_path=None,
                    error_message=f"Failed to download installation script: {download_result.stderr}",
                )

            script_content = download_result.stdout

        except subprocess.TimeoutExpired:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message="Download timeout after 300 seconds. Check your internet connection.",
            )
        except Exception as e:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message=f"Network error during download: {e!s}",
            )

        # Execute installation script with sudo
        print("Installing Azure CLI (you may be prompted for sudo password)...")

        try:
            install_result = subprocess.run(
                ["sudo", "bash", "-c", script_content],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
            )

            if install_result.returncode != 0:
                error_msg = install_result.stderr or install_result.stdout
                if "permission" in error_msg.lower() or "denied" in error_msg.lower():
                    return InstallResult(
                        status=InstallStatus.FAILED,
                        cli_path=None,
                        error_message="Permission denied. Make sure you have sudo access.",
                    )
                return InstallResult(
                    status=InstallStatus.FAILED,
                    cli_path=None,
                    error_message=f"Installation script failed: {error_msg}",
                )

        except subprocess.TimeoutExpired:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message="Installation timeout after 300 seconds",
            )
        except OSError as e:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message=f"Command not found or OS error: {e!s}",
            )
        except Exception as e:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message=f"Error during installation: {e!s}",
            )

        # Verify installation
        print("Verifying installation...")

        try:
            detector = CLIDetector()
            linux_cli = detector.get_linux_cli_path()

            if linux_cli:
                print("✓ Installation successful!")

                # Auto-login using tenant from Windows CLI if available
                self._auto_login_with_tenant(linux_cli)

                return InstallResult(
                    status=InstallStatus.SUCCESS,
                    cli_path=linux_cli,
                    error_message=None,
                )
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message="Installation completed but CLI verification failed. Azure CLI may not be in PATH.",
            )
        except Exception as e:
            return InstallResult(
                status=InstallStatus.FAILED,
                cli_path=None,
                error_message=f"Error verifying installation: {e!s}",
            )


    def _auto_login_with_tenant(self, linux_cli_path: Path) -> None:
        """Auto-login to Linux CLI using tenant from Windows CLI.

        If Windows CLI is authenticated, extracts tenant ID and uses it
        to streamline Linux CLI authentication.

        Args:
            linux_cli_path: Path to newly installed Linux CLI
        """
        print("\nChecking for existing Azure authentication...")

        try:
            # Try to get tenant from Windows CLI
            result = subprocess.run(
                ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                tenant_id = result.stdout.strip()
                print(f"✓ Found tenant ID from Windows CLI: {tenant_id}")
                print(f"\nTo authenticate Linux CLI with same tenant, run:")
                print(f"  {linux_cli_path} login --tenant {tenant_id}")
                print(f"\nOr run: {linux_cli_path} login (for interactive login)")
            else:
                print(f"\nTo authenticate Linux CLI, run:")
                print(f"  {linux_cli_path} login")

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # Windows CLI not available or not authenticated - just show basic login command
            print(f"\nTo authenticate Linux CLI, run:")
            print(f"  {linux_cli_path} login")


__all__ = ["CLIInstaller", "InstallResult", "InstallStatus"]
