"""Batch executor module for operating on multiple VMs.

This module provides batch operations on multiple VMs:
- VM selection by tags, patterns, or all
- Parallel execution with progress tracking
- Per-VM error handling
- Result aggregation

Security:
- Input validation for tags and patterns
- No shell=True in subprocess calls
- Timeout enforcement
- Resource limits (max_workers)
"""

import fnmatch
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from azlin.modules.home_sync import HomeSyncManager
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.remote_exec import RemoteExecutor
from azlin.vm_lifecycle_control import VMLifecycleController
from azlin.vm_manager import VMInfo

logger = logging.getLogger(__name__)


class BatchExecutorError(Exception):
    """Raised when batch operations fail."""

    pass


@dataclass
class TagFilter:
    """Tag filter for VM selection."""

    key: str
    value: str

    @classmethod
    def parse(cls, tag_str: str) -> "TagFilter":
        """Parse tag string in format 'key=value'.

        Args:
            tag_str: Tag string to parse

        Returns:
            TagFilter instance

        Raises:
            BatchExecutorError: If tag format is invalid
        """
        if "=" not in tag_str:
            raise BatchExecutorError(f"Invalid tag format: '{tag_str}'. Expected 'key=value'")

        # Split on first = only
        parts = tag_str.split("=", 1)
        key = parts[0].strip()
        value = parts[1].strip()

        if not key:
            raise BatchExecutorError(f"Invalid tag format: '{tag_str}'. Key cannot be empty")

        return cls(key=key, value=value)

    def matches(self, vm: VMInfo) -> bool:
        """Check if VM matches this tag filter.

        Args:
            vm: VM to check

        Returns:
            True if VM has matching tag
        """
        if not vm.tags:
            return False
        return vm.tags.get(self.key) == self.value


@dataclass
class BatchOperationResult:
    """Result of a batch operation on a single VM."""

    vm_name: str
    success: bool
    message: str
    output: str | None = None
    duration: float = 0.0


class BatchResult:
    """Aggregated results from batch operation."""

    def __init__(self, results: list[BatchOperationResult]):
        """Initialize batch result.

        Args:
            results: List of operation results
        """
        self.results = results

    @property
    def total(self) -> int:
        """Total number of operations."""
        return len(self.results)

    @property
    def succeeded(self) -> int:
        """Number of successful operations."""
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        """Number of failed operations."""
        return sum(1 for r in self.results if not r.success)

    @property
    def all_succeeded(self) -> bool:
        """Check if all operations succeeded."""
        return all(r.success for r in self.results) if self.results else True

    def get_failures(self) -> list[BatchOperationResult]:
        """Get only failed results."""
        return [r for r in self.results if not r.success]

    def get_successes(self) -> list[BatchOperationResult]:
        """Get only successful results."""
        return [r for r in self.results if r.success]

    def format_summary(self) -> str:
        """Format summary of results."""
        return f"Total: {self.total}, Succeeded: {self.succeeded}, Failed: {self.failed}"


class BatchSelector:
    """VM selection logic for batch operations."""

    @staticmethod
    def select_by_tag(vms: list[VMInfo], tag_filter: str) -> list[VMInfo]:
        """Select VMs by tag filter.

        Args:
            vms: List of VMs to filter
            tag_filter: Tag filter string (format: key=value)

        Returns:
            List of matching VMs
        """
        tag = TagFilter.parse(tag_filter)
        return [vm for vm in vms if tag.matches(vm)]

    @staticmethod
    def select_by_pattern(vms: list[VMInfo], pattern: str) -> list[VMInfo]:
        """Select VMs by name pattern.

        Args:
            vms: List of VMs to filter
            pattern: Glob pattern for VM names

        Returns:
            List of matching VMs
        """
        return [vm for vm in vms if fnmatch.fnmatch(vm.name, pattern)]

    @staticmethod
    def select_all(vms: list[VMInfo]) -> list[VMInfo]:
        """Select all VMs.

        Args:
            vms: List of VMs

        Returns:
            All VMs
        """
        return vms

    @staticmethod
    def select_running_only(vms: list[VMInfo]) -> list[VMInfo]:
        """Select only running VMs.

        Args:
            vms: List of VMs to filter

        Returns:
            List of running VMs
        """
        return [vm for vm in vms if vm.is_running()]


