"""Terminal launcher module.

This module handles launching new terminal windows with SSH connections.
Supports macOS (Terminal.app, iTerm2) and Linux (gnome-terminal, xterm).

Security:
- Command sanitization
- No shell=True for subprocess
- Proper escaping for AppleScript
"""

import os
import sys
import logging
import subprocess
import shlex
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TerminalLauncherError(Exception):
    """Raised when terminal launch fails."""
    pass


@dataclass
class TerminalConfig:
    """Terminal launch configuration."""
    ssh_host: str
    ssh_user: str
    ssh_key_path: Path
    command: Optional[str] = None
    title: Optional[str] = None
    tmux_session: Optional[str] = None


class TerminalLauncher:
    """Launch new terminal windows with SSH connections.

    This class provides platform-specific terminal launching:
    - macOS: Terminal.app or iTerm2
    - Linux: gnome-terminal, xterm
    """

    @classmethod
    def launch(
        cls,
        config: TerminalConfig,
        fallback_inline: bool = True
    ) -> bool:
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
            if platform == 'darwin':
                return cls._launch_macos(config)
            elif platform.startswith('linux'):
                return cls._launch_linux(config)
            else:
                logger.warning(f"Unsupported platform: {platform}")
                if fallback_inline:
                    return cls._fallback_inline_ssh(config)
                return False

        except Exception as e:
            logger.error(f"Failed to launch terminal: {e}")
            if fallback_inline:
                logger.info("Falling back to inline SSH connection")
                return cls._fallback_inline_ssh(config)
            raise TerminalLauncherError(f"Terminal launch failed: {e}")

    @classmethod
    def _launch_macos(cls, config: TerminalConfig) -> bool:
        """Launch terminal on macOS using AppleScript.

        Args:
            config: Terminal configuration

        Returns:
            True if successful
        """
        # Build SSH command
        ssh_cmd = cls._build_ssh_command(config)

        # Escape for AppleScript
        escaped_cmd = ssh_cmd.replace('\\', '\\\\').replace('"', '\\"')

        # Build AppleScript
        title = config.title or f"azlin - {config.ssh_host}"
        applescript = f'''
        tell application "Terminal"
            activate
            do script "{escaped_cmd}"
            set custom title of front window to "{title}"
        end tell
        '''

        logger.debug(f"Launching macOS terminal with: {ssh_cmd}")

        # Execute AppleScript
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )

        if result.returncode == 0:
            logger.info("Terminal launched successfully")
            return True
        else:
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
        ssh_cmd = cls._build_ssh_command(config)
        title = config.title or f"azlin - {config.ssh_host}"

        # Try gnome-terminal first
        if cls._has_command('gnome-terminal'):
            logger.debug("Launching gnome-terminal")
            try:
                subprocess.Popen(
                    [
                        'gnome-terminal',
                        '--title', title,
                        '--',
                        'bash', '-c', ssh_cmd
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info("Terminal launched successfully")
                return True
            except Exception as e:
                logger.error(f"gnome-terminal failed: {e}")

        # Try xterm as fallback
        if cls._has_command('xterm'):
            logger.debug("Launching xterm")
            try:
                subprocess.Popen(
                    [
                        'xterm',
                        '-title', title,
                        '-e', ssh_cmd
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info("Terminal launched successfully")
                return True
            except Exception as e:
                logger.error(f"xterm failed: {e}")

        logger.error("No terminal emulator found")
        return False

    @classmethod
    def _build_ssh_command(cls, config: TerminalConfig) -> str:
        """Build SSH command string.

        Args:
            config: Terminal configuration

        Returns:
            SSH command string
        """
        # Base SSH command
        parts = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-i', str(config.ssh_key_path),
            f'{config.ssh_user}@{config.ssh_host}'
        ]

        # Add remote command if specified
        if config.command:
            # If command includes tmux, add it
            if config.tmux_session:
                remote_cmd = (
                    f'tmux new-session -A -s {shlex.quote(config.tmux_session)} '
                    f'{shlex.quote(config.command)}'
                )
            else:
                remote_cmd = config.command

            parts.append(shlex.quote(remote_cmd))
        elif config.tmux_session:
            # Just tmux session, no command
            remote_cmd = f'tmux new-session -A -s {shlex.quote(config.tmux_session)}'
            parts.append(shlex.quote(remote_cmd))

        return ' '.join(parts)

    @classmethod
    def _fallback_inline_ssh(cls, config: TerminalConfig) -> bool:
        """Fallback to inline SSH connection in current terminal.

        Args:
            config: Terminal configuration

        Returns:
            True (always succeeds or exits)
        """
        ssh_cmd = cls._build_ssh_command(config)
        logger.info(f"Connecting via SSH: {ssh_cmd}")

        # Execute SSH in current terminal
        exit_code = os.system(ssh_cmd)

        # Return based on exit code
        return exit_code == 0

    @classmethod
    def _has_command(cls, command: str) -> bool:
        """Check if command is available.

        Args:
            command: Command name

        Returns:
            True if available
        """
        try:
            subprocess.run(
                ['which', command],
                capture_output=True,
                timeout=5,
                check=True
            )
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
        title: Optional[str] = None
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
            title=title or f"azlin - {command}"
        )

        return cls.launch(config)


__all__ = [
    'TerminalLauncher',
    'TerminalConfig',
    'TerminalLauncherError'
]
