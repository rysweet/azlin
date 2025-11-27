# Auto-Sync SSH Keys

Automatically synchronize SSH keys from Azure Key Vault to your VMs, eliminating manual key management and connection failures.

## What is Auto-Sync Keys?

Auto-sync keys is an azlin feature that automatically ensures your VM has the correct SSH public key from Key Vault before every connection attempt. When you run `azlin connect`, azlin:

1. Retrieves the VM-specific SSH key from Azure Key Vault (the source of truth)
2. Checks if the public key exists in the VM's `~/.ssh/authorized_keys` file
3. Appends the key to the VM if missing
4. Proceeds with the SSH connection

This eliminates the common problem where Key Vault has the correct key, but the VM has a different or outdated key, causing connection failures.

## Why Would I Use It?

Auto-sync keys solves several real-world problems:

### Problem 1: Key Vault/VM Mismatch
You store your SSH keys in Key Vault, but somehow the VM has a different key in its `authorized_keys` file. Your connection fails with "Permission denied (publickey)".

**Without auto-sync**: You manually SSH into the VM (if you can) and append the Key Vault key to `authorized_keys`.

**With auto-sync**: azlin automatically appends the Key Vault key before connecting. Connection succeeds.

### Problem 2: First-Time Connections
You create a new VM with one key, then store a different key in Key Vault. Now the keys don't match.

**Without auto-sync**: Connection fails. You debug for 30 minutes before realizing the key mismatch.

**With auto-sync**: azlin syncs the Key Vault key automatically. Connection works on first try.

### Problem 3: Key Rotation
Your security team rotates SSH keys regularly. You update Key Vault, but forget to update the VM.

**Without auto-sync**: All connections fail until you manually update each VM.

**With auto-sync**: azlin keeps VMs synchronized automatically.

## How Does It Work?

### The Sync Process

When you run `azlin connect my-vm`, here's what happens behind the scenes:

```
1. Fetch SSH key from Key Vault
   └─▶ Query: az keyvault secret show --name azlin-my-vm-key

2. Check if key exists on VM
   └─▶ Run: grep -Fq "<public-key>" ~/.ssh/authorized_keys

3. If key missing: Append it
   └─▶ Run: echo "<public-key>" >> ~/.ssh/authorized_keys

4. Connect via SSH
   └─▶ ssh -i ~/.ssh/azlin_key azureuser@my-vm
```

### Sync Methods

azlin uses two methods to sync keys, automatically choosing the best one:

#### Method 1: Azure VM Run Command (Primary)

The default method uses Azure's `az vm run-command` API to append the key:

```bash
az vm run-command invoke \
  --name my-vm \
  --resource-group my-rg \
  --command-id RunShellScript \
  --scripts "echo '<public-key>' >> ~/.ssh/authorized_keys"
```

**Advantages:**
- Works without an existing SSH connection
- Reliable across network configurations
- Handles first-boot scenarios

**Requirements:**
- VM Agent must be running (enabled by default on Azure VMs)
- You need VM Contributor permissions

**Performance:** Adds 2-3 seconds to first connection only

#### Method 2: SSH (Fallback)

If VM Agent is unavailable, azlin falls back to SSH:

```bash
ssh azureuser@my-vm "echo '<public-key>' >> ~/.ssh/authorized_keys"
```

**When used:**
- VM Agent not responding
- VM run-command permissions denied
- SSH connection already established

**Performance:** Less than 1 second

### Security Guarantees

Auto-sync keys is designed with security first:

1. **Append-Only**: Keys are always appended (`>>` operator), never replaced (`>` operator). This preserves any existing keys on the VM.

2. **No Private Key Exposure**: Only the public key is transmitted to the VM. Your private key never leaves your local machine.

3. **Audit Logging**: Every sync operation is logged to `~/.azlin/logs/key_sync_audit.log` with timestamp, VM name, and user.

4. **Idempotent**: Running the sync multiple times is safe. If the key already exists, no changes are made.

5. **Fail-Safe**: If sync fails (VM not running, timeout, permissions), azlin logs a warning but continues with the connection attempt. The feature never blocks your work.

