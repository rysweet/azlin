# Backup & DR System - Security Review

**Reviewed By**: Security Agent
**Date**: 2025-12-01
**Specification**: BACKUP_DR_SPEC.md
**Overall Assessment**: APPROVED with recommendations

## Executive Summary

The backup and disaster recovery specification follows solid security practices and aligns with azlin's security-first philosophy. The Azure CLI delegation pattern, input validation approach, and encryption handling are appropriate. However, several enhancements are recommended to strengthen the security posture.

**Security Rating**: 8.5/10 (Good - with recommended improvements)

## Findings by Category

### 1. Authentication & Authorization ✅ PASS

**Strengths**:
- Azure CLI delegation pattern prevents credential storage
- Clear RBAC requirements documented
- No hardcoded credentials or tokens

**Recommendations**:

#### R1.1: Add RBAC Validation (MEDIUM)
Validate user has required RBAC roles before operations:

```python
class BackupManager:
    @classmethod
    def _validate_rbac_permissions(cls, operation: str) -> None:
        """Verify user has required RBAC permissions for operation.

        Raises:
            SecurityError: If permissions insufficient
        """
        required_roles = {
            "backup": ["Contributor", "Disk Backup Reader"],
            "replicate": ["Contributor"],
            "restore": ["Virtual Machine Contributor"],
        }

        # Check Azure RBAC via CLI
        cmd = ["az", "role", "assignment", "list", "--query", "[].roleDefinitionName"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        user_roles = json.loads(result.stdout)

        if not any(role in user_roles for role in required_roles[operation]):
            raise SecurityError(
                f"Insufficient permissions for {operation}. "
                f"Required: {required_roles[operation]}"
            )
```

#### R1.2: Session Token Validation (LOW)
Verify Azure CLI token is valid before long operations:

```python
@classmethod
def _validate_azure_token(cls) -> None:
    """Ensure Azure CLI token is valid and not expired."""
    cmd = ["az", "account", "get-access-token"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise SecurityError("Azure CLI authentication expired. Run 'az login'")
```

### 2. Data Protection ✅ PASS

**Strengths**:
- Snapshots inherit VM disk encryption (Azure handles this)
- SQLite permissions documented (600)
- No sensitive data stored locally

**Recommendations**:

#### R2.1: Encrypt Sensitive Metadata (MEDIUM)
Encrypt sensitive fields in SQLite databases:

```python
import hashlib
from cryptography.fernet import Fernet

class SecureStorage:
    """Secure storage for sensitive metadata."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Derive key from Azure subscription ID (stable, per-subscription)
        self.key = self._derive_encryption_key()
        self.cipher = Fernet(self.key)

    def _derive_encryption_key(self) -> bytes:
        """Derive encryption key from Azure subscription ID."""
        cmd = ["az", "account", "show", "--query", "id", "-o", "tsv"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        subscription_id = result.stdout.strip()

        # Use PBKDF2 to derive key
        kdf_key = hashlib.pbkdf2_hmac(
            'sha256',
            subscription_id.encode(),
            b'azlin-backup-encryption',
            100000
        )
        return base64.urlsafe_b64encode(kdf_key[:32])

    def encrypt_field(self, value: str) -> str:
        """Encrypt sensitive field value."""
        return self.cipher.encrypt(value.encode()).decode()

    def decrypt_field(self, encrypted: str) -> str:
        """Decrypt sensitive field value."""
        return self.cipher.decrypt(encrypted.encode()).decode()
```

**Apply to error messages in databases** (may contain sensitive paths/config):
```sql
-- Store encrypted error messages
INSERT INTO replication_jobs (error_message) VALUES (?);
-- ? = encrypt_field(actual_error)
```

#### R2.2: Backup Metadata Sanitization (LOW)
Sanitize backup tags to prevent information leakage:

```python
@classmethod
def _sanitize_backup_tags(cls, tags: dict) -> dict:
    """Remove sensitive information from backup tags."""
    sensitive_keys = ["owner_email", "api_key", "password"]
    return {k: v for k, v in tags.items() if k.lower() not in sensitive_keys}
```

### 3. Input Validation ⚠️ NEEDS IMPROVEMENT

**Strengths**:
- Inherits SnapshotManager validation for VM names and resource groups
- Uses Azure naming patterns

**Critical Recommendations**:

#### R3.1: Region Name Validation (HIGH)
Add strict validation for region names to prevent command injection:

