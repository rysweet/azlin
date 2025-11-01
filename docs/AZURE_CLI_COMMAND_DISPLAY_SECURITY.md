# Azure CLI Command Display Security Analysis

## Executive Summary

This document provides a comprehensive security analysis for displaying Azure CLI commands in azlin before execution. It identifies security risks, provides implementation guidance, and establishes testing requirements to prevent sensitive data exposure.

**Risk Level**: HIGH - Command display features can leak credentials, secrets, and sensitive configuration data if not properly sanitized.

---

## 1. Security Risks Identified

### 1.1 Sensitive Data Exposure (CRITICAL)

**Risk**: Azure CLI commands contain sensitive parameters that must never be logged or displayed in plain text.

**Attack Vectors**:
- Terminal history leaking passwords
- Log files containing secrets
- Screen sharing exposing credentials
- Debug output in error reports
- Copy-paste of commands to public forums

**Impact**: Complete account compromise, unauthorized resource access, data breach

### 1.2 Command Injection Attack Surface (HIGH)

**Risk**: Displaying unsanitized commands may encourage users to copy-paste malicious commands.

**Attack Vectors**:
- Specially crafted resource names with shell metacharacters
- Command substitution in parameter values
- Multi-command injection via semicolons

**Impact**: Remote code execution, privilege escalation

### 1.3 Log File Security (HIGH)

**Risk**: Commands logged to files persist indefinitely and may be accessed by unauthorized users.

**Attack Vectors**:
- Log aggregation systems collecting secrets
- Backup systems preserving credentials
- Insecure log file permissions
- Log shipping to cloud services

**Impact**: Long-term credential exposure, compliance violations

### 1.4 Terminal Escape Sequence Injection (MEDIUM)

**Risk**: Malicious escape sequences in displayed commands can manipulate terminal behavior.

**Attack Vectors**:
- ANSI escape codes in resource names
- Terminal title manipulation
- Clipboard hijacking via OSC sequences

**Impact**: UI spoofing, clipboard credential theft

### 1.5 Race Conditions in Multi-threaded Scenarios (MEDIUM)

**Risk**: Concurrent command display may interleave sensitive data from different contexts.

**Attack Vectors**:
- Thread-unsafe sanitization logic
- Shared sanitizer state across threads
- Time-of-check to time-of-use vulnerabilities

**Impact**: Cross-session data leakage

### 1.6 Information Leakage to Unauthorized Users (MEDIUM)

**Risk**: Command display may reveal infrastructure details to unauthorized observers.

**Attack Vectors**:
- Screen sharing during demos
- Shoulder surfing
- Terminal session recording
- Shared terminal multiplexer sessions

**Impact**: Reconnaissance for targeted attacks

---

## 2. Sensitive Azure CLI Parameters

### 2.1 Authentication & Identity

```python
SENSITIVE_AUTH_PARAMS = [
    # Direct credentials
    "--password",
    "--admin-password",
    "--client-secret",

    # SSH keys
    "--ssh-key-value",
    "--ssh-key-values",
    "--ssh-private-key-file",
    "--generate-ssh-keys",  # Caution: generates keys

    # Certificates
    "--certificate-data",
    "--certificate-file",

    # Service principals
    "--service-principal",
    "--tenant",

    # Managed identity
    "--identity",
]
```

### 2.2 Secrets & Keys

```python
SENSITIVE_SECRET_PARAMS = [
    # Key Vault
    "--secrets",
    "--secret",

    # Storage
    "--account-key",
    "--connection-string",
    "--sas-token",

    # Database
    "--administrator-login-password",
    "--admin-user",
    "--admin-password",

    # Container registry
    "--password",
    "--docker-password",

    # API tokens
    "--token",
    "--access-token",
]
```

### 2.3 Sensitive Configuration

```python
SENSITIVE_CONFIG_PARAMS = [
    # Custom data (may contain secrets)
    "--custom-data",
    "--user-data",
    "--cloud-init",

    # Environment variables
    "--environment-variables",

    # Configuration strings
    "--settings",
    "--configuration",
]
```

---

## 3. Detection Logic & Regex Patterns

### 3.1 Parameter-Based Detection

