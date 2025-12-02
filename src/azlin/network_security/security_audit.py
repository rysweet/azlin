"""Enhanced Security Audit Logging with Integrity Verification.

Comprehensive audit logging system for security-sensitive operations.
Provides tamper-evident logging with integrity checksums and compliance reporting.

Key features:
- JSONL format (one JSON per line)
- Integrity checksums (SHA256)
- Secure file permissions (0600)
- Automated backup
- Query interface
- Compliance reporting (CIS, SOC2, ISO27001)

Philosophy:
- Comprehensive: Log ALL security decisions
- Tamper-evident: Integrity checksums detect tampering
- Secure: Owner-only file permissions
- Queryable: Structured format for analysis

Public API:
    SecurityAuditLogger: Main logger class
    AuditEvent: Structured security event
    AuditEventType: Event type enumeration

Example:
    >>> logger = SecurityAuditLogger()
    >>> event = AuditEvent(...)
    >>> logger.log_event(event)
"""

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
import logging

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of security events to audit."""

    BASTION_OPT_OUT = "bastion_opt_out"
    BASTION_TUNNEL_CREATE = "bastion_tunnel_create"
    BASTION_TUNNEL_CLOSE = "bastion_tunnel_close"
    NSG_RULE_APPLY = "nsg_rule_apply"
    NSG_RULE_MODIFY = "nsg_rule_modify"
    NSG_RULE_DELETE = "nsg_rule_delete"
    NSG_VALIDATION_FAIL = "nsg_validation_fail"
    NSG_VALIDATION_PASS = "nsg_validation_pass"
    CREDENTIAL_ACCESS = "credential_access"
    PUBLIC_IP_ASSIGN = "public_ip_assign"
    SECURITY_SCAN_FAIL = "security_scan_fail"
    POLICY_VIOLATION = "policy_violation"
    CONFIGURATION_DRIFT = "configuration_drift"
    VPN_GATEWAY_CREATE = "vpn_gateway_create"
    PRIVATE_ENDPOINT_CREATE = "private_endpoint_create"


@dataclass
class AuditEvent:
    """Structured security audit event.

    Represents a security-sensitive operation that must be logged for
    accountability and compliance purposes.
    """

    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    user: str
    resource: str
    action: str
    outcome: str  # "success" or "failure"
    details: Dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # "info", "warning", "critical"
    compliance_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation with ISO timestamp in UTC
        """
        # Ensure timezone-aware timestamp (treat naive as UTC)
        timestamp = self.timestamp.replace(tzinfo=UTC) if self.timestamp.tzinfo is None else self.timestamp

        return {
            "event_id": self.event_id,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "event_type": self.event_type.value if isinstance(self.event_type, Enum) else self.event_type,
            "user": self.user,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "details": self.details,
            "severity": self.severity,
            "compliance_tags": self.compliance_tags,
        }


