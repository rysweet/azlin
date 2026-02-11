# Troubleshooting Compound Naming

This guide helps ye resolve common issues with `hostname:session_name` compound naming.

**💡 Simplicity First**: Most issues stem from simple causes (typos, wrong VM, missing session). Check the basics before diving into complex diagnostics.

## Common Issues

### Ambiguous Session Name

**Symptom:**

```bash
azlin connect main

Error: Ambiguous session name 'main'
Found on multiple VMs:
  - myvm:main (20.12.34.56)
  - prodvm:main (20.45.67.89)
```

**Cause:** Multiple VMs have sessions with the same name.

**Solutions:**

1. **Use compound format** (recommended):
   ```bash
   azlin connect myvm:main
   ```

2. **Rename sessions for uniqueness**:
   ```bash
   azlin session myvm dev-main
   azlin session prodvm prod-main
   # Now: azlin connect dev-main (unambiguous)
   ```

3. **Use VM-specific default sessions**:
   ```bash
   azlin connect myvm  # Uses default 'azlin' session
   ```

---

### Session Not Found

**Symptom:**

```bash
azlin connect myvm:dev

Error: Session 'myvm:dev' not found
Available sessions on myvm: myvm:main, myvm:staging
```

**Causes:**

1. **Typo in session name**
   ```bash
   # Check exact session name
   azlin list | grep myvm
   # HOSTNAME    SESSION     STATUS
   # myvm        main        Running
   # myvm        staging     Running

   # Correct usage
   azlin connect myvm:staging  # Not myvm:dev
   ```

2. **Session not created yet**
   ```bash
   # Create the session first
   azlin ssh myvm --tmux-session dev
   # Now available as: myvm:dev
   ```

3. **Wrong VM hostname**
   ```bash
   # Verify hostname
   azlin list
   # Use exact hostname shown in list
   ```

---

### VM Not Found

**Symptom:**

```bash
azlin connect wrongvm:main

Error: VM 'wrongvm' not found
Available VMs: myvm, prodvm
```

**Causes:**

1. **Typo in hostname**
   ```bash
   # Check available VMs
   azlin list
   # Use exact hostname
   ```

2. **VM in different resource group**
   ```bash
   # Specify resource group
   azlin connect myvm:main --resource-group other-rg
   ```

3. **VM is stopped**
   ```bash
   # Check status
   azlin list --all

   # Start VM if stopped
   azlin start wrongvm
   ```

---

### Invalid Compound Format

**Symptom:**

```bash
azlin connect myvm:dev:test

Error: Invalid compound name format
Expected: hostname:session_name
```

**Cause:** Multiple colons in identifier.

**Solution:**

```bash
# Session names cannot contain colons
# Use hyphens or underscores instead
azlin ssh myvm --tmux-session dev-test  # ✅
azlin ssh myvm --tmux-session dev_test  # ✅
azlin ssh myvm --tmux-session dev:test  # ❌
```

---

### Connection Fails After List Shows Session

**Symptom:**

```bash
azlin list
# Shows: myvm:main

azlin connect myvm:main
# Error: Connection refused
```

**Causes:**

1. **VM recently stopped**
   ```bash
   azlin status myvm
   # If stopped: azlin start myvm
   ```

2. **Network connectivity issue**
   ```bash
   # Test connectivity
   ping $(azlin ip myvm)

   # Try with bastion if available
   azlin connect myvm:main --use-bastion
   ```

3. **SSH key issue**
   ```bash
   # Sync SSH keys
   azlin keys rotate --vm-prefix myvm
   ```

---

## Diagnostic Commands

### List All Sessions

```bash
# See all hostname:session combinations
azlin list

# Wide format (no truncation)
azlin list --wide

# Include stopped VMs
azlin list --all
```

### Verify Session Configuration

```bash
# Check config file
cat ~/.azlin/config.toml | grep -A 20 "\[sessions\]"

# Output shows mappings:
# [sessions]
# "myvm:main" = "20.12.34.56"
# "myvm:dev" = "20.12.34.56"
```

### Test Connection

```bash
# Try direct SSH (bypass azlin)
ssh azureuser@$(azlin ip myvm)

# If works: Issue is with session resolution
# If fails: Network/SSH key issue
```

