"""Environment variable management for remote VMs.

This module provides functionality to manage environment variables on remote VMs
by modifying the ~/.bashrc file. Variables are stored in a dedicated section
marked with special comments to avoid interfering with user configuration.

Security features:
- Input validation for environment variable names
- Secret detection warnings
- SSH stdin redirection (eliminates command injection)
- Isolated bashrc section management
- Content size limits
"""

import base64
import logging
import re
import subprocess
from pathlib import Path

from azlin.modules.ssh_connector import SSHConfig, SSHConnector

logger = logging.getLogger(__name__)


class EnvManagerError(Exception):
    """Raised when environment variable management fails."""

    pass


class EnvManager:
    """Manage environment variables on remote VMs.

    Environment variables are stored in ~/.bashrc within a dedicated section:

    # AZLIN_ENV_START - Do not edit this section manually
    export VAR_NAME="value"
    # AZLIN_ENV_END
    """

    # Markers for azlin-managed environment variables section
    ENV_MARKER_START = "# AZLIN_ENV_START - Do not edit this section manually"
    ENV_MARKER_END = "# AZLIN_ENV_END"

    # Security limits
    MAX_CONTENT_SIZE = 1024 * 1024  # 1MB max bashrc size
    MAX_VALUE_SIZE = 32 * 1024  # 32KB max per env var value

    # Patterns for secret detection
    SECRET_PATTERNS = [
        (r"api[_-]?key", "api_key"),
        (r"secret", "secret"),
        (r"password", "password"),
        (r"token", "token"),
        (r"auth", "auth"),
        (r"credential", "credential"),
        (r"postgres://", "postgres://"),
        (r"mysql://", "mysql://"),
        (r"mongodb(\+srv)?://", "mongodb+srv://"),
        (r"redis://", "redis://"),
        (r"Bearer\s+", "Bearer"),
    ]

    @classmethod
    def _validate_content_size(cls, content: str) -> None:
        """Validate content size to prevent DoS attacks.

        Args:
            content: Content to validate

        Raises:
            EnvManagerError: If content exceeds size limit
        """
        if len(content) > cls.MAX_CONTENT_SIZE:
            raise EnvManagerError(
                f"Content size {len(content)} exceeds maximum {cls.MAX_CONTENT_SIZE} bytes"
            )

    @classmethod
    def _validate_value_size(cls, value: str) -> None:
        """Validate environment variable value size.

        Args:
            value: Value to validate

        Raises:
            EnvManagerError: If value exceeds size limit
        """
        if len(value) > cls.MAX_VALUE_SIZE:
            raise EnvManagerError(
                f"Value size {len(value)} exceeds maximum {cls.MAX_VALUE_SIZE} bytes"
            )

    @classmethod
    def _validate_ssh_config(cls, ssh_config: SSHConfig) -> None:
        """Validate SSH configuration.

        Args:
            ssh_config: SSH configuration to validate

        Raises:
            EnvManagerError: If configuration is invalid
        """
        if not ssh_config.host or not isinstance(ssh_config.host, str):
            raise EnvManagerError("Invalid SSH host")
        if not ssh_config.user or not isinstance(ssh_config.user, str):
            raise EnvManagerError("Invalid SSH user")
        if not ssh_config.key_path or not Path(ssh_config.key_path).exists():
            raise EnvManagerError("Invalid or missing SSH key path")

    @classmethod
    def set_env_var(cls, ssh_config: SSHConfig, key: str, value: str) -> bool:
        """Set an environment variable on remote VM.

        Args:
            ssh_config: SSH configuration for target VM
            key: Environment variable name (must be valid shell variable)
            value: Environment variable value

        Returns:
            True if successful

        Raises:
            EnvManagerError: If operation fails
        """
        # Validate SSH config
        cls._validate_ssh_config(ssh_config)

        # Validate key
        is_valid, message = cls.validate_env_key(key)
        if not is_valid:
            raise EnvManagerError(f"Invalid environment variable name: {message}")

        # Validate value size
        cls._validate_value_size(value)

        try:
            # Read current bashrc
            bashrc_content = cls._read_bashrc(ssh_config)

            # Get current env vars
            current_vars = cls._extract_env_vars(bashrc_content)

            # Update or add the variable
            current_vars[key] = value

            # Write back
            new_bashrc = cls._update_bashrc_with_env_vars(bashrc_content, current_vars)
            cls._write_bashrc(ssh_config, new_bashrc)

            logger.info(f"Set {key} on {ssh_config.host}")
            return True

        except Exception as e:
            raise EnvManagerError(f"Failed to set environment variable: {e}")

    @classmethod
    def list_env_vars(cls, ssh_config: SSHConfig) -> dict[str, str]:
        """List all azlin-managed environment variables on remote VM.

        Args:
            ssh_config: SSH configuration for target VM

        Returns:
            Dictionary of environment variable names to values

        Raises:
            EnvManagerError: If operation fails
        """
        try:
            bashrc_content = cls._read_bashrc(ssh_config)
            return cls._extract_env_vars(bashrc_content)

        except Exception as e:
            raise EnvManagerError(f"Failed to list environment variables: {e}")

    @classmethod
    def delete_env_var(cls, ssh_config: SSHConfig, key: str) -> bool:
        """Delete an environment variable from remote VM.

        Args:
            ssh_config: SSH configuration for target VM
            key: Environment variable name to delete

        Returns:
            True if variable was deleted, False if it didn't exist

        Raises:
            EnvManagerError: If operation fails
        """
        try:
            # Read current bashrc
            bashrc_content = cls._read_bashrc(ssh_config)

            # Get current env vars
            current_vars = cls._extract_env_vars(bashrc_content)

            # Check if variable exists
            if key not in current_vars:
                return False

            # Remove the variable
            del current_vars[key]

            # Write back
            new_bashrc = cls._update_bashrc_with_env_vars(bashrc_content, current_vars)
            cls._write_bashrc(ssh_config, new_bashrc)

            logger.info(f"Deleted {key} from {ssh_config.host}")
            return True

        except Exception as e:
            raise EnvManagerError(f"Failed to delete environment variable: {e}")

    @classmethod
    def clear_all_env_vars(cls, ssh_config: SSHConfig) -> bool:
        """Clear all azlin-managed environment variables from remote VM.

        Args:
            ssh_config: SSH configuration for target VM

        Returns:
            True if successful

        Raises:
            EnvManagerError: If operation fails
        """
        try:
            # Read current bashrc
            bashrc_content = cls._read_bashrc(ssh_config)

            # Remove the entire section
            new_bashrc = cls._remove_env_section(bashrc_content)
            cls._write_bashrc(ssh_config, new_bashrc)

            logger.info(f"Cleared all env vars from {ssh_config.host}")
            return True

        except Exception as e:
            raise EnvManagerError(f"Failed to clear environment variables: {e}")

    @classmethod
    def export_env_vars(cls, ssh_config: SSHConfig, output_file: str | None = None) -> str:
        """Export environment variables in .env file format.

        Args:
            ssh_config: SSH configuration for target VM
            output_file: Optional path to write .env file

        Returns:
            Path to output file if written, or the .env content as string

        Raises:
            EnvManagerError: If operation fails
        """
        try:
            env_vars = cls.list_env_vars(ssh_config)

            # Format as .env file
            lines = []
            for key, value in sorted(env_vars.items()):
                # Escape quotes in value
                escaped_value = value.replace('"', '\\"')
                lines.append(f'{key}="{escaped_value}"')

            content = "\n".join(lines)

            if output_file:
                Path(output_file).write_text(content + "\n")
                return output_file
            return content

        except Exception as e:
            raise EnvManagerError(f"Failed to export environment variables: {e}")

    @classmethod
    def import_env_file(cls, ssh_config: SSHConfig, env_file_path: str) -> int:
        """Import environment variables from .env file.

        Args:
            ssh_config: SSH configuration for target VM
            env_file_path: Path to .env file

        Returns:
            Number of variables imported

        Raises:
            EnvManagerError: If operation fails
        """
        try:
            # Read .env file
            env_file = Path(env_file_path)
            if not env_file.exists():
                raise EnvManagerError(f"File not found: {env_file_path}")

            content = env_file.read_text()

            # Parse .env format
            count = 0
            for line in content.splitlines():
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse KEY=VALUE or KEY="VALUE"
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]

                    # Validate and set
                    is_valid, _ = cls.validate_env_key(key)
                    if is_valid:
                        cls.set_env_var(ssh_config, key, value)
                        count += 1

            return count

        except EnvManagerError:
            raise
        except Exception as e:
            raise EnvManagerError(f"Failed to import .env file: {e}")

    @classmethod
    def validate_env_key(cls, key: str) -> tuple[bool, str]:
        """Validate environment variable name.

        Args:
            key: Variable name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not key:
            return False, "Variable name cannot be empty"

        # Must start with letter or underscore
        if not re.match(r"^[a-zA-Z_]", key):
            return False, "Variable name must start with a letter or underscore"

        # Must contain only alphanumeric and underscores
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
            return False, "Variable name can only contain letters, numbers, and underscores"

        return True, ""

    @classmethod
    def detect_secrets(cls, value: str) -> list[str]:
        """Detect potential secrets in environment variable value.

        Args:
            value: Environment variable value

        Returns:
            List of warning messages for detected patterns
        """
        warnings = []
        value_lower = value.lower()

        for pattern, name in cls.SECRET_PATTERNS:
            if re.search(pattern, value_lower):
                warnings.append(f"Value contains potential secret pattern: {name}")

        return warnings

    # Private helper methods

    @classmethod
    def _read_bashrc(cls, ssh_config: SSHConfig) -> str:
        """Read ~/.bashrc from remote VM using SSH stdin redirection.

        Security: Uses Python script via SSH stdin to eliminate shell command injection.
        No user input is interpolated into shell commands.
        """
        try:
            # Python script to safely read file
            python_script = """