## Examples

### Basic Usage

Connect to a VM with auto-sync enabled (default):

```bash
azlin connect my-vm
```

Output:
```
Fetching SSH key from Key Vault... ✓
Auto-syncing key to VM... ✓
SSH key synchronized to VM
Connecting to my-vm...
Connected!
```

If the key was already present:

```bash
azlin connect my-vm
```

Output:
```
Fetching SSH key from Key Vault... ✓
Checking key on VM... ✓
SSH key already present on VM
Connecting to my-vm...
Connected!
```

### Seeing It in Action

Enable debug logging to see detailed sync information:

```bash
azlin --debug connect my-vm
```

Output:
```
DEBUG: Loading configuration from ~/.azlin/config.toml
DEBUG: Feature auto_sync_keys=true
INFO: Fetching SSH key from Key Vault...
DEBUG: Retrieved key from vault: azlin-my-vm-key
INFO: Auto-syncing SSH key to VM...
DEBUG: Using sync method: run-command
DEBUG: Checking if key exists on VM...
DEBUG: Key not found in authorized_keys
INFO: Appending key to VM's authorized_keys...
DEBUG: Running az vm run-command invoke --name my-vm ...
INFO: SSH key synchronized to VM (2.4 seconds)
INFO: Connecting to my-vm via SSH...
Connected!
```

### First Connection After Key Change

You updated the Key Vault key and now connect:

```bash
azlin connect my-vm
```

Output:
```
Fetching SSH key from Key Vault... ✓
Auto-syncing key to VM... ✓
SSH key synchronized to VM
Connecting to my-vm...
Connected!
```

Check the audit log to verify:

```bash
cat ~/.azlin/logs/key_sync_audit.log | tail -1
```

Output:
```json
{
  "timestamp": "2025-11-26T14:32:10Z",
  "vm_name": "my-vm",
  "resource_group": "my-rg",
  "synced": true,
  "method": "run-command",
  "user": "username"
}
```

### Disabling Auto-Sync for One Connection

If you need to disable auto-sync for a specific connection:

```bash
azlin connect my-vm --no-auto-sync-keys
```

Output:
```
Fetching SSH key from Key Vault... ✓
Skipping auto-sync (disabled via --no-auto-sync-keys)
Connecting to my-vm...
Connected!
```

### Forcing SSH Sync Method

Force the SSH fallback method instead of VM run-command:

```bash
azlin connect my-vm --sync-method=ssh
```

Output:
```
Fetching SSH key from Key Vault... ✓
Auto-syncing key via SSH... ✓
SSH key synchronized to VM
Connecting to my-vm...
Connected!
```

## Configuration Options

### Enable/Disable Globally

Enable auto-sync (default):

```bash
azlin config set ssh.auto_sync_keys true
```

Disable auto-sync globally:

```bash
azlin config set ssh.auto_sync_keys false
```

View current setting:

```bash
azlin config get ssh.auto_sync_keys
```

### Adjust Timeout

Change the sync operation timeout (default: 30 seconds):

```bash
azlin config set ssh.sync_timeout 60
```

### Force Sync Method

Choose the sync method explicitly:

```bash
# Automatic (default - tries run-command, falls back to SSH)
azlin config set ssh.sync_method auto

# Always use run-command (fail if unavailable)
azlin config set ssh.sync_method run-command

# Always use SSH
azlin config set ssh.sync_method ssh

# Skip sync entirely
azlin config set ssh.sync_method skip
```

### Configuration File

Edit `~/.azlin/config.toml` directly:

```toml
[ssh]
auto_sync_keys = true        # Enable auto-sync
sync_timeout = 30            # Timeout in seconds
sync_method = "auto"         # auto, run-command, ssh, skip
```

### CLI Flags Reference

| Flag | Description | Example |
|------|-------------|---------|
| `--no-auto-sync-keys` | Disable auto-sync for this connection | `azlin connect vm --no-auto-sync-keys` |
| `--sync-method=METHOD` | Force specific sync method | `azlin connect vm --sync-method=ssh` |
| `--sync-timeout=SEC` | Override sync timeout | `azlin connect vm --sync-timeout=60` |
| `--dry-run` | Check only, make no changes | `azlin connect vm --dry-run` |

