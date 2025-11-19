"""Multi-tenant kubectl-style context management for azlin.

This module provides kubectl-inspired context management for switching between
Azure subscriptions and tenants. Contexts allow users to manage multiple
Azure environments (dev, staging, production) with different authentication
profiles.

Architecture:
- Contexts stored in config.toml under [contexts] section
- Each context has: subscription_id, tenant_id, auth_profile (optional)
- Current context stored in [contexts.current]
- Backward compatible with existing config format

Security:
- No secrets stored in config (only references to auth profiles)
- All UUIDs validated before use
- Config file permissions enforced (0600)
- Atomic file writes for safety

Example config.toml:
    [contexts]
    current = "production"

    [contexts.definitions.production]
    subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    tenant_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
    auth_profile = "prod-sp"

    [contexts.definitions.development]
    subscription_id = "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"
    tenant_id = "wwwwwwww-wwww-wwww-wwww-wwwwwwwwwwww"
"""

import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomli  # type: ignore[import]
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import]
    except ImportError as e:
        raise ImportError("toml library not available. Install with: pip install tomli") from e

try:
    import tomlkit  # type: ignore[import]
except ImportError as e:
    raise ImportError("tomlkit library not available. Install with: pip install tomlkit") from e

logger = logging.getLogger(__name__)

# Thread lock for subscription switching to prevent race conditions
_subscription_lock = threading.Lock()


class ContextError(Exception):
    """Raised when context operations fail."""

    pass