---

## Understanding Resolution Order

azlin resolves identifiers in this order:

1. **Exact compound match**: `hostname:session`
2. **Unique session name**: `session` (if only one VM has it)
3. **Hostname with default session**: `hostname` (uses "azlin" session)

**Example:**

```bash
# Setup:
# myvm has sessions: main, dev
# prodvm has sessions: main, api

# These work:
azlin connect myvm:main      # Exact match
azlin connect dev            # Unique session
azlin connect prodvm:api     # Exact match

# This fails (ambiguous):
azlin connect main           # Both myvm and prodvm have "main"
```

---

## Error Message Reference

### "Ambiguous session name"

**Meaning:** Session name exists on multiple VMs.

**Fix:** Use compound format to specify which VM.

**Example:**
```bash
azlin connect myvm:main  # Instead of: azlin connect main
```

---

### "Session not found"

**Meaning:** No session with that name exists.

**Fixes:**

1. Check spelling: `azlin list`
2. Create session: `azlin ssh vm --tmux-session name`
3. Verify VM: `azlin list --all`

---

### "Invalid compound name format"

**Meaning:** Identifier has wrong format (e.g., multiple colons).

**Fix:** Use exactly one colon: `hostname:session`

**Valid:**
- `myvm:dev` ✅
- `prod-vm:api` ✅

**Invalid:**
- `myvm:dev:test` ❌
- `myvm::dev` ❌

---

### "VM not found"

**Meaning:** Hostname doesn't match any VM.

**Fixes:**

1. Verify hostname: `azlin list`
2. Check resource group: `--resource-group`
3. Start stopped VM: `azlin start hostname`

---

## Best Practices for Avoiding Issues

### 1. Use Consistent Naming

```bash
# Good: Descriptive, no colons
azlin ssh vm --tmux-session feature-auth
azlin ssh vm --tmux-session feature-api

# Bad: Generic, confusing
azlin ssh vm --tmux-session dev
azlin ssh vm --tmux-session test
```

### 2. Document Team Conventions

```bash
# Example convention:
# Format: {env}-{component}
# - dev-api, staging-api, prod-api
# - dev-web, staging-web, prod-web
```

### 3. Verify Before Scripting

```bash
# Always test manually first
azlin connect myvm:main

# Then script it
#!/bin/bash
azlin exec myvm:main "deploy.sh"
```

### 4. Use --verbose for Debugging

```bash
# See resolution details
azlin --verbose connect myvm:main

# Output shows:
# Resolving identifier: myvm:main
# Detected compound format
# hostname=myvm, session=main
# Found VM: myvm (20.12.34.56)
# Found session: main
# Connecting...
```

---

## Advanced Troubleshooting

### Session Cache Issues

If `azlin list` shows stale sessions:

```bash
# Force cache refresh
rm ~/.azlin/.cache/sessions.json

# Rebuild session list
azlin list
```

### Hostname Resolution

If hostnames not resolving:

```bash
# Check Azure VM names
az vm list --output table

# Verify config matches Azure
cat ~/.azlin/config.toml | grep -A 10 "\[vms\]"
```

### Network Debugging

```bash
# Test Azure connectivity
az account show

# Test SSH directly
ssh -v azureuser@$(azlin ip myvm)

# Check bastion availability
azlin bastion list
```

---

## Getting Help

If issues persist:

1. **Check version**:
   ```bash
   azlin --version  # Compound naming available in v2.3.0+
   ```

2. **Collect diagnostics**:
   ```bash
   azlin list --verbose > diagnostic.txt
   azlin status >> diagnostic.txt
   cat ~/.azlin/config.toml >> diagnostic.txt
   ```

3. **Ask for help**:
   - GitHub Issues: https://github.com/rysweet/azlin/issues
   - Discussions: https://github.com/rysweet/azlin/discussions

---

## See Also

- [Compound Naming Guide](../getting-started/compound-naming.md) - Basic usage
- [CLI Reference](../commands/compound-naming-reference.md) - Command details
- [Session Management](../advanced/session-management.md) - Advanced usage
- [General Troubleshooting](./index.md) - Other common issues
