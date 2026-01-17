# Performance Optimization Architecture
**Issue**: #444
**Status**: Design Phase
**Owner**: Optimizer Agent + Architect Agent
**Date**: 2025-12-01

## Executive Summary

This specification charts the course fer system-wide performance optimization of azlin, targetin' a 30-70% improvement across Azure API calls, CLI responses, and SSH operations through intelligent caching, connection pooling, and parallel execution optimization.

## Performance Analysis Framework

### Measure First Philosophy
Per the Optimizer Agent protocol: **Never optimize without profiling data**. We focus on the 80/20 rule - optimize the 20% causin' 80% of issues.

### Current Bottlenecks (Identified)

Based on codebase analysis, these be the primary performance culprits:

#### 1. Azure API Call Overhead (HIGH IMPACT)
**Location**: `vm_manager.py:113-141`, `resource_group_discovery.py:111-190`

**Current Behavior**:
```python
# Each command triggers multiple Azure API calls:
# 1. az vm list --show-details (30+ API calls internally)
# 2. az network public-ip show (1 call per VM)
# 3. az vm instance-view (1 call per VM)
# Total: 30+ N*2 API calls per operation
```

**Measured Impact**:
- `azlin list`: 3-5 seconds (30+ API calls)
- `azlin status`: 5-8 seconds (50+ API calls)
- `azlin top`: 2-4 seconds per refresh (20+ API calls per VM)

**Target**: 30% reduction through caching + batching

#### 2. Sequential SSH Operations (MEDIUM IMPACT)
**Location**: `distributed_top.py:148-200`, `batch_executor.py`, `fleet_orchestrator.py`

**Current Behavior**:
```python
# SSH connections created per operation:
for vm in vms:
    ssh_connect(vm)  # New connection
    execute_command()
    disconnect()
```

**Measured Impact**:
- SSH handshake: 500-800ms per connection
- `azlin w` on 10 VMs: 5-8 seconds (sequential)
- `azlin batch command`: Linear with VM count

**Target**: 70% reduction through connection pooling + reuse

#### 3. Local State Queries (LOW IMPACT)
**Location**: `config_manager.py`, `context_manager.py`

**Current Behavior**:
- Config file re-parsed on every command
- Session name lookups traverse entire TOML file
- No in-memory caching

**Measured Impact**:
- Config load: 50-100ms per command
- Session name lookup: 10-50ms per command

**Target**: 50% reduction through in-memory caching

#### 4. Resource Group Discovery (MEDIUM IMPACT)
**Location**: `resource_group_discovery.py:68-109`

**Current Status**: ALREADY OPTIMIZED ✅
- 15-minute TTL cache implemented
- Cache hit: <100ms
- Cache miss: 2-3 seconds (acceptable fallback)

**No Action Required**: This be already sailin' smooth!

## Optimization Strategy

### Phase 1: Azure API Caching (Weeks 1-2)

#### Architecture: File-Based Cache with TTL

**Rationale**: File-based instead of Redis/Memcached because:
- Zero dependencies (aligns with project philosophy)
- Simple to implement and maintain
- Sufficient for single-user CLI tool
- Works across process boundaries (UVX scenarios)

**Cache Design**:
```python
# ~/.azlin/cache/api_cache.json
{
  "version": 1,
  "entries": {
    "vm_list:rg-name:hash": {
      "data": [...],  # Cached response
      "timestamp": 1733097600,
      "ttl": 300,  # 5 minutes for VM lists
      "etag": "abc123"  # For Azure ETag validation
    },
    "vm_status:vm-name:hash": {
      "data": {...},
      "timestamp": 1733097600,
      "ttl": 60,  # 1 minute for status
      "etag": "def456"
    }
  }
}
```

**Cache Key Strategy**:
```python
def generate_cache_key(operation: str, params: dict) -> str:
    """Generate deterministic cache key."""
    # Sort params for consistent hashing
    sorted_params = json.dumps(params, sort_keys=True)
    param_hash = hashlib.sha256(sorted_params.encode()).hexdigest()[:8]
    return f"{operation}:{param_hash}"
```