```python
import re
from typing import Pattern

class AzureCommandSanitizer:
    """Sanitize Azure CLI commands for safe display."""

    # Parameter patterns (case-insensitive)
    SENSITIVE_PARAM_PATTERNS: dict[str, Pattern] = {
        "password": re.compile(
            r'--[a-z-]*password\s+["\']?([^\s"\']+)',
            re.IGNORECASE
        ),
        "secret": re.compile(
            r'--[a-z-]*secret\s+["\']?([^\s"\']+)',
            re.IGNORECASE
        ),
        "key": re.compile(
            r'--[a-z-]*(key|sas-token)\s+["\']?([^\s"\']+)',
            re.IGNORECASE
        ),
        "token": re.compile(
            r'--[a-z-]*token\s+["\']?([^\s"\']+)',
            re.IGNORECASE
        ),
        "connection_string": re.compile(
            r'--connection-string\s+["\']?([^\s"\']+)',
            re.IGNORECASE
        ),
    }

    # Value patterns (detect secrets in values)
    SECRET_VALUE_PATTERNS: dict[str, Pattern] = {
        # Azure connection string format
        "azure_connection_string": re.compile(
            r'AccountKey=([A-Za-z0-9+/=]+)',
            re.IGNORECASE
        ),
        # Azure SAS token
        "sas_token": re.compile(
            r'(\?sv=\d{4}-\d{2}-\d{2}[^"\s]+)',
            re.IGNORECASE
        ),
        # Base64 encoded secrets (likely keys)
        "base64_long": re.compile(
            r'\b([A-Za-z0-9+/]{40,}={0,2})\b'
        ),
        # JWT tokens
        "jwt": re.compile(
            r'(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)'
        ),
    }

    REDACTED = "[REDACTED]"

    @classmethod
    def sanitize_command(cls, command: str) -> str:
        """Sanitize Azure CLI command for safe display.

        Args:
            command: Azure CLI command string

        Returns:
            Sanitized command with secrets replaced by [REDACTED]

        Examples:
            >>> sanitize_command("az vm create --admin-password MyPass123")
            'az vm create --admin-password [REDACTED]'
        """
        result = command

        # Apply parameter-based patterns
        for name, pattern in cls.SENSITIVE_PARAM_PATTERNS.items():
            result = pattern.sub(
                lambda m: m.group(0).split()[0] + " " + cls.REDACTED,
                result
            )

        # Apply value-based patterns
        for name, pattern in cls.SECRET_VALUE_PATTERNS.items():
            result = pattern.sub(cls.REDACTED, result)

        return result
```

### 3.2 Comprehensive Parameter List

```python
# Complete list of sensitive Azure CLI parameters
AZURE_SENSITIVE_PARAMS = {
    # Authentication
    "--password", "--admin-password", "--administrator-login-password",
    "--client-secret", "--service-principal-secret",

    # SSH
    "--ssh-key-value", "--ssh-key-values", "--ssh-private-key-file",

    # Storage & Keys
    "--account-key", "--connection-string", "--sas-token",
    "--primary-key", "--secondary-key", "--shared-access-key",

    # Secrets
    "--secret", "--secrets", "--secret-value",

    # Tokens
    "--token", "--access-token", "--refresh-token", "--bearer-token",

    # Certificates
    "--certificate-data", "--certificate-password", "--pfx-password",

    # Database
    "--db-password", "--sql-password",

    # Custom data (may contain secrets)
    "--custom-data", "--user-data", "--cloud-init",

    # Docker
    "--docker-password", "--registry-password",

    # Environment variables (may contain secrets)
    "--environment-variables", "--env",
}
```

---

## 4. Security Best Practices

### 4.1 Defense in Depth

Implement multiple layers of protection:

1. **Input Sanitization**: Sanitize at the point of command construction
2. **Display Sanitization**: Sanitize before displaying to user
3. **Log Sanitization**: Sanitize before writing to logs
4. **Output Sanitization**: Sanitize in error messages

```python
class CommandDisplayService:
    """Service for safely displaying Azure CLI commands."""

    def __init__(self):
        self.sanitizer = AzureCommandSanitizer()
        self.log_sanitizer = LogSanitizer()

    def display_command(self, command: str) -> None:
        """Display command with all sanitization layers applied."""
        # Layer 1: Command-specific sanitization
        safe_cmd = self.sanitizer.sanitize_command(command)

        # Layer 2: General log sanitization
        safe_cmd = self.log_sanitizer.sanitize(safe_cmd)

        # Layer 3: Terminal escape sanitization
        safe_cmd = self._sanitize_terminal_escapes(safe_cmd)

        # Display
        print(f"Executing: {safe_cmd}")

        # Layer 4: Log with additional sanitization
        self._log_command(safe_cmd)

    def _sanitize_terminal_escapes(self, text: str) -> str:
        """Remove ANSI escape sequences and control characters."""
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub('', text)

        # Remove control characters except newline/tab
        text = ''.join(char for char in text
                      if char in '\n\t' or ord(char) >= 32)

        return text

    def _log_command(self, command: str) -> None:
        """Log command with additional protection."""
        # Use existing audit logger with sanitization
        logger.info(f"Command: {command}")
```