class BatchExecutor:
    """Execute operations on multiple VMs in parallel."""

    def __init__(self, max_workers: int = 10):
        """Initialize batch executor.

        Args:
            max_workers: Maximum number of parallel workers
        """
        self.max_workers = max_workers

    def execute_stop(
        self,
        vms: list[VMInfo],
        resource_group: str,
        deallocate: bool = True,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BatchOperationResult]:
        """Execute stop operation on multiple VMs.

        Args:
            vms: VMs to stop
            resource_group: Resource group name
            deallocate: Whether to deallocate VMs
            progress_callback: Optional progress callback

        Returns:
            List of operation results
        """
        if not vms:
            return []

        def stop_vm(vm: VMInfo) -> BatchOperationResult:
            """Stop a single VM."""
            import time

            start_time = time.time()

            try:
                if progress_callback:
                    progress_callback(f"Stopping {vm.name}...")

                result = VMLifecycleController.stop_vm(
                    vm_name=vm.name,
                    resource_group=resource_group,
                    deallocate=deallocate,
                    no_wait=False,
                )

                duration = time.time() - start_time

                if progress_callback:
                    status = "✓" if result.success else "✗"
                    progress_callback(f"{status} {vm.name}: {result.message}")

                return BatchOperationResult(
                    vm_name=vm.name,
                    success=result.success,
                    message=result.message,
                    duration=duration,
                )
            except Exception as e:
                duration = time.time() - start_time
                if progress_callback:
                    progress_callback(f"✗ {vm.name}: {e!s}")

                return BatchOperationResult(
                    vm_name=vm.name, success=False, message=str(e), duration=duration
                )

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(stop_vm, vm): vm for vm in vms}
            return [future.result() for future in as_completed(futures)]

    def execute_start(
        self,
        vms: list[VMInfo],
        resource_group: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BatchOperationResult]:
        """Execute start operation on multiple VMs.

        Args:
            vms: VMs to start
            resource_group: Resource group name
            progress_callback: Optional progress callback

        Returns:
            List of operation results
        """
        if not vms:
            return []

        def start_vm(vm: VMInfo) -> BatchOperationResult:
            """Start a single VM."""
            import time

            start_time = time.time()

            try:
                if progress_callback:
                    progress_callback(f"Starting {vm.name}...")

                result = VMLifecycleController.start_vm(
                    vm_name=vm.name, resource_group=resource_group, no_wait=False
                )

                duration = time.time() - start_time

                if progress_callback:
                    status = "✓" if result.success else "✗"
                    progress_callback(f"{status} {vm.name}: {result.message}")

                return BatchOperationResult(
                    vm_name=vm.name,
                    success=result.success,
                    message=result.message,
                    duration=duration,
                )
            except Exception as e:
                duration = time.time() - start_time
                if progress_callback:
                    progress_callback(f"✗ {vm.name}: {e!s}")

                return BatchOperationResult(
                    vm_name=vm.name, success=False, message=str(e), duration=duration
                )

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(start_vm, vm): vm for vm in vms}
            return [future.result() for future in as_completed(futures)]

    def execute_command(
        self,
        vms: list[VMInfo],
        command: str,
        resource_group: str,
        timeout: int = 300,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BatchOperationResult]:
        """Execute command on multiple VMs.

        Args:
            vms: VMs to execute command on
            command: Command to execute
            resource_group: Resource group name
            timeout: Command timeout in seconds
            progress_callback: Optional progress callback

        Returns:
            List of operation results
        """
        if not vms:
            return []

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        def execute_on_vm(vm: VMInfo) -> BatchOperationResult:
            """Execute command on a single VM."""
            import time

            start_time = time.time()

            try:
                if progress_callback:
                    progress_callback(f"Executing on {vm.name}...")

                if not vm.public_ip:
                    raise Exception("VM has no public IP")

                ssh_config = SSHConfig(
                    host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
                )

                result = RemoteExecutor.execute_command(
                    ssh_config=ssh_config, command=command, timeout=timeout
                )

                duration = time.time() - start_time

                if progress_callback:
                    status = "✓" if result.success else "✗"
                    progress_callback(f"{status} {vm.name}: exit code {result.exit_code}")

                return BatchOperationResult(
                    vm_name=vm.name,
                    success=result.success,
                    message=f"Exit code: {result.exit_code}",
                    output=result.get_output(),
                    duration=duration,
                )
            except Exception as e:
                duration = time.time() - start_time
                if progress_callback:
                    progress_callback(f"✗ {vm.name}: {e!s}")

                return BatchOperationResult(
                    vm_name=vm.name, success=False, message=str(e), duration=duration
                )

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(execute_on_vm, vm): vm for vm in vms}
            return [future.result() for future in as_completed(futures)]

    def execute_sync(
        self,
        vms: list[VMInfo],
        resource_group: str,
        dry_run: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BatchOperationResult]:
        """Execute home sync on multiple VMs.

        Args:
            vms: VMs to sync to
            resource_group: Resource group name
            dry_run: Whether to perform dry run
            progress_callback: Optional progress callback

        Returns:
            List of operation results
        """
        if not vms:
            return []

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        def sync_to_vm(vm: VMInfo) -> BatchOperationResult:
            """Sync to a single VM."""
            import time

            start_time = time.time()

            try:
                if progress_callback:
                    progress_callback(f"Syncing to {vm.name}...")

                if not vm.public_ip:
                    raise Exception("VM has no public IP")

                ssh_config = SSHConfig(
                    host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
                )

                result = HomeSyncManager.sync_to_vm(ssh_config=ssh_config, dry_run=dry_run)

                duration = time.time() - start_time

                if progress_callback:
                    status = "✓" if result.success else "✗"
                    progress_callback(f"{status} {vm.name}: {result.files_synced} files")

                return BatchOperationResult(
                    vm_name=vm.name,
                    success=result.success,
                    message=f"Synced {result.files_synced} files",
                    duration=duration,
                )
            except Exception as e:
                duration = time.time() - start_time
                if progress_callback:
                    progress_callback(f"✗ {vm.name}: {e!s}")

                return BatchOperationResult(
                    vm_name=vm.name, success=False, message=str(e), duration=duration
                )

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(sync_to_vm, vm): vm for vm in vms}
            return [future.result() for future in as_completed(futures)]