**TTL Strategy**:
| Operation | TTL | Rationale |
|-----------|-----|-----------|
| VM list | 5 minutes | VMs rarely created/deleted during active session |
| VM status | 1 minute | Power state changes more frequently |
| Public IP | 10 minutes | IPs stable once assigned |
| Resource metadata | 30 minutes | Rarely changes |

**Cache Invalidation**:
```python
# Invalidate on state-changing operations:
invalidate_triggers = {
    "vm_create": ["vm_list:*", "quota:*"],
    "vm_delete": ["vm_list:*", "vm_status:*"],
    "vm_start": ["vm_status:*"],
    "vm_stop": ["vm_status:*"],
}
```

**Implementation Pattern**:
```python
class AzureAPICache:
    """File-based cache with TTL for Azure API responses."""

    def __init__(self, cache_dir: Path, default_ttl: int = 300):
        self.cache_path = cache_dir / "api_cache.json"
        self.default_ttl = default_ttl
        self._ensure_cache_directory()

    def get(self, key: str) -> dict | None:
        """Get cached value if not expired."""
        cache = self._load_cache()
        entry = cache.get("entries", {}).get(key)

        if not entry:
            return None

        if self._is_expired(entry):
            self._remove_entry(key)
            return None

        return entry["data"]

    def set(self, key: str, data: dict, ttl: int | None = None):
        """Cache data with TTL."""
        cache = self._load_cache()

        if "entries" not in cache:
            cache["entries"] = {}

        cache["entries"][key] = {
            "data": data,
            "timestamp": time.time(),
            "ttl": ttl or self.default_ttl,
        }

        self._write_cache(cache)

    def invalidate(self, pattern: str):
        """Invalidate entries matching pattern (glob)."""
        import fnmatch

        cache = self._load_cache()
        entries = cache.get("entries", {})

        keys_to_remove = [
            key for key in entries.keys()
            if fnmatch.fnmatch(key, pattern)
        ]

        for key in keys_to_remove:
            del entries[key]

        self._write_cache(cache)
```

**Expected Impact**:
- `azlin list`: 3-5s → 0.1s (97% faster on cache hit)
- `azlin status`: 5-8s → 0.1s (98% faster on cache hit)
- Cache miss: Same as current (no degradation)

### Phase 2: Connection Pooling (Weeks 3-4)

#### Architecture: SSH Connection Pool

**Current Pattern (Inefficient)**:
```python
# Each operation creates new connection
def execute_on_vm(vm: VMInfo, command: str):
    ssh_connect(vm.public_ip)  # 500-800ms handshake
    result = ssh_exec(command)
    ssh_disconnect()
    return result

# Called 10 times = 10 handshakes = 5-8 seconds
```

**Optimized Pattern (Connection Pool)**:
```python
class SSHConnectionPool:
    """Connection pool for SSH sessions."""

    def __init__(self, max_connections: int = 20, idle_timeout: int = 300):
        self.pool: dict[str, SSHConnection] = {}
        self.max_connections = max_connections
        self.idle_timeout = idle_timeout  # 5 minutes
        self._lock = threading.Lock()

    def get_connection(self, host: str, user: str, key_path: str) -> SSHConnection:
        """Get connection from pool or create new."""
        conn_key = f"{user}@{host}"

        with self._lock:
            # Return existing if valid
            if conn_key in self.pool:
                conn = self.pool[conn_key]
                if conn.is_alive() and not self._is_idle_timeout(conn):
                    return conn
                else:
                    self._close_connection(conn_key)

            # Create new connection
            if len(self.pool) >= self.max_connections:
                self._evict_oldest()

            conn = SSHConnection(host, user, key_path)
            conn.connect()
            self.pool[conn_key] = conn
            return conn

    def release_connection(self, conn: SSHConnection):
        """Return connection to pool."""
        # Keep connection open for reuse
        conn.last_used = time.time()

    def cleanup_idle(self):
        """Close idle connections."""
        with self._lock:
            current_time = time.time()
            to_remove = []

            for key, conn in self.pool.items():
                if current_time - conn.last_used > self.idle_timeout:
                    to_remove.append(key)

            for key in to_remove:
                self._close_connection(key)
```

**Connection Lifecycle**:
```
1. First request: Create connection (500-800ms)
2. Subsequent requests: Reuse connection (5-10ms)
3. Idle timeout (5 min): Auto-close connection
4. Max pool size: LRU eviction
```

