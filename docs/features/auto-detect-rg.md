# Auto-Detect Resource Group

Automatically discover which resource group contains your VM, eliminating the need to specify `--resource-group` on every connection.

## What is Auto-Detect Resource Group?

Auto-detect resource group is an azlin feature that automatically finds your VM across all resource groups in your Azure subscription. When you run `azlin connect my-vm` without specifying `--resource-group`, azlin:

1. Checks its cache for a recent resource group mapping
2. If not cached, queries Azure for VMs with the matching name or session tag
3. Caches the result for future connections (15-minute TTL)
4. Uses the discovered resource group for the connection

This eliminates "VM not found" errors when VMs are moved between resource groups or when you don't remember which resource group contains a specific VM.

## Why Would I Use It?

Auto-detect resource group solves several common pain points:

### Problem 1: VM Moved to Different Resource Group

Your VM was in `rg-dev`, but your team moved it to `rg-prod`. Now your connection fails:

```bash
azlin connect my-vm --resource-group rg-dev
```

Error:
```
Error: VM 'my-vm' not found in resource group 'rg-dev'
```

**Without auto-detect**: You manually search for the VM, update your config file, and retry.

**With auto-detect**: azlin finds the VM in `rg-prod` automatically:

```bash
azlin connect my-vm
# Discovered VM 'my-vm' in resource group 'rg-prod' ✓
```

### Problem 2: Don't Remember Resource Group

You have 20 VMs across 5 resource groups. You want to connect to a specific VM but can't remember its resource group.

**Without auto-detect**: You run `az vm list` to search, then copy the resource group name.

**With auto-detect**: Just use the VM name:

```bash
azlin connect my-vm
# Auto-discovery finds the VM wherever it lives
```

### Problem 3: Session-Based Workflows

You use azlin sessions (e.g., `atg-dev`, `frontend-test`) and want to reconnect without remembering VM details.

**Without auto-detect**: You look up the VM name and resource group from your notes or config file.

**With auto-detect**: Use the session name directly:

```bash
azlin connect atg-dev
# Finds VM by azlin-session tag: "atg-dev"
```

### Problem 4: Multi-Region Deployments

You have VMs in multiple regions, each in a different resource group (`rg-eastus`, `rg-westus`, etc.).

**Without auto-detect**: You must remember or look up which region each VM is in.

**With auto-detect**: Just connect, azlin finds the right resource group:

```bash
azlin connect my-vm
# Auto-detects: my-vm is in rg-westus
```

## How Does It Work?

### Discovery Process

When you run `azlin connect my-vm` without `--resource-group`:

```
1. Check local cache (~/.azlin/cache/rg_cache.json)
   ├─▶ Cache hit (< 15 min old) → Use cached resource group
   └─▶ Cache miss or expired → Continue to step 2

2. Query Azure for VM
   ├─▶ az vm list --query "[?tags.managed-by=='azlin' && ...]"
   └─▶ Returns: [{name: "my-vm", resourceGroup: "rg-prod", ...}]

3. Cache the result
   └─▶ Save to ~/.azlin/cache/rg_cache.json (15-min TTL)

4. Use discovered resource group
   └─▶ Connect to my-vm in rg-prod
```

### Discovery Priority

azlin searches for VMs in this order:

1. **Cache lookup** (fast: <100ms)
   - Check if session name or VM name is in cache
   - Verify cache entry is not expired (< 15 minutes old)

2. **Azure tags query** (moderate: 2-3 seconds)
   - Search all VMs with `managed-by=azlin` tag
   - Match by VM name OR `azlin-session` tag
   - Cache the result for future lookups

3. **Config file fallback** (fast: <10ms)
   - Check `~/.azlin/config.toml` for explicit resource group mapping
   - Backward compatibility with older azlin configs

4. **Default resource group** (fast: <10ms)
   - Use `default_resource_group` from config file
   - Last resort if all else fails

### Azure Query Details

The discovery query looks like this:

```bash
az vm list \
  --query "[?tags.\"managed-by\"=='azlin' &&
           (name=='my-vm' || tags.\"azlin-session\"=='my-vm')].
           {name:name, resourceGroup:resourceGroup,
            sessionName:tags.\"azlin-session\"}" \
  --output json
```

