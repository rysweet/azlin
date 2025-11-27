# Troubleshooting Connection Issues

Comprehensive guide to diagnosing and resolving connection problems with azlin's automatic behaviors.

## Quick Diagnosis

Start here to identify your issue quickly:

```bash
# Run connection with debug logging
azlin --debug connect my-vm 2>&1 | tee debug.log
```

Look for these indicators in the output:

| Symptom | Likely Cause | Jump to Section |
|---------|--------------|-----------------|
| "Failed to sync SSH key" | Auto-sync issue | [Auto-Sync Issues](#auto-sync-issues) |
| "Auto-discovery failed" | Resource group discovery issue | [Resource Group Discovery Issues](#resource-group-discovery-issues) |
| "Permission denied (publickey)" | Key mismatch or SSH config | [SSH Authentication Issues](#ssh-authentication-issues) |
| "VM not found" | Wrong resource group or VM deleted | [VM Not Found](#vm-not-found) |
| "Timeout" | Network or Azure service issue | [Timeout Issues](#timeout-issues) |
| "Permission denied" (Azure) | RBAC permissions missing | [Permission Issues](#permission-issues) |

## Auto-Sync Issues

Problems with automatic SSH key synchronization.

### Issue: Auto-Sync Failed - VM Agent Not Responding

**Symptoms:**
```
Warning: Failed to sync SSH key to VM (VM Agent not responding)
Connection may fail if VM has different key.
Attempting connection...
```

**Root Causes:**
1. VM is booting (VM Agent not ready yet)
2. VM Agent crashed or disabled
3. Network connectivity to VM Agent endpoint

**Diagnosis Steps:**

1. Check VM power state:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query "instanceView.statuses[?starts_with(code, 'PowerState/')].displayStatus" -o tsv
   ```

   Expected: `VM running`

2. Check VM Agent status:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query "instanceView.vmAgent.statuses" -o json
   ```

   Expected:
   ```json
   [
     {
       "code": "ProvisioningState/succeeded",
       "level": "Info",
       "displayStatus": "Ready",
       "message": "Guest Agent is running"
     }
   ]
   ```

3. Check VM Agent version:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query "instanceView.vmAgent.vmAgentVersion" -o tsv
   ```

   If empty or very old (< 2.2.0), VM Agent may need updating.

**Solutions:**

**Solution 1: Wait for VM to finish booting**
```bash
# Wait 2 minutes for first boot
echo "Waiting for VM to boot..."
sleep 120
azlin connect my-vm
```

**Solution 2: Force SSH sync method**
```bash
azlin connect my-vm --sync-method=ssh
```

This bypasses VM Agent and uses SSH directly.

**Solution 3: Manually restart VM Agent**
```bash
# Connect via Azure Bastion or serial console, then:
sudo systemctl restart walinuxagent
```

**Solution 4: Disable auto-sync temporarily**
```bash
azlin connect my-vm --no-auto-sync-keys
# Then manually add key once connected:
echo "ssh-ed25519 AAAA..." >> ~/.ssh/authorized_keys
```

**Prevention:**
- Enable VM Agent monitoring: `az vm update --name my-vm --resource-group my-rg --set diagnosticsProfile.bootDiagnostics.enabled=true`
- Use auto-shutdown rules to minimize long-running VMs
- Consider using SSH method for fast connections: `azlin config set ssh.sync_method ssh`

---

### Issue: Auto-Sync Failed - Permission Denied

**Symptoms:**
```
Error: Failed to sync SSH key to VM (Permission denied)
You need 'Virtual Machine Contributor' role for VM run-command.
```

**Root Cause:**
Your Azure account lacks the required RBAC permission to run commands on the VM.

**Diagnosis Steps:**

1. Check your current permissions:
   ```bash
   az role assignment list \
     --assignee $(az ad signed-in-user show --query id -o tsv) \
     --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm" \
     -o table
   ```

2. Check if you have VM Contributor anywhere:
   ```bash
   az role assignment list \
     --assignee $(az ad signed-in-user show --query id -o tsv) \
     --query "[?roleDefinitionName=='Virtual Machine Contributor']" -o table
   ```

**Solutions:**

**Solution 1: Request VM Contributor role (recommended)**

Ask your Azure administrator to grant the role:
```bash
az role assignment create \
  --assignee your-email@company.com \
  --role "Virtual Machine Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm"
```

Or at resource group level (for all VMs in RG):
```bash
az role assignment create \
  --assignee your-email@company.com \
  --role "Virtual Machine Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/my-rg"
```

**Solution 2: Use SSH sync method**

If you already have SSH access:
```bash
azlin connect my-vm --sync-method=ssh
```

**Solution 3: Request custom role with minimal permissions**

Create a custom role with only `Microsoft.Compute/virtualMachines/runCommand/action`:

```json
{
  "Name": "VM Command Executor",
  "Description": "Can run commands on VMs",
  "Actions": [
    "Microsoft.Compute/virtualMachines/read",
    "Microsoft.Compute/virtualMachines/runCommand/action"
  ],
  "AssignableScopes": [
    "/subscriptions/<subscription-id>"
  ]
}
```

**Solution 4: Disable auto-sync**
```bash
azlin config set ssh.auto_sync_keys false
```

Manually manage keys going forward.

---

### Issue: Auto-Sync Timeout

**Symptoms:**
```
Warning: SSH key sync operation timed out (30 seconds)
Connection may fail if VM has different key.
Attempting connection...
```

**Root Causes:**
1. Slow Azure VM run-command API response
2. VM under heavy load (CPU/memory exhaustion)
3. Network latency to Azure region
4. Azure service degradation

**Diagnosis Steps:**

1. Check VM resource utilization:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query "instanceView.statuses[?starts_with(code, 'PowerState/')].{status:displayStatus, time:time}" -o table
   ```

2. Test Azure CLI latency:
   ```bash
   time az vm show --name my-vm --resource-group my-rg -o none
   ```

   If this takes > 5 seconds, you have network/API latency issues.

3. Check Azure service health:
   ```bash
   az rest --method get \
     --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2020-05-01" \
     --query "value[?contains(id, 'my-vm')]"
   ```

**Solutions:**

**Solution 1: Increase timeout**
```bash
azlin connect my-vm --sync-timeout=60
# Or permanently:
azlin config set ssh.sync_timeout 60
```

**Solution 2: Reduce VM load**

Connect and check load:
```bash
azlin connect my-vm --no-auto-sync-keys
# On VM:
top
htop
vmstat 1
```

Stop unnecessary processes or resize VM if undersized.

**Solution 3: Use SSH method (faster)**
```bash
azlin config set ssh.sync_method ssh
```

SSH method typically completes in <1 second vs 2-3 seconds for run-command.

**Solution 4: Check Azure status page**

Visit https://status.azure.com/ or:
```bash
az rest --method get \
  --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.ResourceHealth/events?api-version=2022-10-01&queryStartTime=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S)Z"
```

If Azure has outage, wait for resolution.

---

### Issue: Key Synced But Connection Still Fails

**Symptoms:**
```
SSH key synchronized to VM ✓
Connecting to my-vm...
Permission denied (publickey)
```

**Root Cause:**
The sync succeeded, but there's a different authentication issue.

**Diagnosis Steps:**

1. Verify key was actually added to VM:
   ```bash
   az vm run-command invoke \
     --name my-vm \
     --resource-group my-rg \
     --command-id RunShellScript \
     --scripts "cat ~/.ssh/authorized_keys"
   ```

   Check if your key is present in the output.

2. Verify you're using the correct username:
   ```bash
   azlin connect my-vm --user azureuser --debug
   ```

3. Check SSH key fingerprint matches:
   ```bash
   # Local key fingerprint
   ssh-keygen -lf ~/.ssh/azlin_key.pub

   # Key on VM (from step 1 output)
   echo "ssh-ed25519 AAAA..." | ssh-keygen -lf -
   ```

   Fingerprints should match.

4. Check SSH daemon config on VM:
   ```bash
   az vm run-command invoke \
     --name my-vm \
     --resource-group my-rg \
     --command-id RunShellScript \
     --scripts "sudo grep -E '^(PubkeyAuthentication|AuthorizedKeysFile)' /etc/ssh/sshd_config"
   ```

   Expected:
   ```
   PubkeyAuthentication yes
   AuthorizedKeysFile .ssh/authorized_keys
   ```

**Solutions:**

**Solution 1: Check username**
```bash
# Try different usernames
azlin connect my-vm --user ubuntu
azlin connect my-vm --user admin
```

**Solution 2: Fix file permissions on VM**
```bash
az vm run-command invoke \
  --name my-vm \
  --resource-group my-rg \
  --command-id RunShellScript \
  --scripts "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

**Solution 3: Check SSH logs on VM**
```bash
az vm run-command invoke \
  --name my-vm \
  --resource-group my-rg \
  --command-id RunShellScript \
  --scripts "sudo tail -50 /var/log/auth.log | grep sshd"
```

Look for error messages indicating why authentication failed.

**Solution 4: Verify Key Vault key**
```bash
# Get public key from Key Vault
az keyvault secret show \
  --vault-name my-keyvault \
  --name azlin-my-vm-key-pub \
  --query value -o tsv

# Compare to local key
cat ~/.ssh/azlin_key.pub
```

Keys should match. If not, reconnect to trigger auto-sync:
```bash
# Auto-sync fetches latest key from Key Vault and syncs to VM
azlin connect my-vm
```

---

## Resource Group Discovery Issues

Problems with automatic resource group detection.

### Issue: Auto-Discovery Failed - No VMs Found

**Symptoms:**
```
Error: Auto-discovery failed - No VMs found with identifier 'my-vm'
Use --resource-group to specify explicitly
```

**Root Causes:**
1. VM doesn't exist
2. VM not tagged with `managed-by=azlin`
3. Wrong subscription selected
4. Insufficient permissions to list VMs

**Diagnosis Steps:**

1. Verify VM exists in current subscription:
   ```bash
   az vm list --query "[?name=='my-vm']" -o table
   ```

2. Check current subscription:
   ```bash
   az account show --query "{name:name, id:id}" -o table
   ```

3. Check VM tags:
   ```bash
   az vm show --name my-vm --resource-group <rg> \
     --query "tags" -o json
   ```

   Expected: `{"managed-by": "azlin"}`

4. Check list permissions:
   ```bash
   az vm list -o none 2>&1
   ```

   If you get "Forbidden" or "Authorization failed", you lack permissions.

**Solutions:**

**Solution 1: Add managed-by tag to VM**
```bash
az vm update --name my-vm --resource-group my-rg \
  --set tags.managed-by=azlin
```

**Solution 2: Switch to correct subscription**
```bash
# List subscriptions
az account list -o table

# Switch subscription
az account set --subscription "My Subscription"
```

**Solution 3: Request Reader permissions**

Ask your administrator:
```bash
az role assignment create \
  --assignee your-email@company.com \
  --role "Reader" \
  --scope "/subscriptions/<subscription-id>"
```

**Solution 4: Use explicit resource group**
```bash
azlin connect my-vm --resource-group my-rg
```

Bypass auto-discovery entirely.

**Solution 5: Disable auto-detect globally**
```bash
azlin config set resource_group.auto_detect false
azlin config set default_resource_group my-rg
```

---

### Issue: Auto-Discovery Failed - Multiple Matches

**Symptoms:**
```
Multiple VMs found with identifier 'my-vm':
  1. my-vm (rg-dev) - Session: dev
  2. my-vm (rg-prod) - Session: prod
Select VM [1-2]:
```

**Root Cause:**
You have multiple VMs with the same name (or same session name) in different resource groups.

**Diagnosis Steps:**

1. List all VMs with that name:
   ```bash
   az vm list --query "[?name=='my-vm'].{name:name, rg:resourceGroup, session:tags.\"azlin-session\"}" -o table
   ```

2. Check session tags:
   ```bash
   az vm list --query "[?tags.\"azlin-session\"=='my-vm'].{name:name, rg:resourceGroup}" -o table
   ```

**Solutions:**

**Solution 1: Use session name instead of VM name**
```bash
# Connect by unique session name
azlin connect dev      # Connects to my-vm in rg-dev
azlin connect prod     # Connects to my-vm in rg-prod
```

**Solution 2: Specify resource group explicitly**
```bash
azlin connect my-vm --resource-group rg-prod
```

**Solution 3: Rename sessions to be unique**
```bash
az vm update --name my-vm --resource-group rg-dev \
  --set tags.azlin-session=my-vm-dev

az vm update --name my-vm --resource-group rg-prod \
  --set tags.azlin-session=my-vm-prod
```

Now:
```bash
azlin connect my-vm-dev    # Unambiguous
azlin connect my-vm-prod   # Unambiguous
```

**Solution 4: Select VM from prompt and let azlin cache**

When prompted:
```
Multiple VMs found with identifier 'my-vm':
  1. my-vm (rg-dev) - Session: dev
  2. my-vm (rg-prod) - Session: prod
Select VM [1-2]: 2
```

Your choice is cached for 15 minutes. Subsequent connections use `rg-prod` automatically.

---

### Issue: Auto-Discovery Timeout

**Symptoms:**
```
Warning: Resource group discovery timed out (30 seconds)
Falling back to default resource group 'my-rg'
```

**Root Causes:**
1. Large Azure subscription (hundreds/thousands of VMs)
2. Slow network to Azure
3. Azure API throttling
4. Azure service degradation

**Diagnosis Steps:**

1. Test Azure CLI latency:
   ```bash
   time az vm list -o none
   ```

   If this takes > 10 seconds, you have a slow query issue.

2. Check number of VMs in subscription:
   ```bash
   az vm list --query "length(@)"
   ```

   If > 500 VMs, queries will be slow.

3. Check Azure throttling headers:
   ```bash
   az vm list --debug 2>&1 | grep -i "x-ms-ratelimit"
   ```

**Solutions:**

**Solution 1: Increase query timeout**
```bash
azlin connect my-vm --query-timeout=60
# Or permanently:
azlin config set resource_group.query_timeout 60
```

**Solution 2: Use cache aggressively**
```bash
# Increase cache TTL to 1 hour
azlin config set resource_group.cache_ttl 3600
```

**Solution 3: Disable auto-detect for large subscriptions**
```bash
azlin config set resource_group.auto_detect false
azlin config set default_resource_group my-rg
```

Always specify `--resource-group` or rely on default.

---

### Issue: Cache Corruption

**Symptoms:**
```
Warning: Resource group cache corrupted, rebuilding...
```

**Root Cause:**
The cache file (`~/.azlin/cache/rg_cache.json`) is malformed.

**Diagnosis Steps:**

1. Validate cache JSON:
   ```bash
   cat ~/.azlin/cache/rg_cache.json | jq empty
   ```

   If error, JSON is invalid.

2. Check cache file permissions:
   ```bash
   ls -la ~/.azlin/cache/rg_cache.json
   ```

   Expected: `-rw-------` (0600)

**Solutions:**

**Solution 1: Delete and rebuild cache**
```bash
rm ~/.azlin/cache/rg_cache.json
azlin connect my-vm  # Rebuilds cache automatically
```

**Solution 2: Fix permissions**
```bash
chmod 600 ~/.azlin/cache/rg_cache.json
```

**Solution 3: Manually recreate cache directory**
```bash
rm -rf ~/.azlin/cache
mkdir -p ~/.azlin/cache
chmod 700 ~/.azlin/cache
```

**Prevention:**
- Don't manually edit cache files
- Don't run azlin as root (creates permission issues)
- Use `azlin cache` commands instead of direct file manipulation

---

## SSH Authentication Issues

Problems with SSH key authentication (beyond auto-sync).

### Issue: Permission Denied (Publickey)

**Symptoms:**
```
Permission denied (publickey)
```

**Diagnosis Steps:**

1. Test SSH connection directly:
   ```bash
   ssh -i ~/.ssh/azlin_key -v azureuser@<vm-ip>
   ```

   Look for these in verbose output:
   ```
   debug1: Offering public key: ~/.ssh/azlin_key ED25519 SHA256:...
   debug1: Server accepts key: ~/.ssh/azlin_key ED25519 SHA256:...
   debug1: Authentication succeeded (publickey)
   ```

2. Check local key permissions:
   ```bash
   ls -la ~/.ssh/azlin_key
   ```

   Must be `-rw-------` (0600) or SSH rejects it.

3. Verify Key Vault key matches local key:
   ```bash
   # Key Vault public key
   az keyvault secret show \
     --vault-name my-vault \
     --name azlin-my-vm-key-pub \
     --query value -o tsv | ssh-keygen -lf -

   # Local public key
   ssh-keygen -lf ~/.ssh/azlin_key.pub
   ```

   Fingerprints should match.

**Solutions:**

**Solution 1: Fix local key permissions**
```bash
chmod 600 ~/.ssh/azlin_key
chmod 644 ~/.ssh/azlin_key.pub
```

**Solution 2: Reconnect to trigger auto-sync**
```bash
# Auto-sync automatically fetches latest key from Key Vault
azlin connect my-vm
```

**Solution 3: Generate new key pair**
```bash
# Generate new key
ssh-keygen -t ed25519 -f ~/.ssh/azlin_key -N ""

# Upload to Key Vault
az keyvault secret set \
  --vault-name my-vault \
  --name azlin-my-vm-key \
  --file ~/.ssh/azlin_key

az keyvault secret set \
  --vault-name my-vault \
  --name azlin-my-vm-key-pub \
  --file ~/.ssh/azlin_key.pub

# Sync to VM
azlin connect my-vm
```

---

## VM Not Found

The VM cannot be located.

### Issue: VM Not Found in Resource Group

**Symptoms:**
```
Error: VM 'my-vm' not found in resource group 'my-rg'
```

**Diagnosis Steps:**

1. Verify VM exists:
   ```bash
   az vm list --query "[?name=='my-vm']" -o table
   ```

2. Check if VM moved to different resource group:
   ```bash
   az vm list --query "[?name=='my-vm'].resourceGroup" -o tsv
   ```

3. Check if VM was deleted:
   ```bash
   az monitor activity-log list \
     --resource-group my-rg \
     --query "[?contains(resourceId, 'my-vm') && operationName.value=='Microsoft.Compute/virtualMachines/delete']" \
     -o table
   ```

**Solutions:**

**Solution 1: Clear cache and retry (auto-detect finds new RG)**
```bash
rm ~/.azlin/cache/rg_cache.json
azlin connect my-vm
```

**Solution 2: Use correct resource group**
```bash
# Find correct RG
az vm list --query "[?name=='my-vm'].resourceGroup" -o tsv

# Connect with correct RG
azlin connect my-vm --resource-group <correct-rg>
```

**Solution 3: Update config file**
```bash
azlin config set default_resource_group <correct-rg>
```

---

## Timeout Issues

Connection or operation timeouts.

### Issue: Connection Timeout

**Symptoms:**
```
Error: Connection timeout after 60 seconds
```

**Diagnosis Steps:**

1. Check VM is running:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query "instanceView.statuses[?starts_with(code, 'PowerState/')]" -o table
   ```

2. Check network connectivity:
   ```bash
   # Get VM IP
   VM_IP=$(az vm show --name my-vm --resource-group my-rg \
     --query "privateIps" -o tsv)

   # Test connectivity
   ping -c 3 $VM_IP
   nc -zv $VM_IP 22
   ```

3. Check NSG rules:
   ```bash
   az network nsg list \
     --resource-group my-rg \
     --query "[].securityRules[?destinationPortRange=='22']" -o table
   ```

**Solutions:**

**Solution 1: Start the VM**
```bash
az vm start --name my-vm --resource-group my-rg
```

**Solution 2: Add SSH NSG rule**
```bash
az network nsg rule create \
  --resource-group my-rg \
  --nsg-name my-nsg \
  --name Allow-SSH \
  --priority 1000 \
  --source-address-prefixes '*' \
  --destination-port-ranges 22 \
  --access Allow \
  --protocol Tcp
```

**Solution 3: Use Azure Bastion**
```bash
azlin connect my-vm --bastion
```

---

## Permission Issues

Azure RBAC permission problems.

### Issue: Insufficient Permissions

**Symptoms:**
```
Error: Permission denied - You don't have authorization to perform action...
```

**Diagnosis Steps:**

1. Check your current roles:
   ```bash
   az role assignment list \
     --assignee $(az ad signed-in-user show --query id -o tsv) \
     --all -o table
   ```

2. Check required permissions for operation:
   ```bash
   # For VM run-command
   # Required: Microsoft.Compute/virtualMachines/runCommand/action

   # For listing VMs
   # Required: Microsoft.Compute/virtualMachines/read
   ```

**Solutions:**

**Solution 1: Request appropriate role**

Request from your administrator:
```bash
# For full VM management
az role assignment create \
  --assignee your-email@company.com \
  --role "Virtual Machine Contributor" \
  --scope "/subscriptions/<sub-id>"

# Or just read access
az role assignment create \
  --assignee your-email@company.com \
  --role "Reader" \
  --scope "/subscriptions/<sub-id>"
```

---

## Advanced Debugging

### Enable Full Debug Logging

```bash
azlin --debug connect my-vm 2>&1 | tee full-debug.log
```

This captures:
- Azure CLI commands and responses
- Key Vault queries
- Resource group discovery queries
- SSH connection attempts
- Cache operations

### Check Audit Log

```bash
cat ~/.azlin/logs/audit.log | jq .
```

Look for patterns:
- Frequent sync failures
- Specific VMs causing issues
- Timing patterns (certain times of day)

### Network Diagnostics

```bash
# Test Azure API latency
time az vm show --name my-vm --resource-group my-rg -o none

# Test Key Vault latency
time az keyvault secret show --vault-name my-vault --name my-secret -o none

# Test VM Agent latency
time az vm run-command invoke \
  --name my-vm \
  --resource-group my-rg \
  --command-id RunShellScript \
  --scripts "echo test" -o none
```

## Getting Help

If you've tried all troubleshooting steps:

1. Collect diagnostics manually:
   ```bash
   # Create a diagnostics directory
   mkdir -p azlin-diagnostics

   # Collect debug logs
   cp ~/.azlin/logs/audit.log azlin-diagnostics/ 2>/dev/null || echo "No audit log"

   # Collect current configuration (remove sensitive values)
   cp ~/.azlin/config.toml azlin-diagnostics/config.toml 2>/dev/null || echo "No config"

   # Collect system information
   echo "=== Environment ===" > azlin-diagnostics/env.txt
   az --version >> azlin-diagnostics/env.txt
   python3 --version >> azlin-diagnostics/env.txt
   uname -a >> azlin-diagnostics/env.txt

   # Collect cache state
   cp -r ~/.azlin/cache azlin-diagnostics/ 2>/dev/null || echo "No cache"

   # Create archive
   tar -czf azlin-diagnostics.tar.gz azlin-diagnostics/
   ```

   This collects:
   - Audit logs
   - Configuration files
   - System versions
   - Cache state

2. Open a GitHub issue:
   - Go to https://github.com/rysweet/azlin/issues/419
   - Attach `azlin-diagnostics.tar.gz`
   - Describe what you tried

3. Join the discussion:
   - https://github.com/rysweet/azlin/discussions

## Related Documentation

- [Auto-Sync SSH Keys](../features/auto-sync-keys.md) - Feature guide
- [Auto-Detect Resource Group](../features/auto-detect-rg.md) - Feature guide
- [Configuration Reference](../reference/config-default-behaviors.md) - All configuration options

## Feedback

Found a bug or have a feature request? [Open an issue on GitHub](https://github.com/rysweet/azlin/issues/419).

Have questions? [Start a discussion](https://github.com/rysweet/azlin/discussions).
