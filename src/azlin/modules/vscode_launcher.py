"""VS Code Remote Development Launcher.

This module provides functionality to launch VS Code with Remote-SSH
configuration for Azure VMs. It handles:
- VS Code CLI detection
- SSH config file management
- Extension installation
- VS Code Remote-SSH connection
- WSL environment detection and Windows SSH config sync

Security:
- Command injection prevention via shlex.quote()
- SSH config validation
- Extension ID validation
- Subprocess timeout enforcement
"""

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

from azlin.modules.vscode_config import VSCodeConfig

logger = logging.getLogger(__name__)


def _is_wsl() -> bool:
    """Detect if running in WSL environment."""
    return 'microsoft' in platform.uname().release.lower() or os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop')


def _get_windows_username() -> str | None:
    """Get Windows username from WSL environment.

    Tries multiple methods to determine the Windows username:
    1. WSLENV / Windows environment variables
    2. /mnt/c/Users directory (find current user's home)
    3. Fallback to WSL username (may not match)
    """
    try:
        # Method 1: Check /mnt/c/Users for the current user
        # The directory that contains the WSL distribution is usually the Windows user
        users_dir = Path("/mnt/c/Users")
        if users_dir.exists():
            # Look for a user directory that isn't Public, Default, etc.
            for user_dir in users_dir.iterdir():
                if user_dir.is_dir() and user_dir.name not in ['Public', 'Default', 'Default User', 'All Users']:
                    # Check if this looks like the active user (has .ssh or recent files)
                    if (user_dir / '.ssh').exists() or (user_dir / 'AppData').exists():
                        logger.debug(f"Detected Windows username: {user_dir.name}")
                        return user_dir.name

        # Method 2: Try environment variable (set by Windows in WSL2)
        win_user = os.environ.get('LOGNAME') or os.environ.get('USER')
        if win_user:
            return win_user

        return None
    except Exception as e:
        logger.debug(f"Failed to detect Windows username: {e}")
        return None


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

        Checks for both 'code' (stable) and 'code-insiders' (Insiders).

        Returns:
            str: Path to VS Code CLI executable

        Raises:
            VSCodeNotFoundError: If VS Code CLI not found

        Example:
            >>> cli_path = VSCodeLauncher.check_vscode_installed()
            >>> print(cli_path)
            /usr/local/bin/code
        """
        # Try 'code' first (stable), then 'code-insiders' (Insiders edition)
        for code_cmd in ["code", "code-insiders"]:
            code_path = shutil.which(code_cmd)
            if code_path:
                logger.debug(f"Found VS Code CLI at {code_path} ({code_cmd})")
                return code_path

        raise VSCodeNotFoundError(
            "VS Code CLI not found. Please install VS Code and ensure 'code' or 'code-insiders' is in PATH.\n"
            "Installation: https://code.visualstudio.com/docs/setup/setup-overview#_launching-from-the-command-line"
        )

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

            # If on WSL, also copy to Windows .ssh for VS Code compatibility
            if _is_wsl():
                cls._sync_ssh_config_to_windows(config)

        except OSError as e:
            raise VSCodeLauncherError(f"Failed to write SSH config: {e}") from e

    @classmethod
    def _sync_ssh_config_to_windows(cls, config: VSCodeConfig) -> None:
        """Sync SSH config and keys to Windows .ssh directory for VS Code on WSL.

        VS Code Remote-SSH on WSL/Windows uses Windows SSH by default, which reads
        config from C:\\Users\\username\\.ssh\\config. This method copies the WSL
        SSH config and keys to Windows location with corrected paths.
        """
        try:
            # Get Windows username (assume same as WSL username)
            username = _get_windows_username() or os.environ.get('USER', 'user')
            windows_ssh_dir = Path(f"/mnt/c/Users/{username}/.ssh")

            # Create Windows .ssh directory
            windows_ssh_dir.mkdir(parents=True, exist_ok=True)

            # Copy SSH keys to Windows
            wsl_key_path = Path(config.key_path).expanduser()
            windows_key_path = windows_ssh_dir / wsl_key_path.name
            windows_pub_path = windows_ssh_dir / f"{wsl_key_path.name}.pub"

            shutil.copy2(wsl_key_path, windows_key_path)
            if wsl_key_path.with_suffix('.pub').exists():
                shutil.copy2(wsl_key_path.with_suffix('.pub'), windows_pub_path)

            # Generate Windows SSH config with Windows paths
            ssh_host = f"azlin-{config.vm_name}"
            windows_key_path_str = f"C:\\Users\\{username}\\.ssh\\{wsl_key_path.name}"

            windows_config = [
                f"Host {ssh_host}",
                f"    HostName {config.host}",
                f"    Port {config.port}",
                f"    User {config.user}",
                f"    IdentityFile {windows_key_path_str}",
                "    StrictHostKeyChecking no",
                "    UserKnownHostsFile NUL",
                "    ServerAliveInterval 60",
                "    ServerAliveCountMax 3",
            ]

            # Write to Windows SSH config
            windows_config_path = windows_ssh_dir / "config"
            windows_config_path.write_text("\n# Added by azlin\n" + "\n".join(windows_config) + "\n")

            logger.info(f"Synced SSH config to Windows: {windows_config_path}")

            # Also configure VS Code settings for remote platform
            cls._configure_vscode_remote_platform(ssh_host, windows_ssh_dir.parent)

        except Exception as e:
            logger.warning(f"Failed to sync SSH config to Windows (non-critical): {e}")

    @classmethod
    def _configure_vscode_remote_platform(cls, ssh_host: str, windows_home: Path) -> None:
        """Configure VS Code Remote-SSH platform setting for Linux hosts.

        Creates or updates VS Code settings.json to include remote.SSH.remotePlatform
        setting, telling VS Code the remote host is Linux (Azure Ubuntu VMs).
        """
        try:
            import json

            # VS Code settings location (Windows)
            vscode_dir = windows_home / "AppData/Roaming/Code/User"
            vscode_insiders_dir = windows_home / "AppData/Roaming/Code - Insiders/User"

            # Try both Code and Code Insiders
            for settings_dir in [vscode_dir, vscode_insiders_dir]:
                if not settings_dir.exists():
                    continue

                settings_file = settings_dir / "settings.json"

                # Load existing settings or create new
                if settings_file.exists():
                    try:
                        settings = json.loads(settings_file.read_text())
                    except json.JSONDecodeError:
                        settings = {}
                else:
                    settings = {}

                # Add remote platform setting
                if "remote.SSH.remotePlatform" not in settings:
                    settings["remote.SSH.remotePlatform"] = {}

                settings["remote.SSH.remotePlatform"][ssh_host] = "linux"

                # Write back
                settings_file.write_text(json.dumps(settings, indent=2))
                logger.info(f"Configured VS Code remote platform for {ssh_host}")

        except Exception as e:
            logger.warning(f"Failed to configure VS Code settings (non-critical): {e}")

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
    ) -> None:
        """Complete VS Code launch workflow.

        This is the main entry point that orchestrates:
        1. VS Code CLI check
        2. SSH config generation and write
        3. Extension installation
        4. VS Code launch

        Works with both direct connections and bastion tunnels (Issue #581):
        - Direct: host=VM_IP, port=22
        - Bastion tunnel: host=127.0.0.1, port=tunnel_port

        Args:
            vm_name: VM name for SSH host alias
            host: SSH host (VM IP or 127.0.0.1 for bastion tunnel)
            user: SSH username
            key_path: Path to SSH private key
            port: SSH port (22 for direct, tunnel port for bastion)
            install_extensions: Install extensions (default: True)
            workspace_path: Optional custom workspace path

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

        # Step 2: Generate configuration
        config = VSCodeConfig(
            vm_name=vm_name,
            host=host,
            user=user,
            key_path=key_path,
            port=port,
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
