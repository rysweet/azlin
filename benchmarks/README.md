# Performance Benchmarking Suite

**Purpose**: Measure azlin performance before and after optimizations

## Benchmark Categories

### 1. Azure API Operations
- `benchmark_vm_list.py` - VM listing performance
- `benchmark_vm_status.py` - VM status queries
- `benchmark_resource_discovery.py` - Resource group discovery

### 2. SSH Operations
- `benchmark_ssh_connections.py` - Connection establishment
- `benchmark_distributed_commands.py` - Multi-VM operations
- `benchmark_connection_reuse.py` - Connection pooling efficiency

### 3. Local State Operations
- `benchmark_config_load.py` - Configuration loading
- `benchmark_session_lookup.py` - Session name lookups
- `benchmark_cache_performance.py` - Cache hit/miss ratios

## Running Benchmarks

### Quick Start
```bash
# Run all benchmarks
python benchmarks/run_all.py

# Run specific category
python benchmarks/run_all.py --category azure_api

# Run single benchmark
python benchmarks/benchmark_vm_list.py
```

### Prerequisites
```bash
# Install profiling tools
pip install memory-profiler line-profiler pytest-benchmark

# Ensure Azure credentials configured
az login

# Set test resource group
export AZLIN_TEST_RG="azlin-perf-test"
```

## Benchmark Output Format

Each benchmark produces JSON results:
```json
{
  "benchmark": "vm_list",
  "timestamp": "2025-12-01T20:00:00Z",
  "iterations": 10,
  "stats": {
    "mean": 3.245,
    "median": 3.189,
    "stddev": 0.342,
    "min": 2.876,
    "max": 4.123,
    "p95": 3.987,
    "p99": 4.089
  },
  "cache_stats": {
    "hits": 0,
    "misses": 10,
    "hit_ratio": 0.0
  },
  "resource_usage": {
    "peak_memory_mb": 45.2,
    "cpu_percent": 12.5
  }
}
```

## Baseline vs. Optimized Comparison

```bash
# Capture baseline
python benchmarks/run_all.py --output baselines/baseline_2025_12_01.json

# After optimization, compare
python benchmarks/run_all.py --output results/optimized_2025_12_15.json
python benchmarks/compare.py baselines/baseline_2025_12_01.json results/optimized_2025_12_15.json
```

Expected comparison output:
```
Performance Comparison Report
==============================

Operation: vm_list (10 VMs)
  Baseline:   mean=3.24s, p95=3.99s
  Optimized:  mean=0.21s, p95=0.31s
  Improvement: 93.5% faster ✅

Operation: vm_status (1 VM)
  Baseline:   mean=2.45s, p95=2.89s
  Optimized:  mean=0.15s, p95=0.28s
  Improvement: 93.9% faster ✅

Operation: ssh_connect (10 VMs)
  Baseline:   mean=6.12s, p95=7.34s
  Optimized:  mean=1.45s, p95=1.78s
  Improvement: 76.3% faster ✅

Overall: 88.2% performance improvement across all operations
```

## Profiling Tools

### CPU Profiling
```bash
# Profile VM list command
python -m cProfile -o profiles/vm_list.stats azlin list

# Analyze results
python -m pstats profiles/vm_list.stats
# > sort cumulative
# > stats 20
```

### Memory Profiling
```bash
# Profile memory usage
python -m memory_profiler azlin list

# Line-by-line profiling
kernprof -l -v src/azlin/vm_manager.py
```

### Continuous Profiling
```bash
# Run performance monitoring daemon
python benchmarks/monitor_daemon.py --interval 60 --duration 3600
# Collects metrics every 60s for 1 hour
```

## Test Data Setup

### Create Test Environment
```bash
# Provision test VMs
./benchmarks/setup_test_env.sh

# Creates:
# - 10 test VMs (Standard_B2s)
# - Test resource group
# - Sample SSH keys
# - Test config files
```

### Cleanup Test Environment
```bash
./benchmarks/cleanup_test_env.sh
```

## Benchmark Development Guidelines

### Template Structure
```python
# benchmarks/template.py
import time
import statistics
import json
from pathlib import Path

class BenchmarkTemplate:
    """Template fer performance benchmarks."""

    def __init__(self, name: str, iterations: int = 10):
        self.name = name
        self.iterations = iterations
        self.results = []

    def setup(self):
        """Setup before benchmark (not timed)."""
        pass

    def benchmark_operation(self):
        """Operation to benchmark (timed)."""
        raise NotImplementedError

    def teardown(self):
        """Cleanup after benchmark (not timed)."""
        pass

    def run(self) -> dict:
        """Run benchmark and return results."""
        self.setup()

        for i in range(self.iterations):
            start = time.perf_counter()
            self.benchmark_operation()
            elapsed = time.perf_counter() - start
            self.results.append(elapsed)

        self.teardown()

        return self.generate_report()

    def generate_report(self) -> dict:
        """Generate benchmark report."""
        return {
            "benchmark": self.name,
            "iterations": self.iterations,
            "stats": {
                "mean": statistics.mean(self.results),
                "median": statistics.median(self.results),
                "stddev": statistics.stdev(self.results),
                "min": min(self.results),
                "max": max(self.results),
            }
        }
```

### Example Usage
```python
class VMListBenchmark(BenchmarkTemplate):
    def __init__(self):
        super().__init__("vm_list", iterations=10)

    def setup(self):
        from azlin.vm_manager import VMManager
        self.manager = VMManager()
        self.rg = "test-rg"

    def benchmark_operation(self):
        self.manager.list_vms(self.rg)

if __name__ == "__main__":
    benchmark = VMListBenchmark()
    results = benchmark.run()
    print(json.dumps(results, indent=2))
```

## CI Integration

### GitHub Actions Workflow
```yaml
# .github/workflows/performance.yml
name: Performance Benchmarks

on:
  pull_request:
    paths:
      - 'src/azlin/**'
      - 'benchmarks/**'

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run benchmarks
        run: |
          python benchmarks/run_all.py --output results/pr_${{ github.event.pull_request.number }}.json

      - name: Compare with baseline
        run: |
          python benchmarks/compare.py baselines/main.json results/pr_${{ github.event.pull_request.number }}.json

      - name: Comment on PR
        uses: actions/github-script@v6
        with:
          script: |
            // Post benchmark results as PR comment
```

## Monitoring Dashboard

View real-time performance metrics:
```bash
# Start monitoring dashboard
python benchmarks/dashboard.py

# Access at http://localhost:8050
```

Dashboard shows:
- Operation latency over time
- Cache hit ratios
- Resource usage trends
- Performance regressions

## Troubleshooting

### Benchmark Failures
```bash
# Check Azure credentials
az account show

# Verify test resource group exists
az group show --name $AZLIN_TEST_RG

# Check SSH connectivity
azlin list --resource-group $AZLIN_TEST_RG
```

### Inconsistent Results
- Ensure test environment is idle
- Run multiple iterations (>10)
- Check for background processes
- Verify network stability

## References

- Performance Spec: `specs/PERFORMANCE_SPEC.md`
- Optimizer Agent: `.claude/agents/amplihack/specialized/optimizer.md`
- Project Philosophy: `.claude/context/PHILOSOPHY.md`
