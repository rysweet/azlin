#!/usr/bin/env python3
"""Benchmark Parallel VM Listing Performance.

This benchmark compares the performance of:
1. Baseline: VMManager.list_vms() (serial operations)
2. Optimized: list_vms_parallel() (parallel operations + caching)

Usage:
    python benchmarks/benchmark_parallel_vm_list.py
    python benchmarks/benchmark_parallel_vm_list.py --iterations 10 --resource-group my-rg
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from azlin.cache.vm_list_cache import VMListCache
from azlin.vm_manager import VMManager, VMManagerError
from azlin.vm_manager_async import list_vms_parallel_with_stats


class ParallelVMListBenchmark:
    """Benchmark parallel VM listing performance."""

    def __init__(self, resource_group: str, iterations: int = 10, warmup: int = 2):
        """Initialize benchmark.

        Args:
            resource_group: Azure resource group to test
            iterations: Number of iterations to run
            warmup: Number of warmup iterations (not measured)
        """
        self.resource_group = resource_group
        self.iterations = iterations
        self.warmup = warmup
        self.results = {
            "baseline": [],  # VMManager.list_vms()
            "parallel_cold": [],  # First run with parallel (no cache)
            "parallel_warm": [],  # Subsequent runs with parallel (with cache)
        }
        self.cache_stats = []

    def setup(self):
        """Setup before benchmark."""
        print(f"Setting up benchmark for resource group: {self.resource_group}")
        print(f"Iterations: {self.iterations}, Warmup: {self.warmup}")

        # Verify resource group exists
        try:
            vms = VMManager.list_vms(self.resource_group)
            print(f"Found {len(vms)} VMs in resource group")
            if len(vms) == 0:
                print("WARNING: No VMs found. Benchmark results may not be meaningful.")
        except VMManagerError as e:
            print(f"ERROR: Failed to access resource group: {e}")
            sys.exit(1)

    def benchmark_baseline(self) -> float:
        """Benchmark baseline (serial operations, no cache).

        Returns:
            Elapsed time in seconds
        """
        start = time.perf_counter()
        VMManager.list_vms(self.resource_group)
        elapsed = time.perf_counter() - start

        return elapsed

    def benchmark_parallel(self, clear_cache: bool = False) -> tuple[float, dict]:
        """Benchmark parallel operations (with caching).

        Args:
            clear_cache: Clear cache before benchmark

        Returns:
            Tuple of (elapsed time, cache stats)
        """
        cache = VMListCache()

        if clear_cache:
            cache.clear()

        start = time.perf_counter()
        vms, stats = list_vms_parallel_with_stats(self.resource_group, cache=cache)
        elapsed = time.perf_counter() - start

        cache_stats = {
            "cache_hit_rate": stats.cache_hit_rate(),
            "cache_hits": stats.cache_hits,
            "cache_misses": stats.cache_misses,
            "api_calls": stats.api_calls,
            "vms_found": stats.vms_found,
        }

        return elapsed, cache_stats

    def run(self) -> dict:
        """Run benchmark and return results."""
        self.setup()

        print("\nRunning warmup iterations...")
        for i in range(self.warmup):
            self.benchmark_baseline()
            print(f"  Warmup {i + 1}/{self.warmup} complete")

        print("\nMeasuring BASELINE performance (serial operations)...")
        for i in range(self.iterations):
            baseline_time = self.benchmark_baseline()
            self.results["baseline"].append(baseline_time)
            print(f"  Iteration {i + 1}/{self.iterations}: {baseline_time:.3f}s")

        print("\nMeasuring PARALLEL performance (cold start - no cache)...")
        cold_time, cold_stats = self.benchmark_parallel(clear_cache=True)
        self.results["parallel_cold"].append(cold_time)
        self.cache_stats.append(("cold", cold_stats))
        print(f"  Cold start: {cold_time:.3f}s")
        print(f"  Cache hit rate: {cold_stats['cache_hit_rate']:.1%}")
        print(f"  API calls: {cold_stats['api_calls']}")

        print("\nMeasuring PARALLEL performance (warm start - with cache)...")
        for i in range(self.iterations):
            warm_time, warm_stats = self.benchmark_parallel(clear_cache=False)
            self.results["parallel_warm"].append(warm_time)
            self.cache_stats.append(("warm", warm_stats))
            print(f"  Iteration {i + 1}/{self.iterations}: {warm_time:.3f}s")
            print(f"    Cache hit rate: {warm_stats['cache_hit_rate']:.1%}")

        return self.generate_report()

    def generate_report(self) -> dict:
        """Generate benchmark report."""
        baseline_times = self.results["baseline"]
        parallel_cold_times = self.results["parallel_cold"]
        parallel_warm_times = self.results["parallel_warm"]

        baseline_mean = statistics.mean(baseline_times)
        parallel_cold_mean = statistics.mean(parallel_cold_times) if parallel_cold_times else 0.0
        parallel_warm_mean = statistics.mean(parallel_warm_times)

        # Calculate improvement percentages
        cold_improvement = ((baseline_mean - parallel_cold_mean) / baseline_mean) * 100 if baseline_mean > 0 else 0
        warm_improvement = ((baseline_mean - parallel_warm_mean) / baseline_mean) * 100 if baseline_mean > 0 else 0

        report = {
            "benchmark": "parallel_vm_list",
            "timestamp": datetime.utcnow().isoformat(),
            "resource_group": self.resource_group,
            "iterations": self.iterations,
            "baseline": {
                "mean": baseline_mean,
                "median": statistics.median(baseline_times),
                "stddev": statistics.stdev(baseline_times) if len(baseline_times) > 1 else 0.0,
                "min": min(baseline_times),
                "max": max(baseline_times),
            },
            "parallel_cold": {
                "mean": parallel_cold_mean,
                "improvement_pct": cold_improvement,
            },
            "parallel_warm": {
                "mean": parallel_warm_mean,
                "median": statistics.median(parallel_warm_times),
                "stddev": statistics.stdev(parallel_warm_times) if len(parallel_warm_times) > 1 else 0.0,
                "min": min(parallel_warm_times),
                "max": max(parallel_warm_times),
                "improvement_pct": warm_improvement,
            },
            "cache_stats": self.cache_stats,
        }

        return report

    def print_summary(self, report: dict):
        """Print human-readable summary."""
        print("\n" + "=" * 70)
        print("BENCHMARK RESULTS: PARALLEL VM LISTING")
        print("=" * 70)

        print(f"\nBenchmark: {report['benchmark']}")
        print(f"Resource Group: {report['resource_group']}")
        print(f"Timestamp: {report['timestamp']}")
        print(f"Iterations: {report['iterations']}")

        baseline = report["baseline"]
        print("\nBASELINE (Serial Operations, No Cache):")
        print(f"  Mean:   {baseline['mean']:.3f}s")
        print(f"  Median: {baseline['median']:.3f}s")
        print(f"  Stddev: {baseline['stddev']:.3f}s")
        print(f"  Min:    {baseline['min']:.3f}s")
        print(f"  Max:    {baseline['max']:.3f}s")

        parallel_cold = report["parallel_cold"]
        print("\nPARALLEL (Cold Start - No Cache):")
        print(f"  Mean:        {parallel_cold['mean']:.3f}s")
        print(f"  Improvement: {parallel_cold['improvement_pct']:.1f}%")
        if parallel_cold['improvement_pct'] < 0:
            print("  ⚠️  SLOWER than baseline (expected for cold start)")

        parallel_warm = report["parallel_warm"]
        print("\nPARALLEL (Warm Start - With Cache):")
        print(f"  Mean:        {parallel_warm['mean']:.3f}s")
        print(f"  Median:      {parallel_warm['median']:.3f}s")
        print(f"  Stddev:      {parallel_warm['stddev']:.3f}s")
        print(f"  Min:         {parallel_warm['min']:.3f}s")
        print(f"  Max:         {parallel_warm['max']:.3f}s")
        print(f"  Improvement: {parallel_warm['improvement_pct']:.1f}%")

        print("\nPERFORMANCE SUMMARY:")
        if parallel_warm['improvement_pct'] >= 70:
            print(f"  ✅ SUCCESS: {parallel_warm['improvement_pct']:.1f}% improvement (target: 70%)")
        elif parallel_warm['improvement_pct'] >= 50:
            print(f"  ⚠️  PARTIAL: {parallel_warm['improvement_pct']:.1f}% improvement (target: 70%)")
        else:
            print(f"  ❌ FAILED: {parallel_warm['improvement_pct']:.1f}% improvement (target: 70%)")

        # Print cache effectiveness
        if report['cache_stats']:
            avg_hit_rate = statistics.mean(
                stats['cache_hit_rate'] for _, stats in report['cache_stats'] if _ == 'warm'
            )
            print(f"\nCACHE EFFECTIVENESS:")
            print(f"  Average Hit Rate: {avg_hit_rate:.1%}")
            if avg_hit_rate >= 0.8:
                print("  Status: Excellent cache performance ✅")
            elif avg_hit_rate >= 0.5:
                print("  Status: Good cache performance")
            else:
                print("  Status: Poor cache performance ⚠️")

        print("\n" + "=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark parallel VM listing performance")
    parser.add_argument(
        "--resource-group",
        "-g",
        default="azlin-perf-test",
        help="Resource group to test (default: azlin-perf-test)",
    )
    parser.add_argument(
        "--iterations",
        "-i",
        type=int,
        default=10,
        help="Number of iterations (default: 10)",
    )
    parser.add_argument(
        "--warmup",
        "-w",
        type=int,
        default=2,
        help="Number of warmup iterations (default: 2)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file for JSON results (optional)",
    )

    args = parser.parse_args()

    # Run benchmark
    benchmark = ParallelVMListBenchmark(
        resource_group=args.resource_group,
        iterations=args.iterations,
        warmup=args.warmup,
    )

    try:
        report = benchmark.run()
        benchmark.print_summary(report)

        # Save JSON results if output specified
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nResults saved to: {args.output}")

    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