import sys
from pathlib import Path

try:
    bashrc_path = Path.home() / '.bashrc'
    if bashrc_path.exists():
        content = bashrc_path.read_text()
        sys.stdout.write(content)
    else:
        # Empty file if doesn't exist
        sys.stdout.write('')
except Exception as e:
    sys.stderr.write(f"Error reading bashrc: {e}\\n")
    sys.exit(1)
"""

            # Build SSH command with stdin redirection
            ssh_args = [
                "ssh",
                "-i", str(ssh_config.key_path),
                "-p", str(ssh_config.port),
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=30",
            ]

            if not ssh_config.strict_host_key_checking:
                ssh_args.extend(["-o", "StrictHostKeyChecking=no"])
                ssh_args.extend(["-o", "UserKnownHostsFile=/dev/null"])

            ssh_args.extend([
                f"{ssh_config.user}@{ssh_config.host}",
                "python3"
            ])

            # Execute with stdin redirection
            result = subprocess.run(
                ssh_args,
                input=python_script,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise EnvManagerError(f"SSH command failed: {result.stderr}")

            # Validate content size
            cls._validate_content_size(result.stdout)

            return result.stdout

        except subprocess.TimeoutExpired:
            raise EnvManagerError("SSH command timed out")
        except Exception as e:
            raise EnvManagerError(f"Failed to read ~/.bashrc: {e}")

    @classmethod
    def _write_bashrc(cls, ssh_config: SSHConfig, content: str) -> None:
        """Write ~/.bashrc to remote VM using SSH stdin redirection.

        Security: Uses Python script via SSH stdin to eliminate shell command injection.
        Content is base64-encoded and passed via stdin, never interpolated into shell.
        """
        try:
            # Validate content size before transmission
            cls._validate_content_size(content)

            # Base64 encode content to safely transmit
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')

            # Python script to safely write file
            python_script = f"""
