"""Core PWA configuration generator implementation.

Extracts Azure configuration from multiple sources:
1. Azure CLI (az account show) - highest priority
2. azlin config.toml file - fallback
3. Default values - last resort

CRITICAL: Never overwrites existing .env files without force=True flag.
"""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from azlin.modules.azure_cli_helper import get_az_command


class ConfigSource(Enum):
    """Source of configuration values for tracking provenance."""

    AZURE_CLI = "azure_cli"
    AZLIN_CONFIG = "azlin_config"
    DEFAULT = "default"
    EXISTING_ENV = "existing_env"


@dataclass
class PWAConfigResult:
    """Result of PWA configuration generation operation."""

    success: bool
    env_path: Path | None
    config_values: dict[str, str]
    source_attribution: dict[str, ConfigSource]
    message: str
    error: str | None = None


class PWAConfigGenerator:
    """Generates PWA .env configuration from azlin parent config.

    Extracts Azure configuration from:
    1. Azure CLI (az account show) - highest priority
    2. azlin config.toml - fallback
    3. Default values - last resort

    Key Features:
    - NEVER overwrites existing .env without force=True
    - Tracks source attribution for each value
    - Generates Vite-compatible .env format (VITE_* prefix)
    - Graceful fallback when Azure CLI unavailable
    """

    def __init__(self):
        """Initialize PWA config generator."""
        self._last_error = None  # Track last error for better error messages

    def is_azure_cli_available(self) -> bool:
        """Check if Azure CLI is installed and available.

        Returns:
            True if az command is available, False otherwise
        """
        return shutil.which("az") is not None

    def extract_azure_config(self) -> dict[str, str] | None:
        """Extract Azure configuration from Azure CLI.

        Runs 'az account show' to get current Azure subscription info.

        Returns:
            Dictionary with subscription_id and tenant_id, or None if extraction fails
        """
        self._last_error = None  # Reset error

        if not self.is_azure_cli_available():
            return None

        try:
            result = subprocess.run(
                [get_az_command(), "account", "show", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Capture stderr for error reporting
                self._last_error = (
                    result.stderr.strip()
                    if result.stderr
                    else f"Azure CLI command failed with exit code {result.returncode}"
                )
                return None

            data = json.loads(result.stdout)

            config = {}
            if data.get("id"):
                config["subscription_id"] = data["id"]
            if data.get("tenantId"):
                config["tenant_id"] = data["tenantId"]

            return config if config else None

        except subprocess.TimeoutExpired:
            self._last_error = "Azure CLI command timed out after 30 seconds"
            return None
        except json.JSONDecodeError as e:
            self._last_error = f"Failed to parse Azure CLI JSON output: {e}"
            return None
        except Exception as e:
            self._last_error = f"Unexpected error running Azure CLI: {e}"
            return None

    def extract_from_azlin_config(self, azlin_config_dir: Path) -> dict[str, str] | None:
        """Extract Azure configuration from azlin config.toml file.

        Args:
            azlin_config_dir: Path to .azlin directory containing config.toml

        Returns:
            Dictionary with configuration values, or None if file doesn't exist
        """
        config_file = azlin_config_dir / "config.toml"
        if not config_file.exists():
            return None

        try:
            content = config_file.read_text()
            config = {}

            # Simple TOML parsing for [azure] section
            in_azure_section = False
            for line in content.split("\n"):
                line = line.strip()

                if line == "[azure]":
                    in_azure_section = True
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_azure_section = False
                    continue

                if in_azure_section and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    config[key] = value

            return config if config else None

        except Exception:
            return None

    def map_azure_config_to_env_vars(self, azure_config: dict[str, str]) -> dict[str, str]:
        """Map Azure configuration to Vite environment variables.

        Args:
            azure_config: Dictionary with subscription_id, tenant_id, etc.

        Returns:
            Dictionary with VITE_* prefixed environment variables
        """
        env_vars = {}

        if "subscription_id" in azure_config:
            env_vars["VITE_AZURE_SUBSCRIPTION_ID"] = azure_config["subscription_id"]

        if "tenant_id" in azure_config:
            env_vars["VITE_AZURE_TENANT_ID"] = azure_config["tenant_id"]

        if "resource_group" in azure_config:
            env_vars["VITE_AZURE_RESOURCE_GROUP"] = azure_config["resource_group"]

        return env_vars

    def is_valid_subscription_id(self, subscription_id: str) -> bool:
        """Validate subscription ID format (UUID).

        Args:
            subscription_id: Subscription ID to validate

        Returns:
            True if valid UUID format, False otherwise
        """
        if not subscription_id:
            return False

        # UUID format: 8-4-4-4-12 hexadecimal characters
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        return bool(uuid_pattern.match(subscription_id))

    def generate_env_file_content(
        self,
        config_values: dict[str, str],
        source_attribution: dict[str, ConfigSource],
    ) -> str:
        """Generate .env file content with comments and source attribution.

        Args:
            config_values: Dictionary of environment variables
            source_attribution: Dictionary tracking source of each value

        Returns:
            Formatted .env file content as string
        """
        lines = [
            "# PWA Configuration - Generated by azlin",
            "# Source: Azure CLI and/or azlin config.toml",
            "",
        ]

        # Group by source for better organization
        for key, value in sorted(config_values.items()):
            source = source_attribution.get(key, ConfigSource.DEFAULT)
            lines.append(f"# Source: {source.value}")
            lines.append(f"{key}={value}")
            lines.append("")

        # Add placeholder for client ID (must be manually configured)
        lines.extend(
            [
                "# VITE_AZURE_CLIENT_ID must be configured manually",
                "# Get this from Azure Portal > App Registrations",
                "# VITE_AZURE_CLIENT_ID=your-client-id-here",
                "",
            ]
        )

        # Add default redirect URI
        lines.extend(
            [
                "# Default redirect URI for local development",
                "VITE_AZURE_REDIRECT_URI=http://localhost:3000",
                "",
            ]
        )

        return "\n".join(lines)

    def generate_pwa_env_from_azlin(
        self,
        pwa_dir: Path,
        azlin_config_dir: Path | None = None,
        force: bool = False,
    ) -> PWAConfigResult:
        """Generate PWA .env file from azlin configuration.

        This is the main public API method.

        Args:
            pwa_dir: Path to PWA directory where .env will be created
            azlin_config_dir: Path to .azlin directory (optional, for config.toml)
            force: If True, overwrite existing .env file

        Returns:
            PWAConfigResult with success status, file path, and messages
        """
        # Validate PWA directory exists
        if not pwa_dir.exists():
            # Create directory if it doesn't exist
            try:
                pwa_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return PWAConfigResult(
                    success=False,
                    env_path=None,
                    config_values={},
                    source_attribution={},
                    message=f"Failed to create PWA directory: {pwa_dir}",
                    error=str(e),
                )

        env_path = pwa_dir / ".env"

        # CRITICAL: Never overwrite existing .env without force flag
        try:
            exists = env_path.exists()
        except PermissionError:
            # Directory not readable - permission error
            return PWAConfigResult(
                success=False,
                env_path=None,
                config_values={},
                source_attribution={},
                message=f"Permission denied accessing {pwa_dir}",
                error="Cannot check if .env exists due to permission error",
            )

        if exists and not force:
            return PWAConfigResult(
                success=False,
                env_path=None,
                config_values={},
                source_attribution={},
                message=f".env already exists at {env_path}. Use force=True to overwrite.",
                error=None,
            )

        # Extract configuration from available sources
        config_values = {}
        source_attribution = {}
        messages = []

        # Try Azure CLI first (highest priority)
        azure_config = self.extract_azure_config()
        if azure_config:
            env_vars = self.map_azure_config_to_env_vars(azure_config)
            for key, value in env_vars.items():
                # Validate subscription ID if present
                if key == "VITE_AZURE_SUBSCRIPTION_ID":
                    if not value:
                        messages.append("Warning: Empty subscription ID from Azure CLI")
                        continue
                    # Only validate if it has 4 dashes (looks like a full UUID: xxxx-xxxx-xxxx-xxxx-xxxx)
                    if value.count("-") == 4 and not self.is_valid_subscription_id(value):
                        messages.append(f"Warning: Invalid subscription ID UUID format: {value}")
                        continue

                config_values[key] = value
                source_attribution[key] = ConfigSource.AZURE_CLI

            messages.append("Successfully extracted configuration from Azure CLI")
        elif self._last_error:
            # Azure CLI is available but command failed - this is an error we should report
            messages.append(f"Azure CLI command failed: {self._last_error}")
        else:
            # Azure CLI not installed/available
            messages.append("Azure CLI not available or not authenticated")

        # Try azlin config.toml as fallback
        if azlin_config_dir:
            azlin_config = self.extract_from_azlin_config(azlin_config_dir)
            if azlin_config:
                env_vars = self.map_azure_config_to_env_vars(azlin_config)
                for key, value in env_vars.items():
                    # Only add if not already present from Azure CLI
                    if key not in config_values:
                        config_values[key] = value
                        source_attribution[key] = ConfigSource.AZLIN_CONFIG

                messages.append("Extracted additional configuration from azlin config.toml")

        # Check if we have any meaningful Azure configuration (subscription_id or tenant_id)
        has_azure_config = any(
            key in config_values for key in ["VITE_AZURE_SUBSCRIPTION_ID", "VITE_AZURE_TENANT_ID"]
        )

        if not has_azure_config:
            # No Azure config from any source
            # If Azure CLI had a specific error (not just unavailable), treat as failure
            if self._last_error:
                return PWAConfigResult(
                    success=False,
                    env_path=None,
                    config_values={},
                    source_attribution={},
                    message="\n".join(messages),
                    error=self._last_error,
                )

            # Otherwise, graceful fallback: create .env with placeholders and helpful message
            if azlin_config_dir:
                messages.append(f"No configuration found in {azlin_config_dir}/config.toml")
            messages.append("Creating .env with placeholder values")
            messages.append(
                "Please configure Azure values manually:\n"
                + "  - VITE_AZURE_SUBSCRIPTION_ID\n"
                + "  - VITE_AZURE_TENANT_ID\n"
                + "  - VITE_AZURE_CLIENT_ID"
            )

            # Add default redirect URI as the only real value
            config_values["VITE_AZURE_REDIRECT_URI"] = "http://localhost:3000"
            source_attribution["VITE_AZURE_REDIRECT_URI"] = ConfigSource.DEFAULT

        # Generate .env file content
        env_content = self.generate_env_file_content(config_values, source_attribution)

        # Write .env file
        try:
            env_path.write_text(env_content, encoding="utf-8")
        except PermissionError as e:
            return PWAConfigResult(
                success=False,
                env_path=None,
                config_values={},
                source_attribution={},
                message=f"Permission denied writing to {env_path}",
                error=str(e),
            )
        except Exception as e:
            return PWAConfigResult(
                success=False,
                env_path=None,
                config_values={},
                source_attribution={},
                message=f"Failed to write .env file: {e!s}",
                error=str(e),
            )

        return PWAConfigResult(
            success=True,
            env_path=env_path,
            config_values=config_values,
            source_attribution=source_attribution,
            message="\n".join(messages),
            error=None,
        )
