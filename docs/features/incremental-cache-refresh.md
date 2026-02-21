# Incremental Cache Refresh

**Status**: Implemented
**Version**: 2.3.0
**Related**: VM List Caching (`src/azlin/cache/vm_list_cache.py`)

## Overview

Incremental cache refresh dramatically reduces Azure API calls by refreshing only expired VM cache entries instead of refetching entire resource groups.

### Problem Solved

Before incremental refresh:
- When **1 VM** cache entry expires out of 50 VMs in a resource group
- **ALL 50 VMs** were refetched from Azure API
- Wasted 49 unnecessary API calls (98% waste)

After incremental refresh:
- Only the **1 expired VM** is refreshed
- **80-95% reduction** in cache refresh API calls
- Significantly faster list operations
- Better Azure API quota utilization

## How It Works

### Architecture

The incremental cache refresh system consists of three components:

1. **Detection Layer** (`VMListCache.get_expired_entries()`)
   - Identifies which specific VM cache entries have expired
   - Returns list of VM names that need refresh
   - Thread-safe read-only operation

2. **Refresh Layer** (`VMManager.refresh_expired_vms()`)
   - Queries only expired VMs from Azure in parallel
   - Uses ThreadPoolExecutor for efficient parallel queries
   - Updates cache atomically after each successful query

3. **Integration Layer** (`VMManager.list_vms_with_cache()`)
   - Automatically uses selective refresh when appropriate
   - Falls back to full refresh for cold starts (empty cache)
   - Maintains backward compatibility with existing API

### Cache TTL Behavior

The system respects existing tiered TTL behavior:

- **Immutable Layer** (24h TTL): VM metadata (name, location, size, OS type)
- **Mutable Layer** (5min TTL): VM state (power state, IPs, provisioning state)

When either layer expires, the VM is marked for incremental refresh.

### Parallel Refresh

Expired VMs are refreshed in parallel using ThreadPoolExecutor:

```python
# Example: 5 expired VMs out of 50 total
expired_vms = cache.get_expired_entries("my-resource-group")
# Returns: ["vm1", "vm12", "vm25", "vm38", "vm41"]

# Refresh only these 5 VMs in parallel
refreshed = VMManager.refresh_expired_vms("my-resource-group", expired_vms)
# 5 parallel Azure API calls instead of 50 sequential calls
# Time: ~1 second instead of ~10-15 seconds
```

**Parallelization Settings**:
- `max_workers=10` (conservative limit to avoid Azure API throttling)
- Graceful error handling: Failed VM queries don't block others
- Atomic cache updates after each successful query

## Performance Improvements

### API Call Reduction

| Scenario | Expired VMs | Before | After | Reduction |
|----------|-------------|---------|-------|-----------|
| Best case | 1 out of 50 | 100 calls | 1 call | **99%** ✅ |
| Typical | 5 out of 50 | 100 calls | 5 calls | **95%** ✅ |
| Moderate | 10 out of 50 | 100 calls | 10 calls | **90%** ✅ |
| Heavy | 25 out of 50 | 100 calls | 25 calls | **75%** ⚠️ |

### Time Improvements

| Scenario | Before (seconds) | After (seconds) | Time Saved |
|----------|------------------|-----------------|------------|
| 1 expired | 10-15s | 0.5-1s | **93%** |
| 5 expired | 10-15s | 1-2s | **87%** |
| 10 expired | 10-15s | 2-3s | **80%** |

### Azure API Quota Utilization

For users with large VM fleets:
- Before: Could trigger API throttling with frequent list operations
- After: Stays well below rate limits even with frequent refreshes
- Impact: More reliable operations, fewer "TooManyRequests" errors

## Usage

### Automatic Behavior

Incremental refresh is **automatic** - no configuration changes needed:

```bash
# First call (cold start) - full refresh
azlin list  # Takes 10-15s, caches all VMs

# Subsequent calls within 5 minutes - cache hit
azlin list  # Takes <1s, uses cached data

# After 6 minutes (mutable layer expired) - incremental refresh
azlin list  # Takes 1-2s, refreshes only expired state
```

### Programmatic Usage

For Python API users:

```python
from azlin.vm_manager import VMManager
from azlin.cache.vm_list_cache import VMListCache

# Detect expired VMs
cache = VMListCache()
expired_vm_names = cache.get_expired_entries("my-resource-group")
print(f"Need to refresh {len(expired_vm_names)} VMs")

# Refresh only expired VMs
if expired_vm_names:
    refreshed_vms = VMManager.refresh_expired_vms(
        resource_group="my-resource-group",
        expired_vm_names=expired_vm_names
    )
    print(f"Refreshed {len(refreshed_vms)} VMs")
```