## Troubleshooting

### Sync Failed: VM Agent Not Responding

**Error:**
```
Warning: Failed to sync SSH key to VM (VM Agent not responding)
Connection may fail if VM has different key.
Attempting connection...
```

**Cause:** The Azure VM Agent is not running or not responding.

**Solutions:**

1. Check VM Agent status:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query "instanceView.vmAgent.statuses"
   ```

2. Wait for VM to finish booting (VM Agent starts automatically):
   ```bash
   # Wait 2 minutes for first boot, then retry
   sleep 120
   azlin connect my-vm
   ```

3. Force SSH sync method:
   ```bash
   azlin connect my-vm --sync-method=ssh
   ```

4. Disable auto-sync and manually add key:
   ```bash
   azlin connect my-vm --no-auto-sync-keys
   # Then manually append key on VM:
   echo "<public-key>" >> ~/.ssh/authorized_keys
   ```

### Sync Failed: Permission Denied

**Error:**
```
Error: Failed to sync SSH key to VM (Permission denied)
You need 'Virtual Machine Contributor' role for VM run-command.
```

**Cause:** Your Azure account lacks permissions to run commands on the VM.

**Solutions:**

1. Request VM Contributor role:
   ```bash
   # Ask your Azure admin to grant this role:
   az role assignment create \
     --assignee your-email@company.com \
     --role "Virtual Machine Contributor" \
     --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<vm>"
   ```

2. Use SSH fallback (requires existing SSH access):
   ```bash
   azlin connect my-vm --sync-method=ssh
   ```

3. Disable auto-sync:
   ```bash
   azlin config set ssh.auto_sync_keys false
   ```

### Sync Timeout

**Error:**
```
Warning: SSH key sync operation timed out (30 seconds)
Connection may fail if VM has different key.
Attempting connection...
```

**Cause:** Azure VM run-command took longer than expected (network latency, VM under load).

**Solutions:**

1. Increase timeout:
   ```bash
   azlin connect my-vm --sync-timeout=60
   ```

2. Retry the connection:
   ```bash
   azlin connect my-vm
   # Sync is idempotent - safe to retry
   ```

3. Check Azure service health:
   ```bash
   az monitor service-health list-events
   ```

### Connection Still Fails After Sync

**Error:**
```
SSH key synchronized to VM ✓
Connecting to my-vm...
Permission denied (publickey)
```

**Cause:** The sync succeeded, but there's a different issue (wrong username, VM firewall, SSH daemon config).

**Solutions:**

1. Verify the key was actually added:
   ```bash
   az vm run-command invoke \
     --name my-vm \
     --resource-group my-rg \
     --command-id RunShellScript \
     --scripts "cat ~/.ssh/authorized_keys"
   ```

2. Check SSH username:
   ```bash
   # Default is 'azureuser'
   azlin connect my-vm --user azureuser
   ```

3. Check VM firewall rules:
   ```bash
   az vm show \
     --name my-vm \
     --resource-group my-rg \
     --query "networkProfile.networkInterfaces[0].id" -o tsv
   ```

4. Examine SSH daemon logs on VM:
   ```bash
   az vm run-command invoke \
     --name my-vm \
     --resource-group my-rg \
     --command-id RunShellScript \
     --scripts "sudo tail -50 /var/log/auth.log | grep sshd"
   ```

### Key Appended Multiple Times

**Problem:** You notice duplicate keys in `authorized_keys` after multiple connections.

**Cause:** This should not happen (sync is idempotent), but if it does:

**Solutions:**

1. Check the audit log to see if syncs are happening repeatedly:
   ```bash
   cat ~/.azlin/logs/key_sync_audit.log | grep my-vm
   ```

2. File a bug report:
   ```bash
   # Include this information:
   azlin --version
   cat ~/.azlin/config.toml
   cat ~/.azlin/logs/key_sync_audit.log
   ```

3. Manually clean up duplicates on VM:
   ```bash
   az vm run-command invoke \
     --name my-vm \
     --resource-group my-rg \
     --command-id RunShellScript \
     --scripts "sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys"
   ```

## Frequently Asked Questions

### Does auto-sync replace my existing keys?

No. Auto-sync always uses the append operator (`>>`) and never the replace operator (`>`). All existing keys in your `authorized_keys` file are preserved.

### What if I have custom keys on the VM?

They are safe. Auto-sync adds the Key Vault key without touching existing keys. You can have multiple keys in `authorized_keys` (Key Vault key, personal keys, CI/CD keys, etc.).

### Does auto-sync work with Azure Bastion?

Yes. When connecting through Bastion, azlin still syncs the key to the VM using Azure VM run-command, which works regardless of network configuration.

### Can I disable auto-sync for specific VMs?

Not currently. The setting applies globally or per-connection (via `--no-auto-sync-keys` flag). This is a planned feature for future releases.

### What permissions do I need?

For VM run-command method:
- `Virtual Machine Contributor` role on the VM
- `Reader` role on the resource group

For SSH fallback method:
- Existing SSH access to the VM

### Does auto-sync work on Windows VMs?

No. Auto-sync is designed for Linux VMs with OpenSSH. Windows VMs use a different authentication mechanism.

### How long does auto-sync add to connection time?

- **First connection**: 2-3 seconds (one-time sync)
- **Subsequent connections**: ~100ms (key check only, no sync needed)

### Where is the audit log stored?

`~/.azlin/logs/key_sync_audit.log`

Each entry logs: timestamp, VM name, resource group, sync result, method, and username.

### Can I sync keys without connecting?

Not directly, but you can use dry-run mode to verify:

```bash
azlin connect my-vm --dry-run
```

Or manually trigger the sync operation (requires direct access to azlin Python API).

### What happens if Key Vault is unavailable?

If azlin cannot fetch the key from Key Vault, auto-sync is skipped and the connection proceeds with your local key file. You'll see:

```
Warning: Could not fetch key from Key Vault (service unavailable)
Skipping auto-sync
Connecting with local key...
```

## Advanced Topics

### Audit Log Analysis

Analyze sync patterns:

```bash
# Count syncs per VM
cat ~/.azlin/logs/key_sync_audit.log | \
  jq -r '.vm_name' | sort | uniq -c

