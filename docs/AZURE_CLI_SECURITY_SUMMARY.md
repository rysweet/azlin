# Azure CLI Command Display Security - Implementation Summary

## Quick Reference

This document provides a quick reference for implementing secure Azure CLI command display in azlin.

---

## TL;DR - Security Checklist

### Before Displaying Any Command:

```python
from azlin.security import AzureCommandSanitizer

# Always sanitize before display
safe_command = AzureCommandSanitizer.sanitize(command)
print(f"Executing: {safe_command}")
```

### Before Logging Any Command:

```python
from azlin.security import AzureCommandSanitizer

safe_command = AzureCommandSanitizer.sanitize_for_logging(command)
logger.info(f"Command: {safe_command}")
```

---

## Critical Sensitive Parameters

**These MUST be redacted:**

### Tier 1 - Critical Secrets (Immediate Compromise)
- `--password`, `--admin-password`, `--administrator-login-password`
- `--client-secret`, `--service-principal-secret`
- `--account-key`, `--connection-string`
- `--secret`, `--secrets`, `--secret-value`
- `--token`, `--access-token`, `--bearer-token`

### Tier 2 - High Risk (Privilege Escalation)
- `--ssh-key-value`, `--ssh-key-values`, `--ssh-private-key-file`
- `--certificate-data`, `--certificate-password`, `--pfx-password`
- `--sas-token`, `--shared-access-key`

### Tier 3 - Medium Risk (Potential Information Disclosure)
- `--custom-data`, `--user-data`, `--cloud-init` (may contain secrets)
- `--environment-variables`, `--env` (may contain secrets)
- `--docker-password`, `--registry-password`

---

## Implementation Pattern

### 1. Command Display Service

```python
from azlin.security import AzureCommandSanitizer
from azlin.agentic.audit_logger import AuditLogger

class CommandDisplayService:
    """Secure command display service."""

    def __init__(self):
        self.sanitizer = AzureCommandSanitizer()
        self.audit_logger = AuditLogger()

    def display_before_execution(
        self,
        command: str,
        context: dict[str, Any] | None = None
    ) -> None:
        """Display command before execution with security controls.

        Args:
            command: Azure CLI command to display
            context: Optional execution context
        """
        # Sanitize
        safe_cmd = self.sanitizer.sanitize(command)

        # Check if command contains sensitive parameters
        sensitive_params = self.sanitizer.get_sensitive_parameters_in_command(command)

        # Warn user if sensitive parameters detected
        if sensitive_params:
            print("⚠️  Command contains sensitive parameters (redacted in display)")

        # Display
        print(f"🔄 Executing: {safe_cmd}")

        # Audit log
        self.audit_logger.log(
            event="COMMAND_DISPLAY",
            details={"command": safe_cmd, "has_secrets": bool(sensitive_params)}
        )

    def display_progress(self, message: str) -> None:
        """Display progress message (also sanitized)."""
        safe_msg = self.sanitizer.sanitize(message)
        print(f"   {safe_msg}")

    def display_result(self, result: dict[str, Any]) -> None:
        """Display command result with sanitization."""
        # Sanitize result output
        if "output" in result:
            result["output"] = self.sanitizer.sanitize(result["output"])

        if "error" in result and result["error"]:
            result["error"] = self.sanitizer.sanitize(result["error"])

        # Display
        if result.get("success"):
            print(f"✓ Success: {result.get('output', '')}")
        else:
            print(f"✗ Error: {result.get('error', '')}")
```

### 2. Integration with Existing Code

#### In azure_cli.py Strategy:

