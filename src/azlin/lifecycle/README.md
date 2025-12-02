# VM Lifecycle Automation Module

Automated health monitoring, self-healing, and lifecycle event hooks for Azure VMs managed by azlin.

## Philosophy

- **Ruthless Simplicity**: Clear, direct implementations without unnecessary abstraction
- **Bricks & Studs**: Self-contained modules with well-defined public APIs
- **Working Code Only**: No stubs or placeholders, every function works
- **Regeneratable**: Any module can be rebuilt from its specification

## Public API Overview

The lifecycle module provides **6 core components** with clean contracts:

| Component | Purpose | Public API |
|-----------|---------|------------|
| **LifecycleManager** | Configuration management | `enable_monitoring()`, `disable_monitoring()`, `get_monitoring_status()`, `list_monitored_vms()` |
| **HealthMonitor** | VM health checking | `check_vm_health()`, `get_health_history()`, `clear_health_history()` |
| **SelfHealer** | Automatic recovery | `should_restart()`, `restart_vm()`, `handle_failure()` |
| **HookExecutor** | Lifecycle event hooks | `execute_hook()`, `execute_hook_async()`, `validate_hook_script()` |
| **LifecycleDaemon** | Background monitoring | `start()`, `stop()`, `get_status()`, `reload_config()` |
| **DaemonController** | Daemon management | `start_daemon()`, `stop_daemon()`, `restart_daemon()`, `daemon_status()`, `show_logs()` |

## Core Components

### 1. LifecycleManager

**Purpose**: Manage VM lifecycle configurations

**Public API** (exported via `__all__`):
```python
from azlin.lifecycle import (
    LifecycleManager,
    MonitoringConfig,
    MonitoringStatus,
    LifecycleConfigError,
    LIFECYCLE_CONFIG_PATH,
    VALID_RESTART_POLICIES,
    VALID_HOOK_TYPES,
)
```

**Key Methods**:

```python
# Enable monitoring for a VM
config = MonitoringConfig(
    enabled=True,
    check_interval_seconds=60,
    restart_policy="on-failure",
    ssh_failure_threshold=3,
    hooks={"on_failure": "/path/to/alert.sh"}
)
manager.enable_monitoring("my-vm", config)

# Get monitoring status
status = manager.get_monitoring_status("my-vm")
print(f"Enabled: {status.enabled}")
print(f"Check interval: {status.config.check_interval_seconds}s")

# List all monitored VMs
vms = manager.list_monitored_vms()

# Disable monitoring
manager.disable_monitoring("my-vm")
```

**Configuration File**: `~/.azlin/lifecycle-config.toml`

**Data Models**:
- `MonitoringConfig`: Configuration for a single VM
- `MonitoringStatus`: Current monitoring status with config
- `LifecycleConfigError`: Configuration errors

### 2. HealthMonitor

**Purpose**: Check VM health via Azure API and SSH connectivity

**Public API**:
```python
from azlin.lifecycle import (
    HealthMonitor,
    HealthStatus,
    VMState,
    VMMetrics,
    HealthFailure,
    HealthCheckError,
)
```

**Key Methods**:

```python
monitor = HealthMonitor()

# Check VM health
health = monitor.check_vm_health("my-vm")
print(f"State: {health.state}")
print(f"SSH reachable: {health.ssh_reachable}")
print(f"Failures: {health.ssh_failures}")
if health.metrics:
    print(f"CPU: {health.metrics.cpu_percent}%")

# Get health history
history = monitor.get_health_history("my-vm")

# Clear health history
monitor.clear_health_history("my-vm")
```

**Data Models**:
- `HealthStatus`: Complete health check result
- `VMState`: Enum of VM states (RUNNING, STOPPED, etc.)
- `VMMetrics`: CPU, memory, disk metrics from SSH
- `HealthFailure`: Failure information for healing decisions
- `HealthCheckError`: Health check errors

