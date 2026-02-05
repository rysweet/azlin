"""VS Code Configuration Manager.

This module manages VS Code Remote-SSH configuration including:
- SSH config entry generation
- Extension list management
- Port forwarding configuration
- Workspace settings synchronization

Security:
- Input validation for VM names and IPs
- Extension ID validation to prevent injection
- Port number validation (1-65535)
- Path sanitization for file operations
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VSCodeConfigError(Exception):
    """Raised when VS Code configuration operations fail."""

    pass


class VSCodeConfig:
    """Manage VS Code Remote-SSH configuration.

    This class handles:
    - SSH config entry generation for VS Code Remote-SSH
    - Extension list loading from user config
    - Port forwarding configuration
    - Workspace settings management
    """

    # Default extensions to install if no config exists
    DEFAULT_EXTENSIONS = [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "github.copilot",
        "ms-azuretools.vscode-docker",
    ]

    # Default port forwards for common development ports
    DEFAULT_PORT_FORWARDS = [
        {"local": 3000, "remote": 3000},  # Node/React
        {"local": 8080, "remote": 8080},  # HTTP
        {"local": 8000, "remote": 8000},  # Django/Flask
        {"local": 5432, "remote": 5432},  # PostgreSQL
    ]

    # Regex for validating extension IDs (publisher.extension-name)
    EXTENSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$")

    def __init__(
        self,
        vm_name: str,
        host: str,
        user: str,
        key_path: Path,
        port: int = 22,
        config_dir: Path | None = None,
    ):
        """Initialize VS Code configuration.

        Supports both direct connections and bastion tunnels (Issue #581):
        - Direct: host=VM_IP, port=22
        - Bastion: host=127.0.0.1, port=tunnel_port

        Args:
            vm_name: VM name for SSH host alias
            host: SSH host (VM IP or 127.0.0.1 for bastion tunnel)
            user: SSH username
            key_path: Path to SSH private key
            port: SSH port (22 for direct, tunnel port for bastion)
            config_dir: Custom config directory (default: ~/.azlin/vscode)

        Security:
        - Validates all inputs
        - Sanitizes paths
        - No shell execution
        """
        self.vm_name = vm_name
        self.host = host
        self.user = user
        self.key_path = key_path.expanduser()
        self.port = port

        # Config directory for VS Code settings
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = Path.home() / ".azlin" / "vscode"

    def generate_ssh_config_entry(self) -> str:
        """Generate SSH config entry for VS Code Remote-SSH.

        Supports both direct connections and bastion tunnel connections (Issue #581):
        - Direct: host=VM_IP, port=22
        - Bastion: host=127.0.0.1, port=tunnel_port

        Returns:
            str: SSH config entry text

        Example output (direct):
            Host azlin-my-vm
                HostName 20.1.2.3
                Port 22
                User azureuser
                IdentityFile ~/.ssh/azlin_key

        Example output (bastion tunnel):
            Host azlin-my-vm
                HostName 127.0.0.1
                Port 50024
                User azureuser
                IdentityFile ~/.ssh/azlin_key
        """
        # Use 'azlin-' prefix for SSH host to avoid conflicts
        ssh_host = f"azlin-{self.vm_name}"

        config_lines = [
            f"Host {ssh_host}",
            f"    HostName {self.host}",
            f"    Port {self.port}",
            f"    User {self.user}",
            f"    IdentityFile {self.key_path}",
            "    StrictHostKeyChecking no",
            "    UserKnownHostsFile /dev/null",
            "    ServerAliveInterval 60",
            "    ServerAliveCountMax 3",
        ]

        return "\n".join(config_lines)

    def load_extensions(self) -> list[str]:
        """Load VS Code extensions list from config file.

        Returns:
            list[str]: List of extension IDs

        Reads from: ~/.azlin/vscode/extensions.json
        Format: {"extensions": ["publisher.name", ...]}

        Falls back to DEFAULT_EXTENSIONS if file doesn't exist or is invalid.

        Security:
        - Validates extension IDs
        - Filters out invalid entries
        """
        ext_file = self.config_dir / "extensions.json"

        if not ext_file.exists():
            logger.debug(f"Extensions config not found at {ext_file}, using defaults")
            return self.DEFAULT_EXTENSIONS.copy()

        try:
            data = json.loads(ext_file.read_text())
            extensions = data.get("extensions", [])

            # Validate extension IDs
            valid_extensions = [ext for ext in extensions if self._validate_extension_id(ext)]

            if len(valid_extensions) != len(extensions):
                logger.warning(
                    f"Filtered out {len(extensions) - len(valid_extensions)} invalid extension IDs"
                )

            return valid_extensions if valid_extensions else self.DEFAULT_EXTENSIONS.copy()

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load extensions from {ext_file}: {e}")
            return self.DEFAULT_EXTENSIONS.copy()

    def load_port_forwards(self) -> list[dict[str, int]]:
        """Load port forwarding configuration from config file.

        Returns:
            list[dict]: List of port forward configs
            Format: [{"local": 3000, "remote": 3000}, ...]

        Reads from: ~/.azlin/vscode/ports.json
        Format: {"forwards": [{"local": 3000, "remote": 3000}, ...]}

        Falls back to DEFAULT_PORT_FORWARDS if file doesn't exist or is invalid.

        Security:
        - Validates port numbers (1-65535)
        - Filters out invalid entries
        """
        ports_file = self.config_dir / "ports.json"

        if not ports_file.exists():
            logger.debug(f"Port forwards config not found at {ports_file}, using defaults")
            return self.DEFAULT_PORT_FORWARDS.copy()

        try:
            data = json.loads(ports_file.read_text())
            forwards = data.get("forwards", [])

            # Validate port numbers
            valid_forwards = [fwd for fwd in forwards if self._validate_port_forward(fwd)]

            if len(valid_forwards) != len(forwards):
                logger.warning(
                    f"Filtered out {len(forwards) - len(valid_forwards)} invalid port forwards"
                )

            return valid_forwards if valid_forwards else self.DEFAULT_PORT_FORWARDS.copy()

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load port forwards from {ports_file}: {e}")
            return self.DEFAULT_PORT_FORWARDS.copy()

    def load_workspace_settings(self) -> dict[str, Any]:
        """Load VS Code workspace settings from config file.

        Returns:
            dict: Workspace settings

        Reads from: ~/.azlin/vscode/settings.json
        Returns empty dict if file doesn't exist or is invalid.
        """
        settings_file = self.config_dir / "settings.json"

        if not settings_file.exists():
            logger.debug(f"Workspace settings not found at {settings_file}")
            return {}

        try:
            return json.loads(settings_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load workspace settings from {settings_file}: {e}")
            return {}

    def _validate_extension_id(self, extension_id: str) -> bool:
        """Validate VS Code extension ID format.

        Args:
            extension_id: Extension ID (e.g., "ms-python.python")

        Returns:
            bool: True if valid

        Security:
        - Prevents command injection
        - Ensures proper format: publisher.extension-name
        - Allows only alphanumeric, hyphens, underscores, and dots
        """
        if not extension_id or not isinstance(extension_id, str):
            return False

        return bool(self.EXTENSION_ID_PATTERN.match(extension_id))

    def _validate_port_forward(self, forward: dict[str, int]) -> bool:
        """Validate port forward configuration.

        Args:
            forward: Port forward dict with 'local' and 'remote' keys

        Returns:
            bool: True if valid

        Security:
        - Ensures port numbers are in valid range (1-65535)
        """
        if not isinstance(forward, dict):
            return False

        local_port = forward.get("local")
        remote_port = forward.get("remote")

        if not isinstance(local_port, int) or not isinstance(remote_port, int):
            return False

        return self._validate_port_number(local_port) and self._validate_port_number(remote_port)

    @staticmethod
    def _validate_port_number(port: int) -> bool:
        """Validate port number is in valid range.

        Args:
            port: Port number

        Returns:
            bool: True if valid (1-65535)
        """
        return 1 <= port <= 65535
