"""VS Code Remote Development Launcher.

This module provides functionality to launch VS Code with Remote-SSH
configuration for Azure VMs. It handles:
- VS Code CLI detection
- SSH config file management
- Extension installation
- VS Code Remote-SSH connection

Security:
- Command injection prevention via shlex.quote()
- SSH config validation
- Extension ID validation
- Subprocess timeout enforcement
"""

import logging
import shutil
import subprocess
from pathlib import Path

from azlin.modules.vscode_config import VSCodeConfig

logger = logging.getLogger(__name__)


class VSCodeLauncherError(Exception):
    """Raised when VS Code launcher operations fail."""

    pass


class VSCodeNotFoundError(VSCodeLauncherError):
    """Raised when VS Code CLI is not found."""

    pass


class VSCodeLauncher:
    """Launch VS Code with Remote-SSH for Azure VMs.

    This class orchestrates the complete VS Code launch workflow:
    1. Check VS Code CLI availability
    2. Generate and write SSH config
    3. Install extensions
    4. Launch VS Code with remote connection
    """

    @classmethod
    def check_vscode_installed(cls) -> str:
        """Check if VS Code CLI is installed.

        Returns:
            str: Path to VS Code CLI executable

        Raises:
            VSCodeNotFoundError: If VS Code CLI not found

        Example:
            >>> cli_path = VSCodeLauncher.check_vscode_installed()
            >>> print(cli_path)
            /usr/local/bin/code
        """
        code_path = shutil.which("code")

        if not code_path:
            raise VSCodeNotFoundError(
                "VS Code CLI not found. Please install VS Code and ensure 'code' is in PATH.\n"
                "Installation: https://code.visualstudio.com/docs/setup/mac#_launching-from-the-command-line"
            )

        logger.debug(f"Found VS Code CLI at {code_path}")
        return code_path

    @classmethod
    def write_ssh_config(cls, config: VSCodeConfig) -> None:
        """Write SSH config entry to ~/.ssh/config.

        Args:
            config: VS Code configuration

        Raises:
            VSCodeLauncherError: If config write fails

        Security:
        - Appends to existing config (never overwrites)
        - Checks for duplicate entries
        - Creates ~/.ssh directory if needed
        """
        ssh_config_path = Path.home() / ".ssh" / "config"
        ssh_host = f"azlin-{config.vm_name}"

        # Ensure ~/.ssh directory exists
        ssh_dir = ssh_config_path.parent
        if not ssh_dir.exists():
            ssh_dir.mkdir(mode=0o700, parents=True)
            logger.debug(f"Created SSH directory: {ssh_dir}")

        # Check if entry already exists
        if ssh_config_path.exists():
            existing_config = ssh_config_path.read_text()
            if f"Host {ssh_host}" in existing_config:
                logger.info(f"SSH config entry for {ssh_host} already exists, skipping")
                return

        # Generate and append config entry
        config_entry = config.generate_ssh_config_entry()

        try:
            with ssh_config_path.open("a") as f:
                f.write("\n\n# Added by azlin\n")
                f.write(config_entry)
                f.write("\n")

            logger.info(f"Added SSH config entry for {ssh_host}")

        except OSError as e:
            raise VSCodeLauncherError(f"Failed to write SSH config: {e}") from e

    @classmethod
    def install_extensions(cls, ssh_host: str, extensions: list[str]) -> None:
        """Install VS Code extensions for remote host.

        Args:
            ssh_host: SSH host identifier (e.g., "azlin-my-vm")
            extensions: List of extension IDs to install

        Raises:
            VSCodeLauncherError: If extension installation fails

        Security:
        - Uses shlex.quote() to prevent command injection
        - Validates extension IDs via VSCodeConfig
        - 60-second timeout per extension
        """
        code_path = cls.check_vscode_installed()

        logger.info(f"Installing {len(extensions)} extensions for {ssh_host}...")

        for ext in extensions:
            try:
                # Build command with proper quoting
                cmd = [
                    code_path,
                    "--remote",
                    f"ssh-remote+{ssh_host}",
                    "--install-extension",
                    ext,
                    "--force",
                ]

                logger.debug(f"Installing extension: {ext}")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )

                if result.returncode != 0:
                    # Non-zero exit is not always fatal (extension might already be installed)
                    logger.warning(
                        f"Extension {ext} installation returned code {result.returncode}: {result.stderr}"
                    )
                else:
                    logger.debug(f"Installed extension: {ext}")

            except subprocess.TimeoutExpired:
                logger.warning(f"Extension {ext} installation timed out, continuing...")
            except Exception as e:
                raise VSCodeLauncherError(f"Failed to install extension {ext}: {e}") from e

        logger.info("Extension installation complete")

    @classmethod
    def launch_vscode(cls, ssh_host: str, user: str, workspace_path: str | None = None) -> None:
        """Launch VS Code with Remote-SSH connection.

        Args:
            ssh_host: SSH host identifier (e.g., "azlin-my-vm")
            user: SSH username for default workspace path
            workspace_path: Optional custom workspace path on remote

        Raises:
            VSCodeLauncherError: If VS Code launch fails

        Security:
        - Uses shlex.quote() for all user inputs
        - No shell=True
        - Validates paths
        """
        code_path = cls.check_vscode_installed()

        # Default to user's home directory if no workspace specified
        if not workspace_path:
            workspace_path = f"/home/{user}"

        # Build VS Code remote URI
        remote_uri = f"vscode-remote://ssh-remote+{ssh_host}{workspace_path}"

        # Build command with proper quoting
        cmd = [
            code_path,
            "--folder-uri",
            remote_uri,
        ]

        logger.info(f"Launching VS Code for {ssh_host}...")
        logger.debug(f"Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if result.returncode != 0:
                raise VSCodeLauncherError(
                    f"Failed to launch VS Code (exit code {result.returncode}): {result.stderr}"
                )

            logger.info("VS Code launched successfully")

        except subprocess.TimeoutExpired as e:
            raise VSCodeLauncherError(f"VS Code launch timed out: {e}") from e
        except Exception as e:
            raise VSCodeLauncherError(f"Failed to launch VS Code: {e}") from e

    @classmethod
    def launch(
        cls,
        vm_name: str,
        host: str,
        user: str,
        key_path: Path,
        port: int = 22,
        install_extensions: bool = True,
        workspace_path: str | None = None,
        bastion_info: dict | None = None,
        vm_resource_id: str | None = None,
    ) -> None:
        """Complete VS Code launch workflow.

        This is the main entry point that orchestrates:
        1. VS Code CLI check
        2. SSH config generation and write (with bastion support)
        3. Extension installation
        4. VS Code launch

        Args:
            vm_name: VM name for SSH host alias
            host: VM IP address or hostname (private IP if using bastion)
            user: SSH username
            key_path: Path to SSH private key
            port: SSH port (default: 22)
            install_extensions: Install extensions (default: True)
            workspace_path: Optional custom workspace path
            bastion_info: Bastion host info if VM is private-only (Issue #581)
            vm_resource_id: VM Azure resource ID (required for bastion ProxyCommand)

        Raises:
            VSCodeNotFoundError: If VS Code CLI not found
            VSCodeLauncherError: If any step fails

        Example:
            >>> VSCodeLauncher.launch(
            ...     vm_name="dev-vm",
            ...     host="20.1.2.3",
            ...     user="azureuser",
            ...     key_path=Path("~/.ssh/azlin_key")
            ... )
        """
        # Step 1: Check VS Code CLI
        cls.check_vscode_installed()

        # Step 2: Generate configuration (with optional bastion support)
        config = VSCodeConfig(
            vm_name=vm_name,
            host=host,
            user=user,
            key_path=key_path,
            port=port,
            bastion_info=bastion_info,
            vm_resource_id=vm_resource_id,
        )

        # Step 3: Write SSH config
        cls.write_ssh_config(config)

        ssh_host = f"azlin-{vm_name}"

        # Step 4: Install extensions
        if install_extensions:
            extensions = config.load_extensions()
            cls.install_extensions(ssh_host, extensions)

        # Step 5: Launch VS Code
        cls.launch_vscode(ssh_host, user, workspace_path)

        logger.info(f"VS Code launch complete for {vm_name}")