Example result:

```json
[
  {
    "name": "azlin-atg-dev-20241120",
    "resourceGroup": "rg-eastus",
    "sessionName": "atg-dev"
  }
]
```

From this, azlin knows `atg-dev` session is in resource group `rg-eastus`.

## Caching Strategy

### Cache File Structure

Cache is stored at `~/.azlin/cache/rg_cache.json`:

```json
{
  "version": 1,
  "entries": {
    "atg-dev": {
      "vm_name": "azlin-atg-dev-20241120",
      "resource_group": "rg-eastus",
      "session_name": "atg-dev",
      "timestamp": 1732628400,
      "ttl": 900
    },
    "my-vm": {
      "vm_name": "my-vm",
      "resource_group": "rg-prod",
      "session_name": null,
      "timestamp": 1732628500,
      "ttl": 900
    }
  }
}
```

### Cache Behavior

**Cache Hit (Fresh Entry)**

```bash
azlin connect atg-dev
# Cache hit: using cached resource group 'rg-eastus' (<1 minute old)
# Connecting to azlin-atg-dev-20241120...
```

**Performance**: ~100ms (no Azure query needed)

**Cache Miss (No Entry)**

```bash
azlin connect new-vm
# Resource group not cached, querying Azure...
# Discovered VM 'new-vm' in resource group 'rg-dev'
# Caching result for future connections...
# Connecting to new-vm...
```

**Performance**: 2-3 seconds (Azure query + cache write)

**Cache Expired (> 15 minutes old)**

```bash
azlin connect atg-dev
# Cache entry expired (17 minutes old), refreshing...
# Discovered VM 'azlin-atg-dev-20241120' in resource group 'rg-eastus'
# Cache updated
# Connecting to azlin-atg-dev-20241120...
```

**Performance**: 2-3 seconds (Azure query + cache update)

### Cache Invalidation

The cache is automatically invalidated when:

1. **Connection fails** - If azlin connects to a VM using cached resource group but the VM is not found, the cache entry is deleted and discovery runs again:

   ```bash
   azlin connect my-vm
   # Using cached resource group 'old-rg'...
   # Error: VM not found in 'old-rg'
   # Cache invalidated, retrying with fresh discovery...
   # Discovered VM 'my-vm' in resource group 'new-rg'
   # Connecting to my-vm...
   ```

2. **Manual invalidation** - You can force cache refresh:

   ```bash
   azlin connect my-vm --force-rg-refresh
   ```

3. **TTL expiration** - Cache entries expire after 15 minutes (configurable)

4. **Cache cleanup** - On startup, azlin purges entries older than 1 hour

### Manual Cache Management

View cache contents:

```bash
cat ~/.azlin/cache/rg_cache.json | jq .
```

Clear entire cache:

```bash
rm ~/.azlin/cache/rg_cache.json
```

## Examples

### Basic Usage

Connect without specifying resource group:

```bash
azlin connect my-vm
```

Output (cache hit):
```
Using cached resource group 'rg-prod' (source: cache) ✓
Connecting to my-vm...
Connected!
```

Output (cache miss):
```
Resource group not specified, attempting auto-discovery...
Querying Azure for VM 'my-vm'...
Discovered VM 'my-vm' in resource group 'rg-prod' (source: tags) ✓
Caching result for future connections...
Connecting to my-vm...
Connected!
```

### Session-Based Connection

Connect using session name:

```bash
azlin connect atg-dev
```

Output:
```
Resource group not specified, attempting auto-discovery...
Discovered VM 'azlin-atg-dev-20241120' in resource group 'rg-eastus' ✓
Session: atg-dev
Connecting to azlin-atg-dev-20241120...
Connected!
```

The cache now contains:

```json
{
  "atg-dev": {
    "vm_name": "azlin-atg-dev-20241120",
    "resource_group": "rg-eastus",
    "session_name": "atg-dev"
  }
}
```

Next connection is instant:

```bash
azlin connect atg-dev
# Cache hit: using cached resource group 'rg-eastus' (<1 minute old) ✓
```

### VM Moved to Different Resource Group