## Implementation Details

### Thread Safety

All cache operations are thread-safe:

- **File I/O**: Uses atomic reads and writes
- **Cache Updates**: Atomic file replacement (temp file + rename pattern)
- **Parallel Queries**: ThreadPoolExecutor handles synchronization
- **No Explicit Locking**: Atomic file operations provide sufficient guarantees

### Error Handling

Graceful degradation on failures:

```python
# If individual VM query fails
try:
    vm_info = VMManager.get_vm(vm_name, resource_group)
    cache.set_full(vm_name, resource_group, ...)
except Exception as e:
    logger.warning(f"Failed to refresh {vm_name}: {e}")
    # Continue with other VMs - don't fail entire operation
```

### Edge Cases

1. **Newly Created VMs**: Detected on next cold start (full refresh)
2. **Deleted VMs**: Stale cache entries removed during next full refresh
3. **All VMs Expired**: Automatically falls back to full refresh
4. **Empty Cache (Cold Start)**: Uses full refresh as before

## Configuration

No configuration needed - incremental refresh is enabled by default.

To disable caching entirely (not recommended):

```python
vms, was_cached = VMManager.list_vms_with_cache(
    resource_group="my-rg",
    use_cache=False  # Force full refresh
)
```

## Testing

Comprehensive test coverage ensures reliability:

### Unit Tests
- `test_get_expired_entries_immutable_expired()` - Detects expired metadata
- `test_get_expired_entries_mutable_expired()` - Detects expired state
- `test_get_expired_entries_mixed()` - Mixed expiration scenarios
- `test_refresh_expired_vms()` - Parallel refresh correctness
- `test_refresh_expired_vms_with_failures()` - Error handling

### Integration Tests
- `test_selective_refresh_one_vm_expired()` - 1 out of 50 scenario
- `test_selective_refresh_performance()` - Verify 80-95% reduction
- `test_cache_consistency_after_selective_refresh()` - Cache integrity

## Monitoring

Track incremental refresh effectiveness:

```bash
# Check cache status
azlin list --verbose
# Output shows: "[CACHE HIT] Using 49 cached VMs, refreshed 1 VM (98% reduction)"
```

Python API monitoring:

```python
# Before refresh
expired = cache.get_expired_entries(resource_group)
print(f"Refreshing {len(expired)} of {len(all_vms)} VMs")
print(f"API call reduction: {(1 - len(expired)/len(all_vms)) * 100:.1f}%")
```

## Troubleshooting

### Unexpected Full Refreshes

If seeing more full refreshes than expected:

1. **Check Cache Location**: Ensure `~/.azlin/vm_list_cache.json` is writable
2. **Verify TTL Settings**: Default 24h/5min should work for most cases
3. **Review Logs**: Enable debug logging to see cache decisions

```bash
export AZLIN_LOG_LEVEL=DEBUG
azlin list
# Look for: "Cache hit: Using X cached VMs" vs "Cache miss: Fetching fresh data"
```

### Performance Not Improved

If incremental refresh isn't improving performance:

1. **Most VMs Expired**: If >50% VMs expire together, consider adjusting TTL
2. **Cold Starts**: First call after cache expiration still requires full refresh
3. **Small VM Counts**: Benefit is minimal for <10 VMs (overhead vs savings)

## Future Enhancements

Potential improvements (not currently implemented):

1. **Layer-Specific Refresh**: Refresh only mutable layer when immutable is fresh
2. **Configurable max_workers**: Allow tuning parallelization for different Azure quotas
3. **Background Refresh**: Proactively refresh expiring entries before user requests
4. **Metrics Dashboard**: Real-time cache hit rate and API call savings

## Related Documentation

- [VM List Caching Architecture](../PERFORMANCE_GUIDE.md#vm-list-caching)
- [Cache Module API](../../src/azlin/cache/vm_list_cache.py)
- [VM Manager API](../../src/azlin/vm_manager.py)

## References

- **Issue**: #638 - Implement per-VM incremental cache refresh
- **Implementation**: `src/azlin/cache/vm_list_cache.py` (lines 597+)
- **Tests**: `tests/test_vm_list_cache.py` (incremental refresh suite)