```python
# src/azlin/agentic/strategies/azure_cli.py

from azlin.security import AzureCommandSanitizer

class AzureCLIStrategy(ExecutionStrategy):
    """Execute Azure operations via direct az CLI commands."""

    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        self.sanitizer = AzureCommandSanitizer()

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using Azure CLI commands."""
        # ... existing code ...

        # Generate commands
        commands = self._generate_commands(context)

        if context.dry_run:
            # Dry run: sanitize and show commands
            output = "DRY RUN - Commands to execute:\n"
            for cmd in commands:
                safe_cmd = self.sanitizer.sanitize(cmd)
                output += f"  {safe_cmd}\n"

            return ExecutionResult(
                success=True,
                strategy=Strategy.AZURE_CLI,
                output=output,
                metadata={"commands": [self.sanitizer.sanitize(c) for c in commands]}
            )

        # Execute commands
        for i, cmd in enumerate(commands, 1):
            # Display sanitized command
            safe_cmd = self.sanitizer.sanitize(cmd)
            print(f"[{i}/{len(commands)}] Executing: {safe_cmd}")

            # Execute command (unsanitized)
            result = self._execute_command(cmd)

            # ... rest of execution logic ...
```

#### In command_executor.py:

```python
# src/azlin/agentic/command_executor.py

from azlin.security import AzureCommandSanitizer

class CommandExecutor:
    """Executes azlin commands and tracks results."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.execution_history: list[dict[str, Any]] = []
        self.sanitizer = AzureCommandSanitizer()

    def execute(self, command_spec: dict[str, str]) -> dict[str, Any]:
        """Execute a single azlin command."""
        command = command_spec["command"]
        args = command_spec.get("args", [])

        # Build full command
        cmd_parts = command.split() + (args if isinstance(args, list) else [args])
        full_command = " ".join(cmd_parts)

        # Display sanitized command
        safe_cmd = self.sanitizer.sanitize(full_command)
        print(f"Executing: {safe_cmd}")

        if self.dry_run:
            result = {
                "command": safe_cmd,  # Store sanitized version
                "stdout": "[DRY RUN] Would execute command",
                "stderr": "",
                "returncode": 0,
                "success": True,
            }
        else:
            # Execute with original command
            # ... subprocess execution ...

            # Sanitize output and errors
            result = {
                "command": safe_cmd,  # Store sanitized
                "stdout": self.sanitizer.sanitize(process.stdout),
                "stderr": self.sanitizer.sanitize(process.stderr),
                "returncode": process.returncode,
                "success": process.returncode == 0,
            }

        # Track execution (with sanitized command)
        self.execution_history.append(result)

        return result
```

---

## Testing Requirements

### Minimum Test Coverage

```bash
# Run security tests
pytest tests/unit/security/test_azure_command_sanitizer.py -v

# Expected: 40+ tests, 100% pass rate

# Run with coverage
pytest tests/unit/security/ --cov=azlin.security --cov-report=term-missing
# Expected: 95%+ coverage
```

### Critical Test Cases

1. **Password Redaction**
   - All password parameters (`--password`, `--admin-password`, etc.)
   - Quoted and unquoted values
   - Multiple passwords in one command

2. **Connection String Redaction**
   - Azure Storage connection strings
   - SQL connection strings
   - Any string with `AccountKey=`

3. **Token Redaction**
   - SAS tokens (URLs starting with `?sv=`)
   - JWT tokens (starting with `eyJ`)
   - Bearer tokens

4. **Thread Safety**
   - Concurrent sanitization calls
   - No state leakage between threads

5. **Non-Sensitive Preservation**
   - Commands without secrets unchanged
   - Resource names preserved
   - Configuration values preserved

---

## Common Pitfalls to Avoid

### ❌ DON'T DO THIS:

```python
# WRONG: Displaying unsanitized command
print(f"Running: {command}")

# WRONG: Logging unsanitized command
logger.info(f"Executing: {command}")

# WRONG: Including command in error message
raise Exception(f"Command failed: {command}")
```

### ✅ DO THIS INSTEAD:

```python
from azlin.security import AzureCommandSanitizer

# RIGHT: Sanitize before display
safe_cmd = AzureCommandSanitizer.sanitize(command)
print(f"Running: {safe_cmd}")

# RIGHT: Sanitize before logging
safe_cmd = AzureCommandSanitizer.sanitize_for_logging(command)
logger.info(f"Executing: {safe_cmd}")

# RIGHT: Sanitize in error messages
safe_cmd = AzureCommandSanitizer.sanitize(command)
raise Exception(f"Command failed: {safe_cmd}")
```