Initial connection (VM in `rg-dev`):

```bash
azlin connect my-vm
# Discovered VM 'my-vm' in resource group 'rg-dev'
```

VM is moved to `rg-prod`. Next connection:

```bash
azlin connect my-vm
# Using cached resource group 'rg-dev'...
# Error: VM 'my-vm' not found in resource group 'rg-dev'
# Cache invalidated, retrying discovery...
# Discovered VM 'my-vm' in resource group 'rg-prod' ✓
# Cache updated
# Connecting to my-vm...
```

The cache is now updated with the new resource group.

### Force Cache Refresh

Bypass cache and force fresh discovery:

```bash
azlin connect my-vm --force-rg-refresh
```

Output:
```
Forcing fresh resource group discovery...
Querying Azure for VM 'my-vm'...
Discovered VM 'my-vm' in resource group 'rg-prod'
Cache updated
Connecting to my-vm...
```

### Disable Auto-Detect for One Connection

Provide resource group explicitly:

```bash
azlin connect my-vm --resource-group rg-prod
```

Output:
```
Using specified resource group 'rg-prod'
Skipping auto-discovery
Connecting to my-vm...
```

The cache is still updated for future auto-detect connections.

### Multiple VMs with Same Name

If you have VMs with the same name in different resource groups:

```bash
azlin connect my-vm
```

Output:
```
Resource group not specified, attempting auto-discovery...
Multiple VMs found with name 'my-vm':
  1. my-vm (rg-dev) - Session: dev
  2. my-vm (rg-prod) - Session: prod
  3. my-vm (rg-staging) - Session: staging
Select VM [1-3]: 2
```

You select #2, and azlin caches your choice:

```json
{
  "my-vm": {
    "vm_name": "my-vm",
    "resource_group": "rg-prod",
    "session_name": "prod"
  }
}
```

Future connections use `rg-prod` automatically until you clear the cache or the entry expires.

## Configuration Options

### Enable/Disable Globally

Enable auto-detect (default):

```bash
azlin config set resource_group.auto_detect true
```

Disable auto-detect globally:

```bash
azlin config set resource_group.auto_detect false
```

When disabled, you must specify `--resource-group` on every connection.

### Adjust Cache TTL

Change cache expiration time (default: 900 seconds = 15 minutes):

```bash
# Cache for 1 hour
azlin config set resource_group.cache_ttl 3600

# Cache for 5 minutes (aggressive invalidation)
azlin config set resource_group.cache_ttl 300

# Cache for 24 hours (slow-changing environments)
azlin config set resource_group.cache_ttl 86400
```

### Adjust Query Timeout

Change Azure query timeout (default: 30 seconds):

```bash
azlin config set resource_group.query_timeout 60
```

### Fallback to Default Resource Group

When auto-detect fails, use default resource group:

```bash
azlin config set resource_group.fallback_to_default true
azlin config set default_resource_group rg-fallback
```

Now if discovery fails:

```bash
azlin connect unknown-vm
# Auto-discovery failed
# Falling back to default resource group 'rg-fallback'
# Connecting to unknown-vm in rg-fallback...
```

### Configuration File

Edit `~/.azlin/config.toml` directly:

```toml
[resource_group]
auto_detect = true           # Enable auto-detection
cache_ttl = 900              # Cache TTL in seconds (15 min)
query_timeout = 30           # Azure query timeout
fallback_to_default = true   # Use default RG if discovery fails

default_resource_group = "rg-default"  # Fallback RG
```

### CLI Flags Reference

| Flag | Description | Example |
|------|-------------|---------|
| `--resource-group=RG` | Explicitly specify resource group (skips auto-detect) | `azlin connect vm --resource-group rg-prod` |
| `--no-auto-detect-rg` | Disable auto-detect for this connection | `azlin connect vm --no-auto-detect-rg --resource-group rg` |
| `--force-rg-refresh` | Force cache refresh (ignore cached value) | `azlin connect vm --force-rg-refresh` |

## Troubleshooting

### Discovery Failed: No VMs Found

**Error:**
```
Error: Auto-discovery failed - No VMs found with identifier 'my-vm'
Use --resource-group to specify explicitly
```

