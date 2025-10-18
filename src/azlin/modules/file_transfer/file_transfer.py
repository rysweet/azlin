"""Secure file transfer operations."""

import ipaddress
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .exceptions import InvalidTransferError, TransferError
from .session_manager import VMSession


@dataclass
class TransferEndpoint:
    """Represents a transfer source or destination."""

    path: Path  # Validated local path
    session: VMSession | None  # None for local, VMSession for remote

    def to_rsync_arg(self) -> str:
        """Convert to rsync argument."""
        if self.session is None:
            # Local path
            return str(self.path)
        # Remote path: user@host:path
        return f"{self.session.user}@{self.session.public_ip}:{self.path}"


@dataclass
class TransferResult:
    """Result of file transfer operation."""

    success: bool
    files_transferred: int
    bytes_transferred: int
    duration_seconds: float
    errors: list[str]


class FileTransfer:
    """Secure file transfer using rsync."""

    @classmethod
    def transfer(
        cls,
        source: TransferEndpoint,
        dest: TransferEndpoint,
        progress_callback: Callable[..., None] | None = None,
    ) -> TransferResult:
        """
        Transfer files from source to destination.

        Args:
            source: Validated source endpoint
            dest: Validated destination endpoint
            progress_callback: Optional progress callback

        Returns:
            TransferResult with statistics

        Raises:
            InvalidTransferError: Both endpoints are local
            TransferError: rsync command failed

        Security:
            - Uses argument arrays (no shell=True)
            - Validates IP addresses
            - No user input in shell commands
        """
        # Validate transfer direction
        if source.session is None and dest.session is None:
            raise InvalidTransferError("Both source and destination are local. Use 'cp' instead.")

        # Build rsync command
        cmd = cls._build_rsync_command(source, dest)

        # Execute rsync with validated arguments
        import time

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=True,
            )

            duration = time.time() - start_time

            # Parse rsync output for statistics
            stats = cls._parse_rsync_output(result.stdout)

            return TransferResult(
                success=True,
                files_transferred=stats["files"],
                bytes_transferred=stats["bytes"],
                duration_seconds=duration,
                errors=[],
            )

        except subprocess.CalledProcessError as e:
            duration = time.time() - start_time
            return TransferResult(
                success=False,
                files_transferred=0,
                bytes_transferred=0,
                duration_seconds=duration,
                errors=[f"rsync failed: {e.stderr}"],
            )

        except subprocess.TimeoutExpired:
            raise TransferError("Transfer timed out after 5 minutes")

    @classmethod
    def _build_rsync_command(cls, source: TransferEndpoint, dest: TransferEndpoint) -> list[str]:
        """
        Build rsync command with validated arguments.

        Returns:
            Command as argument list (NOT shell string)

        Security:
            - Argument array format prevents injection
            - IP addresses validated
            - SSH command in single argument
        """
        cmd = ["rsync", "-avz", "--progress"]

        # Determine which endpoint is remote
        remote_session = source.session or dest.session

        if remote_session is not None:
            # Validate IP address format
            cls._validate_ip_address(remote_session.public_ip)

            # Build SSH command as SINGLE argument
            ssh_cmd = (
                f"ssh "
                f"-i {remote_session.key_path} "
                f"-o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null "
                f"-o ConnectTimeout=10"
            )

            # Add SSH command to rsync
            cmd.extend(["-e", ssh_cmd])

        # Add source and destination
        cmd.append(source.to_rsync_arg())
        cmd.append(dest.to_rsync_arg())

        return cmd

    @classmethod
    def _validate_ip_address(cls, ip: str) -> None:
        """
        Validate IP address format.

        Raises:
            TransferError: Invalid IP address
        """
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise TransferError(f"Invalid IP address: {ip}")

    @classmethod
    def _parse_rsync_output(cls, output: str) -> dict:
        """Parse rsync output for statistics."""
        import re

        # Look for rsync summary line
        # "sent 1,234 bytes  received 56 bytes  1,290.00 bytes/sec"
        files = 0
        bytes_transferred = 0

        for line in output.split("\n"):
            # Count file transfers (lines with file paths)
            if line and not line.startswith(("sending", "sent", "total")):
                files += 1

            # Parse bytes transferred
            match = re.search(r"sent ([\d,]+) bytes", line)
            if match:
                bytes_str = match.group(1).replace(",", "")
                bytes_transferred = int(bytes_str)

        return {"files": files, "bytes": bytes_transferred}
