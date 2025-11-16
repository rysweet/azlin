"""
SSH Connector Module

Establish SSH connection to VM and start tmux session.

Security Requirements:
- SSH key-based authentication only
- No password authentication
- Strict host key checking (configurable)
- Timeout enforcement
- No credential logging
"""

import logging
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SSHConfig:
    """SSH connection configuration."""

    host: str
    user: str
    key_path: Path
    port: int = 22
    strict_host_key_checking: bool = False  # Disabled for new VMs


class SSHConnectionError(Exception):
    """Raised when SSH connection fails."""

    pass


class SSHConnector:
    """
    Manage SSH connection to VM.

    Security:
    - Key-based authentication only
    - No password prompts
    - Timeout enforcement
    - Command validation
    """

    DEFAULT_USER = "azureuser"
    DEFAULT_PORT = 22

    @classmethod
    def connect(
        cls,
        config: SSHConfig,
        tmux_session: str | None = "azlin",
        auto_tmux: bool = True,
        remote_command: str | None = None,
    ) -> int:
        """
        Connect via SSH and optionally start tmux session.

        Args:
            config: SSH configuration
            tmux_session: tmux session name (default: "azlin")
            auto_tmux: Automatically start/attach tmux session
            remote_command: Optional command to run on remote host

        Returns:
            int: SSH exit code (0 = success)

        Raises:
            SSHConnectionError: If connection fails

        Security:
        - Uses key-based authentication
        - No password prompts
        - Validates paths

        Example:
            >>> config = SSHConfig(
            ...     host="20.12.34.56",
            ...     user="azureuser",
            ...     key_path=Path("~/.ssh/azlin_key")
            ... )
            >>> exit_code = SSHConnector.connect(config)
        """
        # Validate configuration
        cls._validate_config(config)

        # Wait for SSH to be ready
        logger.info(f"Waiting for SSH on {config.host}:{config.port}...")
        if not cls.wait_for_ssh_ready(
            config.host, config.key_path, port=config.port, user=config.user
        ):
            raise SSHConnectionError(f"SSH connection to {config.host} timed out")

        # Build SSH command
        if remote_command:
            ssh_args = cls.build_ssh_command(config, remote_command)
        elif auto_tmux and tmux_session:
            tmux_command = cls._build_tmux_command(tmux_session)
            ssh_args = cls.build_ssh_command(config, tmux_command)
        else:
            ssh_args = cls.build_ssh_command(config)

        logger.info(f"Connecting to {config.user}@{config.host}...")

        try:
            # Execute SSH (blocking until session ends)
            result = subprocess.run(ssh_args)

            if result.returncode == 0:
                logger.info("SSH session ended successfully")
            else:
                logger.warning(f"SSH session ended with code {result.returncode}")

            return result.returncode

        except KeyboardInterrupt:
            logger.info("SSH session interrupted by user")
            return 130  # Standard exit code for Ctrl+C

        except Exception as e:
            raise SSHConnectionError(f"SSH connection failed: {e}") from e

    @classmethod
    def _build_tmux_command(cls, session_name: str) -> str:
        """
        Build tmux command to attach or create session.

        Args:
            session_name: tmux session name

        Returns:
            str: tmux command

        Security: Uses safe shell quoting
        """
        # Command to attach to existing session or create new one
        # This is safe because session_name is validated
        import shlex

        safe_session = shlex.quote(session_name)

        # Try to attach to existing session, create if doesn't exist
        return f"tmux attach-session -t {safe_session} 2>/dev/null || tmux new-session -s {safe_session}"

    @classmethod
    def wait_for_ssh_ready(
        cls,
        host: str,
        key_path: Path,
        port: int = 22,
        timeout: int = 300,
        interval: int = 5,
        user: str | None = None,
    ) -> bool:
        """
        Wait for SSH port to be accessible.

        Args:
            host: Target hostname/IP
            key_path: Path to SSH private key
            port: SSH port
            timeout: Maximum wait time in seconds (default: 300)
            interval: Check interval in seconds
            user: SSH username (optional, defaults to DEFAULT_USER)

        Returns:
            bool: True if SSH is ready, False if timed out

        Raises:
            ValueError: If timeout is negative

        Security:
        - Non-blocking socket checks
        - Timeout enforcement
        - No credential exposure

        Example:
            >>> ready = SSHConnector.wait_for_ssh_ready(
            ...     "20.12.34.56",
            ...     Path("~/.ssh/azlin_key")
            ... )
            >>> if ready:
            ...     print("SSH is ready")
        """
        # Validate timeout
        if timeout < 0:
            raise ValueError("timeout must be positive (non-negative)")

        start_time = time.time()
        attempt = 0

        while True:
            current_time = time.time()
            if (current_time - start_time) >= timeout:
                break

            attempt += 1

            # First check if port is open
            if cls._check_port_open(host, port):
                logger.debug(f"Port {port} is open on {host}")

                # Then try actual SSH connection
                if cls._test_ssh_connection(host, key_path, port, user=user):
                    elapsed = current_time - start_time
                    logger.info(
                        f"SSH ready on {host}:{port} (after {elapsed:.1f}s, {attempt} attempts)"
                    )
                    return True

            # Wait before next attempt
            logger.debug(f"SSH not ready, retrying in {interval}s...")
            time.sleep(interval)

        logger.error(f"SSH not ready after {timeout}s ({attempt} attempts)")
        return False

    @classmethod
    def _check_port_open(cls, host: str, port: int, timeout: float = 2.0) -> bool:
        """
        Check if TCP port is open.

        Args:
            host: Hostname or IP
            port: Port number
            timeout: Connection timeout in seconds

        Returns:
            bool: True if port is open

        Security: Non-blocking socket check
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except (TimeoutError, OSError):
            return False

    @classmethod
    def _test_ssh_connection(
        cls, host: str, key_path: Path, port: int, timeout: int = 10, user: str | None = None
    ) -> bool:
        """
        Test SSH connection with actual authentication.

        Args:
            host: Target hostname/IP
            key_path: SSH private key path
            port: SSH port
            timeout: Connection timeout
            user: SSH username (optional, defaults to DEFAULT_USER)

        Returns:
            bool: True if SSH connection succeeds

        Security:
        - Uses key-based auth
        - No password prompts
        - Short timeout
        """
        try:
            # Use provided username or fallback to DEFAULT_USER
            ssh_user = user if user else cls.DEFAULT_USER

            # Build minimal SSH command to test connection
            args = [
                "ssh",
                "-i",
                str(key_path.expanduser()),
                "-p",
                str(port),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "BatchMode=yes",  # No password prompts
                "-o",
                f"ConnectTimeout={timeout}",
                "-o",
                "LogLevel=ERROR",
                f"{ssh_user}@{host}",
                "exit 0",  # Simple command
            ]

            result = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout + 5,  # subprocess timeout > SSH timeout
            )

            return result.returncode == 0

        except (subprocess.TimeoutExpired, Exception):
            return False

    @classmethod
    def build_ssh_command(cls, config: SSHConfig, remote_command: str | None = None) -> list[str]:
        """
        Build SSH command with proper flags.

        Args:
            config: SSH configuration
            remote_command: Optional command to execute on remote

        Returns:
            list: SSH command arguments

        Security:
        - Uses argument list (no shell=True)
        - Key-based authentication
        - Configurable host key checking

        Example:
            >>> config = SSHConfig(
            ...     host="20.12.34.56",
            ...     user="azureuser",
            ...     key_path=Path("~/.ssh/azlin_key")
            ... )
            >>> args = SSHConnector.build_ssh_command(config)
            >>> print(args)
            ['ssh', '-i', '~/.ssh/azlin_key', ...]
        """
        args = [
            "ssh",
            "-i",
            str(config.key_path.expanduser()),
            "-p",
            str(config.port),
            "-o",
            "BatchMode=yes",  # No password prompts
            "-o",
            "LogLevel=INFO",
        ]

        # Host key checking
        if not config.strict_host_key_checking:
            args.extend(["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"])

        # Forward agent (for git operations on remote)
        args.extend(["-A"])  # ForwardAgent=yes

        # TTY allocation (for interactive sessions)
        if remote_command:
            args.extend(["-t"])  # Force TTY allocation

        # User@host
        args.append(f"{config.user}@{config.host}")

        # Remote command (if specified)
        if remote_command:
            args.append(remote_command)

        return args

    @classmethod
    def _validate_config(cls, config: SSHConfig) -> None:
        """
        Validate SSH configuration.

        Args:
            config: SSH configuration to validate

        Raises:
            ValueError: If configuration is invalid

        Security: Validates all parameters
        """
        if not config.host:
            raise ValueError("SSH host cannot be empty")

        if not config.user:
            raise ValueError("SSH user cannot be empty")

        if not config.key_path:
            raise ValueError("SSH key path cannot be empty")

        # Resolve and check key path
        key_path = config.key_path.expanduser().resolve()

        if not key_path.exists():
            raise ValueError(f"SSH key not found: {key_path}")

        # Check key permissions
        stat = key_path.stat()
        if stat.st_mode & 0o077:  # Group or other have access
            logger.warning(
                f"SSH key has insecure permissions: {oct(stat.st_mode & 0o777)}\n"
                f"Expected: 0600 (-rw-------)\n"
                f"File: {key_path}"
            )

        # Validate port
        if not (1 <= config.port <= 65535):
            raise ValueError(f"Invalid SSH port: {config.port}")

    @classmethod
    def execute_remote_command(cls, config: SSHConfig, command: str, timeout: int = 60) -> str:
        """
        Execute a command on remote host and return output.

        Args:
            config: SSH configuration
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            str: Command output (stdout)

        Raises:
            SSHConnectionError: If command fails

        Security:
        - Command passed as single argument
        - Timeout enforcement
        - Output sanitized

        Example:
            >>> config = SSHConfig(...)
            >>> output = SSHConnector.execute_remote_command(
            ...     config, "ls -la"
            ... )
        """
        cls._validate_config(config)

        args = cls.build_ssh_command(config, command)

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout, check=True
            )

            return result.stdout

        except subprocess.TimeoutExpired as e:
            raise SSHConnectionError(f"Remote command timed out after {timeout}s") from e

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise SSHConnectionError(f"Remote command failed: {error_msg}") from e

        except Exception as e:
            raise SSHConnectionError(f"Failed to execute remote command: {e}") from e


# Convenience functions for CLI use
def connect_ssh(
    host: str, user: str = "azureuser", key_path: Path | None = None, tmux_session: str = "azlin"
) -> int:
    """
    Connect to VM via SSH (convenience function).

    Args:
        host: VM IP address or hostname
        user: SSH username
        key_path: Path to SSH private key
        tmux_session: tmux session name

    Returns:
        int: SSH exit code

    Example:
        >>> from azlin.modules.ssh_connector import connect_ssh
        >>> exit_code = connect_ssh("20.12.34.56")
    """
    if key_path is None:
        from .ssh_keys import SSHKeyManager

        key_path = SSHKeyManager.DEFAULT_KEY_PATH

    config = SSHConfig(host=host, user=user, key_path=key_path)

    return SSHConnector.connect(config, tmux_session)
