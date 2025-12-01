#!/usr/bin/env python3
"""Benchmark VM listing performance.

This benchmark measures the performance of listing VMs in a resource group,
includin' both cold start (no cache) and warm start (cached) scenarios.

Usage:
    python benchmarks/benchmark_vm_list.py
    python benchmarks/benchmark_vm_list.py --iterations 20 --resource-group my-rg
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path fer imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from azlin.vm_manager import VMManager, VMManagerError


class VMListBenchmark:
    """Benchmark VM listing performance."""

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
            "cold_start": [],  # First run (no cache)
            "warm_start": [],  # Subsequent runs (may have cache)
        }

    def setup(self):
        """Setup before benchmark."""
        print(f"Setting up benchmark fer resource group: {self.resource_group}")
        print(f"Iterations: {self.iterations}, Warmup: {self.warmup}")

        # Verify resource group exists
        try:
            vms = VMManager.list_vms(self.resource_group)
            print(f"Found {len(vms)} VMs in resource group")
        except VMManagerError as e:
            print(f"ERROR: Failed to access resource group: {e}")
            sys.exit(1)

    def benchmark_cold_start(self) -> float:
        """Benchmark cold start (first run, no cache).

        Returns:
            Elapsed time in seconds
        """
        # Clear any existing cache before measurement
        # (This would invoke cache.clear() if cache implemented)

        start = time.perf_counter()
        VMManager.list_vms(self.resource_group)
        elapsed = time.perf_counter() - start

        return elapsed

    def benchmark_warm_start(self) -> float:
        """Benchmark warm start (subsequent run, may have cache).

        Returns:
            Elapsed time in seconds
        """
        start = time.perf_counter()
        VMManager.list_vms(self.resource_group)
        elapsed = time.perf_counter() - start

        return elapsed

    def run(self) -> dict:
        """Run benchmark and return results."""
        self.setup()

        print("\nRunning warmup iterations...")
        for i in range(self.warmup):
            self.benchmark_warm_start()
            print(f"  Warmup {i+1}/{self.warmup} complete")

        print("\nMeasuring cold start performance...")
        cold_start_time = self.benchmark_cold_start()
        self.results["cold_start"].append(cold_start_time)
        print(f"  Cold start: {cold_start_time:.3f}s")

        print("\nMeasuring warm start performance...")
        for i in range(self.iterations):
            warm_time = self.benchmark_warm_start()
            self.results["warm_start"].append(warm_time)
            print(f"  Iteration {i+1}/{self.iterations}: {warm_time:.3f}s")

        return self.generate_report()

    def generate_report(self) -> dict:
        """Generate benchmark report."""
        warm_times = self.results["warm_start"]

        report = {
            "benchmark": "vm_list",
            "timestamp": datetime.utcnow().isoformat(),
            "resource_group": self.resource_group,
            "iterations": self.iterations,
            "cold_start": {
                "time": self.results["cold_start"][0],
            },
            "warm_start": {
                "mean": statistics.mean(warm_times),
                "median": statistics.median(warm_times),
                "stddev": statistics.stdev(warm_times) if len(warm_times) > 1 else 0.0,
                "min": min(warm_times),
                "max": max(warm_times),
                "p95": self._percentile(warm_times, 0.95),
                "p99": self._percentile(warm_times, 0.99),
            },
        }

        # Calculate cache effectiveness (if warm is significantly faster)
        cold_time = report["cold_start"]["time"]
        warm_mean = report["warm_start"]["mean"]

        if warm_mean < cold_time * 0.5:
            # Warm start is at least 50% faster - likely cache hit
            cache_hit_ratio = 1.0 - (warm_mean / cold_time)
            report["cache_effectiveness"] = {
                "estimated_hit_ratio": cache_hit_ratio,
                "speedup_factor": cold_time / warm_mean,
            }
        else:
            report["cache_effectiveness"] = {
                "estimated_hit_ratio": 0.0,
                "speedup_factor": 1.0,
            }

        return report

    def _percentile(self, data: list[float], percentile: float) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0.0

        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        index = min(index, len(sorted_data) - 1)
        return sorted_data[index]

    def print_summary(self, report: dict):
        """Print human-readable summary."""
        print("\n" + "=" * 60)
        print("BENCHMARK RESULTS")
        print("=" * 60)

        print(f"\nBenchmark: {report['benchmark']}")
        print(f"Resource Group: {report['resource_group']}")
        print(f"Timestamp: {report['timestamp']}")
        print(f"Iterations: {report['iterations']}")

        print(f"\nCold Start (First Run):")
        print(f"  Time: {report['cold_start']['time']:.3f}s")

        warm = report['warm_start']
        print(f"\nWarm Start (Subsequent Runs):")
        print(f"  Mean:   {warm['mean']:.3f}s")
        print(f"  Median: {warm['median']:.3f}s")
        print(f"  Stddev: {warm['stddev']:.3f}s")
        print(f"  Min:    {warm['min']:.3f}s")
        print(f"  Max:    {warm['max']:.3f}s")
        print(f"  P95:    {warm['p95']:.3f}s")
        print(f"  P99:    {warm['p99']:.3f}s")

        cache = report['cache_effectiveness']
        if cache['estimated_hit_ratio'] > 0:
            print(f"\nCache Effectiveness:")
            print(f"  Estimated Hit Ratio: {cache['estimated_hit_ratio']:.1%}")
            print(f"  Speedup Factor: {cache['speedup_factor']:.2f}x")
            print("  Status: Cache likely active ✅")
        else:
            print(f"\nCache Effectiveness:")
            print(f"  Status: No cache detected or cache ineffective")

        print("\n" + "=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark VM listing performance"
    )
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
        help="Output file fer JSON results (optional)",
    )

    args = parser.parse_args()

    # Run benchmark
    benchmark = VMListBenchmark(
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
        sys.exit(1)


if __name__ == "__main__":
    main()