```python
@dataclass
class AzureRegions:
    """Valid Azure regions."""
    VALID_REGIONS = [
        "eastus", "eastus2", "westus", "westus2", "westus3",
        "centralus", "northcentralus", "southcentralus",
        "westcentralus", "canadacentral", "canadaeast",
        "brazilsouth", "northeurope", "westeurope",
        "uksouth", "ukwest", "francecentral", "francesouth",
        "germanywestcentral", "switzerlandnorth", "norwayeast",
        "swedencentral", "eastasia", "southeastasia",
        "japaneast", "japanwest", "australiaeast",
        "australiasoutheast", "centralindia", "southindia",
        "westindia", "koreacentral", "koreasouth",
    ]

class BackupManager:
    @classmethod
    def _validate_region(cls, region: str) -> None:
        """Validate region name against whitelist.

        Args:
            region: Azure region name

        Raises:
            SecurityError: If region is invalid
        """
        if region not in AzureRegions.VALID_REGIONS:
            raise SecurityError(
                f"Invalid region: {region}. Must be valid Azure region."
            )
```

#### R3.2: Snapshot Name Validation (HIGH)
Prevent snapshot name injection attacks:

```python
import re

SNAPSHOT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,80}$')

@classmethod
def _validate_snapshot_name(cls, name: str) -> None:
    """Validate snapshot name against injection attacks.

    Args:
        name: Snapshot name

    Raises:
        SecurityError: If name contains invalid characters
    """
    if not SNAPSHOT_NAME_PATTERN.match(name):
        raise SecurityError(
            f"Invalid snapshot name: {name}. "
            "Must be 1-80 alphanumeric/hyphen/underscore characters."
        )

    # Reject suspicious patterns
    suspicious_patterns = [
        r'[;&|`$]',  # Shell metacharacters
        r'\.\.',     # Path traversal
        r'[\x00-\x1f]',  # Control characters
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, name):
            raise SecurityError(f"Snapshot name contains invalid pattern: {pattern}")
```

#### R3.3: SQL Injection Prevention (CRITICAL)
Use parameterized queries exclusively:

```python
# BAD - SQL injection vulnerable
def query_backups(self, vm_name: str):
    cursor.execute(f"SELECT * FROM backups WHERE vm_name = '{vm_name}'")

# GOOD - Parameterized query
def query_backups(self, vm_name: str):
    cursor.execute("SELECT * FROM backups WHERE vm_name = ?", (vm_name,))
```

**Mandate in all modules**:
```python
class SecureDatabase:
    """Base class for secure database operations."""

    def execute(self, query: str, params: tuple = ()) -> None:
        """Execute query with mandatory parameterization.

        Args:
            query: SQL query with ? placeholders
            params: Parameter tuple

        Raises:
            SecurityError: If query contains string formatting
        """
        # Detect unsafe string formatting
        if "%" in query or ".format(" in query or f"{" in query:
            raise SecurityError("Use parameterized queries only. No string formatting.")

        self.cursor.execute(query, params)
```

### 4. Error Handling ⚠️ NEEDS IMPROVEMENT

**Strengths**:
- Errors logged with timestamps
- Failed operations tracked

**Recommendations**:

#### R4.1: Sanitize Error Messages (HIGH)
Prevent sensitive information leakage in errors:

```python
class SecureErrorHandler:
    """Secure error message handling."""

    SENSITIVE_PATTERNS = [
        r'password[:\s=]+\S+',  # Password values
        r'key[:\s=]+\S+',       # API keys
        r'/home/[^/\s]+',       # User home paths
        r'subscription-id',     # Subscription IDs
    ]

    @classmethod
    def sanitize_error(cls, error: str) -> str:
        """Remove sensitive information from error messages.

        Args:
            error: Raw error message

        Returns:
            Sanitized error message
        """
        sanitized = error
        for pattern in cls.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        return sanitized

    @classmethod
    def log_error(cls, error: Exception, context: str) -> None:
        """Log error securely.

        Args:
            error: Exception to log
            context: Operation context
        """
        sanitized_msg = cls.sanitize_error(str(error))
        logger.error(f"{context}: {sanitized_msg}")

        # Log full error (with sensitive data) to secure audit log only
        cls._audit_log_error(error, context)
