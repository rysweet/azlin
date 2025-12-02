"""VM Lifecycle Automation Module.

Provides automated health monitoring, self-healing, and lifecycle event hooks
for Azure VMs managed by azlin.

Core Components:
- LifecycleManager: Configuration and lifecycle management
- HealthMonitor: VM health checking
- SelfHealer: Automatic recovery actions
- HookExecutor: Lifecycle event hook execution
- LifecycleDaemon: Background monitoring process
- DaemonController: Daemon management interface
"""

from azlin.lifecycle.lifecycle_manager import (
    LifecycleManager,
    MonitoringConfig,
    MonitoringStatus,
    LifecycleConfigError,
    LIFECYCLE_CONFIG_PATH,
    VALID_RESTART_POLICIES,
    VALID_HOOK_TYPES,
)
from azlin.lifecycle.health_monitor import (
    HealthMonitor,
    HealthStatus,
    VMState,
    VMMetrics,
    HealthFailure,
    HealthCheckError,
)
from azlin.lifecycle.self_healer import (
    SelfHealer,
    RestartResult,
    SelfHealingError,
)
from azlin.lifecycle.hook_executor import (
    HookExecutor,
    HookResult,
    HookType,
    HookExecutionError,
)
from azlin.lifecycle.lifecycle_daemon import (
    LifecycleDaemon,
    DaemonStatus,
    DaemonError,
)
from azlin.lifecycle.daemon_controller import (
    DaemonController,
    ControllerError,
)

__all__ = [
    # Configuration
    "LifecycleManager",
    "MonitoringConfig",
    "MonitoringStatus",
    "LifecycleConfigError",
    "LIFECYCLE_CONFIG_PATH",
    "VALID_RESTART_POLICIES",
    "VALID_HOOK_TYPES",
    # Health Monitoring
    "HealthMonitor",
    "HealthStatus",
    "VMState",
    "VMMetrics",
    "HealthFailure",
    "HealthCheckError",
    # Self-Healing
    "SelfHealer",
    "RestartResult",
    "SelfHealingError",
    # Hooks
    "HookExecutor",
    "HookResult",
    "HookType",
    "HookExecutionError",
    # Daemon
    "LifecycleDaemon",
    "DaemonController",
    "DaemonStatus",
    "DaemonError",
    "ControllerError",
]
