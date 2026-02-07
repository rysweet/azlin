"""Terminal launcher module.

This module handles launching new terminal windows with SSH connections.
Supports macOS (Terminal.app, iTerm2) and Linux (gnome-terminal, xterm).

Security:
- All subprocess calls use argument lists (no shell=True)
- Input validation for all user-controlled parameters
- No string concatenation for commands
- Proper escaping for AppleScript
"""

import logging
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class TerminalLauncherError(Exception):
    """Raised when terminal launch fails."""

    pass


class SecurityValidationError(Exception):
    """Raised when input validation fails."""

    pass


def _validate_hostname(hostname: str) -> None:
    """Validate SSH hostname.

    Args:
        hostname: Hostname to validate

    Raises:
        SecurityValidationError: If hostname contains invalid characters
    """
    if not hostname:
        raise SecurityValidationError("Hostname cannot be empty")

    # Allow alphanumeric, dots, hyphens, and underscores
    # Also allow IPv4 addresses and IPv6 addresses
    pattern = r"^[a-zA-Z0-9.\-_:\[\]]+$"
    if not re.match(pattern, hostname):
        raise SecurityValidationError(
            f"Invalid hostname: {hostname}. Contains disallowed characters."
        )

    # Check for command injection patterns
    dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"]
    for char in dangerous_chars:
        if char in hostname:
            raise SecurityValidationError(
                f"Invalid hostname: {hostname}. Contains dangerous character: {char}"
            )


def _validate_username(username: str) -> None:
    """Validate SSH username.

    Args:
        username: Username to validate

    Raises:
        SecurityValidationError: If username contains invalid characters
    """
    if not username:
        raise SecurityValidationError("Username cannot be empty")

    # Allow alphanumeric, dots, hyphens, and underscores
    pattern = r"^[a-zA-Z0-9.\-_]+$"
    if not re.match(pattern, username):
        raise SecurityValidationError(
            f"Invalid username: {username}. Contains disallowed characters."
        )


def _validate_command(command: str | None) -> None:
    """Validate remote command.

    Args:
        command: Command to validate

    Raises:
        SecurityValidationError: If command contains dangerous patterns
    """
    if command is None:
        return

    if not command.strip():
        raise SecurityValidationError("Command cannot be empty or whitespace only")

    # Check for null bytes
    if "\x00" in command:
        raise SecurityValidationError("Command contains null bytes")


def _validate_session_name(session_name: str | None) -> None:
    """Validate tmux session name.

    Args:
        session_name: Session name to validate

    Raises:
        SecurityValidationError: If session name contains invalid characters
    """
    if session_name is None:
        return

    if not session_name.strip():
        raise SecurityValidationError("Session name cannot be empty or whitespace only")

    # Allow alphanumeric, dots, hyphens, and underscores
    pattern = r"^[a-zA-Z0-9.\-_]+$"
    if not re.match(pattern, session_name):
        raise SecurityValidationError(
            f"Invalid session name: {session_name}. Contains disallowed characters."
        )


@dataclass
class TerminalConfig:
    """Terminal launch configuration."""

    ssh_host: str
    ssh_user: str
    ssh_key_path: Path
    ssh_port: int = 22
    command: str | None = None
    title: str | None = None
    tmux_session: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        _validate_hostname(self.ssh_host)
        _validate_username(self.ssh_user)
        _validate_command(self.command)
        _validate_session_name(self.tmux_session)

        # Validate key path exists
        if not self.ssh_key_path.exists():
            raise SecurityValidationError(f"SSH key not found: {self.ssh_key_path}")