**Health Tracking**:
- Maintains failure counters per VM
- Resets counters when VM becomes healthy
- Thread-safe for concurrent checks

### 3. SelfHealer

**Purpose**: Automatic VM recovery actions

**Public API**:
```python
from azlin.lifecycle import (
    SelfHealer,
    RestartResult,
    SelfHealingError,
)
```

**Key Methods**:

```python
healer = SelfHealer()

# Check if restart is needed
failure = HealthFailure(
    vm_name="my-vm",
    failure_count=3,
    reason="SSH connectivity lost"
)
should_restart = healer.should_restart("my-vm", failure)

# Restart VM
result = healer.restart_vm("my-vm")
if result.success:
    print(f"Restarted at: {result.timestamp}")
else:
    print(f"Failed: {result.error_message}")

# Handle failure (decides and acts)
healer.handle_failure("my-vm", failure)
```

**Restart Policies**:
- `never`: Never restart automatically
- `on-failure`: Restart when SSH failures exceed threshold
- `always`: Always restart on any health check failure

**Data Models**:
- `RestartResult`: Result of restart operation
- `SelfHealingError`: Self-healing errors

### 4. HookExecutor

**Purpose**: Execute lifecycle event hooks

**Public API**:
```python
from azlin.lifecycle import (
    HookExecutor,
    HookResult,
    HookType,
    HookExecutionError,
)
```

**Key Methods**:

```python
executor = HookExecutor()

# Execute hook synchronously
result = executor.execute_hook(
    HookType.ON_FAILURE,
    "my-vm",
    {"failure_count": 3, "reason": "SSH lost"}
)
print(f"Success: {result.success}")
print(f"Output: {result.stdout}")

# Execute hook asynchronously
executor.execute_hook_async(
    "on_healthy",
    "my-vm",
    {"state": "running"}
)

# Validate hook script
executor.validate_hook_script("/path/to/hook.sh")
```

**Hook Types**:
- `on_start`: VM starts
- `on_stop`: VM stops
- `on_restart`: VM restarts
- `on_failure`: Health check fails
- `on_healthy`: VM becomes healthy

**Hook Environment Variables**:
- `VM_NAME`: VM name
- `EVENT_TYPE`: Hook type
- `TIMESTAMP`: Event timestamp
- Additional context-specific variables

**Data Models**:
- `HookResult`: Hook execution result
- `HookType`: Enum of hook types
- `HookExecutionError`: Hook execution errors

### 5. LifecycleDaemon

**Purpose**: Background process for continuous VM monitoring

**Public API**:
```python
from azlin.lifecycle import (
    LifecycleDaemon,
    DaemonStatus,
    DaemonError,
)
```

**Key Methods**:

```python
daemon = LifecycleDaemon()

# Start daemon (blocking)
daemon.start()

# Stop daemon
daemon.stop()

# Get daemon status
status = daemon.get_status()
print(f"Running: {status.running}")
print(f"PID: {status.pid}")
print(f"Uptime: {status.uptime}")
print(f"Monitored VMs: {status.monitored_vms}")

# Reload configuration
daemon.reload_config()
```

**Daemon Configuration** (in lifecycle-config.toml):
```toml
[daemon]
pid_file = "~/.azlin/lifecycle-daemon.pid"
log_file = "~/.azlin/lifecycle-daemon.log"
log_level = "INFO"
```

**Monitoring Loop**:
1. Get all VMs with `enabled=True`
2. For each VM:
   - Check health
   - Trigger `on_healthy` or `on_failure` hooks
   - Self-heal if failure threshold reached
3. Sleep for minimum check interval
4. Repeat

**Signals**:
- `SIGTERM`: Graceful shutdown
- `SIGINT`: Graceful shutdown

**Data Models**:
- `DaemonStatus`: Current daemon status
- `DaemonError`: Daemon operation errors

### 6. DaemonController

**Purpose**: CLI interface for daemon management

**Public API**:
```python
from azlin.lifecycle import (
    DaemonController,
    ControllerError,
)
```