import sys
import base64
from pathlib import Path

try:
    # Decode content
    encoded_content = "{encoded_content}"
    content = base64.b64decode(encoded_content).decode('utf-8')

    # Write to temp file then move (atomic operation)
    home = Path.home()
    temp_path = home / '.bashrc.tmp'
    final_path = home / '.bashrc'

    # Write to temp file
    temp_path.write_text(content)

    # Atomic move
    temp_path.rename(final_path)

    sys.stdout.write('OK\\n')
except Exception as e:
    sys.stderr.write(f"Error writing bashrc: {{e}}\\n")
    sys.exit(1)
"""

            # Build SSH command with stdin redirection
            ssh_args = [
                "ssh",
                "-i", str(ssh_config.key_path),
                "-p", str(ssh_config.port),
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=30",
            ]

            if not ssh_config.strict_host_key_checking:
                ssh_args.extend(["-o", "StrictHostKeyChecking=no"])
                ssh_args.extend(["-o", "UserKnownHostsFile=/dev/null"])

            ssh_args.extend([
                f"{ssh_config.user}@{ssh_config.host}",
                "python3"
            ])

            # Execute with stdin redirection
            result = subprocess.run(
                ssh_args,
                input=python_script,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise EnvManagerError(f"SSH command failed: {result.stderr}")

            if "OK" not in result.stdout:
                raise EnvManagerError("Write operation did not complete successfully")

        except subprocess.TimeoutExpired:
            raise EnvManagerError("SSH command timed out")
        except Exception as e:
            raise EnvManagerError(f"Failed to write ~/.bashrc: {e}")

    @classmethod
    def _extract_env_vars(cls, bashrc_content: str) -> dict[str, str]:
        """Extract azlin-managed environment variables from bashrc content."""
        env_vars = {}

        # Find the azlin env section
        in_section = False
        for line in bashrc_content.splitlines():
            if cls.ENV_MARKER_START in line:
                in_section = True
                continue
            if cls.ENV_MARKER_END in line:
                break
            if in_section:
                # Parse export lines: export KEY="value" or export KEY=value
                match = re.match(r'export\s+([A-Z_][A-Z0-9_]*)="?(.*?)"?\s*$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2)
                    env_vars[key] = value

        return env_vars

    @classmethod
    def _update_bashrc_with_env_vars(cls, bashrc_content: str, env_vars: dict[str, str]) -> str:
        """Update bashrc content with new environment variables."""
        # Remove existing azlin env section
        new_content = cls._remove_env_section(bashrc_content)

        # If there are env vars to add, create the section
        if env_vars:
            env_lines = [cls.ENV_MARKER_START]
            for key, value in sorted(env_vars.items()):
                # Escape quotes in value
                escaped_value = value.replace('"', '\\"')
                env_lines.append(f'export {key}="{escaped_value}"')
            env_lines.append(cls.ENV_MARKER_END)

            # Append to the end of the file
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            new_content += "\n".join(env_lines) + "\n"

        return new_content

    @classmethod
    def _remove_env_section(cls, bashrc_content: str) -> str:
        """Remove azlin env section from bashrc content."""
        lines = bashrc_content.splitlines()
        new_lines = []
        in_section = False

        for line in lines:
            if cls.ENV_MARKER_START in line:
                in_section = True
                continue
            if cls.ENV_MARKER_END in line:
                in_section = False
                continue
            if not in_section:
                new_lines.append(line)

        return "\n".join(new_lines)


__all__ = ["EnvManager", "EnvManagerError"]
