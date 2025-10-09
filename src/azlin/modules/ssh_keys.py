"""
SSH Key Manager Module

Generate and manage SSH keys for VM access with secure permissions.

Security Requirements:
- Private key permissions: 0600 (read/write owner only)
- Public key permissions: 0644 (readable by all)
- SSH directory permissions: 0700 (owner only)
- Never log or transmit private key
- Ed25519 keys (preferred over RSA)
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SSHKeyPair:
    """SSH key pair information."""
    private_path: Path
    public_path: Path
    public_key_content: str


class SSHKeyError(Exception):
    """Raised when SSH key operations fail."""
    pass


class SSHKeyManager:
    """
    Manage SSH key generation and retrieval.

    Security:
    - Keys stored in ~/.ssh/
    - Private key: 0600 (-rw-------)
    - Public key: 0644 (-rw-r--r--)
    - SSH directory: 0700 (drwx------)
    - Never logs private key content
    """

    DEFAULT_KEY_PATH = Path.home() / ".ssh" / "azlin_key"
    SSH_DIR = Path.home() / ".ssh"

    @classmethod
    def ensure_key_exists(
        cls,
        key_path: Optional[Path] = None
    ) -> SSHKeyPair:
        """
        Create SSH key if missing, return existing if present.

        Args:
            key_path: Path to private key (default: ~/.ssh/azlin_key)

        Returns:
            SSHKeyPair: Key pair information

        Raises:
            SSHKeyError: If key generation fails

        Security:
        - Creates directory with 0700 permissions
        - Sets private key to 0600
        - Sets public key to 0644
        - Uses Ed25519 algorithm

        Example:
            >>> keys = SSHKeyManager.ensure_key_exists()
            >>> print(keys.public_key_content)
        """
        if key_path is None:
            key_path = cls.DEFAULT_KEY_PATH

        # Ensure key_path is a Path object
        key_path = Path(key_path).expanduser().resolve()
        public_path = key_path.with_suffix(key_path.suffix + ".pub")

        # Check if key already exists
        if key_path.exists() and public_path.exists():
            logger.info(f"Using existing SSH key: {key_path}")

            # Verify permissions
            try:
                cls._verify_permissions(key_path, public_path)
            except PermissionError as e:
                logger.warning(f"Fixing SSH key permissions: {e}")
                cls._fix_permissions(key_path, public_path)

            # Read public key
            public_key_content = cls.read_public_key(key_path)

            return SSHKeyPair(
                private_path=key_path,
                public_path=public_path,
                public_key_content=public_key_content
            )

        # Generate new key
        logger.info(f"Generating new SSH key: {key_path}")
        return cls._generate_key(key_path)

    @classmethod
    def _generate_key(cls, key_path: Path) -> SSHKeyPair:
        """
        Generate new Ed25519 SSH key pair.

        Args:
            key_path: Path for private key

        Returns:
            SSHKeyPair: Generated key pair

        Raises:
            SSHKeyError: If generation fails

        Security:
        - Uses Ed25519 (modern, secure)
        - No passphrase (for automation)
        - Atomic generation (fails if exists)
        """
        # Ensure SSH directory exists with correct permissions
        cls._ensure_ssh_directory()

        public_path = key_path.with_suffix(key_path.suffix + ".pub")

        # Generate key using ssh-keygen
        try:
            # Build command
            args = [
                "ssh-keygen",
                "-t", "ed25519",  # Ed25519 algorithm
                "-f", str(key_path),  # Output file
                "-N", "",  # No passphrase (empty string)
                "-C", f"azlin-key-{key_path.name}",  # Comment
            ]

            logger.debug("Generating SSH key with ssh-keygen")

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            logger.info(f"SSH key generated successfully")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"ssh-keygen failed: {error_msg}")
            raise SSHKeyError(f"Failed to generate SSH key: {error_msg}")

        except subprocess.TimeoutExpired:
            logger.error("ssh-keygen timed out")
            raise SSHKeyError("SSH key generation timed out")

        except FileNotFoundError:
            logger.error("ssh-keygen not found in PATH")
            raise SSHKeyError(
                "ssh-keygen not found. Please install OpenSSH client."
            )

        # Set permissions
        cls._fix_permissions(key_path, public_path)

        # Read public key
        public_key_content = cls.read_public_key(key_path)

        logger.info(f"Private key: {key_path}")
        logger.info(f"Public key: {public_path}")

        return SSHKeyPair(
            private_path=key_path,
            public_path=public_path,
            public_key_content=public_key_content
        )

    @classmethod
    def _ensure_ssh_directory(cls) -> None:
        """
        Ensure ~/.ssh directory exists with correct permissions.

        Security: Creates with mode 0700 (drwx------)
        """
        if not cls.SSH_DIR.exists():
            logger.debug(f"Creating SSH directory: {cls.SSH_DIR}")
            cls.SSH_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            # Verify permissions
            stat = cls.SSH_DIR.stat()
            if stat.st_mode & 0o077:  # Group or other have access
                logger.warning(f"Fixing SSH directory permissions: {cls.SSH_DIR}")
                cls.SSH_DIR.chmod(0o700)

    @classmethod
    def _verify_permissions(cls, private_path: Path, public_path: Path) -> None:
        """
        Verify SSH key permissions are secure.

        Args:
            private_path: Private key path
            public_path: Public key path

        Raises:
            PermissionError: If permissions are insecure

        Security:
        - Private key must be 0600 (-rw-------)
        - Public key should be 0644 (-rw-r--r--)
        """
        # Check private key permissions
        private_stat = private_path.stat()
        private_mode = private_stat.st_mode & 0o777

        if private_stat.st_mode & 0o077:  # Group or other have access
            raise PermissionError(
                f"Private key has insecure permissions: {oct(private_mode)}\n"
                f"Expected: 0600 (-rw-------)\n"
                f"File: {private_path}"
            )

        # Check public key permissions (just warn, don't fail)
        public_stat = public_path.stat()
        public_mode = public_stat.st_mode & 0o777

        if public_mode != 0o644:
            logger.debug(
                f"Public key permissions: {oct(public_mode)} "
                f"(expected 0644)"
            )

    @classmethod
    def _fix_permissions(cls, private_path: Path, public_path: Path) -> None:
        """
        Set correct permissions on SSH keys.

        Args:
            private_path: Private key path
            public_path: Public key path

        Security:
        - Private key: 0600 (-rw-------)
        - Public key: 0644 (-rw-r--r--)
        """
        if private_path.exists():
            private_path.chmod(0o600)
            logger.debug(f"Set private key permissions: 0600")

        if public_path.exists():
            public_path.chmod(0o644)
            logger.debug(f"Set public key permissions: 0644")

    @classmethod
    def read_public_key(cls, key_path: Optional[Path] = None) -> str:
        """
        Read public key content for VM provisioning.

        Args:
            key_path: Path to private key (public key is .pub)

        Returns:
            str: Public key content (single line)

        Raises:
            SSHKeyError: If public key not found or unreadable

        Example:
            >>> pub_key = SSHKeyManager.read_public_key()
            >>> print(pub_key)
            ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... azlin-key
        """
        if key_path is None:
            key_path = cls.DEFAULT_KEY_PATH

        key_path = Path(key_path).expanduser().resolve()
        public_path = key_path.with_suffix(key_path.suffix + ".pub")

        if not public_path.exists():
            raise SSHKeyError(f"Public key not found: {public_path}")

        try:
            content = public_path.read_text().strip()

            if not content:
                raise SSHKeyError(f"Public key is empty: {public_path}")

            logger.debug(f"Read public key from {public_path}")
            return content

        except Exception as e:
            raise SSHKeyError(f"Failed to read public key: {e}")


# Convenience functions for CLI use
def ensure_ssh_key(key_path: Optional[Path] = None) -> SSHKeyPair:
    """
    Ensure SSH key exists (convenience function).

    Args:
        key_path: Optional custom key path

    Returns:
        SSHKeyPair: Key pair information

    Example:
        >>> from azlin.modules.ssh_keys import ensure_ssh_key
        >>> keys = ensure_ssh_key()
        >>> print(keys.public_key_content)
    """
    return SSHKeyManager.ensure_key_exists(key_path)


def get_public_key(key_path: Optional[Path] = None) -> str:
    """
    Get public key content (convenience function).

    Args:
        key_path: Optional custom key path

    Returns:
        str: Public key content

    Example:
        >>> from azlin.modules.ssh_keys import get_public_key
        >>> pub_key = get_public_key()
    """
    return SSHKeyManager.read_public_key(key_path)