### 4.2 Fail Secure

When in doubt, redact:

```python
def should_redact_parameter(param_name: str) -> bool:
    """Conservative approach: redact if uncertain.

    Returns True if parameter name suggests sensitive content.
    """
    sensitive_keywords = [
        'password', 'secret', 'key', 'token', 'credential',
        'auth', 'private', 'cert', 'pfx', 'connection'
    ]

    param_lower = param_name.lower()
    return any(keyword in param_lower for keyword in sensitive_keywords)
```

### 4.3 Thread Safety

Use thread-local storage for sanitization state:

```python
import threading

class ThreadSafeCommandSanitizer:
    """Thread-safe command sanitizer."""

    _local = threading.local()

    @classmethod
    def sanitize(cls, command: str) -> str:
        """Thread-safe sanitization."""
        # Each thread gets its own sanitizer instance
        if not hasattr(cls._local, 'sanitizer'):
            cls._local.sanitizer = AzureCommandSanitizer()

        return cls._local.sanitizer.sanitize_command(command)
```

### 4.4 Secure Logging

```python
import logging
from pathlib import Path

def setup_secure_logging():
    """Configure logging with security controls."""
    log_file = Path.home() / ".azlin" / "commands.log"

    # Ensure secure permissions
    log_file.parent.mkdir(mode=0o700, exist_ok=True)
    if log_file.exists():
        log_file.chmod(0o600)

    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.INFO)

    # Use custom formatter with sanitization
    formatter = SanitizingFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    return handler

class SanitizingFormatter(logging.Formatter):
    """Logging formatter that sanitizes sensitive data."""

    def format(self, record: logging.LogRecord) -> str:
        # Sanitize message before formatting
        record.msg = LogSanitizer.sanitize(str(record.msg))

        # Sanitize args
        if record.args:
            record.args = tuple(
                LogSanitizer.sanitize(str(arg))
                for arg in record.args
            )

        return super().format(record)
```

---

## 5. Testing Requirements

### 5.1 Unit Tests

```python
# tests/unit/test_command_sanitization.py

import pytest
from azlin.security import AzureCommandSanitizer

class TestCommandSanitization:
    """Test Azure CLI command sanitization."""

    @pytest.mark.parametrize("command,expected", [
        # Passwords
        (
            "az vm create --admin-password MySecretPass123",
            "az vm create --admin-password [REDACTED]"
        ),
        # SSH keys
        (
            "az vm create --ssh-key-value 'ssh-rsa AAAAB3...'",
            "az vm create --ssh-key-value [REDACTED]"
        ),
        # Connection strings
        (
            "az storage account show-connection-string --connection-string 'DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=abcd1234'",
            "az storage account show-connection-string --connection-string [REDACTED]"
        ),
        # SAS tokens
        (
            "az storage blob url --account-name myaccount --sas-token '?sv=2021-01-01&ss=b&srt=sco&sp=rwdlac&se=2024-01-01'",
            "az storage blob url --account-name myaccount --sas-token [REDACTED]"
        ),
        # Custom data (may contain secrets)
        (
            "az vm create --custom-data '#!/bin/bash\\nPASS=secret'",
            "az vm create --custom-data [REDACTED]"
        ),
        # Multiple sensitive params
        (
            "az vm create --admin-password Pass123 --ssh-key-value 'ssh-rsa AAA'",
            "az vm create --admin-password [REDACTED] --ssh-key-value [REDACTED]"
        ),
    ])
    def test_sanitize_sensitive_parameters(self, command, expected):
        """Test that sensitive parameters are redacted."""
        result = AzureCommandSanitizer.sanitize_command(command)
        assert result == expected

    def test_preserves_non_sensitive_parameters(self):
        """Test that non-sensitive parameters are preserved."""
        command = "az vm create --name myvm --resource-group myrg --image Ubuntu2204"
        result = AzureCommandSanitizer.sanitize_command(command)
        assert result == command

    def test_handles_quoted_values(self):
        """Test sanitization of quoted parameter values."""
        command = 'az vm create --admin-password "My Pass 123"'
        result = AzureCommandSanitizer.sanitize_command(command)
        assert "My Pass 123" not in result
        assert "[REDACTED]" in result

    def test_thread_safety(self):
        """Test that sanitization is thread-safe."""
        import concurrent.futures

        commands = [
            f"az vm create --admin-password Secret{i}"
            for i in range(100)
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(
                AzureCommandSanitizer.sanitize_command,
                commands
            ))

        # All secrets should be redacted
        for result in results:
            assert "Secret" not in result
            assert "[REDACTED]" in result

    def test_no_partial_redaction(self):
        """Test that entire secret values are redacted, not partial."""
        command = "az vm create --admin-password VeryLongSecretPassword123456"
        result = AzureCommandSanitizer.sanitize_command(command)

        # Should not contain any part of the password
        assert "VeryLong" not in result
        assert "Password" not in result
        assert "123456" not in result
```