@dataclass
class VMMetrics:
    """VM metrics for conditional execution and smart routing."""

    vm_name: str
    load_avg: tuple[float, float, float] | None  # 1min, 5min, 15min
    cpu_percent: float | None
    memory_percent: float | None
    is_idle: bool
    success: bool
    error: str | None = None

    def meets_condition(self, condition: str) -> bool:
        """Check if VM metrics meet specified condition.

        Args:
            condition: Condition string (e.g., 'idle', 'cpu<50', 'mem<80')

        Returns:
            True if condition is met

        Raises:
            BatchExecutorError: If condition format is invalid
        """
        if not self.success:
            return False

        condition = condition.lower().strip()

        # Idle condition
        if condition == "idle":
            return self.is_idle

        # CPU condition (e.g., 'cpu<50', 'cpu-below-50')
        if condition.startswith("cpu"):
            if self.cpu_percent is None:
                return False

            # Extract threshold
            if "<" in condition:
                threshold = float(condition.split("<")[1])
            elif "below" in condition:
                threshold = float(condition.split("-")[-1])
            else:
                raise BatchExecutorError(f"Invalid CPU condition format: {condition}")

            return self.cpu_percent < threshold

        # Memory condition (e.g., 'mem<80', 'memory-below-80')
        if condition.startswith(("mem", "memory")):
            if self.memory_percent is None:
                return False

            # Extract threshold
            if "<" in condition:
                threshold = float(condition.split("<")[1])
            elif "below" in condition:
                threshold = float(condition.split("-")[-1])
            else:
                raise BatchExecutorError(f"Invalid memory condition format: {condition}")

            return self.memory_percent < threshold

        raise BatchExecutorError(f"Unknown condition: {condition}")