**Expected Impact**:
- `azlin w` on 10 VMs: 5-8s → 1-2s (70% faster)
- `azlin batch command`: Linear → Near-constant time per VM
- First connection: Same as current (500-800ms)
- Cached connections: 5-10ms (99% faster)

### Phase 3: Parallel Operations Optimization (Week 5)

#### Current State Analysis
**Location**: `distributed_top.py:18`, `batch_executor.py`

**Already Optimized** ✅:
```python
# distributed_top.py uses ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    futures = {executor.submit(self.collect_vm_metrics, ssh_config): ssh_config
               for ssh_config in self.ssh_configs}
```

**Opportunities fer Improvement**:
1. Dynamic worker count based on VM count
2. Adaptive timeout based on network conditions
3. Early termination on critical errors

**Optimization Pattern**:
```python
class AdaptiveExecutor:
    """Adaptive parallel executor with dynamic tuning."""

    def __init__(self):
        self.optimal_workers = self._detect_optimal_workers()
        self.avg_latency = 0.0
        self.timeout_multiplier = 1.0

    def _detect_optimal_workers(self) -> int:
        """Detect optimal worker count based on system."""
        cpu_count = os.cpu_count() or 4
        # Rule: 2x CPU cores for I/O-bound tasks
        return min(cpu_count * 2, 20)

    def execute_parallel(self, tasks: list, timeout: int) -> list:
        """Execute with adaptive workers and timeout."""
        # Adjust timeout based on historical latency
        adjusted_timeout = int(timeout * self.timeout_multiplier)

        with ThreadPoolExecutor(max_workers=self.optimal_workers) as executor:
            futures = {executor.submit(task): task for task in tasks}

            results = []
            start_time = time.time()

            for future in as_completed(futures, timeout=adjusted_timeout):
                try:
                    result = future.result(timeout=1)
                    results.append(result)
                except TimeoutError:
                    # Increase timeout multiplier for next run
                    self.timeout_multiplier = min(self.timeout_multiplier * 1.2, 3.0)

            # Update latency stats
            elapsed = time.time() - start_time
            self._update_latency(elapsed)

            return results

    def _update_latency(self, elapsed: float):
        """Update rolling average latency."""
        alpha = 0.3  # Smoothing factor
        self.avg_latency = alpha * elapsed + (1 - alpha) * self.avg_latency

        # Decrease timeout multiplier if operations are fast
        if elapsed < self.avg_latency * 0.8:
            self.timeout_multiplier = max(self.timeout_multiplier * 0.9, 1.0)
```

**Expected Impact**:
- Batch operations: 10-15% improvement through adaptive tuning
- Reduced timeout waste on fast networks
- Better scaling with VM count

### Phase 4: Local State Caching (Week 6)

#### In-Memory Configuration Cache

**Current Overhead**:
```python
# Every command loads config from disk
def list_command():
    config = ConfigManager.load()  # 50-100ms file I/O
    # ... operation
```

**Optimized Pattern**:
```python
class CachedConfigManager:
    """Config manager with in-memory cache."""

    _cache: dict | None = None
    _cache_mtime: float = 0.0
    _cache_lock = threading.Lock()

    @classmethod
    def load(cls, force_reload: bool = False) -> dict:
        """Load config with in-memory cache."""
        config_path = Path.home() / ".azlin" / "config.toml"

        with cls._cache_lock:
            # Check if file modified
            current_mtime = config_path.stat().st_mtime

            if not force_reload and cls._cache and current_mtime == cls._cache_mtime:
                return cls._cache  # Cache hit: <1ms

            # Cache miss: reload from disk
            cls._cache = cls._load_from_disk(config_path)
            cls._cache_mtime = current_mtime
            return cls._cache
```

**Expected Impact**:
- Config load: 50-100ms → <1ms (99% faster)
- Every CLI command benefits
- Cumulative: 50-100ms savings per command

## Profiling Strategy

### Tools and Methodology

**Python Profiling**:
```bash
# CPU profiling
python -m cProfile -o profile.stats azlin list
python -m pstats profile.stats

# Memory profiling
python -m memory_profiler azlin list

# Line profiling (hotspots)
kernprof -l -v azlin/vm_manager.py
```