```

#### R4.2: Secure Audit Logging (MEDIUM)
Separate audit log for full error details:

```python
class AuditLogger:
    """Secure audit logging with restricted permissions."""

    def __init__(self):
        self.audit_log = Path.home() / ".azlin" / "audit.log"
        # Ensure restrictive permissions (600)
        self.audit_log.touch(mode=0o600, exist_ok=True)

    def log_operation(
        self,
        operation: str,
        user: str,
        resource: str,
        success: bool,
        details: dict,
    ) -> None:
        """Log operation to audit trail.

        Args:
            operation: Operation type (backup, restore, etc.)
            user: Azure account user
            resource: Resource name
            success: Operation success/failure
            details: Additional details (may contain sensitive data)
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "operation": operation,
            "user": user,
            "resource": resource,
            "success": success,
            "details": details,
        }

        with open(self.audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

### 5. Resource Cleanup ✅ PASS (with minor improvements)

**Strengths**:
- Test resources deleted after verification
- Failed operation tracking
- Cleanup documented in specs

**Recommendations**:

#### R5.1: Resource Cleanup Verification (LOW)
Verify cleanup succeeded and log failures:

```python
class ResourceCleaner:
    """Secure resource cleanup with verification."""

    @classmethod
    def cleanup_test_disk(cls, disk_name: str, resource_group: str) -> bool:
        """Delete test disk and verify cleanup.

        Args:
            disk_name: Test disk name
            resource_group: Resource group

        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            # Delete disk
            cmd = ["az", "disk", "delete", "--name", disk_name, "--resource-group", resource_group, "--yes"]
            subprocess.run(cmd, check=True, timeout=60)

            # Verify deletion
            verify_cmd = ["az", "disk", "show", "--name", disk_name, "--resource-group", resource_group]
            result = subprocess.run(verify_cmd, capture_output=True)

            if result.returncode == 0:
                # Disk still exists - log as orphaned resource
                logger.error(f"Orphaned resource: {disk_name} in {resource_group}")
                cls._track_orphaned_resource(disk_name, resource_group, "disk")
                return False

            return True

        except Exception as e:
            logger.error(f"Cleanup failed for {disk_name}: {e}")
            cls._track_orphaned_resource(disk_name, resource_group, "disk")
            return False
```

#### R5.2: Orphaned Resource Tracking (MEDIUM)
Track and report orphaned resources:

```sql
CREATE TABLE orphaned_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type TEXT NOT NULL,  -- disk, snapshot, vm
    resource_name TEXT NOT NULL,
    resource_group TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    cleanup_attempted DATETIME NOT NULL,
    last_cleanup_attempt DATETIME,
    cleanup_attempts INTEGER DEFAULT 1
);

-- Add index for cleanup retry
CREATE INDEX idx_cleanup_attempts ON orphaned_resources(cleanup_attempts, last_cleanup_attempt);
```

```python
@classmethod
def cleanup_orphaned_resources(cls) -> dict[str, int]:
    """Retry cleanup of orphaned resources.

    Returns:
        {"cleaned": N, "failed": M}
    """
    orphaned = cls._get_orphaned_resources()
    results = {"cleaned": 0, "failed": 0}

    for resource in orphaned:
        try:
            cls._delete_resource(resource.type, resource.name, resource.resource_group)
            cls._remove_orphaned_resource(resource.id)
            results["cleaned"] += 1
        except Exception as e:
            cls._update_cleanup_attempt(resource.id)
            results["failed"] += 1

    return results
```

## Additional Security Requirements

### 6. Rate Limiting (NEW)

Add rate limiting to prevent resource exhaustion:

```python
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    """Rate limiter for Azure operations."""

    # Max operations per hour by type
    LIMITS = {
        "backup": 10,        # 10 backups per hour
        "restore": 5,        # 5 restores per hour
        "replicate": 20,     # 20 replications per hour
        "dr_test": 3,        # 3 DR tests per hour
    }

    def __init__(self):
        self.operations: defaultdict[str, list[datetime]] = defaultdict(list)

    def check_limit(self, operation: str) -> None:
        """Check if operation allowed under rate limit.

        Args:
            operation: Operation type

        Raises:
            SecurityError: If rate limit exceeded
        """
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=1)

        # Clean old operations
        self.operations[operation] = [
            t for t in self.operations[operation] if t > window_start
        ]

        # Check limit
        if len(self.operations[operation]) >= self.LIMITS[operation]:
            raise SecurityError(
                f"Rate limit exceeded for {operation}. "
                f"Max {self.LIMITS[operation]} per hour."
            )

        # Record operation
        self.operations[operation].append(now)
```

### 7. Secure Configuration (NEW)

Validate backup configuration against security policies:

```python
@dataclass
class BackupSecurityPolicy:
    """Security policy for backup configuration."""
    min_daily_retention: int = 7      # Must keep at least 7 days
    min_monthly_retention: int = 3    # Must keep at least 3 months
    require_cross_region: bool = True # Require geo-redundancy
    allowed_regions: list[str] = None # Whitelist regions

