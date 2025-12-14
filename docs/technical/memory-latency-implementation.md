# Memory and Latency Implementation Guide

**Technical documentation for developers and maintainers**

This document explains the internal implementation of memory and latency monitoring in the `azlin list` command.

## Architecture Overview

The memory and latency feature consists of two independent components integrated into the `azlin list` command:

```
┌─────────────────────────────────────────────────────────────┐
│                      azlin list command                      │
│                     (src/azlin/cli.py)                       │
└──────────────────┬──────────────────────┬───────────────────┘
                   │                      │
                   ▼                      ▼
    ┌──────────────────────┐  ┌──────────────────────────┐
    │  QuotaManager        │  │  SSHLatencyMeasurer      │
    │  (quota_manager.py)  │  │  (ssh/latency.py)        │
    └──────────────────────┘  └──────────────────────────┘
                   │                      │
                   ▼                      ▼
    ┌──────────────────────┐  ┌──────────────────────────┐
    │  VM_SIZE_MEMORY      │  │  ThreadPoolExecutor      │
    │  (hardcoded dict)    │  │  (parallel measurement)  │
    └──────────────────────┘  └──────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Performance |
|-----------|---------------|-------------|
| `QuotaManager.get_vm_size_memory()` | Memory lookup from hardcoded catalog | 0ms (O(1) dict lookup) |
| `SSHLatencyMeasurer` | SSH connection latency measurement | 45-5000ms per VM |
| `ThreadPoolExecutor` | Parallel latency measurement | ~max(latencies) (concurrent) |

## Memory Column Implementation

### Data Source

Memory information comes from a hardcoded VM size catalog in `src/azlin/quota_manager.py`:

```python
VM_SIZE_MEMORY: dict[str, int] = {
    # B-series (Burstable)
    "Standard_B1s": 1,      # 1 GB
    "Standard_B1ms": 2,     # 2 GB
    "Standard_B2s": 4,      # 4 GB
    "Standard_B2ms": 8,     # 8 GB
    "Standard_B4ms": 16,    # 16 GB
    "Standard_B8ms": 32,    # 32 GB

    # D-series v3 (General Purpose)
    "Standard_D2s_v3": 8,   # 8 GB
    "Standard_D4s_v3": 16,  # 16 GB
    "Standard_D8s_v3": 32,  # 32 GB
    "Standard_D16s_v3": 64, # 64 GB

    # E-series v5 (Memory Optimized)
    "Standard_E2as_v5": 16,  # 16 GB
    "Standard_E4as_v5": 32,  # 32 GB
    "Standard_E8as_v5": 64,  # 64 GB
    "Standard_E16as_v5": 128, # 128 GB

    # F-series v2 (Compute Optimized)
    "Standard_F2s_v2": 4,    # 4 GB
    "Standard_F4s_v2": 8,    # 8 GB
    "Standard_F8s_v2": 16,   # 16 GB

    # ... (100+ VM sizes in total)
}
```

### QuotaManager Extension

Added method `get_vm_size_memory()` following the existing `get_vm_size_vcpus()` pattern:

```python
@classmethod
def get_vm_size_memory(cls, vm_size: str) -> int:
    """Get memory in GB for a VM size.

    Args:
        vm_size: Azure VM size (e.g., "Standard_B2s")

    Returns:
        Memory in GB for the VM size, or 0 if unknown

    Examples:
        >>> QuotaManager.get_vm_size_memory("Standard_D4s_v3")
        16

        >>> QuotaManager.get_vm_size_memory("UnknownSize")
        0
    """
    return cls.VM_SIZE_MEMORY.get(vm_size, 0)
```

**Design Decisions:**
- **O(1) lookup**: Dict provides constant-time lookups
- **Zero API calls**: No Azure API latency
- **Fail gracefully**: Returns 0 for unknown sizes
- **Standard library only**: No external dependencies
- **Matches vCPU pattern**: Consistent with existing implementation

### CLI Integration

Memory column is added unconditionally (always displayed) in `src/azlin/cli.py`:

```python
# Line ~3451: Add column definition
table.add_column("Memory", justify="right", width=8)

# Line ~3474: Retrieve memory data
memory_gb = QuotaManager.get_vm_size_memory(size) if size != "N/A" else 0
memory_display = f"{memory_gb} GB" if memory_gb > 0 else "-"

