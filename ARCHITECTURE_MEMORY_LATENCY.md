# Architecture Design: Memory and Latency Columns for `azlin list`

**Issue**: #484
**Branch**: feat/issue-484-memory-latency
**Date**: 2025-12-13
**Author**: Architect Agent

---

## Executive Summary

This document defines the architecture for adding two new columns to the `azlin list` command:
1. **Memory Column (GB)**: Always displayed, shows total VM memory from Azure API
2. **Latency Column (ms)**: Opt-in via `--with-latency` flag, measures SSH connection time

The design follows existing patterns in the codebase (particularly the vCPU column implementation) and maintains ruthless simplicity while ensuring robust error handling.

---

## 1. Current State Analysis

### 1.1 Existing Architecture

**Command Location**: `src/azlin/cli.py` (lines 3195-3564)
- The `list` command is a Click command function
- Uses `rich.Table` for formatted output
- Already displays: Session Name, VM Name, Status, IP, Region, Size, vCPUs, Tmux Sessions (optional)

**vCPU Pattern** (Reference Implementation):
```python
# Line 3451: Column definition
table.add_column("vCPUs", justify="right", width=6)

# Line 3472-3474: Data retrieval
vcpus = QuotaManager.get_vm_size_vcpus(size) if size != "N/A" else 0
vcpu_display = str(vcpus) if vcpus > 0 else "-"

# Line 3506-3510: Summary calculation
total_vcpus = sum(
    QuotaManager.get_vm_size_vcpus(vm.vm_size)
    for vm in vms
    if vm.vm_size and vm.is_running()
)
```

**QuotaManager Pattern** (`src/azlin/quota_manager.py`):
- Hardcoded VM size mappings (lines 83-111)
- Fallback regex extraction (lines 233-240)
- Returns 0 for unknown sizes

