# Azure Waagent SSH Key Management Limitation

## Issue Summary

Azure's Linux Agent (waagent) continuously overwrites SSH `authorized_keys` file, making it impossible to maintain custom SSH keys for extended operations after VM initialization.

## Timeline of Discovery

### Initial Problem
- **Symptom**: SSH works for cloud-init status checks and initial operations, but fails with exit code 255 (Permission denied) during NFS mount operations
- **Pattern**: SSH succeeds, then fails after 30-60 seconds, then succeeds briefly, then fails again

### Root Cause Investigation

#### 1. Cloud-Init SSH Key Overwriting (20:05:23 → 20:09:53)
```
2025-10-19 20:05:23 - Writing to /home/azureuser/.ssh/authorized_keys - wb: [600] 101 bytes  # Correct key
2025-10-19 20:09:53 - Writing to /home/azureuser/.ssh/authorized_keys - wb: [600] 0 bytes   # Overwritten!
```

**Module responsible**: `ssh_authkey_fingerprints` (cloud-init final stage)
- Runs after cloud-init's `ssh_authorized_keys` directive
- Overwrites keys with content from Azure metadata service (which is empty)
- Cannot be disabled via `cloud_final_modules` configuration

#### 2. Continuous Waagent SSH Management
Even after:
- ✅ Adding SSH keys via cloud-init `ssh_authorized_keys` directive
- ✅ Disabling `ssh_authkey_fingerprints` module in cloud_final_modules
- ✅ Restoring keys via Azure run-command before NFS operations

**Waagent continues to overwrite keys within 10-30 seconds of any restoration attempt.**

## Attempted Fixes

### Fix #1: Cloud-Init ssh_authorized_keys Directive ❌
**Approach**: Add SSH keys explicitly in cloud-init YAML
```yaml
ssh_authorized_keys:
  - ssh-ed25519 AAAA...
```

**Result**: Keys written correctly but overwritten 4 minutes later by `ssh_authkey_fingerprints` module

### Fix #2: Disable ssh_authkey_fingerprints Module ❌
**Approach**: Exclude module from `cloud_final_modules` list
```yaml
cloud_final_modules:
  - package-update-upgrade-install
  - fan
  # ... other modules ...
  # ssh-authkey-fingerprints INTENTIONALLY OMITTED
```

