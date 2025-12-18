# Audit Logging and Error Handling Improvements

**Last Updated**: 2024-12-18

Azlin now provides robust concurrent audit logging and user-friendly Azure error messages through two new core modules.

## Overview

This document explains two critical improvements to azlin's reliability and user experience:

1. **File Lock Manager** - Eliminates false "AUDIT LOG TAMPERING" warnings during concurrent operations
2. **Resource Conflict Error Handler** - Transforms cryptic Azure errors into clear, actionable guidance

## Contents

- [Why These Improvements Matter](#why-these-improvements-matter)
- [File Lock Manager](#file-lock-manager)
- [Resource Conflict Error Handler](#resource-conflict-error-handler)
- [For Contributors](#for-contributors)
- [Troubleshooting](#troubleshooting)

## Why These Improvements Matter

### Problem 1: False Tampering Warnings

When multiple azlin commands ran concurrently (common in CI/CD pipelines or when provisioning multiple VMs), users saw alarming warnings:

```
WARNING: Potential audit log tampering detected
Expected hash: abc123..., Found: def456...
```

These warnings were **false alarms** caused by race conditions when multiple processes wrote to the audit log simultaneously. The warnings damaged user trust and caused unnecessary investigation.

### Problem 2: Cryptic Azure Errors

Azure resource conflicts produced unhelpful error messages:

```
ERROR: (ResourceExists) The resource already exists
Code: ResourceExists
Message: The resource already exists
```

Users had to manually parse JSON, search documentation, and figure out which resource conflicted and how to resolve it.

## File Lock Manager

### What It Does

The File Lock Manager provides **atomic file locking** for the audit logger. When multiple azlin processes run concurrently, each process waits its turn to write to the audit log, preventing race conditions.

### How It Works

```python
from azlin.file_lock_manager import FileLockManager

# Acquire exclusive lock before writing
with FileLockManager("/path/to/audit.log", timeout=5.0) as lock:
    # Only this process can write
    audit_file.write(entry)
    # Lock automatically released
```

**Cross-platform support:**
- **Unix/macOS/Linux**: Uses `fcntl.flock()` for whole-file advisory locks
- **Windows**: Uses `msvcrt.locking()` for mandatory file locks

**Lock acquisition:**
- Default timeout: 5 seconds
- Exponential backoff in `acquire()`: starts at 0.1s, doubles each retry (0.1s → 0.2s → 0.4s → 0.8s → 1.6s)
- Automatic cleanup on exception or context exit

**Concurrency:**
- Tested with 10+ concurrent processes
- Each process waits its turn (no data corruption)
- Failed lock acquisition raises `TimeoutError` with clear message

### User Benefits

**Before:** False tampering warnings during concurrent operations

```bash
# Terminal 1
azlin vm create dev-vm-1 &

# Terminal 2
azlin vm create dev-vm-2 &

# Output (BEFORE FIX):
WARNING: Potential audit log tampering detected
```

**After:** Silent concurrent operation (no warnings)

```bash
# Terminal 1
azlin vm create dev-vm-1 &

# Terminal 2
azlin vm create dev-vm-2 &

# Output (AFTER FIX):
# Both commands complete successfully
# Audit log contains correct sequential entries
# No tampering warnings
```

### Configuration

The file lock manager uses sensible defaults:

- **Timeout**: 5 seconds (configurable via constructor)
- **Backoff**: Exponential starting at 0.1 seconds
- **Platform detection**: Automatic (no user configuration needed)

To customize timeout:

```python
# For long-running operations, increase timeout
with FileLockManager(path, timeout=10.0) as lock:
    # 10 second timeout instead of default 5
    write_large_audit_entry()
```

## Resource Conflict Error Handler

### What It Does

The Resource Conflict Error Handler detects Azure resource conflicts and transforms them into **clear, actionable messages** with specific commands to resolve the issue.

### How It Works

```python
from azlin.resource_conflict_error_handler import ResourceConflictErrorHandler

handler = ResourceConflictErrorHandler()

try:
    # Azure operation that might conflict
    create_resource_group("my-rg", "eastus")
except Exception as e:
    if handler.is_resource_conflict(e):
        # Transform into user-friendly message
        friendly_msg = handler.format_error_message(e)
        print(friendly_msg)
```

**Detection:**
- Recognizes `ResourceExistsError` and `ConflictError` exceptions
- Parses JSON and plain text Azure CLI errors
- Extracts resource name, type, location, and resource group

**Error transformation:**
- Identifies conflicting resource details
- Suggests specific resolution commands
- Preserves full error details in debug logs

### User Benefits

**Before:** Cryptic Azure error messages

```bash
azlin vm create my-vm --resource-group my-rg --location eastus

# Output (BEFORE FIX):
ERROR: (ResourceExists) The resource already exists
Code: ResourceExists
Message: The resource already exists
```

**After:** Clear guidance with resolution commands

```bash
azlin vm create my-vm --resource-group my-rg --location eastus

# Output (AFTER FIX):
ERROR: Resource 'my-rg' already exists in location 'eastus'

A resource group with this name already exists.

To resolve:
  # Use existing resource group:
  azlin vm create my-vm --resource-group my-rg

  # Or delete existing resource group first:
  az group delete --name my-rg --yes

  # Or choose a different name:
  azlin vm create my-vm --resource-group my-rg-2
```

### Supported Conflict Types

The handler detects and formats errors for:

1. **Resource Group Conflicts**
   - Extracts: Name, location
   - Suggests: Use existing, delete, or rename

2. **Virtual Machine Conflicts**
   - Extracts: Name, resource group
   - Suggests: Use different name or delete existing

3. **Storage Account Conflicts**
   - Extracts: Name, location (globally unique requirement)
   - Suggests: Choose different name (storage accounts are global)

4. **Network Resource Conflicts**
   - Extracts: Name, type (VNet, NSG, NIC), resource group
   - Suggests: Use existing or choose different name

### Error Message Format

All formatted errors follow this structure:

```
ERROR: Resource '<name>' already exists in location '<location>'

<Explanation of what this means>

To resolve:
  # Option 1: <command>
  # Option 2: <command>
  # Option 3: <command>
```

## For Contributors

### File Lock Manager Implementation

**Location**: `src/azlin/file_lock_manager.py`

**Key design decisions:**

0. **QuotaErrorHandler pattern** - Follows same structure as azlin's quota error handling (detect, extract, format)
1. **Context manager pattern** - Ensures locks are always released
2. **Platform abstraction** - Single API works on all platforms
3. **Exponential backoff** - Reduces contention under high concurrency
4. **Configurable timeout** - Prevents indefinite blocking
5. **Standard library only** - No external dependencies (fcntl/msvcrt are standard library)
6. **Separate, self-contained bricks** - Each module is independent and regeneratable

**Extending the lock manager:**

```python
class FileLockManager:
    def __init__(self, filepath: Path, timeout: float = 5.0):
        self.filepath = filepath
        self.timeout = timeout
        self.platform = self._detect_platform()

    def _detect_platform(self) -> str:
        """Detect OS and return locking mechanism"""
        if sys.platform == "win32":
            return "windows"
        else:
            return "unix"

    def acquire(self) -> bool:
        """Acquire lock with exponential backoff"""
        # Implementation uses fcntl (Unix) or msvcrt (Windows)
        pass
```

**Testing concurrent access:**

```python
def test_concurrent_file_locks():
    """Verify 10 processes can safely lock same file"""
    import multiprocessing
    from pathlib import Path

    test_file = Path("test.log")
    test_file.write_text("")  # Start with empty file

    def write_with_lock(process_id):
        with FileLockManager(test_file) as lock:
            # Only one process at a time
            existing = test_file.read_text()
            test_file.write_text(existing + f"Entry {process_id}\n")
            time.sleep(0.1)  # Simulate work
            return process_id

    with multiprocessing.Pool(10) as pool:
        results = pool.map(write_with_lock, range(10))

    # Verify all processes succeeded
    assert len(results) == 10

    # Verify all entries written sequentially (no corruption)
    entries = test_file.read_text().strip().split("\n")
    assert len(entries) == 10  # All 10 entries present
    for i in range(10):
        assert f"Entry {i}" in entries  # Each entry exists
```

### Resource Conflict Error Handler Implementation

**Location**: `src/azlin/resource_conflict_error_handler.py`

**Key design decisions:**

1. **Flexible parsing** - Handles both JSON and plain text errors
2. **Resource type detection** - Identifies resource type from error
3. **Actionable suggestions** - Provides specific commands, not generic advice
4. **Debug preservation** - Full error details logged at debug level

**Adding support for new Azure error types:**

```python
class ResourceConflictErrorHandler:
    def _extract_resource_details(self, error: Exception) -> dict:
        """Extract resource information from error"""
        details = {
            "name": None,
            "type": None,
            "location": None,
            "resource_group": None,
        }

        # Try JSON parsing first
        if hasattr(error, "error") and hasattr(error.error, "message"):
            details.update(self._parse_json_error(error.error.message))

        # Fall back to string parsing
        else:
            details.update(self._parse_string_error(str(error)))

        return details

    def _format_for_resource_type(self, resource_type: str, details: dict) -> str:
        """Format error message based on resource type"""
        formatters = {
            "resource_group": self._format_resource_group_error,
            "virtual_machine": self._format_vm_error,
            "storage_account": self._format_storage_error,
            "network": self._format_network_error,
        }

        formatter = formatters.get(resource_type, self._format_generic_error)
        return formatter(details)
```

**Example: Adding support for Key Vault conflicts**

```python
def _format_key_vault_error(self, details: dict) -> str:
    """Format Key Vault conflict error"""
    name = details.get("name", "unknown")
    location = details.get("location", "unknown")

    return f"""ERROR: Key Vault '{name}' already exists in location '{location}'

Key Vault names are globally unique across all Azure subscriptions.

To resolve:
  # Use a different Key Vault name:
  azlin vm create my-vm --key-vault {name}-2

  # Or delete the existing Key Vault:
  az keyvault delete --name {name}
  az keyvault purge --name {name}  # Required for soft-deleted vaults
"""
```

### Integration Points

Both modules integrate with azlin's core error handling:

**Audit logger integration:**

```python
class AuditLogger:
    def write_entry(self, entry: dict):
        """Write audit entry with file locking"""
        from azlin.file_lock_manager import FileLockManager

        # Acquire lock and open file for writing
        with FileLockManager(self.audit_file_path) as lock:
            # Only this process can write - file handle is exclusive
            with open(self.audit_file_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()  # Ensure data is written before lock release
```

**CLI error handling integration:**

```python
class AzlinCLI:
    def handle_command_error(self, error: Exception):
        """Handle errors with friendly formatting"""
        from azlin.resource_conflict_error_handler import ResourceConflictErrorHandler

        handler = ResourceConflictErrorHandler()

        if handler.is_resource_conflict(error):
            print(handler.format_error_message(error))
        else:
            # Fall back to default error handling
            print(f"ERROR: {str(error)}")
```

**VMProvisioner integration:**

```python
class VMProvisioner:
    def provision_vm(self, vm_config: dict):
        """Provision VM with resource conflict handling"""
        from azlin.resource_conflict_error_handler import ResourceConflictErrorHandler

        handler = ResourceConflictErrorHandler()

        try:
            # Attempt VM provisioning
            result = self._create_vm_resources(vm_config)
            return result
        except Exception as e:
            if handler.is_resource_conflict(e):
                # Transform Azure error into actionable guidance
                friendly_msg = handler.format_error_message(e)
                raise VMProvisioningError(friendly_msg) from e
            else:
                # Re-raise other errors unchanged
                raise
```

## Troubleshooting

### File Lock Timeout Errors

**Symptom**: `TimeoutError: Failed to acquire file lock after 5.0 seconds`

**Cause**: Another process holds the lock for longer than the timeout period

**Solutions:**

1. **Increase timeout for long operations:**
   ```python
   with FileLockManager(path, timeout=10.0) as lock:
       # More time for slow operations
       pass
   ```

2. **Check for hung processes:**
   ```bash
   # Find processes accessing audit log
   lsof /path/to/audit.log

   # Kill hung process if needed
   kill -9 <pid>
   ```

3. **Verify file permissions:**
   ```bash
   # Ensure audit log is writable
   ls -l /path/to/audit.log
   chmod 644 /path/to/audit.log
   ```

### Resource Conflict Detection Issues

**Symptom**: Azure conflict error not formatted as expected

**Cause**: Error format not recognized by handler

**Solutions:**

1. **Enable debug logging to see raw error:**
   ```bash
   azlin --debug vm create my-vm
   ```

2. **Report unhandled error format:**
   - Copy full error output
   - Create issue at https://github.com/rysweet/azlin/issues
   - Include Azure CLI version: `az --version`

3. **Temporary workaround:**
   - Read raw error message
   - Manually execute suggested Azure CLI commands

### Platform-Specific Lock Issues

**Windows**: `msvcrt module not found`

**Solution**: Update Python installation (msvcrt is standard library)

**macOS/Linux**: `fcntl module not found`

**Solution**: Update Python installation (fcntl is standard library)

**WSL**: Locks not working across Windows and Linux

**Explanation**: File locks don't cross filesystem boundaries. Run azlin entirely within WSL or entirely on Windows, not mixed.

---

## Related Documentation

- [Architecture](../ARCHITECTURE.md) - Overall system design
- [AI Agent Guide](../AI_AGENT_GUIDE.md) - Development patterns
- [Testing Strategy](../testing/test_strategy.md) - How these modules are tested

---

**Issues**: [#490](https://github.com/rysweet/azlin/issues/490) - Original bug report and design