class SecurityAuditLogger:
    """Enhanced security audit logging with integrity verification.

    Provides comprehensive audit logging for all security-sensitive operations
    with tamper detection through integrity checksums.

    Features:
    - JSONL format (one JSON object per line)
    - SHA256 integrity checksums
    - Secure file permissions (0600 owner-only)
    - Automated daily backup
    - Query interface for analysis
    - Compliance reporting
    """

    AUDIT_FILE = Path.home() / ".azlin" / "security_audit.jsonl"
    BACKUP_DIR = Path.home() / ".azlin" / "audit_backups"

    def __init__(self):
        """Initialize audit logger and ensure directory structure."""
        self._ensure_audit_structure()

    def _ensure_audit_structure(self) -> None:
        """Create audit directory structure with secure permissions."""
        # Create directories
        self.AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # Set directory permissions (owner-only: rwx------)
        os.chmod(self.AUDIT_FILE.parent, 0o700)
        os.chmod(self.BACKUP_DIR, 0o700)

    def log_event(self, event: AuditEvent) -> None:
        """Log security event to audit trail.

        Writes event to JSONL file with integrity checksum and secure permissions.

        Args:
            event: AuditEvent to log
        """
        # Convert event to dictionary
        event_dict = event.to_dict()

        # Add integrity checksum
        event_dict["checksum"] = self._compute_checksum(event_dict)

        # Append to audit log (JSONL format)
        with open(self.AUDIT_FILE, "a") as f:
            f.write(json.dumps(event_dict) + "\n")

        # Set secure permissions (owner-only: rw-------)
        os.chmod(self.AUDIT_FILE, 0o600)

        # Backup periodically
        if self._should_backup():
            self._backup_audit_log()

    def _compute_checksum(self, event_dict: Dict[str, Any]) -> str:
        """Compute SHA256 integrity checksum for event.

        The checksum is computed over all event fields EXCEPT the checksum itself.
        This allows verification that the event has not been tampered with.

        Args:
            event_dict: Event dictionary

        Returns:
            SHA256 checksum as hex string
        """
        # Exclude checksum field itself
        event_copy = {k: v for k, v in event_dict.items() if k != "checksum"}

        # Sort keys for deterministic output
        event_json = json.dumps(event_copy, sort_keys=True)

        # Compute SHA256
        return hashlib.sha256(event_json.encode()).hexdigest()

    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """Verify audit log integrity by checking all checksums.

        Returns:
            Tuple of (is_valid, list_of_corrupted_event_ids)
        """
        if not self.AUDIT_FILE.exists():
            return True, []

        corrupted = []

        with open(self.AUDIT_FILE) as f:
            for line_num, line in enumerate(f, 1):
                try:
                    event = json.loads(line)
                    stored_checksum = event.get("checksum")
                    computed_checksum = self._compute_checksum(event)

                    if stored_checksum != computed_checksum:
                        corrupted.append(event.get("event_id", f"line_{line_num}"))

                except json.JSONDecodeError:
                    corrupted.append(f"line_{line_num}")

        return len(corrupted) == 0, corrupted

    def _should_backup(self) -> bool:
        """Determine if audit log should be backed up.

        Backup policy: Once per day

        Returns:
            True if backup should be performed
        """
        if not self.AUDIT_FILE.exists():
            return False

        # Check if file is more than 24 hours old
        file_age = time.time() - os.path.getmtime(self.AUDIT_FILE)
        return file_age > 86400  # 24 hours in seconds

    def _backup_audit_log(self) -> None:
        """Create timestamped backup of audit log."""
        if not self.AUDIT_FILE.exists():
            return

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = self.BACKUP_DIR / f"security_audit_{timestamp}.jsonl"

        # Copy file
        shutil.copy2(self.AUDIT_FILE, backup_path)

        # Set secure permissions on backup
        os.chmod(backup_path, 0o600)

        logger.info(f"Audit log backed up to {backup_path}")

    def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        user: Optional[str] = None,
        resource: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[str] = None,
    ) -> List[AuditEvent]:
        """Query audit events with filters.

        Args:
            event_type: Filter by event type
            user: Filter by user
            resource: Filter by resource
            start_time: Filter by start time (inclusive)
            end_time: Filter by end time (inclusive)
            severity: Filter by severity level

        Returns:
            List of matching AuditEvent objects
        """
        events = []

        if not self.AUDIT_FILE.exists():
            return events

        with open(self.AUDIT_FILE) as f:
            for line in f:
                try:
                    event_dict = json.loads(line)

                    # Apply filters
                    if event_type and event_dict["event_type"] != event_type.value:
                        continue
                    if user and event_dict["user"] != user:
                        continue
                    if resource and event_dict["resource"] != resource:
                        continue
                    if severity and event_dict["severity"] != severity:
                        continue

                    # Parse timestamp
                    event_time = datetime.fromisoformat(event_dict["timestamp"].replace("Z", "+00:00"))

                    # Normalize timezone-naive datetimes to UTC for comparison
                    start_time_normalized = start_time.replace(tzinfo=UTC) if start_time and start_time.tzinfo is None else start_time
                    end_time_normalized = end_time.replace(tzinfo=UTC) if end_time and end_time.tzinfo is None else end_time

                    if start_time_normalized and event_time < start_time_normalized:
                        continue
                    if end_time_normalized and event_time > end_time_normalized:
                        continue

                    # Convert back to AuditEvent object
                    event = AuditEvent(
                        event_id=event_dict["event_id"],
                        timestamp=event_time,
                        event_type=AuditEventType(event_dict["event_type"]),
                        user=event_dict["user"],
                        resource=event_dict["resource"],
                        action=event_dict["action"],
                        outcome=event_dict["outcome"],
                        details=event_dict.get("details", {}),
                        severity=event_dict.get("severity", "info"),
                        compliance_tags=event_dict.get("compliance_tags", []),
                    )
                    events.append(event)

                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed audit event: {e}")
                    continue

        return events

    def generate_compliance_report(
        self, framework: str, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """Generate compliance report for audits.

        Args:
            framework: "CIS", "SOC2", or "ISO27001"
            start_date: Report start date
            end_date: Report end date

        Returns:
            Structured compliance report dictionary
        """
        events = self.query_events(start_time=start_date, end_time=end_date)

        # Filter by compliance tags
        relevant_events = [e for e in events if any(framework in tag for tag in e.compliance_tags)]

        # Count events by type
        events_by_type = {}
        for event in relevant_events:
            event_type = event.event_type.value
            events_by_type[event_type] = events_by_type.get(event_type, 0) + 1

        # Count events by user
        events_by_user = {}
        for event in relevant_events:
            user = event.user
            events_by_user[user] = events_by_user.get(user, 0) + 1

        # Count events by severity
        events_by_severity = {}
        for event in relevant_events:
            severity = event.severity
            events_by_severity[severity] = events_by_severity.get(severity, 0) + 1

        report = {
            "framework": framework,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_events": len(relevant_events),
            "critical_findings": len([e for e in relevant_events if e.severity == "critical"]),
            "policy_violations": len(
                [e for e in relevant_events if e.event_type == AuditEventType.POLICY_VIOLATION]
            ),
            "events_by_type": events_by_type,
            "events_by_user": events_by_user,
            "events_by_severity": events_by_severity,
        }

        return report


__all__ = ["SecurityAuditLogger", "AuditEvent", "AuditEventType"]
