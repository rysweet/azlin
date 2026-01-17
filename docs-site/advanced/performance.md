# Performance Optimization

Advanced performance features including API caching, connection pooling, and intelligent request batching.

## Overview

azlin v0.4.0 introduces significant performance improvements that make bulk operations 3x faster and reduce API calls by 50%.

**Key Features:**

- **API Caching**: Cache Azure API responses for faster operations
- **Connection Pooling**: Reuse connections for better throughput
- **Intelligent Batching**: Automatically batch similar requests
- **Parallel Execution**: Execute operations concurrently
- **Request Optimization**: Minimize API calls automatically
- **Performance Monitoring**: Track operation performance

## Performance Improvements

### v0.4.0 Performance Gains

| Operation | v0.3.x | v0.4.0 | Improvement |
|-----------|--------|--------|-------------|
| **List 100 VMs** | 12.5s | 4.2s | **3x faster** |
| **Batch start 10 VMs** | 45s | 15s | **3x faster** |
| **Deploy 5 VMs** | 8.2 min | 5.1 min | **38% faster** |
| **API calls (batch ops)** | 500 calls | 250 calls | **50% reduction** |

### Key Optimizations

1. **API Response Caching**
   - Cache VM status, region info, pricing data
   - Configurable cache TTL
   - Smart invalidation on updates

2. **Connection Pooling**
   - Reuse Azure API connections
   - Reduce connection overhead
   - Better throughput for bulk operations

3. **Intelligent Batching**
   - Automatically batch similar requests
   - Reduce API call count
   - Maintain correctness

4. **Parallel Execution**
   - Execute independent operations concurrently
   - Respect Azure API rate limits
   - Intelligent work distribution

## Configuration

### Enable Performance Features

```bash
# Enable all performance optimizations (default in v0.4.0)
azlin config set performance.enabled true

# Configure specific features
azlin config set performance.caching true
azlin config set performance.batching true
azlin config set performance.parallel true
```

### Cache Configuration

```bash
# Configure cache TTL
azlin config set performance.cache.ttl 300  # 5 minutes

# Configure cache size
azlin config set performance.cache.max_size 100MB

# Clear cache
azlin config cache clear
```

### Concurrency Configuration

```bash
# Set max parallel operations
azlin config set performance.max_parallel 10

# Set API rate limit buffer
azlin config set performance.rate_limit_buffer 20  # 20% buffer
```

## Performance Monitoring

### View Performance Metrics

```bash
# Show performance statistics
azlin perf stats

# Output:
# Performance Statistics (Last 24 hours):
#
# API Calls:
#   Total: 1,250
#   Cached: 625 (50%)
#   Batched: 312 (25%)
#
# Response Times:
#   Average: 1.2s
#   P95: 3.5s
#   P99: 8.2s
#
# Cache Hit Rate: 50%
# Batch Efficiency: 2.5 requests/batch avg
```

### Performance Profiling

```bash
# Profile a specific operation
azlin perf profile "azlin batch start vm-*"

# Output:
# Operation Profile: batch start vm-*
#
# Total Time: 15.2s
# Breakdown:
#   API Calls: 8.5s (56%)
#   Network: 3.2s (21%)
#   Processing: 2.1s (14%)
#   Other: 1.4s (9%)
#
# Optimization Suggestions:
#   - Enable caching: Save ~3.5s (23%)
#   - Increase parallelism: Save ~2.1s (14%)
```

## Optimization Tips

### 1. Use Batch Operations

```bash
# Instead of:
for vm in vm-01 vm-02 vm-03; do
  azlin start $vm
done

# Use:
azlin batch start vm-01,vm-02,vm-03
# 3x faster with automatic batching
```

### 2. Enable Caching for Read-Heavy Workloads

```bash
# For scripts that query VM status frequently
azlin config set performance.caching true

# Example: Monitoring script
while true; do
  azlin status --all  # Uses cached data
  sleep 60
done
```

### 3. Use Selectors for Bulk Operations

```bash
# Instead of listing VMs then operating on them:
vms=$(azlin list | grep prod | awk '{print $1}')
azlin batch start $vms

# Use direct selectors (faster):
azlin batch start --selector "tag:environment=prod"
```

### 4. Parallelize Independent Operations

```bash
# Deploy to multiple regions in parallel
azlin new myapp --regions eastus,westus,centralus --parallel
# 3x faster than sequential deployment
```

## Best Practices

1. **Enable Caching for Read-Heavy Workflows**
   - Monitoring scripts
   - Status dashboards
   - Cost analysis

2. **Use Batch Operations**
   - Always prefer batch over loops
   - Let azlin optimize the requests
   - Significant speedup for 5+ VMs

3. **Leverage Parallel Execution**
   - Multi-region deployments
   - Independent VM operations
   - Bulk data transfers

4. **Monitor Performance**
   - Track operation times
   - Identify slow operations
   - Optimize based on metrics

5. **Tune for Your Workload**
   - Adjust cache TTL based on data change frequency
   - Configure parallelism based on operation types
   - Balance speed vs. API rate limits

## API Reference

```python
from azlin.modules.performance import PerformanceConfig, CacheManager

# Configure performance settings
config = PerformanceConfig()
config.enable_caching = True
config.enable_batching = True
config.max_parallel = 10

# Access cache
cache = CacheManager()
cache.set_ttl(300)  # 5 minutes
cache.clear()

# Get performance statistics
stats = config.get_stats()
print(f"Cache hit rate: {stats.cache_hit_rate}%")
print(f"Avg response time: {stats.avg_response_time}s")
```

## Troubleshooting

### Performance Issues

**Problem**: Operations slower than expected

**Solution**:
```bash
# Profile the operation
azlin perf profile "your-command-here"

# Check if caching is enabled
azlin config get performance.caching

# Verify network connectivity
azlin perf test-connection
```

### Cache Issues

**Problem**: Stale data from cache

**Solution**:
```bash
# Reduce cache TTL
azlin config set performance.cache.ttl 60  # 1 minute

# Clear cache
azlin config cache clear

# Bypass cache for specific operation
azlin status --no-cache
```

## See Also

- [Batch Operations](../batch/index.md)
- [Multi-Region Orchestration](./multi-region.md)
- [Configuration](../getting-started/configuration.md)

---

*Documentation last updated: 2025-12-03*

!!! note "Full Documentation Coming Soon"
    Complete performance tuning guides and advanced optimization techniques will be added in the next documentation update.