# Find failed syncs
cat ~/.azlin/logs/key_sync_audit.log | \
  jq 'select(.synced == false)'

# Average sync duration
cat ~/.azlin/logs/key_sync_audit.log | \
  jq -r '.duration_ms' | awk '{sum+=$1; count++} END {print sum/count}'
```

### Custom Sync Scripts

For advanced use cases, you can extend the sync behavior by editing the generated bash script (advanced users only):

1. Export sync script template:
   ```bash
   azlin config get-sync-script > custom_sync.sh
   ```

2. Edit the script to add custom logic (e.g., SELinux contexts, custom permissions)

3. Use the custom script:
   ```bash
   azlin connect my-vm --sync-script=custom_sync.sh
   ```

Note: Custom sync scripts are not officially supported. Use at your own risk.

### Performance Tuning

For environments with many VMs, reduce sync overhead:

1. Disable sync for VMs you manage manually:
   ```bash
   azlin connect managed-vm --no-auto-sync-keys
   ```

2. Use SSH method for faster syncs (if SSH access available):
   ```bash
   azlin config set ssh.sync_method ssh
   ```

## Related Documentation

- [Auto-Detect Resource Groups](./auto-detect-rg.md) - Automatic resource group discovery
- [Configuration Reference](../reference/config-default-behaviors.md) - Complete configuration options
- [Troubleshooting Connection Issues](../how-to/troubleshoot-connection-issues.md) - Comprehensive troubleshooting guide
- [SSH Key Management](../how-to/manage-ssh-keys.md) - Managing SSH keys in Key Vault

## Feedback

Found a bug or have a feature request? [Open an issue on GitHub](https://github.com/rysweet/azlin/issues/419).

Have questions? [Start a discussion](https://github.com/rysweet/azlin/discussions).
