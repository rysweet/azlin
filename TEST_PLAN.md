# Test Plan: KeyVault SSH Key Retrieval Bug Fix

## Issue #375: SSH key generation occurs instead of KeyVault retrieval on cross-machine login

This test plan documents the required local testing before merging the fix.

## Prerequisites

1. Azure subscription with access to create VMs
2. Two different machines OR ability to simulate by deleting local SSH keys
3. Azure CLI authenticated (`az login`)
4. Azlin installed from the fix branch

## Installation for Testing

### Option 1: Install from Git Branch (Recommended)
```bash
uvx --from git+https://github.com/rysweet/azlin@fix/issue-375-keyvault-ssh-key-retrieval azlin --help
```

### Option 2: Install Locally from Worktree
```bash
cd /Users/ryan/src/azlin/worktrees/fix-issue-375-keyvault-ssh-key-retrieval
uv pip install -e .
```

## Test Scenarios

### Scenario 1: Cross-Machine Connection with Key in KeyVault ✅ (PRIMARY BUG FIX)

**Purpose**: Verify that SSH key is retrieved from KeyVault on a different machine instead of generating a new one

**Setup**:
1. On Machine A (or current state):
   ```bash
   # Create a test VM with KeyVault storage
   azlin new test-kv-vm --resource-group rg-azlin-test
   ```

2. Verify key is stored in KeyVault:
   ```bash
   # Key should be automatically stored in KeyVault during provisioning
   # You can verify by checking the KeyVault in Azure Portal
   ```

3. Simulate Machine B (delete local SSH key):
   ```bash
   # Backup the key first
   cp ~/.ssh/azlin_key ~/.ssh/azlin_key.backup
   cp ~/.ssh/azlin_key.pub ~/.ssh/azlin_key.pub.backup

   # Delete local keys
   rm ~/.ssh/azlin_key ~/.ssh/azlin_key.pub
   ```

**Test**:
```bash
# Connect to the VM (should retrieve key from KeyVault)
azlin connect test-kv-vm
```

**Expected Behavior**:
- Console output should show:
  ```
  INFO: Local SSH key not found, checking Key Vault for VM: test-kv-vm
  INFO: SSH key retrieved from Key Vault: <vault-name>
  INFO: Using SSH key retrieved from Key Vault
  ```
- SSH connection should succeed
- No "Generating new SSH key" message
- Key file should exist at `~/.ssh/azlin_key` (retrieved from vault)

**Failure Indicators** (old buggy behavior):
- Message: "Generating new SSH key for VM: test-kv-vm"
- SSH connection fails with "Permission denied (publickey)"
- Key was regenerated instead of retrieved

**Cleanup**:
```bash
# Restore original keys if needed
mv ~/.ssh/azlin_key.backup ~/.ssh/azlin_key
mv ~/.ssh/azlin_key.pub.backup ~/.ssh/azlin_key.pub

# Delete test VM
azlin destroy test-kv-vm
```

---

### Scenario 2: Connection with Existing Local Key ✅

**Purpose**: Verify that pre-existing local keys are used without checking KeyVault

**Setup**:
```bash
# Ensure local key exists
ls -la ~/.ssh/azlin_key
```

**Test**:
```bash
azlin connect test-kv-vm
```

**Expected Behavior**:
- Console output should show:
  ```
  INFO: Using existing local SSH key
  ```
- KeyVault check happens but returns False immediately (key exists locally)
- SSH connection succeeds
- No KeyVault retrieval message

---

### Scenario 3: Key Not in KeyVault - Generate Fallback ✅

**Purpose**: Verify graceful fallback to key generation when KeyVault doesn't have the key

**Setup**:
```bash
# Create VM without KeyVault (or simulate old VM)
# For testing, manually provision a VM without KeyVault storage
# OR connect to a VM that was created before KeyVault feature
```

**Test**:
```bash
# Delete local key
rm ~/.ssh/azlin_key ~/.ssh/azlin_key.pub

# Try to connect
azlin connect old-vm-without-keyvault
```

**Expected Behavior**:
- Console output should show:
  ```
  INFO: Local SSH key not found, checking Key Vault for VM: old-vm-without-keyvault
  INFO: SSH key not found in Key Vault for VM: old-vm-without-keyvault
  INFO: Generating new SSH key for VM: old-vm-without-keyvault
  ```
- New key is generated
- User is informed that VM may need updated `authorized_keys`

---

### Scenario 4: KeyVault Authentication Failure ❌

**Purpose**: Verify clear error message when Azure authentication expires

**Setup**:
```bash
# Log out of Azure
az logout
```