def validate_uuid(value: str, field_name: str) -> None:
    """Validate UUID format.

    Args:
        value: UUID string to validate
        field_name: Name of field (for error messages)

    Raises:
        ContextError: If UUID format is invalid
    """
    if not value:
        raise ContextError(f"{field_name} cannot be empty")

    # Azure subscription/tenant IDs are UUIDs
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    if not re.match(uuid_pattern, value, re.IGNORECASE):
        raise ContextError(
            f"Invalid {field_name} format: {value}\n"
            f"{field_name} must be a valid UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        )


def validate_context_name(name: str) -> None:
    """Validate context name format.

    Args:
        name: Context name to validate

    Raises:
        ContextError: If name format is invalid

    Rules:
        - 1-64 characters
        - Alphanumeric, hyphen, underscore only
        - Cannot be 'current' (reserved for current context pointer)
        - Cannot be 'definitions' (reserved for context storage)
    """
    if not name:
        raise ContextError("Context name cannot be empty")

    if len(name) > 64:
        raise ContextError(f"Context name too long: {len(name)} characters (max 64)")

    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise ContextError(
            f"Invalid context name: {name}\n"
            "Context names must contain only alphanumeric characters, hyphens, and underscores"
        )

    # Reserved names
    if name.lower() in ["current", "definitions"]:
        raise ContextError(f"Context name '{name}' is reserved and cannot be used")


@dataclass
class Context:
    """Single kubectl-style context definition.

    Represents a specific Azure subscription/tenant combination with
    optional authentication profile.

    Attributes:
        name: Context name (e.g., "production", "dev")
        subscription_id: Azure subscription ID (UUID)
        tenant_id: Azure tenant ID (UUID)
        auth_profile: Optional auth profile name (references [auth.profiles])
        description: Optional human-readable description
    """

    name: str
    subscription_id: str
    tenant_id: str
    auth_profile: str | None = None
    description: str | None = None

    def __post_init__(self):
        """Validate context data after initialization."""
        validate_context_name(self.name)
        validate_uuid(self.subscription_id, "subscription_id")
        validate_uuid(self.tenant_id, "tenant_id")

        # Validate auth_profile name if provided
        if self.auth_profile is not None:
            if not self.auth_profile:
                raise ContextError("auth_profile cannot be empty string (use None instead)")
            if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", self.auth_profile):
                raise ContextError(
                    f"Invalid auth_profile format: {self.auth_profile}\n"
                    "Profile names must be 1-64 characters: alphanumeric, hyphen, or underscore"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization.

        Returns:
            Dictionary with non-None values
        """
        data = {
            "subscription_id": self.subscription_id,
            "tenant_id": self.tenant_id,
        }
        if self.auth_profile is not None:
            data["auth_profile"] = self.auth_profile
        if self.description is not None:
            data["description"] = self.description
        return data

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "Context":
        """Create Context from dictionary.

        Args:
            name: Context name
            data: Context data dictionary

        Returns:
            Context instance

        Raises:
            ContextError: If required fields missing or invalid
        """
        if "subscription_id" not in data:
            raise ContextError(f"Context '{name}' missing required field: subscription_id")
        if "tenant_id" not in data:
            raise ContextError(f"Context '{name}' missing required field: tenant_id")

        return cls(
            name=name,
            subscription_id=data["subscription_id"],
            tenant_id=data["tenant_id"],
            auth_profile=data.get("auth_profile"),
            description=data.get("description"),
        )


@dataclass
class ContextConfig:
    """Complete context configuration.

    Manages all contexts and tracks which one is currently active.

    Attributes:
        current: Name of currently active context (None if not set)
        contexts: Dictionary mapping context name to Context object
    """

    current: str | None = None
    contexts: dict[str, Context] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate current context exists if set
        if self.current is not None:
            if not self.current:
                raise ContextError("current context cannot be empty string (use None instead)")
            if self.current not in self.contexts:
                raise ContextError(
                    f"Current context '{self.current}' not found in contexts: "
                    f"{list(self.contexts.keys())}"
                )

    def get_current_context(self) -> Context | None:
        """Get currently active context.

        Returns:
            Current Context or None if not set
        """
        if self.current is None:
            return None
        return self.contexts.get(self.current)

    def set_current_context(self, name: str) -> None:
        """Set current context.

        Args:
            name: Context name to activate

        Raises:
            ContextError: If context doesn't exist
        """
        if name not in self.contexts:
            raise ContextError(
                f"Context '{name}' not found. Available contexts: {list(self.contexts.keys())}"
            )
        self.current = name

    def add_context(self, context: Context) -> None:
        """Add or update context.

        Args:
            context: Context to add
        """
        self.contexts[context.name] = context

    def delete_context(self, name: str) -> bool:
        """Delete context.

        Args:
            name: Context name to delete

        Returns:
            True if deleted, False if not found

        Note:
            If deleting current context, current is set to None
        """
        if name not in self.contexts:
            return False

        del self.contexts[name]

        # Clear current if we deleted it
        if self.current == name:
            self.current = None

        return True

    def rename_context(self, old_name: str, new_name: str) -> None:
        """Rename context.

        Args:
            old_name: Current context name
            new_name: New context name

        Raises:
            ContextError: If old context doesn't exist or new name already exists
        """
        if old_name not in self.contexts:
            raise ContextError(f"Context '{old_name}' not found")

        if new_name in self.contexts:
            raise ContextError(f"Context '{new_name}' already exists")

        validate_context_name(new_name)

        # Get existing context and update name
        context = self.contexts[old_name]
        context.name = new_name

        # Update dictionary
        self.contexts[new_name] = context
        del self.contexts[old_name]

        # Update current if needed
        if self.current == old_name:
            self.current = new_name

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization.

        Returns:
            Dictionary with contexts and current fields
        """
        data: dict[str, Any] = {}

        if self.current is not None:
            data["current"] = self.current

        if self.contexts:
            data["definitions"] = {name: ctx.to_dict() for name, ctx in self.contexts.items()}

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextConfig":
        """Create ContextConfig from dictionary.

        Args:
            data: Context configuration dictionary

        Returns:
            ContextConfig instance
        """
        current = data.get("current")
        definitions = data.get("definitions", {})

        # Parse contexts
        contexts = {}
        for name, ctx_data in definitions.items():
            contexts[name] = Context.from_dict(name, ctx_data)

        return cls(current=current, contexts=contexts)


class ContextManager:
    """Manage kubectl-style contexts in config.toml.

    This class provides methods to load, save, and manipulate contexts
    stored in the azlin config file.
    """

    DEFAULT_CONFIG_DIR = Path.home() / ".azlin"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"

    @classmethod
    def _validate_config_path(cls, path: Path) -> Path:
        """Validate configuration file path for security.

        Uses same validation as ConfigManager for consistency.

        Args:
            path: Path to validate (must be resolved)

        Returns:
            Validated path

        Raises:
            ContextError: If path is outside allowed directories
        """
        # Ensure path is resolved (symlinks resolved, relative paths absolute)
        resolved_path = path.resolve()

        # Allowed directories
        allowed_dirs = [
            cls.DEFAULT_CONFIG_DIR.resolve(),
            Path.cwd().resolve(),
            Path(tempfile.gettempdir()).resolve(),  # Allow pytest tmp_path
        ]

        # Check if path is within any allowed directory
        for allowed_dir in allowed_dirs:
            try:
                resolved_path.relative_to(allowed_dir)
                return resolved_path
            except ValueError:
                continue

        # Path is not within any allowed directory
        raise ContextError(
            f"Config path outside allowed directories: {resolved_path}\n"
            f"Allowed directories:\n"
            f"  - {cls.DEFAULT_CONFIG_DIR}\n"
            f"  - {Path.cwd()}\n"
            "This restriction prevents path traversal attacks."
        )

    @classmethod
    def load(cls, custom_path: str | None = None) -> ContextConfig:
        """Load context configuration from file.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            ContextConfig object

        Raises:
            ContextError: If loading fails
        """
        config_path = Path(custom_path) if custom_path else cls.DEFAULT_CONFIG_FILE

        if not config_path.exists():
            logger.debug("Config file not found, returning empty context config")
            return ContextConfig()

        try:
            # Validate path
            config_path = cls._validate_config_path(config_path.resolve())

            # Verify file permissions
            stat = config_path.stat()
            mode = stat.st_mode & 0o777

            if mode & 0o077:  # Check if group/other have any permissions
                logger.warning(
                    f"Config file has insecure permissions: {oct(mode)}. Fixing to 0600..."
                )
                os.chmod(config_path, 0o600)

            # Load TOML
            with open(config_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            # Extract contexts section
            contexts_data = data.get("contexts", {})

            logger.debug(f"Loaded context config from: {config_path}")
            return ContextConfig.from_dict(contexts_data)

        except ContextError:
            # Re-raise context errors
            raise
        except Exception as e:
            raise ContextError(f"Failed to load context config: {e}") from e

    @classmethod
    def save(cls, config: ContextConfig, custom_path: str | None = None) -> None:
        """Save context configuration to file.

        Args:
            config: Context configuration to save
            custom_path: Custom config file path (optional)

        Raises:
            ContextError: If saving fails
        """
        # CRITICAL: Prevent tests from modifying production config
        if os.getenv("AZLIN_TEST_MODE") == "true" and custom_path is None:
            raise ContextError(
                "Cannot save to production config during tests. "
                "Tests must use custom_path with tmp_path fixture. "
                "This protects ~/.azlin/config.toml from being overwritten."
            )

        temp_path: Path | None = None
        try:
            # Determine config path
            if custom_path:
                config_path = Path(custom_path).expanduser().resolve()
                # Validate path for security
                config_path = cls._validate_config_path(config_path)
                # Ensure parent directory exists
                config_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # Ensure default directory exists
                cls.DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                os.chmod(cls.DEFAULT_CONFIG_DIR, 0o700)
                config_path = cls.DEFAULT_CONFIG_FILE

            # Use temporary file and atomic rename for safety
            temp_path = config_path.with_suffix(".tmp")

            # Load existing file if it exists (preserves comments/formatting)
            if config_path.exists():
                with open(config_path) as f:
                    doc = tomlkit.load(f)
            else:
                # Create new document
                doc = tomlkit.document()

            # Update contexts section
            contexts_dict = config.to_dict()
            if contexts_dict:
                doc["contexts"] = contexts_dict
            elif "contexts" in doc:
                # Remove empty contexts section
                del doc["contexts"]

            # Write to temp file
            with open(temp_path, "w") as f:
                tomlkit.dump(doc, f)

            # Set secure permissions before moving
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(config_path)

            logger.debug(f"Saved context config to: {config_path}")

        except ContextError:
            # Re-raise context errors
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise
        except Exception as e:
            # Cleanup temp file on error
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise ContextError(f"Failed to save context config: {e}") from e

    @classmethod
    def ensure_subscription_active(cls, custom_path: str | None = None) -> str:
        """Ensure Azure CLI subscription matches current context.

        This method must be called at the start of any command that queries or modifies
        Azure resources. It ensures that the Azure CLI's active subscription matches
        the azlin current context.

        This prevents bugs where:
        - User switches azlin context but Azure CLI subscription unchanged
        - Manual 'az account set' overrides azlin context
        - Different shell sessions have different Azure CLI subscriptions

        Thread-safe: Uses a lock to prevent race conditions when multiple threads
        call this method concurrently.

        Args:
            custom_path: Custom config file path (optional, for testing)

        Returns:
            Active subscription ID (from current context)

        Raises:
            ContextError: If no current context set or subscription switch fails

        Example:
            >>> # At start of any command
            >>> try:
            >>>     ContextManager.ensure_subscription_active()
            >>> except ContextError as e:
            >>>     console.print(f"[red]Error: {e}[/red]")
            >>>     sys.exit(1)
        """
        with _subscription_lock:
            current_ctx = None
            try:
                # Load context configuration
                context_config = cls.load(custom_path)
                current_ctx = context_config.get_current_context()

                if not current_ctx:
                    raise ContextError(
                        "No current context set.\n"
                        "Run 'azlin context list' to see available contexts, or\n"
                        "Run 'azlin context use <name>' to activate a context."
                    )

                # Switch Azure CLI subscription to match context
                # Use capture_output to suppress stderr/stdout
                subprocess.run(
                    ["az", "account", "set", "--subscription", current_ctx.subscription_id],
                    check=True,
                    capture_output=True,
                    timeout=10,
                    text=True,
                )

                logger.debug(
                    f"Switched Azure CLI subscription to match context '{current_ctx.name}' "
                    f"(subscription: {current_ctx.subscription_id})"
                )

                return current_ctx.subscription_id

            except subprocess.TimeoutExpired as e:
                raise ContextError(
                    "Azure CLI command timed out after 10 seconds.\n"
                    "Check if Azure CLI is responding correctly."
                ) from e
            except subprocess.CalledProcessError as e:
                # Parse Azure CLI error message
                error_msg = e.stderr.strip() if e.stderr else "Unknown error"
                ctx_name = current_ctx.name if current_ctx else "unknown"
                ctx_sub = current_ctx.subscription_id if current_ctx else "unknown"
                raise ContextError(
                    f"Failed to switch Azure subscription.\n"
                    f"Context: {ctx_name}\n"
                    f"Subscription: {ctx_sub}\n"
                    f"Azure CLI error: {error_msg}\n"
                    f"Ensure you are logged in: 'az login'"
                ) from e
            except FileNotFoundError as e:
                raise ContextError(
                    "Azure CLI not found. Please install Azure CLI:\n"
                    "https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
                ) from e
            except ContextError:
                # Re-raise context errors as-is
                raise
            except Exception as e:
                raise ContextError(f"Unexpected error ensuring subscription active: {e}") from e

    @classmethod
    def migrate_from_legacy(cls, custom_path: str | None = None) -> bool:
        """Migrate legacy config to context format.

        Checks for legacy config format (standalone subscription_id/tenant_id)
        and creates a default context if found.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            True if migration performed, False if not needed

        Raises:
            ContextError: If migration fails
        """
        config_path = Path(custom_path) if custom_path else cls.DEFAULT_CONFIG_FILE

        if not config_path.exists():
            logger.debug("No config file found, migration not needed")
            return False

        try:
            # Load existing config
            with open(config_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            # Check if already has contexts
            if data.get("contexts"):
                logger.debug("Config already has contexts, migration not needed")
                return False

            # Check for legacy fields
            legacy_sub = data.get("subscription_id")
            legacy_tenant = data.get("tenant_id")

            if not legacy_sub or not legacy_tenant:
                logger.debug("No legacy subscription/tenant found, migration not needed")
                return False

            # Validate legacy UUIDs
            try:
                validate_uuid(legacy_sub, "subscription_id")
                validate_uuid(legacy_tenant, "tenant_id")
            except ContextError as e:
                raise ContextError(f"Invalid legacy config: {e}") from e

            # Create default context from legacy config
            default_context = Context(
                name="default",
                subscription_id=legacy_sub,
                tenant_id=legacy_tenant,
                description="Migrated from legacy config",
            )

            # Create context config
            context_config = ContextConfig(current="default", contexts={"default": default_context})

            # Save updated config (preserving existing settings)
            temp_path = config_path.with_suffix(".tmp")

            with open(config_path) as f:
                doc = tomlkit.load(f)

            # Add contexts section
            doc["contexts"] = context_config.to_dict()

            # Write to temp file
            with open(temp_path, "w") as f:
                tomlkit.dump(doc, f)

            # Set secure permissions
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(config_path)

            logger.info("Migrated legacy config to context 'default'")
            return True

        except ContextError:
            raise
        except Exception as e:
            raise ContextError(f"Failed to migrate legacy config: {e}") from e


__all__ = [
    "Context",
    "ContextConfig",
    "ContextError",
    "ContextManager",
    "validate_context_name",
    "validate_uuid",
]