### 5.2 Integration Tests

```python
# tests/integration/test_command_display_security.py

import logging
from pathlib import Path
import pytest
from azlin.agentic.strategies.azure_cli import AzureCLIStrategy
from azlin.agentic.types import ExecutionContext, Intent

class TestCommandDisplaySecurity:
    """Integration tests for secure command display."""

    def test_dry_run_sanitizes_sensitive_data(self, tmp_path):
        """Test that dry-run output sanitizes sensitive data."""
        intent = Intent(
            intent="Create VM with admin password",
            parameters={
                "vm_name": "test-vm",
                "admin_password": "SuperSecret123!",
            },
            azlin_commands=[],
        )

        context = ExecutionContext(
            intent=intent,
            dry_run=True,
        )

        strategy = AzureCLIStrategy()
        result = strategy.execute(context)

        # Output should not contain password
        assert "SuperSecret123!" not in result.output
        assert "[REDACTED]" in result.output

    def test_logs_do_not_contain_secrets(self, tmp_path, caplog):
        """Test that log files never contain sensitive data."""
        # Configure logging to temp file
        log_file = tmp_path / "test.log"
        handler = logging.FileHandler(log_file)
        logger = logging.getLogger("azlin")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            # Execute command with sensitive data
            intent = Intent(
                intent="Create VM",
                parameters={
                    "vm_name": "test-vm",
                    "admin_password": "TopSecret999",
                },
                azlin_commands=[],
            )

            context = ExecutionContext(intent=intent)
            strategy = AzureCLIStrategy()

            # This will log the command
            strategy.execute(context)

            # Check log file
            log_content = log_file.read_text()
            assert "TopSecret999" not in log_content

        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_error_messages_sanitized(self, monkeypatch):
        """Test that error messages don't leak secrets."""
        import subprocess

        def mock_run(*args, **kwargs):
            # Simulate error that includes password
            raise Exception("Authentication failed with password: SecretPass123")

        monkeypatch.setattr(subprocess, "run", mock_run)

        intent = Intent(
            intent="Create VM",
            parameters={"admin_password": "SecretPass123"},
            azlin_commands=[],
        )

        context = ExecutionContext(intent=intent)
        strategy = AzureCLIStrategy()
        result = strategy.execute(context)

        # Error should be sanitized
        assert "SecretPass123" not in result.error
        assert "[REDACTED]" in result.error
```

### 5.3 Security Test Suite

```python
# tests/security/test_data_leakage.py

class TestDataLeakagePrevention:
    """Security tests to prevent data leakage."""

    def test_no_secrets_in_exception_repr(self):
        """Test that exception __repr__ doesn't leak secrets."""
        try:
            raise ValueError("Auth failed with password: Secret123")
        except ValueError as e:
            sanitized = LogSanitizer.sanitize_exception(e)
            assert "Secret123" not in sanitized

    def test_no_secrets_in_traceback(self):
        """Test that tracebacks are sanitized."""
        import traceback

        try:
            password = "VerySecret123"
            raise ValueError(f"Failed with {password}")
        except ValueError:
            tb = traceback.format_exc()
            sanitized = LogSanitizer.sanitize(tb)
            assert "VerySecret123" not in sanitized

    def test_terminal_output_sanitized(self, capsys):
        """Test that terminal output is sanitized."""
        from azlin.agentic.command_executor import CommandExecutor

        executor = CommandExecutor()
        result = executor.execute({
            "command": "az vm create",
            "args": ["--admin-password", "Secret123"]
        })

        # Capture output
        captured = capsys.readouterr()
        assert "Secret123" not in captured.out
        assert "Secret123" not in captured.err
```

---

## 6. Additional Security Controls

### 6.1 Audit Logging

All command displays should be audit logged (without secrets):

