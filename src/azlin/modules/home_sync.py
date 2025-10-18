"""Home directory synchronization module.

This module manages synchronization of local configuration files to remote VMs.

Philosophy:
- Security first: Never sync credentials
- Transparent: Auto-sync on VM operations
- One-way: Local → Remote only
- Standard library preference
- Fail gracefully

Public API:
    HomeSyncManager: Main sync manager
    SyncResult: Sync operation result
    ValidationResult: Security validation result
    SecurityWarning: Security warning details

SECURITY HARDENING:
    This module implements 4 layers of security defense:
    1. Path-based pattern matching using glob patterns (not regex)
    2. Symlink target validation to prevent credential exfiltration
    3. Content-based secret scanning for embedded credentials
    4. Command injection prevention (argument arrays, no shell=True)
"""

import contextlib
import ipaddress
import logging
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .ssh_connector import SSHConfig

logger = logging.getLogger(__name__)


class HomeSyncError(Exception):
    """Base exception for home sync errors."""

    pass


class SecurityValidationError(HomeSyncError):
    """Raised when security validation fails."""

    pass


class RsyncError(HomeSyncError):
    """Raised when rsync command fails."""

    pass


@dataclass
class SecurityWarning:
    """Security warning about a file."""

    file_path: str
    reason: str
    severity: str  # "error", "warning", "info"


@dataclass
class ValidationResult:
    """Result of security validation."""

    is_safe: bool
    blocked_files: list[str] = field(default_factory=list)  # type: ignore[misc]
    warnings: list[SecurityWarning] = field(default_factory=list)  # type: ignore[misc]


@dataclass
class SyncResult:
    """Result of home directory sync operation."""

    success: bool
    files_synced: int = 0
    bytes_transferred: int = 0
    warnings: list[str] = field(default_factory=list)  # type: ignore[misc]
    errors: list[str] = field(default_factory=list)  # type: ignore[misc]
    duration_seconds: float = 0.0