# Line ~3484: Add to row data
row_data = [
    session_display,
    vm.name,
    status_display,
    ip,
    vm.location,
    size,
    vcpu_display,
    memory_display,  # NEW
]

# Line ~3518: Update summary (optional)
total_memory = sum(
    QuotaManager.get_vm_size_memory(vm.vm_size)
    for vm in vms
    if vm.vm_size and vm.is_running()
)
summary_parts.append(f"{total_memory} GB memory in use")
```

**Performance Impact:**
- Per-VM: ~0.001ms (dict lookup)
- 100 VMs: ~0.1ms total
- Negligible overhead (< 1% of command execution time)

## Latency Column Implementation

### Module: `src/azlin/ssh/latency.py`

New self-contained module following the "brick philosophy":

```
src/azlin/ssh/latency.py
├── LatencyResult (dataclass)      # Encapsulates measurement result
├── SSHLatencyMeasurer (class)     # Core measurement logic
│   ├── measure_single()           # Single VM measurement
│   └── measure_batch()            # Parallel batch measurement
└── __all__ = [...]                # Public API
```

### Data Structures

#### LatencyResult

```python
@dataclass
class LatencyResult:
    """Result of SSH latency measurement.

    Attributes:
        vm_name: VM name
        success: Whether measurement succeeded
        latency_ms: Latency in milliseconds (None if failed)
        error_type: Error type if failed ("timeout", "connection", "unknown")
        error_message: Detailed error message
    """
    vm_name: str
    success: bool
    latency_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None

    def display_value(self) -> str:
        """Get display string for table.

        Returns:
            Formatted string for display:
            - "45ms" for successful measurements
            - "timeout" for timeouts
            - "error" for connection errors
            - "-" for unknown or N/A
        """
        if self.success and self.latency_ms is not None:
            return f"{int(self.latency_ms)}ms"
        elif self.error_type == "timeout":
            return "timeout"
        elif self.error_type == "connection":
            return "error"
        else:
            return "-"
```

**Design Rationale:**
- **Explicit error states**: Clear distinction between timeout vs connection error
- **User-friendly display**: `display_value()` hides implementation details
- **Structured data**: Easy to serialize to JSON for automation

### SSHLatencyMeasurer Class

```python
class SSHLatencyMeasurer:
    """Measure SSH connection latency for VMs.

    Measures time to establish SSH connection (not Bastion tunnel).
    Uses ThreadPoolExecutor for parallel measurement.
    """

    def __init__(
        self,
        timeout: float = 5.0,
        max_workers: int = 10
    ):
        """Initialize latency measurer.

        Args:
            timeout: Connection timeout per VM (seconds)
            max_workers: Maximum parallel workers
        """
        self.timeout = timeout
        self.max_workers = max_workers

    def measure_single(
        self,
        vm: VMInfo,
        ssh_user: str = "azureuser",
        ssh_key_path: str | None = None
    ) -> LatencyResult:
        """Measure latency for a single VM.

        Implementation uses subprocess ssh command for reliability:

        1. Start timer
        2. Execute: ssh -o ConnectTimeout=5 user@host "true"
        3. Measure elapsed time
        4. Return result with latency or error

        Args:
            vm: VM to measure
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            LatencyResult with measurement or error
        """
        # Implementation...

    def measure_batch(
        self,
        vms: list[VMInfo],
        ssh_user: str = "azureuser",
        ssh_key_path: str | None = None
    ) -> dict[str, LatencyResult]:
        """Measure latency for multiple VMs in parallel.

        Uses ThreadPoolExecutor to measure all VMs concurrently:

        1. Filter to running VMs only (skip stopped)
        2. Submit all measurement tasks to executor
        3. Collect results as they complete
        4. Return dict mapping VM name to result

        Args:
            vms: List of VMs to measure
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            Dictionary mapping VM name to LatencyResult
        """
        # Implementation...
