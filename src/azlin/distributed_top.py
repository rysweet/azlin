"""Distributed top command execution module.

This module provides functionality to execute 'top' command across multiple VMs
and display the results in a live-updating dashboard. Shows CPU, memory, load,
and top processes for each VM in a unified view.

Usage:
    from azlin.distributed_top import DistributedTopExecutor

    executor = DistributedTopExecutor(ssh_configs, interval=10)
    executor.run_dashboard()
"""

import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.table import Table

from azlin.modules.ssh_connector import SSHConfig

logger = logging.getLogger(__name__)


class DistributedTopError(Exception):
    """Raised when distributed top execution fails."""

    pass


@dataclass
class VMMetrics:
    """Metrics collected from a VM."""

    vm_name: str
    success: bool
    load_avg: tuple[float, float, float] | None  # 1min, 5min, 15min
    cpu_percent: float | None
    memory_used_mb: int | None
    memory_total_mb: int | None
    memory_percent: float | None
    top_processes: list[dict[str, str]] | None  # List of {pid, user, cpu, mem, command}
    error_message: str | None = None
    timestamp: float = 0.0


class DistributedTopExecutor:
    """Execute top command across multiple VMs with live dashboard.

    This class provides:
    - Parallel metric collection from multiple VMs
    - Live-updating rich dashboard
    - Configurable refresh interval
    - Graceful degradation for unreachable VMs
    """

    def __init__(
        self,
        ssh_configs: list[SSHConfig],
        interval: int = 10,
        max_workers: int = 10,
        timeout: int = 5,
    ):
        """Initialize distributed top executor.

        Args:
            ssh_configs: List of SSH configurations for VMs
            interval: Refresh interval in seconds (default 10)
            max_workers: Maximum parallel workers (default 10)
            timeout: SSH timeout per VM in seconds (default 5)
        """
        self.ssh_configs = ssh_configs
        self.interval = interval
        self.max_workers = max_workers
        self.timeout = timeout
        self.console = Console()

    @classmethod
    def collect_vm_metrics(cls, ssh_config: SSHConfig, timeout: int = 5) -> VMMetrics:
        """Collect metrics from a single VM.

        Executes a compound command to gather:
        - Load average (from uptime)
        - Memory usage (from free -m)
        - Top 3 processes by CPU (from top -bn1)

        Args:
            ssh_config: SSH configuration for the VM
            timeout: SSH timeout in seconds

        Returns:
            VMMetrics object with collected data
        """
        start_time = time.time()

        # Compound command to collect all metrics in one SSH call
        command = "uptime && free -m && top -bn1 -o %CPU | head -n 15"

        try:
            # Build SSH command
            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
                "-o",
                f"ConnectTimeout={timeout}",
                "-i",
                str(ssh_config.key_path),
                f"{ssh_config.user}@{ssh_config.host}",
                command,
            ]

            logger.debug(f"Collecting metrics from {ssh_config.host}")

            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            timestamp = time.time() - start_time

            if result.returncode != 0:
                return VMMetrics(
                    vm_name=ssh_config.host,
                    success=False,
                    load_avg=None,
                    cpu_percent=None,
                    memory_used_mb=None,
                    memory_total_mb=None,
                    memory_percent=None,
                    top_processes=None,
                    error_message=result.stderr or "SSH connection failed",
                    timestamp=timestamp,
                )

            # Parse output
            load_avg, cpu_percent, mem_used, mem_total, mem_percent, processes = (
                cls._parse_metrics_output(result.stdout)
            )

            return VMMetrics(
                vm_name=ssh_config.host,
                success=True,
                load_avg=load_avg,
                cpu_percent=cpu_percent,
                memory_used_mb=mem_used,
                memory_total_mb=mem_total,
                memory_percent=mem_percent,
                top_processes=processes,
                timestamp=timestamp,
            )

        except subprocess.TimeoutExpired:
            return VMMetrics(
                vm_name=ssh_config.host,
                success=False,
                load_avg=None,
                cpu_percent=None,
                memory_used_mb=None,
                memory_total_mb=None,
                memory_percent=None,
                top_processes=None,
                error_message=f"Timeout after {timeout}s",
                timestamp=timeout,
            )
        except Exception as e:
            logger.error(f"Failed to collect metrics from {ssh_config.host}: {e}")
            return VMMetrics(
                vm_name=ssh_config.host,
                success=False,
                load_avg=None,
                cpu_percent=None,
                memory_used_mb=None,
                memory_total_mb=None,
                memory_percent=None,
                top_processes=None,
                error_message=str(e),
                timestamp=time.time() - start_time,
            )

    @classmethod
    def _parse_metrics_output(cls, output: str) -> tuple:
        """Parse metrics from command output.

        Args:
            output: Combined output from uptime, free, and top commands

        Returns:
            Tuple of (load_avg, cpu_percent, mem_used, mem_total, mem_percent, processes)
        """
        lines = output.splitlines()

        # Parse load average from uptime (first line)
        load_avg = None
        cpu_percent = None
        mem_used = None
        mem_total = None
        mem_percent = None
        processes = []

        try:
            # Load average: parse "load average: 0.52, 0.58, 0.59"
            uptime_line = lines[0]
            if "load average:" in uptime_line:
                load_part = uptime_line.split("load average:")[1].strip()
                loads = [float(x.strip()) for x in load_part.split(",")[:3]]
                load_avg = tuple(loads) if len(loads) == 3 else None
        except (IndexError, ValueError) as e:
            logger.debug(f"Failed to parse load average: {e}")

        try:
            # Memory: parse "Mem:" line from free -m
            for line in lines[1:6]:  # free output is typically lines 2-4
                if line.startswith("Mem:"):
                    parts = line.split()
                    mem_total = int(parts[1])
                    mem_used = int(parts[2])
                    mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0.0
                    break
        except (IndexError, ValueError) as e:
            logger.debug(f"Failed to parse memory: {e}")

        try:
            # CPU: Calculate from top output (sum of all process CPU%)
            # Also extract top 3 processes
            in_process_list = False
            for line in lines:
                # Skip until we find the header line
                if "PID" in line and "USER" in line and "COMMAND" in line:
                    in_process_list = True
                    continue

                if in_process_list and line.strip():
                    parts = line.split()
                    if len(parts) >= 11:  # Standard top output has 12 columns
                        try:
                            pid = parts[0]
                            user = parts[1]
                            cpu = parts[8]  # %CPU column
                            mem = parts[9]  # %MEM column
                            command = " ".join(parts[11:])  # COMMAND and args

                            # Add to top processes (limit to 3)
                            if len(processes) < 3 and float(cpu) > 0.0:
                                processes.append(
                                    {
                                        "pid": pid,
                                        "user": user,
                                        "cpu": cpu,
                                        "mem": mem,
                                        "command": command[:40],  # Truncate long commands
                                    }
                                )
                        except (ValueError, IndexError):
                            continue

            # Calculate total CPU (sum of top 3 processes as approximation)
            if processes:
                cpu_percent = sum(float(p["cpu"]) for p in processes)

        except Exception as e:
            logger.debug(f"Failed to parse processes: {e}")

        return load_avg, cpu_percent, mem_used, mem_total, mem_percent, processes

    def collect_all_metrics(self) -> list[VMMetrics]:
        """Collect metrics from all VMs in parallel.

        Returns:
            List of VMMetrics objects
        """
        if not self.ssh_configs:
            return []

        metrics = []
        num_workers = min(self.max_workers, len(self.ssh_configs))

        logger.debug(f"Collecting metrics from {len(self.ssh_configs)} VMs")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            future_to_config = {
                executor.submit(self.collect_vm_metrics, config, self.timeout): config
                for config in self.ssh_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    metric = future.result()
                    metrics.append(metric)
                except Exception as e:
                    logger.error(f"Failed on {config.host}: {e}")
                    metrics.append(
                        VMMetrics(
                            vm_name=config.host,
                            success=False,
                            load_avg=None,
                            cpu_percent=None,
                            memory_used_mb=None,
                            memory_total_mb=None,
                            memory_percent=None,
                            top_processes=None,
                            error_message=str(e),
                        )
                    )

        return metrics

    def _create_dashboard_table(self, metrics: list[VMMetrics]) -> Table:
        """Create rich Table for dashboard display.

        Args:
            metrics: List of VMMetrics objects

        Returns:
            Rich Table object
        """
        table = Table(
            title=f"Distributed VM Metrics (updates every {self.interval}s)",
            show_header=True,
        )

        # Add columns
        table.add_column("VM", style="cyan", no_wrap=True)
        table.add_column("Status", style="green")
        table.add_column("Load (1/5/15)", style="yellow")
        table.add_column("CPU %", style="magenta")
        table.add_column("Memory", style="blue")
        table.add_column("Top Process", style="white")

        # Sort metrics by VM name for consistent ordering
        sorted_metrics = sorted(metrics, key=lambda m: m.vm_name)

        for metric in sorted_metrics:
            if not metric.success:
                # Error row
                table.add_row(
                    metric.vm_name,
                    "[red]OFFLINE[/red]",
                    "—",
                    "—",
                    "—",
                    f"[red]{metric.error_message}[/red]",
                )
                continue

            # Success row
            status = "[green]ONLINE[/green]"

            # Load average
            load_str = (
                f"{metric.load_avg[0]:.2f} / {metric.load_avg[1]:.2f} / {metric.load_avg[2]:.2f}"
                if metric.load_avg
                else "—"
            )

            # CPU percent
            cpu_str = f"{metric.cpu_percent:.1f}%" if metric.cpu_percent is not None else "—"

            # Memory
            mem_str = "—"
            if metric.memory_used_mb is not None and metric.memory_total_mb is not None:
                mem_str = (
                    f"{metric.memory_used_mb}MB / {metric.memory_total_mb}MB "
                    f"({metric.memory_percent:.1f}%)"
                )

            # Top process
            top_proc_str = "—"
            if metric.top_processes and len(metric.top_processes) > 0:
                proc = metric.top_processes[0]
                top_proc_str = f"{proc['command'][:30]} (CPU: {proc['cpu']}%, MEM: {proc['mem']}%)"

            table.add_row(
                metric.vm_name,
                status,
                load_str,
                cpu_str,
                mem_str,
                top_proc_str,
            )

        return table

    def run_dashboard(self, iterations: int | None = None) -> None:
        """Run live-updating dashboard.

        Args:
            iterations: Number of iterations to run (None = infinite)

        Raises:
            KeyboardInterrupt: When user presses Ctrl+C to exit
        """
        try:
            iteration = 0

            with Live(console=self.console, refresh_per_second=1) as live:
                while iterations is None or iteration < iterations:
                    # Collect metrics
                    metrics = self.collect_all_metrics()

                    # Create table
                    table = self._create_dashboard_table(metrics)

                    # Update display
                    live.update(table)

                    # Wait for next iteration
                    if iterations is None or iteration < iterations - 1:
                        time.sleep(self.interval)

                    iteration += 1

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Dashboard stopped by user.[/yellow]")


def run_distributed_top(
    ssh_configs: list[SSHConfig],
    interval: int = 10,
    max_workers: int = 10,
    timeout: int = 5,
) -> None:
    """Run distributed top dashboard.

    Convenience function for running the dashboard with default settings.

    Args:
        ssh_configs: List of SSH configurations for VMs
        interval: Refresh interval in seconds (default 10)
        max_workers: Maximum parallel workers (default 10)
        timeout: SSH timeout per VM in seconds (default 5)
    """
    executor = DistributedTopExecutor(
        ssh_configs=ssh_configs,
        interval=interval,
        max_workers=max_workers,
        timeout=timeout,
    )
    executor.run_dashboard()


__all__ = [
    "DistributedTopError",
    "DistributedTopExecutor",
    "VMMetrics",
    "run_distributed_top",
]
