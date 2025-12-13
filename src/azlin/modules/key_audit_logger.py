"""SSH Key Audit Logging for Compliance & Forensics.

Comprehensive audit trail for all SSH key operations with tamper-evident logging
and compliance reporting capabilities.

This module extends the SecurityAuditLogger pattern to provide specialized
audit logging for SSH key lifecycle events (generate, rotate, access, delete).

Features:
- Comprehensive SSH key operation logging
- Tamper-evident logs with SHA256 integrity checksums
- Compliance reporting (SOC2, ISO 27001)
- Secure file permissions (0600)
- Integration with network security audit trail

Philosophy:
- Ruthless Simplicity: Single responsibility (log SSH key events)
- Zero-BS: No stubs, complete implementation
- Brick pattern: Reuses SecurityAuditLogger infrastructure

Public API:
    KeyAuditLogger: Main logger for SSH key operations
    SSHKeyEventType: Event type enumeration

Example:
    >>> logger = KeyAuditLogger()
    >>> logger.log_key_generation("test-vm", Path("~/.ssh/azlin_key"))
    >>> logger.log_key_rotation("test-vm", success=True)
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azlin.network_security.security_audit import (
    AuditEvent,
    SecurityAuditLogger,
)

logger = logging.getLogger(__name__)


class SSHKeyEventType:
    """SSH key specific event types.

    These extend the base AuditEventType enumeration with SSH-specific events.
    """

    SSH_KEY_GENERATE = "ssh_key_generate"
    SSH_KEY_ROTATE = "ssh_key_rotate"
    SSH_KEY_ACCESS = "ssh_key_access"
    SSH_KEY_DELETE = "ssh_key_delete"
    SSH_KEY_BACKUP = "ssh_key_backup"
    SSH_KEY_UPDATE_VM = "ssh_key_update_vm"
    SSH_KEY_PERMISSION_FIX = "ssh_key_permission_fix"


class KeyAuditLogger:
    """Audit logger for SSH key operations.

    Provides comprehensive audit trail for all SSH key lifecycle events
    with tamper-evident logging and compliance reporting.

    Features:
    - Logs all SSH key operations (generate, rotate, access, delete)
    - Tamper-evident logs with SHA256 checksums
    - Compliance tags (SOC2, ISO 27001)
    - Integration with SecurityAuditLogger infrastructure
    - Secure file permissions (0600 owner-only)

    Example:
        >>> logger = KeyAuditLogger()
        >>> logger.log_key_generation("vm-01", Path("~/.ssh/azlin_key"))
        >>> logger.log_key_rotation("vm-01", success=True, vms_updated=5)
    """

    def __init__(self):
        """Initialize key audit logger."""
        self._audit_logger = SecurityAuditLogger()

    def log_key_generation(
        self,
        vm_name: str,
        key_path: Path,
        algorithm: str = "ed25519",
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log SSH key generation event.

        Args:
            vm_name: VM name the key is for
            key_path: Path to generated key
            algorithm: Key algorithm (default: ed25519)
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_key_generation("dev-vm", Path("~/.ssh/azlin_key"))
        """
        user = user or self._get_system_user()

        event_details = {
            "key_path": str(key_path),
            "algorithm": algorithm,
            "operation": "generate_ssh_key",
        }
        if details:
            event_details.update(details)

        event = AuditEvent(
            event_id=self._generate_event_id("key_gen"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_GENERATE,  # type: ignore
            user=user,
            resource=vm_name,
            action="generate_ssh_key",
            outcome="success",
            details=event_details,
            severity="info",
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE"],
        )

        self._audit_logger.log_event(event)
        logger.info(f"Audit: SSH key generated for {vm_name} at {key_path}")

    def log_key_rotation(
        self,
        resource_group: str,
        success: bool,
        vms_updated: list[str] | None = None,
        vms_failed: list[str] | None = None,
        new_key_path: Path | None = None,
        backup_path: Path | None = None,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log SSH key rotation event.

        Args:
            resource_group: Azure resource group
            success: Whether rotation succeeded
            vms_updated: List of VMs successfully updated
            vms_failed: List of VMs that failed to update
            new_key_path: Path to new key
            backup_path: Path to backup directory
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_key_rotation(
            ...     "my-rg",
            ...     success=True,
            ...     vms_updated=["vm1", "vm2"],
            ...     new_key_path=Path("~/.ssh/azlin_key_new")
            ... )
        """
        user = user or self._get_system_user()

        event_details = {
            "operation": "rotate_ssh_keys",
            "vms_updated_count": len(vms_updated) if vms_updated else 0,
            "vms_failed_count": len(vms_failed) if vms_failed else 0,
        }

        if vms_updated:
            event_details["vms_updated"] = vms_updated
        if vms_failed:
            event_details["vms_failed"] = vms_failed
        if new_key_path:
            event_details["new_key_path"] = str(new_key_path)
        if backup_path:
            event_details["backup_path"] = str(backup_path)
        if details:
            event_details.update(details)

        # Determine severity based on failures
        severity = "critical" if vms_failed else "info"
        if vms_failed and not success:
            severity = "critical"
        elif vms_failed and success:
            severity = "warning"

        event = AuditEvent(
            event_id=self._generate_event_id("key_rotate"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_ROTATE,  # type: ignore
            user=user,
            resource=resource_group,
            action="rotate_ssh_keys",
            outcome="success" if success else "failure",
            details=event_details,
            severity=severity,
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE", "KEY_ROTATION"],
        )

        self._audit_logger.log_event(event)
        logger.info(f"Audit: SSH key rotation for {resource_group}, success={success}")

    def log_key_access(
        self,
        vm_name: str,
        key_path: Path,
        operation: str,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log SSH key access event.

        Args:
            vm_name: VM name
            key_path: Path to accessed key
            operation: Operation type (read, verify_permissions, etc.)
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_key_access("vm-01", Path("~/.ssh/azlin_key"), "read")
        """
        user = user or self._get_system_user()

        event_details = {
            "key_path": str(key_path),
            "operation": operation,
        }
        if details:
            event_details.update(details)

        event = AuditEvent(
            event_id=self._generate_event_id("key_access"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_ACCESS,  # type: ignore
            user=user,
            resource=vm_name,
            action=f"access_ssh_key_{operation}",
            outcome="success",
            details=event_details,
            severity="info",
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE"],
        )

        self._audit_logger.log_event(event)

    def log_key_deletion(
        self,
        vm_name: str,
        key_path: Path,
        reason: str,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log SSH key deletion event.

        Args:
            vm_name: VM name
            key_path: Path to deleted key
            reason: Reason for deletion
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_key_deletion(
            ...     "vm-01",
            ...     Path("~/.ssh/azlin_key_old"),
            ...     "key_rotation_cleanup"
            ... )
        """
        user = user or self._get_system_user()

        event_details = {
            "key_path": str(key_path),
            "reason": reason,
        }
        if details:
            event_details.update(details)

        event = AuditEvent(
            event_id=self._generate_event_id("key_delete"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_DELETE,  # type: ignore
            user=user,
            resource=vm_name,
            action="delete_ssh_key",
            outcome="success",
            details=event_details,
            severity="warning",  # Key deletion is notable
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE"],
        )

        self._audit_logger.log_event(event)
        logger.info(f"Audit: SSH key deleted for {vm_name} at {key_path}, reason={reason}")

    def log_key_backup(
        self,
        backup_dir: Path,
        key_count: int = 1,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log SSH key backup event.

        Args:
            backup_dir: Backup directory path
            key_count: Number of keys backed up
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_key_backup(Path("~/.azlin/key_backups/20250101"))
        """
        user = user or self._get_system_user()

        event_details = {
            "backup_dir": str(backup_dir),
            "key_count": key_count,
            "operation": "backup_ssh_keys",
        }
        if details:
            event_details.update(details)

        event = AuditEvent(
            event_id=self._generate_event_id("key_backup"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_BACKUP,  # type: ignore
            user=user,
            resource="ssh_keys",
            action="backup_ssh_keys",
            outcome="success",
            details=event_details,
            severity="info",
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE", "KEY_ROTATION"],
        )

        self._audit_logger.log_event(event)
        logger.info(f"Audit: SSH keys backed up to {backup_dir}, count={key_count}")

    def log_vm_key_update(
        self,
        vm_name: str,
        resource_group: str,
        success: bool,
        error: str | None = None,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log VM SSH key update event.

        Args:
            vm_name: VM name
            resource_group: Azure resource group
            success: Whether update succeeded
            error: Error message if failed
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_vm_key_update("vm-01", "my-rg", success=True)
        """
        user = user or self._get_system_user()

        event_details = {
            "resource_group": resource_group,
            "operation": "update_vm_ssh_key",
        }
        if error:
            event_details["error"] = error
        if details:
            event_details.update(details)

        severity = "critical" if not success else "info"

        event = AuditEvent(
            event_id=self._generate_event_id("vm_update"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_UPDATE_VM,  # type: ignore
            user=user,
            resource=vm_name,
            action="update_vm_ssh_key",
            outcome="success" if success else "failure",
            details=event_details,
            severity=severity,
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE", "KEY_ROTATION"],
        )

        self._audit_logger.log_event(event)

    def log_permission_fix(
        self,
        key_path: Path,
        old_permissions: str,
        new_permissions: str,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log SSH key permission fix event.

        Args:
            key_path: Path to key
            old_permissions: Old permissions (octal string)
            new_permissions: New permissions (octal string)
            user: Username (defaults to system user)
            details: Additional event details

        Example:
            >>> logger.log_permission_fix(
            ...     Path("~/.ssh/azlin_key"),
            ...     "0644",
            ...     "0600"
            ... )
        """
        user = user or self._get_system_user()

        event_details = {
            "key_path": str(key_path),
            "old_permissions": old_permissions,
            "new_permissions": new_permissions,
            "operation": "fix_ssh_key_permissions",
        }
        if details:
            event_details.update(details)

        event = AuditEvent(
            event_id=self._generate_event_id("perm_fix"),
            timestamp=datetime.now(UTC),
            event_type=SSHKeyEventType.SSH_KEY_PERMISSION_FIX,  # type: ignore
            user=user,
            resource=str(key_path.name),
            action="fix_ssh_key_permissions",
            outcome="success",
            details=event_details,
            severity="warning",  # Insecure permissions are notable
            compliance_tags=["SOC2", "ISO27001", "SSH_KEY_LIFECYCLE", "SECURITY"],
        )

        self._audit_logger.log_event(event)
        logger.info(
            f"Audit: SSH key permissions fixed for {key_path}, "
            f"{old_permissions} -> {new_permissions}"
        )

    def generate_compliance_report(
        self, framework: str, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """Generate compliance report for SSH key operations.

        Args:
            framework: "CIS", "SOC2", or "ISO27001"
            start_date: Report start date
            end_date: Report end date

        Returns:
            Compliance report dictionary

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.now()
            >>> start = end - timedelta(days=30)
            >>> report = logger.generate_compliance_report("SOC2", start, end)
        """
        return self._audit_logger.generate_compliance_report(framework, start_date, end_date)

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify audit log integrity.

        Returns:
            Tuple of (is_valid, list_of_corrupted_event_ids)

        Example:
            >>> is_valid, corrupted = logger.verify_integrity()
            >>> if not is_valid:
            ...     print(f"Corrupted events: {corrupted}")
        """
        return self._audit_logger.verify_integrity()

    def _get_system_user(self) -> str:
        """Get system username.

        Returns:
            Username from environment or 'unknown'
        """
        return os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    def _generate_event_id(self, prefix: str) -> str:
        """Generate unique event ID.

        Args:
            prefix: Event type prefix

        Returns:
            Unique event ID with timestamp
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        return f"{prefix}_{timestamp}"


__all__ = ["KeyAuditLogger", "SSHKeyEventType"]