**Key Methods**:

```python
controller = DaemonController()

# Start daemon (background)
controller.start_daemon()

# Start daemon (foreground - for debugging)
controller.start_daemon(foreground=True)

# Stop daemon
controller.stop_daemon(timeout=10)

# Restart daemon
controller.restart_daemon()

# Get daemon status
status = controller.daemon_status()

# Show logs
controller.show_logs(lines=50)
controller.show_logs(follow=True)  # Like tail -f
```

**PID File Management**:
- Detects and removes stale PID files
- Prevents multiple daemon instances

**Graceful Shutdown**:
1. Send `SIGTERM`
2. Wait up to `timeout` seconds
3. Send `SIGKILL` if still running
4. Raise error if can't stop

**Data Models**:
- `ControllerError`: Daemon control errors

## Complete Example

```python
from azlin.lifecycle import (
    LifecycleManager,
    HealthMonitor,
    SelfHealer,
    DaemonController,
    MonitoringConfig,
)

# 1. Configure monitoring
manager = LifecycleManager()
config = MonitoringConfig(
    enabled=True,
    check_interval_seconds=60,
    restart_policy="on-failure",
    ssh_failure_threshold=3,
    hooks={
        "on_failure": "/usr/local/bin/alert-on-failure.sh",
        "on_healthy": "/usr/local/bin/alert-healthy.sh",
    }
)
manager.enable_monitoring("my-vm", config)

# 2. Manual health check (optional)
monitor = HealthMonitor()
health = monitor.check_vm_health("my-vm")
print(f"VM state: {health.state}, SSH: {health.ssh_reachable}")

# 3. Start daemon for continuous monitoring
controller = DaemonController()
controller.start_daemon()
print("Daemon started - monitoring in background")

# 4. Check daemon status
status = controller.daemon_status()
print(f"Monitoring {len(status.monitored_vms)} VMs")
print(f"Uptime: {status.uptime}")

# 5. View logs
controller.show_logs(lines=20)

# 6. Stop daemon when done
controller.stop_daemon()
```

## Configuration File Format

`~/.azlin/lifecycle-config.toml`:

```toml
[daemon]
pid_file = "~/.azlin/lifecycle-daemon.pid"
log_file = "~/.azlin/lifecycle-daemon.log"
log_level = "INFO"

[vms.my-vm]
enabled = true
check_interval_seconds = 60
restart_policy = "on-failure"
ssh_failure_threshold = 3

[vms.my-vm.hooks]
on_failure = "/usr/local/bin/alert-failure.sh"
on_healthy = "/usr/local/bin/alert-healthy.sh"
on_restart = "/usr/local/bin/alert-restart.sh"

[vms.another-vm]
enabled = true
check_interval_seconds = 120
restart_policy = "never"
```

## Hook Script Requirements

Hook scripts receive environment variables and must:

1. **Be executable**: `chmod +x hook-script.sh`
2. **Return 0 for success**: Non-zero exit codes logged as failures
3. **Handle signals**: Respond to SIGTERM for cleanup
4. **Complete quickly**: Timeout after 30 seconds

**Example hook script**:

```bash
#!/bin/bash
# on-failure.sh - Send alert when VM fails health check

VM_NAME="$VM_NAME"
FAILURE_COUNT="$FAILURE_COUNT"
REASON="$REASON"

# Send alert
curl -X POST https://alerts.example.com/vm-failure \
  -H "Content-Type: application/json" \
  -d "{\"vm\": \"$VM_NAME\", \"failures\": $FAILURE_COUNT, \"reason\": \"$REASON\"}"

exit 0
```

## Error Handling

All components follow consistent error handling:

- **Configuration errors**: Raise `LifecycleConfigError`
- **Health check errors**: Raise `HealthCheckError`
- **Self-healing errors**: Raise `SelfHealingError`
- **Hook execution errors**: Raise `HookExecutionError`
- **Daemon errors**: Raise `DaemonError`
- **Controller errors**: Raise `ControllerError`