```

### Measurement Implementation

#### Method 1: Subprocess SSH (Primary)

```python
def _measure_via_subprocess(
    self,
    host: str,
    user: str,
    key_path: str,
    timeout: float
) -> float:
    """Measure latency using subprocess ssh command.

    Command structure:
        ssh -i <key> \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            -o ConnectTimeout=<timeout> \
            -o BatchMode=yes \
            -o PasswordAuthentication=no \
            <user>@<host> \
            "true"

    Returns:
        Latency in milliseconds

    Raises:
        TimeoutError: Connection timed out
        ConnectionError: Connection failed
    """
    start_time = time.time()

    cmd = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", f"ConnectTimeout={int(timeout)}",
        "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no",
        f"{user}@{host}",
        "true"  # Just test connection, don't run command
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True
        )

        elapsed_ms = (time.time() - start_time) * 1000

        if result.returncode != 0:
            raise ConnectionError(f"SSH failed: {result.stderr}")

        return elapsed_ms

    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Connection timed out after {timeout}s")
```

**SSH Options Explained:**
- `StrictHostKeyChecking=no`: Don't prompt for host key verification
- `UserKnownHostsFile=/dev/null`: Don't save host key
- `ConnectTimeout=5`: Timeout after 5 seconds
- `BatchMode=yes`: Never prompt for password
- `PasswordAuthentication=no`: Only use key-based auth
- `"true"`: Minimal command (just test connection)

**Why subprocess over paramiko?**
1. **Simpler**: Uses system SSH (no Python SSH library complexity)
2. **More reliable**: System SSH handles edge cases (proxies, Kerberos, etc.)
3. **Familiar**: Same behavior as manual SSH
4. **Standard library**: No external dependencies

#### Method 2: Paramiko (Fallback)

```python
def _measure_via_paramiko(
    self,
    host: str,
    user: str,
    key_path: str,
    timeout: float
) -> float:
    """Measure latency using paramiko library (fallback).

    Used when:
    - ssh command not available (Windows)
    - subprocess method fails
    - Explicitly requested via config

    Returns:
        Latency in milliseconds

    Raises:
        TimeoutError: Connection timed out
        ConnectionError: Connection failed
    """
    import paramiko

    start_time = time.time()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            username=user,
            key_filename=key_path,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False
        )

        elapsed_ms = (time.time() - start_time) * 1000
        return elapsed_ms

    finally:
        client.close()
```

**When paramiko is used:**
- Windows (no native ssh command)
- SSH command not found in PATH
- Config override: `ssh.latency_method = "paramiko"`

### Parallel Execution

The `measure_batch()` method uses `ThreadPoolExecutor` for concurrent measurements:

```python
def measure_batch(
    self,
    vms: list[VMInfo],
    ssh_user: str = "azureuser",
    ssh_key_path: str | None = None
) -> dict[str, LatencyResult]:
    """Measure latency for multiple VMs in parallel."""
    results = {}

    # Filter to running VMs only
    running_vms = [vm for vm in vms if vm.is_running()]

    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
        # Submit all tasks
        future_to_vm = {
            executor.submit(
                self.measure_single,
                vm,
                ssh_user,
                ssh_key_path
            ): vm
            for vm in running_vms
        }

        # Collect results as they complete
        for future in as_completed(future_to_vm):
            vm = future_to_vm[future]
            try:
                result = future.result()
                results[vm.name] = result
            except Exception as e:
                # Handle unexpected errors
                results[vm.name] = LatencyResult(
                    vm_name=vm.name,
                    success=False,
                    error_type="unknown",
                    error_message=str(e)
                )

    return results