class BackupManager:
    @classmethod
    def _validate_security_policy(
        cls,
        config: BackupSchedule,
        policy: BackupSecurityPolicy,
    ) -> None:
        """Validate backup configuration against security policy.

        Args:
            config: Backup configuration
            policy: Security policy

        Raises:
            SecurityError: If configuration violates policy
        """
        if config.daily_retention < policy.min_daily_retention:
            raise SecurityError(
                f"Daily retention {config.daily_retention} below "
                f"minimum {policy.min_daily_retention}"
            )

        if config.monthly_retention < policy.min_monthly_retention:
            raise SecurityError(
                f"Monthly retention {config.monthly_retention} below "
                f"minimum {policy.min_monthly_retention}"
            )

        if policy.require_cross_region and not config.cross_region_enabled:
            raise SecurityError("Cross-region replication required by policy")

        if policy.allowed_regions and config.target_region not in policy.allowed_regions:
            raise SecurityError(
                f"Target region {config.target_region} not in "
                f"allowed regions: {policy.allowed_regions}"
            )
```

### 8. Compliance Logging (NEW)

Add compliance-focused logging for audit requirements:

```python
class ComplianceLogger:
    """Compliance logging for regulatory requirements."""

    def log_backup_created(self, backup: BackupInfo) -> None:
        """Log backup creation for compliance."""
        self._log_compliance_event({
            "event_type": "backup_created",
            "backup_name": backup.snapshot_name,
            "vm_name": backup.vm_name,
            "retention_tier": backup.retention_tier,
            "timestamp": backup.creation_time.isoformat(),
            "user": self._get_azure_user(),
        })

    def log_backup_deleted(self, backup_name: str, reason: str) -> None:
        """Log backup deletion for compliance."""
        self._log_compliance_event({
            "event_type": "backup_deleted",
            "backup_name": backup_name,
            "deletion_reason": reason,  # "expired", "manual", "failed"
            "timestamp": datetime.now(UTC).isoformat(),
            "user": self._get_azure_user(),
        })

    def log_restore_operation(
        self,
        backup_name: str,
        target_vm: str,
        success: bool,
    ) -> None:
        """Log restore operation for compliance."""
        self._log_compliance_event({
            "event_type": "restore_operation",
            "backup_name": backup_name,
            "target_vm": target_vm,
            "success": success,
            "timestamp": datetime.now(UTC).isoformat(),
            "user": self._get_azure_user(),
        })
```

## Summary of Recommendations

### Critical (Must Fix Before Release)
1. **R3.3**: SQL injection prevention with parameterized queries (CRITICAL)
2. **R3.1**: Region name validation with whitelist (HIGH)
3. **R3.2**: Snapshot name validation to prevent injection (HIGH)

### High Priority (Should Fix in Phase 5)
4. **R4.1**: Sanitize error messages to prevent info leakage (HIGH)
5. **R1.1**: RBAC validation before operations (MEDIUM)
6. **R2.1**: Encrypt sensitive metadata in SQLite (MEDIUM)

### Medium Priority (Nice to Have)
7. **R4.2**: Secure audit logging (MEDIUM)
8. **R5.2**: Orphaned resource tracking (MEDIUM)
9. **Rate Limiting**: Prevent resource exhaustion (MEDIUM)
10. **Secure Configuration**: Validate against security policies (MEDIUM)

### Low Priority (Future Enhancement)
11. **R1.2**: Session token validation (LOW)
12. **R2.2**: Backup metadata sanitization (LOW)
13. **R5.1**: Resource cleanup verification (LOW)
14. **Compliance Logging**: Regulatory audit trail (LOW)

## Approval Status

**STATUS**: ✅ APPROVED for implementation with mandatory critical fixes

**Conditions**:
1. Implement R3.3 (SQL injection prevention) before any code review
2. Implement R3.1 and R3.2 (validation) in Phase 1
3. Implement R4.1 (error sanitization) in Phase 5 security review
4. Address high-priority recommendations in Phase 5

**Security Sign-Off**: The specification follows solid security principles and can proceed to implementation with the critical fixes applied. The backup/DR system will meet enterprise security standards with these enhancements.

## Next Steps

1. Update BACKUP_DR_SPEC.md with critical security requirements
2. Add security validation to each module specification
3. Include security test cases in unit tests
4. Plan security testing in Phase 5 integration tests

**Reviewer**: Security Agent
**Date**: 2025-12-01
**Next Review**: After Phase 1 implementation
