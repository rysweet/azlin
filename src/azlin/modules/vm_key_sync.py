"""SSH Key Synchronization Module.

Automatically synchronizes SSH keys from Azure Key Vault to VM authorized_keys files.
All operations are append-only (never replace) to preserve existing keys.

Security guarantees:
- Append-only: Keys are always appended, never replaced
- No private key exposure: Only public keys are transmitted
- Audit logging: All operations logged to ~/.azlin/logs/key_sync_audit.log
- Idempotent: Running multiple times is safe
- Fail-safe: Failures log warnings but don't block connections
"""

import json
import logging
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEOUT = 30
MAX_KEY_LENGTH = 8192
KEY_FINGERPRINT_LENGTH = 40


@dataclass
class KeySyncResult:
    """Result from key synchronization operation."""

    synced: bool
    already_present: bool
    error: str | None = None
    method: str = "none"
    duration_ms: int = 0


class VMKeySyncError(Exception):
    """Exception raised for key synchronization failures."""

    pass


class VMKeySync:
    """Manages SSH key synchronization between Key Vault and VMs."""

    def __init__(self, config: dict | None = None):
        """Initialize key sync manager.

        Args:
            config: Configuration dictionary with ssh settings
        """
        self.config = config or {}
        self.audit_log_path = Path.home() / ".azlin" / "logs" / "key_sync_audit.log"
        self._ensure_log_directory()

    def _ensure_log_directory(self):
        """Create log directory if it doesn't exist."""
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def ensure_key_authorized(
        self,
        vm_name: str,
        resource_group: str,
        public_key: str,
        ssh_user: str = "azureuser",
        dry_run: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> KeySyncResult:
        """Ensure SSH public key is in VM's authorized_keys file.

        Main entry point for key synchronization. Checks if key exists,
        appends if missing, and returns result.

        Args:
            vm_name: Name of the VM
            resource_group: Azure resource group name
            public_key: SSH public key to synchronize
            ssh_user: SSH username (default: azureuser)
            dry_run: If True, check only without modifications
            timeout: Operation timeout in seconds

        Returns:
            KeySyncResult with operation details

        Raises:
            VMKeySyncError: For validation failures only
                           (operational failures return error in result)
        """
        start_time = time.time()
        self._validate_inputs(vm_name, resource_group, public_key)

        try:
            # Check if key already exists
            if self.check_key_exists(vm_name, resource_group, public_key, ssh_user, timeout):
                result = KeySyncResult(
                    synced=False,
                    already_present=True,
                    method="check",
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                self._log_audit(vm_name, resource_group, result, ssh_user)
                return result

            if dry_run:
                return KeySyncResult(
                    synced=False,
                    already_present=False,
                    method="dry-run",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            method = self._get_sync_method()
            if method == "skip":
                return KeySyncResult(
                    synced=False,
                    already_present=False,
                    method="skip",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Append key to VM
            try:
                self.append_key_to_vm(
                    vm_name, resource_group, public_key, ssh_user, timeout, method
                )
                result = KeySyncResult(
                    synced=True,
                    already_present=False,
                    method=method,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Failed to sync SSH key to VM {vm_name}: {error_msg}")
                result = KeySyncResult(
                    synced=False,
                    already_present=False,
                    error=error_msg,
                    method=method,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            self._log_audit(vm_name, resource_group, result, ssh_user)
            return result

        except (subprocess.TimeoutExpired, ConnectionError) as e:
            # Consolidate timeout and connection error handling
            if isinstance(e, subprocess.TimeoutExpired):
                error_msg = "Sync operation timed out"
                method = "timeout"
            else:
                error_msg = f"Network error: {e!s}"
                method = "network-error"

            logger.warning(f"{error_msg} for VM {vm_name}")
            result = KeySyncResult(
                synced=False,
                already_present=False,
                error=error_msg,
                method=method,
                duration_ms=int((time.time() - start_time) * 1000),
            )
            self._log_audit(vm_name, resource_group, result, ssh_user)
            return result

    def check_key_exists(
        self,
        vm_name: str,
        resource_group: str,
        public_key: str,
        ssh_user: str = "azureuser",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> bool:
        """Check if public key exists in VM's authorized_keys file.

        Uses key fingerprint for reliable matching.

        Args:
            vm_name: Name of the VM
            resource_group: Azure resource group name
            public_key: SSH public key to check
            ssh_user: SSH username
            timeout: Operation timeout in seconds

        Returns:
            True if key exists, False otherwise
        """
        fingerprint = self._extract_fingerprint(public_key)
        if not fingerprint:
            return False

        check_script = self._build_check_script(fingerprint, ssh_user)

        try:
            result = subprocess.run(
                [
                    "az",
                    "vm",
                    "run-command",
                    "invoke",
                    "--name",
                    vm_name,
                    "--resource-group",
                    resource_group,
                    "--command-id",
                    "RunShellScript",
                    "--scripts",
                    check_script,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    for item in output.get("value", []):
                        if isinstance(item, dict) and "KEY_FOUND" in item.get("message", ""):
                            return True
                except (json.JSONDecodeError, KeyError):
                    pass

            return False

        except subprocess.TimeoutExpired:
            raise
        except Exception as e:
            logger.debug(f"Error checking key existence: {e}")
            return False  # Safe default

    def append_key_to_vm(
        self,
        vm_name: str,
        resource_group: str,
        public_key: str,
        ssh_user: str = "azureuser",
        timeout: int = 30,
        method: str = "auto",
    ):
        """Append public key to VM's authorized_keys file.

        Args:
            vm_name: Name of the VM
            resource_group: Azure resource group name
            public_key: SSH public key to append
            ssh_user: SSH username
            timeout: Operation timeout in seconds
            method: Sync method (auto, run-command, ssh)

        Raises:
            VMKeySyncError: If append operation fails
        """
        # Validate key format before appending
        self._validate_key_format(public_key)

        if method == "auto":
            # Try run-command first, fall back to SSH if it fails
            try:
                self._append_via_run_command(vm_name, resource_group, public_key, ssh_user, timeout)
                return
            except Exception as e:
                logger.debug(f"run-command failed, trying SSH fallback: {e}")
                if "VM Agent" in str(e) or "Permission" not in str(e):
                    try:
                        self._append_via_ssh(vm_name, public_key, ssh_user, timeout)
                        return
                    except Exception as ssh_error:
                        raise VMKeySyncError(
                            f"Both methods failed: {e}, {ssh_error}"
                        ) from ssh_error
                raise
        elif method == "run-command":
            self._append_via_run_command(vm_name, resource_group, public_key, ssh_user, timeout)
        elif method == "ssh":
            self._append_via_ssh(vm_name, public_key, ssh_user, timeout)
        else:
            raise VMKeySyncError(f"Unknown sync method: {method}")

    def _append_via_run_command(
        self, vm_name: str, resource_group: str, public_key: str, ssh_user: str, timeout: int
    ):
        """Append key using Azure VM run-command."""
        sync_script = self._build_sync_command(public_key, ssh_user)

        result = subprocess.run(
            [
                "az",
                "vm",
                "run-command",
                "invoke",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--command-id",
                "RunShellScript",
                "--scripts",
                sync_script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()

            if "VM Agent" in error_msg or "not responding" in error_msg:
                raise VMKeySyncError("VM Agent not responding")
            if "Permission" in error_msg or "Insufficient" in error_msg:
                raise VMKeySyncError("Permission denied - need VM Contributor role")
            if "not in running state" in error_msg:
                raise VMKeySyncError("VM not running")
            raise VMKeySyncError(f"Failed to append key: {error_msg}")

        # Verify success
        try:
            output = json.loads(result.stdout)
            if isinstance(output, dict) and "value" in output:
                for item in output["value"]:
                    if isinstance(item, dict):
                        code = item.get("code", "")
                        if (
                            "succeeded" not in code.lower()
                            and code != "ProvisioningState/succeeded"
                        ):
                            message = item.get("message", "Unknown error")
                            raise VMKeySyncError(f"Command failed: {message}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Could not parse run-command output: {e}")

    def _append_via_ssh(self, vm_name: str, public_key: str, ssh_user: str, timeout: int):
        """Append key using direct SSH connection (fallback method)."""
        # Escape the public key for safe shell transmission
        escaped_key = shlex.quote(public_key.strip())

        ssh_command = (
            f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            f"echo {escaped_key} >> ~/.ssh/authorized_keys && "
            f"chmod 600 ~/.ssh/authorized_keys"
        )

        result = subprocess.run(
            ["ssh", f"{ssh_user}@{vm_name}", ssh_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            raise VMKeySyncError(f"SSH append failed: {result.stderr.strip()}")

    def _extract_fingerprint(self, public_key: str) -> str | None:
        """Extract key fingerprint from public key.

        Args:
            public_key: SSH public key

        Returns:
            First 40 chars of key data, or None if invalid
        """
        key_parts = public_key.strip().split()
        if len(key_parts) < 2:
            return None
        key_data = key_parts[1]
        return (
            key_data[:KEY_FINGERPRINT_LENGTH]
            if len(key_data) > KEY_FINGERPRINT_LENGTH
            else key_data
        )

    def _build_sync_command(self, public_key: str, ssh_user: str) -> str:
        """Build bash script for safe key append operation.

        Args:
            public_key: SSH public key to append
            ssh_user: SSH username

        Returns:
            Bash script as string
        """
        escaped_key = public_key.strip().replace("'", "'\\''")
        fingerprint = self._extract_fingerprint(public_key) or ""

        return f'''#!/bin/bash
set -euo pipefail

SSH_USER="{ssh_user}"
SSH_DIR="/home/$SSH_USER/.ssh"
AUTH_KEYS="$SSH_DIR/authorized_keys"
PUBLIC_KEY='{escaped_key}'

# Create .ssh directory if needed
if [ ! -d "$SSH_DIR" ]; then
    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"
    chown "$SSH_USER:$SSH_USER" "$SSH_DIR"
fi

# Create authorized_keys if needed
if [ ! -f "$AUTH_KEYS" ]; then
    touch "$AUTH_KEYS"
    chmod 600 "$AUTH_KEYS"
    chown "$SSH_USER:$SSH_USER" "$AUTH_KEYS"
fi

# Use flock to prevent concurrent modifications
exec 200>"$AUTH_KEYS.lock"
flock -x 200

# Check if key already exists (idempotent)
if grep -Fq "{fingerprint}" "$AUTH_KEYS" 2>/dev/null; then
    echo "KEY_ALREADY_PRESENT"
    exit 0
fi

# Append key (NEVER use > operator, always >>)
echo "$PUBLIC_KEY" >> "$AUTH_KEYS"

# Ensure correct permissions
chmod 600 "$AUTH_KEYS"
chown "$SSH_USER:$SSH_USER" "$AUTH_KEYS"

echo "KEY_APPENDED_SUCCESSFULLY"
'''

    def _build_check_script(self, fingerprint: str, ssh_user: str) -> str:
        """Build bash script to check if key exists.

        Args:
            fingerprint: Key fingerprint
            ssh_user: SSH username

        Returns:
            Bash script as string
        """
        return f'''#!/bin/bash
SSH_USER="{ssh_user}"
AUTH_KEYS="/home/$SSH_USER/.ssh/authorized_keys"

if [ ! -f "$AUTH_KEYS" ]; then
    echo "FILE_NOT_FOUND"
    exit 1
fi

if grep -Fq "{fingerprint}" "$AUTH_KEYS" 2>/dev/null; then
    echo "KEY_FOUND"
    exit 0
else
    echo "KEY_NOT_FOUND"
    exit 1
fi
'''

    def _validate_inputs(self, vm_name: str, resource_group: str, public_key: str):
        """Validate input parameters.

        Args:
            vm_name: VM name to validate
            resource_group: Resource group name to validate
            public_key: Public key to validate

        Raises:
            ValueError: If any input is invalid
        """
        if not vm_name or not vm_name.strip():
            raise ValueError("VM name cannot be empty")

        if not resource_group or not resource_group.strip():
            raise ValueError("Resource group cannot be empty")

        if not public_key or not public_key.strip():
            raise ValueError("Public key cannot be empty")

        # Whitelist validation for VM name (alphanumeric, dash, underscore, dot)
        if not re.match(r"^[a-zA-Z0-9._-]+$", vm_name):
            raise ValueError(f"Invalid VM name: {vm_name}")

        # Whitelist validation for resource group
        if not re.match(r"^[a-zA-Z0-9._()-]+$", resource_group):
            raise ValueError(f"Invalid resource group name: {resource_group}")

    def _validate_key_format(self, public_key: str):
        """Validate SSH public key format.

        Args:
            public_key: Public key to validate

        Raises:
            VMKeySyncError: If key format is invalid
        """
        key = public_key.strip()

        if "\n" in key or "\r" in key:
            raise VMKeySyncError("Public key contains newlines")

        if len(key) > MAX_KEY_LENGTH:
            raise VMKeySyncError(f"Public key too long (max {MAX_KEY_LENGTH} chars)")

        parts = key.split()
        if len(parts) < 2:
            raise VMKeySyncError("Invalid SSH key format (missing key data)")

        valid_types = {
            "ssh-rsa",
            "ssh-ed25519",
            "ssh-dss",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
        }

        if parts[0] not in valid_types:
            raise VMKeySyncError(f"Invalid or unsupported key type: {parts[0]}")

    def _get_sync_method(self) -> str:
        """Get sync method from configuration.

        Returns:
            Sync method: auto, run-command, ssh, or skip
        """
        return self.config.get("ssh_sync_method", "auto")

    def _log_audit(self, vm_name: str, resource_group: str, result: KeySyncResult, ssh_user: str):
        """Log key sync operation to audit log.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            result: Sync result
            ssh_user: SSH username
        """
        # Audit logging always enabled for security (no config toggle)
        try:
            audit_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "vm_name": vm_name,
                "resource_group": resource_group,
                "synced": result.synced,
                "already_present": result.already_present,
                "method": result.method,
                "duration_ms": result.duration_ms,
                "user": os.environ.get("USER", "unknown"),
                "ssh_user": ssh_user,
                "error": result.error,
            }

            with open(self.audit_log_path, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")

        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")