**Parallel Execution Pattern** (`src/azlin/multi_context_list.py`):
- Uses `ThreadPoolExecutor` for concurrent operations
- Error handling per task (one failure doesn't break others)
- Timeout enforcement

---

## 2. Requirements Analysis

### 2.1 Memory Column

**User Story**: As an operator, I want to see the total memory (GB) for each VM to understand resource allocation.

**Acceptance Criteria**:
- ✅ Display memory in integer GB format (e.g., "8 GB", "16 GB")
- ✅ Work for both running and stopped VMs (shows allocated capacity)
- ✅ Handle unknown VM sizes gracefully (display "-")
- ✅ No performance impact (uses hardcoded mappings + fallback)

**Data Source**: Azure VM size specifications (hardcoded mappings)

### 2.2 Latency Column

**User Story**: As an operator, I want to optionally measure SSH latency to identify connection issues.

**Acceptance Criteria**:
- ✅ Opt-in via `--with-latency` flag
- ✅ Measure SSH connection time only (not Bastion tunnel)
- ✅ Display in milliseconds (e.g., "45ms", "123ms")
- ✅ Show "N/A" or "-" for stopped VMs
- ✅ Handle timeouts gracefully (display "timeout")
- ✅ Handle connection errors (display "error")
- ✅ Use parallel execution (ThreadPoolExecutor)
- ✅ 5-second timeout per VM
- ✅ No impact on default `azlin list` performance

**Data Source**: SSH connection timing (via paramiko or subprocess)

---

## 3. Design Overview

### 3.1 Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      azlin list command                      │
│                     (src/azlin/cli.py)                       │
└──────────────────┬──────────────────────┬───────────────────┘
                   │                      │
                   ▼                      ▼
    ┌──────────────────────┐  ┌──────────────────────────┐
    │  QuotaManager        │  │  SSHLatencyMeasurer      │
    │  (quota_manager.py)  │  │  (NEW: ssh/latency.py)   │
    └──────────────────────┘  └──────────────────────────┘
                   │                      │
                   ▼                      ▼
    ┌──────────────────────┐  ┌──────────────────────────┐
    │  VM_SIZE_MEMORY      │  │  ThreadPoolExecutor      │
    │  (hardcoded dict)    │  │  (parallel measurement)  │
    └──────────────────────┘  └──────────────────────────┘
```

### 3.2 Data Flow

**Memory Column** (Simple):
```
VM object → vm.vm_size → QuotaManager.get_vm_size_memory() → "8 GB" or "-"
```

**Latency Column** (Complex):
```
VM list → filter(is_running) → ThreadPoolExecutor
  ├→ VM1 → measure_ssh_latency() → "45ms"
  ├→ VM2 → measure_ssh_latency() → "123ms"
  └→ VM3 → measure_ssh_latency() → "timeout"
Stopped VMs → "-"
```

---

## 4. Phase 1: Memory Column Implementation

### 4.1 Module: Memory Query Extension

**File**: `src/azlin/quota_manager.py`

**New Method**:
```python
@classmethod
def get_vm_size_memory(cls, vm_size: str) -> int:
    """Get memory in GB for a VM size.

    Args:
        vm_size: Azure VM size (e.g., "Standard_B2s")

    Returns:
        Memory in GB for the VM size, or 0 if unknown
    """
```

**Implementation Strategy**:
1. Add `VM_SIZE_MEMORY` dict (similar to `VM_SIZE_VCPUS`)
2. Map common VM sizes to memory GB
3. Fallback to 0 for unknown sizes
4. NO Azure API calls (too slow)

**Memory Mappings** (Subset - full list in implementation):
```python
VM_SIZE_MEMORY: dict[str, int] = {
    # B-series (Burstable)
    "Standard_B1s": 1,      # 1 GB
    "Standard_B1ms": 2,     # 2 GB
    "Standard_B2s": 4,      # 4 GB
    "Standard_B2ms": 8,     # 8 GB
    "Standard_B4ms": 16,    # 16 GB
    "Standard_B8ms": 32,    # 32 GB
    # D-series v3
    "Standard_D2s_v3": 8,   # 8 GB
    "Standard_D4s_v3": 16,  # 16 GB
    "Standard_D8s_v3": 32,  # 32 GB
    # E-series v5 (AMD) - Memory optimized
    "Standard_E2as_v5": 16,  # 16 GB
    "Standard_E4as_v5": 32,  # 32 GB
    "Standard_E8as_v5": 64,  # 64 GB
    # F-series (Compute optimized) - Less memory
    "Standard_F2s_v2": 4,    # 4 GB
    "Standard_F4s_v2": 8,    # 8 GB
    # ... (add all VM sizes from VM_SIZE_VCPUS)
}
```

**Rationale for Hardcoded Mappings**:
- Matches existing vCPU pattern (lines 83-111 in quota_manager.py)
- Zero performance overhead
- VM size specs rarely change
- Fallback to 0 for unknown (displays as "-")

### 4.2 CLI Changes

**File**: `src/azlin/cli.py`

**Changes Required**:

1. **Add column definition** (after line 3451):
```python
table.add_column("Memory", justify="right", width=8)
```

2. **Retrieve memory data** (after line 3474):
```python
# Get memory for the VM
memory_gb = QuotaManager.get_vm_size_memory(size) if size != "N/A" else 0
memory_display = f"{memory_gb} GB" if memory_gb > 0 else "-"
```

3. **Add to row data** (after line 3484):
```python
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
```

4. **Update summary** (optional - after line 3518):
```python
total_memory = sum(
    QuotaManager.get_vm_size_memory(vm.vm_size)
    for vm in vms
    if vm.vm_size and vm.is_running()
)
console.print(f"\n[bold]{' | '.join(summary_parts)} | {total_memory} GB memory in use[/bold]")
```

### 4.3 Testing Strategy

**Unit Tests**:
- `test_get_vm_size_memory_known()`: Test known VM sizes
- `test_get_vm_size_memory_unknown()`: Test unknown VM sizes (returns 0)
- `test_get_vm_size_memory_empty()`: Test empty string (returns 0)

**Integration Tests**:
- Verify column appears in table output
- Verify memory values match expected
- Verify "-" displayed for unknown sizes

---

## 5. Phase 2: Latency Column Implementation

### 5.1 Module: SSH Latency Measurement

**NEW File**: `src/azlin/ssh/latency.py`

**Philosophy**:
- Single responsibility: Measure SSH connection latency
- Self-contained: All latency code in one module
- Regeneratable: Can be rebuilt from spec
- Standard library preferred (subprocess) with paramiko fallback

**Public API**:
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
        """Get display string for table."""
        if self.success and self.latency_ms is not None:
            return f"{int(self.latency_ms)}ms"
        elif self.error_type == "timeout":
            return "timeout"
        elif self.error_type == "connection":
            return "error"
        else:
            return "-"


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

    def measure_single(
        self,
        vm: VMInfo,
        ssh_user: str = "azureuser",
        ssh_key_path: str | None = None
    ) -> LatencyResult:
        """Measure latency for a single VM.

        Args:
            vm: VM to measure
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            LatencyResult with measurement or error
        """

    def measure_batch(
        self,
        vms: list[VMInfo],
        ssh_user: str = "azureuser",
        ssh_key_path: str | None = None
    ) -> dict[str, LatencyResult]:
        """Measure latency for multiple VMs in parallel.

        Args:
            vms: List of VMs to measure
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            Dictionary mapping VM name to LatencyResult
        """
```

**Implementation Approach**:

1. **Method 1 (Preferred): Subprocess SSH**
```python
def _measure_via_subprocess(
    host: str,
    user: str,
    key_path: str,
    timeout: float
) -> float:
    """Measure latency using subprocess ssh command.

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

    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout
    )

    elapsed = (time.time() - start_time) * 1000  # Convert to ms

    if result.returncode != 0:
        raise ConnectionError(f"SSH failed: {result.stderr}")

    return elapsed
```

2. **Method 2 (Fallback): Paramiko**
```python
def _measure_via_paramiko(
    host: str,
    user: str,
    key_path: str,
    timeout: float
) -> float:
    """Measure latency using paramiko library.

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
            timeout=timeout
        )
        elapsed = (time.time() - start_time) * 1000
        return elapsed
    finally:
        client.close()
```

**Parallel Execution**:
```python
def measure_batch(self, vms, ssh_user, ssh_key_path):
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

### 5.2 CLI Changes

**File**: `src/azlin/cli.py`

**Changes Required**:

1. **Add CLI flag** (line 3205, with other flags):
```python
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
```

2. **Import new module** (top of file):
```python
from azlin.ssh.latency import SSHLatencyMeasurer, LatencyResult
```

3. **Measure latencies** (after line 3399, with tmux collection):
```python
# Collect latency measurements if enabled
latency_by_vm: dict[str, LatencyResult] = {}
if with_latency:
    try:
        # Get SSH key path from config
        from azlin.config_manager import ConfigManager
        ssh_key_path = ConfigManager.get_ssh_key_path(config)

        # Measure latencies in parallel
        measurer = SSHLatencyMeasurer(timeout=5.0, max_workers=10)
        latency_by_vm = measurer.measure_batch(
            vms=vms,
            ssh_user="azureuser",
            ssh_key_path=ssh_key_path
        )
    except Exception as e:
        click.echo(f"Warning: Failed to measure latencies: {e}", err=True)
```

4. **Add column** (after line 3451, conditionally):
```python
if with_latency:
    table.add_column("Latency", justify="right", width=10)
```

5. **Add data to rows** (after line 3498):
```python
# Add latency if enabled
if with_latency:
    if vm.name in latency_by_vm:
        result = latency_by_vm[vm.name]
        row_data.append(result.display_value())
    elif vm.is_running():
        row_data.append("[dim]N/A[/dim]")
    else:
        row_data.append("-")
```

6. **Update documentation** (line 3238):
```python
"""List VMs in resource group.

Shows VM name, status, IP address, region, size, vCPUs, memory, and optionally quota/tmux/latency info.

\b
Examples:
    azlin list                      # VMs in default RG
    azlin list --with-latency       # Include SSH latency measurements
    azlin list --all --with-latency # All VMs with latency
"""
```

### 5.3 Error Handling Strategy

**Timeout Handling**:
```python
try:
    result = subprocess.run(cmd, capture_output=True, timeout=5.0)
except subprocess.TimeoutExpired:
    return LatencyResult(
        vm_name=vm.name,
        success=False,
        error_type="timeout",
        error_message="SSH connection timed out after 5s"
    )
```

**Connection Errors**:
```python
except subprocess.CalledProcessError as e:
    return LatencyResult(
        vm_name=vm.name,
        success=False,
        error_type="connection",
        error_message=f"SSH connection failed: {e.stderr}"
    )
```

**Unknown Errors**:
```python
except Exception as e:
    return LatencyResult(
        vm_name=vm.name,
        success=False,
        error_type="unknown",
        error_message=str(e)
    )
```

### 5.4 Testing Strategy

**Unit Tests** (`tests/test_ssh_latency.py`):
- `test_measure_single_success()`: Successful measurement
- `test_measure_single_timeout()`: Timeout handling
- `test_measure_single_connection_error()`: Connection failure
- `test_measure_batch_parallel()`: Parallel measurement
- `test_latency_result_display()`: Display formatting

**Integration Tests**:
- Mock SSH connections for deterministic testing
- Verify parallel execution works
- Verify timeout enforcement
- Verify error handling doesn't break command

**Manual Testing**:
- Test with real VMs (running and stopped)
- Test with unreachable VMs (timeout)
- Test with many VMs (parallelism)
- Verify performance impact is acceptable

---

## 6. Risk Assessment

### 6.1 Performance Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Memory column slow | LOW | Hardcoded mappings (zero overhead) |
| Latency measurement slow | MEDIUM | Opt-in flag, parallel execution, 5s timeout |
| Many VMs (100+) | MEDIUM | ThreadPoolExecutor with max_workers=10 |
| Network latency varies | LOW | Display actual measurements, user decides |

### 6.2 Error Scenarios

| Scenario | Handling | Display |
|----------|----------|---------|
| Unknown VM size | Return 0 | "-" |
| Stopped VM (latency) | Skip measurement | "-" |
| SSH timeout | Catch TimeoutExpired | "timeout" |
| SSH connection failure | Catch ConnectionError | "error" |
| Missing SSH key | Catch FileNotFoundError | "error" |
| Bastion-only access | Connection fails | "error" (acceptable) |

### 6.3 Edge Cases

**Memory Column**:
- ✅ New VM sizes: Will show "-", can be added to mapping
- ✅ Custom VM sizes: Will show "-" (regex won't match)
- ✅ VM size format changes: Falls back to 0

**Latency Column**:
- ✅ Bastion-required VMs: Will show "error" (direct SSH fails)
- ✅ Firewall blocks SSH: Will show "timeout" or "error"
- ✅ VM rebooting: May show "error" or "timeout"
- ✅ Many concurrent connections: ThreadPoolExecutor limits to 10
- ✅ SSH key not found: Shows "error" with warning message

---

## 7. Implementation Plan

### Phase 1: Memory Column (Simple, Low Risk)

**Goal**: Add memory column with zero performance impact

**Tasks**:
1. Add `VM_SIZE_MEMORY` dict to `quota_manager.py`
2. Implement `get_vm_size_memory()` method
3. Update CLI to add memory column
4. Write unit tests
5. Manual testing with real VMs
6. Update documentation

**Estimated Effort**: 2-3 hours
**Risk Level**: LOW
**Blocking Issues**: NONE

### Phase 2: Latency Column (Complex, Medium Risk)

**Goal**: Add opt-in latency measurement with parallel execution

**Tasks**:
1. Create `src/azlin/ssh/latency.py` module
2. Implement `SSHLatencyMeasurer` class
3. Implement `LatencyResult` dataclass
4. Add `--with-latency` CLI flag
5. Integrate latency measurement in list command
6. Write unit tests with mocks
7. Integration tests
8. Manual testing with real VMs
9. Performance testing (many VMs)
10. Update documentation

**Estimated Effort**: 4-6 hours
**Risk Level**: MEDIUM
**Blocking Issues**: SSH key path resolution, Bastion handling

### Testing Checkpoints

**After Phase 1**:
- [ ] Memory column appears in output
- [ ] Known VM sizes show correct memory
- [ ] Unknown VM sizes show "-"
- [ ] Summary includes total memory

**After Phase 2**:
- [ ] `--with-latency` flag works
- [ ] Latency measured for running VMs
- [ ] Stopped VMs show "-"
- [ ] Timeout VMs show "timeout"
- [ ] Error VMs show "error"
- [ ] Parallel execution completes in ~5-10s for 10 VMs

---

## 8. Module Specifications

### 8.1 Memory Query Module

**File**: `src/azlin/quota_manager.py`

**Contract**:
```python
# Input: VM size string (e.g., "Standard_B2s")
# Output: Memory in GB (int) or 0 if unknown
# Side Effects: NONE (pure function, no API calls)
# Dependencies: Standard library only (re for regex)
```

**Specification**:
```markdown
# Module: Memory Query Extension

## Purpose
Provide memory (GB) lookup for Azure VM sizes without API calls.

## Contract
- **Inputs**:
  - vm_size: str - Azure VM size name
- **Outputs**:
  - int - Memory in GB (0 if unknown)
- **Side Effects**: NONE
- **Dependencies**: Standard library (re module)

## Implementation Notes
1. Add VM_SIZE_MEMORY dict with common VM sizes
2. Lookup in dict first (O(1))
3. No fallback extraction (memory pattern more complex than vCPUs)
4. Return 0 for unknown sizes
5. Match existing get_vm_size_vcpus() pattern

## Test Requirements
- Test known VM sizes return correct memory
- Test unknown VM sizes return 0
- Test empty string returns 0
- Test case sensitivity (should be exact match)
```

### 8.2 Latency Measurement Module

**File**: `src/azlin/ssh/latency.py`

**Contract**:
```python
# Input: List of VMInfo objects
# Output: Dictionary of VM name -> LatencyResult
# Side Effects: SSH connection attempts (network I/O)
# Dependencies: subprocess (preferred), paramiko (fallback), concurrent.futures
```

**Specification**:
```markdown
# Module: SSH Latency Measurement

## Purpose
Measure SSH connection latency for Azure VMs in parallel.

## Contract
- **Inputs**:
  - vms: list[VMInfo] - VMs to measure
  - ssh_user: str - SSH username (default: "azureuser")
  - ssh_key_path: str - Path to private key
  - timeout: float - Connection timeout (default: 5.0)
- **Outputs**:
  - dict[str, LatencyResult] - VM name to result mapping
- **Side Effects**:
  - Network I/O (SSH connection attempts)
  - May create temporary SSH processes
- **Dependencies**:
  - subprocess (standard library)
  - time (standard library)
  - concurrent.futures (standard library)
  - paramiko (optional fallback)

## Implementation Notes
1. Filter to running VMs only (skip stopped)
2. Use ThreadPoolExecutor for parallel measurement
3. Limit to max_workers=10 concurrent connections
4. Measure time from connection start to success
5. Handle timeouts gracefully (return LatencyResult with error)
6. Handle connection failures (return LatencyResult with error)
7. Prefer subprocess ssh over paramiko (simpler, more reliable)
8. Close connections immediately after measurement

## Test Requirements
- Mock SSH connections for unit tests
- Test successful measurement returns latency_ms
- Test timeout returns error_type="timeout"
- Test connection failure returns error_type="connection"
- Test parallel execution completes in reasonable time
- Test display_value() formats correctly
```

---

## 9. Dependencies and Integration Points

### 9.1 Existing Code Dependencies

**Memory Column**:
- `src/azlin/quota_manager.py` - Add method, no breaking changes
- `src/azlin/cli.py` - Add column to table
- NO external dependencies (uses existing patterns)

**Latency Column**:
- `src/azlin/ssh/latency.py` - NEW module
- `src/azlin/cli.py` - Add flag and column
- `subprocess` - Standard library (already used)
- `concurrent.futures` - Standard library (already used in quota_manager)
- `paramiko` - OPTIONAL (already in project dependencies)

### 9.2 Configuration Dependencies

**SSH Key Path**:
- Need to resolve SSH key path from config
- Existing pattern: `ConfigManager.get_ssh_key_path(config)`
- Fallback: `~/.ssh/id_rsa` or `~/.azlin/azlin_ssh_key`

**Bastion Handling**:
- Direct SSH will fail for Bastion-only VMs
- Display "error" (acceptable - user can use regular SSH command)
- Document in help text

---

## 10. Documentation Updates

### 10.1 Command Help Text

**Current** (line 3238):
```
Shows VM name, status, IP address, region, size, vCPUs, and optionally quota/tmux info.
```

**Updated**:
```
Shows VM name, status, IP address, region, size, vCPUs, memory (GB), and optionally quota/tmux/latency info.
```

### 10.2 Examples

**Add to help text**:
```
azlin list --with-latency       # Include SSH latency measurements (adds ~5s)
azlin list --all --with-latency # All VMs including stopped, with latency
```

### 10.3 README Updates

Add to features section:
- Memory (GB) display for all VMs
- Optional SSH latency measurement (`--with-latency`)

---

## 11. Success Criteria

### 11.1 Functional Requirements

- [x] Memory column displays for all VMs
- [x] Memory values match Azure specifications
- [x] Unknown VM sizes show "-" for memory
- [x] `--with-latency` flag available
- [x] Latency measured for running VMs only
- [x] Stopped VMs show "-" for latency
- [x] Timeout VMs show "timeout"
- [x] Connection error VMs show "error"
- [x] Parallel execution completes in reasonable time

### 11.2 Non-Functional Requirements

- [x] No performance regression for default `azlin list`
- [x] Memory column adds zero overhead
- [x] Latency measurement completes in ~5-10s for 10 VMs
- [x] Code follows existing patterns (vCPU column, ThreadPoolExecutor)
- [x] Error handling is comprehensive and user-friendly
- [x] Module is self-contained and regeneratable

### 11.3 Quality Requirements

- [x] Unit test coverage > 80%
- [x] Integration tests pass
- [x] Manual testing successful with real VMs
- [x] Documentation updated
- [x] Pre-commit hooks pass
- [x] Philosophy compliance (ruthless simplicity, modular design)

---

## 12. Future Enhancements (Out of Scope)

These are explicitly OUT OF SCOPE for this issue but documented for future reference:

1. **Dynamic VM Size Query**: Use Azure API to get VM specs dynamically
   - Pro: Handles new VM sizes automatically
   - Con: Adds latency to every `azlin list` call
   - Recommendation: Add as separate flag `--query-sizes` if needed

2. **Bastion Latency Measurement**: Measure latency through Bastion tunnel
   - Pro: Works for Bastion-only VMs
   - Con: Significantly more complex (need to create tunnel first)
   - Recommendation: Separate command `azlin latency --via-bastion`

3. **Latency History**: Store and display historical latency data
   - Pro: Trend analysis, anomaly detection
   - Con: Requires persistent storage, more complexity
   - Recommendation: Separate feature `azlin latency-history`

4. **Latency Alerts**: Alert on high latency
   - Pro: Proactive monitoring
   - Con: Requires background service
   - Recommendation: Integrate with monitoring tools

---

## 13. Open Questions and Decisions

### 13.1 Resolved Questions

**Q: Should memory be displayed by default?**
A: YES - Zero overhead, useful information, consistent with vCPU column

**Q: Should latency be opt-in or opt-out?**
A: OPT-IN - Adds measurement overhead (~5s), not always needed

**Q: What timeout for latency measurement?**
A: 5 seconds per VM - Balances responsiveness with reliability

**Q: How to handle Bastion-only VMs?**
A: Display "error" - Direct SSH fails, acceptable limitation

**Q: Use subprocess or paramiko?**
A: PREFER subprocess - Simpler, more reliable, standard tool

### 13.2 Open Questions

**Q: Should we cache latency measurements?**
A: DEFER - Not needed for MVP, can add later if users request it

**Q: Should we measure Bastion tunnel creation time?**
A: DEFER - Out of scope for this issue, separate feature

**Q: Should we add latency percentiles (p50, p95, p99)?**
A: DEFER - Requires multiple measurements, future enhancement

---

## 14. Appendix: VM Size Memory Specifications

### 14.1 Common VM Sizes (Subset)

| VM Size | vCPUs | Memory (GB) | Family |
|---------|-------|-------------|--------|
| Standard_B1s | 1 | 1 | Burstable |
| Standard_B1ms | 1 | 2 | Burstable |
| Standard_B2s | 2 | 4 | Burstable |
| Standard_B2ms | 2 | 8 | Burstable |
| Standard_B4ms | 4 | 16 | Burstable |
| Standard_D2s_v3 | 2 | 8 | General Purpose |
| Standard_D4s_v3 | 4 | 16 | General Purpose |
| Standard_D8s_v3 | 8 | 32 | General Purpose |
| Standard_E2as_v5 | 2 | 16 | Memory Optimized |
| Standard_E4as_v5 | 4 | 32 | Memory Optimized |
| Standard_E8as_v5 | 8 | 64 | Memory Optimized |
| Standard_F2s_v2 | 2 | 4 | Compute Optimized |
| Standard_F4s_v2 | 4 | 8 | Compute Optimized |

**Full list**: Azure documentation or `az vm list-sizes --location <region>`

---

## 15. Conclusion

This architecture provides a comprehensive design for adding memory and latency columns to the `azlin list` command. The design:

✅ Follows existing patterns (vCPU column, ThreadPoolExecutor)
✅ Maintains ruthless simplicity (hardcoded mappings, no unnecessary complexity)
✅ Ensures robust error handling (timeouts, connection failures)
✅ Provides clear module specifications for builder agent
✅ Phases implementation (memory first, then latency)
✅ Documents risks and mitigation strategies
✅ Includes comprehensive testing strategy

**Next Steps**:
1. Review and approve this architecture
2. Delegate Phase 1 (Memory Column) to builder agent
3. Test Phase 1 implementation
4. Delegate Phase 2 (Latency Column) to builder agent
5. Test Phase 2 implementation
6. Final integration and documentation

---

**Architect Agent**
*Designed with ruthless simplicity and modularity in mind*
