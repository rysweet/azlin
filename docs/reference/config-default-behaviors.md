# Configuration Reference: Default Behaviors

Complete reference for configuring azlin's automatic connection behaviors.

## Overview

azlin provides automatic behaviors that eliminate manual intervention when connecting to VMs:

- **Auto-Sync SSH Keys** - Automatically sync SSH keys from Key Vault to VM
- **Auto-Detect Resource Group** - Automatically discover which resource group contains your VM

These behaviors are configured in `~/.azlin/config.toml` and can be overridden via CLI flags.

## Configuration File Location

**Default Path**: `~/.azlin/config.toml`

**Custom Path** (via environment variable):
```bash
export AZLIN_CONFIG_FILE=~/custom/path/config.toml
azlin connect my-vm
```

## Complete Configuration Schema

```toml
# ~/.azlin/config.toml

# Default resource group (used when auto-detect fails or is disabled)
default_resource_group = "azlin-vms"

# Default region for VM creation
default_region = "westus2"

# Default VM size
default_vm_size = "Standard_E16as_v5"

# ============================================================================
# SSH Configuration
# ============================================================================
[ssh]

# Enable automatic key synchronization from Key Vault to VM
# Type: boolean
# Default: true
# CLI Override: --no-auto-sync-keys
auto_sync_keys = true

# Timeout for key synchronization operations (in seconds)
# Type: integer (1-300)
# Default: 30
# CLI Override: --sync-timeout=<seconds>
sync_timeout = 30

# Method for synchronizing keys to VM
# Type: string (auto, run-command, ssh, skip)
# Default: "auto"
# CLI Override: --sync-method=<method>
#
# Options:
#   - auto: Try run-command first, fall back to SSH if unavailable
#   - run-command: Always use az vm run-command (requires VM Agent)
#   - ssh: Always use SSH (requires existing SSH access)
#   - skip: Skip key sync entirely
sync_method = "auto"

# Default SSH key path
# Type: string (file path)
# Default: "~/.ssh/azlin_key"
# CLI Override: --ssh-key=<path>
key_path = "~/.ssh/azlin_key"

# ============================================================================
# Resource Group Discovery
# ============================================================================
[resource_group]

# Enable automatic resource group detection
# Type: boolean
# Default: true
# CLI Override: --no-auto-detect-rg or --resource-group=<explicit-rg>
auto_detect = true

# Cache TTL for resource group discoveries (in seconds)
# Type: integer (60-86400)
# Default: 900 (15 minutes)
# CLI Override: --cache-ttl=<seconds>
#
# Recommendations:
#   - 300 (5 min): Fast-changing environments
#   - 900 (15 min): Default, balances freshness and performance
#   - 3600 (1 hour): Stable environments with infrequent changes
#   - 86400 (24 hours): Very stable environments
cache_ttl = 900

# Timeout for Azure resource group queries (in seconds)
# Type: integer (10-300)
# Default: 30
# CLI Override: --query-timeout=<seconds>
query_timeout = 30

# Fall back to default_resource_group if discovery fails
# Type: boolean
# Default: true
fallback_to_default = true

# ============================================================================
# Cache Configuration
# ============================================================================
[cache]

# Enable caching globally (resource groups, key checks, etc.)
# Type: boolean
# Default: true
enabled = true

# Cache directory location
# Type: string (directory path)
# Default: "~/.azlin/cache"
directory = "~/.azlin/cache"

# Automatically clean up old cache entries (in seconds)
# Type: integer
# Default: 3600 (1 hour)
# Note: Entries older than this are purged on startup
cleanup_interval = 3600

# ============================================================================
# Logging Configuration
# ============================================================================
[logging]

# Log level
# Type: string (DEBUG, INFO, WARNING, ERROR)
# Default: "INFO"
# CLI Override: --debug (sets to DEBUG) or --quiet (sets to WARNING)
level = "INFO"

# Enable audit logging for key synchronization operations
# Type: boolean
# Default: true
audit_enabled = true

# Audit log file location
# Type: string (file path)
# Default: "~/.azlin/logs/audit.log"
audit_file = "~/.azlin/logs/audit.log"

# Rotate audit log after this size (in megabytes)
# Type: integer
# Default: 10
audit_log_max_size_mb = 10

# Keep this many rotated audit log files
# Type: integer
# Default: 5
audit_log_backup_count = 5
```

## Configuration Options by Category

### SSH Auto-Sync Options

#### `ssh.auto_sync_keys`

**Type**: Boolean
**Default**: `true`
**Description**: Enable automatic synchronization of SSH keys from Key Vault to VM.