class MetricsCollector:
    """Collect VM metrics for conditional execution."""

    @staticmethod
    def collect_metrics(vm: VMInfo, ssh_config: SSHConfig, timeout: int = 5) -> VMMetrics:
        """Collect metrics from a single VM.

        Args:
            vm: VM to collect metrics from
            ssh_config: SSH configuration
            timeout: Timeout in seconds

        Returns:
            VMMetrics object
        """
        try:
            # Collect metrics using remote command
            # Command collects: load avg, CPU %, memory %, idle status
            metrics_cmd = (
                "uptime | awk '{print $(NF-2), $(NF-1), $NF}' | tr -d ',' && "
                "top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}' && "
                "free | grep Mem | awk '{print ($3/$2) * 100.0}' && "
                "if [ $(w -h | wc -l) -eq 0 ]; then echo 'true'; else echo 'false'; fi"
            )

            result = RemoteExecutor.execute_command(
                ssh_config=ssh_config, command=metrics_cmd, timeout=timeout
            )

            if not result.success:
                return VMMetrics(
                    vm_name=vm.name,
                    load_avg=None,
                    cpu_percent=None,
                    memory_percent=None,
                    is_idle=False,
                    success=False,
                    error=f"Metrics collection failed: {result.stderr}",
                )

            # Parse output
            lines = result.stdout.strip().split("\n")
            if len(lines) < 4:
                return VMMetrics(
                    vm_name=vm.name,
                    load_avg=None,
                    cpu_percent=None,
                    memory_percent=None,
                    is_idle=False,
                    success=False,
                    error="Incomplete metrics output",
                )

            # Parse load average
            load_parts = lines[0].split()
            load_avg = (float(load_parts[0]), float(load_parts[1]), float(load_parts[2]))

            # Parse CPU percentage
            cpu_percent = float(lines[1].strip())

            # Parse memory percentage
            memory_percent = float(lines[2].strip())

            # Parse idle status
            is_idle = lines[3].strip().lower() == "true"

            return VMMetrics(
                vm_name=vm.name,
                load_avg=load_avg,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                is_idle=is_idle,
                success=True,
            )

        except Exception as e:
            logger.warning(f"Failed to collect metrics from {vm.name}: {e}")
            return VMMetrics(
                vm_name=vm.name,
                load_avg=None,
                cpu_percent=None,
                memory_percent=None,
                is_idle=False,
                success=False,
                error=str(e),
            )


class ConditionalExecutor:
    """Execute commands conditionally based on VM metrics."""

    def __init__(self, max_workers: int = 10):
        """Initialize conditional executor.

        Args:
            max_workers: Maximum number of parallel workers
        """
        self.max_workers = max_workers

    def filter_by_condition(
        self, vms: list[VMInfo], condition: str, resource_group: str
    ) -> tuple[list[VMInfo], dict[str, VMMetrics]]:
        """Filter VMs by condition after collecting metrics.

        Args:
            vms: VMs to filter
            condition: Condition to check (e.g., 'idle', 'cpu<50')
            resource_group: Resource group name

        Returns:
            Tuple of (filtered VMs, metrics dict)
        """
        if not vms:
            return [], {}

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # Collect metrics from all VMs in parallel
        metrics_dict = {}

        def collect_vm_metrics(vm: VMInfo) -> tuple[str, VMMetrics]:
            """Collect metrics from single VM."""
            if not vm.public_ip:
                return vm.name, VMMetrics(
                    vm_name=vm.name,
                    load_avg=None,
                    cpu_percent=None,
                    memory_percent=None,
                    is_idle=False,
                    success=False,
                    error="No public IP",
                )

            ssh_config = SSHConfig(
                host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
            )

            metrics = MetricsCollector.collect_metrics(vm, ssh_config)
            return vm.name, metrics

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(collect_vm_metrics, vm): vm for vm in vms}

            for future in as_completed(futures):
                vm_name, metrics = future.result()
                metrics_dict[vm_name] = metrics

        # Filter VMs by condition
        filtered_vms = []
        for vm in vms:
            metrics = metrics_dict.get(vm.name)
            if metrics and metrics.success and metrics.meets_condition(condition):
                filtered_vms.append(vm)

        return filtered_vms, metrics_dict


__all__ = [
    "BatchExecutor",
    "BatchExecutorError",
    "BatchOperationResult",
    "BatchResult",
    "BatchSelector",
    "ConditionalExecutor",
    "MetricsCollector",
    "TagFilter",
    "VMMetrics",
]
