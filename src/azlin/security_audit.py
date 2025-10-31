"""Security audit logging for azlin.

This module provides audit logging for security-sensitive operations,
particularly tracking when users opt out of secure Bastion connections.

Classes:
    SecurityAuditLogger: Logs security decisions to audit file
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SecurityAuditLogger:
    """Logs security-sensitive decisions for compliance and audit trails.

    This logger records when users opt out of secure Bastion connections,
    providing accountability and visibility into security decisions.

    Attributes:
        AUDIT_FILE: Path to the audit log file (~/.azlin/security_audit.json)
    """

    AUDIT_FILE = Path.home() / ".azlin" / "security_audit.json"

    @classmethod
    def log_bastion_opt_out(cls, vm_name: str, method: str, user: str | None = None) -> None:
        """Log when a user opts out of using Bastion for VM access.

        Creates an audit entry with timestamp, user, VM name, opt-out method,
        and security impact assessment. The audit file is created with secure
        permissions (0600) to prevent unauthorized access.

        Args:
            vm_name: Name of the VM being provisioned
            method: How the opt-out occurred. Valid values:
                - "flag": User used --no-bastion CLI flag
                - "prompt_existing": User declined existing Bastion in prompt
                - "prompt_create": User declined creating new Bastion in prompt
            user: Username (defaults to system user if not provided)

        Example:
            >>> SecurityAuditLogger.log_bastion_opt_out(
            ...     vm_name="dev-vm-01",
            ...     method="flag",
            ...     user="john.doe"
            ... )
        """
        # Ensure audit directory exists
        cls.AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Get current user if not provided
        if user is None:
            user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        # Create audit entry
        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "user": user,
            "vm_name": vm_name,
            "method": method,
            "security_impact": "VM will have public IP exposed to internet",
        }

        # Load existing audit log or create new
        audit_log: list[dict[str, Any]] = []
        if cls.AUDIT_FILE.exists():
            try:
                with open(cls.AUDIT_FILE) as f:
                    audit_log = json.load(f)
            except (OSError, json.JSONDecodeError):
                # If file is corrupted or unreadable, start fresh
                audit_log = []

        # Append new entry
        audit_log.append(audit_entry)

        # Write audit log with secure permissions
        cls._write_secure_audit_file(audit_log)

    @classmethod
    def _write_secure_audit_file(cls, audit_log: list[dict[str, Any]]) -> None:
        """Write audit log with secure file permissions (0600).

        Args:
            audit_log: List of audit entries to write
        """
        # Write file
        with open(cls.AUDIT_FILE, "w") as f:
            json.dump(audit_log, f, indent=2)

        # Set secure permissions (owner read/write only)
        os.chmod(cls.AUDIT_FILE, 0o600)

    @classmethod
    def get_audit_log(cls) -> list[dict[str, Any]]:
        """Retrieve all audit log entries.

        Returns:
            List of audit entries, empty list if file doesn't exist

        Example:
            >>> entries = SecurityAuditLogger.get_audit_log()
            >>> for entry in entries:
            ...     print(f"{entry['timestamp']}: {entry['user']} opted out for {entry['vm_name']}")
        """
        if not cls.AUDIT_FILE.exists():
            return []

        try:
            with open(cls.AUDIT_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return []


__all__ = ["SecurityAuditLogger"]
