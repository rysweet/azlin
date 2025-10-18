"""Secure path parsing and validation."""

import re
from pathlib import Path

from .exceptions import InvalidPathError, PathTraversalError, SymlinkSecurityError


class PathParser:
    """Parse and validate file paths with security checks."""

    # Security boundaries
    HOME_DIR = Path.home()
    ALLOWED_BASE_DIRS = [
        HOME_DIR,
        HOME_DIR / "Desktop",
        HOME_DIR / "Documents",
        HOME_DIR / "Downloads",
    ]

    # Blocked patterns for extra safety
    BLOCKED_PATH_PATTERNS = [
        r"\.ssh/id_[a-z0-9]+$",
        r"\.ssh/.*_key$",
        r"\.aws/credentials$",
        r"\.azure/",
        r"\.config/gcloud/",
    ]

    @classmethod
    def parse_and_validate(
        cls, path_str: str, allow_absolute: bool = False, base_dir: Path | None = None
    ) -> Path:
        """
        Parse and validate a path string with comprehensive security checks.

        Args:
            path_str: User-provided path string
            allow_absolute: Whether to allow absolute paths
            base_dir: Base directory for relative paths (default: HOME_DIR)

        Returns:
            Validated Path object (always absolute)

        Raises:
            PathTraversalError: Path attempts directory traversal
            InvalidPathError: Path is malformed
            SymlinkSecurityError: Dangerous symlink detected

        Security:
            1. Normalizes path (removes .., ., //)
            2. Resolves symlinks
            3. Validates against boundary
            4. Checks for credential files
        """
        if not path_str or not path_str.strip():
            raise InvalidPathError("Path cannot be empty")

        # Remove any null bytes (security)
        if "\x00" in path_str:
            raise InvalidPathError("Path contains null bytes")

        # Check for shell metacharacters
        if cls._contains_shell_metacharacters(path_str):
            raise InvalidPathError(f"Path contains shell metacharacters: {path_str}")

        # Convert to Path object
        try:
            path = Path(path_str).expanduser()
        except (ValueError, RuntimeError) as e:
            raise InvalidPathError(f"Invalid path format: {e}")

        # Check for absolute path if not allowed
        if path.is_absolute() and not allow_absolute:
            raise InvalidPathError(
                "Absolute paths not allowed. Use relative paths or session:path notation"
            )

        # Make relative paths absolute
        if not path.is_absolute():
            base = base_dir or cls.HOME_DIR
            path = base / path

        # Normalize: remove .., ., //
        try:
            normalized = path.resolve(strict=False)
        except (ValueError, RuntimeError) as e:
            raise InvalidPathError(f"Cannot normalize path: {e}")

        # Check for path traversal by verifying it's within allowed boundaries
        if not cls._is_within_allowed_boundaries(normalized):
            raise PathTraversalError(f"Path escapes allowed directory: {normalized}")

        # Check for explicit .. in parts (defense in depth)
        if ".." in normalized.parts:
            raise PathTraversalError("Path contains '..' after normalization")

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
        """Check if path is within allowed directories."""
        # Path must be within HOME_DIR
        try:
            path.relative_to(cls.HOME_DIR)
            return True
        except ValueError:
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
            raise SymlinkSecurityError(f"Cannot validate symlink: {e}")

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