---

## Detection Logic Summary

### Parameter-Based Detection

Matches patterns like: `--param-name value`

```python
# Regex pattern
r'(--[\w-]+)\s+(["\']?)([^\s"\']+)\2'

# Examples matched:
--password Secret123
--admin-password "My Pass"
--ssh-key-value 'ssh-rsa AAA...'
```

### Value-Based Detection

Detects secrets by their format, regardless of parameter name:

1. **Base64 strings (40+ chars)**: `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/==`
2. **JWT tokens**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig`
3. **Connection strings**: `AccountKey=abc123...==`
4. **SAS tokens**: `?sv=2021-01-01&ss=b&srt=sco&sp=rwdlac...`

---

## Log File Security

### Secure Log Configuration

```python
from pathlib import Path
import logging

def setup_secure_logging():
    """Configure logging with security controls."""
    log_file = Path.home() / ".azlin" / "commands.log"

    # Ensure secure permissions
    log_file.parent.mkdir(mode=0o700, exist_ok=True)
    if log_file.exists():
        log_file.chmod(0o600)  # Owner read/write only

    # Custom formatter with sanitization
    from azlin.security import AzureCommandSanitizer

    class SanitizingFormatter(logging.Formatter):
        def format(self, record):
            record.msg = AzureCommandSanitizer.sanitize(str(record.msg))
            if record.args:
                record.args = tuple(
                    AzureCommandSanitizer.sanitize(str(arg))
                    for arg in record.args
                )
            return super().format(record)

    handler = logging.FileHandler(log_file)
    handler.setFormatter(SanitizingFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    return handler
```

---

## Performance Considerations

### Benchmarks

Typical sanitization performance:
- **Short command (<100 chars)**: ~0.1ms
- **Long command (1000 chars)**: ~0.5ms
- **Very long command (10000 chars)**: ~2ms

**Conclusion**: Negligible performance impact for typical use cases.

### Optimization Tips

1. **Reuse sanitizer instance** (though class methods are stateless)
2. **Don't sanitize twice** - sanitize once at the display boundary
3. **Cache results** if same command displayed multiple times

---

## Integration Checklist

- [ ] Import `AzureCommandSanitizer` in all command display code
- [ ] Sanitize before printing to terminal
- [ ] Sanitize before writing to logs
- [ ] Sanitize in error messages
- [ ] Sanitize in progress indicators
- [ ] Sanitize in dry-run output
- [ ] Add tests for new command types
- [ ] Update documentation
- [ ] Security review
- [ ] Penetration testing

---

## Support & Questions

### Documentation
- Full security analysis: `/docs/AZURE_CLI_COMMAND_DISPLAY_SECURITY.md`
- Implementation: `/src/azlin/security/azure_command_sanitizer.py`
- Tests: `/tests/unit/security/test_azure_command_sanitizer.py`

### Security Contacts
- Security issues: Report via secure channel
- Questions: Team security lead

---

## Quick Examples

### Example 1: Simple Sanitization

```python
from azlin.security import sanitize_azure_command

# Before
cmd = "az vm create --admin-password MySecret123"

# After
safe = sanitize_azure_command(cmd)
# Result: "az vm create --admin-password [REDACTED]"
```

### Example 2: Check if Safe

```python
from azlin.security import AzureCommandSanitizer

cmd = "az vm list"
if AzureCommandSanitizer.is_command_safe(cmd):
    print(f"Safe to display: {cmd}")
else:
    print(f"Contains secrets: {AzureCommandSanitizer.sanitize(cmd)}")
```

### Example 3: List Sensitive Parameters

```python
from azlin.security import AzureCommandSanitizer

cmd = "az vm create --admin-password Pass --ssh-key-value key"
params = AzureCommandSanitizer.get_sensitive_parameters_in_command(cmd)
print(f"Sensitive parameters: {params}")
# Output: ['--admin-password', '--ssh-key-value']
```

---

**Last Updated**: 2025-10-30
**Version**: 1.0
**Status**: Ready for Implementation
