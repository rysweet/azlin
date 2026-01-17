# Troubleshooting Timeout Issues

## Symptoms

- `azlin list` command times out
- Error: "VM list operation timed out"
- Command takes longer than 30 seconds

## Common Causes

### 1. Large Deployments
If you have 100+ VMs, listing operations may take time even with caching.

**Solution:**
```bash
# List VMs in specific resource group
azlin list --rg your-specific-rg

# Use caching (enabled by default)
azlin list
```

### 2. Network Latency
High latency to Azure regions can cause timeouts.

**Check:**
```bash
# Test Azure CLI connectivity
az account show
az vm list --output table
```

**Solution:**
- Use Azure Cloud Shell for better connectivity
- Check your network/VPN connection
- Try from a different network

### 3. Azure API Performance
Occasionally Azure APIs are slow.

**Solution:**
```bash
# Retry after a few minutes
azlin list

# Check Azure status: https://status.azure.com
```

### 4. No Caching
Without cache, every list operation makes fresh API calls.

**Check cache status:**
```bash
ls -la ~/.azlin/vm_list_cache.json
```

**Solution:**
- Ensure cache file exists and is readable
- Cache automatically updates every 5 minutes (mutable data) / 24 hours (immutable data)

## Timeout Values

As of PR #557, azlin uses these timeouts:

| Operation | Timeout | Reason |
|-----------|---------|--------|
| VM list | 30s | Handles large deployments |
| Public IP list | 30s | Batch retrieval of IPs |
| Resource group list | 30s | Cross-RG operations |

## Still Having Issues?

If timeouts persist after trying the above:

1. **Report the issue**: https://github.com/rysweet/azlin/issues
2. **Include details**:
   - Number of VMs in resource group
   - Your Azure region
   - Network setup (VPN, corporate network, etc.)
   - Error message

## Related

- Issue #556: Timeout after cache PR
- PR #557: Increased timeouts to 30s
- PR #553: Cache implementation