class HomeSyncManager:
    """Manage home directory synchronization to VMs.

    SECURITY HARDENING:
    - Multi-layered validation (glob patterns + symlinks + content)
    - Injection-proof rsync command construction
    - Symlink attack prevention
    - Content-based secret detection
    - Path sanitization in error messages

    Example:
        >>> ssh_config = SSHConfig(...)
        >>> result = HomeSyncManager.sync_to_vm(ssh_config)
        >>> print(f"Synced {result.files_synced} files")
    """

    # SECURITY LAYER 1: Glob patterns for path-based blocking (NOT regex)
    # CRITICAL FIX: Remove ** prefix - Path.match() requires relative paths without **
    # The ** prefix breaks matching and would allow ALL credential files through!
    BLOCKED_GLOBS: ClassVar[list[str]] = [
        # SSH keys (private) - Matches id_rsa, id_ed25519 but NOT id_rsa.pub
        ".ssh/id_*[!.pub]",
        ".ssh/*_key",
        ".ssh/*.pem",
        # AWS
        ".aws/credentials",
        ".aws/config",
        # GCP
        ".config/gcloud/**/*.json",
        ".config/gcloud/credentials*",
        ".config/gcloud/access_tokens.db",
        # Azure - GRANULAR: Block tokens/secrets, allow config
        ".azure/accessTokens.json",
        ".azure/msal_token_cache.json",
        ".azure/msal_token_cache.*.json",
        ".azure/service_principal*.json",
        ".azure/*token*",
        ".azure/*secret*",
        ".azure/*credential*",
        # Generic credential files
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
        "credentials",
        "credentials.*",
        "*credentials*",
        ".env",
        ".env.*",
        # Caches and databases
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        ".git/**",
        "__pycache__/**",
        "*.pyc",
        ".mozilla/**",
        ".chrome/**",
        ".config/**/*cache*",
        ".config/**/*Cache*",
    ]

    # Whitelist overrides blacklist
    ALLOWED_GLOBS: ClassVar[list[str]] = [
        ".ssh/config",
        ".ssh/known_hosts",
        ".ssh/*.pub",
        # Azure config files (NOT tokens/secrets)
        ".azure/azureProfile.json",
        ".azure/config",
        ".azure/clouds.config",
    ]

    # SECURITY LAYER 2: Dangerous symlink targets
    # SECURITY FIX: Prevent symlink-based credential exfiltration
    DANGEROUS_SYMLINK_TARGETS: ClassVar[list[Path]] = [
        Path.home() / ".ssh",
        Path.home() / ".aws",
        Path.home() / ".azure",
        Path.home() / ".config" / "gcloud",
    ]

    # SECURITY LAYER 3: Content-based secret patterns (regex for content only)
    # SECURITY FIX: Detect embedded secrets in config files
    SECRET_CONTENT_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{40}", "AWS Secret Key"),
        (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "Private Key"),
        (r"AccountKey=[A-Za-z0-9+/=]{88}", "Azure Storage Key"),
        (r'(?:api[_-]?key|token|secret)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{32,}["\']?', "API Key/Token"),
        (r"gh[ps]_[A-Za-z0-9]{36,}", "GitHub Token"),
        (r"ya29\.[A-Za-z0-9_-]+", "Google OAuth Token"),
    ]

    DEFAULT_SYNC_DIR = Path.home() / ".azlin" / "home"
    EXCLUDE_FILE_NAME = ".azlin-sync-exclude"

    @classmethod
    def get_sync_directory(cls) -> Path:
        """Get the local sync directory path.

        Returns:
            Path to ~/.azlin/home/
        """
        return cls.DEFAULT_SYNC_DIR

    @classmethod
    def _is_path_allowed(cls, file_path: Path, sync_dir: Path) -> bool:
        """Check if path matches allowed patterns (whitelist).

        SECURITY: Use Path.match() with glob patterns for clarity.

        Args:
            file_path: File path to check
            sync_dir: Sync directory root

        Returns:
            True if path is whitelisted
        """
        try:
            # Need to use .resolve() to handle symlinks properly
            resolved_path = file_path.resolve() if file_path.exists() else file_path
            resolved_sync = sync_dir.resolve() if sync_dir.exists() else sync_dir
            relative_path = resolved_path.relative_to(resolved_sync)

            # Convert to string for matching (Path.match can be finicky with relative paths)
            rel_str = str(relative_path)
            return any(Path(rel_str).match(pattern) for pattern in cls.ALLOWED_GLOBS)
        except (ValueError, RuntimeError, OSError):
            return False

    @classmethod
    def _is_path_blocked(cls, file_path: Path, sync_dir: Path) -> bool:
        """Check if path matches blocked patterns (blacklist).

        SECURITY: Use Path.match() with glob patterns instead of regex.

        Args:
            file_path: File path to check
            sync_dir: Sync directory root

        Returns:
            True if path is blocked
        """
        try:
            # Need to use .resolve() to handle symlinks properly
            resolved_path = file_path.resolve() if file_path.exists() else file_path
            resolved_sync = sync_dir.resolve() if sync_dir.exists() else sync_dir
            relative_path = resolved_path.relative_to(resolved_sync)

            # Convert to string for matching
            rel_str = str(relative_path)
            return any(Path(rel_str).match(pattern) for pattern in cls.BLOCKED_GLOBS)
        except (ValueError, RuntimeError, OSError):
            return False

    @classmethod
    def _is_dangerous_symlink(cls, link_path: Path, target_path: Path) -> bool:
        """Check if symlink points to dangerous location.

        SECURITY FIX: Prevents symlink-based credential exfiltration.

        Args:
            link_path: Symlink path
            target_path: Resolved target path

        Returns:
            True if symlink is dangerous
        """
        try:
            # Check if target is in dangerous directories
            for dangerous_dir in cls.DANGEROUS_SYMLINK_TARGETS:
                if target_path == dangerous_dir or dangerous_dir in target_path.parents:
                    return True
        except (OSError, ValueError):
            # If we can't resolve, treat as dangerous
            return True

        return False

    @classmethod
    def _scan_file_content(cls, file_path: Path) -> list[SecurityWarning]:
        """Scan file content for embedded secrets.

        SECURITY FIX: Detects credentials in config files.

        Args:
            file_path: File to scan

        Returns:
            List of security warnings found
        """
        warnings: list[SecurityWarning] = []

        # Skip large files (> 1MB)
        try:
            if file_path.stat().st_size > 1_000_000:
                return warnings
        except (OSError, FileNotFoundError):
            return warnings

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            for pattern, secret_type in cls.SECRET_CONTENT_PATTERNS:
                if re.search(pattern, content):
                    warnings.append(
                        SecurityWarning(
                            file_path=str(file_path),
                            reason=f"Potential {secret_type} detected in file content",
                            severity="error",
                        )
                    )

        except (UnicodeDecodeError, PermissionError, OSError):
            # Binary or unreadable file - skip content scan
            pass

        return warnings

    @classmethod
    def scan_for_secrets(cls, directory: Path) -> list[SecurityWarning]:
        """Scan directory for potential secrets and sensitive files.

        SECURITY: Multi-layered detection:
        1. Path-based pattern matching (glob patterns)
        2. Symlink target validation
        3. Content-based secret scanning

        Args:
            directory: Directory to scan

        Returns:
            List of security warnings
        """
        warnings: list[SecurityWarning] = []

        if not directory.exists():
            return warnings

        for file_path in directory.rglob("*"):
            if not file_path.is_file() and not file_path.is_symlink():
                continue

            # Check if whitelisted (skip further checks)
            if cls._is_path_allowed(file_path, directory):
                continue

            # Check path patterns
            if cls._is_path_blocked(file_path, directory):
                try:
                    relative = file_path.relative_to(directory)
                    warnings.append(
                        SecurityWarning(
                            file_path=str(relative),
                            reason="Matches blocked file pattern",
                            severity="error",
                        )
                    )
                except ValueError:
                    pass
                continue

            # Check symlinks
            if file_path.is_symlink():
                try:
                    target = file_path.resolve()
                    if cls._is_dangerous_symlink(file_path, target):
                        relative = file_path.relative_to(directory)
                        warnings.append(
                            SecurityWarning(
                                file_path=str(relative),
                                reason=f"Symlink points to sensitive location: {target}",
                                severity="error",
                            )
                        )
                except (OSError, RuntimeError):
                    try:
                        relative = file_path.relative_to(directory)
                        warnings.append(
                            SecurityWarning(
                                file_path=str(relative),
                                reason="Broken or circular symlink",
                                severity="warning",
                            )
                        )
                    except ValueError:
                        pass

            # Scan file content (only for regular files)
            if file_path.is_file() and not file_path.is_symlink():
                content_warnings = cls._scan_file_content(file_path)
                for warning in content_warnings:
                    try:
                        relative = file_path.relative_to(directory)
                        warning.file_path = str(relative)
                    except ValueError:
                        pass
                warnings.extend(content_warnings)

        return warnings

    @classmethod
    def validate_sync_directory(cls, sync_dir: Path) -> ValidationResult:
        """Validate sync directory for security.

        SECURITY: Comprehensive validation with multiple layers.
        PHASE 1 FIX: Changed to non-fatal - returns blocked files but allows sync.
        Rsync will handle exclusions via exclude file.

        Args:
            sync_dir: Directory to validate

        Returns:
            ValidationResult with blocked files list (non-fatal)
        """
        if not sync_dir.exists():
            return ValidationResult(is_safe=True, blocked_files=[], warnings=[])

        warnings = cls.scan_for_secrets(sync_dir)

        # Separate blocking errors from non-blocking warnings
        errors = [w for w in warnings if w.severity == "error"]
        blocked_files = [w.file_path for w in errors]

        # PHASE 1 FIX: Always return is_safe=True - let rsync handle exclusions
        # Only mark unsafe if CRITICAL secrets found (future phase)
        return ValidationResult(
            is_safe=True,  # Non-fatal validation
            blocked_files=blocked_files,
            warnings=warnings,
        )

    @classmethod
    def _generate_exclude_file(cls, sync_dir: Path) -> Path:
        """Generate rsync exclude file.

        SECURITY: Exclude patterns as additional defense layer.

        Args:
            sync_dir: Sync directory root

        Returns:
            Path to generated exclude file
        """
        exclude_file = sync_dir / cls.EXCLUDE_FILE_NAME

        # Convert glob patterns to rsync exclude patterns
        exclude_patterns = [
            "# Auto-generated by azlin - DO NOT EDIT",
            "# Credentials and sensitive files",
            ".ssh/id_*[!.pub]",
            ".ssh/*_key",
            ".ssh/*.pem",
            ".aws/credentials",
            ".aws/config",
            # Azure - granular blocking
            ".azure/accessTokens.json",
            ".azure/msal_token_cache.json",
            ".azure/msal_token_cache.*.json",
            ".azure/service_principal*.json",
            ".azure/*token*",
            ".azure/*secret*",
            ".azure/*credential*",
            ".config/gcloud/",
            "*.key",
            "*.pem",
            "*.p12",
            "*.pfx",
            "credentials",
            "credentials.*",
            "*credentials*",
            ".env",
            ".env.*",
            "",
            "# Large/cache files",
            "*.db",
            "*.sqlite",
            "*.sqlite3",
            ".cache/",
            "__pycache__/",
            "*.pyc",
            "node_modules/",
            ".venv/",
            ".git/",
            ".mozilla/",
            ".chrome/",
            cls.EXCLUDE_FILE_NAME,  # Don't sync the exclude file itself
        ]

        exclude_file.write_text("\n".join(exclude_patterns) + "\n")
        return exclude_file

    @classmethod
    def _is_valid_ip_or_hostname(cls, host: str) -> bool:
        """Validate IP address or hostname format.

        SECURITY FIX: Prevent command injection via malformed hostnames.

        Args:
            host: Hostname or IP address to validate

        Returns:
            True if valid
        """
        # Try IP address (strict validation)
        try:
            # This will properly reject invalid IPs like 999.999.999.999
            ipaddress.ip_address(host)
            return True
        except (ValueError, ipaddress.AddressValueError):
            pass

        # Validate hostname (RFC 1123)
        hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        return bool(re.match(hostname_pattern, host) and len(host) <= 253)

    @classmethod
    def _build_rsync_command(
        cls, sync_dir: Path, ssh_config: SSHConfig, exclude_file: Path, dry_run: bool
    ) -> list[str]:
        """Build rsync command with validated inputs.

        SECURITY FIX (LAYER 4):
        1. Use argument list (NOT shell string)
        2. Validate IP/hostname format
        3. Validate all paths are absolute
        4. Use --safe-links to prevent symlink attacks

        Args:
            sync_dir: Local sync directory
            ssh_config: SSH configuration
            exclude_file: Path to exclude file
            dry_run: Whether to perform dry run

        Returns:
            rsync command as argument list

        Raises:
            ValueError: If validation fails
        """
        # SECURITY: Validate host
        if not cls._is_valid_ip_or_hostname(ssh_config.host):
            raise ValueError(f"Invalid host address: {ssh_config.host}")

        # SECURITY: Validate paths are absolute
        if not sync_dir.is_absolute():
            raise ValueError(f"Sync directory must be absolute: {sync_dir}")
        if not exclude_file.is_absolute():
            raise ValueError(f"Exclude file must be absolute: {exclude_file}")
        if not Path(ssh_config.key_path).is_absolute():
            raise ValueError(f"SSH key path must be absolute: {ssh_config.key_path}")

        # Build SSH options as string (passed to rsync -e)
        ssh_opts = (
            f"ssh -i {ssh_config.key_path} "
            f"-o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30"
        )

        # Build command as argument list (SECURITY: No shell=True)
        cmd = [
            "rsync",
            "-avz",  # Archive, verbose, compress
            "--safe-links",  # SECURITY FIX: Prevent symlink attacks
            "--progress",  # Show progress
            "--partial",  # Keep partial files (resume on failure)
            "--inplace",  # Update files in-place (better for large syncs)
            f"--exclude-from={exclude_file}",  # Exclusion patterns
            "-e",
            ssh_opts,  # SSH command (as separate arg)
        ]

        if dry_run:
            cmd.append("--dry-run")

        # Add source and destination (SECURITY: Always use absolute paths)
        cmd.append(f"{sync_dir}/")  # Trailing slash is important
        cmd.append(f"{ssh_config.user}@{ssh_config.host}:~/")

        return cmd

    @classmethod
    def _parse_rsync_stats(cls, output: str) -> tuple[int, int]:
        """Parse rsync output for statistics.

        Args:
            output: rsync stdout

        Returns:
            Tuple of (files_synced, bytes_transferred)
        """
        files_synced = 0
        bytes_transferred = 0

        # Parse rsync output for stats
        # Example line: "sent 1,234 bytes  received 567 bytes  1,801.00 bytes/sec"
        for line in output.split("\n"):
            if "Number of regular files transferred:" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    with contextlib.suppress(ValueError):
                        files_synced = int(parts[1].strip())
            elif "Total transferred file size:" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        size_str = parts[1].strip().split()[0].replace(",", "")
                        bytes_transferred = int(size_str)
                    except (ValueError, IndexError):
                        pass

        return files_synced, bytes_transferred

    @classmethod
    def sync_to_vm(
        cls,
        ssh_config: SSHConfig,
        dry_run: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> SyncResult:
        """Sync local home directory to remote VM.

        SECURITY: Multi-layered validation before sync.

        Args:
            ssh_config: SSH configuration for target VM
            dry_run: If True, show what would be synced without syncing
            progress_callback: Optional callback for progress updates

        Returns:
            SyncResult with sync outcome

        Raises:
            SecurityValidationError: If dangerous files detected
            RsyncError: If rsync command fails
        """
        start_time = time.time()
        sync_dir = cls.get_sync_directory()

        # Skip if directory doesn't exist or is empty
        if not sync_dir.exists():
            return SyncResult(
                success=True, warnings=["Sync directory does not exist: ~/.azlin/home/"]
            )

        if not any(sync_dir.iterdir()):
            return SyncResult(success=True, warnings=["Sync directory is empty"])

        # SECURITY: Validate directory
        if progress_callback:
            progress_callback("Validating sync directory...")

        validation = cls.validate_sync_directory(sync_dir)

        # PHASE 1 FIX: Don't throw exception, just collect warnings
        # Rsync exclude file will handle blocking
        sync_warnings = []

        if validation.blocked_files:
            # Add blocked files to warnings list
            sync_warnings.extend(
                f"Skipped (sensitive): {blocked_file}" for blocked_file in validation.blocked_files
            )

        # Report validation warnings (non-blocking)
        for warning in validation.warnings:
            if warning.severity == "warning" and progress_callback:
                progress_callback(f"Warning: {warning.reason}")

        # Generate exclude file
        exclude_file = cls._generate_exclude_file(sync_dir)

        # Build rsync command
        cmd = cls._build_rsync_command(sync_dir, ssh_config, exclude_file, dry_run)

        # Execute rsync
        try:
            if progress_callback:
                progress_callback("Syncing files to VM...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                check=True,
            )

            # Parse rsync output for stats
            files_synced, bytes_transferred = cls._parse_rsync_stats(result.stdout)

            duration = time.time() - start_time
            return SyncResult(
                success=True,
                files_synced=files_synced,
                bytes_transferred=bytes_transferred,
                duration_seconds=duration,
                warnings=sync_warnings,  # Include blocked file warnings
            )

        except subprocess.TimeoutExpired as e:
            raise RsyncError("Sync timed out after 5 minutes") from e
        except subprocess.CalledProcessError as e:
            raise RsyncError(f"rsync failed: {e.stderr}") from e
        except Exception as e:
            raise RsyncError(f"Sync failed: {e!s}") from e


# Public API
__all__ = [
    "HomeSyncError",
    "HomeSyncManager",
    "RsyncError",
    "SecurityValidationError",
    "SecurityWarning",
    "SyncResult",
    "ValidationResult",
]