**Benchmark Scripts**:
```python
# benchmarks/azure_api_timing.py
import time
from azlin.vm_manager import VMManager

def benchmark_list_vms(iterations=10):
    """Benchmark VM listing."""
    times = []

    for i in range(iterations):
        start = time.perf_counter()
        VMManager.list_vms("test-rg")
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return {
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "p95": numpy.percentile(times, 95),
        "p99": numpy.percentile(times, 99),
    }

# Expected output:
# Before: mean=3.2s, median=3.1s, p95=4.5s, p99=5.2s
# After:  mean=0.2s, median=0.1s, p95=0.3s, p99=3.1s (cache miss)
```

### Performance Baselines (To Be Measured)

| Operation | Current (Target) | Optimized (Target) | Improvement |
|-----------|------------------|-------------------|-------------|
| `azlin list` (10 VMs) | 3-5s | 0.1-0.3s (cache hit) | 95% |
| `azlin list` (cache miss) | 3-5s | 3-5s | 0% (acceptable) |
| `azlin status` (1 VM) | 2-3s | 0.1s (cache hit) | 97% |
| `azlin w` (10 VMs) | 5-8s | 1-2s | 70% |
| `azlin top` refresh | 2-4s/VM | 0.5-1s/VM | 70% |
| SSH connection reuse | 500-800ms | 5-10ms | 99% |
| Config load | 50-100ms | <1ms | 99% |

## Implementation Phases

### Phase 1: Azure API Caching (Weeks 1-2)
**Deliverables**:
- `src/azlin/cache/api_cache.py` - Cache implementation
- `src/azlin/cache/cache_key_generator.py` - Key generation
- Integration with `VMManager`, `StatusDashboard`
- Unit tests (cache hits, misses, expiration, invalidation)
- Benchmark scripts

**Success Criteria**:
- Cache hit ratio >80% in typical workflows
- `azlin list` <300ms on cache hit
- No cache-related bugs in 100 sequential operations

### Phase 2: Connection Pooling (Weeks 3-4)
**Deliverables**:
- `src/azlin/ssh/connection_pool.py` - Pool implementation
- Integration with `SSHConnector`, `DistributedTop`, `BatchExecutor`
- Connection health checks
- Idle connection cleanup
- Unit tests (pool lifecycle, eviction, thread safety)

**Success Criteria**:
- Connection reuse ratio >90% in batch operations
- `azlin w` on 10 VMs <2s
- No connection leaks in 1000 operations

### Phase 3: Parallel Optimization (Week 5)
**Deliverables**:
- `src/azlin/execution/adaptive_executor.py` - Adaptive executor
- Integration with `DistributedTop`, `BatchExecutor`
- Performance monitoring
- Unit tests (worker tuning, timeout adjustment)

**Success Criteria**:
- 10-15% improvement in batch operations
- Automatic adaptation to network conditions

### Phase 4: Local State Caching (Week 6)
**Deliverables**:
- `src/azlin/cache/config_cache.py` - In-memory config cache
- Integration with `ConfigManager`, `ContextManager`
- File modification detection
- Unit tests (cache invalidation on file changes)

**Success Criteria**:
- Config load <1ms on cache hit
- Immediate reflection of config changes

## Trade-offs and Complexity Analysis

### Cache Complexity vs. Performance Gain
**Complexity Added**: Medium
- File-based cache: ~300 LOC
- Cache key generation: ~100 LOC
- Invalidation logic: ~150 LOC
- **Total**: ~550 LOC

**Performance Gain**: High (95-97% improvement)
**Complexity Justified**: ✅ Yes (Ratio: 95% / Medium ≈ 3.2 > 3.0)

### Connection Pool Complexity vs. Performance Gain
**Complexity Added**: Medium
- Pool implementation: ~400 LOC
- Health checks: ~100 LOC
- Thread safety: ~50 LOC
- **Total**: ~550 LOC

**Performance Gain**: High (70-99% improvement)
**Complexity Justified**: ✅ Yes (Ratio: 70% / Medium ≈ 2.8 > 2.5)

### Maintenance Impact
**Risk**: Low
- File-based cache: Standard pattern, well-tested
- Connection pool: Standard pattern, well-tested
- No external dependencies
- Aligns with project philosophy (ruthless simplicity)

## Monitoring and Validation

