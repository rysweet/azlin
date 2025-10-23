"""Profile manager for authentication profiles.

This module provides CRUD operations for authentication profiles stored in
~/.azlin/profiles/ directory.

Security Features (P0):
- NO secrets stored in profile files
- Profile files created with 0600 permissions (owner read/write only)
- Profile name validation (alphanumeric + dash/underscore only)
- Path traversal prevention
- AuthConfig validation before saving
- Secret detection using Brick 7

Profile File Format:
- TOML format for consistency
- Stored at ~/.azlin/profiles/<profile_name>.toml
- Contains auth method, Azure IDs, certificate paths
- Includes metadata (created_at, last_used timestamps)
- NO secrets (client_secret, private keys, etc.)

Philosophy:
- Ruthless simplicity - straightforward file operations
- Self-contained module - minimal dependencies
- Quality over speed - thorough validation
- Fail fast on security violations
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import tomli  # type: ignore[import]
    import tomli_w
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import]

        import tomli_w
    except ImportError as e:
        raise ImportError(
            "toml library not available. Install with: pip install tomli tomli-w"
        ) from e

from azlin.auth_security import detect_secrets_in_config
from azlin.config_auth import AuthConfig, validate_auth_config

logger = logging.getLogger(__name__)


class ProfileError(Exception):
    """Raised when profile operations fail."""

    pass


@dataclass
class ProfileInfo:
    """Profile metadata.

    Attributes:
        name: Profile name
        auth_method: Authentication method (az_cli, service_principal_cert, etc.)
        tenant_id: Azure tenant ID (UUID)
        client_id: Azure client/application ID (UUID)
        subscription_id: Azure subscription ID (UUID)
        created_at: Timestamp when profile was created
        last_used: Timestamp when profile was last used (None if never used)
    """

    name: str
    auth_method: str
    tenant_id: str | None
    client_id: str | None
    subscription_id: str | None
    created_at: datetime
    last_used: datetime | None


class ProfileManager:
    """Manage authentication profiles.

    Provides CRUD operations for authentication profiles with security controls:
    - Profile name validation (prevents path traversal)
    - Secret detection (rejects profiles with embedded secrets)
    - File permission enforcement (0600 for profile files)
    - AuthConfig validation (ensures valid configuration)

    Examples:
        >>> manager = ProfileManager()
        >>> config = AuthConfig(
        ...     auth_method="service_principal_cert",
        ...     tenant_id="12345678-1234-1234-1234-123456789abc",
        ...     client_id="87654321-4321-4321-4321-cba987654321",
        ...     client_certificate_path="~/certs/prod.pem",
        ... )
        >>> info = manager.create_profile("production", config)
        >>> loaded = manager.get_profile("production")
    """

    DEFAULT_PROFILES_DIR = Path.home() / ".azlin" / "profiles"

    def __init__(self, profiles_dir: Path | None = None):
        """Initialize ProfileManager.

        Args:
            profiles_dir: Directory to store profiles (default: ~/.azlin/profiles/)

        Creates the profiles directory with secure permissions (0700) if it doesn't exist.
        """
        self.profiles_dir = profiles_dir or self.DEFAULT_PROFILES_DIR

        # Ensure directory exists with secure permissions
        self._ensure_profiles_dir()

    def _ensure_profiles_dir(self) -> None:
        """Ensure profiles directory exists with secure permissions.

        Creates directory with 0700 permissions (owner only: rwx------).

        Raises:
            ProfileError: If directory creation fails
        """
        try:
            self.profiles_dir.mkdir(parents=True, exist_ok=True)

            # Set secure permissions (owner only: rwx------)
            os.chmod(self.profiles_dir, 0o700)

            logger.debug(f"Profiles directory ready: {self.profiles_dir}")

        except Exception as e:
            raise ProfileError(f"Failed to create profiles directory: {e}") from e

    def _validate_profile_name(self, name: str) -> None:
        """Validate profile name for security.

        Profile names must be:
        - Non-empty
        - 1-64 characters
        - Alphanumeric, dash, or underscore only

        Args:
            name: Profile name to validate

        Raises:
            ProfileError: If name is invalid

        Security:
            - Prevents path traversal attacks (../../../etc/passwd)
            - Prevents directory traversal (profile/subdir/file)
            - Limits character set to safe values
            - Enforces reasonable length limits
        """
        if not name or not name.strip():
            raise ProfileError("Invalid profile name: empty or whitespace-only")

        # Azure-style naming: alphanumeric + dash/underscore, 1-64 chars
        # This prevents path traversal and special characters
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", name):
            raise ProfileError(
                f"Invalid profile name: {name}\n"
                f"Profile names must be 1-64 characters: alphanumeric, dash, or underscore only.\n"
                f"This restriction prevents path traversal attacks."
            )

    def _get_profile_path(self, name: str) -> Path:
        """Get path to profile file.

        Args:
            name: Profile name

        Returns:
            Path to profile TOML file

        Raises:
            ProfileError: If name is invalid
        """
        self._validate_profile_name(name)
        return self.profiles_dir / f"{name}.toml"

    def _check_for_secrets(self, config: AuthConfig) -> None:
        """Check AuthConfig for embedded secrets.

        Args:
            config: AuthConfig to check

        Raises:
            ProfileError: If secrets are detected

        Security:
            Checks for forbidden secrets in profile:
            - client_secret field (FORBIDDEN - must use environment variable)
            - password field (FORBIDDEN)
            - Long base64 strings (potential tokens)
            - Long hex strings (potential secrets)
            - Private key content (PEM blocks)

            ALLOWED fields that are safe to store:
            - client_certificate_path (path to cert file, not the cert itself)
            - tenant_id, client_id, subscription_id (Azure UUIDs, public identifiers)
        """
        # Build config dict for secret detection
        # Explicitly exclude safe fields that contain "certificate" but are just paths
        config_dict = {
            "auth_method": config.auth_method,
            "tenant_id": config.tenant_id,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            # Don't include client_certificate_path in secret detection
            # as it's just a file path, not secret content
            "subscription_id": config.subscription_id,
        }

        # Detect secrets using Brick 7
        secrets = detect_secrets_in_config(config_dict)

        # Filter out false positives:
        # - Paths are safe (e.g., client_certificate_path)
        # - Azure UUIDs are safe (already handled by detect_secrets_in_config)
        filtered_secrets = []
        for secret in secrets:
            # Skip fields that are just paths
            if "_path" in secret.lower():
                continue
            filtered_secrets.append(secret)

        if filtered_secrets:
            raise ProfileError(
                f"SECURITY VIOLATION: Profile contains secrets that cannot be stored in profiles.\n"
                f"Fields with secrets: {', '.join(filtered_secrets)}\n"
                f"\n"
                f"Security Policy:\n"
                f"- client_secret MUST be provided via AZURE_CLIENT_SECRET environment variable\n"
                f"- Profiles store ONLY configuration metadata (IDs, paths, method)\n"
                f"- NO secrets are ever stored in profile files\n"
                f"\n"
                f"Remove these fields from your profile configuration."
            )

    def _validate_config(self, config: AuthConfig) -> None:
        """Validate AuthConfig.

        Args:
            config: AuthConfig to validate

        Raises:
            ProfileError: If configuration is invalid

        Validates:
            - Auth method is supported
            - Required fields are present
            - UUID formats are correct
            - Certificate files exist (if applicable)
        """
        result = validate_auth_config(config)

        if not result.is_valid:
            error_msg = "Invalid configuration:\n" + "\n".join(f"  - {e}" for e in result.errors)
            raise ProfileError(error_msg)

        # Log warnings
        for warning in result.warnings:
            logger.warning(warning)

    def _set_file_permissions(self, path: Path) -> None:
        """Set secure file permissions on profile file.

        Args:
            path: Path to profile file

        Security:
            Sets permissions to 0600 (owner read/write only, no group/other access).
        """
        try:
            os.chmod(path, 0o600)
        except Exception as e:
            logger.warning(f"Failed to set secure permissions on {path}: {e}")

    def _check_file_permissions(self, path: Path) -> None:
        """Check and fix insecure file permissions.

        Args:
            path: Path to profile file

        Security:
            Checks if file has group/other permissions and fixes them to 0600.
        """
        try:
            stat = path.stat()
            mode = stat.st_mode & 0o777

            # Check if group or others have any permissions
            if mode & 0o077:
                logger.warning(
                    f"Profile file has insecure permissions: {oct(mode)}. Fixing to 0600..."
                )
                self._set_file_permissions(path)

        except Exception as e:
            logger.warning(f"Could not check file permissions for {path}: {e}")

    def create_profile(self, name: str, config: AuthConfig) -> ProfileInfo:
        """Create new authentication profile.

        Args:
            name: Profile name (alphanumeric + dash/underscore only)
            config: AuthConfig from Brick 1

        Returns:
            ProfileInfo with metadata

        Raises:
            ProfileError: If profile exists, name is invalid, config is invalid,
                         or contains secrets

        Security:
            - Validates profile name (prevents path traversal)
            - Validates AuthConfig (ensures correct format)
            - Checks for secrets (rejects profiles with embedded secrets)
            - Sets file permissions to 0600
        """
        # Validate profile name
        self._validate_profile_name(name)

        # Get profile path
        profile_path = self._get_profile_path(name)

        # Check if already exists
        if profile_path.exists():
            raise ProfileError(f"Profile '{name}' already exists at: {profile_path}")

        # Security: Check for secrets
        self._check_for_secrets(config)

        # Validate configuration
        self._validate_config(config)

        # Prepare profile data
        created_at = datetime.now(UTC)

        profile_data: dict[str, Any] = {
            "auth_method": config.auth_method,
        }

        # Add optional fields (only if not None)
        if config.tenant_id:
            profile_data["tenant_id"] = config.tenant_id
        if config.client_id:
            profile_data["client_id"] = config.client_id
        if config.client_certificate_path:
            profile_data["client_certificate_path"] = config.client_certificate_path
        if config.subscription_id:
            profile_data["subscription_id"] = config.subscription_id

        # Add metadata
        profile_data["metadata"] = {
            "created_at": created_at.isoformat(),
        }

        # Write TOML file
        try:
            with open(profile_path, "wb") as f:
                tomli_w.dump(profile_data, f)

            # Set secure permissions
            self._set_file_permissions(profile_path)

            logger.info(f"Created profile '{name}' at: {profile_path}")

            # Return ProfileInfo
            return ProfileInfo(
                name=name,
                auth_method=config.auth_method,
                tenant_id=config.tenant_id,
                client_id=config.client_id,
                subscription_id=config.subscription_id,
                created_at=created_at,
                last_used=None,
            )

        except Exception as e:
            # Clean up on error
            if profile_path.exists():
                profile_path.unlink()
            raise ProfileError(f"Failed to create profile '{name}': {e}") from e

    def get_profile(self, name: str) -> AuthConfig:
        """Load profile configuration.

        Args:
            name: Profile name

        Returns:
            AuthConfig that can be passed to AuthResolver

        Raises:
            ProfileError: If profile not found, name is invalid, or file contains secrets

        Security:
            - Validates profile name
            - Checks file permissions (fixes if insecure)
            - Checks for secrets (defense in depth)
        """
        # Validate profile name
        self._validate_profile_name(name)

        # Get profile path
        profile_path = self._get_profile_path(name)

        # Check if exists
        if not profile_path.exists():
            raise ProfileError(f"Profile '{name}' not found at: {profile_path}")

        try:
            # Check and fix file permissions
            self._check_file_permissions(profile_path)

            # Load TOML
            with open(profile_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            # Security: Check for secrets (defense in depth)
            # Build a dict without safe path fields for secret detection
            data_for_secret_check = {
                k: v for k, v in data.items() if k not in ["client_certificate_path", "metadata"]
            }
            secrets = detect_secrets_in_config(data_for_secret_check)

            # Filter out false positives (paths are safe)
            filtered_secrets = [s for s in secrets if "_path" not in s.lower()]

            if filtered_secrets:
                raise ProfileError(
                    f"SECURITY VIOLATION: Profile '{name}' contains secrets that cannot be stored in profiles.\n"
                    f"Fields with secrets: {', '.join(filtered_secrets)}\n"
                    f"Profile file: {profile_path}\n"
                    f"\n"
                    f"Action Required:\n"
                    f"1. Delete this profile: azlin profile delete {name}\n"
                    f"2. Recreate without secrets (use environment variables for secrets)\n"
                )

            # Extract auth config
            auth_method = data.get("auth_method", "az_cli")
            tenant_id = data.get("tenant_id")
            client_id = data.get("client_id")
            client_certificate_path = data.get("client_certificate_path")
            subscription_id = data.get("subscription_id")

            # Validate required fields exist
            if not auth_method:
                raise ProfileError(f"Profile '{name}' missing required field: auth_method")

            # Create AuthConfig
            config = AuthConfig(
                auth_method=auth_method,
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=None,  # Never load secrets from profile
                client_certificate_path=client_certificate_path,
                subscription_id=subscription_id,
                profile_name=name,
            )

            logger.debug(f"Loaded profile '{name}' from: {profile_path}")

            return config

        except ProfileError:
            raise
        except Exception as e:
            raise ProfileError(f"Failed to load profile '{name}': {e}") from e

    def list_profiles(self) -> list[ProfileInfo]:
        """List all available profiles with metadata.

        Returns:
            List of ProfileInfo objects, sorted by name

        Note:
            Silently skips non-TOML files and corrupted profiles.
        """
        profiles = []

        # Iterate through .toml files in profiles directory
        for profile_path in sorted(self.profiles_dir.glob("*.toml")):
            try:
                # Extract profile name from filename
                name = profile_path.stem

                # Load profile data
                with open(profile_path, "rb") as f:
                    data = tomli.load(f)  # type: ignore[attr-defined]

                # Extract fields
                auth_method = data.get("auth_method", "az_cli")
                tenant_id = data.get("tenant_id")
                client_id = data.get("client_id")
                subscription_id = data.get("subscription_id")

                # Extract metadata
                metadata = data.get("metadata", {})
                created_at_str = metadata.get("created_at")
                last_used_str = metadata.get("last_used")

                # Parse timestamps
                created_at = (
                    datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(UTC)
                )
                last_used = datetime.fromisoformat(last_used_str) if last_used_str else None

                # Create ProfileInfo
                info = ProfileInfo(
                    name=name,
                    auth_method=auth_method,
                    tenant_id=tenant_id,
                    client_id=client_id,
                    subscription_id=subscription_id,
                    created_at=created_at,
                    last_used=last_used,
                )

                profiles.append(info)

            except Exception as e:
                logger.warning(f"Failed to load profile from {profile_path}: {e}")
                continue

        return profiles

    def delete_profile(self, name: str) -> bool:
        """Delete profile.

        Args:
            name: Profile name

        Returns:
            True if deleted, False if not found

        Raises:
            ProfileError: If name is invalid
        """
        # Validate profile name
        self._validate_profile_name(name)

        # Get profile path
        profile_path = self._get_profile_path(name)

        # Check if exists
        if not profile_path.exists():
            return False

        try:
            profile_path.unlink()
            logger.info(f"Deleted profile '{name}' from: {profile_path}")
            return True

        except Exception as e:
            raise ProfileError(f"Failed to delete profile '{name}': {e}") from e

    def update_last_used(self, name: str) -> None:
        """Update last_used timestamp for profile.

        Args:
            name: Profile name

        Raises:
            ProfileError: If profile not found or name is invalid
        """
        # Validate profile name
        self._validate_profile_name(name)

        # Get profile path
        profile_path = self._get_profile_path(name)

        # Check if exists
        if not profile_path.exists():
            raise ProfileError(f"Profile '{name}' not found at: {profile_path}")

        try:
            # Load existing data
            with open(profile_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            # Update last_used in metadata
            if "metadata" not in data:
                data["metadata"] = {}

            data["metadata"]["last_used"] = datetime.now(UTC).isoformat()

            # Write back
            with open(profile_path, "wb") as f:
                tomli_w.dump(data, f)

            # Maintain secure permissions
            self._set_file_permissions(profile_path)

            logger.debug(f"Updated last_used for profile '{name}'")

        except Exception as e:
            raise ProfileError(f"Failed to update last_used for profile '{name}': {e}") from e

    def profile_exists(self, name: str) -> bool:
        """Check if profile exists.

        Args:
            name: Profile name

        Returns:
            True if profile exists, False otherwise

        Raises:
            ProfileError: If name is invalid
        """
        # Validate profile name
        self._validate_profile_name(name)

        # Get profile path
        profile_path = self._get_profile_path(name)

        return profile_path.exists()


__all__ = [
    "ProfileError",
    "ProfileInfo",
    "ProfileManager",
]