**Cause:** No VMs match the name or session tag in your Azure subscription.

**Solutions:**

1. List all azlin-managed VMs:
   ```bash
   azlin list
   # Shows all VMs with managed-by=azlin tag
   ```

2. Check if VM exists in Azure:
   ```bash
   az vm list --query "[?name=='my-vm']" -o table
   ```

3. Verify VM has `managed-by=azlin` tag:
   ```bash
   az vm show --name my-vm --resource-group rg-prod \
     --query "tags.\"managed-by\"" -o tsv
   ```

   If missing, add the tag:
   ```bash
   az vm update --name my-vm --resource-group rg-prod \
     --set tags.managed-by=azlin
   ```

4. Specify resource group explicitly:
   ```bash
   azlin connect my-vm --resource-group rg-prod
   ```

### Discovery Failed: Multiple Matches

**Error:**
```
Multiple VMs found with name 'my-vm':
  1. my-vm (rg-dev) - Session: dev
  2. my-vm (rg-prod) - Session: prod
Select VM [1-2]:
```

**Cause:** You have multiple VMs with the same name in different resource groups.

**Solutions:**

1. Select the correct VM from the list (azlin will cache your choice)

2. Use session name instead of VM name:
   ```bash
   azlin connect dev     # Connects to VM with session tag "dev"
   azlin connect prod    # Connects to VM with session tag "prod"
   ```

3. Specify resource group explicitly:
   ```bash
   azlin connect my-vm --resource-group rg-dev
   ```

4. Rename VMs to be unique:
   ```bash
   az vm update --name my-vm --resource-group rg-dev \
     --set tags.azlin-session=my-vm-dev
   ```

### Discovery Timeout

**Error:**
```
Warning: Resource group discovery timed out (30 seconds)
Falling back to default resource group 'rg-default'
```

**Cause:** Azure query took too long (slow network, large subscription).

**Solutions:**

1. Increase query timeout:
   ```bash
   azlin config set resource_group.query_timeout 60
   azlin connect my-vm
   ```

2. Check Azure service status:
   ```bash
   az monitor service-health list-events
   ```

3. Use cached result if available:
   ```bash
   # Wait a moment for timeout, then retry
   # Cache from previous successful connection will be used
   azlin connect my-vm
   ```

4. Specify resource group to skip query:
   ```bash
   azlin connect my-vm --resource-group rg-prod
   ```

### Cache Corruption

**Error:**
```
Warning: Resource group cache corrupted, rebuilding...
```

**Cause:** The cache file is malformed or has invalid JSON.

**Solutions:**

1. Delete corrupted cache (azlin rebuilds automatically):
   ```bash
   rm ~/.azlin/cache/rg_cache.json
   azlin connect my-vm
   ```

2. Verify cache permissions:
   ```bash
   ls -la ~/.azlin/cache/rg_cache.json
   # Should be -rw------- (0600)
   ```

3. Manually recreate cache directory:
   ```bash
   mkdir -p ~/.azlin/cache
   chmod 700 ~/.azlin/cache
   ```

### Insufficient Permissions

**Error:**
```
Error: Permission denied - Cannot list VMs in subscription
You need 'Reader' role at subscription or resource group level
```

**Cause:** Your Azure account lacks permissions to list VMs.

**Solutions:**

1. Request Reader role:
   ```bash
   # Ask your Azure admin to grant this role:
   az role assignment create \
     --assignee your-email@company.com \
     --role "Reader" \
     --scope "/subscriptions/<subscription-id>"
   ```

2. Use explicit resource group (requires Reader role only on that RG):
   ```bash
   azlin connect my-vm --resource-group rg-prod
   ```

3. Disable auto-detect and use config file:
   ```bash
   azlin config set resource_group.auto_detect false
   azlin config set default_resource_group rg-prod
   ```

### Stale Cache After VM Deletion

**Problem:** VM was deleted, but cache still references it.

**Symptom:**
```bash
azlin connect old-vm
# Using cached resource group 'rg-old'...
# Error: VM 'old-vm' not found
# Cache invalidated (VM not found)
# Auto-discovery failed - No VMs found
```