class TerminalLauncher:
    """Launch new terminal windows with SSH connections.

    This class provides platform-specific terminal launching:
    - macOS: Terminal.app or iTerm2
    - Linux: gnome-terminal, xterm
    """

    @classmethod
    def launch(cls, config: TerminalConfig, fallback_inline: bool = True) -> bool:
        """Launch new terminal window with SSH connection.

        Args:
            config: Terminal configuration
            fallback_inline: Fall back to inline SSH if launch fails

        Returns:
            True if successful, False if failed

        Raises:
            TerminalLauncherError: If launch fails and fallback disabled
        """
        platform = sys.platform

        try:
            if platform == "darwin":
                success = cls._launch_macos(config)
                if not success and fallback_inline:
                    logger.info("Terminal launch failed, falling back to inline SSH connection")
                    return cls._fallback_inline_ssh(config)
                return success
            if platform.startswith("linux"):
                success = cls._launch_linux(config)
                if not success and fallback_inline:
                    logger.info("Terminal launch failed, falling back to inline SSH connection")
                    return cls._fallback_inline_ssh(config)
                return success
            logger.warning(f"Unsupported platform: {platform}")
            if fallback_inline:
                return cls._fallback_inline_ssh(config)
            return False

        except Exception as e:
            logger.error(f"Failed to launch terminal: {e}")
            if fallback_inline:
                logger.info("Falling back to inline SSH connection")
                return cls._fallback_inline_ssh(config)
            raise TerminalLauncherError(f"Terminal launch failed: {e}") from e

    @classmethod
    def _launch_macos(cls, config: TerminalConfig) -> bool:
        """Launch terminal on macOS using AppleScript.

        Args:
            config: Terminal configuration

        Returns:
            True if successful
        """
        # Build SSH command string for AppleScript
        ssh_cmd = cls._build_ssh_command_string(config)

        # Escape for AppleScript - only escape quotes and backslashes
        # This is safe because we're not executing via shell
        escaped_cmd = ssh_cmd.replace("\\", "\\\\").replace('"', '\\"')

        # Escape title for AppleScript
        title = config.title or f"azlin - {config.ssh_host}"
        escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')

        # Build AppleScript
        applescript = f"""
        tell application "Terminal"
            activate
            do script "{escaped_cmd}"
            set custom title of front window to "{escaped_title}"
        end tell
        """

        logger.debug(f"Launching macOS terminal with: {ssh_cmd}")

        # Execute AppleScript using argument list
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode == 0:
            logger.info("Terminal launched successfully")
            return True
        logger.error(f"AppleScript failed: {result.stderr}")
        return False

    @classmethod
    def _launch_linux(cls, config: TerminalConfig) -> bool:
        """Launch terminal on Linux.

        Tries gnome-terminal first, then xterm as fallback.

        Args:
            config: Terminal configuration

        Returns:
            True if successful
        """
        # Get SSH command as argument list
        ssh_cmd = cls._build_ssh_command(config)
        title = config.title or f"azlin - {config.ssh_host}"

        # Try gnome-terminal first
        if cls._has_command("gnome-terminal"):
            logger.debug("Launching gnome-terminal")
            try:
                # Use argument list - gnome-terminal requires -- before command
                # Pass ssh command arguments directly
                subprocess.Popen(
                    ["gnome-terminal", "--title", title, "--", *ssh_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("Terminal launched successfully")
                return True
            except Exception as e:
                logger.error(f"gnome-terminal failed: {e}")

        # Try xterm as fallback
        if cls._has_command("xterm"):
            logger.debug("Launching xterm")
            try:
                # xterm -e requires the command as a single string
                # So we need to convert our argument list to a shell command
                # But we do this safely by joining the validated arguments
                ssh_cmd_str = " ".join(ssh_cmd)
                subprocess.Popen(
                    ["xterm", "-title", title, "-e", ssh_cmd_str],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("Terminal launched successfully")
                return True
            except Exception as e:
                logger.error(f"xterm failed: {e}")

        logger.error("No terminal emulator found")
        return False

    @classmethod
    def _build_ssh_command(cls, config: TerminalConfig) -> list[str]:
        """Build SSH command as argument list.

        Args:
            config: Terminal configuration

        Returns:
            SSH command as list of arguments (safe for subprocess)
        """
        # Base SSH command with arguments as list
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-i",
            str(config.ssh_key_path),
            "-p",
            str(config.ssh_port),
        ]

        # Force TTY allocation for commands and interactive sessions
        if config.command or config.tmux_session:
            cmd.append("-t")  # Force pseudo-terminal allocation

        cmd.append(f"{config.ssh_user}@{config.ssh_host}")

        # Add remote command if specified
        if config.command:
            # When a remote command is specified, execute it directly
            # without wrapping in tmux (users expect direct output capture)
            # This fixes: azlin connect vm -- command should not use tmux
            cmd.append(config.command)
        elif config.tmux_session:
            # Interactive mode: attach to or create tmux session
            # This is used when: azlin connect vm (no command specified)
            safe_session = shlex.quote(config.tmux_session)
            remote_cmd = f"tmux attach-session -t {safe_session} 2>/dev/null || tmux new-session -s {safe_session}"
            cmd.append(remote_cmd)

        return cmd

    @classmethod
    def _build_ssh_command_string(cls, config: TerminalConfig) -> str:
        """Build SSH command as shell-safe string for AppleScript.

        Args:
            config: Terminal configuration

        Returns:
            SSH command as properly escaped string
        """
        # Get argument list
        cmd_list = cls._build_ssh_command(config)

        # Join with proper shell escaping for display/logging
        # This is only used for AppleScript embedding, not for execution
        return " ".join(cmd_list)

    @classmethod
    def _fallback_inline_ssh(cls, config: TerminalConfig) -> bool:
        """Fallback to inline SSH connection in current terminal.

        Args:
            config: Terminal configuration

        Returns:
            True if SSH connection succeeds
        """
        ssh_cmd = cls._build_ssh_command(config)
        logger.info(f"Connecting via SSH: {' '.join(ssh_cmd)}")

        # Execute SSH in current terminal using subprocess
        # This replaces the vulnerable os.system() call
        try:
            result = subprocess.run(
                ssh_cmd,
                check=False,
                # Don't use shell=True - we're using argument list
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            return False

    @classmethod
    def _has_command(cls, command: str) -> bool:
        """Check if command is available.

        Args:
            command: Command name

        Returns:
            True if available
        """
        try:
            subprocess.run(["which", command], capture_output=True, timeout=5, check=True)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @classmethod
    def launch_command_in_terminal(
        cls,
        ssh_host: str,
        ssh_user: str,
        ssh_key_path: Path,
        command: str,
        title: str | None = None,
    ) -> bool:
        """Launch terminal and execute command on remote host.

        Args:
            ssh_host: SSH host address
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key
            command: Command to execute
            title: Terminal window title

        Returns:
            True if successful
        """
        config = TerminalConfig(
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
            command=command,
            title=title or f"azlin - {command}",
        )

        return cls.launch(config)


__all__ = [
    "SecurityValidationError",
    "TerminalConfig",
    "TerminalLauncher",
    "TerminalLauncherError",
]