All errors include descriptive messages for debugging.

## Testing

**Test Coverage**: 79% (89 tests passing)

**Test Pyramid** (60% unit, 30% integration, 10% E2E):
- Unit tests: Mock external dependencies, fast execution
- Integration tests: Multiple components, controlled environment
- E2E tests: Full workflows with actual processes

**Run tests**:
```bash
# All tests
pytest tests/lifecycle/

# With coverage
pytest tests/lifecycle/ --cov=src/azlin/lifecycle --cov-report=term-missing

# Specific component
pytest tests/lifecycle/test_daemon_integration.py
```

## Module Dependencies

**Internal**:
- `azlin.config`: Azure configuration
- `azlin.ssh`: SSH connectivity checking

**External** (standard library only for core):
- `pathlib`: File path handling
- `tomli`/`tomli_w`: TOML config parsing
- `dataclasses`: Data models
- `subprocess`: Process execution
- `signal`: Signal handling
- `logging`: Logging

**External (Azure SDK)**:
- `azure.identity`: Azure authentication
- `azure.mgmt.compute`: VM management

## Thread Safety

- **HealthMonitor**: Thread-safe (uses locks for failure counters)
- **LifecycleManager**: Thread-safe (file I/O uses atomic operations)
- **SelfHealer**: Thread-safe (stateless, delegates to Azure SDK)
- **HookExecutor**: Thread-safe (uses process isolation)
- **LifecycleDaemon**: Single-threaded (sequential monitoring loop)
- **DaemonController**: Thread-safe (uses PID file locking)

## Performance Characteristics

- **Health check latency**: 1-3 seconds (Azure API + SSH)
- **Hook execution timeout**: 30 seconds (configurable)
- **Daemon check interval**: 60 seconds (configurable per VM)
- **Restart operation**: 2-5 minutes (Azure VM restart time)
- **Config reload**: < 100ms (reads from disk)

## Limitations

- **Single daemon instance**: One daemon per machine (enforced by PID file)
- **SSH requirement**: Health checks require SSH connectivity
- **Azure VMs only**: Works only with Azure VMs, not other cloud providers
- **No remote daemon**: Daemon must run on same machine as azlin CLI

## Future Enhancements (Not Yet Implemented)

These are potential future improvements, not current capabilities:

- **Metrics collection**: Store health metrics in time-series database
- **Alert aggregation**: Batch multiple failures into single alert
- **Webhook support**: HTTP webhooks in addition to shell scripts
- **Multi-VM operations**: Restart multiple VMs in sequence
- **Health check plugins**: Custom health check implementations
- **Remote monitoring**: Monitor VMs from remote controller

## Troubleshooting

### Daemon won't start
- Check PID file: `cat ~/.azlin/lifecycle-daemon.pid`
- Remove stale PID file if process doesn't exist
- Check logs: `cat ~/.azlin/lifecycle-daemon.log`

### Health checks failing
- Verify Azure credentials: `az account show`
- Test SSH connectivity: `azlin ssh vm-name "echo test"`
- Check VM state in Azure Portal

### Hooks not executing
- Verify script is executable: `ls -l hook-script.sh`
- Test hook manually: `VM_NAME=test-vm ./hook-script.sh`
- Check daemon logs for hook execution errors

### High CPU usage
- Increase check intervals in config
- Reduce number of monitored VMs
- Check for slow hook scripts

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    LifecycleDaemon                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Monitoring Loop (every check_interval_seconds)     │   │
│  │  1. Get monitored VMs → LifecycleManager            │   │
│  │  2. Check health → HealthMonitor                    │   │
│  │  3. Trigger hooks → HookExecutor                    │   │
│  │  4. Self-heal if needed → SelfHealer               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │
                          │ Control
                          │
                    DaemonController
                    (start/stop/status)
```

## License

Part of azlin - Azure Linux VM management tool.