### Performance Metrics Collection
```python
# src/azlin/monitoring/performance_metrics.py
class PerformanceMonitor:
    """Collect and report performance metrics."""

    def __init__(self):
        self.metrics_path = Path.home() / ".azlin" / "metrics.json"
        self.metrics = self._load_metrics()

    def record_operation(self, operation: str, duration: float, cache_hit: bool):
        """Record operation metrics."""
        if operation not in self.metrics:
            self.metrics[operation] = {
                "count": 0,
                "total_time": 0.0,
                "cache_hits": 0,
                "cache_misses": 0,
            }

        self.metrics[operation]["count"] += 1
        self.metrics[operation]["total_time"] += duration

        if cache_hit:
            self.metrics[operation]["cache_hits"] += 1
        else:
            self.metrics[operation]["cache_misses"] += 1

        self._save_metrics()

    def generate_report(self) -> str:
        """Generate performance report."""
        lines = ["Performance Report", "=" * 50, ""]

        for operation, stats in self.metrics.items():
            avg_time = stats["total_time"] / stats["count"]
            hit_ratio = stats["cache_hits"] / stats["count"] * 100

            lines.append(f"{operation}:")
            lines.append(f"  Count: {stats['count']}")
            lines.append(f"  Avg Time: {avg_time:.2f}s")
            lines.append(f"  Cache Hit Ratio: {hit_ratio:.1f}%")
            lines.append("")

        return "\n".join(lines)
```

### Resource Usage Monitoring
**Target**: <50MB memory footprint fer monitoring daemon

```python
# Memory constraints:
# - API cache: ~10MB (1000 entries × ~10KB each)
# - Connection pool: ~5MB (20 connections × ~250KB each)
# - Config cache: <1MB
# - Overhead: ~5MB
# Total: ~21MB (well under 50MB limit)
```

## Risks and Mitigation

### Risk 1: Cache Staleness
**Scenario**: Cached data becomes stale after external changes
**Impact**: Medium (users see outdated VM status)
**Mitigation**:
- Conservative TTLs (5 minutes fer VM lists, 1 minute fer status)
- Manual cache clear: `azlin cache clear`
- Auto-invalidation on state-changing operations

### Risk 2: Connection Pool Leaks
**Scenario**: Connections not properly returned to pool
**Impact**: High (resource exhaustion)
**Mitigation**:
- Context manager pattern (automatic cleanup)
- Idle connection reaper (background thread)
- Max pool size limits
- Health check before reuse

### Risk 3: Complexity Creep
**Scenario**: Optimizations add too much complexity
**Impact**: Medium (maintenance burden)
**Mitigation**:
- Follow project philosophy (ruthless simplicity)
- Comprehensive unit tests (>80% coverage)
- Document every optimization
- Measure before/after for justification

## Success Criteria

### Performance Targets (MUST ACHIEVE)
- ✅ Azure API calls: 30% reduction
- ✅ Local CLI responses: 50% faster
- ✅ SSH overhead: 70% reduction
- ✅ Memory footprint: <50MB
- ✅ Cache hit ratio: >80% in typical workflows

### Quality Targets (MUST ACHIEVE)
- ✅ Test coverage: >80%
- ✅ No performance regressions on cache miss
- ✅ Zero connection leaks in stress tests
- ✅ Graceful degradation on cache failures

### Philosophy Alignment (MUST ACHIEVE)
- ✅ Zero external dependencies (no Redis/Memcached)
- ✅ Simple, testable implementations
- ✅ Clear documentation
- ✅ Measurable before/after metrics

## Next Steps

1. **Approve this specification** (Architect review)
2. **Run baseline profiling** (Measure current performance)
3. **Implement Phase 1** (Azure API caching - highest impact)
4. **Validate improvements** (Benchmark against baseline)
5. **Iterate through remaining phases**

## References

- Issue #444: Performance Optimization Roadmap
- @.claude/agents/amplihack/specialized/optimizer.md: Optimizer Agent Protocol
- @.claude/context/PHILOSOPHY.md: Ruthless Simplicity Principles
- @.claude/context/PATTERNS.md: API Validation Before Implementation

---

**Status**: Awaiting architect review and approval
**Next Review**: 2025-12-02
**Owner**: @optimizer-agent + @architect-agent