```python
class SecureCommandDisplay:
    """Secure command display with audit logging."""

    def __init__(self):
        self.audit_logger = AuditLogger()
        self.sanitizer = AzureCommandSanitizer()

    def display_before_execution(self, command: str, context: dict) -> None:
        """Display command before execution with full security controls."""
        # Sanitize
        safe_command = self.sanitizer.sanitize_command(command)

        # Display to user
        print(f"🔄 Executing: {safe_command}")

        # Audit log
        self.audit_logger.log(
            event="COMMAND_DISPLAY",
            details={
                "command": safe_command,
                "user": context.get("user"),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
```

### 6.2 User Warning System

Warn users when sensitive parameters are used:

```python
def warn_sensitive_parameters(command: str) -> None:
    """Warn user if command contains sensitive parameters."""
    sensitive_params = [
        p for p in AZURE_SENSITIVE_PARAMS
        if p in command
    ]

    if sensitive_params:
        print("⚠️  WARNING: Command contains sensitive parameters:")
        for param in sensitive_params:
            print(f"   - {param}")
        print("   These will be redacted in logs and display.")
```

### 6.3 Environment Variable Sanitization

Environment variables may also contain secrets:

```python
def sanitize_environment(env: dict[str, str]) -> dict[str, str]:
    """Sanitize environment variables for display."""
    sensitive_env_vars = {
        'AZURE_CLIENT_SECRET',
        'AZURE_PASSWORD',
        'AZURE_STORAGE_KEY',
        'ARM_CLIENT_SECRET',
    }

    return {
        key: "[REDACTED]" if key in sensitive_env_vars else value
        for key, value in env.items()
    }
```

---

## 7. Implementation Checklist

- [ ] **Command Sanitization**
  - [ ] Implement AzureCommandSanitizer class
  - [ ] Add parameter-based redaction
  - [ ] Add value-based redaction (connection strings, tokens)
  - [ ] Handle quoted and unquoted values
  - [ ] Thread-safe implementation

- [ ] **Display Layer Security**
  - [ ] Sanitize before terminal output
  - [ ] Remove ANSI escape sequences
  - [ ] Sanitize progress indicators
  - [ ] Sanitize error messages

- [ ] **Logging Security**
  - [ ] Implement SanitizingFormatter
  - [ ] Configure secure log file permissions (0600)
  - [ ] Audit log command displays
  - [ ] Rotate logs securely

- [ ] **Testing**
  - [ ] Unit tests for all sensitive parameters
  - [ ] Integration tests for dry-run mode
  - [ ] Security tests for data leakage
  - [ ] Thread safety tests
  - [ ] Fuzzing tests for edge cases

- [ ] **Documentation**
  - [ ] User documentation on security features
  - [ ] Developer guide for adding new parameters
  - [ ] Security incident response procedures

- [ ] **Code Review**
  - [ ] Security review by team
  - [ ] Penetration testing
  - [ ] Third-party security audit (if required)

---

## 8. Compliance & Regulations

### 8.1 GDPR Considerations

- Personal data in commands must be handled per GDPR
- Right to erasure applies to log files
- Data minimization principle applies to logging

### 8.2 PCI DSS Compliance

If handling payment systems:
- No cardholder data in logs (Requirement 3.4)
- Render PAN unreadable (Requirement 3.4)
- Secure log files (Requirement 10.5)

### 8.3 SOC 2 Type II

For SOC 2 compliance:
- Audit trails of command execution
- Access controls on logs
- Encryption at rest for logs

---

## 9. Incident Response

### 9.1 If Secret Leakage Discovered

1. **Immediate Actions**
   - Rotate compromised credentials immediately
   - Revoke leaked tokens/keys
   - Audit access logs for unauthorized usage

2. **Investigation**
   - Identify scope of exposure
   - Determine if logs were accessed
   - Review backup systems

3. **Remediation**
   - Deploy fix to sanitization logic
   - Update affected systems
   - Notify affected users if required

4. **Prevention**
   - Add test case for missed pattern
   - Review similar code paths
   - Enhanced monitoring

### 9.2 Disclosure Policy

If vulnerability affects users:
- Follow responsible disclosure timeline
- Provide remediation guidance
- Update security documentation

---

## 10. References

### Internal Documentation
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/src/azlin/log_sanitizer.py`
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/src/azlin/agentic/audit_logger.py`
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/tests/unit/test_auth_security.py`

### External Resources
- [Azure CLI Security Best Practices](https://learn.microsoft.com/en-us/cli/azure/azure-cli-security)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [CWE-532: Information Exposure Through Log Files](https://cwe.mitre.org/data/definitions/532.html)

---

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-30 | Security Analysis | Initial security analysis document |

---

**Classification**: INTERNAL - Security Sensitive
**Review Frequency**: Quarterly or after security incidents
**Next Review**: 2026-01-30