**Test**:
```bash
# Delete local key
rm ~/.ssh/azlin_key ~/.ssh/azlin_key.pub

# Try to connect
azlin connect test-kv-vm
```

**Expected Behavior**:
- Console output should show WARNING (not debug):
  ```
  WARNING: Could not access Key Vault: <auth error message>
  INFO: Generating new SSH key for VM: test-kv-vm
  ```
- Clear message indicating Azure login needed
- Falls back to generating new key
- User informed about potential connection failure

**Cleanup**:
```bash
# Log back in
az login
```

---

### Scenario 5: KeyVault Permissions Issue ❌

**Purpose**: Verify clear error message when user lacks KeyVault permissions

**Setup**:
- Use Azure account without "Key Vault Secrets User" role
- OR test with a KeyVault that has restricted access

**Test**:
```bash
# Delete local key
rm ~/.ssh/azlin_key ~/.ssh/azlin_key.pub

# Try to connect
azlin connect test-kv-vm
```

**Expected Behavior**:
- Console output should show WARNING with actionable guidance:
  ```
  WARNING: Could not access Key Vault: <permission error>
  INFO: Generating new SSH key for VM: test-kv-vm
  ```
- Error mentions required role or permissions
- Falls back to generating new key

---

## Verification Checklist

Before considering this fix complete, verify:

- [x] **Unit Tests Pass**: All 30 vm_connector tests pass (verified ✅)
- [x] **Pre-commit Hooks Pass**: Linting, formatting, type checking pass (verified ✅)
- [ ] **Scenario 1 Pass**: Cross-machine connection uses KeyVault key (CRITICAL)
- [ ] **Scenario 2 Pass**: Existing local key is used
- [ ] **Scenario 3 Pass**: Graceful fallback to generation when key not in vault
- [ ] **Scenario 4 Pass**: Clear error when auth fails
- [ ] **Scenario 5 Pass**: Clear error when permissions lacking
- [ ] **No Regressions**: Existing functionality still works
- [ ] **User Feedback Clear**: All INFO messages visible and helpful
- [ ] **Error Messages Actionable**: Users know what to do when errors occur

## Testing with uvx (Preferred Method)

To test the fix without installing locally:

```bash
# Test help command
uvx --from git+https://github.com/rysweet/azlin@fix/issue-375-keyvault-ssh-key-retrieval azlin --help

# Test connection
uvx --from git+https://github.com/rysweet/azlin@fix/issue-375-keyvault-ssh-key-retrieval azlin connect test-kv-vm

# Test new VM creation
uvx --from git+https://github.com/rysweet/azlin@fix/issue-375-keyvault-ssh-key-retrieval azlin new test-vm --resource-group test-rg
```

## Expected Log Output Examples

### Successful KeyVault Retrieval (Fix Working):
```
INFO: Resolving connection info for VM: test-kv-vm
INFO: Local SSH key not found, checking Key Vault for VM: test-kv-vm
INFO: SSH key retrieved from Key Vault: azlin-keyvault-abc123
INFO: Using SSH key retrieved from Key Vault
INFO: Connecting to test-kv-vm at 20.1.2.3...
```

### Using Existing Key (Optimization):
```
INFO: Resolving connection info for VM: test-kv-vm
INFO: Using existing local SSH key
INFO: Connecting to test-kv-vm at 20.1.2.3...
```

### Fallback to Generation (KeyVault Empty):
```
INFO: Resolving connection info for VM: old-vm
INFO: Local SSH key not found, checking Key Vault for VM: old-vm
INFO: SSH key not found in Key Vault for VM: old-vm
INFO: Generating new SSH key for VM: old-vm
INFO: SSH key generated successfully
INFO: Connecting to old-vm at 20.1.2.4...
```

## Success Criteria

**The bug is fixed when**:
1. Connecting from a different machine retrieves SSH key from KeyVault
2. Connection succeeds without generating a new key
3. User sees clear INFO messages about key source
4. All error scenarios provide actionable guidance
5. Backwards compatibility maintained for old VMs

## Notes

- This bug was caused by ignoring the return value of `_try_fetch_key_from_vault()` at line 209
- The fix captures the return value and only generates a new key if KeyVault retrieval failed
- Logging was upgraded from DEBUG to INFO for user visibility
- Code was simplified to eliminate duplication while preserving all requirements

## User Testing Required

Since I cannot test cross-machine scenarios directly, **you must perform Scenario 1 manually**. This is the PRIMARY bug fix verification.

Please run Scenario 1 and confirm:
1. Key is retrieved from KeyVault (not generated)
2. SSH connection succeeds
3. Log messages are clear

All other scenarios can be verified through unit tests, but real-world testing of Scenario 1 is MANDATORY per user preferences.