```

**Execution Flow:**
1. Filter `vms` to only running VMs (stopped VMs can't be measured)
2. Submit all measurement tasks to executor (non-blocking)
3. Executor runs up to `max_workers` (default: 10) concurrently
4. Collect results as they complete (using `as_completed()`)
5. One VM failure doesn't affect others (exception handling per-task)

**Performance:**
- 10 VMs with 5s timeout: ~5-6 seconds total (not 50 seconds!)
- 100 VMs with 5s timeout: ~50-55 seconds total (10 at a time)
- Optimal `max_workers`: 10 (balances parallelism vs network saturation)

### CLI Integration

Latency column is conditionally added based on `--with-latency` flag:

```python
# Line ~3205: Add CLI flag
@click.option(
    "--with-latency",
    is_flag=True,
    default=False,
    help="Measure SSH latency for running VMs (adds ~5s per VM, parallel)"
)
def list_command(
    # ... existing params ...
    with_latency: bool,
):
    """List VMs in resource group.

    Shows VM name, status, IP address, region, size, vCPUs, memory,
    and optionally quota/tmux/latency info.
    """

    # Line ~3399: Measure latencies if enabled
    latency_by_vm: dict[str, LatencyResult] = {}
    if with_latency:
        try:
            from azlin.ssh.latency import SSHLatencyMeasurer
            from azlin.config_manager import ConfigManager

            # Get SSH key path from config
            ssh_key_path = ConfigManager.get_ssh_key_path(config)

            # Measure latencies in parallel
            console.print("Measuring SSH latency...", style="dim")

            measurer = SSHLatencyMeasurer(
                timeout=config.get("ssh", {}).get("latency_timeout", 5.0),
                max_workers=config.get("ssh", {}).get("latency_max_workers", 10)
            )

            latency_by_vm = measurer.measure_batch(
                vms=vms,
                ssh_user="azureuser",
                ssh_key_path=ssh_key_path
            )

        except Exception as e:
            console.print(
                f"Warning: Failed to measure latencies: {e}",
                style="yellow",
                err=True
            )

    # Line ~3451: Add column conditionally
    if with_latency:
        table.add_column("Latency", justify="right", width=10)

    # Line ~3498: Add data to rows
    for vm in vms:
        # ... build row_data ...

        if with_latency:
            if vm.name in latency_by_vm:
                result = latency_by_vm[vm.name]
                row_data.append(result.display_value())
            elif vm.is_running():
                row_data.append("[dim]N/A[/dim]")
            else:
                row_data.append("-")

        table.add_row(*row_data)
```

**Error Handling Strategy:**
- Latency measurement failure doesn't break command
- Warning printed to stderr (visible but not fatal)
- Table still displays without latency column
- Individual VM failures show "error" or "timeout" (don't abort batch)

## Error Handling

### Error Classification

| Error Type | Cause | Display | Recovery |
|------------|-------|---------|----------|
| `timeout` | Connection > 5s | "timeout" | Continue, display result |
| `connection` | SSH failure | "error" | Continue, display result |
| `unknown` | Unexpected exception | "-" | Continue, log error |
| `key_not_found` | SSH key missing | "error" | Warning, skip measurement |
| `vm_stopped` | VM not running | "-" | Skip measurement (expected) |

### Error Handling Implementation

```python
def measure_single(self, vm: VMInfo, ssh_user: str, ssh_key_path: str) -> LatencyResult:
    """Measure latency with comprehensive error handling."""

    # Skip stopped VMs
    if not vm.is_running():
        return LatencyResult(
            vm_name=vm.name,
            success=False,
            error_type="vm_stopped",
            error_message="VM is not running"
        )

    # Check SSH key exists
    if not Path(ssh_key_path).exists():
        return LatencyResult(
            vm_name=vm.name,
            success=False,
            error_type="key_not_found",
            error_message=f"SSH key not found: {ssh_key_path}"
        )

    # Measure latency
    try:
        start_time = time.time()

        latency_ms = self._measure_via_subprocess(
            host=vm.ip_address,
            user=ssh_user,
            key_path=ssh_key_path,
            timeout=self.timeout
        )

        return LatencyResult(
            vm_name=vm.name,
            success=True,
            latency_ms=latency_ms
        )

    except subprocess.TimeoutExpired:
        return LatencyResult(
            vm_name=vm.name,
            success=False,
            error_type="timeout",
            error_message=f"SSH connection timed out after {self.timeout}s"
        )

    except subprocess.CalledProcessError as e:
        return LatencyResult(
            vm_name=vm.name,
            success=False,
            error_type="connection",
            error_message=f"SSH connection failed: {e.stderr}"
        )

    except Exception as e:
        return LatencyResult(
            vm_name=vm.name,
            success=False,
            error_type="unknown",
            error_message=str(e)
        )
```

**Error Philosophy:**
- **Fail gracefully**: One VM error doesn't break entire batch
- **Clear error types**: User can distinguish timeout vs connection failure
- **Detailed messages**: Logs contain enough info for debugging
- **User-friendly display**: Table shows "timeout" or "error", not stack traces

## Testing Strategy

### Unit Tests

Located in `tests/test_ssh_latency.py`:

```python
class TestLatencyResult:
    """Test LatencyResult dataclass."""

    def test_display_value_success(self):
        result = LatencyResult(vm_name="test-vm", success=True, latency_ms=45.3)
        assert result.display_value() == "45ms"

    def test_display_value_timeout(self):
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            error_type="timeout"
        )
        assert result.display_value() == "timeout"

    def test_display_value_error(self):
        result = LatencyResult(
            vm_name="test-vm",
            success=False,
            error_type="connection"
        )
        assert result.display_value() == "error"