**Solution:** Cache is automatically invalidated. No action needed.

To manually clear the cache entry:

```bash
rm ~/.azlin/cache/rg_cache.json
```

## Frequently Asked Questions

### Does auto-detect work across multiple subscriptions?

Not currently. Auto-detect searches only the active Azure subscription. If you have VMs in multiple subscriptions, switch subscriptions first:

```bash
az account set --subscription "My Other Subscription"
azlin connect my-vm
```

Multi-subscription support is planned for a future release.

### What if I rename a resource group?

Cache entries reference resource groups by name. If you rename a resource group in Azure:

1. Existing cache entries become stale
2. Next connection attempt fails (VM not found in old RG)
3. Cache is invalidated automatically
4. Fresh discovery finds VM in new RG

No manual intervention required.

### Can I use auto-detect with IP addresses?

No. Auto-detect only works with VM names or session names. If you specify an IP address, azlin skips auto-detect:

```bash
azlin connect 10.0.1.5 --resource-group rg-prod
```

### How does auto-detect handle Azure regions?

Resource groups can contain VMs in different regions. Auto-detect doesn't care about regions - it searches all resource groups and returns the RG containing your VM, regardless of region.

### What if my VM doesn't have the managed-by tag?

Auto-detect won't find it by default. Add the tag manually:

```bash
az vm update --name my-vm --resource-group rg-prod \
  --set tags.managed-by=azlin
```

Or use `--resource-group` explicitly:

```bash
azlin connect my-vm --resource-group rg-prod
```

### Does auto-detect respect resource group permissions?

Yes. If you have Reader access to only specific resource groups, auto-detect searches only those groups. VMs in other resource groups won't be discovered.

### How much does auto-detect cost?

Auto-detect uses the Azure CLI `az vm list` command, which is a read-only operation. Azure does not charge for read operations like this. The only cost is your time (2-3 seconds for the query).

### Can I see what the Azure query returns?

Yes, run with debug logging:

```bash
azlin --debug connect my-vm
```

Output includes:
```
DEBUG: Running Azure query: az vm list --query "..."
DEBUG: Query returned 3 VMs: [{"name": "my-vm", ...}]
DEBUG: Selected VM: my-vm in rg-prod
```

### Is the cache encrypted?

No. The cache file contains only non-sensitive information (VM names, resource group names, timestamps). It has 0600 permissions (owner read/write only) to prevent tampering.

### What happens if two users share the same machine?

Each user has their own cache file under their home directory (`~/.azlin/cache/rg_cache.json`). Caches are isolated by user account.

## Advanced Topics

### Cache Performance Analysis

Measure cache hit rate:

```bash
cat ~/.azlin/cache/rg_cache.json | \
  jq '.entries | length'
# Shows number of cached entries

# Check freshness of entries
cat ~/.azlin/cache/rg_cache.json | \
  jq '.entries | to_entries[] |
      {key: .key, age_seconds: (now - .value.timestamp)}'
```

### Monitoring Discovery Performance

Track discovery latency over time:

```bash
azlin --debug connect my-vm 2>&1 | \
  grep "Discovery completed" | \
  awk '{print $NF}'
# Prints discovery time in milliseconds
```

Create a monitoring script:

```bash
#!/bin/bash
for vm in vm1 vm2 vm3; do
  start=$(date +%s%N)
  azlin connect $vm --dry-run >/dev/null 2>&1
  end=$(date +%s%N)
  echo "$vm: $((($end - $start) / 1000000))ms"
done
```

## Related Documentation

- [Auto-Sync SSH Keys](./auto-sync-keys.md) - Automatic key synchronization
- [Configuration Reference](../reference/config-default-behaviors.md) - Complete configuration options
- [Troubleshooting Connection Issues](../how-to/troubleshoot-connection-issues.md) - Comprehensive troubleshooting guide
- [Managing Multiple VMs](../how-to/manage-multiple-vms.md) - Working with many VMs efficiently

## Feedback

Found a bug or have a feature request? [Open an issue on GitHub](https://github.com/rysweet/azlin/issues/419).

Have questions? [Start a discussion](https://github.com/rysweet/azlin/discussions).
