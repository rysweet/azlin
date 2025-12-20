"""Secure path parsing and validation."""

import re
from pathlib import Path
from typing import ClassVar

from .exceptions import InvalidPathError, PathTraversalError, SymlinkSecurityError


class PathParser:
    """Parse and validate file paths with security checks."""

    # Security boundaries
    HOME_DIR = Path.home()
    ALLOWED_BASE_DIRS: ClassVar[list[Path]] = [
        HOME_DIR,
        HOME_DIR / "Desktop",
        HOME_DIR / "Documents",
        HOME_DIR / "Downloads",
    ]

    # Blocked patterns for extra safety
    BLOCKED_PATH_PATTERNS: ClassVar[list[str]] = [
        r"\.ssh/id_[a-z0-9]+$",
        r"\.ssh/.*_key$",
        r"\.aws/credentials$",
        r"\.azure/",
        r"\.config/gcloud/",
    ]

    @classmethod
    def parse_and_validate(
        cls,
        path_str: str,
        allow_absolute: bool = False,
        base_dir: Path | None = None,
        is_local: bool = False,
    ) -> Path:
        """
        Parse and validate a path string with comprehensive security checks.

        Args:
            path_str: User-provided path string
            allow_absolute: Whether to allow absolute paths
            base_dir: Base directory for relative paths (default: cwd for local, HOME_DIR for remote)
            is_local: If True, path is on local machine (full validation)
                      If False, path is on remote VM (minimal validation only)

        Returns:
            Validated Path object (always absolute)

        Raises:
            PathTraversalError: Path attempts directory traversal
            InvalidPathError: Path is malformed

        Security:
            For LOCAL paths: Full validation (resolve, symlinks, boundaries, credentials)
            For REMOTE paths: Basic validation only (no filesystem access)
        """
        if not path_str or not path_str.strip():
            raise InvalidPathError("Path cannot be empty")

        # Remove any null bytes (security)
        if "\x00" in path_str:
            raise InvalidPathError("Path contains null bytes")

        # Check for shell metacharacters
        if cls._contains_shell_metacharacters(path_str):
            raise InvalidPathError(f"Path contains shell metacharacters: {path_str}")

        # Check for explicit path traversal in the string (works for both local and remote)
        if "/.." in path_str or path_str.startswith("../") or "/../" in path_str:
            raise PathTraversalError(f"Path contains directory traversal: {path_str}")

        # FOR REMOTE PATHS: Return minimal validation
        # Remote paths are validated by the VM's filesystem, not local checks
        if not is_local:
            # Just create the Path object without resolving
            try:
                path = Path(path_str)
            except (ValueError, RuntimeError) as e:
                raise InvalidPathError(f"Invalid path format: {e}") from e

            # Remote paths typically allow absolute (they're on a different machine)
            # But still respect allow_absolute parameter if caller sets it to False
            if path.is_absolute() and not allow_absolute:
                raise InvalidPathError(f"Absolute paths not allowed for this operation: {path_str}")

            # Make relative paths absolute
            if not path.is_absolute():
                base = base_dir or Path("/home/azureuser")
                path = base / path

            return path

        # FOR LOCAL PATHS: Full validation
        # Convert to Path object and expand user home
        try:
            path = Path(path_str).expanduser()
        except (ValueError, RuntimeError) as e:
            raise InvalidPathError(f"Invalid path format: {e}") from e

        # Note: Local paths always allow absolute (user controls their own filesystem)
        # The allow_absolute parameter is only relevant for remote paths

        # Make relative paths absolute
        if not path.is_absolute():
            base = base_dir or Path.cwd()
            path = base / path

        # Normalize and resolve
        try:
            normalized = path.resolve(strict=False)
        except (ValueError, RuntimeError) as e:
            raise InvalidPathError(f"Cannot normalize path: {e}") from e

        # Check boundaries
        if not cls._is_within_allowed_boundaries(normalized):
            raise PathTraversalError(f"Path escapes allowed directory: {normalized}")

        # Validate symlinks
        if normalized.is_symlink():
            cls._validate_symlink(normalized)

        # Check for credential files
        if cls._is_credential_file(normalized):
            raise InvalidPathError(f"Refusing to copy credential file: {normalized.name}")

        return normalized

    @classmethod
    def _contains_shell_metacharacters(cls, path_str: str) -> bool:
        """Check if path contains shell metacharacters."""
        dangerous_chars = [";", "|", "&", "$", "`", "\n", "\r", ">", "<", "(", ")"]
        return any(char in path_str for char in dangerous_chars)

    @classmethod
    def _is_within_allowed_boundaries(cls, path: Path) -> bool:
        """Check if LOCAL path is within allowed directories.

        For local paths only. Checks against local HOME_DIR.
        """
        # Path must be within HOME_DIR
        try:
            path.relative_to(cls.HOME_DIR)
            return True
        except ValueError:
            return False

    @classmethod
    def _is_within_remote_boundaries(cls, path: Path) -> bool:
        """Check if REMOTE path is within allowed directories.

        For remote VM paths. Checks against /home/azureuser (VM home directory).
        Does not validate against local filesystem.
        """
        # Remote paths must be within /home/azureuser
        remote_home = Path("/home/azureuser")

        try:
            # Check if path is within remote home directory
            path.relative_to(remote_home)
            return True
        except ValueError:
            # Path is outside /home/azureuser
            return False

    @classmethod
    def _validate_symlink(cls, path: Path) -> None:
        """
        Validate symlink doesn't point to sensitive location.

        Raises:
            SymlinkSecurityError: If symlink is dangerous
        """
        try:
            target = path.readlink()

            # Resolve target to absolute path
            if not target.is_absolute():
                target = (path.parent / target).resolve()
            else:
                target = target.resolve()

            # Check if target is within allowed boundaries
            if not cls._is_within_allowed_boundaries(target):
                raise SymlinkSecurityError(
                    f"Symlink points outside allowed directory: {path} -> {target}"
                )

            # Check if target is a credential file
            if cls._is_credential_file(target):
                raise SymlinkSecurityError(f"Symlink points to credential file: {path} -> {target}")

        except (OSError, RuntimeError) as e:
            raise SymlinkSecurityError(f"Cannot validate symlink: {e}") from e

    @classmethod
    def _is_credential_file(cls, path: Path) -> bool:
        """Check if path matches credential file patterns."""
        path_str = str(path)
        return any(re.search(pattern, path_str) for pattern in cls.BLOCKED_PATH_PATTERNS)

    @classmethod
    def sanitize_for_display(cls, path: Path, base: Path | None = None) -> str:
        """
        Sanitize path for error messages (show relative path only).

        Args:
            path: Full path
            base: Base directory (default: HOME_DIR)

        Returns:
            Relative path string for display
        """
        base = base or cls.HOME_DIR
        try:
            return str(path.relative_to(base))
        except ValueError:
            # If not relative, show only filename
            return path.name