When enabled, azlin checks if the Key Vault public key exists in the VM's `~/.ssh/authorized_keys` file before connecting. If missing, the key is automatically appended.

**When to disable**:
- You manage VM keys manually
- You want to control exactly when keys are synced
- Your VMs don't have Azure VM Agent

**Example**:
```toml
[ssh]
auto_sync_keys = false  # Disable auto-sync globally
```

**CLI Override**:
```bash
azlin connect my-vm --no-auto-sync-keys
```

---

#### `ssh.sync_timeout`

**Type**: Integer (1-300)
**Default**: `30`
**Description**: Maximum time (in seconds) to wait for key sync operation to complete.

If the sync operation takes longer than this, azlin logs a warning and proceeds with the connection.

**When to increase**:
- Slow Azure connections
- VMs under heavy load
- Large VMs with slow VM Agent startup

**When to decrease**:
- You want faster failure feedback
- Fast, reliable Azure connections

**Example**:
```toml
[ssh]
sync_timeout = 60  # Wait up to 1 minute
```

**CLI Override**:
```bash
azlin connect my-vm --sync-timeout=60
```

---

#### `ssh.sync_method`

**Type**: String (enum)
**Default**: `"auto"`
**Valid Values**: `"auto"`, `"run-command"`, `"ssh"`, `"skip"`
**Description**: Method used to synchronize keys to VM.

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| `auto` | Try run-command, fall back to SSH | Reliable, works in most scenarios | May be slower on fallback |
| `run-command` | Always use `az vm run-command` | Works without SSH, reliable | Requires VM Agent, slower (2-3s) |
| `ssh` | Always use SSH to append key | Fast (<1s), no VM Agent needed | Requires existing SSH access |
| `skip` | Don't sync keys | No overhead | Key mismatches cause failures |

**Example**:
```toml
[ssh]
sync_method = "ssh"  # Always use SSH
```

**CLI Override**:
```bash
azlin connect my-vm --sync-method=ssh
```

---

#### `ssh.key_path`

**Type**: String (file path)
**Default**: `"~/.ssh/azlin_key"`
**Description**: Default path for SSH private key.

**Example**:
```toml
[ssh]
key_path = "~/.ssh/id_ed25519"
```

**CLI Override**:
```bash
azlin connect my-vm --ssh-key ~/.ssh/custom_key
```

---

### Resource Group Discovery Options

#### `resource_group.auto_detect`

**Type**: Boolean
**Default**: `true`
**Description**: Enable automatic discovery of resource groups by querying Azure.

When enabled and you don't specify `--resource-group`, azlin searches all resource groups for your VM.

**When to disable**:
- You always know the resource group
- You want to avoid Azure queries (performance)
- Your Azure account lacks List VM permissions

**Example**:
```toml
[resource_group]
auto_detect = false  # Require explicit --resource-group
```

**CLI Override**:
```bash
# Disable for one connection
azlin connect my-vm --no-auto-detect-rg --resource-group rg-prod

# Provide explicit RG (auto-detect skipped)
azlin connect my-vm --resource-group rg-prod
```

---

#### `resource_group.cache_ttl`

**Type**: Integer (60-86400)
**Default**: `900` (15 minutes)
**Description**: How long (in seconds) to cache resource group discoveries.

Cached entries are automatically invalidated if a connection fails due to "VM not found".

**Recommendations by environment**:
```toml
# Fast-changing dev environment (VMs created/deleted frequently)
cache_ttl = 300  # 5 minutes

# Typical environment (default)
cache_ttl = 900  # 15 minutes

# Stable production (VMs rarely move)
cache_ttl = 3600  # 1 hour

# Very stable (multi-week VM lifetimes)
cache_ttl = 86400  # 24 hours
```

**CLI Override**:
```bash
azlin connect my-vm --cache-ttl=300
```

---

#### `resource_group.query_timeout`

**Type**: Integer (10-300)
**Default**: `30`
**Description**: Maximum time (in seconds) to wait for Azure resource group query.

**When to increase**:
- Large Azure subscriptions (hundreds of VMs)
- Slow network connections to Azure
- Azure service slowdowns

**When to decrease**:
- You want fast failure feedback
- Small subscriptions with few VMs

**Example**:
```toml
[resource_group]
query_timeout = 60  # Wait up to 1 minute
```

**CLI Override**:
```bash
azlin connect my-vm --query-timeout=60
```

---

#### `resource_group.fallback_to_default`

**Type**: Boolean
**Default**: `true`
**Description**: If auto-discovery fails, fall back to `default_resource_group`.