**Result**: Module still ran despite exclusion (cloud-init merges configs, doesn't replace)

### Fix #3: Restore Keys via runcmd ❌
**Approach**: Add SSH key restoration commands at end of runcmd
```yaml
runcmd:
  - # ... other commands ...
  - echo 'ssh-ed25519 AAAA...' > /home/azureuser/.ssh/authorized_keys
```

**Result**: runcmd executes before `ssh_authkey_fingerprints` in cloud-init stages, so keys still overwritten

### Fix #4: Azure Run-Command Restoration ⚠️
**Approach**: Use Azure's VM run-command API to restore keys without SSH
```bash
az vm run-command invoke --scripts "
mkdir -p /home/azureuser/.ssh
echo 'ssh-ed25519 AAAA...' > /home/azureuser/.ssh/authorized_keys
chown -R azureuser:azureuser /home/azureuser/.ssh
chmod 600 /home/azureuser/.ssh/authorized_keys
"
```

**Result**: Keys restored successfully, but overwritten again within 10-30 seconds by waagent

### Fix #5: SSH Retry Logic with Exponential Backoff ⚠️
**Approach**: Retry SSH commands with delays (5s, 10s, 15s)

**Result**: Helps with transient failures but doesn't solve underlying waagent overwriting issue

## Azure Waagent Behavior

### Continuous SSH Key Management
```
waagent process runs continuously (PID 1098)
├── Fetches VM metadata from 168.63.129.16 every ~25 seconds
├── Processes VM extensions (run-command, etc.)
└── Manages SSH keys from metadata service
```

### Trigger Events for SSH Key Overwrites:
1. **Initial boot**: Cloud-init ssh_authkey_fingerprints module
2. **Extension execution**: Each run-command invocation triggers waagent activity
3. **Periodic checks**: Waagent polls metadata service regularly
4. **VM updates**: Any Azure-initiated VM configuration change

## Architectural Implications

### Why This Matters for NFS Mount Operations
1. **NFS mount requires SSH**: Need to execute mount commands on VM
2. **Mount takes time**: Network configuration, package installation, mount operations take 30-60+ seconds
3. **Keys expire mid-operation**: Waagent overwrites keys while mount is in progress
4. **Retry doesn't help**: Keys get overwritten continuously, not just once

### NFS Network Configuration Requirements
- **Service endpoint**: Subnet needs `Microsoft.Storage` service endpoint
- **Network rules**: Storage account needs `defaultAction: Deny` + explicit subnet rule
- **Timing**: These operations take 10-30 seconds, during which SSH keys may be overwritten

## Potential Solutions

### Option 1: Disable Waagent SSH Management 🔴 **RISKY**
```bash
# /etc/waagent.conf
Provisioning.MonitorHostName=n
Provisioning.RegenerateSshHostKeyPair=n
Provisioning.SshHostKeyPairType=rsa
```
**Risk**: May break other Azure functionality (extensions, diagnostics, etc.)

### Option 2: Use Azure VM Extensions for All Operations ✅ **RECOMMENDED**
- Replace SSH-based operations with VM extensions
- Use run-command extension for all post-init configuration
- Accept slower performance (run-command has ~5-10s overhead per call)

### Option 3: Pre-Configure Everything in Cloud-Init ⚠️ **LIMITED**
- Do all NFS configuration in cloud-init before waagent takes over
- Limitation: Can't configure storage network rules from inside VM
- Limitation: Can't query Azure resources for dynamic configuration

### Option 4: Separate Initialization and Operation Phases ✅ **HYBRID**
- Phase 1: VM init with cloud-init (keys work briefly)
- Phase 2: Restore keys via run-command before each operation
- Phase 3: Execute operation quickly before next overwrite
- Phase 4: Accept that long operations may fail, use run-command instead

## Current Implementation Status

### Implemented ✅
1. **NFS Network Configuration**: Service endpoints + network rules + storage account access control
2. **SSH Retry Logic**: Exponential backoff for transient failures
3. **Cloud-Init SSH Keys**: Attempted to preserve keys via cloud-init directives
4. **Run-Command Restoration**: Pre-operation SSH key restoration
5. **Post-Mount Fixes**: SSH key restoration and permissions after NFS mount

### Known Limitations ⚠️
1. **SSH keys expire mid-operation**: Waagent continuously overwrites keys
2. **Long operations fail**: NFS mount operations take too long for SSH to remain valid
3. **No perfect solution**: All approaches have trade-offs

## Recommendations

### For Short Operations (< 30 seconds)
```python
# Restore keys via run-command
restore_ssh_keys_via_runcommand(vm, key_path)
# Execute operation immediately
ssh_command(vm_ip, key, command)
```

### For Long Operations (> 30 seconds)
```python
# Use run-command extension instead of SSH
az vm run-command invoke --scripts "
# All commands here
"
```

### For NFS Mount Specifically
**Recommendation**: Execute mount operations via run-command extension rather than SSH:
```python
# Generate complete mount script
mount_script = generate_nfs_mount_script(...)
# Execute entire operation via run-command (no SSH dependency)
az vm run-command invoke --scripts mount_script
```

## References

- Azure Linux Agent: https://github.com/Azure/WALinuxAgent
- Cloud-Init Modules: https://cloudinit.readthedocs.io/en/latest/reference/modules.html
- Azure VM Extensions: https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/overview
- Azure Files NFS: https://learn.microsoft.com/en-us/azure/storage/files/storage-files-how-to-mount-nfs-shares

## Related Issues

- SSH works initially but fails after cloud-init completes: `vm_provisioning.py:545`
- NFS mount requires stable SSH connection: `nfs_mount_manager.py:69`
- Network configuration takes 10-30 seconds: `storage_manager.py:624`
- Backup and restore operations interrupted by SSH failures: `nfs_mount_manager.py:113`