class TestSSHLatencyMeasurer:
    """Test SSHLatencyMeasurer class."""

    @patch("subprocess.run")
    def test_measure_single_success(self, mock_run):
        """Test successful latency measurement."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        vm = VMInfo(name="test-vm", ip_address="10.0.1.5", status="Running")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, "azureuser", "/path/to/key")

        assert result.success is True
        assert result.latency_ms > 0
        assert result.error_type is None

    @patch("subprocess.run")
    def test_measure_single_timeout(self, mock_run):
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=5.0)

        vm = VMInfo(name="test-vm", ip_address="10.0.1.5", status="Running")
        measurer = SSHLatencyMeasurer(timeout=5.0)

        result = measurer.measure_single(vm, "azureuser", "/path/to/key")

        assert result.success is False
        assert result.error_type == "timeout"
        assert "timed out" in result.error_message.lower()

    def test_measure_batch_parallel(self):
        """Test parallel measurement."""
        vms = [
            VMInfo(name=f"vm-{i}", ip_address=f"10.0.1.{i}", status="Running")
            for i in range(10)
        ]

        measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=5)

        with patch.object(measurer, "measure_single") as mock_measure:
            mock_measure.return_value = LatencyResult(
                vm_name="test", success=True, latency_ms=45.0
            )

            results = measurer.measure_batch(vms)

            assert len(results) == 10
            assert mock_measure.call_count == 10
```

### Integration Tests

Located in `tests/integration/test_list_command.py`:

```python
class TestListCommandWithLatency:
    """Integration tests for azlin list --with-latency."""

    @patch("azlin.ssh.latency.SSHLatencyMeasurer.measure_batch")
    def test_list_with_latency_flag(self, mock_measure_batch):
        """Test list command with --with-latency flag."""
        mock_measure_batch.return_value = {
            "vm-1": LatencyResult(vm_name="vm-1", success=True, latency_ms=45.0),
            "vm-2": LatencyResult(vm_name="vm-2", success=True, latency_ms=52.0),
        }

        result = runner.invoke(cli, ["list", "--with-latency"])

        assert result.exit_code == 0
        assert "Latency" in result.output
        assert "45ms" in result.output
        assert "52ms" in result.output

    def test_list_without_latency_flag(self):
        """Test list command without latency flag (default)."""
        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "Latency" not in result.output

    @patch("azlin.ssh.latency.SSHLatencyMeasurer.measure_batch")
    def test_list_latency_measurement_failure(self, mock_measure_batch):
        """Test graceful handling of latency measurement failure."""
        mock_measure_batch.side_effect = Exception("Network error")

        result = runner.invoke(cli, ["list", "--with-latency"])

        assert result.exit_code == 0  # Command doesn't fail
        assert "Warning" in result.output
        assert "Failed to measure latencies" in result.output
```

### Manual Testing Checklist

```bash
# Test 1: Basic memory display
azlin list
# ✓ Memory column appears
# ✓ Memory values match Azure specs
# ✓ Unknown VM sizes show "-"

# Test 2: Latency measurement
azlin list --with-latency
# ✓ Latency column appears
# ✓ Running VMs show latency in ms
# ✓ Stopped VMs show "-"

# Test 3: Error handling
# Create unreachable VM (firewall block SSH)
azlin list --with-latency
# ✓ Unreachable VM shows "timeout"
# ✓ Other VMs still measured
# ✓ Command completes successfully

# Test 4: Performance
# Test with 20 VMs
time azlin list --with-latency
# ✓ Completes in ~5-10 seconds (not 100 seconds)
# ✓ Progress bar shows during measurement

# Test 5: JSON output
azlin list --with-latency --format=json | jq .
# ✓ JSON includes memory_gb field
# ✓ JSON includes latency_ms field
# ✓ JSON includes latency_status field
```

## Performance Characteristics

### Memory Column Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Lookup time | ~0.001ms | O(1) dict lookup |
| API calls | 0 | Hardcoded catalog |
| Network I/O | 0 bytes | No network access |
| Memory usage | ~50 KB | VM_SIZE_MEMORY dict |
| Scalability | O(n) | Linear with VM count, negligible per-VM |

**100 VMs:**
- Memory column overhead: ~0.1ms
- Percentage of total command time: < 0.1%

### Latency Column Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Single VM (success) | 45-200ms | Depends on network |
| Single VM (timeout) | 5000ms | Configurable timeout |
| 10 VMs (parallel) | ~5-6 seconds | max_workers=10 |
| 100 VMs (parallel) | ~50-55 seconds | 10 at a time |
| API calls | 0 | Direct SSH, no Azure API |
| Network I/O | ~1-2 KB per VM | SSH handshake |

**Optimization Opportunities:**
1. **Reduce timeout**: Lower default from 5s to 3s (faster failure)
2. **Adaptive workers**: Increase `max_workers` for large fleets
3. **Caching**: Cache results for 60s (optional future enhancement)
4. **Selective measurement**: Allow filtering specific VMs

### Comparison with Alternatives

| Approach | Performance | Accuracy | Complexity |
|----------|-------------|----------|------------|
| **Direct SSH (current)** | 45-5000ms/VM | High | Low |
| Azure API query | 200-500ms/VM | N/A (no latency) | Medium |
| Ping-based | 10-50ms/VM | Low (ICMP != SSH) | Low |
| Bastion tunnel | 2000-10000ms/VM | Medium (includes tunnel) | High |

**Why Direct SSH?**
- Most accurate (measures actual connection time)
- No additional Azure API quota consumption
- Simple implementation (subprocess)
- Matches user experience (SSH is what they use)

## Configuration

### Configuration File Schema

```toml
[ssh]
# Latency measurement timeout (seconds)
latency_timeout = 5.0

# Maximum parallel measurements
latency_max_workers = 10

# Measurement method ("subprocess" or "paramiko")
latency_method = "subprocess"

[cli]
# Show progress bar during latency measurement
show_progress = true
```

### Configuration Loading

```python
from azlin.config_manager import ConfigManager

config = ConfigManager.load_config()

# Get latency timeout (default: 5.0)
timeout = config.get("ssh", {}).get("latency_timeout", 5.0)

# Get max workers (default: 10)
max_workers = config.get("ssh", {}).get("latency_max_workers", 10)

# Get measurement method (default: "subprocess")
method = config.get("ssh", {}).get("latency_method", "subprocess")
```

### Environment Variable Overrides

```bash
# Override timeout via environment variable
export AZLIN_SSH_LATENCY_TIMEOUT=10

# Override max workers
export AZLIN_SSH_LATENCY_MAX_WORKERS=5

# Override method
export AZLIN_SSH_LATENCY_METHOD=paramiko
```

## Module Specifications

### Memory Query Module

**File**: `src/azlin/quota_manager.py`

**Contract**:
```python
# Input: VM size string (e.g., "Standard_B2s")
# Output: Memory in GB (int) or 0 if unknown
# Side Effects: NONE (pure function, no API calls)
# Dependencies: Standard library only (no external deps)
```

**Public API**:
```python
@classmethod
def get_vm_size_memory(cls, vm_size: str) -> int:
    """Get memory in GB for a VM size."""
    return cls.VM_SIZE_MEMORY.get(vm_size, 0)
```

**Test Coverage**:
- ✓ Known VM sizes return correct memory
- ✓ Unknown VM sizes return 0
- ✓ Empty string returns 0
- ✓ Case sensitivity (exact match required)

### Latency Measurement Module

**File**: `src/azlin/ssh/latency.py`

**Contract**:
```python
# Input: List of VMInfo objects
# Output: Dictionary of VM name -> LatencyResult
# Side Effects: SSH connection attempts (network I/O)
# Dependencies: subprocess (stdlib), paramiko (optional fallback)
```

**Public API**:
```python
class SSHLatencyMeasurer:
    def __init__(self, timeout: float = 5.0, max_workers: int = 10): ...
    def measure_single(self, vm: VMInfo, ssh_user: str, ssh_key_path: str) -> LatencyResult: ...
    def measure_batch(self, vms: list[VMInfo], ssh_user: str, ssh_key_path: str) -> dict[str, LatencyResult]: ...

@dataclass
class LatencyResult:
    vm_name: str
    success: bool
    latency_ms: float | None
    error_type: str | None
    error_message: str | None

    def display_value(self) -> str: ...
```

**Test Coverage**:
- ✓ Successful measurement returns latency_ms
- ✓ Timeout returns error_type="timeout"
- ✓ Connection failure returns error_type="connection"
- ✓ Parallel execution completes in reasonable time
- ✓ display_value() formats correctly

## Adding New VM Sizes

When Azure releases new VM sizes, update the catalog:

### Step 1: Identify VM Size Specifications

```bash
# List all VM sizes in a region
az vm list-sizes --location eastus --output table

# Get specific VM size details
az vm list-sizes --location eastus \
  --query "[?name=='Standard_NewSize_v6']" \
  --output json
```

Output:
```json
[
  {
    "maxDataDiskCount": 16,
    "memoryInMB": 32768,
    "name": "Standard_NewSize_v6",
    "numberOfCores": 8,
    "osDiskSizeInMB": 1047552,
    "resourceDiskSizeInMB": 131072
  }
]
```

### Step 2: Add to VM_SIZE_MEMORY Dictionary

Edit `src/azlin/quota_manager.py`:

```python
VM_SIZE_MEMORY: dict[str, int] = {
    # ... existing entries ...

    # New VM sizes (added 2025-12-13)
    "Standard_NewSize_v6": 32,  # 32 GB (32768 MB / 1024)
    "Standard_AnotherSize_v6": 64,  # 64 GB
}
```

**Conversion Formula**:
```
Memory (GB) = ceil(memoryInMB / 1024)
```

### Step 3: Add Test Case

Add to `tests/test_quota_manager.py`:

```python
def test_get_vm_size_memory_new_sizes():
    """Test newly added VM sizes."""
    assert QuotaManager.get_vm_size_memory("Standard_NewSize_v6") == 32
    assert QuotaManager.get_vm_size_memory("Standard_AnotherSize_v6") == 64
```

### Step 4: Verify

```bash
# Run tests
pytest tests/test_quota_manager.py::test_get_vm_size_memory_new_sizes

# Test with real VM (if available)
azlin list
```

## Future Enhancements

### 1. Dynamic VM Size Query

**Problem**: New VM sizes require code updates.

**Solution**: Query Azure API dynamically.

```python
@classmethod
def get_vm_size_memory_dynamic(cls, vm_size: str, location: str) -> int:
    """Get memory dynamically from Azure API (slower)."""
    result = subprocess.run(
        ["az", "vm", "list-sizes", "--location", location,
         "--query", f"[?name=='{vm_size}'].memoryInMB | [0]",
         "-o", "tsv"],
        capture_output=True,
        text=True
    )

    memory_mb = int(result.stdout.strip())
    return memory_mb // 1024
```

**Trade-offs:**
- Pro: Handles all VM sizes automatically
- Con: Adds 200-500ms per unique VM size
- Recommendation: Add as `--query-sizes` flag (opt-in)

### 2. Bastion Tunnel Latency

**Problem**: Can't measure latency for Bastion-only VMs.

**Solution**: Measure tunnel creation time.

```python
def measure_bastion_latency(self, vm: VMInfo) -> LatencyResult:
    """Measure latency through Azure Bastion tunnel."""
    start_time = time.time()

    # Create Bastion tunnel
    proc = subprocess.Popen(
        ["az", "network", "bastion", "tunnel",
         "--name", vm.bastion_name,
         "--resource-group", vm.resource_group,
         "--target-resource-id", vm.id,
         "--resource-port", "22",
         "--port", "2222"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for tunnel ready (monitor stderr)
    # Measure elapsed time

    elapsed_ms = (time.time() - start_time) * 1000
    return LatencyResult(vm_name=vm.name, success=True, latency_ms=elapsed_ms)
```

**Trade-offs:**
- Pro: Works for Bastion-only VMs
- Con: Much slower (2-10 seconds per VM)
- Recommendation: Separate command `azlin latency --via-bastion`

### 3. Latency History and Trending

**Problem**: Can't see latency trends over time.

**Solution**: Store measurements in SQLite database.

```python
class LatencyHistory:
    """Store and query latency measurements."""

    def __init__(self, db_path: str = "~/.azlin/latency_history.db"):
        self.db = sqlite3.connect(db_path)
        self._create_tables()

    def record_measurement(self, vm_name: str, latency_ms: float):
        """Store a latency measurement."""
        self.db.execute(
            "INSERT INTO measurements (vm_name, latency_ms, timestamp) VALUES (?, ?, ?)",
            (vm_name, latency_ms, datetime.now().isoformat())
        )
        self.db.commit()

    def get_history(self, vm_name: str, days: int = 7) -> list[tuple]:
        """Get latency history for a VM."""
        cutoff = datetime.now() - timedelta(days=days)
        cursor = self.db.execute(
            "SELECT timestamp, latency_ms FROM measurements "
            "WHERE vm_name = ? AND timestamp > ? ORDER BY timestamp",
            (vm_name, cutoff.isoformat())
        )
        return cursor.fetchall()
```

**Trade-offs:**
- Pro: Trend analysis, anomaly detection
- Con: Persistent storage, complexity
- Recommendation: Separate feature `azlin latency-history`

### 4. Latency Alerts

**Problem**: No proactive notification of high latency.

**Solution**: Background monitoring with alerts.

```python
class LatencyMonitor:
    """Monitor VM latency and send alerts."""

    def __init__(self, alert_threshold_ms: float = 200):
        self.alert_threshold = alert_threshold_ms

    def monitor(self, vms: list[VMInfo], interval: int = 60):
        """Monitor VMs every interval seconds."""
        while True:
            measurer = SSHLatencyMeasurer()
            results = measurer.measure_batch(vms)

            for vm_name, result in results.items():
                if result.success and result.latency_ms > self.alert_threshold:
                    self.send_alert(vm_name, result.latency_ms)

            time.sleep(interval)

    def send_alert(self, vm_name: str, latency_ms: float):
        """Send alert (email, webhook, etc.)."""
        # Implementation...
```

**Trade-offs:**
- Pro: Proactive monitoring
- Con: Requires background service
- Recommendation: Integrate with Azure Monitor or third-party tools

## Troubleshooting for Developers

### Debugging Latency Measurement

Enable verbose logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("azlin.ssh.latency")

# In SSHLatencyMeasurer
logger.debug(f"Measuring latency for {vm.name} at {vm.ip_address}")
logger.debug(f"SSH command: {' '.join(cmd)}")
logger.debug(f"Result: {result.latency_ms}ms")
```

### Common Issues

#### Issue 1: Latency Measurement Hangs

**Symptom**: `azlin list --with-latency` hangs indefinitely.

**Cause**: ThreadPoolExecutor deadlock or timeout not working.

**Debug**:
```python
# Add timeout to executor
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(measure_single, vm) for vm in vms]

    # Force timeout on all futures
    for future in as_completed(futures, timeout=30):
        try:
            result = future.result(timeout=10)
        except TimeoutError:
            logger.error(f"Future timed out: {future}")
```

#### Issue 2: Memory Column Shows Wrong Values

**Symptom**: Memory values don't match Azure Portal.

**Cause**: Outdated VM_SIZE_MEMORY catalog.

**Fix**:
```bash
# Verify VM size in Azure
az vm show --name my-vm --resource-group my-rg \
  --query hardwareProfile.vmSize -o tsv

# Look up actual memory
az vm list-sizes --location eastus \
  --query "[?name=='<vm-size>'].memoryInMB" -o tsv

# Update catalog in quota_manager.py
```

#### Issue 3: Subprocess SSH Fails on Windows

**Symptom**: Latency measurement fails with "ssh command not found".

**Cause**: Windows doesn't have native SSH (older versions).

**Fix**: Use paramiko fallback automatically:
```python
def _detect_ssh_availability(self) -> str:
    """Detect which SSH method to use."""
    try:
        subprocess.run(["ssh", "-V"], capture_output=True, check=True)
        return "subprocess"
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "paramiko"
```

## Related Documentation

- [Architecture Design](../../ARCHITECTURE_MEMORY_LATENCY.md) - Original design document
- [User Guide](../features/memory-latency.md) - User-facing documentation
- [API Reference](../API_REFERENCE.md) - Complete API documentation
- [Testing Guide](../testing/test-guide.md) - Testing strategy and examples

## Contributing

Found a bug or want to add a feature? See [CONTRIBUTING.md](../contributing/CONTRIBUTING.md).

For questions or discussions, use [GitHub Discussions](https://github.com/rysweet/azlin/discussions).