**When to disable**:
- You want explicit failures (no fallback behavior)
- You don't have a default resource group
- You want to know when discovery fails

**Example**:
```toml
[resource_group]
fallback_to_default = false  # Fail if discovery fails
```

---

### Cache Options

#### `cache.enabled`

**Type**: Boolean
**Default**: `true`
**Description**: Enable all caching (resource groups, key checks, etc.).

**When to disable**:
- Debugging cache-related issues
- You want fresh data on every operation
- Disk space is extremely limited

**Example**:
```toml
[cache]
enabled = false  # Disable all caching
```

---

#### `cache.directory`

**Type**: String (directory path)
**Default**: `"~/.azlin/cache"`
**Description**: Location for cache files.

**Example**:
```toml
[cache]
directory = "~/custom/cache/location"
```

---

#### `cache.cleanup_interval`

**Type**: Integer (seconds)
**Default**: `3600` (1 hour)
**Description**: Delete cache entries older than this on startup.

Prevents cache directory from growing unbounded.

**Example**:
```toml
[cache]
cleanup_interval = 7200  # Keep entries for 2 hours
```

---

### Logging Options

#### `logging.level`

**Type**: String (enum)
**Default**: `"INFO"`
**Valid Values**: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`
**Description**: Minimum log level to display.

| Level | When to use |
|-------|-------------|
| `DEBUG` | Troubleshooting, development |
| `INFO` | Normal operation (default) |
| `WARNING` | Suppress routine messages, show only issues |
| `ERROR` | Suppress everything except errors |

**Example**:
```toml
[logging]
level = "DEBUG"
```

**CLI Override**:
```bash
azlin --debug connect my-vm    # Set to DEBUG
azlin --quiet connect my-vm    # Set to WARNING
```

---

#### `logging.audit_enabled`

**Type**: Boolean
**Default**: `true`
**Description**: Log all key sync operations to audit log file.

Audit logs include: timestamp, VM name, resource group, sync result, method, and username.

**When to disable**:
- You don't need audit trails
- Disk space is limited
- You're in a non-production environment

**Example**:
```toml
[logging]
audit_enabled = false
```

---

#### `logging.audit_file`

**Type**: String (file path)
**Default**: `"~/.azlin/logs/audit.log"`
**Description**: Location for audit log file.

**Example**:
```toml
[logging]
audit_file = "~/logs/azlin_audit.log"
```

---

#### `logging.audit_log_max_size_mb`

**Type**: Integer (megabytes)
**Default**: `10`
**Description**: Rotate audit log after it reaches this size.

**Example**:
```toml
[logging]
audit_log_max_size_mb = 50  # 50 MB before rotation
```

---

#### `logging.audit_log_backup_count`

**Type**: Integer
**Default**: `5`
**Description**: Keep this many rotated audit log files.

Example: With `backup_count = 5`, you'll have:
- `audit.log` (current)
- `audit.log.1` (previous)
- `audit.log.2`
- `audit.log.3`
- `audit.log.4`
- `audit.log.5`

Older logs are deleted automatically.

**Example**:
```toml
[logging]
audit_log_backup_count = 10  # Keep 10 rotated logs
```

---

## CLI Flags Reference

All configuration options can be overridden via CLI flags:

| Config Option | CLI Flag | Example |
|---------------|----------|---------|
| `ssh.auto_sync_keys` | `--no-auto-sync-keys` | `azlin connect vm --no-auto-sync-keys` |
| `ssh.sync_timeout` | `--sync-timeout=<sec>` | `azlin connect vm --sync-timeout=60` |
| `ssh.sync_method` | `--sync-method=<method>` | `azlin connect vm --sync-method=ssh` |
| `ssh.key_path` | `--ssh-key=<path>` | `azlin connect vm --ssh-key ~/.ssh/key` |
| `resource_group.auto_detect` | `--no-auto-detect-rg` | `azlin connect vm --no-auto-detect-rg` |
| `resource_group.cache_ttl` | `--cache-ttl=<sec>` | `azlin connect vm --cache-ttl=300` |
| `resource_group.query_timeout` | `--query-timeout=<sec>` | `azlin connect vm --query-timeout=60` |
| `default_resource_group` | `--resource-group=<rg>` | `azlin connect vm --resource-group rg-prod` |
| `logging.level` | `--debug` or `--quiet` | `azlin --debug connect vm` |
| - | `--force-rg-refresh` | `azlin connect vm --force-rg-refresh` |
| - | `--dry-run` | `azlin connect vm --dry-run` |

## Configuration Management Commands

### View Configuration

View entire configuration:
```bash
azlin config show
```

View specific setting:
```bash
azlin config get ssh.auto_sync_keys
```

### Set Configuration

Set a value:
```bash
azlin config set ssh.auto_sync_keys true
azlin config set resource_group.cache_ttl 1800
azlin config set logging.level DEBUG
```

### Reset to Defaults

Reset specific setting:
```bash
azlin config reset ssh.auto_sync_keys
```

Reset all settings:
```bash
azlin config reset --all
```

### Validate Configuration

Check configuration file for errors:
```bash
azlin config validate
```

Output:
```
Validating configuration file: ~/.azlin/config.toml
✓ Syntax valid (TOML)
✓ All required fields present
✓ All values have correct types
✓ All values within valid ranges
Configuration is valid.
```

### Export Configuration

Export current configuration (useful for backup or sharing):
```bash
azlin config export > my-azlin-config.toml
```

Import configuration:
```bash
azlin config import my-azlin-config.toml
```

## Configuration Best Practices

### Recommended Settings for Different Environments

#### Development Environment

Fast feedback, tolerate some failures:

```toml
[ssh]
auto_sync_keys = false  # Manual control in dev
sync_timeout = 15       # Fail fast

[resource_group]
auto_detect = true
cache_ttl = 300         # 5 min (fast changes)

[logging]
level = "DEBUG"         # Verbose for troubleshooting
```

#### Staging Environment

Balance between dev and prod:

```toml
[ssh]
auto_sync_keys = true
sync_timeout = 30

[resource_group]
auto_detect = true
cache_ttl = 900         # 15 min (default)

[logging]
level = "INFO"
audit_enabled = true
```

#### Production Environment

Reliability and audit trails:

```toml
[ssh]
auto_sync_keys = true
sync_timeout = 60       # Tolerate slow responses
sync_method = "auto"    # Use most reliable method

[resource_group]
auto_detect = true
cache_ttl = 3600        # 1 hour (stable VMs)
query_timeout = 60

[logging]
level = "INFO"
audit_enabled = true    # Required for compliance
audit_log_max_size_mb = 100
audit_log_backup_count = 10
```

#### Performance-Optimized

Minimize overhead:

```toml
[ssh]
auto_sync_keys = true
sync_method = "ssh"           # Faster than run-command

[resource_group]
auto_detect = true
cache_ttl = 3600              # Cache for 1 hour

[logging]
level = "WARNING"             # Minimal logging
audit_enabled = false         # Skip audit overhead
```

#### Security-Focused

Maximum audit and control:

```toml
[ssh]
auto_sync_keys = true
sync_method = "run-command"   # Most auditable (Azure logs)

[resource_group]
auto_detect = true
fallback_to_default = false   # No implicit fallbacks

[logging]
level = "INFO"
audit_enabled = true
audit_file = "/var/log/azlin/audit.log"  # Central location
audit_log_max_size_mb = 100
audit_log_backup_count = 50              # Long retention
```

## Troubleshooting Configuration

### Configuration Not Loading

**Symptom**: Changes to config file don't take effect.

**Cause**: Config file syntax error or wrong location.

**Solutions**:

1. Validate syntax:
   ```bash
   azlin config validate
   ```

2. Check config file location:
   ```bash
   azlin config path
   # Output: /Users/you/.azlin/config.toml
   ```

3. Check for typos (TOML is case-sensitive):
   ```toml
   # Wrong
   [SSH]
   Auto_Sync_Keys = True

   # Correct
   [ssh]
   auto_sync_keys = true
   ```

### Default Values Not Working

**Symptom**: azlin uses wrong defaults despite config file.

**Cause**: Config file not found, or values out of range.

**Solutions**:

1. Ensure config file exists:
   ```bash
   ls -la ~/.azlin/config.toml
   ```

2. Check value ranges:
   ```bash
   azlin config validate
   ```

3. View effective configuration:
   ```bash
   azlin config show --effective
   # Shows merged result of defaults + config file + CLI flags
   ```

## Related Documentation

- [Auto-Sync SSH Keys](../features/auto-sync-keys.md) - Feature guide for key synchronization
- [Auto-Detect Resource Group](../features/auto-detect-rg.md) - Feature guide for RG discovery
- [Troubleshooting Connection Issues](../how-to/troubleshoot-connection-issues.md) - Common problems and solutions

## Feedback

Found a bug or have a feature request? [Open an issue on GitHub](https://github.com/rysweet/azlin/issues/419).

Have questions? [Start a discussion](https://github.com/rysweet/azlin/discussions).
